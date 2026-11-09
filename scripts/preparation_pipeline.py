"""Bounded rolling/closeout orchestration and honest offline readiness checks.

A final-reading receipt proves which local stages ran against which inputs, not
that every source was available, that a model succeeded, or that anyone approved
its analysis. Publication keeps the established abstract-backed evidence gates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
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


def bindings(root, folder, *, canonical=False):
    names = {name: folder / name for name in ("packet.json", "acquisition.json", "readings.json")}
    if canonical:
        names.update({name: Path(root) / "data" / name for name in ("library.json", "weekly.json")})
    return {name: digest(read(path)) for name, path in names.items()}


def validate_reading_inputs(folder, now):
    import collect_weekly_sources as queue
    from prepared_article_readings import validate_bundle
    packet, state, bundle = (read(folder / name) for name in ("packet.json", "acquisition.json", "readings.json"))
    window = validate_packet(packet, now)
    queue.validate_state(state)
    validate_bundle(bundle, window, now=now)
    if (state["publication_window"] != window or bundle["packet_sha256"] != queue.digest(packet)
            or bundle["acquisition_state_sha256"] != state["state_sha256"]):
        raise ValueError("reading_inputs_changed")
    return packet, state, bundle


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
        "started_at": now.isoformat(), "finished_at": finished.isoformat(),
        "publication_window": target_window(now, phase), "bindings": bindings(root, folder),
        "stages": reports, "approved": False, "source_text_saved": False, "note": NOTE}
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


def finalize(root=ROOT, now=None, expected_week=None):
    now = utc(now)
    check_scope(expected_week, now, "closed")
    plan = reading_plan(root, now)
    if not plan["ready"]:
        raise ValueError(plan["status"])
    folder = folder_for(root, now, "closed")
    packet, state, bundle = validate_reading_inputs(folder, now)
    run = read(folder / "reading-run.json")
    if (run.get("kind") != "preparation_reading_run" or run.get("phase") != "closed"
            or run.get("publication_window") != packet["target_publication_window"]
            or run.get("bindings") != bindings(root, folder) or run.get("approved") is not False
            or set(run.get("stages", {})) != {"acquire", "review", "revalidate", "apply"}
            or not utc(packet["observation_at"]) <= utc(run["started_at"]) <= utc(run["finished_at"]) <= now):
        raise ValueError("current_final_reading_run_required")
    coverage = coverage_report(packet, state, bundle, read(Path(root) / "data/library.json"))
    review = run["stages"]["review"]
    coverage["review_attempted_this_run"] = review["attempted"]
    coverage["review_completed_this_run"] = review["summaries_completed"]
    coverage["review_failed_this_run"] = review["failed"]
    coverage["machine_checked_readings_applied_this_run"] = run["stages"]["apply"]["machine_checked_readings_applied"]
    receipt = {"schema_version": 1, "kind": "weekly_final_reading", "completed_at": now.isoformat(),
        "publication_window": packet["target_publication_window"], "bindings": bindings(root, folder, canonical=True),
        "reading_run_sha256": digest(run), "approved": False, "source_text_saved": False,
        "status": "completed_with_review_failures" if review["failed"] else "bounded_stage_completed",
        "coverage": coverage}
    atomic_save(folder / "final-reading.json", receipt)
    return receipt


def edition_ready(root=ROOT, now=None):
    now = utc(now)
    result = reading_plan(root, now)
    if not result["ready"]:
        return result
    folder = folder_for(root, now, "closed")
    result["ready"] = False
    if not (folder / "final-reading.json").exists():
        return dict(result, status="awaiting_final_reading")
    receipt = read(folder / "final-reading.json")
    packet, _, _ = validate_reading_inputs(folder, now)
    if (receipt.get("kind") != "weekly_final_reading" or receipt.get("approved") is not False
            or receipt.get("publication_window") != packet["target_publication_window"]
            or receipt.get("bindings") != bindings(root, folder, canonical=True)
            or receipt.get("reading_run_sha256") != digest(read(folder / "reading-run.json"))
            or not utc(packet["observation_at"]) <= utc(receipt["completed_at"]) <= now):
        return dict(result, status="final_reading_inputs_changed")
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
    if args.action in {"prepare", "closeout"}:
        operation = run_preparation if args.action == "prepare" else run_closeout
        result = operation(args.root, expected_week=args.expected_week, max_requests=args.max_requests,
                           max_feed_requests=args.max_feed_requests, max_pages=1, time_budget=args.time_budget)
    elif args.action == "closeout-plan": result = closeout_plan(args.root)
    elif args.action == "reading-plan": result = reading_plan(args.root, phase=args.phase)
    elif args.action == "readings": result = run_readings(args.root, phase=args.phase, expected_week=args.expected_week)
    elif args.action == "finalize": result = finalize(args.root, expected_week=args.expected_week)
    elif args.action == "edition-check": result = edition_ready(args.root)
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
