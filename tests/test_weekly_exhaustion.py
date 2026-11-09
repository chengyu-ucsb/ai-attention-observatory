"""Exhausted routes must not resurrect historical retry scheduling."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from test_weekly_source_acquisition import queue, document, result_for, rows, weekly

FIXTURE = Path(__file__).parent / 'fixtures/weekly-exhaustion-corisinta.json'
NOW = queue.utc_now('2026-11-08T10:00:00+00:00')
NO_MATCH = {'diagnostics': [{'stage': 'discovery', 'provider': 'Semantic Scholar',
    'status': 'no_exact_match', 'candidates': 0, 'retryable': False}]}


def fixture_state():
    fixture = json.loads(FIXTURE.read_text())
    payload = weekly(fixture['record'])
    state = queue.run(payload, now=NOW, limit=0)
    key = queue.record_key(fixture['record'])
    assert state['records'][key]['fingerprint'] == fixture['row']['fingerprint']
    state['records'][key] = copy.deepcopy(fixture['row'])
    state['provider_pauses'] = copy.deepcopy(fixture['provider_pauses'])
    state.pop('run', None)
    queue.seal_state(state)
    return payload, state


def resume(payload, state, result=NO_MATCH):
    attempt = Mock(return_value=copy.deepcopy(result))
    updated = queue.run(payload, state, now=NOW, clock=lambda: 0, attempt=attempt)
    queue.validate_state(updated)
    return updated, attempt


def finish(payload, state):
    # Keep the real legacy checkpoint unchanged at entry. If a later deployment
    # appends a provider, finish only the remaining stages rather than replaying
    # earlier ones or assuming Semantic Scholar is always last.
    def no_match(record, plan, *args):
        result = copy.deepcopy(NO_MATCH)
        result['diagnostics'][0]['provider'] = plan['name']
        return result
    attempt = Mock(side_effect=no_match)
    updated = state
    for _ in range(len(queue.PROVIDERS) + 1):
        updated = queue.run(payload, updated, now=NOW, clock=lambda: 0, attempt=attempt)
        queue.validate_state(updated)
        if rows(updated)[0]['complete']:
            return updated, attempt
    raise AssertionError('Remaining nonretryable stages did not exhaust')


class ExhaustionTests(unittest.TestCase):
    def test_real_interrupted_final_provider_checkpoint_completes_after_old_429(self):
        payload, state = fixture_state()
        before = copy.deepcopy(state)
        old = rows(state)[0]
        self.assertEqual(old['attempts'], 9)
        self.assertEqual(old['cursor']['provider'], 3)
        self.assertEqual(old['status'], 'in_progress')
        updated, attempt = finish(payload, state)
        after = rows(updated)[0]
        self.assertEqual(state, before, 'Do not rewrite the input checkpoint')
        remaining = len(queue.PROVIDERS) - old['cursor']['provider']
        self.assertEqual(attempt.call_count, remaining)
        self.assertEqual(attempt.call_args_list[0].args[1]['name'], 'Semantic Scholar')
        self.assertTrue(after['complete'])
        self.assertEqual(after['status'], 'source_unavailable')
        self.assertEqual(after['last_outcome'], 'source_unavailable')
        self.assertEqual(after['cursor']['provider'], len(queue.PROVIDERS))
        self.assertEqual(after['attempts'], old['attempts'] + remaining)
        self.assertNotIn('next_retry_at', after)
        self.assertEqual(after['fingerprint'], old['fingerprint'])
        self.assertEqual(after['tried_sources'], old['tried_sources'])
        self.assertEqual(after['diagnostics'][:-remaining], old['diagnostics'])
        self.assertEqual(updated['provider_pauses'], state['provider_pauses'])
        repeated, repeated_attempt = resume(payload, updated)
        repeated_attempt.assert_not_called()
        self.assertEqual(rows(repeated)[0], after)

    def test_old_temporary_errors_never_create_a_terminal_retry_state(self):
        for status in ('rate_limit_pause', 'deferred_time_budget', 'URLError',
                       'http_503', 'worker_failed'):
            with self.subTest(status=status):
                payload, state = fixture_state()
                row = rows(state)[0]
                row['diagnostics'].append({'status': status, 'retryable': True,
                                           'retry_after_seconds': 3600})
                queue.seal_state(state)
                updated, _ = finish(payload, state)
                self.assertTrue(rows(updated)[0]['complete'])
                self.assertEqual(rows(updated)[0]['status'], 'source_unavailable')
                self.assertNotIn('next_retry_at', rows(updated)[0])

    def test_old_access_denial_remains_a_terminal_blocked_outcome(self):
        payload, state = fixture_state()
        row = rows(state)[0]
        row['diagnostics'].append({'stage': 'article', 'status': 'article_http_403',
                                   'url': 'https://www.econstor.eu/denied.pdf', 'retryable': False})
        queue.seal_state(state)
        updated, _ = finish(payload, state)
        self.assertTrue(rows(updated)[0]['complete'])
        self.assertEqual(rows(updated)[0]['status'], 'access_blocked')
        self.assertEqual(rows(updated)[0]['diagnostics'][:len(row['diagnostics'])], row['diagnostics'])

    def test_existing_partial_document_and_evidence_survive_exhaustion(self):
        payload, state = fixture_state()
        row = rows(state)[0]
        evidence = result_for(document(False))
        row['document'] = evidence['document']
        row['document_evidence'] = evidence['diagnostics'][0]
        row['diagnostics'].extend(evidence['diagnostics'])
        queue.seal_state(state)
        updated, _ = finish(payload, state)
        after = rows(updated)[0]
        self.assertTrue(after['complete'])
        self.assertEqual(after['status'], 'partial_full_text_not_reviewed')
        self.assertEqual(after['document'], row['document'])
        self.assertEqual(after['document_evidence'], row['document_evidence'])
        self.assertNotIn('next_retry_at', after)

    def test_current_full_document_takes_precedence_over_old_failures(self):
        payload, state = fixture_state()
        evidence = result_for(document(True))
        updated, attempt = resume(payload, state, evidence)
        after = rows(updated)[0]
        self.assertEqual(attempt.call_count, 1)
        self.assertTrue(after['complete'])
        self.assertEqual(after['status'], 'full_document_retrieved_not_reviewed')
        self.assertEqual(after['document'], evidence['document'])
        self.assertEqual(after['document_evidence'], evidence['diagnostics'][0])
        self.assertNotIn('next_retry_at', after)

    def test_current_retry_keeps_cursor_and_updates_cooldowns(self):
        for status in ('http_429', 'deferred_time_budget', 'URLError'):
            with self.subTest(status=status):
                payload, state = fixture_state()
                current = {'diagnostics': [{'stage': 'discovery', 'provider': 'Semantic Scholar',
                    'status': status, 'retryable': True, 'retry_after_seconds': 7200}]}
                updated, attempt = resume(payload, state, current)
                after = rows(updated)[0]
                self.assertEqual(attempt.call_count, 1)
                self.assertFalse(after['complete'])
                self.assertEqual(after['cursor'], rows(state)[0]['cursor'])
                self.assertEqual(after['next_retry_at'], (NOW + timedelta(hours=2)).isoformat())
                self.assertIn(after['status'], queue.RETRY)
                self.assertEqual(updated['provider_pauses']['provider:CORE'],
                                 state['provider_pauses']['provider:CORE'])
                if status == 'http_429':
                    self.assertEqual(updated['provider_pauses']['provider:Semantic Scholar'],
                                     after['next_retry_at'])

    def test_active_provider_pause_prevents_the_final_attempt(self):
        payload, state = fixture_state()
        until = (NOW + timedelta(hours=1)).isoformat()
        state['provider_pauses']['provider:Semantic Scholar'] = until
        queue.seal_state(state)
        updated, attempt = resume(payload, state)
        self.assertEqual(attempt.call_count, 1)
        self.assertEqual(attempt.call_args.args[1]['name'], 'Crossref publisher locations')
        after = rows(updated)[0]
        self.assertFalse(after['complete'])
        self.assertEqual(after['cursor'], rows(state)[0]['cursor'])
        self.assertEqual(after['attempts'], 10)
        self.assertEqual(after['next_retry_at'], until)
        self.assertEqual(updated['provider_pauses'], state['provider_pauses'])


if __name__ == '__main__':
    unittest.main()
