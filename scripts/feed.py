"""RSS must use the same source-backed, citation-free public reading projection."""
import datetime,json,pathlib,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
if not (DATA/"public-weekly.json").exists():
 from build_public import build
 build()
week=json.loads((DATA/"public-weekly.json").read_text())
channel=ET.Element("channel")
for k,v in [
 ("title","AI & Attention Observatory — verified-source reading updates"),
 ("link","https://chengyu-ucsb.github.io/ai-attention-observatory/"),
 ("description","Source-grounded updates about AI, cognition and attention. Automated extracts are not expert-reviewed appraisals."),
 ("language","en-us")]:
 ET.SubElement(channel,k).text=v
ET.SubElement(channel,"lastBuildDate").text=datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
for x in week.get("items",[])[:30]:
 r=x.get("reading") or {}
 if r.get("level")=="citation_only":continue
 idea=(r.get("findings") or r.get("interpretation") or r.get("overview") or "").strip()
 if not idea:continue
 entry=ET.SubElement(channel,"item")
 for k,v in [
 ("title",x.get("title") or "Source-backed reading"),
 ("link",x.get("url") or "https://chengyu-ucsb.github.io/ai-attention-observatory/"),
 ("description",idea[:550]),
 ("guid",x.get("doi") or x.get("url") or x.get("title") or "")]:
  ET.SubElement(entry,k).text=str(v)
rss=ET.Element("rss",version="2.0");rss.append(channel);ET.indent(rss)
(ROOT/"feed.xml").write_bytes(ET.tostring(rss,encoding="utf-8",xml_declaration=True))
