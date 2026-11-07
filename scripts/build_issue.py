"""Build a weekly issue from validated editorial copy and source-backed readings.

The website's compose_issue workflow creates automatic drafts with evidence checks.
Manually edited copy is also supported. Failed drafts never replace a published issue.
The issue includes citations to the exact source records and a complete source shelf.
"""
from __future__ import annotations
import json,datetime,pathlib,re
from original_readings import public_record, publication_digest, apply as apply_original_readings, note_for
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/"data"
def source_id(x):return x.get("id") or (x.get("doi") or "").lower() or x.get("url") or x.get("title")
def find(needle,items):
 hits=[i for i,x in enumerate(items) if needle.casefold() in x.get("title","").casefold()]
 if len(hits)!=1:raise ValueError("Issue anchor must match exactly one source: "+needle+" (matches "+str(len(hits))+")")
 return items[hits[0]]
def checked_source_metadata(item):
 reading=item.get("reading") or {}
 source=reading if reading.get("original_summary") else item
 if not source.get("original_summary"):return {}
 return {"original_summary":True,**{key:source.get(key,"") for key in (
  "source_url","source_version","source_format","source_doi","related_journal_doi",
  "review_kind","review_scope")},"review_label":source.get("notice") or source.get("review_label",""),
 "original_reading_sha256":publication_digest(item["original_reading"]) if item.get("original_reading") else item.get("original_reading_sha256","")}

def resolve_queued_original(item):
 if not item.get("original_summary"):return item
 ident=str(item.get("id") or "")
 record={**item,"doi":ident if ident.lower().startswith("10.") else "",
         "url":item.get("url") or ident}
 apply_original_readings([record])
 note=record.get("original_reading")
 if not note or publication_digest(note) != item.get("original_reading_sha256"):
  raise ValueError("Queued original reading is no longer current; revalidate the issue before publication")
 record["reading"]=note_for(record)
 return record

def build(edition_date=None):
 weekly=json.loads((DATA/"public-weekly.json").read_text())
 editorial_path=DATA/"editorial-weekly.json"
 if not edition_date and editorial_path.exists():
  editorial=json.loads(editorial_path.read_text(encoding="utf-8"))
  if editorial.get("run",{}).get("date")==weekly.get("run",{}).get("date"):
   weekly=editorial
  else:
   raise ValueError("Editorial evidence packet is stale; rebuild public readings")
 if edition_date:
  datetime.date.fromisoformat(edition_date)
  packet=json.loads((DATA/"editorial-queue"/(edition_date+".json")).read_text(encoding="utf-8"))
  weekly={"run":{"date":edition_date},"items":[{**x,"reading":{"level":x.get("reading_level","")}} for x in packet["sources"]]}
 issue_date=(weekly.get("run") or {}).get("date") or ""
 drafts=json.loads((DATA/"issue-editorial.json").read_text())
 items=weekly.get("items") or []
 if not edition_date:
  checked=[]
  for item in items:
   current=public_record(item,require_current=True)
   if item.get("original_reading") != current.get("original_reading"):
    raise ValueError("Original reading changed or was revoked; rebuild the public source shelf and revalidate the issue before publication")
   if (current.get("reading") or {}).get("level") != "citation_only":checked.append(current)
  items=checked
 else:
  items=[resolve_queued_original(item) for item in items]
 schema={
  "edition_date":issue_date,"source_count":len(items),
  "types":{"scholarly":sum(x.get("kind")=="scholarly" for x in items),"commentary":sum(x.get("kind")!="scholarly" for x in items)},
  "material":{"full_text":sum(x.get("reading",{}).get("level")=="full_text" for x in items),
   "abstract":sum(x.get("reading",{}).get("level")=="abstract" for x in items),
   "publisher_or_editorial":sum(x.get("reading",{}).get("level")=="curated" for x in items)},
  "sources":[{"id":source_id(x),"title":x.get("title",""),"kind":x.get("kind",""),"venue":x.get("venue",""),
     "published":x.get("published",""),"reading_level":x.get("reading",{}).get("level",""),
     "research_type":x.get("research_type") or x.get("reading",{}).get("research_type",""),
     "url":x.get("url",""),
     "editorial_role":x.get("editorial_role","collection_week"),
     **checked_source_metadata(x)} for x in items],
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

