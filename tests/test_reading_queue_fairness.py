"""Persistent summary-queue regressions; no live retrieval or inference."""
from copy import deepcopy
from datetime import date, timedelta
from itertools import permutations
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import comprehensive_readings as reading


def article(name, first_seen='2026-11-01', **extra):
    return {'kind': 'nonacademic', 'title': name,
            'url': 'https://www.econstor.eu/' + name,
            'first_seen': first_seen, 'published': '2026-10-01', **extra}


def scheduled_day(index):
    # The production cadence: Tuesday/Friday, alternating three/four-day gaps.
    return date(2026, 11, 10) + timedelta(days=7 * (index // 2) + 3 * (index % 2))


class ReadingQueueFairnessTests(unittest.TestCase):
    def run_at(self, records, day, retriever=None, **kwargs):
        retriever = retriever or Mock(return_value=(None, []))
        with patch.object(reading, 'date') as clock:
            clock.today.return_value = day
            stats = reading.process(records, Mock(), retriever=retriever, **kwargs)
            clock.today.assert_called_once()
        return stats, retriever

    def test_failed_top_two_cannot_starve_the_other_93_on_tuesday_friday_runs(self):
        records = [article(f'waiting-{n:03d}') for n in range(93)]
        records += [article(f'old-priority-{n}', first_seen='2026-11-09',
                            published='2026-11-09', analysis={'results': 'Indexed source text.'},
                            complete_reading_attempt={'status': 'claim_verification_failed',
                                                      'last_at': '2026-11-06',
                                                      'next_at': '2026-11-08'})
                    for n in range(2)]
        attempted = []
        for index in range(48):
            # Persistence and input reordering must not reset fairness.
            records = list(reversed(json.loads(json.dumps(records))))
            with patch.object(reading, 'synthesize', side_effect=ValueError('claim_verification_failed')):
                stats, retriever = self.run_at(records, scheduled_day(index))
            attempted.extend(call.args[0]['title'] for call in retriever.call_args_list)
            self.assertEqual(stats['attempted'], 2)
            self.assertEqual(stats['failed'], 2)
            self.assertEqual(stats['summaries_completed'], 0)
        self.assertEqual(len(set(attempted[:95])), 95)
        self.assertEqual(set(attempted[:93]), {f'waiting-{n:03d}' for n in range(93)})
        self.assertTrue(all('deep_analysis' not in row for row in records))

    def test_overdue_retries_and_new_arrivals_both_progress_under_continuous_intake(self):
        records = [article('backlog-a'), article('backlog-b')]
        records += [article('retry-' + name, first_seen='2026-10-01',
                            complete_reading_attempt={'last_at': '2026-11-06', 'next_at': '2026-11-08'})
                    for name in ('a', 'b')]
        turns = []
        for index in range(24):
            day = scheduled_day(index)
            records.extend(article(f'arrival-{index:02d}-{name}', first_seen=day.isoformat())
                           for name in ('a', 'b'))
            stats, retriever = self.run_at(records, day)
            turns.append([call.args[0]['title'] for call in retriever.call_args_list])
            self.assertEqual(stats['attempted'], 2)
        self.assertEqual(turns[:3], [['backlog-a', 'backlog-b'], ['retry-a', 'retry-b'],
                                    ['arrival-00-a', 'arrival-00-b']])
        seen = [name for turn in turns for name in turn]
        self.assertGreater(seen.count('retry-a'), 1)
        self.assertGreater(seen.count('backlog-a'), 1)
        self.assertTrue({f'arrival-{n:02d}-{name}' for n in range(4) for name in ('a', 'b')} <= set(seen))
        # Intake plus retries exceed capacity: fairness is not a drained queue.
        self.assertTrue(any('complete_reading_attempt' not in row for row in records))

    def test_queue_uses_eligibility_not_analysis_or_publication_recency(self):
        records = [article('fresh-analysis', first_seen='2026-11-10', published='2026-11-10',
                           analysis={'results': 'Available indexed text.'}),
                   article('old-publication-new-arrival', first_seen='2026-11-10', published='1990-01-01'),
                   article('overdue', complete_reading_attempt={'next_at': '2026-11-08'}),
                   article('waiting', first_seen='2026-11-02')]
        _, retriever = self.run_at(records, scheduled_day(0))
        self.assertEqual([call.args[0]['title'] for call in retriever.call_args_list], ['waiting', 'overdue'])

    def test_equal_dates_have_stable_identity_order_for_every_input_permutation(self):
        records = [article(name) for name in ('d', 'b', 'a', 'c')]
        records[0]['doi'] = '10.5555/example'
        for ordering in permutations(records):
            _, retriever = self.run_at(deepcopy(list(ordering)), scheduled_day(0))
            self.assertEqual([call.args[0]['title'] for call in retriever.call_args_list], ['a', 'b'])

    def test_legacy_undated_rows_get_one_turn_then_rejoin_with_dated_checkpoint(self):
        records = [article('dated'), article('undated-b', first_seen=None),
                   article('undated-a', first_seen=''),
                   article('legacy-attempt', first_seen='1990-01-01',
                           complete_reading_attempt={'last_at': '2026-11-06'})]
        _, first = self.run_at(records, scheduled_day(0))
        self.assertEqual([call.args[0]['title'] for call in first.call_args_list], ['undated-a', 'undated-b'])
        _, second = self.run_at(records, scheduled_day(1))
        self.assertEqual([call.args[0]['title'] for call in second.call_args_list], ['dated', 'legacy-attempt'])

    def test_retry_cooldown_and_per_run_limit_remain_bounded(self):
        records = [article(name) for name in ('a', 'b', 'c')]
        stats, retriever = self.run_at(records, scheduled_day(0), limit=1)
        self.assertEqual(stats['attempted'], 1)
        self.assertEqual(retriever.call_count, 1)
        attempt = records[0]['complete_reading_attempt']
        self.assertEqual(attempt['next_at'], '2026-11-12')
        before = deepcopy(records[0])
        stats, retriever = self.run_at([records[0]], date(2026, 11, 11))
        self.assertEqual(stats['attempted'], 0)
        retriever.assert_not_called()
        self.assertEqual(records[0], before)
        for limit in (0, -1):
            before = deepcopy(records)
            stats, retriever = self.run_at(records, scheduled_day(1), limit=limit)
            self.assertEqual(stats['attempted'], 0)
            retriever.assert_not_called()
            self.assertEqual(records, before)

    def test_completed_fulltext_and_editorially_checked_rows_are_untouched(self):
        completed = article('completed', deep_analysis={'version': 3, 'source_depth': 'full_text',
                            'coverage': {'all_retrieved_text_processed': True,
                                         'evidence_status': 'full_document_retrieved'}},
                            complete_reading_attempt={'next_at': '2020-01-01'})
        reviewed = article('reviewed', source_review={'status': 'checked'})
        paraphrases = article('paraphrases', analysis={'original_paraphrases_only': True})
        records = [completed, reviewed, paraphrases]
        before = deepcopy(records)
        stats, retriever = self.run_at(records, scheduled_day(0))
        self.assertEqual(stats['attempted'], 0)
        retriever.assert_not_called()
        self.assertEqual(records, before)

    def test_scholarly_screen_and_supported_kind_gate_still_precede_attempts(self):
        records = [article('held', kind='scholarly'), article('unsupported', kind='other'), article('eligible')]
        with patch.object(reading, 'screen_source', return_value={'decision': 'hold'}) as screen:
            stats, retriever = self.run_at(records, scheduled_day(0))
        self.assertEqual(stats['attempted'], 1)
        screen.assert_called_once_with(records[0])
        self.assertEqual(retriever.call_args.args[0]['title'], 'eligible')
        self.assertNotIn('complete_reading_attempt', records[0])
        self.assertNotIn('complete_reading_attempt', records[1])

    def test_partial_summary_remains_eligible_for_fulltext_upgrade_after_seven_days(self):
        record = article('partial', analysis={'results': 'PRIVATE_SOURCE_SENTINEL'})
        full = reading.Document([{'location': 'page:1', 'text': 'PRIVATE_FULLTEXT_SENTINEL'}],
                                record['url'], coverage={'evidence_status': 'full_document_retrieved'})
        # Stub successful synthesis only; exercise retrieval fallback, coverage,
        # checkpoints, eligibility, and replacement in the real processing path.
        def accepted(document, *args, **kwargs):
            return {'coverage': {**document.manifest(), 'all_retrieved_text_processed': True}}
        with patch.object(reading, 'synthesize', side_effect=accepted):
            stats, _ = self.run_at([record], scheduled_day(0))
            self.assertEqual(stats['partial_inputs'], 1)
            self.assertEqual(record['complete_reading_attempt']['status'], 'partial_summary')
            self.assertEqual(record['complete_reading_attempt']['next_at'], '2026-11-17')
            self.assertNotIn('PRIVATE_SOURCE_SENTINEL', json.dumps(record['deep_analysis']))
            before = deepcopy(record)
            stats, retriever = self.run_at([record], scheduled_day(1))
            retriever.assert_not_called()
            self.assertEqual(record, before)
            stats, _ = self.run_at([record], scheduled_day(2), retriever=Mock(return_value=(full, [])))
        self.assertEqual(stats['summaries_completed'], 1)
        self.assertEqual(record['deep_analysis']['source_depth'], 'source_html')
        self.assertEqual(record['complete_reading_attempt']['next_at'], '2026-12-17')
        self.assertFalse(reading.due(record, '2027-01-01'))
        self.assertNotIn('PRIVATE_FULLTEXT_SENTINEL', json.dumps(record))

    def test_failed_claim_gate_does_not_publish_or_replace_previous_partial_summary(self):
        previous = {'version': 3, 'source_depth': 'partial_source_html', 'thesis': 'Existing checked note.',
                    'coverage': {'all_retrieved_text_processed': True, 'evidence_status': 'partial_full_text'}}
        record = article('failure', deep_analysis=deepcopy(previous),
                         complete_reading_attempt={'next_at': '2026-11-01'})
        document = reading.Document([{'location': 'page:1', 'text': 'Private source text remains transient.'}],
                                    record['url'], coverage={'evidence_status': 'full_document_retrieved'})
        with patch.object(reading, 'read_chunk', side_effect=ValueError('claim_verification_failed')):
            stats, _ = self.run_at([record], scheduled_day(0), retriever=Mock(return_value=(document, [])))
        self.assertEqual(stats['failure_reasons'], {'claim_verification_failed': 1})
        self.assertEqual(stats['failure_stages'], {'synthesis': 1})
        self.assertEqual(stats['summaries_completed'], 0)
        self.assertEqual(record['deep_analysis'], previous)
        self.assertNotIn('Private source text', json.dumps(record))

    def test_no_model_neither_fetches_nor_advances_or_mutates_queue(self):
        records = [article('a'), article('b', complete_reading_attempt={'next_at': '2026-11-08'})]
        before = deepcopy(records)
        retriever = Mock()
        with patch.object(reading, 'reading_queue_key') as key, patch.object(reading, 'screen_source') as screen:
            stats = reading.process(records, None, retriever=retriever)
        self.assertTrue(stats['skipped_no_model'])
        self.assertEqual(stats['attempted'], 0)
        retriever.assert_not_called()
        key.assert_not_called()
        screen.assert_not_called()
        self.assertEqual(records, before)


if __name__ == '__main__':
    unittest.main()
