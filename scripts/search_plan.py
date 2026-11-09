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

def discovery_window(today, mode="weekly", publication_window=None):
    """Explicit private preparation never changes the default public-week gate."""
    today = publication_date(today)
    if today is None:
        raise ValueError("A complete observation date is required")
    if mode in {"weekly", "backfill"}:
        if publication_window is not None:
            raise ValueError("Public weekly/backfill windows cannot be overridden")
        return previous_week(today) if mode == "weekly" else (dt.date(START_YEAR, 1, 1), today)
    if mode not in {"preparation", "closeout", "closeout_late_index"} or not isinstance(publication_window, dict):
        raise ValueError("Preparation requires an explicit publication window")
    start, end = (publication_date(publication_window.get(k)) for k in ("from", "to"))
    if start is None or end is None or start > end:
        raise ValueError("Invalid preparation publication window")
    monday = today - dt.timedelta(days=today.weekday())
    if mode == "preparation" and not monday <= start <= end <= today:
        raise ValueError("Preparation must stay within the observed current UTC week")
    if mode in {"closeout", "closeout_late_index"} and (start, end) != previous_week(today):
        raise ValueError("Closeout requires the actual previous completed UTC week")
    return start, end


def plan(today=None, mode="weekly", *, publication_window=None):
    today=publication_date(today or dt.datetime.now(dt.timezone.utc))
    if today is None:raise ValueError("A complete run date is required")
    begin,end=discovery_window(today,mode,publication_window)
    tasks=[]
    if mode!="backfill":
        for lane,queries in LANES.items():
            for q in queries:
                tasks.append((lane,q,begin.isoformat(),end.isoformat(),"previous_publication_week" if mode=="weekly" else mode))
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

