"""Reproducible search plan for AI and human attention.

Recent surveillance and historical coverage are separate operations. Historical
years are rotated during ordinary weekly runs; explicit backfills search the
entire post-ChatGPT research window. This is a *structured discovery index*,
not a claim of exhaustive systematic-review retrieval or field-wide trends.
"""
from __future__ import annotations
import datetime as dt
import re

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

def plan(today=None, mode="weekly"):
    today=today or dt.date.today()
    all_years=list(range(START_YEAR,today.year))
    tasks=[]
    # Current research first; balanced across all four questions rather
    # than multiple near-identical broad queries for one subtopic.
    begin=today-dt.timedelta(days=60)
    for lane,queries in LANES.items():
        for q in queries[:2]:
            tasks.append((lane,q,begin.isoformat(),today.isoformat(),"recent"))
    # A weekly issue backfills one historical year per theme so older studies
    # aren't frozen. A manually initiated backfill covers all historical years.
    weekly_index=(today.toordinal()//7)
    for index,(lane,queries) in enumerate(LANES.items()):
        chosen=all_years if mode=="backfill" else [all_years[(weekly_index+index)%len(all_years)]] if all_years else []
        for year in chosen:
            # Each year rotates its query to spread substantive coverage.
            q=queries[(year-START_YEAR+index+weekly_index)%len(queries)]
            tasks.append((lane,q,f"{year}-01-01",f"{year}-12-31",f"historical:{year}"))
    return tasks


def source_class(record):
    """Keep historic digital-attention foundations separate from GenAI work."""
    year=(record.get("published") or "")[:4]
    title=(record.get("title") or "").lower()
    text=(title+" "+(record.get("abstract_text") or record.get("preview") or "").lower())
    direct=bool(re.search(r"\\bai\\b",text)) or any(term in text for term in (
        "chatgpt","generative ai","generative artificial intelligence",
        "large language model","llm","gpt-4","gpt-3","ai-assisted",
        "ai-based","ai powered","ai-powered","artificial intelligence"))
    if year.isdigit() and int(year)<START_YEAR:
        return "Earlier digital-attention foundation" if not direct else "Historical AI context"
    if direct:return "AI-specific"
    return "Adjacent digital-attention evidence"
