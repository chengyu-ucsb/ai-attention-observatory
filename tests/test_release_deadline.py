import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_reader import encoded
from check_release_deadline import check
from verify_publication import BASE


class ReleaseDeadlineTests(unittest.TestCase):
    now = dt.datetime(2026, 11, 23, 16, 30, tzinfo=dt.timezone.utc)

    def fixture(self, tmp, format='compact'):
        root=Path(tmp); folder=root/'data/approved-issues'; folder.mkdir(parents=True)
        issue={'edition_date':'2026-11-23','status':'published','edition_format':format,
               'headline':'A checked synthesis','publication_window':{}}
        (folder/'2026-11-23.json').write_text(json.dumps(issue))
        digest=sha256(encoded(issue)).hexdigest()
        url=BASE+'issues/2026-11-23.html'
        manifest={'edition_id':'2026-11-23','edition_sha256':digest,'issue':issue,'index_url':'data/reader/index.json'}
        responses={BASE+'data/reader-manifest.json':encoded(manifest),
            url:('<meta name="observatory-edition-sha256" content="'+digest+'">A checked synthesis').encode(),
            BASE+'issue-feed.xml':('<rss><channel><item><guid>'+url+'</guid><link>'+url+'</link></item></channel></rss>').encode(),
            BASE+'data/issue-feed.json':encoded({'items':[{'id':url,'url':url,'_observatory':issue}]})}
        return root,responses

    def test_matching_live_archive_and_both_feeds_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,responses=self.fixture(tmp)
            result=check(root,self.now,responses.__getitem__)
            self.assertTrue(result['ready'])
            self.assertFalse(result['deadline_elapsed'])
            self.assertEqual(result['deadline'],'2026-11-23T12:00:00-05:00')
            responses[BASE+'data/issue-feed.json']=encoded({'items':[]})
            self.assertFalse(check(root,self.now,responses.__getitem__)['ready'])

    def test_coverage_is_failure_even_when_marked_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,responses=self.fixture(tmp,'coverage')
            self.assertEqual(check(root,self.now,responses.__getitem__)['status'],
                             'coverage_only_not_a_newsletter')

    def test_old_live_edition_and_missing_archive_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,responses=self.fixture(tmp)
            manifest=json.loads(responses[BASE+'data/reader-manifest.json'])
            manifest['edition_id']='2026-11-16'
            responses[BASE+'data/reader-manifest.json']=encoded(manifest)
            self.assertFalse(check(root,self.now,responses.__getitem__)['ready'])
            (root/'data/approved-issues/2026-11-23.json').unlink()
            self.assertEqual(check(root,self.now,responses.__getitem__)['status'],'missing_synthesis')

    def test_changed_saved_content_must_reach_the_live_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,responses=self.fixture(tmp)
            path=root/'data/approved-issues/2026-11-23.json'
            issue=json.loads(path.read_text());issue['headline']='Revised synthesis'
            path.write_text(json.dumps(issue))
            self.assertFalse(check(root,self.now,responses.__getitem__)['ready'])

    def test_network_failure_cannot_be_reported_as_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,_=self.fixture(tmp)
            def offline(url):raise OSError('offline')
            result=check(root,self.now,offline)
            self.assertFalse(result['ready'])
            self.assertEqual(result['status'],'live_verification_failed')

    def test_last_scheduled_draft_has_real_release_buffer(self):
        workflow=(ROOT/'.github/workflows/weekly-edition.yml').read_text()
        self.assertIn("cron: '17 4,7,9,16 * * 1'",workflow)
        limit=int(re.search(r'timeout-minutes: (\d+)',workflow).group(1))
        # 9:17 + the whole inference job cap + a 20-minute deployment budget
        # must finish at least an hour before the noon delivery.
        self.assertLessEqual(9*60+17+limit+20,11*60)
        prep=(ROOT/'.github/workflows/prepare-weekly-readings.yml').read_text()
        self.assertIn("cron: '17 14,18 * * 1'",prep)
        self.assertNotIn("cron: '17 6,18 * * *'",prep)


if __name__=='__main__':unittest.main()
