"""Generate simple RSS from indexed library and latest weekly additions."""
import json,pathlib,xml.etree.ElementTree as ET,datetime
root=pathlib.Path(__file__).resolve().parents[1]
data=json.loads((root/"data/weekly.json").read_text())
library=json.loads((root/"data/library.json").read_text())
by_doi={x.get("doi"):x for x in library if x.get("doi")}
by_title={x.get("title"):x for x in library if x.get("title")}
channel=ET.Element("channel")
for k,v in [("title","AI & Attention Observatory — weekly research discoveries"),("link","https://chengyu-ucsb.github.io/ai-attention-observatory/"),("description","Research on AI, attention fragmentation and mitigating interventions. Automated metadata indexing; not peer-reviewed synthesis."),("language","en-us")]:ET.SubElement(channel,k).text=v
ET.SubElement(channel,"lastBuildDate").text=datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
for item in data.get("items",[])[:25]:
 x=by_doi.get(item.get("doi")) if item.get("doi") else None
 x=x or by_title.get(item.get("title")) or item
 reading=x.get("reading") or {}
 entry=ET.SubElement(channel,"item")
 for k,v in [("title",x.get("title","New research item")),("link",x.get("url","https://chengyu-ucsb.github.io/ai-attention-observatory/")),("description",reading.get("findings") or reading.get("overview") or x.get("preview") or "Recently indexed source"),("guid",x.get("doi") or x.get("url") or x.get("title",""))]:ET.SubElement(entry,k).text=str(v)
rss=ET.Element("rss",version="2.0");rss.append(channel)
ET.indent(rss)
(root/"feed.xml").write_bytes(ET.tostring(rss,encoding="utf-8",xml_declaration=True))
