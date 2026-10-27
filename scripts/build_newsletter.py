"""Publish the editorial Weekly Edit as a readable email-preview and standards-compliant RSS.

Built from approved issue copy; never sends emails or asserts a subscriber exists.
An unreviewed new week must not erase the latest published edition.
"""
from __future__ import annotations
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
import html
import json
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
BASE="https://chengyu-ucsb.github.io/ai-attention-observatory/"
FEED=BASE+"issue-feed.xml"
ATOM="http://www.w3.org/2005/Atom"
ET.register_namespace("atom",ATOM)
CONTENT="http://purl.org/rss/1.0/modules/content/"
ET.register_namespace("content",CONTENT)

def esc(value):
    return html.escape(str(value or ""),quote=True)

def safe_url(value):
    parts=urlsplit(str(value or ""))
    return value if parts.scheme=="https" and parts.netloc else BASE

def published_on(edition_date):
    return datetime.combine(date.fromisoformat(edition_date),time(hour=12),tzinfo=timezone.utc)

def rss_date(value):
    return format_datetime(value,usegmt=True)

def source_links(issue,ids):
    lookup={r["id"]:r for r in issue.get("sources",[])}
    out=[]
    for number,ident in enumerate(ids or [],1):
        source=lookup.get(ident)
        if not source:continue
        title=source.get("title") or "Original source"
        # Keep full descriptive alt/title; short labels prevent a forest of 80-word citations.
        out.append(
            '<a class="source-link" style="color:#9b3b4d;text-decoration:underline;text-underline-offset:3px;"'
            +' href="'+esc(safe_url(source.get("url")))+'" title="'+esc(title)+'">'
            +esc("Reading "+str(number))+" ↗</a>"
        )
    return " &nbsp;·&nbsp; ".join(out)

def top_html(issue):
    """Email-preview-first design. Typography has accessible system fallbacks."""
    head="""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>"""+esc(issue["subject"])+"""</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&display=swap" rel="stylesheet">
<style>
html{-webkit-text-size-adjust:100%}
body{background:#eee8e5;margin:0;padding:0;color:#34272d}
a{color:#9a3047}
a:hover{text-decoration-thickness:2px!important}
.preview-outer{width:100%;border-collapse:collapse}
.preview{width:100%;max-width:728px;margin:0 auto;background:#fff;border-collapse:collapse}
.display{font-family:Newsreader,Georgia,'Times New Roman',serif!important}
.bodycopy{font-family:'DM Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif!important}
.stamp{font-family:'DM Sans',Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;font-weight:700}
.signal-text{font-size:15px;line-height:1.7}
.source-link{white-space:nowrap}
@media only screen and (max-width:650px){
 .outer-space{padding:0!important}.pad{padding-left:25px!important;padding-right:25px!important}
 .hero-title{font-size:38px!important;line-height:1.1!important}
 .edition-label{font-size:10px!important}
 .signal-title{font-size:25px!important}
 .signal-number{font-size:34px!important}
 .aside-card{display:block!important;width:100%!important;box-sizing:border-box!important}
 .small-stat{display:block!important;margin-top:8px!important}
 .footer-links a{display:block!important;margin:6px 0!important}
}
</style></head>
<body>
<table role="presentation" class="preview-outer" cellspacing="0" cellpadding="0" border="0"><tr>
<td class="outer-space" style="padding:34px 16px 55px">
<table role="presentation" align="center" class="preview" cellspacing="0" cellpadding="0" border="0" width="728" style="width:100%;max-width:728px;background:#fff;border:1px solid #e5d8d5">
<tr><td style="height:7px;background:#a52c3e;font-size:1px;line-height:1px">&nbsp;</td></tr>
<tr><td class="pad" style="padding:28px 48px 21px;border-bottom:1px solid #eee5e2">
 <table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
 <td style="font:700 15px/1.2 'DM Sans',Arial,sans-serif;letter-spacing:1.1px;color:#403037">ATTENTION<span style="color:#a52c3e"> / </span>AI</td>
 <td align="right" style="font:600 10px/1.3 'DM Sans',Arial,sans-serif;color:#8a767e;letter-spacing:.8px">THE WEEKLY EDIT</td>
 </tr></table>
</td></tr>
"""
    return head

def section_label(label):
    return '<p class="stamp edition-label" style="color:#ae4457;font-size:10px;line-height:1.5;letter-spacing:2px;margin:0 0 15px">'+esc(label)+'</p>'

def opening(issue):
    issue_num=issue.get("number","—")
    deck=issue.get("deck","")
    intro=issue.get("letter","")
    return (
        '<tr><td class="pad" style="padding:47px 48px 24px">'
        +section_label("ISSUE "+str(issue_num)+" · "+issue["edition_date"]+" · THE BIG QUESTION")
        +'<h1 class="display hero-title" style="font:500 48px/1.04 Newsreader,Georgia,serif;letter-spacing:-1.3px;color:#392b32;margin:0 0 19px;max-width:590px">'
        +esc(issue["headline"])+'</h1>'
        +'<p class="display" style="font:400 20px/1.45 Newsreader,Georgia,serif;color:#8e3448;margin:0 0 18px">'+esc(deck)+'</p>'
        +'<p class="bodycopy" style="font:400 15px/1.75 DM Sans,Arial,sans-serif;color:#5e5356;margin:0">'+esc(intro)+'</p>'
        +'</td></tr>'
    )

def overview(issue):
    signals=issue.get("signals") or []
    if not signals:return ""
    parts=[
        '<tr><td class="pad" style="padding:21px 48px 13px">',
        '<div style="border-top:1px solid #e6dad7;padding-top:23px">',
        section_label("THREE THREADS · WHAT CONNECTS THE READINGS"),
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
    ]
    for i,sig in enumerate(signals[:3],1):
        parts.append(
          '<td width="33%" valign="top" style="border-left:3px solid '
          +["#a52c3e","#c98790","#e0bfbb"][i-1]
          +';padding:3px 9px 5px 13px">'
          +'<span class="stamp" style="font-size:10px;color:#aa4b5e">'+str(i).zfill(2)+'</span>'
          +'<p class="display" style="font:500 17px/1.28 Newsreader,Georgia,serif;color:#45353c;margin:7px 0">'
          +esc(sig.get("short",sig.get("title","")))+"</p></td>"
        )
    parts+=['</tr></table></div></td></tr>']
    return "".join(parts)

def signal_cards(issue):
    output=[]
    for i,sig in enumerate(issue.get("signals",[]),1):
        output.append(
            '<tr><td class="pad" style="padding:27px 48px 30px">'
            +'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
            +'<td valign="top" width="65" style="padding-top:0">'
            +'<div class="display signal-number" style="font:500 46px/1 Newsreader,Georgia,serif;color:#b85769">'+str(i).zfill(2)+'</div></td>'
            +'<td valign="top" style="padding-left:7px">'
            +section_label("THE SIGNAL")
            +'<h2 class="display signal-title" style="font:500 29px/1.14 Newsreader,Georgia,serif;color:#372a30;margin:0 0 11px">'
            +esc(sig["title"])+"</h2>"
            +'<p class="bodycopy signal-text" style="font:400 14px/1.7 DM Sans,Arial,sans-serif;color:#5e5357;margin:0 0 15px">'
            +esc(sig["text"])+"</p>"
            +'<p class="bodycopy" style="font:600 11px/1.5 DM Sans,Arial,sans-serif;color:#997e84;margin:0">'
            +'FOLLOW THE SOURCES&nbsp;&nbsp;'+source_links(issue,sig.get("source_ids",[]))+"</p>"
            +'</td></tr></table></td></tr>'
            +'<tr><td style="padding:0 48px"><div style="height:1px;background:#f0e7e4"></div></td></tr>'
        )
    return "".join(output)

def question_and_try(issue):
    t=issue["tension"]
    p=issue["experiment"]
    return (
      '<tr><td class="pad" style="padding:37px 48px">'
      +'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
      +'<td class="aside-card" valign="top" width="51%" style="padding:24px;background:#f6e7e5">'
      +section_label("THE PRODUCTIVE TENSION")
      +'<h3 class="display" style="font:500 24px/1.2 Newsreader,Georgia,serif;color:#4a3038;margin:0 0 11px">'+esc(t["title"])+'</h3>'
      +'<p class="bodycopy" style="font:400 13px/1.7 DM Sans,Arial,sans-serif;color:#705960;margin:0 0 12px">'+esc(t["text"])+'</p>'
      +'<p style="margin:0;font:600 11px/1.5 Arial,sans-serif">'+source_links(issue,t.get("source_ids",[]))+'</p>'
      +'</td><td width="12" style="font-size:0">&nbsp;</td>'
      +'<td class="aside-card" valign="top" width="47%" style="padding:24px;background:#f4f0e9">'
      +section_label("THE ONE-MINUTE EXPERIMENT")
      +'<h3 class="display" style="font:500 24px/1.2 Newsreader,Georgia,serif;color:#4a3038;margin:0 0 11px">'+esc(p["title"])+'</h3>'
      +'<p class="bodycopy" style="font:400 13px/1.7 DM Sans,Arial,sans-serif;color:#63585a;margin:0 0 9px">'+esc(p["text"])+'</p>'
      +'<p style="font:400 10px/1.5 Arial,sans-serif;color:#9e868a;margin:0">'+esc(p.get("caution",""))+'</p>'
      +'</td></tr></table></td></tr>'
    )

def bottom(issue):
    count=issue.get("source_count",0)
    permalink=BASE+"issues/"+issue["edition_date"]+".html"
    return (
      '<tr><td class="pad" style="padding:9px 48px 38px">'
      +section_label("ONE THING TO TAKE WITH YOU")
      +'<p class="display" style="font:italic 500 26px/1.34 Newsreader,Georgia,serif;color:#a43a50;margin:0 0 21px">'+esc(issue["closer"])+'</p>'
      +'<a href="'+permalink+'" style="display:inline-block;background:#a52c3e;color:#fff;text-decoration:none;padding:13px 20px;font:700 12px/1.4 DM Sans,Arial,sans-serif;letter-spacing:.3px">'
      +'Read this edition online&nbsp; ↗</a>'
      +'<p class="bodycopy" style="font:400 11px/1.65 DM Sans,Arial,sans-serif;color:#8e7d82;margin:18px 0 0">'
      +'Sources for each idea are linked above. Research findings and commentary are identified separately.</p>'
      +'<p class="bodycopy" style="font:400 11px/1.65 DM Sans,Arial,sans-serif;color:#8e7d82;margin:12px 0 0">'+esc(issue.get('editorial_note',''))+'</p>'
      +'</td></tr>'
      +'<tr><td class="pad footer-links" style="padding:25px 48px 31px;background:#35272f">'
      +'<p style="font:700 12px/1.5 DM Sans,Arial,sans-serif;letter-spacing:1.1px;color:#f5e1df;margin:0 0 10px">THE ATTENTION EDIT</p>'
      +'<p style="font:400 12px/1.75 DM Sans,Arial,sans-serif;color:#dac6cb;margin:0 0 11px">A weekly look at what AI changes about thinking, focus, and human agency.</p>'
      +'<p style="font:600 11px/1.8 DM Sans,Arial,sans-serif;margin:0">'
      +'<a href="'+BASE+'issues/" style="color:#f6d0cf;text-decoration:none">Past editions ↗</a>'
      +'&nbsp;&nbsp; · &nbsp;&nbsp;<a href="'+FEED+'" style="color:#f6d0cf;text-decoration:none">Weekly RSS ↗</a>'
      +'&nbsp;&nbsp; · &nbsp;&nbsp;<a href="https://chengyufang.org/" style="color:#f6d0cf;text-decoration:none">About the editor ↗</a></p>'
      +'<p style="font:400 10px/1.65 DM Sans,Arial,sans-serif;color:#af9fa3;margin:18px 0 0">'
      +'This is an online newsletter preview. Email subscriptions are not active; no address has been collected or message sent.</p>'
      +'</td></tr>'
      +'</table></td></tr></table></body></html>'
    )

def render_issue(issue):
    if issue.get("status")!="published":
        return (top_html({"subject":"The Attention Edit · Ideas about AI and attention"})
                +'<tr><td class="pad" style="padding:48px"><h1 class="display" style="font:500 42px Georgia,serif">'
                +'A place for ideas about attention.</h1><p>Explore the research library while new editions are published.</p></td></tr>'
                +'</table></td></tr></table></body></html>')
    return top_html(issue)+opening(issue)+overview(issue)+signal_cards(issue)+question_and_try(issue)+bottom(issue)

def render_index(issues):
    links=[]
    for issue in issues:
        date_str=issue["edition_date"]
        links.append('<a href="'+esc(date_str)+'.html" style="display:block;background:#fff;border-top:4px solid #a43e50;padding:24px;margin:16px 0;color:#403036;text-decoration:none">'
            +'<span style="font:700 11px Arial,sans-serif;letter-spacing:1px;color:#a43e50">THE ATTENTION EDIT · '+esc(date_str)+'</span>'
            +'<h2 style="font:500 30px/1.2 Newsreader,Georgia,serif;margin:10px 0">'+esc(issue["headline"])+'</h2>'
            +'<p style="font:14px/1.65 Arial,sans-serif;color:#806e74">'+esc(issue.get("deck",""))+'</p>'
            +'<strong style="color:#9e3b4f;font-size:12px">Read the edition ↗</strong></a>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
      +'<title>The Attention Edit · Archive</title><link href="https://fonts.googleapis.com/css2?family=Newsreader:wght@400;500&display=swap" rel="stylesheet"></head>'
      +'<body style="margin:0;background:#f4eeeb;color:#3c2931"><header style="background:#a52c3e;color:#fff;padding:48px max(24px,calc((100% - 760px)/2))">'
      +'<a href="../#issue" style="font:600 12px Arial,sans-serif;color:#ffe8e6;text-decoration:none">← Observatory</a>'
      +'<h1 style="font:500 clamp(42px,6vw,70px)/1.1 Newsreader,Georgia,serif;margin:18px 0 4px">The Attention Edit.</h1>'
      +'<p style="font:14px Arial,sans-serif">Past issues, kept for readers who want to return.</p></header>'
      +'<main style="max-width:760px;margin:auto;padding:30px 24px 70px">'
      +(''.join(links) if links else '<p>No approved issues yet.</p>')+'</main></body></html>')

def rss_content(issue):
    """The same published copy, with sources, for downstream RSS/chat delivery."""
    parts=['<h1>'+esc(issue['headline'])+'</h1>']
    parts += ['<p>'+esc(issue.get(k,''))+'</p>' for k in ('deck','letter')]
    for section in issue.get('signals',[]) + [issue.get('tension',{})]:
        parts += ['<h2>'+esc(section.get('title',''))+'</h2>',
                  '<p>'+esc(section.get('text',''))+'</p>',
                  '<p>'+source_links(issue, section.get('source_ids',[]))+'</p>']
    experiment=issue.get('experiment',{})
    parts += ['<h2>'+esc(experiment.get('title',''))+'</h2>',
              '<p>'+esc(experiment.get('text',''))+'</p>',
              '<p>'+esc(experiment.get('caution',''))+'</p>']
    parts += ['<p>'+esc(issue.get(k,''))+'</p>' for k in ('closer','editorial_note')]
    return ''.join(parts)


def build_rss(issues):
    rss=ET.Element("rss",{"version":"2.0"})
    channel=ET.SubElement(rss,"channel")
    for key,value in (
        ("title","The Attention Edit | AI & Attention Observatory"),
        ("link",BASE+"issues/"),
        ("description","A weekly editorial digest connecting research, ideas and practical questions about AI and human attention."),
        ("language","en-us"),
        ("ttl","60")
    ):ET.SubElement(channel,key).text=value
    ET.SubElement(channel,"{"+ATOM+"}link",{
        "href":FEED,"rel":"self","type":"application/rss+xml"
    })
    if issues:
        latest=published_on(issues[0]["edition_date"])
        ET.SubElement(channel,"lastBuildDate").text=rss_date(latest)
        ET.SubElement(channel,"pubDate").text=rss_date(latest)
    for issue in issues[:50]:
        permalink=BASE+"issues/"+issue["edition_date"]+".html"
        item=ET.SubElement(channel,"item")
        ET.SubElement(item,"title").text=issue["subject"]
        ET.SubElement(item,"link").text=permalink
        ET.SubElement(item,"guid",{"isPermaLink":"true"}).text=permalink
        ET.SubElement(item,"pubDate").text=rss_date(published_on(issue["edition_date"]))
        summary=issue.get("deck","")+" "+issue.get("closer","")
        ET.SubElement(item,"description").text=summary.strip()
        ET.SubElement(item,"{"+CONTENT+"}encoded").text=rss_content(issue)
        ET.SubElement(item,"category").text="AI and attention"
    ET.indent(rss)
    xml=ET.tostring(rss,encoding="utf-8",xml_declaration=True)
    xml=xml.replace(b"?>",b"?>\n<?xml-stylesheet type=\"text/xsl\" href=\"assets/feed.xsl\"?>",1)
    ET.fromstring(xml)
    (ROOT/"issue-feed.xml").write_bytes(xml)
    return len(issues)

def build():
    current=json.loads((DATA/"public-issue.json").read_text())
    approved=DATA/"approved-issues"
    approved.mkdir(parents=True,exist_ok=True)
    if current.get("status")=="published":
        date.fromisoformat(current["edition_date"])
        (approved/(current["edition_date"]+".json")).write_text(
            json.dumps(current,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
        )
    issues=[]
    for file in sorted(approved.glob("????-??-??.json"),reverse=True):
        issue=json.loads(file.read_text(encoding="utf-8"))
        if issue.get("status")=="published":
            date.fromisoformat(issue["edition_date"])
            issues.append(issue)
    newest=issues[0] if issues else current
    (ROOT/"newsletter.html").write_text(render_issue(newest),encoding="utf-8")
    folder=ROOT/"issues"
    folder.mkdir(parents=True,exist_ok=True)
    for issue in issues:
        (folder/(issue["edition_date"]+".html")).write_text(render_issue(issue),encoding="utf-8")
    (folder/"index.html").write_text(render_index(issues),encoding="utf-8")
    count=build_rss(issues)
    print(json.dumps({"newsletter_preview":"latest approved" if count else "in review",
                      "published_issues":count,"rss_path":"issue-feed.xml",
                      "archive_path":"issues/index.html"}))
    return count

if __name__=="__main__":build()
