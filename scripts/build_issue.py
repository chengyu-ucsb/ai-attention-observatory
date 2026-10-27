"""Build a weekly issue from validated editorial copy and source-backed readings.

The website's compose_issue workflow creates automatic drafts with evidence checks.
Manually edited copy is also supported. Failed drafts never replace a published issue.
The issue includes citations to the exact source records and a complete source shelf.
"""
from __future__ import annotations
import json,datetime,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/"data"
def source_id(x):return x.get("id") or (x.get("doi") or "").lower() or x.get("url") or x.get("title")
def find(needle,items):
 hits=[i for i,x in enumerate(items) if needle.casefold() in x.get("title","").casefold()]
 if len(hits)!=1:raise ValueError("Issue anchor must match exactly one source: "+needle+" (matches "+str(len(hits))+")")
 return items[hits[0]]
def build(edition_date=None):
 weekly=json.loads((DATA/"public-weekly.json").read_text())
 if edition_date:
  datetime.date.fromisoformat(edition_date)
  packet=json.loads((DATA/"editorial-queue"/(edition_date+".json")).read_text(encoding="utf-8"))
  weekly={"run":{"date":edition_date},"items":[{**x,"reading":{"level":x.get("reading_level","")}} for x in packet["sources"]]}
 issue_date=(weekly.get("run") or {}).get("date") or ""
 drafts=json.loads((DATA/"issue-editorial.json").read_text())
 items=weekly.get("items") or []
 schema={
  "edition_date":issue_date,"source_count":len(items),
  "types":{"scholarly":sum(x.get("kind")=="scholarly" for x in items),"commentary":sum(x.get("kind")!="scholarly" for x in items)},
  "material":{"full_text":sum(x.get("reading",{}).get("level")=="full_text" for x in items),
   "abstract":sum(x.get("reading",{}).get("level")=="abstract" for x in items),
   "publisher_or_editorial":sum(x.get("reading",{}).get("level")=="curated" for x in items)},
  "sources":[{"id":source_id(x),"title":x.get("title",""),"kind":x.get("kind",""),"venue":x.get("venue",""),
     "published":x.get("published",""),"reading_level":x.get("reading",{}).get("level",""),
     "url":x.get("url","")} for x in items],
  "status":"awaiting_publication",
  "note":"New source records have been indexed. The website's weekly synthesis has not yet passed publication checks."
 }
 draft=drafts.get(issue_date)
 if draft:
  if len(items)<3:raise ValueError("Issue must have at least three source-backed items")
  cards=[]
  for sig in draft["signals"]:
   cited=[find(name,items) for name in sig["sources"]]
   cards.append({**sig,"source_ids":[source_id(x) for x in cited]})
  tension=draft["tension"].copy()
  tension["source_ids"]=[source_id(find(name,items)) for name in tension["sources"]]
  schema.update({k:draft[k] for k in ("number","subject","headline","deck","letter","experiment","closer","editorial_note")})
  schema["signals"]=cards
  schema["tension"]=tension
  schema["status"]="published"
  schema["note"]="Published edition; see editorial_note for evidence and synthesis qualifications."
 (DATA/"public-issue.json").write_text(json.dumps(schema,ensure_ascii=False,indent=2)+"\n")
 # Readers see the latest completed issue while the next week's editorial
 # work stays private. Keep the newest unreviewed source shelf in public-issue
 # for research coverage checks, but never put editorial queue states on pages.
 archived=sorted((DATA/"approved-issues").glob("????-??-??.json"),reverse=True) if (DATA/"approved-issues").exists() else []
 featured=next((json.loads(p.read_text(encoding="utf-8")) for p in archived
                if json.loads(p.read_text(encoding="utf-8")).get("status")=="published"),None)
 if schema["status"]=="published" and (featured is None or schema["edition_date"]>=featured.get("edition_date","")):
  featured=schema
 if featured is None:
  featured={"status":"none","headline":"","deck":"","signals":[],"sources":[],"source_count":0}
 (DATA/"public-featured-issue.json").write_text(json.dumps(featured,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"issue_date":issue_date,"status":schema["status"],"sources_in_shelf":len(items),"themes":len(schema.get("signals",[]))}))
 return schema
if __name__=="__main__":
 import argparse
 parser=argparse.ArgumentParser()
 parser.add_argument("--edition-date",help="Build a reviewed issue from its saved source shelf")
 build(parser.parse_args().edition_date)
