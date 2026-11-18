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
from pathlib import Path
import re

REVIEWED_VISUALS = Path(__file__).resolve().parents[1] / "data/reviewed-visuals.json"


def visual_digest(visual: dict) -> str:
    body = {key: value for key, value in visual.items() if key != "review"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


@lru_cache(maxsize=1)
def reviewed_visuals() -> list:
    try:
        payload = json.loads(REVIEWED_VISUALS.read_text())
        return payload["visuals"] if payload.get("schema_version") == 1 else []
    except (OSError, ValueError, KeyError, TypeError):
        return []


def reviewed_visual(record: dict, candidates: list | None = None) -> dict | None:
    """Only attach a checked visual to the exact source version it describes.

    The content hash detects later edits; it does not establish independent
    review. These original factual comparisons contain no copied source image.
    """
    reading = record.get("reading") or {}
    if record.get("kind") != "scholarly" or not reading.get("original_summary"):
        return None
    for visual in reviewed_visuals() if candidates is None else candidates:
        try:
            source, review = visual["source"], visual["review"]
            if (visual["kind"] != "reviewed_comparison"
                    or visual["doi"] != record.get("doi")
                    or visual["reading_id"] != reading.get("original_summary_id")
                    or visual["rights"] != "original_factual_display_no_source_image"
                    or review["kind"] != "ai_source_check"
                    or review["status"] != "checked"
                    or review["payload_sha256"] != visual_digest(visual)):
                continue
            if any(source[key] != reading.get("source_" + key)
                   for key in ("url", "version", "sha256")):
                continue
            if not re.fullmatch(r"[0-9a-f]{64}", source["sha256"]):
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
    if reading.get("original_summary"):
        checked = reviewed_visual(record)
        if checked:
            return checked
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

