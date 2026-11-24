"""Exercise new, revised and removed readings through the actual publication path."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_weekly_publication_boundary import paper
import build_public
import build_reader
from article_art import canonical_identity
from publication_fixtures import article_covers_ready


class ReadingReviewPipelineTests(unittest.TestCase):
    def test_review_rebuild_and_reader_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            new = paper()
            key = canonical_identity(new)
            library = data / "library.json"
            register = data / "reading-review.json"
            library.write_text(json.dumps([new]))
            (data / "weekly.json").write_text(json.dumps({"run": {}, "items": []}))
            with patch.object(build_public, "DATA", data), article_covers_ready():
                build_public.build()
                summary = json.loads(register.read_text())["articles"][key]["summary"]
                lead = "Students described how well they could focus while learning with AI."
                (data / "plain-reading-leads.json").write_text(json.dumps({
                    key: {"basis_sha256": summary["basis_sha256"], "lead": lead,
                          "limit": "Students reported their own ability to concentrate."}}))
                selected, _ = build_public.build()
                page = build_reader.article(selected[0])
                card = build_reader.card(page, "data/reader/articles/example.json")
                self.assertEqual(card["plain_reading"]["lead"], lead)
                self.assertIn("limit", page["plain_reading"])
                self.assertNotIn("limit", card["plain_reading"])
                self.assertNotIn("basis_sha256", page["plain_reading"])
                before = register.read_bytes()
                build_public.build()
                self.assertEqual(before, register.read_bytes())
                new["abstract_text"] += " The authors corrected their original measurement description."
                library.write_text(json.dumps([new]))
                revised, _ = build_public.build()
                self.assertEqual(revised[0]["plain_reading"]["reason"], "source_changed")
                self.assertFalse(revised[0]["plain_reading"]["lead"])
                library.write_text("[]")
                build_public.build()
                self.assertNotIn(key, json.loads(register.read_text())["articles"])
