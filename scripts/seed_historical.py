"""Retrieve actual bibliographic metadata for verified early AI-attention anchor papers.

One OpenAlex DOI batch, no invented abstracts or paper-level findings.
Unresolved citations stay in the private library until an abstract/full text
can be verified. Anchors are editorially nominated, NOT automatically reviewed.
"""
from __future__ import annotations
import datetime
import json
import os
import pathlib
import urllib.parse
import urllib.request
import urllib.error
from search_plan import source_class
from update import abstract, key, TODAY

LIB=pathlib.Path(__file__).resolve().parents[1]/"data/library.json"
ANCHORS={
 "10.1371/journal.pone.0286102":("Fragmentation","Earlier related work on algorithmic offloading"),
 "10.1002/brx2.30":("AI & cognition","AI and cognition context"),
 "10.1016/j.caeai.2023.100198":("AI & cognition","ChatGPT learning outcomes"),
 "10.1016/j.chb.2024.108386":("AI & cognition","LLM cognitive load versus depth of reasoning"),
 "10.1080/03075079.2024.2316881":("AI & cognition","AI text generators and critical thinking"),
 "10.1080/02188791.2024.2305163":("AI & cognition","Teacher collaboration versus ChatGPT"),
 "10.1145/3706598.3713778":("AI & cognition","Knowledge-worker critical thinking"),
 "10.3390/data10110172":("Interventions","Structured prompting experiment"),
 "10.1108/idd-05-2025-0125":("AI & cognition","Critical thinking evidence review"),
 "10.1016/j.actpsy.2025.105725":("AI & cognition","AI reliance and cognitive fatigue"),
 "10.1016/j.caeai.2026.100571":("AI & cognition","Higher-education critical-thinking evidence review"),
}
def run():
 records=json.loads(LIB.read_text())
 found={r.get("doi","").lower() for r in records}
 remaining=[doi for doi in ANCHORS if doi not in found]
 if not remaining:
  print(json.dumps({"historical_anchor_added":0,"all_present":True}));return
 filt="doi:"+"|".join("https://doi.org/"+doi for doi in remaining)
 params={"filter":filt,"per_page":len(remaining),"select":"id,doi,title,publication_date,abstract_inverted_index,authorships,primary_location,open_access"}
 if os.getenv("OPENALEX_API_KEY"):params["api_key"]=os.environ["OPENALEX_API_KEY"]
 req=urllib.request.Request("https://api.openalex.org/works?"+urllib.parse.urlencode(params),
    headers={"User-Agent":"AttentionAIObservatory/4.0 metadata-index (fangcu@ucmail.uc.edu)",
             "Accept":"application/json"})
 try:
  with urllib.request.urlopen(req,timeout=35) as response:
   works=json.load(response).get("results",[])
 except (urllib.error.URLError,TimeoutError,ValueError) as exc:
  print(json.dumps({"historical_anchor_added":0,"status":"deferred_api_error","error":str(exc)[:120]}))
  return
 mapping={(w.get("doi") or "").replace("https://doi.org/","").lower():w for w in works}
 new=[]
 for doi in remaining:
  w=mapping.get(doi)
  if not w or not w.get("title"):continue
  abst=abstract(w.get("abstract_inverted_index"))
  loc=w.get("primary_location") or {}
  venue=(loc.get("source") or {}).get("display_name") or "OpenAlex"
  meta={
    "title":w["title"],"authors":[a.get("author",{}).get("display_name","") for a in w.get("authorships",[])[:8]],
    "published":w.get("publication_date") or "","venue":venue,"doi":doi,
    "url":"https://doi.org/"+doi,"preview":abst[:420] if len(abst)>=90 else "Bibliographic record awaiting accessible source text.",
    "abstract_text":abst[:3800] if len(abst)>=90 else "",
    "abstract_source":"OpenAlex indexed abstract" if len(abst)>=90 else "",
    "kind":"scholarly","lane":ANCHORS[doi][0],"relation":"AI-related literature",
    "evidence":"DOI-verified metadata; abstract requires source checking",
    "source":"Verified historical DOI anchor (OpenAlex metadata)","curated":True,
    "historical_backfill":True,"first_seen":TODAY,"source_checked":TODAY,
    "discovery_scope":"historical_anchor","reading":{"level":"citation_only"},
  }
  meta["source_group"]=source_class(meta)
  new.append(meta)
 if new:
  records.extend(new)
  records.sort(key=lambda r:(r.get("published") or "",r.get("first_seen") or ""),reverse=True)
  LIB.write_text(json.dumps(records,ensure_ascii=False,indent=2)+"\n")
 print(json.dumps({"historical_anchor_added":len(new),"with_abstract":sum(len(x["abstract_text"])>=90 for x in new),
                   "not_located":len(remaining)-len(new)}))
if __name__=="__main__":run()
