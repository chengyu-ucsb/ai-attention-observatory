"""Freeze the complete discovery-week membership after all intake stages.

The library is the acquisition index; build_public still enforces reading quality.
This stage does not claim all sources were published during the discovery week.
"""
import datetime as dt
import json
from pathlib import Path
from update import diverse_week

ROOT = Path(__file__).resolve().parents[1]

def select(records, date):
    start = (dt.date.fromisoformat(date) - dt.timedelta(days=6)).isoformat()
    return diverse_week([x for x in records if (
        start <= x.get('first_seen', '') <= date
        and not x.get('curated')
        and not x.get('historical_backfill')
        and not str(x.get('discovery_scope', '')).startswith('historical:')
    ) or x.get('brief_provenance', {}).get('week') == date], limit=len(records))

def build(root=ROOT):
    data = root / 'data'
    library = json.loads((data / 'library.json').read_text(encoding='utf-8'))
    week = json.loads((data / 'weekly.json').read_text(encoding='utf-8'))
    week['items'] = select(library, week['run']['date'])
    week['run']['last_seven_days'] = len(week['items'])
    week['run']['total'] = len(library)
    week['run']['selection_basis'] = 'Complete discovery-week set plus verified brief nominations; historical backfills excluded'
    (data / 'weekly.json').write_text(json.dumps(week, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'weekly_candidates': len(week['items']), 'date': week['run']['date']}))

if __name__ == '__main__':
    build()
