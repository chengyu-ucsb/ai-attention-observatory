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
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, urlencode, quote, urljoin, unquote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
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
    # Individually checked institutional/author sources, not a blanket .edu rule.
    'www.microsoft.com','research.aalto.fi','epub.ub.uni-muenchen.de','iagen.unam.mx',
    'opus.lib.uts.edu.au','www.martinreimann.com','ndownloader.figshare.com',
    'ijlter.org','www.ijlter.org',
}
API_HOSTS={'api.unpaywall.org','api.core.ac.uk','api.semanticscholar.org',
           'api.crossref.org','api.openaire.eu','api.openalex.org','www.ebi.ac.uk'}
BLOCKED=re.compile(r'making sure you.re not a bot|verify you are human|enable javascript.*continue|access denied|captcha|anubis',re.I)
DOI=re.compile(r'^10\.\d{4,9}/\S+$',re.I)
MAX_BYTES=20_000_000
SOURCE_HINTS=Path(__file__).resolve().parents[1]/'data/fulltext-source-hints.json'
ARXIV_ID=re.compile(r'^(?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(?:v\d+)?$',re.I)


def normal(value):
    return re.sub(r'[^a-z0-9]+','',str(value).lower())


def doi(value):
    return re.sub(r'^https?://(?:dx\.)?doi\.org/','',str(value or '').strip(),flags=re.I).lower()


def diagnostic_url(value):
    """Retain a useful source path without query tokens, fragments or userinfo."""
    try:
        p=urlsplit(str(value))
        if p.scheme not in ('http','https') or not p.hostname: return ''
        port=f':{p.port}' if p.port and p.port not in (80,443) else ''
        return f'{p.scheme}://{p.hostname.lower()}{port}{p.path}'[:2000]
    except (TypeError,ValueError):
        return ''


def arxiv_identifier(value):
    """Accept only an exact arXiv identifier or its canonical URL/DOI."""
    value=str(value or '').strip()
    identifier=''
    if value.lower().startswith('10.48550/arxiv.'):
        identifier=value[len('10.48550/arxiv.'):]
    elif value.startswith('https://'):
        try:
            p=urlsplit(value)
            if p.hostname not in ('arxiv.org','export.arxiv.org'): return ''
            match=re.fullmatch(r'/(?:abs|pdf|html)/(.+?)(?:\.pdf)?/?',p.path)
            if match: identifier=match.group(1)
        except ValueError:
            return ''
    else:
        identifier=value
    return identifier if ARXIV_ID.fullmatch(identifier) else ''


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
    # Callers may explicitly stage a validated PDF in private storage. This
    # module never writes it, and public manifests never contain the bytes.
    source_bytes: bytes | None=field(default=None,repr=False)

    def manifest(self):
        text='\n'.join(x['text'] for x in self.units)
        output={'source_url':diagnostic_url(self.url),'document_version':self.version,
                'source_sha256':sha256(text.encode()).hexdigest(),
                'characters_retrieved':len(text),'units_retrieved':len(self.units),
                'retrieved_at':datetime.now(timezone.utc).isoformat(),
                'source_text_saved':False,'tables_figures_visually_checked':False,
                'supplements_checked':False,**self.coverage}
        if self.source_bytes is not None:
            output.update(source_bytes_sha256=sha256(self.source_bytes).hexdigest(),
                          source_byte_count=len(self.source_bytes))
        return output


class CitationMetadata(HTMLParser):
    def __init__(self):
        super().__init__(); self.values={}
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='meta':
            name=(attrs.get('name') or attrs.get('property') or '').lower()
            if name in ('citation_doi','dc.identifier','citation_title','citation_pdf_url',
                        'citation_arxiv_id'):
                self.values[name]=attrs.get('content','')


SUPPLEMENT=re.compile(r'(?:supplement(?:ary|al)?|supporting[ _-]*(?:information|material)|appendi(?:x|ces)|(?:^|[/_. -])esm(?:[/_. -]|$)|erratum|corrigendum)',re.I)


class PublisherPDFLinks(CitationMetadata):
    """Follow publisher-declared PDF links, never guessed article URL suffixes."""
    def __init__(self):
        super().__init__(); self.links=[]; self.anchor=None
    def handle_starttag(self,tag,attrs):
        super().handle_starttag(tag,attrs)
        attrs=dict(attrs)
        if tag=='a': self.anchor={'href':attrs.get('href',''),'label':''}
        if tag=='link' and attrs.get('type','').lower()=='application/pdf':
            href=attrs.get('href','')
            if not SUPPLEMENT.search(unquote(href)): self.links.append(href)
    def handle_data(self,text):
        if self.anchor is not None: self.anchor['label']+=text
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor is not None:
            href=self.anchor['href']; label=' '.join(self.anchor['label'].lower().split())
            if not SUPPLEMENT.search(label+' '+unquote(href)) and (('pdf' in label and any(word in label for word in ('download','view','full'))) or label=='pdf'):
                self.links.append(href)
            self.anchor=None


def publisher_pdf_links(page,url,record,candidate_doi=''):
    parser=PublisherPDFLinks(); parser.feed(page)
    if not identity_matches(record,page[:60000],candidate_doi,parser.values): return []
    values=[]
    explicit=parser.values.get('citation_pdf_url')
    if explicit and not SUPPLEMENT.search(unquote(explicit)): values.append(urljoin(url,explicit))
    for raw in parser.links:
        link=urljoin(url,raw)
        # Generic Download links may not move onto another host. Cross-host
        # sources require an explicit citation URL or a verified source hint.
        if urlsplit(link).hostname==urlsplit(url).hostname: values.append(link)
    return list(dict.fromkeys(x for x in values if safe_url(x)))[:2]


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
        'layout_fidelity':'not_verified','semantic_completeness':'not_verified'},raw)


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


def candidate_identity(option,record):
    """Verify a changed-title arXiv version without relaxing document matching.

    A related DOI in an arXiv record is stronger evidence than title similarity.
    Other changed-title versions require a separately implemented verifier;
    an input title alias alone is never authority to substitute a different work.
    """
    parent=doi(record.get('doi'))
    target=doi(option.get('doi') or parent)
    title=str(option.get('title') or record.get('title') or '').strip()
    changed_title=bool(option.get('title') and normal(title)!=normal(record.get('title','')))
    changed_doi=bool(parent and target and parent!=target)
    if not (changed_title or changed_doi): return record,target,{}
    verification=option.get('identity_verification_url') or ''
    if not parent or doi(option.get('related_doi'))!=parent:
        raise ValueError('related_version_parent_mismatch')
    source_id=arxiv_identifier(option.get('url'))
    check_id=arxiv_identifier(verification)
    target_id=arxiv_identifier(target)
    base=lambda value: re.sub(r'v\d+$','',value).lower()
    if not (source_id and check_id and target_id and
            base(source_id)==base(check_id)==base(target_id) and
            urlsplit(verification).path.startswith('/abs/') and safe_url(verification)):
        raise ValueError('related_version_verification_required')
    if not robots_allowed(verification):
        raise ValueError('related_version_verification_unavailable')
    raw,_,kind=request(verification,limit=2_000_000)
    if 'html' not in kind: raise ValueError('related_version_verification_unavailable')
    page=raw.decode('utf-8','replace')
    if BLOCKED.search(page[:18000]): raise ValueError('access_challenge_not_article')
    meta=CitationMetadata(); meta.feed(page)
    if not (doi(meta.values.get('citation_doi'))==parent and
            normal(meta.values.get('citation_title',''))==normal(title) and
            base(meta.values.get('citation_arxiv_id',''))==base(source_id)):
        raise ValueError('related_version_identity_unverified')
    # arXiv can cite the later journal DOI in its own metadata. Require that
    # verified parent DOI and the distinct preprint title when parsing the body.
    identity={**record,'title':title,'doi':parent}
    provenance={'identity_verification':'arxiv_related_doi_title_and_identifier',
                'identity_verification_url':diagnostic_url(verification),
                'record_doi':parent,'source_doi':target,
                'document_title':title,'source_relation':'related_preprint'}
    return identity,parent,provenance


def fetch_candidate(candidate,record):
    if candidate.get('structured_format'):
        from structured_article_access import fetch_structured
        return fetch_structured(candidate,record)
    url=candidate['url']
    if not safe_url(url): raise ValueError('host_requires_review')
    if not robots_allowed(url): raise ValueError('robots_disallow_or_unavailable')
    identity,target,provenance=candidate_identity(candidate,record)
    raw,final,kind=request(url)
    version=candidate.get('version','unspecified')
    def finish(document):
        document.coverage.update(provenance)
        document.coverage.setdefault('document_title',identity.get('title',''))
        document.coverage.setdefault('record_doi',doi(record.get('doi')))
        document.coverage.setdefault('source_doi',doi(candidate.get('doi')))
        document.coverage['retrieval_provider']=candidate.get('provider','explicit_source')
        document.coverage['reported_license']=candidate.get('license')
        document.coverage['redistribution_granted']=False
        return document
    if raw.startswith(b'%PDF'):
        return finish(document_from_pdf(raw,identity,final,version,target))
    if 'html' not in kind: raise ValueError('unsupported_content_type')
    page=raw.decode('utf-8','replace')
    if BLOCKED.search(page[:18000]): raise ValueError('access_challenge_not_article')
    partial_pdf=None
    for pdf in publisher_pdf_links(page,final,identity,target):
        if robots_allowed(pdf):
            try:
                body,pdfurl,_=request(pdf)
                document=document_from_pdf(body,identity,pdfurl,version,target)
                if document.coverage.get('evidence_status')=='full_document_retrieved':
                    return finish(document)
                if partial_pdf is None or sum(len(u['text']) for u in document.units)>sum(len(u['text']) for u in partial_pdf.units):
                    partial_pdf=document
            except Exception:
                pass
    try:
        html=document_from_html(raw,identity,final,version,target)
    except Exception:
        if partial_pdf is not None: return finish(partial_pdf)
        raise
    if partial_pdf is not None and sum(len(u['text']) for u in partial_pdf.units)>sum(len(u['text']) for u in html.units):
        return finish(partial_pdf)
    return finish(html)


def candidate(url,provider,identifier,version='unspecified',license_value=None):
    return {'url':url,'provider':provider,'doi':identifier,'version':version,
            'license':license_value,'redistribution_granted':False}


def unpaywall_candidates(identifier,get=json_request):
    # Contact information must be deliberately configured; never transmit an
    # author's or account holder's address merely because it appears in code.
    email=os.getenv('UNPAYWALL_EMAIL','').strip()
    if not email: raise ValueError('contact_not_configured')
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


def openaire_candidates(identifier,get=json_request):
    from openaire_locations import openaire_candidates as locate
    return locate(identifier,get=get)


def default_providers():
    from structured_article_access import europe_pmc_candidates, openalex_candidates
    return [('Europe PMC XML',europe_pmc_candidates),('OpenAlex XML',openalex_candidates),('OpenAIRE',openaire_candidates),('Unpaywall',unpaywall_candidates),
            ('CORE',core_candidates),('Semantic Scholar',semantic_candidates)]


def registry_candidates(record):
    """Read a small curated source register without modifying the article index."""
    if not SOURCE_HINTS.exists(): return []
    if SOURCE_HINTS.stat().st_size>1_000_000: raise ValueError('source_hint_registry_too_large')
    data=json.loads(SOURCE_HINTS.read_text(encoding='utf-8'))
    identifier=doi(record.get('doi'))
    rows=[]
    for item in data.get('records',[]):
        matches=(identifier and doi(item.get('doi'))==identifier) or (
            not identifier and record.get('url') and item.get('url')==record['url'])
        if matches: rows.extend(item.get('fulltext_candidates') or [])
    return rows


def known_candidates(record):
    """Verified input sources and known article URLs precede locator requests."""
    identifier=doi(record.get('doi'))
    rows=list(record.get('fulltext_candidates') or [])+registry_candidates(record)
    existing=(record.get('analysis') or {}).get('fulltext_url')
    for url,provider in ((existing,'existing_source'),
                         (record.get('open_access_url'),'known_open_access_source'),
                         (record.get('url'),'original_article')):
        if url: rows.append(candidate(url,provider,identifier))
    if arxiv_identifier(identifier):
        rows.append(candidate('https://arxiv.org/abs/'+arxiv_identifier(identifier),
                              'arXiv_identifier',identifier))
    options=[]; seen=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('url'),str): continue
        option=candidate(row['url'],str(row.get('provider') or 'explicit_source'),
                         doi(row.get('doi') or identifier),row.get('version') or 'unspecified',
                         row.get('license'))
        for key in ('title','related_doi','identity_verification_url','structured_format'):
            if row.get(key): option[key]=row[key]
        arxiv=arxiv_identifier(option['url'])
        additions=[]
        if arxiv:
            if option['version']=='unspecified':
                version=re.search(r'v\d+$',arxiv)
                option['version']='arxiv_preprint_'+(version.group() if version else 'unversioned_url')
            additions.append({**option,'url':'https://arxiv.org/pdf/'+arxiv})
        # A DOI resolver is bibliographic routing, not an article host. Let
        # identifier locators supply article locations instead of following
        # arbitrary redirects from doi.org.
        try: host=urlsplit(option['url']).hostname
        except ValueError: host=''
        if host not in ('doi.org','dx.doi.org'):
            additions.append(option)
        for item in additions:
            if item['url'] not in seen:
                seen.add(item['url']); options.append(item)
    return options


def failure_diagnostic(exc,article=False):
    """Classify failures without putting exception URLs or credentials in logs."""
    result={'retryable':False}
    if isinstance(exc,HTTPError):
        result['status']=('article_http_' if article else 'http_')+str(exc.code)
        result['retryable']=exc.code in (408,425,429) or 500<=exc.code<600
        if result['retryable']:
            retry=(exc.headers or {}).get('Retry-After','')
            seconds=int(retry) if str(retry).isdigit() else 3600
            result['retry_after_seconds']=max(1,min(seconds,604800))
    else:
        reason=str(exc)
        result['status']=(reason if isinstance(exc,ValueError) and
                          re.fullmatch(r'[a-z][a-z0-9_]{0,99}',reason) else type(exc).__name__)
        result['retryable']=isinstance(exc,(TimeoutError,URLError,ConnectionError))
        if result['retryable']: result['retry_after_seconds']=3600
    return result


def provider_candidates(name,provider,identifier):
    try:
        found=provider(identifier)
        if not isinstance(found,list) or any(not isinstance(row,dict) or
                not isinstance(row.get('url'),str) for row in found):
            raise ValueError('locator_response_invalid')
        # Locator payloads often lead with doi.org or an unapproved mirror.
        # Spend the bounded document budget on trusted PDF locations first.
        def priority(option):
            url=option['url']
            try: path=urlsplit(url).path.lower()
            except ValueError: path=''
            return (not safe_url(url),not (path.endswith('.pdf') or '/pdf/' in path or '/download/' in path))
        found=sorted(found,key=priority)
        return found,{'stage':'discovery','provider':name,
                      'status':'candidates' if found else 'no_exact_match',
                      'candidates':len(found),'retryable':False}
    except Exception as exc:
        return [],{'stage':'discovery','provider':name,**failure_diagnostic(exc)}


def discover(record,providers=None):
    identifier=doi(record.get('doi'))
    rows=known_candidates(record); diagnostics=[]
    if DOI.fullmatch(identifier):
        for name,provider in (default_providers() if providers is None else providers):
            found,result=provider_candidates(name,provider,identifier)
            rows.extend(found); diagnostics.append(result)
            time.sleep(.25)
    seen=set(); unique=[]
    for row in rows:
        if row.get('url') and row['url'] not in seen:
            seen.add(row['url']); unique.append(row)
    return unique,diagnostics


def retrieve(record,max_candidates=8,providers=None):
    """Try known sources first; retain partial text while seeking a whole PDF.

    Returns a Document (in memory only) and a per-provider/per-source ledger.
    An empty providers list explicitly disables API discovery. A locator miss,
    an authentication failure and a temporary outage remain separate outcomes.
    """
    diagnostics=[]; seen=set(); attempted=0; partial=None
    budget=max(0,min(32,int(max_candidates)))
    def attempt(options):
        nonlocal attempted,partial
        for option in options:
            url=option.get('url')
            if not url or url in seen: continue
            if attempted>=budget: break
            seen.add(url); attempted+=1
            result={'stage':'article','provider':option.get('provider','explicit_source'),
                    'url':diagnostic_url(url)}
            try:
                doc=fetch_candidate(option,record)
                complete=doc.coverage.get('evidence_status')=='full_document_retrieved'
                diagnostics.append({**result,'status':'full_document_retrieved' if complete else 'partial_full_text',
                                    'final_url':diagnostic_url(doc.url),'retryable':False})
                if complete: return doc
                # A mostly scanned PDF must not displace a richer HTML body.
                # Neither partial source is promoted to complete by this rank.
                score=lambda item: sum(len(u['text']) for u in item.units)
                if partial is None or score(doc)>score(partial): partial=doc
            except Exception as exc:
                diagnostics.append({**result,**failure_diagnostic(exc,article=True)})
        return None
    full=attempt(known_candidates(record))
    if full is not None: return full,diagnostics
    identifier=doi(record.get('doi'))
    if DOI.fullmatch(identifier) and attempted<budget:
        for name,provider in (default_providers() if providers is None else providers):
            found,result=provider_candidates(name,provider,identifier)
            diagnostics.append(result)
            full=attempt(found)
            if full is not None: return full,diagnostics
            if attempted>=budget: break
            time.sleep(.25)
    if attempted>=budget:
        diagnostics.append({'stage':'retrieval','status':'candidate_budget_exhausted',
                            'candidates_attempted':attempted,'retryable':False})
    return partial,diagnostics

