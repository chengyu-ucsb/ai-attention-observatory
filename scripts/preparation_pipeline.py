"""Bounded rolling/closeout orchestration and honest offline readiness checks.

A final-reading receipt proves which local stages ran against which inputs, not
that every source was available, that a model succeeded, or that anyone approved
its analysis. Publication keeps the established abstract-backed evidence gates.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from weekly_preparation import (atomic_save, closed_packet, target_window, utc,
                                validate_packet)

ROOT = Path(__file__).resolve().parents[1]
NOTE = ("Bounded source acquisition and machine checking are not independent or expert "
        "approval. Missing, partial, deferred and failed readings remain gaps. "
        "The edition may use explicitly labelled substantive abstracts under its existing evidence policy.")


def read(path):
    from academic_state_schema import strict_json_loads
    return strict_json_loads(Path(path).read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def folder_for(root, now, phase):
    return Path(root) / "data/weekly-preparation" / target_window(now, phase)["from"]


def check_scope(expected_week, now, phase):
    """A prior step may cross Monday; never use its old week as a clock override."""
    if expected_week is not None and expected_week != target_window(now, phase)["from"]:
        raise ValueError("preparation_scope_changed_before_work")


def run_preparation(root=ROOT, now=None, expected_week=None, **budgets):
    from weekly_preparation import prepare
    now = utc(now)
    check_scope(expected_week, now, "preparing")
    packet = prepare(root, now=now, **budgets)
    return {"week": packet["target_publication_window"]["from"], "phase": packet["phase"],
            "status": packet["status"], "approved": False}


def closeout_plan(root=ROOT, now=None):
    """One initial and one late-index generation, then resume without reset."""
    now = utc(now)
    path = folder_for(root, now, "closed") / "packet.json"
    window = target_window(now, "closed")
    result = {"needed": True, "collect_needed": True, "week": window["from"], "closeout_pass": "initial"}
    if not path.exists():
        return dict(result, status="initial_closeout_required")
    packet = read(path)
    validate_packet(packet, packet["observation_at"])
    if packet["target_publication_window"] != window or utc(packet["observation_at"]) > now:
        raise ValueError("invalid_closeout_namespace")
    if packet["phase"] != "closed":
        return dict(result, status="initial_closeout_required")
    closed_packet(packet, now)
    coverage = packet["coverage"]
    passes = coverage.get("closeout_passes") or {}
    if "initial" not in passes:
        raise ValueError("initial_closeout_evidence_missing")
    closing = dt.datetime.combine(dt.date.fromisoformat(window["to"]) + dt.timedelta(days=1),
                                  dt.time(), dt.timezone.utc)
    # A quota-blocked initial generation must not prevent the one later sweep.
    # Its unfinished queries/history stay intact in their own durable namespace.
    if "late_index" not in passes and now >= closing + dt.timedelta(hours=6):
        return dict(result, closeout_pass="late_index", status="late_index_required")
    result["closeout_pass"] = "late_index" if "late_index" in passes else "initial"
    feeds = coverage.get("publisher_snapshots", {}).get("sources", [])
    complete = (coverage.get("configured_query_status") == "complete_for_configured_queries"
                and all(row.get("status") == "ok" for row in feeds)
                and not coverage.get("errors"))
    weekly_path = Path(root) / "data/weekly.json"
    weekly = read(weekly_path) if weekly_path.exists() else {}
    run = weekly.get("run", {})
    adoption_needed = (any(run.get("publication_window", {}).get(k) != window[k] for k in ("from", "to", "timezone"))
                       or run.get("preparation_observation_at") != packet["observation_at"])
    return dict(result, needed=not complete or adoption_needed, collect_needed=not complete,
                adoption_needed=adoption_needed,
                status=("resume_partial_closeout" if not complete else
                        "canonical_adoption_required" if adoption_needed else "configured_pass_complete"))


def run_closeout(root=ROOT, now=None, expected_week=None, **budgets):
    from weekly_preparation import prepare, adopt_to_canonical
    now = utc(now)
    check_scope(expected_week, now, "closed")
    plan = closeout_plan(root, now)
    # Re-adoption is safe and repairs an interrupted multi-file local commit.
    packet = (prepare(root, now=now, closeout=True, closeout_pass=plan["closeout_pass"], **budgets)
              if plan["collect_needed"] else read(folder_for(root, now, "closed") / "packet.json"))
    adopt_to_canonical(root, packet, now)
    return dict(plan, metadata_status=packet["status"], approved=False)


def reading_plan(root=ROOT, now=None, phase="closed"):
    now = utc(now)
    folder = folder_for(root, now, phase)
    result = {"ready": False, "week": folder.name, "phase": phase}
    if not (folder / "packet.json").exists():
        return dict(result, status="awaiting_preparation")
    packet = read(folder / "packet.json")
    validate_packet(packet, now)
    if packet["phase"] != phase:
        return dict(result, status="awaiting_closeout")
    if phase == "closed":
        closed_packet(packet, now)
        if "late_index" not in packet["coverage"].get("closeout_passes", {}):
            return dict(result, status="awaiting_late_index_closeout")
        weekly = read(Path(root) / "data/weekly.json")
        import collect_weekly_sources as queue
        if queue.validate_window(weekly, now) != packet["target_publication_window"]:
            return dict(result, status="awaiting_canonical_adoption")
    return dict(result, ready=True, status="ready_with_explicit_coverage_gaps")


# Version 1 bound the complete historical library. Version 2 binds every field
# of the target week's canonical candidates and their identity dependencies.
# It deliberately does not reinterpret or migrate an existing execution receipt.
CANONICAL_BINDING_VERSION = 2
CANONICAL_POLICY_INPUTS = ("editorial-corrections.json", "editorial-source-readings.json",
    "original-readings.json", "source-lineage.json", "venue-standards.json", "fulltext-source-hints.json")


def scoped_library_inputs(root, packet, weekly, library):
    """Conservative publication-week dependency set, not a public-quality filter.

    Include dated candidates even when withdrawn, unapproved or unverified;
    filtering on current eligibility would hide the very changes we must hold.
    Packet/weekly identity matches also retain records with corrected dates.
    All fields (including source URLs, versions, licenses and cooldowns) remain
    bound. Policy/approval registries are exact inputs, never cached projections.
    """
    import collect_weekly_sources as queue
    from collection_window import date_in_window
    from source_lineage import canonical_url, prepare as apply_lineage
    from editorial_corrections import apply as apply_corrections
    window = packet["target_publication_window"]
    if type(library) is not list or any(type(record) is not dict for record in library):
        raise ValueError("invalid_canonical_library")
    keys = [queue.record_key(record) for record in library]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate_library_publication_identity")

    def identities(record):
        # Match the DOI and URL identity conventions used by acquisition and
        # public lineage, including aliases which could otherwise shadow a row.
        values = {"key:" + queue.record_key(record)}
        for field in ("doi", "companion_to"):
            doi = queue.access.doi(record.get(field))
            if doi:
                values.add("doi:" + doi)
        for field in ("url", "id"):
            value = record.get(field)
            if value:
                values.add(field + ":" + str(value))
        url = canonical_url(record.get("url"))
        if url:
            values.add("canonical_url:" + url)
        return values

    policy = {}
    configs = {}
    for name in CANONICAL_POLICY_INPUTS:
        path = Path(root) / "data" / name
        value = read(path) if path.exists() else None
        if path.exists() and type(value) is not dict:
            raise ValueError("invalid_canonical_policy_input:" + name)
        configs[name] = value
        policy[name] = digest(value)
    # Use the real pure local correction/lineage functions for selection only.
    # Keep the raw full records in the digest. A historical raw URL/date may be
    # corrected into this week, and must not escape the dependency closure.
    projected = apply_lineage(apply_corrections(deepcopy(library),
        configs["editorial-corrections.json"] or {}), configs["source-lineage.json"] or {})
    wanted = set()
    for record in packet["items"] + weekly["items"]:
        wanted.update(identities(record))
    selected = set()
    aliases = [identities(record) | identities(projected[index])
               for index, record in enumerate(library)]
    for index, record in enumerate(library):
        if (any(date_in_window(row.get("published"), window["from"], window["to"])
                for row in (record, projected[index]))
                or not (record.get("doi") or record.get("url") or record.get("id"))):
            selected.add(index)
            wanted.update(aliases[index])
    for record in projected[len(library):]:
        if date_in_window(record.get("published"), window["from"], window["to"]):
            wanted.update(identities(record))
    # A relationship can point at another library record; retain the complete
    # connected identity set rather than assuming every row is independent.
    while True:
        added = {index for index, values in enumerate(aliases)
                 if index not in selected and values & wanted}
        if not added:
            break
        selected.update(added)
        for index in added:
            wanted.update(aliases[index])
    return {"binding_policy_version": CANONICAL_BINDING_VERSION,
            "publication_window": window,
            "records": [record for index, record in enumerate(library) if index in selected],
            "policy_inputs": policy}


def bindings(root, folder, *, canonical=False, binding_policy_version=CANONICAL_BINDING_VERSION):
    values = {name: read(folder / name) for name in ("packet.json", "acquisition.json", "readings.json")}
    if canonical:
        values.update({name: read(Path(root) / "data" / name) for name in ("library.json", "weekly.json")})
        if binding_policy_version == CANONICAL_BINDING_VERSION:
            values["library.json"] = scoped_library_inputs(root, values["packet.json"],
                values["weekly.json"], values["library.json"])
        elif binding_policy_version != 1:
            raise ValueError("invalid_canonical_binding_policy_version")
    return {name: digest(value) for name, value in values.items()}


class ReadingInputsChanged(ValueError):
    """Independently valid snapshots no longer describe the same input set."""

    def __init__(self, changed_inputs):
        super().__init__("reading_inputs_changed")
        self.changed_inputs = changed_inputs


def validate_reading_inputs(folder, now, *, allow_missing=False):
    import collect_weekly_sources as queue
    from prepared_article_readings import validate_bundle
    packet = read(folder / "packet.json")
    window = validate_packet(packet, now)
    missing = set()
    def load(name):
        path = folder / name
        if allow_missing and not path.exists():
            missing.add(name)
            return None
        return read(path)
    state, bundle = load("acquisition.json"), load("readings.json")
    if "acquisition.json" not in missing:
        queue.validate_state(state)
        if state["publication_window"] != window:
            raise ValueError("reading_acquisition_window_mismatch")
    if "readings.json" not in missing:
        validate_bundle(bundle, window, now=now)
    if state is None or bundle is None:
        return packet, state, bundle
    changed = []
    if bundle["packet_sha256"] != queue.digest(packet):
        changed.append("packet.json")
    if bundle["acquisition_state_sha256"] != state["state_sha256"]:
        changed.append("acquisition.json")
    if changed:
        raise ReadingInputsChanged(changed)
    return packet, state, bundle


def validate_counts(values):
    import collect_weekly_sources as queue
    queue.require(type(values) is dict)
    for key, count in values.items():
        queue.require(type(key) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,100}", key))
        queue.integer(count)


READING_POLICY_VERSION = 2


def validate_stage_report(stage, report):
    import collect_weekly_sources as queue
    if stage == "acquire":
        counts = {"selected_records", "attempted_records", "attempted_stages", "completed_records",
                  "pending_records", "deferred_retry_records", "duplicate_records", "limit",
                  "max_candidates_per_provider_stage"}
        queue.shape(report, counts | {"checked_at", "statuses", "excluded", "stop_reason", "known_sources_only",
            "time_budget_seconds", "item_time_budget_seconds", "active_provider_pauses", "scope",
            "model_used", "publication_or_review_performed"})
        for key in counts:
            queue.integer(report[key])
        queue.timestamp(report["checked_at"])
        validate_counts(report["statuses"]); validate_counts(report["excluded"])
        queue.validate_pauses(report["active_provider_pauses"])
        queue.require(type(report["known_sources_only"]) is bool and report["scope"] == queue.SCOPE
                      and report["model_used"] is False and report["publication_or_review_performed"] is False
                      and report["stop_reason"] in {"queue_checked", "record_limit", "time_budget"})
        for key in ("time_budget_seconds", "item_time_budget_seconds"):
            queue.require(type(report[key]) in (int, float) and 0 < report[key] <= 86400)
    elif stage == "review":
        counts = {"attempted", "summaries_completed", "failed"}
        queue.shape(report, counts | {"skipped_no_model"},
                    {"documents_retrieved", "partial_inputs", "failure_reasons", "failure_stages", "source_text_saved", "selection"})
        for key in counts | ({"documents_retrieved", "partial_inputs"} & set(report)):
            queue.integer(report[key])
        queue.require(report["skipped_no_model"] is False
                      and report["attempted"] == report["summaries_completed"] + report["failed"])
        for key in ("failure_reasons", "failure_stages"):
            if key in report:
                validate_counts(report[key])
        if 'selection' in report:
            validate_selection(report['selection'], report['attempted'])
    else:
        count = "attempted" if stage == "revalidate" else "machine_checked_readings_applied"
        queue.shape(report, {count, "approved"}, {"source_text_saved", "publication_window"})
        queue.integer(report[count])
        queue.require(report["approved"] is False)
        if "publication_window" in report:
            queue.saved_window(report["publication_window"])
    queue.require(report.get("source_text_saved", False) is False)


def validate_selection(value, attempted):
    import collect_weekly_sources as queue
    queue.shape(value, {'considered', 'eligible', 'deferred_by_limit', 'skipped'})
    for key in ('considered', 'eligible', 'deferred_by_limit'):
        queue.integer(value[key])
    queue.require(type(value['skipped']) is dict and not set(value['skipped']) - {
        'unsupported_kind', 'already_editorially_reviewed', 'complete_machine_reading',
        'retry_cooldown', 'unverified_venue', 'off_topic', 'no_explicit_human_topic'})
    validate_counts(value['skipped'])
    queue.require(value['considered'] == value['eligible'] + sum(value['skipped'].values())
                  and value['eligible'] == attempted + value['deferred_by_limit'])


def validate_coverage(coverage):
    import collect_weekly_sources as queue
    counts = {"eligible_metadata", "eligible_canonical_records", "quarantined_metadata", "acquisition_records",
        "full_documents_acquired", "partial_documents_acquired", "machine_checked_full_readings",
        "machine_checked_partial_readings", "full_readings_source_revalidated", "readings_held_at_revalidation",
        "separately_accepted_original_readings", "independent_approvals_granted_by_pipeline",
        "review_attempted_this_run", "review_completed_this_run", "review_failed_this_run",
        "machine_checked_readings_applied_this_run"}
    queue.shape(coverage, counts | {"metadata_status", "configured_query_status",
                "expert_review_verified_by_pipeline", "acquisition_statuses", "note"})
    for key in counts:
        queue.integer(coverage[key])
    validate_counts(coverage["acquisition_statuses"])
    queue.require(coverage["independent_approvals_granted_by_pipeline"] == 0
                  and coverage["expert_review_verified_by_pipeline"] is False and coverage["note"] == NOTE
                  and coverage["metadata_status"] in {"prepared", "partial"}
                  and coverage["configured_query_status"] in {None, "partial", "complete_for_configured_queries"})


def validate_reading_receipt(value, kind, now):
    """Corrupt receipts are errors, not a request to retry provider/model work.

    This checks the receipt itself. An otherwise valid receipt for older inputs
    is stale, and the readiness check must hold it without claiming completion.
    """
    import collect_weekly_sources as queue
    common = {"schema_version", "kind", "publication_window", "bindings", "approved", "source_text_saved"}
    run = kind == "preparation_reading_run"
    required = common | ({"phase", "started_at", "finished_at", "stages", "note"} if run else
                         {"completed_at", "reading_run_sha256", "status", "coverage"})
    names = {"packet.json", "acquisition.json", "readings.json"}
    if not run:
        names |= {"library.json", "weekly.json"}
    try:
        queue.shape(value, required, {'reading_policy_version'} if run else {'binding_policy_version'})
        if 'binding_policy_version' in value:
            queue.require(type(value['binding_policy_version']) is int
                          and 1 <= value['binding_policy_version'] <= CANONICAL_BINDING_VERSION)
        if 'reading_policy_version' in value:
            queue.require(type(value['reading_policy_version']) is int
                          and 1 <= value['reading_policy_version'] <= READING_POLICY_VERSION)
        queue.require(type(value["schema_version"]) is int and value["schema_version"] == 1
                      and value["kind"] == kind and value["approved"] is False
                      and value["source_text_saved"] is False)
        queue.saved_window(value["publication_window"])
        queue.shape(value["bindings"], names)
        for bound in value["bindings"].values():
            queue.hash_value(bound)
        for field in (("started_at", "finished_at") if run else ("completed_at",)):
            queue.timestamp(value[field])
            queue.require(utc(value[field]) <= now)
        if run:
            queue.require(value["phase"] in {"preparing", "closed"} and value["note"] == NOTE
                          and utc(value["started_at"]) <= utc(value["finished_at"]))
            if value.get('reading_policy_version', 1) >= 2:
                queue.require('selection' in value['stages']['review'])
            stages = {"acquire", "review"} | ({"revalidate", "apply"} if value["phase"] == "closed" else set())
            queue.shape(value["stages"], stages)
            for stage, report in value["stages"].items():
                validate_stage_report(stage, report)
            queue.require(utc(value["started_at"]) <= utc(value["stages"]["acquire"]["checked_at"])
                          <= utc(value["finished_at"]))
            if "apply" in stages and "publication_window" in value["stages"]["apply"]:
                queue.require(value["stages"]["apply"]["publication_window"] == value["publication_window"])
        else:
            queue.hash_value(value["reading_run_sha256"])
            queue.require(value["status"] in {"bounded_stage_completed", "completed_with_review_failures"}
                          and type(value["coverage"]) is dict)
            validate_coverage(value["coverage"])
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError("invalid_" + kind + "_receipt") from None
    return value


def current_reading_run(run, packet, current_bindings, now):
    return (run.get("reading_policy_version", 1) == READING_POLICY_VERSION
            and run["phase"] == "closed" and run["publication_window"] == packet["target_publication_window"]
            and run["bindings"] == {key: current_bindings[key] for key in run["bindings"]}
            and utc(packet["observation_at"]) <= utc(run["started_at"]) <= utc(run["finished_at"]) <= now)


def run_readings(root=ROOT, now=None, phase="closed", runner=None, expected_week=None):
    """Execute real CLI stages; a zero exit with a skipped-model report is held."""
    now = utc(now)
    check_scope(expected_week, now, phase)
    plan = reading_plan(root, now, phase)
    if not plan["ready"]:
        raise ValueError(plan["status"])
    folder = folder_for(root, now, phase)
    runner = runner or subprocess.run
    stages = [("acquire", 12), ("review", 2)]
    if phase == "closed":
        stages += [("revalidate", 12), ("apply", 2)]
    reports = {}
    for stage, limit in stages:
        result = runner([sys.executable, str(Path(root) / "scripts/prepared_article_readings.py"),
                         stage, "--week", plan["week"], "--limit", str(limit)],
                        cwd=root, check=True, capture_output=True, text=True)
        # Each CLI ends with a bounded metadata report; model logs are not receipts.
        report = json.loads(result.stdout.strip().splitlines()[-1])
        if (not isinstance(report, dict) or report.get("status") in {
                "model_unavailable", "awaiting_acquisition", "awaiting_prepared_readings"}
                or report.get("skipped_no_model") is True):
            raise ValueError("reading_stage_not_executed:" + stage)
        if stage == "review" and not all(type(report.get(k)) is int and report[k] >= 0
                                          for k in ("attempted", "summaries_completed", "failed")):
            raise ValueError("missing_review_outcome")
        reports[stage] = report
    finished = utc()  # A CLI cannot backdate its observed completion.
    validate_reading_inputs(folder, finished)
    receipt = {"schema_version": 1, "kind": "preparation_reading_run", "phase": phase,
        "reading_policy_version": READING_POLICY_VERSION,
        "started_at": now.isoformat(), "finished_at": finished.isoformat(),
        "publication_window": target_window(now, phase), "bindings": bindings(root, folder),
        "stages": reports, "approved": False, "source_text_saved": False, "note": NOTE}
    validate_reading_receipt(receipt, "preparation_reading_run", finished)
    atomic_save(folder / "reading-run.json", receipt)
    return receipt


def coverage_report(packet, state, bundle, library):
    from original_readings import weekly_source_eligible
    from collection_window import weekly_eligible
    window = packet["target_publication_window"]
    current = [r for r in library if weekly_eligible(r, window["from"], window["to"])]
    documents = [r.get("document") or {} for r in state["records"].values()]
    analyses = [r["record"].get("deep_analysis") or {} for r in bundle["records"].values()]
    partial_analyses = [r["record"].get("partial_reading_candidate") or r["record"].get("deep_analysis") or {}
                        for r in bundle["records"].values()]
    return {"eligible_metadata": len(packet["items"]), "eligible_canonical_records": len(current), "quarantined_metadata": len(packet["quarantine"]),
        "metadata_status": packet["status"], "configured_query_status": packet["coverage"].get("configured_query_status"),
        "acquisition_records": len(state["records"]),
        "full_documents_acquired": sum(d.get("evidence_status") == "full_document_retrieved" for d in documents),
        "partial_documents_acquired": sum(d.get("evidence_status") == "partial_full_text" for d in documents),
        "machine_checked_full_readings": sum(a.get("review_status") == "machine_checked_not_independently_reviewed"
            and a.get("coverage", {}).get("evidence_status") == "full_document_retrieved" for a in analyses),
        "machine_checked_partial_readings": sum(a.get("review_status") == "machine_checked_not_independently_reviewed"
            and a.get("coverage", {}).get("evidence_status") == "partial_full_text" for a in partial_analyses),
        "full_readings_source_revalidated": sum(r.get("revalidation", {}).get("status") == "source_revalidated"
            for r in bundle["records"].values()),
        "readings_held_at_revalidation": sum(r.get("revalidation", {}).get("status") == "held"
            for r in bundle["records"].values()),
        "separately_accepted_original_readings": sum(weekly_source_eligible(r) for r in current),
        "independent_approvals_granted_by_pipeline": 0, "expert_review_verified_by_pipeline": False,
        "acquisition_statuses": state.get("run", {}).get("statuses", {}), "note": NOTE}


def final_coverage(packet, state, bundle, library, run):
    coverage = coverage_report(packet, state, bundle, library)
    review = run["stages"]["review"]
    coverage["review_attempted_this_run"] = review["attempted"]
    coverage["review_completed_this_run"] = review["summaries_completed"]
    coverage["review_failed_this_run"] = review["failed"]
    coverage["machine_checked_readings_applied_this_run"] = run["stages"]["apply"]["machine_checked_readings_applied"]
    return coverage


def finalize(root=ROOT, now=None, expected_week=None):
    now = utc(now)
    check_scope(expected_week, now, "closed")
    plan = reading_plan(root, now)
    if not plan["ready"]:
        raise ValueError(plan["status"])
    folder = folder_for(root, now, "closed")
    packet, state, bundle = validate_reading_inputs(folder, now)
    run = validate_reading_receipt(read(folder / "reading-run.json"), "preparation_reading_run", now)
    current = bindings(root, folder, canonical=True)
    if not current_reading_run(run, packet, current, now):
        raise ValueError("current_final_reading_run_required")
    previous_path = folder / "final-reading.json"
    if previous_path.exists():
        previous = validate_reading_receipt(read(previous_path), "weekly_final_reading", now)
        # Never upgrade/rebind the same completed execution, including a legacy
        # receipt. Only a real new bounded reading run may create a new receipt.
        if previous["reading_run_sha256"] == digest(run):
            if not edition_ready(root, now)["ready"]:
                raise ValueError("current_final_reading_run_required")
            return previous
    coverage = final_coverage(packet, state, bundle, read(Path(root) / "data/library.json"), run)
    review = run["stages"]["review"]
    receipt = {"schema_version": 1, "kind": "weekly_final_reading", "completed_at": now.isoformat(),
        "binding_policy_version": CANONICAL_BINDING_VERSION,
        "publication_window": packet["target_publication_window"], "bindings": current,
        "reading_run_sha256": digest(run), "approved": False, "source_text_saved": False,
        "status": "completed_with_review_failures" if review["failed"] else "bounded_stage_completed",
        "coverage": coverage}
    validate_reading_receipt(receipt, "weekly_final_reading", now)
    atomic_save(folder / "final-reading.json", receipt)
    return receipt


def edition_ready(root=ROOT, now=None, *, reconcile_legacy=False):
    """Read-only gate: changed reading inputs need real work, never reblessing.

    The finalizer uses ready=false to enter its existing bounded reading stages;
    the edition uses it to skip publication. Explicit legacy reconciliation
    can prove only a narrow canonical no-op from exact local Git evidence.
    Schema, checksum, date and namespace errors
    still fail closed rather than starting work on corrupt evidence.
    """
    now = utc(now)
    result = reading_plan(root, now)
    if not result["ready"]:
        return result
    folder = folder_for(root, now, "closed")
    result["ready"] = False
    receipts = {}
    for name, kind in (("final-reading.json", "weekly_final_reading"),
                       ("reading-run.json", "preparation_reading_run")):
        if (folder / name).exists():
            receipts[name] = validate_reading_receipt(read(folder / name), kind, now)
    changed = None
    try:
        packet, state, bundle = validate_reading_inputs(folder, now, allow_missing=True)
    except ReadingInputsChanged as exc:
        changed = exc.changed_inputs
    if "final-reading.json" not in receipts:
        return dict(result, status="awaiting_final_reading", next_action="readings")
    if "reading-run.json" not in receipts:
        return dict(result, status="awaiting_final_reading_run", next_action="readings")
    receipt, run = receipts["final-reading.json"], receipts["reading-run.json"]
    if changed:
        return dict(result, status="reading_inputs_changed", next_action="readings", changed_inputs=changed)
    if state is None or bundle is None:
        return dict(result, status="awaiting_reading_inputs", next_action="readings")
    current = bindings(root, folder, canonical=True,
                       binding_policy_version=receipt.get("binding_policy_version", 1))
    if run.get('reading_policy_version', 1) != READING_POLICY_VERSION:
        return dict(result, status='final_reading_policy_changed', next_action='readings')
    other_inputs_current = (receipt["publication_window"] == packet["target_publication_window"]
            and current_reading_run(run, packet, current, now)
            and receipt["reading_run_sha256"] == digest(run)
            and utc(run["finished_at"]) <= utc(receipt["completed_at"]) <= now)
    changed_inputs = [key for key in current if receipt["bindings"][key] != current[key]]
    reconciliation = None
    if (reconcile_legacy and other_inputs_current and changed_inputs == ["library.json"]
            and receipt.get("binding_policy_version", 1) == 1):
        from reading_receipt_reconciliation import reconcile_legacy_library
        reconciliation = reconcile_legacy_library(root, folder, receipt, run, packet,
            read(Path(root) / "data/weekly.json"), read(Path(root) / "data/library.json"), now)
    if not other_inputs_current or (changed_inputs and not reconciliation):
        return dict(result, status="final_reading_inputs_changed", next_action="readings",
                    changed_inputs=changed_inputs)
    expected_status = "completed_with_review_failures" if run["stages"]["review"]["failed"] else "bounded_stage_completed"
    if (receipt["status"] != expected_status or receipt["coverage"] !=
            final_coverage(packet, state, bundle, read(Path(root) / "data/library.json"), run)):
        raise ValueError("invalid_weekly_final_reading_coverage_receipt")
    if reconciliation:
        result["reconciliation"] = reconciliation
    return dict(result, ready=True, status=receipt["status"], coverage=receipt["coverage"])


def checkpoint(root, destination, now=None, phase="closed", week=None):
    """Preserve independently valid metadata, including across UTC rollover.

    Invalid files are excluded and reported, not allowed to erase unrelated
    provider pauses. The CLI fails this step when any validation fails, while
    exposing the valid recovery subset for the workflow's always-save path.
    """
    now = utc(now)
    week = week or target_window(now, phase)["from"]
    start = dt.date.fromisoformat(week)
    if start.isoformat() != week or start.weekday() != 0 or start > now.date():
        raise ValueError("invalid_checkpoint_week")
    folder = Path(root) / "data/weekly-preparation" / week
    window = {"from": week, "to": (start + dt.timedelta(days=6)).isoformat(), "timezone": "UTC"}
    selected, errors = [], []

    def retain(path, validate):
        if not path.exists():
            return None
        try:
            if path.is_symlink(): raise ValueError("symlink_checkpoint")
            value = read(path)
            validate(value)
        except (ValueError, TypeError, KeyError, AttributeError, OSError):
            errors.append(str(path.relative_to(root)))
            return None
        selected.append(path)
        return value

    def packet_check(value):
        observed = utc(value["observation_at"])
        if observed > now or validate_packet(value, observed) != window:
            raise ValueError("invalid_checkpoint_observation")
    packet = retain(folder / "packet.json", packet_check)
    if packet:
        status_path = Path(destination) / folder.relative_to(root) / "status.json"
        atomic_save(status_path, {k: packet[k] for k in ("observation_at", "phase", "status",
            "target_publication_window", "public_eligible", "source_checked", "approved")})
    for path in sorted((folder / "snapshots").glob("*.json")):
        retain(path, packet_check)
    import collect_weekly_sources as queue
    from prepared_article_readings import validate_bundle
    from academic_state import DiscoveryState
    import discover_editorial as editorial
    from editorial_feed_cache import load_cache

    def state_check(value):
        queue.validate_state(value)
        if value["publication_window"] != window:
            raise ValueError("invalid_checkpoint_namespace")
    retain(folder / "acquisition.json", state_check)
    retain(folder / "readings.json", lambda value: validate_bundle(value, window, now=now))
    academic = Path(root) / "data/academic-discovery-state.json"
    retain(academic, lambda value: DiscoveryState(academic, mode="weekly", window={k: window[k] for k in ("from", "to")}))
    cache = Path(root) / "data/editorial-feed-cache.json"
    retain(cache, lambda value: load_cache(cache, editorial.FEEDS))
    for path in selected:
        target = Path(destination) / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return {"valid": bool(selected), "complete": not errors, "invalid_files": errors,
            "validated_files": len(selected), "source_text_saved": False}


def checkpoint_commit(root, snapshot, worktree):
    """Commit validated metadata in a clean detached worktree, never the dirty runner.

    No fetch, push, provider or model operation occurs here. The workflow owns
    bounded rebase/push retries using this exact saved commit. Failed canonical
    projections remain untouched in the original ephemeral checkout.
    """
    root, snapshot, worktree = map(lambda p: Path(p).resolve(), (root, snapshot, worktree))
    selected = []
    for source in sorted((snapshot / "data").rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(snapshot)
        parts = relative.parts
        allowed = (len(parts) == 2 and parts[1] in {"academic-discovery-state.json", "editorial-feed-cache.json"})
        if len(parts) >= 4 and parts[:2] == ("data", "weekly-preparation"):
            week = dt.date.fromisoformat(parts[2])
            allowed = (week.isoformat() == parts[2] and week.weekday() == 0 and
                ((len(parts) == 4 and parts[3] in {"packet.json", "status.json", "acquisition.json", "readings.json"})
                 or (len(parts) == 5 and parts[3] == "snapshots" and source.suffix == ".json")))
        if not allowed or source.is_symlink():
            raise ValueError("unexpected_checkpoint_file")
        read(source)  # Refuse corrupt/truncated JSON even after earlier validation.
        selected.append((source, relative))
    if not selected:
        raise ValueError("empty_checkpoint")
    def git(*args, cwd=root):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    git("worktree", "add", "--detach", str(worktree), "HEAD")
    for source, relative in selected:
        target = worktree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    git("add", "--", *[str(relative) for _, relative in selected], cwd=worktree)
    changed = bool(git("diff", "--cached", "--name-only", cwd=worktree).stdout.strip())
    if changed:
        git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "Preserve validated preparation checkpoints after interrupted processing", cwd=worktree)
    return {"worktree": str(worktree), "committed": changed,
            "commit": git("rev-parse", "HEAD", cwd=worktree).stdout.strip()}


def lead_time():
    return {"measured_schedule_delay_hours": [4, 8], "measured_synthesis_minutes": [12, 18],
        "measured_pages_minutes": 1, "known_downstream_minutes_excluding_review": [253, 499],
        "full_review_throughput": "not_verified", "full_review_completion_estimate": None,
        "planning": "Prepare daily from Monday through Sunday; close out after Monday 00:00 and once after 06:00 UTC. "
                    "Additional queue waits, discovery, model setup and remaining review time are unmeasured. "
                    "This is not a guaranteed Monday publication time."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "closeout-plan", "closeout", "reading-plan", "readings", "finalize", "edition-check", "checkpoint", "checkpoint-commit", "scope", "lead-time"))
    parser.add_argument("--reconcile-legacy-library", action="store_true",
        help="Opt-in read-only proof against exact local Git history; edition-check only")
    parser.add_argument("--phase", choices=("preparing", "closed"), default="closed")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--expected-week", help="Fail before writing if the real UTC target changed since run scope")
    parser.add_argument("--week", help="Captured run namespace for recovery only, never a publication clock override")
    parser.add_argument("--max-requests", type=int, default=48)
    parser.add_argument("--max-feed-requests", type=int, default=24)
    parser.add_argument("--time-budget", type=int, default=240)
    args = parser.parse_args()
    if args.reconcile_legacy_library and args.action != "edition-check":
        parser.error("--reconcile-legacy-library is only supported for edition-check")
    if args.action in {"prepare", "closeout"}:
        operation = run_preparation if args.action == "prepare" else run_closeout
        result = operation(args.root, expected_week=args.expected_week, max_requests=args.max_requests,
                           max_feed_requests=args.max_feed_requests, max_pages=1, time_budget=args.time_budget)
    elif args.action == "closeout-plan": result = closeout_plan(args.root)
    elif args.action == "reading-plan": result = reading_plan(args.root, phase=args.phase)
    elif args.action == "readings": result = run_readings(args.root, phase=args.phase, expected_week=args.expected_week)
    elif args.action == "finalize": result = finalize(args.root, expected_week=args.expected_week)
    elif args.action == "edition-check": result = edition_ready(args.root, reconcile_legacy=args.reconcile_legacy_library)
    elif args.action == "lead-time": result = lead_time()
    elif args.action == "scope": result = {"week": target_window(utc(), args.phase)["from"], "phase": args.phase}
    elif args.action == "checkpoint-commit":
        if not args.destination or not args.worktree: parser.error("checkpoint-commit needs --destination and --worktree")
        result = checkpoint_commit(args.root, args.destination, args.worktree)
    else:
        if not args.destination: parser.error("checkpoint needs --destination")
        result = checkpoint(args.root, args.destination, phase=args.phase, week=args.week)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
            for key in ("ready", "needed", "week", "closeout_pass", "status", "valid", "complete"):
                if key in result:
                    out.write(key + "=" + (str(result[key]).lower() if isinstance(result[key], bool) else str(result[key])) + "\n")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write("Preparation stage: " + args.action + "\n\n" + json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if args.action == "checkpoint" and result["invalid_files"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
