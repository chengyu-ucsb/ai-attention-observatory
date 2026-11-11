"""Synthetic source-projection regressions; no paper text or model calls."""
import copy
import hashlib
import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_readings
import compose_issue as composer


class EvidenceCoverageTests(unittest.TestCase):
    def record(self):
        return {
            'title': 'A synthetic survey of intended tool use', 'kind': 'scholarly',
            'doi': '10.0000/synthetic', 'url': 'https://example.org/synthetic',
            'analysis': {
                'fulltext_url': 'https://example.org/synthetic',
                'methods': 'A questionnaire design was used. ' * 70
                    + 'The main study included 417 respondents selected by convenience sampling.',
                'results': 'The analysis used a specified estimation procedure. ' * 80
                    + 'The social predictor had no significant association with intention. '
                    + 'The indirect association did not establish a causal sequence.',
                'discussion': 'The authors considered possible explanations, not tested interventions.',
                'limitations': 'Several measurement limitations were considered. ' * 40
                    + 'Self-reported intentions do not establish actual adoption or learning gains. '
                    + 'Unmeasured controls and convenience sampling limit generalization.',
                'extraction_coverage': {
                    'scope': 'bounded_section_excerpts', 'full_document': False,
                    'truncated_sections': ['discussion'],
                    'tables_omitted_by_section': {'results': 1},
                    'table_policy': 'Tables omitted; consult the original.'}}}

    def test_display_caps_do_not_drop_late_results_or_limits_from_model(self):
        record = self.record()
        record['reading'] = build_readings.make_note(record)
        self.assertNotIn('417', record['reading']['methods'])
        self.assertNotIn('social predictor', record['reading']['findings'])
        self.assertNotIn('actual adoption', record['reading']['limitations'])
        for field in ('methods', 'findings', 'limitations'):
            meta = record['reading']['projection_coverage']['fields'][field]
            self.assertGreater(meta['omitted_characters'], 0)
            self.assertFalse(meta['complete_retained_section'])
        packet = composer.evidence([record])[0]
        for key in ('methods', 'results', 'discussion', 'limitations'):
            self.assertIn(record['analysis'][key], packet['evidence'])
        self.assertIn('417 respondents', packet['evidence'])
        self.assertIn('no significant association', packet['evidence'])
        self.assertIn('did not establish a causal sequence', packet['evidence'])
        self.assertIn('actual adoption', packet['evidence'])
        coverage = packet['evidence_coverage']
        self.assertFalse(coverage['downstream_truncation'])
        self.assertFalse(coverage['full_article_review_inferred'])
        self.assertEqual(coverage['upstream']['truncated_sections'], ['discussion'])
        self.assertEqual(coverage['upstream']['tables_omitted_by_section'], {'results': 1})
        self.assertEqual(coverage['fields']['findings']['sha256'], hashlib.sha256(
            record['analysis']['results'].encode()).hexdigest())

    def test_missing_results_do_not_qualify_via_interpretation_or_stale_digest(self):
        record = self.record()
        record['analysis'].pop('results')
        record['reading'] = build_readings.make_note(record)
        record['reading']['digest'] = {'finding': 'A stale apparent benefit from earlier processing.'}
        self.assertEqual(composer.evidence([record]), [])
        self.assertEqual(record['reading']['findings'], '')

    def test_conceptual_framework_keeps_attributed_proposal_not_measured_results(self):
        record = self.record()
        record['analysis'].pop('results')
        record['research_type'] = 'conceptual_framework'
        record['framework_notes'] = {'idea': ('The authors propose a conceptual account of tool use. '
                                    'Their framework separates the choices a learner makes from '
                                    'the actions delegated to an assistant, offering questions for '
                                    'future research rather than claiming that any design has improved learning.'),
                                    'qualification': 'The proposal has not been empirically tested.'}
        record['reading'] = build_readings.make_note(record)
        packet = composer.evidence([record])[0]
        self.assertNotIn('findings:', packet['evidence'])
        self.assertIn('interpretation:', packet['evidence'])
        record['analysis'].pop('discussion')
        record['reading'] = build_readings.make_note(record)
        packet = composer.evidence([record])[0]
        self.assertIn(record['framework_notes']['idea'], packet['evidence'])
        self.assertIn(record['framework_notes']['qualification'], packet['evidence'])
        self.assertEqual(packet['evidence_coverage']['basis'], 'conceptual_framework_notes')
        record['analysis']['results'] = 'Prior experiments reported an effect, not a result of this proposal.'
        packet = composer.evidence([record])[0]
        self.assertNotIn('Prior experiments', packet['evidence'])
        self.assertIn('results', packet['evidence_coverage']['excluded_sections'])

    def test_stale_display_digest_cannot_replace_available_sections(self):
        record = self.record()
        record['reading'] = build_readings.make_note(record)
        record['reading']['digest'] = {'finding': 'STALE HYPOTHESIS', 'approach': 'STALE PILOT'}
        packet = composer.evidence([record])[0]
        self.assertNotIn('STALE', packet['evidence'])
        self.assertIn('417 respondents', packet['evidence'])

    def test_complete_abstract_is_retained_beyond_selected_display_highlights(self):
        text = 'The survey examined intended tool use. ' * 35 + 'There was no improvement in measured retention.'
        record = {'title': 'Synthetic abstract', 'kind': 'scholarly',
                  'url': 'https://example.org/abstract', 'abstract_text': text,
                  'reading': {'level': 'abstract', 'findings': 'The survey examined intended tool use.'}}
        packet = composer.evidence([record])[0]
        self.assertIn(text, packet['evidence'])
        self.assertIn('no improvement', packet['evidence'])

    def test_accepted_summary_does_not_reintroduce_raw_analysis(self):
        record = self.record()
        reading = {'level': 'full_text', 'original_summary': True,
                   'findings': 'The checked original summary preserves the observed finding.',
                   'limitations': 'Its explicit scope and limitations remain attached.'}
        fields, coverage = composer.complete_evidence_fields(record, reading)
        self.assertEqual(fields['findings'], reading['findings'])
        self.assertNotIn(record['analysis']['results'], str(fields))
        self.assertEqual(coverage['basis'], 'accepted_original_reading')

    def test_packet_and_display_coverage_do_not_mutate_source(self):
        record = self.record()
        record['reading'] = build_readings.make_note(record)
        original = copy.deepcopy(record)
        composer.evidence([record])
        self.assertEqual(record, original)

    def test_context_preflight_precedes_every_completion_and_preserves_input(self):
        model = Mock()
        messages = [{'role': 'user', 'content': 'FULL SOURCE TAIL'}]
        with patch('comprehensive_readings.check_context_budget',
                   side_effect=ValueError('deferred_model_context_budget')) as check:
            with self.assertRaisesRegex(ValueError, 'deferred_model_context_budget'):
                composer.checked_completion(model, messages=messages, max_tokens=123)
        check.assert_called_once_with(model, messages, 123)
        model.create_chat_completion.assert_not_called()
        self.assertEqual(messages[0]['content'], 'FULL SOURCE TAIL')

    def test_truncated_or_interrupted_output_is_not_salvaged(self):
        for reason in ('length', 'interrupted'):
            model = Mock()
            model.create_chat_completion.return_value = {
                'choices': [{'finish_reason': reason, 'message': {'content': '{"text":"apparently valid"}'}}]}
            with self.subTest(reason=reason), patch('comprehensive_readings.check_context_budget'):
                with self.assertRaisesRegex(ValueError, 'Edition model output incomplete'):
                    composer.checked_completion(model, messages=[], max_tokens=123)

    def test_default_runtime_matches_verified_context_and_chat_template(self):
        constructor = Mock()
        packet = [{'key': f'S{i}', 'evidence': 'Synthetic retained source evidence.'}
                  for i in range(1, 4)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            with patch.object(composer, 'pending', return_value={'run': {'date': '2026-11-11'}, 'items': []}), \
                 patch.object(composer, 'evidence', return_value=packet), \
                 patch.object(composer, 'draft_in_stages', side_effect=ValueError('stop before generation')), \
                 patch.dict('os.environ', {'LOCAL_ISSUE_MODEL': 'synthetic-model-path'}), \
                 patch.dict(sys.modules, {'llama_cpp': SimpleNamespace(Llama=constructor)}):
                with self.assertRaisesRegex(ValueError, 'stop before generation'):
                    composer.compose(root)
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs['n_ctx'], 24576)
        self.assertEqual(kwargs['chat_format'], 'chatml')
        self.assertFalse(kwargs['use_mmap'])
        constructor.return_value.create_chat_completion.assert_not_called()


if __name__ == '__main__':
    unittest.main()
