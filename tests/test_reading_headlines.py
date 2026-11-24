"""Keep current and future reading headings concise without inventing claims."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from reading_headlines import (accepted_heading, genre_label, headline_decision,
                              reader_genre, reader_headline, review_item, source_id)
import original_readings
import build_public
from publication_fixtures import article_covers_ready
from test_original_readings import accepted, approve, record


class ReadingHeadlineTests(unittest.TestCase):
    def long_record(self):
        row = record()
        row["title"] = "Generative AI and students' attention during a classroom task: a detailed comparison of several forms of assistance"
        return row

    def test_checked_heading_preserves_full_bibliographic_title(self):
        row = self.long_record(); before = deepcopy(row)
        result = headline_decision(row, {source_id(row): "AI assistance and classroom attention"})
        self.assertEqual(result["headline"], "AI assistance and classroom attention")
        self.assertEqual(result["basis"], "editorial_register")
        self.assertEqual(row, before)

    def test_short_original_title_is_attributable_without_an_extra_heading(self):
        row = record()
        self.assertEqual(headline_decision(row, {})["headline"], row["title"])

    def test_long_title_is_held_despite_cached_heading_or_automatic_findings(self):
        row = self.long_record()
        row.update(display_headline="Stale unchecked cached title", reading={
            "original_summary": True,
            "digest": {"idea": "An unchecked automatic claim", "finding": "A short raw result."}})
        result = headline_decision(row, {})
        self.assertEqual(result["status"], "review_needed")
        self.assertEqual(result["headline"], "")
        item = review_item(row, result)
        self.assertEqual(item["title"], row["title"])
        self.assertEqual(set(item), {"id", "title", "url", "kind", "reason"})

    def test_an_accepted_summary_idea_can_supply_a_heading_but_revocation_cannot(self):
        row = self.long_record(); note = accepted()
        note["title"] = row["title"]; approve(note)
        original_readings.apply([row], {"articles": [note]})
        result = headline_decision(row, {})
        self.assertEqual(result["headline"], note["summary"]["idea"])
        self.assertEqual(result["basis"], "accepted_original_summary")
        row["original_reading"]["publication"]["decision"] = "pending"
        self.assertEqual(headline_decision(row, {})["status"], "review_needed")

    def test_invalid_register_values_cannot_reenter_as_long_or_clipped_headlines(self):
        row = self.long_record()
        for value in ("x" * 89, "A partial conclusion…", "Results: a difference emerged",
                      "The association was r = .55", "See Figure 2", "", None, {"idea": "Wrong shape"}):
            with self.subTest(value=value):
                self.assertEqual(headline_decision(row, {source_id(row): value})["status"], "review_needed")
        self.assertEqual(accepted_heading("A title\nwith ordinary spacing"), "A title with ordinary spacing")

    def test_only_the_problem_record_is_held(self):
        rows = [record(), self.long_record()]
        ready = [row for row in rows if headline_decision(row, {})["status"] == "ready"]
        self.assertEqual(ready, [rows[0]])

    def test_projection_holds_one_source_until_review_without_losing_the_index(self):
        short = record(); short["doi"] = "10.9999/short-heading"
        long = self.long_record(); long["doi"] = "10.9999/long-heading"
        rows = [short, long]
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "library.json").write_text(json.dumps(rows))
            (data / "weekly.json").write_text(json.dumps({"run": {}, "items": rows}))
            with patch.object(build_public, "DATA", data), article_covers_ready():
                public, weekly = build_public.build()
                self.assertEqual([source_id(row) for row in public], [short["doi"]])
                self.assertEqual([source_id(row) for row in weekly["items"]], [short["doi"]])
                queue = json.loads((data / "headline-review-queue.json").read_text())
                self.assertEqual([item["id"] for item in queue["items"]], [long["doi"]])
                self.assertEqual(json.loads((data / "library.json").read_text()), rows)
                (data / "reading-headlines.json").write_text(json.dumps({
                    long["doi"]: "AI assistance and students’ classroom attention"}))
                public, weekly = build_public.build()
                self.assertEqual(len(public), 2)
                self.assertEqual(len(weekly["items"]), 2)
                self.assertEqual(json.loads((data / "headline-review-queue.json").read_text())["items"], [])
                restored = next(row for row in public if row["doi"] == long["doi"])
                self.assertEqual(restored["title"], long["title"])
                self.assertEqual(restored["display_headline"], "AI assistance and students’ classroom attention")

    def test_short_titles_across_current_and_frozen_source_shelves(self):
        register = json.loads((ROOT / "data/reading-headlines.json").read_text())
        editions = (list((ROOT / "data/approved-issues").glob("*.json")) +
                    list((ROOT / "data/edition-revisions").glob("*.json")))
        for path in editions:
            for row in json.loads(path.read_text()).get("sources", []):
                with self.subTest(edition=path.name, source=source_id(row)):
                    heading = reader_headline(row)
                    self.assertEqual(heading, register[source_id(row)])
                    self.assertLessEqual(len(heading), 55)
                    self.assertLessEqual(len(heading.split()), 10)

    def test_long_titles_cannot_return_through_a_snapshot_or_checkless_excerpt(self):
        title = "How the tasks students try to perform change when a teacher allows them to use an AI tutor"
        source = {"kind": "nonacademic", "title": title, "display_headline": title}
        self.assertFalse(accepted_heading("A B C D E F G H I J K"))
        self.assertNotEqual(reader_headline(source, {}), title)
        self.assertEqual(source["title"], title)
        self.assertEqual(headline_decision(source, {})["status"], "review_needed")

    def test_genre_describes_the_publication_before_its_subject(self):
        media = {"kind": "nonacademic", "title": "A systematic review of AI at school",
                 "companion_to": "10.12345/original", "genre": "reported_analysis"}
        self.assertEqual(reader_genre(media), "reporting")
        self.assertEqual(genre_label(dict(media, reader_genre="research")), "News report")
        self.assertEqual(reader_genre({"kind": "nonacademic", "format": "Product & design"}), "commentary")
        self.assertEqual(reader_genre({"kind": "nonacademic", "source": "Official product documentation"}), "guide")
        self.assertEqual(reader_genre({"kind": "scholarly", "article_type": "Opinion", "research_type": "unclassified"}), "opinion")
        self.assertEqual(reader_genre({"kind": "scholarly", "title": "Editorial: A review of AI"}), "editorial")
        self.assertEqual(reader_genre({"kind": "scholarly", "article_type": "news", "title": "Researchers report a breakthrough"}), "reporting")
        self.assertEqual(reader_genre({"kind": "scholarly", "article_type": "study-protocol", "title": "A systematic review protocol"}), "proposal")
        self.assertEqual(reader_genre({"kind": "scholarly", "title": "AI and learning: a systematic review"}), "review")
        self.assertEqual(reader_genre({"kind": "scholarly", "research_type": "conceptual_framework"}), "conceptual")
        self.assertEqual(reader_genre({"kind": "scholarly", "research_type": "research_proposal"}), "proposal")
        self.assertEqual(reader_genre({"kind": "scholarly", "research_type": "observational"}), "research")

    def test_current_public_corpus_has_complete_concise_headings(self):
        rows = json.loads((ROOT / "data/public-library.json").read_text())
        register = json.loads((ROOT / "data/reading-headlines.json").read_text())
        self.assertTrue(rows)
        held = [source_id(row) for row in rows if headline_decision(row, register)["status"] != "ready"]
        self.assertEqual(held, [])
        for key, heading in register.items():
            with self.subTest(source=key):
                self.assertEqual(accepted_heading(heading), heading)


if __name__ == "__main__":
    unittest.main()
