"""Build a small reader index and immutable, on-demand article payloads.

Only the already screened public library is an input. Operational state and
pending source bodies must never enter this export. The edition retains its canonical archive digest
and displays a separately verifiable public projection.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
from pathlib import Path

from reading_headlines import reader_genre, reader_headline
from reader_issue import feed_snapshot
from article_art import canonical_identity
from article_art_queue import review_fingerprint

ROOT = Path(__file__).resolve().parents[1]
CARD_FIELDS = ('title', 'display_headline', 'authors', 'published', 'venue', 'doi', 'url', 'kind',
               'lane', 'relation', 'source', 'first_seen', 'source_group',
               'format', 'source_type', 'reader_genre', 'research_type', 'legacy_urls', 'companion_to')
READING_FIELDS = ('level', 'original_summary', 'research_type', 'source_format',
                  'source_version', 'source_url', 'source_doi', 'related_journal_doi',
                  'genre', 'attributed_to')
DIGEST_FIELDS = ('idea', 'explain', 'explain_source', 'status', 'finding_source', 'editorial_basis')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()


def immutable(data, folder, value):
    raw = encoded(value)
    relative = Path('reader') / folder / (sha256(raw).hexdigest() + '.json')
    target = data / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return 'data/' + relative.as_posix()


def pick(record, fields):
    return {key: record[key] for key in fields if key in record}


def article(record):
    # Select reader fields explicitly. Internal acquisition metadata, checks,
    # fingerprints and per-field evidence receipts stay in the editorial index.
    page = pick(record, CARD_FIELDS + ('abstract_text', 'abstract_source', 'preview',
                                      'framework_notes', 'visual'))
    if record.get('source_review'):
        page['source_review'] = pick(record['source_review'], ('source_url',))
    if record.get('analysis'):
        page['analysis'] = pick(record['analysis'], ('fulltext_url', 'methods', 'results',
                                'discussion', 'limitations', 'original_paraphrases_only', 'figures'))
    if record.get('editorial_art'):
        page['editorial_art'] = pick(record['editorial_art'], ('kind', 'status', 'src',
                                   'thumbnail_src', 'alt', 'width', 'height'))
    reading = record.get('reading') or {}
    detail = pick(reading, READING_FIELDS + ('original_summary_id', 'source_sha256', 'overview',
                  'methods', 'findings', 'interpretation', 'limitations', 'reported_findings'))
    digest = reading.get('digest') or {}
    if reading.get('machine_account'):
        detail['machine_account'] = reading['machine_account']
    detail['digest'] = pick(digest, DIGEST_FIELDS + ('approach', 'finding', 'interpretation',
                              'limitation', 'approach_source', 'limitation_source', 'tags'))
    if digest.get('longform'):
        fields = ('source_depth', 'source_url', 'review_status', 'thesis', 'reasoning', 'examples', 'tension', 'qualification',
                  'research_question', 'study_design', 'reported_results', 'authors_interpretation',
                  'limitations')
        detail['digest']['longform'] = pick(digest['longform'], fields)
    page['reading'] = detail
    return page


def card(record, article_url):
    reading = record.get('reading') or {}
    digest = reading.get('digest') or {}
    result = pick(record, CARD_FIELDS + ('editorial_art',))
    result['reading'] = {key: reading[key] for key in READING_FIELDS if key in reading}
    if reading.get('machine_account'):
        result['reading']['machine_account'] = {k: v for k, v in reading['machine_account'].items()
            if k in ('research_question', 'study_design', 'review_status') and len(v) <= 430}
    result['reading']['digest'] = {key: digest[key] for key in DIGEST_FIELDS if key in digest}
    # Presence is sufficient for collection statistics/ranking; no findings are
    # shortened into a new public assertion in the index.
    result['has_finding'] = bool(digest.get('finding'))
    result['has_methods'] = bool(reading.get('methods'))
    result['has_limitations'] = bool(reading.get('limitations'))
    result['analysis'] = {key: record['analysis'][key] for key in
                         ('fulltext_url', 'original_paraphrases_only')
                         if key in (record.get('analysis') or {})}
    longform = digest.get('longform') or {}
    if longform.get('source_depth'):
        result['reading']['digest']['longform'] = {'source_depth': longform['source_depth']}
    if digest.get('status') == 'automatically_condensed_source_text' and record.get('abstract_text'):
        # The card displays only complete opening sentences from the public excerpt.
        result['card_abstract'] = record['abstract_text'][:520]
    # Preserve phrase-search order using only already screened public fields.
    search_values = [record.get('abstract_text', ''), record.get('preview', ''),
                     reading.get('findings', ''), reading.get('methods', '')]
    search_values += [v for v in digest.values() if isinstance(v, str)]
    result['search_text'] = ' '.join(' '.join(search_values).split()).lower()
    result['article_payload'] = article_url
    return result


def build(root=ROOT, *, pages_data=None):
    data = Path(root) / 'data'
    records = json.loads((data / 'public-library.json').read_text())
    if not isinstance(records, list) or any((r.get('reading') or {}).get('level') in (None, 'citation_only') for r in records):
        raise ValueError('reader_requires_screened_public_library')
    issue = json.loads((data / 'public-featured-issue.json').read_text())
    if issue.get('status') != 'published':
        issue = {}  # An unfinished draft is not a public edition.
    destination = Path(pages_data) if pages_data else data
    if pages_data and destination.resolve() == data.resolve():
        raise ValueError('Pages compatibility files need a separate destination from editorial inputs')
    destination.mkdir(parents=True, exist_ok=True)
    weekly = json.loads((data / 'public-weekly.json').read_text())
    commission_state = data / 'article-art-state.json'
    commissioning = {}
    if commission_state.is_file():
        commissioning = json.loads(commission_state.read_text(encoding='utf-8')).get('commissioning', {})
    if commissioning or (data / 'article-art-overrides.json').is_file():
        approved = commissioning.get('approved', {})
        for record in [*records, *weekly.get('items', [])]:
            identity = canonical_identity(record)
            cover = record.get('editorial_art') or {}
            if approved.get(identity) != review_fingerprint(identity, cover):
                raise ValueError(f'reader_requires_reviewed_commission: {identity}')
    pages = [article(record) for record in records]
    cards = [card(page, immutable(destination, 'articles', page)) for page in pages]
    index_url = immutable(destination, 'indexes', cards)
    run = weekly.get('run') or {}
    backlog_path = data / 'fulltext-backfill-state.json'
    backlog = json.loads(backlog_path.read_text()) if backlog_path.exists() else {}
    # The canonical digest addresses the archived publication; public formats use the reader digest.
    # Display metadata accompanies that frozen record, including older shelves.
    current = {row.get('doi') or row.get('url'): row for row in records}
    source_labels = {}
    for source in issue.get('sources', []):
        key = source.get('id')
        if key:
            row = current.get(key) or source
            source_labels[key] = {'display_headline': reader_headline(row), 'reader_genre': reader_genre(row)}
    published = feed_snapshot(issue)
    manifest = {'schema_version': 1, 'source_labels': source_labels, 'edition_id': issue.get('edition_date'),
                'edition_sha256': sha256(encoded(issue)).hexdigest(), 'issue': published,
                'reader_sha256': sha256(encoded(published)).hexdigest(),
                'index_url': index_url,
                'collection': {'date': run.get('date'), 'mode': run.get('mode'),
                               'publication_window': run.get('publication_window'),
                               'last_seven_days': len(weekly.get('items', []))},
                'backlog': {key: backlog[key] for key in
                            ('total_scholarly','full_text_extracted','ready_for_attempt','status')
                            if key in backlog},
                'library_count': sum(not r.get('companion_to') for r in records)}
    (destination / 'reader-manifest.json').write_bytes(encoded(manifest))
    if pages_data:
        # Publish only the pending canonical IDs from this build. Acquisition,
        # review notes and the internal state never enter this public handoff.
        if commissioning:
            pending = commissioning["pending"]
            (destination / "art-commissions.json").write_bytes(encoded({"pending": sorted(pending)}))
        current = json.loads((data / 'public-issue.json').read_text())
        if current.get('status') == 'published':
            public_issue = feed_snapshot(current)
        else:
            public_issue = pick(current, ('edition_date', 'publication_window', 'status'))
            public_issue.update(sources=[], source_count=0)
        collection = pick(run, ('date', 'mode', 'publication_window', 'last_seven_days',
                                'reading_eligible_count', 'full_text_count', 'abstract_count'))
        weekly_articles = []
        for row in weekly.get('items', []):
            if (row.get('reading') or {}).get('level') in (None, 'citation_only'):
                raise ValueError('reader_requires_screened_public_weekly_items')
            weekly_articles.append(article(row))
        exports = {'public-library': pages,
                   'public-weekly': {'run': collection, 'items': weekly_articles},
                   'public-featured-issue': published if published else {'status': 'none'},
                   'public-issue': public_issue}
        for name, value in exports.items():
            (destination / (name + '.json')).write_bytes(encoded(value))
    return {'manifest_bytes': len(encoded(manifest)), 'index_bytes': len(encoded(cards)),
            'articles': len(records), 'edition_id': manifest['edition_id']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages-data', type=Path, help='Generate deployable reader URLs in this data directory.')
    print(json.dumps(build(pages_data=parser.parse_args().pages_data)))
