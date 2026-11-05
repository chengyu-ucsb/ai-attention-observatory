"""Offline comparison integrity tests; no model, download or network access."""
import copy
from contextlib import redirect_stdout
import io
from hashlib import sha256
import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evaluate_synthesis as evaluation
import comprehensive_readings as reading
from full_document_access import Document

SOURCE = ('The classroom comparison included students who completed a structured task '
          'and did not establish independent transfer beyond this setting.')
CLAIM = {'field': 'limitations',
         'text': 'Independent learning beyond the classroom was not established in this comparison.',
         'source_span': 'C0001:S001'}
ANSWER = {'claims': [CLAIM], 'no_claim_reason': ''}
CHECK = {'supported': [0], 'rejected': []}


def completion(value):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(value)}}]}


class Model:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return completion(next(self.values))


def records():
    return [dict(doi=doi, kind='scholarly', title='A study', deep_analysis={'keep': True})
            for doi in evaluation.DOIS]


def document():
    return Document([{'location': 'page:1', 'text': SOURCE}], 'https://example.org',
                    coverage={'evidence_status': 'full_document_retrieved'})


class EvaluationTests(unittest.TestCase):
    def evaluate(self, model, data=None, retriever=None, **kwargs):
        return evaluation.evaluate(records() if data is None else data, model,
            deadline=time.monotonic() + 60, retriever=retriever or Mock(return_value=(document(), [])), **kwargs)

    def test_same_source_retrieved_once_per_record_and_only_first_chunk(self):
        doc = document()
        doc.units.append({'location': 'page:2', 'text': 'Later text ' * 2000})
        retrieve = Mock(return_value=(doc, [{'private': SOURCE}]))
        model = Model([ANSWER, CHECK] * 4)
        rows = self.evaluate(model, retriever=retrieve)
        self.assertEqual(retrieve.call_count, 2)
        self.assertEqual([c.args[0]['doi'] for c in retrieve.call_args_list], list(evaluation.DOIS))
        first = reading.chunk_document(doc)[0]
        for row in rows:
            self.assertEqual(row['chunk_id'], 'C0001')
            self.assertEqual(row['chunk_sha256'], sha256(first['text'].encode()).hexdigest())
            self.assertGreater(row['chunks_total'], 1)
            self.assertEqual(row['accepted_claim_count'], 1)
        self.assertEqual(rows[0]['source_sha256'], rows[1]['source_sha256'])
        self.assertEqual(rows[0]['chunk_sha256'], rows[1]['chunk_sha256'])

    def test_baseline_and_verification_unchanged_seeds_fixed(self):
        reference = Model([ANSWER, CHECK])
        reading.read_chunk(reference, reading.chunk_document(document())[0], 'scholarly', 'A study')
        model = Model([ANSWER, CHECK] * 4)
        self.evaluate(model)
        for call in model.calls:
            self.assertEqual(call['seed'], 7)
        for i in (0, 1):
            actual = dict(model.calls[i])
            actual.pop('seed')
            self.assertEqual(actual, reference.calls[i])
        self.assertEqual(model.calls[1], model.calls[3])
        candidate = model.calls[2]
        baseline = model.calls[0]
        schema = candidate['response_format']['schema']['properties']['claims']['items']
        self.assertEqual(list(schema['properties']), ['source_span', 'field', 'text'])
        self.assertEqual(schema, baseline['response_format']['schema']['properties']['claims']['items'])
        self.assertEqual(candidate['messages'][-1]['content'],
                         evaluation.INSTRUCTION + baseline['messages'][-1]['content'])
        self.assertEqual(candidate['messages'][0], baseline['messages'][0])
        self.assertEqual(list(reading.claim_schema('scholarly', [{'id':'s'}])['properties']['claims']['items']['properties']),
                         ['field', 'text', 'source_span'])

    def test_candidate_rechecks_modified_context_before_inference(self):
        model = Model([ANSWER])
        wrapper = evaluation.ComparisonModel(model, 'evidence_first', time.monotonic() + 60)
        with patch.object(reading, 'check_context_budget', side_effect=ValueError('deferred_model_context_budget')) as check:
            with self.assertRaisesRegex(ValueError, 'deferred_model_context_budget'):
                wrapper.create_chat_completion(messages=[{'role':'user','content':'original'}],
                    response_format={'schema':reading.claim_schema('scholarly', [{'id':'s'}])}, max_tokens=2200)
        self.assertTrue(check.call_args.args[1][-1]['content'].startswith(evaluation.INSTRUCTION))
        self.assertEqual(model.calls, [])

    def test_candidate_cannot_bypass_verifier_rejection(self):
        reject = {'supported': [], 'rejected': [0]}
        model = Model([ANSWER, reject] * 4)
        rows = self.evaluate(model)
        self.assertTrue(all(r['code'] == 'claim_verification_failed' for r in rows))
        self.assertTrue(all(r['accepted_claim_count'] == 0 for r in rows))
        self.assertEqual(len(model.calls), 8)

    def test_candidate_cannot_bypass_unknown_span_or_copied_text(self):
        for claim, code in ((dict(CLAIM, source_span='C9999:S001'), 'unknown_source_span'),
                            (dict(CLAIM, text=SOURCE), 'copied_source_passage')):
            model = Model([{'claims':[claim], 'no_claim_reason':''}] * 4)
            rows = self.evaluate(model)
            self.assertTrue(all(r['code'] == code for r in rows))
            self.assertEqual(len(model.calls), 4)

    def test_format_retries_are_seeded_and_do_not_change_verifier(self):
        model = Model([{'claims':[], 'no_claim_reason':0}, ANSWER, CHECK] * 4)
        rows = self.evaluate(model)
        self.assertTrue(all(r['code'] == 'gate_pass' for r in rows))
        self.assertEqual(len(model.calls), 12)
        self.assertTrue(all(c['seed'] == evaluation.SEED for c in model.calls))
        self.assertNotIn(evaluation.INSTRUCTION, model.calls[5]['messages'][-1]['content'])

    def test_partial_source_never_falls_back(self):
        doc = document()
        doc.coverage['evidence_status'] = 'partial_full_text'
        model = Model([])
        with patch.object(reading, 'indexed_sections', side_effect=AssertionError('no fallback')):
            rows = self.evaluate(model, retriever=Mock(return_value=(doc, [])))
        self.assertTrue(all(r['code'] == 'full_document_required' for r in rows))
        self.assertEqual(model.calls, [])

    def test_exact_record_selection_not_backlog_order_or_duplicates(self):
        data = list(reversed(records())) + [{'doi':'10.9999/other', 'kind':'scholarly'}]
        retrieve = Mock(return_value=(document(), []))
        self.evaluate(Model([ANSWER, CHECK] * 4), data, retrieve)
        self.assertEqual([c.args[0]['doi'] for c in retrieve.call_args_list], list(evaluation.DOIS))
        data.append(copy.deepcopy(data[0]))
        rows = self.evaluate(Model([ANSWER, CHECK] * 2), data)
        self.assertEqual([r['code'] for r in rows[2:]], ['record_selection_failed'] * 2)

    def test_no_source_persistence_or_record_mutation(self):
        data = records()
        before = copy.deepcopy(data)
        library_hash = sha256(reading.LIB.read_bytes()).hexdigest()
        with patch.object(Path, 'write_text', side_effect=AssertionError('no writes')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('no writes')):
            rows = self.evaluate(Model([ANSWER, CHECK] * 4), data)
        encoded = json.dumps(rows)
        self.assertNotIn(SOURCE, encoded)
        self.assertNotIn(CLAIM['text'], encoded)
        self.assertNotIn('quote', encoded)
        self.assertEqual(data, before)
        self.assertEqual(library_hash, sha256(reading.LIB.read_bytes()).hexdigest())

    def test_deadline_reports_unfinished_without_retrieval(self):
        retrieve = Mock()
        rows = evaluation.evaluate(records(), Model([]), deadline=time.monotonic() - 1, retriever=retrieve)
        retrieve.assert_not_called()
        self.assertTrue(all(r['code'] == 'deadline_exceeded' for r in rows))

    def test_unknown_exception_does_not_leak_source(self):
        rows = self.evaluate(Model([]), retriever=Mock(side_effect=RuntimeError(SOURCE)))
        self.assertTrue(all(r['code'] == 'evaluation_error' for r in rows))
        self.assertNotIn(SOURCE, json.dumps(rows))

    def test_hard_timeout_terminates_blocked_worker_and_keeps_safe_progress(self):
        context = Mock()
        process = context.Process.return_value
        process.is_alive.return_value = True
        out = context.Queue.return_value
        row = evaluation.initial_rows()[0]
        row.update(code='gate_pass', accepted_claim_count=1)
        out.get.side_effect = [row, queue.Empty(), queue.Empty()]
        with patch.object(evaluation.time, 'monotonic', side_effect=[0, 0, 0, 0.2, 0.2, 2]):
            report = evaluation.run_bounded('/not-loaded.gguf', 1, context=context)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(report['status'], 'deadline_exceeded')
        self.assertEqual(report['results'][0]['code'], 'gate_pass')
        self.assertTrue(all(r['code'] == 'deadline_exceeded' for r in report['results'][1:]))

    def test_empty_claims_are_not_substantive_success(self):
        model = Model([{'claims': [], 'no_claim_reason': 'No substantive evidence here.'}] * 4)
        rows = self.evaluate(model)
        self.assertTrue(all(r['code'] == 'no_substantive_claims' for r in rows))
        self.assertTrue(all(r['accepted_claim_count'] == 0 for r in rows))
        self.assertEqual(len(model.calls), 4)

    def test_cli_report_contains_only_sanitized_report_and_quality_failure_exits_zero(self):
        report = {'status':'deadline_exceeded', 'results':evaluation.initial_rows()}
        for row in report['results']:
            row['code'] = 'deadline_exceeded'
        with tempfile.TemporaryDirectory() as temp, patch.object(evaluation, 'run_bounded', return_value=report) as run:
            path = Path(temp) / 'report.json'
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = evaluation.main(['--report', str(path), '--time-budget-seconds', '720'])
            self.assertEqual(stdout.getvalue(), path.read_text())
            self.assertEqual(json.loads(stdout.getvalue()), report)
            self.assertNotIn(SOURCE, stdout.getvalue())
            self.assertNotIn(CLAIM['text'], stdout.getvalue())
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(path.read_text()), report)
            self.assertEqual(run.call_args.args[1], 720)

    def test_missing_model_reports_worker_failed_without_loading_native_backend(self):
        out = Mock()
        backend = Mock()
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(evaluation.os, 'dup2') as redirect, \
             patch.dict(sys.modules, {'llama_cpp': backend}):
            evaluation._worker(out, str(Path(temp) / 'missing.gguf'), time.monotonic() + 60)
        backend.Llama.assert_not_called()
        out.put.assert_called_once_with({'worker_failed': True})
        self.assertEqual([call.args[1] for call in redirect.call_args_list], [1, 2])

    def test_worker_failure_is_reported_safely_on_stdout_with_nonzero_exit(self):
        report = {'status': 'worker_failed', 'results': evaluation.initial_rows()}
        for row in report['results']:
            row['code'] = 'worker_failed'
        stdout = io.StringIO()
        with patch.object(evaluation, 'run_bounded', return_value=report), redirect_stdout(stdout):
            result = evaluation.main(['--model', '/missing.gguf'])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        self.assertNotIn('/missing.gguf', stdout.getvalue())

    def test_output_rejects_repository_and_symlink_into_repository(self):
        with self.assertRaises(ValueError):
            evaluation.report_path(reading.ROOT / 'report.json')
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / 'repo'
            link.symlink_to(reading.ROOT, target_is_directory=True)
            with self.assertRaises(ValueError):
                evaluation.report_path(link / 'report.json')
            self.assertEqual(evaluation.report_path(Path(temp) / 'safe.json'), Path(temp) / 'safe.json')


if __name__ == '__main__':
    unittest.main()
