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
    parts=(work.get("published") or work.get("published-online") or work.get("issued") or {}).get("date-parts") or []
    if not parts or not parts[0]:return ""
    xs=(parts[0]+[1,1])[:3]
    try:return dt.date(*xs).isoformat()
    except (TypeError,ValueError):return ""


def crossref_article(work, *, lane, scope, query, today, expected_venue=None, editor_seed=False):
    if not isinstance(work,dict) or work.get("type") not in TYPES:return None
    doi=doi_id(work.get("DOI"))
    if not re.fullmatch(r"10\.\d{4,9}/\S+",doi):return None
    title=(work.get("title") or [""])[0].strip() if isinstance(work.get("title"),list) else str(work.get("title") or "").strip()
    containers=work.get("container-title") or []
    venue=(containers[0] if isinstance(containers,list) and containers else "") or ""
    published=date_of(work)
    if not title or not published or published>today.isoformat():return None
    if expected_venue and normal(venue)!=normal(expected_venue):return None
    abstract=HTML.sub(" ",str(work.get("abstract") or ""))
    abstract=" ".join(abstract.split())[:6000]
    candidate={
        "title":title,"authors":[" ".join(filter(None,[a.get("given"),a.get("family")])) for a in work.get("author",[])[:8]],
        "published":published,"venue":venue,"doi":doi,"url":"https://doi.org/"+doi,
        "preview":abstract[:420] if abstract else "Abstract unavailable; bibliographic metadata only.",
        "abstract_text":abstract,"abstract_source":"Crossref publisher-supplied abstract" if abstract else "",
        "kind":"scholarly","lane":lane,
        "relation":"AI-related literature" if re.search(r"\bAI\b|ChatGPT|generative|language model|artificial intelligence",title+" "+abstract,re.I) else "Adjacent digital-attention evidence",
        "evidence":"Registry metadata screened; original paper not yet independently assessed",
        "source":"Publisher-verified DOI via Crossref" if editor_seed else "Journal-targeted Crossref",
        "curated":False,"first_seen":today.isoformat(),
        "discovery_scope":scope,"discovery_query":query,
    }
    if not editor_seed and (venue_class(venue) not in ("priority","specialist") or topic_class(candidate) not in ("direct","adjacent")):
        return None
    return candidate


def discover(request, today, *, mode="weekly", existing_dois=None, manifest=None, max_venue_queries=8):
    """Return candidates, error diagnostics, and per-channel statistics.

    request(url) is injected so the discovery is testable without network or
    any institutional access. A missing API provider is visible, never
    silently counted as zero evidence.
    """
    manifest=manifest or load_manifest()
    existing_dois={doi_id(d) for d in (existing_dois or ()) if d}
    found=[];errors=[]
    stats={"priority_dois_requested":0,"priority_dois_found":0,"journal_queries_attempted":0,
           "journal_queries_succeeded":0,"journal_records_seen":0,"journal_relevant":0}
    # Try the nominated, publisher-verified missing primary papers first.
    # Existing works retain their acquired full-text sections and metadata.
    for p in manifest.get("papers",[])[:20]:
        doi=doi_id(p.get("doi"))
        if not doi or doi in existing_dois:continue
        stats["priority_dois_requested"]+=1
        try:
            result=request("https://api.crossref.org/works/"+quote(doi,safe="/"))
            work=result.get("message") or {}
            entry=crossref_article(work,lane=p["lane"],scope="editorial_priority",query="exact DOI verification",today=today,expected_venue=p.get("venue"),editor_seed=True)
            if not entry or entry["doi"]!=doi:errors.append("Priority DOI metadata mismatch: "+doi);continue
            if topic_class(entry)=="off_topic":errors.append("Priority DOI topical mismatch: "+doi);continue
            entry["research_type"]=p.get("research_type","unclassified")
            entry["priority_selection_reason"]=p.get("rationale","")
            entry["source_verification"]=p.get("url","")
            found.append(entry)
            existing_dois.add(doi)
            stats["priority_dois_found"]+=1
        except Exception as exc:
            errors.append("Priority DOI lookup unavailable ("+doi+"): "+type(exc).__name__)
    # Rotate venue searches while covering multiple fields every week.
    queries=manifest.get("venue_queries",[])
    max_venue_queries=max(0,min(max_venue_queries,len(queries)))
    offset=0 if mode=="backfill" else (today.toordinal()//7)%len(queries) if queries else 0
    ordered=queries[offset:]+queries[:offset]
    since=today-dt.timedelta(days=365 if mode=="backfill" else 120)
    for p in ordered[:max_venue_queries]:
        if venue_class(p["venue"]) not in ("priority","specialist"):
            errors.append("Journal not recognized in venue baseline: "+p["venue"]);continue
        stats["journal_queries_attempted"]+=1
        params=urlencode({
            "query.title":p["q"],"query.container-title":p["venue"],
            "filter":"from-pub-date:"+since.isoformat()+",until-pub-date:"+today.isoformat(),
            "rows":20,"mailto":"fangcu@ucmail.uc.edu"
        })
        try:
            result=request("https://api.crossref.org/works?"+params)
            stats["journal_queries_succeeded"]+=1
            works=(result.get("message") or {}).get("items") or []
            stats["journal_records_seen"]+=len(works)
            for w in works:
                entry=crossref_article(w,lane=p["lane"],scope="venue_targeted",query=p["q"],today=today,expected_venue=p["venue"])
                if entry and entry["doi"] not in existing_dois:
                    found.append(entry);existing_dois.add(entry["doi"])
                    stats["journal_relevant"]+=1
        except Exception as exc:
            errors.append("Journal search failed ("+p["venue"]+"): "+type(exc).__name__)
    return found,errors,stats
