"""Exact reviewed copies are available without admitting a shared CDN wholesale."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import full_document_access as access


class ReviewedCopiesTests(unittest.TestCase):
    def test_shared_cdn_scope_is_exact_and_keeps_robots_check(self):
        url = ('https://static1.squarespace.com/static/57a40c19414fb54f51f8095f/'
               't/685daca461a93c25f5b3dabe/1750969509917/2019%2BFitz%2BBatching.pdf')
        self.assertTrue(access.safe_url(url))
        self.assertTrue(access.safe_url('https://static1.squarespace.com/robots.txt'))
        self.assertFalse(access.safe_url(url.replace('Batching.pdf', 'other.pdf')))
        self.assertFalse(access.safe_url('https://static1.squarespace.com/unrelated.pdf'))
        self.assertFalse(access.safe_url(url.replace('https://', 'http://')))
        self.assertFalse(access.safe_url(url.replace('static1.', 'evil.static1.')))
        with patch.object(access, 'robots_allowed', return_value=False), \
                patch.object(access, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'robots_disallow'):
                access.fetch_candidate({'url': url}, {'title': 'A verified article title'})
            request.assert_not_called()

    def test_recovered_copies_have_distinct_identity_versions_and_rights(self):
        expected = {
            '10.1016/j.chb.2019.07.016': ('static1.squarespace.com', None),
            '10.14742/ajet.11584': ('ajet.org.au', 'cc-by-nc-nd-4.0'),
            '10.1016/j.compedu.2025.105448': ('researchmgt.monash.edu', 'cc-by-4.0'),
        }
        for identifier, (host, license_value) in expected.items():
            record = next(x for x in json.loads(access.SOURCE_HINTS.read_text())['records']
                          if x.get('doi') == identifier)
            options = access.known_candidates(record)
            self.assertEqual(len(options), 1)
            option = options[0]
            self.assertEqual(option['doi'], identifier)
            self.assertEqual(option['version'], 'publishedVersion')
            self.assertEqual(option['license'], license_value)
            self.assertFalse(option['redistribution_granted'])
            self.assertTrue(option['url'].startswith('https://' + host + '/'))
            self.assertTrue(access.safe_url(option['url']))
            self.assertTrue(option['identity_verification_url'].startswith('https://'))
            self.assertIn('verification_note', record)

class SourcePilotTests(unittest.TestCase):
    def test_previous_portal_denial_is_retained_without_retry(self):
        import article_access_trials as trials
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            root = Path(directory); (root / 'data').mkdir()
            path = root / 'data/fulltext-access-tests.json'
            path.write_text(json.dumps({'checked_at': '2026-11-08T07:00:00Z', 'tests': [
                {'url': 'https://www.researchgate.net/publication/old', 'status': 'http_403'}]}))
            with patch.object(trials, 'ROOT', root):
                denied = trials.prior_access_denials()
                self.assertFalse(denied['www.researchgate.net']['network_attempted'])
                path.write_text(json.dumps({'checked_at': '2026-11-09T07:00:00Z', 'tests': [
                    {'url': 'https://www.researchgate.net/publication/old', **denied['www.researchgate.net']}]}))
                self.assertEqual(trials.prior_access_denials(), denied)

    def test_new_pilot_reports_access_not_summary_approval(self):
        import article_access_trials as trials
        document = access.Document([{'location': 'page:1', 'text': 'Test article body'}],
            'https://researchmgt.monash.edu/test.pdf', 'publishedVersion',
            {'evidence_status': 'full_document_retrieved', 'pages_total': 1,
             'pages_processed': 1, 'pages_with_text': 1})
        with patch.object(trials, 'fetch_candidate', return_value=document):
            rows = trials.recovered_source_pilot()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(row['fulltext_retrieved'] for row in rows))
        self.assertFalse(any(row['summary_completed'] for row in rows))
        self.assertTrue(all(row['all_retrieved_text_retained'] for row in rows))
        self.assertNotIn('Test article body', json.dumps(rows))


class TemporaryErrorPageTests(unittest.TestCase):
    def test_http_200_error_page_is_retryable_and_pauses_same_host(self):
        url = 'https://www.sciencedirect.com/science/article/pii/TEST'
        other = url + '2'
        record = {'title': 'An exact scientific article title long enough'}
        page = b'<html><head><title>Site Unavailable</title></head><body>Try later.</body></html>'
        with patch.object(access, 'robots_allowed', return_value=True), \
                patch.object(access, 'request', return_value=(page, url, 'text/html')) as request:
            doc, log = access.retrieve(record, providers=[], known_sources=[
                {'url': url}, {'url': other}])
        self.assertIsNone(doc)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(log[0]['status'], 'source_unavailable_page')
        self.assertTrue(log[0]['retryable'])
        self.assertEqual(log[1]['status'], 'rate_limit_pause')
        self.assertFalse(log[1]['network_attempted'])
        import collect_weekly_sources as weekly
        self.assertEqual(weekly.code(log[0]['status']), 'source_unavailable_page')

    def test_real_article_mentioning_unavailability_is_not_error_page(self):
        access.check_html_availability('<title>Study of source availability</title><p>Site unavailable</p>',
                                       'https://www.sciencedirect.com/article')


if __name__ == '__main__':
    unittest.main()
