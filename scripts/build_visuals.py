"""Stable, source-grounded visual metadata for every new public reading.

This runs for each ingestion or enrichment update, not a fixed list of DOIs.
It deliberately does NOT infer a sample size, compute a statistic, draw an
effect-size chart, infer causation, or reproduce copyrighted paper figures.
"""
from __future__ import annotations
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
from article_art import canonical_identity
from verified_full_article_notes import note_digest

REVIEWED_VISUALS = Path(__file__).resolve().parents[1] / "data/reviewed-visuals.json"


def visual_digest(visual: dict) -> str:
    body = {key: value for key, value in visual.items() if key != "review"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


@lru_cache(maxsize=1)
def reviewed_registry() -> dict:
    try:
        payload = json.loads(REVIEWED_VISUALS.read_text())
        if (isinstance(payload, dict) and payload.get("schema_version") == 1
                and isinstance(payload.get("visuals"), list)):
            return payload
    except (OSError, ValueError):
        pass
    return {}


def reviewed_visuals() -> list:
    return reviewed_registry().get("visuals", [])


def matches_reading(record: dict, visual: dict) -> bool:
    reading = record.get("reading") or {}
    source = visual["source"]
    if visual.get("doi"):
        if visual["doi"] != record.get("doi"):
            return False
    elif not visual.get("record_url") or visual["record_url"] != record.get("url"):
        return False
    if reading.get("original_summary"):
        return (visual["reading_id"] == reading.get("original_summary_id")
                and bool(re.fullmatch(r"[0-9a-f]{64}", source.get("sha256", "")))
                and all(source[key] == reading.get("source_" + key)
                        for key in ("url", "version", "sha256")))
    notes = record.get("verified_article_review") or {}
    return (visual["reading_id"] == "verified-notes" and notes.get("original_paraphrases_only")
            and notes.get("source_checked") and source["url"] == notes.get("fulltext_url")
            and source["version"] == notes.get("source_version")
            and source.get("notes_sha256") == notes.get("note_sha256") == note_digest(notes))


def valid_bar_chart(chart, rows, headers) -> bool:
    if not isinstance(chart, dict) or chart.get("kind") != "bar" or len(headers) != 2:
        return False
    maximum = chart.get("maximum")
    if (type(maximum) not in (int, float) or not math.isfinite(maximum) or maximum <= 0
            or not isinstance(chart.get("unit"), str) or not compact(chart["unit"], 60)):
        return False
    return len(rows) >= 2 and all(isinstance(row[1], str)
                                  and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", row[1])
                                  and float(row[1]) <= maximum for row in rows)


def reviewed_visual(record: dict, candidates: list | None = None) -> dict | None:
    """Only attach a checked visual to the exact source version it describes.

    The content hash detects later edits; it does not establish independent
    review. These original factual comparisons contain no copied source image.
    """
    for visual in reviewed_visuals() if candidates is None else candidates:
        try:
            source, review = visual["source"], visual["review"]
            if (visual["kind"] != "reviewed_comparison"
                    or not matches_reading(record, visual)
                    or visual["rights"] != "original_factual_display_no_source_image"
                    or review["kind"] != "ai_source_check"
                    or review["status"] != "checked"
                    or review["payload_sha256"] != visual_digest(visual)):
                continue
            if not source["url"].startswith("https://"):
                continue
            if not all(compact(visual.get(key), 600) for key in ("title", "description", "caption")):
                continue
            if not all(compact(source.get(key), 200) for key in ("locator", "attribution")):
                continue
            headers, rows = visual["headers"], visual["rows"]
            if (not isinstance(headers, list) or not 2 <= len(headers) <= 4
                    or not isinstance(rows, list) or not 1 <= len(rows) <= 6
                    or not all(compact(cell, 100) for cell in headers)
                    or not all(isinstance(row, list) and len(row) == len(headers)
                               and all(compact(cell, 180) for cell in row) for row in rows)):
                continue
            if "chart" in visual and not valid_bar_chart(visual["chart"], rows, headers):
                continue
            return deepcopy(visual)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return None


def compact(value: object, limit: int = 600) -> str:
    """Reject incomplete or boilerplate extracts rather than truncate claims."""
    text = " ".join(str(value or "").strip().split())
    if (not text or len(text) > limit or text.endswith("…") or
            text.endswith("...") or text.lower().startswith(("the source describes",
                "one interpretation is that", "plato's dialogues show that"))):
        return ""
    return text


def visual_spec(record: dict) -> dict:
    """Annotate one record with a safe visual type and source-derived facts.

    A topical image is still assigned by the website's shared image selector.
    This metadata controls additional study graphics only when real excerpts
    have survived the source-aware digest checks.
    """
    reading = record.get("reading") or {}
    checked = reviewed_visual(record)
    if checked:
        return checked
    if reading.get("original_summary"):
        # Avoid mixing old DOI-specific/extracted graphics with a versioned summary.
        return {"kind": "illustration_only", "reason": "original_summary_has_separate_evidence_locators"}
    digest = reading.get("digest") or {}
    if record.get("kind") != "scholarly":
        return {"kind": "illustration_only", "reason": "nonempirical_or_commentary"}

    approach = compact(digest.get("approach"), 600)
    finding = compact(digest.get("finding"), 600)
    limitation = compact(digest.get("limitation"), 600)
    basis = "full_text" if reading.get("level") == "full_text" else "abstract"
    finding_source = digest.get("finding_source")
    if finding_source not in ("full_text", "abstract", "editorial"):
        finding = ""
    # Don't convert an unsupported research question into an apparent finding.
    if not approach and not finding:
        return {"kind": "illustration_only", "reason": "insufficient_indexed_evidence"}

    edited = digest.get("status") == "editorially_written_from_indexed_sections"
    blocks = []
    if approach:
        blocks.append({"label": "Research approach", "text": approach, "source": digest.get("approach_source") or ("editorial" if edited else basis)})
    if finding:
        blocks.append({"label": "Reported finding", "text": finding, "source": finding_source})
    if limitation:
        blocks.append({"label": "What remains uncertain", "text": limitation, "source": digest.get("limitation_source") or ("editorial" if edited else basis)})
    if not blocks:
        return {"kind": "illustration_only", "reason": "insufficient_indexed_evidence"}
    return {
        "kind": "evidence_snapshot" if finding else "research_design",
        "basis": basis,
        "status": "edited" if digest.get("status") == "editorially_written_from_indexed_sections" else "indexed",
        "finding_source": finding_source if finding else "none",
        "blocks": blocks,
    }


# Keep locators in the editorial queue. Captions and unverified numbers never go
# into a generated chart, and a fresh build reconsiders changed source text.
VISUAL_REFERENCE = re.compile(r"\b(?:supplementary\s+)?(?:tables?|fig(?:ure)?s?\.?)\s+S?\d+[a-z]?(?:\s*[–−-]\s*S?\d+[a-z]?)?", re.I)


def find_adaptation(record: dict) -> dict:
    """Identify a real source locator or a previously checked adaptation."""
    reading = record.get("reading") or {}
    notes = record.get("verified_article_review") or {}
    analysis = record.get("analysis") or {}
    source_url = (reading.get("source_url") or notes.get("fulltext_url")
                  or (record.get("source_review") or {}).get("source_url")
                  or analysis.get("fulltext_url") or record.get("url") or "")
    # visual_spec has already checked the actual registry against this version.
    visual = record.get("visual") or {}
    if visual.get("kind") == "reviewed_comparison" and reviewed_visual(record, [visual]):
        return {"status": "ready", "reason": "source_checked_adaptation",
                "format": "bar_chart" if visual.get("chart") else "comparison_table",
                "source_url": visual["source"]["url"], "locators": [visual["source"]["locator"]]}
    # A corrected reading must bring its previous adaptation back to review
    # even if the revised notes no longer mention the original table.
    for entry in reviewed_visuals():
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), dict) or not entry["source"].get("locator"):
            continue
        if ((entry.get("doi") and entry["doi"] == record.get("doi"))
                or (entry.get("record_url") and entry["record_url"] == record.get("url"))):
            return {"status": "needs_review", "reason": "recheck_registered_adaptation",
                    "source_url": source_url, "locators": [entry["source"]["locator"]]}

    sections = list(notes.get("source_sections") or [])
    for field in (reading.get("evidence") or {}).values():
        if isinstance(field, list):
            sections.extend(entry.get("section") for entry in field if isinstance(entry, dict))
    sections = list(dict.fromkeys(s for s in sections if isinstance(s, str) and s.strip()))
    references = []
    for section in sections:
        references.extend(m.group() for m in VISUAL_REFERENCE.finditer(section))
    if not reading.get("original_summary") and not notes:
        for fig in analysis.get("figures") or []:
            if isinstance(fig, dict) and isinstance(fig.get("label"), str):
                references.extend(m.group() for m in VISUAL_REFERENCE.finditer(fig["label"]))
        for field in ("results", "methods", "discussion"):
            references.extend(m.group() for m in VISUAL_REFERENCE.finditer(analysis.get(field) or ""))

    if references and source_url:
        return {"status": "needs_review", "reason": "source_table_or_figure",
                "source_url": source_url, "locators": list(dict.fromkeys(references))[:6]}
    if sections and source_url:
        genre = record.get("reader_genre")
        if genre in ("conceptual", "proposal", "guide"):
            return {"status": "needs_review", "reason": "checked_explanation",
                    "format": "process_or_concept", "source_url": source_url,
                    "locators": sections[:3]}
        if genre in ("reporting", "opinion", "analysis") and (reading.get("digest") or {}).get("examples"):
            return {"status": "needs_review", "reason": "checked_examples", "format": "side_by_side",
                    "source_url": source_url, "locators": sections[:3]}
        if (reading.get("reported_findings") or notes.get("results")) and re.search(
                r"\b(?:compar\w+|differ\w+|groups?|versus|whereas)\b",
                reading.get("findings") or notes.get("results") or "", re.I):
            return {"status": "needs_review", "reason": "comparison_in_checked_text",
                    "format": "comparison_table", "source_url": source_url, "locators": sections[:3]}
    return {"status": "text_only",
            "reason": "abstract_only" if reading.get("level") == "abstract" else "no_located_comparison"}


def visual_assessment(record: dict, decisions: dict | None = None) -> dict:
    """A prose-only decision applies to a particular candidate and source."""
    candidate = find_adaptation(record)
    if candidate["status"] != "needs_review":
        return candidate
    source_fields = ("reading", "source_review", "editorial_notes", "abstract_text")
    evidence = {key: record.get(key) for key in source_fields}
    analysis = record.get("analysis") or {}
    evidence["sections"] = {key: analysis.get(key)
                            for key in ("methods", "results", "discussion", "limitations", "figures")}
    if record.get("verified_article_review"):
        evidence["notes_sha256"] = note_digest(record["verified_article_review"])
    identity = canonical_identity(record)
    fingerprint = hashlib.sha256(json.dumps([identity, candidate, evidence], sort_keys=True,
                                             ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    decisions = reviewed_registry().get("text_only", {}) if decisions is None else decisions
    decision = decisions.get(identity) if isinstance(decisions, dict) else None
    if (isinstance(decision, dict) and decision.get("source_fingerprint") == fingerprint
            and isinstance(decision.get("reason"), str) and compact(decision["reason"], 350)):
        return {**candidate, "source_fingerprint": fingerprint, "status": "text_only",
                "reason": "editor_selected_prose", "decision": decision["reason"]}
    return {**candidate, "source_fingerprint": fingerprint}
