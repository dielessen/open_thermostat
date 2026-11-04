"""Pre-install captures for the attended update of an E32 on the Home Assistant route (installer's capture).

docs/modern-thermostat/HA-UPDATE-ACCEPTANCE-BETA19.md sections 0-2, in two stages. Which release it is comes from
install-config.json (or --config / the version arguments); nothing about a release is written in this script.

  --stage ha-baseline   BEFORE the Home Assistant integration is upgraded (HA still runs ha_previous_version).
                        Home Assistant and GitHub only, no E32 contact: the config entry, the integration version,
                        the entity counts and states (for "no new duplicates"), the update entity. Exit 2: do not
                        start.
  --stage e32 --baseline <ha-baseline folder>
                        AFTER the new integration is installed and HA restarted, BEFORE anyone presses Install:
                        GitHub (the release, firmware.bin and e32v2-update.json checked against each other), HA
                        again (the upgrade kept the one config entry, no new duplicate or stale entities, the
                        entity offers exactly the planned tag), then one E32 session: identity, health, the
                        active-control state, the password state, what was learned, and the settings backup with
                        the passphrase-less export. Exit 2: do not press Install.

Sends: anonymous GitHub GETs; HA GETs to the configured LAN address only (/api/config, /api/states,
/api/states/<update entity>, /api/config/config_entries/entry?domain=open_thermostat,
/api/diagnostics/config_entry/<entry id>); stage e32 also E32 GETs through e32client with at most one /auth/login,
one POST /config/backup {"action":"export"} (no passphrase) and one POST /auth/logout. Nothing changes on the E32 or
in HA. The E32 password: OT_E32_PASSWORD or a prompt, or --factory-password.

Usage (PowerShell, home network):
  python -I capture_preinstall.py --stage ha-baseline --out <new folder> [--dry-run]
  python -I capture_preinstall.py --stage e32 --baseline <ha-baseline folder> --out <new folder>
         [--factory-password] [--cache <folder>] [--dry-run]
Output: CAPTURE-SUMMARY.json and CAPTURE-MANIFEST.json (stage e32: its SHA-256 = installer_receipt_sha256),
stage e32 also backup/BACKUP-MANIFEST.json (its SHA-256 = backup_manifest_sha256), github-*.json, e32/, ha/.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script folder; this module is ours
import acceptance as acc  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
acc.add_config_arguments(parser)
parser.add_argument('--stage', choices=('ha-baseline', 'e32'), required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--baseline', help='stage e32: the ha-baseline folder')
parser.add_argument('--cache', help='Folder for the downloaded release assets (default: <out>/../release-cache)')
parser.add_argument('--token-file', default=str(acc.TOKEN_FILE))
parser.add_argument('--factory-password', action='store_true',
                    help='the E32 still has the factory password (else OT_E32_PASSWORD or a prompt)')
parser.add_argument('--dry-run', action='store_true', help='print what would be requested; nothing is sent')
args = parser.parse_args()
if args.stage == 'e32' and not args.baseline:
    parser.error('--stage e32 needs --baseline <ha-baseline folder>')
cfg = acc.load_config(args)

HA_GETS = ['HA GET /api/config', f'HA GET /api/states/{cfg.entity_id}',
           f'HA GET /api/config/config_entries/entry?domain={acc.DOMAIN}',
           'HA GET /api/diagnostics/config_entry/<the one entry id> (kept: versions, entity counts, issues + SHA-256)',
           'HA GET /api/states (kept: id/state/restored per entity + SHA-256)']
GITHUB_GETS = [f'GitHub GET api.github.com/repos/{cfg.repository}/releases/tags/{cfg.tag}',
               f'GitHub GET api.github.com/repos/{cfg.repository}/releases/tags/{cfg.ha_tag}',
               f'GitHub GET api.github.com/repos/{cfg.hacs_repository}/releases/tags/{cfg.hacs_tag}']
if args.dry_run:
    requests = ['refuse a non-empty --out folder', *GITHUB_GETS, *HA_GETS]
    if args.stage == 'e32':
        requests = [f'verify {args.baseline}/CAPTURE-MANIFEST.json',
                    'resolve the E32 password first (' + ('factory default' if args.factory_password
                                                          else f'{acc.E32_PASSWORD_ENV} or a prompt') + ')',
                    *requests,
                    'GitHub GET e32v2-update.json and firmware.bin (only when not in the cache folder yet)',
                    f'E32 GET {cfg.e32_url}/auth/session (401 expected), POST /auth/login once, GET /auth/session',
                    'E32 GET /status/version, /updates/status, /status, /status/logs, /status/heating, /auth/session',
                    'E32 GET ' + ', '.join(acc.SETTINGS_ROUTES) + ' and /config/programs/<each program>',
                    'E32 POST /config/backup {"action":"export"} (no passphrase, CSRF header)',
                    'E32 POST /auth/logout (also after an error)']
    acc.dry_run('capture_preinstall.py --stage ' + args.stage, requests,
                [f'release {cfg.previous_tag} -> {cfg.tag}, integration {cfg.ha_previous_version} -> {cfg.ha_version}',
                 'stage ha-baseline: no E32 contact' if args.stage == 'ha-baseline'
                 else 'one E32 web session, logged out at the end; none at all when HA or GitHub is not ready'],
                token_file=args.token_file)

baseline = None
if args.stage == 'e32':
    base_dir = Path(args.baseline).resolve()
    acc.verify_manifest(base_dir, 'CAPTURE-MANIFEST.json')
    baseline = json.loads((base_dir / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
    if baseline.get('kind') != 'ha_baseline_capture':
        raise SystemExit(f'{base_dir} is not an ha-baseline capture')
    if baseline.get('tag') != cfg.tag:
        raise SystemExit(f'{base_dir} was captured for {baseline.get("tag")}, not for {cfg.tag}')
    password = acc.e32_password(args.factory_password)  # before any network: no half runs
out = acc.new_folder(args.out)
cache = Path(args.cache).resolve() if args.cache else out.parent / 'release-cache'
notes = []

# 1. The published releases. The firmware release must be a published release whose channel follows the tag.
raw_release, github_release = acc.release(cfg, cfg.tag, record=out / 'github-release-raw.json')
acc.save(out / 'github-release.json', github_release)
published = acc.release_published(cfg, github_release)
if not published:
    notes.append(f'Release {cfg.tag} is not published as a '
                 f'{"pre-release" if cfg.expect_prerelease else "normal release"} '
                 '(or firmware.bin/digest missing)')
_, ha_release = acc.release(cfg, cfg.ha_tag, record=out / 'github-release-ha-raw.json')
if ha_release['tag_name'] != cfg.ha_tag or ha_release['draft'] is not False:
    notes.append(cfg.ha_tag + ' is not published')
_, hacs_release = acc.release(cfg, cfg.hacs_tag, record=out / 'github-release-hacs-raw.json', repository=cfg.hacs_repository)
if hacs_release['tag_name'] != cfg.hacs_tag or hacs_release['draft'] is not False:
    notes.append(f'HACS release {cfg.hacs_repository} {cfg.hacs_tag} is not published: HACS cannot offer it yet')
if args.stage == 'e32' and not published:
    raise SystemExit(notes[0] + ': do not install; nothing was asked from HA or the E32')

# 2. Home Assistant (GET only, LAN address).
token = acc.ha_token(args.token_file)
snapshot = acc.ha_snapshot(cfg, token, out / 'ha')
entity = snapshot['entity']
ha_state = {'ha_entity_id': entity['entity_id'], 'ha_installed_version_before': entity['installed_version'],
            'ha_latest_version_before': entity['latest_version'], 'state': entity['state'],
            'in_progress': entity['in_progress'], 'last_install_before': entity['last_install'],
            'ha_core_version': snapshot['ha_core_version'], 'ha_integration_version': snapshot['integration_version'],
            'config_entries': snapshot['config_entries'], 'issues': acc.issue_flags(snapshot['diagnostics']),
            'control_sensors': snapshot['control_sensors'], 'hacs_update_entities': snapshot['hacs_update_entities']}
if snapshot['config_entries']['count'] != 1:
    notes.append(f'{snapshot["config_entries"]["count"]} open_thermostat config entries; expected exactly one')
if entity['installed_version'] != cfg.previous_tag:
    notes.append(f'HA reports {entity["installed_version"]} installed, expected {cfg.previous_tag}')
warnings = []
if entity['latest_version'] not in (None, cfg.tag, cfg.previous_tag):
    (warnings if args.stage == 'ha-baseline' else notes).append(
        f'HA offers {entity["latest_version"]}: do NOT install it (only {cfg.tag})')
if entity['in_progress']:
    notes.append('An install is already in progress')

if args.stage == 'ha-baseline':
    if snapshot['integration_version'] != cfg.ha_previous_version:
        notes.append(f'HA integration is {snapshot["integration_version"]}, expected {cfg.ha_previous_version} before '
                     'the upgrade (a later baseline cannot show the upgrade)')
    summary = {'schema': 1, 'kind': 'ha_baseline_capture', 'tag': cfg.tag, 'config': cfg.as_dict(),
               'finished_at_utc': acc.now_utc(),
               'github_release': github_release, 'ha_release': ha_release, 'hacs_release': hacs_release,
               'ha': ha_state, 'notes': notes, 'warnings': warnings, 'ready_for_ha_upgrade': not notes}
    acc.save(out / 'CAPTURE-SUMMARY.json', summary)
    sha = acc.write_manifest(out, 'CAPTURE-MANIFEST.json', 'ha_baseline_capture')
    acc.verify_manifest(out, 'CAPTURE-MANIFEST.json')
    print(json.dumps({'out': str(out), 'ha_baseline_manifest_sha256': sha, 'ready_for_ha_upgrade': not notes,
                      'integration_version': snapshot['integration_version'],
                      'config_entries': snapshot['config_entries'], 'issues': ha_state['issues'],
                      'notes': notes, 'warnings': warnings}, indent=1))
    sys.exit(0 if not notes else 2)

# Stage e32: the Home Assistant upgrade as HA shows it now, against the baseline.
base_snapshot = {'config_entries': baseline['ha']['config_entries']}
base_states = json.loads((base_dir / 'ha' / 'states-reduced.json').read_text(encoding='utf-8'))['entities']
base_diag_path = base_dir / 'ha' / 'diagnostics-extract.json'
base_diag = json.loads(base_diag_path.read_text(encoding='utf-8')) if base_diag_path.exists() else None
now_states = json.loads((out / 'ha' / 'states-reduced.json').read_text(encoding='utf-8'))['entities']
ha_upgrade = {'baseline_integration_version': baseline['ha']['ha_integration_version'],
              'integration_version': snapshot['integration_version'],
              'single_entry_kept': acc.single_entry(base_snapshot, snapshot),
              'entities': acc.entity_changes(base_states, now_states, base_diag, snapshot['diagnostics'])}
if snapshot['integration_version'] != cfg.ha_version:
    notes.append(f'HA integration is {snapshot["integration_version"]}, not {cfg.ha_version}: install it first '
                 '(HACS) and restart HA')
if not ha_upgrade['single_entry_kept']:
    notes.append('The Home Assistant upgrade did not keep the one loaded config entry: '
                 + json.dumps({'before': base_snapshot['config_entries'], 'now': snapshot['config_entries']}))
if not ha_upgrade['entities']['ok']:
    notes.append('New duplicate or stale entities after the Home Assistant upgrade: ' + json.dumps(
        {k: ha_upgrade['entities'][k] for k in ('new_duplicate_ids', 'new_stale_ids', 'new_possible_duplicate_groups')}))
if entity['latest_version'] != cfg.tag:
    notes.append('HA does not offer ' + cfg.tag + ' yet: Settings -> Updates -> Check for updates, then capture again')
if notes:  # Home Assistant is not ready: no E32 session spent; this folder can never become a pre-install capture
    acc.save(out / 'CAPTURE-SUMMARY.json', {'schema': 1, 'kind': 'installer_preinstall_not_ready', 'tag': cfg.tag,
                                            'finished_at_utc': acc.now_utc(), 'ha_before': ha_state,
                                            'ha_upgrade': ha_upgrade, 'notes': notes, 'ready_to_install': False})
    acc.write_manifest(out, 'CAPTURE-MANIFEST.json', 'installer_preinstall_not_ready')
    print(json.dumps({'out': str(out), 'ready_to_install': False, 'e32_contacted': False, 'notes': notes}, indent=1))
    sys.exit(2)

# The release files (cached, shared with the post captures): firmware.bin against e32v2-update.json and GitHub.
public, image, descriptor, files_ok = acc.release_files(raw_release, cache, github_release)
firmware = {'sha256': acc.digest(image), 'bytes': len(image), 'descriptor': descriptor,
            'public_manifest': {k: public.get(k) for k in ('version', 'source_commit', 'web_sha256', 'sha256', 'size')},
            'matches_github_digest_size_and_marker': files_ok}
acc.save(out / 'firmware-check.json', firmware)
if not files_ok:
    notes.append('firmware.bin, e32v2-update.json and the GitHub digest/size do not agree: do NOT install')
    acc.save(out / 'CAPTURE-SUMMARY.json', {'schema': 1, 'kind': 'installer_preinstall_not_ready', 'tag': cfg.tag,
                                            'finished_at_utc': acc.now_utc(), 'ha_before': ha_state,
                                            'ha_upgrade': ha_upgrade, 'firmware': firmware, 'notes': notes,
                                            'ready_to_install': False})
    acc.write_manifest(out, 'CAPTURE-MANIFEST.json', 'installer_preinstall_not_ready')
    print(json.dumps({'out': str(out), 'ready_to_install': False, 'e32_contacted': False, 'notes': notes}, indent=1))
    sys.exit(2)

# 3. The E32 before the update: identity, health, active control, password, learned, then the settings backup.
e, client = acc.e32(cfg, out, 'preinstall-session.cookies', password)
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
if e32_before['version'] != cfg.previous_tag:
    notes.append(f'E32 runs {e32_before["version"]}, expected {cfg.previous_tag}')
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

summary = {'schema': 1, 'kind': 'installer_preinstall_capture', 'tag': cfg.tag, 'config': cfg.as_dict(),
           'finished_at_utc': acc.utc(e.now()),
           'baseline': {'folder': str(base_dir), 'manifest_sha256': acc.file_digest(base_dir / 'CAPTURE-MANIFEST.json'),
                        'finished_at_utc': baseline['finished_at_utc']},
           'github_release': github_release, 'ha_release': ha_release, 'hacs_release': hacs_release,
           'firmware': firmware, 'ha_before': ha_state, 'ha_upgrade': ha_upgrade, 'e32_before': e32_before,
           'backup_manifest_sha256': backup_manifest_sha256, 'backup_files': len(entries), 'export': export,
           'expectations': expectations, 'notes': notes, 'ready_to_install': not notes}
acc.save(out / 'CAPTURE-SUMMARY.json', summary)
installer = acc.write_manifest(out, 'CAPTURE-MANIFEST.json', 'installer_preinstall_capture')
acc.verify_manifest(out, 'CAPTURE-MANIFEST.json')
print(json.dumps({'out': str(out), 'installer_receipt_sha256': installer, 'backup_manifest_sha256': backup_manifest_sha256,
                  'ready_to_install': not notes, 'notes': notes, 'expectations': expectations}, indent=1))
sys.exit(0 if not notes else 2)
