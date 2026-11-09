"""Bounded weekly article acquisition, independent of publication eligibility.

Only metadata crosses the worker boundary or is saved. Text/PDF bytes remain
transient; complete text coverage is not semantic review or reuse permission.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import time
import threading
from urllib.parse import urlsplit, parse_qsl

import full_document_access as access
import source_access_controls as controls
from article_body_parser import EXTRACTION_VERSION as HTML_EXTRACTION_VERSION
from collection_window import date_in_window, previous_week, publication_date, weekly_eligible
from comprehensive_readings import chunk_document, coverage_is_complete
from arxiv_publication import identifier_for as arxiv_record_identifier

ROOT = Path(__file__).resolve().parents[1]
VERSION = 2
# Fail closed at capacity; never evict old evidence or retry an evicted revision.
MAX_HTML_REFRESH_ATTEMPTS = 8
# Reuse only existing anonymous locator functions. Never enable a new account,
# contact-address transmission, key, model, or hosted inference service here.
# Append only: persisted numeric cursors retain their original meaning.
LEGACY_PROVIDERS = ('Europe PMC XML', 'OpenAIRE', 'CORE', 'Semantic Scholar')
PROVIDER_PLAN_VERSION = 2
PROVIDERS = LEGACY_PROVIDERS + ('Crossref publisher locations',)
# Reader-only providers may contribute restrictions, never acquisition stages.
CONTROL_PROVIDERS = PROVIDERS + ('OpenAlex XML and OA locations', 'Unpaywall')
SUCCESS = {'full_document_retrieved', 'partial_full_text'}
BLOCKED = {'article_http_401', 'article_http_403', 'http_401', 'http_403',
           'access_challenge_not_article', 'robots_disallow_or_unavailable',
           'related_version_verification_unavailable', 'host_access_denied_this_run',
           'source_access_denied_this_run', 'provider_access_denied_history'}
CODES = BLOCKED | SUCCESS | {
    'no_exact_match', 'candidates', 'candidate_budget_exhausted',
    'host_requires_review', 'unapproved_host', 'unapproved_redirect',
    'cross_host_redirect_requires_review', 'document_identity_unverified',
    'insufficient_document_text', 'insufficient_article_body', 'not_pdf',
    'document_too_large', 'document_exceeds_page_budget', 'unsupported_content_type',
    'locator_identity_mismatch', 'locator_response_invalid',
    'related_version_parent_mismatch', 'related_version_verification_required',
    'related_version_identity_unverified', 'structured_article_identity_unverified',
    'structured_reuse_license_unverified', 'structured_endpoint_invalid',
    'insufficient_structured_article_body', 'article_xml_body_missing',
    'article_xml_invalid', 'article_xml_ambiguous', 'xml_encoding_unsupported',
    'xml_entities_disallowed', 'structured_document_too_large',
    'TimeoutError', 'URLError', 'ConnectionError', 'HTTPError', 'ValueError',
    'deferred_time_budget', 'interrupted_attempt', 'worker_failed',
    'retrieval_error', 'coverage_gap', 'invalid_document_locations',
    'route_policy_excluded', 'metadata_budget_exhausted', 'rate_limit_pause',
    'credentialed_source_url_disallowed', 'source_version_unverified', 'source_unavailable_page', 'receipt_refresh_changed_again',
}
SAFE_PROVIDERS = set(CONTROL_PROVIDERS) | {
    'explicit_source', 'existing_source', 'known_open_access_source',
    'original_article', 'arXiv_identifier', 'Europe PMC full-text API',
    'OpenAIRE', 'CORE', 'Semantic Scholar', 'source_route',
}
MANIFEST_ENUMS = {
    'evidence_status': SUCCESS,
    'document_format': {'jats', 'tei'},
    'html_completeness': {'not_verified'},
    'structured_text_coverage': {'all_text_in_supplied_article_xml'},
    'source_document_equivalence': {'not_verified'},
    'layout_fidelity': {'not_verified'},
    'rights_basis': {'article_metadata_permissive_license',
                     'provider_reported_oa_transient_reading_only'},
}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode()).hexdigest()


def utc_now(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def code(value):
    return value if isinstance(value, str) and (value in CODES or
        re.fullmatch(r'(?:article_)?http_[1-5]\d\d', value)) else 'retrieval_error'


def token(value, default='unspecified'):
    known = {'unspecified', 'publishedVersion', 'acceptedVersion', 'submittedVersion',
             'repository_article_xml', 'provider_cached_article_xml',
             'working_paper_not_journal_version', 'author_accepted_manuscript',
             'article_in_press', 'published_article'}
    return value if isinstance(value, str) and (value in known or
        re.fullmatch(r'(?:(?:arxiv_)?preprint_)?(?:v\d+|unversioned_url)', value)) else default


def diagnostic(value):
    """Allowlist diagnostics; never persist arbitrary exception prose."""
    row = {'status': code(value.get('status')), 'retryable': value.get('retryable') is True}
    if value.get('stage') in ('article', 'discovery', 'retrieval'):
        row['stage'] = value['stage']
    if value.get('provider'):
        row['provider'] = value['provider'] if value['provider'] in SAFE_PROVIDERS else 'source_route'
    for key in ('url', 'final_url', 'failure_url'):
        if value.get(key):
            row[key] = access.diagnostic_url(value[key])
    for key in ('candidates', 'candidates_attempted', 'retry_after_seconds'):
        if type(value.get(key)) is int:
            row[key] = max(0, min(value[key], 604800))
    return row


# Closed persisted schema. A checksum detects accidental/tampered checkpoints;
# structural validation is still required and is not proof of source truth.
STATE_ERROR = 'invalid_acquisition_state'
SCOPE = 'Selected previous-week records only; not comprehensive web coverage.'
CLOSED_NOTICE = 'Not retried by the current-week stage; a separate historical backlog is required.'
EXCLUSIONS = {'excluded_invalid_record', 'excluded_missing_publication_date',
    'excluded_nonpublication_date', 'excluded_conflicting_publication_date',
    'excluded_outside_publication_window', 'excluded_historical_backfill',
    'excluded_unverified_original_publication_date', 'excluded_unsupported_kind'}
TERMINAL = {'full_document_retrieved_not_reviewed', 'partial_full_text_not_reviewed',
            'access_blocked', 'source_unavailable'}
RETRY = {'rate_limited', 'temporarily_unavailable', 'deferred_time_budget'}
STATUSES = TERMINAL | RETRY | {'pending', 'pending_routes', 'in_progress'}


def require(condition):
    if not condition:
        raise ValueError(STATE_ERROR)


def shape(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value) <= set(required) | set(optional))


def integer(value, maximum=100000000):
    require(type(value) is int and 0 <= value <= maximum)


def hash_value(value):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None)


def timestamp(value):
    require(type(value) is str and len(value) <= 40)
    try:
        require(utc_now(value).isoformat() == value and 'T' in value and value.endswith('+00:00'))
    except (TypeError, ValueError, OverflowError):
        raise ValueError(STATE_ERROR) from None


def saved_url(value, allow_empty=False):
    require(type(value) is str)
    require((allow_empty and value == '') or
            (value.startswith('https://') and access.diagnostic_url(value) == value and len(value) <= 2000))


def saved_window(window):
    shape(window, {'from', 'to', 'timezone'})
    start, end = publication_date(window['from']), publication_date(window['to'])
    require(start is not None and end is not None and window['timezone'] == 'UTC')
    require(window['from'] == start.isoformat() and window['to'] == end.isoformat())
    require(start.weekday() == 0 and end - start == timedelta(days=6))


def validate_diagnostic(row):
    shape(row, {'status', 'retryable'}, {'stage', 'provider', 'url', 'final_url', 'failure_url',
        'candidates', 'candidates_attempted', 'retry_after_seconds'})
    require(type(row['status']) is str and code(row['status']) == row['status'])
    require(type(row['retryable']) is bool)
    if 'stage' in row:
        require(row['stage'] in {'article', 'discovery', 'retrieval'})
    if 'provider' in row:
        require(type(row['provider']) is str and row['provider'] in SAFE_PROVIDERS)
    for key in ('url', 'final_url', 'failure_url'):
        if key in row:
            saved_url(row[key], allow_empty=True)
    for key in ('candidates', 'candidates_attempted', 'retry_after_seconds'):
        if key in row:
            integer(row[key], 604800)
    if row['status'].endswith('http_429'):
        require(row['retryable'])
    if row['status'] in BLOCKED or row['status'] in SUCCESS:
        require(not row['retryable'])


def extraction_version(value):
    require(type(value) is str and len(value) <= 40
            and re.fullmatch(r'article-body-v[1-9][0-9]*', value) is not None)


def is_html_document(meta):
    return (meta.get('html_completeness') == 'not_verified'
            and meta.get('evidence_status') == 'partial_full_text'
            and 'pages_total' not in meta and 'document_format' not in meta)


def validate_document(meta):
    required = {'source_url', 'document_version', 'semantic_completeness', 'review_status',
        'source_text_saved', 'redistribution_granted', 'all_retrieved_text_chunked',
        'chunks_total', 'units', 'chunk_intervals', 'evidence_status',
        'characters_retrieved', 'units_retrieved', 'source_sha256'}
    optional = set(MANIFEST_ENUMS) | {'source_byte_count', 'source_bytes_sha256',
                                    'pages_total', 'pages_processed', 'pages_with_text',
                                    'html_extraction_version'}
    shape(meta, required, optional)
    if 'html_extraction_version' in meta:
        extraction_version(meta['html_extraction_version'])
        require(is_html_document(meta))
    saved_url(meta['source_url'])
    require(token(meta['document_version']) == meta['document_version'])
    require(meta['semantic_completeness'] == 'not_verified' and meta['review_status'] == 'not_reviewed')
    require(meta['source_text_saved'] is False and meta['redistribution_granted'] is False
            and meta['all_retrieved_text_chunked'] is True)
    for key, allowed in MANIFEST_ENUMS.items():
        if key in meta:
            require(type(meta[key]) is str and meta[key] in allowed)
    hash_value(meta['source_sha256'])
    for key in ('characters_retrieved', 'units_retrieved', 'chunks_total'):
        integer(meta[key])
        require(meta[key] > 0)
    require(type(meta['units']) is list and len(meta['units']) == meta['units_retrieved'])
    lengths = {}
    for number, unit in enumerate(meta['units'], 1):
        shape(unit, {'unit', 'characters', 'has_text'})
        integer(unit['unit']); integer(unit['characters'])
        require(unit['unit'] == number and type(unit['has_text']) is bool
                and (not unit['has_text'] or unit['characters'] > 0))
        lengths[number] = unit['characters']
    require(meta['characters_retrieved'] == sum(lengths.values()) + len(lengths) - 1)
    require(type(meta['chunk_intervals']) is list and len(meta['chunk_intervals']) == meta['chunks_total'])
    offsets = dict.fromkeys(lengths, 0)
    for number, chunk in enumerate(meta['chunk_intervals'], 1):
        shape(chunk, {'chunk', 'ranges'})
        require(chunk['chunk'] == f'C{number:04d}' and type(chunk['ranges']) is list and chunk['ranges'])
        for span in chunk['ranges']:
            shape(span, {'unit', 'start', 'end'})
            for key in span:
                integer(span[key])
            unit = span['unit']
            require(unit in lengths and span['start'] == offsets[unit]
                    and span['start'] < span['end'] <= lengths[unit])
            offsets[unit] = span['end']
    require(offsets == lengths)
    if 'source_byte_count' in meta or 'source_bytes_sha256' in meta:
        require({'source_byte_count', 'source_bytes_sha256'} <= set(meta))
        integer(meta['source_byte_count']); hash_value(meta['source_bytes_sha256'])
        require(meta['source_byte_count'] > 0)
    pages = {'pages_total', 'pages_processed', 'pages_with_text'}
    if pages & set(meta):
        require(pages <= set(meta))
        for key in pages:
            integer(meta[key], 300)
        require(meta['pages_total'] >= meta['pages_processed'] == len(lengths)
                and meta['pages_with_text'] == sum(unit['has_text'] for unit in meta['units']))
        if meta['evidence_status'] == 'full_document_retrieved':
            require(meta['pages_total'] == meta['pages_with_text'])
    elif meta['evidence_status'] == 'full_document_retrieved':
        require(meta.get('document_format') in {'jats', 'tei'}
                and meta.get('structured_text_coverage') == 'all_text_in_supplied_article_xml'
                and meta.get('source_document_equivalence') == 'not_verified')
    require(access.safe_url(meta['source_url']) or (meta.get('document_format') == 'jats'
        and re.fullmatch(r'https://www\.ebi\.ac\.uk/europepmc/webservices/rest/PMC\d+/fullTextXML', meta['source_url'])))


def validate_row(row, window):
    shape(row, {'fingerprint', 'kind', 'published', 'source_url', 'status', 'complete',
        'attempts', 'cursor', 'plan', 'tried_sources', 'excluded_related_or_outside_window_routes',
        'diagnostics', 'source_text_saved'},
        {'document', 'document_evidence', 'last_outcome', 'next_retry_at', 'last_attempt_at',
         'html_refresh', 'html_refresh_attempts', 'previous_documents', 'provider_fallbacks', 'provider_attempted_at',
         'source_refreshes', 'source_refresh_hold'})
    hash_value(row['fingerprint']); saved_url(row['source_url'], allow_empty=True)
    require(row['kind'] in {'scholarly', 'nonacademic'} and type(row['complete']) is bool)
    require(type(row['status']) is str and row['status'] in STATUSES and row['source_text_saved'] is False)
    require(publication_date(row['published']) is not None
            and publication_date(row['published']).isoformat() == row['published']
            and date_in_window(row['published'], window['from'], window['to']))
    integer(row['attempts']); integer(row['excluded_related_or_outside_window_routes'])
    shape(row['plan'], {'known_routes', 'known_sources_only', 'doi_lookup_permitted'},
          {'provider_plan_version'})
    plan_version = row['plan'].get('provider_plan_version', 1)
    require(type(plan_version) is int and plan_version in {1, PROVIDER_PLAN_VERSION})
    provider_count = len(LEGACY_PROVIDERS) if plan_version == 1 else len(PROVIDERS)
    known = row['plan']['known_routes']
    require(type(known) is list and type(row['plan']['known_sources_only']) is bool
            and type(row['plan']['doi_lookup_permitted']) is bool)
    require(not row['plan']['known_sources_only'] or not row['plan']['doi_lookup_permitted'])
    for identity in known:
        hash_value(identity)
    require(len(set(known)) == len(known))
    require(type(row['tried_sources']) is list)
    for identity in row['tried_sources']: hash_value(identity)
    require(row['tried_sources'] == sorted(set(row['tried_sources'])))
    cursor = row['cursor']
    shape(cursor, {'known', 'provider', 'provider_tried'})
    integer(cursor['known'], len(known)); integer(cursor['provider'], provider_count)
    tried = cursor['provider_tried']
    require(type(tried) is list)
    for identity in tried:
        hash_value(identity)
    require(tried == sorted(set(tried)) and set(tried) <= set(row['tried_sources']))
    if cursor['known'] < len(known) or not row['plan']['doi_lookup_permitted']:
        require(cursor['provider'] == 0 and not tried)
    if cursor['provider'] == provider_count:
        require(not tried)
    fallbacks = row.get('provider_fallbacks', {})
    require(type(fallbacks) is dict)
    for index, progress in fallbacks.items():
        require(type(index) is str and index.isdigit() and str(int(index)) == index
                and cursor['provider'] < int(index) < provider_count
                and cursor['known'] == len(known) and row['plan']['doi_lookup_permitted'])
        shape(progress, {'complete', 'tried_sources', 'status', 'attempted_at'}, {'next_retry_at'})
        timestamp(progress['attempted_at'])
        require(type(progress['complete']) is bool
                and progress['status'] in RETRY | {'pending_routes', 'in_progress', 'exhausted', 'full_document_retrieved'})
        require(progress['complete'] == (progress['status'] in {'exhausted', 'full_document_retrieved'}))
        if progress['status'] == 'full_document_retrieved':
            require(row['complete'] and row['status'] == 'full_document_retrieved_not_reviewed')
        require(type(progress['tried_sources']) is list
                and progress['tried_sources'] == sorted(set(progress['tried_sources']))
                and set(progress['tried_sources']) <= set(row['tried_sources']))
        for identity in progress['tried_sources']:
            hash_value(identity)
        require(('next_retry_at' in progress) == (progress['status'] in RETRY))
        if 'next_retry_at' in progress:
            timestamp(progress['next_retry_at'])
    require(row['attempts'] >= cursor['known'] + cursor['provider'] + len(fallbacks))
    if 'provider_attempted_at' in row:
        require(row['attempts'] > 0 and cursor['known'] == len(known)
                and row['plan']['doi_lookup_permitted'] and cursor['provider'] < provider_count)
    exhausted = cursor['known'] == len(known) and (not row['plan']['doi_lookup_permitted']
                                                or cursor['provider'] == provider_count)
    require(type(row['diagnostics']) is list and len(row['diagnostics']) <= 96)
    for entry in row['diagnostics']:
        validate_diagnostic(entry)
    if 'document' in row:
        validate_document(row['document'])
        require('document_evidence' in row)
        evidence = row['document_evidence']; validate_diagnostic(evidence)
        require(evidence['status'] == row['document']['evidence_status'] and not evidence['retryable']
                and (evidence.get('final_url') or evidence.get('url')) == row['document']['source_url'])
        require(row['attempts'] > 0)
    else:
        require('document_evidence' not in row)
    if 'source_refreshes' in row:
        import source_receipt_refresh
        source_receipt_refresh.validate(row)
    if 'source_refresh_hold' in row:
        import source_receipt_refresh
        source_receipt_refresh.validate_hold(row)
    if {'previous_documents', 'html_refresh', 'html_refresh_attempts'} & set(row):
        history_row = row
        if row.get('source_refreshes'):
            # Parser migration history ends at the receipt preceding content recovery.
            history_row = {**row, **row['source_refreshes'][0]['receipt'],
                           'last_attempt_at': row['html_refresh']['attempted_at']}
        validate_html_refresh(history_row)
    if row['complete']:
        require(row['status'] in TERMINAL and 'next_retry_at' not in row)
        if row['status'] == 'full_document_retrieved_not_reviewed':
            require(row.get('document', {}).get('evidence_status') == 'full_document_retrieved'
                    and row.get('last_outcome') == 'full_document_retrieved')
        else:
            require(exhausted)
            if row['status'] == 'partial_full_text_not_reviewed':
                require(row.get('document', {}).get('evidence_status') == 'partial_full_text')
            else:
                require('document' not in row)
                if row['status'] == 'access_blocked':
                    require(any(entry['status'] in BLOCKED for entry in row['diagnostics']))
    else:
        require(row['status'] not in TERMINAL)
    if row['status'] in RETRY:
        require('next_retry_at' in row)
    elif row['status'] != 'in_progress':
        require('next_retry_at' not in row)
    for key in ('next_retry_at', 'last_attempt_at', 'provider_attempted_at'):
        if key in row:
            timestamp(row[key])
    if row['attempts']:
        require('last_attempt_at' in row)
    if 'last_outcome' in row:
        require(row['last_outcome'] in SUCCESS | RETRY | {'access_blocked', 'source_unavailable', 'interrupted_attempt'})


def validate_html_refresh(row):
    """Bounded audit trail, tied to the same physical source and parser revisions.

    Original v2 checkpoints omit these optional fields and remain valid. Once
    a refresh is attempted, every revision stays in the ledger, even failures
    and interrupted attempts. Reaching the cap requires separate reviewed work.
    """
    require({'document', 'html_refresh', 'html_refresh_attempts', 'last_attempt_at'} <= set(row)
            and row['complete'] and row['status'] == 'partial_full_text_not_reviewed')
    current = row['document']
    require(is_html_document(current))
    attempts = row['html_refresh_attempts']
    require(type(attempts) is list and 1 <= len(attempts) <= MAX_HTML_REFRESH_ATTEMPTS
            and row['attempts'] >= len(attempts) + 1)
    revisions = []; successes = []; times = []
    for attempt in attempts:
        shape(attempt, {'version', 'attempted_at', 'outcome'})
        extraction_version(attempt['version']); timestamp(attempt['attempted_at'])
        require(code(attempt['outcome']) == attempt['outcome']
                and attempt['outcome'] != 'full_document_retrieved')
        revisions.append(attempt['version']); times.append(utc_now(attempt['attempted_at']))
        if attempt['outcome'] == 'partial_full_text':
            successes.append(attempt['version'])
    require(len(revisions) == len(set(revisions)) and times == sorted(times)
            and row['html_refresh'] == attempts[-1]
            and row['last_attempt_at'] == attempts[-1]['attempted_at'])
    history = row.get('previous_documents', [])
    require(type(history) is list and len(history) == len(successes)
            and len(history) <= MAX_HTML_REFRESH_ATTEMPTS)
    documents = []
    for prior in history:
        shape(prior, {'document', 'document_evidence'})
        doc = prior['document']; evidence = prior['document_evidence']
        validate_document(doc); validate_diagnostic(evidence)
        require(is_html_document(doc) and evidence['status'] == doc['evidence_status']
                and (evidence.get('final_url') or evidence.get('url')) == doc['source_url']
                and doc['source_url'] == current['source_url']
                and doc['document_version'] == current['document_version'])
        documents.append(doc)
    documents.append(current)
    retained_versions = [doc.get('html_extraction_version') for doc in documents]
    # The first extraction may predate version tracking. Every later retained
    # extraction must correspond, in order, to exactly one successful refresh.
    require(len(retained_versions) == len(set(retained_versions))
            and retained_versions[1:] == successes
            and not set(revisions) & {retained_versions[0]})


def validate_pauses(pauses):
    require(type(pauses) is dict)
    for key, value in pauses.items():
        require(type(key) is str and (key in {'provider:' + name for name in CONTROL_PROVIDERS}
            or re.fullmatch(r'host:[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', key)))
        timestamp(value)


def validate_state(state):
    """Pure offline validation; reject corrupt or old checkpoints without repair.

    No network, filesystem writes, or source re-fetches occur here. The checksum
    is an integrity aid, not a cryptographic attestation of source retrieval.
    """
    try:
        shape(state, {'schema_version', 'publication_window', 'source_text_saved', 'records',
            'cursor', 'provider_pauses', 'closed_windows', 'dispositions',
            'input_fingerprint', 'state_sha256'}, {'next_cursor', 'run', 'access_controls'})
        require(type(state['schema_version']) is int and state['schema_version'] == VERSION)
        hash_value(state['state_sha256'])
        require(state['state_sha256'] == digest({k: v for k, v in state.items() if k != 'state_sha256'}))
        saved_window(state['publication_window'])
        require(state['source_text_saved'] is False and type(state['records']) is dict)
        for key, row in state['records'].items():
            hash_value(key); validate_row(row, state['publication_window'])
        integer(state['cursor'], max(0, len(state['records']) - 1))
        if 'next_cursor' in state:
            integer(state['next_cursor'], max(0, len(state['records']) - 1))
        hash_value(state['input_fingerprint'])
        require(state['input_fingerprint'] == digest([(key, state['records'][key]['fingerprint'])
                                                      for key in sorted(state['records'])]))
        validate_pauses(state['provider_pauses'])
        if 'access_controls' in state:
            controls.validate_controls(state['access_controls'])
        require(type(state['closed_windows']) is list and type(state['dispositions']) is list)
        for closed in state['closed_windows']:
            shape(closed, {'publication_window', 'selected_records', 'completed_records',
                'pending_records', 'pending_record_metadata', 'status', 'notice'})
            saved_window(closed['publication_window'])
            for key in ('selected_records', 'completed_records', 'pending_records'):
                integer(closed[key])
            require(closed['selected_records'] == closed['completed_records'] + closed['pending_records'])
            require(type(closed['pending_record_metadata']) is dict
                    and len(closed['pending_record_metadata']) == closed['pending_records'])
            require(closed['status'] == ('closed_with_pending_records' if closed['pending_records'] else 'closed')
                    and closed['notice'] == CLOSED_NOTICE)
            for key, row in closed['pending_record_metadata'].items():
                hash_value(key); validate_row(row, closed['publication_window'])
                require(not row['complete'])
        for disposition in state['dispositions']:
            shape(disposition, {'record_key', 'publication_window', 'reason', 'record', 'observed_at'})
            hash_value(disposition['record_key']); saved_window(disposition['publication_window'])
            require(disposition['reason'] in EXCLUSIONS | {'removed_from_input', 'replaced_input_version'})
            timestamp(disposition['observed_at'])
            validate_row(disposition['record'], disposition['publication_window'])
        if 'run' in state:
            summary = state['run']
            keys = {'checked_at', 'selected_records', 'attempted_records', 'attempted_stages',
                'completed_records', 'pending_records', 'deferred_retry_records', 'statuses',
                'excluded', 'duplicate_records', 'stop_reason', 'known_sources_only', 'limit',
                'time_budget_seconds', 'item_time_budget_seconds', 'max_candidates_per_provider_stage',
                'active_provider_pauses', 'scope', 'model_used', 'publication_or_review_performed'}
            shape(summary, keys)
            timestamp(summary['checked_at'])
            for key in ('selected_records', 'attempted_records', 'attempted_stages', 'completed_records',
                        'pending_records', 'deferred_retry_records', 'duplicate_records', 'limit',
                        'max_candidates_per_provider_stage'):
                integer(summary[key])
            require(summary['selected_records'] == len(state['records'])
                    and summary['pending_records'] == sum(not r['complete'] for r in state['records'].values())
                    and summary['completed_records'] + summary['pending_records'] == summary['selected_records'])
            require(summary['attempted_records'] == summary['attempted_stages'] <= min(summary['limit'], summary['selected_records']))
            require(summary['deferred_retry_records'] == sum('next_retry_at' in r for r in state['records'].values()))
            require(type(summary['statuses']) is dict and summary['statuses'] == dict(Counter(r['status'] for r in state['records'].values())))
            for value in summary['statuses'].values():
                integer(value)
            require(type(summary['excluded']) is dict and set(summary['excluded']) <= EXCLUSIONS)
            for value in summary['excluded'].values():
                integer(value)
            require(summary['stop_reason'] in {'queue_checked', 'record_limit', 'time_budget'})
            require(type(summary['known_sources_only']) is bool and summary['scope'] == SCOPE
                    and summary['model_used'] is False and summary['publication_or_review_performed'] is False)
            for key, maximum in (('time_budget_seconds', 86400), ('item_time_budget_seconds', 3600)):
                require(type(summary[key]) in (int, float) and 0 < summary[key] <= maximum)
            require(1 <= summary['max_candidates_per_provider_stage'] <= 32 and summary['limit'] <= 1000)
            validate_pauses(summary['active_provider_pauses'])
            require(summary['active_provider_pauses'] == {key: value for key, value in state['provider_pauses'].items()
                if utc_now(value) > utc_now(summary['checked_at'])})
        return state
    except (TypeError, KeyError, ValueError, OverflowError, RecursionError):
        raise ValueError(STATE_ERROR) from None


def seal_state(state):
    state['state_sha256'] = digest({key: value for key, value in state.items() if key != 'state_sha256'})
    validate_state(state)
    return state


def document_metadata(document):
    """Keep exact interval proof without a source character or PDF byte."""
    locations = [unit['location'] for unit in document.units]
    if len(set(locations)) != len(locations):
        raise ValueError('invalid_document_locations')
    chunks = chunk_document(document)
    if not coverage_is_complete(document, chunks):
        raise ValueError('coverage_gap')
    # Use stable numeric unit IDs so XML tag/location strings cannot leak prose.
    unit_ids = {location: index + 1 for index, location in enumerate(locations)}
    raw = document.manifest()
    result = {
        'source_url': access.diagnostic_url(document.url),
        'document_version': token(document.version),
        'semantic_completeness': 'not_verified',
        'review_status': 'not_reviewed',
        'source_text_saved': False,
        'redistribution_granted': False,
        'all_retrieved_text_chunked': True,
        'chunks_total': len(chunks),
        'units': [{'unit': index + 1, 'characters': len(unit['text']), 'has_text': bool(unit['text'].strip())}
                  for index, unit in enumerate(document.units)],
        'chunk_intervals': [{'chunk': chunk['id'], 'ranges': [
            {'unit': unit_ids[r['location']], 'start': r['start'], 'end': r['end']}
            for r in chunk['ranges']]} for chunk in chunks],
    }
    for key, allowed in MANIFEST_ENUMS.items():
        if raw.get(key) in allowed:
            result[key] = raw[key]
    for key in ('characters_retrieved', 'units_retrieved', 'source_byte_count',
                'pages_total', 'pages_processed', 'pages_with_text'):
        if type(raw.get(key)) is int and raw[key] >= 0:
            result[key] = raw[key]
    for key in ('source_sha256', 'source_bytes_sha256'):
        if isinstance(raw.get(key), str) and re.fullmatch(r'[0-9a-f]{64}', raw[key]):
            result[key] = raw[key]
    if is_html_document(result) and raw.get('html_extraction_version') == HTML_EXTRACTION_VERSION:
        result['html_extraction_version'] = HTML_EXTRACTION_VERSION
    # Byte and text coverage are physical extraction diagnostics only.
    return result


def validate_window(payload, now):
    window = payload.get('run', {}).get('publication_window')
    start, end = previous_week(now)
    if (not isinstance(window, dict) or window.get('timezone') != 'UTC'
            or window.get('from') != start.isoformat() or window.get('to') != end.isoformat()):
        raise ValueError('previous_completed_utc_week_required')
    return {'from': start.isoformat(), 'to': end.isoformat(), 'timezone': 'UTC'}


def verified_arxiv_v1(record):
    """Return the exact verified v1 ID, None if unrelated, or '' if invalid.

    The official first-publication verifier binds its requested ID, returned
    source ID, version URL and original day. Do not infer a first version from
    an unversioned URL or relabel prior unversioned retrieval evidence.
    """
    provenance = record.get('publication_date_provenance') or {}
    if not isinstance(provenance, dict) or provenance.get('basis') != 'arxiv_first_submitted':
        return None
    base = arxiv_record_identifier(record)
    if not base:
        return ''
    expected = base + 'v1'
    if (provenance.get('source') != 'Official arXiv Atom metadata'
            or provenance.get('status') != 'day_known' or provenance.get('field') != 'published'
            or provenance.get('requested_id') != expected
            or provenance.get('version_url') != 'https://arxiv.org/abs/' + expected
            or provenance.get('source_id') not in {'http://arxiv.org/abs/' + expected,
                                                    'https://arxiv.org/abs/' + expected}
            or publication_date(provenance.get('value')) != publication_date(record.get('published'))
            or publication_date(provenance.get('raw')) != publication_date(record.get('published'))
            or publication_date(record.get('published')) is None):
        return ''
    try:
        source = urlsplit(provenance.get('source_url', ''))
        if (source.scheme != 'https' or source.hostname != 'export.arxiv.org'
                or source.path != '/api/query' or source.username or source.password
                or source.port not in (None, 443) or source.fragment
                or parse_qsl(source.query, keep_blank_values=True) != [('id_list', expected)]):
            return ''
        original = urlsplit(record.get('url') or '')
        if original.hostname in {'arxiv.org', 'www.arxiv.org', 'export.arxiv.org'}:
            match = re.fullmatch(r'/(?:abs|pdf|html)/(' + re.escape(base) + r')(?:v\d+)?(?:\.pdf)?/?', original.path)
            if not match:
                return ''
    except (TypeError, ValueError):
        return ''
    return expected


def is_pinned_arxiv_url(url, identifier):
    try:
        parsed = urlsplit(url)
        return bool(parsed.scheme == 'https' and parsed.hostname in {'arxiv.org', 'export.arxiv.org'}
            and not parsed.username and not parsed.password and parsed.port in (None, 443)
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r'/(?:abs|pdf|html)/' + re.escape(identifier) + r'(?:\.pdf)?/?', parsed.path))
    except (TypeError, ValueError):
        return False


def pin_arxiv_route(route, record):
    identifier = verified_arxiv_v1(record)
    return {**route, 'version': 'arxiv_preprint_v1'} if identifier else route


def eligibility(record, window):
    day = publication_date(record.get('published'))
    if day is None:
        return 'excluded_missing_publication_date'
    provenance = record.get('publication_date_provenance') or {}
    basis = str(provenance.get('basis') or provenance.get('field') or '').lower()
    if any(marker in basis for marker in ('updated', 'modified', 'first_seen', 'indexed', 'deposited', 'created')):
        return 'excluded_nonpublication_date'
    evidence_day = provenance.get('date') or provenance.get('value')
    if evidence_day and publication_date(evidence_day) != day:
        return 'excluded_conflicting_publication_date'
    if provenance.get('status') == 'unresolved':
        return 'excluded_missing_publication_date'
    if not date_in_window(day, window['from'], window['to']):
        return 'excluded_outside_publication_window'
    if record.get('historical_backfill') or str(record.get('discovery_scope', '')).startswith('historical:'):
        return 'excluded_historical_backfill'
    if verified_arxiv_v1(record) == '':
        return 'excluded_unverified_original_publication_date'
    if not weekly_eligible(record, window['from'], window['to']):
        return 'excluded_unverified_original_publication_date'
    if record.get('kind') not in ('scholarly', 'nonacademic'):
        return 'excluded_unsupported_kind'
    return ''


def route_permitted(route, record, window):
    """Shared date/version and no-credential policy for known and locator URLs."""
    try:
        url = urlsplit(route.get('url', ''))
        # The inherited TEI adapter reads OPENALEX_API_KEY. It is not a public
        # anonymous route, even when supplied directly in known candidates.
        if route.get('structured_format') == 'tei' or url.hostname in {'content.openalex.org', 'api.openalex.org'}:
            return False
        if url.username or url.password:
            return False
        if not access.anonymous_source_url(route.get('url', '')):
            return False
    except (TypeError, ValueError):
        return False
    pinned = verified_arxiv_v1(record)
    if pinned == '' or (pinned and not is_pinned_arxiv_url(route.get('url', ''), pinned)):
        return False
    if pinned:
        # A locator omitting a date cannot erase an explicit exclusion for
        # this same verified version, including its /abs and /pdf aliases.
        originals = list(record.get('fulltext_candidates') or []) + access.registry_candidates(record)
        for original in originals:
            if not isinstance(original, dict) or access.arxiv_identifier(original.get('url')) != pinned:
                continue
            stated = original.get('published') or original.get('publication_date')
            if stated and not date_in_window(stated, window['from'], window['to']):
                return False
    original_date = route.get('published') or route.get('publication_date')
    related = (route.get('related_doi') or route.get('identity_verification_url')
        or (record.get('doi') and route.get('doi') and access.doi(record['doi']) != access.doi(route['doi'])))
    return not related and (not original_date or date_in_window(original_date, window['from'], window['to']))


def eligible_routes(record, window):
    routes = []; excluded = 0; pinned_route_seen = False
    pinned = verified_arxiv_v1(record)
    inputs = list(record.get('fulltext_candidates') or []) + access.registry_candidates(record)
    for route in access.known_candidates(record):
        source_id = access.arxiv_identifier(route['url'])
        pinned_route_seen = pinned_route_seen or bool(pinned and source_id == pinned)
        originals = [r for r in inputs if isinstance(r, dict) and
            (r.get('url') == route['url'] or (source_id and access.arxiv_identifier(r.get('url')) == source_id))]
        original = next((r for r in originals if r.get('published') or r.get('publication_date')), {})
        if not route_permitted({**original, **route}, record, window):
            excluded += 1
            continue
        routes.append(pin_arxiv_route(route, record))
    if pinned and not routes and not pinned_route_seen:
        # Use the metadata-verified first version, not today's arXiv alias.
        routes.append(access.candidate('https://arxiv.org/pdf/' + pinned, 'arXiv_identifier',
            access.doi(record.get('doi')), 'arxiv_preprint_v1'))
    return routes, excluded


def record_key(record):
    identity = access.doi(record.get('doi')) or record.get('url') or record.get('id')
    return digest({'identity': identity, 'title_if_no_identity': '' if identity else record.get('title', '')})


def prepare(record, window, known_only):
    routes, excluded = eligible_routes(record, window)
    # Fingerprint access-relevant inputs, including actual URL/query/version
    # changes. Persist only the digest, never authentication-bearing URLs.
    fingerprint = digest({'version': VERSION, 'kind': record.get('kind'),
        'doi': record.get('doi'), 'url': record.get('url'), 'title': record.get('title'),
        'published': record.get('published'), 'routes': routes,
        'candidate_input': record.get('fulltext_candidates'),
        'date_provenance': record.get('publication_date_provenance'),
        'known_sources_only': known_only})
    return routes, excluded, fingerprint


def new_row(record, fingerprint, excluded, routes, known_only):
    return {
        'fingerprint': fingerprint, 'kind': record.get('kind'),
        'published': publication_date(record.get('published')).isoformat(),
        'source_url': access.diagnostic_url(record.get('url')),
        'status': 'pending', 'complete': False, 'attempts': 0,
        'cursor': {'known': 0, 'provider': 0, 'provider_tried': []}, 'tried_sources': [],
        'plan': {'provider_plan_version': PROVIDER_PLAN_VERSION,
                 'known_routes': [digest(route) for route in routes], 'known_sources_only': known_only,
                 'doi_lookup_permitted': not known_only and bool(access.DOI.fullmatch(access.doi(record.get('doi'))))},
        'excluded_related_or_outside_window_routes': excluded,
        'diagnostics': [], 'source_text_saved': False,
    }


def stage_plan(routes, cursor, known_only, window, tried_sources=(), providers_enabled=True):
    if cursor['known'] < len(routes):
        return {'kind': 'known', 'source': routes[cursor['known']], 'publication_window': window}
    if not known_only and providers_enabled and cursor['provider'] < len(PROVIDERS):
        return {'kind': 'provider', 'name': PROVIDERS[cursor['provider']],
                'tried_sources': list(tried_sources), 'publication_window': window}
    return None


def fallback_stage_plan(row, window, pauses, now, prefer_primary=False):
    """Try one later independent provider while the primary checkpoint waits.

    The primary cursor and retry deadline stay intact. This is not a retry of
    the paused provider, a mirror workaround, or permission to bypass a host
    cooldown: perform_stage still receives all active article-host pauses.
    """
    if (not row['plan']['doi_lookup_permitted']
            or row['cursor']['known'] < len(row['plan']['known_routes'])):
        return None
    count = (len(LEGACY_PROVIDERS) if row['plan'].get('provider_plan_version', 1) == 1
             else len(PROVIDERS))
    available = []
    for index in range(row['cursor']['provider'] + 1, count):
        progress = row.get('provider_fallbacks', {}).get(str(index), {})
        pause = pauses.get('provider:' + PROVIDERS[index])
        if (progress.get('complete')
                or (progress.get('next_retry_at') and utc_now(progress['next_retry_at']) > now)
                or (pause and utc_now(pause) > now)):
            continue
        available.append((progress.get('attempted_at', ''), index))
    if not available:
        return None
    attempted_at, index = min(available)
    # Retry-After is a minimum delay, not a reason to retry the same provider
    # first forever when cron runs less often than the cooldown. Oldest ready
    # checkpoint wins; untouched independent providers get their first turn.
    if prefer_primary and row.get('provider_attempted_at', row.get('last_attempt_at', '')) <= attempted_at:
        return None
    return {'kind': 'provider', 'name': PROVIDERS[index], 'fallback_provider': index,
            'tried_sources': list(row['tried_sources']), 'publication_window': window}


def provider_stage_complete(ledger):
    count = sum(d.get('stage') == 'article' for d in ledger)
    remaining = max([d.get('candidates', 0) for d in ledger if d.get('stage') == 'discovery'] or [0])
    return not (count and remaining > count)


def consume_provider_fallbacks(row):
    """Advance past completed fallback stages, or adopt their pending cursor."""
    progress = row.get('provider_fallbacks', {})
    while str(row['cursor']['provider']) in progress:
        saved = progress.pop(str(row['cursor']['provider']))
        if saved['complete']:
            row['cursor']['provider'] += 1
            row['cursor']['provider_tried'] = []
        else:
            row['cursor']['provider_tried'] = saved['tried_sources']
            row['provider_attempted_at'] = saved['attempted_at']
            row['status'] = saved['status']
            if 'next_retry_at' in saved:
                row['next_retry_at'] = saved['next_retry_at']
            break
    if not progress:
        row.pop('provider_fallbacks', None)


def perform_stage(record, plan, max_candidates):
    """Apply serialized restrictions inside spawn, not just parent ContextVars."""
    shared = controls.validate_controls(plan.get('access_controls', controls.empty_controls()))
    effective = controls.stage_controls(shared, plan.get('controls_checked_at'))
    if plan['kind'] == 'provider':
        name = plan['name']
        if name in effective['denied_providers']:
            return {'diagnostics': [{'stage': 'discovery', 'provider': name,
                'status': 'provider_access_denied_history', 'retryable': False}], 'tried_sources': []}
        if name in effective['paused_providers']:
            until = shared['provider_pauses']['provider:' + name]
            seconds = max(1, math.ceil((utc_now(until) - utc_now(plan.get('controls_checked_at'))).total_seconds()))
            return {'diagnostics': [{'stage': 'discovery', 'provider': name,
                'status': 'rate_limit_pause', 'retryable': True,
                'retry_after_seconds': min(604800, seconds)}], 'tried_sources': []}
    scoped_plan = dict(plan)
    scoped_plan['host_backoff'] = dict(plan.get('host_backoff', {}))
    for host, seconds in effective['host_backoff'].items():
        scoped_plan['host_backoff'][host] = max(scoped_plan['host_backoff'].get(host, 0), seconds)
    stage_started = time.monotonic()
    with controls.retrieval_scope(effective['denied_hosts'], effective['blocked_urls'],
                                  scoped_plan['host_backoff'], started=stage_started):
        return _perform_stage(record, scoped_plan, max_candidates, stage_started)


def _perform_stage(record, plan, max_candidates, stage_started):
    """Bounded stage; never continue to another source after a rate limit."""
    window = plan['publication_window']
    if verified_arxiv_v1(record) == '':
        return {'diagnostics': [{'status': 'route_policy_excluded', 'retryable': False}], 'tried_sources': []}
    diagnostics = []; tried = []; best = None; host_waits = []
    host_backoff = dict(plan.get('host_backoff', {}))
    denied_hosts = set(access.HOST_DENIALS.get() or ())
    unavailable_hosts = set()
    if plan['kind'] == 'known':
        candidates = [pin_arxiv_route(plan['source'], record)]
        if not route_permitted(plan['source'], record, window):
            return {'diagnostics': [{'status': 'route_policy_excluded', 'retryable': False}],
                    'tried_sources': []}
    else:
        if not access.DOI.fullmatch(access.doi(record.get('doi'))):
            return {'diagnostics': [{'stage': 'discovery', 'provider': plan['name'],
                'status': 'no_exact_match', 'candidates': 0, 'retryable': False}], 'tried_sources': []}
        function = dict(access.default_providers())[plan['name']]
        found, discovery = access.provider_candidates(plan['name'], function, access.doi(record.get('doi')))
        attempted = set(plan['tried_sources'])
        def priority(route):
            value = route['url']
            try:
                path = urlsplit(value).path.lower()
            except ValueError:
                path = ''
            return (not access.safe_url(value), not (path.endswith('.pdf') or
                    '/pdf/' in path or '/download/' in path), value, digest(route))
        unique = {}
        for route in sorted(found, key=priority):
            if route_permitted(route, record, window):
                unique.setdefault(route['url'], pin_arxiv_route(route, record))
        candidates = [route for url, route in unique.items() if digest(url) not in attempted]
        discovery = {**discovery, 'candidates': len(candidates)}
        diagnostics.append(diagnostic(discovery))
    for route in candidates[:max_candidates]:
        host = urlsplit(access.diagnostic_url(route['url'])).hostname
        wait = host_backoff.get(host, 0) - (time.monotonic() - stage_started)
        if wait > 0:
            host_waits.append(max(1, math.ceil(wait)))
            continue
        remaining_backoff = {host: max(0, seconds - (time.monotonic() - stage_started))
                             for host, seconds in host_backoff.items()}
        # retrieve scopes its own context. Carry observed failures across calls,
        # including failures on nested URLs rather than just the landing host.
        denial_scope = access.HOST_DENIALS.set(denied_hosts)
        try:
            doc, ledger = access.retrieve(record, max_candidates=1, providers=[], known_sources=[route],
                                          anonymous_only=True, host_backoff=remaining_backoff)
        finally:
            access.HOST_DENIALS.reset(denial_scope)
        local = controls.diagnostic_controls(diagnostic(entry) for entry in ledger)
        access.SOURCE_DENIALS.get().update(local['blocked_urls'])
        for entry in ledger:
            target = entry.get('failure_url') or entry.get('url') or ''
            failed_host = urlsplit(access.diagnostic_url(target)).hostname
            status = entry.get('status')
            if not failed_host or entry.get('stage') != 'article':
                continue
            if status in {'article_http_401', 'article_http_403', 'http_401', 'http_403'}:
                denied_hosts.add(failed_host)
            if status == 'source_unavailable_page':
                unavailable_hosts.add(failed_host)
                seconds = max(1, min(entry.get('retry_after_seconds', 3600), 604800))
                host_backoff[failed_host] = max(host_backoff.get(failed_host, 0),
                    time.monotonic() - stage_started + seconds)
        if (doc is not None and 'receipt_refresh_version' in plan
                and doc.version != plan['receipt_refresh_version']):
            # Reject unknown returned labels before document_metadata can
            # normalize them to unspecified. A refresh cannot relabel versions.
            ledger = [{**entry, 'status': 'source_version_unverified'}
                      if entry.get('status') in SUCCESS else entry for entry in ledger]
            doc = None
        pinned = verified_arxiv_v1(record)
        if doc is not None and pinned:
            if not is_pinned_arxiv_url(doc.url, pinned) or doc.version != 'arxiv_preprint_v1':
                # Redirects or provider substitutions cannot make a latest
                # version into first-version evidence. Retain only a failure.
                ledger = [{**entry, 'status': 'source_version_unverified'}
                          if entry.get('status') in SUCCESS else entry for entry in ledger]
                doc = None
        diagnostics.extend(diagnostic(row) for row in ledger)
        if not any(row.get('retryable') for row in ledger):
            tried.append(digest(route['url']))
        if doc is not None:
            meta = document_metadata(doc)
            if (best is None or meta['evidence_status'] == 'full_document_retrieved'
                    or meta['characters_retrieved'] > best['characters_retrieved']):
                best = meta
        if any((row.get('status') == 'rate_limit_pause'
                and urlsplit(access.diagnostic_url(row.get('failure_url') or row.get('url') or '')).hostname
                    not in unavailable_hosts) or
               str(row.get('status', '')).endswith('http_429') for row in ledger):
            break
        if best and best['evidence_status'] == 'full_document_retrieved':
            break
    if host_waits and (not best or best['evidence_status'] != 'full_document_retrieved'):
        diagnostics.append({'stage': 'retrieval', 'status': 'rate_limit_pause',
                            'retryable': True, 'retry_after_seconds': max(host_waits)})
    result = {'diagnostics': diagnostics, 'tried_sources': sorted(set(tried))}
    if best is not None:
        result['document'] = best
    return result


MAX_METADATA_BYTES = 16_000_000


def child_stage(sender, record, plan, max_candidates):
    sink = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(sink, 1); os.dup2(sink, 2)
    finally:
        os.close(sink)
    try:
        result = perform_stage(record, plan, max_candidates)
    except BaseException as exc:
        result = {'diagnostics': [diagnostic(access.failure_diagnostic(exc, article=True))]}
    try:
        encoded = json.dumps(result, separators=(',', ':')).encode()
        if len(encoded) > MAX_METADATA_BYTES:
            encoded = b'{"diagnostics":[{"status":"metadata_budget_exhausted","retryable":false}]}'
        sender.send_bytes(encoded)
    finally:
        sender.close()


def bounded_stage(record, plan, max_candidates, timeout):
    """Deadline covers the complete IPC frame, not only its first byte."""
    deadline = time.monotonic() + max(0, timeout)
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=child_stage, args=(sender, record, plan, max_candidates))
    child.start(); sender.close()
    done = threading.Event(); received = []
    def receive():
        try:
            received.append(receiver.recv_bytes(MAX_METADATA_BYTES))
        except (EOFError, OSError):
            pass
        finally:
            done.set()
    reader = threading.Thread(target=receive, daemon=True)
    reader.start()
    timed_out = not done.wait(max(0, deadline - time.monotonic()))
    try:
        if timed_out or time.monotonic() > deadline:
            return {'diagnostics': [{'status': 'deferred_time_budget', 'retryable': True,
                                     'retry_after_seconds': 3600}]}
        if not received:
            return {'diagnostics': [{'status': 'worker_failed', 'retryable': True,
                                     'retry_after_seconds': 3600}]}
        try:
            result = json.loads(received[0])
        except (ValueError, UnicodeError):
            return {'diagnostics': [{'status': 'worker_failed', 'retryable': True,
                                     'retry_after_seconds': 3600}]}
        if time.monotonic() > deadline:
            return {'diagnostics': [{'status': 'deferred_time_budget', 'retryable': True,
                                     'retry_after_seconds': 3600}]}
        return result
    finally:
        if child.is_alive(): child.terminate()
        child.join(timeout=.2)
        if child.is_alive():
            child.kill(); child.join(timeout=.2)
        reader.join(timeout=.1)
        receiver.close()


def failure_status(diagnostics):
    statuses = {d['status'] for d in diagnostics}
    if 'deferred_time_budget' in statuses:
        return 'deferred_time_budget'
    if 'rate_limit_pause' in statuses or any(status.endswith('http_429') for status in statuses):
        return 'rate_limited'
    if any(d.get('retryable') for d in diagnostics):
        return 'temporarily_unavailable'
    if statuses & BLOCKED:
        return 'access_blocked'
    return 'source_unavailable'


def advance(row, result, plan, routes, known_only, now):
    ledger = [diagnostic(item) for item in result.get('diagnostics', [])]
    row['diagnostics'] = (row['diagnostics'] + ledger)[-96:]
    retrieved = result.get('document')
    if retrieved:
        validate_document(retrieved)
    if retrieved and (not row.get('document') or
            retrieved.get('characters_retrieved', 0) > row['document'].get('characters_retrieved', 0)
            or retrieved.get('evidence_status') == 'full_document_retrieved'):
        evidence = next((d for d in ledger if d['status'] == retrieved['evidence_status']
                         and (d.get('final_url') or d.get('url')) == retrieved['source_url']), None)
        require(evidence is not None)
        row['document'] = retrieved
        row['document_evidence'] = evidence
    tried = result.get('tried_sources', [])
    require(type(tried) is list)
    for identity in tried: hash_value(identity)
    if plan['kind'] == 'known' and not any(d.get('retryable') for d in ledger):
        tried = tried + [digest(plan['source']['url'])]
    row['tried_sources'] = sorted(set(row['tried_sources']) | set(tried))
    if plan['kind'] == 'provider' and 'fallback_provider' not in plan:
        row['cursor']['provider_tried'] = sorted(set(row['cursor']['provider_tried']) | set(tried))
    row['last_outcome'] = (retrieved or {}).get('evidence_status') or failure_status(ledger)
    retry = [d for d in ledger if d.get('retryable')]
    if retrieved and retrieved.get('evidence_status') == 'full_document_retrieved':
        row.pop('next_retry_at', None)
        row.update(status='full_document_retrieved_not_reviewed', complete=True)
        if 'fallback_provider' in plan:
            progress = row['provider_fallbacks'][str(plan['fallback_provider'])]
            progress.update(complete=True, status='full_document_retrieved',
                            tried_sources=sorted(set(progress['tried_sources']) | set(tried)))
            progress.pop('next_retry_at', None)
        return
    if 'fallback_provider' in plan:
        progress = row.setdefault('provider_fallbacks', {}).setdefault(str(plan['fallback_provider']),
            {'complete': False, 'tried_sources': [], 'status': 'pending_routes', 'attempted_at': now.isoformat()})
        progress['tried_sources'] = sorted(set(progress['tried_sources']) | set(tried))
        progress.pop('next_retry_at', None)
        if retry:
            seconds = max(max(1, d.get('retry_after_seconds', 3600)) for d in retry)
            progress.update(status=failure_status(ledger), complete=False,
                next_retry_at=(now + timedelta(seconds=seconds)).isoformat())
        else:
            complete = provider_stage_complete(ledger)
            progress.update(complete=complete, status='exhausted' if complete else 'pending_routes')
        # Keep the primary provider's status, cursor and Retry-After unchanged.
        return
    row.pop('next_retry_at', None)
    if retry:
        seconds = max(max(1, d.get('retry_after_seconds', 3600)) for d in retry)
        row.update(status=failure_status(ledger),
                   next_retry_at=(now + timedelta(seconds=seconds)).isoformat())
        return
    if plan['kind'] == 'known':
        row['cursor']['known'] += 1
    else:
        if provider_stage_complete(ledger):
            row['cursor']['provider'] += 1
            row['cursor']['provider_tried'] = []
            row.pop('provider_attempted_at', None)
            consume_provider_fallbacks(row)
    if stage_plan(routes, row['cursor'], known_only, plan['publication_window'],
                  row['tried_sources'], row['plan']['doi_lookup_permitted']) is None:
        # Current retryable failures returned above. Older rate limits/outages
        # remain audit evidence, not a new retry state after every route is done.
        # Retain access-denial history and any retrieved partial document.
        terminal = ('partial_full_text_not_reviewed' if row.get('document') else
                    'access_blocked' if any(d['status'] in BLOCKED for d in row['diagnostics']) else
                    'source_unavailable')
        row.update(complete=True, status=terminal)
    elif 'next_retry_at' not in row:
        row['status'] = 'pending_routes'


def html_refresh_plan(row, routes, record, window):
    """One re-extraction per revision, never a discovery reset or failed-route retry.

    Missing provenance is legacy HTML, not a reason to invalidate the identity
    fingerprint. Only the exact successful URL/version still in the known plan
    is eligible. Locator-only and redirect-only sources require separate review.
    """
    meta = row.get('document', {})
    if (row.get('source_refreshes') or row.get('source_refresh_hold') or not row['complete'] or not is_html_document(meta)
            or meta.get('html_extraction_version') == HTML_EXTRACTION_VERSION
            or len(row.get('html_refresh_attempts', [])) >= MAX_HTML_REFRESH_ATTEMPTS
            or any(attempt['version'] == HTML_EXTRACTION_VERSION
                   for attempt in row.get('html_refresh_attempts', []))
            or any(prior['document'].get('html_extraction_version') == HTML_EXTRACTION_VERSION
                   for prior in row.get('previous_documents', []))):
        return None
    for route in routes:
        if (route['url'] == meta['source_url'] and token(route.get('version')) == meta['document_version']
                and route_permitted(route, record, window)):
            if any((d['status'] in BLOCKED or d['status'].endswith('http_429'))
                   and meta['source_url'] in (d.get('url'), d.get('final_url'), d.get('failure_url'))
                   for d in row['diagnostics']):
                return None
            return {'kind': 'known', 'source': route, 'publication_window': window}
    return None


def finish_html_refresh(row, result):
    ledger = [diagnostic(item) for item in result.get('diagnostics', [])]
    row['diagnostics'] = (row['diagnostics'] + ledger)[-96:]
    # Keep old extraction and provenance on every failure. Do not call advance:
    # a parser deployment cannot move the discovery cursor or reopen other URLs.
    row['html_refresh']['outcome'] = ledger[-1]['status'] if ledger else 'retrieval_error'
    retrieved = result.get('document')
    if not retrieved:
        if row['html_refresh']['outcome'] in SUCCESS:
            row['html_refresh']['outcome'] = 'retrieval_error'
        return
    validate_document(retrieved)
    old = row['document']
    evidence = next((d for d in ledger if d['status'] == retrieved['evidence_status']
                     and (d.get('final_url') or d.get('url')) == retrieved['source_url']), None)
    if (not is_html_document(retrieved) or evidence is None
            or retrieved.get('html_extraction_version') != HTML_EXTRACTION_VERSION
            or retrieved['source_url'] != old['source_url']
            or retrieved['document_version'] != old['document_version']):
        row['html_refresh']['outcome'] = 'document_identity_unverified'
        return
    row.setdefault('previous_documents', []).append({
        'document': old, 'document_evidence': row['document_evidence']})
    # A smaller extraction can be better: teaser removal must not lose to size.
    row['document'] = retrieved
    row['document_evidence'] = evidence
    row['html_refresh']['outcome'] = retrieved['evidence_status']
    row['last_outcome'] = retrieved['evidence_status']


def run(payload, state=None, *, now=None, limit=10, time_budget=300,
        item_time_budget=60, max_candidates=8, known_sources_only=False,
        attempt=bounded_stage, save=None, clock=time.monotonic, shared_controls=None):
    """Production entry point: only the previous completed UTC week."""
    now = utc_now(now)
    window = validate_window(payload, now)
    return _run_window(payload, state, window=window, now=now, limit=limit,
        time_budget=time_budget, item_time_budget=item_time_budget,
        max_candidates=max_candidates, known_sources_only=known_sources_only,
        attempt=attempt, save=save, clock=clock, shared_controls=shared_controls)


def _run_window(payload, state=None, *, window, now=None, limit=10, time_budget=300,
                item_time_budget=60, max_candidates=8, known_sources_only=False,
                attempt=bounded_stage, save=None, clock=time.monotonic, shared_controls=None):
    """Shared engine for separately validated production/preparation packets.

    The preparation wrapper owns its open-week boundary and isolated output.
    This private function does not relax the production CLI's date gate.
    """
    now = utc_now(now)
    saved_window(window)
    if (type(limit) is not int or limit < 0 or limit > 1000 or
            not 0 < time_budget <= 86400 or not 0 < item_time_budget <= 3600
            or type(max_candidates) is not int or not 1 <= max_candidates <= 32):
        raise ValueError('invalid_acquisition_budget')
    if not isinstance(payload.get('items'), list):
        raise ValueError('weekly_items_required')
    started = clock()
    previous = deepcopy(validate_state(state)) if state is not None else {}
    shared = controls.merge_controls(
        controls.controls_from_state(previous) if previous else controls.empty_controls(),
        shared_controls if shared_controls is not None else controls.empty_controls())
    state = {'schema_version': VERSION, 'publication_window': window,
             'source_text_saved': False, 'records': {}, 'cursor': previous.get('cursor', 0),
             'provider_pauses': dict(shared['provider_pauses']),
             'access_controls': shared,
             'closed_windows': list(previous.get('closed_windows') or []),
             'dispositions': list(previous.get('dispositions') or [])}
    if previous.get('publication_window') and previous['publication_window'] != window:
        pending_old = {key: row for key, row in previous.get('records', {}).items() if not row.get('complete')}
        state['closed_windows'].append({
            'publication_window': previous['publication_window'],
            'selected_records': len(previous.get('records', {})),
            'completed_records': len(previous.get('records', {})) - len(pending_old),
            'pending_records': len(pending_old), 'pending_record_metadata': pending_old,
            'status': 'closed_with_pending_records' if pending_old else 'closed',
            'notice': CLOSED_NOTICE})
    selected = {}; prepared = {}; rejected = Counter(); duplicates = 0; excluded_keys = {}
    for record in payload['items']:
        if not isinstance(record, dict):
            rejected['excluded_invalid_record'] += 1
            continue
        reason = eligibility(record, window)
        if reason:
            rejected[reason] += 1
            excluded_keys[record_key(record)] = reason
            continue
        key = record_key(record)
        routes, excluded, fingerprint = prepare(record, window, known_sources_only)
        if key in prepared:
            duplicates += 1
            group = prepared[key]
            group['fingerprints'].add(fingerprint)
            group['routes'].extend(routes)
            group['excluded'] += excluded
            group['duplicate'] = True
        else:
            prepared[key] = {'record': record, 'routes': routes, 'excluded': excluded,
                             'fingerprints': {fingerprint}, 'duplicate': False}
    for key, group in prepared.items():
        record = group['record']; routes = group['routes']
        fingerprints = sorted(group['fingerprints'])
        fingerprint = fingerprints[0] if len(fingerprints) == 1 else digest(fingerprints)
        if group['duplicate']:
            # A second index row can add a legitimate source/version. Merge it
            # instead of silently losing its routes, using a stable ordering.
            unique = {digest(route): route for route in routes}
            routes = ([unique[identity] for identity in sorted(unique)]
                      if len(fingerprints) > 1 else list(unique.values()))
        old = previous.get('records', {}).get(key)
        if not old:
            old = next((entry['record'] for entry in reversed(state['dispositions'])
                        if entry['record_key'] == key and entry['publication_window'] == window
                        and entry['record']['fingerprint'] == fingerprint), None)
        if old and old['fingerprint'] == fingerprint:
            require({k: v for k, v in old['plan'].items() if k != 'provider_plan_version'} == {'known_routes': [digest(route) for route in routes],
                                    'known_sources_only': known_sources_only,
                                    'doi_lookup_permitted': not known_sources_only and bool(access.DOI.fullmatch(access.doi(record.get('doi'))))})
            require(old['source_url'] == access.diagnostic_url(record.get('url'))
                    and old['published'] == publication_date(record.get('published')).isoformat()
                    and old['kind'] == record.get('kind'))
            row = deepcopy(old)
            # Only selected, unchanged current-window rows adopt the appended route.
            # Historical snapshots keep their original plan and exhaustion semantics.
            # Refresh histories require terminal HTML evidence: leave their legacy
            # plan intact until a separate provenance-safe migration is available.
            if (row['plan'].get('provider_plan_version', 1) < PROVIDER_PLAN_VERSION
                    and 'html_refresh' not in row and 'source_refreshes' not in row
                    and 'source_refresh_hold' not in row):
                row['plan']['provider_plan_version'] = PROVIDER_PLAN_VERSION
                if (row['complete'] and row['plan']['doi_lookup_permitted']
                        and row['status'] != 'full_document_retrieved_not_reviewed'):
                    row.update(complete=False, status='pending_routes')
        else:
            row = new_row(record, fingerprint, group['excluded'], routes, known_sources_only)
        if row.get('status') == 'in_progress':
            row.update(status='pending', last_outcome='interrupted_attempt')
        state['records'][key] = row
        selected[key] = (record, routes)
    if previous.get('publication_window') == window:
        for key, old in previous.get('records', {}).items():
            current = state['records'].get(key)
            if current is None or current['fingerprint'] != old['fingerprint']:
                state['dispositions'].append({
                    'record_key': key, 'publication_window': window, 'record': old,
                    'reason': (excluded_keys.get(key, 'removed_from_input') if current is None
                               else 'replaced_input_version'), 'observed_at': now.isoformat()})
    order = sorted(selected)
    state['input_fingerprint'] = digest([(key, state['records'][key]['fingerprint']) for key in order])
    if state['input_fingerprint'] != previous.get('input_fingerprint'):
        state['cursor'] = 0
    attempted = 0; attempted_records = set(); stop = 'queue_checked'
    # Rotate through every eligible input, including records later held by
    # publication quality screening. Quality is not an acquisition gate.
    for offset in range(len(order)):
        index = (state['cursor'] + offset) % len(order)
        key = order[index]; row = state['records'][key]
        record, routes = selected[key]
        import source_receipt_refresh
        content_plan = source_receipt_refresh.plan(row, routes, record, window, state['access_controls'], now)
        refresh_plan = content_plan or html_refresh_plan(row, routes, record, window)
        if row.get('complete') and refresh_plan is None:
            continue
        waiting = bool(row.get('next_retry_at') and utc_now(row['next_retry_at']) > now)
        fallback = (fallback_stage_plan(row, window, state['provider_pauses'], now, prefer_primary=not waiting)
                    if row['status'] in RETRY else None)
        if waiting and fallback is None:
            continue
        remaining = time_budget - (clock() - started)
        if attempted >= limit or remaining <= 0:
            stop = 'record_limit' if attempted >= limit else 'time_budget'
            state['next_cursor'] = index
            break
        record, routes = selected[key]
        plan = fallback or refresh_plan or stage_plan(routes, row['cursor'], known_sources_only, window, row['tried_sources'],
                                          row['plan']['doi_lookup_permitted'])
        if plan is None:
            row.update(complete=True, status='source_unavailable')
            continue
        stage_now = now + timedelta(seconds=max(0, time_budget - remaining))
        pause_key = ('host:' + (urlsplit(access.diagnostic_url(plan['source']['url'])).hostname or '')
                     if plan['kind'] == 'known' else 'provider:' + plan['name'])
        pause = state['provider_pauses'].get(pause_key)
        if pause and utc_now(pause) > now:
            if refresh_plan is None:
                row.update(status='rate_limited', next_retry_at=pause, last_outcome='rate_limited')
            plan = fallback_stage_plan(row, window, state['provider_pauses'], stage_now)
            if plan is None:
                continue
            pause_key = 'provider:' + plan['name']
        plan['access_controls'] = deepcopy(state['access_controls'])
        plan['controls_checked_at'] = stage_now.isoformat()
        plan['host_backoff'] = {key[5:]: max(1, math.ceil((utc_now(until) - stage_now).total_seconds()))
            for key, until in state['provider_pauses'].items()
            if key.startswith('host:') and utc_now(until) > stage_now}
        if 'fallback_provider' not in plan:
            row.pop('next_retry_at', None)
        if plan['kind'] == 'provider':
            if 'fallback_provider' not in plan:
                row['provider_attempted_at'] = now.isoformat()
            elif 'provider_attempted_at' not in row and row.get('last_attempt_at'):
                row['provider_attempted_at'] = row['last_attempt_at']
        row.update(attempts=row['attempts'] + 1, last_attempt_at=now.isoformat())
        if content_plan is not None:
            source_receipt_refresh.start(row, now)
        elif refresh_plan is not None:
            # Save before I/O: interruption must not cause automatic repeated fetches.
            row['html_refresh'] = {'version': HTML_EXTRACTION_VERSION,
                'attempted_at': now.isoformat(), 'outcome': 'interrupted_attempt'}
            row.setdefault('html_refresh_attempts', []).append(row['html_refresh'])
        elif 'fallback_provider' not in plan:
            row['status'] = 'in_progress'
        else:
            progress = row.setdefault('provider_fallbacks', {}).setdefault(str(plan['fallback_provider']),
                {'complete': False, 'tried_sources': [], 'status': 'pending_routes', 'attempted_at': now.isoformat()})
            progress.update(status='in_progress', complete=False, attempted_at=now.isoformat())
            progress.pop('next_retry_at', None)
        seal_state(state)
        if save:
            save(state)
        try:
            result = attempt(record, plan, max_candidates, min(item_time_budget, remaining))
        except Exception as exc:
            result = {'diagnostics': [diagnostic(access.failure_diagnostic(exc, article=True))]}
        response_at = now + timedelta(seconds=max(0, clock() - started))
        if content_plan is not None:
            source_receipt_refresh.finish(row, result, response_at)
        elif refresh_plan is not None:
            finish_html_refresh(row, result)
        else:
            advance(row, result, plan, routes, known_sources_only, response_at)
        quota = [d for d in result.get('diagnostics', [])
                 if str(d.get('status', '')).endswith('http_429')
                 or d.get('status') == 'source_unavailable_page']
        for entry in quota:
            seconds = max(1, min(entry.get('retry_after_seconds', 3600), 604800))
            until = (response_at + timedelta(seconds=seconds)).isoformat()
            # An unavailable article host does not pause an independent locator API.
            keys = set() if entry.get('status') == 'source_unavailable_page' else {pause_key}
            if entry.get('stage') == 'article':
                target = entry.get('failure_url') or entry.get('url') or ''
                host = urlsplit(access.diagnostic_url(target)).hostname
                if host: keys.add('host:' + host)
            for pause_target in keys:
                if not state['provider_pauses'].get(pause_target) or utc_now(state['provider_pauses'][pause_target]) < utc_now(until):
                    state['provider_pauses'][pause_target] = until
        observed = controls.diagnostic_controls(diagnostic(entry) for entry in result.get('diagnostics', []))
        observed['provider_pauses'] = dict(state['provider_pauses'])
        state['access_controls'] = controls.merge_controls(state['access_controls'], observed)
        attempted += 1; attempted_records.add(key)
        state['next_cursor'] = (index + 1) % len(order)
        seal_state(state)
        if save:
            save(state)
    state['cursor'] = state.pop('next_cursor', state['cursor']) if order else 0
    counts = Counter(row['status'] for row in state['records'].values())
    pending = sum(not row.get('complete') for row in state['records'].values())
    state['run'] = {
        'checked_at': now.isoformat(), 'selected_records': len(order),
        'attempted_records': len(attempted_records), 'attempted_stages': attempted,
        'completed_records': len(order) - pending, 'pending_records': pending,
        'deferred_retry_records': sum(bool(row.get('next_retry_at')) for row in state['records'].values()),
        'statuses': dict(sorted(counts.items())), 'excluded': dict(sorted(rejected.items())),
        'duplicate_records': duplicates, 'stop_reason': stop,
        'known_sources_only': known_sources_only, 'limit': limit,
        'time_budget_seconds': time_budget, 'item_time_budget_seconds': item_time_budget,
        'max_candidates_per_provider_stage': max_candidates,
        'active_provider_pauses': {key: until for key, until in state['provider_pauses'].items()
                                   if utc_now(until) > now},
        'scope': SCOPE,
        'model_used': False, 'publication_or_review_performed': False,
    }
    seal_state(state)
    if save:
        save(state)
    return state


def atomic_save(path, state):
    validate_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/weekly.json')
    parser.add_argument('--state', type=Path, default=ROOT / 'data/weekly-source-acquisition.json')
    parser.add_argument('--limit', type=int, default=10, help='Maximum distinct records attempted this run')
    parser.add_argument('--time-budget', type=float, default=300)
    parser.add_argument('--item-time-budget', type=float, default=60)
    parser.add_argument('--max-candidates', type=int, default=8, help='Candidate cap for one locator stage')
    parser.add_argument('--known-sources-only', action='store_true', help='Disable all API locator discovery')
    options = parser.parse_args()
    try:
        payload = json.loads(options.input.read_text(encoding='utf-8'))
        state = json.loads(options.state.read_text(encoding='utf-8')) if options.state.exists() else None
        shared = controls.load_shared_controls(controls.data_root_for_state(options.state), states=[state] if state is not None else [])
        state = run(payload, state, shared_controls=shared, limit=options.limit, time_budget=options.time_budget,
            item_time_budget=options.item_time_budget, max_candidates=options.max_candidates,
            known_sources_only=options.known_sources_only, save=lambda data: atomic_save(options.state, data))
    except Exception as exc:
        allowed = {'previous_completed_utc_week_required', 'invalid_acquisition_budget', 'weekly_items_required', STATE_ERROR, controls.ERROR}
        print(json.dumps({'status': str(exc) if isinstance(exc, ValueError) and str(exc) in allowed else 'acquisition_input_or_state_error',
                          'source_text_saved': False}))
        return 2
    print(json.dumps(state['run'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
