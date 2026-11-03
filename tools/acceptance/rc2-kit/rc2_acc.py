"""Shared helpers for the attended beta.22 -> rc.2 acceptance on the Home Assistant route.

E32 v0.1.0-e32v2-beta.22 -> v1.0.0-e32v2-rc.2 through the HA Firmware update entity, after HA 0.4.0b15 (manual
install) -> 1.0.0rc2 through HACS. rc.1 (v1.0.0-e32v2-rc.1 / 1.0.0rc1) is never installed.

Used by capture_rc2_preinstall.py, capture_rc2_post.py and write_rc2_receipt.py. capture_rc2_independent.py
deliberately does NOT import this module.

Network rules (binding):
  * E32: only through out/beta19-install/e32client.py: GETs plus at most one POST /auth/login per session. The
    only extra POSTs are POST /config/backup {"action":"export"} (no passphrase) and POST /auth/logout, both with
    the session's CSRF header. Every session ends with a logout (also after an error). One session at a time:
    the E32 has 4 web sessions and Home Assistant needs its own for the update.
  * E32 password: OT_E32_PASSWORD or a getpass prompt, or --factory-password for the public factory default.
    Never on the command line, never in a file; removed from the process environment after the login.
  * MQTT (preferred over E32 web sessions for liveness): a read-only listener; the broker password comes from
    OT_MQTT_PASSWORD or a prompt (the Samba share with HA's stored credentials is not readable any more).
  * Home Assistant: GET only, and only https://192.168.1.130:8123 (self-signed certificate), with the token file
    in the scratchpad. Nothing is posted to HA: no service calls, no websocket.
  * GitHub: anonymous GET of the public API and the release assets.

Pure evaluators (no network) are at the end; the offline tests (test_rc2_receipt.py) exercise them.
"""
import getpass
import hashlib
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TAG, PREV, HA_TAG = 'v1.0.0-e32v2-rc.2', 'v0.1.0-e32v2-beta.22', 'ha-v1.0.0rc2'
HA_VERSION = '1.0.0rc2'
HA_PREV_VERSION = '0.4.0b15'
NEVER_INSTALL = ('v1.0.0-e32v2-rc.1', '1.0.0rc1', 'ha-v1.0.0rc1')
REPOSITORY = 'dielessen/open_thermostat'
HACS_REPOSITORY = 'dielessen/openthermostat-ha'
HACS_TAG = HA_VERSION  # publish_hacs_repo.py tags the HACS repository with the bare version
DOMAIN = 'open_thermostat'
HA_HOST = '192.168.1.130'
HA_URL = 'https://' + HA_HOST + ':8123'
ENTITY = 'update.woonkamer_e32_regelaar_ketel_en_diagnose_firmware'
CLIENT_DIR = Path(r'C:\Users\m.dielessen\Downloads\open_thermostat-vscode-20261021\out\beta19-install')
SCRATCH = Path(__file__).resolve().parent
TOKEN_FILE = SCRATCH / 'ha-token.txt'
RELEASE_WORKTREE = Path(r'C:\Users\m.dielessen\Downloads\open_thermostat-10-release')
E32_PASSWORD_ENV, MQTT_PASSWORD_ENV, MQTT_USER_ENV = 'OT_E32_PASSWORD', 'OT_MQTT_PASSWORD', 'OT_MQTT_USER'
FACTORY_PASSWORD = 'admin'  # the public factory default, not a secret
MQTT_PREFIX = 'ib-therm'
SETTINGS_ROUTES = ('/config/rooms', '/config/wifi', '/config/boiler', '/config/boiler-display', '/config/hardware',
                   '/config/debug', '/config/logging', '/config/program/current', '/status/programs',
                   '/config/bluetooth', '/config/heating')
IDENTITY_ROUTES = (('version', '/status/version'), ('updates', '/updates/status'), ('status', '/status'))
LIMIT = 262144
# Bluetooth runtime fields that change on their own (checklist section 5: "volatile").
VOLATILE = re.compile(r'(last|seen|age|rssi|battery|temp|humid|reading|advert|received|stale|count|value|frames)', re.I)
# Top-level members of GET /config/heating that are device-local history, not settings (the backup export drops
# them too: ConfigBackup.h exportDocument deletes "revision" and "features"). Reported, not compared.
PLAN_LOCAL = ('revision',)
# Safe phases of the active-control guard after the update (rc.2 ActiveHeatGuard / HeatingController).
OWNING = ('arming', 'active')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    return digest(Path(path).read_bytes())


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def utc(text):
    """e32client.now() (isoformat with microseconds and +00:00) -> 2026-11-08T09:00:00Z."""
    return text[:19] + 'Z'


def now_utc():
    import datetime as dt
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def new_folder(path):
    out = Path(path).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f'{out} is not empty; use a new folder')
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_manifest(out, name, kind):
    files = sorted(p for p in out.rglob('*') if p.is_file() and p.name != name and not p.name.endswith('.cookies'))
    path = save(out / name, {'schema': 1, 'kind': kind, 'files': [
        {'file': p.relative_to(out).as_posix(), 'sha256': file_digest(p), 'bytes': p.stat().st_size} for p in files]})
    return file_digest(path)


def verify_manifest(out, name):
    out = Path(out)
    manifest = json.loads((out / name).read_text(encoding='utf-8'))
    for entry in manifest['files']:
        if file_digest(out / entry['file']) != entry['sha256']:
            raise SystemExit(f'{out / entry["file"]} changed after its capture (manifest {name})')
    return len(manifest['files'])


def dry_run(script, requests, notes=()):
    """--dry-run: print what the script would request, touch nothing (no network, no files, no prompts)."""
    print(f'DRY RUN {script}: nothing is sent, read from the network, prompted or written.')
    for line in requests:
        print('  would ' + line)
    for line in notes:
        print('  note: ' + line)
    print('  token file ' + ('present' if TOKEN_FILE.exists() else 'MISSING') + f': {TOKEN_FILE}')
    sys.exit(0)


# ------------------------------------------------------------------ secrets (never stored)

def read_secret(env, prompt, stdin=None, ask=getpass.getpass):
    """The value of `env`, else a getpass prompt on a terminal; never a command-line argument or a file."""
    value = os.environ.get(env)
    if value:
        return value
    stdin = sys.stdin if stdin is None else stdin
    if stdin is not None and stdin.isatty():
        value = ask(prompt)
        if value:
            return value
    raise SystemExit(f'Set {env} in this PowerShell window or run the script in an interactive window for a '
                     'prompt (never on the command line).')


def e32_password(factory):
    """--factory-password: the public default; else OT_E32_PASSWORD or a prompt. Resolved before any network."""
    if factory:
        return FACTORY_PASSWORD
    return read_secret(E32_PASSWORD_ENV, 'E32 web password (user admin): ')


# ------------------------------------------------------------------ GitHub (anonymous, public)

class _GithubRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlsplit(newurl).hostname or ''
        if urllib.parse.urlsplit(newurl).scheme != 'https' or not (
                host == 'github.com' or host.endswith('.githubusercontent.com')):
            raise RuntimeError('Redirect refused: ' + host)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def github(url, cap=LIMIT, record=None):
    assert url.startswith('https://api.github.com/') or url.startswith('https://github.com/')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _GithubRedirects())
    request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json' if 'api.github' in url
                                                   else 'application/octet-stream',
                                                   'User-Agent': 'openthermostat-acceptance-capture'})
    with opener.open(request, timeout=120) as response:
        raw = response.read(cap + 1)
    assert len(raw) <= cap, url + ': response too large'
    if record:
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        Path(record).write_bytes(raw)
    return raw


def release_summary(value, asset_name='firmware.bin'):
    asset = next((a for a in value.get('assets', []) if a.get('name') == asset_name), None)
    return {'tag_name': value.get('tag_name'), 'draft': value.get('draft'),
            'prerelease': value.get('prerelease'), 'published_at': value.get('published_at'),
            'asset': ({'name': asset['name'], 'size': asset['size'], 'digest': asset.get('digest')}
                      if asset else None)}


def release(tag, record=None, repository=REPOSITORY):
    """The release by tag; a missing release (404) is returned as {'tag_name': None, ...}."""
    try:
        raw = github(f'https://api.github.com/repos/{repository}/releases/tags/{urllib.parse.quote(tag)}', record=record)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return {}, {'tag_name': None, 'draft': None, 'prerelease': None, 'published_at': None, 'asset': None,
                    'http_status': 404}
    value = json.loads(raw)
    return value, release_summary(value)


def app_descriptor(raw):
    """esp_app_desc_t right after the image header and the first segment header (as scratchpad/appdesc.py)."""
    import struct
    off = 24 + 8
    magic, _ = struct.unpack_from('<II', raw, off)
    d = raw[off + 16:]
    cut = lambda b: b.split(b'\0')[0].decode('ascii', 'replace')
    return {'magic': hex(magic), 'version': cut(d[0:32]), 'project': cut(d[32:64]),
            'idf': cut(d[96:128]), 'elf_sha256': d[128:160].hex()}


# ------------------------------------------------------------------ Home Assistant (GET only, LAN IP only)

def ha_token(path=TOKEN_FILE):
    return Path(path).read_text(encoding='utf-8').strip()


def ha_bytes(path, token, cap=4 * 1024 * 1024):
    url = HA_URL + path
    assert urllib.parse.urlsplit(url).hostname == HA_HOST, 'HA requests only go to the LAN IP'
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # HA's own self-signed certificate on the LAN IP
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token}, method='GET')
    with opener.open(request, timeout=60) as response:
        raw = response.read(cap + 1)
    assert len(raw) <= cap, path + ': response too large'
    return raw


def ha(path, token, record=None, cap=4 * 1024 * 1024):
    raw = ha_bytes(path, token, cap)
    if record:
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        Path(record).write_bytes(raw)
    return json.loads(raw)


def entity_summary(state):
    a = state.get('attributes', {}) if isinstance(state, dict) else {}
    return {'entity_id': state.get('entity_id'), 'state': state.get('state'), 'last_changed': state.get('last_changed'),
            'installed_version': a.get('installed_version'), 'latest_version': a.get('latest_version'),
            'in_progress': a.get('in_progress'), 'last_install': a.get('last_install'),
            'release_url': a.get('release_url')}


def ha_entity(token, record=None):
    return entity_summary(ha('/api/states/' + urllib.parse.quote(ENTITY), token, record))


def ha_snapshot(token, folder):
    """Everything this acceptance needs from HA in GETs: Core version, the update entity, the config entries of
    open_thermostat, the integration's diagnostics download (integration version from HA itself, the entity
    registry counts and the Repairs issues of the domain), and the states list (reduced to id/state/restored).
    The diagnostics and the states list are kept as extracts plus the SHA-256 of the full answer."""
    folder = Path(folder)
    config = ha('/api/config', token)
    save(folder / 'config-extract.json', {k: config.get(k) for k in ('version', 'state', 'safe_mode', 'recovery_mode')})
    entity_raw = ha('/api/states/' + urllib.parse.quote(ENTITY), token, record=folder / 'update-entity.json')
    entries = ha('/api/config/config_entries/entry?domain=' + DOMAIN, token, record=folder / 'config-entries.json')
    ours = [e for e in entries if isinstance(e, dict) and e.get('domain') == DOMAIN]
    diagnostics = None
    if len(ours) == 1:
        raw = ha_bytes('/api/diagnostics/config_entry/' + urllib.parse.quote(ours[0]['entry_id'], safe=''), token,
                       cap=16 * 1024 * 1024)
        diagnostics = {**diagnostics_extract(json.loads(raw)), 'sha256': digest(raw), 'bytes': len(raw)}
        save(folder / 'diagnostics-extract.json', diagnostics)
    raw = ha_bytes('/api/states', token, cap=32 * 1024 * 1024)
    states = json.loads(raw)
    reduced = reduce_states(states)
    save(folder / 'states-reduced.json', {'sha256': digest(raw), 'bytes': len(raw), 'count': len(reduced),
                                          'entities': reduced})
    hacs = [entity_summary(s) for s in states if str(s.get('entity_id', '')).startswith('update.')
            and HACS_REPOSITORY in str((s.get('attributes') or {}).get('release_url') or '')]
    control = control_sensors(states)
    save(folder / 'hacs-and-control.json', {'hacs_update_entities': hacs, 'control_sensors': control})
    return summarize_snapshot(config, entity_summary(entity_raw), entries, diagnostics, reduced, hacs, control)


def summarize_snapshot(config, entity, entries, diagnostics, reduced, hacs, control):
    return {'ha_core_version': config.get('version'), 'entity': entity, 'config_entries': entries_summary(entries),
            'diagnostics': diagnostics, 'integration_version': integration_version(diagnostics),
            'states': {'count': len(reduced), 'restored': sorted(e['entity_id'] for e in reduced if e['restored'])},
            'hacs_update_entities': hacs, 'control_sensors': control}


def ha_history(token, entity_id, since, record=None):
    return ha('/api/history/period/' + urllib.parse.quote(since) + '?filter_entity_id=' + urllib.parse.quote(entity_id)
              + '&significant_changes_only=0', token, record=record)


# ------------------------------------------------------------------ E32

def e32(out, cookie_name, password):
    """The bounded e32client, with its request log and cookies in this capture folder; one login at most."""
    sys.path.insert(0, str(CLIENT_DIR))
    import e32client as e
    e.D = Path(out)
    assert e.POST_ALLOWED == ('/auth/login',), 'e32client allows more than /auth/login; refusing'
    client = e.Client(cookie_name=cookie_name)
    os.environ[E32_PASSWORD_ENV] = password  # e32client reads it here; removed again right after the login
    try:
        e.login_if_needed(client, Path(out).name)
    finally:
        os.environ.pop(E32_PASSWORD_ENV, None)
    return e, client


def password_state(client):
    """GET /auth/session of this signed-in client: only default_password is kept (never the CSRF value)."""
    status, raw = client.request('/auth/session')
    assert status == 200, f'/auth/session: HTTP{status}'
    value = json.loads(raw)
    flag = value.get('default_password')
    return {'default_password': flag if type(flag) is bool else None, 'reported': 'default_password' in value}


def csrf_post(e, client, path, body, record=None):
    """Exactly two extra POSTs: the passphrase-less backup export and the sign-out."""
    assert (path, body) in (('/config/backup', {'action': 'export'}), ('/auth/logout', None)), 'POST refused'
    if client.csrf is None:
        assert client.session() == 200, 'No session for ' + path
    headers = {'Origin': e.HOST, 'Cache-Control': 'no-store', 'X-OpenThermostat-CSRF': client.csrf}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    started = e.now()
    try:
        response = client.opener.open(urllib.request.Request(e.HOST + path, data=data if data is not None else b'',
                                                             headers=headers, method='POST'), timeout=60)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        status = response.code
        raw = response.read(LIMIT + 1)
    assert len(raw) <= LIMIT, 'Response bound exceeded'
    if record and status == 200:
        Path(record).parent.mkdir(parents=True, exist_ok=True)
        Path(record).write_bytes(raw)
    e.append(e.D / 'requests.jsonl', {'at_utc': started, 'finished_at_utc': e.now(), 'method': 'POST', 'path': path,
                                      'http_status': status, 'bytes': len(raw),
                                      **({'sha256': digest(raw)} if path != '/auth/logout' else {})})
    return status, raw


def logout(e, client):
    try:
        status, _ = csrf_post(e, client, '/auth/logout', None)
    except Exception as error:  # the capture itself is done; a failed sign-out only costs a session slot
        return f'logout failed: {type(error).__name__}'
    for cookie in Path(e.D).glob('*.cookies'):
        cookie.unlink()
    return status


def read_settings(e, client, folder, export_required=True):
    """GET every settings document and program, then the passphrase-less backup export.

    rc.2 refuses every change while the E32 has the factory password, the export included (403
    password_change_required). With export_required=False that refusal is recorded instead of failing; the
    comparison then skips the export for this run (another run must compare it)."""
    folder = Path(folder)
    entries = []
    for path in SETTINGS_ROUTES:
        name = path.strip('/').replace('/', '-') + '.json'
        status, raw = client.request(path, record=folder / name)
        assert status == 200 or (path == '/config/boiler-display' and status == 404), f'{path}: HTTP{status}'
        entries.append({'path': path, 'file': name, 'http_status': status, 'sha256': digest(raw), 'bytes': len(raw)})
    programs = json.loads((folder / 'status-programs.json').read_bytes())
    assert isinstance(programs, list) and len(programs) <= 128
    for index, program in enumerate(programs):
        path = '/config/programs/' + urllib.parse.quote(program, safe='')
        name = f'program-{index:03}.json'
        status, raw = client.request(path, record=folder / name)
        assert status == 200, f'{path}: HTTP{status}'
        entries.append({'path': path, 'file': name, 'http_status': status, 'sha256': digest(raw), 'bytes': len(raw)})
    status, raw = csrf_post(e, client, '/config/backup', {'action': 'export'}, record=folder / 'config-backup-export.json')
    export = {'http_status': status, 'compared': status == 200, 'refusal': None}
    if status == 200:
        document = json.loads(raw)
        assert document.get('secrets') is None, 'Export unexpectedly contains a sealed secrets box'
        entries.append({'path': 'POST /config/backup {"action":"export"}', 'file': 'config-backup-export.json',
                        'http_status': status, 'sha256': digest(raw), 'bytes': len(raw)})
    else:
        try:
            export['refusal'] = json.loads(raw).get('error')
        except (ValueError, AttributeError):
            export['refusal'] = None
        if export_required or not (status == 403 and export['refusal'] == 'password_change_required'):
            raise AssertionError(f'/config/backup export: HTTP{status} {export["refusal"]}')
    for entry in entries:  # backup_verified: every payload re-read from disk matches
        assert file_digest(folder / entry['file']) == entry['sha256'], entry['file'] + ' changed on disk'
    return entries, export


# ------------------------------------------------------------------ MQTT (read-only listener in WSL)

WSL_PYTHON = '/home/dielessen/venvs/ha/bin/python'
MQTT_LINE = re.compile(r'^\s*([\d.]+) ([R-]) (\S+) (\d+)B ?(.*)$')


def mqtt_credentials(args):
    """Resolved before any network: host/port/user from the arguments or OT_MQTT_USER, the password from
    OT_MQTT_PASSWORD or a prompt; --mqtt-smb keeps the old route (HA's stored credentials over Samba)."""
    if args.no_mqtt:
        return None
    if args.mqtt_smb:
        import subprocess
        creds = subprocess.run([sys.executable, '-I', str(SCRATCH / 'mqtt_creds.py')], capture_output=True,
                               timeout=60, check=True)
        return creds.stdout
    user = args.mqtt_user or os.environ.get(MQTT_USER_ENV)
    if not user and sys.stdin is not None and sys.stdin.isatty():
        user = input(f'MQTT user on {args.mqtt_host} (the broker account Home Assistant uses): ').strip()
    if not user:
        raise SystemExit(f'Give --mqtt-user (or {MQTT_USER_ENV}); or --no-mqtt (the MQTT checks then stay false).')
    password = read_secret(MQTT_PASSWORD_ENV, f'MQTT password for {user}@{args.mqtt_host}: ')
    return (json.dumps({'host': args.mqtt_host, 'port': args.mqtt_port, 'user': user, 'pw': password}) + '\n').encode()


def add_mqtt_arguments(parser):
    parser.add_argument('--mqtt-host', default=HA_HOST)
    parser.add_argument('--mqtt-port', type=int, default=1883)
    parser.add_argument('--mqtt-user', help=f'broker user (or {MQTT_USER_ENV}); password: {MQTT_PASSWORD_ENV} or a prompt')
    parser.add_argument('--mqtt-smb', action='store_true', help='read HA\'s stored broker credentials over Samba (old route)')
    parser.add_argument('--no-mqtt', action='store_true', help='skip the listener (the MQTT checks stay false)')


def wsl_path(path):
    import ctypes
    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetLongPathNameW(str(path), buffer, 1024)
    long = buffer.value or str(path)
    return '/mnt/' + long[0].lower() + long[2:].replace('\\', '/')


def mqtt_listen(credentials, seconds):
    """Runs mqtt_listen_rc2.py in WSL with the credentials on stdin (never on a command line or in a file)."""
    import subprocess
    listen = subprocess.run(['wsl', '-e', WSL_PYTHON, wsl_path(SCRATCH / 'mqtt_listen_rc2.py'), str(seconds), MQTT_PREFIX],
                            input=credentials, capture_output=True, timeout=seconds + 120)
    return listen.stdout


def parse_mqtt(text):
    return [m.groups() for m in map(MQTT_LINE.match, text.splitlines()) if m]


def mqtt_evaluate(messages, listen_s):
    """Findings from one listening window: availability, heartbeat cadence and the heartbeat's own disconnect
    counters, the boiler fields, and the active-control block of the last fw/state/heating."""
    availability = [p for t, r, topic, n, p in messages if topic.endswith('/fw/availability')]
    beats = [(float(t), p) for t, r, topic, n, p in messages if topic.endswith('/fw/heartbeat') and r == '-']
    times = [t for t, _ in beats]
    gaps = [b - a for a, b in zip(times, times[1:])]
    payloads = []
    for _, payload in beats:
        try:
            payloads.append(json.loads(payload))
        except ValueError:
            payloads.append(None)
    disconnects = [((p or {}).get('mqtt') or {}).get('disconnects') for p in payloads]
    uptimes = [(p or {}).get('uptime_s') for p in payloads]
    heating = None
    for t, r, topic, n, p in messages:
        if topic.endswith('/fw/state/heating'):
            try:
                heating = json.loads(p)
            except ValueError:
                pass
    active = (heating or {}).get('active') if isinstance(heating, dict) else None
    return {
        'availability_online': bool(availability) and availability[-1].strip().strip('"') == 'online',
        'heartbeat_every_60s': (len(times) >= 2 and all(gap <= 75 for gap in gaps)
                                and (listen_s - times[-1]) <= 75 and times[0] <= 75),
        'heartbeat_counters_steady': (len(disconnects) >= 2 and all(isinstance(d, dict) for d in disconnects)
                                      and all(d == disconnects[0] for d in disconnects)),
        'heartbeat_uptime_rising': (len(uptimes) >= 2 and all(isinstance(u, int) for u in uptimes)
                                    and all(b > a for a, b in zip(uptimes, uptimes[1:]))),
        'boiler_fields_seen': any('/fw/state/boiler_fields/' in topic for _, _, topic, _, _ in messages),
        'detail': {'availability': availability[-3:], 'beats_at_s': times, 'gaps_s': gaps, 'uptimes_s': uptimes,
                   'disconnects': disconnects[:1] + disconnects[-1:], 'messages': len(messages),
                   'state_heating_active': active},
    }


# ------------------------------------------------------------------ pure evaluators (offline-tested)

def diagnostics_extract(doc):
    """HA's diagnostics download (homeassistant.components.diagnostics): the loaded integration's own manifest
    version, the custom_components list entry, Core, HACS, the integration's entity-registry counts
    (support_diagnostics.entity_counts) and its firmware view, and the domain's Repairs issues (if listed)."""
    doc = doc if isinstance(doc, dict) else {}
    info = doc.get('home_assistant') or {}
    custom = doc.get('custom_components') or {}
    manifest = doc.get('integration_manifest') or {}
    e32 = (doc.get('data') or {}).get('e32') or {}
    issues = doc.get('issues')
    return {'home_assistant_version': info.get('version'), 'manifest_domain': manifest.get('domain'),
            'manifest_version': manifest.get('version'), 'custom_component_version': (custom.get(DOMAIN) or {}).get('version'),
            'hacs_version': (custom.get('hacs') or {}).get('version'),
            'entities': e32.get('entities'),
            'firmware': {k: (e32.get('firmware') or {}).get(k) for k in ('installed_version', 'latest_version', 'in_progress')},
            'issues': None if not isinstance(issues, list) else [
                {'issue_id': i.get('issue_id'), 'translation_key': i.get('translation_key'),
                 'dismissed_version': i.get('dismissed_version'), 'is_fixable': i.get('is_fixable')}
                for i in issues if isinstance(i, dict)]}


def integration_version(diagnostics):
    """The integration version as HA loaded it: the manifest in the diagnostics download, confirmed by the
    custom_components entry (a mismatch or a missing download gives None)."""
    if not isinstance(diagnostics, dict) or diagnostics.get('manifest_domain') != DOMAIN:
        return None
    version = diagnostics.get('manifest_version')
    return version if version and version == diagnostics.get('custom_component_version') else None


def issue_flags(diagnostics):
    """Which OpenThermostat Repairs issues are open (None when the download does not list issues)."""
    issues = (diagnostics or {}).get('issues') if isinstance(diagnostics, dict) else None
    if not isinstance(issues, list):
        return None
    ids = [str(i.get('issue_id') or '') for i in issues if not i.get('dismissed_version')]
    return {'default_password': any(i.startswith('e32_default_password_') for i in ids),
            'reconfirm_takeover': any(i.startswith('reconfirm_takeover_') for i in ids), 'open': sorted(ids)}


def reduce_states(states):
    return sorted(({'entity_id': s.get('entity_id'), 'state': s.get('state'),
                    'restored': (s.get('attributes') or {}).get('restored') is True}
                   for s in states if isinstance(s, dict) and isinstance(s.get('entity_id'), str)),
                  key=lambda e: e['entity_id'])


def control_sensors(states):
    """HA's heat-request sensor of the E32 (heating_link.HeatRequestSensor): its "control" attribute is the
    E32's active-control state (rc.2 HA; absent in 0.4.0b15)."""
    found = []
    for s in states:
        a = (s.get('attributes') or {}) if isinstance(s, dict) else {}
        if {'mode', 'reason', 'revision'} <= set(a) and str(s.get('entity_id', '')).startswith('sensor.'):
            found.append({'entity_id': s.get('entity_id'), 'state': s.get('state'), 'mode': a.get('mode'),
                          'control': a.get('control')})
    return found


def entries_summary(entries):
    ours = [e for e in entries or [] if isinstance(e, dict) and e.get('domain') == DOMAIN]
    return {'count': len(ours), 'entry_ids': [e.get('entry_id') for e in ours], 'states': [e.get('state') for e in ours],
            'disabled_by': [e.get('disabled_by') for e in ours], 'titles': [e.get('title') for e in ours]}


def single_entry(baseline, now):
    """One loaded open_thermostat config entry, the same one as before the HACS migration."""
    b, n = baseline['config_entries'], now['config_entries']
    return (b['count'] == 1 and n['count'] == 1 and n['entry_ids'] == b['entry_ids'] and n['states'] == ['loaded']
            and n['disabled_by'] == [None])


_SUFFIX = re.compile(r'_\d+$')


def entity_changes(before, after, before_diag=None, after_diag=None):
    """New duplicates and stale entities between two HA snapshots.

    Duplicates: an entity ID that is new and ends in _2, _3 ... while its base ID exists, and possible-duplicate
    groups the integration's registry counts did not list before. Stale: entities that newly show
    "restored": true (in the registry, no longer provided by any integration)."""
    b = {e['entity_id']: e for e in before}
    a = {e['entity_id']: e for e in after}
    new = sorted(set(a) - set(b))
    duplicates = [x for x in new if _SUFFIX.search(x) and _SUFFIX.sub('', x) in (set(a) | set(b))]
    stale = sorted(x for x, e in a.items() if e['restored'] and not (b.get(x) or {}).get('restored'))
    groups_before = ((before_diag or {}).get('entities') or {}).get('possible_duplicates') or []
    groups_after = ((after_diag or {}).get('entities') or {}).get('possible_duplicates') or []
    new_groups = [g for g in groups_after if g not in groups_before]
    counts = lambda d: {k: ((d or {}).get('entities') or {}).get(k) for k in ('total', 'devices')}
    return {'ok': not duplicates and not stale and not new_groups and after_diag is not None,
            'new_duplicate_ids': duplicates, 'new_stale_ids': stale, 'new_possible_duplicate_groups': new_groups,
            'new_ids': new[:200], 'removed_ids': sorted(set(b) - set(a))[:200],
            'integration_counts': {'before': counts(before_diag), 'after': counts(after_diag)}}


def owned_before(heating):
    """Did the E32 control the boiler before the update (beta.22: active state with a stored confirmation)?"""
    a = (heating or {}).get('active') or {}
    return a.get('confirmation_stored') is True and a.get('state') in OWNING + ('stopped_measurement_lost',)


def control_state(heating, owned):
    """The E32's active control after the update (rc.2 ActiveHeatGuard), as a phase and whether it is safe.

    owned (the E32 controlled the boiler under beta.22):
      awaiting_reconfirm: reconfirm_required, no confirmation of this firmware, the reconfirm record stored,
                          state awaiting_confirmation, and at most frost protection or a zero is requested;
      reconfirmed:        the owner confirmed again: confirmation stored, nothing pending, arming/active;
    not owned: shadow, nothing sent. Anything else (a foreign controller, lost measurements, stopping) is not
    the documented safe state."""
    a = (heating or {}).get('active') or {}
    command = a.get('command') or {}
    warnings = a.get('warnings') or []
    positive = bool(command.get('send')) and (command.get('flow_c') or 0) > 0
    if a.get('reconfirm_required') is True:
        phase = 'awaiting_reconfirm'
        ok = (owned and a.get('state') == 'awaiting_confirmation' and a.get('confirmation_stored') is False
              and a.get('reconfirm_stored') is True and a.get('enabled') is True
              and (not positive or command.get('why') == 'frost_unconfirmed') and 'foreign_controller' not in warnings)
    elif a.get('confirmation_stored') is True:
        phase = 'reconfirmed'
        ok = (owned and a.get('state') in OWNING and a.get('reconfirm_stored') is False and a.get('enabled') is True
              and 'foreign_controller' not in warnings)
    elif a.get('state') == 'shadow':
        phase = 'shadow'
        ok = not owned and not positive
    else:
        phase = 'other'
        ok = False
    detail = {k: a.get(k) for k in ('state', 'reconfirm_required', 'confirmation_stored', 'reconfirm_stored',
                                    'taken_over_before', 'enabled', 'warnings')}
    detail['command'] = {k: command.get(k) for k in ('send', 'flow_c', 'why')}
    detail['plan_mode'] = (heating or {}).get('mode')
    return {'phase': phase, 'ok': bool(ok), 'detail': detail}


def learned_summary(heating):
    learned = (heating or {}).get('learned') or {}
    tuning = (heating or {}).get('tuning')
    rooms = [{k: r.get(k) for k in ('id', 'readiness', 'segments', 'periods')}
             for r in learned.get('rooms') or [] if isinstance(r, dict)]
    return {'status': learned.get('status'), 'applied': learned.get('applied'),
            'heating_periods': learned.get('heating_periods'), 'boiler_minimum_flow_c': learned.get('boiler_minimum_flow_c'),
            'rooms': rooms,
            'tuning': None if not isinstance(tuning, dict) else {
                'state': tuning.get('state'), 'manual': tuning.get('manual'), 'yesterday': tuning.get('yesterday'),
                'log_entries': len(tuning.get('log') or []), 'would_entries': len(tuning.get('would') or [])}}


def learned_fresh(summary):
    """rc.2 is the first firmware that keeps what it learned (one NVS record); beta.22 kept nothing over a
    restart. Right after the update the self-tuning has no history and the learner counts only this boot."""
    tuning = summary.get('tuning') or {}
    small = lambda v: isinstance(v, (int, float)) and v <= 1
    return (summary.get('tuning') is not None and tuning.get('log_entries') == 0 and tuning.get('yesterday') is None
            and small(summary.get('heating_periods')) and all(small(r.get('periods')) for r in summary['rooms'])
            and summary.get('boiler_minimum_flow_c') is None)


def _diff(before, after, where, volatile, out):
    if isinstance(before, dict) and isinstance(after, dict):
        for key, value in before.items():
            if volatile and VOLATILE.search(key):
                continue
            if key not in after:
                out.append({'at': f'{where}.{key}', 'change': 'removed'})
            else:
                _diff(value, after[key], f'{where}.{key}', volatile, out)
        # keys only in `after` are schema additions: allowed
    elif isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            out.append({'at': where, 'change': f'length {len(before)} -> {len(after)}'})
        for index, (a, b) in enumerate(zip(before, after)):
            _diff(a, b, f'{where}[{index}]', volatile, out)
    elif before != after:
        out.append({'at': where, 'change': 'value', 'before': before, 'after': after})


def settings_finding(differences, notes, export, default_password):
    """One run's settings verdict: no differences, and the export compared, or refused only because the E32 still
    has the factory password (rc.2: 403 password_change_required; a later run must compare it)."""
    refused_for_password = (export.get('http_status') == 403 and export.get('refusal') == 'password_change_required'
                            and default_password is True)
    ok = not differences and (bool(export.get('compared')) or refused_for_password)
    return ok, {'differences': differences[:50], 'export': export, **notes}


def compare_settings(before_dir, after_dir, entries):
    """(differences, notes): differences that are not schema additions, Bluetooth runtime values or device-local
    plan history. An export missing after the update because the E32 refused it (factory password) is a note,
    not a difference; the caller checks that some run compared it."""
    differences, notes = [], {'export_compared': False, 'plan_revision': None}
    for entry in entries:
        name = entry['file']
        a, b = Path(before_dir) / name, Path(after_dir) / name
        if not b.exists():
            if name == 'config-backup-export.json':
                notes['export_skipped'] = True
                continue
            differences.append({'at': name, 'change': 'missing after the update'})
            continue
        if entry['http_status'] != 200:
            continue
        before, after = json.loads(a.read_bytes()), json.loads(b.read_bytes())
        found = []
        if name == 'config-backup-export.json':
            notes['export_compared'] = True
            before, after = dict(before), dict(after)
            for key in ('firmware', 'created'):  # describe the export itself, not a setting
                before.pop(key, None)
                after.pop(key, None)
            bt_before, bt_after = before.pop('bluetooth', None), after.pop('bluetooth', None)
            _diff(before, after, name, False, found)
            _diff(bt_before, bt_after, name + '.bluetooth', True, found)
        elif name == 'config-heating.json' and isinstance(before, dict) and isinstance(after, dict):
            before, after = dict(before), dict(after)
            notes['plan_revision'] = {'before': before.get('revision'), 'after': after.get('revision')}
            for key in PLAN_LOCAL:
                before.pop(key, None)
                after.pop(key, None)
            _diff(before, after, name, False, found)
        else:
            _diff(before, after, name, name == 'config-bluetooth.json', found)
        differences.extend(found)
    return differences, notes
