"""Pre-install captures for the attended beta.22 -> rc.2 update (installer's capture), in two stages.

docs/modern-thermostat/HA-UPDATE-ACCEPTANCE-BETA19.md sections 0-2, for rc.2 with the HACS migration in front.

  --stage ha-baseline   BEFORE the HACS migration (HA still runs the manual 0.4.0b15). Home Assistant and
                        GitHub only, no E32 contact: the config entry, the integration version, the entity
                        counts and states (for "no new duplicates"), the update entity. Exit 2: do not start.
  --stage e32 --baseline <ha-baseline folder>
                        AFTER HA 1.0.0rc2 is installed through HACS and HA restarted, BEFORE anyone presses
                        Install: HA again (the migration kept the one config entry, no new duplicate or stale
                        entities, the entity offers exactly rc.2), then one E32 session: identity, health,
                        the active-control state, the password state, what was learned, and the settings
                        backup with the passphrase-less export. Exit 2: do not press Install.

Sends: anonymous GitHub GETs; HA GETs to https://192.168.1.130:8123 only (/api/config, /api/states,
/api/states/<update entity>, /api/config/config_entries/entry?domain=open_thermostat,
/api/diagnostics/config_entry/<entry id>); stage e32 also E32 GETs through e32client with at most one
/auth/login, one POST /config/backup {"action":"export"} (no passphrase) and one POST /auth/logout.
Nothing changes on the E32 or in HA. The E32 password: OT_E32_PASSWORD or a prompt, or --factory-password.

Usage (PowerShell, home network):
  python -I capture_rc2_preinstall.py --stage ha-baseline --out <new folder> [--dry-run]
  python -I capture_rc2_preinstall.py --stage e32 --baseline <ha-baseline folder> --out <new folder>
         [--factory-password] [--dry-run]
Output: CAPTURE-SUMMARY.json and CAPTURE-MANIFEST.json (stage e32: its SHA-256 = installer_receipt_sha256),
stage e32 also backup/BACKUP-MANIFEST.json (its SHA-256 = backup_manifest_sha256), github-*.json, e32/, ha/.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script folder; this module is ours
import rc2_acc as acc  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument('--stage', choices=('ha-baseline', 'e32'), required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--baseline', help='stage e32: the ha-baseline folder')
parser.add_argument('--token-file', default=str(acc.TOKEN_FILE))
parser.add_argument('--factory-password', action='store_true',
                    help='the E32 still has the factory password (else OT_E32_PASSWORD or a prompt)')
parser.add_argument('--dry-run', action='store_true', help='print what would be requested; nothing is sent')
args = parser.parse_args()
if args.stage == 'e32' and not args.baseline:
    parser.error('--stage e32 needs --baseline <ha-baseline folder>')

HA_GETS = ['HA GET /api/config', f'HA GET /api/states/{acc.ENTITY}',
           f'HA GET /api/config/config_entries/entry?domain={acc.DOMAIN}',
           'HA GET /api/diagnostics/config_entry/<the one entry id> (kept: versions, entity counts, issues + SHA-256)',
           'HA GET /api/states (kept: id/state/restored per entity + SHA-256)']
GITHUB_GETS = [f'GitHub GET api.github.com/repos/{acc.REPOSITORY}/releases/tags/{acc.TAG}',
               f'GitHub GET api.github.com/repos/{acc.REPOSITORY}/releases/tags/{acc.HA_TAG}',
               f'GitHub GET api.github.com/repos/{acc.HACS_REPOSITORY}/releases/tags/{acc.HACS_TAG}']
if args.dry_run:
    requests = ['refuse a non-empty --out folder', *GITHUB_GETS, *HA_GETS]
    if args.stage == 'e32':
        requests = [f'verify {args.baseline}/CAPTURE-MANIFEST.json',
                    'resolve the E32 password first (' + ('factory default' if args.factory_password
                                                          else f'{acc.E32_PASSWORD_ENV} or a prompt') + ')',
                    *requests,
                    'E32 GET /auth/session (401 expected), POST /auth/login once, GET /auth/session',
                    'E32 GET /status/version, /updates/status, /status, /status/logs, /status/heating, /auth/session',
                    'E32 GET ' + ', '.join(acc.SETTINGS_ROUTES) + ' and /config/programs/<each program>',
                    'E32 POST /config/backup {"action":"export"} (no passphrase, CSRF header)',
                    'E32 POST /auth/logout (also after an error)']
    acc.dry_run('capture_rc2_preinstall.py --stage ' + args.stage, requests,
                ['stage ha-baseline: no E32 contact' if args.stage == 'ha-baseline'
                 else 'one E32 web session, logged out at the end; none at all when HA or GitHub is not ready'])

baseline = None
if args.stage == 'e32':
    base_dir = Path(args.baseline).resolve()
    acc.verify_manifest(base_dir, 'CAPTURE-MANIFEST.json')
    baseline = json.loads((base_dir / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
    assert baseline.get('kind') == 'ha_baseline_capture', '--baseline is not an ha-baseline capture'
    password = acc.e32_password(args.factory_password)  # before any network: no half runs
out = acc.new_folder(args.out)
notes = []

# 1. The published releases. rc.1 is never installed; rc.2 must be the published pre-release.
_, github_release = acc.release(acc.TAG, record=out / 'github-release-raw.json')
acc.save(out / 'github-release.json', github_release)
asset = github_release['asset']
published = (github_release['tag_name'] == acc.TAG and github_release['draft'] is False
             and github_release['prerelease'] is True and bool(asset) and str(asset.get('digest', '')).startswith('sha256:'))
if not published:
    notes.append(f'Release {acc.TAG} is not published (or firmware.bin/digest missing)')
_, ha_release = acc.release(acc.HA_TAG, record=out / 'github-release-ha-raw.json')
if ha_release['tag_name'] != acc.HA_TAG or ha_release['draft'] is not False:
    notes.append(acc.HA_TAG + ' is not published')
_, hacs_release = acc.release(acc.HACS_TAG, record=out / 'github-release-hacs-raw.json', repository=acc.HACS_REPOSITORY)
if hacs_release['tag_name'] != acc.HACS_TAG or hacs_release['draft'] is not False:
    notes.append(f'HACS release {acc.HACS_REPOSITORY} {acc.HACS_TAG} is not published: HACS cannot offer it yet')
if args.stage == 'e32' and not published:
    raise SystemExit(notes[0] + ': do not install; nothing was asked from HA or the E32')

# 2. Home Assistant (GET only, LAN IP).
token = acc.ha_token(args.token_file)
snapshot = acc.ha_snapshot(token, out / 'ha')
entity = snapshot['entity']
ha_state = {'ha_entity_id': entity['entity_id'], 'ha_installed_version_before': entity['installed_version'],
            'ha_latest_version_before': entity['latest_version'], 'state': entity['state'],
            'in_progress': entity['in_progress'], 'last_install_before': entity['last_install'],
            'ha_core_version': snapshot['ha_core_version'], 'ha_integration_version': snapshot['integration_version'],
            'config_entries': snapshot['config_entries'], 'issues': acc.issue_flags(snapshot['diagnostics']),
            'control_sensors': snapshot['control_sensors'], 'hacs_update_entities': snapshot['hacs_update_entities']}
if snapshot['config_entries']['count'] != 1:
    notes.append(f'{snapshot["config_entries"]["count"]} open_thermostat config entries; expected exactly one')
if entity['installed_version'] != acc.PREV:
    notes.append(f'HA reports {entity["installed_version"]} installed, expected {acc.PREV}')
warnings = []
if entity['latest_version'] in acc.NEVER_INSTALL:
    (warnings if args.stage == 'ha-baseline' else notes).append(
        f'HA offers {entity["latest_version"]}: do NOT install it (only {acc.TAG})')
if entity['in_progress']:
    notes.append('An install is already in progress')

if args.stage == 'ha-baseline':
    if snapshot['integration_version'] != acc.HA_PREV_VERSION:
        notes.append(f'HA integration is {snapshot["integration_version"]}, expected {acc.HA_PREV_VERSION} before the '
                     'HACS migration (a later baseline cannot show the migration)')
    summary = {'schema': 1, 'kind': 'ha_baseline_capture', 'tag': acc.TAG, 'finished_at_utc': acc.now_utc(),
               'github_release': github_release, 'ha_release': ha_release, 'hacs_release': hacs_release,
        'ha': ha_state, 'notes': notes, 'warnings': warnings, 'ready_for_hacs': not notes}
    acc.save(out / 'CAPTURE-SUMMARY.json', summary)
    sha = acc.write_manifest(out, 'CAPTURE-MANIFEST.json', 'ha_baseline_capture')
    acc.verify_manifest(out, 'CAPTURE-MANIFEST.json')
    print(json.dumps({'out': str(out), 'ha_baseline_manifest_sha256': sha, 'ready_for_hacs': not notes,
                      'integration_version': snapshot['integration_version'],
                      'config_entries': snapshot['config_entries'], 'issues': ha_state['issues'],
                      'notes': notes, 'warnings': warnings}, indent=1))
    sys.exit(0 if not notes else 2)

# Stage e32: the HACS migration as HA shows it now, against the baseline.
base_snapshot = {'config_entries': baseline['ha']['config_entries']}
base_states = json.loads((base_dir / 'ha' / 'states-reduced.json').read_text(encoding='utf-8'))['entities']
base_diag_path = base_dir / 'ha' / 'diagnostics-extract.json'
base_diag = json.loads(base_diag_path.read_text(encoding='utf-8')) if base_diag_path.exists() else None
now_states = json.loads((out / 'ha' / 'states-reduced.json').read_text(encoding='utf-8'))['entities']
migration = {'baseline_integration_version': baseline['ha']['ha_integration_version'],
             'integration_version': snapshot['integration_version'],
             'single_entry_kept': acc.single_entry(base_snapshot, snapshot),
             'entities': acc.entity_changes(base_states, now_states, base_diag, snapshot['diagnostics'])}
if snapshot['integration_version'] != acc.HA_VERSION:
    notes.append(f'HA integration is {snapshot["integration_version"]}, not {acc.HA_VERSION}: install it via HACS '
                 'and restart HA first')
if not migration['single_entry_kept']:
    notes.append('The HACS migration did not keep the one loaded config entry: '
                 + json.dumps({'before': base_snapshot['config_entries'], 'now': snapshot['config_entries']}))
if not migration['entities']['ok']:
    notes.append('New duplicate or stale entities after the HACS migration: ' + json.dumps(
        {k: migration['entities'][k] for k in ('new_duplicate_ids', 'new_stale_ids', 'new_possible_duplicate_groups')}))
if entity['latest_version'] != acc.TAG:
    notes.append('HA does not offer ' + acc.TAG + ' yet: Settings -> Updates -> Check for updates, then capture again')
if notes:  # Home Assistant is not ready: no E32 session spent; this folder can never become a pre-install capture
    acc.save(out / 'CAPTURE-SUMMARY.json', {'schema': 1, 'kind': 'installer_preinstall_not_ready', 'tag': acc.TAG,
                                            'finished_at_utc': acc.now_utc(), 'ha_before': ha_state,
                                            'ha_migration': migration, 'notes': notes, 'ready_to_install': False})
    acc.write_manifest(out, 'CAPTURE-MANIFEST.json', 'installer_preinstall_not_ready')
    print(json.dumps({'out': str(out), 'ready_to_install': False, 'e32_contacted': False, 'notes': notes}, indent=1))
    sys.exit(2)

# 3. The E32 before the update: identity, health, active control, password, learned, then the settings backup.
e, client = acc.e32(out, 'preinstall-session.cookies', password)
del password
try:
    identity = {name: client.read(path, out / 'e32', name) for name, path in acc.IDENTITY_ROUTES}
    logs = client.read('/status/logs', out / 'e32', 'logs')
    heating = client.read('/status/heating', out / 'e32', 'heating')
    access = acc.password_state(client)
    entries, export = acc.read_settings(e, client, out / 'backup', export_required=True)
finally:
    logged_out = acc.logout(e, client)
runtime = logs.get('runtime') or {}
owned = acc.owned_before(heating)
e32_before = {'version': identity['version'].get('version'), 'source_commit': identity['version'].get('source'),
              'elf_sha256': identity['version'].get('sha256'), 'web_sha256': identity['version'].get('web_sha256'),
              'uptime_seconds': identity['status'].get('uptime'), 'boot_pending': identity['updates'].get('boot_pending'),
              'busy': identity['updates'].get('busy'), 'phase': identity['updates'].get('phase'),
              'mqtt_counters': {k: runtime.get(k) for k in runtime if k.startswith('mqtt_')},
              'active': acc.control_state(heating, owned)['detail'], 'owned_boiler': owned,
              'plan_mode': heating.get('mode'), 'password': access, 'learned': acc.learned_summary(heating),
              'logout_http_status': logged_out}
if e32_before['version'] != acc.PREV:
    notes.append(f'E32 runs {e32_before["version"]}, expected {acc.PREV}')
if e32_before['boot_pending'] is not False or e32_before['busy']:
    notes.append('E32 update state is not idle/confirmed')
expectations = [('The E32 controls the boiler (active, confirmation stored): after the update it waits for the '
                 'owner to confirm again (Repairs), with frost protection only' if owned else
                 'The E32 does not control the boiler now: no re-confirmation is expected after the update'),
                ('The E32 has the factory password: after the update HA shows the Repairs issue "E32 still uses the '
                 'default password"; choose a new one BEFORE the re-confirmation' if access['default_password'] else
                 'The E32 has its own password: no password Repairs issue is expected')]

acc.save(out / 'backup' / 'BACKUP-MANIFEST.json', {
    'schema': 1, 'at_utc': acc.utc(e.now()), 'files': entries, 'payloads_rechecked': len(entries),
    'scope': 'Settings documents, room catalog, programs, Bluetooth bindings and the heating plan as the API returns '
             'them (secrets redacted by the device), plus the passphrase-less /config/backup export (no keys, no '
             'Wi-Fi or web passwords). Not a raw NVS/flash image; an app-only update keeps NVS/SPIFFS.'})
backup_manifest_sha256 = acc.file_digest(out / 'backup' / 'BACKUP-MANIFEST.json')
acc.verify_manifest(out / 'backup', 'BACKUP-MANIFEST.json')

summary = {'schema': 1, 'kind': 'installer_preinstall_capture', 'tag': acc.TAG, 'finished_at_utc': acc.utc(e.now()),
           'baseline': {'folder': str(base_dir), 'manifest_sha256': acc.file_digest(base_dir / 'CAPTURE-MANIFEST.json'),
                        'finished_at_utc': baseline['finished_at_utc']},
           'github_release': github_release, 'ha_release': ha_release, 'hacs_release': hacs_release,
           'ha_before': ha_state, 'ha_migration': migration, 'e32_before': e32_before,
           'backup_manifest_sha256': backup_manifest_sha256, 'backup_files': len(entries), 'export': export,
           'expectations': expectations, 'notes': notes, 'ready_to_install': not notes}
acc.save(out / 'CAPTURE-SUMMARY.json', summary)
installer = acc.write_manifest(out, 'CAPTURE-MANIFEST.json', 'installer_preinstall_capture')
acc.verify_manifest(out, 'CAPTURE-MANIFEST.json')
print(json.dumps({'out': str(out), 'installer_receipt_sha256': installer, 'backup_manifest_sha256': backup_manifest_sha256,
                  'ready_to_install': not notes, 'notes': notes, 'expectations': expectations}, indent=1))
sys.exit(0 if not notes else 2)
