"""Check the actual live synthesis, not a green job or a coverage placeholder."""
import argparse
import datetime as dt
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time

from build_reader import encoded
from reader_issue import feed_snapshot
from verify_publication import BASE, LiveContentMismatch, fetch, verify
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
            or issue.get('synthesis_current') is False
            or issue.get('edition_format', 'full') not in ('full', 'compact')):
        return dict(result, status='unpublished_or_wrong_edition')
    try:
        manifest = json.loads(reader(BASE + 'data/reader-manifest.json'))
        expected = {'edition_id': edition,
                    'edition_sha256': sha256(encoded(issue)).hexdigest(),
                    'reader_sha256': sha256(encoded(feed_snapshot(issue))).hexdigest(),
                    'index_url': manifest.get('index_url')}
        verified = verify(expected, reader=reader, approved_issue=issue)
    except LiveContentMismatch as error:
        return dict(result, status='live_content_mismatch', reason=str(error),
                    recovery_key=edition + '-' + expected['edition_sha256'])
    except Exception as error:
        return dict(result, status='live_verification_failed',
                    reason=type(error).__name__ + ': ' + str(error)[:240])
    return dict(result, ready=True, status='live_synthesis_verified',
                permanent_url=verified['permanent_url'],
                edition_sha256=verified['edition_sha256'])


def pages_runs(edition):
    repo = os.environ['GITHUB_REPOSITORY']
    # A Monday recovery cannot predate its edition. Include the prior day for
    # deployments already queued when the UTC date changed.
    since = dt.date.fromisoformat(edition) - dt.timedelta(days=1)
    endpoint = (f'repos/{repo}/actions/workflows/publish.yml/runs?branch=main'
                f'&created=%3E%3D{since}&per_page=100')
    raw = subprocess.check_output(
        ['gh', 'api', '--paginate', endpoint, '--jq',
         '.workflow_runs[] | {status, display_title} | @json'], text=True)
    return [json.loads(line) for line in raw.splitlines()]


def request_pages(key):
    subprocess.run(['gh', 'workflow', 'run', 'publish.yml', '--ref', 'main',
                    '-f', 'recovery_for=' + key], check=True)


def recover(result, *, read=check, runs=pages_runs, dispatch=request_pages,
            pause=time.sleep, clock=time.monotonic):
    key = result.get('recovery_key')
    if not key:
        return result
    title = 'Restore edition ' + key
    dispatched = False
    deadline = clock() + 15 * 60
    while clock() < deadline:
        history = runs(result['edition_date'])
        active = any(run['status'] != 'completed' for run in history)
        if not active:
            if any(run['display_title'] == title for run in history):
                # The one repair for this revision has finished. Read after it.
                return read()
            if not dispatched:
                print('Requesting Pages recovery for ' + key, flush=True)
                dispatch(key)
                dispatched = True
        pause(20)
        result = read()
        if result.get('recovery_key') != key:
            return result
    return dict(result, reason='Pages recovery did not verify within 15 minutes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--recover', action='store_true')
    mode.add_argument('--before-deploy', metavar='RECOVERY_KEY')
    options = parser.parse_args()
    result = check()
    if options.before_deploy:
        # The Pages concurrency lock is already held. A preceding deployment
        # may have fixed this mismatch or a newer editorial may be approved.
        if result['status'] == 'live_verification_failed':
            raise SystemExit('Could not verify live content before recovery deployment')
        needed = result.get('recovery_key') == options.before_deploy
        with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
            out.write('needed=' + str(needed).lower() + '\n')
        print(json.dumps(result))
        return
    if options.recover:
        result = recover(result)
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
