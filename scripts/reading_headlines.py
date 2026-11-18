"""Admit concise reading headings without clipping or inventing source claims.

Run after source screening and note reconciliation. The register is editorial
input; cached ``display_headline`` and automatic digest text are not approvals.
"""
from __future__ import annotations

import re

MAX_CHARACTERS = 88
STATISTICAL = re.compile(
    r"\b(?:p|r(?:²|\^2)?|b|t|f|n|se|sd|cfi|rmsea)\s*(?:\([^)]*\))?\s*[=<>≤≥]"
    r"|[βρχ](?:²|\^2)?\s*(?:\([^)]*\))?\s*[=<>≤≥]"
    r"|\b\d+(?:\.\d+)?%\s*(?:CI|confidence)|\b(?:Table|Figure)\s+\d", re.I)
FRAGMENT = re.compile(
    r"^(?:In contrast|Similarly|Furthermore|Moreover|As shown|In conclusion|Results?|Conclusions?)\s*[,：:]"
    r"|(?:…|\.\.\.)$", re.I)


def source_id(record: dict) -> str:
    return str(record.get("doi") or "").lower() or str(record.get("url") or record.get("title") or "")


def accepted_heading(value: object) -> str:
    """Return the complete normalized heading, or nothing; never truncate."""
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    if (not value or len(value) > MAX_CHARACTERS or STATISTICAL.search(value)
            or FRAGMENT.search(value)):
        return ""
    return value


def headline_decision(record: dict, register: dict) -> dict:
    """Select an approved heading, or request review of this one source.

    A short bibliographic title is already attributable to its source. A longer
    title needs either a checked register entry or a still-accepted original
    summary's complete main idea. Findings and automatic extract digests cannot
    become display headings. No input record or bibliographic title is changed.
    """
    edited = accepted_heading(register.get(source_id(record)))
    if edited:
        return {"status": "ready", "headline": edited, "basis": "editorial_register"}
    title = accepted_heading(record.get("title"))
    if title:
        return {"status": "ready", "headline": title, "basis": "publication_title"}
    original = record.get("original_reading")
    if original:
        from original_readings import eligible
        if eligible(original, record):
            summary = original.get("summary") or {}
            idea = accepted_heading(summary.get("idea") or summary.get("thesis"))
            if idea:
                return {"status": "ready", "headline": idea, "basis": "accepted_original_summary"}
    return {"status": "review_needed", "headline": "", "basis": "missing_concise_checked_heading"}


def review_item(record: dict, decision: dict) -> dict:
    """Minimal editorial-queue locator, without source text or private drafts."""
    return {"id": source_id(record), "title": record.get("title") or "",
            "url": record.get("url") or "", "kind": record.get("kind") or "",
            "reason": decision["basis"]}
