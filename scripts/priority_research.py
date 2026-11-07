"""Reproducible, field-venue-first scholarly discovery for weekly runs.

Publisher-verified DOI leads are matched against registry metadata, not seeded
as fabricated full-text reviews. Journal-targeted Crossref queries require an
exact recognized container-title match and article-level topical screening.
No paywalled PDFs or private library accounts are touched.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
from urllib.parse import quote, urlencode
from source_quality import normal, topic_class, venue_class
from collection_window import crossref_publication, date_in_window, previous_week, reconcile_publication_evidence

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"data/priority-research.json"
TYPES={"journal-article","proceedings-article","posted-content"}
HTML=re.compile(r"<[^>]+>")


def load_manifest(path=None):
    return json.loads(Path(path or MANIFEST).read_text(encoding="utf-8"))


def doi_id(value):
    raw=str(value or "").lower().strip()
    return re.sub(r"^https?://(?:dx\.)?doi\.org/","",raw).rstrip(" .;,)")


def date_of(work):
    return crossref_publication(work)[0]


def crossref_search(request, params, *, max_pages=5, page_size=100):
    """Bounded cursor traversal with an explicit completeness audit.

    Completeness describes this provider/query/window only, never all online
    scholarship. Errors and caps return partial records with visible reasons.
    """
    rows=[]; errors=[]; cursor="*"; seen_cursors=set()
    audit={"provider":"Crossref", "query":params.get("query.bibliographic") or params.get("query.title", ""),
           "filter":params.get("filter", ""), "pages":0, "records_seen":0,
           "provider_total":None, "max_pages":max_pages, "page_size":page_size,
           "status":"complete", "truncated":False}
    if max_pages < 1:
        return [],dict(audit,status="truncated",truncated=True,reason="page budget is zero"),[]
    for page in range(max_pages):
        try:
            result=request("https://api.crossref.org/works?"+urlencode(dict(params,rows=page_size,cursor=cursor)))
            message=result.get("message")
            if not isinstance(message,dict) or not isinstance(message.get("items"),list):
                raise ValueError("Malformed Crossref search response")
            works=message["items"]
            audit["pages"]+=1
            audit["provider_total"]=message.get("total-results", audit["provider_total"])
            rows.extend(works); audit["records_seen"]=len(rows)
            total=audit["provider_total"]
            if not works:
                if isinstance(total,int) and len(rows)<total:audit.update(status="truncated",truncated=True,reason="empty page before reported total")
                break
            if (isinstance(total,int) and len(rows)>=total) or (len(works)<page_size and not isinstance(total,int)):
                break
            next_cursor=message.get("next-cursor")
            if not next_cursor or next_cursor==cursor or next_cursor in seen_cursors:
                audit.update(status="truncated",truncated=True,reason="provider did not supply a new cursor")
                break
            seen_cursors.add(cursor); cursor=next_cursor
            if page+1==max_pages:
                audit.update(status="truncated",truncated=True,reason="page budget reached")
        except Exception as exc:
            reason="HTTP "+str(exc.code) if hasattr(exc,"code") else type(exc).__name__
            audit.update(status="error",truncated=True,reason=reason)
            if getattr(exc,"code",None)==429:audit["quota_exhausted"]=True
            if getattr(exc,"code",None) in (403,429):audit["provider_paused"]=True
            errors.append("Crossref search unavailable: "+reason)
            break
    return rows,audit,errors


def crossref_article(work, *, lane, scope, query, today, expected_venue=None, editor_seed=False, screen=True):
    if not isinstance(work,dict) or work.get("type") not in TYPES:return None
    doi=doi_id(work.get("DOI"))
    if not re.fullmatch(r"10\.\d{4,9}/\S+",doi):return None
    title=(work.get("title") or [""])[0].strip() if isinstance(work.get("title"),list) else str(work.get("title") or "").strip()
    containers=work.get("container-title") or []
    venue=(containers[0] if isinstance(containers,list) and containers else "") or ""
    published,date_provenance=crossref_publication(work)
    if not title or not published or published>today.isoformat():return None
    if expected_venue and normal(venue)!=normal(expected_venue):return None
    abstract=HTML.sub(" ",str(work.get("abstract") or ""))
    abstract=" ".join(abstract.split())[:6000]
    candidate={
        "title":title,"authors":[" ".join(filter(None,[a.get("given"),a.get("family")])) for a in work.get("author",[])[:8]],
        "published":published,"publication_date_provenance":date_provenance,"venue":venue,"doi":doi,"url":"https://doi.org/"+doi,
        "preview":abstract[:420] if abstract else "Abstract unavailable; bibliographic metadata only.",
        "abstract_text":abstract,"abstract_source":"Crossref publisher-supplied abstract" if abstract else "",
        "kind":"scholarly","lane":lane,
        "relation":"AI-related literature" if re.search(r"\bAI\b|ChatGPT|generative|language model|artificial intelligence",title+" "+abstract,re.I) else "Adjacent digital-attention evidence",
        "evidence":"Registry metadata screened; original paper not yet independently assessed",
        "source":"Publisher-verified DOI via Crossref" if editor_seed else "Journal-targeted Crossref",
        "curated":False,"first_seen":today.isoformat(),
        "discovery_scope":scope,"discovery_query":query,
    }
    if screen and not editor_seed and (venue_class(venue) not in ("priority","specialist") or topic_class(candidate) not in ("direct","adjacent")):
        return None
    return candidate


def discover(request, today, *, mode="weekly", existing_dois=None, manifest=None,
             max_venue_queries=None, max_pages=5, page_size=100):
    """Discover previous-week publications; nominated historical DOI leads are backfill only."""
    if mode not in {"weekly", "backfill"}:raise ValueError("Unsupported discovery mode: "+mode)
    manifest=manifest if manifest is not None else load_manifest()
    existing_dois={doi_id(d) for d in (existing_dois or ()) if d}
    found=[]; errors=[]; found_dois=set()
    stats={"priority_dois_requested":0,"priority_dois_found":0,"journal_queries_attempted":0,
           "journal_queries_succeeded":0,"journal_records_seen":0,"journal_relevant":0,
           "publication_date_rejected":0,"provider_windows":[],"publication_date_corrections":{}}
    if mode=="backfill":
        for p in manifest.get("papers",[]):
            doi=doi_id(p.get("doi"))
            if not doi or doi in existing_dois:continue
            stats["priority_dois_requested"]+=1
            try:
                result=request("https://api.crossref.org/works/"+quote(doi,safe="/"))
                work=result.get("message") or {}
                entry=crossref_article(work,lane=p["lane"],scope="historical:editorial_priority",query="exact DOI verification",today=today,expected_venue=p.get("venue"),editor_seed=True)
                if not entry or entry["doi"]!=doi:errors.append("Priority DOI metadata mismatch: "+doi);continue
                if topic_class(entry)=="off_topic":errors.append("Priority DOI topical mismatch: "+doi);continue
                entry["research_type"]=p.get("research_type","unclassified")
                entry["priority_selection_reason"]=p.get("rationale","")
                entry["source_verification"]=p.get("url","")
                entry["historical_backfill"]=True
                found.append(entry);found_dois.add(doi)
                stats["priority_dois_found"]+=1
            except Exception as exc:
                errors.append("Priority DOI lookup unavailable ("+doi+"): "+type(exc).__name__)
    queries=manifest.get("venue_queries",[])
    limit=len(queries) if max_venue_queries is None else max(0,max_venue_queries)
    stats["journal_queries_planned"]=len(queries)
    stats["journal_queries_deferred"]=max(0,len(queries)-limit)
    since,until=previous_week(today) if mode=="weekly" else (dt.date(2023,1,1),today)
    for p in queries[:limit]:
        if venue_class(p["venue"]) not in ("priority","specialist"):
            errors.append("Journal not recognized in venue baseline: "+p["venue"]);continue
        stats["journal_queries_attempted"]+=1
        params={"query.title":p["q"],"query.container-title":p["venue"],
                "filter":"from-pub-date:"+since.isoformat()+",until-pub-date:"+until.isoformat()}
        works,audit,search_errors=crossref_search(request,params,max_pages=max_pages,page_size=page_size)
        audit["venue"]=p["venue"];stats["provider_windows"].append(audit)
        errors.extend(search_errors)
        if audit["status"]=="complete":stats["journal_queries_succeeded"]+=1
        stats["journal_records_seen"]+=len(works)
        for w in works:
            doi=doi_id(w.get("DOI"))
            if doi:stats["publication_date_corrections"][doi]=reconcile_publication_evidence(stats["publication_date_corrections"].get(doi),crossref_publication(w))
            scope="venue_targeted" if mode=="weekly" else "historical:venue_targeted"
            entry=crossref_article(w,lane=p["lane"],scope=scope,query=p["q"],today=today,expected_venue=p["venue"])
            if not entry:continue
            if not date_in_window(entry["published"],since,until):
                stats["publication_date_rejected"]+=1;continue
            if entry["doi"] not in found_dois:
                entry["historical_backfill"]=mode=="backfill"
                found.append(entry);found_dois.add(entry["doi"])
                stats["journal_relevant"]+=1
        if audit.get("provider_paused"):
            stats["journal_queries_deferred"]+=len(queries[:limit])-stats["journal_queries_attempted"]
            break
    if mode=="weekly":
        for entry in found:
            canonical=stats["publication_date_corrections"].get(entry["doi"])
            if canonical:entry["published"],entry["publication_date_provenance"]=canonical
        found=[entry for entry in found if date_in_window(entry["published"],since,until)]
        stats["journal_relevant"]=len(found)
    stats["discovery_status"]="partial" if errors or stats["journal_queries_deferred"] or any(a["truncated"] for a in stats["provider_windows"]) else "complete"
    return found,errors,stats
