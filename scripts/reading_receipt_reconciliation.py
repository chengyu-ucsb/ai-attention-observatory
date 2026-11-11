"""Opt-in, offline proof for a legacy final receipt after a narrow library race.

Never alters a receipt or starts acquisition/review. Git is only a local source
of the exact prior inputs; incomplete or ambiguous history is not evidence.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


def _waiting_for_license(value, now):
    import collect_weekly_sources as queue
    queue.shape(value, {'attempts', 'last_at', 'pipeline_version', 'status', 'next_at'})
    queue.integer(value['attempts'])
    queue.require(value['attempts'] >= 1)
    queue.require(type(value['pipeline_version']) is int and value['pipeline_version'] == 3
                  and value['status'] == 'waiting_for_license')
    queue.timestamp(value['last_at']); queue.timestamp(value['next_at'])
    queue.require(queue.utc_now(value['last_at']) <= now
                  and queue.utc_now(value['next_at']) > queue.utc_now(value['last_at']))


def _same_record(before, after, window, now, root, completed_at=None):
    """Only allow an unproductive licensed-text retry and its redundant alias."""
    import collect_weekly_sources as queue
    import preparation_pipeline as pipeline
    if before == after:
        return True
    changed = {key for key in set(before) | set(after) if before.get(key) != after.get(key)
               or (key in before) != (key in after)}
    if not changed <= {'fulltext_attempt', 'open_access_url'}:
        return False
    # No special treatment for a record with extracted/reviewed source text.
    if (before.get('kind') != 'scholarly'
            or (before.get('reading') or {}).get('level') != 'abstract'
            or any(before.get(key) for key in ('analysis', 'deep_analysis', 'source_review',
                'original_reading', 'partial_reading_candidate', 'original_reading_sha256',
                'approved', 'approval', 'original_summary', 'source_checked',
                'independently_approved', 'review_status', 'digest'))
            or any((before.get('reading') or {}).get(key) for key in (
                'original_summary', 'approved', 'approval', 'review_status', 'digest', 'status'))):
        return False
    if 'fulltext_attempt' in changed:
        if 'fulltext_attempt' not in after:
            return False
        _waiting_for_license(after['fulltext_attempt'], now)
        if completed_at is not None and queue.utc_now(after['fulltext_attempt']['last_at']) < completed_at:
            return False
        if 'fulltext_attempt' in before:
            _waiting_for_license(before['fulltext_attempt'], now)
            old, new = before['fulltext_attempt'], after['fulltext_attempt']
            if (new['attempts'] < old['attempts']
                    or queue.utc_now(new['last_at']) < queue.utc_now(old['last_at'])
                    or queue.utc_now(new['next_at']) < queue.utc_now(old['next_at'])):
                return False
    if 'open_access_url' in changed:
        # Addition of this exact DOI-derived unversioned landing alias only.
        # A wrong host, query, credential, v2 link, removal or replacement holds,
        # even when the route gate happens to discard it and fingerprints agree.
        pinned = queue.verified_arxiv_v1(before)
        if (not pinned or not pinned.endswith('v1') or 'open_access_url' in before
                or after.get('open_access_url') != 'https://arxiv.org/abs/' + pinned[:-2]
                or queue.verified_arxiv_v1(after) != pinned):
            return False
        hints = Path(root) / 'data/fulltext-source-hints.json'
        actual = queue.access.SOURCE_HINTS
        # The route helper must consult exactly the registry whose history was
        # checked, even when a caller provides a different --root checkout.
        if pipeline.digest(pipeline.read(hints) if hints.exists() else None) != pipeline.digest(
                pipeline.read(actual) if actual.exists() else None):
            return False
        without_alias = {key: value for key, value in before.items() if key != 'open_access_url'}
        if not any(row['url'] == after['open_access_url']
                   for row in queue.access.known_candidates(without_alias)):
            return False
        for known_only in (True, False):
            if queue.prepare(before, window, known_only) != queue.prepare(after, window, known_only):
                return False
    return True


def reconcile_legacy_library(root, folder, receipt, run, packet, weekly, current_library, now):
    """Return a proof summary, or None. All Git commands are read-only/local."""
    import preparation_pipeline as pipeline
    from academic_state_schema import strict_json_loads
    root, folder = Path(root).resolve(), Path(folder).resolve()
    relative = folder.relative_to(root).as_posix()
    receipt_path = relative + '/final-reading.json'
    environment = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')

    def git(*args, missing_ok=False):
        result = subprocess.run(['git', '--no-pager', *args], cwd=root, env=environment,
            check=False, capture_output=True, text=True, timeout=10)
        if missing_ok and result.returncode == 1:
            return ""
        result.check_returncode()
        return result.stdout.strip()

    def snapshot(commit, path, optional=False):
        if optional and not git('ls-tree', '--name-only', commit, '--', path):
            return None
        return strict_json_loads(git('show', commit + ':' + path))

    try:
        if (Path(git('rev-parse', '--show-toplevel')).resolve() != root
                or git('rev-parse', '--is-shallow-repository') != 'false'):
            return None
        if git('config', '--get-regexp', r'^remote\..*\.promisor$|^extensions\.partialclone$', missing_ok=True):
            return None
        revisions = git('log', '--format=%H', '--max-count=33', 'HEAD', '--', receipt_path).splitlines()
        if len(revisions) > 32 or any(not re.fullmatch(r'[0-9a-f]{40,64}', rev) for rev in revisions):
            return None
        matches = [rev for rev in revisions if snapshot(rev, receipt_path) == receipt]
        if not matches:
            return None
        # Multiple commits carrying the same complete content proof are not
        # ambiguous. Any inconsistent receipt/input or policy snapshot is held.
        for candidate in matches:
            for name, expected in receipt['bindings'].items():
                path = ('data/' if name in {'library.json', 'weekly.json'} else relative + '/') + name
                if pipeline.digest(snapshot(candidate, path)) != expected:
                    return None
            if snapshot(candidate, relative + '/reading-run.json') != run:
                return None
            for name in pipeline.CANONICAL_POLICY_INPUTS:
                path = root / 'data' / name
                current = pipeline.read(path) if path.exists() else None
                if snapshot(candidate, 'data/' + name, optional=True) != current:
                    return None
        baseline = matches[0]
        old_library = snapshot(baseline, 'data/library.json')
        old = pipeline.scoped_library_inputs(root, packet, weekly, old_library)['records']
        new = pipeline.scoped_library_inputs(root, packet, weekly, current_library)['records']
        # Ordered complete identity closures protect additions/removals/date
        # changes. No row is dropped just because its approval was withdrawn.
        if len(old) != len(new) or not all(_same_record(a, b, packet['target_publication_window'],
                                                     now, root, pipeline.utc(receipt["completed_at"]))
                                         for a, b in zip(old, new)):
            return None
        return {'basis': 'verified_legacy_git_snapshot', 'baseline_commit': baseline,
                'receipt_rewritten': False, 'source_or_model_calls': False}
    except (subprocess.SubprocessError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
