"""Save validated canonical reader changes without replaying external work.

Acquisition metadata is independently recoverable after a reading/validation
failure. Only a successful validation path may request library inclusion, and
only the reader's validated enrichment fields may differ from the Git baseline.
All commits are made in a clean worktree, leaving failed runner output intact.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

from academic_state_schema import strict_json_loads
import collect_weekly_sources as queue
from prepared_reading_schema import ENRICHMENT, validate_saved_record

ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = 'data/weekly-source-acquisition.json'
LIBRARY = 'data/library.json'
MANIFEST = 'checkpoint.json'


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout


def read(path):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size > 64_000_000:
        raise ValueError('invalid_reading_checkpoint_file')
    raw = path.read_bytes()
    return raw, strict_json_loads(raw.decode('utf-8'))


def validate_library(value, baseline, now=None):
    """Preserve existing canonical metadata; validate every new enrichment."""
    if type(value) is not list or type(baseline) is not list or len(value) != len(baseline):
        raise ValueError('invalid_reading_library_delta')
    for old, new in zip(baseline, value):
        if type(old) is not dict or type(new) is not dict:
            raise ValueError('invalid_reading_library_delta')
        if {k: v for k, v in old.items() if k not in ENRICHMENT} != {k: v for k, v in new.items() if k not in ENRICHMENT}:
            raise ValueError('invalid_reading_library_delta')
        changed = {key for key in ENRICHMENT if old.get(key) != new.get(key) or (key in old) != (key in new)}
        if not changed:
            continue
        if any(key not in new for key in changed):
            raise ValueError('invalid_reading_library_delta')
        # A failed fetch may retain legacy analysis unchanged. Validate the new
        # failure record without retroactively rewriting that old analysis.
        fields = changed if changed == {'complete_reading_attempt'} else ENRICHMENT
        validate_saved_record({'kind': new.get('kind'), **{key: new[key] for key in fields if key in new}}, now=now)
    return value


def snapshot(root, destination, *, include_library=False, now=None):
    root, destination = Path(root).resolve(), Path(destination)
    destination.mkdir(parents=True, exist_ok=False)  # Never reuse an old artifact directory.
    base = git(root, 'rev-parse', 'HEAD').strip()
    files = {}; errors = []
    for relative in ([ACQUISITION, LIBRARY] if include_library else [ACQUISITION]):
        source = root / relative
        if relative == ACQUISITION and not source.exists() and not source.is_symlink():
            continue
        if relative == LIBRARY and errors:
            # Do not couple a new library to invalid source evidence.
            continue
        try:
            raw, value = read(source)
            if relative == ACQUISITION:
                queue.validate_state(value)
            else:
                baseline = strict_json_loads(git(root, 'show', base + ':' + LIBRARY))
                validate_library(value, baseline, now)
        except (ValueError, TypeError, KeyError, OSError, UnicodeError, subprocess.CalledProcessError):
            errors.append(relative)
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files[relative] = sha256(raw).hexdigest()
    manifest = {'schema_version': 1, 'base_commit': base, 'files': files, 'source_text_saved': False}
    (destination / MANIFEST).write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return {'valid': bool(files), 'complete': not errors, 'invalid_files': errors,
            'validated_files': sorted(files), 'source_text_saved': False}


def validated_snapshot(root, snapshot_path, now=None):
    root, snapshot_path = Path(root).resolve(), Path(snapshot_path).resolve()
    _, manifest = read(snapshot_path / MANIFEST)
    queue.shape(manifest, {'schema_version', 'base_commit', 'files', 'source_text_saved'})
    queue.require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1
                  and manifest['source_text_saved'] is False
                  and type(manifest['base_commit']) is str and re.fullmatch(r'[0-9a-f]{40}', manifest['base_commit'])
                  and manifest['base_commit'] == git(root, 'rev-parse', 'HEAD').strip())
    files = manifest['files']
    queue.require(type(files) is dict and files and set(files) <= {ACQUISITION, LIBRARY})
    actual = set()
    for path in snapshot_path.rglob('*'):
        queue.require(not path.is_symlink())
        if path.is_file(): actual.add(path.relative_to(snapshot_path).as_posix())
    queue.require(actual == set(files) | {MANIFEST})
    retained = {}
    for relative, expected in files.items():
        queue.hash_value(expected)
        raw, value = read(snapshot_path / relative)
        queue.require(sha256(raw).hexdigest() == expected)
        if relative == ACQUISITION:
            queue.validate_state(value)
        else:
            baseline = strict_json_loads(git(root, 'show', manifest['base_commit'] + ':' + LIBRARY))
            validate_library(value, baseline, now)
        retained[relative] = raw
    return manifest, retained


def commit(root, snapshot_path, worktree, *, now=None):
    """Recheck the immutable snapshot and commit only its exact validated files."""
    root, worktree = Path(root).resolve(), Path(worktree).resolve()
    manifest, retained = validated_snapshot(root, snapshot_path, now)
    git(root, 'worktree', 'add', '--detach', str(worktree), manifest['base_commit'])
    for relative, raw in retained.items():
        target = worktree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    git(worktree, 'add', '--', *sorted(retained))
    changed = bool(git(worktree, 'diff', '--cached', '--name-only').strip())
    if changed:
        git(worktree, '-c', 'user.name=github-actions[bot]', '-c',
            'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            'commit', '-m', 'Preserve validated source-reading notes and acquisition controls')
    return {'worktree': str(worktree), 'committed': changed,
            'commit': git(worktree, 'rev-parse', 'HEAD').strip()}


def verify_rebased(root, snapshot_path, worktree, *, now=None):
    """Do not attach old-source notes to silently merged new bibliographic inputs.

    Rebase may merge distant JSON lines without a conflict. Stay conservative:
    files written by this run must still match the original validated snapshot
    byte for byte. Independent files may advance; same-file changes need review.
    Never validate against a new baseline that could conceal identity drift.
    """
    _, retained = validated_snapshot(root, snapshot_path, now)
    worktree = Path(worktree).resolve()
    queue.require(not git(worktree, 'status', '--porcelain').strip())
    for relative, expected in retained.items():
        raw, _ = read(worktree / relative)
        if raw != expected:
            raise ValueError('rebased_reading_checkpoint_changed')
    acquisition = worktree / ACQUISITION
    if LIBRARY in retained and ACQUISITION not in retained and (acquisition.exists() or acquisition.is_symlink()):
        raise ValueError('rebased_reading_checkpoint_changed')
    if acquisition.exists() or acquisition.is_symlink():
        queue.validate_state(read(acquisition)[1])
    return {'valid': True, 'snapshot_unchanged': True, 'source_text_saved': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('snapshot', 'commit', 'verify'))
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--worktree', type=Path)
    parser.add_argument('--include-library', action='store_true')
    args = parser.parse_args()
    if args.action == 'snapshot':
        result = snapshot(args.root, args.destination, include_library=args.include_library)
        output = os.getenv('GITHUB_OUTPUT')
        if output:
            with open(output, 'a', encoding='utf-8') as stream:
                stream.write('valid=' + str(result['valid']).lower() + '\n')
    else:
        if not args.worktree or args.include_library:
            parser.error('commit/verify requires --worktree and does not accept --include-library')
        operation = commit if args.action == 'commit' else verify_rebased
        result = operation(args.root, args.destination, args.worktree)
    print(json.dumps(result))
    if result.get('invalid_files'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
