"""Post-install observation for the attended beta.22 -> rc.2 update on the Home Assistant route.

docs/modern-thermostat/HA-UPDATE-ACCEPTANCE-BETA19.md sections 4-5, for rc.2. Run it at least twice after the
one Install press, each time into a new folder, never while another capture runs:
  post 1  as soon as HA shows rc.2 installed, BEFORE the owner changes the password or confirms the takeover
          again: shows the documented safe state after the restart (waiting for re-confirmation, at most frost
          protection). With the factory password the E32 refuses the export (403 password_change_required);
          that is recorded, and the export is compared in post 2.
  post 2  after the password Repairs (if any) and the re-confirmation, and 600 s or more after the restart:
          the takeover state after re-confirmation, stable uptime, the export comparison.

Each run reads (read-only, plus one passphrase-less backup export and one sign-out on the E32):
  * HA (GET, https://192.168.1.130:8123 only): the update entity incl. last_install, its history since the
    pre-install capture (install-action count), Core version, the open_thermostat config entries, the
    integration's diagnostics download (integration version, entity counts, Repairs issues), the states list
    (no new duplicate or stale entities against the ha-baseline and the pre-install capture), and the history of
    HA's heat-request sensor (its "control" attribute: the E32's active-control state over time);
  * GitHub (anonymous): the release, e32v2-update.json and firmware.bin (cached; SHA-256 vs. the asset digest;
    the app descriptor's ELF SHA-256);
  * E32 (one session): /status/version, /updates/status, /status, /status/logs, /status/heating, /auth/session
    (default_password only), every settings document, the programs and the export, compared with the
    pre-install backup;
  * MQTT: the read-only listener for --listen seconds (fw/availability, fw/heartbeat with its uptime and
    disconnect counters, fw/state/heating's active block).

Usage (PowerShell):
  python -I capture_rc2_post.py --preinstall <pre folder> --out <new folder> --mqtt-user <user>
         [--factory-password] [--listen 150] [--cache <folder>] [--no-mqtt | --mqtt-smb] [--dry-run]
  E32 password: OT_E32_PASSWORD or a prompt (or --factory-password); MQTT password: OT_MQTT_PASSWORD or a prompt.
Output: OBSERVATION.json (all findings) and OBS-MANIFEST.json. Exit code 2 when a finding failed.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script folder; this module is ours
import rc2_acc as acc  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--preinstall', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--listen', type=int, default=150, help='MQTT listening time in seconds (>= 130)')
parser.add_argument('--cache', help='Folder for the downloaded release assets (default: <preinstall>/../release-cache)')
parser.add_argument('--token-file', default=str(acc.TOKEN_FILE))
parser.add_argument('--factory-password', action='store_true',
                    help='the E32 still has the factory password (else OT_E32_PASSWORD or a prompt)')
acc.add_mqtt_arguments(parser)
parser.add_argument('--dry-run', action='store_true', help='print what would be requested; nothing is sent')
args = parser.parse_args()
if args.listen < 130:
    parser.error('Listen at least 130 s to see two heartbeats')
if args.dry_run:
    acc.dry_run('capture_rc2_post.py', [
        f'verify {args.preinstall}/CAPTURE-MANIFEST.json and its ha-baseline manifest',
        'resolve the E32 password (' + ('factory default' if args.factory_password else f'{acc.E32_PASSWORD_ENV} or a prompt')
        + ') and the MQTT credentials (' + ('none: --no-mqtt' if args.no_mqtt else 'Samba' if args.mqtt_smb
                                            else f'--mqtt-user, {acc.MQTT_PASSWORD_ENV} or a prompt') + ') first',
        'refuse a non-empty --out folder',
        f'GitHub GET api.github.com/repos/{acc.REPOSITORY}/releases/tags/{acc.TAG}',
        'GitHub GET e32v2-update.json and firmware.bin (only when not in the cache folder yet)',
        'HA GET /api/config, /api/states/<update entity>, /api/config/config_entries/entry?domain=open_thermostat, '
        '/api/diagnostics/config_entry/<entry id>, /api/states',
        f'HA GET /api/history/period/<pre-install end>?filter_entity_id={acc.ENTITY}&significant_changes_only=0',
        'HA GET /api/history/period/<pre-install end>?filter_entity_id=<heat-request sensor> (when HA has one)',
        'E32 GET /auth/session (401), POST /auth/login once, GET /auth/session',
        'E32 GET /status/version, /updates/status, /status, /status/logs, /status/heating, /auth/session',
        'E32 GET ' + ', '.join(acc.SETTINGS_ROUTES) + ' and /config/programs/<each program>',
        'E32 POST /config/backup {"action":"export"} (no passphrase; 403 with the factory password is recorded)',
        'E32 POST /auth/logout (also after an error)',
        ('no MQTT' if args.no_mqtt else f'MQTT subscribe {acc.MQTT_PREFIX}/# on {args.mqtt_host}:{args.mqtt_port} for '
         f'{args.listen} s through WSL (read-only, credentials on stdin)')])

pre = Path(args.preinstall).resolve()
acc.verify_manifest(pre, 'CAPTURE-MANIFEST.json')
pre_summary = json.loads((pre / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
if pre_summary.get('kind') != 'installer_preinstall_capture' or pre_summary.get('tag') != acc.TAG:
    raise SystemExit(f'{pre} is not a ready rc.2 pre-install capture (kind {pre_summary.get("kind")})')
base_dir = Path(pre_summary['baseline']['folder'])
acc.verify_manifest(base_dir, 'CAPTURE-MANIFEST.json')
assert acc.file_digest(base_dir / 'CAPTURE-MANIFEST.json') == pre_summary['baseline']['manifest_sha256'], 'baseline changed'
baseline = json.loads((base_dir / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
pre_entries = json.loads((pre / 'backup' / 'BACKUP-MANIFEST.json').read_text(encoding='utf-8'))['files']
password = acc.e32_password(args.factory_password)  # secrets before any network: no half runs
credentials = acc.mqtt_credentials(args)
out = acc.new_folder(args.out)
cache = Path(args.cache).resolve() if args.cache else pre.parent / 'release-cache'
cache.mkdir(parents=True, exist_ok=True)
findings, info = [], {}
owned = pre_summary['e32_before']['owned_boiler']


def check(name, ok, detail=None):
    findings.append({'check': name, 'ok': bool(ok), 'detail': detail})
    return bool(ok)


def stamp(text):
    return dt.datetime.strptime(text[:19], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=dt.timezone.utc)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else None


# 1. GitHub: the release and its assets.
raw_release, github_release = acc.release(acc.TAG, record=out / 'github-release-raw.json')
assets = {a['name']: a for a in raw_release.get('assets', [])}
manifest_path = cache / 'e32v2-update.json'
if not manifest_path.exists():
    acc.github(assets['e32v2-update.json']['browser_download_url'], record=manifest_path)
public = json.loads(manifest_path.read_bytes())
firmware = cache / 'firmware.bin'
if not firmware.exists():
    acc.github(assets['firmware.bin']['browser_download_url'], cap=0x3C0000, record=firmware)
image = firmware.read_bytes()
descriptor = acc.app_descriptor(image)
check('github.release_is_the_capture_one', github_release == pre_summary['github_release'],
      {'now': github_release, 'preinstall': pre_summary['github_release']})
check('github.firmware_digest_and_size', 'sha256:' + acc.digest(image) == github_release['asset']['digest']
      and len(image) == github_release['asset']['size'] == public.get('size') and acc.digest(image) == public.get('sha256'),
      {'sha256': acc.digest(image), 'bytes': len(image)})
# The descriptor's version field holds the IDF string (Arduino build); the release marker is the build marker.
check('github.descriptor', descriptor['magic'] == '0xabcd5432'
      and ('OT_E32V2_OTA_V1:' + acc.TAG + ':' + str(public.get('source_commit')) + ':').encode() in image, descriptor)

# 2. Home Assistant (GET only, LAN IP).
token = acc.ha_token(args.token_file)
snapshot = acc.ha_snapshot(token, out / 'ha')
entity = snapshot['entity']
since = pre_summary['finished_at_utc']
history = acc.ha_history(token, acc.ENTITY, since, record=out / 'ha' / 'update-entity-history.json')
states = history[0] if history else []
progress_starts, previous, starts = 0, False, set()
for state in states:
    attributes = state.get('attributes') or {}
    running = attributes.get('in_progress') not in (None, False, 0)
    progress_starts += running and not previous
    previous = running
    last = attributes.get('last_install') or {}
    if last.get('started_at') and last['started_at'] >= since:
        starts.add(last['started_at'])
install_actions = max(progress_starts, len(starts))
last = entity['last_install'] or {}
now_states = load(out / 'ha' / 'states-reduced.json')['entities']
now_diag = snapshot['diagnostics']
base_states = load(base_dir / 'ha' / 'states-reduced.json')['entities']
pre_states = load(pre / 'ha' / 'states-reduced.json')['entities']
changes_base = acc.entity_changes(base_states, now_states, load(base_dir / 'ha' / 'diagnostics-extract.json'), now_diag)
changes_pre = acc.entity_changes(pre_states, now_states, load(pre / 'ha' / 'diagnostics-extract.json'), now_diag)
check('ha.integration_version', snapshot['integration_version'] == acc.HA_VERSION, snapshot['integration_version'])
check('ha.single_config_entry', acc.single_entry({'config_entries': baseline['ha']['config_entries']}, snapshot),
      {'baseline': baseline['ha']['config_entries'], 'now': snapshot['config_entries']})
check('ha.no_new_duplicate_or_stale_entities', changes_base['ok'] and changes_pre['ok'],
      {'since_baseline': changes_base, 'since_preinstall': {k: changes_pre[k] for k in (
          'new_duplicate_ids', 'new_stale_ids', 'new_possible_duplicate_groups')}})
check('ha.entity_reports_new_version', entity['installed_version'] == acc.TAG and entity['state'] == 'off',
      {k: entity[k] for k in ('state', 'installed_version', 'latest_version', 'in_progress')})
check('ha.install_actions==1', install_actions == 1,
      {'in_progress_starts': progress_starts, 'last_install_starts': sorted(starts), 'history_states': len(states)})
check('ha.last_install', last.get('result') == 'installed' and last.get('uploads') == 1 and last.get('tag') == acc.TAG
      and last.get('from_version') == acc.PREV and last.get('sha256') == acc.digest(image) and last.get('size') == len(image)
      and isinstance(last.get('duration_s'), (int, float)) and 0 < last['duration_s'] <= 900
      and github_release['published_at'] <= last.get('started_at', '') <= last.get('finished_at', '')
      and last['started_at'] >= since, last)
control_history = []
for sensor in snapshot['control_sensors']:
    rows = acc.ha_history(token, sensor['entity_id'], since)
    sequence = []
    for row in (rows[0] if rows else []):
        value = (row.get('attributes') or {}).get('control')
        if not sequence or sequence[-1]['control'] != value:
            sequence.append({'at': row.get('last_changed'), 'control': value})
    control_history.append({'entity_id': sensor['entity_id'], 'sequence': sequence[-40:]})
acc.save(out / 'ha' / 'control-history.json', control_history)
info['ha_issues'] = acc.issue_flags(now_diag)
info['ha_control_history'] = control_history
info['ha_hacs_update_entities'] = snapshot['hacs_update_entities']

# 3. The E32 (one session, always logged out): identity, health, active control, password, learned, settings.
e, client = acc.e32(out, 'post-session.cookies', password)
del password
try:
    at = acc.utc(e.now())
    identity = {name: client.read(path, out / 'e32', name) for name, path in acc.IDENTITY_ROUTES}
    logs = client.read('/status/logs', out / 'e32', 'logs')
    heating = client.read('/status/heating', out / 'e32', 'heating')
    access = acc.password_state(client)
    entries, export = acc.read_settings(e, client, out / 'settings', export_required=False)
finally:
    logged_out = acc.logout(e, client)
version, updates, status = identity['version'], identity['updates'], identity['status']
runtime = logs.get('runtime') or {}
uptime = status.get('uptime')
reported = last.get('reported') or {}
check('e32.version_source_elf_web_exact',
      version.get('version') == public.get('version') == acc.TAG and version.get('source') == public.get('source_commit')
      and version.get('web_sha256') == public.get('web_sha256') and version.get('sha256') == descriptor['elf_sha256']
      and reported == {'version': acc.TAG, 'source_commit': version.get('source'), 'web_sha256': version.get('web_sha256'),
                       'elf_sha256': version.get('sha256')}
      and updates.get('build_marker') == f'OT_E32V2_OTA_V1:{acc.TAG}:{version.get("source")}:{version.get("web_sha256")}:END',
      {'version': version, 'public': public, 'descriptor_elf': descriptor['elf_sha256'], 'reported': reported})
check('e32.boot_confirmed', updates.get('boot_pending') is False and updates.get('reboot_required') is False
      and not updates.get('busy'), {k: updates.get(k) for k in ('boot_pending', 'reboot_required', 'busy', 'phase')})
since_install = (stamp(at) - stamp(last['started_at'])).total_seconds() if last.get('started_at') else None
check('e32.new_boot_after_install', since_install is not None and isinstance(uptime, int)
      and uptime <= since_install + 5 and pre_summary['e32_before']['version'] == acc.PREV,
      {'uptime_seconds': uptime, 'seconds_since_install_start': since_install})
control = acc.control_state(heating, owned)
check('e32.control_state_safe', control['ok'], {**control, 'owned_before_update': owned})
differences, compare_notes = acc.compare_settings(pre / 'backup', out / 'settings', pre_entries)
check('e32.settings_programs_bindings_preserved',
      *acc.settings_finding(differences, compare_notes, export, access['default_password']))
summary = acc.learned_summary(heating)
info['learned'] = {'summary': summary, 'fresh': acc.learned_fresh(summary),
                   'before_update': pre_summary['e32_before']['learned']}
info['password'] = {**access, 'before_update': pre_summary['e32_before']['password']}
observation = {'at_utc': at, 'version': version.get('version'), 'boot_pending': updates.get('boot_pending'),
               'uptime_seconds': uptime, 'mqtt_counters': {k: runtime.get(k) for k in runtime if k.startswith('mqtt_')},
               'control_phase': control['phase'], 'default_password': access['default_password'],
               'export_http_status': export['http_status'], 'logout_http_status': logged_out}

# 4. MQTT: availability, heartbeat and the active block (read-only listener; credentials stay in the pipe).
if credentials is None:
    for name in ('availability_online', 'heartbeat_every_60s', 'heartbeat_counters_steady', 'boiler_fields_seen'):
        check('mqtt.' + name, False, 'not run (--no-mqtt)')
else:
    text = acc.mqtt_listen(credentials, args.listen)
    del credentials
    (out / 'mqtt').mkdir(exist_ok=True)
    (out / 'mqtt' / 'listen.txt').write_bytes(text)
    result = acc.mqtt_evaluate(acc.parse_mqtt(text.decode('utf-8', 'replace')), args.listen)
    for name in ('availability_online', 'heartbeat_every_60s', 'heartbeat_counters_steady', 'boiler_fields_seen'):
        check('mqtt.' + name, result[name], result['detail'] if name != 'boiler_fields_seen' else result['detail']['messages'])
    info['mqtt_state_heating_active'] = result['detail']['state_heating_active']
    info['mqtt_heartbeat_uptime_rising'] = result['heartbeat_uptime_rising']

failed = [f['check'] for f in findings if not f['ok']]
acc.save(out / 'OBSERVATION.json', {'schema': 1, 'kind': 'installer_post_observation', 'tag': acc.TAG,
                                    'preinstall': str(pre), 'observation': observation, 'install_actions': install_actions,
                                    'ha_entity': entity, 'ha_core_version': snapshot['ha_core_version'],
                                    'ha_integration_version': snapshot['integration_version'],
                                    'ha_config_entries': snapshot['config_entries'], 'github_release': github_release,
                                    'public_manifest': public, 'firmware_descriptor': descriptor,
                                    'firmware_sha256': acc.digest(image), 'firmware_bytes': len(image),
                                    'control': control, 'settings_differences': differences, 'export': export,
                                    'info': info, 'findings': findings, 'failed': failed})
sha = acc.write_manifest(out, 'OBS-MANIFEST.json', 'installer_post_observation')
print(json.dumps({'out': str(out), 'observation': observation, 'failed': failed, 'obs_manifest_sha256': sha,
                  'ha_issues': info['ha_issues'], 'learned_fresh': info['learned']['fresh']}, indent=1))
sys.exit(0 if not failed else 2)
