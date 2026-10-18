"""Weekly metadata collector for AI and attention research (no full-text scraping)."""
import json, re, os, time, urllib.request, urllib.parse, datetime, pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
DIR=ROOT/"data"
TODAY=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
SEARCHES=[
("AI & cognition","generative artificial intelligence cognitive offloading attention"),
("AI & cognition","AI critical thinking cognitive effort"),
("Fragmentation","AI interruptions attention fragmentation multitasking"),
("Fragmentation","digital distraction notifications task switching"),
("Interventions","AI attention management digital wellbeing interventions"),
("Interventions","AI adaptive notifications focus assistant"),
("Technology & society","artificial intelligence attention economy cognitive autonomy")]
KEYWORDS=re.compile(r"attention|cognit|think|interrup|focus|distract|multitask|switch|well.?being|self.regulat|engag|notification|offload",re.I)
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
def discover(days=60):
 found=[];errors=[];stats={"openalex":0,"crossref":0}
 since=(datetime.date.fromisoformat(TODAY)-datetime.timedelta(days=days)).isoformat()
 for lane,q in SEARCHES:
  params=urllib.parse.urlencode({"search":q,"filter":"from_publication_date:"+since,"per_page":25,**({"api_key":os.environ["OPENALEX_API_KEY"]} if os.getenv("OPENALEX_API_KEY") else {})})
  try:
   result=request("https://api.openalex.org/works?"+params)
   for w in result.get("results",[]):
    title=w.get("title") or "";ab=abstract(w.get("abstract_inverted_index"));doi=(w.get("doi") or "").replace("https://doi.org/","")
    if not title or not KEYWORDS.search(title+" "+ab) or w.get("is_retracted"):continue
    loc=w.get("primary_location") or {};venue=(loc.get("source") or {}).get("display_name") or "OpenAlex"
    authors=[a.get("author",{}).get("display_name","") for a in w.get("authorships",[])[:8]]
    found.append({"title":title,"authors":authors,"published":w.get("publication_date") or "","venue":venue,"doi":doi,"url":"https://doi.org/"+doi if doi else w.get("id",""),"preview":ab[:550] or "Abstract unavailable; bibliographic metadata only.","kind":"scholarly","lane":lane,"relation":"AI-related literature" if re.search(r"\bAI\b|artificial intelligence|generative",title+" "+ab,re.I) else "Adjacent digital-attention evidence","evidence":"Metadata screened (unverified)","source":"OpenAlex","curated":False,"first_seen":TODAY})
   stats["openalex"]+=len(result.get("results",[]))
  except Exception as e:errors.append("OpenAlex "+lane+": "+str(e)[:130])
  time.sleep(.3)
 # Crossref as complementary discovery, not full-paper content.
 for lane,q in SEARCHES[:5]:
  args=urllib.parse.urlencode({"query.bibliographic":q,"filter":"from-pub-date:"+since,"rows":15})
  try:
   result=request("https://api.crossref.org/works?"+args)
   for w in result.get("message",{}).get("items",[]):
    title=(w.get("title") or [""])[0];ab=re.sub("<[^>]+>"," ",w.get("abstract") or "")
    if not title or not KEYWORDS.search(title+" "+ab):continue
    doi=w.get("DOI") or "";dp=(w.get("published",{}).get("date-parts") or [[]])[0];datev="-".join(str(z).zfill(2) if i else str(z) for i,z in enumerate(dp+[1,1]) if i<3)
    found.append({"title":title,"authors":[" ".join(filter(None,[a.get("given"),a.get("family")])) for a in w.get("author",[])[:8]],"published":datev,"venue":(w.get("container-title") or ["Crossref"])[0],"doi":doi,"url":"https://doi.org/"+doi if doi else w.get("URL",""),"preview":ab[:550] or "Abstract unavailable; bibliographic metadata only.","kind":"scholarly","lane":lane,"relation":"AI-related literature" if re.search(r"\bAI\b|artificial intelligence|generative",title+" "+ab,re.I) else "Adjacent digital-attention evidence","evidence":"Metadata screened (unverified)","source":"Crossref","curated":False,"first_seen":TODAY})
   stats["crossref"]+=len(result.get("message",{}).get("items",[]))
  except Exception as e:errors.append("Crossref "+lane+": "+str(e)[:130])
  time.sleep(.3)
 # News RSS is metadata discovery, not endorsement or full-text analysis.
 import xml.etree.ElementTree as ET
 for query,lane in [("AI attention cognitive offloading","AI & cognition"),("AI distraction focus attention technology","Fragmentation"),("artificial intelligence digital wellbeing attention tools","Interventions")]:
  url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":query+" when:30d","hl":"en-US","gl":"US","ceid":"US:en"})
  try:
   req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; AIAttentionObservatory/1.1)"})
   with urllib.request.urlopen(req,timeout=20) as r:root=ET.fromstring(r.read())
   for item in root.findall(".//item")[:30]:
    title=(item.findtext("title") or "").strip()
    link=(item.findtext("link") or "").strip()
    pub=(item.findtext("pubDate") or "").strip()
    desc=re.sub("<[^>]+>"," ",item.findtext("description") or "").strip()
    if not title or not link or not KEYWORDS.search(title+" "+desc):continue
    try:
     from email.utils import parsedate_to_datetime
     pub=parsedate_to_datetime(pub).date().isoformat()
    except (TypeError,ValueError):pub=""
    found.append({"title":title,"authors":[],"published":pub,"venue":(item.findtext("source") or "News RSS"),"doi":"","url":link,"preview":desc[:500] or "News headline indexed via RSS; article not independently reviewed.","kind":"nonacademic","lane":lane,"relation":"AI-related literature","evidence":"News / commentary (not reviewed)","source":"Google News RSS","curated":False,"first_seen":TODAY})
    stats["news_rss"]=stats.get("news_rss",0)+1
  except Exception as e:errors.append("News RSS: "+str(e)[:130])
 return found,errors,stats
def main():
 DIR.mkdir(exist_ok=True)
 previous=read(DIR/"library.json",[])
 records={key(x):x for x in previous}
 candidates,errors,stats=discover(150 if os.environ.get("MODE")=="backfill" else 60)
 new=[]
 for x in candidates:
  k=key(x)
  if not x["title"] or not x["url"]:continue
  if k in records:
   if not records[k].get("preview") or records[k]["preview"].startswith("Abstract unavailable"):records[k]["preview"]=x["preview"]
   continue
  records[k]=x;new.append(x)
 collection=sorted(records.values(),key=lambda x:(x.get("published") or "",x.get("first_seen") or ""),reverse=True)[:2500]
 prior=read(DIR/"runs.json",[])
 run={"date":TODAY,"mode":os.environ.get("MODE","weekly"),"new":len(new),"total":len(collection),"candidates":len(candidates),"stats":dict(stats,errors=errors)}
 if not candidates and errors:raise SystemExit("Discovery did not return records: "+"; ".join(errors[:3]))
 (DIR/"library.json").write_text(json.dumps(collection,ensure_ascii=False,indent=2)+"\n")
 (DIR/"weekly.json").write_text(json.dumps({"run":run,"items":new[:35]},ensure_ascii=False,indent=2)+"\n")
 (DIR/"runs.json").write_text(json.dumps([r for r in prior if r.get("date")!=TODAY][-51:]+[run],indent=2)+"\n")
 print(json.dumps(run,indent=2))
if __name__=="__main__":main()
