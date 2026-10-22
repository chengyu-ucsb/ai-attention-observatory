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
        if not source.get("verified_url","").startswith("https://") or not all(source.get(k) for k in ("method","results","discussion","limitations","verified_on","review_scope")):
            continue
        # Never overwrite machine-extracted article material already available.
        if row.get("analysis") and not row["analysis"].get("original_paraphrases_only"):
            continue
        row["analysis"]={
            "provenance":"Editorial full-article synthesis of verified publisher HTML; original paraphrases (no copied text)",
            "license":row.get("open_access_license") or "publisher OA; excerpt republication not assumed",
            "fulltext_url":source["verified_url"],
            "methods":source["method"],
            "results":source["results"],
            "discussion":source["discussion"],
            "limitations":source["limitations"],
            "figures":[],
            "sections_available":["methods","results","discussion","limitations"],
            "original_paraphrases_only":True,
            "read_from_article_html":True,
            "review_scope":source["review_scope"],
            "source_checked":source["verified_on"],
            "extraction_version":3
        }
        row["editorial_digest"]=source.get("digest") or {}
        row["source_review_status"]="editorially_checked_full_article"
        row["open_access_url"]=source["verified_url"]
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
