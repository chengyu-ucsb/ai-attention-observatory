"""Persist source shelves and expose the discovery/editorial/deployment boundary."""
import datetime as dt
import json
from pathlib import Path
from collection_window import window_metadata

ROOT = Path(__file__).resolve().parents[1]


def weekly_freshness(discovery_date, published_date, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    monday = today - dt.timedelta(days=today.weekday())
    start = monday.isoformat()
    discovery_current = bool(discovery_date and start <= discovery_date <= today.isoformat())
    publication_current = bool(published_date and start <= published_date <= today.isoformat())
    return {
        'expected_collection_week': start,
        'discovery_current': discovery_current,
        'publication_current': publication_current,
        'pipeline_health': (
            'stale_discovery' if not discovery_current else
            'awaiting_publication' if not publication_current else
            'current'
        ),
    }


def build(root=ROOT):
    data = root / 'data'
    read = lambda name: json.loads((data / name).read_text(encoding='utf-8'))
    weekly, current, featured = (read(n) for n in ('public-weekly.json', 'public-issue.json', 'public-featured-issue.json'))
    date = weekly['run']['date']
    if window_metadata(current['edition_date']) != window_metadata(date):
        raise ValueError('Current editorial shelf and discovery week do not match; rebuild the current issue')
    # Archive the exact eligible shelf before the next discovery replaces it.
    folder = data / 'editorial-queue'
    folder.mkdir(exist_ok=True)
    (folder / (date + '.json')).write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending = []
    approved = data / 'approved-issues'
    published_windows = {window_metadata(json.loads(p.read_text()).get('edition_date') or p.stem)['from']
                         for p in approved.glob('????-??-??.json')
                         if json.loads(p.read_text()).get('status') == 'published'}
    for file in sorted(folder.glob('*.json')):
        packet = json.loads(file.read_text(encoding='utf-8'))
        approved_path = approved / file.name
        is_approved = approved_path.exists() and json.loads(approved_path.read_text(encoding='utf-8')).get('status') == 'published'
        if (packet.get('status') != 'published' and not is_approved
                and window_metadata(packet['edition_date'])['from'] not in published_windows):
            pending.append(packet['edition_date'])
    status = {
        'discovery_date': date,
        'publication_window': weekly['run'].get('publication_window'),
        'discovery_status': weekly['run'].get('stats', {}).get('discovery_status', 'unknown'),
        'source_backed_weekly_count': len(weekly['items']),
        'editorial_source_count': len(current.get('sources', [])),
        'editorial_context_source_count': sum(
            x.get('editorial_role') == 'previously_indexed_context'
            for x in current.get('sources', [])
        ),
        'featured_issue_date': featured.get('edition_date'),
        'editorial_status': current['status'],
        'pending_editorial_dates': pending,
        'canonical_source': 'Website repository: discovery → readings → weekly edition → RSS',
        'delivery_feed': 'https://chengyu-ucsb.github.io/ai-attention-observatory/issue-feed.xml',
        'delivery_json_feed': 'https://chengyu-ucsb.github.io/ai-attention-observatory/data/issue-feed.json',
        'source_nominations': 'Optional verified DOI/URL leads; routine discovery does not depend on chat',
        'publication': 'Built payload; successful Pages deployment must be verified in Actions',
    }
    editorial=weekly['run'].get('stats',{}).get('editorial_feeds',{})
    if editorial.get('status'):
        status['editorial_discovery_status']=editorial['status']
    status.update(weekly_freshness(date, featured.get('edition_date')))
    status['edition_format'] = featured.get('edition_format', 'full')
    status['synthesis_current'] = status['publication_current'] and featured.get('edition_format') != 'coverage'
    if status['publication_current'] and not status['synthesis_current']:
        status['pipeline_health'] = 'coverage_only'
    from worker_schedule import publication_target
    status['publication_target'] = publication_target()
    if not status['publication_current']:
        status['reader_notice'] = (
            'This week’s edition has not been published yet. '
            if status['publication_target']['deadline_elapsed'] else
            'This week’s edition is being prepared for Monday. '
        ) + ('The latest published edition is ' + featured.get('edition_date', 'unavailable') + '.')
    elif not status['synthesis_current']:
        status['reader_notice'] = 'This week’s coverage update is available. The research synthesis is still under review.'
    else:
        status['reader_notice'] = ''
    if status['pipeline_health'] != 'current':
        print('::warning::Observatory publication health: ' + status['pipeline_health'])
    intake = data / 'brief-intake-status.json'
    if intake.exists():
        from collections import Counter
        status['brief_intake_counts'] = dict(Counter(x['status'] for x in json.loads(intake.read_text(encoding='utf-8'))))
    import os
    if os.getenv('GITHUB_SHA'):
        import subprocess
        # workflow_run's event SHA can differ from the main revision checked out.
        status['build_revision'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
        status['build_run_url'] = 'https://github.com/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    (data / 'pipeline-status.json').write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(status))
    if pending:
        print('::warning::Weekly edition not yet published for ' + ', '.join(pending))
    return status

if __name__ == '__main__':
    build()

