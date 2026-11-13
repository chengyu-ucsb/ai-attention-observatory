"""Build a weekly issue from validated editorial copy and source-backed readings.

The website's compose_issue workflow creates automatic drafts with evidence checks.
Manually edited copy is also supported. Failed drafts never replace a published issue.
The issue includes citations to the exact source records and a complete source shelf.
"""
from __future__ import annotations
import json,datetime,pathlib,re
from urllib.parse import urlsplit
from original_readings import public_record, publication_digest, apply as apply_original_readings, note_for, identifier
from checked_reading_types import record_context, RECORD_FIELDS
from collection_window import window_metadata,previous_week,weekly_eligible
from edition_schedule import canonical_edition_date
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/"data"
def source_id(x):return x.get("id") or (x.get("doi") or "").lower() or x.get("url") or x.get("title")
def find(needle,items):
 hits=[i for i,x in enumerate(items) if needle.casefold() in x.get("title","").casefold()]
 if len(hits)!=1:raise ValueError("Issue anchor must match exactly one source: "+needle+" (matches "+str(len(hits))+")")
 return items[hits[0]]
def citation_url(source):
 """Prefer the actual edition read; allow ordinary HTTPS publisher URLs."""
 for value in (source.get("source_url"),source.get("url")):
  if not isinstance(value,str) or re.search(r'\s|\\|[\x00-\x1f]',value):continue
  try:
   parsed=urlsplit(value)
   if parsed.scheme=="https" and parsed.hostname and not parsed.username and not parsed.password:
    parsed.port  # Reject malformed ports.
    return value
  except ValueError:pass
 raise ValueError("Citation source requires a valid HTTPS source URL: "+str(source.get("title","")))

def validate_section_citations(section,sources,required=False):
 """Resolve exact visible spans before publication; never edit escaped HTML."""
 text=section.get("text","")
 entries=section.get("citations",[])
 if not isinstance(entries,list):raise ValueError("Section citations must be a list")
 resolved=[];spans=[]
 allowed=section.get("source_ids",[])
 for entry in entries:
  if not isinstance(entry,dict):raise ValueError("Invalid inline citation")
  phrase=entry.get("text")
  if not isinstance(phrase,str) or not phrase.strip():raise ValueError("Citation text must not be empty")
  starts=[m.start() for m in re.finditer('(?='+re.escape(phrase)+')',text)]
  if len(starts)!=1:raise ValueError("Citation text must occur exactly once: "+phrase)
  hits=[s for s in sources if s.get("id") in allowed and
        (s.get("title")==entry["source"] if "source" in entry else s.get("id")==entry.get("source_id"))]
  if len(hits)!=1:raise ValueError("Citation must resolve to exactly one section source: "+str(entry))
  source=hits[0]
  if entry.get("source_id") and entry["source_id"]!=source["id"]:raise ValueError("Citation source identity mismatch")
  citation_url(source)
  if "page" in entry and (type(entry["page"]) is not int or entry["page"]<1):raise ValueError("Citation page must be a positive integer")
  if "locator" in entry and (not isinstance(entry["locator"],str) or not entry["locator"].strip()):raise ValueError("Citation locator must be nonempty text")
  start=starts[0];end=start+len(phrase)
  if any(start<b and end>a for a,b in spans):raise ValueError("Inline citation spans overlap")
  spans.append((start,end))
  resolved.append({**entry,"source_id":source["id"],"text":phrase})
 if required and (not allowed or set(allowed)!={c["source_id"] for c in resolved}):
  raise ValueError("Each section source needs an explicit inline citation")
 return resolved

def validate_issue_citations(issue):
 if issue.get('edition_format')=='coverage':
  from publish_deadline import validate_coverage
  validate_coverage(issue)
  return issue
 version=issue.get("citation_schema_version")
 if version is not None and (type(version) is not int or version!=1):raise ValueError("Unsupported citation schema version")
 for section in issue.get("signals",[])+[issue.get("tension",{})]:
  citations=validate_section_citations(section,issue.get("sources",[]),required=version==1)
  if "citations" in section or version==1:section["citations"]=citations
 glossary=issue.get("glossary",[])
 if not isinstance(glossary,list):raise ValueError("Glossary must be a list")
 seen=set()
 for entry in glossary:
  if not isinstance(entry,dict) or any(not isinstance(entry.get(k),str) or not entry[k].strip() for k in ("term","definition")):
   raise ValueError("Glossary entries require a term and definition")
  term=entry["term"].casefold()
  if term in seen:raise ValueError("Duplicate glossary term")
  seen.add(term)
 return issue

def checked_source_metadata(item):
 reading=item.get("reading") or {}
 source=reading if reading.get("original_summary") else item
 if not source.get("original_summary"):return {}
 return {"original_summary":True,
 **({"original_record_context":record_context(item)} if (item.get("original_reading") or {}).get("article_screen")
    else {"original_record_context":item["original_record_context"]} if item.get("original_record_context") else {}),**{key:source.get(key,"") for key in (
  "source_url","source_version","source_format","source_doi","related_journal_doi",
  "review_kind","review_scope","quality_note","temporal","temporal_notice",
  "genre","attributed_to","evidence","research_type")},"review_label":source.get("notice") or source.get("review_label",""),
 "original_reading_sha256":publication_digest(item["original_reading"]) if item.get("original_reading") else item.get("original_reading_sha256","")}

def resolve_queued_original(item):
 if not item.get("original_summary"):
  if any(item.get(key) for key in ("original_reading_sha256","review_kind","source_version")):
   raise ValueError("Queued original reading marker is incomplete; revalidate the issue before publication")
  return item
 ident=str(item.get("id") or "")
 record={**item,"doi":ident if ident.lower().startswith("10.") else "",
         "url":item.get("url") or ident}
 context=item.get("original_record_context")
 if context is not None:
  if not isinstance(context,dict) or set(context)!=set(RECORD_FIELDS):
   raise ValueError("Queued original record context is invalid; revalidate the issue")
  for key in ("title","kind","url","venue","published","publication_date_provenance"):
   if item.get(key)!=context.get(key):
    raise ValueError("Queued original record context changed; revalidate the issue")
  if identifier(context)!=(ident.lower() if ident.lower().startswith("10.") else ident):
   raise ValueError("Queued original identity changed; revalidate the issue")
  record.update(context)
  # Topic screening may depend on the current abstract, which must not be
  # copied into the public queue merely to reconstruct a display record.
  library_path=DATA/"library.json"
  if not library_path.exists():
   raise ValueError("Current index unavailable; rebuild and revalidate the issue")
  if library_path.exists():
   library=json.loads(library_path.read_text())
   candidates=[r for r in library if identifier(r)==identifier(record)]
   if len(candidates)!=1 or record_context(candidates[0])!=context:
    raise ValueError("Current indexed record changed; rebuild and revalidate the issue")
   record.update(candidates[0])
 apply_original_readings([record])
 note=record.get("original_reading")
 if note and note.get("article_screen") and context is None:
  raise ValueError("Queued original record context is missing; rebuild and revalidate the issue")
 if not note or publication_digest(note) != item.get("original_reading_sha256"):
  raise ValueError("Queued original reading is no longer current; revalidate the issue before publication")
 record["reading"]=note_for(record)
 return record

def build(edition_date=None, use_published_sources=False):
 if use_published_sources and not edition_date:raise ValueError("Published source correction requires an explicit edition date")
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
  packet_path=DATA/("approved-issues" if use_published_sources else "editorial-queue")/(edition_date+".json")
  packet=json.loads(packet_path.read_text(encoding="utf-8"))
  if use_published_sources and packet.get("status")!="published":raise ValueError("Correction requires an existing published edition")
  weekly={"run":{"date":edition_date,"publication_window":packet.get("publication_window") or window_metadata(edition_date)},"items":[{**x,"reading":{"level":x.get("reading_level","")}} for x in packet["sources"]]}
 issue_date=(weekly.get("run") or {}).get("date") or ""
 if issue_date and not edition_date:issue_date=canonical_edition_date(DATA.parent,issue_date)
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
 if weekly.get("run",{}).get("date"):
  weekly["run"].setdefault("publication_window",window_metadata(weekly["run"]["date"]))
  expected=window_metadata(weekly["run"]["date"])
  if any(weekly["run"]["publication_window"].get(key)!=expected[key] for key in ("from","to","timezone")):
   raise ValueError("Publication window does not match previous completed UTC week")
  bounds=previous_week(weekly["run"]["date"])
  if any(not weekly_eligible(x,*bounds) for x in items):
   raise ValueError("Weekly source lacks verified previous-week original publication evidence; rebuild/review the source shelf")
 schema={
  "edition_date":issue_date,"source_count":len(items),
  **({"publication_window":weekly["run"]["publication_window"]} if weekly.get("run",{}).get("publication_window") else {}),
  "types":{"scholarly":sum(x.get("kind")=="scholarly" for x in items),"commentary":sum(x.get("kind")!="scholarly" for x in items)},
  "material":{"full_text":sum(x.get("reading",{}).get("level")=="full_text" for x in items),
   "abstract":sum(x.get("reading",{}).get("level")=="abstract" for x in items),
   "publisher_or_editorial":sum(x.get("reading",{}).get("level")=="curated" for x in items)},
  "sources":[{"id":source_id(x),"title":x.get("title",""),"kind":x.get("kind",""),"venue":x.get("venue",""),
     "published":x.get("published",""),"publication_date_provenance":x.get("publication_date_provenance",{}),"reading_level":x.get("reading",{}).get("level",""),
     "research_type":x.get("research_type") or x.get("reading",{}).get("research_type",""),
     "url":x.get("url",""),
     "editorial_role":x.get("editorial_role","collection_week"),
     **checked_source_metadata(x)} for x in items],
  "status":"awaiting_publication",
  "note":"New source records have been indexed. The website's weekly synthesis has not yet passed publication checks."
 }
 draft=drafts.get(issue_date)
 existing_archive=DATA/"approved-issues"/(issue_date+".json")
 if not edition_date and schema.get("publication_window") and existing_archive.exists():
  archived=json.loads(existing_archive.read_text(encoding="utf-8"))
  if archived.get("status")=="published" and archived.get('edition_format')!='coverage':
   # A new collection rule/shelf must not rewrite an already published edition.
   draft=None
 if draft:
  if len(items)<(2 if draft.get("edition_format")=="compact" else 3):raise ValueError("Issue has too few source-backed items for its format")
  cards=[]
  for sig in draft["signals"]:
   cited=[find(name,items) for name in sig["sources"]]
   cards.append({**sig,"source_ids":[source_id(x) for x in cited]})
  tension=draft["tension"].copy()
  tension["source_ids"]=[source_id(find(name,items)) for name in tension["sources"]]
  schema.update({k:draft[k] for k in ("number","subject","headline","deck","letter","experiment","closer","editorial_note")})
  for key in ("citation_schema_version","glossary","edition_format"):
   if key in draft:schema[key]=draft[key]
  schema["signals"]=cards
  schema["tension"]=tension
  schema["status"]="published"
  schema["note"]="Published edition; see editorial_note for evidence and synthesis qualifications."
 if schema["status"]=="published":validate_issue_citations(schema)
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
 parser.add_argument("--use-published-sources",action="store_true",help="Correct an archived edition against its frozen source shelf, revalidating current review and original dates")
 args=parser.parse_args()
 build(args.edition_date,use_published_sources=args.use_published_sources)

