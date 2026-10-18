"""Generate simple RSS from indexed library and latest weekly additions."""
import json,pathlib,xml.etree.ElementTree as ET,datetime
root=pathlib.Path(__file__).resolve().parents[1]
data=json.loads((root/"data/weekly.json").read_text())
channel=ET.Element("channel")
for k,v in [("title","AI & Attention Observatory — weekly research discoveries"),("link","https://chengyu-ucsb.github.io/ai-attention-observatory/"),("description","Research on AI, attention fragmentation and mitigating interventions. Automated metadata indexing; not peer-reviewed synthesis."),("language","en-us")]:ET.SubElement(channel,k).text=v
ET.SubElement(channel,"lastBuildDate").text=datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
for x in data.get("items",[])[:25]:
 entry=ET.SubElement(channel,"item")
 for k,v in [("title",x.get("title","New research item")),("link",x.get("url","https://chengyu-ucsb.github.io/ai-attention-observatory/")),("description",x.get("analysis",{}).get("key_idea") or x.get("preview") or "Recently indexed source"),("guid",x.get("doi") or x.get("url") or x.get("title",""))]:ET.SubElement(entry,k).text=str(v)
rss=ET.Element("rss",version="2.0");rss.append(channel)
ET.indent(rss)
(root/"feed.xml").write_bytes(ET.tostring(rss,encoding="utf-8",xml_declaration=True))
