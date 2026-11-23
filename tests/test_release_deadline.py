import datetime as dt
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import Mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_newsletter import json_feed, rss_item
from build_reader import encoded
from check_release_deadline import check, recover
from verify_publication import BASE


class ReleaseDeadlineTests(unittest.TestCase):
    now = dt.datetime(2026, 11, 23, 16, 30, tzinfo=dt.timezone.utc)

    def fixture(self, tmp):
        root=Path(tmp); folder=root/'data/approved-issues'; folder.mkdir(parents=True)
        issue={'edition_date':'2026-11-23','status':'published','edition_format':'compact',
               'subject':'A checked synthesis','headline':'A checked synthesis','publication_window':{}}
        (folder/'2026-11-23.json').write_text(json.dumps(issue))
        digest=sha256(encoded(issue)).hexdigest()
        url=BASE+'issues/2026-11-23.html'
        manifest={'edition_id':'2026-11-23','edition_sha256':digest,'reader_sha256':digest,'issue':issue,'index_url':'data/reader/index.json'}
        rss=ET.fromstring('<rss><channel/></rss>')
        rss.find('channel').append(rss_item(issue))
        responses={BASE+'data/reader-manifest.json':encoded(manifest),
            url:('<meta name="observatory-edition-sha256" content="'+digest+'">A checked synthesis').encode(),
            BASE+'issue-feed.xml':ET.tostring(rss),
            BASE+'data/issue-feed.json':encoded(json_feed([issue]))}
        return root,responses

    def test_matching_live_archive_and_both_feeds_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,responses=self.fixture(tmp)
            result=check(root,self.now,responses.__getitem__)
            self.assertTrue(result['ready'])
            self.assertFalse(result['deadline_elapsed'])
            self.assertEqual(result['deadline'],'2026-11-23T12:00:00-05:00')
            responses[BASE+'data/issue-feed.json']=encoded({'items':[]})
            self.assertEqual(check(root,self.now,responses.__getitem__)['status'], 'live_content_mismatch')

    def test_coverage_is_failure_even_when_marked_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,responses=self.fixture(tmp)
            path=root/'data/approved-issues/2026-11-23.json'
            issue=json.loads(path.read_text()); issue['edition_format']='coverage'
            path.write_text(json.dumps(issue))
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

    def test_one_redeploy_for_stale_leading_guid_then_verify_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, responses = self.fixture(tmp)
            original = responses[BASE+'issue-feed.xml']
            rss = ET.fromstring(original)
            rss.find('./channel/item/guid').text = 'previous-week'
            responses[BASE+'issue-feed.xml'] = ET.tostring(rss)
            read = lambda: check(root, self.now, responses.__getitem__)
            stale = read()
            self.assertEqual(stale['status'], 'live_content_mismatch')
            dispatch = Mock()
            # Simulate a dispatch taking one poll to become visible in Actions.
            pauses = 0
            def advance(seconds):
                nonlocal pauses
                pauses += 1
                if pauses == 2:
                    responses[BASE+'issue-feed.xml'] = original
            self.assertTrue(recover(stale, read=read, runs=lambda date: [],
                                    dispatch=dispatch, pause=advance)['ready'])
            dispatch.assert_called_once_with(stale['recovery_key'])

    def test_existing_deployment_and_prior_recovery_are_not_dispatched_again(self):
        stale = {'edition_date': '2026-11-23', 'status': 'live_content_mismatch', 'recovery_key': 'key'}
        dispatch = Mock()
        ready = {'ready': True}
        active = lambda date: [{'display_title': 'Deploy', 'status': 'in_progress'}]
        self.assertEqual(recover(stale, read=lambda: ready, runs=active, dispatch=dispatch,
                                 pause=lambda seconds: None), ready)
        finished = lambda date: [{'display_title': 'Restore edition key', 'status': 'completed'}]
        self.assertEqual(recover(stale, read=lambda: stale, runs=finished, dispatch=dispatch), stale)
        dispatch.assert_not_called()

    def test_network_errors_and_unfinished_editions_never_contact_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, responses = self.fixture(tmp)
            lookup = Mock()
            for suffix, error_body in [
                    ('data/reader-manifest.json', b'malformed-json'),
                    ('data/reader-manifest.json', b'{"error":"rate limited"}'),
                    ('issues/2026-11-23.html', b'<html>temporarily unavailable</html>'),
                    ('issue-feed.xml', b'<error>try later</error>'),
                    ('data/issue-feed.json', b'{"error":"upstream offline"}')]:
                with self.subTest(suffix=suffix):
                    faulty = dict(responses, **{BASE + suffix: error_body})
                    result = check(root, self.now, faulty.__getitem__)
                    self.assertEqual(recover(result, runs=lookup)['status'], 'live_verification_failed')
            path = root/'data/approved-issues/2026-11-23.json'
            issue = json.loads(path.read_text())
            issue['synthesis_current'] = False
            path.write_text(json.dumps(issue))
            self.assertEqual(recover(check(root, self.now, responses.__getitem__), runs=lookup)['status'],
                             'unpublished_or_wrong_edition')
            path.unlink()
            self.assertEqual(recover(check(root, self.now, responses.__getitem__), runs=lookup)['status'],
                             'missing_synthesis')
            lookup.assert_not_called()

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
