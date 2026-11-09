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
            'Preserve independently validated acquisition metadata after reading',
            'Save exact validated checkpoint without replaying source or model work',
            'Retain validated recovery metadata and permitted original notes',
        )
        for name in production_steps:
            with self.subTest(step=name):
                step = text.split('      - name: ' + name + '\n', 1)[1].split('      - name:', 1)[0]
                condition = next(line.strip() for line in step.splitlines() if line.strip().startswith('if:'))
                self.assertRegex(condition, r"^if: (?:always\(\) && )?github.event_name != 'pull_request'(?:$| && )")

    def test_claim_benchmark_models_run_only_on_explicit_manual_request(self):
        text = WORKFLOW.with_name('claim-quality-evaluation.yml').read_text()
        self.assertIn('  pull_request:', text)
        self.assertIn('  workflow_dispatch:', text)
        self.assertNotIn('  schedule:', text)
        self.assertNotIn('  push:', text)
        self.assertIn('  contents: read', text)
        self.assertIn('options: [exact_partition, focused_checks]', text)
        self.assertIn('options: [development, holdout]', text)
        for name in ('Install the observed production inference version',
                     'Download the stronger open model without hosted inference',
                     'Measure labeled-claim acceptance without publishing readings'):
            self.assertIn('- name: ' + name +
                          "\n        if: github.event_name == 'workflow_dispatch'", text)
        self.assertIn('if: always() && github.event_name == \'workflow_dispatch\'', text)
        self.assertIn('--variant "$EVALUATION_VARIANT"', text)
        self.assertIn('--fixtures "$fixtures"', text)


if __name__ == '__main__':
    unittest.main()
