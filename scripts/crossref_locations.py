"""Discover publisher-deposited locations, without inferring access or rights.

Crossref metadata is not article text. Only an exact DOI response is accepted;
the whole-document reader must independently verify title/identity, robots,
access, and completeness. No search-result title match substitutes for a DOI.
"""
from __future__ import annotations

from urllib.parse import quote


def crossref_candidates(identifier, get=None):
    from full_document_access import anonymous_source_url, candidate, doi, json_request
    get = get or json_request
    payload = get('https://api.crossref.org/works/' + quote(identifier, safe=''))
    work = payload.get('message') or {}
    if not isinstance(work, dict) or doi(work.get('DOI')) != identifier:
        raise ValueError('locator_identity_mismatch')
    rows, seen = [], set()
    versions = {'vor': 'publishedVersion', 'am': 'acceptedVersion'}
    # A TDM/similarity link is a location only, not permission to mine or reuse.
    # Keep its intended use visible; ordinary access checks still apply.
    for link in (work.get('link') or [])[:20]:
        if not isinstance(link, dict):
            continue
        url = link.get('URL')
        if not isinstance(url, str) or not anonymous_source_url(url) or url in seen:
            continue
        seen.add(url)
        rows.append({**candidate(url, 'Crossref publisher deposit', identifier,
                                 versions.get(link.get('content-version'), 'unspecified')),
                     'discovery_basis': 'publisher_deposited_link',
                     'declared_content_type': str(link.get('content-type') or '')[:100],
                     'declared_link_purpose': str(link.get('intended-application') or '')[:100]})
    resource = work.get('resource') or {}
    primary = (resource.get('primary') or {}) if isinstance(resource, dict) else {}
    url = primary.get('URL') if isinstance(primary, dict) else None
    if isinstance(url, str) and anonymous_source_url(url) and url not in seen:
        rows.append({**candidate(url, 'Crossref publisher landing page', identifier),
                     'discovery_basis': 'publisher_deposited_primary_resource'})
    return rows
