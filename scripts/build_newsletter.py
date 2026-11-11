"""Publish the editorial Weekly Brief as a readable email-preview and standards-compliant RSS.

Built from approved issue copy; never sends emails or asserts a subscriber exists.
An unreviewed new week must not erase the latest published edition.
"""
from __future__ import annotations
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from original_readings import safe_url as safe_original_url
from build_issue import citation_url, validate_issue_citations, validate_section_citations
from build_reader import encoded
from hashlib import sha256
import html
import json
import re
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

STYLE = '''
.glossary dt{scroll-margin-top:24px}.glossary dt:focus{outline:3px solid #E00122;outline-offset:4px}

*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;background:#fffefa;color:#333;font:16px/1.75 "Open Sans",Arial,sans-serif}a{color:#b6001c;text-underline-offset:4px}a:hover{text-decoration-thickness:2px}a:focus-visible,summary:focus-visible{outline:3px solid #E00122;outline-offset:5px}.shell{max-width:920px;margin:auto;padding:0 40px}header{border-top:7px solid #E00122;border-bottom:1px solid #d7d1d2;padding:22px 0;background:#fff}.nav{display:flex;justify-content:space-between;gap:24px;align-items:center;font-size:13px}.brand{font:700 18px/1.1 Jost,Arial,sans-serif;letter-spacing:.025em;text-decoration:none;color:#333}.stamp{font:600 12px/1.6 Jost,Arial,sans-serif;text-transform:uppercase;letter-spacing:.12em;color:#a8001a}main{padding-top:48px!important;padding-bottom:64px!important}h1,h2,h3{font-family:"Gentium Book Plus",Georgia,serif;font-weight:400;line-height:1.1;letter-spacing:-.025em;margin:0 0 18px}h1{font-size:clamp(38px,5.8vw,62px);max-width:800px}h2{font-size:34px}h3{font-size:28px}p{margin:0 0 18px}.deck{font-size:19px;line-height:1.65;max-width:720px}.scope{font-size:12px;color:#646064}.overview{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;padding:0;list-style:none;margin:36px 0}.overview li{border-top:3px solid #E00122;padding:18px 0;font:400 23px/1.18 "Gentium Book Plus",Georgia,serif}.signal{padding:34px 0;border-top:1px solid #d7d1d2}.source-links{font-size:13px;margin-top:20px}.source-link{overflow-wrap:anywhere}.pair{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin:28px 0}.card{padding:28px;background:#f1eeed;border:1px solid #d7d1d2;border-radius:0}.card:last-child{background:#E00122;color:#fff;border-color:#E00122}.card:last-child a,.card:last-child summary,.card:last-child .stamp{color:#fff}.card:last-child a:focus-visible,.card:last-child summary:focus-visible,footer a:focus-visible{outline-color:#fff}details{margin:18px 0}summary{cursor:pointer;font:600 13px/1.7 "Open Sans",Arial,sans-serif;color:#333;min-height:44px;padding:10px 0}details[open]>summary{margin-bottom:12px}.long-copy{max-width:72ch}.caution{font-size:13px}.takeaway{border-left:4px solid #E00122;padding:8px 0 8px 24px;font:400 27px/1.35 "Gentium Book Plus",Georgia,serif}.source-shelf{border-top:1px solid #d7d1d2;padding-top:22px;font-size:14px}.source-shelf li{margin:24px 0;overflow-wrap:anywhere}.source-shelf p{margin:6px 0}.source-meta{color:#646064;font-size:13px}footer{background:#E00122;color:#fff;padding:36px 0}footer a{color:#fff}footer p{font-size:13px}.archive-card{display:block;background:#fff;border:0;border-top:2px solid #E00122;padding:28px 0;margin:20px 0;text-decoration:none;color:#333}.archive-card:hover h2{color:#b6001c}@media(max-width:600px){.shell{padding:0 20px}.nav{align-items:flex-start;gap:14px;font-size:12px}.brand{font-size:15px}main{padding-top:32px!important}.overview{grid-template-columns:1fr;gap:0;margin:28px 0}.overview li{padding:16px 0;border-top-width:1px;font-size:23px}.pair{grid-template-columns:1fr}.card{padding:24px}h2{font-size:29px}.deck{font-size:17px}.takeaway{font-size:24px;padding-left:20px}}@media print{details>*{display:block!important}}
'''

def brief_title(value):
    """Present the new masthead without rewriting frozen issue snapshots."""
    return str(value or '').replace('Attention Edit','Attention Brief').replace('Weekly Edit','Weekly Brief')

def readable_version(value):
    version=str(value or 'stated version')
    return version.replace('_',' ').replace('arxiv','arXiv').replace('publisher article','Publisher article')

def source_links(issue,ids):
    lookup={r['id']:r for r in issue.get('sources',[])}
    out=[]
    for number,ident in enumerate(ids or [],1):
        source=lookup.get(ident)
        if not source:continue
        original=source.get('original_summary') and safe_original_url(source.get('source_url'))
        url=citation_url(source)
        version=(' · '+readable_version(source.get('source_version'))) if original else ''
        out.append('<a class="source-link" href="'+esc(url)+'" title="'+esc(source.get('title') or 'Original source')+'">'+esc((source.get('title') or 'Original source')+version)+'</a>')
    return ' · '.join(out)

def source_shelf(issue, disclosure=True):
    """One provenance shelf, complete in RSS and expandable on the web."""
    rows=[]
    for source in issue.get('sources',[]):
        original=source.get('original_summary') and safe_original_url(source.get('source_url'))
        url=citation_url(source)
        row='<li><a href="'+esc(url)+'">'+esc(source.get('title') or 'Original source')+'</a>'
        meta=[source.get(k) for k in ('kind','venue','published','reading_level','source_version') if source.get(k)]
        row+='<p class="source-meta">'+esc(' · '.join(meta))+'</p>'
        for key,label in [('source_doi','Source DOI'),('related_journal_doi','Related journal DOI (different version)'),('review_label','Source assessment'),('review_scope','Scope'),('quality_note','Limits')]:
            if source.get(key):row+='<p>'+esc(label+': '+source[key])+'</p>'
        notices=[]
        for key in ('notice','temporal_notice'):
            notice=source.get(key)
            if notice and notice not in notices:
                row+='<p>'+esc(notice)+'</p>'
                notices.append(notice)
        rows.append(row+'</li>')
    note=render_text(issue.get('editorial_note',''),issue)
    if any(s.get('original_summary') for s in issue.get('sources',[])):
        note+='<p>AI source-check, not human review or independent replication. Version-specific scope and limitations are listed with each source.</p>'
    content=note+'<ol>'+''.join(rows)+'</ol>'
    return ('<details class="source-shelf"><summary>Sources &amp; reading details · '+str(len(rows))+'</summary>'+content+'</details>') if disclosure else '<h2>Sources &amp; reading details</h2>'+content

def top_html(issue):
    snapshot = ('<meta name="observatory-edition-sha256" content="'+sha256(encoded(issue)).hexdigest()+'">') if issue.get('status')=='published' else ''
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="theme-color" content="#E00122">'+snapshot+'<title>'+esc(brief_title(issue['subject']))+'</title><style>'+STYLE+'</style></head><body>'
            '<header><div class="shell nav"><a class="brand" href="'+BASE+'">AI &amp; ATTENTION</a><a href="'+BASE+'issues/">The Weekly Brief</a></div></header><main class="shell">')

def section_label(label):
    return '<p class="stamp">'+esc(label)+'</p>'

def publication_scope(issue):
    window=issue.get('publication_window') or {}
    return ('Sources originally published '+str(window.get('from'))+' through '+str(window.get('to'))+
            ' (UTC). Older background sources are not included.') if window else ''

def glossary_id(index,entry):
    slug=re.sub(r'[^a-z0-9]+','-',entry['term'].casefold()).strip('-') or 'definition'
    return 'term-'+slug+'-'+str(index)

def text_spans(text,issue=None,section=None):
    issue=issue or {};section=section or {}
    sources={s['id']:s for s in issue.get('sources',[])}
    spans=[]
    for citation in validate_section_citations(section,issue.get('sources',[])) if section else []:
        start=text.index(citation['text']);source=sources[citation['source_id']]
        url=citation_url(source)
        path=urlsplit(url).path.lower()
        if citation.get('page') and (path.endswith('.pdf') or '/pdf/' in path):
            url=url.split('#',1)[0]+'#page='+str(citation['page'])
        title=source.get('title','')+(' · '+citation['locator'] if citation.get('locator') else '')
        spans.append((start,start+len(citation['text']),url,title,'inline-citation'))
    for index,entry in enumerate(issue.get('glossary',[]),1):
        for match in re.finditer(r'(?<!\w)'+re.escape(entry['term'])+r'(?!\w)',text,re.I):
            start,end=match.span()
            if not any(start<b and end>a for a,b,*_ in spans):
                spans.append((start,end,'#'+glossary_id(index,entry),entry['definition'],'glossary-term'))
    return sorted(spans)

def render_text(text,issue=None,section=None,end=None,css='long-copy'):
    """Escape plain-text segments separately, never search or replace HTML."""
    text=str(text or '');end=len(text) if end is None else end
    spans=text_spans(text,issue,section)
    paragraphs=[]
    # Keep exact paragraph boundaries. A citation spanning a break is split into
    # two links to the same source, preserving valid paragraph markup.
    start=0
    for paragraph in re.split(r'\n\s*\n',text[:end]):
        stop=start+len(paragraph);cursor=start;parts=[]
        for a,b,url,title,kind in spans:
            left=max(a,start);right=min(b,stop)
            if left>=right:continue
            parts.append(esc(text[cursor:left]))
            parts.append('<a class="'+kind+'" href="'+esc(url)+'" title="'+esc(title)+'">'+esc(text[left:right])+'</a>')
            cursor=right
        parts.append(esc(text[cursor:stop]))
        paragraphs.append('<p'+(' class="'+css+'"' if css else '')+'>'+''.join(parts)+'</p>')
        separator=re.match(r'\n\s*\n',text[stop:end])
        start=stop+(separator.end() if separator else 0)
    return ''.join(paragraphs)

def glossary_html(issue):
    entries=issue.get('glossary',[])
    if not entries:return ''
    return '<section class="glossary" aria-label="Plain-language glossary"><h2>A few useful terms</h2><dl>'+''.join(
        '<dt id="'+glossary_id(i,e)+'" tabindex="-1"><strong>'+esc(e['term'])+'</strong></dt><dd>'+esc(e['definition'])+'</dd>'
        for i,e in enumerate(entries,1))+'</dl></section>'

def long_copy(text,label='Read the full analysis',issue=None,section=None):
    text=str(text or '')
    full=render_text(text,issue,section)
    if len(text)<260:return full
    end=len(text)
    for match in re.finditer(r'[.!?][”’"\']?(?=\s|$)',text):
        prefix=text[:match.end()]
        if re.search(r'\b(?:e\.g|i\.e|et al|Dr|Mr|Ms|Prof|Fig|vs)\.$',prefix,re.I):continue
        if re.search(r'\b[A-Z]\.$',prefix):continue
        end=match.end();break
    # Do not cut a source phrase in half at a sentence boundary.
    for start,stop,*_ in text_spans(text,issue,section):
        if start<end<stop:end=stop
    if end==len(text):return full
    return render_text(text,issue,section,end=end,css='long-copy preview-copy')+'<details><summary>'+esc(label)+'</summary>'+full+'</details>'

def opening(issue):
    return (section_label('Issue '+str(issue.get('number','—'))+' · '+issue['edition_date'])
            +'<h1>'+esc(issue['headline'])+'</h1><p class="deck">'+esc(issue.get('deck',''))+'</p>'
            +long_copy(issue.get('letter',''),'Read the opening argument',issue)
            +('<p class="scope">'+esc(publication_scope(issue))+'</p>' if publication_scope(issue) else ''))

def overview(issue):
    return '<ul class="overview">'+''.join('<li><a href="#signal-'+str(i)+'">'+esc(s.get('short',s.get('title','')))+'</a></li>' for i,s in enumerate(issue.get('signals',[]),1))+'</ul>'

def signal_cards(issue):
    return ''.join('<section class="signal" id="signal-'+str(i)+'">'+section_label('Signal '+str(i).zfill(2))+'<h2>'+esc(s['title'])+'</h2>'+long_copy(s['text'],issue=issue,section=s)+'<p class="source-links">'+source_links(issue,s.get('source_ids',[]))+'</p></section>' for i,s in enumerate(issue.get('signals',[]),1))

def question_and_try(issue):
    t=issue['tension'];p=issue['experiment']
    return ('<div class="pair"><section class="card">'+section_label('The productive tension')+'<h3>'+esc(t['title'])+'</h3>'+long_copy(t['text'],'Explore the tension',issue,t)+'<p class="source-links">'+source_links(issue,t.get('source_ids',[]))+'</p></section>'
            '<section class="card">'+section_label('Try it')+'<h3>'+esc(p['title'])+'</h3>'+long_copy(p['text'],'See the activity',issue)+'<p class="caution">'+esc(p.get('caution',''))+'</p></section></div>')

def bottom(issue):
    return ('<p class="takeaway">'+esc(issue['closer'])+'</p>'+glossary_html(issue)+source_shelf(issue)+'</main><footer><div class="shell">'
            '<p><strong>THE ATTENTION BRIEF</strong></p><p>A weekly look at what AI changes about thinking, focus, and human agency.</p>'
            '<p><a href="'+BASE+'issues/">Past editions</a> · <a href="'+FEED+'">Weekly RSS</a> · <a href="https://chengyufang.org/">About the editor</a></p>'
            '<p>Read online or follow via RSS. Email subscriptions are not active.</p></div></footer></body></html>')

def render_issue(issue):
    if issue.get('status')!='published':
        return top_html({'subject':'The Attention Brief · Ideas about AI and attention'})+'<h1>A place for ideas about attention.</h1><p>Explore the research library while new editions are published.</p></main></body></html>'
    validate_issue_citations(issue)
    return top_html(issue)+opening(issue)+overview(issue)+signal_cards(issue)+question_and_try(issue)+bottom(issue)

def render_index(issues):
    links=['<a class="archive-card" href="'+esc(i['edition_date'])+'.html">'+section_label('Issue '+str(i.get('number','—'))+' · '+i['edition_date'])+'<h2>'+esc(i['headline'])+'</h2><p>'+esc(i.get('deck',''))+'</p><strong>Read the edition</strong></a>' for i in issues]
    return top_html({'subject':'The Attention Brief · Archive'})+'<h1>The Attention Brief.</h1><p>Past issues, ready to revisit.</p>'+(''.join(links) if links else '<p>No approved issues yet.</p>')+'</main></body></html>'

def rss_content(issue):
    """The same published copy, with sources, for downstream RSS/chat delivery."""
    validate_issue_citations(issue)
    parts=['<h1>'+esc(issue['headline'])+'</h1>']
    if publication_scope(issue):parts.append('<p>'+esc(publication_scope(issue))+'</p>')
    parts += [render_text(issue.get(k,''),issue) for k in ('deck','letter')]
    for section in issue.get('signals',[]) + [issue.get('tension',{})]:
        parts += ['<h2>'+esc(section.get('title',''))+'</h2>',
                  render_text(section.get('text',''),issue,section),
                  '<p>'+source_links(issue, section.get('source_ids',[]))+'</p>']
    experiment=issue.get('experiment',{})
    parts += ['<h2>'+esc(experiment.get('title',''))+'</h2>',
              render_text(experiment.get('text',''),issue),
              '<p>'+esc(experiment.get('caution',''))+'</p>']
    parts += ['<p>'+esc(issue.get('closer',''))+'</p>', glossary_html(issue), source_shelf(issue, disclosure=False)]
    return ''.join(parts)


def build_rss(issues):
    rss=ET.Element("rss",{"version":"2.0"})
    channel=ET.SubElement(rss,"channel")
    for key,value in (
        ("title","The Attention Brief | AI & Attention Observatory"),
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
        ET.SubElement(item,"title").text=brief_title(issue["subject"])
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

def json_feed(issues):
    """Same published editions and stable IDs for clients that reject XML."""
    return {'version':'https://jsonfeed.org/version/1.1',
            'title':'The Attention Brief | AI & Attention Observatory',
            'home_page_url':BASE+'issues/', 'feed_url':BASE+'data/issue-feed.json',
            'items':[{'id':BASE+'issues/'+i['edition_date']+'.html',
                      'url':BASE+'issues/'+i['edition_date']+'.html',
                      'title':brief_title(i['subject']), 'date_published':published_on(i['edition_date']).isoformat(),
                      'summary':i.get('deck',''), 'content_html':rss_content(i),
                      '_observatory':i} for i in issues[:50] if i.get('status')=='published']}


def build():
    current=json.loads((DATA/"public-issue.json").read_text())
    approved=DATA/"approved-issues"
    approved.mkdir(parents=True,exist_ok=True)
    if current.get("status")=="published":
        validate_issue_citations(current)
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
    (DATA/'issue-feed.json').write_text(json.dumps(json_feed(issues),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({"newsletter_preview":"latest approved" if count else "in review",
                      "published_issues":count,"rss_path":"issue-feed.xml",
                      "archive_path":"issues/index.html"}))
    return count

if __name__=="__main__":build()
