"""Additional fail-closed article gates for commentary and reviewed preprints.

These receipts attest to a source-specific editorial decision, not peer review.
They are bound by original_readings' separate review/publication hashes.
"""
import hashlib
import json
import re
from urllib.parse import urlsplit

COMMENTARY_FIELDS = ('thesis', 'reasoning', 'examples', 'tension', 'qualification')
PREPRINT_NOTICE = ('Preprint, not verified peer-reviewed evidence. Article screening is not '
                   'peer review; reported results do not establish strong causal evidence.')
COMMENTARY_NOTICE = ('Attributed commentary, not a study or measured findings. Main argument '
                     'checked from HTML; extraction and semantic completeness are not verified; '
                     'figures, supplements and linked claims were not independently checked.')


RECORD_FIELDS = ('kind', 'doi', 'url', 'title', 'venue', 'published',
                 'publication_date_provenance', 'research_type', 'source_version')


def record_context(record):
    return {k: record.get(k) for k in RECORD_FIELDS}


def record_digest(record):
    return hashlib.sha256(json.dumps(record_context(record), sort_keys=True,
                                    ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def is_preprint(record, source=None):
    from source_quality import PREPRINT
    source = source or {}
    identities = (record.get('doi'), source.get('source_doi'))
    urls = (record.get('url') or '', source.get('url') or '')
    versions = (str(record.get('source_version') or ''), str(source.get('version') or ''))
    return bool(PREPRINT.search(str(record.get('venue') or ''))
                or any(str(v or '').lower().startswith('10.48550/arxiv.') for v in identities)
                or any(re.search(r'preprint|working.paper|accepted.manuscript', v, re.I) for v in versions)
                or any(urlsplit(v).hostname in ('arxiv.org', 'www.arxiv.org', 'export.arxiv.org') for v in urls)
                or (record.get('publication_date_provenance') or {}).get('basis') == 'arxiv_first_submitted')



def valid_extension(note, record):
    from original_readings import text, valid_date
    gate = note.get('article_screen')
    if not isinstance(gate, dict) or set(gate) != {
            'record_sha256', 'decision', 'reviewer', 'checked_on', 'topic_fit',
            'methodological_assessment', 'limitations_assessment', 'peer_review_claimed',
            'strong_causal_evidence_claimed'}: return False
    if gate['record_sha256'] != record_digest(record) or gate['decision'] != 'acceptable': return False
    if gate['peer_review_claimed'] is not False or gate['strong_causal_evidence_claimed'] is not False: return False
    if not text(gate['reviewer'], 100) or not valid_date(gate['checked_on']): return False
    if not valid_date(record.get('published')) or record['published'] > gate['checked_on']: return False
    provenance = record.get('publication_date_provenance') or {}
    if not isinstance(provenance, dict) or provenance.get('status') in ('unresolved', 'conflict', 'conflicting', 'unknown'): return False
    if (provenance.get('value') or provenance.get('date')) != record['published']: return False
    if not gate['checked_on'] <= note['review']['checked_on'] <= note['publication']['approved_on']: return False
    for field in ('topic_fit', 'methodological_assessment', 'limitations_assessment'):
        if not text(gate[field], 1000) or len(gate[field].split()) < 6: return False
    if record['kind'] == 'scholarly':
        from source_quality import topic_class
        return topic_class(record) in ('direct', 'adjacent')
    c = note.get('commentary')
    if not isinstance(c, dict) or set(c) != {'genre', 'attributed_to', 'source_depth',
            'html_completeness', 'semantic_completeness', 'figures_checked',
            'supplements_checked', 'linked_claims_independently_verified', 'temporal'}: return False
    temporal = c['temporal']
    if not isinstance(temporal, dict) or set(temporal) != {'original_published', 'reported_modified', 'checked_on', 'historical_snapshot_verified'}: return False
    if temporal['original_published'] != record['published'] or temporal['checked_on'] != note['review']['checked_on']: return False
    if temporal['historical_snapshot_verified'] is not False: return False
    modified = temporal['reported_modified']
    if modified is not None and (not valid_date(modified) or not record['published'] <= modified <= temporal['checked_on']): return False
    if c['genre'] not in ('opinion', 'policy_analysis', 'reported_analysis', 'product_analysis',
                          'practical_advice', 'product_control_guidance'): return False
    if not text(c['attributed_to'], 200): return False
    if c['source_depth'] != 'main_argument_html': return False
    if c['html_completeness'] != 'not_verified' or c['semantic_completeness'] != 'not_verified': return False
    if any(c[k] is not False for k in ('figures_checked', 'supplements_checked', 'linked_claims_independently_verified')): return False
    source = note['source']
    return (not note['doi'] and not source['source_doi'] and not source['related_journal_doi']
            and source['format'] == 'html' and source['url'] == note['record_url'] == record['url']
            and urlsplit(source['url']).hostname not in ('news.google.com', 'google.com')
            and source['version'] == 'publisher_article')


def temporal_notice(temporal):
    modified = temporal['reported_modified'] or 'unknown'
    return (f"Limited reading of current publisher HTML. Originally published {temporal['original_published']}; "
            f"reported modification: {modified}; source checked {temporal['checked_on']}. "
            "No historical snapshot of the original publication was verified.")
