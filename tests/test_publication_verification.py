from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from build_newsletter import ATOM, CONTENT, json_feed, rss_item
from build_reader import encoded
from verify_publication import verify, BASE


class PublicationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.issue = {'edition_date': '2026-11-09', 'headline': 'What changed?',
                      'subject': 'The Attention Brief: What changed?', 'status': 'published',
                      'letter': 'These are the updated findings.',
                      'updated_at': '2026-11-09T19:00:00+00:00',
                      'publication_window': {'from': '2026-11-02', 'to': '2026-11-08'}}
        self.url = BASE + 'issues/2026-11-09.html'
        self.publish_fixture()

    def publish_fixture(self):
        digest = sha256(encoded(self.issue)).hexdigest()
        self.manifest = {'edition_id': self.issue['edition_date'], 'issue': self.issue,
                         'edition_sha256': digest, 'reader_sha256': digest,
                         'index_url': 'data/reader/indexes/a.json'}
        self.feed = ET.fromstring('<rss><channel/></rss>')
        self.feed.find('channel').append(rss_item(self.issue))
        self.json_feed = json_feed([self.issue])
        self.pages = {BASE + 'data/reader-manifest.json': encoded(self.manifest),
                      self.url: ('<meta name="observatory-edition-sha256" content="' + digest
                                 + '"><h1>What changed?</h1>').encode()}

    def verify(self):
        self.pages[BASE + 'issue-feed.xml'] = ET.tostring(self.feed)
        self.pages[BASE + 'data/issue-feed.json'] = encoded(self.json_feed)
        return verify(self.manifest, reader=self.pages.__getitem__, approved_issue=self.issue)

    def test_only_matching_live_manifest_permalink_and_feed_are_success(self):
        result = self.verify()
        self.assertEqual(result['status'], 'live_verified')
        self.assertEqual(result['edition_id'], '2026-11-09')
        self.feed.find('channel').clear()
        with self.assertRaisesRegex(ValueError, 'feed_entry_missing'):
            self.verify()

    def test_old_deployed_issue_is_not_new_publication_success(self):
        stale = deepcopy(self.manifest)
        stale['edition_id'] = '2026-11-07'
        self.pages[BASE + 'data/reader-manifest.json'] = encoded(stale)
        with self.assertRaisesRegex(ValueError, 'manifest_mismatch'):
            self.verify()

    def test_same_id_with_stale_json_content_is_not_publication_success(self):
        self.json_feed['items'][0]['content_html'] = '<p>Still preparing the issue.</p>'
        with self.assertRaisesRegex(ValueError, 'feed_content_mismatch'):
            self.verify()

    def test_stale_fields_under_current_rss_guid_are_rejected(self):
        first = self.feed.find('./channel/item')
        for field in ('title', 'description', 'pubDate', f'{{{ATOM}}}updated', f'{{{CONTENT}}}encoded'):
            with self.subTest(field=field):
                value = first.findtext(field)
                first.find(field).text = 'Previous edition copy'
                with self.assertRaisesRegex(ValueError, 'rss_feed_content_mismatch'):
                    self.verify()
                first.find(field).text = value

    def test_matching_edition_must_lead_both_feeds(self):
        older = dict(self.issue, edition_date='2026-11-02')
        self.feed.find('channel').insert(0, rss_item(older))
        with self.assertRaisesRegex(ValueError, 'missing_or_not_first'):
            self.verify()
        self.feed.find('channel').remove(self.feed.find('./channel/item'))
        self.json_feed['items'].insert(0, json_feed([older])['items'][0])
        with self.assertRaisesRegex(ValueError, 'feed_content_mismatch'):
            self.verify()

    def test_stale_reader_projection_is_rejected_even_if_archive_id_matches(self):
        stale = deepcopy(self.manifest)
        stale['issue']['headline'] = 'Old reader copy'
        stale['reader_sha256'] = sha256(encoded(stale['issue'])).hexdigest()
        self.pages[BASE + 'data/reader-manifest.json'] = encoded(stale)
        with self.assertRaisesRegex(ValueError, 'deployed_reader_hash_invalid'):
            self.verify()

    def test_retained_legacy_feed_identity_requires_canonical_monday_link(self):
        legacy = BASE + 'issues/2026-11-13.html'
        self.issue['feed_id'] = legacy
        self.publish_fixture()
        self.assertEqual(self.verify()['status'], 'live_verified')
        self.assertEqual(self.feed.findtext('./channel/item/guid'), legacy)
        self.json_feed['items'][0]['url'] = legacy
        with self.assertRaisesRegex(ValueError, 'feed_content_mismatch'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
