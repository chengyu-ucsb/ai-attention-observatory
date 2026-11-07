"""Stable, source-grounded visual metadata for every new public reading.

This runs for each ingestion or enrichment update, not a fixed list of DOIs.
It deliberately does NOT infer a sample size, compute a statistic, draw an
effect-size chart, infer causation, or reproduce copyrighted paper figures.
"""
from __future__ import annotations


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

