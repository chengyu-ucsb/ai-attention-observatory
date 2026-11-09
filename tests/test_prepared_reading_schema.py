"""Offline schema regressions using actual reader output, no model/network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import comprehensive_readings as reading
from full_document_access import Document
import prepared_reading_schema as schema


def generated(kind="scholarly", complete=True, structured=False, previous=None):
    now = datetime.now(timezone.utc)
    record = deepcopy(previous) if previous else {
        "kind": kind, "title": "Attention and generative artificial intelligence",
        "doi": "10.5555/schema", "url": "https://www.econstor.eu/article.pdf"}
    coverage = {"evidence_status": "full_document_retrieved" if complete else "partial_full_text",
                "semantic_completeness": "not_verified", "layout_fidelity": "not_verified"}
    if structured:
        coverage.update(document_format="jats", structured_text_coverage="all_text_in_supplied_article_xml",
                        source_document_equivalence="not_verified", rights_basis="article_metadata_permissive_license",
                        redistribution_granted=False)
        locations = ["xml:article/body:1/sec:1/p:1", "xml:article/back:1/ref-list:1"]
    elif complete:
        coverage.update(pages_total=2, pages_processed=2, pages_with_text=2)
        locations = ["page:1", "page:2"]
    else:
        coverage.update(html_completeness="not_verified", html_extraction_version="article-body-v2",
                        html_body_selection="article:explicit_body", html_blocks_extracted=2,
                        html_list_items_found=1)
        locations = ["paragraph:1", "paragraph:2"]
    document = Document([{"location": loc, "text": ("Private transient article source passage. " * 100)}
                         for loc in locations], record["url"], "publishedVersion", coverage,
                        b"%PDF-fixture" if complete and not structured else None)
    field = "limitations" if kind == "scholarly" else "qualification"
    def chunk_notes(model, chunk, *args, **kwargs):
        return [{"field": field,
                 "text": "These observations leave longer term independent learning outcomes unresolved in this comparison.",
                 "quote": "Private transient article source passage."}]
    with patch.object(reading, "screen_source", return_value={"decision": "include"}), \
         patch.object(reading, "read_chunk", side_effect=chunk_notes), \
         patch.object(reading, "due", return_value=True):
        stats = reading.process([record], Mock(), limit=1, retriever=lambda row: (document, [
            {"stage": "article", "provider": "original_article", "status": coverage["evidence_status"],
             "url": document.url, "retryable": False, "network_attempted": True}]), run_date=now.date())
    assert stats["summaries_completed"] == 1, stats
    return record


class PreparedReadingSchemaTests(unittest.TestCase):
    def setUp(self):
        self.record = generated()
        self.now = datetime.now(timezone.utc)

    def reject(self, mutate):
        value = deepcopy(self.record)
        mutate(value)
        with self.assertRaisesRegex(ValueError, schema.ERROR):
            schema.validate_saved_record(value, now=self.now)

    def revalidation(self, record=None):
        deep = (record or self.record)["deep_analysis"]
        fingerprint = "a" * 64
        return {"basis": schema.digest({"input": fingerprint, "analysis": deep}),
                "checked_at": self.now.isoformat(), "status": "source_revalidated", "approved": False,
                "source_sha256": deep["coverage"]["source_sha256"],
                "document_version": deep["coverage"]["document_version"]}

    def test_actual_process_outputs_for_pdf_html_and_xml_are_accepted(self):
        for kind, complete, structured in (("scholarly", True, False), ("nonacademic", True, False),
                                           ("scholarly", False, False), ("nonacademic", False, False),
                                           ("scholarly", True, True)):
            with self.subTest(kind=kind, complete=complete, structured=structured):
                record = generated(kind, complete, structured)
                self.assertIs(schema.validate_saved_record(record), record)
                self.assertNotIn("Private transient article source passage", str(record))

    def test_valid_partial_candidate_and_later_failed_attempt_are_accepted(self):
        record = generated(complete=False, previous=self.record)
        self.assertIn("partial_reading_candidate", record)
        schema.validate_saved_record(record)
        with patch.object(reading, "screen_source", return_value={"decision": "include"}), \
             patch.object(reading, "due", return_value=True):
            reading.process([record], Mock(), retriever=Mock(side_effect=ValueError("prepared_source_changed")))
        schema.validate_saved_record(record)

    def test_failed_first_attempt_is_valid_without_analysis(self):
        record = {"kind": "nonacademic", "title": "A commentary"}
        reading.process([record], Mock(), retriever=Mock(side_effect=ValueError("source_unavailable")))
        schema.validate_saved_record(record)

    def test_unknown_analysis_approval_and_raw_source_keys_fail_closed(self):
        for key, value in (("approved", True), ("raw_source_text", "PRIVATE_SOURCE"),
                           ("review", {"status": "passed"}), ("publication", {"decision": "approved"})):
            with self.subTest(key=key):
                self.reject(lambda row: row["deep_analysis"].update({key: value}))

    def test_metadata_fields_cannot_hide_saved_approval_or_raw_bodies(self):
        for key in ("source_review", "original_reading", "analysis", "source_text", "approved"):
            with self.subTest(key=key):
                self.reject(lambda row: row.update({key: "not accepted"}))

    def test_text_must_equal_the_ordered_checked_claims(self):
        self.reject(lambda row: row["deep_analysis"].update(limitations="An invented claim outside the checked notes."))
        self.reject(lambda row: row["deep_analysis"].pop("reported_results"))
        self.reject(lambda row: row["deep_analysis"]["claim_evidence"][0].update(field="reported_results"))
        self.reject(lambda row: row["deep_analysis"]["claim_evidence"][0].update(quote="Unlawful raw copied source"))

    def test_version_kind_depth_status_and_labels_are_exact(self):
        for field, value in (("version", True), ("version", 2), ("version", 4), ("kind", "nonacademic"),
                              ("review_status", "approved"), ("source_depth", "read_article"),
                              ("basis", "Independently approved full source review")):
            with self.subTest(field=field, value=value):
                self.reject(lambda row: row["deep_analysis"].update({field: value}))

    def test_source_hash_and_url_must_match_coverage(self):
        self.reject(lambda row: row["deep_analysis"].update(source_hash="b"*64))
        self.reject(lambda row: row["deep_analysis"].update(source_url="https://www.econstor.eu/other.pdf"))
        self.reject(lambda row: row["deep_analysis"]["coverage"].update(source_sha256="invalid"))

    def test_coverage_is_closed_and_booleans_cannot_be_truthy_strings(self):
        for field, value in (("approved", True), ("raw_text", "PRIVATE_SOURCE"), ("all_retrieved_text_processed", "true"),
                              ("source_text_saved", 0), ("tables_figures_visually_checked", True),
                              ("semantic_completeness", "verified"), ("chunks_processed", 0),
                              ("claims_checked", 0), ("redistribution_granted", True)):
            with self.subTest(field=field):
                self.reject(lambda row: row["deep_analysis"]["coverage"].update({field: value}))

    def test_partial_html_cannot_claim_complete_evidence(self):
        row = generated(complete=False)
        row["deep_analysis"]["coverage"]["evidence_status"] = "full_document_retrieved"
        with self.assertRaises(ValueError):
            schema.validate_saved_record(row)

    def test_inconsistent_byte_page_and_chunk_counts_are_rejected(self):
        self.reject(lambda row: row["deep_analysis"]["coverage"].pop("source_bytes_sha256"))
        self.reject(lambda row: row["deep_analysis"]["coverage"].update(pages_with_text=1))
        self.reject(lambda row: row["deep_analysis"]["coverage"].update(empty_claim_chunks=["C0001"]))

    def test_handoff_provenance_requires_both_hashes_and_unreviewed_status(self):
        row = deepcopy(self.record)
        # process uses the same coverage object for these two fields.
        row["deep_analysis"]["coverage"].update(acquisition_state_sha256="a"*64,
            acquisition_input_fingerprint="b"*64, acquisition_receipt_status="revalidated_not_reviewed")
        schema.validate_saved_record(row)
        row["deep_analysis"]["coverage"]["acquisition_receipt_status"] = "approved"
        with self.assertRaises(ValueError):
            schema.validate_saved_record(row)
        row["deep_analysis"]["coverage"]["acquisition_receipt_status"] = "revalidated_not_reviewed"
        row["deep_analysis"]["coverage"].pop("acquisition_input_fingerprint")
        with self.assertRaises(ValueError):
            schema.validate_saved_record(row)

    def test_claim_locations_and_anchor_hashes_cannot_hide_source_prose(self):
        for field, value in (("location", "Full private article text instead of a source location"),
                              ("start", True), ("start", -1), ("end", 100_000_000)):
            with self.subTest(field=field):
                self.reject(lambda row: row["deep_analysis"]["claim_evidence"][0]["locations"][0].update({field: value}))
        self.reject(lambda row: row["deep_analysis"]["claim_evidence"][0].update(evidence_anchor_sha256="not_a_hash"))
        self.reject(lambda row: row["deep_analysis"]["claim_evidence"][0].update(chunk_id="C9999"))

    def test_detached_reading_coverage_is_rejected(self):
        self.reject(lambda row: row["reading_coverage"].update(source_sha256="c"*64))
        self.reject(lambda row: row.pop("reading_coverage"))

    def test_unknown_or_unsanitized_attempt_diagnostics_are_rejected(self):
        self.reject(lambda row: row["complete_reading_attempt"]["provider_diagnostics"][0].update(raw_response="PRIVATE_SOURCE"))
        self.reject(lambda row: row["complete_reading_attempt"]["provider_diagnostics"][0].update(url="https://www.econstor.eu/p?token=SECRET"))
        self.reject(lambda row: row["complete_reading_attempt"].update(approved=True))

    def test_inconsistent_attempt_status_and_future_dates_are_rejected(self):
        self.reject(lambda row: row["complete_reading_attempt"].update(status="partial_summary"))
        self.reject(lambda row: row["deep_analysis"].update(created_at="2099-01-01"))
        self.reject(lambda row: row["complete_reading_attempt"].update(next_at="2000-01-01"))

    def test_matching_revalidation_and_explicit_hold_are_accepted(self):
        checked = self.revalidation()
        schema.validate_revalidation(checked, self.record["deep_analysis"], "a"*64, now=self.now)
        checked.pop("source_sha256"); checked.pop("document_version")
        checked.update(status="held", reason="prepared_source_changed")
        schema.validate_revalidation(checked, self.record["deep_analysis"], "a"*64, now=self.now)

    def test_revalidation_requires_exact_source_basis_and_actual_timestamp(self):
        for field, value in (("checked_at", "2099-01-01T00:00:00+00:00"), ("checked_at", "2000-01-01T00:00:00"),
                              ("approved", True), ("source_sha256", "b"*64), ("document_version", "anotherVersion"),
                              ("basis", "c"*64), ("raw_source", "PRIVATE_SOURCE")):
            with self.subTest(field=field):
                checked = self.revalidation(); checked[field] = value
                with self.assertRaisesRegex(ValueError, schema.ERROR):
                    schema.validate_revalidation(checked, self.record["deep_analysis"], "a"*64, now=self.now)

    def test_revalidation_cannot_promote_a_partial_analysis(self):
        row = generated(complete=False)
        with self.assertRaisesRegex(ValueError, schema.ERROR):
            schema.validate_revalidation(self.revalidation(row), row["deep_analysis"], "a"*64)

    def test_strip_staged_fields_is_a_copy_and_never_inherits_review(self):
        original = {**self.record, "original_reading": {"publication": {"decision": "approved"}},
                    "analysis": {"methods": "RAW_SOURCE"}, "source_review": {"approved": True},
                    "fulltext_candidates": [{"url": "https://www.econstor.eu/source.pdf"}]}
        result = schema.strip_staged_enrichment(original)
        self.assertFalse(set(result) & schema.STAGED_FIELDS)
        self.assertEqual(result["fulltext_candidates"], original["fulltext_candidates"])
        result["fulltext_candidates"][0]["url"] = "changed"
        self.assertNotEqual(result["fulltext_candidates"], original["fulltext_candidates"])
        self.assertIn("deep_analysis", original)

    def test_preparation_provenance_never_grants_approval(self):
        row = deepcopy(self.record)
        monday = self.now.date() - timedelta(days=self.now.weekday() + 7)
        row["deep_analysis"]["preparation_provenance"] = {
            "publication_window": {"from": monday.isoformat(), "to": (monday+timedelta(days=6)).isoformat(), "timezone": "UTC"},
            "source_revalidated_at": self.now.isoformat(), "independently_approved": False}
        schema.validate_saved_record(row, now=self.now)
        row["deep_analysis"]["preparation_provenance"]["independently_approved"] = True
        with self.assertRaises(ValueError):
            schema.validate_saved_record(row, now=self.now)


if __name__ == "__main__":
    unittest.main()
