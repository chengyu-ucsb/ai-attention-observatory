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

def publication_timestamp(issue):
    """Feed clocks record release time; Monday is an edition identity, not a claim of timely release."""
    value=issue.get('feed_published_at') or issue.get('published_at')
    if not value:return published_on(issue['edition_date'])
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None:raise ValueError('Publication timestamp must include a timezone')
    return stamp.astimezone(timezone.utc)

def feed_identity(issue):
    value=issue.get('feed_id') or BASE+'issues/'+issue['edition_date']+'.html'
    if not re.fullmatch(re.escape(BASE)+r'issues/20\d\d-\d\d-\d\d\.html',value):
        raise ValueError('Invalid permanent edition feed identity')
    return value

def edition_label(issue):
    day=date.fromisoformat(issue['edition_date'])
    # Frozen pre-consolidation versions retain their real historical label.
    prefix='Week of ' if day.weekday()==0 else 'Original edition · '
    return prefix+day.strftime('%A, %B ')+str(day.day)+day.strftime(', %Y')

def rss_date(value):
    return format_datetime(value.astimezone(timezone.utc),usegmt=True)

STYLE = '''
/* Layout is local; font families and the reading scale come from typography.css. */
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#fffefa;color:#333;font:400 var(--type-body)/var(--leading-reading) var(--font-reading)}
a{color:#b6001c;text-underline-offset:4px}a:hover{text-decoration-thickness:2px}
a:focus-visible,summary:focus-visible,button:focus-visible,select:focus-visible{outline:3px solid #E00122;outline-offset:5px}
.shell{max-width:920px;margin:auto;padding:0 40px}
header{border-top:7px solid #E00122;border-bottom:1px solid #d7d1d2;padding:22px 0;background:#fff}
.nav{display:flex;justify-content:space-between;gap:24px;align-items:center;font:600 var(--type-small)/1.5 var(--font-interface)}
.brand{font:700 1.125rem/1.2 var(--font-interface);letter-spacing:.025em;text-decoration:none;color:#333}
.stamp{font:600 var(--type-caption)/1.5 var(--font-interface);text-transform:uppercase;letter-spacing:.08em;color:#a8001a}
main{padding-top:48px!important;padding-bottom:64px!important}
h1,h2,h3{font-family:var(--font-editorial);font-weight:700;line-height:var(--leading-heading);letter-spacing:-.015em;margin:0 0 18px;text-wrap:balance;overflow-wrap:break-word}
h1{font-size:var(--type-title);max-width:800px}h2{font-size:var(--type-section)}h3{font-size:var(--type-card)}
p{margin:0 0 18px}.deck{font-size:var(--type-lead);line-height:1.65;max-width:var(--measure-reading)}
.scope{font-size:var(--type-caption);color:#646064}
.overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;padding:0;list-style:none;margin:36px 0}
.overview li{border-top:3px solid #E00122;padding:18px 0;font:400 var(--type-card)/1.3 var(--font-editorial)}
.signal{padding:34px 0;border-top:1px solid #d7d1d2}
.source-links{font-size:var(--type-small);margin-top:20px}.source-link{overflow-wrap:anywhere}
.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px;margin:28px 0}
.card{padding:28px;background:#f1eeed;border:1px solid #d7d1d2;border-radius:0;min-width:0}
.card:last-child{background:#E00122;color:#fff;border-color:#E00122}
.card:last-child a,.card:last-child summary,.card:last-child .stamp{color:#fff}
.card:last-child a:focus-visible,.card:last-child summary:focus-visible,footer a:focus-visible{outline-color:#fff}
details{margin:18px 0}summary{cursor:pointer;font:600 var(--type-small)/1.6 var(--font-interface);color:#333;min-height:44px;padding:10px 0}
details[open]>summary{margin-bottom:12px}.long-copy{max-width:var(--measure-reading)}.caution{font-size:var(--type-small)}
.takeaway{border-left:4px solid #E00122;padding:8px 0 8px 24px;font:400 var(--type-card)/1.4 var(--font-editorial);max-width:50ch}
.source-shelf{border-top:1px solid #d7d1d2;padding-top:22px;font-size:var(--type-small)}
.source-shelf li{margin:24px 0;overflow-wrap:anywhere}.source-shelf p{margin:6px 0}.source-meta{color:#646064;font-size:var(--type-caption)}
.glossary{max-width:var(--measure-reading)}.glossary dt{scroll-margin-top:24px}.glossary dt:focus{outline:3px solid #E00122;outline-offset:4px}.glossary dd{margin:6px 0 20px}
footer{background:#E00122;color:#fff;padding:36px 0}footer a{color:#fff}footer p{font-size:var(--type-small)}
.archive-card{display:block;background:#fff;border:0;border-top:2px solid #E00122;padding:28px 0;margin:20px 0;text-decoration:none;color:#333}.archive-card:hover h2{color:#b6001c}
@media(max-width:600px){.shell{padding:0 20px}.nav{align-items:flex-start;gap:14px;flex-wrap:wrap}.brand{font-size:1rem}main{padding-top:32px!important}.overview{grid-template-columns:1fr;gap:0;margin:28px 0}.overview li{padding:16px 0;border-top-width:1px}.pair{grid-template-columns:1fr}.card{padding:24px}.takeaway{padding-left:20px}}
@media print{details>*{display:block!important}}
'''

# The full edition remains readable without JavaScript. Enhancement adds one
# reading section at a time and moves secondary material into native dialogs.
STYLE += '''
[hidden]{display:none!important}
button,select{font:600 var(--type-small)/1.4 var(--font-interface);color:inherit}
button{cursor:pointer;min-height:44px;border:1px solid #bfb7b7;background:#fffefa;padding:10px 16px;border-radius:4px}
button:hover{border-color:#b6001c;color:#b6001c}
.edition-intro{max-width:var(--measure-reading)}.edition-intro .preview-copy{display:none}
.edition-intro details{margin:4px 0 12px}.edition-intro .layer-open{margin:0 0 12px}
.ai-note{font-size:var(--type-caption);color:#646064;margin:12px 0 22px}
.reader-map{padding:22px;background:#f5f1ee;border:1px solid #ded6d1;margin:26px 0 20px;border-radius:8px}
.reader-map .stamp{margin:0 0 14px}.map-hub{display:flex;align-items:center;gap:10px;font:600 var(--type-small)/1.4 var(--font-interface);margin:0 0 16px}
.map-hub svg{width:34px;height:34px;flex:none;color:#b6001c}.map-note{font-size:var(--type-caption);margin:0;color:#646064}
.overview{grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:0 0 12px}.overview li{padding:0;border:0;position:relative}
.overview a{display:flex;flex-direction:column;gap:6px;height:100%;min-height:108px;padding:15px;background:#fffefa;border:1px solid #cfc5c2;border-top:3px solid #b6001c;border-radius:5px;text-decoration:none;color:#333}
.overview a:hover,.overview a[aria-current="true"]{border-color:#b6001c;background:#fff}.map-index{font:600 var(--type-caption)/1.2 var(--font-interface);color:#b6001c}
.map-label{font:600 1.05rem/1.35 var(--font-interface)}.map-count{font:400 var(--type-caption)/1.4 var(--font-reading);color:#646064;margin-top:auto}
.edition-controls{display:flex;align-items:end;justify-content:space-between;gap:14px;padding:16px 0;border-bottom:1px solid #d7d1d2}
.edition-select{display:grid;gap:6px;min-width:0;max-width:70%;font:600 var(--type-caption)/1.4 var(--font-interface)}
.edition-select select{width:100%;min-height:44px;max-width:100%;padding:8px 30px 8px 12px;background:#fffefa;border:1px solid #bfb7b7;border-radius:4px;text-overflow:ellipsis}
.edition-controls button[aria-pressed="true"]{background:#333;color:#fff;border-color:#333}
.edition-panel:focus{outline:none}.edition-panel{scroll-margin-top:24px}.edition-panel .signal:first-child{border-top:0}
.edition-utilities{display:flex;flex-wrap:wrap;gap:10px;margin-top:28px;padding-top:20px;border-top:1px solid #d7d1d2}
.edition-utilities>details{flex-basis:100%}.layer-open{background:transparent;font-weight:500}.layer-open::after{content:' +';color:#b6001c}.card:last-child .layer-open{color:#fff;border-color:#fff}.card:last-child .layer-open::after{color:#fff}
.edition-dialog{position:fixed;inset:0;width:min(760px,calc(100% - 32px));max-height:calc(100dvh - 32px);padding:0;border:1px solid #bfb7b7;border-top:4px solid #E00122;border-radius:10px;color:#333;background:#fffefa;overflow:auto;box-shadow:0 22px 90px #0004;overscroll-behavior:contain}
.edition-dialog::backdrop{background:#17121299}.dialog-header{position:sticky;top:0;display:flex;align-items:start;justify-content:space-between;gap:20px;padding:20px 26px 12px;background:#fffefa;border-bottom:1px solid #ded6d1;z-index:1}
.dialog-header h2{font-size:var(--type-card);margin:6px 0 0}.dialog-header button{flex:none}.dialog-body{padding:24px 26px}.dialog-body>ol{padding-left:22px}.dialog-body .source-shelf{border:0;padding:0}.dialog-body .scope{font-size:var(--type-small)}
@media(max-width:600px){.reader-map{padding:16px;margin-top:22px}.overview{gap:8px}.overview a{min-height:0;display:grid;grid-template-columns:25px minmax(0,1fr) auto;gap:8px;align-items:center;padding:12px;border-top-width:1px;border-left:3px solid #b6001c}.map-label{font-size:1rem}.map-count{margin:0;font-size:.8125rem;white-space:nowrap}.edition-controls{align-items:stretch;flex-direction:column;gap:10px}.edition-select{max-width:100%}.edition-controls button{align-self:start}.edition-dialog{width:calc(100% - 20px);max-height:calc(100dvh - 20px)}.dialog-header{padding:16px}.dialog-body{padding:20px}.edition-utilities .layer-open{flex:1 1 auto}}
@media(prefers-reduced-motion:no-preference){.edition-dialog[open]{animation:card-arrive .16s ease-out}@keyframes card-arrive{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}}
@media print{[data-edition-panel][hidden],.edition-dialog{display:block!important}.edition-controls,.layer-open,.dialog-header button{display:none!important}.edition-dialog{position:static;max-height:none;width:auto;border:0;box-shadow:none}.dialog-header{position:static}.dialog-body{padding:0}.overview{break-inside:avoid}}
'''

READER_SCRIPT = '''
<script>
(() => {
  'use strict';
  const panels=Array.from(document.querySelectorAll('[data-edition-panel]'));
  const controls=document.querySelector('.edition-controls'),select=document.getElementById('edition-section'),all=document.getElementById('edition-read-all');
  let showingAll=false;
  function show(id,focus=false){
    const target=document.getElementById(id);if(!target||!panels.includes(target))return;
    showingAll=false;panels.forEach(panel=>panel.hidden=panel!==target);
    select.value=id;all.setAttribute('aria-pressed','false');all.textContent='Show all sections';
    document.querySelectorAll('[data-edition-target]').forEach(link=>link.setAttribute('aria-current',String(link.dataset.editionTarget===id)));
    if(focus){target.focus({preventScroll:true});target.scrollIntoView({block:'start'});}
  }
  function showAll(){showingAll=true;panels.forEach(panel=>panel.hidden=false);all.setAttribute('aria-pressed','true');all.textContent='One section at a time';document.querySelectorAll('[data-edition-target]').forEach(link=>link.removeAttribute('aria-current'));}
  function revealHash(){
    let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
    const target=document.getElementById(id),panel=target&&target.closest('[data-edition-panel]');
    if(panel&&!showingAll)show(panel.id);
    if(target){requestAnimationFrame(()=>{target.scrollIntoView({block:'start'});if(target.hasAttribute('tabindex'))target.focus({preventScroll:true});});}
  }
  if(panels.length&&controls&&select&&all){
    controls.hidden=false;show(panels[0].id);
    select.addEventListener('change',()=>show(select.value));
    all.addEventListener('click',()=>showingAll?show(select.value):showAll());
    document.querySelectorAll('[data-edition-target]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();show(link.dataset.editionTarget,true);history.replaceState(null,'','#'+link.dataset.editionTarget);}));
    window.addEventListener('hashchange',revealHash);revealHash();
  }
  if(typeof HTMLDialogElement==='undefined'||!HTMLDialogElement.prototype.showModal)return;
  document.querySelectorAll('details[data-edition-layer]').forEach((details,index)=>{
    const summary=details.querySelector('summary'),label=summary.textContent.trim();
    const button=document.createElement('button');button.type='button';button.className='layer-open';button.textContent=label;
    const dialog=document.createElement('dialog');dialog.className='edition-dialog';dialog.id='edition-layer-'+index;
    button.setAttribute('aria-haspopup','dialog');button.setAttribute('aria-controls',dialog.id);button.dataset.openLayer=details.dataset.editionLayer;
    const header=document.createElement('div');header.className='dialog-header';const title=document.createElement('h2');title.id=dialog.id+'-title';title.textContent=label;dialog.setAttribute('aria-labelledby',title.id);
    const close=document.createElement('button');close.type='button';close.textContent='Close';close.setAttribute('aria-label','Close '+label);header.append(title,close);
    const body=document.createElement('div');body.className='dialog-body';Array.from(details.childNodes).forEach(node=>{if(node!==summary)body.append(node);});dialog.append(header,body);
    details.replaceWith(button);document.body.append(dialog);let previousOverflow='';
    button.addEventListener('click',()=>{previousOverflow=document.body.style.overflow;dialog.showModal();dialog.scrollTop=0;document.body.style.overflow='hidden';close.focus();});
    close.addEventListener('click',()=>dialog.close());
    dialog.addEventListener('close',()=>{document.body.style.overflow=previousOverflow;button.focus({preventScroll:true});});
    dialog.addEventListener('click',event=>{const r=dialog.getBoundingClientRect();if(event.target===dialog&&(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom))dialog.close();});
    dialog.querySelectorAll('a.glossary-term').forEach(link=>link.addEventListener('click',()=>dialog.close()));
  });
})();
</script>
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

def source_shelf(issue, disclosure=True, include_note=True):
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
    note=render_text(issue.get('editorial_note',''),issue) if include_note else ''
    if include_note and any(s.get('original_summary') for s in issue.get('sources',[])):
        note+='<p>AI source-check, not human review or independent replication. Version-specific scope and limitations are listed with each source.</p>'
    content=note+'<ol>'+''.join(rows)+'</ol>'
    return ('<details class="source-shelf" data-edition-layer="sources"><summary>Sources · '+str(len(rows))+'</summary>'+content+'</details>') if disclosure else '<h2>Sources &amp; reading details</h2>'+content

def top_html(issue, asset_prefix=""):
    """Load the shared type system relative to this page, including archives."""
    snapshot = ('<meta name="observatory-edition-sha256" content="'+sha256(encoded(issue)).hexdigest()+'">') if issue.get('status')=='published' else ''
    canonical=('<link rel="canonical" href="'+BASE+'issues/'+esc(issue['edition_date'])+'.html">') if issue.get('status')=='published' else ''
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="theme-color" content="#E00122">'+snapshot+canonical+'<title>'+esc(brief_title(issue['subject']))+'</title><link rel="stylesheet" href="'+esc(asset_prefix)+'assets/typography.css"><style>'+STYLE+'</style></head><body>'
            '<header><div class="shell nav"><a class="brand" href="'+BASE+'">AI &amp; ATTENTION</a><a href="'+BASE+'issues/">The Weekly Brief</a></div></header><main class="shell">')

def section_label(label):
    return '<p class="stamp">'+esc(label)+'</p>'

def publication_scope(issue):
    if issue.get('scope_kind')=='legacy_collection':
        return 'Historical collection, including earlier sources; not a strict previous-week digest.'
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

def glossary_html(issue, panel=False):
    entries=issue.get('glossary',[])
    if not entries:return ''
    attributes=' id="edition-glossary" data-edition-panel tabindex="-1"' if panel else ''
    return '<section class="glossary'+(' edition-panel' if panel else '')+'"'+attributes+' aria-label="Plain-language glossary"><h2>A few useful terms</h2><dl>'+''.join(
        '<dt id="'+glossary_id(i,e)+'" tabindex="-1"><strong>'+esc(e['term'])+'</strong></dt><dd>'+esc(e['definition'])+'</dd>'
        for i,e in enumerate(entries,1))+'</dl></section>'

def long_copy(text,label='Read the full analysis',issue=None,section=None,layer=None):
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
    attributes=(' data-edition-layer="'+esc(layer)+'"') if layer else ''
    return render_text(text,issue,section,end=end,css='long-copy preview-copy')+'<details'+attributes+'><summary>'+esc(label)+'</summary>'+full+'</details>'

def opening(issue):
    return (section_label('Issue '+str(issue.get('number','—'))+' · '+edition_label(issue))
            +'<h1>'+esc(issue['headline'])+'</h1><p class="deck">'+esc(issue.get('deck',''))+'</p>'
            +'<div class="edition-intro">'+long_copy(issue.get('letter',''),'The opening argument',issue,layer='opening')+'</div>'
            +'<p class="scope ai-note">AI-assisted summary. AI can make mistakes.</p>')

def overview(issue):
    return ('<nav class="reader-map" aria-label="Edition reading map">'+section_label('At a glance')
            +'<p class="map-hub"><svg aria-hidden="true" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2"><circle cx="20" cy="10" r="5"/><path d="M20 15v8M7 30v-7h26v7"/><circle cx="7" cy="33" r="3"/><circle cx="20" cy="33" r="3"/><circle cx="33" cy="33" r="3"/><path d="M20 23v7"/></svg>One argument, several lenses</p>'
            +'<ul class="overview">'+''.join('<li><a href="#signal-'+str(i)+'" data-edition-target="signal-'+str(i)+'"><span class="map-index">'+str(i).zfill(2)+'</span><span class="map-label">'+esc(s.get('short',s.get('title','')))+'</span><span class="map-count">'+str(len(s.get('source_ids',[])))+' source'+('' if len(s.get('source_ids',[]))==1 else 's')+'</span></a></li>' for i,s in enumerate(issue.get('signals',[]),1))+'</ul>'
            +'<p class="map-note">A guide to this edition. Choose a theme to explore.</p></nav>')

def reader_controls(issue):
    options=[('signal-'+str(i),s.get('short') or s['title']) for i,s in enumerate(issue.get('signals',[]),1)]
    options += [('edition-supplement-'+str(i),section['title']) for i,section in enumerate(issue.get('supplements',[]),1)]
    options += [('edition-question','The question & something to try')]
    if issue.get('glossary'):options.append(('edition-glossary','Useful terms'))
    return ('<div class="edition-controls" hidden><label class="edition-select" for="edition-section">Explore this edition<select id="edition-section">'
            +''.join('<option value="'+esc(key)+'">'+esc(label)+'</option>' for key,label in options)
            +'</select></label><button type="button" id="edition-read-all" aria-pressed="false">Show all sections</button></div>')

def source_layer(issue,ids,key):
    return ('<details class="source-links" data-edition-layer="'+esc(key)+'"><summary>Sources behind this theme · '+str(len(ids))+'</summary>'
            +'<p>'+source_links(issue,ids)+'</p></details>')

def signal_cards(issue):
    return ''.join('<section class="signal edition-panel" id="signal-'+str(i)+'" data-edition-panel tabindex="-1">'+section_label('Theme '+str(i).zfill(2))+'<h2>'+esc(s['title'])+'</h2>'+render_text(s['text'],issue,s)+source_layer(issue,s.get('source_ids',[]),'signal-'+str(i)+'-sources')+'</section>' for i,s in enumerate(issue.get('signals',[]),1))

def supplement_cards(issue):
    return ''.join('<section class="signal supplementary-analysis edition-panel" id="edition-supplement-'+str(i)+'" data-edition-panel tabindex="-1"><h2>'+esc(section['title'])+'</h2>'
        +render_text(section['text'],issue,section)
        +source_layer(issue,section.get('source_ids',[]),'supplement-'+str(i)+'-sources')+'</section>'
        for i,section in enumerate(issue.get('supplements',[]),1))

def publication_history(issue):
    first=issue.get('first_published_date') or str(issue.get('published_at') or '')[:10]
    updated=str(issue.get('updated_at') or '')[:10]
    entries=issue.get('edition_history',[])
    if not first and not entries:return ''
    parts=['<details class="publication-history" data-edition-layer="history"><summary>Publication history</summary>']
    if first:
        date.fromisoformat(first)
        parts.append('<p>First published '+esc(first)+'. The Monday label identifies the edition; it does not change when this version was released.</p>')
    if updated:
        date.fromisoformat(updated)
        parts.append('<p>Updated '+esc(updated)+'.</p>')
    if entries:
        parts.append('<ul>')
        for entry in entries:
            path=entry.get('url','')
            if not re.fullmatch(r'history/20\d\d-\d\d-\d\d\.html',path):raise ValueError('Invalid edition history path')
            parts.append('<li><a href="'+BASE+'issues/'+esc(path)+'">Original version · '+esc(entry['original_date'])+'</a>'
                         +(' — '+esc(entry['note']) if entry.get('note') else '')+'</li>')
        parts.append('</ul>')
    return ''.join(parts)+'</details>'

def question_and_try(issue):
    t=issue['tension'];p=issue['experiment']
    return ('<section id="edition-question" class="edition-panel" data-edition-panel tabindex="-1" aria-label="The question and something to try"><div class="pair"><section class="card">'+section_label('The productive tension')+'<h3>'+esc(t['title'])+'</h3>'+render_text(t['text'],issue,t)+source_layer(issue,t.get('source_ids',[]),'tension-sources')+'</section>'
            '<section class="card">'+section_label('Try it')+'<h3>'+esc(p['title'])+'</h3>'+render_text(p['text'],issue)+'<p class="caution">'+esc(p.get('caution',''))+'</p></section></div></section>')

def bottom(issue):
    methods='<details data-edition-layer="methods"><summary>How this was made</summary>'+render_text(issue.get('editorial_note',''),issue)
    if publication_scope(issue):methods+='<p class="scope">'+esc(publication_scope(issue))+'</p>'
    methods+='</details>'
    return ('<p class="takeaway">'+esc(issue['closer'])+'</p>'+glossary_html(issue,panel=True)+'<div class="edition-utilities">'+methods+source_shelf(issue,include_note=False)+publication_history(issue)+'</div></main><footer><div class="shell">'
            '<p><strong>THE ATTENTION BRIEF</strong></p><p>A weekly look at what AI changes about thinking, focus, and human agency.</p>'
            '<p><a href="'+BASE+'issues/">Past editions</a> · <a href="'+FEED+'">Weekly RSS</a> · <a href="https://chengyufang.org/">About the editor</a></p>'
            '</div></footer>'+READER_SCRIPT+'</body></html>')

def render_issue(issue, asset_prefix=""):
    if issue.get('status')!='published':
        return top_html({'subject':'The Attention Brief · Ideas about AI and attention'},asset_prefix)+'<h1>A place for ideas about attention.</h1><p>Explore the research library while new editions are published.</p></main></body></html>'
    validate_issue_citations(issue)
    return top_html(issue,asset_prefix)+opening(issue)+overview(issue)+reader_controls(issue)+signal_cards(issue)+supplement_cards(issue)+question_and_try(issue)+bottom(issue)

def render_index(issues):
    links=['<a class="archive-card" href="'+esc(i['edition_date'])+'.html">'+section_label('Issue '+str(i.get('number','—'))+' · '+edition_label(i))+'<h2>'+esc(i['headline'])+'</h2><p>'+esc(i.get('deck',''))+'</p><strong>Read the edition</strong></a>' for i in issues]
    return top_html({'subject':'The Attention Brief · Archive'},'../')+'<h1>The Attention Brief.</h1><p>Past issues, ready to revisit.</p>'+(''.join(links) if links else '<p>No approved issues yet.</p>')+'</main></body></html>'

def rss_content(issue):
    """The same published copy, with sources, for downstream RSS/chat delivery."""
    validate_issue_citations(issue)
    parts=['<p>'+esc(edition_label(issue))+'</p>'] if issue.get('edition_date') else []
    parts.append('<h1>'+esc(issue['headline'])+'</h1>')
    if publication_scope(issue):parts.append('<p>'+esc(publication_scope(issue))+'</p>')
    parts += [render_text(issue.get(k,''),issue) for k in ('deck','letter')]
    for section in issue.get('signals',[]) + issue.get('supplements',[]) + [issue.get('tension',{})]:
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
        latest=max(publication_timestamp(issue) for issue in issues)
        ET.SubElement(channel,"lastBuildDate").text=rss_date(latest)
        ET.SubElement(channel,"pubDate").text=rss_date(latest)
    for issue in issues[:50]:
        permalink=BASE+"issues/"+issue["edition_date"]+".html"
        item=ET.SubElement(channel,"item")
        ET.SubElement(item,"title").text=brief_title(issue["subject"])
        ET.SubElement(item,"link").text=permalink
        ET.SubElement(item,"guid",{"isPermaLink":"true"}).text=feed_identity(issue)
        ET.SubElement(item,"pubDate").text=rss_date(publication_timestamp(issue))
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
            'items':[{'id':feed_identity(i),
                      'url':BASE+'issues/'+i['edition_date']+'.html',
                      'title':brief_title(i['subject']), 'date_published':publication_timestamp(i).isoformat(),
                      'summary':i.get('deck',''), 'content_html':rss_content(i),
                      '_observatory':i} for i in issues[:50] if i.get('status')=='published']}



def render_alias(original_date,canonical_date):
    date.fromisoformat(original_date);date.fromisoformat(canonical_date)
    destination=canonical_date+'.html'
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="refresh" content="0; url='+destination+'"><link rel="canonical" href="'+BASE+'issues/'+destination+'">'
            '<meta name="robots" content="noindex"><title>This edition has a permanent Monday home</title>'
            '<link rel="stylesheet" href="../assets/typography.css"></head><body>'
            '<p>This edition is now part of the <a href="'+destination+'">'+canonical_date+' Monday edition</a>.</p>'
            '<p><a href="history/'+original_date+'.html">Read the original published version</a>.</p></body></html>')

def build_history_pages(folder,issues):
    path=DATA/'edition-lineage.json'
    if not path.exists():return
    lineage=json.loads(path.read_text())
    canonical={issue['edition_date'] for issue in issues}
    revisions=DATA/'edition-revisions'
    history=folder/'history';history.mkdir(exist_ok=True)
    for original,entry in lineage.get('revisions',{}).items():
        date.fromisoformat(original)
        target=entry['canonical_date']
        if target not in canonical:raise ValueError('History points to an absent canonical edition')
        snapshot=(revisions/(original+'.json')).read_bytes()
        if sha256(snapshot).hexdigest()!=entry.get('sha256'):
            raise ValueError('Original edition snapshot hash mismatch: '+original)
        source=json.loads(snapshot)
        page=render_issue(source,asset_prefix='../../')
        notice=('<aside class="scope"><strong>Original published version · '+esc(original)+'</strong><p>'+esc(entry.get('note',''))+'</p>'
                '<p><a href="../'+esc(target)+'.html">Read the consolidated '+esc(target)+' Monday edition</a>.</p></aside>')
        page=page.replace('<link rel="canonical" href="'+BASE+'issues/'+source['edition_date']+'.html">',
                          '<link rel="canonical" href="'+BASE+'issues/'+target+'.html">',1)
        page=page.replace('</head>','<meta name="robots" content="noindex"></head>',1)
        page=page.replace('<main class="shell">','<main class="shell">'+notice,1)
        (history/(original+'.html')).write_text(page,encoding='utf-8')
    for original,target in lineage.get('aliases',{}).items():
        if target not in canonical or original in canonical:raise ValueError('Invalid edition alias')
        if original not in lineage.get('revisions',{}):raise ValueError('Alias has no preserved original version')
        (folder/(original+'.html')).write_text(render_alias(original,target),encoding='utf-8')

def build():
    current=json.loads((DATA/"public-issue.json").read_text())
    approved=DATA/"approved-issues"
    approved.mkdir(parents=True,exist_ok=True)
    if current.get("status")=="published":
        validate_issue_citations(current)
        if date.fromisoformat(current["edition_date"]).weekday()!=0:
            raise ValueError("New editions must use their canonical Monday; consolidate legacy dates before building")
        (approved/(current["edition_date"]+".json")).write_text(
            json.dumps(current,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
        )
    issues=[]
    for file in sorted(approved.glob("????-??-??.json"),reverse=True):
        issue=json.loads(file.read_text(encoding="utf-8"))
        if issue.get("status")=="published":
            if date.fromisoformat(issue["edition_date"]).weekday()!=0:
                raise ValueError("Archive contains an unconsolidated edition date")
            if file.stem!=issue["edition_date"]:raise ValueError("Edition path and identity disagree")
            issues.append(issue)
    newest=issues[0] if issues else current
    (ROOT/"newsletter.html").write_text(render_issue(newest),encoding="utf-8")
    folder=ROOT/"issues"
    folder.mkdir(parents=True,exist_ok=True)
    for issue in issues:
        (folder/(issue["edition_date"]+".html")).write_text(render_issue(issue,asset_prefix="../"),encoding="utf-8")
    (folder/"index.html").write_text(render_index(issues),encoding="utf-8")
    build_history_pages(folder,issues)
    count=build_rss(issues)
    (DATA/'issue-feed.json').write_text(json.dumps(json_feed(issues),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({"newsletter_preview":"latest approved" if count else "in review",
                      "published_issues":count,"rss_path":"issue-feed.xml",
                      "archive_path":"issues/index.html"}))
    return count

if __name__=="__main__":build()
