"""Reproducible search plan for AI and human attention.

Weekly surveillance covers only the previous completed UTC publication week.
Historical coverage is a separate, explicitly requested backfill operation. This is a *structured discovery index*,
not a claim of exhaustive systematic-review retrieval or field-wide trends.
"""
from __future__ import annotations
import datetime as dt
import re
from collection_window import previous_week, publication_date

START_YEAR=2023
LANES={
 "AI & cognition":[
  "generative AI cognitive offloading critical thinking",
  "ChatGPT metacognition memory cognitive effort",
  "large language model cognitive engagement agency"
 ],
 "Fragmentation":[
  "generative AI sustained attention task switching",
  "AI assistant interruptions distraction multitasking",
  "digital distraction notification fatigue attention"
 ],
 "Interventions":[
  "AI attention management intervention focus assistant",
  "generative AI self regulation learning intervention",
  "adaptive notifications attention digital wellbeing"
 ],
 "Technology & society":[
  "artificial intelligence attention economy cognitive autonomy",
  "generative AI interface attention design human agency",
  "AI information overload algorithmic mediation"
 ]
}

# Broad historical terms recover formative work that used different terminology
# than the current research literature. Inclusion screening remains separate.
HISTORICAL_TERMS={
 "AI & cognition":["ChatGPT critical thinking","generative AI cognitive effort","ChatGPT learning cognition"],
 "Fragmentation":["generative AI attention","AI cognitive offloading","ChatGPT distraction"],
 "Interventions":["ChatGPT self regulated learning","generative AI scaffolding","AI learning intervention"],
 "Technology & society":["ChatGPT human agency","generative AI attention economy","AI information overload"]
}

def plan(today=None, mode="weekly"):
    today=publication_date(today or dt.datetime.now(dt.timezone.utc))
    if today is None:raise ValueError("A complete run date is required")
    if mode not in {"weekly", "backfill"}:raise ValueError("Unsupported search mode: "+mode)
    tasks=[]
    if mode=="weekly":
        begin,end=previous_week(today)
        for lane,queries in LANES.items():
            for q in queries:
                tasks.append((lane,q,begin.isoformat(),end.isoformat(),"previous_publication_week"))
        return tasks
    # Manual backfill searches the current year and the complete historical
    # matrix. No historical task is mixed into the normal weekly collector.
    for lane,queries in LANES.items():
        for q in queries[:2]:
            tasks.append((lane,q,f"{today.year}-01-01",today.isoformat(),f"historical:{today.year}"))
    weekly_index=today.toordinal()//7
    for index,(lane,queries) in enumerate(LANES.items()):
        for year in range(START_YEAR,today.year):
            options=HISTORICAL_TERMS[lane]
            start=(year-START_YEAR+index+weekly_index)%len(options)
            n_queries=2 if year in (2023,2024) else 1
            for offset in range(n_queries):
                q=options[(start+offset)%len(options)]
                tasks.append((lane,q,f"{year}-01-01",f"{year}-12-31",f"historical:{year}"))
    return tasks


def source_class(record):
    """Keep historic digital-attention foundations separate from GenAI work."""
    year=(record.get("published") or "")[:4]
    title=(record.get("title") or "").lower()
    text=(title+" "+(record.get("abstract_text") or record.get("preview") or "").lower())
    direct=bool(re.search(r"\bai\b",text)) or any(term in text for term in (
        "chatgpt","generative ai","generative artificial intelligence",
        "large language model","llm","gpt-4","gpt-3","ai-assisted",
        "ai-based","ai powered","ai-powered","artificial intelligence"))
    if year.isdigit() and int(year)<START_YEAR:
        return "Earlier digital-attention foundation" if not direct else "Historical AI context"
    if direct:return "AI-specific"
    return "Adjacent digital-attention evidence"

