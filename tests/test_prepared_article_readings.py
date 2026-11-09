"""Offline rolling retrieval/review and strict post-Sunday publication boundary."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepared_article_readings as prepared
import comprehensive_readings as reading
from test_weekly_source_acquisition import queue, item, document, result_for

FRIDAY = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
MONDAY = datetime(2026, 11, 16, 7, tzinfo=timezone.utc)
WINDOW = {"from": "2026-11-09", "to": "2026-11-15", "timezone": "UTC"}


def packet(closed=False):
    now = MONDAY if closed else FRIDAY
    record = item()
    record.update(kind="nonacademic", published="2026-11-13", first_seen="2026-11-13")
    record["publication_date_provenance"] = {"status": "day_known", "basis": "editor_verified_original_publication_date",
                                              "value": record["published"], "checked_at": "2026-11-13"}
    return {"schema_version": 1, "kind": "weekly_preparation", "observation_at": now.isoformat(),
        "target_publication_window": dict(WINDOW), "phase": "closed" if closed else "preparing",
        "status": "prepared", "date_eligibility": "verified_original_publication_date_only",
        "public_eligible": False, "source_checked": False, "approved": False,
        "run": {"date": now.date().isoformat(), "mode": "preparation", "publication_window": dict(WINDOW)},
        "items": [record], "quarantine": [], "coverage": {"closeout_required": not closed,
            **({"closeout_started_at": MONDAY.isoformat()} if closed else {})}}


def claim(model, chunk, kind, title, **kwargs):
    return [{"field": reading.FIELDS[kind][0],
             "text": "Careful interpretation of this source remains necessary before drawing broader conclusions.",
             "quote": " ".join(chunk["text"].split()[:8])}]


class PreparedReadingTests(unittest.TestCase):
    def setUp(self):
        self.packet = packet()
        self.document = document()
        self.state = prepared.acquire(self.packet, now=FRIDAY, known_sources_only=True,
            attempt=lambda *args: result_for(self.document), clock=lambda: 0)

    def reviewed(self, document=None, packet=None, state=None, previous=None, now=FRIDAY):
        with patch.object(reading, "read_chunk", side_effect=claim):
            return prepared.review(packet or self.packet, state or self.state, previous, model=Mock(), now=now,
                retriever=Mock(return_value=(deepcopy(document or self.document), [])))

    def closed(self, bundle=None):
        return prepared.revalidate(packet(True), self.state, bundle or self.reviewed(), now=MONDAY,
                                   retriever=Mock(return_value=(deepcopy(self.document), [])))

    def canonical_weekly(self):
        from weekly_preparation import closed_packet
        return closed_packet(packet(True), now=MONDAY)

    def test_open_week_uses_actual_time_and_cannot_enter_production_queue(self):
        self.assertEqual(self.state["run"]["checked_at"], FRIDAY.isoformat())
        self.assertEqual(self.state["publication_window"], WINDOW)
        self.assertEqual(self.state["run"]["statuses"], {"full_document_retrieved_not_reviewed": 1})
        with self.assertRaisesRegex(ValueError, "previous_completed_utc_week_required"):
            queue.run(self.packet, now=FRIDAY)

    def test_repeat_acquisition_preserves_completed_receipt_without_new_request(self):
        fetch = Mock()
        state = prepared.acquire(self.packet, self.state, now=FRIDAY, known_sources_only=True, attempt=fetch)
        fetch.assert_not_called()
        self.assertEqual(state["records"], self.state["records"])

    def test_machine_reading_is_private_and_never_an_approval(self):
        bundle = self.reviewed()
        self.assertEqual(bundle["review_run"]["summaries_completed"], 1)
        self.assertFalse(bundle["approved"])
        self.assertFalse(bundle["public_eligible"])
        self.assertFalse(bundle["source_text_saved"])
        record = next(iter(bundle["records"].values()))["record"]
        self.assertEqual(record["deep_analysis"]["created_at"], "2026-11-13")
        self.assertEqual(record["deep_analysis"]["review_status"], "machine_checked_not_independently_reviewed")
        self.assertNotIn("source_review", record)
        self.assertNotIn("original_reading", record)
        self.assertNotIn(self.document.units[0]["text"], json.dumps(bundle))

    def test_only_post_closeout_same_source_can_apply(self):
        bundle = self.closed()
        library = deepcopy(self.packet["items"])
        output, report = prepared.apply_closed(packet(True), self.state, bundle, library, self.canonical_weekly(), now=MONDAY)
        self.assertEqual(report["machine_checked_readings_applied"], 1)
        self.assertNotIn("deep_analysis", library[0])
        self.assertFalse(report["approved"])
        self.assertFalse(output[0]["deep_analysis"]["preparation_provenance"]["independently_approved"])
        with self.assertRaises(ValueError):
            prepared.apply_closed(self.packet, self.state, bundle, library, self.canonical_weekly(), now=FRIDAY)
        incomplete = packet(True); incomplete["coverage"]["closeout_required"] = True
        with self.assertRaises(ValueError):
            prepared.revalidate(incomplete, self.state, self.reviewed(), now=MONDAY)

    def test_changed_source_is_held_and_not_imported(self):
        changed = deepcopy(self.document)
        changed.units[0]["text"] += " Materially new source passage."
        bundle = prepared.revalidate(packet(True), self.state, self.reviewed(), now=MONDAY,
                                     retriever=Mock(return_value=(changed, [])))
        checked = next(iter(bundle["records"].values()))["revalidation"]
        self.assertEqual(checked["status"], "held")
        self.assertEqual(checked["reason"], "prepared_source_changed")
        output, report = prepared.apply_closed(packet(True), self.state, bundle, self.packet["items"], self.canonical_weekly(), now=MONDAY)
        self.assertEqual(report["machine_checked_readings_applied"], 0)
        self.assertNotIn("deep_analysis", output[0])

    def test_revalidation_cache_is_bound_and_cannot_be_future_dated(self):
        bundle = self.closed(); fetch = Mock()
        prepared.revalidate(packet(True), self.state, bundle, now=MONDAY, retriever=fetch)
        fetch.assert_not_called()
        bad = deepcopy(bundle)
        next(iter(bad["records"].values()))["revalidation"]["checked_at"] = "2099-01-01T00:00:00+00:00"
        prepared.sealed(bad)
        with self.assertRaises(ValueError):
            prepared.revalidate(packet(True), self.state, bad, now=MONDAY, retriever=fetch)
        fetch.assert_not_called()

    def test_held_revalidation_does_not_starve_unchecked_or_older_records(self):
        source = packet()
        for number in (2, 3):
            row = deepcopy(source["items"][0])
            row.update(doi=f"10.5555/weekly{number}", url=f"https://www.econstor.eu/article{number}.pdf")
            source["items"].append(row)
        state = prepared.acquire(source, now=FRIDAY, known_sources_only=True,
            attempt=lambda *args: result_for(self.document), clock=lambda: 0)
        with patch.object(reading, "read_chunk", side_effect=claim):
            bundle = prepared.review(source, state, model=Mock(), now=FRIDAY, limit=3,
                retriever=lambda row: (deepcopy(self.document), []))
        closing = packet(True); closing["items"] = deepcopy(source["items"])
        order = [item["record"]["doi"] for _, item in sorted(bundle["records"].items())]
        successful = order[-1]
        calls = []
        def retrieve(row):
            calls.append(row["doi"])
            return (deepcopy(self.document) if row["doi"] == successful else None), []
        for minute in range(5):
            # Simulate a new process and differently ordered metadata each run.
            bundle = json.loads(json.dumps(bundle))
            closing["items"].reverse()
            bundle = prepared.revalidate(closing, state, bundle,
                now=MONDAY + timedelta(minutes=minute), limit=1, retriever=retrieve)
        self.assertEqual(calls, order + order[:2])
        self.assertEqual(calls.count(successful), 1)
        for item in bundle["records"].values():
            checked = item["revalidation"]
            self.assertFalse(checked["approved"])
            if item["record"]["doi"] != successful:
                self.assertEqual(checked["status"], "held")
                self.assertEqual(checked["reason"], "prepared_source_unavailable")
                self.assertGreaterEqual(queue.utc_now(checked["checked_at"]), MONDAY)

    def test_alternative_receipt_is_held_before_model_and_keeps_retry_delay(self):
        alternative = deepcopy(self.document)
        alternative.url = "https://www.econstor.eu/independent-alternative.pdf"
        fetch = Mock(return_value=(alternative, []))
        with patch.object(reading, "synthesize") as synthesize:
            bundle = prepared.review(self.packet, self.state, model=Mock(), now=FRIDAY, retriever=fetch)
            again = prepared.review(self.packet, self.state, json.loads(json.dumps(bundle)),
                model=Mock(), now=FRIDAY + timedelta(hours=1), retriever=fetch)
        synthesize.assert_not_called()
        fetch.assert_called_once()
        self.assertEqual(bundle["review_run"]["attempted"], 1)
        self.assertEqual(bundle["review_run"]["failed"], 1)
        self.assertEqual(again["review_run"]["attempted"], 0)
        record = next(iter(again["records"].values()))["record"]
        self.assertNotIn("deep_analysis", record)
        self.assertEqual(record["complete_reading_attempt"]["status"], "prepared_acquisition_receipt_mismatch")
        self.assertEqual(record["complete_reading_attempt"]["next_at"], "2026-11-15")
        self.assertEqual(self.state["records"][queue.record_key(record)]["document"]["source_url"],
                         self.document.manifest()["source_url"])
        recovered = self.reviewed(previous=again, now=FRIDAY + timedelta(days=2))
        self.assertEqual(recovered["review_run"]["summaries_completed"], 1)

    def test_byte_version_and_coverage_mismatch_never_spend_model_work(self):
        for kind in ("bytes", "version", "coverage", "text"):
            changed = deepcopy(self.document)
            acquired = deepcopy(self.document)
            if kind == "bytes":
                acquired.source_bytes = b"%PDF-original"
                changed.source_bytes = b"%PDF-changed"
            elif kind == "version":
                changed.version = "acceptedVersion"
            elif kind == "coverage":
                changed.coverage["evidence_status"] = "partial_full_text"
            else:
                changed.units[0]["text"] += " Changed text."
            state = prepared.acquire(self.packet, now=FRIDAY, known_sources_only=True,
                attempt=lambda *args: result_for(acquired), clock=lambda: 0)
            with self.subTest(kind=kind), patch.object(reading, "synthesize") as synthesize:
                bundle = prepared.review(self.packet, state, model=Mock(), now=FRIDAY,
                    retriever=lambda row: (changed, []))
                synthesize.assert_not_called()
                self.assertEqual(bundle["review_run"]["failure_stages"], {"retrieval": 1})

    def test_removing_stale_analysis_preserves_unchanged_input_failure_cooldown(self):
        bundle = self.reviewed()
        record = next(iter(bundle["records"].values()))["record"]
        record["complete_reading_attempt"] = {
            "status": "prepared_acquisition_receipt_mismatch", "stage": "retrieval",
            "last_at": "2026-11-13", "next_at": "2026-11-15", "provider_diagnostics": []}
        prepared.sealed(bundle)
        changed = deepcopy(self.document)
        changed.units[0]["text"] += " New receipt evidence."
        state = prepared.acquire(self.packet, now=FRIDAY, known_sources_only=True,
            attempt=lambda *args: result_for(changed), clock=lambda: 0)
        fetch = Mock(return_value=(changed, []))
        result = prepared.review(self.packet, state, bundle, model=Mock(), now=FRIDAY, retriever=fetch)
        fetch.assert_not_called()
        saved = next(iter(result["records"].values()))["record"]
        self.assertNotIn("deep_analysis", saved)
        self.assertEqual(saved["complete_reading_attempt"], record["complete_reading_attempt"])

    def test_resealed_raw_source_or_approval_fields_fail_closed(self):
        for field, value in (("raw_source_text", "PRIVATE SOURCE SENTINEL"), ("approved", True)):
            bundle = self.closed()
            next(iter(bundle["records"].values()))["record"]["deep_analysis"][field] = value
            prepared.sealed(bundle)
            with self.assertRaises(ValueError):
                prepared.apply_closed(packet(True), self.state, bundle, self.packet["items"], self.canonical_weekly(), now=MONDAY)

    def test_bundle_envelope_and_hash_metadata_are_closed(self):
        for field, value in (("raw_document", "PRIVATE"), ("packet_sha256", "invalid"),
                             ("observation_at", "2099-01-01T00:00:00+00:00")):
            bundle = self.reviewed(); bundle[field] = value; prepared.sealed(bundle)
            with self.assertRaises(ValueError):
                prepared.reconcile(self.packet, self.state, bundle, now=FRIDAY)
        bundle = self.reviewed()
        next(iter(bundle["records"].values()))["raw_document"] = "PRIVATE"
        prepared.sealed(bundle)
        with self.assertRaises(ValueError):
            prepared.reconcile(self.packet, self.state, bundle, now=FRIDAY)

    def test_changed_registry_cannot_reconstruct_both_inputs_and_reuse_old_notes(self):
        old = self.reviewed()
        original = queue.prepare
        def revised(record, window, known_only):
            routes, excluded, fingerprint = original(record, window, known_only)
            return routes, excluded, queue.digest({"changed_registry": fingerprint})
        with patch.object(queue, "prepare", side_effect=revised):
            new_state = prepared.acquire(self.packet, now=FRIDAY, known_sources_only=True,
                attempt=lambda *args: result_for(self.document), clock=lambda: 0)
            result = prepared.reconcile(self.packet, new_state, old, now=FRIDAY)
        self.assertNotIn("deep_analysis", next(iter(result["records"].values()))["record"])

    def test_staged_approval_fields_do_not_skip_review_or_get_copied(self):
        staged = packet()
        staged["items"][0].update(source_review={"approved": True},
                                 deep_analysis={"approved": True, "raw_source_text": "PRIVATE"})
        # Those fields never alter source identity or retrieval proof.
        with patch.object(prepared, "validated_window", return_value=dict(WINDOW)):
            bundle = self.reviewed(packet=staged)
        row = next(iter(bundle["records"].values()))["record"]
        self.assertNotIn("source_review", row)
        self.assertNotIn("original_reading", row)
        self.assertNotIn("approved", row["deep_analysis"])
        self.assertEqual(bundle["review_run"]["attempted"], 1)
        staged["items"][0]["original_reading"] = {"status": "accepted"}
        with patch.object(prepared, "validated_window", return_value=dict(WINDOW)):
            held = self.reviewed(packet=staged)
        self.assertEqual(held["records"], {})

    def test_conflicting_duplicate_publication_identity_fails_closed(self):
        weekly = self.canonical_weekly()
        wrong = deepcopy(weekly["items"][0]); wrong["title"] = "Conflicting article"
        weekly["items"].insert(0, wrong)
        with self.assertRaisesRegex(ValueError, "duplicate_weekly_publication_identity"):
            prepared.apply_closed(packet(True), self.state, self.closed(), self.packet["items"], weekly, now=MONDAY)

    def test_operational_date_recheck_does_not_regenerate_machine_reading(self):
        old = self.reviewed()
        current = packet(True)
        current["items"][0]["publication_date_provenance"]["checked_at"] = "2026-11-16"
        new_state = prepared.acquire(current, self.state, now=MONDAY, known_sources_only=True,
            attempt=lambda *args: result_for(self.document), clock=lambda: 0)
        bundle = prepared.reconcile(current, new_state, old, now=MONDAY)
        self.assertIn("deep_analysis", next(iter(bundle["records"].values()))["record"])
        canonical = deepcopy(current["items"])
        canonical[0]["publication_date_provenance"]["checked_at"] = "2026-11-17"
        bundle = prepared.revalidate(current, new_state, bundle, now=MONDAY,
            retriever=Mock(return_value=(deepcopy(self.document), [])))
        output, report = prepared.apply_closed(current, new_state, bundle, canonical,
            {"run": {"publication_window": WINDOW}, "items": canonical}, now=MONDAY)
        self.assertEqual(report["machine_checked_readings_applied"], 1)

    def test_semantic_date_or_route_changes_cannot_reuse_reading(self):
        for change in ({"title": "Changed title"}, {"fulltext_candidates": [{"url": "https://www.econstor.eu/new.pdf"}]}):
            candidate = deepcopy(self.packet["items"][0]); candidate.update(change)
            self.assertFalse(prepared.same_input(candidate, self.packet["items"][0], WINDOW, True))

    def test_model_failure_and_partial_source_remain_unapproved(self):
        with patch.object(reading, "synthesize", side_effect=ValueError("claim_verification_failed")):
            failed = prepared.review(self.packet, self.state, model=Mock(), now=FRIDAY,
                                      retriever=Mock(return_value=(self.document, [])))
        self.assertEqual(failed["review_run"]["failed"], 1)
        self.assertNotIn("deep_analysis", next(iter(failed["records"].values()))["record"])
        partial = deepcopy(self.document); partial.coverage["evidence_status"] = "partial_full_text"
        state = prepared.acquire(self.packet, now=FRIDAY, known_sources_only=True,
                                 attempt=lambda *args: result_for(partial), clock=lambda: 0)
        bundle = self.reviewed(document=partial, state=state)
        checked = prepared.revalidate(packet(True), state, bundle, now=MONDAY, retriever=Mock())
        self.assertEqual(checked["revalidation_run"]["attempted"], 0)


if __name__ == "__main__":
    unittest.main()
