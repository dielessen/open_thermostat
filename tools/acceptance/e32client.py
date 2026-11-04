"""Bounded HTTP client for the attended E32 acceptance: GETs plus at most one POST /auth/login per session.

Vendored from the install clients of beta.18 to beta.22, reduced to what the acceptance kit needs and made
generic: the E32's address is set by the caller (acceptance.e32 sets `HOST` from the kit's configuration), the
password is passed to login_if_needed (it is never read from, or put into, the process environment here), and
every network error is reported to the caller, never retried here.

Rules (binding for every script of the kit):
  * One session at a time. The E32 allows 4 web sessions and Home Assistant needs its own for the update.
  * Every response is bounded (262144 bytes), redirects are refused, no proxy is used.
  * The only POST this client sends is /auth/login (POST_ALLOWED). acceptance.csrf_post adds the two other
    POSTs of the kit (the passphrase-less settings export and the sign-out) with the session's CSRF header.
  * It never records authentication bodies, CSRF values or cookie headers. The cookie jar is a file in the
    capture folder that acceptance.logout removes again after the sign-out.
"""
import datetime as dt
import hashlib
import http.client
import http.cookiejar
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

D = Path(__file__).resolve().parent  # the capture folder; acceptance.e32 sets it per run
HOST = None  # set by acceptance.e32 from the configuration (e32_url) before any request
POST_ALLOWED = ('/auth/login',)
NETWORK_ERRORS = (OSError, http.client.HTTPException)  # URLError, timeouts, resets, bad status lines
LIMIT = 262144


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def append(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(obj, ensure_ascii=False) + '\n')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError('Redirect refused')


def probe(timeout=3):
    """Unauthenticated, cookie-less GET /auth/session. Returns the HTTP status or None (no answer)."""
    assert HOST, 'e32client.HOST is not set'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(HOST + '/auth/session', headers={'Origin': HOST, 'Cache-Control': 'no-store'})
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    except NETWORK_ERRORS:
        return None
    try:
        with response:
            response.read(4096)
            return response.code
    except NETWORK_ERRORS:
        return None


class Client:
    def __init__(self, cookie_name='session.cookies'):
        cookies = D / cookie_name
        self.jar = http.cookiejar.MozillaCookieJar(str(cookies))
        if cookies.exists():
            self.jar.load(ignore_discard=True, ignore_expires=True)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                                  urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = None

    def request(self, path, *, body=None, form=False, record=None, timeout=40):
        assert HOST, 'e32client.HOST is not set'
        assert path.startswith('/') and not path.startswith('//')
        method = 'GET' if body is None else 'POST'
        assert method == 'GET' or path in POST_ALLOWED, 'POST route not allowed by this client'
        headers = {'Origin': HOST, 'Cache-Control': 'no-store'}
        data = None
        if body is not None:
            data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        started = now()
        try:
            response = self.opener.open(urllib.request.Request(HOST + path, data=data, headers=headers, method=method),
                                        timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        except NETWORK_ERRORS as error:
            append(D / 'requests.jsonl', {'at_utc': started, 'finished_at_utc': now(), 'method': method, 'path': path,
                                          'error': type(error).__name__})
            raise
        with response:
            status = response.code
            raw = response.read(LIMIT + 1)
            assert len(raw) <= LIMIT, 'Response bound exceeded'
        self.jar.save(ignore_discard=True, ignore_expires=True)
        if record:
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_bytes(raw)
        meta = {'at_utc': started, 'finished_at_utc': now(), 'method': method, 'path': path,
                'http_status': status, 'bytes': len(raw)}
        if path not in ('/auth/session', '/auth/login'):
            meta['sha256'] = digest(raw)
        if record:
            meta['file'] = str(record.relative_to(D))
        append(D / 'requests.jsonl', meta)
        return status, raw

    def session(self):
        status, raw = self.request('/auth/session')
        if status == 200:
            self.csrf = json.loads(raw)['csrf']
        return status

    def read(self, path, directory, name):
        status, raw = self.request(path, record=directory / (name + '.json'))
        assert status == 200, f'{path}: HTTP{status}'
        return json.loads(raw)


def login_if_needed(client, label, password):
    """At most one POST /auth/login per call; never retried. The password is a parameter, never recorded."""
    status = client.session()
    if status == 401:
        save(D / f'login-intent-{label}.json', {'at_utc': now(), 'count': 1})
        code, _ = client.request('/auth/login', body={'username': 'admin', 'password': password}, form=True)
        assert code == 200, f'Login failed HTTP{code}; no retry'
        status = client.session()
    assert status == 200, f'Session unavailable HTTP{status}'
