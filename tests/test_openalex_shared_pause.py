"""Offline XML/PDF provider-budget integration and request-accounting checks."""
import contextlib
import datetime as dt
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import enrich_openalex_fulltext as xml
import enrich_pdf_fulltext as pdf


class OpenAlexSharedPauseTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.library = self.root / "library.json"
        self.status = self.root / "fulltext-backfill-state.json"
        self.time = dt.datetime(2026, 11, 8, 10, tzinfo=dt.timezone.utc)
        self.rows = [
            {"kind": "scholarly", "doi": f"10.1000/{n}", "title": f"AI attention study {n}"}
            for n in range(3)
        ]
        self.library.write_text(json.dumps(self.rows))
        self.stack.enter_context(patch.object(xml, "now", side_effect=lambda: self.time))
        self.stack.enter_context(patch.object(xml, "LIB", self.library))
        self.stack.enter_context(patch.object(xml, "STATE", self.status))
        self.stack.enter_context(patch.object(pdf, "LIB", self.library))
        self.stack.enter_context(patch.object(pdf.time, "sleep"))
        self.stack.enter_context(patch.dict(os.environ, {
            "OPENALEX_API_KEY": "test-placeholder", "OPENALEX_FULLTEXT_LIMIT": "3",
            "PDF_FULLTEXT_LOOKUPS": "3", "PDF_FULLTEXT_DOWNLOADS": "3",
        }))
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.fetch = self.stack.enter_context(patch.object(pdf, "fetch"))

    def limited(self, headers=None):
        return urllib.error.HTTPError(
            "https://api.openalex.org/works/example", 429, "Too Many Requests",
            {"Retry-After": "60"} if headers is None else headers, None,
        )

    def saved_rows(self):
        return json.loads(self.library.read_text())

    def saved_state(self):
        return json.loads(self.status.read_text())

    def licensed_work(self):
        return json.dumps({
            "id": "https://openalex.org/W123",
            "best_oa_location": {"license": "cc-by", "landing_page_url": "https://example.org/article"},
            "content_urls": {"pdf": "https://content.openalex.org/works/W123.pdf"},
        }).encode()

    def assert_requests(self, stats, lookups, downloads):
        self.assertEqual(stats["lookup_attempts"], lookups)
        # Retained legacy name: pdf_downloads counts attempted content requests.
        self.assertEqual(stats["pdf_downloads"], downloads)
        self.assertEqual(stats["request_attempts"], lookups + downloads)
        self.assertEqual(self.fetch.call_count, lookups + downloads)

    def test_xml_429_pauses_immediately_following_pdf_stage(self):
        with patch.object(xml, "get", side_effect=self.limited()) as get:
            first = xml.run()
        self.assertEqual(first["status"], "waiting_for_budget")
        self.assertEqual(get.call_count, 1)
        library_bytes, state_bytes = self.library.read_bytes(), self.status.read_bytes()
        second = pdf.run()
        self.assert_requests(second, 0, 0)
        self.assertEqual(second["status"], "waiting_for_budget")
        self.assertEqual(second["quota_pause_until"], first["quota_pause_until"])
        self.assertEqual(self.library.read_bytes(), library_bytes)
        self.assertEqual(self.status.read_bytes(), state_bytes)
        self.assertTrue(all("pdf_fulltext_attempt" not in row for row in self.saved_rows()))

    def test_active_pause_preserves_existing_attempts_and_unattempted_rows(self):
        self.rows[0]["pdf_fulltext_attempt"] = {
            "version": 1, "status": "pdf_temporary_error", "next_at": "2026-11-01", "attempts": 4,
        }
        self.library.write_text(json.dumps(self.rows))
        self.status.write_text(json.dumps({
            "quota_pause_until": "2026-11-08T11:00:00Z", "status": "waiting_for_budget", "attempted": 7,
        }))
        before = self.library.read_bytes(), self.status.read_bytes()
        stats = pdf.run()
        self.assert_requests(stats, 0, 0)
        self.assertEqual((self.library.read_bytes(), self.status.read_bytes()), before)
        self.assertEqual(stats["remaining_scholarly"], 3)

    def test_first_metadata_429_stops_at_one_request_and_defers_only_that_row(self):
        self.status.write_text(json.dumps({"attempted": 7, "deferred_by_reason": {"waiting_for_license": 2}}))
        self.fetch.side_effect = self.limited({"X-RateLimit-Reset": "7200"})
        stats = pdf.run()
        self.assert_requests(stats, 1, 0)
        self.assertEqual(stats["errors"], 0)
        self.assertEqual(stats["rate_limited"], 1)
        self.assertEqual(stats["fulltexts_recovered"], 0)
        self.assertEqual(stats["status"], "waiting_for_budget")
        self.assertEqual(stats["quota_pause_until"], "2026-11-08T12:02:00+00:00")
        rows = self.saved_rows()
        self.assertEqual(rows[1:], self.rows[1:])
        self.assertEqual(rows[0]["pdf_fulltext_attempt"], {
            "version": 1, "status": "budget_retry", "last_at": "2026-11-08T10:00:00+00:00",
            "next_at": stats["quota_pause_until"], "attempts": 1,
        })
        self.assertEqual(self.saved_state()["attempted"], 7)
        self.assertEqual(self.saved_state()["deferred_by_reason"], {"waiting_for_license": 2})
        self.assertEqual(self.saved_state()["quota_pause_until"], stats["quota_pause_until"])

    def test_midbatch_429_keeps_completed_outcome_and_leaves_tail_untouched(self):
        self.fetch.side_effect = [b"{}", self.limited(), AssertionError("must not fetch tail")]
        stats = pdf.run()
        self.assert_requests(stats, 2, 0)
        self.assertEqual(stats["no_licensed_pdf"], 1)
        self.assertEqual(stats["errors"], 0)
        rows = self.saved_rows()
        self.assertEqual(rows[0]["pdf_fulltext_attempt"]["status"], "no_licensed_machine_pdf")
        self.assertEqual(rows[1]["pdf_fulltext_attempt"]["status"], "budget_retry")
        self.assertEqual(rows[2], self.rows[2])

    def test_pdf_content_429_also_pauses_next_xml_run(self):
        self.fetch.side_effect = [self.licensed_work(), self.limited()]
        stats = pdf.run()
        self.assert_requests(stats, 1, 1)
        self.assertEqual(stats["rate_limited"], 1)
        self.assertEqual(stats["errors"], 0)
        self.assertNotIn("analysis", self.saved_rows()[0])
        self.assertEqual(self.saved_rows()[1:], self.rows[1:])
        with patch.object(xml, "get") as get:
            later = xml.run()
        get.assert_not_called()
        self.assertEqual(later["attempted"], 0)
        self.assertEqual(later["status"], "waiting_for_budget")
        self.assertEqual(later["quota_pause_until"], stats["quota_pause_until"])

    def test_pause_expiry_resumes_at_exact_timestamp_and_clears_global_pause(self):
        self.library.write_text(json.dumps(self.rows[:1]))
        self.fetch.side_effect = self.limited()
        first = pdf.run()
        until = xml.parse(first["quota_pause_until"])
        self.fetch.reset_mock()
        self.fetch.side_effect = None
        self.fetch.return_value = b"{}"
        self.time = until - dt.timedelta(seconds=1)
        paused = pdf.run()
        self.assert_requests(paused, 0, 0)
        self.assertEqual(self.saved_rows()[0]["pdf_fulltext_attempt"]["attempts"], 1)
        self.time = until
        resumed = pdf.run()
        self.assert_requests(resumed, 1, 0)
        self.assertEqual(resumed["status"], "batch_processed")
        self.assertIsNone(resumed["quota_pause_until"])
        self.assertIsNone(self.saved_state()["quota_pause_until"])
        self.assertEqual(self.saved_state()["status"], "batch_processed")
        self.assertEqual(self.saved_rows()[0]["pdf_fulltext_attempt"]["attempts"], 2)

    def test_per_paper_budget_retry_does_not_round_down_to_midnight(self):
        self.rows[0]["pdf_fulltext_attempt"] = {
            "version": 1, "status": "budget_retry", "next_at": "2026-11-08T10:30:00+00:00", "attempts": 1,
        }
        self.library.write_text(json.dumps(self.rows[:1]))
        before = self.saved_rows()
        stats = pdf.run()
        self.assert_requests(stats, 0, 0)
        self.assertEqual(stats["status"], "no_ready_sources")
        self.assertEqual(self.saved_rows(), before)

    def test_no_header_429_reuses_xml_next_day_reset_policy(self):
        self.fetch.side_effect = self.limited({})
        stats = pdf.run()
        self.assertEqual(stats["quota_pause_until"], "2026-11-09T01:00:00+00:00")
        self.assert_requests(stats, 1, 0)

    def test_non_quota_errors_are_counted_and_do_not_pause_other_papers(self):
        for error in [
            urllib.error.HTTPError("https://api.openalex.org", 503, "Unavailable", {}, None),
            urllib.error.URLError("temporary network failure"), TimeoutError("timed out"),
        ]:
            with self.subTest(error=error):
                self.library.write_text(json.dumps(self.rows))
                self.fetch.reset_mock()
                self.fetch.side_effect = [error, b"{}", b"{}"]
                stats = pdf.run()
                self.assert_requests(stats, 3, 0)
                self.assertEqual(stats["errors"], 1)
                self.assertEqual(stats["rate_limited"], 0)
                self.assertEqual(stats["no_licensed_pdf"], 2)
                self.assertEqual(self.saved_rows()[0]["pdf_fulltext_attempt"]["status"], "pdf_temporary_error")
                self.assertFalse(self.status.exists())

    def test_no_argument_run_retains_limits_and_unauthenticated_lookup_behavior(self):
        with patch.dict(os.environ, {"PDF_FULLTEXT_LOOKUPS": "1", "OPENALEX_API_KEY": ""}):
            self.fetch.return_value = b"{}"
            stats = pdf.run()
        self.assert_requests(stats, 1, 0)
        self.assertEqual(self.fetch.call_args.args[1], "")
        self.assertEqual(self.saved_rows()[1:], self.rows[1:])
        self.assertFalse(self.status.exists())

    def test_no_argument_run_retains_pdf_download_budget(self):
        with patch.dict(os.environ, {"PDF_FULLTEXT_DOWNLOADS": "1"}), patch.object(pdf, "extract_pdf", return_value={"results": "Source-backed results."}):
            self.fetch.side_effect = [self.licensed_work(), b"%PDF-example"]
            stats = pdf.run()
        self.assert_requests(stats, 1, 1)
        self.assertEqual(stats["fulltexts_recovered"], 1)
        self.assertEqual(self.saved_rows()[1:], self.rows[1:])

    def test_explicit_paths_and_missing_state_are_compatible(self):
        other_library = self.root / "other-library.json"
        other_status = self.root / "other-state.json"
        other_library.write_text(json.dumps(self.rows[:1]))
        self.fetch.side_effect = self.limited()
        stats = pdf.run(str(other_library), str(other_status))
        self.assert_requests(stats, 1, 0)
        self.assertEqual(json.loads(other_status.read_text())["quota_pause_until"], stats["quota_pause_until"])
        self.assertEqual(self.saved_rows(), self.rows)
        self.assertFalse(self.status.exists())


if __name__ == "__main__":
    unittest.main()
