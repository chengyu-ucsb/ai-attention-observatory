"""Keep scheduled reading updates separate from offline code checks."""
from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/deepen-readings.yml'


class ReadingWorkflowTests(unittest.TestCase):
    def test_scheduled_and_manual_production_remain_available(self):
        text = WORKFLOW.read_text()
        events = text.split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertEqual(re.findall(r'^  ([a-z_]+):', events, re.MULTILINE),
                         ['pull_request', 'schedule', 'workflow_dispatch'])
        self.assertIn("    - cron: '35 13 * * 2,5'", events)
        self.assertIn("run: python scripts/comprehensive_readings.py", text)

    def test_pull_requests_still_check_code_without_running_production(self):
        text = WORKFLOW.read_text()
        self.assertIn('python -m unittest discover -s tests -v', text)
        self.assertIn('node tests/validate_article_ui.cjs', text)
        production_steps = (
            'Install PDF extraction and local CPU inference',
            'Download open model weights without hosted inference',
            'Read complete retrieved text and check each claim',
            'Validate completed notes before saving',
            'Save original notes and coverage only',
        )
        for name in production_steps:
            with self.subTest(step=name):
                self.assertIn('- name: ' + name +
                              "\n        if: github.event_name != 'pull_request'", text)


if __name__ == '__main__':
    unittest.main()
