"""Research intentions cannot become measured findings through verb matching."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import condense_readings


class ResultSelectionIntentTests(unittest.TestCase):
    def test_past_expectation_is_not_a_finding(self):
        text = ("We expected an increased ability and willingness to switch (i.e., switch readiness) "
                "in the current chunk when the previous chunk entailed a task switch rather than a repetition.")
        self.assertEqual(condense_readings.reported_result(text, maxlen=600), "")

    def test_examined_association_is_not_an_observed_association(self):
        text = ("Grounded in Cognitive Load Theory and Social Cognitive Theory, this study examines how "
                "perceived Agentic AI Capability is associated with students' extraneous cognitive load, "
                "academic self-efficacy, and overall student engagement in systems development courses.")
        self.assertEqual(condense_readings.reported_result(text, maxlen=600), "")

    def test_reported_result_survives_rejected_expectation(self):
        text = ("We expected increased task switching after using the assistant. "
                "Results showed that students reported lower effort on the second task.")
        self.assertEqual(condense_readings.reported_result(text, maxlen=600),
                         "Results showed that students reported lower effort on the second task.")

    def test_current_corpus_regressions_do_not_select_aims(self):
        rows = json.loads((ROOT / "data/library.json").read_text())
        for doi in ("10.1016/j.cognition.2026.106458", "10.3389/fpsyg.2026.1978175"):
            row = next(row for row in rows if row.get("doi") == doi)
            finding = condense_readings.reported_result_bundle(row["abstract_text"], row["title"])
            self.assertNotIn("We expected", finding)
            self.assertNotIn("this study examines", finding)


if __name__ == "__main__":
    unittest.main()
