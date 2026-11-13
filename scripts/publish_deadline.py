"""A small, model-independent Monday publication boundary.

Never turn a failed synthesis into accepted research. When no checked edition
is ready at the cutoff, publish an explicitly labelled coverage update using
only eligible source metadata. A later checked edition keeps the same URL.
This path uses no model, database connection, or external retrieval.
"""
from __future__ import annotations
import datetime as dt
import argparse
import json
import os
from pathlib import Path

from build_issue import source_id, citation_url, checked_source_metadata
from collection_window import previous_week, weekly_eligible, window_metadata
from edition_schedule import canonical_edition_date, release_cutoff
from original_readings import public_record

ROOT = Path(__file__).resolve().parents[1]


def same_window(issue, window):
    try:
        actual = window_metadata(issue['edition_date'])
    except (KeyError, TypeError, ValueError):
        return False
    declared = issue.get('publication_window') or actual
    return all(actual[k] == declared.get(k) == window[k] for k in ('from', 'to', 'timezone'))


def published_in_window(root, window):
    return [value for path in sorted((root / 'data/approved-issues').glob('????-??-??.json'))
            if (value := json.loads(path.read_text())).get('status') == 'published'
            and same_window(value, window)]


def eligible_shelf(root, date):
    path = root / 'data/editorial-weekly.json'
    if not path.exists():
        path = root / 'data/public-weekly.json'
    if not path.exists():
        return []
    packet = json.loads(path.read_text())
    # Old discovery is an outage, not a new week's evidence. Do not relabel it.
    packet_date = (packet.get('run') or {}).get('date')
    if not packet_date or window_metadata(packet_date) != window_metadata(date):
        return []
    items, seen = [], set()
    for item in packet.get('items', []):
        try:
            current = public_record(item, require_current=True)
            if item.get('original_reading') != current.get('original_reading'):
                continue
            if (current.get('reading') or {}).get('level') == 'citation_only':
                continue
            if not weekly_eligible(current, *previous_week(date)):
                continue
            ident = source_id(current)
            if not ident or ident in seen:
                continue
            citation_url(current)
        except (ValueError, KeyError, TypeError):
            continue  # A bad record cannot be promoted by the deadline path.
        seen.add(ident)
        items.append(current)
    return items


def coverage_issue(date, number, items, *, published_at=None):
    sources = [{
        'id': source_id(x), 'title': x['title'], 'url': x.get('url', ''),
        'kind': x.get('kind', ''), 'venue': x.get('venue', ''),
        'published': x.get('published', ''),
        'publication_date_provenance': x.get('publication_date_provenance', {}),
        'reading_level': x['reading']['level'],
        'editorial_role': 'collection_week', **checked_source_metadata(x),
    } for x in items]
    return coverage_from_sources(date, number, sources, published_at=published_at)


def coverage_from_sources(date, number, sources, *, published_at=None):
    """All public wording is fixed; no rejected prose can reach this path."""
    date = canonical_edition_date(None, date)
    count = len(sources)
    timestamp = {}
    if published_at is not None:
        actual = dt.datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        if actual.tzinfo is None:
            raise ValueError('First publication timestamp must include a timezone')
        timestamp['published_at'] = actual.astimezone(dt.timezone.utc).isoformat()
    headline = 'This week’s reading list and evidence check'
    return {
        'edition_date': date, 'number': number, 'status': 'published', **timestamp,
        'edition_format': 'coverage', 'coverage_template_version': 1,
        'publication_window': window_metadata(date),
        'source_count': count, 'sources': sources,
        'types': {'scholarly': sum(x['kind'] == 'scholarly' for x in sources),
                  'commentary': sum(x['kind'] != 'scholarly' for x in sources)},
        'material': {key: sum(x['reading_level'] == level for x in sources)
                     for key, level in [('full_text', 'full_text'), ('abstract', 'abstract'),
                                        ('publisher_or_editorial', 'curated')]},
        'subject': f'The Attention Brief #{number} — {headline}',
        'headline': headline,
        'deck': 'Coverage update: this week’s research synthesis is still under review. '
                'The available source shelf is below; no new findings or cross-paper conclusions are being endorsed in this update.',
        'letter': f'This week’s eligible reading shelf contains {count} source-backed records. '
                  'These are records with substantive source material and a verified publication date in the covered week. '
                  'Availability does not establish the quality of an individual study or mean that a summary has passed review. '
                  'A complete synthesis is not ready. This dated update keeps the weekly archive current and makes the coverage gap visible. '
                  'A checked analysis can replace this update at the same permanent link.',
        'signals': [{'short': 'Coverage update', 'title': 'Read the available originals',
                     'text': ('The source shelf links to the available originals and identifies the material available for each record. '
                              'Treat an abstract as a limited account and distinguish a research report from commentary. '
                              'The shelf is a starting point for reading; it is not a claim that every relevant publication was found.'
                              if count else
                              'No eligible source-backed records are available for this edition yet. '
                              'This does not show that nothing relevant was published. Source acquisition or verification may be incomplete. '
                              'Older articles and unverified search results have not been presented as this week’s evidence.'),
                     'sources': [], 'source_ids': []}],
        'tension': {'title': 'What remains open',
                    'text': 'The evidence synthesis remains pending. Until it is checked, this update makes no claim about whether AI helps or harms attention, learning, or wellbeing. '
                            'When reading the linked material, ask what was measured, whose experience was represented, and whether a conclusion concerns association, interpretation, or a tested intervention.',
                    'sources': [], 'source_ids': []},
        'closer': 'Which claims can the available designs support, and which questions still need better evidence?',
        'experiment': {'title': 'Keep a reading question',
                       'text': 'Choose one source and write down a question its design can answer and a question it leaves open.',
                       'caution': 'A reading prompt, not a tested attention intervention.'},
        'editorial_note': 'Coverage update assembled from eligible source metadata without model inference. '
                          'Research synthesis is pending. Rejected drafts have not been promoted to findings. '
                          'Source availability and publication dates were checked; this is not a methodological endorsement or an independent expert review.',
        'note': 'Published coverage update; research synthesis pending.',
    }


def validate_coverage(issue):
    if issue.get('edition_format') != 'coverage':
        return
    expected = coverage_from_sources(issue['edition_date'], issue['number'], issue['sources'],
                                     published_at=issue.get('published_at'))
    if issue != expected:
        raise ValueError('Coverage updates must contain only the fixed, transparent coverage template')
    seen = set()
    for source in issue['sources']:
        if source['id'] in seen or source.get('reading_level') == 'citation_only':
            raise ValueError('Invalid coverage source')
        seen.add(source['id'])
        citation_url(source)
        if not weekly_eligible(source, *previous_week(issue['edition_date'])):
            raise ValueError('Coverage source is outside the verified publication window')


def publish(root=ROOT, now=None, *, dry_run=False):
    now = now or dt.datetime.now(dt.timezone.utc)
    date = canonical_edition_date(root, now)
    if not release_cutoff(now):
        return {'status': 'before_cutoff', 'changed': False}
    existing = published_in_window(root, window_metadata(date))
    if existing:
        return {'status': 'edition_exists', 'changed': False,
                'edition_format': existing[-1].get('edition_format', 'full'),
                'edition_date': existing[-1]['edition_date']}
    # Prefer a fully built, checked edition that has not been archived yet.
    current_path = root / 'data/public-issue.json'
    if current_path.exists():
        current = json.loads(current_path.read_text())
        if current.get('status') == 'published' and same_window(current, window_metadata(date)):
            return {'status': 'checked_edition_ready', 'changed': False}
    if dry_run:
        return {'status': 'coverage_due', 'changed': False}
    folder = root / 'data/approved-issues'
    folder.mkdir(parents=True, exist_ok=True)
    number = f'{len(list(folder.glob("????-??-??.json")))+1:02d}'
    issue = coverage_issue(date, number, eligible_shelf(root, date),
                           published_at=now.astimezone(dt.timezone.utc).isoformat())
    validate_coverage(issue)
    (folder / (date + '.json')).write_text(json.dumps(issue, ensure_ascii=False, indent=2) + '\n')
    return {'status': 'coverage_published', 'changed': True, 'edition_date': date,
            'source_count': issue['source_count'], 'synthesis_status': 'pending'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args=parser.parse_args()
    result = publish(dry_run=args.check)
    if args.check and os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write('needed='+str(result['status'] in ('coverage_due','checked_edition_ready')).lower()+'\n')
    print(json.dumps(result))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write('Monday release: ' + result['status'] + '\n\n')
            if result['status'] == 'coverage_published':
                out.write('A clearly labelled coverage update is published. Research synthesis remains pending; no rejected claims were released.\n')
