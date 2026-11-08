"""Offline append-only provider migration and source-policy regression tests."""
import copy
import unittest
from unittest.mock import Mock, patch

from test_weekly_source_acquisition import (queue, access, NOW, WINDOW, item,
                                           weekly, rows, document, result_for)

CROSSREF = 'Crossref publisher locations'


def unavailable(*args):
    return {'diagnostics': [{'status': 'no_exact_match', 'retryable': False}]}


def legacy_state(record=None, *, attempt=unavailable, stages=5, known_only=False):
    record = record or item()
    state = None
    with patch.object(queue, 'PROVIDERS', queue.LEGACY_PROVIDERS), \
         patch.object(queue, 'PROVIDER_PLAN_VERSION', 1):
        for _ in range(stages):
            state = queue.run(weekly(record), state, now=NOW, attempt=attempt,
                              known_sources_only=known_only, clock=lambda: 0)
    # An actual original snapshot omitted the field entirely.
    for row in rows(state):
        row['plan'].pop('provider_plan_version')
    queue.seal_state(state)
    return state


def resume(state, record=None, **kwargs):
    return queue.run(weekly(record or item()), state, now=NOW, clock=lambda: 0,
                     **kwargs)


class ProviderMigrationTests(unittest.TestCase):
    def test_exhausted_legacy_appends_only_crossref_without_replaying_sources(self):
        state = legacy_state()
        before = copy.deepcopy(state)
        row = rows(state)[0]
        self.assertTrue(row['complete'])
        self.assertEqual(row['cursor']['provider'], 4)
        stage = Mock(side_effect=unavailable)
        updated = resume(state, attempt=stage)
        self.assertEqual(state, before, 'Validation/migration must not mutate caller snapshots')
        self.assertEqual(stage.call_count, 1)
        self.assertEqual(stage.call_args.args[1]['name'], CROSSREF)
        self.assertEqual(stage.call_args.args[1]['tried_sources'], row['tried_sources'])
        after = rows(updated)[0]
        self.assertEqual(after['fingerprint'], row['fingerprint'])
        self.assertEqual(after['cursor']['known'], row['cursor']['known'])
        self.assertEqual(after['cursor']['provider'], 5)
        self.assertEqual(after['attempts'], row['attempts'] + 1)
        self.assertTrue(after['complete'])
        stage.reset_mock()
        resume(updated, attempt=stage)
        stage.assert_not_called()

    def test_denied_source_stays_tried_when_crossref_returns_it(self):
        record = item()
        deny = lambda *a: {'diagnostics': [{'stage': 'article', 'status': 'article_http_403',
                         'url': record['url'], 'retryable': False}]}
        state = legacy_state(record, attempt=deny)
        candidate = {'url': record['url'], 'doi': record['doi']}
        fetch = Mock()
        with patch.object(access, 'default_providers', return_value=[(CROSSREF, lambda _: [candidate])]), \
             patch.object(access, 'fetch_candidate', fetch):
            updated = resume(state, attempt=lambda r, p, n, t: queue.perform_stage(r, p, n))
        fetch.assert_not_called()
        self.assertEqual(rows(updated)[0]['status'], 'access_blocked')
        self.assertEqual(rows(updated)[0]['tried_sources'], rows(state)[0]['tried_sources'])
        self.assertEqual(rows(updated)[0]['diagnostics'][:-1], rows(state)[0]['diagnostics'])

    def test_full_success_remains_complete_and_partial_keeps_its_evidence(self):
        full = legacy_state(attempt=lambda *a: result_for(document()))
        stage = Mock(side_effect=unavailable)
        updated = resume(full, attempt=stage)
        stage.assert_not_called()
        self.assertEqual(rows(updated)[0]['document'], rows(full)[0]['document'])
        self.assertEqual(rows(updated)[0]['attempts'], rows(full)[0]['attempts'])
        partial = legacy_state(attempt=lambda *a: result_for(document(complete=False)))
        updated = resume(partial, attempt=stage)
        self.assertEqual(stage.call_args.args[1]['name'], CROSSREF)
        self.assertEqual(rows(updated)[0]['document'], rows(partial)[0]['document'])
        self.assertEqual(rows(updated)[0]['document_evidence'], rows(partial)[0]['document_evidence'])
        self.assertEqual(rows(updated)[0]['status'], 'partial_full_text_not_reviewed')

    def test_cooldown_and_provider_cursor_survive_upgrade(self):
        state = legacy_state(stages=2)
        row = rows(state)[0]
        row.update(status='rate_limited', next_retry_at='2026-11-08T12:00:00+00:00',
                   last_outcome='rate_limited')
        state['provider_pauses'] = {'provider:OpenAIRE': row['next_retry_at'],
                                  'host:www.econstor.eu': row['next_retry_at']}
        state.pop('run')
        queue.seal_state(state)
        stage = Mock()
        updated = resume(state, attempt=stage)
        stage.assert_not_called()
        after = rows(updated)[0]
        for key in ('cursor', 'tried_sources', 'next_retry_at', 'attempts', 'diagnostics'):
            self.assertEqual(after[key], row[key])
        self.assertEqual(updated['provider_pauses'], state['provider_pauses'])

    def test_in_progress_resumes_existing_provider_not_restarted_plan(self):
        state = legacy_state(stages=2)
        row = rows(state)[0]
        row['status'] = 'in_progress'
        state.pop('run')
        queue.seal_state(state)
        stage = Mock(side_effect=unavailable)
        updated = resume(state, attempt=stage)
        self.assertEqual(stage.call_args.args[1]['name'], 'OpenAIRE')
        self.assertEqual(rows(updated)[0]['cursor']['provider'], 2)
        self.assertEqual(rows(updated)[0]['fingerprint'], row['fingerprint'])

    def test_known_only_and_doi_less_records_do_not_gain_locator_routes(self):
        for record, known_only in ((item(), True), (item(doi='', kind='nonacademic'), False)):
            with self.subTest(known_only=known_only):
                state = legacy_state(record, known_only=known_only)
                stage = Mock()
                updated = resume(state, record, known_sources_only=known_only, attempt=stage)
                stage.assert_not_called()
                self.assertTrue(rows(updated)[0]['complete'])
                self.assertEqual(rows(updated)[0]['cursor']['provider'], 0)

    def test_historical_dispositions_stay_legacy_and_are_not_retried(self):
        state = legacy_state()
        original = copy.deepcopy(rows(state)[0])
        updated = resume(state, item(historical_backfill=True), attempt=Mock())
        self.assertFalse(updated['records'])
        self.assertEqual(updated['dispositions'][0]['record'], original)
        queue.validate_state(updated)
        # The same eligible input may reappear: its archived cursor, not zero, resumes.
        stage = Mock(side_effect=unavailable)
        resumed = resume(updated, attempt=stage)
        self.assertEqual(stage.call_args.args[1]['name'], CROSSREF)
        self.assertEqual(resumed['dispositions'][0]['record'], original)

    def test_new_window_archives_pending_legacy_rows_without_migration(self):
        state = legacy_state(stages=2)
        original = copy.deepcopy(rows(state)[0])
        payload = weekly(item(published='2026-11-04'))
        payload['run'] = {'date': '2026-11-09', 'publication_window': {
            'from': '2026-11-02', 'to': '2026-11-08', 'timezone': 'UTC'}}
        stage = Mock()
        updated = queue.run(payload, state, now='2026-11-10T12:00:00+00:00',
                            limit=0, attempt=stage, clock=lambda: 0)
        stage.assert_not_called()
        archived = list(updated['closed_windows'][0]['pending_record_metadata'].values())[0]
        self.assertEqual(archived, original)
        self.assertNotIn('provider_plan_version', archived['plan'])
        self.assertEqual(rows(updated)[0]['cursor'], {'known': 0, 'provider': 0, 'provider_tried': []})
        queue.validate_state(updated)

    def test_provider_pause_holds_new_route_and_zero_budget_only_migrates(self):
        state = legacy_state()
        state['provider_pauses'][f'provider:{CROSSREF}'] = '2026-11-08T12:00:00+00:00'
        state.pop('run')
        queue.seal_state(state)
        stage = Mock()
        migrated = resume(state, attempt=stage, limit=0)
        stage.assert_not_called()
        row = rows(migrated)[0]
        self.assertFalse(row['complete'])
        self.assertEqual(row['status'], 'pending_routes')
        self.assertEqual(row['cursor'], rows(state)[0]['cursor'])
        paused = resume(migrated, attempt=stage)
        stage.assert_not_called()
        self.assertEqual(rows(paused)[0]['status'], 'rate_limited')
        self.assertEqual(rows(paused)[0]['next_retry_at'], '2026-11-08T12:00:00+00:00')
        self.assertEqual(rows(paused)[0]['attempts'], rows(state)[0]['attempts'])

    def test_closed_schema_rejects_forged_versions_and_legacy_cursor_overrun(self):
        for version in (0, 3, True, '2'):
            state = legacy_state()
            rows(state)[0]['plan']['provider_plan_version'] = version
            with self.assertRaisesRegex(ValueError, queue.STATE_ERROR):
                queue.seal_state(state)
        state = legacy_state()
        rows(state)[0]['cursor']['provider'] = 5
        rows(state)[0]['attempts'] += 1
        with self.assertRaisesRegex(ValueError, queue.STATE_ERROR):
            queue.seal_state(state)

    def test_host_denial_diagnostic_is_preserved_and_nonretryable(self):
        diagnostic = {'status': 'host_access_denied_this_run', 'retryable': False,
                      'stage': 'article', 'provider': CROSSREF}
        self.assertEqual(queue.diagnostic(diagnostic), diagnostic)
        queue.validate_diagnostic(diagnostic)
        self.assertEqual(queue.failure_status([diagnostic]), 'access_blocked')
        with self.assertRaisesRegex(ValueError, queue.STATE_ERROR):
            queue.validate_diagnostic({**diagnostic, 'retryable': True})


if __name__ == '__main__':
    unittest.main()
