"""Weekly metadata collector for AI and attention research (no full-text scraping)."""
import json, re, os, time, urllib.request, urllib.parse, urllib.error, datetime, pathlib
from search_plan import plan,source_class
from arxiv_publication import ArxivPublicationVerifier, identifier_for as arxiv_identifier
from priority_research import discover as discover_priority, crossref_article, crossref_search, doi_id
from collection_window import (crossref_publication, date_in_window, previous_week,
                               publication_date, weekly_eligible, window_metadata, reconcile_publication_evidence)
ROOT=pathlib.Path(__file__).resolve().parents[1]
DIR=ROOT/"data"
TODAY=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
KEYWORDS=re.compile(r"attention|cognit|think|interrup|focus|distract|multitask|switch|well.?being|self.regulat|engag|notification|offload|metacognit|overreliance|problem.solv|dependency",re.I)

AI_TOPIC=re.compile(r"\b(?:ai|genai|chatgpt|artificial intelligence|generative ai|llms?|large language model|machine learning|algorithmic)\b",re.I)
ATTENTION_TOPIC=re.compile(r"attention|focus|distract|interrupt|offload|critical think|cognit(?:ive)? (?:effort|load|scaffold|control|strain|decline)|human agency|mindful|metacognit|well.?being|notification|self.regulat|task.switch|multitask|information overload|techno.?stress|digital stress|cognitive autonomy|problem.solv|epistemic",re.I)
ADJACENT_TOPIC=re.compile(r"attention (?:fragmentation|residue|economy|control|span)|digital distraction|distracted (?:work|learning)|notification(?:s)?|task.switch|multitask|sustained attention|focus(?:ed)? work",re.I)
EXCLUDE_TITLE=re.compile(r"gaining .*attention|stock price|share price|trading|market investment|marketing personalization|consumer engagement|car.following|warehouse logistics|diabetes mellitus|security tools",re.I)
TRUSTED_OUTLETS=re.compile(r"The Atlantic|WIRED|MIT Technology Review|Nature|Science|The Verge|Tech Policy Press|The Guardian|The Conversation|Ars Technica|Harvard Business Review|New York Times|Financial Times|Bloomberg|BBC|NPR|Vox|IEEE Spectrum|Quanta|The Decoder|Inside Higher Ed|EdSurge|PsyPost|New Scientist|Washington Post|Psychology Today|Communications of the ACM|The Economist|Rest of World",re.I)
def relevant(x):
 if x.get("curated"):return True
 if x.get("kind")=="nonacademic" and x.get("source")=="Publisher RSS / Google News RSS":
  return (not x.get("published") or x["published"]<=TODAY) and bool(AI_TOPIC.search((x.get("title") or "")+" "+(x.get("preview") or "")) and ATTENTION_TOPIC.search((x.get("title") or "")+" "+(x.get("preview") or "")))
 if x.get("published") and x["published"]>TODAY:return False
 title=x.get("title","");blurb=x.get("preview","")
 if EXCLUDE_TITLE.search(title):return False
 direct=(bool(AI_TOPIC.search(title)) and bool(ATTENTION_TOPIC.search(title+" "+blurb))) or (bool(ATTENTION_TOPIC.search(title)) and bool(AI_TOPIC.search(blurb)))
 adjacent=bool(ADJACENT_TOPIC.search(title)) and x.get("lane")=="Fragmentation" and x.get("kind")=="scholarly"
 if not (direct or adjacent):return False
 if x.get("kind")=="nonacademic" and not TRUSTED_OUTLETS.search(x.get("venue","")):return False
 return True
def diverse_week(items,limit=None):
 """Interleave themes without silently dropping any eligible source."""
 items=sorted(items,key=lambda x:x.get("published") or "",reverse=True)
 lanes=list(dict.fromkeys(["AI & cognition","Fragmentation","Interventions","Technology & society"]+[x.get("lane","") for x in items]))
 batches={lane:[x for x in items if x.get("lane","")==lane] for lane in lanes}
 out=[]
 while any(batches.values()) and (limit is None or len(out)<limit):
  for lane in batches:
   if batches[lane] and (limit is None or len(out)<limit):out.append(batches[lane].pop(0))
 return out

def read(p,default):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return default
def key(x):
 doi=(x.get("doi") or "").lower()
 if doi:return "doi:"+doi
 return "title:"+re.sub("[^a-z0-9]","",(x.get("title") or "").lower())[:140]
def request(url):
 req=urllib.request.Request(url,headers={"User-Agent":"AttentionAIObservatory/1.1 academic metadata research (contact via repository README)","Accept":"application/json"})
 with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)
def abstract(inv):
 if not isinstance(inv,dict):return ""
 return " ".join(word for _,word in sorted((p,word) for word,ps in inv.items() for p in ps if isinstance(p,int)))[:800]
def openalex_search(params, *, max_pages=5, page_size=100):
 rows=[]; errors=[]; cursor="*"; seen_cursors=set()
 audit={"provider":"OpenAlex","query":params.get("search", ""),"filter":params.get("filter", ""),
        "pages":0,"records_seen":0,"provider_total":None,"max_pages":max_pages,"page_size":page_size,
        "status":"complete","truncated":False}
 if max_pages<1:return [],dict(audit,status="truncated",truncated=True,reason="page budget is zero"),[]
 for page in range(max_pages):
  try:
   result=request("https://api.openalex.org/works?"+urllib.parse.urlencode(dict(params,per_page=page_size,cursor=cursor)))
   if not isinstance(result.get("results"),list):raise ValueError("Malformed OpenAlex search response")
   works=result["results"];meta=result.get("meta") or {}
   audit["pages"]+=1;audit["provider_total"]=meta.get("count",audit["provider_total"])
   rows.extend(works);audit["records_seen"]=len(rows)
   total=audit["provider_total"]
   if not works:
    if isinstance(total,int) and len(rows)<total:audit.update(status="truncated",truncated=True,reason="empty page before reported total")
    break
   if (isinstance(total,int) and len(rows)>=total) or (len(works)<page_size and not isinstance(total,int)):break
   next_cursor=meta.get("next_cursor")
   if not next_cursor or next_cursor==cursor or next_cursor in seen_cursors:
    audit.update(status="truncated",truncated=True,reason="provider did not supply a new cursor");break
   seen_cursors.add(cursor);cursor=next_cursor
   if page+1==max_pages:audit.update(status="truncated",truncated=True,reason="page budget reached")
  except Exception as exc:
   reason="HTTP "+str(exc.code) if hasattr(exc,"code") else type(exc).__name__
   audit.update(status="error",truncated=True,reason=reason)
   if getattr(exc,"code",None)==429:audit["quota_exhausted"]=True
   if getattr(exc,"code",None) in (403,429):audit["provider_paused"]=True
   errors.append("OpenAlex search unavailable: "+reason);break
 return rows,audit,errors


def discover(days=None,mode="weekly",max_pages=5,page_size=100,max_date_lookups=100,arxiv_verifier=None):
 """Collect metadata within explicit publication windows, with coverage limits."""
 found=[];errors=[];stats={"openalex":0,"crossref":0,"provider_windows":[],
                         "publication_date_rejected":0,"publication_date_unverified":0,"publication_date_quarantine":[],
                         "date_lookups":0,"date_lookups_deferred":0}
 today=datetime.date.fromisoformat(TODAY)
 scopes=plan(today,mode)
 stats["search_scopes"]=[{"theme":lane,"period":scope,"from":start,"to":end,"query":q} for lane,q,start,end,scope in scopes]
 stats["queries_planned"]=2*len(scopes);stats["queries_attempted"]=0
 crossref_dates={};crossref_paused=False
 for lane,q,start,end,scope in scopes:
  params={"search":q,"filter":"from_publication_date:"+start+",to_publication_date:"+end,
          **({"api_key":os.environ["OPENALEX_API_KEY"]} if os.getenv("OPENALEX_API_KEY") else {})}
  works,audit,provider_errors=openalex_search(params,max_pages=max_pages,page_size=page_size)
  audit.update(theme=lane,scope=scope);stats["provider_windows"].append(audit)
  errors.extend(provider_errors);stats["openalex"]+=len(works);stats["queries_attempted"]+=1
  for w in works:
   title=w.get("title") or "";ab=abstract(w.get("abstract_inverted_index"));doi=doi_id(w.get("doi"))
   if not title or not KEYWORDS.search(title+" "+ab) or w.get("is_retracted"):continue
   pub=publication_date(w.get("publication_date"))
   if not date_in_window(pub,start,end):stats["publication_date_rejected"]+=1;continue
   loc=w.get("primary_location") or {};venue=(loc.get("source") or {}).get("display_name") or "OpenAlex"
   authors=[a.get("author",{}).get("display_name","") for a in w.get("authorships",[])[:8]]
   found.append({"title":title,"authors":authors,"published":pub.isoformat(),"venue":venue,"doi":doi,
     "publication_date_provenance":{"source":"OpenAlex","field":"publication_date","value":pub.isoformat(),"status":"day_known","original_day_verified":False},
     "url":"https://doi.org/"+doi if doi else w.get("id",""),
     "preview":ab[:420]+("…" if len(ab)>420 else "") if ab else "Abstract unavailable; bibliographic metadata only.",
     "abstract_text":ab[:3800],"abstract_source":"OpenAlex abstract index" if ab else "","kind":"scholarly","lane":lane,
     "relation":"AI-related literature" if re.search(r"\bAI\b|artificial intelligence|generative",title+" "+ab,re.I) else "Adjacent digital-attention evidence",
     "evidence":"Metadata screened (unverified)","source":"OpenAlex","curated":False,"first_seen":TODAY,
     "discovery_scope":scope,"discovery_query":q,"historical_backfill":mode=="backfill"})
  if audit.get("provider_paused"):break
  time.sleep(.3)
 for lane,q,start,end,scope in scopes:
  works,audit,provider_errors=crossref_search(request,{"query.bibliographic":q,"filter":"from-pub-date:"+start+",until-pub-date:"+end},max_pages=max_pages,page_size=page_size)
  audit.update(theme=lane,scope=scope);stats["provider_windows"].append(audit)
  errors.extend(provider_errors);stats["crossref"]+=len(works);stats["queries_attempted"]+=1
  for w in works:
   doi=doi_id(w.get("DOI"));datev,provenance=crossref_publication(w)
   if doi:crossref_dates[doi]=reconcile_publication_evidence(crossref_dates.get(doi),(datev,provenance))
   x=crossref_article(w,lane=lane,scope=scope,query=q,today=today,screen=False)
   if not x or not date_in_window(datev,start,end):stats["publication_date_rejected"]+=1;continue
   x["source"]="Crossref";x["historical_backfill"]=mode=="backfill"
   if KEYWORDS.search(x["title"]+" "+x["abstract_text"]):found.append(x)
  if audit.get("provider_paused"):
   crossref_paused=True;break
  time.sleep(.3)
 # A print/issue date must not turn an old online-first paper into new work.
 # Verify DOI-backed OpenAlex candidates against the publication events in
 # Crossref. Missing registry evidence is fail-closed for the weekly set.
 if mode=="weekly":
  start,end=previous_week(today)
  kept=[];deferred=set();quarantined={};conflicts={};quota=crossref_paused
  arxiv=arxiv_verifier or ArxivPublicationVerifier()
  def quarantine(x,reason):
   pending=dict(x)
   evidence=dict(x.get("publication_date_provenance") or {})
   evidence.update(status="unresolved",reason=reason,provider_publication_date=x.get("published", ""))
   pending.update(published="",publication_date_provenance=evidence,acquisition_status="original_publication_date_required")
   quarantined[key(x)]=pending
  for x in found:
   if x["source"]=="OpenAlex" and arxiv_identifier(x):
    day,provenance=arxiv.verify(x)
    if x.get("doi"):crossref_dates[x["doi"]]=(day,provenance)
    x["publication_date_provenance"]=provenance
    if day:
     x["published"]=day
     if date_in_window(day,start,end):kept.append(x)
     else:stats["publication_date_rejected"]+=1
    else:quarantine(x,provenance.get("reason", "arXiv original publication day unresolved"))
    continue
   if x["source"]=="OpenAlex" and not x.get("doi"):
    quarantine(x,"OpenAlex publication_date alone does not verify the original publication event")
    continue
   if x["source"]=="OpenAlex" and x.get("doi"):
    doi=x["doi"]
    if doi not in crossref_dates:
     if quota or stats["date_lookups"]>=max_date_lookups:
      deferred.add(doi);quarantine(x,"Original-day verification deferred by provider or lookup budget");continue
     stats["date_lookups"]+=1
     try:
      result=request("https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="/"))
      work=result.get("message") or {}
      if doi_id(work.get("DOI"))!=doi:raise ValueError("DOI identity mismatch")
      crossref_dates[doi]=crossref_publication(work)
     except Exception as exc:
      reason="HTTP "+str(exc.code) if hasattr(exc,"code") else type(exc).__name__
      errors.append("Original publication date unavailable for "+doi+": "+reason)
      crossref_dates[doi]=("",{"source":"Crossref","status":"unresolved","reason":reason,"verification_error":True})
      if getattr(exc,"code",None) in (403,429):quota=True;crossref_paused=True
    registry_day,provenance=crossref_dates[doi]
    # An earlier generic OpenAlex day is conflicting evidence, not a
    # publisher-verified original date. Never relabel it as Crossref evidence.
    if registry_day and x["published"]<registry_day:
     provenance=dict(provenance,status="conflict",reason="OpenAlex date precedes verified publisher events; original date conflict requires review",
                     openalex_publication_date=x["published"],crossref_publication_date=registry_day,
                     requires_explicit_date_resolution=True)
     conflicts[doi]=provenance
     x["publication_date_provenance"]=provenance
     quarantine(x,provenance["reason"])
     x["published"]=""
    elif registry_day:
     provenance=dict(provenance,openalex_publication_date=x["published"])
     x["published"]=registry_day
    else:
     quarantine(x,"Crossref original-publication day unavailable or unresolved")
     x["published"]=""
    x["publication_date_provenance"]=provenance
   canonical=crossref_dates.get(doi_id(x.get("doi")))
   if x["source"]!="OpenAlex" and canonical:
    x["published"],x["publication_date_provenance"]=canonical
   if date_in_window(x["published"],start,end):kept.append(x)
   else:stats["publication_date_rejected"]+=1
  # A disputed DOI cannot re-enter through another query or provider. Keep
  # the conflict correction so existing indexed records fail closed too.
  found=[x for x in kept if doi_id(x.get("doi")) not in conflicts]
  for doi,provenance in conflicts.items():crossref_dates[doi]=("",provenance)
  stats["date_lookups_deferred"]=len(deferred)
  stats["publication_date_unverified"]=len(quarantined)
  stats["publication_date_quarantine"]=list(quarantined.values())
  stats["arxiv_publication_verification"]=arxiv.audit
 # Used to correct existing records even when an earlier original date
 # rightly removes a rediscovered paper from this week. Not a public count.
 stats["publication_date_corrections"]=crossref_dates
 stats["crossref_provider_paused"]=crossref_paused
 stats["queries_deferred"]=stats["queries_planned"]-stats["queries_attempted"]
 stats["discovery_status"]="partial" if errors or stats["queries_deferred"] or stats["date_lookups_deferred"] or stats["publication_date_unverified"] or any(a["truncated"] for a in stats["provider_windows"]) else "complete"
 stats["coverage_note"]="Bounded provider/query coverage, not exhaustive web or literature coverage; candidates still require article screening."
 return found,errors,stats
def apply_publication_evidence(current, day, provenance):
 """Refresh registry evidence without losing a known earlier original event."""
 prior=current.get("publication_date_provenance") or {}
 # Routine later metadata cannot resolve a genuine provider date conflict.
 # Preserve its evidence until an explicit source check resolves the dispute.
 if prior.get("requires_explicit_date_resolution") and not provenance.get("requires_explicit_date_resolution"):
  return
 trusted_prior=weekly_eligible({**current,"historical_backfill":False,"discovery_scope":""},datetime.date.min,datetime.date.max)
 older=current.get("published") if trusted_prior else None
 if provenance.get("verification_error") and publication_date(older):return
 selected=min(older,day) if day and publication_date(older) else day
 refreshed=dict(provenance,value=selected)
 if selected and selected==older and selected!=day:
  refreshed["earlier_publication_evidence"]=prior
 current["published"]=selected
 current["publication_date_provenance"]=refreshed


def main():
 DIR.mkdir(exist_ok=True)
 previous=read(DIR/"library.json",[])
 # Preserve previously found scholarly metadata, including unverified venues,
 # as internal review candidates; the public selection is a separate gate.
 records={key(x):x for x in previous if x.get("kind")=="scholarly" or relevant(x)}
 for record in records.values():record["source_group"]=source_class(record)
 mode=os.environ.get("MODE","weekly")
 candidates,errors,stats=discover(mode=mode)
 if stats.get("crossref_provider_paused"):
  priority=[];priority_errors=["Crossref unavailable or rate-limited; journal searches deferred."]
  priority_stats={"discovery_status":"partial","deferred_reason":"Crossref provider paused"}
 else:
  priority,priority_errors,priority_stats=discover_priority(
   request,datetime.date.fromisoformat(TODAY),mode=mode,
   existing_dois={x.get("doi") for x in records.values() if x.get("doi")}
  )
 corrections=stats.pop("publication_date_corrections",{})
 for doi,evidence in priority_stats.pop("publication_date_corrections",{}).items():
  corrections[doi]=reconcile_publication_evidence(corrections.get(doi),evidence)
 for current in records.values():
  known=corrections.get(doi_id(current.get("doi")))
  if known:
   day,provenance=known
   apply_publication_evidence(current,day,provenance)
 quarantined=stats.pop("publication_date_quarantine",[])
 for pending in quarantined:
  if relevant(pending) and key(pending) not in records:
   pending["source_group"]=source_class(pending)
   records[key(pending)]=pending
 candidates=priority+candidates
 errors.extend(priority_errors)
 stats["priority_and_journal_discovery"]=priority_stats
 stats["discovery_status"]="partial" if errors or stats.get("discovery_status")=="partial" or priority_stats.get("discovery_status")=="partial" else "complete"
 if stats["discovery_status"]=="partial":
  print("::warning::Discovery completed with some unavailable provider searches; see run diagnostics.")
 new=[]
 for x in candidates:
  canonical=corrections.get(doi_id(x.get("doi")))
  if canonical:apply_publication_evidence(x,*canonical)
  k=key(x)
  if not x["title"] or not x["url"] or (not relevant(x) and x.get("discovery_scope") not in {"editorial_priority","historical:editorial_priority"}):continue
  if mode=="weekly" and not weekly_eligible(x,*previous_week(TODAY)):continue
  if k in records:
   current=records[k]
   if x.get("publication_date_provenance"):
    # Replace legacy padded dates with registry evidence. When both sources
    # have precise provenance, retain the earliest reliable publication day.
    apply_publication_evidence(current,x["published"],x["publication_date_provenance"])
   if mode=="weekly" and weekly_eligible(x,*previous_week(TODAY)):
    current.pop("acquisition_status",None)
    current["historical_backfill"]=False
    current["discovery_scope"]=x.get("discovery_scope", "previous_publication_week")
   current["source_group"]=source_class(current)
   if len(x.get("abstract_text",""))>len(current.get("abstract_text","")):
    current["abstract_text"]=x["abstract_text"];current["abstract_source"]=x.get("abstract_source","");current["preview"]=x["preview"]
   elif not current.get("preview") or current["preview"].startswith("Abstract unavailable"):
    if not x.get("preview","").startswith("Abstract unavailable"):current["preview"]=x["preview"]
   continue
  x["source_group"]=source_class(x)
  x["historical_backfill"]=str(x.get("discovery_scope") or "").startswith("historical:")
  records[k]=x;new.append(x)
 collection=sorted(records.values(),key=lambda x:(x.get("published") or "",x.get("first_seen") or ""),reverse=True)
 start,end=previous_week(TODAY)
 week_items=[x for x in collection if weekly_eligible(x,start,end)]
 prior=read(DIR/"runs.json",[])
 run={"date":TODAY,"mode":os.environ.get("MODE","weekly"),"new":len(new),"total":len(collection),"candidates":len(candidates),"last_seven_days":len(week_items),"publication_window":window_metadata(TODAY),
      "selection_basis":"original_publication_date_previous_completed_week","stats":dict(stats,errors=errors)}

 run["stats"]["accepted_new"]=len(new)
 run["stats"]["publication_date_quarantine_records"]=sum(x.get("acquisition_status")=="original_publication_date_required" for x in collection)
 run["stats"]["source_screen_note"]="Discovery yields metadata candidates, not verified full texts or journal-level quality certification."
 (DIR/"library.json").write_text(json.dumps(collection,ensure_ascii=False,indent=2)+"\n")
 # A manual historical backfill must not replace the current weekly edition.
 if mode=="weekly":
  (DIR/"weekly.json").write_text(json.dumps({"run":run,"items":diverse_week(week_items)},ensure_ascii=False,indent=2)+"\n")
 (DIR/"runs.json").write_text(json.dumps([r for r in prior if r.get("date")!=TODAY][-51:]+[run],indent=2)+"\n")
 print(json.dumps(run,indent=2))
 if not candidates and errors:raise SystemExit("Discovery did not return records: "+"; ".join(errors[:3]))
if __name__=="__main__":main()

