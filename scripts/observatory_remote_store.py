"""Private Supabase bridge authenticated by short-lived GitHub Actions OIDC.

The endpoint is public configuration, not a credential. No database password or
Supabase API key leaves Supabase. All HTTP errors are scrubbed before reporting.
"""
from datetime import date
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from observatory_store import source_id, source_metadata, fingerprint

STORE_URL = 'https://jrndagmzayiwpmyjtczx.supabase.co/functions/v1/observatory-store'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward either bearer token to a redirect destination.
        return None


class RemoteStore:
    def __init__(self, endpoint=None, *, opener=None, clock=time.monotonic, sleep=time.sleep):
        self.endpoint = endpoint or os.getenv('OBSERVATORY_STORE_URL')
        if self.endpoint != STORE_URL:
            raise ValueError('unrecognized_store_endpoint')
        self.opener = opener or build_opener(NoRedirect())
        self.clock, self.sleep = clock, sleep
        self._token, self._renew_at = None, 0

    def _github_token(self):
        if self._token and self.clock() < self._renew_at:
            return self._token
        url = os.getenv('ACTIONS_ID_TOKEN_REQUEST_URL', '')
        credential = os.getenv('ACTIONS_ID_TOKEN_REQUEST_TOKEN', '')
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or not parsed.hostname or
                not parsed.hostname.endswith('.actions.githubusercontent.com') or
                parsed.username or parsed.password or parsed.port not in (None, 443) or
                parsed.fragment or not credential):
            raise RuntimeError('github_oidc_not_available')
        params = [(key, value) for key, value in parse_qsl(parsed.query) if key != 'audience']
        params.append(('audience', self.endpoint))
        target = urlunsplit(parsed._replace(query=urlencode(params)))
        request = Request(target, headers={'Authorization': 'Bearer ' + credential})
        try:
            with self.opener.open(request, timeout=20) as response:
                value = json.loads(response.read(20000))['value']
            if not isinstance(value, str) or value.count('.') != 2 or len(value) > 16000:
                raise ValueError('invalid_token')
        except Exception:
            raise RuntimeError('github_oidc_request_failed') from None
        self._token, self._renew_at = value, self.clock() + 180
        return value

    def _call(self, op, **payload):
        body = json.dumps({'op': op, **payload}, ensure_ascii=False).encode()
        if len(body) > 65536:
            raise ValueError('store_request_too_large')
        for attempt in range(3):
            request = Request(self.endpoint, data=body, method='POST', headers={
                'Authorization': 'Bearer ' + self._github_token(),
                'Content-Type': 'application/json', 'User-Agent': 'ObservatoryWorker/1.0'})
            try:
                with self.opener.open(request, timeout=25) as response:
                    result = json.loads(response.read(65537))
                if not isinstance(result, dict) or 'error' in result:
                    raise ValueError('invalid_response')
                return result
            except HTTPError as error:
                if error.code == 401:
                    self._token = None
                elif error.code not in (429, 502, 503, 504):
                    break
            except (URLError, TimeoutError):
                pass
            except Exception:
                break
            if attempt < 2:
                self.sleep(attempt + 1)
        raise RuntimeError('private_store_request_failed') from None

    def put_source(self, record):
        ident, metadata = source_id(record), source_metadata(record)
        digest = fingerprint(metadata)
        url = 'https://doi.org/' + str(record['doi']).strip() if record.get('doi') else record.get('url', '')
        if not ident or not url.startswith('https://') or record.get('kind') not in ('scholarly', 'nonacademic'):
            raise ValueError('invalid_source_identity')
        published = str(record.get('published') or '')
        try:
            published = date.fromisoformat(published).isoformat() if len(published) == 10 else None
        except ValueError:
            published = None
        saved = self._call('put_source', source_id=ident, kind=record['kind'], canonical_url=url,
                           fingerprint=digest, metadata=metadata, published_on=published)
        if saved.get('source_id') != ident or saved.get('fingerprint') != digest:
            raise RuntimeError('source_receipt_mismatch')
        return ident, digest

    def get_checkpoint(self, key):
        result = self._call('get_checkpoint', key=key)
        if 'checkpoint' not in result:
            raise RuntimeError('checkpoint_receipt_missing')
        return result['checkpoint']

    def save_checkpoint(self, key, ident, source_hash, version, segment, result):
        saved = self._call('save_checkpoint', key=key, source_id=ident, source_hash=source_hash,
                           reader_version=version, segment_id=segment, result=result)
        if saved.get('saved') is not True:
            raise RuntimeError('checkpoint_not_saved')

    def status(self):
        return self._call('status')

    def get_editorial(self, key):
        result = self._call('get_editorial', key=key)
        if type(result.get('revision')) is not int or result['revision'] < 0 or 'value' not in result:
            raise RuntimeError('editorial_checkpoint_receipt_invalid')
        return result

    def save_editorial(self, key, revision, value):
        saved = self._call('save_editorial', key=key, revision=revision, value=value)
        if saved.get('saved') is not True or type(saved.get('revision')) is not int or saved.get('revision') != revision + 1:
            raise RuntimeError('editorial_checkpoint_conflict')
        return saved['revision']

    def probe(self):
        return self._call('probe')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'probe'))
    args = parser.parse_args()
    try:
        result = getattr(RemoteStore(), args.action)()
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1)
