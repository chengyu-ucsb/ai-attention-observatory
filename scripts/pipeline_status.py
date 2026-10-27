"""Persist source shelves and expose the discovery/editorial/deployment boundary."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def build(root=ROOT):
    data = root / 'data'
    read = lambda name: json.loads((data / name).read_text(encoding='utf-8'))
    weekly, current, featured = (read(n) for n in ('public-weekly.json', 'public-issue.json', 'public-featured-issue.json'))
    date = weekly['run']['date']
    if current['edition_date'] != date:
        raise ValueError('Current editorial shelf and discovery week do not match; rebuild the current issue')
    # Archive the exact eligible shelf before the next discovery replaces it.
    folder = data / 'editorial-queue'
    folder.mkdir(exist_ok=True)
    (folder / (date + '.json')).write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    pending = []
    approved = data / 'approved-issues'
    for file in sorted(folder.glob('*.json')):
        packet = json.loads(file.read_text(encoding='utf-8'))
        approved_path = approved / file.name
        is_approved = approved_path.exists() and json.loads(approved_path.read_text(encoding='utf-8')).get('status') == 'published'
        if packet.get('status') != 'published' and not is_approved:
            pending.append(packet['edition_date'])
    status = {
        'discovery_date': date,
        'discovery_status': weekly['run'].get('stats', {}).get('discovery_status', 'unknown'),
        'source_backed_weekly_count': len(weekly['items']),
        'featured_issue_date': featured.get('edition_date'),
        'editorial_status': current['status'],
        'pending_editorial_dates': pending,
        'canonical_source': 'Website repository: discovery → readings → weekly edition → RSS',
        'delivery_feed': 'https://chengyu-ucsb.github.io/ai-attention-observatory/issue-feed.xml',
        'delivery_json_feed': 'https://chengyu-ucsb.github.io/ai-attention-observatory/data/issue-feed.json',
        'source_nominations': 'Optional verified DOI/URL leads; routine discovery does not depend on chat',
        'publication': 'Built payload; successful Pages deployment must be verified in Actions',
    }
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
