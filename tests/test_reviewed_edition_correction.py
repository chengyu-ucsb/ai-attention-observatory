"""A checked supplement can revise its own Monday issue after the rolling queue changes."""
import copy
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import build_issue as issues
from collection_window import window_metadata


class ReviewedCorrectionTests(unittest.TestCase):
    date = "2026-11-02"

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data = pathlib.Path(tmp.name)
        mapping = patch.object(issues, "DATA", self.data)
        mapping.start()
        self.addCleanup(mapping.stop)
        for folder in ("approved-issues", "edition-corrections"):
            (self.data / folder).mkdir()
        self.write("public-weekly.json", {"run": {"date": "2026-11-09"}, "items": []})
        day = "2026-10-29"
        self.source = {
            "doi": "10.9999/addition", "kind": "scholarly", "title": "Attention in the classroom",
            "url": "https://example.org/addition", "venue": "Example Journal", "published": day,
            "publication_date_provenance": {"basis": "editor_verified_original_publication_date", "value": day},
            "abstract_text": "The study compared reported focus across classroom activities. Its immediate questionnaire does not establish lasting learning.",
            "reading": {"level": "abstract", "overview": "Students reported different experiences."},
        }
        original = {**self.source, "id": "10.9999/first", "url": "https://example.org/first",
                    "title": "First paper", "reading_level": "abstract", "editorial_role": "publication_week"}
        self.archive = {
            "edition_date": self.date, "number": "03", "status": "published",
            "publication_window": window_metadata(self.date), "sources": [original],
            "feed_id": "https://example.org/first-issue", "published_at": "2026-11-02T17:00:00+00:00",
        }
        section = {"title": "The comparison", "text": "The classroom questionnaire was immediate.",
                   "sources": [self.source["title"]], "citations": [{"text": "classroom questionnaire",
                   "source": self.source["title"], "locator": "Abstract"}]}
        self.draft = {"number": "03", "edition_format": "compact", "citation_schema_version": 1,
                      "headline": "A classroom comparison", "subject": "Weekly issue", "deck": "Classroom attention",
                      "letter": "What can a classroom study tell us?", "signals": [section], "tension": section,
                      "experiment": {"title": "Try it", "text": "Compare the evidence."},
                      "closer": "Read the original.", "editorial_note": "The new reading covers the abstract."}
        self.packet = {
            "edition_date": self.date, "baseline_source_ids": [original["id"]],
            "editorial_sha256": issues.correction_digest(self.draft),
            "reviewed_additions": [{
                "source": {**self.source, "id": self.source["doi"]},
                "checks": ["Verified that the outcome was immediate and self-reported."],
                "source_locator": "Abstract, final two sentences",
                "reading_sha256": issues.correction_reading_digest(self.source),
            }],
        }
        self.save_inputs()

    def write(self, name, value):
        (self.data / name).write_text(json.dumps(value), encoding="utf-8")

    def save_inputs(self):
        self.write("approved-issues/" + self.date + ".json", self.archive)
        self.write("edition-corrections/" + self.date + ".json", self.packet)
        self.write("issue-editorial.json", {self.date: self.draft})
        self.write("public-library.json", [self.source])

    def test_explicit_preview_and_repeat_keep_identity_and_timestamp(self):
        preview = issues.build(self.date, reviewed_correction=True, check_only=True)
        self.assertEqual(preview["source_count"], 2)
        self.assertFalse((self.data / "public-issue.json").exists())
        first = issues.build(self.date, reviewed_correction=True)
        self.assertEqual(first["published_at"], self.archive["published_at"])
        self.assertEqual(first["feed_id"], self.archive["feed_id"])
        self.assertEqual([r["id"] for r in first["sources"]], ["10.9999/first", self.source["doi"]])
        self.write("approved-issues/" + self.date + ".json", first)
        self.assertEqual(issues.build(self.date, reviewed_correction=True), first)

    def test_changed_copy_or_reading_requires_review_before_writing(self):
        self.draft["deck"] = "Later draft"
        self.save_inputs()
        with self.assertRaisesRegex(ValueError, "editorial review"):
            issues.build(self.date, reviewed_correction=True)
        self.packet["editorial_sha256"] = issues.correction_digest(self.draft)
        self.source["reading"]["overview"] = "A different substantive reading"
        self.save_inputs()
        with self.assertRaisesRegex(ValueError, "source review"):
            issues.build(self.date, reviewed_correction=True)
        self.assertFalse((self.data / "public-issue.json").exists())

    def test_rejects_missing_unreviewed_or_uncited_additions(self):
        clean = copy.deepcopy(self.packet)
        for field, value, reason in (("source_locator", [], "locators"), ("checks", [], "checks"),
                                     ("reading_sha256", "", "source review")):
            with self.subTest(field=field):
                self.packet = copy.deepcopy(clean)
                self.packet["reviewed_additions"][0][field] = value
                self.save_inputs()
                with self.assertRaisesRegex(ValueError, reason):
                    issues.build(self.date, reviewed_correction=True)
        self.packet = clean
        self.packet["reviewed_additions"][0]["source"]["id"] = "10.9999/unknown"
        self.save_inputs()
        with self.assertRaisesRegex(ValueError, "unavailable"):
            issues.build(self.date, reviewed_correction=True)
        self.packet["reviewed_additions"][0]["source"]["id"] = self.source["doi"]
        for section in self.draft["signals"] + [self.draft["tension"]]:
            section["sources"] = ["First paper"]
            section["citations"][0]["source"] = "First paper"
        self.packet["editorial_sha256"] = issues.correction_digest(self.draft)
        self.save_inputs()
        with self.assertRaisesRegex(ValueError, "must be cited"):
            issues.build(self.date, reviewed_correction=True)
        self.assertFalse((self.data / "public-issue.json").exists())

    def test_existing_archive_sources_cannot_be_dropped(self):
        self.archive["sources"].append({"id": "10.9999/other", "reading_level": "abstract"})
        self.save_inputs()
        with self.assertRaisesRegex(ValueError, "remove an existing"):
            issues.build(self.date, reviewed_correction=True)

if __name__ == "__main__":
    unittest.main()
