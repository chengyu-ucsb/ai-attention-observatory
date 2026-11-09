"""Bounded staging of an open publication week, then strict closeout.

Metadata uses the production academic/feed collectors. Retrieval and review may
consume packet.json. Preparation never writes canonical/public output; explicit
post-closeout adoption writes canonical metadata only, never public editions,
readings, approvals or source bodies. Use the common data-writer lock:
academic queries and publisher snapshots share their existing provider pauses.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time

from academic_state import DiscoveryState, ProviderDeferred
from academic_state_schema import strict_json_loads
from collection_window import (previous_week, publication_date, weekly_eligible,
                               reconcile_publication_evidence, window_metadata)
import discover_editorial as editorial
import editorial_feed_cache as feeds_cache
from priority_research import discover as discover_priority, doi_id
import update

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_NOTE = ("Bounded configured provider queries and publisher snapshots only. "
                 "Delayed indexing, unavailable sources and unresolved dates can remain partial; "
                 "calendar closure is not exhaustive coverage, source review or approval.")

def utc(value=None):
    value = value or dt.datetime.now(dt.timezone.utc)
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, dt.datetime) or value.tzinfo is None:
        raise ValueError("An actual timezone-aware observation time is required")
    return value.astimezone(dt.timezone.utc)

def target_window(now, phase):
    now = utc(now)
    if phase == "preparing":
        start = now.date() - dt.timedelta(days=now.weekday())
        end = start + dt.timedelta(days=6)
    elif phase == "closed":
        start, end = previous_week(now)
    else:
        raise ValueError("Unsupported preparation phase")
    return {"from": start.isoformat(), "to": end.isoformat(), "timezone": "UTC"}

def validate_packet(packet, now=None):
    """Shared fail-closed boundary for preparation retrieval, never publication."""
    now = utc(now)
    validate_packet_metadata(packet)
    if type(packet.get("schema_version")) is not int or packet.get("schema_version") != 1 or packet.get("kind") != "weekly_preparation":
        raise ValueError("Invalid preparation packet")
    observed = utc(packet.get("observation_at")) if packet.get("observation_at") else None
    if observed is None or observed > now:
        raise ValueError("Preparation observation must be actual, not future")
    phase = packet.get("phase")
    window = target_window(observed, phase)
    if packet.get("target_publication_window") != window or target_window(now, phase) != window:
        raise ValueError("Preparation target does not match the actual UTC week")
    run = packet.get("run") or {}
    if (run.get("mode") != "preparation" or run.get("date") != observed.date().isoformat()
            or run.get("publication_window") != window
            or packet.get("status") not in {"prepared", "partial"}
            or packet.get("date_eligibility") != "verified_original_publication_date_only"
            or any(packet.get(key) is not False for key in ("public_eligible", "source_checked", "approved"))
            or not isinstance(packet.get("items"), list) or not isinstance(packet.get("quarantine"), list)):
        raise ValueError("Invalid preparation readiness/date contract")
    seen = set()
    for row in packet["items"]:
        if (not isinstance(row, dict) or not weekly_eligible(row, window["from"], window["to"])
                or publication_date(row.get("published")) > observed.date()):
            raise ValueError("Preparation contains an unverified or future publication")
        key = record_key(row)
        if key in seen:
            raise ValueError("Duplicate preparation identity")
        seen.add(key)
    return window

def closed_packet(packet, now=None):
    """Produce normal strict previous-week input, without publishing any file.

    Partial coverage is explicit. Source acquisition/review/approval and public
    builders remain mandatory downstream, even for a closed calendar window.
    """
    now = utc(now)
    window = validate_packet(packet, now)
    coverage = packet.get("coverage") or {}
    if (packet["phase"] != "closed" or not coverage.get("closeout_started_at")
            or coverage.get("closeout_required") is not False):
        raise ValueError("A real post-Sunday closeout is required")
    started = utc(coverage["closeout_started_at"])
    closing = dt.datetime.combine(publication_date(window["to"]) + dt.timedelta(days=1),
                                  dt.time(), dt.timezone.utc)
    if not closing <= started <= utc(packet["observation_at"]):
        raise ValueError("Closeout did not begin after Sunday UTC")
    return {"run": {"date": now.date().isoformat(), "mode": "weekly",
                    "publication_window": window_metadata(now),
                    "selection_basis": "original_publication_date_previous_completed_week",
                    "preparation_observation_at": packet["observation_at"],
                    "stats": {"discovery_status": "complete" if packet["status"] == "prepared" else "partial", "preparation_coverage": deepcopy(coverage)}},
            "items": [metadata_record(row) for row in packet["items"]]}


def adopt_closed_packet(packet, library, now=None):
    """Pure metadata adoption for a real closed week; caller owns atomic writes.

    Existing reading bodies, receipts and approval fields are not copied from
    staging or rewritten. Changed/conflicting dates still fail the normal source
    receipt/date gate. Only downstream source checks can approve prepared work.
    """
    now = utc(now)
    weekly = closed_packet(packet, now)
    start, end = previous_week(now)
    records = {record_key(row): deepcopy(row) for row in library}
    known = set(records)
    previous_records = deepcopy(records)
    for row in records.values():
        evidence = packet.get("coverage", {}).get("publication_date_corrections", {}).get(doi_id(row.get("doi")))
        if evidence:
            update.apply_publication_evidence(row, *evidence)
    incoming = {record_key(row): metadata_record(row) for row in packet["quarantine"]
                if row.get("kind") in {"scholarly", "nonacademic"}}
    incoming.update({record_key(row): metadata_record(row) for row in packet["items"]})
    for key, row in incoming.items():
        if key not in records:
            records[key] = deepcopy(row)
            continue
        current = records[key]
        prior = current.get("publication_date_provenance") or {}
        evidence = row.get("publication_date_provenance") or {}
        if current.get("kind") == "scholarly":
            update.apply_publication_evidence(current, row.get("published", ""), evidence)
        elif (prior.get("status") in {"unresolved", "conflict", "conflicting", "unknown"}
                or prior.get("requires_explicit_date_resolution")):
            pass  # Routine feed observations cannot resolve a prior dispute.
        elif evidence.get("status") in {"unresolved", "conflict", "conflicting", "unknown"}:
            current["publication_date_provenance"] = deepcopy(evidence)
        elif current.get("published") and current["published"] != row.get("published"):
            current["publication_date_provenance"] = {"status": "unresolved",
                "reason": "conflicting_original_publication_dates",
                "evidence": [deepcopy(prior), deepcopy(evidence)]}
        elif not (prior.get("independently_verified") is True and
                  weekly_eligible(current, dt.date.min, dt.date.max)):
            current["published"] = row.get("published", "")
            current["publication_date_provenance"] = deepcopy(evidence)
        if len(row.get("abstract_text", "")) > len(current.get("abstract_text", "")):
            for field in ("abstract_text", "abstract_source", "preview"):
                current[field] = row.get(field, "")
        if row.get("metadata_observed_at"):
            current["metadata_observed_at"] = row["metadata_observed_at"]
    preserve_unchanged_check_times(records, previous_records)
    library = sorted(records.values(), key=lambda row: (row.get("published", ""), row.get("first_seen", "")), reverse=True)
    weekly["items"] = update.diverse_week([row for row in library if weekly_eligible(row, start, end)])
    weekly["run"].update(total=len(library), new=len(set(records) - known),
                         candidates=len(packet["items"]), last_seven_days=len(weekly["items"]))
    weekly["run"]["stats"]["publication_date_quarantine_records"] = len(packet["quarantine"])
    return {"library": library, "weekly": weekly,
            "quarantine": {"publication_window": deepcopy(packet["target_publication_window"]),
                           "items": [metadata_record(row) if row.get("kind") in {"scholarly", "nonacademic"}
                                     else {k: deepcopy(v) for k, v in row.items() if k in {"title", "url", "publisher", "feed_id",
                                         "reported_date", "reported_date_basis", "status", "eligible_for_weekly", "observed_at"}}
                                     for row in packet["quarantine"]]}}

def adopt_closeout_checkpoint(path, now=None, *, closeout_pass="initial"):
    """Share a finished closeout with normal resume only if its namespace is new.

    Provider controls and every existing weekly query/evidence remain unchanged.
    Incomplete closeouts stay in their own generation and resume there, so an
    independent ordinary weekly cursor cannot drift away from the closing pass.
    """
    now = utc(now)
    window = target_window(now, "closed")
    bounds = {key: window[key] for key in ("from", "to")}
    if closeout_pass not in {"initial", "late_index"}:
        raise ValueError("Invalid closeout pass")
    mode = "closeout" if closeout_pass == "initial" else "closeout_late_index"
    state = DiscoveryState(path, mode=mode, window=bounds)
    if not state.had_window or not state.current["plans"]:
        return {"status": "no_closeout_checkpoint", "adopted": False}
    if state.summary()["status"] != "complete_for_configured_queries":
        return {"status": "partial_closeout_resume_required", "adopted": False}
    closing = dt.datetime.combine(publication_date(window["to"]) + dt.timedelta(days=1),
                                  dt.time(), dt.timezone.utc).timestamp()
    if any(not closing <= query.get("started_at", 0) <= now.timestamp()
           or not closing <= query.get("observed_at", 0) <= now.timestamp()
           for query in state.current["queries"].values()):
        raise ValueError("Closeout queries must be actually observed after Sunday")
    ident = "weekly:" + bounds["from"] + ":" + bounds["to"]
    if ident in state.data["windows"]:
        return {"status": "existing_weekly_checkpoint_preserved", "adopted": False}
    clone = deepcopy(state.current)
    clone["mode"] = "weekly"
    state.data["windows"][ident] = clone
    state.save()
    return {"status": "closeout_checkpoint_adopted", "adopted": True, "window_id": ident}



# Canonical adoption is metadata-only even if a stale/tampered staging packet
# carries review fields. Prepared source analysis has its own receipt-bound gate.
METADATA_FIELDS = {"title", "authors", "published", "venue", "doi", "url", "preview", "kind", "lane",
    "relation", "evidence", "source", "format", "source_type", "source_type_basis",
    "publication_date_provenance", "discovery_provenance", "first_seen", "content_access",
    "abstract_text", "abstract_source", "discovery_scope", "discovery_query", "historical_backfill",
    "source_group", "metadata_observed_at", "preparation_first_seen_at", "acquisition_status"}


def preserve_unchanged_check_times(records, previous):
    """Operational rechecks do not invalidate otherwise identical source proof."""
    for key, row in records.items():
        prior = previous.get(key, {}).get("publication_date_provenance") or {}
        current = row.get("publication_date_provenance") or {}
        if (prior.get("checked_at") and
                {k: v for k, v in prior.items() if k != "checked_at"} ==
                {k: v for k, v in current.items() if k != "checked_at"}):
            current["checked_at"] = prior["checked_at"]

def metadata_record(row):
    selected = {key: deepcopy(value) for key, value in row.items() if key in METADATA_FIELDS}
    # OpenAlex permits null author display names. Omit the absent metadata,
    # while still rejecting objects or other payloads in author-name slots.
    if isinstance(selected.get("authors"), (list, tuple)):
        selected["authors"] = [name for name in selected["authors"] if name is not None]
    validate_metadata_record(selected)
    return selected


# These repository-public packets are metadata, not arbitrary JSON envelopes.
# Keep the collectors' useful diagnostics, but never relay new body/approval
# fields through a known report name, provenance object or quarantine entry.
METADATA_ERROR = "Invalid preparation metadata; preserve the packet for inspection"
MAX_PACKET_BYTES = 32_000_000


def metadata_require(condition):
    if not condition:
        raise ValueError(METADATA_ERROR)


def meta_text(value, maximum=2048):
    metadata_require(type(value) is str and len(value) <= maximum
                     and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value))


def meta_count(value):
    metadata_require(type(value) is int and 0 <= value <= 1_000_000_000)


def meta_number(value):
    metadata_require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100_000_000_000)


def meta_bool(value):
    metadata_require(type(value) is bool)


def meta_false(value):
    metadata_require(value is False)


def meta_day(value):
    meta_text(value, 10)
    metadata_require(not value or (publication_date(value) is not None and len(value) == 10))


def meta_time(value):
    meta_text(value, 50)
    utc(value)


def meta_url(value):
    from urllib.parse import urlsplit
    meta_text(value, 4096)
    if not value:
        return
    parts = urlsplit(value)
    metadata_require(parts.scheme in {"https", "http"} and bool(parts.hostname)
                     and not parts.username and not parts.password and not editorial.credentialed_url(value))


def nullable(check):
    return lambda value: None if value is None else check(value)


def meta_enum(*values):
    return lambda value: metadata_require(type(value) is str and value in values)


def meta_check_time(value):
    meta_text(value, 50)
    if len(value) == 10:
        meta_day(value)
    else:
        meta_time(value)


def meta_list(check, maximum=5000):
    def validate(value):
        metadata_require(type(value) in (list, tuple) and len(value) <= maximum)
        for entry in value:
            check(entry)
    return validate


def meta_object(value, fields, required=()):
    metadata_require(type(value) is dict and set(required) <= set(value) <= set(fields))
    for key, entry in value.items():
        fields[key](entry)


def object_check(fields, required=()):
    return lambda value: meta_object(value, fields, required)


def meta_map(value, check, key_check=meta_text, maximum=5000):
    metadata_require(type(value) is dict and len(value) <= maximum)
    for key, entry in value.items():
        key_check(key); check(entry)


def meta_provenance(value, depth=0):
    metadata_require(depth <= 8)
    strings = {"source", "policy", "status", "field", "reason", "basis", "requested_id",
               "timezone", "precision", "version"}
    days = {"value", "date", "openalex_publication_date", "crossref_publication_date",
            "provider_publication_date", "stored_publication_date"}
    fields = {key: meta_text for key in strings}
    fields.update({key: meta_day for key in days})
    fields.update({key: meta_bool for key in {"requires_explicit_date_resolution", "verification_error",
                                             "independently_verified", "original_day_verified"}})
    fields.update({key: meta_url for key in {"source_url", "version_url", "source_id"}})
    fields.update(raw=lambda x: meta_text(x, 512), checked_at=meta_check_time,
        date_parts=meta_list(lambda x: metadata_require(type(x) is int and abs(x) <= 10000), 8),
        evidence=meta_list(lambda x: meta_provenance(x, depth + 1), 128),
        earlier_publication_evidence=lambda x: meta_provenance(x, depth + 1))
    meta_object(value, fields)


DISCOVERY_SCHEMA = {key: meta_text for key in {"method", "feed_id"}}
DISCOVERY_SCHEMA.update(feed_url=meta_url, checked_at=meta_check_time,
                        metadata_snapshot_observed_at=meta_time)


def validate_metadata_record(row):
    fields = {key: meta_text for key in METADATA_FIELDS}
    fields.update(title=lambda x: meta_text(x, 4096), abstract_text=lambda x: meta_text(x, 6000),
        preview=lambda x: meta_text(x, 1000), authors=meta_list(lambda x: meta_text(x, 1024), 50),
        published=meta_day, first_seen=meta_day, url=meta_url,
        historical_backfill=meta_bool, publication_date_provenance=meta_provenance,
        discovery_provenance=object_check(DISCOVERY_SCHEMA), metadata_observed_at=meta_time,
        preparation_first_seen_at=meta_time)
    meta_object(row, fields, {"kind", "title", "url", "published", "publication_date_provenance"})
    metadata_require(row["kind"] in {"scholarly", "nonacademic"})


QUARANTINE_SCHEMA = {key: meta_text for key in {"title", "publisher", "feed_id", "reported_date_basis", "status"}}
QUARANTINE_SCHEMA.update(url=meta_url, reported_date=meta_day, eligible_for_weekly=meta_false, observed_at=meta_time)


def validate_quarantine(row):
    if type(row) is dict and row.get("kind") in {"scholarly", "nonacademic"}:
        validate_metadata_record(row)
    else:
        meta_object(row, QUARANTINE_SCHEMA, {"title", "url", "status", "eligible_for_weekly"})


WINDOW_SCHEMA = {"from": meta_day, "to": meta_day, "timezone": meta_text,
                 "basis": meta_text, "inclusive": meta_bool, "scope": meta_text}
WINDOW_CHECK = object_check(WINDOW_SCHEMA, {"from", "to"})
PROVIDER_SCHEMA = {key: meta_number for key in {"next_retry_at", "last_request_at"}}
PROVIDER_SCHEMA.update(blocked=meta_bool, last_http_status=nullable(meta_count),
    consecutive_failures=meta_count, reason=lambda x: meta_text(x, 240))
CHECKPOINT_SCHEMA = {key: meta_count for key in {"active_queries", "completed_queries", "pending_queries", "superseded_queries"}}
CHECKPOINT_SCHEMA.update(window_id=meta_text, status=meta_text, query_plan_drift=meta_bool,
    stale_windows=meta_list(object_check({"window_id": meta_text, "window": WINDOW_CHECK,
                                        "pending_queries": meta_count, "action": meta_text})),
    provider_state=object_check({key: object_check(PROVIDER_SCHEMA) for key in {"Crossref", "OpenAlex", "arXiv"}}))
CHECKPOINT_SCHEMA["status"] = meta_enum("complete_for_configured_queries", "partial")
QUERY_SCHEMA = {key: meta_count for key in {"pages", "pages_this_run", "cached_pages", "requests_this_run",
    "records_seen", "records_unique", "max_pages", "page_size"}}
QUERY_SCHEMA.update({key: meta_text for key in {"provider", "query_id", "query", "filter", "status", "reason",
    "completion_scope", "query_status", "index_note", "window_id", "theme", "scope", "venue"}})
QUERY_SCHEMA.update({key: meta_bool for key in {"truncated", "resumable", "provider_paused", "access_blocked", "quota_exhausted"}})
QUERY_SCHEMA.update(provider_total=nullable(meta_count), observed_at=nullable(meta_number), retry_at=nullable(meta_number))
QUERY_SCHEMA.update(status=meta_enum("pending", "complete", "truncated", "error"),
                    query_status=meta_enum("complete_for_configured_query", "partial"))
STATS_SCHEMA = {key: meta_count for key in {"openalex", "crossref", "publication_date_rejected", "publication_date_unverified",
    "date_lookups", "date_lookups_deferred", "queries_planned", "queries_attempted", "queries_completed", "queries_deferred",
    "priority_dois_requested", "priority_dois_found", "journal_queries_attempted", "journal_queries_succeeded",
    "journal_records_seen", "journal_relevant", "journal_queries_planned", "journal_queries_deferred"}}
STATS_SCHEMA.update({key: meta_text for key in {"discovery_status", "configured_query_status", "coverage_note"}})
STATS_SCHEMA.update(discovery_status=meta_enum("complete", "partial"),
                    configured_query_status=meta_enum("complete_for_configured_queries", "partial"))
STATS_SCHEMA.update(crossref_provider_paused=meta_bool, checkpoint=object_check(CHECKPOINT_SCHEMA),
    provider_windows=meta_list(object_check(QUERY_SCHEMA)),
    search_scopes=meta_list(object_check({"theme": meta_text, "period": meta_text,
                                        "from": meta_day, "to": meta_day, "query": meta_text})),
    arxiv_publication_verification=object_check({
        **{key: meta_count for key in {"request_limit", "minimum_interval_seconds", "requests", "verified", "failures", "deferred"}},
        **{key: meta_text for key in {"provider", "purpose"}}, "status": meta_enum("complete", "partial")}))
SNAPSHOT_SCHEMA = {"checked_at": meta_time, "requests": meta_count, "scope": meta_text,
    "sources": meta_list(object_check({"source_id": meta_text,
                                      "status": meta_enum("ok", "partial", "blocked", "rate_limited", "unavailable",
                                                          "deferred_provider_pause", "deferred_budget"), "pages": meta_count,
                                      "retained_candidates": meta_count, "next_retry_at": nullable(meta_time)}))}
EDITORIAL_SOURCE_SCHEMA = {key: meta_text for key in {"source_id", "name", "status", "reason", "error_type", "error", "retry_after"}}
EDITORIAL_SOURCE_SCHEMA.update({key: meta_count for key in {"pages", "returned", "accepted", "cached_candidates", "cached_evidence_rows", "http_status"}})
EDITORIAL_SOURCE_SCHEMA.update(feed_url=meta_url, warnings=meta_list(lambda x: meta_text(x, 160), 32),
    oldest_original_date=meta_day, newest_original_date=meta_day,
    rejected=object_check({key: meta_count for key in {"conflicting_original_publication_dates", "duplicate", "not_topical",
        "original_publication_date_missing", "outside_previous_week", "publisher_url_unverified"}}),
    snapshot_coverage=object_check({"snapshots_during_publication_week": meta_count,
        "largest_unobserved_interval_hours": meta_number, "coverage_claim": meta_text}))
EDITORIAL_SOURCE_SCHEMA["status"] = meta_enum("ok", "partial", "deferred", "failed")
EDITORIAL_SCHEMA = {key: meta_count for key in {"schema_version", "accepted", "quarantined", "full_articles_retrieved", "conflicting_new_records"}}
EDITORIAL_SCHEMA.update({key: meta_text for key in {"date_policy", "scope", "status"}})
EDITORIAL_SCHEMA["status"] = meta_enum("partial", "completed_configured_sources")
EDITORIAL_SCHEMA["full_articles_retrieved"] = lambda value: metadata_require(type(value) is int and value == 0)
EDITORIAL_SCHEMA.update(checked_on=meta_day, publication_window=WINDOW_CHECK,
    source_type_counts=object_check({key: meta_count for key in {"journalism", "opinion", "policy", "analysis"}}),
    sources=meta_list(object_check(EDITORIAL_SOURCE_SCHEMA)),
    verified_existing_records=meta_list(object_check({"url": meta_url, "published": meta_day,
        "publication_date_provenance": meta_provenance, "discovery_provenance": object_check(DISCOVERY_SCHEMA)})),
    conflicting_existing_records=meta_list(object_check({"url": meta_url, "stored_publication_date": meta_day,
        "conflicting_evidence": meta_list(meta_provenance, 128)})))


def correction(value):
    metadata_require(type(value) in (list, tuple) and len(value) == 2)
    meta_day(value[0]); meta_provenance(value[1])


def validate_packet_metadata(packet):
    """Validate every persisted subtree, including old snapshots, without repair."""
    try:
        coverage = {"configured_query_status": meta_enum("complete_for_configured_queries", "partial"), "closeout_required": meta_bool,
            "closeout_pass": nullable(lambda x: metadata_require(x in {"initial", "late_index"})),
            "closeout_passes": object_check({key: object_check({"started_at": meta_time}, {"started_at"})
                                            for key in {"initial", "late_index"}}),
            "closeout_started_at": nullable(meta_time), "coverage_note": lambda x: metadata_require(x == COVERAGE_NOTE),
            "academic_requests_this_run": meta_count,
            "academic": meta_list(object_check({"window": WINDOW_CHECK, "checkpoint": object_check(CHECKPOINT_SCHEMA),
                "general": object_check(STATS_SCHEMA), "journals": object_check(STATS_SCHEMA)}), 7),
            "publisher_snapshots": object_check(SNAPSHOT_SCHEMA), "editorial": object_check(EDITORIAL_SCHEMA),
            "errors": meta_list(lambda x: meta_text(x, 1024)),
            "publication_date_corrections": lambda x: meta_map(x, correction,
                lambda key: metadata_require(type(key) is str and len(key) <= 2048 and
                    re.fullmatch(r"10\.\d{4,9}/\S+", key, re.I) is not None), 50000)}
        fields = {"schema_version": meta_count, "kind": meta_text, "observation_at": meta_time,
            "target_publication_window": object_check({key: WINDOW_SCHEMA[key] for key in {"from", "to", "timezone"}},
                                                      {"from", "to", "timezone"}),
            "phase": meta_text, "status": meta_text, "date_eligibility": meta_text,
            "public_eligible": meta_false, "source_checked": meta_false, "approved": meta_false,
            "source_text_saved": meta_false,
            "run": object_check({"date": meta_day, "mode": meta_text, "publication_window": WINDOW_CHECK},
                                {"date", "mode", "publication_window"}),
            "items": meta_list(validate_metadata_record, 50000), "quarantine": meta_list(validate_quarantine, 50000),
            "coverage": object_check(coverage)}
        meta_object(packet, fields, set(fields) - {"source_text_saved"})
        metadata_require(len(json.dumps(packet, ensure_ascii=False, allow_nan=False).encode()) <= MAX_PACKET_BYTES)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError):
        raise ValueError(METADATA_ERROR) from None

def record_key(row):
    if row.get("kind") == "scholarly":
        return update.key(row)
    return "url:" + editorial.url_key(row.get("url", ""))

def atomic_save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class BoundedDiscoveryState(DiscoveryState):
    """Share durable provider state, with a total request/deadline run ceiling."""
    def __init__(self, *args, budget, **kwargs):
        self.budget = budget
        super().__init__(*args, max_attempts=1, max_inline_wait=0, **kwargs)

    def fetch(self, provider, url, request):
        if self.budget["remaining"] <= 0 or time.monotonic() >= self.budget["deadline"]:
            raise ProviderDeferred(provider, "Preparation request/time budget reached")
        def bounded_request(value):
            self.budget["remaining"] -= 1
            return request(value)
        return super().fetch(provider, url, bounded_request)

def merge_candidates(records, candidates, corrections, now, state):
    """Reconcile metadata without overwriting prepared source analysis or receipts."""
    for row in records.values():
        evidence = corrections.get(doi_id(row.get("doi")))
        if evidence:
            update.apply_publication_evidence(row, *evidence)
    # Preserve the actual provider-observation time even when replaying a cursor.
    observations = {}
    for query in state.current["queries"].values():
        if query.get("observed_at") is None:
            continue
        stamp = dt.datetime.fromtimestamp(query["observed_at"], dt.timezone.utc).isoformat()
        for work in query["rows"].values():
            doi = doi_id(work.get("DOI") or work.get("doi"))
            title = work.get("title") or ""
            if isinstance(title, list):
                title = title[0] if title else ""
            key = update.key({"doi": doi, "title": title})
            observations[key] = max(observations.get(key, stamp), stamp)
    for row in candidates:
        if not update.relevant(row, now.date()):
            continue
        row = deepcopy(row)
        evidence = corrections.get(doi_id(row.get("doi")))
        if evidence:
            update.apply_publication_evidence(row, *evidence)
        key = record_key(row)
        if key not in records:
            records[key] = row
        else:
            prior = records[key]
            if row.get("publication_date_provenance"):
                update.apply_publication_evidence(prior, row.get("published", ""), row["publication_date_provenance"])
            if len(row.get("abstract_text", "")) > len(prior.get("abstract_text", "")):
                for field in ("abstract_text", "abstract_source", "preview"):
                    prior[field] = row.get(field, "")
        if key in observations:
            records[key]["metadata_observed_at"] = observations[key]
        records[key].setdefault("preparation_first_seen_at", now.isoformat())

def prepare(root=ROOT, *, now=None, closeout=False, closeout_pass=None, max_requests=48, max_feed_requests=24,
            max_pages=1, page_size=100, time_budget=240, feeds=None, manifest=None,
            academic_request=None, feed_fetcher=None):
    """Collect one bounded pass; caller must hold the common data-writer lock.

    No provider/model calls are made at import. Injectable transport functions
    support offline tests. Daily academic slices replay once complete; a distinct
    closeout generation starts from the provider head only after Sunday ends.
    """
    now = utc(now)
    if min(max_requests, max_feed_requests, max_pages, time_budget) < 0:
        raise ValueError("Preparation budgets cannot be negative")
    phase = "closed" if closeout else "preparing"
    window = target_window(now, phase)
    data = Path(root) / "data"
    folder = data / "weekly-preparation" / window["from"]
    packet_path = folder / "packet.json"
    if packet_path.exists() and packet_path.stat().st_size > MAX_PACKET_BYTES:
        raise ValueError(METADATA_ERROR)
    previous = strict_json_loads(packet_path.read_text()) if packet_path.exists() else None
    if previous:
        # Validate against its own actual observation: an open packet is expected
        # to become a closed packet at the next week's first real closeout.
        validate_packet(previous, previous["observation_at"])
        if previous["target_publication_window"] != window or utc(previous["observation_at"]) > now:
            raise ValueError("Stale/mismatched preparation packet")
    if closeout_pass is not None and (not closeout or closeout_pass not in {"initial", "late_index"}):
        raise ValueError("An explicit closeout pass requires --closeout")
    passes = deepcopy((previous or {}).get("coverage", {}).get("closeout_passes", {}))
    closeout_pass = (closeout_pass or ("late_index" if "late_index" in passes else "initial")) if closeout else None
    if closeout_pass == "initial" and "late_index" in passes:
        raise ValueError("Resume the later closeout generation; do not regress to initial")
    if closeout_pass == "late_index":
        closing = dt.datetime.combine(publication_date(window["to"]) + dt.timedelta(days=1), dt.time(), dt.timezone.utc)
        if "initial" not in passes or now < closing + dt.timedelta(hours=6):
            raise ValueError("Late-index reconciliation requires initial closeout and Monday 06:00 UTC")
    if closeout:
        passes.setdefault(closeout_pass, {"started_at": now.isoformat()})
    records = {record_key(row): deepcopy(row) for row in (previous or {}).get("items", [])}
    quarantine = deepcopy((previous or {}).get("quarantine", []))
    # Full candidate records stay recoverable for later date reconciliation;
    # URL-only feed diagnostics never masquerade as records.
    for row in quarantine:
        if row.get("kind") in {"scholarly", "nonacademic"}:
            records.setdefault(record_key(row), deepcopy(row))
    previous_records = deepcopy(records)
    budget = {"remaining": max_requests, "deadline": time.monotonic() + time_budget}
    start, end = map(publication_date, (window["from"], window["to"]))
    mode = ("closeout_late_index" if closeout_pass == "late_index" else "closeout") if closeout else "preparation"
    slices = [(start, end)] if closeout else [(start + dt.timedelta(days=i), start + dt.timedelta(days=i))
                    for i in range((now.date() - start).days + 1)]
    academic_reports, errors = [], []
    all_corrections = deepcopy((previous or {}).get("coverage", {}).get("publication_date_corrections", {}))
    for begin, stop in slices:
        bounds = {"from": begin.isoformat(), "to": stop.isoformat()}
        state = BoundedDiscoveryState(data / "academic-discovery-state.json", mode=mode,
                    window=bounds, budget=budget, now=lambda: now.timestamp())
        # Production collectors use this injected transport without replacing TODAY.
        # A local callable parameter avoids any global monkeypatching/concurrency.
        candidates, issues, stats = update.discover(mode=mode, state=state, observed_on=now,
                    publication_window=bounds, max_pages=max_pages, page_size=page_size,
                    metadata_request=academic_request)
        priority, extra_issues, priority_stats = discover_priority(academic_request or update.request,
                    now.date(), mode=mode, state=state, manifest=manifest,
                    publication_window=bounds, max_pages=max_pages, page_size=page_size)
        corrections = stats.pop("publication_date_corrections", {})
        for doi, evidence in priority_stats.pop("publication_date_corrections", {}).items():
            corrections[doi] = reconcile_publication_evidence(corrections.get(doi), evidence)
        for doi, evidence in corrections.items():
            all_corrections[doi] = reconcile_publication_evidence(all_corrections.get(doi), evidence)
        corrections = {doi: all_corrections[doi] for doi in corrections}
        pending = stats.pop("publication_date_quarantine", []) + priority_stats.pop("publication_date_quarantine", [])
        merge_candidates(records, candidates + priority + pending, corrections, now, state)
        errors.extend(issues + extra_issues)
        academic_reports.append({"window": bounds, "checkpoint": state.summary(),
                                 "general": stats, "journals": priority_stats})
    selected_feeds = editorial.FEEDS if feeds is None else feeds
    cache_path = data / "editorial-feed-cache.json"
    cache = feeds_cache.load_cache(cache_path, selected_feeds)
    def observe(feed, items):
        for item in items:
            if editorial.eligible(item) and not item.get("date"):
                quarantined = editorial.quarantine_item(item, feed, "original_publication_date_missing")
                quarantined["observed_at"] = now.isoformat()
                quarantine.append(quarantined)
    cache, capture = feeds_cache.capture(cache, feeds=selected_feeds, now=now, fetcher=feed_fetcher,
        max_requests=max_feed_requests, deadline_seconds=max(0, budget["deadline"] - time.monotonic()),
        checkpoint=lambda value: feeds_cache.save_cache(cache_path, value, selected_feeds), observer=observe)
    bounds = {"from": window["from"], "to": min(end, now.date()).isoformat()}
    cached = feeds_cache.candidate_items(cache, selected_feeds, now=now, mode=mode, publication_window=bounds)
    coverage = feeds_cache.coverage_report(cache, selected_feeds, now=now, mode=mode, publication_window=bounds)
    editorial_rows = [row for row in records.values() if row.get("kind") == "nonacademic"]
    added, report, pending = editorial.collect(editorial_rows, now=now, feeds=selected_feeds, searches=[],
        sleep=lambda _: None, live=False, cached_items=cached, cache_coverage=coverage,
        mode=mode, publication_window=bounds)
    for row in added:
        row["metadata_observed_at"] = row.get("discovery_provenance", {}).get("metadata_snapshot_observed_at", now.isoformat())
        row["preparation_first_seen_at"] = now.isoformat()
        records[record_key(row)] = row
    editorial.apply_discovery_evidence(list(records.values()), report)
    quarantine.extend(pending)
    preserve_unchanged_check_times(records, previous_records)
    items = []
    for row in records.values():
        if weekly_eligible(row, start, min(end, now.date())):
            row.pop("acquisition_status", None)
            items.append(row)
        else:
            quarantine.append(row)
    # Retain unresolved evidence, even after a later source/date resolution; the
    # matching candidate's presence signals resolution without deleting history.
    quarantine = list({hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(): row
                       for row in quarantine}.values())
    academic_complete = all(r["checkpoint"]["status"] == "complete_for_configured_queries"
                            and r["general"]["discovery_status"] == "complete"
                            and r["journals"]["discovery_status"] == "complete" for r in academic_reports)
    feed_complete = all(x["status"] == "ok" for x in capture["sources"])
    # Calendar is necessarily open during preparation; delayed-index completeness
    # is never claimed even after all configured query snapshots finish.
    status = "prepared" if academic_complete and feed_complete and not quarantine else "partial"
    packet = {"schema_version": 1, "kind": "weekly_preparation", "observation_at": now.isoformat(),
        "target_publication_window": window, "phase": phase, "status": status,
        "date_eligibility": "verified_original_publication_date_only", "public_eligible": False,
        "source_checked": False, "approved": False,
        "run": {"date": now.date().isoformat(), "mode": "preparation", "publication_window": window},
        "items": sorted((metadata_record(row) for row in items), key=record_key),
        "quarantine": [metadata_record(row) if row.get("kind") in {"scholarly", "nonacademic"}
                       else deepcopy(row) for row in quarantine],
        "coverage": {"configured_query_status": "complete_for_configured_queries" if academic_complete else "partial",
            "closeout_required": not closeout, "closeout_pass": closeout_pass, "closeout_passes": passes,
            "closeout_started_at": ((previous or {}).get("coverage", {}).get("closeout_started_at") or now.isoformat()) if closeout else None,
            "coverage_note": COVERAGE_NOTE, "academic_requests_this_run": max_requests - budget["remaining"],
            "academic": academic_reports, "publisher_snapshots": capture, "editorial": report, "errors": errors,
            "publication_date_corrections": all_corrections}}
    validate_packet(packet, now)
    stamp = now.strftime("%Y%m%dT%H%M%S%fZ")
    content_hash = hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()[:12]
    atomic_save(folder / "snapshots" / (stamp + "-" + content_hash + ".json"), packet)
    atomic_save(packet_path, packet)
    atomic_save(folder / "status.json", {key: packet[key] for key in ("observation_at", "phase", "status",
        "target_publication_window", "public_eligible", "source_checked", "approved")})
    return packet


def adopt_to_canonical(root, packet, now=None):
    """Write validated closeout metadata; each file replacement is atomic.

    Caller holds the common writer lock. The packet remains durable if a crash
    interrupts these writes, so retry adoption rather than repeat discovery.
    No multi-file filesystem transaction or public approval is claimed.
    """
    now = utc(now)
    data = Path(root) / "data"
    path = data / "library.json"
    library = strict_json_loads(path.read_text()) if path.exists() else []
    result = adopt_closed_packet(packet, library, now)
    atomic_save(data / "library.json", result["library"])
    atomic_save(data / "weekly.json", result["weekly"])
    atomic_save(data / "preparation-discovery-quarantine.json", result["quarantine"])
    runs_path = data / "runs.json"
    runs = strict_json_loads(runs_path.read_text()) if runs_path.exists() else []
    run = result["weekly"]["run"]
    atomic_save(runs_path, [r for r in runs if r.get("date") != run["date"]][-51:] + [run])
    result["checkpoint_adoption"] = adopt_closeout_checkpoint(data / "academic-discovery-state.json", now,
        closeout_pass=packet["coverage"].get("closeout_pass") or "initial")
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closeout", action="store_true", help="Fresh post-Sunday reconciliation for the actual previous UTC week")
    parser.add_argument("--closeout-pass", choices=("initial", "late_index"))
    parser.add_argument("--adopt", action="store_true", help="After closeout, adopt metadata into canonical library/weekly; never approve readings")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--max-requests", type=int, default=48)
    parser.add_argument("--max-feed-requests", type=int, default=24)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--time-budget", type=int, default=240)
    args = parser.parse_args()
    if args.adopt and not args.closeout:
        parser.error("--adopt requires a real --closeout")
    packet = prepare(args.root, closeout=args.closeout, closeout_pass=args.closeout_pass, max_requests=args.max_requests,
        max_feed_requests=args.max_feed_requests, max_pages=args.max_pages, time_budget=args.time_budget)
    if args.adopt:
        adopt_to_canonical(args.root, packet)
    print(json.dumps({"window": packet["target_publication_window"], "phase": packet["phase"],
                      "status": packet["status"], "candidates": len(packet["items"]),
                      "quarantined": len(packet["quarantine"]), "public_eligible": False}))


if __name__ == "__main__":
    main()
