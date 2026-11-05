"""Failure-isolation, privacy and resumability checks for bibliography retrieval."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from full_document_access import Document
import retrieve_articles as runner

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


class AcquisitionTests(unittest.TestCase):
    def records(self):
        return runner.input_records([{"doi": "10.1234/test", "title": "An explicit test article title", "project": "education"}])

    def document(self):
        return Document([{"location": "page:1", "text": "PRIVATE SOURCE PASSAGE"}],
                        "https://arxiv.org/pdf/1234.56789", "submittedVersion",
                        {"evidence_status": "full_document_retrieved", "pages_total": 1})

    def test_two_projects_share_one_retrieval(self):
        base = self.records()[0]
        items = runner.input_records([base, {**base, "projects": ["observatory"]}])
        calls = []
        def fetch(row, **kwargs):
            calls.append(row["doi"])
            return self.document(), []
        report = runner.process(items, retriever=fetch, now=NOW)
        self.assertEqual(calls, ["10.1234/test"])
        self.assertEqual(report["records"][0]["projects"], ["education", "observatory"])

    def test_completed_record_is_not_redownloaded_but_new_candidate_reopens(self):
        items = self.records()
        first = runner.process(items, retriever=lambda r, **kw: (self.document(), []), now=NOW)
        def forbidden(*args, **kwargs):
            self.fail("completed unchanged record was fetched again")
        second = runner.process(items, first, retriever=forbidden, now=NOW)
        self.assertEqual(second["summary"]["attempted_this_run"], 0)
        items[0]["fulltext_candidates"] = [{"url": "https://arxiv.org/pdf/1234.56789v2"}]
        self.assertTrue(runner.due(items[0], first["records"][0], NOW))

    def test_one_failure_does_not_discard_other_results_or_log_secrets(self):
        items = runner.input_records(self.records() + [{"doi": "10.1234/other", "title": "Another explicit article title"}])
        def fetch(row, **kwargs):
            if row["doi"].endswith("test"):
                raise ValueError("https://api.example/?api_key=private-secret")
            return self.document(), []
        report = runner.process(items, retriever=fetch, now=NOW)
        self.assertEqual([x["status"] for x in report["records"]], ["retrieval_error", "full_document_retrieved"])
        self.assertNotIn("private-secret", json.dumps(report))
        self.assertNotIn("PRIVATE SOURCE PASSAGE", json.dumps(report))

    def test_rate_limit_honors_backoff_and_is_not_missing_paper(self):
        report = runner.process(self.records(), retriever=lambda r, **kw: (
            None, [{"provider": "example", "status": "http_429", "retry_after_seconds": 172800}]), now=NOW)
        row = report["records"][0]
        self.assertEqual(row["status"], "provider_limited")
        self.assertEqual(row["next_retry_at"], "2026-11-07T00:00:00+00:00")
        self.assertFalse(runner.due(self.records()[0], row, NOW))

    def test_private_outputs_cannot_be_written_under_public_repo(self):
        with self.assertRaisesRegex(ValueError, "outside the public repository"):
            runner.private_path(runner.ROOT / "data" / "private-papers.json")

    def test_staged_pdf_never_claims_cloud_sync(self):
        doc = self.document()
        doc.source_bytes = b"%PDF-1.7\nfixture source bytes"
        with tempfile.TemporaryDirectory() as directory:
            report = runner.process(self.records(), retriever=lambda r, **kw: (doc, []),
                                    stage_directory=directory, now=NOW)
            attachment = report["records"][0]["attachment"]
            self.assertEqual(Path(attachment["staged_path"]).read_bytes(), doc.source_bytes)
            self.assertFalse(attachment["cloud_save_verified"])
            self.assertFalse(report["report_cloud_save_verified"])
            self.assertTrue(report["records"][0]["coverage"]["source_text_saved"])

    def test_conflicting_citation_identity_requires_resolution(self):
        with self.assertRaisesRegex(ValueError, "Conflicting titles"):
            runner.input_records(self.records() + [{"doi": "10.1234/test", "title": "A different title"}])


if __name__ == "__main__":
    unittest.main()
