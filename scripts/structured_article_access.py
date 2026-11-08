"""Official article XML routes for the transient whole-source reader.

No source prose is persisted. XML coverage means all text in the supplied XML,
not PDF/layout equivalence or independent verification of a generated summary.
"""
from __future__ import annotations
import gzip
import io
import os
import re
from urllib.parse import quote, urlencode, urlsplit
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 20_000_000
EPMC = 'https://www.ebi.ac.uk/europepmc/webservices/rest/'
XML_HOSTS = {'www.ebi.ac.uk', 'content.openalex.org'}


def local(tag):
    return tag.rsplit('}', 1)[-1].lower()


def content(element):
    return ' '.join(' '.join(element.itertext()).split())


def decoded_xml(raw):
    if raw[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(MAX_XML_BYTES + 1)
    if len(raw) > MAX_XML_BYTES:
        raise ValueError('structured_document_too_large')
    # ElementTree never fetches external DTDs. Reject entity declarations and
    # internal subsets explicitly, rather than accepting entity amplification.
    # Parse only UTF-8/ASCII. Searching encoded bytes alone misses a UTF-16
    # internal DTD whose letters are separated by NUL bytes.
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('xml_encoding_unsupported') from None
    if '\x00' in text:
        raise ValueError('xml_encoding_unsupported')
    encoding = re.search(r'<\?xml[^>]*encoding=[\"\']([^\"\']+)', text[:200], re.I)
    if encoding and encoding.group(1).lower() not in ('utf-8', 'utf8', 'ascii', 'us-ascii'):
        raise ValueError('xml_encoding_unsupported')
    if re.search(r'<!ENTITY\b|<!DOCTYPE[^>]*\[', text, re.I):
        raise ValueError('xml_entities_disallowed')
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        raise ValueError('article_xml_invalid') from None


def xml_units(root):
    """Emit disjoint blocks, including introductions, captions and references."""
    containers = {'article', 'front', 'article-meta', 'body', 'back', 'sec',
                  'tei', 'teiheader', 'text', 'div', 'group'}
    units = []
    def add(text, location):
        text = ' '.join((text or '').split())
        if text:
            units.append({'location': location, 'text': text})
    def walk(node, path):
        if local(node.tag) not in containers:
            add(content(node), path)
            return
        add(node.text, path + '/text')
        counts = {}
        for child in node:
            tag = local(child.tag)
            counts[tag] = counts.get(tag, 0) + 1
            target = path + '/' + tag + ':' + str(counts[tag])
            walk(child, target)
            add(child.tail, target + '/tail')
    walk(root, 'xml:' + local(root.tag))
    return units


def document_from_xml(raw, record, url, *, format, version='unspecified'):
    from full_document_access import Document, doi, normal
    from enrich_pmc_oai import reusable_jats_license
    root = decoded_xml(raw)
    if format == 'jats':
        articles = [e for e in root.iter() if local(e.tag) == 'article']
        if len(articles) != 1:
            raise ValueError('article_xml_ambiguous')
        article = articles[0]
        front = next((e for e in article if local(e.tag) == 'front'), None)
        meta = next((e for e in front if local(e.tag) == 'article-meta'), None) if front is not None else None
        body = next((e for e in article if local(e.tag) == 'body'), None)
        if meta is None or body is None:
            raise ValueError('article_xml_body_missing')
        ids = {doi(content(e)) for e in meta if local(e.tag) == 'article-id' and e.get('pub-id-type') == 'doi'}
        titles = [content(e) for e in meta.iter() if local(e.tag) == 'article-title']
        permissions = [e for e in meta if local(e.tag) == 'permissions']
        licenses = [content(e) + ' ' + ' '.join(e.attrib.values())
                    for p in permissions for e in p.iter() if local(e.tag) == 'license']
        # The legacy helper accepts CC BY substrings. First exclude restricted
        # SPDX/plain-text variants even when no canonical license URI exists.
        compact = [re.sub(r'[^a-z0-9]+', '', value.lower()) for value in licenses]
        restricted = any(any(marker in value for marker in
                         ('ccbync', 'ccbynd', 'licensesbync', 'licensesbynd',
                          'noncommercial', 'noderivatives', 'allrightsreserved')) for value in compact)
        if restricted or not reusable_jats_license(licenses):
            raise ValueError('structured_reuse_license_unverified')
        rights = 'article_metadata_permissive_license'
    elif format == 'tei':
        articles = [e for e in root.iter() if local(e.tag) == 'tei']
        if len(articles) != 1:
            raise ValueError('article_xml_ambiguous')
        article = articles[0]
        header = next((e for e in article if local(e.tag) == 'teiheader'), None)
        text = next((e for e in article if local(e.tag) == 'text'), None)
        body = next((e for e in text if local(e.tag) == 'body'), None) if text is not None else None
        # Older OpenAlex TEI uses text/div without a body wrapper.
        if body is None and text is not None and any(local(e.tag) == 'div' for e in text):
            body = text
        if header is None or body is None:
            raise ValueError('article_xml_body_missing')
        ids = {doi(content(e)) for e in header.iter() if local(e.tag) == 'idno' and e.get('type', '').lower() == 'doi'}
        titles = [content(e) for e in header.iter() if local(e.tag) == 'title' and e.get('level') in (None, 'a')]
        rights = 'provider_reported_oa_transient_reading_only'
    else:
        raise ValueError('unsupported_article_xml_format')
    expected = doi(record.get('doi'))
    title = normal(record.get('title', ''))
    if not expected or expected not in ids or len(title) < 25 or title not in {normal(x) for x in titles}:
        raise ValueError('structured_article_identity_unverified')
    units = xml_units(article)
    if len(content(body)) < 1600 or len(units) < 3:
        raise ValueError('insufficient_structured_article_body')
    return Document(units, url, version, {
        'evidence_status': 'full_document_retrieved',
        'document_format': format,
        'structured_text_coverage': 'all_text_in_supplied_article_xml',
        'source_document_equivalence': 'not_verified',
        'semantic_completeness': 'not_verified',
        'layout_fidelity': 'not_verified',
        'rights_basis': rights,
        'redistribution_granted': False,
    })


def europe_pmc_candidates(identifier, get=None):
    from full_document_access import json_request, doi, candidate
    get = get or json_request
    payload = get(EPMC + 'search?' + urlencode({'query': 'DOI:"' + identifier + '"', 'format': 'json', 'pageSize': 10}))
    rows = []
    for work in (payload.get('resultList') or {}).get('result') or []:
        pmcid = work.get('pmcid', '')
        if doi(work.get('doi')) == identifier and work.get('isOpenAccess') == 'Y' and re.fullmatch(r'PMC\d+', pmcid):
            rows.append({**candidate(EPMC + pmcid + '/fullTextXML', 'Europe PMC full-text API', identifier,
                                    'repository_article_xml'), 'structured_format': 'jats'})
    return rows


def openalex_candidates(identifier, get=None):
    from full_document_access import json_request, doi, candidate
    get = get or json_request
    key = os.getenv('OPENALEX_API_KEY', '').strip()
    if not key:
        raise ValueError('openalex_key_not_configured')
    # Credentials are used only on the two official OpenAlex endpoints. They
    # never become candidate URLs, manifests, source hints or diagnostics.
    work = get('https://api.openalex.org/works/' + quote('https://doi.org/' + identifier, safe='') + '?' + urlencode({'api_key': key}))
    if doi(work.get('doi')) != identifier:
        raise ValueError('locator_identity_mismatch')
    ident = str(work.get('id', '')).rsplit('/', 1)[-1]
    url = (work.get('content_urls') or {}).get('grobid_xml') or ''
    if not re.fullmatch(r'W\d+', ident):
        return []
    rows = []
    if ((work.get('open_access') or {}).get('is_oa') and
            url == 'https://content.openalex.org/works/' + ident + '.grobid-xml'):
        rows.append({**candidate(url, 'OpenAlex content API', identifier, 'provider_cached_article_xml'),
                     'structured_format': 'tei'})
    # Content XML is absent for many papers that do have repository versions.
    # Reuse this exact-DOI response rather than paying for another lookup.
    from full_document_access import anonymous_source_url
    seen = {row['url'] for row in rows}
    locations = [work.get('best_oa_location')] + (work.get('locations') or [])
    for location in locations[:40]:
        if not isinstance(location, dict) or location.get('is_oa') is not True:
            continue
        version = location.get('version') or 'unspecified'
        for key in ('pdf_url', 'landing_page_url'):
            target = location.get(key)
            if not isinstance(target, str) or not anonymous_source_url(target) or target in seen:
                continue
            seen.add(target)
            rows.append({**candidate(target, 'OpenAlex OA location', identifier,
                                     version, location.get('license')),
                         'discovery_basis': 'exact_doi_open_access_location'})
    return rows


def fetch_structured(candidate, record):
    from full_document_access import request, diagnostic_url, doi
    url = candidate['url']
    fmt = candidate.get('structured_format')
    p = urlsplit(url)
    if p.query or p.fragment or p.username or p.password or p.port not in (None, 443) or p.scheme != 'https':
        raise ValueError('structured_endpoint_invalid')
    if fmt == 'jats' and p.hostname == 'www.ebi.ac.uk' and re.fullmatch(r'/europepmc/webservices/rest/PMC\d+/fullTextXML', p.path):
        target = url
    elif fmt == 'tei' and p.hostname == 'content.openalex.org' and re.fullmatch(r'/works/W\d+\.grobid-xml', p.path):
        key = os.getenv('OPENALEX_API_KEY', '').strip()
        if not key:
            raise ValueError('openalex_key_not_configured')
        target = url + '?' + urlencode({'api_key': key})
    else:
        raise ValueError('structured_endpoint_invalid')
    # These sanctioned API endpoints are not article-page crawls. Existing
    # HTTP/redirect/size guards still apply; authentication failures are final.
    raw, final, kind = request(target, XML_HOSTS, MAX_XML_BYTES)
    document = document_from_xml(raw, record, diagnostic_url(final), format=fmt,
                                 version=candidate.get('version', 'unspecified'))
    document.coverage.update(record_doi=doi(record.get('doi')), source_doi=doi(record.get('doi')),
                             retrieval_provider=candidate.get('provider', 'official_article_xml'),
                             reported_license=candidate.get('license'), document_title=record.get('title', ''))
    return document
