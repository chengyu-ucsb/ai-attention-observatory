"""Freeze all eligible sources published in the previous completed UTC week.

Library acquisition and historical context remain separate. A nomination,
rediscovery or first_seen date can never override publication boundaries.
The public builder still enforces substantive reading and source quality.
"""
import json
from pathlib import Path
from collection_window import previous_week, weekly_eligible, window_metadata
from update import diverse_week

ROOT = Path(__file__).resolve().parents[1]


def select(records, date):
    start, end = previous_week(date)
    return diverse_week([x for x in records if weekly_eligible(x, start, end)])


def build(root=ROOT):
    data = root / 'data'
    library = json.loads((data / 'library.json').read_text(encoding='utf-8'))
    week = json.loads((data / 'weekly.json').read_text(encoding='utf-8'))
    week['items'] = select(library, week['run']['date'])
    week['run']['last_seven_days'] = len(week['items'])
    week['run']['total'] = len(library)
    week['run']['publication_window'] = window_metadata(week['run']['date'])
    week['run']['selection_basis'] = 'original_publication_date_previous_completed_week'
    (data / 'weekly.json').write_text(json.dumps(week, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'weekly_candidates': len(week['items']), 'date': week['run']['date'],
                      'publication_window': week['run']['publication_window']}))


if __name__ == '__main__':
    build()
