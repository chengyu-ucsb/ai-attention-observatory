"""New-week retrieval continues through independent providers during outages.

Synthetic offline sources only. No future publication or live access is claimed.
"""
import copy
from datetime import timedelta
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from test_weekly_source_acquisition import queue, access, item, weekly, rows, NOW, document, result_for


def miss(*args):
    return {'diagnostics': [{'stage': 'discovery', 'status': 'no_exact_match', 'retryable': False}]}


def limited(seconds=7200):
    return {'diagnostics': [{'stage': 'discovery', 'status': 'http_429',
                             'retryable': True, 'retry_after_seconds': seconds}]}


class RecurringRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.record = item(url='https://doi.org/10.5555/weekly1')
        self.payload = weekly(self.record)

    def run_queue(self, state=None, result=None, **kwargs):
        attempt = Mock(return_value=result or miss())
        state = queue.run(self.payload, state, now=kwargs.pop('now', NOW),
                          attempt=attempt, clock=lambda: 0, **kwargs)
        queue.validate_state(state)
        return state, attempt

    def test_rate_limited_provider_does_not_block_independent_later_success(self):
        state, _ = self.run_queue(result=limited())
        before = copy.deepcopy(rows(state)[0])
        state, second = self.run_queue(state)
        self.assertEqual(second.call_args.args[1]['name'], 'OpenAIRE')
        after = rows(state)[0]
        self.assertEqual(after['cursor'], before['cursor'])
        self.assertEqual(after['next_retry_at'], before['next_retry_at'])
        self.assertEqual(after['status'], 'rate_limited')
        state, third = self.run_queue(state, result=result_for(document()))
        self.assertEqual(third.call_args.args[1]['name'], 'CORE')
        self.assertTrue(rows(state)[0]['complete'])
        self.assertEqual(rows(state)[0]['status'], 'full_document_retrieved_not_reviewed')
        self.assertNotIn('next_retry_at', rows(state)[0])
        self.assertEqual(state['provider_pauses']['provider:Europe PMC XML'], before['next_retry_at'])
        self.assertEqual(rows(state)[0]['diagnostics'][0], before['diagnostics'][0])
        _, repeat = self.run_queue(state)
        repeat.assert_not_called()

    def test_two_independent_provider_retries_do_not_block_a_third(self):
        state, _ = self.run_queue(result=limited())
        state, _ = self.run_queue(state, result=limited(10800))
        primary = rows(state)[0]['next_retry_at']
        fallback = copy.deepcopy(rows(state)[0]['provider_fallbacks']['1'])
        state, third = self.run_queue(state)
        self.assertEqual(third.call_args.args[1]['name'], 'CORE')
        self.assertEqual(rows(state)[0]['next_retry_at'], primary)
        self.assertEqual(rows(state)[0]['provider_fallbacks']['1'], fallback)
        self.assertGreater(fallback['next_retry_at'], primary)

    def test_primary_recovers_and_consumes_done_fallback_without_replay(self):
        state, _ = self.run_queue(result=limited())
        state, _ = self.run_queue(state)  # OpenAIRE exhausted.
        state, _ = self.run_queue(state)  # CORE exhausted.
        for provider in queue.PROVIDERS[3:]:
            state['provider_pauses']['provider:' + provider] = (NOW + timedelta(hours=4)).isoformat()
        state.pop('run'); queue.seal_state(state)
        state, attempt = self.run_queue(state, now=NOW + timedelta(hours=2))
        self.assertEqual(attempt.call_args.args[1]['name'], 'Europe PMC XML')
        self.assertEqual(rows(state)[0]['cursor']['provider'], 3)
        self.assertNotIn('provider_fallbacks', rows(state)[0])
        state, attempt = self.run_queue(state, now=NOW + timedelta(hours=4))
        self.assertEqual(attempt.call_args.args[1]['name'], 'Semantic Scholar')

    def test_primary_adopts_still_paused_fallback_checkpoint(self):
        state, _ = self.run_queue(result=limited())
        state, _ = self.run_queue(state, result=limited(10800))
        deadline = rows(state)[0]['provider_fallbacks']['1']['next_retry_at']
        for _ in range(3):
            state, _ = self.run_queue(state)  # Other independent providers exhaust.
        state, attempt = self.run_queue(state, now=NOW + timedelta(hours=2))
        self.assertEqual(attempt.call_args.args[1]['name'], 'Europe PMC XML')
        self.assertEqual(rows(state)[0]['cursor']['provider'], 1)
        self.assertEqual(rows(state)[0]['next_retry_at'], deadline)
        self.assertEqual(rows(state)[0]['status'], 'rate_limited')
        state, attempt = self.run_queue(state, now=NOW + timedelta(hours=2))
        attempt.assert_not_called()
        state, attempt = self.run_queue(state, now=NOW + timedelta(hours=3))
        self.assertEqual(attempt.call_args.args[1]['name'], 'OpenAIRE')

    def test_partial_fallback_resumes_exact_url_hashes_before_advancing(self):
        state, _ = self.run_queue(result=limited())
        partial = result_for(document(False))
        tried = queue.digest('https://www.econstor.eu/partial.pdf')
        partial['tried_sources'] = [tried]
        partial['diagnostics'].insert(0, {'stage': 'discovery', 'status': 'candidates',
                                        'retryable': False, 'candidates': 3})
        state, _ = self.run_queue(state, result=partial)
        self.assertFalse(rows(state)[0]['provider_fallbacks']['1']['complete'])
        original = copy.deepcopy(rows(state)[0]['document'])
        for _ in range(3):
            state, _ = self.run_queue(state)  # Fairly check other untouched providers first.
        state, attempt = self.run_queue(state)
        self.assertEqual(attempt.call_args.args[1]['name'], 'OpenAIRE')
        self.assertIn(tried, attempt.call_args.args[1]['tried_sources'])
        self.assertTrue(rows(state)[0]['provider_fallbacks']['1']['complete'])
        self.assertEqual(rows(state)[0]['document'], original)

    def test_checkpoint_before_fallback_io_is_valid_and_resumes_same_stage(self):
        state, _ = self.run_queue(result=limited())
        snapshots = []
        final, _ = self.run_queue(state, save=lambda value: snapshots.append(copy.deepcopy(value)))
        self.assertEqual(rows(snapshots[0])[0]['provider_fallbacks']['1']['status'], 'in_progress')
        self.assertEqual(rows(snapshots[0])[0]['next_retry_at'], rows(state)[0]['next_retry_at'])
        resumed = snapshots[0]
        for _ in range(3):
            resumed, _ = self.run_queue(resumed)
        resumed, attempt = self.run_queue(resumed)
        self.assertEqual(attempt.call_args.args[1]['name'], 'OpenAIRE')
        self.assertTrue(rows(resumed)[0]['provider_fallbacks']['1']['complete'])
        self.assertEqual(rows(final)[0]['cursor'], rows(resumed)[0]['cursor'])

    def test_no_provider_is_replayed_when_all_fallbacks_are_done(self):
        state, _ = self.run_queue(result=limited())
        for provider in queue.PROVIDERS[1:]:
            state, attempt = self.run_queue(state)
            self.assertEqual(attempt.call_args.args[1]['name'], provider)
        state, attempt = self.run_queue(state)
        attempt.assert_not_called()
        self.assertFalse(rows(state)[0]['complete'])
        self.assertEqual(rows(state)[0]['cursor']['provider'], 0)
        state, attempt = self.run_queue(state, now=NOW + timedelta(hours=2))
        self.assertEqual(attempt.call_args.args[1]['name'], queue.PROVIDERS[0])
        self.assertTrue(rows(state)[0]['complete'])
        self.assertEqual(rows(state)[0]['cursor']['provider'], len(queue.PROVIDERS))
        self.assertEqual(rows(state)[0]['status'], 'source_unavailable')
        self.assertNotIn('next_retry_at', rows(state)[0])

    def test_shared_pause_skips_provider_but_preserves_host_cooldown_and_budgets(self):
        state, _ = self.run_queue(result=limited())
        until = rows(state)[0]['next_retry_at']
        state['provider_pauses']['host:www.econstor.eu'] = until
        state.pop('run'); queue.seal_state(state)
        paused, attempt = self.run_queue(state, limit=0)
        attempt.assert_not_called()
        state, attempt = self.run_queue(paused, limit=1)
        self.assertEqual(attempt.call_count, 1)
        self.assertEqual(attempt.call_args.args[1]['host_backoff']['www.econstor.eu'], 7200)
        self.assertEqual(state['run']['attempted_stages'], 1)
        self.assertEqual(state['run']['attempted_records'], 1)
        self.assertEqual(state['provider_pauses']['host:www.econstor.eu'], until)

    def test_next_week_preserves_old_fallback_metadata_without_fetching_old_records(self):
        state, _ = self.run_queue(result=limited())
        state, _ = self.run_queue(state)
        prior = copy.deepcopy(rows(state)[0])
        self.payload = weekly(item(2, published='2026-11-04'))
        self.payload['run']['publication_window'] = {'from': '2026-11-02', 'to': '2026-11-08', 'timezone': 'UTC'}
        state, attempt = self.run_queue(state, now='2026-11-09', result=result_for(document()))
        self.assertEqual(attempt.call_count, 1)
        self.assertEqual(attempt.call_args.args[0]['doi'], '10.5555/weekly2')
        self.assertEqual(list(state['closed_windows'][0]['pending_record_metadata'].values()), [prior])
        self.assertNotIn('provider_fallbacks', rows(state)[0])
        self.assertNotIn('PRIVATE_SOURCE_SENTINEL', json.dumps(state))

    def test_six_hour_schedule_does_not_keep_retrying_one_hour_outage(self):
        state, first = self.run_queue(result=limited(3600))
        state, second = self.run_queue(state, now=NOW + timedelta(hours=6), result=result_for(document()))
        self.assertEqual(first.call_args.args[1]['name'], 'Europe PMC XML')
        self.assertEqual(second.call_args.args[1]['name'], 'OpenAIRE')
        self.assertTrue(rows(state)[0]['complete'])
        self.assertEqual(rows(state)[0]['attempts'], 2)

    def test_all_retrying_providers_get_fair_turns_after_cooldowns_expire(self):
        state = None
        start = queue.utc_now('2026-11-03T00:00:00+00:00')
        attempted = []
        for tick in range(12):
            state, attempt = self.run_queue(state, now=start + timedelta(hours=6 * tick), result=limited(3600))
            attempted.append(attempt.call_args.args[1]['name'])
            self.assertEqual(state['run']['attempted_records'], 1)
            self.assertFalse(rows(state)[0]['complete'])
        self.assertEqual(attempted, list(queue.PROVIDERS) * 2 + list(queue.PROVIDERS[:2]))

    def test_corrupt_fallback_metadata_is_refused_before_io(self):
        state, _ = self.run_queue(result=limited())
        state, _ = self.run_queue(state)
        for mutate in (lambda p: p.update(raw_text='private'),
                       lambda p: p.update(complete=True, status='rate_limited'),
                       lambda p: p.update(tried_sources=['f' * 64])):
            bad = copy.deepcopy(state)
            mutate(rows(bad)[0]['provider_fallbacks']['1'])
            with self.assertRaisesRegex(ValueError, queue.STATE_ERROR):
                queue.seal_state(bad)


if __name__ == '__main__':
    unittest.main()
