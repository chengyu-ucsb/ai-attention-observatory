"""Publish a reading-first projection. Citation-only metadata NEVER enters the website.

The internal index (data/library.json) is retained for acquisition and retry.
The public website, news feed, metrics, and recommended items use only this projection.
"""
from __future__ import annotations
import json
from pathlib import Path
from condense_readings import annotate
from build_visuals import visual_spec
from search_plan import source_class
from source_lineage import prepare
from build_readings import make_note
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
    all_records=prepare(json.loads((DATA/"library.json").read_text()))
    selected=[]
    for source in all_records:
        if not source.get("reading") or (source.get("research_type")=="conceptual_framework" and source.get("reading",{}).get("research_type")!="conceptual_framework"):
            source["reading"]=make_note(source)
        if not readable(source):continue
        published=annotate(source)
        published["source_group"]=source_class(source)
        published["visual"]=visual_spec(published)
        selected.append(published)
    selection_ids={record_id(x) for x in selected}
    canonical=[x for x in selected if not x.get("companion_to")]
    by_id={record_id(x):x for x in canonical}
    week=json.loads((DATA/"weekly.json").read_text())
    # Weekly source entries are snapshots and may be older than the final enrichment.
    # A linked explainer brings its original paper into this week's reading set,
    # but does not count as a second independent scholarly contribution.
    wanted=set()
    for incoming in week.get("items",[]):
        linked=incoming.get("companion_to")
        if not linked:
            source=next((x for x in selected if record_id(x)==record_id(incoming)),None)
            linked=(source or {}).get("companion_to")
        original=linked if linked in by_id else record_id(incoming)
        wanted.add(original)
    items=[x for x in canonical if record_id(x) in wanted]
    items.sort(key=lambda x:(x.get("published") or "",x.get("first_seen") or ""),reverse=True)
    run=dict(week.get("run") or {})
    run["total"]=len(canonical)
    run["reading_eligible_count"]=len(canonical)
    run["companion_count"]=len(selected)-len(canonical)
    run["full_text_count"]=sum(x.get("reading",{}).get("level")=="full_text" for x in canonical)
    run["abstract_count"]=sum(x.get("reading",{}).get("level")=="abstract" for x in selected)
    run["ai_specific_count"]=sum(x["source_group"]=="AI-specific" for x in selected)
    run["historical_foundations_count"]=sum(x["source_group"].startswith(("Earlier","Historical")) for x in selected)
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
