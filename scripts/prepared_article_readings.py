"""Prepare source readings in a separate staging area, then revalidate identity.

No source document is saved. Machine checks, fresh source verification and
independent approval stay separate; this module never supplies approval.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import collect_weekly_sources as queue
import comprehensive_readings as readings
from acquisition_handoff import retrieve_for_reading, matching_row, same_article

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("deep_analysis", "partial_reading_candidate", "reading_coverage", "complete_reading_attempt")


def validated_window(packet, now):
    from weekly_preparation import validate_packet
    return validate_packet(packet, now=now)


def sealed(value):
    value.pop("metadata_sha256", None)
    value["metadata_sha256"] = queue.digest(value)
    return value


def same_input(left, right, window, known_only):
    """Observation refreshes are not new publication or source versions."""
    if not same_article(left, right, queue):
        return False
    def normalized(record):
        value = deepcopy(record)
        evidence = value.get("publication_date_provenance") or {}
        evidence.pop("checked_at", None)
        value["publication_date_provenance"] = evidence
        return queue.prepare(value, window, known_only)[2]
    return normalized(left) == normalized(right)


def validate_bundle(value, window, now=None):
    from prepared_reading_schema import validate_saved_record, validate_revalidation
    now = queue.utc_now(now)
    required = {"schema_version", "kind", "publication_window", "observation_at", "packet_sha256",
        "acquisition_state_sha256", "public_eligible", "approved", "source_text_saved", "records", "metadata_sha256"}
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1
            or not required <= set(value) or set(value) - required - {"review_run", "revalidation_run"}
            or value.get("kind") != "prepared_article_readings"
            or value.get("publication_window") != window
            or value.get("public_eligible") is not False or value.get("approved") is not False
            or value.get("source_text_saved") is not False or not isinstance(value.get("records"), dict)
            or value.get("metadata_sha256") != queue.digest({k: v for k, v in value.items() if k != "metadata_sha256"})):
        raise ValueError("invalid_prepared_readings")
    if 'review_run' in value:
        from preparation_pipeline import validate_stage_report
        validate_stage_report('review', value['review_run'])
    queue.timestamp(value["observation_at"])
    if queue.utc_now(value["observation_at"]) > now:
        raise ValueError("invalid_prepared_readings")
    queue.hash_value(value["packet_sha256"])
    queue.hash_value(value["acquisition_state_sha256"])
    for key, item in value["records"].items():
        queue.hash_value(key)
        if (not isinstance(item, dict) or not isinstance(item.get("record"), dict)
                or not {"input_fingerprint", "record"} <= set(item)
                or set(item) - {"input_fingerprint", "record", "revalidation", "acquisition_receipt_sha256"}):
            raise ValueError("invalid_prepared_readings")
        queue.hash_value(item.get("input_fingerprint"))
        if "acquisition_receipt_sha256" in item:
            queue.hash_value(item["acquisition_receipt_sha256"])
        if key != queue.record_key(item["record"]):
            raise ValueError("invalid_prepared_readings")
        validate_saved_record(item["record"], now=now)
        if "revalidation" in item:
            validate_revalidation(item["revalidation"], item["record"].get("deep_analysis") or {},
                                  item["input_fingerprint"], now=now)
    return value


def reconcile(packet, state, previous=None, *, now=None):
    from prepared_reading_schema import strip_staged_enrichment
    now = queue.utc_now(now)
    window = validated_window(packet, now)
    queue.validate_state(state)
    if state["publication_window"] != window:
        raise ValueError("prepared_acquisition_window_mismatch")
    previous = validate_bundle(previous, window, now=now) if previous is not None else {"records": {}}
    records = {}
    for candidate in packet["items"]:
        key = queue.record_key(candidate)
        if key in records:
            raise ValueError("duplicate_preparation_identity")
        row = matching_row(candidate, packet, state, queue)
        if row is None:
            continue
        record = strip_staged_enrichment(candidate)
        saved = previous["records"].get(key)
        item = {"input_fingerprint": row["fingerprint"], "record": record}
        if row.get("document"):
            item["acquisition_receipt_sha256"] = queue.digest(row["document"])
        if (saved and queue.prepare(saved["record"], window, row["plan"]["known_sources_only"])[2] == saved["input_fingerprint"]
                and same_input(record, saved["record"], window, row["plan"]["known_sources_only"])):
            for field in FIELDS:
                if field in saved["record"]:
                    record[field] = deepcopy(saved["record"][field])
            if "revalidation" in saved and saved["input_fingerprint"] == row["fingerprint"]:
                item["revalidation"] = deepcopy(saved["revalidation"])
            # New, materially fuller source evidence gets a new reading turn.
            old_coverage = (record.get("deep_analysis") or {}).get("coverage") or {}
            receipt = row.get("document") or {}
            receipt_changed = (saved.get("acquisition_receipt_sha256") is not None
                and saved["acquisition_receipt_sha256"] != item.get("acquisition_receipt_sha256"))
            if receipt_changed or (old_coverage and (not receipt or any(old_coverage.get(k) != receipt.get(k)
                    for k in ("source_sha256", "source_bytes_sha256", "source_byte_count",
                              "html_extraction_version", "document_version", "source_url", "evidence_status")))):
                # An unchanged input's failed attempt still owns its cooldown.
                # Removing stale analysis must not make the same failed source
                # immediately eligible again on every preparation schedule.
                attempt = record.get("complete_reading_attempt") or {}
                failed = attempt.get("stage") in {"retrieval", "synthesis"}
                refreshed = any(event["status"] == "refreshed"
                    and event["replacement_sha256"] == item.get("acquisition_receipt_sha256")
                    and queue.digest(event["receipt"]["document"]) == saved.get("acquisition_receipt_sha256")
                    for event in row.get("source_refreshes", []))
                for field in FIELDS:
                    if field == "complete_reading_attempt" and failed and not refreshed:
                        continue
                    record.pop(field, None)
                item.pop("revalidation", None)
        # A newly observed mismatch also invalidates an older cached success
        # before reacquisition. Retaining the old receipt is not permission to
        # publish stale analysis while recovery is pending or held.
        if ((row.get("source_refresh_hold") or (row.get("source_refreshes")
                and row["source_refreshes"][-1]["status"] != "refreshed"))
                and (item.get("revalidation") or {}).get("status") == "source_revalidated"):
            item.pop("revalidation", None)
        records[key] = item
    return sealed({"schema_version": 1, "kind": "prepared_article_readings", "publication_window": window,
        "observation_at": now.isoformat(), "packet_sha256": queue.digest(packet),
        "acquisition_state_sha256": state["state_sha256"], "public_eligible": False,
        "approved": False, "source_text_saved": False, "records": records})


def acquire(packet, state=None, *, now=None, shared_controls=None, **options):
    now = queue.utc_now(now)
    window = validated_window(packet, now)
    return queue._run_window(packet, state, window=window, now=now,
                             shared_controls=shared_controls, **options)


def observe_retrieval(state, diagnostics, now, save_state=None):
    """Keep newly observed restrictions and receipt requests in the retained state."""
    from source_access_controls import merge_diagnostics_into_state
    updated = merge_diagnostics_into_state(state, diagnostics, now=now)
    state.clear(); state.update(updated)
    if save_state is not None:
        save_state(state)


def observed_retriever(packet, state, now, data_dir=None, save_state=None):
    def moment():
        return queue.utc_now(now() if callable(now) else now)
    def retrieve(record):
        return retrieve_for_reading(record, state=state, payload=packet, now=moment(),
            controls_data_dir=data_dir, diagnostic_observer=lambda diagnostics:
                observe_retrieval(state, diagnostics, moment(), save_state))
    return retrieve


def observe_document_mismatch(record, document, state, now):
    from acquisition_handoff import receipt_change_note
    row = state["records"][queue.record_key(record)]
    if row.get("document") and queue.document_metadata(document)["source_url"] == row["document"]["source_url"]:
        observe_retrieval(state, [receipt_change_note(record, row, document, queue)], now)


def review(packet, state, previous=None, *, model, now=None, limit=2, retriever=None, data_dir=None):
    now = queue.utc_now(now)
    bundle = reconcile(packet, state, previous, now=now)
    candidates = []
    for key, item in bundle["records"].items():
        if state["records"][key].get("document"):
            candidates.append(item["record"])
    if retriever is None:
        retriever = observed_retriever(packet, state, now, data_dir)
    def receipt_checked_retriever(record):
        document, diagnostics = retriever(record)
        if document is None:
            raise ValueError("prepared_source_unavailable")
        receipt = state["records"][queue.record_key(record)].get("document")
        current = document.manifest()
        # The ordinary handoff can return an independently retrieved alternative.
        # Preparation cannot spend model work on it or adopt its source receipt.
        # Include byte/parser/interval evidence, not just an extracted-text hash.
        if (not receipt or current.get("document_version") != receipt.get("document_version")
                or queue.document_metadata(document) != receipt):
            observe_document_mismatch(record, document, state, now)
            raise ValueError("prepared_acquisition_receipt_mismatch")
        return document, diagnostics
    stats = readings.process(candidates, model, limit=limit, retriever=receipt_checked_retriever, run_date=now.date())
    bundle["review_run"] = stats
    bundle["acquisition_state_sha256"] = state["state_sha256"]
    return validate_bundle(sealed(bundle), bundle["publication_window"], now=now)


def revalidate(packet, state, bundle, *, now=None, limit=10, retriever=None, data_dir=None):
    now = queue.utc_now(now)
    window = validated_window(packet, now)
    if packet.get("phase") != "closed":
        raise ValueError("closed_preparation_required")
    from weekly_preparation import closed_packet
    queue.validate_window(closed_packet(packet, now=now), now)
    bundle = reconcile(packet, state, bundle, now=now)
    if retriever is None:
        retriever = observed_retriever(packet, state, now, data_dir)
    attempted = 0
    def oldest_check(entry):
        checked = (entry[1].get("revalidation") or {}).get("checked_at")
        return (queue.utc_now(checked) if checked else datetime.min.replace(tzinfo=timezone.utc), entry[0])
    # A held first item must not consume every later run's bounded budget.
    # Ordering survives JSON reloads and packet reordering; matching successes
    # remain cached below and do not consume a turn.
    for key, item in sorted(bundle["records"].items(), key=oldest_check):
        deep = item["record"].get("deep_analysis") or {}
        coverage = deep.get("coverage") or {}
        if (deep.get("version", 0) < 3 or not coverage.get("all_retrieved_text_processed")
                or coverage.get("evidence_status") != "full_document_retrieved"
                or deep.get("review_status") != "machine_checked_not_independently_reviewed"):
            continue
        basis = queue.digest({"input": item["input_fingerprint"], "analysis": deep})
        previous = item.get("revalidation") or {}
        closed_at = datetime.fromisoformat(window["to"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
        if (previous.get("basis") == basis and previous.get("status") == "source_revalidated"
                and closed_at <= queue.utc_now(previous.get("checked_at")) <= now):
            continue
        if attempted >= limit:
            break
        attempted += 1
        result = {"basis": basis, "checked_at": now.isoformat(), "status": "held", "approved": False}
        try:
            document, diagnostics = retriever(item["record"])
            if document is None:
                raise ValueError("prepared_source_unavailable")
            current = document.manifest()
            receipt = state["records"][key].get("document")
            if queue.document_metadata(document) != receipt:
                observe_document_mismatch(item["record"], document, state, now)
                raise ValueError("prepared_source_changed")
            for field in ("source_sha256", "source_bytes_sha256", "source_byte_count",
                          "html_extraction_version", "source_url", "document_version", "evidence_status"):
                if current.get(field) != coverage.get(field):
                    raise ValueError("prepared_source_changed")
            if current.get("evidence_status") != "full_document_retrieved":
                raise ValueError("prepared_source_partial")
            result.update(status="source_revalidated", source_sha256=current["source_sha256"],
                          document_version=current["document_version"])
        except Exception as exc:
            result["reason"] = str(exc) if isinstance(exc, ValueError) and str(exc).replace("_", "").isalnum() else type(exc).__name__
        item["revalidation"] = result
    bundle["revalidation_run"] = {"attempted": attempted, "source_text_saved": False, "approved": False}
    bundle["acquisition_state_sha256"] = state["state_sha256"]
    return validate_bundle(sealed(bundle), window, now=now)


def apply_closed(packet, state, bundle, library, weekly, *, now=None):
    """Return copied library with eligible machine notes, never an approval."""
    now = queue.utc_now(now)
    window = validated_window(packet, now)
    if packet.get("phase") != "closed":
        raise ValueError("closed_preparation_required")
    from weekly_preparation import closed_packet
    queue.validate_window(closed_packet(packet, now=now), now)
    if queue.validate_window(weekly, now) != window:
        raise ValueError("prepared_publication_window_mismatch")
    bundle = reconcile(packet, state, bundle, now=now)
    selected = {}
    for record in weekly["items"]:
        key = queue.record_key(record)
        if key in selected:
            raise ValueError("duplicate_weekly_publication_identity")
        selected[key] = record
    library_keys = [queue.record_key(record) for record in library]
    if len(library_keys) != len(set(library_keys)):
        raise ValueError("duplicate_library_publication_identity")
    output = deepcopy(library); applied = []
    closed_at = datetime.fromisoformat(window["to"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
    for record in output:
        key = queue.record_key(record)
        item = bundle["records"].get(key)
        if not item or key not in selected or record.get("source_review") or record.get("original_reading"):
            continue
        deep = item["record"].get("deep_analysis") or {}
        checked = item.get("revalidation") or {}
        basis = queue.digest({"input": item["input_fingerprint"], "analysis": deep})
        if (checked.get("status") != "source_revalidated" or checked.get("basis") != basis
                or checked.get("approved") is not False or queue.utc_now(checked.get("checked_at")) < closed_at
                or queue.utc_now(checked["checked_at"]) > now
                or not same_article(record, item["record"], queue)
                or not same_article(selected[key], item["record"], queue)
                or queue.eligibility(record, window)):
            continue
        if (deep.get("review_status") != "machine_checked_not_independently_reviewed"
                or (deep.get("coverage") or {}).get("evidence_status") != "full_document_retrieved"
                or not (deep.get("coverage") or {}).get("all_retrieved_text_processed")):
            continue
        acquisition = state["records"][key]
        if (not same_input(record, item["record"], window, acquisition["plan"]["known_sources_only"])
                or not same_input(selected[key], item["record"], window, acquisition["plan"]["known_sources_only"])):
            continue
        current = record.get("deep_analysis") or {}
        if (current and (current.get("coverage") or {}).get("evidence_status") == "full_document_retrieved"
                and current.get("source_hash") != deep.get("source_hash")):
            continue
        for field in FIELDS:
            if field in item["record"]:
                record[field] = deepcopy(item["record"][field])
        record["deep_analysis"]["preparation_provenance"] = {"publication_window": window,
            "source_revalidated_at": checked["checked_at"], "independently_approved": False}
        applied.append(key)
    return output, {"machine_checked_readings_applied": len(applied), "approved": False,
                    "source_text_saved": False, "publication_window": window}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("acquire", "review", "revalidate", "apply"))
    parser.add_argument("--week", required=True)
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    if not 0 <= args.limit <= 20:
        raise ValueError("invalid_preparation_budget")
    week = datetime.strptime(args.week, "%Y-%m-%d").date()
    if week.isoformat() != args.week or week.weekday() != 0:
        raise ValueError("invalid_preparation_week")
    data = ROOT / "data"
    folder = data / "weekly-preparation" / args.week
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    packet = read(folder / "packet.json")
    now = datetime.now(timezone.utc)
    window = validated_window(packet, now)
    if window["from"] != args.week:
        raise ValueError("preparation_namespace_mismatch")
    state_path, bundle_path = folder / "acquisition.json", folder / "readings.json"
    state = read(state_path) if state_path.exists() else None
    if args.stage == "acquire":
        from source_access_controls import load_shared_controls
        controls = load_shared_controls(data, states=[state] if state else (), now=now)
        result = acquire(packet, state, now=now, limit=args.limit, time_budget=480,
            item_time_budget=60, shared_controls=controls, save=lambda value: queue.atomic_save(state_path, value))
        print(json.dumps(result["run"]))
        return
    if state is None:
        print(json.dumps({"status": "awaiting_acquisition", "approved": False})); return
    bundle = read(bundle_path) if bundle_path.exists() else None
    tracked_retriever = observed_retriever(packet, state, lambda: datetime.now(timezone.utc), data,
        save_state=lambda value: queue.atomic_save(state_path, value))
    if args.stage == "review":
        model_path = Path(os.getenv("LOCAL_READING_MODEL", "/tmp/attention-model.gguf"))
        if not model_path.is_file():
            print(json.dumps({"status": "model_unavailable", "approved": False})); return
        from llama_cpp import Llama
        model = Llama(model_path=str(model_path), n_ctx=6144, chat_format="chatml",
                      n_threads=min(os.cpu_count() or 2, 4), verbose=False)
        result = review(packet, state, bundle, model=model, now=now, limit=min(args.limit, 2),
                        retriever=tracked_retriever, data_dir=data)
        result["acquisition_state_sha256"] = state["state_sha256"]
        sealed(result)
        save(bundle_path, result); print(json.dumps(result["review_run"])); return
    if bundle is None:
        print(json.dumps({"status": "awaiting_prepared_readings", "approved": False})); return
    if args.stage == "revalidate":
        result = revalidate(packet, state, bundle, now=now, limit=args.limit,
                            retriever=tracked_retriever, data_dir=data)
        result["acquisition_state_sha256"] = state["state_sha256"]
        sealed(result)
        save(bundle_path, result); print(json.dumps(result["revalidation_run"])); return
    library, report = apply_closed(packet, state, bundle, read(data / "library.json"), read(data / "weekly.json"), now=now)
    save(data / "library.json", library)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
