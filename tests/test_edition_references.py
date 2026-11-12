"""Reference selection prevents transcription failures, not factual mistakes."""
import copy
import json
import re
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compose_issue as composer
import edition_references as refs
import test_compose_issue


class ReferenceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.draft, self.packet = test_compose_issue.CompositionTests().fixture()

    def selected_section(self, index=0):
        section = copy.deepcopy(self.draft['signals'][index])
        keys = [anchor['key'] for anchor in section['evidence']]
        sources = [source for source in self.packet if source['key'] in keys]
        section['citations'] = {entry['key']: entry['text'] for entry in section['citations']}
        section['evidence'] = {source['key']: next(iter(refs.source_options(source))) for source in sources}
        return section, sources

    def selected_review(self):
        passage = next(iter(refs.draft_passages(self.draft)))
        return {'decision': 'pass', 'checks': {criterion: {
            'pass': True, 'reason': 'The named source and its observed outcome remain clearly distinguished here.',
            'example_id': passage} for criterion in composer.REVIEW_CRITERIA},
            'source_checks': {source['key']: {
                'anchor_id': next(iter(refs.source_options(source))), 'claim_id': passage,
                'supported': True} for source in self.packet}, 'issues': []}

    def test_passages_are_exact_bounded_and_include_late_limitations(self):
        source = {'key': 'S7', 'evidence': '\n'.join(
            f'Finding {i} describes a different condition and its reported observation.' for i in range(80))
            + '\nLimitations include self selection and a short period of observation.'}
        options = refs.source_options(source)
        self.assertEqual(options, refs.source_options(source))
        self.assertLessEqual(len(options), 20)
        self.assertTrue(any('Limitations' in quote for quote in options.values()))
        for quote in options.values():
            self.assertIn(quote, source['evidence'])
            self.assertTrue(5 <= len(composer.normalize(quote).split()) <= 12)

    def test_source_selections_still_pass_normal_citation_and_copying_gates(self):
        section, sources = self.selected_section()
        resolved = refs.resolve_section_references(section, sources)
        composer.validate_section(resolved, sources)
        composer.resolve_inline_citations(resolved, sources)
        self.assertIsInstance(section['evidence'], dict)  # Do not mutate the audit candidate.
        resolved['text'] += ' The improvement was 987 percent.'
        with self.assertRaisesRegex(ValueError, 'Unsupported numeric'):
            composer.validate_section(resolved, sources)

    def test_required_source_paragraphs_render_unambiguous_named_citations(self):
        sources = self.packet[:2]
        prose = self.draft['signals'][0]['text'].split('address this question. ', 1)[1]
        raw = {'source_notes': {'S1': prose, 'S2': prose},
               'comparison': ' '.join(prose.split()[:35]),
               'evidence': {source['key']: next(iter(refs.source_options(source))) for source in sources}}
        resolved = refs.resolve_section_references(raw, sources)
        self.assertNotIn('source_notes', resolved)
        self.assertEqual(resolved['text'].count('Source 1'), 1)
        self.assertEqual(resolved['text'].count('Source 2'), 1)
        composer.validate_section(resolved, sources)
        composer.resolve_inline_citations(resolved, sources)
        for change in ('missing', 'empty', 'mixed'):
            bad = copy.deepcopy(raw)
            if change == 'missing': bad['source_notes'].pop('S2')
            if change == 'empty': bad['source_notes']['S2'] = ''
            if change == 'mixed': bad['citations'] = {'S1': 'Invented link'}
            with self.subTest(change=change), self.assertRaises(ValueError):
                refs.resolve_section_references(bad, sources)

    def test_repeated_author_mentions_do_not_duplicate_the_rendered_source_link(self):
        sources = copy.deepcopy(self.packet[:2])
        sources[0]['authors'] = ['Jing Zhan']
        sources[1]['authors'] = ['Michael Agyemang Adarkwah', 'Esinam Afi Kayi']
        prose = self.draft['signals'][0]['text'].split('address this question. ', 1)[1]
        raw = {'source_notes': {'S1': "Jing Zhan's account considers this question. " + prose,
                                'S2': "Michael Agyemang Adarkwah's account considers this question. " + prose},
               'comparison': ' '.join(prose.split()[:35]),
               'evidence': {source['key']: next(iter(refs.source_options(source))) for source in sources}}
        resolved = refs.resolve_section_references(raw, sources)
        self.assertEqual(resolved['text'].count('Jing Zhan'), 2)
        self.assertEqual(resolved['text'].count('Jing Zhan:'), 1)
        composer.validate_section(resolved, sources)
        composer.resolve_inline_citations(resolved, sources)

    def test_internal_references_are_named_and_unknown_sources_are_rejected(self):
        sources = copy.deepcopy(self.packet[:2])
        sources[0]['authors'] = ['Jing Zhan']
        sources[1]['authors'] = ['Michael Adarkwah']
        prose = self.draft['signals'][0]['text'].split('address this question. ', 1)[1]
        raw = {'source_notes': {'S1': prose, 'S2': prose},
               'comparison': 'S1 and S2 ask related questions. ' + ' '.join(prose.split()[:35]),
               'evidence': {source['key']: next(iter(refs.source_options(source))) for source in sources}}
        resolved = refs.resolve_section_references(raw, sources)
        self.assertIn('Jing Zhan and Michael Adarkwah ask related questions.', resolved['text'])
        self.assertNotRegex(resolved['text'], r'\bS\d+\b')
        composer.validate_section(resolved, sources)
        composer.resolve_inline_citations(resolved, sources)
        raw['comparison'] += ' S99 adds another finding.'
        with self.assertRaisesRegex(ValueError, 'Unknown source reference'):
            refs.resolve_section_references(raw, sources)

    def test_frame_schema_keeps_numbers_in_evidence_bearing_sections(self):
        schema = refs.frame_response_schema(self.packet)
        for field in ('headline', 'deck', 'letter', 'closer'):
            pattern = schema['properties'][field]['pattern']
            self.assertIsNotNone(re.fullmatch(pattern, 'Learning outcomes remain uncertain.'))
            self.assertIsNone(re.fullmatch(pattern, 'The mean was 4.58.'))
        citation = schema['properties']['tension']['properties']['citations']['items']
        self.assertEqual(citation['properties']['key']['enum'], ['S1', 'S2', 'S3', 'S4'])

    def test_missing_cross_source_or_fabricated_choices_are_never_repaired(self):
        section, sources = self.selected_section()
        for mutation in ('missing', 'foreign', 'invented', 'missing_citation'):
            bad = copy.deepcopy(section)
            if mutation == 'missing': bad['evidence'].pop('S2')
            if mutation == 'foreign': bad['evidence']['S1'] = bad['evidence']['S2']
            if mutation == 'invented': bad['evidence']['S1'] = 'S1-A999'
            if mutation == 'missing_citation': bad['citations'].pop('S1')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                refs.resolve_section_references(bad, sources)

    def test_old_free_form_quotes_are_not_silently_replaced_with_real_passages(self):
        bad = copy.deepcopy(self.draft['signals'][0])
        bad['evidence'][0]['quote'] = 'invented source words that cannot be found'
        with self.assertRaisesRegex(ValueError, 'does not match source'):
            composer.validate_section(refs.resolve_section_references(bad, self.packet[:2]), self.packet[:2])

    def test_staged_writer_uses_schema_and_resolves_selected_ids(self):
        sections = [self.selected_section(i)[0] for i in range(3)]
        plan = {'themes': [{'short': section['short'], 'title': section['title'],
                            'keys': list(section['evidence'])} for section in sections]}
        for section in sections:
            prose = section['text'].split('address this question. ', 1)[1]
            section['source_notes'] = {key: ' '.join(prose.split()[:42]) for key in section['evidence']}
            section['comparison'] = ' '.join(prose.split()[42:80])
            section.pop('text'); section.pop('citations')
        frame = {key: value for key, value in copy.deepcopy(self.draft).items() if key != 'signals'}
        frame['tension'].pop('evidence')
        model = Mock()
        model.create_chat_completion.side_effect = [
            {'choices': [{'message': {'content': json.dumps(value)}}]} for value in [plan, *sections, frame]]
        result = composer.draft_in_stages(model, self.packet, {})
        self.assertEqual(model.create_chat_completion.call_count, 5)
        schema = model.create_chat_completion.call_args_list[1].kwargs['response_format']['schema']
        self.assertEqual(set(schema['properties']['evidence']['required']), {'S1', 'S2'})
        self.assertNotIn('S2-A01', schema['properties']['evidence']['properties']['S1']['enum'])
        self.assertEqual(set(schema['properties']['source_notes']['required']), {'S1', 'S2'})
        self.assertIn('pattern', model.create_chat_completion.call_args_list[-1].kwargs[
            'response_format']['schema']['properties']['letter'])
        self.assertTrue(all(anchor['quote'] for section in result['signals'] for anchor in section['evidence']))

    def test_review_resolves_real_passages_but_cannot_override_an_unsupported_judgment(self):
        review = self.selected_review()
        resolved = refs.resolve_review_references(review, self.draft, self.packet, composer.REVIEW_CRITERIA)
        composer.validate_editorial_review(resolved, self.draft, self.packet)
        review['source_checks']['S1']['supported'] = False
        resolved = refs.resolve_review_references(review, self.draft, self.packet, composer.REVIEW_CRITERIA)
        with self.assertRaisesRegex(ValueError, 'cannot pass'):
            composer.validate_editorial_review(resolved, self.draft, self.packet)
        for field, value in (('anchor_id', 'S2-A01'), ('claim_id', 'D999')):
            bad = self.selected_review(); bad['source_checks']['S1'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                refs.resolve_review_references(bad, self.draft, self.packet, composer.REVIEW_CRITERIA)

    def test_separate_review_uses_schema_and_saves_the_resolved_assessment(self):
        model = Mock()
        model.create_chat_completion.return_value = {'choices': [{'message': {'content': json.dumps(self.selected_review())}}]}
        audit = {}
        composer.review_and_revise(model, self.draft, self.packet, audit)
        self.assertIn('schema', model.create_chat_completion.call_args.kwargs['response_format'])
        self.assertTrue(audit['editorial_reviews'][0]['resolved_review']['source_checks'][0]['quote'])


if __name__ == '__main__':
    unittest.main()
