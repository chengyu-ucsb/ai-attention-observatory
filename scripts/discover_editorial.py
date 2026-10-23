"""Discover thoughtful nonacademic articles independently of scholarly DOI search.

Sources: publisher RSS/Atom feeds and narrowly scoped Google News RSS.
No arbitrary publisher HTML crawling, paywall bypassing, or full-text copying.
Only source metadata and short feed descriptions are stored/published.
"""
import datetime, email.utils, html, json, pathlib, re, time
import urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from news_quality import useful_description, publisher_url
from editorial_corrections import apply as apply_editorial_corrections

ROOT=pathlib.Path(__file__).resolve().parents[1]
DIR=ROOT/"data"
TODAY=datetime.datetime.now(datetime.timezone.utc).date()
ATOM="{http://www.w3.org/2005/Atom}"
FEEDS=[
    {"name":"The Conversation","url":"https://theconversation.com/topics/artificial-intelligence-ai-90/articles.atom","category":"Expert commentary"},
    {"name":"The Verge","url":"https://www.theverge.com/rss/index.xml","category":"Technology journalism"},
    {"name":"Ars Technica","url":"https://feeds.arstechnica.com/arstechnica/technology-lab","category":"Technology journalism"},
]
GOOGLE_SEARCHES=[
    ('"AI" "attention" OR "distraction" OR "focus" when:45d',"AI & cognition"),
    ('"ChatGPT" "thinking" OR "cognitive" OR "memory" when:45d',"AI & cognition"),
    ('"AI" "digital wellbeing" OR "attention management" when:45d',"Interventions"),
    ('"AI" "learning" "critical thinking" when:45d',"AI & cognition"),
    ('"notification batching" OR "interruption recovery" when:45d',"Interventions"),
    ('"AI" "productivity" "focus" when:45d',"Interventions"),
    ('"cognitive offloading" "generative AI" when:45d',"AI & cognition"),
    ('"attention economy" "AI" "design" when:45d',"Technology & society"),
]
# Narrowly curated sources. Include practitioners and independent analysis, not just journal literature.
PUBLISHERS={
    "The Conversation","The Verge","Ars Technica","WIRED","MIT Technology Review",
    "Tech Policy Press","The Atlantic","The Guardian","BBC","The New York Times",
    "Financial Times","The Economist","Harvard Business Review","IEEE Spectrum",
    "Nielsen Norman Group","NPR","Vox","Rest of World","EdSurge",
    "Inside Higher Ed","404 Media","The Markup","TechCrunch","Poynter",
    "New Scientist","Nature","Scientific American","Fast Company",
}
AI=re.compile(r"\b(?:ai|genai|chatgpt|copilot|generative|artificial intelligence|language models?|llms?|claude|algorithmic)\b",re.I)
FOCUS=re.compile(r"\b(?:attention|focus|distraction|cognitive|offloading|thinking|think|mental effort|memory|learning|workflows?|interruption|notifications?|task.switching|mindful|productivity|deep work|wellbeing|well-being|autonomy)\b",re.I)
NOISE=re.compile(r"stock (?:price|market)|share price|market cap|latest earnings|price target|football|crypto investment|gambling|celebrity|smartphone deal|focus on privacy|focuses on privacy|paying attention to (?:the|a|creative)|(?:ai|artificial intelligence).*museum|museum.*(?:ai|artificial intelligence)",re.I)
def clean(s):
    s=html.unescape(re.sub(r"<[^>]+>"," ",s or ""))
    return re.sub(r"\s+"," ",s).strip()
def url_key(s):
    try:
        p=urllib.parse.urlsplit(s)
        return (p.netloc.lower()+p.path.rstrip("/")).replace("www.","")
    except Exception:return s
def normalize_date(s):
    if not s:return ""
    try:return email.utils.parsedate_to_datetime(s).date().isoformat()
    except (ValueError,TypeError):
        try:return datetime.date.fromisoformat(s[:10]).isoformat()
        except ValueError:return ""
def get_xml(url):
    r=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; ResearchObservatory/2.0; contact fangcu@ucmail.uc.edu)","Accept":"application/atom+xml,application/rss+xml,application/xml,text/xml"})
    with urllib.request.urlopen(r,timeout=22) as response:
        blob=response.read(2_200_000)
    return ET.fromstring(blob)
def atom_text(el,local):
    child=el.find(ATOM+local)
    return "".join(child.itertext()) if child is not None else ""
def parse_feed(root):
    out=[]
    if root.tag.endswith("feed"):
        for item in root.findall(ATOM+"entry")[:65]:
            links=item.findall(ATOM+"link")
            url=next((a.get("href") for a in links if a.get("rel","alternate")=="alternate" and a.get("href","").startswith("https://")),None)
            url=url or next((a.get("href") for a in links if a.get("href","").startswith("https://")),"")
            summary=atom_text(item,"summary") or atom_text(item,"content")
            author=item.find(ATOM+"author")
            people=[atom_text(author,"name")] if author is not None else []
            out.append(dict(title=clean(atom_text(item,"title")),url=url,description=clean(summary),date=normalize_date(atom_text(item,"published") or atom_text(item,"updated")),authors=[x for x in people if x]))
    else:
        for item in root.findall(".//item")[:65]:
            source=item.find("source")
            creator=item.find("{http://purl.org/dc/elements/1.1/}creator")
            out.append(dict(title=clean(item.findtext("title")),url=clean(item.findtext("link")),description=clean(item.findtext("description")),date=normalize_date(item.findtext("pubDate")),authors=[creator.text.strip()] if creator is not None and creator.text else [],source=source.text.strip() if source is not None and source.text else ""))
    return out
def label(title,desc,category):
    match=(title+" "+desc).lower()
    if re.search("design|tool|product|focus mode|notification|workflow|interface|usability|prototype",match):return "Product & design"
    if "Perspective" in category or "commentary" in category.lower():return "Opinion & analysis"
    return category
def classify(title,desc):
    s=(title+" "+desc).lower()
    if re.search(r"\b(?:focus|notification|self.regulation|digital wellbeing|attention support|intervention|design)\b",s):return "Interventions"
    if re.search(r"distraction|fragmentation|interruption|task.switching",s):return "Fragmentation"
    if re.search(r"attention economy|ethics|agency|platform|policy",s):return "Technology & society"
    return "AI & cognition"
def eligible(item):
    title=item["title"]
    description=item["description"]
    if len(title)<16 or NOISE.search(title) or NOISE.search(description[:260]):return False
    if re.search(r"focus on (?:privacy|market|revenue|policy|security|investment)|paying attention to",title+" "+description[:100],re.I):return False
    if item["date"] and item["date"]>TODAY.isoformat():return False
    body=title+" "+description
    # Require explicit discussion of AI and a human attention/cognition/product-design concept.
    if not ((AI.search(body) and FOCUS.search(body)) or
            (re.search(r"attention|focus|digital wellbeing|notification|cognitive offload",title,re.I) and FOCUS.search(body))):
        return False
    return True
def to_record(item,publisher,format_label):
    title=item["title"]
    desc=item["description"]
    if not useful_description(title,desc,publisher) or not publisher_url(item["url"]):
        # A headline alone is not a substantive summary.
        overview=""
        reading_level="citation_only"
    else:
        overview=desc[:320].rsplit(" ",1)[0]+"…" if len(desc)>320 else desc
        reading_level="source_preview"
    lane=classify(title,desc)
    return {
        "title":title,"authors":item["authors"],"published":item["date"],"venue":publisher,
        "doi":"","url":item["url"],"preview":overview or "Source listed; editorial text not yet available.",
        "kind":"nonacademic","lane":lane,"relation":"Nonacademic reporting / commentary",
        "evidence":"Publisher feed metadata (not independently reviewed)",
        "source":"Publisher RSS / Google News RSS","format":format_label,
        "curated":False,"first_seen":TODAY.isoformat(),
        "reading":{"level":reading_level,"provenance":publisher+" RSS/Atom description",
                   "overview":overview,"methods":"","findings":"","limitations":"",
                   "notice":"This is a short description supplied by the publisher feed, not a full-article review or independent assessment."},
        "content_access":"feed_description" if overview else "headline_only",
        "source_checked":TODAY.isoformat(),
    }
def run():
    path=DIR/"library.json"
    data=apply_editorial_corrections(json.loads(path.read_text()))
    # Remove earlier automatic editorial false positives; never remove manually curated work.
    data=[r for r in data if r.get("source")!="Publisher RSS / Google News RSS" or eligible({"title":r.get("title",""),"description":r.get("preview",""),"date":r.get("published","")})]
    seen={url_key(x.get("url","")) for x in data if x.get("url")}
    seen_titles={re.sub("[^a-z0-9]","",(x.get("title") or "").lower())[:110] for x in data}
    added=[];errors=[];source_counts={}
    for feed in FEEDS:
        try:
            items=parse_feed(get_xml(feed["url"]))
            source_counts[feed["name"]]=len(items)
            for item in items:
                if not item["url"].startswith("https://") or not eligible(item):continue
                key=url_key(item["url"]);name=re.sub("[^a-z0-9]","",item["title"].lower())[:110]
                if key in seen or name in seen_titles:continue
                seen.add(key);seen_titles.add(name)
                added.append(to_record(item,feed["name"],label(item["title"],item["description"],feed["category"])))
        except Exception as e:errors.append(feed["name"]+": "+str(e)[:130])
        time.sleep(.25)
    for query,lane in GOOGLE_SEARCHES:
        url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":query,"hl":"en-US","gl":"US","ceid":"US:en"})
        try:
            for item in parse_feed(get_xml(url))[:45]:
                publisher=item.get("source","")
                if publisher not in PUBLISHERS or not eligible(item):continue
                if not item["url"].startswith("https://"):continue
                key=url_key(item["url"]);name=re.sub("[^a-z0-9]","",item["title"].lower())[:110]
                if key in seen or name in seen_titles:continue
                seen.add(key);seen_titles.add(name)
                rec=to_record(item,publisher,label(item["title"],item["description"],"Technology journalism"))
                rec["lane"]=lane
                added.append(rec)
        except Exception as e:errors.append("Google News RSS: "+str(e)[:130])
        time.sleep(.25)
    # Avoid growing the published site through unbounded automated imports.
    limit=80
    added=sorted(added,key=lambda r:r.get("published") or "",reverse=True)[:limit]
    data.extend(added)
    data=apply_editorial_corrections(data)
    data.sort(key=lambda r:(r.get("published") or "",r.get("first_seen") or ""),reverse=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
    weekly_path=DIR/"weekly.json"
    week=json.loads(weekly_path.read_text())
    start=(TODAY-datetime.timedelta(days=6)).isoformat()
    latest=[r for r in data if r.get("first_seen","")>=start and not r.get("curated")]
    # Give journalism and practitioner perspectives a real place in the weekly selection.
    media=[r for r in latest if r.get("kind")=="nonacademic"]
    scholarly=[r for r in latest if r.get("kind")=="scholarly"]
    by_date=lambda records:sorted(records,key=lambda x:x.get("published") or "",reverse=True)
    week["items"]=by_date(media)[:15]+by_date(scholarly)[:25]
    week["run"]["total"]=len(data)
    week["run"]["last_seven_days"]=len(latest)
    week["run"]["new"]=week["run"].get("new",0)+len(added)
    week["run"]["nonacademic_added"]=len(added)
    week["run"]["nonacademic_total"]=len([x for x in data if x.get("kind")=="nonacademic"])
    week["run"].setdefault("stats",{})["editorial_feeds"]={"source_counts":source_counts,"errors":errors}
    weekly_path.write_text(json.dumps(week,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"nonacademic_discovered":len(added),"nonacademic_total":week["run"]["nonacademic_total"],"feed_counts":source_counts,"errors":errors},indent=2))
if __name__=="__main__":run()
