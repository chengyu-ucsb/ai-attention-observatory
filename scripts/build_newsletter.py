"""Render a shareable, email-client-friendly issue preview from reviewed copy only.

Does not send email or collect addresses. Requires an editorially published issue.
A real mailing list needs an opt-in provider, consent records and unsubscribe handling.
"""
import html,json,pathlib,urllib.parse,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/"data"
def esc(s):return html.escape(str(s or ""),quote=True)
def safe(url):
 parts=urllib.parse.urlsplit(url or "")
 return url if parts.scheme=="https" and parts.netloc else "https://chengyu-ucsb.github.io/ai-attention-observatory/"
def build():
 current=json.loads((DATA/"public-issue.json").read_text())
 approved=DATA/"approved-issues";approved.mkdir(parents=True,exist_ok=True)
 if current.get("status")=="published":
  edition=current.get("edition_date","")
  if not edition or not edition[:4].isdigit():raise ValueError("Published issue needs a date")
  (approved/(edition+".json")).write_text(json.dumps(current,indent=2,ensure_ascii=False)+chr(10))
 archived=sorted(approved.glob("????-??-??.json"),reverse=True)
 issue=current if current.get("status")=="published" else (json.loads(archived[0].read_text()) if archived else current)
 root="https://chengyu-ucsb.github.io/ai-attention-observatory/"
 published=issue.get("status")=="published"
 archive_link=root+"issues/"+issue.get("edition_date","")+".html" if published else root+"#issue"
 title=issue.get("subject") if published else "The Attention Edit — issue in review"
 if not published:
  body='<h1>Our next edition is being prepared.</h1><p>New sources are being reviewed before the cross-source newsletter is published.</p>'
 else:
  source_lookup={x["id"]:x for x in issue["sources"]}
  def refs(ids):
   return " · ".join('<a href="'+esc(safe(source_lookup[i].get("url")))+'" style="color:#8b3345;text-decoration:underline;">'+esc(source_lookup[i]["title"][:64])+'</a>' for i in ids)
  signals="".join('<tr><td style="padding:24px 30px;border-bottom:1px solid #eadfdb;">'
       +'<p style="margin:0 0 6px;color:#a43a4d;text-transform:uppercase;font-size:11px;font-weight:bold;">SIGNAL '+str(k+1)+' · '+esc(x["short"])+'</p>'
       +'<h2 style="font:normal 25px Georgia,serif;margin:0 0 10px;color:#30282b;">'+esc(x["title"])+'</h2>'
       +'<p style="font:15px/1.7 Arial,sans-serif;color:#594e51;margin:0 0 11px;">'+esc(x["text"])+'</p>'
       +'<p style="font:11px/1.55 Arial,sans-serif;color:#9a8085;margin:0;">READ MORE: '+refs(x["source_ids"])+'</p></td></tr>'
       for k,x in enumerate(issue["signals"]))
  body='<p style="font:11px Arial,sans-serif;color:#a44355;letter-spacing:2px;font-weight:bold;">THE ATTENTION EDIT · ISSUE '+esc(issue["number"])+'</p>'
  body+='<h1 style="font:normal 44px/1.08 Georgia,serif;color:#362a2e;margin:13px 0 16px;">'+esc(issue["headline"])+'</h1>'
  body+='<p style="font:17px/1.6 Georgia,serif;color:#68585c;">'+esc(issue["deck"])+'</p>'
  body+='<p style="font:15px/1.8 Arial,sans-serif;color:#50474a;margin:25px 0;">'+esc(issue["letter"])+'</p>'
  body+='</td></tr>'+signals+'<tr><td style="padding:25px 30px;background:#f2e5e1;">'
  body+='<p style="font:11px Arial,sans-serif;font-weight:bold;letter-spacing:1px;color:#a43a4d;">THE TENSION</p>'
  body+='<h2 style="font:normal 26px Georgia,serif;margin:8px 0;">'+esc(issue["tension"]["title"])+'</h2>'
  body+='<p style="font:14px/1.7 Arial,sans-serif;">'+esc(issue["tension"]["text"])+'</p>'
  body+='<p style="font:11px Arial,sans-serif;color:#8e646b;">'+refs(issue["tension"]["source_ids"])+'</p>'
  body+='</td></tr><tr><td style="padding:27px 30px;">'
  body+='<p style="font:11px Arial,sans-serif;color:#a43a4d;font-weight:bold;">THE 45-SECOND EXPERIMENT</p><h2 style="font:normal 26px Georgia,serif;margin:8px 0;">'+esc(issue["experiment"]["title"])+'</h2><p style="font:14px/1.75 Arial,sans-serif;">'+esc(issue["experiment"]["text"])+'</p>'
  body+='<p style="font:12px/1.6 Arial,sans-serif;color:#8a7d80;">'+esc(issue["experiment"]["caution"])+'</p>'
  body+='<p style="font:17px/1.55 Georgia,serif;color:#8b3345;">'+esc(issue["closer"])+'</p>'
  body+='<p style="font:11px/1.6 Arial,sans-serif;color:#8a7d80;">'+esc(issue["editorial_note"])+'</p>'
  body+='<p style="font:12px Arial,sans-serif;">'+str(issue["source_count"])+' readings considered, including '+str(issue["types"]["commentary"])+' nonacademic perspectives. <a style="color:#a43a4d;" href="'+root+'#issue">See the complete source shelf →</a></p>'
  body+='<p style="font:11px/1.5 Arial,sans-serif;color:#8a7d80;">This is a publicly viewable preview, not a mailing-list message. No email addresses are collected. Email delivery and unsubscribe controls require a separate opt-in newsletter service.</p>'
  body+='</td></tr><tr><td style="padding:0;">'
 wrapper='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+esc(title)+'''</title></head><body style="background:#f9f4f2;margin:0;padding:20px 10px;"><table role="presentation" align="center" cellpadding="0" cellspacing="0" style="width:100%;max-width:640px;background:white;border-collapse:collapse;border:1px solid #ecdedb;"><tr><td style="background:#a52c3e;padding:20px 30px;color:white;font:800 12px Arial,sans-serif;letter-spacing:1.5px;">ATTENTION / AI <span style="float:right;font-size:11px;font-weight:normal;">THE WEEKLY EDIT</span></td></tr><tr><td style="padding:32px 30px;">'''
 footer='''</td></tr><tr><td style="padding:22px 30px;background:#3a2730;color:#f2d9d7;font:12px/1.7 Arial,sans-serif;">Curated by the Attention Observatory · <a href="https://chengyufang.org/" style="color:#ffe1db;">chengyufang.org</a><br/>Read on the website: <a style="color:#ffe1db;" href="'''+archive_link+'''">Latest approved issue</a></td></tr></table></body></html>'''
 rendered=wrapper+body+footer
 (ROOT/"newsletter.html").write_text(rendered)
 if published:
  outdir=ROOT/"issues";outdir.mkdir(exist_ok=True)
  (outdir/(issue["edition_date"]+".html")).write_text(rendered)
 rss=ET.Element("rss",version="2.0");ch=ET.SubElement(rss,"channel")
 for k,v in [("title","The Attention Edit — Weekly editorial"),("link",root+"#issue"),("description","A concise cross-source editorial from the AI & Attention Observatory")]:ET.SubElement(ch,k).text=v
 for archived_issue in archived[:30]:
  previous=json.loads(archived_issue.read_text())
  if previous.get("status")!="published":continue
  item=ET.SubElement(ch,"item")
  for k,v in [("title",previous["subject"]),("link",root+"issues/"+previous["edition_date"]+".html"),
              ("guid",previous["edition_date"]),("description",previous["deck"]+" "+previous["closer"])]:
   ET.SubElement(item,k).text=v
 ET.indent(rss);(ROOT/"issue-feed.xml").write_bytes(ET.tostring(rss,encoding="utf-8",xml_declaration=True))
 print(f"Newsletter preview: {'latest approved issue retained' if current.get('status')!='published' and published else 'published' if published else 'awaiting editorial review'}; {issue['source_count']} source-backed readings.")
if __name__=="__main__":build()
