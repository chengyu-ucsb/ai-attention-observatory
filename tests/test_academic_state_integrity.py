"""Checkpoints cannot smuggle unknown data or change saved query identities."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from academic_state import DiscoveryState, cursor_search
from academic_state_schema import digest
from collection_window import crossref_publication

WINDOW = {'from': '2026-10-26', 'to': '2026-11-01'}
PARAMS = {'query.title': 'AI attention'}
WORK = {'DOI': '10.1234/a', 'title': ['AI attention'], 'type': 'journal-article',
        'published': {'date-parts': [[2026, 10, 29]]}, 'author': [{'given': 'A', 'family': 'Researcher'}]}
OA = {'id': 'https://openalex.org/W1', 'doi': 'https://doi.org/10.1234/a', 'title': 'AI attention',
      'publication_date': '2026-10-29', 'primary_location': {'source': {'display_name': 'Journal'}},
      'authorships': [{'author': {'display_name': 'A Researcher'}}]}


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'state.json'
        self.state = DiscoveryState(self.path, window=WINDOW, now=lambda: 1804500000, minimum_interval=0)
        self.state.register_plan('general', [('Crossref', PARAMS, 100), ('OpenAlex', {'search': 'AI attention'}, 100)])
        cursor_search(lambda _: {'message': {'items': [copy.deepcopy(WORK)], 'total-results': 1}}, 'Crossref', PARAMS, state=self.state)
        cursor_search(lambda _: {'results': [copy.deepcopy(OA)], 'meta': {'count': 1}}, 'OpenAlex', {'search': 'AI attention'}, state=self.state)
        self.state.current['date_evidence']['10.1234/a'] = crossref_publication(WORK)
        self.state.data['providers']['Crossref'].update(next_retry_at=1804503600, last_http_status=429, consecutive_failures=1)
        self.state.save()
        self.valid = json.loads(self.path.read_text())
        self.window_id = self.state.window_id
        self.query_id = self.state.query_id('Crossref', PARAMS, 100)
        self.oa_id = self.state.query_id('OpenAlex', {'search': 'AI attention'}, 100)

    def query(self, data): return data['windows'][self.window_id]['queries'][self.query_id]
    def window(self, data): return data['windows'][self.window_id]
    def row(self, data): return next(iter(self.query(data)['rows'].values()))
    def oa_row(self, data): return next(iter(self.window(data)['queries'][self.oa_id]['rows'].values()))

    def rejected(self, data):
        serialized = json.dumps(data)
        self.path.write_text(serialized)
        with self.assertRaises(ValueError) as error: DiscoveryState(self.path, window=WINDOW)
        self.assertNotIn('PRIVATE', str(error.exception)); self.assertNotIn('SECRET_VALUE', str(error.exception))
        self.assertEqual(self.path.read_text(), serialized)

    def test_unknown_fields_rejected_at_every_nested_boundary(self):
        modifications = [
            lambda d: d.update(source_body='PRIVATE BODY'),
            lambda d: d['providers']['Crossref'].update(api_key='SECRET_VALUE'),
            lambda d: self.window(d).update(source_body='PRIVATE BODY'),
            lambda d: self.window(d)['window'].update(source_body='PRIVATE BODY'),
            lambda d: self.window(d)['plans']['general'].update(article_body='PRIVATE BODY'),
            lambda d: self.query(d).update(article_body='PRIVATE BODY'),
            lambda d: self.query(d)['params'].update(api_key='SECRET_VALUE'),
            lambda d: self.row(d).update(article_body='PRIVATE BODY'),
            lambda d: self.row(d)['published'].update(article_body='PRIVATE BODY'),
            lambda d: self.row(d)['author'][0].update(api_key='SECRET_VALUE'),
            lambda d: self.oa_row(d)['primary_location']['source'].update(api_key='SECRET_VALUE'),
            lambda d: self.oa_row(d)['authorships'][0]['author'].update(article_body='PRIVATE BODY'),
            lambda d: self.window(d)['date_evidence']['10.1234/a'][1].update(article_body='PRIVATE BODY'),
            lambda d: self.window(d)['date_evidence']['10.1234/a'][1]['evidence'][0].update(source_body='PRIVATE BODY'),
        ]
        for index, mutate in enumerate(modifications):
            with self.subTest(index=index):
                data = copy.deepcopy(self.valid); mutate(data)
                # Recompute row keys so nested-schema rejection is independently tested.
                for query in self.window(data)['queries'].values():
                    query['rows'] = {digest(row): row for row in query['rows'].values()}
                self.rejected(data)

    def test_saved_query_fingerprint_recomputed_for_params_provider_and_size(self):
        for field, changed in [('params', {'query.title': 'different query'}), ('provider', 'OpenAlex'), ('page_size', 50)]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.valid); self.query(data)[field] = changed
                self.rejected(data)

    def test_saved_row_digest_recomputed(self):
        data = copy.deepcopy(self.valid); self.row(data)['title'] = ['Changed AI attention title']
        self.rejected(data)

    def test_window_identity_cannot_be_relabelled(self):
        data = copy.deepcopy(self.valid); self.window(data)['window']['from'] = '2026-11-02'
        self.rejected(data)
        data = copy.deepcopy(self.valid); self.window(data)['mode'] = 'backfill'
        self.rejected(data)

    def test_invalid_provider_numbers_never_reset_cooldowns(self):
        for field, value in [('next_retry_at', 'soon'), ('next_retry_at', float('nan')), ('next_retry_at', float('inf')),
                             ('next_retry_at', -1), ('last_request_at', True), ('consecutive_failures', 0.5),
                             ('last_http_status', '429'), ('blocked', 'yes')]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.valid); data['providers']['Crossref'][field] = value
                self.rejected(data)

    def test_unknown_provider_and_invalid_nested_types_rejected(self):
        modifications = [
            lambda d: d['providers'].update(unexpected={'api_key': 'SECRET_VALUE'}),
            lambda d: self.query(d).update(provider=[]),
            lambda d: self.query(d).update(pages=True),
            lambda d: self.query(d).update(status={}),
            lambda d: self.query(d).update(seen_cursors=['same', 'same']),
            lambda d: self.row(d)['author'][0].update(given={'source_body': 'PRIVATE BODY'}),
            lambda d: self.row(d)['published'].update(**{'date-parts': [['PRIVATE BODY']]}),
            lambda d: self.window(d)['date_evidence']['10.1234/a'][1].update(source={'api_key': 'SECRET_VALUE'}),
            lambda d: self.window(d)['date_evidence']['10.1234/a'][1].update(value='2026-10-30'),
        ]
        for index, mutate in enumerate(modifications):
            with self.subTest(index=index):
                data = copy.deepcopy(self.valid); mutate(data); self.rejected(data)

    def test_date_evidence_semantics_cannot_claim_unproven_original_event(self):
        for change in ({'field': 'published-online'}, {'policy': 'trust any date'}, {'status': 'conflict'},
                       {'source_url': 'https://example.test/?api_key=SECRET_VALUE'},
                       {'evidence': [{'field': 'published', 'precision': 'day', 'date_parts': [2026, 10, 30]}]}):
            with self.subTest(change=change):
                data = copy.deepcopy(self.valid)
                self.window(data)['date_evidence']['10.1234/a'][1].update(change)
                self.rejected(data)

    def test_arxiv_evidence_is_bound_to_saved_identifier_title_and_raw_day(self):
        state = DiscoveryState(Path(self.tmp.name) / 'arxiv.json', window=WINDOW)
        work = dict(OA, doi='https://doi.org/10.48550/arxiv.2610.12345')
        cursor_search(lambda _: {'results': [work], 'meta': {'count': 1}}, 'OpenAlex', {'search': 'arxiv AI attention'}, state=state)
        proof = {'source': 'Official arXiv Atom metadata', 'status': 'day_known', 'basis': 'arxiv_first_submitted',
                 'field': 'published', 'requested_id': '2610.12345v1', 'value': '2026-10-29',
                 'source_url': 'https://export.arxiv.org/api/query?id_list=2610.12345v1',
                 'version_url': 'https://arxiv.org/abs/2610.12345v1',
                 'source_id': 'http://arxiv.org/abs/2610.12345v1', 'raw': '2026-10-29T12:00:00Z'}
        state.current['arxiv_date_evidence'] = {'2610.12345:AI attention': ['2026-10-29', proof]}
        state.save(); self.assertEqual(DiscoveryState(state.path, window=WINDOW).current, state.current)
        valid = json.loads(state.path.read_text())
        for change in ('title', 'identifier', 'raw', 'source_body'):
            with self.subTest(change=change):
                data = copy.deepcopy(valid); cache = self.window(data)['arxiv_date_evidence']
                if change in {'title', 'identifier'}:
                    value = cache.pop('2610.12345:AI attention')
                    cache['2610.12345:Different title' if change == 'title' else '2610.99999:AI attention'] = value
                elif change == 'raw': cache['2610.12345:AI attention'][1]['raw'] = '2026-10-30T12:00:00Z'
                else: cache['2610.12345:AI attention'][1]['source_body'] = 'PRIVATE BODY'
                self.rejected(data)

    def test_duplicate_json_keys_are_rejected_without_overwrite(self):
        contents = '{"schema_version":1,"schema_version":1,"providers":{},"windows":{}}'
        self.path.write_text(contents)
        with self.assertRaises(ValueError): DiscoveryState(self.path, window=WINDOW)
        self.assertEqual(self.path.read_text(), contents)

    def test_valid_cooldown_and_completed_queries_survive_reload(self):
        state = DiscoveryState(self.path, window=WINDOW, now=lambda: 1804500100)
        self.assertEqual(state.data['providers']['Crossref']['next_retry_at'], 1804503600)
        rows, audit, errors = cursor_search(lambda _: self.fail('Completed query re-requested'), 'Crossref', PARAMS, state=state)
        self.assertEqual(len(rows), 1); self.assertEqual(audit['status'], 'complete'); self.assertFalse(errors)
        state.save()
        self.assertEqual(json.loads(self.path.read_text()), self.valid)

    def test_in_memory_injection_cannot_be_saved_exposed_or_used_for_requests(self):
        before = self.path.read_text()
        self.state.data['providers']['Crossref']['api_key'] = 'SECRET_VALUE'
        for operation in (self.state.save, self.state.summary,
                          lambda: self.state.fetch('Crossref', 'https://example.test', lambda _: self.fail('Unexpected request')),
                          lambda: cursor_search(lambda _: self.fail('Unexpected replay'), 'Crossref', PARAMS, state=self.state)):
            with self.assertRaises(ValueError): operation()
        self.assertEqual(self.path.read_text(), before)

    def test_new_provider_projection_strips_nested_body_and_credentials(self):
        work = copy.deepcopy(WORK)
        work['article_body'] = 'PRIVATE BODY'
        work['published']['article_body'] = 'PRIVATE BODY'
        work['published']['api_key'] = 'SECRET_VALUE'
        work['author'][0]['api_key'] = 'SECRET_VALUE'
        other = DiscoveryState(Path(self.tmp.name) / 'other.json', window=WINDOW)
        rows, audit, errors = cursor_search(lambda _: {'message': {'items': [work], 'total-results': 1}}, 'Crossref', PARAMS, state=other)
        self.assertFalse(errors); self.assertEqual(audit['status'], 'complete')
        self.assertEqual(rows[0], WORK)
        contents = other.path.read_text()
        self.assertNotIn('PRIVATE BODY', contents); self.assertNotIn('SECRET_VALUE', contents)
        self.assertEqual(DiscoveryState(other.path, window=WINDOW).current, other.current)

    def test_new_provider_abstract_object_is_not_stringified_into_public_state(self):
        work = copy.deepcopy(WORK); work['abstract'] = {'source_body': 'PRIVATE BODY'}
        other = DiscoveryState(Path(self.tmp.name) / 'other.json', window=WINDOW)
        rows, audit, errors = cursor_search(lambda _: {'message': {'items': [work], 'total-results': 1}}, 'Crossref', PARAMS, state=other)
        self.assertFalse(rows); self.assertTrue(errors); self.assertEqual(audit['status'], 'error')
        self.assertNotIn('PRIVATE BODY', other.path.read_text())

    def test_new_provider_nested_nonmetadata_value_is_rejected(self):
        work = copy.deepcopy(WORK)
        work['published']['date-parts'] = [[{'article_body': 'PRIVATE BODY'}]]
        other = DiscoveryState(Path(self.tmp.name) / 'other.json', window=WINDOW)
        rows, audit, errors = cursor_search(lambda _: {'message': {'items': [work], 'total-results': 1}}, 'Crossref', PARAMS, state=other)
        self.assertFalse(rows); self.assertEqual(audit['status'], 'error'); self.assertTrue(errors)
        self.assertNotIn('PRIVATE BODY', other.path.read_text())


if __name__ == '__main__': unittest.main()
