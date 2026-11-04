"""Bounded, identifier-checked article retrieval; source text stays in memory.

Public accessibility is not permission to redistribute. This module never writes
PDFs or extracted passages. It uses official OA locators, records version and
coverage, respects robots, rejects login/challenge pages, and stops at 401/403.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
import os
import re
import time
from urllib.parse import urlsplit, urlencode, quote, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser

from enrich_deep_readings import ArticleParser, HOSTS as EDITORIAL_HOSTS
from enrich_repository_fulltext import ALLOWED_HOSTS as LEGACY_HOSTS

AGENT='AIAttentionObservatory/7.0 (+https://github.com/chengyu-ucsb/ai-attention-observatory)'
ARTICLE_HOSTS=set(LEGACY_HOSTS) | set(EDITORIAL_HOSTS) | {
    'www.econstor.eu','econstor.eu','pubsonline.informs.org',
    'bera-journals.onlinelibrary.wiley.com','onlinelibrary.wiley.com',
    'ajet.org.au','core.ac.uk','files01.core.ac.uk','fileserver-az.core.ac.uk',
    'ora.ox.ac.uk','discovery.ucl.ac.uk','eprints.soton.ac.uk','eprints.whiterose.ac.uk',
    'escholarship.org','dash.harvard.edu','dspace.mit.edu',
    'pure.mpg.de','research.manchester.ac.uk','eprints.lse.ac.uk',
    'arxiv.org','export.arxiv.org','zenodo.org','osf.io',
}
API_HOSTS={'api.unpaywall.org','api.core.ac.uk','api.semanticscholar.org','api.crossref.org'}
BLOCKED=re.compile(r'making sure you.re not a bot|verify you are human|enable javascript.*continue|access denied|captcha|anubis',re.I)
DOI=re.compile(r'^10\.\d{4,9}/\S+$',re.I)
MAX_BYTES=20_000_000


def normal(value):
    return re.sub(r'[^a-z0-9]+','',str(value).lower())


def doi(value):
    return re.sub(r'^https?://(?:dx\.)?doi\.org/','',str(value or '').strip(),flags=re.I).lower()


def safe_url(url, hosts=ARTICLE_HOSTS):
    try:
        p=urlsplit(url)
        host=(p.hostname or '').lower()
        # Exact hosts, plus known editorial subdomains; never arbitrary .edu/.org.
        allowed=host in hosts or (hosts is ARTICLE_HOSTS and any(host.endswith('.'+h) for h in EDITORIAL_HOSTS))
        return bool(p.scheme=='https' and allowed and not p.username and not p.password
                    and p.port in (None,443) and len(url)<2000)
    except ValueError:
        return False


class Guard(HTTPRedirectHandler):
    def __init__(self, hosts):
        super().__init__(); self.hosts=hosts
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not safe_url(newurl,self.hosts):
            raise ValueError('unapproved_redirect')
        # Never forward an API credential to another host.
        if urlsplit(newurl).hostname!=urlsplit(req.full_url).hostname:
            raise ValueError('cross_host_redirect_requires_review')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def request(url, hosts=ARTICLE_HOSTS, limit=MAX_BYTES, headers=None):
    if not safe_url(url,hosts): raise ValueError('unapproved_host')
    req=Request(url,headers={'User-Agent':AGENT,**(headers or {})})
    with build_opener(Guard(hosts)).open(req,timeout=22) as response:
        size=response.headers.get('Content-Length')
        if size and int(size)>limit: raise ValueError('document_too_large')
        body=response.read(limit+1)
        if len(body)>limit: raise ValueError('document_too_large')
        return body,response.geturl(),response.headers.get('Content-Type','')


def json_request(url,headers=None):
    body,_,_=request(url,API_HOSTS,4_000_000,headers)
    return json.loads(body)


def robots_allowed(url):
    p=urlsplit(url)
    try:
        body,_,_=request(p.scheme+'://'+p.netloc+'/robots.txt',limit=500000)
    except HTTPError as exc:
        return exc.code==404
    except Exception:
        return False
    robot=RobotFileParser()
    robot.parse(body.decode('utf-8','replace').splitlines())
    return robot.can_fetch(AGENT,url)


@dataclass
class Document:
    units: list[dict]
    url: str
    version: str='unspecified'
    coverage: dict=field(default_factory=dict)

    def manifest(self):
        text='\n'.join(x['text'] for x in self.units)
        return {'source_url':self.url,'document_version':self.version,
                'source_sha256':sha256(text.encode()).hexdigest(),
                'characters_retrieved':len(text),'units_retrieved':len(self.units),
                'retrieved_at':datetime.now(timezone.utc).isoformat(),
                'source_text_saved':False,'tables_figures_visually_checked':False,
                'supplements_checked':False,**self.coverage}


class CitationMetadata(HTMLParser):
    def __init__(self):
        super().__init__(); self.values={}
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='meta':
            name=(attrs.get('name') or attrs.get('property') or '').lower()
            if name in ('citation_doi','dc.identifier','citation_title','citation_pdf_url'):
                self.values[name]=attrs.get('content','')


def identity_matches(record,front,candidate_doi='',metadata=None):
    metadata=metadata or {}
    expected=doi(candidate_doi or record.get('doi'))
    title=normal(record.get('title',''))
    meta_doi=doi(metadata.get('citation_doi',''))
    if meta_doi and expected and meta_doi!=expected: return False
    title_match=bool(len(title)>=25 and title in normal(front))
    # Exact DOI boundary, not substring (10.x/abc cannot match 10.x/abcd).
    doi_match=bool(expected and re.search(re.escape(expected)+r'(?![A-Za-z0-9/._-])',front,re.I))
    return bool(title_match or (doi_match and meta_doi==expected))


def document_from_pdf(raw,record,url,version='unspecified',candidate_doi=''):
    if not raw.startswith(b'%PDF'): raise ValueError('not_pdf')
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(raw))
    if len(reader.pages)>300: raise ValueError('document_exceeds_page_budget')
    units=[{'location':f'page:{n+1}','text':page.extract_text() or ''}
           for n,page in enumerate(reader.pages)]
    front='\n'.join(x['text'] for x in units[:3])
    if not identity_matches(record,front,candidate_doi):
        raise ValueError('document_identity_unverified')
    text_pages=sum(bool(x['text'].strip()) for x in units)
    if sum(len(x['text']) for x in units)<1600: raise ValueError('insufficient_document_text')
    return Document(units,url,version,{
        'evidence_status':'full_document_retrieved' if text_pages==len(units) else 'partial_full_text',
        'pages_total':len(units),'pages_processed':len(units),'pages_with_text':text_pages,
        'layout_fidelity':'not_verified','semantic_completeness':'not_verified'})


def document_from_html(raw,record,url,version='unspecified',candidate_doi=''):
    page=raw.decode('utf-8','replace')
    if BLOCKED.search(page[:18000]): raise ValueError('access_challenge_not_article')
    meta=CitationMetadata(); meta.feed(page)
    if not identity_matches(record,page[:60000],candidate_doi,meta.values):
        raise ValueError('document_identity_unverified')
    parser=ArticleParser(); parser.feed(page)
    units=[{'location':f'paragraph:{n+1}','text':p} for n,p in enumerate(parser.paragraphs)]
    if len(units)<7 or sum(len(x['text']) for x in units)<1600:
        raise ValueError('insufficient_article_body')
    # Large HTML is NOT silently sampled or truncated. Completeness is not
    # inferred from body length, section names, or the presence of an abstract.
    return Document(units,url,version,{'evidence_status':'partial_full_text',
        'html_completeness':'not_verified','semantic_completeness':'not_verified'})


def fetch_candidate(candidate,record):
    url=candidate['url']
    if not safe_url(url): raise ValueError('host_requires_review')
    if not robots_allowed(url): raise ValueError('robots_disallow_or_unavailable')
    raw,final,kind=request(url)
    version=candidate.get('version','unspecified')
    target=candidate.get('doi',record.get('doi',''))
    if raw.startswith(b'%PDF'):
        return document_from_pdf(raw,record,final,version,target)
    if 'html' not in kind: raise ValueError('unsupported_content_type')
    meta=CitationMetadata(); meta.feed(raw.decode('utf-8','replace'))
    pdf=meta.values.get('citation_pdf_url')
    if pdf:
        pdf=urljoin(final,pdf)
        if safe_url(pdf) and robots_allowed(pdf):
            try:
                body,pdfurl,_=request(pdf)
                return document_from_pdf(body,record,pdfurl,version,target)
            except Exception:
                pass
    return document_from_html(raw,record,final,version,target)


def candidate(url,provider,identifier,version='unspecified',license_value=None):
    return {'url':url,'provider':provider,'doi':identifier,'version':version,
            'license':license_value,'redistribution_granted':False}


def unpaywall_candidates(identifier,get=json_request):
    email=os.getenv('UNPAYWALL_EMAIL','fangcu@ucmail.uc.edu')
    work=get('https://api.unpaywall.org/v2/'+quote(identifier,safe='/')+'?'+urlencode({'email':email}))
    if doi(work.get('doi'))!=identifier: raise ValueError('locator_identity_mismatch')
    rows=[]
    for loc in ([work.get('best_oa_location')] + (work.get('oa_locations') or [])):
        if not loc: continue
        for key in ('url_for_pdf','url_for_landing_page'):
            if loc.get(key): rows.append(candidate(loc[key],'Unpaywall',identifier,loc.get('version','unspecified'),loc.get('license')))
    return rows


def core_candidates(identifier,get=json_request):
    # CORE documents anonymous rate-limited access; no registration or payment
    # is initiated here. A 401/403/429 remains a recorded provider failure.
    work=get('https://api.core.ac.uk/v3/search/works?'+urlencode({'q':f'doi:"{identifier}"','limit':5}))
    rows=[]
    for hit in work.get('results',[]):
        ids=hit.get('doi') or hit.get('dois') or []
        if isinstance(ids,str): ids=[ids]
        if identifier not in {doi(x) for x in ids}: continue
        for key in ('downloadUrl','sourceFulltextUrls'):
            values=hit.get(key) or []
            if isinstance(values,str): values=[values]
            for value in values:
                if isinstance(value,str): rows.append(candidate(value,'CORE',identifier,license_value=hit.get('license')))
    return rows


def semantic_candidates(identifier,get=json_request):
    url='https://api.semanticscholar.org/graph/v1/paper/DOI:'+quote(identifier,safe='/')+'?fields=title,externalIds,openAccessPdf'
    work=get(url)
    if doi((work.get('externalIds') or {}).get('DOI'))!=identifier:
        raise ValueError('locator_identity_mismatch')
    pdf=work.get('openAccessPdf') or {}
    return [candidate(pdf['url'],'Semantic Scholar',identifier,license_value=pdf.get('license'))] if pdf.get('url') else []


def discover(record,providers=None):
    identifier=doi(record.get('doi'))
    rows=[]; diagnostics=[]
    existing=(record.get('analysis') or {}).get('fulltext_url')
    if existing: rows.append(candidate(existing,'existing_source',identifier))
    if record.get('kind')=='nonacademic' and record.get('url'):
        rows.append(candidate(record['url'],'original_article',''))
    if DOI.fullmatch(identifier):
        for name,provider in (providers or [('Unpaywall',unpaywall_candidates),('CORE',core_candidates),('Semantic Scholar',semantic_candidates)]):
            try:
                found=provider(identifier)
                rows.extend(found)
                diagnostics.append({'provider':name,'status':'candidates' if found else 'no_exact_match','candidates':len(found)})
            except HTTPError as exc:
                diagnostics.append({'provider':name,'status':'http_'+str(exc.code)})
            except Exception as exc:
                diagnostics.append({'provider':name,'status':type(exc).__name__})
            time.sleep(.25)
    seen=set(); unique=[]
    for row in rows:
        if row['url'] not in seen:
            seen.add(row['url']); unique.append(row)
    return unique,diagnostics


def retrieve(record,max_candidates=8):
    options,diagnostics=discover(record)
    # Try more than two alternatives, and retain landing pages for PDF metadata.
    for option in options[:max_candidates]:
        try:
            doc=fetch_candidate(option,record)
            return doc,diagnostics
        except HTTPError as exc:
            diagnostics.append({'provider':option['provider'],'status':'article_http_'+str(exc.code)})
        except Exception as exc:
            status=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
            diagnostics.append({'provider':option['provider'],'status':status[:100]})
    return None,diagnostics
