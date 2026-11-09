"""Metadata-only access restrictions shared by acquisition and reader handoff.

These controls can only restrict existing routes. They grant no host, source,
version, rights or provider access. Denials have no invented expiration; explicit
provider/host pause deadlines are merged by maximum, never restarted on load.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import timedelta
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import full_document_access as access

ROOT = Path(__file__).resolve().parents[1]
ERROR = 'invalid_shared_access_controls'
MAX_STATE_BYTES = 32_000_000
MAX_CONTROL_ENTRIES = 32768
MAX_CONTROL_BYTES = 4_000_000
HOST = re.compile(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?')
KEYS = {'denied_hosts', 'blocked_urls', 'denied_providers', 'provider_pauses'}


def empty_controls():
    return {'denied_hosts': [], 'blocked_urls': [], 'denied_providers': [], 'provider_pauses': {}}


def validate_controls(controls):
    import collect_weekly_sources as queue
    try:
        queue.shape(controls, KEYS)
        queue.require(sum(len(controls[key]) for key in KEYS) <= MAX_CONTROL_ENTRIES
                      and len(json.dumps(controls, separators=(',', ':'))) <= MAX_CONTROL_BYTES)
        for key in ('denied_hosts', 'blocked_urls', 'denied_providers'):
            values = controls[key]
            queue.require(type(values) is list and all(type(value) is str for value in values)
                          and values == sorted(set(values)))
        for host in controls['denied_hosts']:
            queue.require(HOST.fullmatch(host) is not None)
        for url in controls['blocked_urls']:
            queue.saved_url(url)
        queue.require(set(controls['denied_providers']) <= queue.SAFE_PROVIDERS)
        queue.validate_pauses(controls['provider_pauses'])
        return controls
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError(ERROR) from None


def merge_controls(*collections):
    import collect_weekly_sources as queue
    result = empty_controls()
    for controls in collections:
        validate_controls(controls)
        for key in ('denied_hosts', 'blocked_urls', 'denied_providers'):
            result[key] = sorted(set(result[key]) | set(controls[key]))
        for key, until in controls['provider_pauses'].items():
            if key not in result['provider_pauses'] or queue.utc_now(until) > queue.utc_now(result['provider_pauses'][key]):
                result['provider_pauses'][key] = until
    result['provider_pauses'] = dict(sorted(result['provider_pauses'].items()))
    return validate_controls(result)


def diagnostic_controls(diagnostics):
    """Extract restrictions before bounded diagnostic ledgers can discard them."""
    import collect_weekly_sources as queue
    controls = empty_controls()
    denied = set(); blocked = set(); providers = set()
    for entry in diagnostics:
        queue.validate_diagnostic(entry)
        status = entry['status']
        if status not in queue.BLOCKED:
            continue
        if entry.get('stage') == 'discovery' and entry.get('provider'):
            providers.add(entry['provider'])
        target = entry.get('failure_url') or entry.get('url') or entry.get('final_url')
        if target:
            blocked.add(target)
            if status in {'article_http_401', 'article_http_403', 'http_401', 'http_403',
                          'host_access_denied_this_run'}:
                host = urlsplit(target).hostname
                if host:
                    denied.add(host)
    controls.update(denied_hosts=sorted(denied), blocked_urls=sorted(blocked), denied_providers=sorted(providers))
    return validate_controls(controls)


def controls_from_diagnostics(diagnostics, now=None):
    """Sanitize retrieval observations and preserve only newly observed limits.

    ``rate_limit_pause`` is an already enforced control, not a new response.
    Re-encountering it must not restart a provider or host deadline.
    """
    import collect_weekly_sources as queue
    moment = queue.utc_now(now)
    ledger = [queue.diagnostic(entry) for entry in diagnostics]
    result = diagnostic_controls(ledger)
    for entry in ledger:
        status = entry['status']
        if not (status.endswith('http_429') or status == 'source_unavailable_page'):
            continue
        keys = set()
        if entry.get('stage') == 'discovery' and entry.get('provider') in queue.CONTROL_PROVIDERS:
            keys.add('provider:' + entry['provider'])
        target = entry.get('failure_url') or entry.get('url') or entry.get('final_url')
        if target:
            host = urlsplit(target).hostname
            if host:
                keys.add('host:' + host)
        seconds = max(1, min(entry.get('retry_after_seconds', 3600), 604800))
        until = (moment + timedelta(seconds=seconds)).isoformat()
        for key in keys:
            if key not in result['provider_pauses'] or queue.utc_now(until) > queue.utc_now(result['provider_pauses'][key]):
                result['provider_pauses'][key] = until
    return validate_controls(result)


def merge_diagnostics_into_state(state, diagnostics, *, now=None):
    """Return sealed acquisition metadata after a reader's independent retrieval.

    Callers can save immediately before model/receipt validation. No article
    records, attempts, cursors, input fingerprints or source receipts change.
    """
    import collect_weekly_sources as queue
    shared = merge_controls(controls_from_state(state), controls_from_diagnostics(diagnostics, now))
    updated = deepcopy(state)
    updated['access_controls'] = shared
    updated['provider_pauses'] = dict(shared['provider_pauses'])
    if 'run' in updated:
        checked = queue.utc_now(updated['run']['checked_at'])
        updated['run']['active_provider_pauses'] = {key: until for key, until in updated['provider_pauses'].items()
                                                  if queue.utc_now(until) > checked}
    return queue.seal_state(updated)


def controls_from_state(state):
    """Validate the whole checkpoint, including history, before using any part."""
    import collect_weekly_sources as queue
    try:
        queue.validate_state(state)
        rows = list(state['records'].values())
        for closed in state['closed_windows']:
            rows.extend(closed['pending_record_metadata'].values())
        rows.extend(disposition['record'] for disposition in state['dispositions'])
        controls = empty_controls()
        controls['provider_pauses'] = dict(state['provider_pauses'])
        return merge_controls(controls, state.get('access_controls', empty_controls()),
            diagnostic_controls(entry for row in rows for entry in row['diagnostics']))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise ValueError(ERROR) from None


def read_state(path):
    path = Path(path)
    if path.stat().st_size > MAX_STATE_BYTES:
        raise ValueError(ERROR)
    return json.loads(path.read_text(encoding='utf-8'))


def data_root_for_state(state_path):
    """Infer the documented preparation layout or a standalone state's parent."""
    path = Path(state_path)
    if path.name == 'acquisition.json' and path.parent.parent.name == 'weekly-preparation':
        import collect_weekly_sources as queue
        start = queue.publication_date(path.parent.name)
        if start is None or start.isoformat() != path.parent.name or start.weekday() != 0:
            raise ValueError(ERROR)
        return path.parent.parent.parent
    return path.parent


def load_shared_controls(data_dir=ROOT / 'data', *, states=(), now=None):
    """Read canonical and every preparation checkpoint without mutating either.

    Missing checkpoints are fine. Existing unreadable, oversized or malformed
    checkpoints fail closed, even for a different publication week. ``now`` is
    accepted for caller convenience; absolute deadlines stay intact until used.
    """
    data_dir = Path(data_dir)
    try:
        result = merge_controls(*(controls_from_state(state) for state in states))
        canonical = data_dir / 'weekly-source-acquisition.json'
        paths = [canonical] if canonical.exists() or canonical.is_symlink() else []
        preparation = data_dir / 'weekly-preparation'
        if preparation.exists() or preparation.is_symlink():
            # iterdir surfaces I/O failures, rather than glob silently dropping
            # a directory whose denied/cooldown metadata cannot be read.
            for folder in sorted(preparation.iterdir()):
                if not folder.is_dir():
                    continue
                path = folder / 'acquisition.json'
                if path.exists() or path.is_symlink():
                    import collect_weekly_sources as queue
                    start = queue.publication_date(folder.name)
                    if start is None or start.weekday() != 0 or start.isoformat() != folder.name:
                        raise ValueError(ERROR)
                    state = read_state(path)
                    controls = controls_from_state(state)
                    if state['publication_window']['from'] != folder.name:
                        raise ValueError(ERROR)
                    result = merge_controls(result, controls)
        for path in paths:
            result = merge_controls(result, controls_from_state(read_state(path)))
        return result
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError):
        raise ValueError(ERROR) from None


def stage_controls(controls, now=None):
    """JSON-safe controls for spawned workers; only deadline conversion uses now."""
    import collect_weekly_sources as queue
    controls = validate_controls(controls)
    now = queue.utc_now(now)
    waits = {}; paused = set(controls['denied_providers'])
    for key, until in controls['provider_pauses'].items():
        remaining = math.ceil((queue.utc_now(until) - now).total_seconds())
        if remaining <= 0:
            continue
        if key.startswith('provider:'):
            paused.add(key[len('provider:'):])
        else:
            waits[key[len('host:'):]] = min(604800, remaining)
    return {'denied_hosts': list(controls['denied_hosts']),
            'blocked_urls': list(controls['blocked_urls']),
            'denied_providers': list(controls['denied_providers']),
            'paused_providers': sorted(paused), 'host_backoff': waits}


@contextmanager
def retrieval_scope(denied_hosts=(), blocked_urls=(), host_backoff=None, *, started=None):
    deadlines = dict(access.HOST_COOLDOWNS.get() or {})
    started = time.monotonic() if started is None and host_backoff else started
    for host, seconds in (host_backoff or {}).items():
        deadlines[host] = max(deadlines.get(host, 0), started + seconds)
    hosts = access.HOST_DENIALS.set(set(access.HOST_DENIALS.get() or ()) | set(denied_hosts))
    sources = access.SOURCE_DENIALS.set(set(access.SOURCE_DENIALS.get() or ()) | set(blocked_urls))
    cooldowns = access.HOST_COOLDOWNS.set(deadlines)
    try:
        yield
    finally:
        access.HOST_COOLDOWNS.reset(cooldowns)
        access.SOURCE_DENIALS.reset(sources)
        access.HOST_DENIALS.reset(hosts)
