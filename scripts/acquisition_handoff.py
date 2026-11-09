"""Reuse validated acquisition locations, never cached prose or review approval.

A checkpoint receipt is a retrieval hint. The normal reader must fetch again
through its existing host/robots/rights/identity guards; source hashes and version
must still agree before the receipt can be attached to the new reading.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

import full_document_access as access
import source_access_controls as controls

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'data/weekly-source-acquisition.json'
WEEKLY = ROOT / 'data/weekly.json'
MAX_STATE_BYTES = 32_000_000
PROVIDER = 'validated_acquisition_checkpoint'

def note(status, **fields):
    return {'stage': 'handoff', 'provider': PROVIDER, 'status': status,
            'retryable': False, **fields}

def read_metadata(path):
    path = Path(path)
    if path.stat().st_size > MAX_STATE_BYTES:
        raise ValueError('acquisition_metadata_too_large')
    return json.loads(path.read_text(encoding='utf-8'))

def date_evidence(record):
    # An operational recheck timestamp is not publication identity. Keep the
    # original source, date, basis, returned IDs and version URL exactly bound.
    return {key: value for key, value in (record.get('publication_date_provenance') or {}).items()
            if key != 'checked_at'}

def same_article(left, right, queue):
    """A DOI alone cannot bind a receipt to changed title/date/version evidence."""
    return (queue.record_key(left) == queue.record_key(right)
            and left.get('kind') == right.get('kind')
            and access.doi(left.get('doi')) == access.doi(right.get('doi'))
            and access.normal(left.get('title', '')) == access.normal(right.get('title', ''))
            and left.get('url') == right.get('url')
            and queue.publication_date(left.get('published')) == queue.publication_date(right.get('published'))
            and date_evidence(left) == date_evidence(right))

def matching_row(record, payload, state, queue):
    window = state['publication_window']
    actual = payload.get('run', {}).get('publication_window', {})
    if any(actual.get(key) != window[key] for key in ('from', 'to', 'timezone')):
        return None
    key = queue.record_key(record)
    row = state['records'].get(key)
    if row is None or queue.eligibility(record, window):
        return None
    inputs = [item for item in payload.get('items', [])
              if isinstance(item, dict) and queue.record_key(item) == key]
    if not inputs or any(not same_article(record, item, queue) or queue.eligibility(item, window)
                         for item in inputs):
        return None
    # Recreate the queue's exact duplicate-aware input fingerprint and route plan.
    fingerprints = set(); routes = []
    for item in inputs:
        candidates, _, fingerprint = queue.prepare(item, window, row['plan']['known_sources_only'])
        fingerprints.add(fingerprint); routes.extend(candidates)
    ordered = sorted(fingerprints)
    fingerprint = ordered[0] if len(ordered) == 1 else queue.digest(ordered)
    if len(inputs) > 1:
        unique = {queue.digest(route): route for route in routes}
        routes = ([unique[identity] for identity in sorted(unique)]
                  if len(fingerprints) > 1 else list(unique.values()))
    if (fingerprint != row['fingerprint']
            or row['plan']['known_routes'] != [queue.digest(route) for route in routes]):
        return None
    return row

def retrieval_controls(state, now, queue, shared_controls=None):
    """A receipt cannot erase controls recorded in another queue or its history."""
    shared = controls.merge_controls(
        controls.controls_from_state(state) if state is not None else controls.empty_controls(),
        shared_controls if shared_controls is not None else controls.empty_controls())
    effective = controls.stage_controls(shared, now)
    return (effective['host_backoff'], set(effective['paused_providers']),
            set(effective['denied_hosts']), set(effective['blocked_urls']))



def available_providers(paused, blocked):
    providers = []
    for name, provider in access.default_providers():
        if name in paused:
            continue
        def filtered(identifier, provider=provider):
            return [route for route in provider(identifier)
                    if access.diagnostic_url(route.get('url', '')) not in blocked]
        providers.append((name, filtered))
    return providers

def guarded_retrieval(record, retriever, denied, blocked, **options):
    with controls.retrieval_scope(denied, blocked):
        return retriever(record, **options)


def ordinary_retrieval(record, retriever, queue, state=None, now=None, shared_controls=None):
    """Missing receipts do not erase first-version or existing access controls."""
    options = {}; denied = set(); blocked = set()
    if state is not None or shared_controls is not None:
        backoff, paused, denied, blocked = retrieval_controls(state, queue.utc_now(now), queue, shared_controls)
        if backoff:
            options['host_backoff'] = backoff
        if paused or blocked:
            options['providers'] = available_providers(paused, blocked)
        if blocked:
            options['known_sources'] = [route for route in access.known_candidates(record)
                if access.diagnostic_url(route['url']) not in blocked]
    pinned = queue.verified_arxiv_v1(record)
    if pinned is None:
        return guarded_retrieval(record, retriever, denied, blocked, **options)
    if not pinned:
        return None, [note('acquisition_source_version_unverified')]
    known = [queue.pin_arxiv_route(route, record) for route in access.known_candidates(record)
             if queue.is_pinned_arxiv_url(route['url'], pinned)]
    if not known:
        known = [access.candidate('https://arxiv.org/pdf/' + pinned, 'arXiv_identifier',
                                  access.doi(record.get('doi')), 'arxiv_preprint_v1')]
    options.update(known_sources=known, providers=[])
    document, diagnostics = guarded_retrieval(record, retriever, denied, blocked, **options)
    if document is not None and (not queue.is_pinned_arxiv_url(document.url, pinned)
                                or document.version != 'arxiv_preprint_v1'):
        return None, list(diagnostics) + [note('acquisition_source_version_changed')]
    return document, diagnostics

def _retrieve_for_reading(record, *, state_path=STATE, weekly_path=WEEKLY,
                         state=None, payload=None, now=None, retriever=None,
                         shared_controls=None, controls_data_dir=None):
    """Drop-in reader callback; returns the same (Document, diagnostics) pair.

    Missing or unrelated metadata uses ordinary retrieval. Corrupt checkpoint
    metadata is held without network I/O. Matching receipts are checked afresh;
    no article text is loaded from or written to acquisition state.
    """
    retriever = retriever or access.retrieve
    # Lazy import avoids collect_weekly_sources -> comprehensive_readings ->
    # this adapter -> collect_weekly_sources during module initialization.
    import collect_weekly_sources as queue
    try:
        if shared_controls is None:
            shared_controls = controls.load_shared_controls(
                controls_data_dir if controls_data_dir is not None else controls.data_root_for_state(state_path), now=now)
        else:
            controls.validate_controls(shared_controls)
    except (ValueError, TypeError, OSError):
        return None, [note('acquisition_metadata_invalid')]
    try:
        state = read_metadata(state_path) if state is None else state
    except FileNotFoundError:
        return ordinary_retrieval(record, retriever, queue, now=now, shared_controls=shared_controls)
    except (ValueError, TypeError, OSError):
        return None, [note('acquisition_metadata_invalid')]
    try:
        queue.validate_state(state)
    except (ValueError, TypeError, KeyError):
        return None, [note('acquisition_metadata_invalid')]
    try:
        payload = read_metadata(weekly_path) if payload is None else payload
    except FileNotFoundError:
        return ordinary_retrieval(record, retriever, queue, state, now, shared_controls)
    except (ValueError, TypeError, OSError):
        return None, [note('acquisition_metadata_invalid')]
    try:
        if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
            raise ValueError('acquisition_metadata_invalid')
        row = matching_row(record, payload, state, queue)
    except (ValueError, TypeError, KeyError, AttributeError):
        return None, [note('acquisition_metadata_invalid')]
    if row is None:
        return ordinary_retrieval(record, retriever, queue, state, now, shared_controls)
    moment = queue.utc_now(now or datetime.now(timezone.utc))
    backoff, paused, denied, blocked = retrieval_controls(state, moment, queue, shared_controls)
    receipt = row.get('document')
    pinned = queue.verified_arxiv_v1(record)
    known = access.known_candidates(record)
    hint = None
    if receipt:
        hint = access.candidate(receipt['source_url'], PROVIDER, access.doi(record.get('doi')),
                                receipt['document_version'])
        if receipt.get('document_format'):
            hint['structured_format'] = receipt['document_format']
        # Date/version and anonymous URL restrictions are rechecked, not inherited
        # as permission from a previously successful fetch.
        if not queue.route_permitted(hint, record, state['publication_window']):
            return None, [note('acquisition_receipt_route_changed')]
        if hint['url'] in blocked or urlsplit(hint['url']).hostname in denied:
            return None, [note('acquisition_source_access_blocked', url=hint['url'])]
        known = [hint] + [route for route in known if route['url'] != hint['url']]
    known = [route for route in known if access.diagnostic_url(route['url']) not in blocked]
    if pinned:
        # Never substitute today's unversioned alias for the acquired first version.
        known = [queue.pin_arxiv_route(route, record) for route in known
                 if queue.is_pinned_arxiv_url(route['url'], pinned)]
        if not known:
            known = [access.candidate('https://arxiv.org/pdf/' + pinned, 'arXiv_identifier',
                                      access.doi(record.get('doi')), 'arxiv_preprint_v1')]
        providers = []
    else:
        providers = available_providers(paused, blocked)
    document, diagnostics = guarded_retrieval(record, retriever, denied, blocked,
        known_sources=known, providers=providers, host_backoff=backoff)
    diagnostics = list(diagnostics)
    if document is None:
        return None, diagnostics
    if pinned and (not queue.is_pinned_arxiv_url(document.url, pinned)
                   or document.version != 'arxiv_preprint_v1'):
        return None, diagnostics + [note('acquisition_source_version_changed')]
    if not receipt:
        return document, diagnostics
    source = access.diagnostic_url(document.url)
    if source != receipt['source_url']:
        if document.coverage.get('retrieval_provider') == PROVIDER or pinned:
            return None, diagnostics + [note('acquisition_receipt_route_changed')]
        # Independently retrieved alternatives retain their own version, hashes,
        # coverage and license. Do not transfer the checkpoint's receipt to them.
        return document, diagnostics + [note('independent_source_after_acquisition_hint')]
    manifest = document.manifest()
    fields = ('document_version', 'source_sha256', 'source_bytes_sha256',
              'source_byte_count', 'evidence_status', 'html_extraction_version')
    if any(key in receipt and manifest.get(key) != receipt[key] for key in fields):
        return None, diagnostics + [note('acquisition_receipt_content_changed', url=source)]
    document.coverage.update(acquisition_state_sha256=state['state_sha256'],
                             acquisition_input_fingerprint=row['fingerprint'],
                             acquisition_receipt_status='revalidated_not_reviewed')
    return document, diagnostics + [note('acquisition_receipt_revalidated', url=source)]


HANDOFF_HOLDS = {
    'acquisition_metadata_invalid', 'acquisition_source_version_unverified',
    'acquisition_source_version_changed', 'acquisition_receipt_route_changed',
    'acquisition_source_access_blocked', 'acquisition_receipt_content_changed',
}

def retrieve_for_reading(record, *, diagnostic_observer=None, **options):
    """Reader callback; explicit evidence holds cannot use stale indexed sections.

    The existing comprehensive reader catches ValueError as a retrieval-stage
    failure and retains prior analysis. Ordinary source misses still return the
    usual pair, allowing its separately labeled partial-section fallback.
    """
    document, diagnostics = _retrieve_for_reading(record, **options)
    # Save newly observed restrictions before a source/version hold raises.
    # Callers may persist metadata here; no approval or source prose is passed.
    if diagnostic_observer is not None:
        diagnostic_observer(diagnostics)
    for entry in diagnostics:
        if entry.get('stage') == 'handoff' and entry.get('status') in HANDOFF_HOLDS:
            raise ValueError(entry['status'])
    return document, diagnostics
