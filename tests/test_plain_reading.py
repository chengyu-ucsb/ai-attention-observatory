import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from article_art import canonical_identity
from plain_reading import basis_fingerprint, prepare_plain_reading


def source(**attrs):
    return {
        "doi": "10.1234/TEST", "kind": "scholarly", "reader_genre": "research",
        "title": "Ratings and performance in assisted work",
        "reading": {"level": "full_text", "digest": {
            "status": "editorially_written_from_indexed_sections",
            "idea": "Students said the assisted task felt easier. Their test scores were similar.",
        }}, **attrs,
    }


class TestPlainReading(unittest.TestCase):

    def test_prefers_whole_edited_field(self):
        paper = source()
        result = prepare_plain_reading(paper)
        self.assertEqual(result["lead"], paper["reading"]["digest"]["idea"])
        self.assertEqual(result["status"], "prepared")

    def test_prepared_context_preserves_complete_measure_and_boundary(self):
        paper = source()
        digest = paper["reading"]["digest"]
        digest.update(approach="Students rated the difficulty of each practice set.",
                      limitation="Researchers counted attempts during a single class session.")
        prepared = prepare_plain_reading(paper)
        self.assertEqual(prepared["detail"], digest["approach"])
        self.assertEqual(prepared["limit"], digest["limitation"])
        digest["approach"] = digest["idea"]
        self.assertNotIn("detail", prepare_plain_reading(paper))

    def test_revision_holds_previous_lead_and_context(self):
        paper = source()
        override = {canonical_identity(paper): {
            "basis_sha256": basis_fingerprint(paper),
            "lead": "Students rated the assisted task as easier.",
            "detail": "Students rated how much work it took to finish.",
            "limit": "The test scores were similar.",
        }}
        copy_with_art = {**paper, "first_seen": "2030-01-01", "editorial_art": {"status": "ready"}}
        result = prepare_plain_reading(copy_with_art, override)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["limit"], override["doi:10.1234/test"]["limit"])
        updated = copy.deepcopy(paper)
        updated["reading"]["digest"]["idea"] = "Students rated the two tasks differently."
        stale = prepare_plain_reading(updated, override)
        self.assertEqual(stale["reason"], "source_changed")
        self.assertEqual(stale["lead"], "")
        self.assertNotIn("detail", stale)
        self.assertNotIn("limit", stale)

    def test_no_promotion_of_titles_or_excerpts(self):
        paper = source()
        paper["reading"]["digest"] = {"status": "automatically_condensed_source_text",
            "explain_source": "abstract_excerpt",
            "explain": "Students showed clear improvement in the latest round of testing."}
        self.assertEqual(prepare_plain_reading(paper)["status"], "needs_review")
        paper["reading"]["digest"]["explain_source"] = "abstract_paraphrase"
        self.assertEqual(prepare_plain_reading(paper)["basis"], "Abstract")
        paper["display_headline"] = paper["reading"]["digest"]["explain"]
        self.assertFalse(prepare_plain_reading(paper)["lead"])

    def test_no_statistical_fragment_as_lead(self):
        paper = source()
        paper["reading"]["digest"]["idea"] = "These results show that a LASSO coefficient was lower."
        self.assertFalse(prepare_plain_reading(paper)["lead"])

    def test_argument_retains_attribution(self):
        paper = source(kind="nonacademic", reader_genre="opinion")
        paper["reading"]["digest"] = {"status": "edited_perspective",
            "idea": "An app feature would help students finish their work.",
            "explain": "The author argues that students should decide which apps can send alerts."}
        result = prepare_plain_reading(paper)
        self.assertEqual(result["lead"], paper["reading"]["digest"]["explain"])
        self.assertEqual(result["basis"], "Attributed source account")

    def test_unsupported_source_and_unchecked_raw_account(self):
        paper = source(reading={"level": "citation_only"}, deep_analysis={
            "research_question": "An unsupported article account that should stay private."})
        self.assertEqual(prepare_plain_reading(paper)["reason"], "insufficient_reading")
        paper["reading"]["level"] = "full_text"
        self.assertFalse(prepare_plain_reading(paper)["lead"])


if __name__ == "__main__":
    unittest.main()
