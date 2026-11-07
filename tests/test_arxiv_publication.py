"""Exact version-one identity and original-day checks; no network needed."""
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from arxiv_publication import ArxivPublicationVerifier, identifier_for
from collection_window import weekly_eligible, previous_week


def atom(identifier='2610.12345v1', title='AI and cognitive offloading', published='2026-10-29T10:00:00Z'):
    return f'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
    <id>http://arxiv.org/abs/{identifier}</id><title>{title}</title>
    <published>{published}</published><updated>2026-11-04T12:00:00Z</updated>
    <summary>THIS MUST NEVER BE PERSISTED</summary></entry></feed>'''


def candidate(identifier='2610.12345'):
    return dict(doi='10.48550/arXiv.' + identifier, title='AI and cognitive offloading', source='OpenAlex', kind='scholarly')


class ArxivPublicationTests(unittest.TestCase):
    def test_exact_version_one_id_and_original_published_day(self):
        urls = []
        def fetch(url):
            urls.append(url); return atom()
        verifier = ArxivPublicationVerifier(fetch, sleep=Mock())
        day, evidence = verifier.verify(candidate())
        self.assertEqual(day, '2026-10-29')
        self.assertEqual(parse_qs(urlparse(urls[0]).query), {'id_list': ['2610.12345v1']})
        self.assertEqual(evidence['version_url'], 'https://arxiv.org/abs/2610.12345v1')
        self.assertNotIn('summary', str(evidence)); self.assertNotIn('THIS MUST', str(evidence))
        self.assertTrue(weekly_eligible(dict(candidate(), published=day, publication_date_provenance=evidence), *previous_week('2026-11-07')))

    def test_latest_version_title_change_is_held(self):
        verifier = ArxivPublicationVerifier(lambda url: atom(title='An earlier different title'), sleep=Mock())
        day, evidence = verifier.verify(candidate())
        self.assertEqual(day, ''); self.assertEqual(evidence['status'], 'conflict')

    def test_mismatched_or_unversioned_id_is_rejected(self):
        for identifier in ['2610.12345', '2610.12345v2', '2610.99999v1']:
            verifier = ArxivPublicationVerifier(lambda url: atom(identifier), sleep=Mock())
            self.assertEqual(verifier.verify(candidate())[0], '', identifier)

    def test_updated_does_not_substitute_missing_original_published(self):
        verifier = ArxivPublicationVerifier(lambda url: atom(published=''), sleep=Mock())
        self.assertEqual(verifier.verify(candidate())[0], '')
        verifier = ArxivPublicationVerifier(lambda url: atom(published='2026-10'), sleep=Mock())
        self.assertEqual(verifier.verify(candidate())[0], '')

    def test_cached_identifiers_and_serial_request_spacing(self):
        sleep = Mock(); urls = []
        def fetch(url):
            urls.append(url)
            return atom(parse_qs(urlparse(url).query)['id_list'][0])
        verifier = ArxivPublicationVerifier(fetch, limit=2, sleep=sleep)
        verifier.verify(candidate()); verifier.verify(candidate()); verifier.verify(candidate('2610.12346'))
        self.assertEqual(len(urls), 2); sleep.assert_called_once_with(3)
        self.assertEqual(verifier.verify(candidate('2610.12347'))[0], '')
        self.assertEqual(verifier.audit['deferred'], 1)

    def test_rate_limit_pauses_remaining_provider_calls(self):
        fetch = Mock(side_effect=HTTPError('https://export.arxiv.org', 429, 'Quota', None, None))
        verifier = ArxivPublicationVerifier(fetch, sleep=Mock())
        verifier.verify(candidate()); verifier.verify(candidate('2610.12346'))
        self.assertEqual(fetch.call_count, 1); self.assertEqual(verifier.audit['status'], 'partial')

    def test_general_datacite_or_journal_doi_is_not_misidentified(self):
        self.assertIsNone(identifier_for(dict(doi='10.5281/zenodo.12345')))
        self.assertIsNone(identifier_for(dict(doi='10.1234/journal', url='https://arxiv.org/abs/2610.12345')))
        self.assertEqual(identifier_for(dict(url='https://arxiv.org/abs/2610.12345v3')), '2610.12345')


if __name__ == '__main__':
    unittest.main()
