"""The Observatory must distinguish a successful build from current publication."""
import sys
from datetime import date
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from pipeline_status import weekly_freshness


class FreshnessTests(unittest.TestCase):
    def test_outdated_discovery_is_explicit_even_if_an_old_issue_was_published(self):
        status = weekly_freshness('2026-10-26', '2026-10-26', today=date(2026, 11, 2))
        self.assertEqual(status['expected_collection_week'], '2026-11-02')
        self.assertEqual(status['pipeline_health'], 'stale_discovery')
        self.assertFalse(status['discovery_current'])
        self.assertFalse(status['publication_current'])

    def test_fresh_discovery_waiting_for_edition_is_not_reported_as_current(self):
        status = weekly_freshness('2026-11-02', '2026-10-26', today=date(2026, 11, 2))
        self.assertEqual(status['pipeline_health'], 'awaiting_publication')
        self.assertTrue(status['discovery_current'])
        self.assertFalse(status['publication_current'])

    def test_published_edition_this_week_is_current_and_tuesday_keeps_monday(self):
        status = weekly_freshness('2026-11-02', '2026-11-02', today=date(2026, 11, 3))
        self.assertEqual(status['expected_collection_week'], '2026-11-02')
        self.assertEqual(status['pipeline_health'], 'current')


if __name__ == '__main__':
    unittest.main()
