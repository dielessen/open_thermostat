"""Independent post-check for E32 rc.2 + HA 1.0.0rc2 (checklist section 6): a separate tool, separate code,
separate folder. Run it LAST: after the re-confirmation and after the final post capture, never at the same
time as another capture (the E32 has 4 web sessions).

It does not import e32client or rc2_acc and never reuses the installer's files. It reads the E32 and Home
Assistant directly and compares them with the public release on GitHub:
  * E32 (http://192.168.1.206): one POST /auth/login, GETs, one POST /auth/logout (also after an error).
  * HA: GET only, https://192.168.1.130:8123 only: the update entity, /api/config, the open_thermostat config
    entries and the integration's diagnostics download (only its version fields are kept).
  * GitHub: anonymous GET of the release and e32v2-update.json.

Usage (PowerShell): python -I capture_rc2_independent.py --out <new folder> [--preinstall-backup <pre>/backup]
                    [--factory-password] [--dry-run]
  E32 password: OT_E32_PASSWORD or a prompt (--factory-password: the public factory default). With
  --preinstall-backup the settings documents are compared with the installer's backup *files* read-only.
Output: INDEPENDENT-SUMMARY.json and INDEPENDENT-MANIFEST.json (its SHA-256 = independent_receipt_sha256).
"""
import argparse
import getpass
import hashlib
import http.client
import http.cookies
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TAG, PREV, HA_VERSION = 'v1.0.0-e32v2-rc.2', 'v0.1.0-e32v2-beta.22', '1.0.0rc2'
E32 = '192.168.1.206'
HA = 'https://192.168.1.130:8123'
ENTITY = 'update.woonkamer_e32_regelaar_ketel_en_diagnose_firmware'
ROUTES = ('/config/rooms', '/config/boiler', '/config/hardware', '/config/program/current', '/status/programs',
          '/config/bluetooth', '/config/heating')
CAP = 262144

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--out', required=True)
parser.add_argument('--token-file', default=str(Path(__file__).resolve().parent / 'ha-token.txt'))
parser.add_argument('--preinstall-backup')
parser.add_argument('--factory-password', action='store_true')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
if args.dry_run:
    print('DRY RUN capture_rc2_independent.py: nothing is sent, read from the network, prompted or written.')
    planned = ['resolve the E32 password first (' + ('factory default' if args.factory_password
                                                    else 'OT_E32_PASSWORD or a prompt') + ')',
               'refuse a non-empty --out folder',
               f'GitHub GET api.github.com/repos/dielessen/open_thermostat/releases/tags/{TAG} and e32v2-update.json',
               f'E32 POST http://{E32}/auth/login once, GET /auth/session',
               'E32 GET /status/version, /updates/status, /status, /status/heating, ' + ', '.join(ROUTES),
               'E32 POST /auth/logout (also after an error)',
               f'HA GET /api/states/{ENTITY}, /api/config, /api/config/config_entries/entry?domain=open_thermostat, '
               '/api/diagnostics/config_entry/<entry id> (only the version fields are kept)']
    if args.preinstall_backup:
        planned.append(f'read {args.preinstall_backup} (installer backup files, read-only, to compare)')
    for line in planned:
        print('  would ' + line)
    sys.exit(0)


def secret():
    if args.factory_password:
        return 'admin'  # the public factory default
    value = os.environ.get('OT_E32_PASSWORD')
    if value:
        return value
    if sys.stdin is not None and sys.stdin.isatty():
        value = getpass.getpass('E32 web password (user admin): ')
        if value:
            return value
    raise SystemExit('Set OT_E32_PASSWORD in this window or run interactively for a prompt (never on the command line).')


password = secret()
out = Path(args.out).resolve()
if out.exists() and any(out.iterdir()):
    raise SystemExit(f'{out} is not empty')
out.mkdir(parents=True, exist_ok=True)
log = []


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def keep(name, raw):
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return json.loads(raw) if raw[:1] in (b'{', b'[') else raw


class Device:
    """Plain http.client session with the E32; the cookie and CSRF value are never written to disk."""
    def __init__(self):
        self.cookie, self.csrf = None, None

    def call(self, method, path, body=None, kind=None):
        connection = http.client.HTTPConnection(E32, 80, timeout=40)
        headers = {'Origin': 'http://' + E32, 'Cache-Control': 'no-store'}
        if self.cookie:
            headers['Cookie'] = self.cookie
        if method == 'POST' and self.csrf:
            headers['X-OpenThermostat-CSRF'] = self.csrf
        if kind:
            headers['Content-Type'] = kind
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read(CAP + 1)
        assert len(raw) <= CAP
        for header in response.headers.get_all('Set-Cookie') or []:
            morsel = http.cookies.SimpleCookie(header)
            if 'OTSESSION' in morsel:
                self.cookie = 'OTSESSION=' + morsel['OTSESSION'].value
        connection.close()
        log.append({'at_utc': now(), 'method': method, 'path': path, 'http_status': response.status, 'bytes': len(raw)})
        return response.status, raw

    def login(self, secret_value):
        status, _ = self.call('POST', '/auth/login', urllib.parse.urlencode(
            {'username': 'admin', 'password': secret_value}), 'application/x-www-form-urlencoded')
        assert status == 200, f'login HTTP{status}; not retried'
        status, raw = self.call('GET', '/auth/session')
        assert status == 200
        session = json.loads(raw)
        self.csrf = session['csrf']
        return session.get('default_password')

    def get(self, path, name):
        status, raw = self.call('GET', path)
        assert status == 200, f'{path}: HTTP{status}'
        return keep(name, raw)


def fetch(url, headers, name=None, context=None, cap=CAP):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60, context=context) as r:
        raw = r.read(cap + 1)
    assert len(raw) <= cap
    log.append({'at_utc': now(), 'method': 'GET', 'url': url.split('?')[0], 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest()})
    return keep(name, raw) if name else json.loads(raw)


def phase(heating):
    """The active-control state in plain terms: waiting for the owner, taken over again, or shadow."""
    a = heating.get('active') or {}
    command = a.get('command') or {}
    heat = bool(command.get('send')) and (command.get('flow_c') or 0) > 0
    if a.get('reconfirm_required') is True:
        return 'waiting', a.get('state') == 'awaiting_confirmation' and (not heat or command.get('why') == 'frost_unconfirmed')
    if a.get('confirmation_stored') is True:
        return 'taken_over', a.get('state') in ('arming', 'active') and 'foreign_controller' not in (a.get('warnings') or [])
    return a.get('state'), a.get('state') == 'shadow' and not heat


checks = {}
gh = {'User-Agent': 'openthermostat-independent-check', 'Accept': 'application/vnd.github+json'}
release = fetch(f'https://api.github.com/repos/dielessen/open_thermostat/releases/tags/{TAG}', gh, 'github/release.json')
asset = {a['name']: a for a in release['assets']}
public = fetch(asset['e32v2-update.json']['browser_download_url'], {'User-Agent': gh['User-Agent']},
               'github/e32v2-update.json')
checks['release_published'] = release['draft'] is False and release['prerelease'] is True \
    and asset['firmware.bin']['digest'] == 'sha256:' + public['sha256'] and asset['firmware.bin']['size'] == public['size']

device = Device()
try:
    default_password = device.login(password)
    del password
    version = device.get('/status/version', 'e32/version.json')
    updates = device.get('/updates/status', 'e32/updates.json')
    status = device.get('/status', 'e32/status.json')
    heating = device.get('/status/heating', 'e32/heating.json')
    settings = {path: device.get(path, 'e32/settings/' + path.strip('/').replace('/', '-') + '.json') for path in ROUTES}
finally:
    if device.cookie:  # signed in: always sign out again (one of the E32's 4 web sessions)
        try:
            device.call('POST', '/auth/logout', b'')
        except OSError:
            pass
checks['identity_matches_public_release'] = (version.get('version') == public['version'] == TAG
                                             and version.get('source') == public['source_commit']
                                             and version.get('web_sha256') == public['web_sha256'])
checks['boot_confirmed'] = updates.get('boot_pending') is False and not updates.get('busy')
control_phase, control_ok = phase(heating)
taken_over_before = (heating.get('active') or {}).get('taken_over_before') is True
checks['control_state_safe'] = control_ok
# The E32 controlled the boiler before the update (rc.2 reports it): the owner must have confirmed again.
checks['takeover_reconfirmed'] = control_phase == 'taken_over' if taken_over_before else control_phase == 'shadow'
if args.preinstall_backup:
    backup = Path(args.preinstall_backup)
    same = {}
    for path in ROUTES:
        name = path.strip('/').replace('/', '-') + '.json'
        before = json.loads((backup / name).read_bytes())
        after = settings[path]
        if path == '/config/bluetooth':  # bound sensors must stay; their runtime readings may move
            ids = lambda doc: sorted(json.dumps({k: v for k, v in d.items() if k in ('id', 'address', 'mac', 'name', 'model', 'type', 'key')},
                                                sort_keys=True) for d in (doc.get('devices') or doc.get('sensors') or []) if isinstance(d, dict)) \
                if isinstance(doc, dict) else doc
            same[path] = ids(before) == ids(after)
        elif path == '/config/heating':  # the plan; its revision counter is device-local history
            same[path] = all(after.get(k) == v for k, v in before.items() if k != 'revision')
        else:
            same[path] = all(after.get(k) == v for k, v in before.items()) if isinstance(before, dict) else before == after
    checks['settings_same_as_preinstall_backup'] = all(same.values())
    checks['settings_detail'] = same

token = Path(args.token_file).read_text(encoding='utf-8').strip()
context = ssl.create_default_context()
context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
assert urllib.parse.urlsplit(HA).hostname == '192.168.1.130'
auth = {'Authorization': 'Bearer ' + token}
entity = fetch(HA + '/api/states/' + ENTITY, auth, 'ha/update-entity.json', context)
config = fetch(HA + '/api/config', auth, None, context)
entries = [e for e in fetch(HA + '/api/config/config_entries/entry?domain=open_thermostat', auth,
                            'ha/config-entries.json', context) if e.get('domain') == 'open_thermostat']
integration = None
if len(entries) == 1:
    diagnostics = fetch(HA + '/api/diagnostics/config_entry/' + urllib.parse.quote(entries[0]['entry_id'], safe=''),
                        auth, None, context, cap=16 * 1024 * 1024)
    manifest = diagnostics.get('integration_manifest') or {}
    listed = ((diagnostics.get('custom_components') or {}).get('open_thermostat') or {}).get('version')
    integration = manifest.get('version') if manifest.get('domain') == 'open_thermostat' and manifest.get('version') == listed else None
    keep('ha/integration-version.json', (json.dumps({'manifest_version': manifest.get('version'),
                                                     'custom_component_version': listed}) + '\n').encode())
attributes = entity.get('attributes', {})
checks['ha_reports_new_version'] = attributes.get('installed_version') == TAG and entity.get('state') == 'off'
reported = (attributes.get('last_install') or {}).get('reported') or {}
checks['ha_last_install_matches_e32'] = reported == {'version': TAG, 'source_commit': version.get('source'),
                                                     'web_sha256': version.get('web_sha256'), 'elf_sha256': version.get('sha256')}
checks['ha_one_config_entry'] = len(entries) == 1 and entries[0].get('state') == 'loaded'
checks['ha_integration_version'] = integration == HA_VERSION

summary = {'schema': 1, 'kind': 'independent_postcheck', 'tool': 'capture_rc2_independent.py (own HTTP code)',
           'at_utc': now(), 'tag': TAG, 'e32': {'version': version.get('version'), 'source_commit': version.get('source'),
           'web_sha256': version.get('web_sha256'), 'elf_sha256': version.get('sha256'), 'uptime_seconds': status.get('uptime'),
           'boot_pending': updates.get('boot_pending'), 'control_phase': control_phase,
           'taken_over_before': taken_over_before, 'default_password': default_password,
           'own_password_in_use': default_password is False},
           'ha_core_version': config.get('version'), 'ha_integration_version': integration, 'checks': checks,
           'passed': all(v is True for k, v in checks.items() if k != 'settings_detail'), 'requests': log}
keep('INDEPENDENT-SUMMARY.json', (json.dumps(summary, indent=2) + '\n').encode())
files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != 'INDEPENDENT-MANIFEST.json')
manifest = {'schema': 1, 'kind': 'independent_postcheck', 'files': [
    {'file': p.relative_to(out).as_posix(), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
(out / 'INDEPENDENT-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'out': str(out), 'passed': summary['passed'], 'checks': checks,
                  'independent_receipt_sha256': hashlib.sha256((out / 'INDEPENDENT-MANIFEST.json').read_bytes()).hexdigest()},
                 indent=1))
sys.exit(0 if summary['passed'] else 2)
