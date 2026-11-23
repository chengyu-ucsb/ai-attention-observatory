"""Trace the basis of public research summaries and prioritize unresolved readings."""
from collections import Counter
import json
from pathlib import Path
import re


SECTION_KEYS = ("methods", "results", "discussion", "limitations")


def distinct_summary_roles(values):
    """An empty optional role is fine; pasted fields and pending notes are not prose."""
    roles = [" ".join(value.casefold().split()).rstrip(".!? ") for value in values
             if isinstance(value, str) and value.strip()]
    placeholders = {"editorial note", "source: editorial note", "tbd", "pending", "not provided"}
    return len(roles) == len(set(roles)) and not placeholders.intersection(roles)


def has_article_sections(record):
    """A source locator alone is not a reading of article text.

    This validates presence only, not completeness, quality, or reuse rights.
    A partial extraction stays partial even when it has usable paragraphs.
    """
    source = record.get("verified_article_review") or record.get("analysis") or {}
    if not isinstance(source, dict) or not source.get("fulltext_url"):
        return False
    for key in SECTION_KEYS:
        value = source.get(key)
        if isinstance(value, str):
            value = re.sub(r"<[^>]+>", " ", value)
            if len(value.strip()) >= 20 and len(re.findall(r"[^\W\d_]+", value)) >= 4:
                return True
    return False


def has_machine_sections(record):
    """Count extracted article prose separately from original reviewed paraphrases."""
    source = record.get("analysis") or {}
    return (isinstance(source, dict) and not source.get("original_paraphrases_only")
            and has_article_sections({"analysis": source}))


def identity(record):
    return (record.get("doi") or "").lower() or record.get("url") or record.get("title")


def depth_audit(records):
    findings = Counter()
    gaps = []
    editorial_queue = []
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
        # Editorial reconstruction and document acquisition are different work.
        # A source may be fully accessible yet still expose only selected sentences.
        machine = reading.get("machine_account") or {}
        has_checked_machine_account = (machine.get("review_status") == "machine_checked_not_independently_reviewed"
                                       and bool(machine.get("source_url")))
        if (digest.get("status") == "automatically_condensed_source_text"
                and not reading.get("original_summary") and not record.get("verified_article_review")
                and not has_checked_machine_account):
            reasons = ["extracts_only"]
            if not digest.get("finding") and not digest.get("explain"):
                reasons.append("no_result_or_source_context")
            if not digest.get("approach"):
                reasons.append("no_selected_approach")
            if level == "full_text" and basis == "abstract":
                reasons.append("result_only_in_abstract")
            editorial_queue.append({"id": identity(record), "title": record.get("title", ""),
                                    "reading_level": level, "reasons": reasons})
        if level == "abstract":
            reason = "abstract_only_open_link" if open_link else "abstract_only"
        elif level == "full_text" and not reading.get("original_summary") and not has_article_sections(record):
            reason = "full_text_label_without_article_sections"
        elif level == "full_text" and basis == "abstract":
            reason = "finding_from_abstract_despite_article_sections"
        elif level == "full_text" and basis == "none" and reading.get("research_type") not in (
                "conceptual_framework", "editorial", "perspective", "theory"):
            reason = "no_result_selected_check_article_type_and_sections"
        else:
            continue
        counts[reason] += 1
        gaps.append({"id": identity(record), "title": record.get("title", ""), "reason": reason,
                     "open_access_url": open_link, "reading_level": level,
                     "finding_source": basis})
    return {"counts": dict(sorted(counts.items())), "finding_basis": dict(sorted(findings.items())),
            "summary_review": sorted(editorial_queue, key=lambda row: (-len(row["reasons"]), row["id"])),
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
