"""Publish a reading-first projection. Citation-only metadata NEVER enters the website.

The internal index (data/library.json) is retained for acquisition and retry.
The public website, news feed, metrics, and recommended items use only this projection.
"""
from __future__ import annotations
import json
from pathlib import Path
from condense_readings import annotate
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"

def readable(record):
    reading=record.get("reading") or {}
    level=reading.get("level")
    if level=="citation_only":return False
    if record.get("kind")=="scholarly":
        if level=="full_text":return bool(record.get("analysis",{}).get("fulltext_url"))
        # Scholarly sources must contain real abstract text, not title-based synopsis.
        return level=="abstract" and len(record.get("abstract_text") or "")>=90
    # Nonacademic descriptions and editorial annotations can be used if attributable
    # to the publisher or an editorial summary, not headline-only metadata.
    return level in ("curated","abstract","full_text") and bool(reading.get("overview") or (record.get("editorial_notes") or {}).get("argument"))

def record_id(x):
    return (x.get("doi") or "").lower() or x.get("url") or x.get("title") or ""

def build():
    all_records=json.loads((DATA/"library.json").read_text())
    selected=[annotate(x) for x in all_records if readable(x)]
    selection_ids={record_id(x) for x in selected}
    week=json.loads((DATA/"weekly.json").read_text())
    # Weekly source entries are snapshots and may be older than the final enrichment.
    items=[x for x in selected if record_id(x) in {record_id(y) for y in week.get("items",[])}]
    items.sort(key=lambda x:(x.get("published") or "",x.get("first_seen") or ""),reverse=True)
    run=dict(week.get("run") or {})
    run["total"]=len(selected)
    run["reading_eligible_count"]=len(selected)
    run["full_text_count"]=sum(x.get("reading",{}).get("level")=="full_text" for x in selected)
    run["abstract_count"]=sum(x.get("reading",{}).get("level")=="abstract" for x in selected)
    # Never use unverified records in visitor-facing counts.
    run.pop("candidates",None)
    run["last_seven_days"]=len(items)
    projected={"run":run,"items":items[:50]}
    (DATA/"public-library.json").write_text(json.dumps(selected,ensure_ascii=False,indent=2)+"\n")
    (DATA/"public-weekly.json").write_text(json.dumps(projected,ensure_ascii=False,indent=2)+"\n")
    assert all(readable(r) for r in selected)
    assert len(selection_ids)==len({record_id(x) for x in selected})
    print(json.dumps({"public_readable":len(selected),"private_index_only":len(all_records)-len(selected),"weekly_readable":len(items),"fulltext":run["full_text_count"]}))
    return selected,projected

if __name__=="__main__":build()
