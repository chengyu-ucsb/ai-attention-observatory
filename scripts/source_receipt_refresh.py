"""Bounded recovery from an observed stale receipt, never a source/review grant.

Only physical extraction metadata is retained. Every refresh must match the
observed replacement at the same currently permitted source and version. A
failed/interrupted or moving-source refresh cannot reset discovery or approval.
"""
from copy import deepcopy
from datetime import timedelta
from urllib.parse import urlsplit

MAX_REQUESTS = 8
MAX_ATTEMPTS = 2
RECEIPT_FIELDS = ('document_version', 'source_sha256', 'source_bytes_sha256', 'source_byte_count',
                   'evidence_status', 'html_extraction_version')


def changed(old, observed):
    return any(old.get(key) != observed.get(key) for key in RECEIPT_FIELDS)


def same_version(old, observed, kind):
    version = old['document_version']
    return (version == observed['document_version']
            and 'unversioned' not in version
            and (version != 'unspecified' or kind == 'nonacademic'))


def validate(row):
    import collect_weekly_sources as queue
    events = row['source_refreshes']
    queue.require(type(events) is list and 1 <= len(events) <= MAX_REQUESTS
                  and row['complete'] and 'document' in row)
    receipts = []; times = []; all_attempt_times = []
    for index, event in enumerate(events):
        queue.shape(event, {'input_fingerprint', 'receipt', 'observed_document', 'observed_at', 'status', 'attempts'},
                    {'reason', 'next_retry_at', 'replacement_sha256'})
        queue.require(event['input_fingerprint'] == row['fingerprint'])
        prior = event['receipt']
        queue.shape(prior, {'document', 'document_evidence'})
        old = prior['document']; evidence = prior['document_evidence']; observed = event['observed_document']
        queue.validate_document(old); queue.validate_document(observed); queue.validate_diagnostic(evidence)
        queue.require(evidence['status'] == old['evidence_status'] and not evidence['retryable']
            and (evidence.get('final_url') or evidence.get('url')) == old['source_url']
            and old['source_url'] == observed['source_url'] and changed(old, observed))
        queue.timestamp(event['observed_at']); times.append(queue.utc_now(event['observed_at']))
        receipts.append(queue.digest(old))
        attempts = event['attempts']
        queue.require(type(attempts) is list and len(attempts) <= MAX_ATTEMPTS)
        attempt_times = []
        for attempt in attempts:
            queue.shape(attempt, {'attempted_at', 'outcome'})
            queue.timestamp(attempt['attempted_at'])
            queue.require(queue.code(attempt['outcome']) == attempt['outcome'])
            attempt_times.append(queue.utc_now(attempt['attempted_at']))
        queue.require(attempt_times == sorted(attempt_times)
            and all(time >= times[-1] for time in attempt_times))
        if all_attempt_times:
            queue.require(times[-1] >= all_attempt_times[-1])
        all_attempt_times.extend(attempt_times)
        status = event['status']
        queue.require(status in {'pending', 'held', 'refreshed'}
                      and ('reason' in event) == (status == 'held')
                      and ('replacement_sha256' in event) == (status == 'refreshed'))
        if status == 'held':
            queue.require(queue.code(event['reason']) == event['reason'])
        else:
            queue.require(same_version(old, observed, row['kind'])
                and old['evidence_status'] == observed['evidence_status']
                and old.get('document_format') == observed.get('document_format'))
        if 'next_retry_at' in event:
            queue.timestamp(event['next_retry_at'])
            queue.require(status == 'pending' and attempts and len(attempts) < MAX_ATTEMPTS
                          and queue.utc_now(event['next_retry_at']) > attempt_times[-1])
        elif status == 'pending':
            queue.require(not attempts)
        if status == 'refreshed':
            queue.require(attempts and attempts[-1]['outcome'] == observed['evidence_status'])
            queue.hash_value(event['replacement_sha256'])
            next_doc = events[index + 1]['receipt']['document'] if index + 1 < len(events) else row['document']
            queue.require(event['replacement_sha256'] == queue.digest(observed) == queue.digest(next_doc))
        else:
            queue.require(index == len(events) - 1 and old == row['document']
                          and evidence == row['document_evidence'])
    queue.require(len(set(receipts)) == len(receipts) and times == sorted(times)
                  and row['attempts'] >= len(all_attempt_times) + len(row.get('html_refresh_attempts', [])) + 1)
    if all_attempt_times:
        queue.require(queue.utc_now(row['last_attempt_at']) == all_attempt_times[-1])
    if 'html_refresh_attempts' in row:
        queue.require(times[0] >= queue.utc_now(row['html_refresh_attempts'][-1]['attempted_at']))


def validate_hold(row):
    import collect_weekly_sources as queue
    hold = row['source_refresh_hold']
    queue.shape(hold, {'input_fingerprint', 'receipt_sha256', 'observed_at', 'observed_document', 'reason'})
    queue.require(row['complete'] and hold['input_fingerprint'] == row['fingerprint']
                  and hold['receipt_sha256'] == queue.digest(row['document']))
    queue.timestamp(hold['observed_at']); queue.validate_document(hold['observed_document'])
    queue.require(hold['observed_document']['source_url'] == row['document']['source_url'])
    if hold['reason'] == 'source_version_unverified':
        # The raw returned label was unknown and normalized to unspecified.
        # Its mismatch status must survive even when physical hashes agree.
        queue.require(row['document']['document_version'] == 'unspecified'
                      and hold['observed_document']['document_version'] == 'unspecified')
        return
    queue.require(changed(row['document'], hold['observed_document']))
    events = row.get('source_refreshes', [])
    queue.require(events and events[-1]['status'] == 'refreshed')
    if hold['reason'] == 'receipt_refresh_limit':
        queue.require(len(events) == MAX_REQUESTS)
    else:
        queue.require(hold['reason'] == 'receipt_refresh_cycle'
            and any(queue.digest(event['receipt']['document']) == hold['receipt_sha256'] for event in events))


def hold_unadmitted(row, observed, now, reason):
    """No room for another request is not permission to reuse cached approval."""
    import collect_weekly_sources as queue
    row.setdefault('source_refresh_hold', {
        'input_fingerprint': row['fingerprint'], 'receipt_sha256': queue.digest(row['document']),
        'observed_document': deepcopy(observed), 'observed_at': now.isoformat(), 'reason': reason})


def observe(state, diagnostics, now):
    """Merge only exact, validated handoff observations; do not fetch or approve."""
    import collect_weekly_sources as queue
    for entry in diagnostics:
        observation = entry.get('receipt_observation')
        if (entry.get('stage') != 'handoff' or entry.get('provider') != 'validated_acquisition_checkpoint'
                or entry.get('status') not in {'acquisition_receipt_content_changed', 'acquisition_source_version_changed'}
                or observation is None):
            continue
        queue.shape(observation, {'record_key', 'input_fingerprint', 'receipt_sha256', 'document'})
        for key in ('record_key', 'input_fingerprint', 'receipt_sha256'):
            queue.hash_value(observation[key])
        observed = observation['document']; queue.validate_document(observed)
        row = state['records'].get(observation['record_key'])
        if (not row or not row['complete'] or not row.get('document')
                or row['fingerprint'] != observation['input_fingerprint']
                or queue.digest(row['document']) != observation['receipt_sha256']):
            continue
        old = row['document']
        if observed['source_url'] != old['source_url'] or row.get('source_refresh_hold'):
            continue
        events = row.get('source_refreshes', [])
        existing = next((event for event in events
                         if queue.digest(event['receipt']['document']) == observation['receipt_sha256']), None)
        version_ok = (entry['status'] != 'acquisition_source_version_changed'
                      and same_version(old, observed, row['kind']))
        if not version_ok and not changed(old, observed):
            hold_unadmitted(row, observed, now, 'source_version_unverified')
            continue
        if existing:
            if existing['status'] == 'refreshed' and changed(old, observed):
                hold_unadmitted(row, observed, now, 'receipt_refresh_cycle')
            # A later contrary version observation can only restrict a request.
            # Repeated observations never restart its attempts or cooldown.
            if not version_ok and existing['status'] == 'pending':
                existing.update(status='held', reason='source_version_unverified')
                existing.pop('next_retry_at', None)
            continue
        if not changed(old, observed):
            continue
        if len(events) >= MAX_REQUESTS:
            hold_unadmitted(row, observed, now, 'receipt_refresh_limit')
            continue
        event = {'input_fingerprint': row['fingerprint'],
                 'receipt': {'document': deepcopy(old), 'document_evidence': deepcopy(row['document_evidence'])},
                 'observed_document': deepcopy(observed), 'observed_at': now.isoformat(),
                 'status': 'pending', 'attempts': []}
        if not version_ok:
            event.update(status='held', reason='source_version_unverified')
        elif (old['evidence_status'] != observed['evidence_status']
              or old.get('document_format') != observed.get('document_format')):
            event.update(status='held', reason='document_identity_unverified')
        row.setdefault('source_refreshes', []).append(event)


def plan(row, routes, record, window, shared, now):
    import collect_weekly_sources as queue
    events = row.get('source_refreshes', [])
    if row.get('source_refresh_hold') or not events or events[-1]['status'] != 'pending':
        return None
    event = events[-1]; old = row['document']
    if (event.get('next_retry_at') and queue.utc_now(event['next_retry_at']) > now):
        return None
    effective = queue.controls.stage_controls(shared, now)
    host = urlsplit(old['source_url']).hostname
    if (host in effective['denied_hosts'] or host in effective['host_backoff']
            or old['source_url'] in effective['blocked_urls']):
        return None
    for route in routes:
        if (route['url'] == old['source_url'] and queue.token(route.get('version')) == old['document_version']
                and queue.route_permitted(route, record, window)
                and route.get('provider') not in effective['paused_providers']):
            return {'kind': 'known', 'source': route, 'publication_window': window,
                    'receipt_refresh_version': old['document_version']}
    return None


def start(row, now):
    event = row['source_refreshes'][-1]
    event.pop('next_retry_at', None)
    # Persist before I/O. Interruption is held, not automatically replayed.
    event.update(status='held', reason='interrupted_attempt')
    event['attempts'].append({'attempted_at': now.isoformat(), 'outcome': 'interrupted_attempt'})


def finish(row, result, now):
    import collect_weekly_sources as queue
    event = row['source_refreshes'][-1]
    ledger = [queue.diagnostic(entry) for entry in result.get('diagnostics', [])]
    row['diagnostics'] = (row['diagnostics'] + ledger)[-96:]
    attempt = event['attempts'][-1]
    failures = [entry for entry in ledger if entry['status'] not in queue.SUCCESS |
                {'candidates', 'candidate_budget_exhausted', 'no_exact_match'}]
    blocked = [entry for entry in failures if entry['status'] in queue.BLOCKED]
    outcome = (blocked or failures or ledger or [{'status': 'retrieval_error'}])[-1]['status']
    retrieved = result.get('document')
    if retrieved is not None:
        queue.validate_document(retrieved)
        evidence = next((entry for entry in ledger if entry['status'] == retrieved['evidence_status']
                         and (entry.get('final_url') or entry.get('url')) == retrieved['source_url']), None)
        if not same_version(row['document'], retrieved, row['kind']):
            outcome = 'source_version_unverified'
        elif retrieved != event['observed_document'] or evidence is None:
            outcome = 'receipt_refresh_changed_again'
        else:
            row['document'] = deepcopy(retrieved); row['document_evidence'] = evidence
            row['last_outcome'] = retrieved['evidence_status']
            event.update(status='refreshed', replacement_sha256=queue.digest(retrieved))
            event.pop('reason', None)
            attempt['outcome'] = retrieved['evidence_status']
            return
    elif outcome in queue.SUCCESS:
        outcome = 'retrieval_error'
    event.update(status='held', reason=outcome); attempt['outcome'] = outcome
    retry = [entry for entry in ledger if entry['retryable']]
    if retrieved is None and retry and not any(entry['status'] in queue.BLOCKED for entry in ledger) and len(event['attempts']) < MAX_ATTEMPTS:
        seconds = max(max(1, entry.get('retry_after_seconds', 3600)) for entry in retry)
        event.update(status='pending', next_retry_at=(now + timedelta(seconds=seconds)).isoformat())
        event.pop('reason', None)
