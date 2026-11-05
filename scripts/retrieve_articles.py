"""Retrieve a project bibliography without loading a language model.

Writes a resumable metadata report and, only when explicitly requested, stages
verified PDF bytes outside the public repository. Staging is NOT a cloud save.
The caller must upload to its authoritative private destination and verify it.
No institutional login, author email, or document-delivery request is sent.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from full_document_access import doi, retrieve

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
TERMINAL = {"full_document_retrieved"}


def utcnow():
    return datetime.now(timezone.utc)


def record_key(record):
    identifier = doi(record.get("doi"))
    return identifier or record.get("url") or "title:" + sha256(
        record.get("title", "").strip().casefold().encode()).hexdigest()[:20]


def fingerprint(record):
    # A new verified candidate or corrected identity immediately reopens a row.
    keys = ("doi", "title", "url", "open_access_url", "fulltext_candidates")
    payload = {k: record.get(k) for k in keys if record.get(k)}
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def input_records(payload):
    records = payload.get("records", []) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("Input must be a JSON list or an object containing records")
    unique = {}
    for original in records:
        if not isinstance(original, dict) or not str(original.get("title", "")).strip():
            raise ValueError("Each record needs an explicit article title")
        row = dict(original)
        row["doi"] = doi(row.get("doi"))
        row.setdefault("kind", "scholarly")
        row["projects"] = sorted(set(row.get("projects") or [row.get("project", "unassigned")]))
        key = record_key(row)
        if key in unique:
            previous = unique[key]
            if previous["title"].strip().casefold() != row["title"].strip().casefold():
                raise ValueError("Conflicting titles for one identity; verify version relationships first")
            previous["projects"] = sorted(set(previous["projects"] + row["projects"]))
            candidates = previous.get("fulltext_candidates", []) + row.get("fulltext_candidates", [])
            previous["fulltext_candidates"] = list({json.dumps(c, sort_keys=True): c for c in candidates}.values())
        else:
            unique[key] = row
    return list(unique.values())


def outcome(document, diagnostics):
    if document is not None:
        return document.coverage.get("evidence_status", "partial_full_text")
    states = [str(d.get("status", "")) for d in diagnostics]
    if "retrieval_error" in states:
        return "retrieval_error"
    if any("identity" in x for x in states):
        return "identity_review_required"
    if any("401" in x for x in states):
        return "authentication_required"
    if any("429" in x or "rate_limit" in x for x in states):
        return "provider_limited"
    if any("403" in x or "robots" in x or "challenge" in x for x in states):
        return "source_blocked"
    if any("host" in x or "redirect" in x for x in states):
        return "source_review_required"
    if any(x in ("insufficient_document_text", "insufficient_article_body") for x in states):
        return "extraction_incomplete"
    return "not_retrieved"


def next_step(status):
    return {
        "full_document_retrieved": "Verify cloud save, then check relevant tables, figures and article claims.",
        "partial_full_text": "Find a complete PDF or XML source; keep the reading labeled partial.",
        "identity_review_required": "Check title, authors and explicit preprint-to-publication relationship.",
        "authentication_required": "Open through an authorized institutional session and save the attachment privately.",
        "provider_limited": "Retry after provider backoff; try an independently verified source meanwhile.",
        "source_blocked": "Try an independent repository or an authorized institutional session; do not bypass the block.",
        "source_review_required": "Verify the exact scholarly host or redirect before adding a candidate.",
        "extraction_incomplete": "Inspect the document and determine whether OCR or a different format is needed.",
        "not_retrieved": "Search the exact title in repositories, then prepare an institutional or author request if needed.",
        "retrieval_error": "Inspect the retrieval error and retry independently of other records.",
    }[status]


def retry_at(status, now, diagnostics):
    if status in TERMINAL:
        return None
    delay = 1 if status in {"provider_limited", "retrieval_error"} else 7 if status in {
        "source_blocked", "partial_full_text", "extraction_incomplete"} else 30
    seconds = max([delay * 86400] + [int(d.get("retry_after_seconds") or 0) for d in diagnostics])
    return (now + timedelta(seconds=seconds)).isoformat()


def due(record, previous, now, force=False):
    if force or not previous or previous.get("input_fingerprint") != fingerprint(record):
        return True
    if previous.get("status") in TERMINAL:
        return False
    try:
        return datetime.fromisoformat(previous["next_retry_at"]) <= now
    except (KeyError, TypeError, ValueError):
        return True


def private_path(path):
    path = Path(path).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("Private acquisition outputs must be outside the public repository")
    return path


def stage_pdf(document, record, directory):
    raw = getattr(document, "source_bytes", None)
    if not raw or not raw.startswith(b"%PDF"):
        return None
    directory = private_path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    digest = sha256(raw).hexdigest()
    stem = re.sub(r"[^A-Za-z0-9]+", "-", record.get("title", "article")).strip("-")[:90]
    target = directory / (stem + "-" + digest[:12] + ".pdf")
    if not target.exists():
        target.write_bytes(raw)
    if sha256(target.read_bytes()).hexdigest() != digest:
        raise ValueError("Staged PDF checksum verification failed")
    return {"staged_path": str(target), "sha256": digest, "bytes": len(raw),
            "cloud_save_verified": False,
            "storage_status": "staged_awaiting_verified_cloud_save"}


def report_for(results, now, processed):
    counts = dict(Counter(x["status"] for x in results))
    return {"schema_version": SCHEMA_VERSION, "checked_at": now.isoformat(),
            "scope": "Named input bibliography only; not a corpus-wide recovery rate.",
            "summary": {"records": len(results), "attempted_this_run": processed,
                        "by_status": counts},
            "research_review_completed": False,
            "institutional_access_used": False, "messages_sent": False,
            "report_cloud_save_verified": False,
            "records": results}


def write_report(path, report):
    path = private_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def process(records, previous=None, *, limit=12, force=False, providers=None,
            stage_directory=None, retriever=retrieve, now=None, checkpoint=None):
    now = now or utcnow()
    prior = {x["record_key"]: x for x in (previous or {}).get("records", [])}
    results, processed = [], 0
    for record in records:
        key = record_key(record)
        old = prior.get(key)
        if not due(record, old, now, force) or processed >= limit:
            if old:
                row = dict(old)
                row["projects"] = record["projects"]
                results.append(row)
            else:
                results.append({"record_key": key, "title": record["title"],
                                "doi": record.get("doi", ""), "projects": record["projects"],
                                "status": "not_attempted", "input_fingerprint": fingerprint(record),
                                "next_retry_at": now.isoformat()})
            continue
        try:
            document, diagnostics = retriever(record, providers=providers)
        except Exception as exc:
            # One bad source must not discard the completed bibliography.
            # Error messages can contain authenticated URLs, so retain only type.
            document, diagnostics = None, [{"provider": "retriever", "status": "retrieval_error",
                                           "error_type": type(exc).__name__, "retryable": True}]
        processed += 1
        status = outcome(document, diagnostics)
        row = {"record_key": key, "title": record["title"], "doi": record.get("doi", ""),
               "projects": record["projects"], "status": status,
               "input_fingerprint": fingerprint(record), "checked_at": now.isoformat(),
               "attempt_count": (old or {}).get("attempt_count", 0) + 1,
               "next_retry_at": retry_at(status, now, diagnostics),
               "next_action": next_step(status), "attempts": diagnostics,
               "research_review_completed": False, "cloud_save_verified": False}
        if document is not None:
            row["coverage"] = document.manifest()
            if stage_directory:
                archive = stage_pdf(document, record, stage_directory)
                if archive:
                    row["attachment"] = archive
                    row["coverage"]["source_text_saved"] = True
                    row["coverage"]["source_storage_scope"] = "private_staging_outside_public_repository"
        results.append(row)
        if checkpoint:
            # Preserve all remaining previous rows until their turn in this run.
            seen = {x["record_key"] for x in results}
            rest = [prior[record_key(r)] for r in records if record_key(r) in prior and record_key(r) not in seen]
            checkpoint(report_for(results + rest, now, processed))
    return report_for(results, now, processed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--stage-pdfs", type=Path)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--known-sources-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    output = private_path(args.report)
    if args.stage_pdfs:
        private_path(args.stage_pdfs)
    records = input_records(json.loads(args.manifest.read_text()))
    prior = json.loads(output.read_text()) if output.exists() else None
    report = process(records, prior, limit=max(1, min(args.limit, 100)), force=args.force,
                     providers=[] if args.known_sources_only else None,
                     stage_directory=args.stage_pdfs,
                     checkpoint=lambda r: write_report(output, r))
    write_report(output, report)
    print(json.dumps(report["summary"], sort_keys=True))
    print("Results are staged; verify the private cloud save before delivery.")


if __name__ == "__main__":
    main()
