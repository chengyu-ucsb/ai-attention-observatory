"""Prepare one plain-language introduction from the current admitted reading.

This downstream presentation pass cannot confer source or publication approval.
"""
from __future__ import annotations

import hashlib
import json
import re

from article_art import canonical_identity


def basis_fingerprint(paper: dict) -> str:
    """Bind a paraphrase to the evidence and wording that an editor could use.

    Exclude ingestion dates, unrelated metadata and downstream outputs so an
    unchanged reading can retain its introduction across routine rebuilds.
    """
    reading = paper.get("reading") or {}
    analysis = paper.get("analysis") or {}
    reviewed = paper.get("original_reading") or {}
    basis = {
        "identity": canonical_identity(paper),
        "title": paper.get("title"),
        "reader_genre": paper.get("reader_genre"),
        "abstract": paper.get("abstract_text") or paper.get("preview"),
        "reading": {key: reading.get(key) for key in (
            "digest", "overview", "methods", "findings", "interpretation",
            "limitations", "source_version", "source_url", "source_sha256", "level",
        )},
        "analysis": {key: analysis.get(key) for key in (
            "fulltext_url", "methods", "results", "discussion", "limitations",
        )},
        "checked_source": reviewed.get("source"),
        "checked_evidence": reviewed.get("evidence"),
        "checked_summary": reviewed.get("summary"),
    }
    if reading.get("machine_account"):
        basis["machine_account"] = reading["machine_account"]
    encoded = json.dumps(basis, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# These are signals for selecting an existing editorial sentence, not a score
# for readers or a list of words banned from the article.
TECHNICAL = re.compile(
    r"\b(?:MASEM|UTAUT\d*|ANOVA|ANCOVA|LASSO|structural equation model\w*|"
    r"moderated mediation|metacognitive calibration|psychometric properties|"
    r"cognitive attentional syndrome|latent profile analysis)\b|"
    r"\b(?:p|r|β|χ²)\s*[=<>≤≥]|\b(?:Table|Figure)\s+\d", re.I
)
FRAGMENT = re.compile(
    r"^(?:This (?:result|pattern|difference)|These (?:results|findings)|"
    r"In contrast|Similarly|However|Furthermore|Respectively|They|It)\b|"
    r"(?:…|\.\.\.)$|[<>]", re.I
)
DIGEST_TYPES = {
    "ai_source_checked_original_summary", "editorially_written_from_indexed_sections",
    "edited_perspective", "journal_argument", "conceptual_framework",
    "locally_analyzed_article", "publisher_or_editorial_synopsis",
}


def source_label(paper: dict) -> str:
    reading = paper.get("reading") or {}
    digest = reading.get("digest") or {}
    if (reading.get("level") == "abstract"
            or digest.get("editorial_basis") == "publisher_source_abstract"):
        return "Abstract"
    if reading.get("original_summary") or paper.get("verified_article_review"):
        return "Checked article notes"
    if paper.get("kind") == "nonacademic":
        return "Attributed source account"
    return "Indexed article"


def clean_lead(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    if not 6 <= len(value.split()) <= 95 or FRAGMENT.search(value):
        return ""
    return value


def usable_sentence(value: object, paper: dict) -> str:
    """Keep the entire editorial field so a second-sentence caveat survives."""
    lead = clean_lead(value)
    if (not lead.endswith((".", "?", "!", ".”", "?’", '."'))
            or lead in (paper.get("title"), paper.get("display_headline"))
            or len(lead.split()) > 55 or TECHNICAL.search(lead)):
        return ""
    return lead


def prepare_plain_reading(paper: dict, overrides: dict | None = None) -> dict:
    """Build a card lead using the current source-qualified public reading.

    A stale approved lead always goes back to the queue. An automatically
    selected field stays distinguishable from an individually edited lead.
    """
    reading = paper.get("reading") or {}
    digest = reading.get("digest") or {}
    key = canonical_identity(paper)
    fingerprint = basis_fingerprint(paper)
    result = {"lead": "", "basis": source_label(paper), "basis_sha256": fingerprint,
              "status": "needs_review", "reason": "needs_plain_language_paraphrase"}
    if not reading or reading.get("level") in {"citation_only", "source_preview"}:
        return {**result, "reason": "insufficient_reading"}
    if overrides is not None and key in overrides:
        override = overrides[key]
        if not isinstance(override, dict) or override.get("basis_sha256") != fingerprint:
            return {**result, "reason": "source_changed"}
        lead = clean_lead(override.get("lead"))
        if not lead:
            return {**result, "reason": "invalid_reviewed_lead"}
        context = {}
        for field in ("detail", "limit"):
            value = override.get(field, "")
            if not isinstance(value, str) or "<" in value or ">" in value:
                return {**result, "reason": "invalid_reviewed_context"}
            if value.strip():
                context[field] = " ".join(value.split())
        return {**result, **context, "lead": lead, "status": "reviewed", "reason": "source_bound_edit"}

    # Only newly written or checked material may become reader-facing prose.
    # Raw abstract excerpts, titles and unverified private drafts stay upstream.
    candidates = []
    status = digest.get("status")
    if status in DIGEST_TYPES:
        # A self-contained example usually explains a proposal best. An
        # argument needs an attributable thesis. Study cards favor the idea
        # and explanation, which retain more context than an isolated result.
        if paper.get("reader_genre") in ("proposal", "conceptual"):
            fields = ("approach", "explain", "idea")
        elif paper.get("kind") == "nonacademic" or status == "journal_argument":
            fields = ("explain", "idea")
        else:
            fields = ("idea", "explain", "approach")
        candidates.extend((digest.get(field), f"digest.{field}") for field in fields)
    if digest.get("explain_source") == "abstract_paraphrase":
        candidates.append((digest.get("explain"), "abstract_paraphrase"))
    account = reading.get("machine_account") or {}
    if account.get("review_status") == "machine_checked_not_independently_reviewed":
        candidates.extend((account.get(field), f"machine_account.{field}")
                          for field in ("research_question", "study_design"))
    for candidate, field in candidates:
        lead = usable_sentence(candidate, paper)
        if lead:
            if field == "abstract_paraphrase":
                result["basis"] = "Abstract"
            prepared = {**result, "lead": lead, "status": "prepared", "reason": field}
            if field.startswith("machine_account."):
                context = {"detail": account.get("study_design"), "limit": account.get("limitations")}
            elif status in DIGEST_TYPES:
                longform = digest.get("longform") or {}
                context = {"detail": digest.get("approach") or longform.get("examples"),
                           "limit": digest.get("limitation") or longform.get("qualification")}
            else:
                context = {}
            used = {lead}
            for role, value in context.items():
                sentence = usable_sentence(value, paper)
                if sentence and sentence not in used:
                    prepared[role] = sentence
                    used.add(sentence)
            return prepared
    return result
