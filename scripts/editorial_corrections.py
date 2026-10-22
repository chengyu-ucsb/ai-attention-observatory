"""Apply editorially verified publisher URLs and short source-grounded notes.

Corrections are explicit and idempotent. Feed-only records never become a
full-article reading merely because a website or title matches a topic.
"""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"data/editorial-corrections.json"

def apply(records,config=None):
    config=config if config is not None else json.loads(PATH.read_text(encoding="utf-8"))
    for edit in config.get("entries",[]):
        hits=[x for x in records if x.get("kind")=="nonacademic" and
              x.get("title")==edit.get("match_title")]
        for r in hits:
            for key,source in (("title","canonical_title"),("url","canonical_url"),
                               ("authors","authors"),("venue","venue"),
                               ("published","published"),("format","format"),
                               ("source_checked","source_checked"),
                               ("preview","preview")):
                if edit.get(source):
                    r[key]=edit[source]
            r["editorial_notes"]=edit.get("editorial_notes",{})
            r["content_access"]="editorially_read_source"
            r["source_verification"]=edit.get("source_verification","")
            r["reading"]={
                "level":"curated",
                "provenance":"Original publisher article, editorially read; original synthesis",
                "overview":edit.get("preview",""),
                "methods":"","findings":"","limitations":"",
                "reported_findings":False,
                "notice":"Editorial account of the accessible public essay, not a measured research result."
            }
    return records
