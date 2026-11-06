"""Offline reproductions of the live reader's JSON/schema failures.

Controlled responses test recovery, not real-model source comprehension.
"""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import comprehensive_readings as reading
from full_document_access import Document


SOURCE = 'The classroom comparison included 47 students who completed a structured task and did not establish independent transfer.'
CLAIM = {'field': 'limitations',
         'text': 'Independent learning beyond the classroom was not established in this comparison.',
         'quote': SOURCE}
PROPOSAL = {'field': CLAIM['field'], 'text': CLAIM['text'], 'source_span': 'C0001:S001'}
ANSWER = {'claims': [PROPOSAL], 'no_claim_reason': ''}
CHECK = {'supported': [0], 'rejected': []}
CHUNK = {'id': 'C0001', 'text': SOURCE}


def completion(value, finish='stop'):
    content = value if isinstance(value, str) else json.dumps(value)
    return {'choices': [{'finish_reason': finish, 'message': {'content': content}}]}


def model_with(*values):
    model = Mock()
    model.create_chat_completion.side_effect = [completion(value) for value in values]
    return model


class SynthesisFormatTests(unittest.TestCase):
    def test_source_spans_preserve_text_and_anchor_bounds(self):
        for count in (5, 6, 23, 24, 25, 32, 33, 40, 90, 901):
            text = '  ' + '\n\t'.join('word'+str(n) for n in range(count)) + '  '
            spans = reading.source_spans({'id': 'C0002', 'text': text})
            self.assertEqual(''.join(s['text'] for s in spans), text)
            self.assertTrue(all(5 <= len(s['text'].split()) <= 24 for s in spans))
            self.assertTrue(all(s['id'].startswith('C0002:') for s in spans))
            self.assertEqual(spans[0]['start'], 0)
            self.assertEqual(spans[-1]['end'], len(text))
        text = 'These source words include human–AI co-regulation and “quoted” terms.'
        self.assertEqual(''.join(s['text'] for s in reading.source_spans({'id': 'C0001', 'text': text})), text)

    def test_too_short_source_is_deferred_not_omitted(self):
        for count in (0, 1, 4):
            model = Mock()
            with self.assertRaisesRegex(ValueError, '^deferred_chunk_without_evidence_span$'):
                reading.read_chunk(model, {'id':'C0001','text':'word '*count}, 'scholarly', 'Title')
            model.create_chat_completion.assert_not_called()

    def test_unknown_or_cross_chunk_span_cannot_be_used(self):
        for ident in ('C9999:S001', 'C0001:S999', None):
            bad = {'claims':[dict(PROPOSAL, source_span=ident)],'no_claim_reason':''}
            model = model_with(bad, ANSWER, CHECK)
            with self.assertRaisesRegex(ValueError, '^unknown_source_span$'):
                reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
            self.assertEqual(model.create_chat_completion.call_count, 1)
            with patch.object(reading, 'model_json', return_value=bad):
                with self.assertRaisesRegex(ValueError, '^unknown_source_span$'):
                    reading.read_chunk(Mock(), CHUNK, 'scholarly', 'Title')
        missing = {'claims':[{'field':PROPOSAL['field'],'text':PROPOSAL['text']}], 'no_claim_reason':''}
        model = model_with(missing, ANSWER, CHECK)
        with self.assertRaisesRegex(ValueError, '^unknown_source_span$'):
            reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
        self.assertEqual(model.create_chat_completion.call_count, 1)
        model = Mock()
        model.create_chat_completion.side_effect = [completion(missing, 'length'), completion(ANSWER), completion(CHECK)]
        with self.assertRaisesRegex(ValueError, '^unknown_source_span$'):
            reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
        self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_valid_span_id_is_not_treated_as_claim_support(self):
        source = ('Background context describes the classroom setting and explains the historical motivation for studying this learning question. '
                  'The intervention did not improve delayed retention and the authors explicitly caution against generalizing beyond this sample.')
        chunk = {'id':'C0001','text':source}
        spans = reading.source_spans(chunk)
        proposal = {'field':'reported_results',
                    'text':'The intervention improved delayed retention in this classroom comparison.',
                    'source_span':spans[0]['id']}
        model = model_with({'claims':[proposal],'no_claim_reason':''}, {'supported':[],'rejected':[0]})
        with self.assertRaisesRegex(ValueError, '^claim_verification_failed$'):
            reading.read_chunk(model, chunk, 'scholarly', 'Title')
        calls = model.create_chat_completion.call_args_list
        for span in spans:
            self.assertIn(span['text'], calls[0].kwargs['messages'][-1]['content'])
        self.assertIn(source, calls[1].kwargs['messages'][-1]['content'])
        self.assertIn('not an unrelated', calls[1].kwargs['messages'][-1]['content'])
        self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_context_preflight_uses_full_rendered_template_and_output_budget(self):
        rendered = SimpleNamespace(prompt='RENDERED SYSTEM + SOURCE + CHAT TOKENS', added_special=False)
        formatter = Mock(return_value=rendered)
        module = SimpleNamespace(format_chatml=formatter)
        model = Mock(chat_format='chatml')
        model.n_ctx.return_value = 2400
        model.tokenize.return_value = [1] * 300
        messages = [{'role':'system','content':'System'}, {'role':'user','content':'Source'}]
        with patch.dict(sys.modules, {'llama_cpp.llama_chat_format':module}):
            with self.assertRaisesRegex(ValueError, '^deferred_model_context_budget$'):
                reading.check_context_budget(model, messages, 2200)
            model.n_ctx.return_value = 2500
            reading.check_context_budget(model, messages, 2200)
        formatter.assert_called_with(messages=messages)
        model.tokenize.assert_called_with(rendered.prompt.encode(), add_bos=True, special=True)
        model.create_chat_completion.assert_not_called()

    def test_unverified_chat_format_cannot_skip_context_preflight(self):
        model = Mock(chat_format='other')
        model.n_ctx.return_value = 6144
        with self.assertRaisesRegex(ValueError, '^unverified_model_chat_format$'):
            reading.check_context_budget(model, [], 2200)
        model.tokenize.assert_not_called()

    def test_generation_and_verification_are_schema_constrained(self):
        model = model_with(ANSWER, CHECK)
        self.assertEqual(reading.read_chunk(model, CHUNK, 'scholarly', 'Title'), [CLAIM])
        calls = model.create_chat_completion.call_args_list
        self.assertEqual(calls[0].kwargs['response_format']['schema'], reading.claim_schema('scholarly', reading.source_spans(CHUNK)))
        self.assertEqual(calls[1].kwargs['response_format']['schema'], reading.verification_schema())
        self.assertEqual(calls[0].kwargs['max_tokens'], 2200)
        self.assertEqual(calls[1].kwargs['max_tokens'], 500)
        self.assertIn('limitations', calls[0].kwargs['response_format']['schema']['properties']['claims']['items']['properties']['field']['enum'])

    def test_malformed_json_can_recover_once_before_all_evidence_checks(self):
        model = model_with('{"claims":[', ANSWER, CHECK)
        self.assertEqual(reading.read_chunk(model, CHUNK, 'scholarly', 'Title'), [CLAIM])
        retry = model.create_chat_completion.call_args_list[1].kwargs['messages'][-1]['content']
        self.assertIn('FORMAT RETRY: model_json_invalid', retry)
        self.assertIn(SOURCE, retry)
        self.assertEqual(model.create_chat_completion.call_count, 3)

    def test_schema_failure_is_retried_not_coerced(self):
        for bad in ({'claims': 'not a list', 'no_claim_reason': ''},
                    {'summary': 'A different output contract'}, [],
                    {'claims': [dict(PROPOSAL, field='invented')], 'no_claim_reason': ''},
                    {'claims': [PROPOSAL] * 7, 'no_claim_reason': ''}):
            with self.subTest(bad=bad):
                model = model_with(bad, ANSWER, CHECK)
                self.assertEqual(reading.read_chunk(model, CHUNK, 'scholarly', 'Title'), [CLAIM])
                self.assertEqual(model.create_chat_completion.call_count, 3)

    def test_valid_json_marked_truncated_is_not_accepted(self):
        model = Mock()
        model.create_chat_completion.side_effect = [completion(ANSWER, 'length'), completion(ANSWER), completion(CHECK)]
        self.assertEqual(reading.read_chunk(model, CHUNK, 'scholarly', 'Title'), [CLAIM])
        self.assertIn('model_output_truncated', model.create_chat_completion.call_args_list[1].kwargs['messages'][-1]['content'])
        self.assertEqual(model.create_chat_completion.call_count, 3)

    def test_repeated_truncation_fails_closed(self):
        model = Mock()
        model.create_chat_completion.return_value = completion(ANSWER, 'length')
        with self.assertRaisesRegex(ValueError, '^model_output_truncated$'):
            reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
        self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_malformed_json_stops_after_two_calls(self):
        model = model_with('{', '{')
        with self.assertRaisesRegex(ValueError, '^model_json_invalid$'):
            reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
        self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_numeric_copy_and_length_rejections_do_not_retry(self):
        invalid = [
            (dict(PROPOSAL, text='The comparison established learning gains in 500 students.'), 'numeric'),
            (dict(PROPOSAL, text=SOURCE), 'copied'),
            (dict(PROPOSAL, text='Too short.'), 'length'),
        ]
        for claim, reason in invalid:
            with self.subTest(reason=reason):
                model = model_with({'claims': [claim], 'no_claim_reason': ''})
                with self.assertRaisesRegex(ValueError, reason):
                    reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
                self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_repaired_format_does_not_bypass_evidence_validation(self):
        bad = {'claims': [dict(PROPOSAL, text='The comparison established learning gains in 500 students.')], 'no_claim_reason': ''}
        model = model_with('{', bad)
        with self.assertRaisesRegex(ValueError, 'unsupported_numeric_claim'):
            reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
        self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_second_pass_rejection_and_missing_indexes_do_not_retry(self):
        for verdict, reason in (({'supported': [], 'rejected': [0]}, 'claim_verification_failed'),
                                ({'supported': [], 'rejected': []}, 'verifier_indices_invalid'),
                                ({'supported': [1], 'rejected': []}, 'verifier_indices_invalid')):
            with self.subTest(verdict=verdict):
                model = model_with(ANSWER, verdict, CHECK)
                with self.assertRaisesRegex(ValueError, '^'+reason+'$') as raised:
                    reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
                self.assertNotIsInstance(raised.exception, reading.ModelFormatError)
                self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_second_pass_format_repair_still_requires_all_indexes(self):
        model = model_with(ANSWER, {'supported': [True], 'rejected': []}, CHECK)
        self.assertEqual(reading.read_chunk(model, CHUNK, 'scholarly', 'Title'), [CLAIM])
        self.assertEqual(model.create_chat_completion.call_count, 3)

    def test_explicit_verifier_rejection_cannot_be_retried_as_malformed(self):
        for verdict in ({'supported': [True], 'rejected': [0]},
                        {'supported': [], 'rejected': [], 'extra': 'malformed'},
                        {'supported': [0], 'rejected': 'claim is unsupported'},
                        {'supported': [0], 'rejected': None},
                        {'supported': [0], 'rejected': False},
                        {'supported': [0], 'rejected': [False]},
                        {'supported': 'not indexes', 'rejected': [0]},
                        {'rejected': [0]},
                        {'supported': []}):
            with self.subTest(verdict=verdict):
                model = model_with(ANSWER, verdict, CHECK)
                with self.assertRaisesRegex(ValueError, '^verifier_schema_invalid$') as raised:
                    reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
                self.assertNotIsInstance(raised.exception, reading.ModelFormatError)
                self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_explicit_rejection_is_final_even_when_completion_reports_length(self):
        for verdict in ({'supported': [], 'rejected': [0]},
                        {'supported': [], 'rejected': []},
                        {'supported': [0], 'rejected': [0]},
                        {'rejected': [0]}):
            for finish, reason in (('length', 'verifier_output_truncated'),
                                   ('content_filter', 'verifier_output_incomplete'),
                                   (None, 'verifier_output_incomplete')):
                with self.subTest(verdict=verdict, finish=finish):
                    model = Mock()
                    model.create_chat_completion.side_effect = [completion(ANSWER),
                        completion(verdict, finish), completion(CHECK)]
                    with self.assertRaisesRegex(ValueError, '^'+reason+'$') as raised:
                        reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
                    self.assertNotIsInstance(raised.exception, reading.ModelFormatError)
                    self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_verifier_partitions_require_unique_in_range_disjoint_and_all_indexes(self):
        for count, verdict in (
            (1, {'supported': [0, 0], 'rejected': []}),
            (1, {'supported': [], 'rejected': [0, 0]}),
            (1, {'supported': [0], 'rejected': [0]}),
            (1, {'supported': [0, 1], 'rejected': []}),
            (1, {'supported': [], 'rejected': [1]}),
            (1, {'supported': [-1], 'rejected': [0]}),
            (1, {'supported': [0], 'rejected': [-1]}),
            (2, {'supported': [0], 'rejected': []}),
            (2, {'supported': [], 'rejected': [0]}),
            (3, {'supported': [0], 'rejected': [1]}),
        ):
            with self.subTest(count=count, verdict=verdict):
                model = model_with(verdict, {'supported': list(range(count)), 'rejected': []})
                with self.assertRaisesRegex(ValueError, '^verifier_indices_invalid$') as raised:
                    reading.model_json(model, 'Verify claims', schema=reading.verification_schema(),
                                       claim_count=count)
                self.assertNotIsInstance(raised.exception, reading.ModelFormatError)
                self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_only_complete_valid_negative_partitions_are_semantic_rejections(self):
        for verdict in ({'supported': [2, 0], 'rejected': [1]},
                        {'supported': [], 'rejected': [2, 0, 1]},
                        {'supported': [0], 'rejected': [2, 1]}):
            with self.subTest(verdict=verdict):
                model = model_with(verdict)
                with self.assertRaisesRegex(ValueError, '^claim_verification_failed$'):
                    reading.model_json(model, 'Verify claims', schema=reading.verification_schema(),
                                       claim_count=3)
                self.assertEqual(model.create_chat_completion.call_count, 1)
        accepted = {'supported': [2, 0, 1], 'rejected': []}
        model = model_with(accepted)
        self.assertEqual(reading.model_json(model, 'Verify claims',
                         schema=reading.verification_schema(), claim_count=3), accepted)
        self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_final_read_chunk_gate_rechecks_schema_and_exact_partition(self):
        for verdict, reason in (({'supported': [0, 0], 'rejected': []}, 'verifier_indices_invalid'),
                                ({'supported': [], 'rejected': []}, 'verifier_indices_invalid'),
                                ({'supported': [0]}, 'verifier_schema_invalid'),
                                ({'supported': [], 'rejected': [0]}, 'claim_verification_failed')):
            with self.subTest(verdict=verdict):
                with patch.object(reading, 'model_json', side_effect=[ANSWER, verdict]):
                    with self.assertRaisesRegex(ValueError, '^'+reason+'$'):
                        reading.read_chunk(Mock(), CHUNK, 'scholarly', 'Title')

    def test_every_complete_partition_accepts_only_unanimous_support(self):
        for count in range(1, 7):
            for mask in range(1 << count):
                verdict = {'supported': [i for i in range(count) if mask & (1 << i)],
                           'rejected': [i for i in range(count) if not mask & (1 << i)]}
                with self.subTest(count=count, mask=mask):
                    model = model_with(verdict)
                    if verdict['rejected']:
                        with self.assertRaisesRegex(ValueError, '^claim_verification_failed$'):
                            reading.model_json(model, 'Verify claims',
                                schema=reading.verification_schema(), claim_count=count)
                    else:
                        self.assertEqual(reading.model_json(model, 'Verify claims',
                            schema=reading.verification_schema(), claim_count=count), verdict)
                    self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_pure_verifier_format_errors_keep_only_one_retry(self):
        for verdict, reason in (({'supported': [True], 'rejected': []}, 'model_schema_invalid'),
                                ({'supported': [0]}, 'model_schema_invalid'),
                                ({'rejected': []}, 'model_schema_invalid'),
                                ({**CHECK, 'extra': 'malformed'}, 'model_schema_invalid'),
                                ([], 'model_schema_invalid'),
                                ('{"supported": [], "rejected": [0]', 'model_json_invalid')):
            with self.subTest(verdict=verdict):
                # Undecodable JSON is never mined for a partial verdict, even
                # when its prefix contains text resembling rejected indexes.
                model = model_with(ANSWER, verdict, CHECK)
                self.assertEqual(reading.read_chunk(model, CHUNK, 'scholarly', 'Title'), [CLAIM])
                self.assertEqual(model.create_chat_completion.call_count, 3)
                self.assertIn('FORMAT RETRY: '+reason,
                              model.create_chat_completion.call_args_list[2].kwargs['messages'][-1]['content'])
                model = model_with(ANSWER, verdict, verdict, CHECK)
                with self.assertRaisesRegex(reading.ModelFormatError, '^'+reason+'$'):
                    reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
                self.assertEqual(model.create_chat_completion.call_count, 3)

    def test_pure_verifier_truncation_or_incomplete_output_keeps_bounded_retry(self):
        for finish, reason in (('length', 'model_output_truncated'),
                               (None, 'model_output_incomplete')):
            with self.subTest(finish=finish):
                model = Mock()
                model.create_chat_completion.side_effect = [completion(ANSWER),
                    completion(CHECK, finish), completion(CHECK)]
                self.assertEqual(reading.read_chunk(model, CHUNK, 'scholarly', 'Title'), [CLAIM])
                self.assertEqual(model.create_chat_completion.call_count, 3)
                model = Mock()
                model.create_chat_completion.side_effect = [completion(ANSWER),
                    completion(CHECK, finish), completion(CHECK, finish), completion(CHECK)]
                with self.assertRaisesRegex(reading.ModelFormatError, '^'+reason+'$'):
                    reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
                self.assertEqual(model.create_chat_completion.call_count, 3)

    def test_verifier_format_retry_cannot_retry_a_later_invalid_partition(self):
        model = model_with(ANSWER, {'supported': [True], 'rejected': []},
                           {'supported': [0], 'rejected': [0]}, CHECK)
        with self.assertRaisesRegex(ValueError, '^verifier_indices_invalid$') as raised:
            reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
        self.assertNotIsInstance(raised.exception, reading.ModelFormatError)
        self.assertEqual(model.create_chat_completion.call_count, 3)

    def test_empty_claims_need_a_substantive_explanation(self):
        model = model_with({'claims': [], 'no_claim_reason': ''})
        with self.assertRaisesRegex(ValueError, 'unexplained_empty_segment'):
            reading.read_chunk(model, CHUNK, 'scholarly', 'Title')
        self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_document_deadline_blocks_a_format_retry(self):
        model = model_with('{')
        with patch.object(reading.time, 'monotonic', side_effect=[1, 11]):
            with self.assertRaisesRegex(ValueError, 'deferred_document_time_budget'):
                reading.read_chunk(model, CHUNK, 'scholarly', 'Title', deadline=10)
        self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_document_deadline_blocks_second_pass_and_publication(self):
        model = model_with(ANSWER)
        with patch.object(reading.time, 'monotonic', side_effect=[1, 2, 11]):
            with self.assertRaisesRegex(ValueError, 'deferred_document_time_budget'):
                reading.read_chunk(model, CHUNK, 'scholarly', 'Title', deadline=10)
        self.assertEqual(model.create_chat_completion.call_count, 1)

    def test_failed_synthesis_preserves_previous_reading_and_saves_no_source(self):
        previous = {'version': 2, 'source_depth': 'full_text', 'limitations': 'Existing note.'}
        record = {'kind': 'scholarly', 'title': 'Title', 'deep_analysis': copy.deepcopy(previous)}
        doc = Document([{'location': 'page:1', 'text': SOURCE}], 'https://www.econstor.eu/paper.pdf',
                       coverage={'evidence_status': 'full_document_retrieved'})
        model = model_with('{', '{')
        with patch.object(reading, 'screen_source', return_value={'decision': 'include'}):
            stats = reading.process([record], model, retriever=lambda row: (doc, []))
        self.assertEqual(stats['documents_retrieved'], 1)
        self.assertEqual(stats['summaries_completed'], 0)
        self.assertEqual(stats['failure_stages'], {'synthesis': 1})
        self.assertEqual(record['complete_reading_attempt']['stage'], 'synthesis')
        self.assertEqual(record['complete_reading_attempt']['status'], 'model_json_invalid')
        self.assertEqual(record['deep_analysis'], previous)
        self.assertNotIn(SOURCE, json.dumps(record))
        self.assertNotIn(CLAIM['quote'], json.dumps(record))

    def test_invalid_verifier_is_recorded_without_semantic_rejection_or_rewrite(self):
        previous = {'version': 2, 'source_depth': 'full_text', 'limitations': 'Existing note.'}
        record = {'kind': 'scholarly', 'title': 'Title', 'deep_analysis': copy.deepcopy(previous)}
        doc = Document([{'location': 'page:1', 'text': SOURCE}], 'https://www.econstor.eu/paper.pdf',
                       coverage={'evidence_status': 'full_document_retrieved'})
        model = model_with(ANSWER, {'supported': [0], 'rejected': [0]}, CHECK)
        with patch.object(reading, 'screen_source', return_value={'decision': 'include'}):
            stats = reading.process([record], model, retriever=lambda row: (doc, []))
        self.assertEqual(stats['summaries_completed'], 0)
        self.assertEqual(stats['failure_stages'], {'synthesis': 1})
        self.assertEqual(stats['failure_reasons'], {'verifier_indices_invalid': 1})
        self.assertEqual(record['complete_reading_attempt']['status'], 'verifier_indices_invalid')
        self.assertEqual(record['deep_analysis'], previous)
        self.assertNotIn('claim_verification_failed', json.dumps(record))
        self.assertNotIn(SOURCE, json.dumps(record))
        self.assertEqual(model.create_chat_completion.call_count, 2)

    def test_no_source_is_retrieval_failure_and_never_calls_model(self):
        record = {'kind': 'scholarly', 'title': 'Title'}
        model = Mock()
        with patch.object(reading, 'screen_source', return_value={'decision': 'include'}):
            stats = reading.process([record], model, retriever=lambda row: (None, []))
        self.assertEqual(stats['failure_stages'], {'retrieval': 1})
        self.assertEqual(record['complete_reading_attempt']['stage'], 'retrieval')
        model.create_chat_completion.assert_not_called()

    def test_completed_synthesis_still_saves_anchors_as_hashes_only(self):
        doc = Document([{'location': 'page:1', 'text': SOURCE}], 'https://www.econstor.eu/paper.pdf',
                       coverage={'evidence_status': 'full_document_retrieved'})
        result = reading.synthesize(doc, model_with('{', ANSWER, CHECK), 'scholarly', 'Title')
        self.assertTrue(result['coverage']['all_retrieved_text_processed'])
        self.assertEqual(result['coverage']['chunks_processed'], result['coverage']['chunks_total'])
        self.assertEqual(result['coverage']['claims_checked'], 1)
        self.assertNotIn(CLAIM['quote'], json.dumps(result))
        self.assertNotIn(SOURCE, json.dumps(result))


if __name__ == '__main__':
    unittest.main()
