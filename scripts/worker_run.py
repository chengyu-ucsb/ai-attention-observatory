"""Lease a bounded reading pass and record its actual, input-bound outcome.

Only the lease token is kept in RUNNER_TEMP while a job runs. The operational
record is in Supabase; validated readings are saved by the established Git writer.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from observatory_store import fingerprint
from observatory_remote_store import RemoteStore
from preparation_pipeline import (ROOT, read, folder_for, target_window,
                                  validate_reading_receipt)


def input_hash(root, phase, now):
    folder = folder_for(root, now, phase)
    inputs = {name: read(folder/name) if (folder/name).exists() else None
              for name in ('packet.json', 'acquisition.json', 'readings.json')}
    # A fixed input set can be retried after a code or model-policy correction.
    from hashlib import sha256
    policy = {name: sha256((Path(root)/'scripts'/name).read_bytes()).hexdigest() for name in
              ('prepared_article_readings.py', 'comprehensive_readings.py', 'reading_progress.py', 'worker_run.py')}
    return fingerprint({'phase': phase, 'inputs': inputs, 'policy': policy})


def begin(root, phase, lease_path, store, now=None):
    now = now or datetime.now(timezone.utc)
    week = target_window(now, phase)['from']
    lease = store._call('begin_run', phase=phase, week=week, inputs_hash=input_hash(root, phase, now))
    if type(lease.get('claimed')) is not bool:
        raise ValueError('invalid_lease_receipt')
    if lease['claimed']:
        for key in ('id', 'lease_token'):
            if not re.fullmatch(r'[0-9a-f-]{36}', str(lease.get(key, ''))):
                raise ValueError('invalid_lease_receipt')
        # Keep credentials out of repository files, step outputs and logs.
        lease_path = Path(lease_path)
        lease_path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(lease_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as out:
            json.dump({**lease, 'phase': phase, 'week': week}, out)
    return {k: v for k, v in lease.items() if k != 'lease_token'}


def outcome(root, lease, saved_commit, now=None):
    now = now or datetime.now(timezone.utc)
    receipt = read(Path(root)/'data/weekly-preparation'/lease['week']/'reading-run.json')
    validate_reading_receipt(receipt, 'preparation_reading_run', now)
    if receipt['phase'] != lease['phase'] or receipt['publication_window']['from'] != lease['week']:
        raise ValueError('worker_receipt_scope_mismatch')
    if not re.fullmatch(r'[0-9a-f]{40}', saved_commit):
        raise ValueError('saved_commit_required')
    review = receipt['stages']['review']
    return {'phase': lease['phase'], 'week': lease['week'], 'reading_run_sha256': fingerprint(receipt),
            'repository_commit': saved_commit,
            'attempted': review['attempted'], 'completed': review['summaries_completed'], 'failed': review['failed'],
            'deferred_by_limit': review['selection']['deferred_by_limit'],
            'source_text_saved': False, 'independently_approved': False, 'weekly_publication_verified': False}


def finish(root, lease_path, store, succeeded, saved_commit, now=None):
    lease = read(lease_path)
    args = {'id': lease['id'], 'lease_token': lease['lease_token']}
    if succeeded:
        value = outcome(root, lease, saved_commit, now)
        result = store._call('finish_run', **args, result=value)
    else:
        result = store._call('fail_run', **args, reason='workflow_failed')
    if result.get('saved') is not True:
        raise ValueError('worker_lease_expired_or_replaced')
    return {'job_id': lease['id'], 'state': 'done' if succeeded else 'retry_pending',
            'weekly_publication_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('begin', 'finish'))
    parser.add_argument('--phase', choices=('preparing', 'closed'), default='closed')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--lease', type=Path, required=True)
    args = parser.parse_args()
    try:
        store = RemoteStore()
        if args.action == 'begin':
            result = begin(args.root, args.phase, args.lease, store)
            if os.getenv('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a') as out:
                    out.write('claimed=' + str(result['claimed']).lower() + '\n')
        else:
            result = finish(args.root, args.lease, store,
                            os.getenv('WORKER_SAVED') == 'true', os.getenv('WORKER_COMMIT', ''))
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1)
