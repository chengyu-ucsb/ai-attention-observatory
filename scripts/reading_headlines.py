"""Admit concise reading headings without clipping or inventing source claims.

Run after source screening and note reconciliation. The register is editorial
input; cached ``display_headline`` and automatic digest text are not approvals.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re

DATA = Path(__file__).resolve().parents[1] / "data"
MAX_CHARACTERS = 55
MAX_WORDS = 10
STATISTICAL = re.compile(
    r"\b(?:p|r(?:²|\^2)?|b|t|f|n|se|sd|cfi|rmsea)\s*(?:\([^)]*\))?\s*[=<>≤≥]"
    r"|[βρχ](?:²|\^2)?\s*(?:\([^)]*\))?\s*[=<>≤≥]"
    r"|\b\d+(?:\.\d+)?%\s*(?:CI|confidence)|\b(?:Table|Figure)\s+\d", re.I)
FRAGMENT = re.compile(
    r"^(?:In contrast|Similarly|Furthermore|Moreover|As shown|In conclusion|Results?|Conclusions?)\s*[,：:]"
    r"|(?:…|\.\.\.)$", re.I)


def source_id(record: dict) -> str:
    identity = str(record.get("doi") or record.get("id") or record.get("url") or record.get("title") or "")
    if identity.lower().startswith("https://doi.org/"):
        return identity[len("https://doi.org/"):].lower()
    return identity.lower() if identity.startswith("10.") else identity


def accepted_heading(value: object) -> str:
    """Return the complete normalized heading, or nothing; never truncate."""
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    if (not value or len(value) > MAX_CHARACTERS or len(value.split()) > MAX_WORDS
            or STATISTICAL.search(value)
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


@lru_cache(maxsize=2)
def _register(filename: str) -> dict:
    return json.loads((DATA / filename).read_text(encoding="utf-8"))


def headline_register() -> dict:
    return _register("reading-headlines.json")


def reader_headline(record: dict, register: dict | None = None) -> str:
    """Render screened articles and frozen edition references using one title."""
    register = headline_register() if register is None else register
    edited = accepted_heading(register.get(source_id(record)))
    # Frozen editions may reference sources that no longer qualify for the catalog.
    # Preserve their links even if an older item has no approved concise heading.
    return (edited or accepted_heading(record.get("display_headline"))
            or accepted_heading(record.get("title")) or "Read the original article")


GENRE_LABELS = {
    "research": "Research", "review": "Research review", "proposal": "Research proposal",
    "conceptual": "Conceptual paper", "editorial": "Journal editorial",
    "reporting": "News report", "analysis": "Analysis", "opinion": "Opinion",
    "commentary": "Commentary", "guide": "Product guide",
}

# Publisher and reviewer metadata use different names for the same genre.
MEDIA_GENRES = {
    "reported_analysis": "reporting", "reporting": "reporting", "news": "reporting",
    "news_reporting": "reporting", "press_reporting": "reporting",
    "journalism": "reporting", "news_report": "reporting", "opinion": "opinion",
    "policy": "analysis", "policy_analysis": "analysis", "policy_&_analysis": "analysis",
    "product_analysis": "analysis", "analysis": "analysis", "practical_advice": "analysis",
    "product_control_guidance": "analysis", "guide": "guide", "product_guide": "guide",
    "product_documentation": "guide", "commentary": "commentary",
}


def reader_genre(record: dict) -> str:
    """Classify the piece itself, independently of the studies it discusses."""
    reviewed = _register("reading-genres.json").get(source_id(record))
    if reviewed:
        return reviewed
    reading = record.get("reading") or {}
    explicit = record.get("reader_genre")
    scholarly = record.get("kind") == "scholarly"
    if explicit in GENRE_LABELS and (record.get("kind") != "nonacademic" or explicit in MEDIA_GENRES):
        return explicit
    title = str(record.get("title") or "")
    if scholarly:
        # A generic index type (e.g. "journal-article" or "preprint") says
        # where a work appeared, not whether it presents a study or an argument.
        types = {str(value or "").lower().strip().replace(" ", "_").replace("-", "_")
                 for value in (record.get("research_type"), reading.get("research_type"),
                               record.get("article_type"), record.get("source_type"),
                               record.get("genre"), reading.get("genre"))}
        if "editorial" in types or re.match(r"^editorial\s*:", title, re.I):
            return "editorial"
        if types & {"opinion", "perspective", "commentary", "comment", "news_and_views"}:
            return "opinion"
        if types & {"news", "news_report", "journalism", "press_reporting"}:
            return "reporting"
        if types & {"proposal", "protocol", "study_protocol", "research_proposal"}:
            return "proposal"
        if types & {"research_synthesis", "review", "systematic_review", "meta_analysis",
                    "scoping_review", "narrative_review"}:
            return "review"
        if re.search(r"\b(?:systematic (?:literature )?review|scoping review|narrative review|meta-analysis)\b", title, re.I):
            return "review"
        if types & {"conceptual", "conceptual_analysis", "conceptual_framework", "theoretical"}:
            return "conceptual"
        return "research"
    if record.get("source") == "Official product documentation":
        return "guide"
    for field in (reading.get("genre"), record.get("genre"),
                  record.get("source_type"), record.get("format")):
        genre = MEDIA_GENRES.get(str(field or "").strip().lower().replace(" ", "_"))
        if genre:
            return genre
    return "commentary"


def genre_label(record: dict) -> str:
    return GENRE_LABELS[reader_genre(record)]
