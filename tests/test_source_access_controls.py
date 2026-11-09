"""Offline cross-window controls never grant or repeat restricted source access."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_weekly_source_acquisition import queue, access, item, weekly, rows, NOW, WINDOW
import acquisition_handoff as handoff
import source_access_controls as controls


def checkpoint(*diagnostics, pauses=None, record=None):
    state = queue.run(weekly(record or item()), now=NOW, known_sources_only=True,
                      attempt=lambda *args: {'diagnostics': list(diagnostics)}, clock=lambda: 0)
    if pauses:
        state.pop('run')
        state['provider_pauses'].update(pauses)
        queue.seal_state(state)
    return state


def denial(url='https://www.econstor.eu/article1.pdf', status='article_http_403', **fields):
    return {'stage': 'article', 'status': status, 'retryable': False, 'url': url, **fields}


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))
    return path


class SharedAccessControlsTests(unittest.TestCase):
    def test_discover_canonical_and_preparation_without_mutation_or_provider_reset(self):
        future = (NOW + timedelta(hours=2)).isoformat()
        early = (NOW + timedelta(hours=1)).isoformat()
        canonical = checkpoint(denial(), pauses={'provider:CORE': future})
        staged = checkpoint(denial('https://arxiv.org/pdf/2610.00001v1', 'robots_disallow_or_unavailable'),
                            {'stage': 'discovery', 'provider': 'OpenAIRE', 'status': 'http_403', 'retryable': False},
                            pauses={'provider:CORE': early, 'host:arxiv.org': future})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [write_state(root / 'weekly-source-acquisition.json', canonical),
                     write_state(root / 'weekly-preparation/2026-10-26/acquisition.json', staged)]
            before = [p.read_bytes() for p in paths]
            merged = controls.load_shared_controls(root, now=NOW)
            self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertEqual(merged['denied_hosts'], ['www.econstor.eu'])
        self.assertEqual(merged['denied_providers'], ['OpenAIRE'])
        self.assertEqual(merged['provider_pauses']['provider:CORE'], future)
        self.assertIn('https://arxiv.org/pdf/2610.00001v1', merged['blocked_urls'])
        self.assertEqual(controls.stage_controls(merged, NOW)['host_backoff'], {'arxiv.org': 7200})
        expired = controls.stage_controls(merged, NOW + timedelta(days=2))
        self.assertEqual(expired['host_backoff'], {})
        self.assertEqual(expired['paused_providers'], ['OpenAIRE'])
        self.assertEqual(expired['denied_hosts'], ['www.econstor.eu'])

    def test_history_and_replaced_input_controls_survive(self):
        # Legacy state has no additive metadata. Discover retained histories too.
        old = checkpoint(denial(), record=item(fulltext_candidates=[{'url':'https://www.econstor.eu/first.pdf'}]))
        old.pop('access_controls'); old.pop('run'); queue.seal_state(old)
        changed = queue.run(weekly(item(title='Changed exact title')), old, now=NOW,
                            known_sources_only=True, limit=0, clock=lambda: 0)
        changed.pop('access_controls'); queue.seal_state(changed)
        self.assertEqual(controls.controls_from_state(changed)['denied_hosts'], ['www.econstor.eu'])
        future = weekly(); future['run']['publication_window'] = {
            'from':'2026-11-02', 'to':'2026-11-08', 'timezone':'UTC'}
        closed = queue.run(future, old, now=NOW + timedelta(days=7), known_sources_only=True, clock=lambda: 0)
        closed.pop('access_controls'); queue.seal_state(closed)
        self.assertEqual(controls.controls_from_state(closed)['denied_hosts'], ['www.econstor.eu'])

    def test_completed_denials_survive_rollover_without_copying_records(self):
        old = checkpoint(denial())
        self.assertTrue(rows(old)[0]['complete'])
        future = weekly(); future['run']['publication_window'] = {
            'from':'2026-11-02', 'to':'2026-11-08', 'timezone':'UTC'}
        closed = queue.run(future, old, now=NOW + timedelta(days=7), known_sources_only=True, clock=lambda: 0)
        self.assertEqual(closed['records'], {})
        self.assertEqual(closed['closed_windows'][0]['pending_record_metadata'], {})
        self.assertEqual(closed['access_controls']['denied_hosts'], ['www.econstor.eu'])
        self.assertEqual(controls.controls_from_state(closed)['denied_hosts'], ['www.econstor.eu'])

    def test_fail_closed_on_corrupt_or_misfiled_preparation_checkpoint(self):
        good = checkpoint()
        for mutation in ('checksum', 'unknown_prose', 'wrong_week', 'broken_json', 'oversized'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); state = copy.deepcopy(good)
                path = root / 'weekly-preparation/2026-10-26/acquisition.json'
                if mutation == 'checksum': state['state_sha256'] = '0' * 64
                if mutation == 'unknown_prose':
                    state['unvalidated_text'] = 'not allowed'
                    state['state_sha256'] = queue.digest({k:v for k,v in state.items() if k != 'state_sha256'})
                if mutation == 'wrong_week': path = root / 'weekly-preparation/2026-11-02/acquisition.json'
                write_state(path, state)
                if mutation == 'broken_json': path.write_text('{')
                with patch.object(controls, 'MAX_STATE_BYTES', 1 if mutation == 'oversized' else 32_000_000):
                    with self.assertRaisesRegex(ValueError, controls.ERROR):
                        controls.load_shared_controls(root)

    def test_corrupt_controls_cannot_be_repaired_into_permission(self):
        for bad in ({}, {'denied_hosts': ['www.econstor.eu']}):
            fetch = Mock()
            with self.assertRaisesRegex(ValueError, controls.ERROR):
                queue.run(weekly(item()), now=NOW, shared_controls=bad, attempt=fetch)
            fetch.assert_not_called()
        state = checkpoint(); state['access_controls']['blocked_urls'] = ['https://x.example/article?token=private']
        state['state_sha256'] = queue.digest({k:v for k,v in state.items() if k != 'state_sha256'})
        with self.assertRaisesRegex(ValueError, queue.STATE_ERROR): queue.validate_state(state)

    def test_control_capacity_fails_closed_without_eviction(self):
        shared = controls.empty_controls(); shared['denied_hosts'] = ['a.example', 'b.example']
        with patch.object(controls, 'MAX_CONTROL_ENTRIES', 1):
            with self.assertRaisesRegex(ValueError, controls.ERROR): controls.validate_controls(shared)
        self.assertEqual(shared['denied_hosts'], ['a.example', 'b.example'])

    def test_same_run_denials_propagate_without_changing_input_fingerprint(self):
        plans = []
        def attempt(record, plan, *args):
            plans.append(copy.deepcopy(plan))
            return {'diagnostics': [denial()]}
        plain = queue.run(weekly(item(1), item(2)), now=NOW, known_sources_only=True, limit=0)
        state = queue.run(weekly(item(1), item(2)), now=NOW, known_sources_only=True, attempt=attempt, clock=lambda: 0)
        self.assertEqual(state['input_fingerprint'], plain['input_fingerprint'])
        self.assertEqual(plans[1]['access_controls']['denied_hosts'], ['www.econstor.eu'])
        self.assertEqual(set(state['records']), set(plain['records']))
        self.assertEqual(controls.validate_controls(plans[1]['access_controls']), plans[1]['access_controls'])

    def test_bounded_diagnostic_history_does_not_forget_source_denials(self):
        ledger = [denial()] + [{'stage':'discovery', 'provider':'CORE', 'status':'no_exact_match',
                               'retryable':False} for _ in range(100)]
        state = checkpoint(*ledger)
        self.assertEqual(len(rows(state)[0]['diagnostics']), 96)
        self.assertFalse(any(d['status'] in queue.BLOCKED for d in rows(state)[0]['diagnostics']))
        self.assertEqual(state['access_controls']['denied_hosts'], ['www.econstor.eu'])
        self.assertEqual(controls.controls_from_state(state)['denied_hosts'], ['www.econstor.eu'])


    def test_new_controls_restrict_normal_and_private_window_engine(self):
        shared = controls.controls_from_state(checkpoint(denial()))
        for engine in (queue.run, queue._run_window):
            called = []
            def attempt(record, plan, *args):
                called.append(plan)
                return queue.perform_stage(record, plan, 1)
            with patch.object(access, 'fetch_candidate') as fetch:
                options = {'window': WINDOW} if engine is queue._run_window else {}
                state = engine(weekly(item()), now=NOW, known_sources_only=True, shared_controls=shared,
                               attempt=attempt, clock=lambda: 0, **options)
            fetch.assert_not_called()
            self.assertEqual(rows(state)[0]['status'], 'access_blocked')
            self.assertEqual(called[0]['access_controls']['denied_hosts'], ['www.econstor.eu'])

    def test_spawned_stage_receives_source_denials_without_parent_context(self):
        record = item(); shared = controls.empty_controls()
        shared['blocked_urls'] = [record['url']]
        plan = {'kind': 'known', 'source': access.known_candidates(record)[0],
                'publication_window': WINDOW, 'access_controls': shared,
                'controls_checked_at': NOW.isoformat()}
        result = queue.bounded_stage(record, plan, 1, 10)
        self.assertEqual(result['diagnostics'][0]['status'], 'source_access_denied_this_run')
        self.assertNotIn('document', result)
        self.assertIsNone(access.SOURCE_DENIALS.get())

    def test_provider_denials_and_cooldowns_do_not_call_locator(self):
        for denied in (True, False):
            shared = controls.empty_controls()
            if denied: shared['denied_providers'] = ['CORE']
            else: shared['provider_pauses'] = {'provider:CORE': (NOW + timedelta(hours=2)).isoformat()}
            plan = {'kind':'provider', 'name':'CORE', 'tried_sources':[],
                    'publication_window':WINDOW, 'access_controls':shared, 'controls_checked_at':NOW.isoformat()}
            with patch.object(access, 'default_providers') as providers:
                result = queue.perform_stage(item(), plan, 1)
            providers.assert_not_called()
            self.assertEqual(result['diagnostics'][0]['status'],
                             'provider_access_denied_history' if denied else 'rate_limit_pause')

    def test_provider_api_host_obeys_shared_cooldown_before_any_request(self):
        shared = controls.empty_controls()
        shared['provider_pauses'] = {'host:api.core.ac.uk':(NOW + timedelta(hours=2)).isoformat()}
        def locate(identifier):
            access.check_host_cooldown('https://api.core.ac.uk/v3/search/works')
            self.fail('The paused host must not reach the request step')
        plan = {'kind':'provider', 'name':'CORE', 'tried_sources':[], 'publication_window':WINDOW,
                'access_controls':shared, 'controls_checked_at':NOW.isoformat()}
        with patch.object(access, 'default_providers', return_value=[('CORE', locate)]):
            result = queue.perform_stage(item(), plan, 1)
        self.assertEqual(result['diagnostics'][0]['status'], 'rate_limit_pause')
        self.assertIsNone(access.HOST_COOLDOWNS.get())


    def test_article_host_cooldown_is_serialized_and_not_extended_on_resume(self):
        until = (NOW + timedelta(hours=2)).isoformat()
        shared = controls.empty_controls(); shared['provider_pauses'] = {'host:www.econstor.eu': until}
        callback = Mock()
        state = queue.run(weekly(item()), now=NOW, known_sources_only=True,
                          shared_controls=shared, attempt=callback, clock=lambda:0)
        callback.assert_not_called()
        self.assertEqual(state['provider_pauses']['host:www.econstor.eu'], until)
        state = queue.run(weekly(item()), state, now=NOW + timedelta(minutes=30),
                          known_sources_only=True, shared_controls=shared, attempt=callback, clock=lambda:0)
        callback.assert_not_called()
        self.assertEqual(rows(state)[0]['next_retry_at'], until)
        self.assertEqual(state['access_controls']['provider_pauses']['host:www.econstor.eu'], until)

    def test_preparation_handoff_discovers_canonical_without_matching_receipt(self):
        state = checkpoint(denial())
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_state(root / 'weekly-source-acquisition.json', state)
            missing = root / 'weekly-preparation/2026-10-26/acquisition.json'
            def retrieve(record, **options):
                self.assertIn('www.econstor.eu', access.HOST_DENIALS.get())
                self.assertIn(record['url'], access.SOURCE_DENIALS.get())
                return None, []
            callback = Mock(side_effect=retrieve)
            handoff._retrieve_for_reading(item(), state_path=missing, weekly_path=missing.parent/'weekly.json',
                                          retriever=callback, now=NOW)
            callback.assert_called_once()

    def test_normal_handoff_discovers_preparation_provider_and_host_controls(self):
        staged = checkpoint(denial(), {'stage':'discovery', 'provider':'CORE', 'status':'http_403', 'retryable':False},
                            pauses={'host:arxiv.org': (NOW + timedelta(hours=1)).isoformat()})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_state(root / 'weekly-preparation/2026-10-26/acquisition.json', staged)
            callback = Mock(return_value=(None, []))
            handoff._retrieve_for_reading(item(), state_path=root/'weekly-source-acquisition.json',
                                         weekly_path=root/'weekly.json', retriever=callback, now=NOW)
        self.assertEqual(callback.call_args.kwargs['host_backoff'], {'arxiv.org':3600})
        self.assertNotIn('CORE', [name for name, _ in callback.call_args.kwargs['providers']])
        self.assertEqual(callback.call_args.kwargs['known_sources'], [])

    def test_corrupt_preparation_holds_normal_handoff_before_retriever(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_state(root/'weekly-preparation/2026-10-26/acquisition.json', {'garbage':True})
            callback = Mock()
            with self.assertRaisesRegex(ValueError, 'acquisition_metadata_invalid'):
                handoff.retrieve_for_reading(item(), state_path=root/'weekly-source-acquisition.json',
                                             weekly_path=root/'weekly.json', retriever=callback)
            callback.assert_not_called()

    def test_reader_observations_are_saved_without_changing_acquisition_identity(self):
        state = checkpoint(); before = copy.deepcopy(state)
        ledger = [denial('https://www.econstor.eu/blocked.pdf?token=SECRET#fragment'),
                  {'stage':'discovery', 'provider':'OpenAlex XML and OA locations', 'status':'http_429',
                   'retryable':True, 'retry_after_seconds':7200},
                  {'stage':'article', 'status':'source_unavailable_page', 'retryable':True,
                   'url':'https://arxiv.org/pdf/2610.12345v1', 'retry_after_seconds':3600}]
        updated = controls.merge_diagnostics_into_state(state, ledger, now=NOW)
        queue.validate_state(updated)
        self.assertEqual(state, before)
        self.assertEqual(updated['records'], state['records'])
        self.assertEqual(updated['input_fingerprint'], state['input_fingerprint'])
        self.assertNotIn('SECRET', json.dumps(updated))
        self.assertEqual(updated['access_controls']['blocked_urls'], ['https://www.econstor.eu/blocked.pdf'])
        self.assertEqual(updated['provider_pauses']['provider:OpenAlex XML and OA locations'],
                         (NOW + timedelta(hours=2)).isoformat())
        self.assertEqual(updated['provider_pauses']['host:arxiv.org'], (NOW + timedelta(hours=1)).isoformat())
        original = copy.deepcopy(updated['provider_pauses'])
        updated = controls.merge_diagnostics_into_state(updated,
            [{'stage':'discovery', 'provider':'OpenAlex XML and OA locations', 'status':'rate_limit_pause',
              'retryable':True, 'retry_after_seconds':7200}], now=NOW + timedelta(hours=1))
        self.assertEqual(updated['provider_pauses'], original)

    def test_reader_provider_denials_do_not_enable_new_acquisition_providers(self):
        state = controls.merge_diagnostics_into_state(checkpoint(),
            [{'stage':'discovery', 'provider':'Unpaywall', 'status':'http_403', 'retryable':False}], now=NOW)
        self.assertEqual(state['access_controls']['denied_providers'], ['Unpaywall'])
        self.assertNotIn('Unpaywall', queue.PROVIDERS)
        self.assertNotIn('OpenAlex XML and OA locations', queue.PROVIDERS)


    def test_normal_main_loads_shared_controls_before_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); input_path = root/'weekly.json'; state_path = root/'weekly-source-acquisition.json'
            input_path.write_text(json.dumps(weekly(item())))
            write_state(root/'weekly-preparation/2026-10-26/acquisition.json', checkpoint(denial()))
            with patch.object(sys, 'argv', ['collect_weekly_sources', '--input', str(input_path), '--state', str(state_path)]), \
                    patch.object(queue, 'run', return_value={'run':{}}) as run, \
                    patch('builtins.print'):
                self.assertEqual(queue.main(), 0)
            self.assertEqual(run.call_args.kwargs['shared_controls']['denied_hosts'], ['www.econstor.eu'])


if __name__ == '__main__': unittest.main()
