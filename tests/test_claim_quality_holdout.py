"""Offline integrity checks for the separately source-reviewed holdout."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import comprehensive_readings as reading
import evaluate_claim_quality as evaluation


class ClaimQualityHoldoutTests(unittest.TestCase):
    def test_holdout_is_separate_and_keeps_deterministic_gates(self):
        fixtures = json.loads((ROOT / 'tests/fixtures/claim_quality_holdout.json').read_text())
        development = json.loads((ROOT / 'tests/fixtures/claim_quality_sources.json').read_text())
        counts = evaluation.validate_fixtures(fixtures)
        self.assertEqual(counts, {'sources': 2, 'cases': 10,
                                  'expected_supported': 4, 'expected_unsupported': 6})
        self.assertFalse({s['doi'] for s in fixtures['sources']} &
                         {s['doi'] for s in development['sources']})
        for source in fixtures['sources']:
            self.assertLessEqual(len(source['text'].split()), 150)
            for case in source['cases']:
                with self.subTest(case=case['id']):
                    reading.validate_claim({key: case[key] for key in ('field', 'text', 'quote')},
                                           {'id': 'C0001', 'text': source['text']}, 'scholarly')


if __name__ == '__main__':
    unittest.main()
