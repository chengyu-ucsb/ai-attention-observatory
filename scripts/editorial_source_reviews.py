"""Apply a small, sourced library of original public-article readings.

A source review is not a copied article, a source excerpt, or an automatically
generated claim. The publisher URL remains canonical, while the article that
was actually read (including an attributed republication) is recorded.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"data/editorial-source-readings.json"
REQUIRED=("thesis","reasoning","examples","tension","implications","open_question",
          "qualification","reading_basis","source_url","source_checked")

def apply(records,config=None):
    config=config if config is not None else json.loads(PATH.read_text(encoding="utf-8"))
    index={str(entry.get("url") or ""):entry for entry in config.get("entries",[])}
    for record in records:
        source=index.get(record.get("url") or "")
        if not source or record.get("kind")!="nonacademic":
            continue
        if not all(isinstance(source.get(k),str) and source[k].strip() for k in REQUIRED):
            continue
        if not source["source_url"].startswith("https://"):
            continue
        # Preserves original URL and RSS metadata; only adds independent
        # analytical fields and explicit independent verification provenance.
        record["source_review"]={key:source[key] for key in REQUIRED}
        record["source_review"]["source_relation"]=source.get("source_relation","")
        record["source_review"]["secondary_verification_url"]=source.get("secondary_verification_url","")
        record["source_review"]["evidence_scope"]=source.get("evidence_scope","")
        record["editorial_takeaway"]=source.get("takeaway") or source.get("thesis") or ""
        record["content_access"]="editorially_read_source"
        record["source_checked"]=source["source_checked"]
    return records
