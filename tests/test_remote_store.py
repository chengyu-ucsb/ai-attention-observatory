import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from observatory_remote_store import RemoteStore, STORE_URL, NoRedirect


class RemoteStoreTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://run.actions.githubusercontent.com/idtoken?api-version=2',
            'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'request-credential',
        })
        self.env.start(); self.addCleanup(self.env.stop)

    def test_token_audience_caching_renewal_and_safe_payload(self):
        requests, clock, responses = [], [0], []
        class Opener:
            def open(self, request, timeout):
                requests.append(request)
                if request.data is None:
                    return io.BytesIO(b'{"value":"signed.token.here"}')
                body = json.loads(request.data)
                if body['op'] == 'put_source':
                    responses.append(body)
                    return io.BytesIO(json.dumps({k: body[k] for k in ('source_id', 'fingerprint')}).encode())
                return io.BytesIO(b'{"checkpoints":1}')
        store = RemoteStore(STORE_URL, opener=Opener(), clock=lambda: clock[0])
        record = {'doi': '10.1234/EXAMPLE', 'kind': 'scholarly', 'published': 'bad-date',
                  'full_text': 'Never send this passage', 'title': 'An example'}
        store.put_source(record); store.status()
        self.assertEqual(len(requests), 3)
        self.assertEqual(parse_qs(urlsplit(requests[0].full_url).query)['audience'], [STORE_URL])
        self.assertNotIn('full_text', responses[0]['metadata'])
        self.assertIsNone(responses[0]['published_on'])
        self.assertEqual(responses[0]['source_id'], '10.1234/example')
        clock[0] = 181; store.status()
        self.assertEqual(len(requests), 5)

    def test_untrusted_destinations_and_redirects_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unrecognized_store_endpoint'):
            RemoteStore('https://example.org/store')
        for url in ('http://run.actions.githubusercontent.com/a', 'https://example.org/a',
                    'https://run.actions.githubusercontent.com.example.org/a'):
            with patch.dict(os.environ, {'ACTIONS_ID_TOKEN_REQUEST_URL': url}):
                with self.assertRaisesRegex(RuntimeError, 'github_oidc_not_available'):
                    RemoteStore(STORE_URL).status()
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.org'))

    def test_failure_is_bounded_scrubbed_and_never_reported_saved(self):
        requests = []
        class Opener:
            def open(self, request, timeout):
                requests.append(request)
                if request.data is None:
                    return io.BytesIO(b'{"value":"signed.token.here"}')
                raise HTTPError(request.full_url, 503, 'PRIVATE SECRET MESSAGE', {}, None)
        store = RemoteStore(STORE_URL, opener=Opener(), sleep=lambda _: None)
        with self.assertRaisesRegex(RuntimeError, '^private_store_request_failed$'):
            store.save_checkpoint('a'*64, 'source', 'b'*64, 'c'*64, 'C0001', {'claims': [], 'checked': True})
        self.assertEqual(len(requests), 4)


if __name__ == '__main__':
    unittest.main()
