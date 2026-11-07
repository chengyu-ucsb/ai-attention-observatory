"""Bounded official arXiv v1 publication-day verification, not paper extraction.

Only known arXiv identifiers are queried. No broad search, login, summary or
full text is requested or persisted. A current title that differs from the v1
title is held for review rather than inferred to identify the same version.
"""
from __future__ import annotations

import html
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collection_window import publication_date

NS = {'a': 'http://www.w3.org/2005/Atom'}
IDENTIFIER = r'\d{4}\.\d{4,5}'


def identifier_for(record):
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', str(record.get('doi') or '').strip(), flags=re.I)
    match = re.fullmatch(r'10\.48550/arxiv\.(' + IDENTIFIER + r')(?:v\d+)?', doi, re.I)
    if match:
        return match[1]
    # Do not apply arXiv metadata to a non-arXiv journal DOI.
    if doi:
        return None
    match = re.fullmatch(r'https?://(?:www\.)?arxiv\.org/(?:abs|html)/(' + IDENTIFIER + r')(?:v\d+)?/?', str(record.get('url') or ''), re.I)
    return match[1] if match else None


def normalized_title(value):
    return ' '.join(re.findall(r'\w+', html.unescape(str(value)).casefold()))


def fetch_atom(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'AttentionAIObservatory/1.1 (public metadata research)',
                                              'Accept': 'application/atom+xml'})
    with urllib.request.urlopen(req, timeout=25) as response:
        content = response.read(2_000_001)
    if len(content) > 2_000_000:
        raise ValueError('arXiv metadata response exceeds limit')
    return content


class ArxivPublicationVerifier:
    """Cache per-identifier metadata; at most 20 serial requests, >=3 s apart."""
    def __init__(self, fetch=fetch_atom, *, limit=20, sleep=time.sleep):
        self.fetch = fetch
        self.limit = max(0, limit)
        self.sleep = sleep
        self.cache = {}
        self.deferred = set()
        self.paused = False
        self.audit = {'provider': 'arXiv', 'purpose': 'v1 original publication date',
                      'request_limit': self.limit, 'minimum_interval_seconds': 3,
                      'requests': 0, 'verified': 0, 'failures': 0, 'deferred': 0,
                      'status': 'complete'}

    def verify(self, record):
        identifier = identifier_for(record)
        if not identifier:
            return '', {'status': 'unresolved', 'reason': 'Not a recognized arXiv identifier'}
        versioned = identifier + 'v1'
        url = 'https://export.arxiv.org/api/query?' + urllib.parse.urlencode({'id_list': versioned})
        provenance = {'source': 'Official arXiv Atom metadata', 'basis': 'arxiv_first_submitted',
                      'field': 'published', 'requested_id': versioned, 'source_url': url,
                      'version_url': 'https://arxiv.org/abs/' + versioned}
        if identifier not in self.cache:
            if self.paused or self.audit['requests'] >= self.limit:
                self.deferred.add(identifier)
                self.audit.update(deferred=len(self.deferred), status='partial')
                return '', dict(provenance, status='unresolved', reason='arXiv verification budget or provider pause')
            if self.audit['requests']:
                self.sleep(3)
            self.audit['requests'] += 1
            try:
                root = ET.fromstring(self.fetch(url))
                entries = root.findall('a:entry', NS)
                if len(entries) != 1:
                    raise ValueError('Expected exactly one arXiv entry')
                entry = entries[0]
                source_id = entry.findtext('a:id', '', NS).strip()
                if not re.fullmatch(r'https?://arxiv\.org/abs/' + re.escape(versioned), source_id):
                    raise ValueError('arXiv first-version identifier mismatch')
                raw_date = entry.findtext('a:published', '', NS).strip()
                day = publication_date(raw_date)
                if day is None:
                    raise ValueError('arXiv original published date is absent or imprecise')
                title = ' '.join(entry.findtext('a:title', '', NS).split())
                if not title:
                    raise ValueError('arXiv first-version title is absent')
                self.cache[identifier] = {'title': title, 'published': day.isoformat(), 'raw': raw_date, 'id': source_id}
            except Exception as exc:
                reason = 'HTTP ' + str(exc.code) if hasattr(exc, 'code') else type(exc).__name__ + ': ' + str(exc)[:160]
                self.cache[identifier] = {'error': reason}
                self.audit['failures'] += 1
                self.audit['status'] = 'partial'
                if getattr(exc, 'code', None) in (403, 429):
                    self.paused = True
        metadata = self.cache[identifier]
        if metadata.get('error'):
            return '', dict(provenance, status='unresolved', reason=metadata['error'], verification_error=True)
        if normalized_title(record.get('title', '')) != normalized_title(metadata['title']):
            self.audit['status'] = 'partial'
            return '', dict(provenance, status='conflict', reason='Candidate title differs from arXiv v1 title')
        self.audit['verified'] += 1
        return metadata['published'], dict(provenance, status='day_known', value=metadata['published'],
                                           raw=metadata['raw'], source_id=metadata['id'])
