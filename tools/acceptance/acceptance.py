"""Shared helpers for the attended acceptance of an E32 firmware update on the Home Assistant route.

One release is described by a small JSON file (install-config.json next to the scripts, or --config) and by
command-line overrides: the E32 tag and the tag it replaces, the Home Assistant integration version and the one it
replaces, the update entity, the addresses and the MQTT prefix. Nothing about a release is written in the code.
Used by capture_preinstall.py, capture_post.py and write_receipt.py; capture_independent.py deliberately does NOT
import this module (it has its own HTTP code and reads the same configuration file itself).

Network rules (binding):
  * E32: only through e32client.py: GETs plus at most one POST /auth/login per session. The only extra POSTs are
    POST /config/backup {"action":"export"} (no passphrase) and POST /auth/logout, both with the session's CSRF
    header. Every session ends with a logout (also after an error). One session at a time: the E32 has 4 web
    sessions and Home Assistant needs its own for the update. Only a LAN address is accepted.
  * E32 password: OT_E32_PASSWORD or a getpass prompt, or --factory-password for the public factory default.
    Never on the command line, never in a file, never in the process environment after the login.
  * MQTT (preferred over E32 web sessions for liveness): a read-only listener (mqtt_listen.py); the broker login
    comes from OT_MQTT_USER / OT_MQTT_PASSWORD or is typed at a prompt, and travels to the listener on its stdin.
    It is never read from Home Assistant's storage.
  * Home Assistant: GET only, only the configured LAN address, with the token from ha-token.txt next to these
    scripts (git-ignored). Nothing is posted to HA: no service calls, no websocket.
  * GitHub: anonymous GET of the public API and the release assets.

Pure evaluators (no network) are at the end; the offline tests (test_receipt.py) exercise them.
"""
import getpass
import hashlib
import ipaddress
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]  # the worktree this kit lives in: scripts/verify_e32_update_gate.py is read from here
TOKEN_FILE = HERE / 'ha-token.txt'
DEFAULT_CONFIG = HERE / 'install-config.json'
DOMAIN = 'open_thermostat'
E32_PASSWORD_ENV, MQTT_PASSWORD_ENV, MQTT_USER_ENV = 'OT_E32_PASSWORD', 'OT_MQTT_PASSWORD', 'OT_MQTT_USER'
FACTORY_PASSWORD = 'admin'  # the public factory default, not a secret
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
# Safe phases of the active-control guard after the update (ActiveHeatGuard / HeatingController).
OWNING = ('arming', 'active')
# The boot instant of the E32 (observation time minus uptime) may differ this much between two observations ...
BOOT_JITTER_S = 5
# ... and the first one must lie in [install start - BOOT_BEFORE_S, install end + BOOT_AFTER_S] (R5-08).
BOOT_BEFORE_S, BOOT_AFTER_S = 60, 300

TAG_RE = re.compile(r'v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-e32v2(?:-(alpha|beta|rc)\.(0|[1-9]\d*))?')
HA_VERSION_RE = re.compile(r'\d+\.\d+\.\d+(?:(?:\.dev|a|b|rc)\d+)?')
CONFIG_KEYS = ('tag', 'previous_tag', 'ha_version', 'ha_previous_version', 'entity_id', 'ha_url', 'e32_url',
               'mqtt_host', 'mqtt_port', 'mqtt_prefix', 'repository', 'hacs_repository', 'wsl_python')
CONFIG_DEFAULTS = {'mqtt_port': 1883, 'mqtt_prefix': 'ib-therm', 'repository': 'dielessen/open_thermostat',
                   'hacs_repository': 'dielessen/openthermostat-ha', 'wsl_python': '~/venvs/ha/bin/python'}
CONFIG_REQUIRED = ('tag', 'previous_tag', 'ha_version', 'ha_previous_version', 'entity_id', 'ha_url', 'e32_url')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    return digest(Path(path).read_bytes())


def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))  # LF on every OS
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


# ------------------------------------------------------------------ release tags and versions

def tag_key(tag):
    """The order key of an E32 firmware tag (the same order as scripts/verify_e32_update_gate.version), or None."""
    match = TAG_RE.fullmatch(tag) if isinstance(tag, str) else None
    if not match:
        return None
    major, minor, patch, stage, sequence = match.groups()
    return (int(major), int(minor), int(patch), {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[stage], int(sequence or 0))


def is_stable_tag(tag):
    """vX.Y.Z-e32v2 without alpha/beta/rc: a normal GitHub release, not a pre-release."""
    key = tag_key(tag)
    return key is not None and key[3] == 3


def receipt_stem(tag):
    """The receipt file name stem of a tag: v1.0.0-e32v2-rc.4 -> e32-rc4, v0.1.0-e32v2-beta.19 -> e32-beta19."""
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ValueError('not an E32 firmware tag: ' + str(tag))
    major, minor, patch, stage, sequence = match.groups()
    return f'e32-{stage}{sequence}' if stage else f'e32-{major}.{minor}.{patch}'


# ------------------------------------------------------------------ configuration (no release in the code)

class Config:
    """One release and one installation: versions, tags, addresses, update entity and MQTT prefix."""

    def __init__(self, values):
        self.__dict__.update(values)

    @property
    def ha_tag(self):
        return 'ha-v' + self.ha_version

    @property
    def hacs_tag(self):
        return self.ha_version  # publish_hacs_repo.py tags the HACS repository with the bare version

    @property
    def ha_host(self):
        return urllib.parse.urlsplit(self.ha_url).hostname

    @property
    def expect_prerelease(self):
        """True for -rc/-beta/-alpha tags, False for a stable tag: GitHub's flag follows the tag."""
        return not is_stable_tag(self.tag)

    def as_dict(self):
        return {key: getattr(self, key, None) for key in CONFIG_KEYS}


def is_lan_host(host):
    """A private, loopback or link-local address, or a local name: tokens and passwords never go further than that."""
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
        return address.is_private or address.is_loopback or address.is_link_local
    except ValueError:
        pass
    host = host.lower().rstrip('.')
    return '.' not in host or host.endswith(('.local', '.lan', '.home.arpa', '.internal'))


def add_config_arguments(parser):
    """--config and one override per configuration key (the file is the default, the argument wins)."""
    parser.add_argument('--config', help=f'JSON file with the release and the installation (default: {DEFAULT_CONFIG.name}'
                                         ' next to these scripts)')
    parser.add_argument('--tag', help='E32 firmware tag to install, e.g. v1.0.0-e32v2-rc.4')
    parser.add_argument('--previous-tag', help='the E32 firmware tag that is installed now')
    parser.add_argument('--ha-version', help='Home Assistant integration version to install, e.g. 1.0.0rc5')
    parser.add_argument('--ha-previous-version', help='the integration version that is installed now')
    parser.add_argument('--entity-id', help='the E32 Firmware update entity in Home Assistant')
    parser.add_argument('--ha-url', help='https://<LAN address of Home Assistant>:8123')
    parser.add_argument('--e32-url', help='http://<LAN address of the E32>')
    parser.add_argument('--mqtt-host', help='MQTT broker (default: the host of --ha-url)')
    parser.add_argument('--mqtt-port', type=int, help='MQTT broker port (default 1883)')
    parser.add_argument('--mqtt-prefix', help='MQTT topic prefix of the E32 (default ib-therm)')
    parser.add_argument('--repository', help='GitHub repository of the firmware release')
    parser.add_argument('--hacs-repository', help='GitHub repository HACS installs the integration from')
    parser.add_argument('--wsl-python', help='Python with paho-mqtt inside WSL, used when this Windows Python has none')


def load_config(args, needs=CONFIG_REQUIRED):
    """The configuration: defaults, then the JSON file, then the command-line overrides; checked as far as needed."""
    values = dict(CONFIG_DEFAULTS)
    path = Path(args.config) if getattr(args, 'config', None) else DEFAULT_CONFIG
    if path.exists():
        document = json.loads(path.read_text(encoding='utf-8'))
        unknown = sorted(set(document) - set(CONFIG_KEYS) - {'comment'})
        if unknown:
            raise SystemExit(f'{path}: unknown keys {unknown}')
        values.update({key: document[key] for key in CONFIG_KEYS if key in document})
    elif getattr(args, 'config', None):
        raise SystemExit(f'{path} does not exist')
    for key in CONFIG_KEYS:
        override = getattr(args, key, None)
        if override is not None:
            values[key] = override
    if not values.get('mqtt_host') and values.get('ha_url'):
        values['mqtt_host'] = urllib.parse.urlsplit(values['ha_url']).hostname
    missing = [key for key in needs if not values.get(key)]
    if missing:
        raise SystemExit(f'Missing {", ".join(missing)}: put it in {path.name} or give it as an argument '
                         f'(--{missing[0].replace("_", "-")})')
    cfg = Config(values)
    check_config(cfg, needs)
    return cfg


def check_config(cfg, needs=CONFIG_REQUIRED):
    problems = []
    if 'tag' in needs and tag_key(cfg.tag) is None:
        problems.append(f'tag {cfg.tag!r} is not an E32 firmware tag (vX.Y.Z-e32v2[-rc.N])')
    if 'previous_tag' in needs and tag_key(cfg.previous_tag) is None:
        problems.append(f'previous_tag {cfg.previous_tag!r} is not an E32 firmware tag')
    if 'tag' in needs and 'previous_tag' in needs and tag_key(cfg.tag) and tag_key(cfg.previous_tag) \
            and tag_key(cfg.previous_tag) >= tag_key(cfg.tag):
        problems.append('previous_tag must be older than tag')
    for key in ('ha_version', 'ha_previous_version'):
        if key in needs and not HA_VERSION_RE.fullmatch(str(getattr(cfg, key))):
            problems.append(f'{key} {getattr(cfg, key)!r} is not an integration version (like 1.0.0rcN)')
    if 'entity_id' in needs and not re.fullmatch(r'update\.[a-z0-9_]{1,200}', str(cfg.entity_id)):
        problems.append(f'entity_id {cfg.entity_id!r} is not an update entity')
    for key, schemes in (('ha_url', ('http', 'https')), ('e32_url', ('http',))):
        if key in needs:
            parts = urllib.parse.urlsplit(str(getattr(cfg, key)))
            if parts.scheme not in schemes or not is_lan_host(parts.hostname) or parts.path not in ('', '/') \
                    or parts.username or parts.query:
                problems.append(f'{key} {getattr(cfg, key)!r} must be {"/".join(schemes)}://<LAN address> '
                                '(passwords and tokens never leave the home network)')
    if problems:
        raise SystemExit('Configuration problems:\n  ' + '\n  '.join(problems))


def dry_run(script, requests, notes=(), token_file=TOKEN_FILE):
    """--dry-run: print what the script would request, touch nothing (no network, no files, no prompts)."""
    print(f'DRY RUN {script}: nothing is sent, read from the network, prompted or written.')
    for line in requests:
        print('  would ' + line)
    for line in notes:
        print('  note: ' + line)
    print('  token file ' + ('present' if Path(token_file).exists() else 'MISSING') + f': {token_file}')
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


def release(cfg, tag, record=None, repository=None):
    """The release by tag; a missing release (404) is returned as {'tag_name': None, ...}."""
    repository = repository or cfg.repository
    try:
        raw = github(f'https://api.github.com/repos/{repository}/releases/tags/{urllib.parse.quote(tag)}', record=record)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return {}, {'tag_name': None, 'draft': None, 'prerelease': None, 'published_at': None, 'asset': None,
                    'http_status': 404}
    value = json.loads(raw)
    return value, release_summary(value)


def release_published(cfg, summary, tag=None):
    """The firmware release is published (not a draft), has firmware.bin with a SHA-256 digest, and its channel
    follows the tag: a pre-release for -rc/-beta/-alpha, a normal release for a stable tag."""
    asset = summary.get('asset')
    return (summary.get('tag_name') == (tag or cfg.tag) and summary.get('draft') is False
            and summary.get('prerelease') is cfg.expect_prerelease and bool(asset)
            and str(asset.get('digest', '')).startswith('sha256:'))


def app_descriptor(raw):
    """esp_app_desc_t right after the image header and the first segment header."""
    import struct
    off = 24 + 8
    magic, _ = struct.unpack_from('<II', raw, off)
    d = raw[off + 16:]
    cut = lambda b: b.split(b'\0')[0].decode('ascii', 'replace')
    return {'magic': hex(magic), 'version': cut(d[0:32]), 'project': cut(d[32:64]),
            'idf': cut(d[96:128]), 'elf_sha256': d[128:160].hex()}


def release_files(raw_release, cache, summary):
    """firmware.bin and e32v2-update.json of the release, cached in `cache`, checked against each other and
    against GitHub's digest and size, with the app descriptor's ELF hash. Returns (public, image, descriptor, ok)."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    assets = {a['name']: a for a in raw_release.get('assets', [])}
    manifest_path = cache / 'e32v2-update.json'
    if not manifest_path.exists():
        github(assets['e32v2-update.json']['browser_download_url'], record=manifest_path)
    public = json.loads(manifest_path.read_bytes())
    firmware = cache / 'firmware.bin'
    if not firmware.exists():
        github(assets['firmware.bin']['browser_download_url'], cap=0x3C0000, record=firmware)
    image = firmware.read_bytes()
    descriptor = app_descriptor(image)
    asset = summary.get('asset') or {}
    marker = ('OT_E32V2_OTA_V1:' + str(summary.get('tag_name')) + ':' + str(public.get('source_commit')) + ':').encode()
    ok = ('sha256:' + digest(image) == asset.get('digest') and len(image) == asset.get('size') == public.get('size')
          and digest(image) == public.get('sha256') and public.get('version') == summary.get('tag_name')
          and descriptor['magic'] == '0xabcd5432' and marker in image)
    return public, image, descriptor, ok


# ------------------------------------------------------------------ Home Assistant (GET only, LAN address only)

def ha_token(path=TOKEN_FILE):
    path = Path(path)
    if not path.exists():
        raise SystemExit(f'No Home Assistant token: put a long-lived access token in {path} (git-ignored)')
    return path.read_text(encoding='utf-8').strip()


def ha_bytes(cfg, path, token, cap=4 * 1024 * 1024):
    url = cfg.ha_url.rstrip('/') + path
    assert urllib.parse.urlsplit(url).hostname == cfg.ha_host and is_lan_host(cfg.ha_host), \
        'HA requests only go to the configured LAN address'
    handlers = [urllib.request.ProxyHandler({})]
    if url.startswith('https://'):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # HA's own self-signed certificate on the LAN address
        handlers.append(urllib.request.HTTPSHandler(context=context))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token}, method='GET')
    with opener.open(request, timeout=60) as response:
        raw = response.read(cap + 1)
    assert len(raw) <= cap, path + ': response too large'
    return raw


def ha(cfg, path, token, record=None, cap=4 * 1024 * 1024):
    raw = ha_bytes(cfg, path, token, cap)
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


def ha_snapshot(cfg, token, folder):
    """Everything this acceptance needs from HA in GETs: Core version, the update entity, the config entries of
    open_thermostat, the integration's diagnostics download (integration version from HA itself, the entity
    registry counts and the Repairs issues of the domain), and the states list (reduced to id/state/restored).
    The diagnostics and the states list are kept as extracts plus the SHA-256 of the full answer."""
    folder = Path(folder)
    config = ha(cfg, '/api/config', token)
    save(folder / 'config-extract.json', {k: config.get(k) for k in ('version', 'state', 'safe_mode', 'recovery_mode')})
    entity_raw = ha(cfg, '/api/states/' + urllib.parse.quote(cfg.entity_id), token, record=folder / 'update-entity.json')
    entries = ha(cfg, '/api/config/config_entries/entry?domain=' + DOMAIN, token, record=folder / 'config-entries.json')
    ours = [e for e in entries if isinstance(e, dict) and e.get('domain') == DOMAIN]
    diagnostics = None
    if len(ours) == 1:
        raw = ha_bytes(cfg, '/api/diagnostics/config_entry/' + urllib.parse.quote(ours[0]['entry_id'], safe=''), token,
                       cap=16 * 1024 * 1024)
        diagnostics = {**diagnostics_extract(json.loads(raw)), 'sha256': digest(raw), 'bytes': len(raw)}
        save(folder / 'diagnostics-extract.json', diagnostics)
    raw = ha_bytes(cfg, '/api/states', token, cap=32 * 1024 * 1024)
    states = json.loads(raw)
    reduced = reduce_states(states)
    save(folder / 'states-reduced.json', {'sha256': digest(raw), 'bytes': len(raw), 'count': len(reduced),
                                          'entities': reduced})
    hacs = [entity_summary(s) for s in states if str(s.get('entity_id', '')).startswith('update.')
            and cfg.hacs_repository in str((s.get('attributes') or {}).get('release_url') or '')]
    control = control_sensors(states)
    save(folder / 'hacs-and-control.json', {'hacs_update_entities': hacs, 'control_sensors': control})
    return summarize_snapshot(config, entity_summary(entity_raw), entries, diagnostics, reduced, hacs, control)


def summarize_snapshot(config, entity, entries, diagnostics, reduced, hacs, control):
    return {'ha_core_version': config.get('version'), 'entity': entity, 'config_entries': entries_summary(entries),
            'diagnostics': diagnostics, 'integration_version': integration_version(diagnostics),
            'states': {'count': len(reduced), 'restored': sorted(e['entity_id'] for e in reduced if e['restored'])},
            'hacs_update_entities': hacs, 'control_sensors': control}


def ha_history(cfg, token, entity_id, since, record=None):
    return ha(cfg, '/api/history/period/' + urllib.parse.quote(since) + '?filter_entity_id=' + urllib.parse.quote(entity_id)
              + '&significant_changes_only=0', token, record=record)


# ------------------------------------------------------------------ E32

def e32(cfg, out, cookie_name, password):
    """The bounded e32client, with its request log and cookies in this capture folder; one login at most.
    The password goes to the login call as an argument; it is not put into the environment at all."""
    sys.path.insert(0, str(HERE))
    import e32client as e
    e.D = Path(out)
    e.HOST = cfg.e32_url.rstrip('/')
    assert is_lan_host(urllib.parse.urlsplit(e.HOST).hostname), 'the E32 is only reached on the LAN'
    assert e.POST_ALLOWED == ('/auth/login',), 'e32client allows more than /auth/login; refusing'
    client = e.Client(cookie_name=cookie_name)
    e.login_if_needed(client, Path(out).name, password)
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

    The E32 refuses every change while it has the factory password, the export included (403
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


# ------------------------------------------------------------------ MQTT (read-only listener)

MQTT_LINE = re.compile(r'^\s*([\d.]+) ([R-]) (\S+) (\d+)B ?(.*)$')


def add_mqtt_arguments(parser):
    parser.add_argument('--mqtt-user', help=f'broker user (or {MQTT_USER_ENV}); password: {MQTT_PASSWORD_ENV} or a prompt')
    parser.add_argument('--no-mqtt', action='store_true', help='skip the listener (the MQTT checks stay false)')


def mqtt_credentials(args, cfg):
    """Resolved before any network: host/port from the configuration, user from --mqtt-user, OT_MQTT_USER or a
    prompt, the password from OT_MQTT_PASSWORD or a prompt. They only ever travel on the listener's stdin."""
    if args.no_mqtt:
        return None
    user = args.mqtt_user or os.environ.get(MQTT_USER_ENV)
    if not user and sys.stdin is not None and sys.stdin.isatty():
        user = input(f'MQTT user on {cfg.mqtt_host} (the broker account Home Assistant uses): ').strip()
    if not user:
        raise SystemExit(f'Give --mqtt-user (or {MQTT_USER_ENV}); or --no-mqtt (the MQTT checks then stay false).')
    password = read_secret(MQTT_PASSWORD_ENV, f'MQTT password for {user}@{cfg.mqtt_host}: ')
    return (json.dumps({'host': cfg.mqtt_host, 'port': cfg.mqtt_port, 'user': user, 'pw': password}) + '\n').encode()


def wsl_path(path):
    """C:\\Users\\x\\file -> /mnt/c/Users/x/file (long form: GetLongPathName turns 8.3 names into real ones)."""
    import ctypes
    buffer = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetLongPathNameW(str(path), buffer, 1024)
    long = buffer.value or str(path)
    return '/mnt/' + long[0].lower() + long[2:].replace('\\', '/')


def listener_command(cfg, seconds):
    """How to run mqtt_listen.py: with this Python when it has paho-mqtt, else (Windows) inside WSL."""
    script = HERE / 'mqtt_listen.py'
    try:
        import importlib.util
        if importlib.util.find_spec('paho') is not None:
            return [sys.executable, '-I', str(script), str(seconds), cfg.mqtt_prefix]
    except (ImportError, ValueError):
        pass
    if sys.platform != 'win32':
        raise SystemExit('The MQTT listener needs paho-mqtt: pip install paho-mqtt (or use --no-mqtt)')
    python = cfg.wsl_python
    python = '"$HOME/' + python[2:] + '"' if python.startswith('~/') else "'" + python.replace("'", "'\\''") + "'"
    return ['wsl', '-e', 'bash', '-c', f'exec {python} "$@"', 'ot-mqtt-listen', wsl_path(script), str(seconds),
            cfg.mqtt_prefix]


def mqtt_listen(cfg, credentials, seconds):
    """Runs mqtt_listen.py with the credentials on stdin (never on a command line or in a file)."""
    import subprocess
    listen = subprocess.run(listener_command(cfg, seconds), input=credentials, capture_output=True,
                            timeout=seconds + 120)
    return listen.stdout


def parse_mqtt(text):
    return [m.groups() for m in map(MQTT_LINE.match, text.splitlines()) if m]


def mqtt_evaluate(messages, listen_s):
    """Findings from one listening window: availability, heartbeat cadence and the heartbeat's own disconnect
    counters and uptime, the boiler fields, and the active-control block of the last fw/state/heating."""
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

def stamp(text):
    import datetime as dt
    return dt.datetime.strptime(text[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc)


def boot_instant(at_utc, uptime_seconds):
    """When the E32 booted: the time of the reading minus its uptime (a datetime), or None."""
    import datetime as dt
    if not isinstance(at_utc, str) or type(uptime_seconds) is not int:
        return None
    try:
        return stamp(at_utc) - dt.timedelta(seconds=uptime_seconds)
    except ValueError:
        return None


def boot_continuity(observations, install_started, install_finished):
    """R5-08: the observations belong to the boot that the install produced. `observations` = [{'at_utc',
    'uptime_seconds'}] in time order. All boot instants agree (BOOT_JITTER_S: the same boot, no restart between
    the reads), and the first one lies in [install start - 60 s, install end + 300 s]."""
    import datetime as dt
    boots = [boot_instant(o.get('at_utc'), o.get('uptime_seconds')) for o in observations]
    detail = {'boot_instants': [b and b.strftime('%Y-%m-%dT%H:%M:%SZ') for b in boots]}
    if not boots or any(b is None for b in boots):
        return False, {**detail, 'why': 'an observation has no time or uptime'}
    try:
        started, finished = stamp(install_started), stamp(install_finished)
    except (TypeError, ValueError):
        return False, {**detail, 'why': 'the install record has no start or end time'}
    same = all(abs((b - boots[0]).total_seconds()) <= BOOT_JITTER_S for b in boots)
    inside = (started - dt.timedelta(seconds=BOOT_BEFORE_S) <= boots[0] <= finished + dt.timedelta(seconds=BOOT_AFTER_S))
    return same and inside, {**detail, 'same_boot': same, 'boot_inside_install_window': inside}


def diagnostics_extract(doc):
    """HA's diagnostics download (homeassistant.components.diagnostics): the loaded integration's own manifest
    version, the custom_components list entry, Core, HACS, the integration's entity-registry counts
    (support_diagnostics.entity_counts) and its firmware view, and the domain's Repairs issues (if listed)."""
    doc = doc if isinstance(doc, dict) else {}
    info = doc.get('home_assistant') or {}
    custom = doc.get('custom_components') or {}
    manifest = doc.get('integration_manifest') or {}
    e32_data = (doc.get('data') or {}).get('e32') or {}
    issues = doc.get('issues')
    return {'home_assistant_version': info.get('version'), 'manifest_domain': manifest.get('domain'),
            'manifest_version': manifest.get('version'), 'custom_component_version': (custom.get(DOMAIN) or {}).get('version'),
            'hacs_version': (custom.get('hacs') or {}).get('version'),
            'entities': e32_data.get('entities'),
            'firmware': {k: (e32_data.get('firmware') or {}).get(k) for k in ('installed_version', 'latest_version', 'in_progress')},
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
    E32's active-control state."""
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
    """One loaded open_thermostat config entry, the same one as before the Home Assistant upgrade."""
    b, n = baseline['config_entries'], now['config_entries']
    return (b['count'] == 1 and n['count'] == 1 and n['entry_ids'] == b['entry_ids'] and n['states'] == ['loaded']
            and n['disabled_by'] == [None])


def one_loaded_entry(now):
    """Without a baseline (post-only): exactly one loaded, enabled open_thermostat config entry."""
    n = now['config_entries']
    return n['count'] == 1 and n['states'] == ['loaded'] and n['disabled_by'] == [None]


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
    """Did the E32 control the boiler before the update (an active state with a stored confirmation)?"""
    a = (heating or {}).get('active') or {}
    return a.get('confirmation_stored') is True and a.get('state') in OWNING + ('stopped_measurement_lost',)


def control_state(heating, owned):
    """The E32's active control after the update (ActiveHeatGuard), as a phase and whether it is safe.

    owned (the E32 controlled the boiler before the update):
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
    """Right after an update from a firmware that kept nothing over a restart, the self-tuning has no history and
    the learner counts only this boot. (Informational: a firmware that keeps what it learned does not start fresh.)"""
    tuning = summary.get('tuning') or {}
    small = lambda v: isinstance(v, (int, float)) and v <= 1
    return (summary.get('tuning') is not None and tuning.get('log_entries') == 0 and tuning.get('yesterday') is None
            and small(summary.get('heating_periods')) and all(small(r.get('periods')) for r in summary['rooms'])
            and summary.get('boiler_minimum_flow_c') is None)


def learned_kept(before, after):
    """Did what the E32 had learned survive the update? True when no counter went down, False when one did,
    None when there was nothing to keep (or no earlier reading). Informational, never gating."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    pairs = [(before.get('heating_periods'), after.get('heating_periods'))]
    rooms = {r.get('id'): r for r in after.get('rooms') or []}
    for room in before.get('rooms') or []:
        now = rooms.get(room.get('id')) or {}
        pairs += [(room.get('periods'), now.get('periods')), (room.get('segments'), now.get('segments'))]
    pairs = [(b, a) for b, a in pairs if isinstance(b, (int, float)) and b > 0]
    if not pairs:
        return None
    return all(isinstance(a, (int, float)) and a >= b for b, a in pairs)


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
    has the factory password (403 password_change_required; a later run must compare it)."""
    refused_for_password = (export.get('http_status') == 403 and export.get('refusal') == 'password_change_required'
                            and default_password is True)
    ok = not differences and (bool(export.get('compared')) or refused_for_password)
    return ok, {'differences': differences[:50], 'export': export, **notes}


def compare_export(before, after):
    """The passphrase-less export document of two moments: everything the first had must be in the second
    (schema additions are allowed). `firmware` and `created` describe the export itself, not a setting."""
    before, after = dict(before), dict(after)
    for key in ('firmware', 'created', 'secrets'):  # the sealed secrets box differs per export and cannot be compared
        before.pop(key, None)
        after.pop(key, None)
    bt_before, bt_after = before.pop('bluetooth', None), after.pop('bluetooth', None)
    found = []
    _diff(before, after, 'config-backup-export.json', False, found)
    _diff(bt_before, bt_after, 'config-backup-export.json.bluetooth', True, found)
    return found


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
            found = compare_export(before, after)
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


def export_document(raw):
    """A saved E32 settings export (the passphrase-less /config/backup export, or the plain document that Home
    Assistant's daily backup holds), or None when the bytes are something else."""
    try:
        document = json.loads(raw)
    except ValueError:
        return None
    ok = isinstance(document, dict) and document.get('format') == 'openthermostat-e32-backup' and document.get('schema') == 1
    return document if ok else None
