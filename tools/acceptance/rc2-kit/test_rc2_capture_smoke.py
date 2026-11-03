"""End-to-end smoke test of the rc.2 capture scripts against a faked network (no real socket is opened).

Runs, in-process and in the real order, capture_rc2_preinstall.py --stage ha-baseline, --stage e32,
capture_rc2_post.py twice (post 1 with the factory password: export refused; post 2 after the password change
and the re-confirmation), capture_rc2_independent.py, then write_rc2_receipt.py's build() on their real output
folders, and checks the PASS receipt with verify_e32_update_gate.py's home_assistant_acceptance (read-only).
GitHub, Home Assistant, the E32 (through rc2_acc's e32/csrf_post), the WSL MQTT listener and the independent
tool's own http.client/urllib calls are replaced by fakes; socket.connect raises if anything slips through.

Run: python -I test_rc2_capture_smoke.py [-v]
"""
import contextlib
import hashlib
import http.client
import io
import json
import os
import runpy
import shutil
import socket
import struct
import sys
import tempfile
import unittest
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rc2_acc as acc  # noqa: E402
import test_rc2_receipt as fx  # noqa: E402  (shared fixture documents)
import write_rc2_receipt as writer  # noqa: E402

ENTRY = fx.ENTRY
SOURCE, WEB, ELF = fx.SOURCE, fx.WEB, fx.ELF


def image():
    raw = bytearray(1_100_000)
    struct.pack_into('<II', raw, 32, 0xABCD5432, 0)
    raw[48 + 128:48 + 160] = bytes.fromhex(ELF)
    marker = f'OT_E32V2_OTA_V1:{acc.TAG}:{SOURCE}:{WEB}:END'.encode()
    raw[4096:4096 + len(marker)] = marker
    return bytes(raw)


IMAGE = image()
FW = hashlib.sha256(IMAGE).hexdigest()
PUBLIC = {'version': acc.TAG, 'source_commit': SOURCE, 'web_sha256': WEB, 'sha256': FW, 'size': len(IMAGE)}
DL = f'https://github.com/{acc.REPOSITORY}/releases/download/{acc.TAG}/'
CLOCK = {'pre': '2026-11-08T09:05:00.000000+00:00', 'post1': '2026-11-08T09:14:10.000000+00:00',
         'post2': '2026-11-08T09:24:00.000000+00:00'}
UPTIME = {'pre': 90000, 'post1': 230, 'post2': 820}
INSTALL = {**fx.last_install(), 'sha256': FW, 'size': len(IMAGE)}


class World:
    phase = 'baseline'
    offer = acc.TAG  # what the update entity offers as latest_version

    @classmethod
    def after_update(cls):
        return cls.phase in ('post1', 'post2', 'independent')


def release_json(tag):
    if tag == acc.TAG:
        return {'tag_name': tag, 'draft': False, 'prerelease': True, 'published_at': fx.PUBLISHED, 'assets': [
            {'name': 'firmware.bin', 'size': len(IMAGE), 'digest': 'sha256:' + FW, 'browser_download_url': DL + 'firmware.bin'},
            {'name': 'e32v2-update.json', 'size': 200, 'digest': None, 'browser_download_url': DL + 'e32v2-update.json'}]}
    return {'tag_name': tag, 'draft': False, 'prerelease': True, 'published_at': '2026-11-08T08:40:00Z', 'assets': []}


def github_bytes(url):
    if url == DL + 'firmware.bin':
        return IMAGE
    if url == DL + 'e32v2-update.json':
        return json.dumps(PUBLIC).encode()
    return json.dumps(release_json(urllib.parse.unquote(url.rsplit('/', 1)[1]))).encode()


def fake_github(url, cap=acc.LIMIT, record=None):
    raw = github_bytes(url)
    assert len(raw) <= cap
    if record:
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        Path(record).write_bytes(raw)
    return raw


def update_entity():
    after = World.after_update()
    return {'entity_id': acc.ENTITY, 'state': 'off' if after else 'on', 'last_changed': '2026-11-08T09:11:31Z',
            'attributes': {'installed_version': acc.TAG if after else acc.PREV, 'latest_version': World.offer,
                           'in_progress': False, 'release_url': 'x',
                           'last_install': INSTALL if after else {**INSTALL, 'tag': acc.PREV, 'started_at': '2026-10-31T14:04:44Z'}}}


def ha_document(path):
    version = acc.HA_PREV_VERSION if World.phase == 'baseline' else acc.HA_VERSION
    issues = {'baseline': [], 'pre': ['e32_default_password_' + ENTRY],
              'post1': ['e32_default_password_' + ENTRY, 'reconfirm_takeover_' + ENTRY]}.get(World.phase, [])
    control = {'post1': 'awaiting_confirmation', 'post2': 'active'}.get(World.phase, 'active')
    if path == '/api/config':
        return {'version': '2026.10.4', 'state': 'RUNNING', 'latitude': 52.0}
    if path == '/api/states/' + acc.ENTITY:
        return update_entity()
    if path == f'/api/config/config_entries/entry?domain={acc.DOMAIN}':
        return fx.entries()
    if path == '/api/diagnostics/config_entry/' + ENTRY:
        return fx.diagnostics(version, issues=issues)
    if path == '/api/states':
        listed = fx.states()
        listed[2]['attributes'] = {'mode': 'active', 'reason': 'heating', 'rooms': [], 'revision': 7,
                                   **({} if World.phase == 'baseline' else {'control': control})}
        return [update_entity(), *listed[1:]]
    if path.startswith('/api/history/period/'):
        entity = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)['filter_entity_id'][0]
        if entity == acc.ENTITY:
            row = lambda progress: {**update_entity(), 'attributes': {**update_entity()['attributes'], 'in_progress': progress}}
            return [[row(False), row(37), row(False)]]
        return [[{'last_changed': '2026-11-08T09:12:00Z', 'attributes': {'control': 'awaiting_confirmation'}},
                 {'last_changed': '2026-11-08T09:19:00Z', 'attributes': {'control': control}}]]
    raise AssertionError('unexpected HA GET ' + path)


def fake_ha_bytes(path, token, cap=4 * 1024 * 1024):
    assert token == 'TEST-TOKEN'
    return json.dumps(ha_document(path)).encode()


def e32_document(path):
    phase = World.phase
    after = World.after_update()
    if path == '/status/version':
        return {'version': acc.TAG, 'source': SOURCE, 'sha256': ELF, 'web_sha256': WEB} if after else \
            {'version': acc.PREV, 'source': 'b' * 40, 'sha256': 'c' * 64, 'web_sha256': WEB}
    if path == '/updates/status':
        return {'boot_pending': False, 'busy': False, 'phase': 'idle', 'reboot_required': False,
                'build_marker': f'OT_E32V2_OTA_V1:{acc.TAG}:{SOURCE}:{WEB}:END'}
    if path == '/status':
        return {'uptime': UPTIME.get(phase, 900)}
    if path == '/status/logs':
        return {'runtime': {'mqtt_stalled_disconnects': 0, 'mqtt_socket_error_disconnects': 0}}
    if path == '/status/heating':
        return fx.heating({'pre': 'beta22_active', 'post1': 'awaiting'}.get(phase, 'reconfirmed'), fresh=phase != 'pre')
    if path == '/auth/session':
        return {'authenticated': True, 'csrf': 'CSRF', 'default_password': phase in ('pre', 'post1')}
    if path == '/config/programs/week':
        return fx.SETTINGS['program-000.json']
    name = path.strip('/').replace('/', '-') + '.json'
    if name in fx.SETTINGS:
        value = json.loads(json.dumps(fx.SETTINGS[name]))
        if after and name == 'config-heating.json':
            value.update(revision=9, features=['levels'])
        return value
    raise AssertionError('unexpected E32 GET ' + path)


class FakeE:
    HOST = 'http://192.168.1.206'
    D = None

    @staticmethod
    def now():
        return CLOCK[World.phase]

    @staticmethod
    def append(path, obj):
        with Path(path).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(obj) + '\n')


class FakeClient:
    csrf = 'CSRF'

    def request(self, path, record=None):
        raw = json.dumps(e32_document(path)).encode()
        if record:
            Path(record).parent.mkdir(parents=True, exist_ok=True)
            Path(record).write_bytes(raw)
        FakeE.append(FakeE.D / 'requests.jsonl', {'method': 'GET', 'path': path})
        return 200, raw

    def read(self, path, directory, name):
        return json.loads(self.request(path, record=Path(directory) / (name + '.json'))[1])

    def session(self):
        return 200


LOGINS = []


def fake_e32(out, cookie_name, password):
    LOGINS.append((World.phase, password))
    FakeE.D = Path(out)
    return FakeE, FakeClient()


def fake_csrf_post(e, client, path, body, record=None):
    assert (path, body) in (('/config/backup', {'action': 'export'}), ('/auth/logout', None)), 'POST refused'
    FakeE.append(FakeE.D / 'requests.jsonl', {'method': 'POST', 'path': path})
    if path == '/auth/logout':
        return 200, b''
    if World.phase == 'post1':  # rc.2 with the factory password refuses every change
        return 403, b'{"error":"password_change_required"}'
    value = {**fx.EXPORT, **({'firmware': acc.TAG, 'learned': {'state': 'abcd'}} if World.after_update() else {})}
    raw = json.dumps(value).encode()
    if record:
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        Path(record).write_bytes(raw)
    return 200, raw


def fake_listen(credentials, seconds):
    assert json.loads(credentials)['pw'] == 'mqtt-secret'
    return fx.mqtt_text().encode()


# ---- the independent tool's own HTTP code (http.client for the E32, urllib for GitHub and HA)

class FakeResponse(io.BytesIO):
    def __init__(self, raw, status=200, cookie=None):
        super().__init__(raw)
        self.status = status
        self.headers = http.client.HTTPMessage()
        if cookie:
            self.headers['Set-Cookie'] = cookie

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, host, port, timeout=None):
        assert host == '192.168.1.206' and port == 80

    def request(self, method, path, body=None, headers=None):
        self.method, self.path = method, path

    def getresponse(self):
        if self.method == 'POST' and self.path == '/auth/login':
            return FakeResponse(b'{"authenticated":true}', cookie='OTSESSION=abc; Path=/; HttpOnly')
        if self.method == 'POST' and self.path == '/auth/logout':
            return FakeResponse(b'')
        assert self.method == 'GET', self.path
        return FakeResponse(json.dumps(e32_document(self.path)).encode())

    def close(self):
        pass


def fake_urlopen(request, timeout=None, context=None):
    url = request.full_url
    if url.startswith(acc.HA_URL):
        return FakeResponse(fake_ha_bytes(url[len(acc.HA_URL):], request.get_header('Authorization')[7:]))
    return FakeResponse(github_bytes(url))


def refuse_connect(self, address):
    raise AssertionError(f'real network access attempted: {address}')


class Smoke(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='rc2-smoke-'))
        (self.tmp / 'token.txt').write_text('TEST-TOKEN\n')
        self.saved = {name: getattr(acc, name) for name in ('github', 'ha_bytes', 'e32', 'csrf_post', 'mqtt_listen')}
        acc.github, acc.ha_bytes, acc.e32, acc.csrf_post, acc.mqtt_listen = (
            fake_github, fake_ha_bytes, fake_e32, fake_csrf_post, fake_listen)
        self.saved_net = (socket.socket.connect, http.client.HTTPConnection, urllib.request.urlopen)
        socket.socket.connect = refuse_connect
        http.client.HTTPConnection = FakeConnection
        urllib.request.urlopen = fake_urlopen
        os.environ['OT_MQTT_PASSWORD'] = 'mqtt-secret'
        LOGINS.clear()

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(acc, name, value)
        socket.socket.connect, http.client.HTTPConnection, urllib.request.urlopen = self.saved_net
        for name in ('OT_MQTT_PASSWORD', 'OT_E32_PASSWORD'):
            os.environ.pop(name, None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, phase, script, *arguments):
        World.phase = phase
        argv = sys.argv
        sys.argv = [script, *arguments, '--token-file', str(self.tmp / 'token.txt')]
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                runpy.run_path(str(HERE / script), run_name='__main__')
            code = 0
        except SystemExit as exit_:
            code = exit_.code
        finally:
            sys.argv = argv
        return code, output.getvalue()

    def test_whole_attended_sequence(self):
        t = self.tmp
        code, text = self.run_script('baseline', 'capture_rc2_preinstall.py', '--stage', 'ha-baseline', '--out', str(t / 'base'))
        self.assertEqual(code, 0, text)
        self.assertFalse((t / 'base' / 'e32').exists(), 'the baseline must not contact the E32')
        code, text = self.run_script('pre', 'capture_rc2_preinstall.py', '--stage', 'e32', '--baseline', str(t / 'base'),
                                     '--out', str(t / 'pre'), '--factory-password')
        self.assertEqual(code, 0, text)
        pre = json.loads((t / 'pre' / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
        self.assertTrue(pre['e32_before']['owned_boiler'] and pre['ha_migration']['single_entry_kept'])
        self.assertTrue(pre['e32_before']['password']['default_password'])
        common = ['--preinstall', str(t / 'pre'), '--mqtt-user', 'acceptance', '--cache', str(t / 'cache')]
        code, text = self.run_script('post1', 'capture_rc2_post.py', *common, '--out', str(t / 'post1'), '--factory-password')
        self.assertEqual(code, 0, text)
        post1 = json.loads((t / 'post1' / 'OBSERVATION.json').read_text(encoding='utf-8'))
        self.assertEqual(post1['observation']['control_phase'], 'awaiting_reconfirm')
        self.assertEqual(post1['export']['refusal'], 'password_change_required')
        self.assertTrue(post1['info']['ha_issues']['default_password'])
        self.assertTrue(post1['info']['learned']['fresh'])
        os.environ['OT_E32_PASSWORD'] = 'the-new-password'
        code, text = self.run_script('post2', 'capture_rc2_post.py', *common, '--out', str(t / 'post2'))
        self.assertEqual(code, 0, text)
        code, text = self.run_script('independent', 'capture_rc2_independent.py', '--out', str(t / 'ind'),
                                     '--preinstall-backup', str(t / 'pre' / 'backup'))
        self.assertEqual(code, 0, text)
        self.assertEqual([phase for phase, _ in LOGINS], ['pre', 'post1', 'post2'])
        self.assertEqual([p for _, p in LOGINS], ['admin', 'admin', 'the-new-password'])
        for folder in t.rglob('*'):  # no secret reached a capture file
            if folder.is_file() and folder.name != 'token.txt':
                data = folder.read_bytes()
                self.assertNotIn(b'the-new-password', data, folder)
                self.assertNotIn(b'mqtt-secret', data, folder)
                self.assertNotIn(b'TEST-TOKEN', data, folder)
        ci = {'commit': SOURCE, 'runs': [{'id': 1, 'name': 'PlatformIO CI', 'head_branch': acc.TAG, 'event': 'push',
                                          'status': 'completed', 'conclusion': 'success', 'html_url': 'x',
                                          'created_at': '2026-11-08T08:30:00Z'}]}
        record, limits = writer.build(t / 'pre', [t / 'post2', t / 'post1'], t / 'ind', ci)
        self.assertEqual(record['status'], 'PASS', limits)
        if fx.VERIFIER.exists():
            writer.load_verifier(fx.WORKTREE).home_assistant_acceptance(record)

    def test_real_e32_wrapper_drops_the_password_after_login(self):
        """acc.e32 itself (with a stub e32client): the password reaches login_if_needed only, then leaves os.environ."""
        seen = {}

        class StubClient:
            def __init__(self, cookie_name):
                self.cookie_name = cookie_name

        stub = type(sys)('e32client')
        stub.POST_ALLOWED = ('/auth/login',)
        stub.Client = StubClient
        stub.login_if_needed = lambda client, label: seen.update(password=os.environ.get('OT_E32_PASSWORD'), label=label)
        saved_module = sys.modules.get('e32client')
        sys.modules['e32client'] = stub
        os.environ.pop('OT_E32_PASSWORD', None)
        try:
            e, client = self.saved['e32'](self.tmp / 'run', 'x.cookies', 'the-new-password')
        finally:
            if saved_module is None:
                sys.modules.pop('e32client', None)
            else:
                sys.modules['e32client'] = saved_module
        self.assertEqual(seen, {'password': 'the-new-password', 'label': 'run'})
        self.assertNotIn('OT_E32_PASSWORD', os.environ)
        self.assertEqual(e.D, self.tmp / 'run')

    def test_rc1_offered_stops_before_the_e32(self):
        World.offer = 'v1.0.0-e32v2-rc.1'
        try:
            code, text = self.run_script('baseline', 'capture_rc2_preinstall.py', '--stage', 'ha-baseline',
                                         '--out', str(self.tmp / 'b'))
            self.assertEqual(code, 0, text)  # a warning at the baseline, not a stop
            self.assertIn('do NOT install', text)
            code, text = self.run_script('pre', 'capture_rc2_preinstall.py', '--stage', 'e32', '--baseline',
                                         str(self.tmp / 'b'), '--out', str(self.tmp / 'p'), '--factory-password')
        finally:
            World.offer = acc.TAG
        self.assertEqual(code, 2, text)
        self.assertIn('"e32_contacted": false', text)
        self.assertEqual(LOGINS, [], 'an E32 session was spent although HA was not ready')
        summary = json.loads((self.tmp / 'p' / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['kind'], 'installer_preinstall_not_ready')
        code, text = self.run_script('post1', 'capture_rc2_post.py', '--preinstall', str(self.tmp / 'p'), '--out',
                                     str(self.tmp / 'o'), '--mqtt-user', 'u', '--factory-password')
        self.assertNotEqual(code, 0)  # a not-ready folder is never accepted as a pre-install capture
        self.assertFalse((self.tmp / 'o').exists())

    def test_secrets_are_resolved_before_any_network(self):
        code, text = self.run_script('baseline', 'capture_rc2_preinstall.py', '--stage', 'ha-baseline', '--out', str(self.tmp / 'b'))
        self.assertEqual(code, 0, text)
        sys.stdin, saved = io.StringIO(''), sys.stdin  # no terminal, no OT_E32_PASSWORD: refuse, contact nothing
        try:
            code, text = self.run_script('pre', 'capture_rc2_preinstall.py', '--stage', 'e32', '--baseline',
                                         str(self.tmp / 'b'), '--out', str(self.tmp / 'p'))
        finally:
            sys.stdin = saved
        self.assertIn('OT_E32_PASSWORD', str(code))
        self.assertFalse((self.tmp / 'p').exists())
        self.assertEqual(LOGINS, [])


if __name__ == '__main__':
    unittest.main()
