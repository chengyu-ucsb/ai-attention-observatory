"""Regression tests for locator coverage, fairness and per-run access stops."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import full_document_access as access
from crossref_locations import crossref_candidates
from structured_article_access import openalex_candidates


class LocationTests(unittest.TestCase):
    def test_crossref_exact_doi_links_and_primary_are_distinct_from_access(self):
        payload = {'message': {'DOI': '10.5555/test', 'link': [
            {'URL': 'https://www.econstor.eu/a.pdf', 'content-version': 'am',
             'intended-application': 'text-mining', 'content-type': 'application/pdf'},
            {'URL': 'https://www.econstor.eu/a.pdf'},
            {'URL': 'https://www.econstor.eu/a.pdf?token=SECRET'},
            {'URL': 'http://www.econstor.eu/insecure.pdf'}],
            'resource': {'primary': {'URL': 'https://www.econstor.eu/article'}}}}
        rows = crossref_candidates('10.5555/test', get=lambda _: payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['version'], 'acceptedVersion')
        self.assertEqual(rows[0]['declared_link_purpose'], 'text-mining')
        self.assertIsNone(rows[0]['license'])
        self.assertFalse(rows[0]['redistribution_granted'])
        self.assertNotIn('SECRET', json.dumps(rows))
        with self.assertRaisesRegex(ValueError, 'identity_mismatch'):
            crossref_candidates('10.5555/other', get=lambda _: payload)

    def test_openalex_uses_oa_locations_even_without_content_xml(self):
        payload = {'id': 'https://openalex.org/W123', 'doi': 'https://doi.org/10.5555/test',
                   'open_access': {'is_oa': True}, 'locations': [
                       {'is_oa': True, 'pdf_url': 'https://www.econstor.eu/paper.pdf',
                        'landing_page_url': 'https://www.econstor.eu/article',
                        'version': 'acceptedVersion', 'license': 'cc-by-nc'},
                       {'is_oa': False, 'pdf_url': 'https://www.econstor.eu/closed.pdf'},
                       {'is_oa': True, 'pdf_url': 'https://www.econstor.eu/private.pdf?api_key=SECRET'}]}
        with patch.dict('os.environ', {'OPENALEX_API_KEY': 'PRIVATE_FIXTURE'}):
            rows = openalex_candidates('10.5555/test', get=lambda _: payload)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['version'], 'acceptedVersion')
        self.assertEqual(rows[0]['license'], 'cc-by-nc')
        self.assertFalse(rows[0]['redistribution_granted'])
        self.assertNotIn('PRIVATE_FIXTURE', json.dumps(rows))
        self.assertNotIn('SECRET', json.dumps(rows))

    def test_pdf_typography_is_normalized_without_fuzzy_matching(self):
        record = {'title': 'Effects of cognitive offloading in scientific inquiry'}
        self.assertTrue(access.identity_matches(record, 'Eﬀects of cognitive oﬄoading in scientiﬁc inquiry'))
        self.assertFalse(access.identity_matches(record, 'Effects of cognitive offloading in social inquiry'))


class FairRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.record = {'doi': '10.5555/test', 'title': 'An exact title for a scholarly publication'}
        self.pdf = 'https://www.econstor.eu/paper.pdf'
        self.document = access.Document([{'location': 'page:1', 'text': 'body'}], self.pdf,
                                         coverage={'evidence_status': 'full_document_retrieved'})

    def test_unapproved_locations_do_not_exhaust_the_document_budget(self):
        unapproved = Mock(return_value=[access.candidate('https://unreviewed.example/' + str(n), 'unknown',
                                                       self.record['doi']) for n in range(12)])
        good = Mock(return_value=[access.candidate(self.pdf, 'repository', self.record['doi'])])
        with patch.object(access, 'fetch_candidate', return_value=self.document) as fetch, patch.object(access.time, 'sleep'):
            result, log = access.retrieve(self.record, max_candidates=1,
                                         providers=[('unapproved', unapproved), ('good', good)])
        self.assertIs(result, self.document)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(sum(x['status'] == 'host_requires_review' for x in log), 12)
        self.assertFalse(any(x.get('status') == 'candidate_budget_exhausted' for x in log))

    def test_provider_cannot_consume_all_attempts_before_later_repository(self):
        many = [access.candidate('https://www.microsoft.com/paper' + str(n) + '.pdf', 'many',
                                 self.record['doi']) for n in range(10)]
        def fetch(option, _):
            if option['url'] == self.pdf: return self.document
            raise ValueError('document_identity_unverified')
        with patch.object(access, 'fetch_candidate', side_effect=fetch) as getter, patch.object(access.time, 'sleep'):
            result, _ = access.retrieve(self.record, max_candidates=3,
                providers=[('many', lambda _: many), ('good', lambda _: [access.candidate(self.pdf, 'repo', self.record['doi'])])])
        self.assertIs(result, self.document)
        self.assertEqual(getter.call_count, 2)

    def test_deferred_provider_candidates_are_used_if_budget_remains(self):
        rows = [access.candidate('https://www.econstor.eu/' + str(n) + '.pdf', 'repo',
                                self.record['doi']) for n in range(3)]
        with patch.object(access, 'fetch_candidate', side_effect=[ValueError('not_pdf'), ValueError('not_pdf'), self.document]), patch.object(access.time, 'sleep'):
            result, _ = access.retrieve(self.record, max_candidates=3, providers=[('repo', lambda _: rows)])
        self.assertIs(result, self.document)

    def test_access_denial_stops_host_but_independent_repository_still_works(self):
        first = 'https://www.microsoft.com/denied.pdf'
        other = 'https://www.microsoft.com/alternate.pdf'
        record = {**self.record, 'fulltext_candidates': [{'url': first}, {'url': other}, {'url': self.pdf}]}
        with patch.object(access, 'fetch_candidate', side_effect=[HTTPError(first, 403, 'denied', {}, None), self.document]) as fetch:
            result, log = access.retrieve(record, providers=[])
        self.assertIs(result, self.document)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn('host_access_denied_this_run', [x['status'] for x in log])
        # The scoped failure never leaks into another, later retrieval run.
        with patch.object(access, 'fetch_candidate', return_value=self.document) as fetch:
            access.retrieve({**self.record, 'fulltext_candidates': [{'url': first}]}, providers=[])
        fetch.assert_called_once()

    def test_retry_after_stops_further_requests_to_same_host(self):
        first = 'https://www.microsoft.com/limited.pdf'
        record = {**self.record, 'fulltext_candidates': [{'url': first},
                  {'url': 'https://www.microsoft.com/other.pdf'}, {'url': self.pdf}]}
        with patch.object(access, 'fetch_candidate', side_effect=[HTTPError(first, 429, 'limited', {'Retry-After': '7200'}, None), self.document]) as fetch:
            result, log = access.retrieve(record, providers=[])
        self.assertIs(result, self.document)
        self.assertEqual(fetch.call_count, 2)
        pause = next(x for x in log if x['status'] == 'rate_limit_pause')
        self.assertGreaterEqual(pause['retry_after_seconds'], 7199)


if __name__ == '__main__':
    unittest.main()
