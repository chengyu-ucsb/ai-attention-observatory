"""Attach editor-verified original summaries of publicly readable full articles.

These are original source-grounded paraphrases, never copied article sections.
They coexist with the automatic licensed-XML/PDF path. License restrictions on
republication do not automatically prohibit careful, attributed factual analysis.
"""
from __future__ import annotations
import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit
from reading_depth import distinct_summary_roles
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"data/verified-full-article-notes.json"
LIB=ROOT/"data/library.json"


def valid_source(source):
    """Reject incomplete register entries; this is not independent source review."""
    if not isinstance(source, dict):
        return False
    doi = str(source.get("doi") or "").strip().lower()
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return False
    fields = ("method", "discussion", "limitations", "verified_on", "review_scope", "verified_url")
    if not all(isinstance(source.get(key), str) and source[key].strip() for key in fields):
        return False
    if source.get("research_type") != "conceptual_framework" and not (
            isinstance(source.get("results"), str) and source["results"].strip()):
        return False
    try:
        checked = source["verified_on"]
        if date.fromisoformat(checked).isoformat() != checked:
            return False
        url = urlsplit(source["verified_url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            return False
    except ValueError:
        return False
    roles = [source.get(key) for key in ("method", "results", "discussion", "limitations")]
    return isinstance(source.get("digest", {}), dict) and distinct_summary_roles(roles)

def note_digest(note):
    """Bind adaptations to the exact checked notes, version and source location."""
    fields = ("fulltext_url", "source_version", "source_checked", "source_sections",
              "methods", "results", "discussion", "limitations", "review_scope")
    payload = {key: note.get(key) for key in fields}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def clear_previous_review(row):
    """Remove only this register's projection, preserving actual source extracts."""
    previous = row.pop("verified_article_review", None)
    legacy = (row.get("source_review_status") == "editorially_checked_full_article"
              and (row.get("analysis") or {}).get("original_paraphrases_only"))
    if not previous and not legacy:
        return
    if (row.get("analysis") or {}).get("original_paraphrases_only"):
        row.pop("analysis", None)
    row.pop("editorial_digest", None)
    row.pop("source_review_status", None)
    row.pop("reading", None)
    # Newly attached reviews remember overwritten metadata. Legacy reviews did
    # not, so avoid guessing whether their topic/type or OA locator predated us.
    for key, state in (previous or {}).get("previous_metadata", {}).items():
        if key not in ("research_type", "open_access_url"):
            continue
        if not isinstance(state, dict) or "present" not in state:
            continue
        if state["present"]:
            row[key] = deepcopy(state["value"])
        else:
            row.pop(key, None)


def apply(rows, manifest=None):
    manifest = manifest if manifest is not None else json.loads(MANIFEST.read_text(encoding="utf-8"))
    notes = {}
    for source in manifest.get("articles", []):
        if isinstance(source, dict):
            notes.setdefault(str(source.get("doi") or "").strip().lower(), []).append(source)
    applied = 0
    for row in rows:
        clear_previous_review(row)
        if row.get("kind") != "scholarly":
            continue
        matches = notes.get(str(row.get("doi") or "").strip().lower(), [])
        if len(matches) != 1:
            continue
        source = matches[0]
        if not valid_source(source):
            continue
        conceptual = source.get("research_type") == "conceptual_framework"
        url = source["verified_url"]
        submitted = source.get("source_format") or ("PDF" if ".pdf" in url.lower() else
                    "XML" if "/xml/" in url.lower() else "HTML")
        if not isinstance(submitted, str):
            continue
        submitted = submitted.upper()
        if submitted not in ("HTML", "PDF", "XML", "JATS", "TEI"):
            continue
        previous_metadata = {key: {"present": key in row, "value": deepcopy(row.get(key))}
                             for key in ("research_type", "open_access_url")}
        checked = {
            "provenance": "Full-article synthesis of verified publisher HTML; original paraphrases" if submitted == "HTML" and "source_format" not in source
                          else f"Original paraphrases from the checked {submitted} article",
            "fulltext_url": url, "methods": source["method"],
            "results": "" if conceptual else source.get("results", ""),
            "discussion": source["discussion"], "limitations": source["limitations"],
            "original_paraphrases_only": True, "review_scope": source["review_scope"],
            "source_checked": source["verified_on"], "source_format": submitted,
            "source_version": source.get("source_version", "publisher article"),
            "source_sections": deepcopy(source.get("source_sections") or []),
            "previous_metadata": previous_metadata,
        }
        checked["note_sha256"] = note_digest(checked)
        if source.get("research_type"):
            row["research_type"] = source["research_type"]
        row["verified_article_review"] = checked
        if not row.get("analysis"):
            row["analysis"] = {**checked, "license": row.get("open_access_license") or
               "Open reading; excerpt redistribution not assumed", "figures": [],
               "sections_available": [k for k in ("methods", "results", "discussion", "limitations") if checked[k]],
               "read_from_article_html": submitted == "HTML", "extraction_version": 3}
        row["editorial_digest"] = source.get("digest") or {}
        row["source_review_status"] = "editorially_checked_full_article"
        row["open_access_url"] = url
        applied += 1
    return applied

def run(path=LIB):
    path=Path(path)
    rows=json.loads(path.read_text(encoding="utf-8"))
    applied=apply(rows)
    path.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"verified_full_article_notes_attached":applied,"original_source_text_stored":False}))
    return applied

if __name__=="__main__":run()
