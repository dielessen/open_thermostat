"""End-to-end smoke test of the capture scripts against a faked network (no real socket is opened).

Runs, in-process and in the real order, capture_preinstall.py --stage ha-baseline, --stage e32, capture_post.py
twice (post 1 with the factory password: export refused; post 2 after the password change and the re-confirmation),
capture_independent.py, then write_receipt.py's build() on their real output folders, and checks the PASS receipt
with verify_e32_update_gate.py's home_assistant_acceptance (read-only). A second sequence does the same for an
install without a pre-install capture (capture_post.py --post-only). GitHub, Home Assistant, the E32 (through
acceptance's e32/csrf_post), the MQTT listener and the independent tool's own http.client/urllib calls are replaced
by fakes; socket.connect raises if anything slips through.

Run: python -I -m unittest discover -s tools/acceptance -p "test_*.py"
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
import acceptance as acc  # noqa: E402
import test_receipt as fx  # noqa: E402  (shared fixture documents)
import write_receipt as writer  # noqa: E402

CFG = fx.CFG
ENTRY = fx.ENTRY
SOURCE, WEB, ELF = fx.SOURCE, fx.WEB, fx.ELF
E32_HOST = 'http://192.168.1.20'


def image():
    raw = bytearray(1_100_000)
    struct.pack_into('<II', raw, 32, 0xABCD5432, 0)
    raw[48 + 128:48 + 160] = bytes.fromhex(ELF)
    marker = f'OT_E32V2_OTA_V1:{CFG.tag}:{SOURCE}:{WEB}:END'.encode()
    raw[4096:4096 + len(marker)] = marker
    return bytes(raw)


IMAGE = image()
FW = hashlib.sha256(IMAGE).hexdigest()
PUBLIC = {'version': CFG.tag, 'source_commit': SOURCE, 'web_sha256': WEB, 'sha256': FW, 'size': len(IMAGE)}
DL = f'https://github.com/{CFG.repository}/releases/download/{CFG.tag}/'
# post 1 at 09:14:10 with an uptime of 230 s and post 2 at 09:24:00 with 820 s: one boot, at 09:10:20.
CLOCK = {'pre': '2026-11-08T09:05:00.000000+00:00', 'post1': '2026-11-08T09:14:10.000000+00:00',
         'post2': '2026-11-08T09:24:00.000000+00:00'}
UPTIME = {'pre': 90000, 'post1': 230, 'post2': 820}
INSTALL = {**fx.last_install(CFG), 'sha256': FW, 'size': len(IMAGE)}


class World:
    phase = 'baseline'
    offer = CFG.tag  # what the update entity offers as latest_version

    @classmethod
    def after_update(cls):
        return cls.phase in ('post1', 'post2', 'independent')


def release_json(tag, repository):
    if tag == CFG.tag:
        return {'tag_name': tag, 'draft': False, 'prerelease': CFG.expect_prerelease, 'published_at': fx.PUBLISHED, 'assets': [
            {'name': 'firmware.bin', 'size': len(IMAGE), 'digest': 'sha256:' + FW, 'browser_download_url': DL + 'firmware.bin'},
            {'name': 'e32v2-update.json', 'size': 200, 'digest': None, 'browser_download_url': DL + 'e32v2-update.json'}]}
    return {'tag_name': tag, 'draft': False, 'prerelease': True, 'published_at': '2026-11-08T08:40:00Z', 'assets': []}


def github_bytes(url):
    if url == DL + 'firmware.bin':
        return IMAGE
    if url == DL + 'e32v2-update.json':
        return json.dumps(PUBLIC).encode()
    parts = urllib.parse.urlsplit(url).path.split('/')
    return json.dumps(release_json(urllib.parse.unquote(parts[-1]), '/'.join(parts[2:4]))).encode()


def fake_github(url, cap=acc.LIMIT, record=None):
    raw = github_bytes(url)
    assert len(raw) <= cap
    if record:
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        Path(record).write_bytes(raw)
    return raw


def update_entity():
    after = World.after_update()
    return {'entity_id': CFG.entity_id, 'state': 'off' if after else 'on', 'last_changed': '2026-11-08T09:11:31Z',
            'attributes': {'installed_version': CFG.tag if after else CFG.previous_tag, 'latest_version': World.offer,
                           'in_progress': False, 'release_url': 'x',
                           'last_install': INSTALL if after else {**INSTALL, 'tag': CFG.previous_tag, 'started_at': '2026-10-31T14:04:44Z'}}}


def ha_document(path):
    version = CFG.ha_previous_version if World.phase == 'baseline' else CFG.ha_version
    issues = {'baseline': [], 'pre': ['e32_default_password_' + ENTRY],
              'post1': ['e32_default_password_' + ENTRY, 'reconfirm_takeover_' + ENTRY]}.get(World.phase, [])
    control = {'post1': 'awaiting_confirmation', 'post2': 'active'}.get(World.phase, 'active')
    if path == '/api/config':
        return {'version': '2026.10.4', 'state': 'RUNNING', 'latitude': 52.0}
    if path == '/api/states/' + CFG.entity_id:
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
        if entity == CFG.entity_id:
            def row(progress, installed, at):
                attributes = {**update_entity()['attributes'], 'in_progress': progress, 'installed_version': installed}
                return {**update_entity(), 'last_changed': at, 'attributes': attributes}
            return [[row(False, CFG.previous_tag, '2026-11-08T08:58:00Z'), row(37, CFG.previous_tag, STARTED_ROW),
                     row(False, CFG.tag, '2026-11-08T09:11:31Z')]]
        return [[{'last_changed': '2026-11-08T09:12:00Z', 'attributes': {'control': 'awaiting_confirmation'}},
                 {'last_changed': '2026-11-08T09:19:00Z', 'attributes': {'control': control}}]]
    raise AssertionError('unexpected HA GET ' + path)


STARTED_ROW = fx.STARTED


def fake_ha_bytes(cfg, path, token, cap=4 * 1024 * 1024):
    assert token == 'TEST-TOKEN'
    assert cfg.ha_url == CFG.ha_url
    return json.dumps(ha_document(path)).encode()


def e32_document(path):
    phase = World.phase
    after = World.after_update()
    if path == '/status/version':
        return {'version': CFG.tag, 'source': SOURCE, 'sha256': ELF, 'web_sha256': WEB} if after else \
            {'version': CFG.previous_tag, 'source': 'b' * 40, 'sha256': 'c' * 64, 'web_sha256': WEB}
    if path == '/updates/status':
        return {'boot_pending': False, 'busy': False, 'phase': 'idle', 'reboot_required': False,
                'build_marker': f'OT_E32V2_OTA_V1:{CFG.tag}:{SOURCE}:{WEB}:END'}
    if path == '/status':
        return {'uptime': UPTIME.get(phase, 900)}
    if path == '/status/logs':
        return {'runtime': {'mqtt_stalled_disconnects': 0, 'mqtt_socket_error_disconnects': 0}}
    if path == '/status/heating':
        return fx.heating({'pre': 'before_active', 'post1': 'awaiting'}.get(phase, 'reconfirmed'), fresh=False)
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
    HOST = E32_HOST
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


def fake_e32(cfg, out, cookie_name, password):
    assert cfg.e32_url == E32_HOST
    LOGINS.append((World.phase, password))
    FakeE.D = Path(out)
    return FakeE, FakeClient()


def fake_csrf_post(e, client, path, body, record=None):
    assert (path, body) in (('/config/backup', {'action': 'export'}), ('/auth/logout', None)), 'POST refused'
    FakeE.append(FakeE.D / 'requests.jsonl', {'method': 'POST', 'path': path})
    if path == '/auth/logout':
        return 200, b''
    if World.phase == 'post1':  # with the factory password the E32 refuses every change
        return 403, b'{"error":"password_change_required"}'
    value = {**fx.EXPORT, **({'firmware': CFG.tag, 'learned': {'state': 'abcd'}} if World.after_update() else {})}
    raw = json.dumps(value).encode()
    if record:
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        Path(record).write_bytes(raw)
    return 200, raw


def fake_listen(cfg, credentials, seconds):
    assert json.loads(credentials)['pw'] == 'mqtt-secret'
    assert json.loads(credentials)['host'] == '192.168.1.10' and cfg.mqtt_prefix == 'ib-therm'
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
        assert host == '192.168.1.20' and port == 80

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
    if url.startswith(CFG.ha_url):
        return FakeResponse(fake_ha_bytes(CFG, url[len(CFG.ha_url):], request.get_header('Authorization')[7:]))
    return FakeResponse(github_bytes(url))


def refuse_connect(self, address):
    raise AssertionError(f'real network access attempted: {address}')


class Smoke(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='acceptance-smoke-'))
        (self.tmp / 'token.txt').write_text('TEST-TOKEN\n')
        self.config = fx.config_file(self.tmp)
        self.saved = {name: getattr(acc, name) for name in ('github', 'ha_bytes', 'e32', 'csrf_post', 'mqtt_listen')}
        acc.github, acc.ha_bytes, acc.e32, acc.csrf_post, acc.mqtt_listen = (
            fake_github, fake_ha_bytes, fake_e32, fake_csrf_post, fake_listen)
        self.saved_net = (socket.socket.connect, http.client.HTTPConnection, urllib.request.urlopen)
        socket.socket.connect = refuse_connect
        http.client.HTTPConnection = FakeConnection
        urllib.request.urlopen = fake_urlopen
        os.environ['OT_MQTT_PASSWORD'] = 'mqtt-secret'
        os.environ.pop('OT_E32_PASSWORD', None)
        LOGINS.clear()
        World.offer = CFG.tag

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
        sys.argv = [script, '--config', str(self.config), *arguments, '--token-file', str(self.tmp / 'token.txt')]
        if script == 'write_receipt.py':
            sys.argv = sys.argv[:-2]
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

    def ci_json(self):
        ci = {'commit': SOURCE, 'runs': [{'id': 1, 'name': 'PlatformIO CI', 'head_branch': CFG.tag, 'event': 'push',
                                          'status': 'completed', 'conclusion': 'success', 'html_url': 'x',
                                          'created_at': '2026-11-08T08:30:00Z'}]}
        return ci

    def assert_no_secret_written(self):
        for path in self.tmp.rglob('*'):  # no secret reached a capture file
            if path.is_file() and path.name not in ('token.txt',):
                data = path.read_bytes()
                for secret in (b'the-new-password', b'mqtt-secret', b'TEST-TOKEN'):
                    self.assertNotIn(secret, data, path)

    def test_whole_attended_sequence(self):
        t = self.tmp
        code, text = self.run_script('baseline', 'capture_preinstall.py', '--stage', 'ha-baseline', '--out', str(t / 'base'))
        self.assertEqual(code, 0, text)
        self.assertFalse((t / 'base' / 'e32').exists(), 'the baseline must not contact the E32')
        code, text = self.run_script('pre', 'capture_preinstall.py', '--stage', 'e32', '--baseline', str(t / 'base'),
                                     '--out', str(t / 'pre'), '--factory-password')
        self.assertEqual(code, 0, text)
        pre = json.loads((t / 'pre' / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
        self.assertTrue(pre['e32_before']['owned_boiler'] and pre['ha_upgrade']['single_entry_kept'])
        self.assertTrue(pre['e32_before']['password']['default_password'])
        self.assertTrue(pre['firmware']['matches_github_digest_size_and_marker'])
        self.assertEqual(pre['firmware']['sha256'], FW)
        self.assertEqual(pre['config']['tag'], CFG.tag)
        common = ['--preinstall', str(t / 'pre'), '--mqtt-user', 'acceptance', '--cache', str(t / 'cache')]
        code, text = self.run_script('post1', 'capture_post.py', *common, '--out', str(t / 'post1'), '--factory-password')
        self.assertEqual(code, 0, text)
        post1 = json.loads((t / 'post1' / 'OBSERVATION.json').read_text(encoding='utf-8'))
        self.assertEqual(post1['observation']['control_phase'], 'awaiting_reconfirm')
        self.assertEqual(post1['export']['refusal'], 'password_change_required')
        self.assertTrue(post1['info']['ha_issues']['default_password'])
        self.assertEqual(post1['mode'], 'full')
        self.assertEqual(post1['observation']['boot_at_utc'], '2026-11-08T09:10:20Z')
        self.assertIs(post1['info']['learned']['kept_over_update'], True)
        os.environ['OT_E32_PASSWORD'] = 'the-new-password'
        code, text = self.run_script('post2', 'capture_post.py', *common, '--out', str(t / 'post2'))
        self.assertEqual(code, 0, text)
        post2 = json.loads((t / 'post2' / 'OBSERVATION.json').read_text(encoding='utf-8'))
        self.assertEqual(post2['observation']['boot_at_utc'], post1['observation']['boot_at_utc'])
        code, text = self.run_script('independent', 'capture_independent.py', '--out', str(t / 'ind'),
                                     '--preinstall-backup', str(t / 'pre' / 'backup'))
        self.assertEqual(code, 0, text)
        self.assertEqual([phase for phase, _ in LOGINS], ['pre', 'post1', 'post2'])
        self.assertEqual([p for _, p in LOGINS], ['admin', 'admin', 'the-new-password'])
        self.assert_no_secret_written()
        record, limits = writer.build(CFG, t / 'pre', [t / 'post2', t / 'post1'], t / 'ind', self.ci_json())
        self.assertEqual(record['status'], 'PASS', limits)
        if fx.VERIFIER.exists():
            writer.load_verifier(fx.WORKTREE).home_assistant_acceptance(record)

    def test_post_only_sequence_without_a_pre_install_capture(self):
        t = self.tmp
        backup = t / 'daily-backup.json'
        backup.write_text(json.dumps({**fx.EXPORT, 'created': '2026-11-08T03:00:00Z'}))
        common = ['--post-only', '--history-since', '2026-11-08T08:00:00Z', '--pre-backup', str(backup),
                  '--owned-before', 'yes', '--mqtt-user', 'acceptance', '--cache', str(t / 'cache')]
        code, text = self.run_script('post1', 'capture_post.py', *common, '--out', str(t / 'post1'), '--factory-password')
        self.assertEqual(code, 0, text)
        os.environ['OT_E32_PASSWORD'] = 'the-new-password'
        code, text = self.run_script('post2', 'capture_post.py', *common, '--out', str(t / 'post2'))
        self.assertEqual(code, 0, text)
        post2 = json.loads((t / 'post2' / 'OBSERVATION.json').read_text(encoding='utf-8'))
        self.assertEqual(post2['mode'], 'post_only')
        self.assertIsNone(post2['preinstall'])
        self.assertEqual(post2['substitutes']['owned_before'], 'yes')
        self.assertEqual(post2['substitutes']['pre_backup_at'], '2026-11-08T03:00:00Z')
        self.assertTrue(post2['offered_before_install'])
        self.assertEqual(post2['install_actions'], 1)
        self.assertTrue(any('No pre-install capture' in gap for gap in post2['gaps']))
        code, text = self.run_script('independent', 'capture_independent.py', '--out', str(t / 'ind'))
        self.assertEqual(code, 0, text)
        record, limits = writer.build(CFG, None, [t / 'post1', t / 'post2'], t / 'ind', self.ci_json(), post_only=True)
        self.assertEqual(record['status'], 'PASS', limits)
        self.assertEqual(record['details']['mode'], 'post_only')
        self.assertTrue(any('Substitute evidence' in line for line in limits))
        self.assert_no_secret_written()
        if fx.VERIFIER.exists():
            writer.load_verifier(fx.WORKTREE).home_assistant_acceptance(record)

    def test_post_only_without_anything_named_cannot_be_accepted(self):
        t = self.tmp
        common = ['--post-only', '--mqtt-user', 'acceptance', '--cache', str(t / 'cache')]
        code, text = self.run_script('post1', 'capture_post.py', *common, '--out', str(t / 'post1'), '--factory-password')
        self.assertEqual(code, 2, text)  # findings failed: no history, no owner statement
        os.environ['OT_E32_PASSWORD'] = 'the-new-password'
        code, text = self.run_script('post2', 'capture_post.py', *common, '--out', str(t / 'post2'))
        self.assertEqual(code, 2, text)
        code, text = self.run_script('independent', 'capture_independent.py', '--out', str(t / 'ind'))
        self.assertEqual(code, 0, text)
        record, limits = writer.build(CFG, None, [t / 'post1', t / 'post2'], t / 'ind', self.ci_json(), post_only=True)
        self.assertEqual(record['status'], 'INCOMPLETE')
        for name in ('backup_verified', 'settings_programs_bindings_preserved', 'control_state_safe_after_restart',
                     'single_ha_install_action'):
            self.assertIs(record['checks'][name], False, name)

    def test_real_e32_wrapper_passes_the_password_to_the_login_only(self):
        """acc.e32 itself (with a stub e32client): the password reaches login_if_needed as an argument, never the environment."""
        seen = {}

        class StubClient:
            def __init__(self, cookie_name):
                self.cookie_name = cookie_name

        stub = type(sys)('e32client')
        stub.POST_ALLOWED = ('/auth/login',)
        stub.Client = StubClient

        def login(client, label, password):
            seen.update(password=password, label=label, env=os.environ.get('OT_E32_PASSWORD'), host=stub.HOST)

        stub.login_if_needed = login
        saved_module = sys.modules.get('e32client')
        sys.modules['e32client'] = stub
        os.environ.pop('OT_E32_PASSWORD', None)
        try:
            e, client = self.saved['e32'](CFG, self.tmp / 'run', 'x.cookies', 'the-new-password')
        finally:
            if saved_module is None:
                sys.modules.pop('e32client', None)
            else:
                sys.modules['e32client'] = saved_module
        self.assertEqual(seen, {'password': 'the-new-password', 'label': 'run', 'env': None, 'host': E32_HOST})
        self.assertNotIn('OT_E32_PASSWORD', os.environ)
        self.assertEqual(e.D, self.tmp / 'run')

    def test_real_e32_wrapper_refuses_an_address_outside_the_home_network(self):
        outside = acc.Config({**CFG.__dict__, 'e32_url': 'http://8.8.8.8'})
        with self.assertRaises(AssertionError):
            self.saved['e32'](outside, self.tmp / 'run', 'x.cookies', 'pw')

    def test_the_vendored_client_only_posts_to_login(self):
        sys.path.insert(0, str(HERE))
        import e32client
        http.client.HTTPConnection = self.saved_net[1]  # the real class: urllib builds its handlers from it
        e32client.D, e32client.HOST = self.tmp, E32_HOST
        client = e32client.Client('t.cookies')
        for path in ('/config/backup', '/auth/logout', '/updates/install'):
            with self.assertRaises(AssertionError):
                client.request(path, body={'action': 'x'})
        with self.assertRaises(AssertionError):
            client.request('//evil.example/x')

    def test_an_unexpected_offer_stops_before_the_e32(self):
        World.offer = 'v1.0.0-e32v2-rc.9'
        code, text = self.run_script('baseline', 'capture_preinstall.py', '--stage', 'ha-baseline',
                                     '--out', str(self.tmp / 'b'))
        self.assertEqual(code, 0, text)  # a warning at the baseline, not a stop
        self.assertIn('do NOT install', text)
        code, text = self.run_script('pre', 'capture_preinstall.py', '--stage', 'e32', '--baseline',
                                     str(self.tmp / 'b'), '--out', str(self.tmp / 'p'), '--factory-password')
        self.assertEqual(code, 2, text)
        self.assertIn('"e32_contacted": false', text)
        self.assertEqual(LOGINS, [], 'an E32 session was spent although HA was not ready')
        summary = json.loads((self.tmp / 'p' / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['kind'], 'installer_preinstall_not_ready')
        code, text = self.run_script('post1', 'capture_post.py', '--preinstall', str(self.tmp / 'p'), '--out',
                                     str(self.tmp / 'o'), '--mqtt-user', 'u', '--factory-password')
        self.assertNotEqual(code, 0)  # a not-ready folder is never accepted as a pre-install capture
        self.assertFalse((self.tmp / 'o').exists())

    def test_a_release_that_does_not_match_its_files_stops_before_the_e32(self):
        saved = dict(PUBLIC)
        PUBLIC['sha256'] = 'f' * 64
        try:
            code, text = self.run_script('baseline', 'capture_preinstall.py', '--stage', 'ha-baseline', '--out', str(self.tmp / 'b'))
            self.assertEqual(code, 0, text)
            code, text = self.run_script('pre', 'capture_preinstall.py', '--stage', 'e32', '--baseline', str(self.tmp / 'b'),
                                         '--out', str(self.tmp / 'p'), '--factory-password')
        finally:
            PUBLIC.update(saved)
        self.assertEqual(code, 2, text)
        self.assertIn('do NOT install', text)
        self.assertEqual(LOGINS, [])

    def test_a_pre_release_flag_that_does_not_follow_the_tag_is_not_published(self):
        original = release_json

        def stable_as_prerelease(tag, repository):
            value = original(tag, repository)
            value['prerelease'] = not value['prerelease'] if tag == CFG.tag else value['prerelease']
            return value
        globals()['release_json'] = stable_as_prerelease
        try:
            code, text = self.run_script('baseline', 'capture_preinstall.py', '--stage', 'ha-baseline', '--out', str(self.tmp / 'b'))
        finally:
            globals()['release_json'] = original
        self.assertEqual(code, 2, text)
        self.assertIn('is not published as a', text)

    def test_secrets_are_resolved_before_any_network(self):
        code, text = self.run_script('baseline', 'capture_preinstall.py', '--stage', 'ha-baseline', '--out', str(self.tmp / 'b'))
        self.assertEqual(code, 0, text)
        sys.stdin, saved = io.StringIO(''), sys.stdin  # no terminal, no OT_E32_PASSWORD: refuse, contact nothing
        try:
            code, text = self.run_script('pre', 'capture_preinstall.py', '--stage', 'e32', '--baseline',
                                         str(self.tmp / 'b'), '--out', str(self.tmp / 'p'))
        finally:
            sys.stdin = saved
        self.assertIn('OT_E32_PASSWORD', str(code))
        self.assertFalse((self.tmp / 'p').exists())
        self.assertEqual(LOGINS, [])

    def test_no_mqtt_login_means_the_mqtt_checks_stay_false(self):
        t = self.tmp
        self.run_script('baseline', 'capture_preinstall.py', '--stage', 'ha-baseline', '--out', str(t / 'base'))
        self.run_script('pre', 'capture_preinstall.py', '--stage', 'e32', '--baseline', str(t / 'base'),
                        '--out', str(t / 'pre'), '--factory-password')
        code, text = self.run_script('post1', 'capture_post.py', '--preinstall', str(t / 'pre'), '--no-mqtt',
                                     '--cache', str(t / 'cache'), '--out', str(t / 'post1'), '--factory-password')
        self.assertEqual(code, 2, text)
        post1 = json.loads((t / 'post1' / 'OBSERVATION.json').read_text(encoding='utf-8'))
        self.assertTrue(all(not f['ok'] for f in post1['findings'] if f['check'].startswith('mqtt.')))

    def test_a_baseline_for_another_release_is_refused(self):
        t = self.tmp
        self.run_script('baseline', 'capture_preinstall.py', '--stage', 'ha-baseline', '--out', str(t / 'base'))
        code, text = self.run_script('pre', 'capture_preinstall.py', '--stage', 'e32', '--baseline', str(t / 'base'),
                                     '--out', str(t / 'pre'), '--factory-password', '--tag', 'v1.0.0-e32v2-rc.5',
                                     '--previous-tag', CFG.tag)
        self.assertNotEqual(code, 0)
        self.assertFalse((t / 'pre').exists())


if __name__ == '__main__':
    unittest.main()
