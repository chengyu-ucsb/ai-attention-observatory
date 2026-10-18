"""Enrich indexed research using additional metadata providers (no publisher-page scraping).

Sources: OpenAlex DOI batches, Europe PMC abstract metadata, optional Semantic Scholar.
Only DOI/title metadata and a short, attributed abstract digest are published.
Do not infer missing study methods or results.
"""
import datetime, html, json, os, pathlib, re, time
import urllib.parse, urllib.request, urllib.error
from xml.etree import ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TODAY = datetime.date.today().isoformat()
EMPTY = ("abstract unavailable", "abstract not available", "bibliographic metadata", "no abstract")
FIELDS = ("aim", "methods", "findings", "limitations")
def textclean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", text or ""))).strip()

def quality(record):
    if record.get("analysis") and record["analysis"].get("discussion"):return 6
    t = record.get("abstract_text") or ""
    if len(t) > 900:return 5
    if len(t) > 300:return 4
    if len(record.get("preview") or "") > 180 and not is_empty(record.get("preview")):return 2
    return 0
def is_empty(s):
    return not s or any(x in s.lower() for x in EMPTY)
def api_json(url,headers=None):
    h={"User-Agent":"AI-Attention-Observatory/2.0 (fangcu@ucmail.uc.edu)", "Accept":"application/json"}
    if headers:h.update(headers)
    request=urllib.request.Request(url,headers=h)
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request,timeout=16) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (400,403,404):return {}
            if exc.code in (429,500,502,503) and attempt == 0:
                time.sleep(3)
            else:
                raise
    return {}
def uninvert(inv):
    if not isinstance(inv,dict):return ""
    word_at={}
    for word,indices in inv.items():
        for pos in indices:
            if isinstance(pos,int) and pos < 20000:word_at[pos]=word
    return textclean(" ".join(word for _,word in sorted(word_at.items())))
def enrich_record(record,abstract,provider):
    abstract=textclean(abstract)
    if len(abstract)<90:return False
    before=record.get("abstract_text") or ""
    if len(abstract)<=len(before):return False
    # Keep one medium-size abstract, not a full publisher PDF.
    record["abstract_text"]=abstract[:3800]
    record["abstract_source"]=provider
    record["abstract_updated"]=TODAY
    record["preview"]=abstract[:420]+("…" if len(abstract)>420 else "")
    return True
def run():
    file=DATA/"library.json"
    records=json.loads(file.read_text())
    limited=int(os.getenv("META_ENRICH_LIMIT","65"))
    eligible=[r for r in records if r.get("kind")=="scholarly" and r.get("doi") and quality(r)<5]
    eligible.sort(key=lambda r:(quality(r),0 if r.get("curated") else 1,-len(r.get("preview") or "")))
    eligible=eligible[:limited]
    updated=0;provider_stats={"OpenAlex":0,"Europe PMC":0,"Semantic Scholar":0}
    # OpenAlex DOI batch fetches: up to 30 per request for economical metadata lookup.
    for start in range(0,len(eligible),30):
        group=eligible[start:start+30]
        dois=[r["doi"].strip().lower() for r in group]
        filt="doi:"+ "|".join("https://doi.org/"+d for d in dois)
        params={"filter":filt,"per_page":len(group)}
        if os.getenv("OPENALEX_API_KEY"):params["api_key"]=os.environ["OPENALEX_API_KEY"]
        url="https://api.openalex.org/works?"+urllib.parse.urlencode(params)
        try:
            items=api_json(url).get("results",[])
            mapped={w.get("doi","").replace("https://doi.org/","").lower():w for w in items}
            for r in group:
                w=mapped.get(r["doi"].lower())
                if not w:continue
                if enrich_record(r,uninvert(w.get("abstract_inverted_index")),"OpenAlex abstract index"):
                    updated+=1;provider_stats["OpenAlex"]+=1
        except Exception as e:print("OpenAlex abstract batch:",str(e)[:170])
        time.sleep(.25)
    # Europe PMC sometimes has a structured abstract even when OpenAlex does not.
    no_abstract=[r for r in eligible if quality(r)<4]
    for r in no_abstract[:30]:
        try:
            params={"query":"DOI:"+r["doi"],"format":"json","resultType":"core","pageSize":1}
            url="https://www.ebi.ac.uk/europepmc/webservices/rest/search?"+urllib.parse.urlencode(params)
            items=api_json(url).get("resultList",{}).get("result",[])
            if not items:continue
            ab=items[0].get("abstractText","")
            if enrich_record(r,ab,"Europe PMC bibliographic abstract"):
                updated+=1;provider_stats["Europe PMC"]+=1
        except Exception as e:print("Europe PMC metadata:",r["doi"],str(e)[:100])
        time.sleep(.12)
    # An API key is recommended; protect the unauthenticated public quota.
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        for r in [r for r in eligible if quality(r)<4][:12]:
            try:
                params=urllib.parse.urlencode({"fields":"title,abstract,openAccessPdf,tldr"})
                url="https://api.semanticscholar.org/graph/v1/paper/"+urllib.parse.quote("DOI:"+r["doi"],safe="")+ "?"+params
                response=api_json(url,{"x-api-key":os.environ["SEMANTIC_SCHOLAR_API_KEY"]})
                if enrich_record(r,response.get("abstract",""),"Semantic Scholar abstract"):
                    updated+=1;provider_stats["Semantic Scholar"]+=1
            except Exception as e:print("Semantic Scholar metadata:",str(e)[:90])
            time.sleep(.35)
    file.write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"checked":len(eligible),"new_or_longer_abstracts":updated,"providers":provider_stats}))
if __name__=="__main__":run()
