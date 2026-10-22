"""Weekly metadata collector for AI and attention research (no full-text scraping)."""
import json, re, os, time, urllib.request, urllib.parse, urllib.error, datetime, pathlib
from search_plan import plan,source_class
ROOT=pathlib.Path(__file__).resolve().parents[1]
DIR=ROOT/"data"
TODAY=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
KEYWORDS=re.compile(r"attention|cognit|think|interrup|focus|distract|multitask|switch|well.?being|self.regulat|engag|notification|offload",re.I)

AI_TOPIC=re.compile(r"\b(?:ai|genai|chatgpt|artificial intelligence|generative ai|llms?|large language model|machine learning|algorithmic)\b",re.I)
ATTENTION_TOPIC=re.compile(r"attention|focus|distract|interrupt|offload|critical think|cognit(?:ive)? (?:effort|load|scaffold|control|strain|decline)|human agency|mindful|metacognit|well.?being|notification|self.regulat|task.switch|multitask|information overload|techno.?stress|digital stress|cognitive autonomy",re.I)
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
def diverse_week(items,limit=36):
 items=sorted(items,key=lambda x:x.get("published") or "",reverse=True)
 batches={lane:[x for x in items if x.get("lane")==lane] for lane in ("AI & cognition","Fragmentation","Interventions","Technology & society")}
 out=[]
 while len(out)<limit and any(batches.values()):
  for lane in batches:
   if batches[lane] and len(out)<limit:out.append(batches[lane].pop(0))
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
def discover(days=60,mode="weekly"):
 found=[];errors=[];stats={"openalex":0,"crossref":0}
 scopes=plan(datetime.date.fromisoformat(TODAY),mode)
 stats["search_scopes"]=[{"theme":lane,"period":scope,"from":start,"to":end,"query":q} for lane,q,start,end,scope in scopes]
 for lane,q,start,end,scope in scopes:
  params=urllib.parse.urlencode({"search":q,"filter":"from_publication_date:"+start+",to_publication_date:"+end,"per_page":20,**({"api_key":os.environ["OPENALEX_API_KEY"]} if os.getenv("OPENALEX_API_KEY") else {})})
  try:
   result=request("https://api.openalex.org/works?"+params)
   for w in result.get("results",[]):
    title=w.get("title") or "";ab=abstract(w.get("abstract_inverted_index"));doi=(w.get("doi") or "").replace("https://doi.org/","")
    if not title or not KEYWORDS.search(title+" "+ab) or w.get("is_retracted"):continue
    loc=w.get("primary_location") or {};venue=(loc.get("source") or {}).get("display_name") or "OpenAlex"
    authors=[a.get("author",{}).get("display_name","") for a in w.get("authorships",[])[:8]]
    found.append({"title":title,"authors":authors,"published":w.get("publication_date") or "","venue":venue,"doi":doi,"url":"https://doi.org/"+doi if doi else w.get("id",""),"preview":ab[:420]+("…" if len(ab)>420 else "") if ab else "Abstract unavailable; bibliographic metadata only.","abstract_text":ab[:3800],"abstract_source":"OpenAlex abstract index" if ab else "","kind":"scholarly","lane":lane,"relation":"AI-related literature" if re.search(r"\bAI\b|artificial intelligence|generative",title+" "+ab,re.I) else "Adjacent digital-attention evidence","evidence":"Metadata screened (unverified)","source":"OpenAlex","curated":False,"first_seen":TODAY,"discovery_scope":scope,"discovery_query":q})
   stats["openalex"]+=len(result.get("results",[]))
  except urllib.error.HTTPError as e:
   errors.append("OpenAlex "+lane+": HTTP "+str(e.code))
   if e.code==429:
    errors.append("OpenAlex quota reached; remaining OpenAlex searches deferred until the next run.")
    break
  except Exception as e:errors.append("OpenAlex "+lane+": "+str(e)[:130])
  time.sleep(.3)
 # Crossref as complementary discovery, not full-paper content.
 for lane,q,start,end,scope in (scopes if mode=="backfill" else scopes[:6]):
  args=urllib.parse.urlencode({"query.bibliographic":q,"filter":"from-pub-date:"+start+",until-pub-date:"+end,"rows":12,"mailto":"fangcu@ucmail.uc.edu"})
  try:
   result=request("https://api.crossref.org/works?"+args)
   for w in result.get("message",{}).get("items",[]):
    title=(w.get("title") or [""])[0];ab=re.sub("<[^>]+>"," ",w.get("abstract") or "")
    if not title or not KEYWORDS.search(title+" "+ab):continue
    doi=w.get("DOI") or "";dp=(w.get("published",{}).get("date-parts") or [[]])[0];datev="-".join(str(z).zfill(2) if i else str(z) for i,z in enumerate(dp+[1,1]) if i<3)
    found.append({"title":title,"authors":[" ".join(filter(None,[a.get("given"),a.get("family")])) for a in w.get("author",[])[:8]],"published":datev,"venue":(w.get("container-title") or ["Crossref"])[0],"doi":doi,"url":"https://doi.org/"+doi if doi else w.get("URL",""),"preview":ab[:420]+("…" if len(ab)>420 else "") if ab else "Abstract unavailable; bibliographic metadata only.","abstract_text":ab[:3800],"abstract_source":"Crossref abstract" if ab else "","kind":"scholarly","lane":lane,"relation":"AI-related literature" if re.search(r"\bAI\b|artificial intelligence|generative",title+" "+ab,re.I) else "Adjacent digital-attention evidence","evidence":"Metadata screened (unverified)","source":"Crossref","curated":False,"first_seen":TODAY,"discovery_scope":scope,"discovery_query":q})
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
 records={key(x):x for x in previous if relevant(x)}
 for record in records.values():record["source_group"]=source_class(record)
 candidates,errors,stats=discover(mode=os.environ.get("MODE","weekly"))
 new=[]
 for x in candidates:
  k=key(x)
  if not x["title"] or not x["url"] or not relevant(x):continue
  if k in records:
   current=records[k]
   current["source_group"]=source_class(current)
   if len(x.get("abstract_text",""))>len(current.get("abstract_text","")):
    current["abstract_text"]=x["abstract_text"];current["abstract_source"]=x.get("abstract_source","");current["preview"]=x["preview"]
   elif not current.get("preview") or current["preview"].startswith("Abstract unavailable"):
    if not x.get("preview","").startswith("Abstract unavailable"):current["preview"]=x["preview"]
   continue
  x["source_group"]=source_class(x)
  records[k]=x;new.append(x)
 collection=sorted(records.values(),key=lambda x:(x.get("published") or "",x.get("first_seen") or ""),reverse=True)
 week_start=(datetime.date.fromisoformat(TODAY)-datetime.timedelta(days=6)).isoformat()
 week_items=[x for x in collection if x.get("first_seen","")>=week_start and not x.get("curated")]
 prior=read(DIR/"runs.json",[])
 run={"date":TODAY,"mode":os.environ.get("MODE","weekly"),"new":len(new),"total":len(collection),"candidates":len(candidates),"last_seven_days":len(week_items),"stats":dict(stats,errors=errors)}
 if not candidates and errors:raise SystemExit("Discovery did not return records: "+"; ".join(errors[:3]))
 (DIR/"library.json").write_text(json.dumps(collection,ensure_ascii=False,indent=2)+"\n")
 (DIR/"weekly.json").write_text(json.dumps({"run":run,"items":diverse_week(week_items)},ensure_ascii=False,indent=2)+"\n")
 (DIR/"runs.json").write_text(json.dumps([r for r in prior if r.get("date")!=TODAY][-51:]+[run],indent=2)+"\n")
 print(json.dumps(run,indent=2))
if __name__=="__main__":main()
