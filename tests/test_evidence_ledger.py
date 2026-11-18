"""Synthetic, offline ledger tests. No held-out examples, retrieval or inference."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import comprehensive_readings as reading
from full_document_access import Document
import evidence_ledger as ledger


TEXT = ("The classroom comparison included 47 learners who completed an assisted exercise. "
        "Participants were assigned by existing classroom rather than individually randomized. "
        "The reported test describes immediate task completion only and cannot establish "
        "independent learning or later transfer beyond this setting.")
LATER = ("Later limitations identify unmeasured baseline differences between classrooms. "
         "Follow up without assistance was unavailable and the investigation did not test "
         "lasting attention changes. The interpretation should therefore stay narrow and "
         "should not imply a causal benefit for independent performance.")
PARAPHRASE = "This comparison leaves durable unassisted learning uncertain despite describing an assisted exercise."
POLICY = sha256(b"synthetic offline policy version 1").hexdigest()


def context(two=True, blank=False, limit=5500):
    units = [{"location": "page:1", "text": TEXT}]
    sections = ["results"]
    if blank:
        units.append({"location": "page:2", "text": ""})
        sections.append("unknown")
    if two:
        units.append({"location": "page:3" if blank else "page:2", "text": LATER})
        sections.append("limitations")
    doc = Document(units, "https://example.org/source?token=URL_SECRET#PRIVATE_FRAGMENT", "submitted-v2",
        {"evidence_status": "full_document_retrieved", "all_retrieved_text_processed": True,
         "source_body": "COVERAGE_SECRET", "token": "DO_NOT_SAVE"}, b"%PDF-1.7 PRIVATE_PDF_BYTES")
    return ledger.SourceContext(doc, reading.chunk_document(doc, limit), "private-record-id",
        POLICY, provider="user_supplied", license_code="restricted", sections=sections)


def valid_claim(chunk, text=PARAPHRASE):
    return {"field": "limitations", "text": text,
            "quote": " ".join(reading.source_spans(chunk)[0]["text"].split())}


def hold_lock(path, ready, release):
    import fcntl
    fd = os.open(str(Path(path) / ".lock"), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    ready.set()
    release.wait(10)
    os.close(fd)


class EvidenceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="private-evidence-tests-")
        self.base = Path(self.temp.name)
        self.directory = self.base / "private" / "paper"
        self.source = context()
        self.handles = []

    def tearDown(self):
        for handle in self.handles:
            handle.close()
        self.temp.cleanup()

    def open(self, source=None, directory=None):
        handle = ledger.EvidenceLedger.open(directory or self.directory, source or self.source)
        self.handles.append(handle)
        return handle

    def checked(self, handle, source=None, claims=None):
        source = source or self.source
        calls = []
        def reader(model, chunk, kind, title, deadline=None):
            calls.append(chunk["id"])
            return claims if claims is not None else [valid_claim(chunk)]
        with patch.object(reading, "read_chunk", side_effect=reader):
            for chunk in source.chunks:
                handle.run_chunk(source, chunk["id"], model=object(), title="Synthetic title")
        return calls

    def mutate_file(self, mutate, checksum=True):
        path = self.directory / "ledger.json"
        wrapper = json.loads(path.read_text())
        mutate(wrapper["payload"])
        if checksum:
            wrapper["sha256"] = ledger._digest(wrapper["payload"])
        path.write_text(json.dumps(wrapper))

    def test_round_trip_resumes_completed_claims_without_running_reader(self):
        handle = self.open()
        self.checked(handle)
        expected = handle.claims_for("C0001")
        handle.close()
        resumed = self.open()
        with patch.object(reading, "read_chunk") as reader:
            self.assertEqual(resumed.run_chunk(self.source, "C0001", model=None, title="Ignored"), expected)
            reader.assert_not_called()
        self.assertEqual(expected[0]["text"], PARAPHRASE)
        self.assertNotIn("quote", expected[0])
        self.assertTrue(resumed.status()["all_retrieved_text_processed"])
        self.assertEqual(resumed.status()["cross_section_review"], "pending")
        self.assertEqual(resumed.status()["independent_review"], "pending")

    def test_all_units_intervals_and_no_overstated_coverage(self):
        source = context(blank=True, limit=250)
        handle = self.open(source)
        status = handle.status()
        self.assertEqual([u["location"] for u in status["units"]], ["page:1", "page:2", "page:3"])
        self.assertEqual(status["units"][1]["characters"], 0)
        self.assertFalse(status["all_retrieved_text_processed"])
        self.assertEqual(status["whole_article_coverage"], "not_established")
        self.assertEqual(status["semantic_completeness"], "not_verified")
        self.assertNotIn("public_ready", status)
        self.checked(handle, source, claims=[])
        self.assertEqual(sum(r["end"] - r["start"] for r in handle.status()["processed_intervals"]), len(TEXT) + len(LATER))
        self.assertIn("page:2", handle.status()["unexamined_units"])

    def test_source_identity_version_text_bytes_and_policy_drift_fail_closed(self):
        self.open()
        variants = [replace(self.source, source_id="other-source"),
                    replace(self.source, policy_sha256=sha256(b"new model or prompt").hexdigest()),
                    replace(self.source, provider="repository"), replace(self.source, sections=["methods", "limitations"])]
        for key, value in (("url", "https://example.org/other"), ("version", "submitted-v3"),
                           ("source_bytes", b"%PDF altered")):
            doc = deepcopy(self.source.document)
            setattr(doc, key, value)
            variants.append(replace(self.source, document=doc))
        doc = deepcopy(self.source.document)
        doc.units[0]["text"] = doc.units[0]["text"].replace("47", "48")
        variants.append(replace(self.source, document=doc, chunks=reading.chunk_document(doc)))
        variants.append(replace(self.source, chunks=reading.chunk_document(self.source.document, 250)))
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaisesRegex(ledger.LedgerError, "source_binding_mismatch"):
                self.open(changed)
        self.assertEqual(self.open().status()["per_chunk_machine_checks"][0]["state"], "pending")

    def test_coverage_dictionary_is_ignored_not_trusted_or_saved(self):
        handle = self.open()
        self.source.document.coverage = {"raw_response": "UNTRUSTED_RESPONSE", "review_status": "public_ready"}
        self.assertEqual(self.open().status(), handle.status())
        self.assertNotIn("UNTRUSTED_RESPONSE", (self.directory / "ledger.json").read_text())

    def test_invalid_gap_overlap_missing_duplicate_and_out_of_order_ranges(self):
        base = context(limit=250)
        for change in ("gap", "overlap", "missing", "duplicate", "reverse", "zero", "boolean", "unknown", "text"):
            chunks = deepcopy(base.chunks)
            if change == "gap": chunks[0]["ranges"][0]["start"] = 1
            if change == "overlap": chunks[1]["ranges"][0]["start"] -= 1
            if change == "missing": chunks.pop()
            if change == "duplicate": chunks[0]["ranges"].append(deepcopy(chunks[0]["ranges"][0]))
            if change == "reverse": chunks.reverse()
            if change == "zero": chunks[0]["ranges"][0]["end"] = 0
            if change == "boolean": chunks[0]["ranges"][0]["start"] = False
            if change == "unknown": chunks[0]["ranges"][0]["location"] = "page:99"
            if change == "text": chunks[0]["text"] += " inserted text"
            with self.subTest(change=change), self.assertRaises(ledger.LedgerError):
                self.open(replace(base, chunks=chunks))
        self.assertFalse(self.directory.exists())

    def test_duplicate_locations_and_unallowlisted_provenance_fail(self):
        variants = []
        doc = deepcopy(self.source.document)
        doc.units[1]["location"] = "page:1"
        variants.append(replace(self.source, document=doc))
        doc = deepcopy(self.source.document)
        doc.units[0]["location"] = "SECRET_SECTION_TITLE"
        variants.append(replace(self.source, document=doc))
        variants.extend((replace(self.source, sections=["Raw protected heading", "limitations"]),
                         replace(self.source, provider="secret token"), replace(self.source, policy_sha256="missing")))
        for source in variants:
            with self.assertRaises(ledger.LedgerError): self.open(source)

    def test_private_files_and_all_new_directories_have_strict_permissions(self):
        self.open()
        for name in (self.directory, self.directory.parent):
            self.assertEqual(stat.S_IMODE(name.stat().st_mode), 0o700)
        for name in self.directory.iterdir():
            self.assertEqual(stat.S_IMODE(name.stat().st_mode), 0o600)

    def test_repository_paths_relative_paths_and_dotdot_are_rejected(self):
        for path in (ledger.ROOT / "private-ledger", Path("private-ledger"), self.base / ".." / "escape"):
            with self.subTest(path=path), self.assertRaises(ledger.LedgerError): self.open(directory=path)
        repo = self.base / "other-repo"
        repo.mkdir(mode=0o700)
        (repo / ".git").write_text("gitdir: /some/worktree")
        with self.assertRaisesRegex(ledger.LedgerError, "repository_path_forbidden"):
            self.open(directory=repo / "private")

    def test_symlink_directory_and_repository_escape_are_rejected(self):
        target = self.base / "target"
        target.mkdir(mode=0o700)
        for name, dest in (("private-link", target), ("repo-link", ledger.ROOT)):
            link = self.base / name
            link.symlink_to(dest, target_is_directory=True)
            with self.assertRaises(ledger.LedgerError): self.open(directory=link / "new")
        self.assertFalse((target / "new").exists())

    def test_symlink_file_hardlink_and_insecure_mode_are_rejected(self):
        handle = self.open()
        handle.close()
        data = self.directory / "ledger.json"
        backup = self.base / "backup"
        data.rename(backup)
        data.symlink_to(backup)
        with self.assertRaises(ledger.LedgerError): self.open()
        data.unlink()
        os.link(backup, data)
        with self.assertRaisesRegex(ledger.LedgerError, "unsafe_ledger_file"): self.open()
        data.unlink()
        backup.rename(data)
        data.chmod(0o644)
        with self.assertRaisesRegex(ledger.LedgerError, "unsafe_ledger_file"): self.open()

    def test_insecure_existing_directory_is_not_silently_chmodded(self):
        self.directory.mkdir(parents=True)
        self.directory.chmod(0o755)
        with self.assertRaisesRegex(ledger.LedgerError, "private_directory_permissions_required"): self.open()
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o755)

    def test_directory_substitution_invalidates_open_handle(self):
        handle = self.open()
        relocated = self.directory.with_name("moved")
        self.directory.rename(relocated)
        self.directory.mkdir(mode=0o700)
        with self.assertRaisesRegex(ledger.LedgerError, "private_directory_replaced"):
            handle.add_obligation(self.source, kind="later_limitation", origin_location="page:2", affected_chunks=["C0001"])

    def test_source_quote_pdf_url_coverage_and_identifier_nonpersistence(self):
        handle = self.open()
        self.checked(handle)
        for path in self.directory.iterdir():
            data = path.read_bytes()
            for secret in (TEXT, LATER, "PRIVATE_PDF_BYTES", "URL_SECRET", "PRIVATE_FRAGMENT",
                           "COVERAGE_SECRET", "DO_NOT_SAVE", "private-record-id", "submitted-v2",
                           valid_claim(self.source.chunks[0])["quote"]):
                self.assertNotIn(secret.encode(), data)
        self.assertIn(PARAPHRASE, (self.directory / "ledger.json").read_text())

    def test_extra_raw_response_or_quote_fields_are_not_salvaged(self):
        handle = self.open()
        claims = [dict(valid_claim(self.source.chunks[0]), raw_response="SECRET_RESPONSE")]
        with self.assertRaisesRegex(ledger.LedgerError, "invalid_checked_claims"):
            self.checked(handle, claims=claims)
        self.assertEqual(handle.status()["per_chunk_machine_checks"][0]["claim_count"], 0)
        self.assertNotIn("SECRET_RESPONSE", (self.directory / "ledger.json").read_text())

    def test_existing_anchor_number_copy_gates_remain_required(self):
        for variant, code in (("anchor", "claim_anchor_absent"), ("number", "unsupported_numeric_claim"),
                              ("copy", "copied_source_passage")):
            source = context(two=False)
            handle = self.open(source, self.base / variant)
            claim = valid_claim(source.chunks[0])
            if variant == "anchor": claim["quote"] = "This supporting quotation never appeared in the source"
            if variant == "number": claim["text"] = "A comparison involving 9000 learners established lasting unassisted learning benefits."
            if variant == "copy": claim["text"] = " ".join(TEXT.split()[:16])
            with self.assertRaisesRegex(ledger.LedgerError, code): self.checked(handle, source, [claim])
            self.assertFalse(handle.status()["all_retrieved_text_processed"])

    def test_short_verbatim_claim_and_credentials_are_rejected(self):
        for n, text in enumerate((" ".join(TEXT.split()[:8]),
                "Researchers disclosed the password dangerous-secret while describing their study methods.",
                "Further details appear at https://example.org/token=EXPOSED inside the original discussion.",
                "The identifier sk-abcdefghijklmnopqrstuvwxyz123456789 was included alongside observed task outcomes.")):
            source = context(two=False)
            handle = self.open(source, self.base / f"privacy-{n}")
            with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
                self.checked(handle, source, [valid_claim(source.chunks[0], text)])
            self.assertNotIn(text, (handle.directory / "ledger.json").read_text())

    def test_aggregate_copy_split_across_individually_nonverbatim_claims_is_rejected(self):
        source = context(two=False)
        words = TEXT.split()
        one = "A cautious interpretation says " + " ".join(words[:7])
        two = " ".join(words[7:14]) + " which remains a tentative interpretation."
        handle = self.open(source)
        with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
            self.checked(handle, source, [valid_claim(source.chunks[0], one), valid_claim(source.chunks[0], two)])
        self.assertEqual(handle.status()["per_chunk_machine_checks"][0]["claim_count"], 0)

    def test_no_accepted_subset_after_one_claim_fails(self):
        handle = self.open()
        good = valid_claim(self.source.chunks[0])
        bad = {**good, "text": "The trial involved 50000 learners and demonstrated improved independent learning."}
        with self.assertRaises(ledger.LedgerError): self.checked(handle, claims=[good, bad])
        self.assertNotIn(PARAPHRASE, (self.directory / "ledger.json").read_text())
        with self.assertRaisesRegex(ledger.LedgerError, "chunk_not_checked"): handle.claims_for("C0001")

    def test_final_verifier_rejection_cannot_be_retried_into_acceptance(self):
        handle = self.open()
        with patch.object(reading, "read_chunk", side_effect=ValueError("claim_verification_failed")):
            with self.assertRaisesRegex(ledger.LedgerError, "claim_verification_failed"):
                handle.run_chunk(self.source, "C0001", model=None, title="Synthetic")
        resumed = self.open()
        with patch.object(reading, "read_chunk") as reader:
            with self.assertRaisesRegex(ledger.LedgerError, "no_automatic_retry"):
                resumed.run_chunk(self.source, "C0001", model=None, title="Synthetic")
            reader.assert_not_called()
        self.assertEqual(resumed.status()["per_chunk_machine_checks"][0]["error"], "claim_verification_failed")

    def test_untrusted_exception_text_is_never_saved_or_returned(self):
        handle = self.open()
        with patch.object(reading, "read_chunk", side_effect=RuntimeError("password=EXCEPTION_SECRET " + TEXT)):
            with self.assertRaisesRegex(ledger.LedgerError, "^reader_failed$"):
                handle.run_chunk(self.source, "C0001", model=None, title="Synthetic")
        self.assertNotIn("EXCEPTION_SECRET", (self.directory / "ledger.json").read_text())

    def test_keyboard_interrupt_records_uncertainty_without_claims(self):
        handle = self.open()
        with patch.object(reading, "read_chunk", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): handle.run_chunk(self.source, "C0001", model=None, title="Synthetic")
        resumed = self.open()
        self.assertEqual(resumed.status()["per_chunk_machine_checks"][0]["state"], "interrupted")
        with self.assertRaisesRegex(ledger.LedgerError, "no_automatic_retry"):
            resumed.run_chunk(self.source, "C0001", model=None, title="Synthetic")

    def test_lost_process_started_state_resumes_as_interrupted(self):
        handle = self.open()
        handle.close()
        self.mutate_file(lambda state: state["checkpoints"][0].update(state="started"))
        resumed = self.open()
        self.assertEqual(resumed.status()["per_chunk_machine_checks"][0]["error"], "interrupted_or_uncertain")
        self.assertFalse(resumed.status()["all_retrieved_text_processed"])

    def test_write_interrupted_before_replace_retains_previous_committed_state(self):
        handle = self.open()
        previous = (self.directory / "ledger.json").read_bytes()
        with patch.object(ledger.os, "replace", side_effect=OSError("RAW_IO_SECRET")):
            with self.assertRaisesRegex(ledger.LedgerError, "ledger_write_uncertain"):
                handle.add_obligation(self.source, kind="later_limitation", origin_location="page:2", affected_chunks=["C0001"])
        self.assertEqual((self.directory / "ledger.json").read_bytes(), previous)
        self.assertEqual(self.open().status()["unresolved_obligations"], [])
        with self.assertRaisesRegex(ledger.LedgerError, "ledger_reopen_required"):
            handle.add_obligation(self.source, kind="contradiction", origin_location="page:2", affected_chunks=["C0001"])

    def test_write_interrupted_after_replace_has_uncertain_outcome_then_valid_resume(self):
        handle = self.open()
        real_fsync = os.fsync
        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode): raise OSError("sensitive filesystem detail")
            return real_fsync(fd)
        with patch.object(ledger.os, "fsync", side_effect=fail_directory):
            with self.assertRaisesRegex(ledger.LedgerError, "ledger_write_uncertain"):
                handle.add_obligation(self.source, kind="later_limitation", origin_location="page:2", affected_chunks=["C0001"])
        self.assertEqual(len(self.open().status()["unresolved_obligations"]), 1)

    def test_stale_pending_file_is_discarded_not_salvaged(self):
        self.open().close()
        temp = self.directory / (".pending-" + "a" * 32)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, b'{"payload":')
        os.close(fd)
        self.assertFalse(self.open().status()["all_retrieved_text_processed"])
        self.assertFalse(temp.exists())

    def test_checksum_schema_duplicate_keys_and_truncated_json_fail_closed(self):
        for n, variant in enumerate(("checksum", "extra", "bool_revision", "duplicate", "truncated")):
            directory = self.base / f"corrupt-{n}"
            self.open(directory=directory).close()
            path = directory / "ledger.json"
            wrapper = json.loads(path.read_text())
            if variant == "checksum": wrapper["payload"]["revision"] += 1
            if variant == "extra":
                wrapper["payload"]["raw_model_output"] = "SECRET"
                wrapper["sha256"] = ledger._digest(wrapper["payload"])
            if variant == "bool_revision":
                wrapper["payload"]["revision"] = True
                wrapper["sha256"] = ledger._digest(wrapper["payload"])
            if variant == "duplicate": path.write_text('{"payload":{},"payload":{},"sha256":""}')
            elif variant == "truncated": path.write_text('{"payload":')
            else: path.write_text(json.dumps(wrapper))
            with self.subTest(variant=variant), self.assertRaises(ledger.LedgerError): self.open(directory=directory)

    def test_tampered_claim_anchor_even_with_recomputed_checksum_is_rejected(self):
        handle = self.open()
        self.checked(handle)
        handle.close()
        self.mutate_file(lambda state: state["checkpoints"][0]["claims"][0].update(anchor_sha256="0" * 64))
        with self.assertRaisesRegex(ledger.LedgerError, "invalid_checked_claims"): self.open()

    def test_two_open_handles_do_not_merge_stale_state(self):
        first = self.open()
        second = self.open()
        first.add_obligation(self.source, kind="later_limitation", origin_location="page:2", affected_chunks=["C0001"])
        with self.assertRaisesRegex(ledger.LedgerError, "ledger_concurrent_update"):
            second.add_obligation(self.source, kind="contradiction", origin_location="page:1", affected_chunks=["C0001"])
        self.assertEqual(len(self.open().status()["unresolved_obligations"]), 1)

    def test_separate_process_lock_fails_closed_without_writes(self):
        handle = self.open()
        ctx = multiprocessing.get_context("fork")
        ready, release = ctx.Event(), ctx.Event()
        worker = ctx.Process(target=hold_lock, args=(str(self.directory), ready, release))
        worker.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaisesRegex(ledger.LedgerError, "ledger_busy"):
                handle.add_obligation(self.source, kind="later_limitation", origin_location="page:2", affected_chunks=["C0001"])
        finally:
            release.set()
            worker.join(5)
        self.assertEqual(worker.exitcode, 0)
        self.assertEqual(self.open().status()["unresolved_obligations"], [])

    def test_cross_section_scaffold_requires_all_units_and_explicit_obligations(self):
        source = context(blank=True)
        handle = self.open(source)
        ident = handle.add_obligation(source, kind="later_limitation", origin_location="page:3", affected_chunks=["C0001"])
        with self.assertRaisesRegex(ledger.LedgerError, "retrieved_text_processing_pending"):
            handle.examine_unit(source, "page:1", caveats_checked=True, contradictions_checked=True)
        self.checked(handle, source)
        with self.assertRaisesRegex(ledger.LedgerError, "cross_section_obligations_pending"):
            handle.attest_cross_section_review(source)
        for location in ("page:1", "page:2", "page:3"):
            handle.examine_unit(source, location, caveats_checked=True, contradictions_checked=True)
        with self.assertRaisesRegex(ledger.LedgerError, "cross_section_obligations_pending"):
            handle.attest_cross_section_review(source)
        with self.assertRaisesRegex(ledger.LedgerError, "invalid_obligation_resolution"):
            handle.resolve_obligation(source, ident, resolution="claims_require_revision")
        handle.resolve_obligation(source, ident, resolution="qualified_in_private_review")
        self.assertEqual(handle.status()["cross_section_review"], "pending")
        handle.attest_cross_section_review(source)
        self.assertEqual(handle.status()["cross_section_review"], "attested_not_verified")
        self.assertEqual(handle.status()["independent_review"], "pending")
        self.assertEqual(handle.status()["semantic_completeness"], "not_verified")
        handle.add_obligation(source, kind="contradiction", origin_location="page:3", affected_chunks=["C0001"])
        self.assertEqual(handle.status()["cross_section_review"], "pending")
        self.assertEqual(len(handle.status()["unresolved_obligations"]), 1)

    def test_partial_unit_attestation_is_not_accepted(self):
        handle = self.open()
        self.checked(handle)
        with self.assertRaisesRegex(ledger.LedgerError, "unit_review_incomplete"):
            handle.examine_unit(self.source, "page:1", caveats_checked=True, contradictions_checked=False)
        self.assertIn("page:1", handle.status()["unexamined_units"])

    def test_real_reader_contract_with_static_responses_uses_all_existing_gates(self):
        source = context(two=False)
        handle = self.open(source)
        class StaticModel:
            def __init__(self, verdict):
                self.responses = [
                    {"claims": [{"field": "limitations", "text": PARAPHRASE,
                                 "source_span": "C0001:S001"}], "no_claim_reason": ""}, verdict]
                self.calls = 0
            def create_chat_completion(self, **kwargs):
                self.calls += 1
                return {"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(self.responses.pop(0))}}]}
        model = StaticModel({"supported": [0], "rejected": []})
        accepted = handle.run_chunk(source, "C0001", model=model, title="Synthetic")
        self.assertEqual(model.calls, 2)
        self.assertEqual(accepted[0]["text"], PARAPHRASE)
        rejected = self.open(source, self.base / "rejected-verdict")
        model = StaticModel({"supported": [], "rejected": [0]})
        with self.assertRaisesRegex(ledger.LedgerError, "claim_verification_failed"):
            rejected.run_chunk(source, "C0001", model=model, title="Synthetic")
        self.assertEqual(model.calls, 2)
        self.assertEqual(rejected.status()["per_chunk_machine_checks"][0]["claim_count"], 0)

    def test_missing_committed_state_is_not_silently_reinitialized(self):
        self.open().close()
        (self.directory / "ledger.json").unlink()
        with self.assertRaisesRegex(ledger.LedgerError, "ledger_state_missing"):
            self.open()

    def test_literal_quotation_inside_paraphrase_is_not_saved(self):
        source = context(two=False)
        handle = self.open(source)
        text = 'This interpretation repeats "The classroom comparison included 47 learners" without appropriate original synthesis.'
        with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
            self.checked(handle, source, [valid_claim(source.chunks[0], text)])
        self.assertNotIn(text, (self.directory / "ledger.json").read_text())

    def test_status_contains_no_claim_prose_and_stale_reads_fail_closed(self):
        first = self.open()
        self.checked(first)
        second = self.open()
        self.assertNotIn(PARAPHRASE, json.dumps(first.status()))
        second.add_obligation(self.source, kind="later_limitation", origin_location="page:2", affected_chunks=["C0001"])
        with self.assertRaisesRegex(ledger.LedgerError, "ledger_concurrent_update"):
            first.status()
        with self.assertRaisesRegex(ledger.LedgerError, "ledger_concurrent_update"):
            first.claims_for("C0001")

    def test_malformed_context_types_and_binding_bool_coercion_fail_closed(self):
        for changed in (replace(self.source, kind=[]), replace(self.source, provider={}),
                        replace(self.source, license_code=[])):
            with self.assertRaisesRegex(ledger.LedgerError, "invalid_source_context"):
                self.open(changed)
        self.open().close()
        self.mutate_file(lambda state: state["binding"]["units"][0].update(characters=True))
        with self.assertRaisesRegex(ledger.LedgerError, "source_binding_mismatch"):
            self.open()

    def test_actual_git_head_marker_and_lock_symlink_are_rejected(self):
        repo = self.base / "actual-repo"
        (repo / ".git").mkdir(parents=True)
        (repo / ".git" / "HEAD").write_text("ref: refs/heads/main")
        with self.assertRaisesRegex(ledger.LedgerError, "repository_path_forbidden"):
            self.open(directory=repo / "private")
        self.directory.mkdir(parents=True, mode=0o700)
        (self.directory / ".lock").symlink_to(self.base / "do-not-create")
        with self.assertRaises(ledger.LedgerError): self.open()
        self.assertFalse((self.base / "do-not-create").exists())

    def test_interrupted_later_chunk_preserves_prior_completed_work(self):
        source = context(limit=350)
        handle = self.open(source)
        with patch.object(reading, "read_chunk", side_effect=lambda model, chunk, kind, title, deadline=None: [valid_claim(chunk)]):
            handle.run_chunk(source, "C0001", model=None, title="Synthetic")
        with patch.object(reading, "read_chunk", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                handle.run_chunk(source, "C0002", model=None, title="Synthetic")
        resumed = self.open(source)
        self.assertEqual(resumed.claims_for("C0001")[0]["text"], PARAPHRASE)
        self.assertEqual(resumed.status()["per_chunk_machine_checks"][1]["state"], "interrupted")
        self.assertFalse(resumed.status()["all_retrieved_text_processed"])
        self.assertEqual(resumed.status()["cross_section_review"], "pending")

    def test_punctuation_only_and_unicode_width_source_copies_are_rejected(self):
        source = context(two=False)
        examples = ["The classroom comparison included 47 learners.",
            "The classroom comparison included 47 learners, who completed an assisted exercise.",
            "Ｔｈｅ ｃｌａｓｓｒｏｏｍ ｃｏｍｐａｒｉｓｏｎ ｉｎｃｌｕｄｅｄ 47 ｌｅａｒｎｅｒｓ."]
        for i, text in enumerate(examples):
            handle = self.open(source, self.base / f"punctuation-{i}")
            with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
                self.checked(handle, source, [valid_claim(source.chunks[0], text)])
            self.assertEqual(handle.status()["per_chunk_machine_checks"][0]["claim_count"], 0)
            self.assertNotIn(text, (handle.directory / "ledger.json").read_text())

    def test_resume_revalidates_punctuation_only_source_copy(self):
        handle = self.open()
        self.checked(handle)
        handle.close()
        text = "The classroom comparison included 47 learners."
        self.mutate_file(lambda state: state["checkpoints"][0]["claims"][0].update(
            text=text, claim_sha256=ledger._hash(text)))
        with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
            self.open()

    def test_all_url_schemes_and_userinfo_are_rejected(self):
        source = context(two=False)
        examples = ["ftp://alice:private-pass@example.org/report", "//alice:private-pass@example.org/report",
            "sftp://alice:private-pass@example.org/report", "alice:private-pass@example.org",
            "ｆｔｐ：／／alice:private-pass@example.org/report"]
        for i, url in enumerate(examples):
            text = "Supporting material lives at " + url + " for a separate private examination."
            handle = self.open(source, self.base / f"userinfo-{i}")
            with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
                self.checked(handle, source, [valid_claim(source.chunks[0], text)])
            self.assertNotIn("private-pass", (handle.directory / "ledger.json").read_text())

    def test_unicode_literal_quotes_and_format_character_secrets_are_rejected(self):
        source = context(two=False)
        examples = ["This evidence repeats «learners who completed an assisted exercise» during a narrow review.",
            "This evidence repeats ❝learners who completed an assisted exercise❞ during a narrow review.",
            "This evidence repeats 「learners who completed an assisted exercise」 during a narrow review.",
            "Researchers disclosed the pass\u200bword private-pass while describing their study methods."]
        for i, text in enumerate(examples):
            handle = self.open(source, self.base / f"unicode-privacy-{i}")
            with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
                self.checked(handle, source, [valid_claim(source.chunks[0], text)])

    def test_repeated_anchor_spans_fail_closed_instead_of_inventing_location(self):
        repeated = "The findings describe bounded classroom observations without proving persistent independent transfer or broad changes in attention."
        doc = Document([{"location": "page:1", "text": repeated + " " + repeated}],
                       "https://example.org/source", "v1")
        source = ledger.SourceContext(doc, reading.chunk_document(doc), "repeated-anchor-record", POLICY)
        handle = self.open(source)
        with self.assertRaisesRegex(ledger.LedgerError, "ambiguous_claim_anchor"):
            self.checked(handle, source, [valid_claim(source.chunks[0])])
        self.assertEqual(handle.status()["per_chunk_machine_checks"][0]["error"], "ambiguous_claim_anchor")
        self.assertNotIn(PARAPHRASE, (self.directory / "ledger.json").read_text())

    def test_fragment_wrappers_cannot_reconstruct_source_or_dilute_with_appendix(self):
        for i, appendix in enumerate(("", " Unrelated supplementary context has no bearing on the reported comparison." * 20)):
            doc = Document([{"location": "page:1", "text": TEXT + appendix}], "https://example.org/source", "v1")
            source = ledger.SourceContext(doc, reading.chunk_document(doc), "fragment-record", POLICY)
            handle = self.open(source, self.base / f"fragments-{i}")
            words = TEXT.split()
            claims = [valid_claim(source.chunks[0], "The account explains " + " ".join(words[n:n+11]) + ".")
                for n in range(0, len(words), 11) if len(words[n:n+11]) >= 6]
            with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
                self.checked(handle, source, claims)
            self.assertEqual(handle.status()["per_chunk_machine_checks"][0]["claim_count"], 0)

    def test_source_union_catches_short_fragments_that_pass_individual_thresholds(self):
        source = context(two=False)
        words = TEXT.split()
        texts = ["Our cautious provisional interpretation of this record describes " +
            " ".join(words[n:n+4]) + " without establishing any wider significance."
            for n in range(0, 16, 4)]
        # Four-token fragments alone are below individual copying thresholds.
        for text in texts:
            ledger._check_fragment_copy([text], TEXT)
        with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
            ledger._check_fragment_copy(texts, TEXT)
        handle = self.open(source)
        with self.assertRaisesRegex(ledger.LedgerError, "privacy_check_failed"):
            self.checked(handle, source, [valid_claim(source.chunks[0], text) for text in texts])
        self.assertEqual(handle.status()["per_chunk_machine_checks"][0]["claim_count"], 0)

    def test_returned_data_cannot_mutate_internal_state(self):
        handle = self.open()
        self.checked(handle)
        saved = handle.claims_for("C0001")
        saved[0]["text"] = "changed"
        handle.status()["per_chunk_machine_checks"].clear()
        self.assertEqual(handle.claims_for("C0001")[0]["text"], PARAPHRASE)


if __name__ == "__main__":
    unittest.main()
