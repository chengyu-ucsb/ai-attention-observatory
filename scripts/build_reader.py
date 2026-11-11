"""Build a small reader index and immutable, on-demand article payloads.

Only the already screened public library is an input. Operational state and
pending source bodies must never enter this export. The edition is an exact
published snapshot; latest discovery cannot replace its source shelf.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD_FIELDS = ('title', 'authors', 'published', 'venue', 'doi', 'url', 'kind',
               'lane', 'relation', 'source', 'first_seen', 'source_group',
               'format', 'research_type', 'legacy_urls', 'companion_to', 'editorial_art')
READING_FIELDS = ('level', 'original_summary', 'research_type', 'notice',
                  'review_label', 'review_scope', 'quality_note', 'temporal_notice',
                  'source_version', 'source_url', 'source_doi', 'related_journal_doi',
                  'genre', 'attributed_to')
DIGEST_FIELDS = ('idea', 'explain', 'status', 'finding_source', 'editorial_basis')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()


def immutable(data, folder, value):
    raw = encoded(value)
    relative = Path('reader') / folder / (sha256(raw).hexdigest() + '.json')
    target = data / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return 'data/' + relative.as_posix()


def card(record, article_url):
    reading = record.get('reading') or {}
    digest = reading.get('digest') or {}
    result = {key: record[key] for key in CARD_FIELDS if key in record}
    result['reading'] = {key: reading[key] for key in READING_FIELDS if key in reading}
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
    # Preserve phrase-search order using only already screened public fields.
    search_values = [record.get('abstract_text', ''), record.get('preview', ''),
                     reading.get('findings', ''), reading.get('methods', '')]
    search_values += [v for v in digest.values() if isinstance(v, str)]
    result['search_text'] = ' '.join(' '.join(search_values).split()).lower()
    result['article_payload'] = article_url
    return result


def build(root=ROOT):
    data = Path(root) / 'data'
    records = json.loads((data / 'public-library.json').read_text())
    if not isinstance(records, list) or any((r.get('reading') or {}).get('level') in (None, 'citation_only') for r in records):
        raise ValueError('reader_requires_screened_public_library')
    issue = json.loads((data / 'public-featured-issue.json').read_text())
    if issue.get('status') != 'published':
        issue = {}  # An unfinished draft is not a public edition.
    cards = [card(row, immutable(data, 'articles', row)) for row in records]
    index_url = immutable(data, 'indexes', cards)
    weekly = json.loads((data / 'public-weekly.json').read_text())
    run = weekly.get('run') or {}
    backlog_path = data / 'fulltext-backfill-state.json'
    backlog = json.loads(backlog_path.read_text()) if backlog_path.exists() else {}
    manifest = {'schema_version': 1, 'edition_id': issue.get('edition_date'),
                'edition_sha256': sha256(encoded(issue)).hexdigest(), 'issue': issue,
                'index_url': index_url,
                'collection': {'date': run.get('date'), 'mode': run.get('mode'),
                               'publication_window': run.get('publication_window'),
                               'last_seven_days': len(weekly.get('items', []))},
                'backlog': {key: backlog[key] for key in
                            ('total_scholarly','full_text_extracted','ready_for_attempt','status')
                            if key in backlog},
                'library_count': sum(not r.get('companion_to') for r in records)}
    (data / 'reader-manifest.json').write_bytes(encoded(manifest))
    return {'manifest_bytes': len(encoded(manifest)), 'index_bytes': len(encoded(cards)),
            'articles': len(records), 'edition_id': manifest['edition_id']}


if __name__ == '__main__':
    print(json.dumps(build()))
