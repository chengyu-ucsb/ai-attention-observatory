"""Weekly metadata collector for AI and attention research (no full-text scraping)."""
import json, re, os, time, urllib.request, urllib.parse, urllib.error, datetime, pathlib
from academic_state import DiscoveryState, ProviderDeferred, cursor_search
from search_plan import plan,source_class
from arxiv_publication import ArxivPublicationVerifier, identifier_for as arxiv_identifier, fetch_atom
from priority_research import discover as discover_priority, crossref_article, crossref_search, doi_id, load_manifest as priority_manifest
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
def openalex_search(params, *, max_pages=5, page_size=100, state=None):
 return cursor_search(request,"OpenAlex",params,state=state,max_pages=max_pages,page_size=page_size)


def discover(days=None,mode="weekly",max_pages=5,page_size=100,max_date_lookups=100,arxiv_verifier=None,state=None):
 """Collect metadata within explicit publication windows, with coverage limits."""
 found=[];errors=[];stats={"openalex":0,"crossref":0,"provider_windows":[],
                         "publication_date_rejected":0,"publication_date_unverified":0,"publication_date_quarantine":[],
                         "date_lookups":0,"date_lookups_deferred":0}
 today=datetime.date.fromisoformat(TODAY)
 scopes=plan(today,mode)
 start_window,end_window=previous_week(today) if mode=="weekly" else (datetime.date(2023,1,1),today)
 window={"from":start_window.isoformat(),"to":end_window.isoformat()}
 state=state or DiscoveryState(mode=mode,window=window)
 state.validate_window(mode,window)
 planned=[]
 for lane,q,start,end,scope in scopes:
  planned.extend([("OpenAlex",{"search":q,"filter":"from_publication_date:"+start+",to_publication_date:"+end},page_size),
                  ("Crossref",{"query.bibliographic":q,"filter":"from-pub-date:"+start+",until-pub-date:"+end},page_size)])
 state.register_plan("general",planned)
 stats["search_scopes"]=[{"theme":lane,"period":scope,"from":start,"to":end,"query":q} for lane,q,start,end,scope in scopes]
 stats["queries_planned"]=2*len(scopes);stats["queries_attempted"]=0
 crossref_dates=dict(state.current["date_evidence"]);crossref_paused=False;uncertain=[]
 for lane,q,start,end,scope in scopes:
  params={"search":q,"filter":"from_publication_date:"+start+",to_publication_date:"+end,
          **({"api_key":os.environ["OPENALEX_API_KEY"]} if os.getenv("OPENALEX_API_KEY") else {})}
  works,audit,provider_errors=openalex_search(params,max_pages=max_pages,page_size=page_size,state=state)
  audit.update(theme=lane,scope=scope);stats["provider_windows"].append(audit)
  errors.extend(provider_errors);stats["openalex"]+=len(works);stats["queries_attempted"]+=int(audit.get("requests_this_run",0)>0)
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
  if audit.get("requests_this_run"):time.sleep(.3)
 for lane,q,start,end,scope in scopes:
  works,audit,provider_errors=crossref_search(request,{"query.bibliographic":q,"filter":"from-pub-date:"+start+",until-pub-date:"+end},max_pages=max_pages,page_size=page_size,state=state)
  audit.update(theme=lane,scope=scope);stats["provider_windows"].append(audit)
  errors.extend(provider_errors);stats["crossref"]+=len(works);stats["queries_attempted"]+=int(audit.get("requests_this_run",0)>0)
  for w in works:
   doi=doi_id(w.get("DOI"));datev,provenance=crossref_publication(w)
   if doi:crossref_dates[doi]=reconcile_publication_evidence(crossref_dates.get(doi),(datev,provenance))
   x=crossref_article(w,lane=lane,scope=scope,query=q,today=today,screen=False,allow_unresolved=True)
   if x and not datev and mode=="weekly" and relevant(x):
    uncertain.append(x)
   if not x or not date_in_window(datev,start,end):stats["publication_date_rejected"]+=1;continue
   x["source"]="Crossref";x["historical_backfill"]=mode=="backfill"
   if KEYWORDS.search(x["title"]+" "+x["abstract_text"]):found.append(x)
  if audit.get("provider_paused"):
   crossref_paused=True
  if audit.get("requests_this_run"):time.sleep(.3)
 # A print/issue date must not turn an old online-first paper into new work.
 # Verify DOI-backed OpenAlex candidates against the publication events in
 # Crossref. Missing registry evidence is fail-closed for the weekly set.
 if mode=="weekly":
  start,end=previous_week(today)
  kept=[];deferred=set();quarantined={};conflicts={};quota=crossref_paused
  arxiv=arxiv_verifier or ArxivPublicationVerifier(fetch=lambda url:state.fetch("arXiv",url,fetch_atom))
  def quarantine(x,reason):
   pending=dict(x)
   evidence=dict(x.get("publication_date_provenance") or {})
   evidence.update(status="unresolved",reason=reason,provider_publication_date=x.get("published", ""))
   pending.update(published="",publication_date_provenance=evidence,acquisition_status="original_publication_date_required")
   quarantined[key(x)]=pending
  for x in uncertain:quarantine(x,"Crossref original-publication day unavailable or unresolved")
  for x in found:
   if x["source"]=="OpenAlex" and arxiv_identifier(x):
    arxiv_key=arxiv_identifier(x)+":"+x["title"]
    arxiv_cache=state.current.setdefault("arxiv_date_evidence",{})
    if arxiv_key in arxiv_cache:
     day,provenance=arxiv_cache[arxiv_key]
    else:
     day,provenance=arxiv.verify(x)
     if day:arxiv_cache[arxiv_key]=(day,provenance);state.save()
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
      result=state.fetch("Crossref","https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="/"),request)
      work=result.get("message") or {}
      if doi_id(work.get("DOI"))!=doi:raise ValueError("DOI identity mismatch")
      crossref_dates[doi]=crossref_publication(work)
      state.current["date_evidence"][doi]=crossref_dates[doi];state.save()
     except Exception as exc:
      reason="HTTP "+str(exc.code) if getattr(exc,"code",None) else type(exc).__name__
      errors.append("Original publication date unavailable for "+doi+": "+reason)
      crossref_dates[doi]=("",{"source":"Crossref","status":"unresolved","reason":reason,"verification_error":True})
      if isinstance(exc,ProviderDeferred) or getattr(exc,"code",None) in (401,403,429,500,502,503,504):quota=True;crossref_paused=True
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
   if not x["published"] and x["source"]!="OpenAlex":quarantine(x,"Crossref original-publication day unavailable or unresolved")
   if weekly_eligible(x,start,end):kept.append(x)
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
 for doi,evidence in crossref_dates.items():
  if not evidence[1].get("verification_error"):state.current["date_evidence"][doi]=evidence
 state.save()
 # Replayed queries and overlapping providers are one article, not several.
 unique={}
 for entry in found:
  k=key(entry)
  if k not in unique or len(entry.get("abstract_text", ""))>len(unique[k].get("abstract_text", "")):unique[k]=entry
 found=list(unique.values())
 stats["publication_date_corrections"]=crossref_dates
 stats["crossref_provider_paused"]=crossref_paused
 stats["queries_completed"]=sum(a["status"]=="complete" for a in stats["provider_windows"])
 stats["queries_deferred"]=sum(a["status"]!="complete" and not a.get("requests_this_run") for a in stats["provider_windows"])
 stats["discovery_status"]="partial" if state.summary()["query_plan_drift"] or errors or stats["queries_deferred"] or stats["date_lookups_deferred"] or stats["publication_date_unverified"] or any(a["truncated"] for a in stats["provider_windows"]) else "complete"
 stats["configured_query_status"]="complete_for_configured_queries" if stats["discovery_status"]=="complete" else "partial"
 stats["checkpoint"]=state.summary()
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
 start_window,end_window=previous_week(TODAY) if mode=="weekly" else (datetime.date(2023,1,1),datetime.date.fromisoformat(TODAY))
 resume_only=os.environ.get("DISCOVERY_RESUME_ONLY","").lower() in {"1","true","yes"}
 if resume_only and mode!="weekly":raise ValueError("Resume-only recovery supports the current weekly window only")
 state=DiscoveryState(os.environ.get("ACADEMIC_DISCOVERY_STATE") or DIR/"academic-discovery-state.json",mode=mode,
                      window={"from":start_window.isoformat(),"to":end_window.isoformat()},resume_only=resume_only,
                      max_inline_wait=float(os.environ.get("ACADEMIC_MAX_INLINE_WAIT_SECONDS","5")))
 if resume_only and (not state.had_window or not state.current["plans"].get("general")):
  print(json.dumps({"status":"no_current_window_plan","publication_window":window_metadata(TODAY),
                    "note":"No full discovery started; stale windows remain excluded."}))
  return
 max_pages=int(os.environ.get("ACADEMIC_MAX_PAGES","5"));page_size=int(os.environ.get("ACADEMIC_PAGE_SIZE","100"))
 manifest=priority_manifest()
 state.register_plan("journals",[("Crossref",{"query.title":p["q"],"query.container-title":p["venue"],
                       "filter":"from-pub-date:"+start_window.isoformat()+",until-pub-date:"+end_window.isoformat()},page_size)
                      for p in manifest.get("venue_queries",[])])
 candidates,errors,stats=discover(mode=mode,state=state,max_pages=max_pages,page_size=page_size,
                                 max_date_lookups=int(os.environ.get("ACADEMIC_MAX_DATE_LOOKUPS","100")))
 priority,priority_errors,priority_stats=discover_priority(
   request,datetime.date.fromisoformat(TODAY),mode=mode,state=state,manifest=manifest,max_pages=max_pages,page_size=page_size,
   existing_dois={x.get("doi") for x in records.values() if x.get("doi")}
 )
 stats["checkpoint"]=state.summary()
 stats["resume_only"]=resume_only
 corrections=stats.pop("publication_date_corrections",{})
 for doi,evidence in priority_stats.pop("publication_date_corrections",{}).items():
  corrections[doi]=reconcile_publication_evidence(corrections.get(doi),evidence)
 for current in records.values():
  known=corrections.get(doi_id(current.get("doi")))
  if known:
   day,provenance=known
   apply_publication_evidence(current,day,provenance)
 quarantined=stats.pop("publication_date_quarantine",[])+priority_stats.pop("publication_date_quarantine",[])
 for pending in quarantined:
  if relevant(pending) and key(pending) not in records:
   pending["source_group"]=source_class(pending)
   records[key(pending)]=pending
 candidates=priority+candidates
 errors.extend(priority_errors)
 stats["priority_and_journal_discovery"]=priority_stats
 stats["discovery_status"]="partial" if errors or stats.get("discovery_status")=="partial" or priority_stats.get("discovery_status")=="partial" or stats["checkpoint"]["status"]=="partial" or stats["checkpoint"]["query_plan_drift"] else "complete"
 stats["configured_query_status"]="complete_for_configured_queries" if stats["discovery_status"]=="complete" else "partial"
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

