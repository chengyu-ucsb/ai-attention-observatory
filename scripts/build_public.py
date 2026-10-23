"""Publish a reading-first projection. Citation-only metadata NEVER enters the website.

The internal index (data/library.json) is retained for acquisition and retry.
The public website, news feed, metrics, and recommended items use only this projection.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from condense_readings import annotate
from build_visuals import visual_spec
from search_plan import source_class
from source_lineage import prepare
from build_readings import make_note
from editorial_corrections import apply as apply_editorial_corrections
from source_quality import screen as screen_source
from news_quality import substantive_article
from editorial_source_reviews import apply as apply_source_reviews
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
    return (level in ("curated","abstract","full_text") or (level=="source_preview" and record.get("companion_to"))) and bool(reading.get("overview") or (record.get("editorial_notes") or {}).get("argument"))

def record_id(x):
    return (x.get("doi") or "").lower() or x.get("url") or x.get("title") or ""

def build():
    all_records=prepare(apply_source_reviews(apply_editorial_corrections(json.loads((DATA/"library.json").read_text()))))
    selected=[]
    pending=[]
    held=Counter()
    for source in all_records:
        if not source.get("reading") or (source.get("research_type")=="conceptual_framework" and source.get("reading",{}).get("research_type")!="conceptual_framework"):
            source["reading"]=make_note(source)
        if source.get("kind")=="scholarly":
            quality=screen_source(source)
            if quality["decision"]!="include":
                held[quality["reason"]]+=1
                continue
        else:
            quality={"decision":"include","venue_level":"editorial","reason":"reviewed_full_article_or_documentation"}
        if (source.get("kind")=="nonacademic" and (source.get("reading") or {}).get("level")=="source_preview"
                and (source.get("deep_analysis") or {}).get("source_depth")=="source_html"):
            source["reading"]["level"]="curated"
        published=annotate(source)
        if published.get("kind")=="nonacademic" and not substantive_article(published):
            # Keep a minimal locator so bookmarks remain useful. It must never
            # appear as a source-backed analysis in the featured/library lists.
            held["journalism_awaiting_full_article_reading"]+=1
            pending.append({"kind":"nonacademic","url":source.get("url"),"title":source.get("title"),
                            "venue":source.get("venue"),"published":source.get("published"),
                            "source_quality":{"decision":"awaiting_full_article_reading"},
                            "reason":"No article-based analysis has passed the source-depth checks."})
            continue
        if not readable(published):
            held["insufficient_source_text"]+=1
            continue
        published["source_quality"]=quality
        published["source_group"]=source_class(source)
        published["visual"]=visual_spec(published)
        selected.append(published)
    selection_ids={record_id(x) for x in selected}
    canonical=[x for x in selected if not x.get("companion_to")]
    by_id={record_id(x):x for x in canonical}
    week=json.loads((DATA/"weekly.json").read_text())
    week["items"]=apply_source_reviews(apply_editorial_corrections(week.get("items",[])))
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
    run["abstract_count"]=sum(x.get("reading",{}).get("level")=="abstract" for x in canonical)
    run["ai_specific_count"]=sum(x["source_group"]=="AI-specific" for x in canonical)
    run["historical_foundations_count"]=sum(x["source_group"].startswith(("Earlier","Historical")) for x in canonical)
    # Never use unverified records in visitor-facing counts.
    run.pop("candidates",None)
    run["last_seven_days"]=len(items)
    projected={"run":run,"items":items[:50]}
    (DATA/"source-quality-audit.json").write_text(json.dumps({
        "version":1,
        "internal_scholarly_total":sum(x.get("kind")=="scholarly" for x in all_records),
        "public_scholarly_total":sum(x.get("kind")=="scholarly" for x in canonical),
        "journalism_awaiting_reading":len(pending),
        "withheld_by_reason":dict(sorted(held.items())),
        "priority_venues":sum(x.get("source_quality",{}).get("venue_level")=="priority" for x in canonical),
        "specialist_venues":sum(x.get("source_quality",{}).get("venue_level")=="specialist" for x in canonical),
        "note":"Screening is a venue/relevance triage, not peer-review verification or a journal-impact-factor judgment."
    },ensure_ascii=False,indent=2)+"\n")
    (DATA/"public-pending-sources.json").write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n")
    (DATA/"public-library.json").write_text(json.dumps(selected,ensure_ascii=False,indent=2)+"\n")
    (DATA/"public-weekly.json").write_text(json.dumps(projected,ensure_ascii=False,indent=2)+"\n")
    assert all(readable(r) for r in selected)
    assert len(selection_ids)==len({record_id(x) for x in selected})
    print(json.dumps({"public_readable":len(selected),"private_index_only":len(all_records)-len(selected),"weekly_readable":len(items),"fulltext":run["full_text_count"]}))
    return selected,projected

if __name__=="__main__":build()
