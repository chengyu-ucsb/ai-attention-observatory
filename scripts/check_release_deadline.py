"""Check the actual live synthesis, not a green job or a coverage placeholder."""
import datetime as dt
from hashlib import sha256
import json
import os
from pathlib import Path

from build_reader import encoded
from reader_issue import feed_snapshot
from verify_publication import BASE, fetch, verify
from worker_schedule import publication_target

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT, now=None, reader=fetch):
    now = now or dt.datetime.now(dt.timezone.utc)
    target = publication_target(now)
    edition = target['target_collection_week']
    result = {'ready': False, 'edition_date': edition,
              'observed_at': now.isoformat(), 'deadline': target['target_at'],
              'verification_target': target['verification_target_at'],
              'deadline_elapsed': target['deadline_elapsed']}
    path = Path(root) / 'data/approved-issues' / (edition + '.json')
    if not path.exists():
        return dict(result, status='missing_synthesis')
    issue = json.loads(path.read_text())
    if issue.get('edition_format') == 'coverage':
        return dict(result, status='coverage_only_not_a_newsletter')
    if (issue.get('status') != 'published' or issue.get('edition_date') != edition
            or issue.get('edition_format', 'full') not in ('full', 'compact')):
        return dict(result, status='unpublished_or_wrong_edition')
    try:
        manifest = json.loads(reader(BASE + 'data/reader-manifest.json'))
        expected = {'edition_id': edition,
                    'edition_sha256': sha256(encoded(issue)).hexdigest(),
                    'reader_sha256': sha256(encoded(feed_snapshot(issue))).hexdigest(),
                    'index_url': manifest.get('index_url')}
        verified = verify(expected, reader=reader)
    except Exception as error:
        return dict(result, status='live_verification_failed',
                    reason=type(error).__name__ + ': ' + str(error)[:240])
    return dict(result, ready=True, status='live_synthesis_verified',
                permanent_url=verified['permanent_url'],
                edition_sha256=verified['edition_sha256'])


def main():
    result = check()
    print(json.dumps(result))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write('## Monday release check\n\n' + result['status'] + '\n\n'
                      + 'Edition: ' + result['edition_date'] + '\n\n'
                      + 'Deadline: ' + result['deadline'] + '\n\n')
            if not result['ready']:
                out.write('Inspect source admission, final readings, synthesis and deployment. '
                          'A coverage notice does not meet the newsletter deadline.\n')
    if not result['ready']:
        print('::error::Monday newsletter is not verified live: ' + result['status'])
        raise SystemExit(1)


if __name__ == '__main__':
    main()
