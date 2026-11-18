"""Trace the basis of public research summaries and prioritize unresolved readings."""
from collections import Counter
import json
from pathlib import Path


def identity(record):
    return (record.get("doi") or "").lower() or record.get("url") or record.get("title")


def depth_audit(records):
    findings = Counter()
    gaps = []
    counts = Counter()
    for record in records:
        if record.get("kind") != "scholarly":
            continue
        reading = record.get("reading") or {}
        digest = reading.get("digest") or {}
        level = reading.get("level")
        basis = digest.get("finding_source") or "none"
        counts["scholarly_readings"] += 1
        findings[basis] += 1
        open_link = record.get("open_access_url") or ""
        if level == "abstract":
            reason = "abstract_only_open_link" if open_link else "abstract_only"
        elif level == "full_text" and basis == "abstract":
            reason = "finding_from_abstract_despite_article_sections"
        elif level == "full_text" and basis == "none" and reading.get("research_type") not in (
                "conceptual_framework", "editorial", "perspective", "theory"):
            reason = "no_result_selected_check_article_type_and_sections"
        else:
            continue
        counts[reason] += 1
        gaps.append({"id": identity(record), "title": record["title"], "reason": reason,
                     "open_access_url": open_link, "reading_level": level,
                     "finding_source": basis})
    return {"counts": dict(sorted(counts.items())), "finding_basis": dict(sorted(findings.items())),
            "records": sorted(gaps, key=lambda x: (x["reason"], x["id"]))}


def recovery_ids(data_dir):
    audit_path = Path(data_dir) / "source-quality-audit.json"
    if not audit_path.is_file():
        return set()
    report = json.loads(audit_path.read_text(encoding="utf-8")).get("reading_depth") or {}
    return {row["id"] for row in report.get("records", []) if row.get("id")}


def reserve_recovery_slot(candidates, public_gaps, limit):
    """Reserve one slot in a multi-article historical batch; keep the oldest first."""
    if limit < 2 or not public_gaps or len(candidates) <= limit:
        return
    if any(identity(record) in public_gaps for record in candidates[:limit]):
        return
    for index in range(limit, len(candidates)):
        if identity(candidates[index]) in public_gaps:
            candidates.insert(limit - 1, candidates.pop(index))
            return
