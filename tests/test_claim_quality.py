"""Offline claim-quality evaluation tests using original synthetic source text.

No inference, remote retrieval, model download, library update or publication.
"""
import copy
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import itertools
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import comprehensive_readings as reading
import evaluate_claim_quality as evaluation


SOURCE = (
    'The classroom comparison included 20 students who completed a structured task '
    'with written guidance during one lesson. Independent transfer was not established '
    'outside that setting. The researchers measured immediate task completion and '
    'did not assess attention or performance on a later unassisted task.'
)
POSITIVE = 'The classroom comparison did not establish independent learning outside its original setting.'
NEGATIVE = 'The classroom comparison established lasting improvements in independent attention outside its original setting.'
CHECK = {'supported': [0], 'rejected': []}
REJECT = {'supported': [], 'rejected': [0]}


def fixtures():
    chunk = {'id': 'C0001', 'text': SOURCE}
    span = reading.source_spans(chunk)[1]
    quote = ' '.join(span['text'].split())
    return {
        'version': 1, 'review_status': evaluation.REVIEW_STATUS,
        'sources': [{
            'id': 'synthetic_source', 'title': 'Original synthetic classroom example',
            'doi': '10.9999/synthetic-test-only', 'url': 'https://example.org/synthetic-test-only',
            'license': 'CC0-1.0', 'license_url': evaluation.LICENSES['CC0-1.0'],
            'license_verified_at': '2026-01-01', 'section': 'Synthetic test data', 'text': SOURCE,
            'license_verification_basis': 'Original synthetic text written for this test; no external article is represented.',
            'excerpt_locations': [{'section': 'Synthetic', 'locator': 'Entire original test paragraph.',
                                   'start': 0, 'end': len(SOURCE)}],
            'cases': [
                {'id': 'synthetic_positive', 'field': 'limitations', 'text': POSITIVE,
                 'quote': quote, 'source_span': span['id'], 'expected_supported': True,
                 'category': 'supported', 'rationale': 'The excerpt explicitly limits independent transfer.'},
                {'id': 'synthetic_negative', 'field': 'reported_results', 'text': NEGATIVE,
                 'quote': quote, 'source_span': span['id'], 'expected_supported': False,
                 'category': 'unsupported_transfer_attention', 'rationale': 'No later attention improvement was measured.'},
            ],
        }],
    }


def completion(value, finish='stop'):
    return {'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(value)}}]}


class Model:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return value if 'choices' in value else completion(value)


class FixtureValidationTests(unittest.TestCase):
    def test_original_synthetic_fixture_has_both_labels_and_hash_is_stable(self):
        data = fixtures()
        before = copy.deepcopy(data)
        self.assertEqual(evaluation.validate_fixtures(data), {
            'sources': 1, 'cases': 2, 'expected_supported': 1, 'expected_unsupported': 1})
        self.assertEqual(data, before)
        self.assertEqual(evaluation.fixture_digest(data), evaluation.fixture_digest(copy.deepcopy(data)))
        data['sources'][0]['cases'][0]['rationale'] += ' Additional label evidence.'
        self.assertNotEqual(evaluation.fixture_digest(data), evaluation.fixture_digest(before))

    def test_missing_or_restrictive_license_and_evidence_fail_closed(self):
        for change in (
            lambda s: s.pop('license'),
            lambda s: s.update(license='CC-BY-NC-ND-4.0'),
            lambda s: s.update(license_url='https://example.org/not-the-license'),
            lambda s: s.update(license_verified_at='not-a-date'),
            lambda s: s.update(license_verified_at='2099-01-01'),
            lambda s: s.update(license_verification_basis=''),
            lambda s: s.pop('license_verification_basis'),
            lambda s: s.update(excerpt_locations=[]),
            lambda s: s['excerpt_locations'][0].update(start=10),
            lambda s: s['excerpt_locations'][0].update(end=len(SOURCE) - 10),
            lambda s: s['excerpt_locations'][0].update(locator=''),
        ):
            data = fixtures()
            change(data['sources'][0])
            with self.subTest(data=data['sources'][0].get('license')), self.assertRaises(evaluation.FixtureError):
                evaluation.validate_fixtures(data)

    def test_exact_anchor_source_span_bool_and_unique_safe_identifiers_required(self):
        for change in (
            lambda c: c.update(quote=c['quote'].lower()),
            lambda c: c.update(quote=c['quote'] + ' '),
            lambda c: c.update(source_span='C9999:S001'),
            lambda c: c.update(expected_supported=1),
            lambda c: c.update(expected_supported='true'),
            lambda c: c.update(id=SOURCE),
            lambda c: c.update(id='synthetic_negative'),
            lambda c: c.update(category=SOURCE),
            lambda c: c.update(rationale=''),
        ):
            data = fixtures()
            change(data['sources'][0]['cases'][0])
            with self.assertRaises(evaluation.FixtureError):
                evaluation.validate_fixtures(data)

    def test_positive_copy_or_unsupported_number_cannot_be_labeled_supported(self):
        for text in (' '.join(SOURCE.split()[:20]), 'The comparison enrolled 99 students in one classroom setting.'):
            data = fixtures()
            data['sources'][0]['cases'][0]['text'] = text
            with self.assertRaisesRegex(evaluation.FixtureError, 'fixture_positive_fails_production_gate'):
                evaluation.validate_fixtures(data)
        data = fixtures()
        data['sources'][0]['cases'][1]['text'] = ' '.join(SOURCE.split()[:20])
        self.assertEqual(evaluation.validate_fixtures(data)['cases'], 2)

    def test_unreviewed_fixture_single_label_or_unrecognized_metadata_rejected(self):
        for change in (
            lambda d: d.update(review_status='independent_expert_verified'),
            lambda d: d.update(version=True),
            lambda d: d.update(unrecognized=SOURCE),
            lambda d: d['sources'][0].update(kind='news'),
            lambda d: d['sources'][0].update(url='http://example.org'),
            lambda d: d['sources'][0]['cases'][1].update(expected_supported=True),
        ):
            data = fixtures()
            change(data)
            with self.assertRaises(evaluation.FixtureError):
                evaluation.validate_fixtures(data)


class EvaluationTests(unittest.TestCase):
    def evaluate(self, model, data=None, **kwargs):
        return evaluation.evaluate(fixtures() if data is None else data, model,
                                   deadline=time.monotonic() + 60, **kwargs)

    def test_confusion_matrix_distinguishes_acceptances_and_rejections(self):
        accepted = self.evaluate(Model([CHECK, CHECK]))
        rejected = self.evaluate(Model([REJECT, REJECT]))
        self.assertEqual([r['outcome'] for r in accepted], ['true_acceptance', 'false_acceptance'])
        self.assertEqual([r['outcome'] for r in rejected], ['false_rejection', 'true_rejection'])
        result = evaluation.metrics(accepted + rejected)
        self.assertEqual(result['confusion_matrix'], dict.fromkeys(evaluation.QUALITY_OUTCOMES, 1))
        self.assertEqual(result['quality_evaluated'], 4)
        self.assertEqual(result['false_acceptance_rate'], 0.5)
        self.assertEqual(result['false_rejection_rate'], 0.5)

    def test_exact_partition_schema_contains_every_decision_for_one_to_six_claims(self):
        production = reading.verification_schema()
        before = copy.deepcopy(production)
        with patch.object(reading, 'verification_schema', return_value=production):
            for count in range(1, 7):
                schema = evaluation.exact_partition_schema(count)
                decisions = schema.pop('enum')
                self.assertEqual(schema, production)
                self.assertEqual(len(decisions), 2 ** count)
                actual = set()
                for decision in decisions:
                    supported, rejected = decision['supported'], decision['rejected']
                    self.assertEqual(len(set(supported)), len(supported))
                    self.assertEqual(len(set(rejected)), len(rejected))
                    self.assertFalse(set(supported) & set(rejected))
                    self.assertEqual(set(supported) | set(rejected), set(range(count)))
                    actual.add(tuple(index in supported for index in range(count)))
                self.assertEqual(actual, set(itertools.product((False, True), repeat=count)))
                self.assertIn({'supported': [], 'rejected': list(range(count))}, decisions)
                self.assertIn({'supported': list(range(count)), 'rejected': []}, decisions)
        self.assertEqual(production, before)

    def test_exact_partition_rejects_invalid_claim_counts_and_variants(self):
        for count in (None, True, False, 0, -1, 7, 1.0, '1'):
            with self.assertRaises(ValueError):
                evaluation.exact_partition_schema(count)
        with self.assertRaisesRegex(ValueError, 'invalid_variant'):
            self.evaluate(Model([]), variant='unsupported')
        with self.assertRaisesRegex(ValueError, 'invalid_variant'):
            evaluation.run_bounded(fixtures(), '/never-loaded.gguf', variant='unsupported')

    def test_candidate_changes_only_verifier_schema_and_preserves_fixtures_and_all_decisions(self):
        data = fixtures()
        before = copy.deepcopy(data)
        baseline, candidate = Model([CHECK, REJECT]), Model([CHECK, REJECT])
        baseline_rows = self.evaluate(baseline, data)
        candidate_rows = self.evaluate(candidate, data, variant='exact_partition')
        self.assertEqual(candidate_rows, baseline_rows)
        self.assertEqual(len(candidate.calls), 2)
        for reference, actual in zip(baseline.calls, candidate.calls):
            expected = copy.deepcopy(reference)
            expected['response_format']['schema']['enum'] = [REJECT, CHECK]
            self.assertEqual(actual, expected)
            self.assertEqual(actual['seed'], 7)
        self.assertEqual(data, before)

    def test_candidate_generation_retry_is_not_modified(self):
        case = fixtures()['sources'][0]['cases'][0]
        model = Model([{'claims': [], 'no_claim_reason': 'Later generation request.'}])
        wrapper = evaluation.FixtureModel(model, case, time.monotonic() + 60, variant='exact_partition')
        kwargs = {'messages': [{'role': 'user', 'content': 'original generation'}],
                  'response_format': {'schema': reading.claim_schema('scholarly', [{'id': case['source_span']}])},
                  'max_tokens': 2200, 'temperature': 0.1}
        before = copy.deepcopy(kwargs)
        wrapper.create_chat_completion(**kwargs)
        wrapper.create_chat_completion(**kwargs)
        self.assertEqual(model.calls, [dict(before, seed=7)])
        self.assertEqual(kwargs, before)

    def test_candidate_backend_ignoring_grammar_still_excludes_malformed_and_truncated_negative(self):
        for response, code in (
            (completion({'supported': [], 'rejected': 'BROKEN'}), 'model_schema_invalid'),
            (completion(REJECT, finish='length'), 'model_output_truncated'),
            (completion({'supported': [0], 'rejected': [0]}), 'model_verdict_indices_invalid'),
        ):
            model = Model([response, response])
            rows = self.evaluate(model, variant='exact_partition')
            self.assertEqual(len(model.calls), 2)  # Negative production verdict remains final.
            self.assertTrue(all(row['code'] == code and row['outcome'] is None for row in rows))
            self.assertEqual(evaluation.metrics(rows)['quality_evaluated'], 0)

    def test_candidate_format_retry_preserves_prompt_and_allows_final_rejection(self):
        model = Model([{'supported': [0]}, REJECT] * 2)
        rows = self.evaluate(model, variant='exact_partition')
        self.assertEqual(len(model.calls), 4)
        self.assertEqual([row['outcome'] for row in rows], ['false_rejection', 'true_rejection'])
        self.assertTrue(all(call['response_format']['schema']['enum'] == [REJECT, CHECK] for call in model.calls))
        self.assertTrue(all(call['seed'] == 7 for call in model.calls))
        self.assertTrue(model.calls[1]['messages'][-1]['content'].startswith(model.calls[0]['messages'][-1]['content']))

    def test_production_verifier_prompt_and_every_parameter_unchanged_except_seed(self):
        data = fixtures()
        source = data['sources'][0]
        case = source['cases'][0]
        proposal = {'claims': [{key: case[key] for key in ('field', 'text', 'source_span')}], 'no_claim_reason': ''}
        reference = Model([proposal, CHECK])
        reading.read_chunk(reference, {'id': 'C0001', 'text': SOURCE}, 'scholarly', source['title'])
        model = Model([CHECK, CHECK])
        self.evaluate(model, data)
        self.assertEqual(len(model.calls), 2)
        actual = copy.deepcopy(model.calls[0])
        self.assertEqual(actual.pop('seed'), 7)
        self.assertEqual(actual, reference.calls[1])
        self.assertEqual(model.calls[1]['seed'], 7)
        self.assertNotIn('claims', model.calls[0]['response_format']['schema']['properties'])

    def test_only_first_generation_is_injected_and_backend_gets_later_generation_unchanged(self):
        case = fixtures()['sources'][0]['cases'][0]
        model = Model([{'claims': [], 'no_claim_reason': 'Later generation request.'}, CHECK])
        wrapper = evaluation.FixtureModel(model, case, time.monotonic() + 60)
        kwargs = {'messages': [{'role': 'user', 'content': 'exact original prompt'}],
                  'response_format': {'schema': reading.claim_schema('scholarly', [{'id': case['source_span']}])},
                  'max_tokens': 2200, 'temperature': 0.1}
        before = copy.deepcopy(kwargs)
        initial = wrapper.create_chat_completion(**kwargs)
        self.assertEqual(json.loads(initial['choices'][0]['message']['content'])['claims'][0]['text'], POSITIVE)
        self.assertEqual(model.calls, [])
        wrapper.create_chat_completion(**kwargs)
        self.assertEqual(model.calls[0], dict(before, seed=7))
        self.assertEqual(wrapper.stage, 'generation_retry')
        self.assertEqual(kwargs, before)
        case['text'] = 'A later caller mutation must not change the prescribed fixture.'
        self.assertEqual(wrapper.proposal['text'], POSITIVE)

    def test_verifier_format_retry_is_real_seeded_and_uses_production_retry_prompt(self):
        invalid = {'supported': [0]}  # Missing rejected, but not a discernible rejection.
        model = Model([invalid, CHECK, invalid, CHECK])
        rows = self.evaluate(model)
        self.assertTrue(all(r['status'] == 'accepted' for r in rows))
        self.assertEqual(len(model.calls), 4)
        self.assertTrue(all(call['seed'] == 7 for call in model.calls))
        self.assertEqual(model.calls[1]['messages'][-1]['content'], model.calls[0]['messages'][-1]['content'] +
                         '\nFORMAT RETRY: model_schema_invalid. Return the entire required JSON object. '
                         'Use concise original paraphrases while retaining substantive evidence and qualifications.')
        self.assertEqual(model.calls[0]['response_format'], model.calls[1]['response_format'])

    def test_discernible_negative_verdict_never_retries_even_if_other_fields_invalid(self):
        for answer, code in (
            (REJECT, 'claim_verification_failed'),
            ({'supported': [], 'rejected': [0], 'private_output': SOURCE}, 'model_schema_invalid'),
            ({'supported': [], 'rejected': []}, 'model_verdict_indices_invalid'),
            ({'supported': [0], 'rejected': [0]}, 'model_verdict_indices_invalid'),
        ):
            model = Model([answer, answer])
            rows = self.evaluate(model)
            self.assertEqual(len(model.calls), 2)
            self.assertTrue(all(r['code'] == code for r in rows))
            self.assertTrue(all(r['stage'] == 'verifier' for r in rows))

    def test_malformed_truncated_incomplete_or_invalid_index_negative_is_not_quality_rejection(self):
        for response, code in (
            (completion({'supported': [], 'rejected': 'BROKEN'}), 'model_schema_invalid'),
            (completion(REJECT, finish='length'), 'model_output_truncated'),
            (completion(REJECT, finish=None), 'model_output_incomplete'),
            (completion({'supported': [], 'rejected': [0, 0]}), 'model_verdict_indices_invalid'),
            (completion({'supported': [], 'rejected': [1]}), 'model_verdict_indices_invalid'),
            (completion({'supported': [-1], 'rejected': []}), 'model_verdict_indices_invalid'),
            (completion({'supported': [0], 'rejected': [0]}), 'model_verdict_indices_invalid'),
            (completion({'supported': [False], 'rejected': [0]}), 'model_schema_invalid'),
        ):
            with self.subTest(code=code, response=response):
                model = Model([response, response])
                rows = self.evaluate(model)
                self.assertEqual(len(model.calls), 2)  # Production still rejects without retry.
                self.assertTrue(all(row['code'] == code for row in rows))
                self.assertTrue(all(row['status'] == 'format_error' and row['outcome'] is None for row in rows))
                self.assertEqual(evaluation.metrics(rows)['quality_evaluated'], 0)

    def test_duplicate_acceptance_indexes_do_not_count_as_quality_acceptance(self):
        model = Model([{'supported': [0, 0], 'rejected': []}] * 2)
        rows = self.evaluate(model)
        self.assertEqual(len(model.calls), 2)
        self.assertTrue(all(row['code'] == 'model_verdict_indices_invalid' and row['outcome'] is None for row in rows))

    def test_format_retry_then_valid_rejection_only_counts_valid_final_verdict(self):
        invalid = {'supported': [0]}
        model = Model([invalid, REJECT, invalid, REJECT])
        rows = self.evaluate(model)
        self.assertEqual(len(model.calls), 4)
        self.assertEqual([row['outcome'] for row in rows], ['false_rejection', 'true_rejection'])
        self.assertTrue(all(row['code'] == 'claim_verification_failed' for row in rows))
        self.assertTrue(all(call['seed'] == 7 for call in model.calls))

    def test_original_copy_and_numeric_gates_remain_active_before_verification(self):
        for text, code in (
            (' '.join(SOURCE.split()[:20]), 'copied_source_passage'),
            ('The comparison enrolled 99 students in one classroom setting.', 'unsupported_numeric_claim'),
        ):
            data = fixtures()
            data['sources'][0]['cases'][1]['text'] = text
            model = Model([CHECK])
            rows = self.evaluate(model, data)
            self.assertEqual(rows[1]['code'], code)
            self.assertEqual(rows[1]['outcome'], 'true_rejection')
            self.assertEqual(rows[1]['stage'], 'validator')
            self.assertEqual(len(model.calls), 1)

    def test_format_context_and_backend_errors_are_not_true_rejections(self):
        invalid = {'choices': [{'finish_reason': 'stop', 'message': {'content': 'PRIVATE INVALID ' + SOURCE}}]}
        for values, status in (
            ([invalid] * 4, 'format_error'),
            ([ValueError('deferred_model_context_budget')] * 2, 'context_error'),
            ([ValueError('unverified_model_chat_format')] * 2, 'context_error'),
            ([ValueError('deferred_document_time_budget')] * 2, 'unavailable'),
            ([RuntimeError(SOURCE)] * 2, 'evaluation_error'),
            ([ValueError(SOURCE)] * 2, 'evaluation_error'),
        ):
            with self.subTest(status=status):
                rows = self.evaluate(Model(values))
                self.assertTrue(all(row['status'] == status and row['outcome'] is None for row in rows))
                metrics = evaluation.metrics(rows)
                self.assertEqual(metrics['quality_evaluated'], 0)
                self.assertEqual(metrics['confusion_matrix']['true_rejection'], 0)
                self.assertEqual(metrics['excluded_from_quality'][status], 2)
                self.assertIsNone(metrics['false_acceptance_rate'])
                self.assertNotIn(SOURCE, json.dumps(rows))

    def test_generation_context_gate_is_not_bypassed_by_fixture_injection(self):
        model = Model([])
        with patch.object(reading, 'check_context_budget', side_effect=ValueError('deferred_model_context_budget')) as check:
            rows = self.evaluate(model)
        self.assertEqual(check.call_count, 2)
        self.assertEqual(model.calls, [])
        self.assertTrue(all(row['status'] == 'context_error' for row in rows))
        self.assertTrue(all(row['stage'] == 'generation' for row in rows))

    def test_changed_or_empty_return_cannot_be_claimed_as_fixture_acceptance(self):
        with patch.object(reading, 'read_chunk', return_value=[]):
            rows = self.evaluate(Model([]))
        self.assertTrue(all(row['code'] == 'fixture_proposal_changed' and row['outcome'] is None for row in rows))

    def test_source_claim_privacy_input_immutability_and_no_library_access(self):
        data = fixtures()
        before = copy.deepcopy(data)
        model = Model([CHECK, REJECT])
        emitted = []
        def emit(row):
            emitted.append(copy.deepcopy(row))
            row['source_id'] = 'mutated_callback'
        with patch.object(Path, 'read_text', side_effect=AssertionError('no library reads')), \
             patch.object(Path, 'write_text', side_effect=AssertionError('no writes')), \
             patch.object(Path, 'write_bytes', side_effect=AssertionError('no writes')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('no network')):
            rows = self.evaluate(model, data, emit=emit)
        self.assertEqual(data, before)
        self.assertEqual(rows[0]['source_id'], 'synthetic_source')
        encoded = json.dumps(rows + emitted)
        for private in (SOURCE, POSITIVE, NEGATIVE, before['sources'][0]['title'],
                        before['sources'][0]['doi'], before['sources'][0]['cases'][0]['quote']):
            self.assertNotIn(private, encoded)
        self.assertEqual(rows[0]['source_sha256'], sha256(SOURCE.encode()).hexdigest())

    def test_expired_deadline_does_not_call_backend_and_excludes_all_cases(self):
        model = Model([])
        rows = evaluation.evaluate(fixtures(), model, deadline=time.monotonic() - 1)
        self.assertEqual(model.calls, [])
        self.assertTrue(all(row['code'] == 'deadline_exceeded' and row['outcome'] is None for row in rows))


class BoundedWorkerAndCliTests(unittest.TestCase):
    def test_worker_loads_same_model_seed_and_reports_file_hash_not_verified_identity(self):
        model = Model([CHECK, REJECT])
        backend = Mock()
        backend.Llama.return_value = model
        out = Mock()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'test-only.gguf'
            path.write_bytes(b'original synthetic placeholder, never inference')
            with patch.object(evaluation.os, 'dup2') as dup, patch.dict(sys.modules, {'llama_cpp': backend}):
                evaluation._worker(out, fixtures(), str(path), time.monotonic() + 60)
            self.assertEqual(out.put.call_args_list[0].args[0], {'model_sha256': sha256(path.read_bytes()).hexdigest()})
            self.assertEqual(backend.Llama.call_args.kwargs, {
                'model_path': str(path), 'n_ctx': 6144, 'chat_format': 'chatml',
                'n_threads': min(os.cpu_count() or 2, 4), 'seed': 7, 'verbose': False})
        self.assertEqual([call.args[1] for call in dup.call_args_list], [1, 2])
        self.assertEqual(out.put.call_args_list[-1].args[0], {'done': True})

    def test_missing_model_worker_fails_without_import_or_source_diagnostics(self):
        backend = Mock()
        out = Mock()
        stdout, stderr = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as temp, patch.object(evaluation.os, 'dup2'), \
             patch.dict(sys.modules, {'llama_cpp': backend}), redirect_stdout(stdout), redirect_stderr(stderr):
            evaluation._worker(out, fixtures(), str(Path(temp) / 'missing.gguf'), time.monotonic() + 60)
        backend.Llama.assert_not_called()
        out.put.assert_called_once_with({'worker_failed': True})
        self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')

    def test_worker_suppresses_native_and_python_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'placeholder.gguf'
            path.write_bytes(b'test only')
            script = (
                "import sys, os, types, time\n"
                f"sys.path.insert(0, {str(evaluation.ROOT / 'scripts')!r})\n"
                "import evaluate_claim_quality as e\n"
                "def noisy(**kwargs):\n"
                "    print('PRIVATE PYTHON SOURCE')\n"
                "    print('PRIVATE PYTHON ERROR', file=sys.stderr)\n"
                "    os.write(1, b'PRIVATE NATIVE SOURCE')\n"
                "    os.write(2, b'PRIVATE NATIVE ERROR')\n"
                "    raise RuntimeError('PRIVATE EXCEPTION')\n"
                "sys.modules['llama_cpp'] = types.SimpleNamespace(Llama=noisy)\n"
                "class Output:\n"
                "    def put(self, value): pass\n"
                f"e._worker(Output(), {{}}, {str(path)!r}, time.monotonic() + 10)\n"
            )
            run = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                                 timeout=10, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout + run.stderr, '')

    def test_hard_deadline_kills_native_hang_preserving_completed_results(self):
        data = fixtures()
        context = Mock()
        process = context.Process.return_value
        process.is_alive.return_value = True
        out = context.Queue.return_value
        row = evaluation.initial_rows(data)[0]
        evaluation.set_result(row, 'gate_pass', 'verifier')
        out.get.side_effect = [row, queue.Empty()]
        clock = [0, 0, 0, 0, 0.2, 0.2, 0.95, 0.96, 0.97]
        with patch.object(evaluation.time, 'monotonic', side_effect=clock):
            report = evaluation.run_bounded(data, '/never-loaded.gguf', 1, context=context)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(context.Process.call_args.kwargs['args'][-1], 0.9)
        self.assertLessEqual(sum(call.kwargs['timeout'] for call in process.join.call_args_list), 0.1)
        self.assertEqual(report['status'], 'deadline_exceeded')
        self.assertEqual(report['results'][0]['outcome'], 'true_acceptance')
        self.assertEqual(report['results'][1]['code'], 'deadline_exceeded')
        self.assertEqual(report['metrics']['quality_evaluated'], 1)
        self.assertEqual(report['metrics']['confusion_matrix']['true_rejection'], 0)

    def test_all_budget_values_outside_hard_limit_are_rejected(self):
        for seconds in (0, -1, 721, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                evaluation.run_bounded(fixtures(), '/never-loaded.gguf', seconds)

    def test_untrusted_worker_event_cannot_add_source_text_or_relabel_errors(self):
        rows = evaluation.initial_rows(fixtures())
        initial = copy.deepcopy(rows)
        for mutation in (
            lambda r: r.update(text=SOURCE),
            lambda r: r.update(code=SOURCE),
            lambda r: r.update(source_id=SOURCE),
            lambda r: r.update(expected_supported=False),
            lambda r: r.update(status='format_error', code='model_json_invalid', outcome='true_rejection'),
        ):
            value = copy.deepcopy(rows[0])
            mutation(value)
            evaluation._accept_row(value, rows)
            self.assertEqual(rows, initial)

    def test_worker_failure_and_start_failure_have_only_unavailable_outcomes(self):
        for fails_to_start in (False, True):
            context = Mock()
            process = context.Process.return_value
            process.is_alive.return_value = False
            if fails_to_start:
                process.start.side_effect = RuntimeError(SOURCE)
            else:
                context.Queue.return_value.get.return_value = {'worker_failed': True}
            report = evaluation.run_bounded(fixtures(), '/never-loaded.gguf', 1, context=context)
            self.assertEqual(report['status'], 'worker_failed')
            self.assertEqual(report['metrics']['quality_evaluated'], 0)
            self.assertEqual(report['metrics']['excluded_from_quality']['unavailable'], 2)
            self.assertNotIn(SOURCE, json.dumps(report))

    def test_completed_worker_without_case_results_is_not_success(self):
        context = Mock()
        context.Process.return_value.is_alive.return_value = False
        context.Queue.return_value.get.return_value = {'done': True}
        report = evaluation.run_bounded(fixtures(), '/never-loaded.gguf', 1, context=context)
        self.assertEqual(report['status'], 'worker_failed')
        self.assertEqual(report['metrics']['quality_evaluated'], 0)
        self.assertTrue(all(row['code'] == 'unfinished' for row in report['results']))

    def test_validate_only_cli_is_offline_private_and_can_save_new_external_report(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'fixtures.json'
            source.write_text(json.dumps(fixtures()))
            target = Path(temp) / 'report.json'
            stdout = io.StringIO()
            with patch.object(evaluation, 'run_bounded', side_effect=AssertionError('must not load model')), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('no network')), redirect_stdout(stdout):
                result = evaluation.main(['--fixtures', str(source), '--validate-only', '--report', str(target)])
            self.assertEqual(result, 0)
            self.assertEqual(stdout.getvalue(), target.read_text())
            report = json.loads(stdout.getvalue())
            self.assertEqual(report['status'], 'validated')
            self.assertFalse(report['model_loaded'])
            self.assertEqual(report['fixture_counts']['cases'], 2)
            for private in (SOURCE, POSITIVE, NEGATIVE, str(source)):
                self.assertNotIn(private, stdout.getvalue())

    def test_invalid_fixture_cli_emits_safe_code_without_exception_or_source(self):
        data = fixtures()
        data['sources'][0]['cases'][0]['quote'] = SOURCE
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'fixtures.json'
            source.write_text(json.dumps(data))
            stdout = io.StringIO()
            with patch.object(evaluation, 'run_bounded', side_effect=AssertionError('must not load model')), redirect_stdout(stdout):
                result = evaluation.main(['--fixtures', str(source), '--validate-only'])
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(stdout.getvalue()), {
            'status': 'fixture_invalid', 'variant': 'baseline', 'code': 'fixture_anchor_mismatch', 'model_loaded': False})

    def test_full_cli_uses_local_reading_model_env_and_reports_safe_result(self):
        report = {'status': 'worker_failed', 'results': []}
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'fixtures.json'
            source.write_text(json.dumps(fixtures()))
            stdout = io.StringIO()
            with patch.dict(os.environ, LOCAL_READING_MODEL='/private/model-path.gguf'), \
                 patch.object(evaluation, 'run_bounded', return_value=report) as run, redirect_stdout(stdout):
                result = evaluation.main(['--fixtures', str(source), '--time-budget-seconds', '720'])
            self.assertEqual(run.call_args.args[1:], ('/private/model-path.gguf', 720))
            self.assertEqual(run.call_args.kwargs, {'variant': 'baseline'})
        self.assertEqual(result, 1)
        self.assertEqual(json.loads(stdout.getvalue()), report)
        self.assertNotIn('/private/model-path.gguf', stdout.getvalue())

    def test_candidate_variant_reaches_cli_worker_and_report(self):
        context = Mock()
        context.Process.return_value.is_alive.return_value = False
        context.Queue.return_value.get.return_value = {'worker_failed': True}
        report = evaluation.run_bounded(fixtures(), '/never-loaded.gguf', 1, context=context,
                                        variant='exact_partition')
        self.assertEqual(context.Process.call_args.kwargs['kwargs'], {'variant': 'exact_partition'})
        self.assertEqual(report['variant'], 'exact_partition')
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'fixtures.json'
            source.write_text(json.dumps(fixtures()))
            with patch.object(evaluation, 'run_bounded', return_value=report) as run, redirect_stdout(io.StringIO()):
                evaluation.main(['--fixtures', str(source), '--variant', 'exact_partition'])
            self.assertEqual(run.call_args.kwargs, {'variant': 'exact_partition'})
        backend = Mock()
        backend.Llama.return_value = Model([])
        with tempfile.TemporaryDirectory() as temp:
            model_file = Path(temp) / 'placeholder.gguf'
            model_file.write_bytes(b'test only')
            with patch.object(evaluation.os, 'dup2'), patch.dict(sys.modules, {'llama_cpp': backend}), \
                 patch.object(evaluation, 'evaluate') as evaluate:
                evaluation._worker(Mock(), fixtures(), str(model_file), time.monotonic() + 60,
                                   variant='exact_partition')
            self.assertEqual(evaluate.call_args.kwargs['variant'], 'exact_partition')

    def test_real_spawn_missing_model_produces_safe_worker_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'fixtures.json'
            source.write_text(json.dumps(fixtures()))
            run = subprocess.run([sys.executable, str(evaluation.ROOT / 'scripts/evaluate_claim_quality.py'),
                                  '--fixtures', str(source), '--time-budget-seconds', '10'],
                                 capture_output=True, text=True, timeout=12,
                                 env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                                          LOCAL_READING_MODEL=str(Path(temp) / 'missing.gguf')))
        self.assertEqual(run.returncode, 1)
        self.assertEqual(run.stderr, '')
        report = json.loads(run.stdout)
        self.assertEqual(report['status'], 'worker_failed')
        self.assertIsNone(report['model_sha256'])
        self.assertEqual(report['metrics']['quality_evaluated'], 0)
        self.assertNotIn(SOURCE, run.stdout)

    def test_repository_reports_and_symlink_targets_forbidden_existing_files_not_overwritten(self):
        with self.assertRaises(ValueError):
            evaluation.report_path(evaluation.ROOT / 'report.json')
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / 'repo'
            link.symlink_to(evaluation.ROOT, target_is_directory=True)
            with self.assertRaises(ValueError):
                evaluation.report_path(link / 'report.json')
            existing = Path(temp) / 'existing.json'
            existing.write_text('must retain this file')
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                evaluation.main(['--validate-only', '--report', str(existing)])
            self.assertEqual(existing.read_text(), 'must retain this file')


if __name__ == '__main__':
    unittest.main()
