"""Source-depth labels must survive stale cards, extraction and review withdrawal."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_public
import build_readings
import reading_depth
import publisher_sections
import verified_full_article_notes as checked
import original_readings


def article():
    return {"kind": "scholarly", "doi": "10.1111/test.12345", "title": "Synthetic article",
            "abstract_text": "We conducted a randomized experiment with university students. "
                             "Results showed a significant difference in observed task performance."}


def review():
    return {"doi": "10.1111/test.12345", "verified_url": "https://example.org/article",
            "verified_on": "2026-11-18", "method": "Students completed two randomly assigned tasks.",
            "results": "The observed groups differed on the second task only.",
            "discussion": "The authors discuss a possible explanation for the observed difference.",
            "limitations": "The single-session design did not measure later learning.",
            "review_scope": "Methods, results and stated limitations of the source article.",
            "digest": {"finding": "The groups differed on the second task."}}


class SourceDepthIntegrityTests(unittest.TestCase):
    def test_url_without_sections_cannot_be_a_full_text_reading(self):
        row = article()
        row["analysis"] = {"fulltext_url": "https://example.org/article", "figures": [{"url": "figure.png"}]}
        row["reading"] = {"level": "full_text", "digest": {"finding_source": "full_text"}}
        self.assertFalse(reading_depth.has_article_sections(row))
        self.assertFalse(build_public.readable(row))
        self.assertEqual(build_readings.make_note(row)["level"], "abstract")
        self.assertEqual(reading_depth.depth_audit([row])["records"][0]["reason"],
                         "full_text_label_without_article_sections")

    def test_empty_html_and_table_digits_do_not_establish_article_text(self):
        for value in ("<p> </p>", "1 22 333 4444 55555 66666", "", [], {"text": "not prose"}):
            row = article()
            row["analysis"] = {"fulltext_url": "https://example.org/article", "results": value}
            self.assertFalse(reading_depth.has_article_sections(row))

    def test_reviewed_paraphrase_cannot_fill_machine_extraction_count(self):
        row = article()
        row["analysis"] = {"fulltext_url": "https://example.org/article"}
        checked.apply([row], {"articles": [review()]})
        self.assertTrue(reading_depth.has_article_sections(row))
        self.assertFalse(reading_depth.has_machine_sections(row))
        row["analysis"]["results"] = "The original machine-extracted source prose is present here."
        self.assertTrue(reading_depth.has_machine_sections(row))
        row["analysis"]["original_paraphrases_only"] = True
        self.assertFalse(reading_depth.has_machine_sections(row))

    def test_partial_sections_do_not_create_results_or_complete_review(self):
        row = article()
        row["analysis"] = {"fulltext_url": "https://example.org/article",
                           "methods": "Participants completed two tasks in a single laboratory session."}
        note = build_readings.make_note(row)
        self.assertEqual(note["section_coverage"], ["methods"])
        self.assertEqual(note["extraction_depth"], "limited")
        self.assertFalse(note["reported_findings"])
        self.assertEqual(note["findings"], "")
        self.assertNotIn("reviewed and paraphrased", note["notice"])

    def test_accepted_original_summary_is_not_mistaken_for_machine_extract(self):
        from test_original_readings import accepted, approve, record
        row = record()
        row["original_reading"] = approve(accepted())
        row["reading"] = build_readings.make_note(row)
        self.assertTrue(row["reading"]["original_summary"])
        self.assertTrue(build_public.readable(row))
        reasons = [x["reason"] for x in reading_depth.depth_audit([row])["records"]]
        self.assertNotIn("full_text_label_without_article_sections", reasons)

    def test_tutoring_record_uses_checked_version_and_keeps_limits(self):
        rows = json.loads((ROOT / "data/library.json").read_text())
        row = next(x for x in rows if x.get("doi") == "10.1111/bjet.70100")
        original_readings.apply([row])
        note = build_readings.make_note(row)
        self.assertTrue(note["original_summary"])
        self.assertEqual(note["digest"]["finding_source"], "original_summary")
        self.assertIn("149", note["methods"])
        self.assertIn("second set", note["findings"])
        self.assertIn("did not score answer accuracy", note["limitations"])
        self.assertIn("Table 2", note["review_scope"])


class CheckedReviewLifecycleTests(unittest.TestCase):
    def test_reapply_is_idempotent_and_preserves_machine_extract(self):
        row = article()
        row["analysis"] = {"fulltext_url": "https://example.org/licensed",
                           "results": "The licensed source passage remains separate from paraphrases.",
                           "license": "cc-by"}
        before = deepcopy(row["analysis"])
        manifest = {"articles": [review()]}
        self.assertEqual(checked.apply([row], manifest), 1)
        first = deepcopy(row)
        self.assertEqual(checked.apply([row], manifest), 1)
        self.assertEqual(row, first)
        self.assertEqual(row["analysis"], before)

    def test_withdrawal_removes_paraphrases_and_stale_reading(self):
        row = article()
        row["research_type"] = "empirical_study"
        row["open_access_url"] = "https://example.org/prior"
        source = review()
        source["research_type"] = "systematic_review"
        checked.apply([row], {"articles": [source]})
        row["reading"] = build_readings.make_note(row)
        checked.apply([row], {"articles": []})
        self.assertEqual(row["research_type"], "empirical_study")
        self.assertEqual(row["open_access_url"], "https://example.org/prior")
        for key in ("analysis", "reading", "verified_article_review", "editorial_digest", "source_review_status"):
            self.assertNotIn(key, row)
        self.assertEqual(build_readings.make_note(row)["level"], "abstract")

    def test_removed_review_leaves_actual_machine_text_untouched(self):
        row = article()
        row["analysis"] = {"fulltext_url": "https://example.org/licensed",
                           "results": "The existing source excerpt remains available for a new reading."}
        analysis = deepcopy(row["analysis"])
        checked.apply([row], {"articles": [review()]})
        checked.apply([row], {"articles": []})
        self.assertEqual(row["analysis"], analysis)
        self.assertNotIn("open_access_url", row)
        self.assertEqual(build_readings.make_note(row)["findings"], analysis["results"])

    def test_duplicate_or_invalid_entries_cannot_keep_an_old_review(self):
        manifests = [{"articles": [review(), review()]}]
        for key, value in (("doi", ""), ("verified_url", "https://"), ("verified_on", "yesterday"),
                           ("method", []), ("results", ""), ("source_format", "unknown"), ("digest", [])):
            source = review()
            source[key] = value
            manifests.append({"articles": [source]})
        for manifest in manifests:
            with self.subTest(manifest=manifest):
                row = article()
                checked.apply([row], {"articles": [review()]})
                self.assertEqual(checked.apply([row], manifest), 0)
                self.assertNotIn("verified_article_review", row)
                self.assertNotIn("analysis", row)

    def test_conceptual_review_never_publishes_a_measured_result(self):
        source = review()
        source["research_type"] = "conceptual_framework"
        row = article()
        checked.apply([row], {"articles": [source]})
        note = build_readings.make_note(row)
        self.assertEqual(note["findings"], "")
        self.assertFalse(note["reported_findings"])
        self.assertEqual(note["sample"], "")

    def test_current_register_is_well_formed_and_jats_stays_jats(self):
        sources = json.loads((ROOT / "data/verified-full-article-notes.json").read_text())["articles"]
        dois = [source["doi"].lower() for source in sources]
        self.assertEqual(len(dois), len(set(dois)))
        for source in sources:
            self.assertTrue(checked.valid_source(source), source["doi"])
            if "JATS XML" in source["review_scope"]:
                row = article()
                row["doi"] = source["doi"]
                checked.apply([row], {"articles": [source]})
                self.assertEqual(row["verified_article_review"]["source_format"], "JATS")
                self.assertNotIn("publisher HTML", row["analysis"]["provenance"])


class FlattenedSectionTests(unittest.TestCase):
    def paragraph(self, marker):
        return f"<p>{marker}: This synthetic paragraph provides enough words to test source section ancestry.</p>"

    def extract(self, sections):
        return publisher_sections.xml_sections(ET.fromstring("<TEI><text><body>" + sections +
                "</body></text></TEI>"), "div", "head", 10000)

    def section(self, number, title, marker):
        return f'<div><head n="{number}">{title}</head>{self.paragraph(marker)}</div>'

    def test_numbered_siblings_inherit_only_their_real_ancestor(self):
        sections = (self.section("3", "Results", "RESULT_PARENT") +
                    self.section("3.1", "Task performance", "RESULT_CHILD") +
                    self.section("3.2", "Effort", "EFFORT_CHILD") +
                    self.section("4", "Supplementary analyses", "UNKNOWN_PEER") +
                    self.section("4.1", "Another outcome", "UNKNOWN_CHILD") +
                    self.section("5", "Discussion", "DISCUSSION_PARENT") +
                    self.section("5.1", "Results", "INTERPRETATION_CHILD"))
        result = self.extract(sections)
        self.assertIn("RESULT_CHILD", result["results"])
        self.assertIn("EFFORT_CHILD", result["results"])
        self.assertIn("INTERPRETATION_CHILD", result["discussion"])
        self.assertNotIn("UNKNOWN", str(result))
        self.assertNotIn("INTERPRETATION", result["results"])

    def test_excluded_numbered_subtrees_cannot_reenter_results(self):
        sections = (self.section("3", "Results", "ACTUAL") +
                    self.section("3.1", "Future research", "FUTURE") +
                    self.section("3.1.1", "Results", "FUTURE_NESTED") +
                    self.section("3.2", "Task effort", "ACTUAL_SIBLING") +
                    self.section("4", "References", "CITATIONS") +
                    self.section("4.1", "Results", "CITED_RESULT"))
        result = self.extract(sections)
        self.assertIn("ACTUAL_SIBLING", result["results"])
        for marker in ("FUTURE", "CITATIONS", "CITED_RESULT"):
            self.assertNotIn(marker, str(result))

    def test_unnumbered_peer_clears_flattened_ancestry(self):
        sections = (self.section("3", "Results", "ACTUAL") +
                    "<div><head>Supplement</head>" + self.paragraph("SUPPLEMENT") + "</div>" +
                    self.section("3.1", "Task effort", "AMBIGUOUS"))
        result = self.extract(sections)
        self.assertNotIn("AMBIGUOUS", str(result))
        self.assertNotIn("SUPPLEMENT", str(result))

    def test_nested_jats_keeps_paragraphs_once(self):
        xml = ET.fromstring("<article><body><sec><title>Results</title>" + self.paragraph("PARENT") +
              "<sec><title>Task effort</title>" + self.paragraph("CHILD") + "</sec></sec></body></article>")
        result = publisher_sections.xml_sections(xml, "sec", "title", 10000)
        self.assertEqual(result["results"].count("CHILD"), 1)
        self.assertEqual(result["results"].count("PARENT"), 1)

    def test_analysis_result_headings_require_unambiguous_ancestry(self):
        parser = publisher_sections.ArticleHTML()
        parser.feed("<article><h2>Study design</h2>" + self.paragraph("DESIGN") +
                    "<h3>Hypothesis testing</h3>" + self.paragraph("PLANNED_ANALYSIS") +
                    "<h2>Data analysis and results</h2><h3>Hypothesis testing</h3>" +
                    self.paragraph("OBSERVED_PATHS") +
                    "<h2>Discussion</h2><h3>Hypothesis testing</h3>" +
                    self.paragraph("INTERPRETATION") +
                    "<h2>Data analysis</h2>" + self.paragraph("AMBIGUOUS") + "</article>")
        self.assertIn("DESIGN", parser.secs["methods"])
        self.assertIn("PLANNED_ANALYSIS", parser.secs["methods"])
        self.assertIn("OBSERVED_PATHS", parser.secs["results"])
        self.assertIn("INTERPRETATION", parser.secs["discussion"])
        self.assertNotIn("PLANNED_ANALYSIS", parser.secs["results"])
        self.assertNotIn("AMBIGUOUS", str(parser.secs))


if __name__ == "__main__":
    unittest.main()
