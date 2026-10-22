"""Zenodo fallback: only exact published DOI, permissive rights and bounded PDFs."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import enrich_zenodo_fulltext as zenodo
import enrich_repository_fulltext as repository

TODAY = dt.date(2026, 10, 22)
DOI = "10.5281/zenodo.12345678"
WORK = {
    "id": "12345678",
    "doi": DOI,
    "is_published": True,
    "access": {"record": "public", "files": "public"},
    "metadata": {"rights": [{"id": "cc-by-4.0"}]},
    "files": {"enabled": True, "entries": {
        "manuscript.pdf": {"key": "manuscript.pdf", "size": 12345}
    }},
}
SECTIONS = {
    "methods": "The study collected participants' daily interruption experiences.",
    "results": "Frequent interruptions were associated with task resumption costs.",
    "discussion": "The authors discuss possible mechanisms, without establishing causality."
}


class ZenodoRecoveryTests(unittest.TestCase):
    def test_license_must_be_permissive_and_unambiguous(self):
        self.assertEqual(zenodo.license_name("cc-by-4.0"), "cc-by")
        self.assertEqual(zenodo.license_name("cc-by-sa-4.0"), "cc-by-sa")
        self.assertEqual(zenodo.license_name("cc0-1.0"), "cc0")
        self.assertEqual(zenodo.license_name("cc-by-nc-4.0"), "")
        self.assertEqual(zenodo.license_name("cc-by-nd-4.0"), "")
        self.assertEqual(zenodo.record_license(WORK), "cc-by")
        mixed = dict(WORK, metadata={"rights": [{"id": "cc-by-4.0"}, {"id": "all-rights-reserved"}]})
        self.assertEqual(zenodo.record_license(mixed), "")

    def test_doi_and_public_file_access_are_required(self):
        self.assertTrue(zenodo.verified_record(WORK, DOI))
        self.assertFalse(zenodo.verified_record(WORK, "10.5281/zenodo.99999"))
        self.assertFalse(zenodo.verified_record(dict(WORK, access={"files": "restricted"}), DOI))
        self.assertFalse(zenodo.verified_record(dict(WORK, is_published=False), DOI))

    def test_only_simple_bounded_article_pdfs_are_considered(self):
        work = dict(WORK, files=[
            {"key": "supplement.pdf", "size": 1000},
            {"key": "../secret.pdf", "size": 1000},
            {"key": "poster.pdf", "size": 1000},
            {"key": "huge.pdf", "size": 40_000_000},
            {"key": "manuscript.pdf", "size": 1048576}
        ])
        self.assertEqual(zenodo.pdf_keys(work), ["manuscript.pdf"])

    def test_no_permission_or_wrong_doi_never_downloads(self):
        for work in [dict(WORK, doi="10.5281/zenodo.87654321"),
                     dict(WORK, metadata={"rights": [{"id": "cc-by-nc-4.0"}]})]:
            row = {"kind": "scholarly", "doi": DOI}
            with patch.object(zenodo, "metadata", return_value=work), patch.object(zenodo, "download_pdf") as download:
                stats = zenodo.recover_due([row], TODAY)
                download.assert_not_called()
            self.assertEqual(stats["recovered"], 0)
            self.assertNotIn("analysis", row)

    def test_licensed_pdf_becomes_source_attributed_sections(self):
        row = {"kind": "scholarly", "doi": DOI}
        with patch.object(zenodo, "metadata", return_value=WORK), \
             patch.object(zenodo, "download_pdf", return_value=b"%PDF-1.7 test"), \
             patch.object(zenodo, "extract_pdf", return_value=SECTIONS):
            stats = zenodo.recover_due([row], TODAY)
        self.assertEqual(stats["recovered"], 1)
        self.assertEqual(row["analysis"]["license"], "cc-by")
        self.assertIn("Zenodo", row["analysis"]["provenance"])
        self.assertEqual(row["analysis"]["results"], SECTIONS["results"])
        self.assertNotIn("%PDF", str(row))
        self.assertEqual(row["zenodo_recovery"]["status"], "full_text_recovered")
        self.assertFalse(zenodo.eligible(row, TODAY))

    def test_failed_attempt_respects_backoff(self):
        row = {"kind": "scholarly", "doi": DOI}
        with patch.object(zenodo, "metadata", return_value=dict(WORK, metadata={})), \
             patch.object(zenodo, "download_pdf") as pdf:
            self.assertEqual(zenodo.recover_due([row], TODAY)["license_unverified"], 1)
            self.assertEqual(zenodo.recover_due([row], TODAY)["attempted"], 0)
            pdf.assert_not_called()
        self.assertTrue(zenodo.eligible(row, TODAY + dt.timedelta(days=30)))

    def test_parent_pipeline_saves_zenodo_when_no_other_sources_due(self):
        row = {"kind": "scholarly", "doi": DOI,
               "repository_recovery": {"version": 1, "next_at": "2099-01-01", "attempts": 1}}
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / "library.json"
            lib.write_text(json.dumps([row]))
            with patch.object(repository, "LIB", lib), \
                 patch.object(zenodo, "metadata", return_value=WORK), \
                 patch.object(zenodo, "download_pdf", return_value=b"%PDF-1.7 test"), \
                 patch.object(zenodo, "extract_pdf", return_value=SECTIONS):
                stats = repository.run()
            saved = json.loads(lib.read_text())[0]
        self.assertEqual(stats["zenodo"]["recovered"], 1)
        self.assertEqual(stats["remaining_without_sections"], 0)
        self.assertEqual(saved["analysis"]["license"], "cc-by")


if __name__ == "__main__":
    unittest.main()
