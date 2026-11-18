"""Attach editor-verified original summaries of publicly readable full articles.

These are original source-grounded paraphrases, never copied article sections.
They coexist with the automatic licensed-XML/PDF path. License restrictions on
republication do not automatically prohibit careful, attributed factual analysis.
"""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"data/verified-full-article-notes.json"
LIB=ROOT/"data/library.json"

def apply(rows,manifest=None):
    manifest=manifest if manifest is not None else json.loads(MANIFEST.read_text(encoding="utf-8"))
    notes={str(p.get("doi") or "").lower():p for p in manifest.get("articles",[])}
    applied=0
    for row in rows:
        if row.get("kind")!="scholarly":continue
        source=notes.get(str(row.get("doi") or "").lower())
        if not source:continue
        conceptual = source.get("research_type") == "conceptual_framework"
        required = ("method", "discussion", "limitations", "verified_on", "review_scope")
        if (not source.get("verified_url", "").startswith("https://")
                or not all(source.get(key) for key in required)
                or (not conceptual and not source.get("results"))):
            continue
        url = source["verified_url"]
        submitted = source.get("source_format") or ("PDF" if ".pdf" in url.lower() else
                    "XML" if "/xml/" in url.lower() else "HTML")
        submitted = submitted.upper()
        # A checked paraphrase and a machine extract can describe the same work.
        # Keep the original extract and its rights information intact.
        checked = {
            "provenance": "Full-article synthesis of verified publisher HTML; original paraphrases" if submitted == "HTML" and "source_format" not in source
                          else f"Original paraphrases from the checked {submitted} article",
            "fulltext_url": url, "methods": source["method"],
            "results": "" if conceptual else source.get("results", ""),
            "discussion": source["discussion"], "limitations": source["limitations"],
            "original_paraphrases_only": True, "review_scope": source["review_scope"],
            "source_checked": source["verified_on"], "source_format": submitted,
            "source_version": source.get("source_version", "publisher article"),
        }
        if source.get("research_type"):
            row["research_type"] = source["research_type"]
        row["verified_article_review"] = checked
        if not row.get("analysis") or row["analysis"].get("original_paraphrases_only"):
            row["analysis"] = {**checked, "license": row.get("open_access_license") or
               "Open reading; excerpt redistribution not assumed", "figures": [],
               "sections_available": [k for k in ("methods","results","discussion","limitations") if checked[k]],
               "read_from_article_html": submitted == "HTML", "extraction_version": 3}
        row["editorial_digest"] = source.get("digest") or {}
        row["source_review_status"] = "editorially_checked_full_article"
        row["open_access_url"] = url
        applied+=1
    return applied

def run(path=LIB):
    path=Path(path)
    rows=json.loads(path.read_text(encoding="utf-8"))
    applied=apply(rows)
    path.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"verified_full_article_notes_attached":applied,"original_source_text_stored":False}))
    return applied

if __name__=="__main__":run()
