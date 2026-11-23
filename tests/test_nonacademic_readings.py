"""Protect source-specific prose on the public nonacademic reading path."""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from condense_readings import annotate
from enrich_deep_readings import model_json
from news_quality import commentary_reading_depth
from nonacademic_reading_voice import verification_guidance, writing_guidance
from seed_products import PRODUCTS


class Model:
    def create_chat_completion(self, *, messages, **options):
        self.prompt = messages[-1]['content']
        return {'choices': [{'message': {'content': json.dumps({})}}]}


class NonacademicReadingTests(unittest.TestCase):
    def test_editorial_generation_adapts_to_the_source_type(self):
        for source_type, genre, detail in (
                ('news', 'reporting', 'who did what'),
                ('opinion', 'opinion', 'position they defend'),
                ('policy', 'analysis', 'who controls it'),
                ('product_documentation', 'guide', 'user action')):
            with self.subTest(genre=genre):
                record = {'kind': 'nonacademic', 'title': 'An unfamiliar source',
                          'source_type': source_type, 'url': 'https://example.org/story'}
                model = Model()
                model_json('A complete source paragraph.', record, 'nonacademic', model)
                self.assertIn(writing_guidance(genre), model.prompt)
                self.assertIn(detail, model.prompt)
                self.assertIn('A complete source paragraph.', model.prompt)
        self.assertIn('proposed or already in force', verification_guidance('analysis'))
        self.assertIn('effectiveness claim', verification_guidance('guide'))
        self.assertIn('actual speakers', verification_guidance('opinion'))
        self.assertIn('at the time of reporting', verification_guidance('reporting'))
        self.assertIn('For reporting', writing_guidance('commentary'))

    def test_machine_depth_requires_an_example_distinct_from_the_thesis_and_reasoning(self):
        claim = ('A reporter describes students taking a break between homework tasks and '
                 'asking a teacher before opening their chat app again. ')
        evidence = {'thesis': claim, 'reasoning': claim * 2, 'examples': claim.upper(),
                    'tension': 'A nearby school tried a different arrangement. ' * 3,
                    'qualification': 'The reporter interviewed pupils at one school and did not track them afterward.',
                    'source_depth': 'machine_read_full_article'}
        row = {'url': 'https://example.org/report', 'reading': {'digest': {'longform': evidence}}}
        self.assertFalse(commentary_reading_depth(row))
        evidence['examples'] = ('One student tells the reporter about shutting the app during homework. '
                                'Her teacher kept the first draft so the student could return to it.')
        self.assertTrue(commentary_reading_depth(row))

    def test_focus_guides_explain_an_action_and_what_people_see(self):
        expected = {'Apple Developer': ('personal account', 'implement'),
                    'Android': ('communication apps', 'time spent')}
        for product in PRODUCTS:
            if product['venue'] not in expected:
                continue
            with self.subTest(product=product['venue']):
                record = {'kind': 'nonacademic', 'url': product['url'], 'title': product['title'],
                          'source': 'Official product documentation',
                          'reading': {'level': 'curated', 'overview': product['overview']},
                          'editorial_notes': {'argument': product['argument'],
                                              'design_relevance': product['design_relevance']}}
                digest = annotate(record)['reading']['digest']
                detail, scope = expected[product['venue']]
                longform = digest['longform']
                self.assertEqual(longform['source_depth'], 'product_documentation')
                self.assertIn(detail, longform['examples'].lower())
                self.assertIn(scope, longform['qualification'].lower())
                self.assertNotEqual(digest['explain'], longform['reasoning'])
                self.assertEqual(digest['finding'], '')


if __name__ == '__main__':
    unittest.main()
