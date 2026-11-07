"""Admission and projection for original summaries, separate from source excerpts.

No inference, retrieval, credentials, or automatic approval occurs here. Review
and publication receipts are content-bound attestations, not cryptographic proof
that a review happened. Only accepted summaries belong in the public manifest;
private drafts, source prose, and unresolved reviews must stay outside the repo.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

MANIFEST = Path(__file__).resolve().parents[1] / 'data/original-readings.json'
FIELDS = ('idea', 'explain', 'approach', 'finding', 'interpretation', 'limitation')
STATUS = 'ai_source_checked_original_summary'
BASIS = ('Original summary checked against the stated source by a separate AI pass; '
         'not human review or independent replication.')


def text(value, maximum=1500):
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum and not re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value)


def safe_url(value):
    if not text(value, 2000) or re.search(r'\s|\\|[\x00-\x1f]', value):
        return False
    try:
        p = urlsplit(value)
        host = p.hostname or ''
        if (p.scheme != 'https' or not host or '.' not in host or host.endswith(('.local', '.localhost'))
                or host.endswith('.') or p.username or p.password or p.port not in (None, 443) or p.query or p.fragment):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        return bool(re.fullmatch(r'[a-zA-Z0-9.-]+', host))
    except ValueError:
        return False


def valid_date(value):
    try:
        return (isinstance(value, str) and len(value) == 10 and date.fromisoformat(value).isoformat() == value
                and date.fromisoformat(value) <= datetime.now(timezone.utc).date())
    except ValueError:
        return False


def identifier(record):
    doi = str(record.get('doi') or '').strip().lower()
    return doi or str(record.get('record_url') or record.get('url') or '').strip()


def payload_digest(note):
    """Editing content, locators, version, rights or quality invalidates the check."""
    body = {k: v for k, v in note.items() if k not in ('review', 'publication')}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def publication_digest(note):
    """Re-reviewing a summary also requires renewed publication acceptance."""
    body = {k: v for k, v in note.items() if k != 'publication'}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def eligible(note, record):
    """Fail closed: a source check is neither a quality decision nor approval."""
    try:
        if not isinstance(note, dict) or record.get('kind') != 'scholarly': return False
        if set(note) != {'id', 'doi', 'record_url', 'title', 'author', 'source', 'summary', 'evidence', 'rights', 'quality', 'review', 'publication'}: return False
        if not text(note['id'], 100) or not text(note['author'], 100): return False
        if not isinstance(note['doi'], str) or not safe_url(note['record_url']): return False
        if note['doi'] and not re.fullmatch(r'10\.\d{4,9}/\S+', note['doi'], re.I): return False
        if not identifier(note) or identifier(note) != identifier(record): return False
        if ' '.join(note['title'].split()).casefold() != ' '.join(record['title'].split()).casefold(): return False
        source = note['source']
        if not isinstance(source, dict) or set(source) != {'url', 'version', 'format', 'source_doi', 'related_journal_doi', 'journal_version_equivalence_claimed', 'review_scope', 'source_sha256'}: return False
        if not safe_url(source['url']) or not text(source['version'], 100): return False
        if source['version'].strip().casefold() in ('unspecified', 'unknown'): return False
        if source['format'] not in ('pdf', 'html', 'jats', 'tei'): return False
        if not text(source['review_scope'], 1000) or len(source['review_scope'].split()) < 6: return False
        if not re.fullmatch(r'[0-9a-f]{64}', source['source_sha256']): return False
        if source['journal_version_equivalence_claimed'] is not False: return False
        if not isinstance(source['source_doi'], str) or not isinstance(source['related_journal_doi'], str): return False
        if any(value and not re.fullmatch(r'10\.\d{4,9}/\S+', value, re.I)
               for value in (source['source_doi'], source['related_journal_doi'])): return False
        if source['source_doi'].lower() != str(note['doi'] or '').lower():
            if not (source['source_doi'] and source['related_journal_doi'].lower() == note['doi'].lower()
                    and re.search(r'preprint|working.paper|accepted.manuscript', source['version'], re.I)):
                return False
        if urlsplit(source['url']).hostname in ('arxiv.org', 'www.arxiv.org', 'export.arxiv.org'):
            if not re.fullmatch(r'/(?:abs|pdf|html)/\d{4}\.\d{4,5}v[1-9]\d*(?:\.pdf)?/?', urlsplit(source['url']).path): return False
        summary = note['summary']
        if not isinstance(summary, dict) or set(summary) != set(FIELDS): return False
        if any(not text(summary[k]) for k in FIELDS if k != 'finding'): return False
        if record.get('research_type') == 'conceptual_framework' and summary['finding'] != '': return False
        if not text(summary['finding']) and not (summary['finding'] == '' and record.get('research_type') == 'conceptual_framework'): return False
        if sum(len(summary[k].split()) for k in FIELDS) > 220: return False
        evidence = note['evidence']
        if not isinstance(evidence, dict) or set(evidence) != set(FIELDS): return False
        for locations in evidence.values():
            if not isinstance(locations, list) or not 1 <= len(locations) <= 8: return False
            for loc in locations:
                if not isinstance(loc, dict) or not set(loc) <= {'section', 'page', 'paragraph'} or not text(loc.get('section'), 180): return False
                for key in ('page', 'paragraph'):
                    if key in loc and (type(loc[key]) is not int or not 1 <= loc[key] <= 100000): return False
        rights = note['rights']
        if not isinstance(rights, dict) or set(rights) != {'original_paraphrases_only', 'source_text_redistribution', 'license_context'}: return False
        if rights['original_paraphrases_only'] is not True or rights['source_text_redistribution'] is not False or not text(rights['license_context'], 500): return False
        quality = note['quality']
        if not isinstance(quality, dict) or set(quality) != {'decision', 'note'} or quality['decision'] != 'acceptable' or not text(quality['note'], 1000): return False
        review = note['review']
        if not isinstance(review, dict) or set(review) != {'kind', 'status', 'reviewer', 'checked_on', 'payload_sha256'}: return False
        if review['kind'] != 'ai_source_check' or review['status'] != 'passed' or not text(review['reviewer'], 100): return False
        if ' '.join(review['reviewer'].split()).casefold() == ' '.join(note['author'].split()).casefold(): return False
        if not valid_date(review['checked_on']) or review['payload_sha256'] != payload_digest(note): return False
        publication = note['publication']
        if not isinstance(publication, dict) or set(publication) != {'decision', 'approved_by', 'approved_on', 'payload_sha256'}: return False
        if publication['decision'] != 'approved' or not text(publication['approved_by'], 100) or not valid_date(publication['approved_on']): return False
        return (publication['approved_on'] >= review['checked_on']
                and publication['payload_sha256'] == publication_digest(note))
    except (KeyError, TypeError, ValueError, AttributeError):
        return False



def weekly_source_eligible(record):
    """A dated publication cannot stand in for a different checked source version.

    This is deliberately stricter than general-library admission. In particular,
    an older related manuscript remains a labeled library reading, not evidence
    for the journal publication's week. It performs no external lookups.
    """
    note = record.get('original_reading')
    if not eligible(note, record): return False
    source = note['source']
    doi = str(record.get('doi') or '').lower()
    if doi and source['source_doi'].lower() != doi: return False
    provenance = record.get('publication_date_provenance') or {}
    is_arxiv = (provenance.get('basis') == 'arxiv_first_submitted'
                or doi.startswith('10.48550/arxiv.')
                or urlsplit(source['url']).hostname in ('arxiv.org', 'www.arxiv.org', 'export.arxiv.org')
                or urlsplit(record.get('url') or '').hostname in ('arxiv.org', 'www.arxiv.org', 'export.arxiv.org'))
    if is_arxiv:
        # Reuse the acquisition queue's pure binding checks, never its network
        # route functions, so summary and retrieval versions cannot diverge.
        from collect_weekly_sources import verified_arxiv_v1, is_pinned_arxiv_url
        pinned = verified_arxiv_v1(record)
        if not pinned or source['version'] not in ('arxiv_preprint_v1', 'preprint_v1'): return False
        if not is_pinned_arxiv_url(source['url'], pinned): return False
        # The acquisition verifier accepts unversioned record locators, but an
        # explicitly different indexed version must not label a v1 summary.
        for value in (doi, record.get('url') or '', note['record_url']):
            version = re.search(r'v(\d+)(?:\.pdf)?/?$', value, re.I)
            if version and version.group(1) != '1': return False
        return True
    if not doi:
        return source['url'] == note['record_url'] == record.get('url')
    return True

def apply(rows, manifest=None):
    """Reconcile the accepted register; removal/revocation removes old summaries.

    Does not change analysis, bibliographic DOI, OA URLs, or extraction counts.
    Duplicate identities are rejected rather than choosing an arbitrary winner.
    """
    if manifest is None:
        manifest = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {'articles': []}
    notes = manifest.get('articles') if isinstance(manifest, dict) else None
    if not isinstance(notes, list): raise ValueError('invalid_original_readings_manifest')
    grouped = {}
    for note in notes:
        if isinstance(note, dict): grouped.setdefault(identifier(note), []).append(note)
    count = 0
    for row in rows:
        had = 'original_reading' in row or (row.get('reading') or {}).get('original_summary')
        row.pop('original_reading', None)
        matches = grouped.get(identifier(row), [])
        if len(matches) == 1 and eligible(matches[0], row):
            row['original_reading'] = deepcopy(matches[0]); count += 1; had = True
        if had:
            # Clear previously projected prose so rejection cannot leave a stale digest.
            row.pop('reading', None)
    return count


def note_for(record):
    original = record.get('original_reading')
    if not eligible(original, record): return None
    s = original['summary']; source = original['source']
    return {
        'level': 'full_text', 'original_summary': True, 'original_summary_id': original['id'],
        'provenance': BASIS, 'notice': BASIS + ' Source version: ' + source['version'] + '.',
        'overview': s['explain'], 'methods': s['approach'], 'findings': s['finding'],
        'interpretation': s['interpretation'], 'limitations': s['limitation'],
        'sample': '', 'reported_findings': bool(s['finding']),
        'research_type': record.get('research_type') or 'unclassified',
        'section_coverage': [], 'extraction_depth': 'original_summary_not_machine_extraction',
        'source_url': source['url'], 'source_version': source['version'], 'source_format': source['format'],
        'source_doi': source['source_doi'], 'related_journal_doi': source['related_journal_doi'],
        'review_kind': 'ai_source_check', 'review_scope': source['review_scope'],
        'source_sha256': source['source_sha256'], 'evidence': deepcopy(original['evidence']),
        'digest': {**deepcopy(s), 'status': STATUS, 'basis': BASIS,
                   'finding_source': 'original_summary', 'editorial_basis': 'stated_source_version',
                   'source_url': source['url'], 'source_version': source['version'],
                   'review_scope': source['review_scope'], 'tags': []},
    }


def public_record(record, *, require_current=False):
    """Revalidate cached snapshots and strip nonaccepted private candidate data."""
    result = deepcopy(record)
    had_original = 'original_reading' in result or (result.get('reading') or {}).get('original_summary') or ((result.get('reading') or {}).get('digest') or {}).get('status') == STATUS
    if require_current:
        apply([result])
    if (had_original or 'original_reading' in result or (result.get('reading') or {}).get('original_summary')
            or ((result.get('reading') or {}).get('digest') or {}).get('status') == STATUS):
        if not eligible(result.get('original_reading'), result): result.pop('original_reading', None)
        result.pop('reading', None)
        from build_readings import make_note
        result['reading'] = make_note(result)
    return result
