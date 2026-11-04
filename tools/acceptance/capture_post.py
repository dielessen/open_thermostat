"""Post-install observation for the attended update of an E32 on the Home Assistant route.

docs/modern-thermostat/HA-UPDATE-ACCEPTANCE-BETA19.md sections 4-5. Run it at least twice after the one Install
press, each time into a new folder, never while another capture runs:
  post 1  as soon as HA shows the new version installed, BEFORE the owner changes the password or confirms the
          takeover again: shows the documented safe state after the restart (waiting for re-confirmation, at most
          frost protection). With the factory password the E32 refuses the export (403 password_change_required);
          that is recorded, and the export is compared in post 2.
  post 2  after the password Repairs (if any) and the re-confirmation, and 600 s or more after the restart:
          the takeover state after re-confirmation, stable uptime, the export comparison.

Each run reads (read-only, plus one passphrase-less backup export and one sign-out on the E32):
  * HA (GET, the configured LAN address only): the update entity incl. last_install, its history since the
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

--post-only is for an install that was made WITHOUT a pre-install capture (and only then). It records what can
still be read and what cannot, and accepts substitute evidence only when it is named:
  --history-since <UTC>   the start of the Home Assistant recorder history to read (install actions, the
                          offer before the install, the heat-request sensor's control phases);
  --pre-backup <file>     an E32 settings export from BEFORE the install (the document Home Assistant's daily
                          backup holds, or an earlier passphrase-less export), compared with the export now;
                          --pre-backup-at <UTC> says when it was made if its "created" field does not;
  --owned-before yes|no   whether the E32 controlled the boiler before the update (from your own knowledge).
Every one of these is listed as a substitute in the observation. Without them the checks that need a pre-install
capture stay false and the receipt stays INCOMPLETE.

Usage (PowerShell):
  python -I capture_post.py --preinstall <pre folder> --out <new folder> --mqtt-user <user>
         [--factory-password] [--listen 150] [--cache <folder>] [--no-mqtt] [--dry-run]
  python -I capture_post.py --post-only --history-since <UTC> [--pre-backup <file>] [--owned-before yes|no]
         --out <new folder> ...
  E32 password: OT_E32_PASSWORD or a prompt (or --factory-password); MQTT login: OT_MQTT_USER / OT_MQTT_PASSWORD
  or typed at a prompt.
Output: OBSERVATION.json (all findings) and OBS-MANIFEST.json. Exit code 2 when a finding failed.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script folder; this module is ours
import acceptance as acc  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
acc.add_config_arguments(parser)
parser.add_argument('--preinstall', help='the pre-install capture folder (not with --post-only)')
parser.add_argument('--post-only', action='store_true', help='no pre-install capture exists: record the gaps')
parser.add_argument('--history-since', help='--post-only: UTC time from which the HA recorder history is read')
parser.add_argument('--pre-backup', help='--post-only: an E32 settings export from before the install')
parser.add_argument('--pre-backup-at', help='--post-only: UTC time of that export (default: its "created" field)')
parser.add_argument('--owned-before', choices=('yes', 'no'), help='--post-only: did the E32 control the boiler before?')
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
if args.post_only and args.preinstall:
    parser.error('--post-only is for an install without a pre-install capture; drop --preinstall')
if not args.post_only and not args.preinstall:
    parser.error('--preinstall <pre folder> is required (or --post-only for an install without one)')
if not args.post_only and (args.history_since or args.pre_backup or args.pre_backup_at or args.owned_before):
    parser.error('--history-since, --pre-backup, --pre-backup-at and --owned-before belong to --post-only')
if args.pre_backup_at and not args.pre_backup:
    parser.error('--pre-backup-at needs --pre-backup')
cfg = acc.load_config(args)
for option, value in (('--history-since', args.history_since), ('--pre-backup-at', args.pre_backup_at)):
    if value:
        try:
            acc.stamp(value)
        except ValueError:
            parser.error(f'{option} must be a UTC time like 2026-11-08T09:00:00Z')

if args.dry_run:
    acc.dry_run('capture_post.py' + (' --post-only' if args.post_only else ''), [
        (f'verify {args.preinstall}/CAPTURE-MANIFEST.json and its ha-baseline manifest' if not args.post_only else
         f'read {args.pre_backup} (an E32 settings export from before the install)' if args.pre_backup else
         'read no pre-install capture (there is none)'),
        'resolve the E32 password (' + ('factory default' if args.factory_password else f'{acc.E32_PASSWORD_ENV} or a prompt')
        + ') and the MQTT login (' + ('none: --no-mqtt' if args.no_mqtt
                                      else f'--mqtt-user / {acc.MQTT_USER_ENV}, {acc.MQTT_PASSWORD_ENV} or a prompt') + ') first',
        'refuse a non-empty --out folder',
        f'GitHub GET api.github.com/repos/{cfg.repository}/releases/tags/{cfg.tag}',
        'GitHub GET e32v2-update.json and firmware.bin (only when not in the cache folder yet)',
        'HA GET /api/config, /api/states/<update entity>, /api/config/config_entries/entry?domain=open_thermostat, '
        '/api/diagnostics/config_entry/<entry id>, /api/states',
        f'HA GET /api/history/period/<{"--history-since" if args.post_only else "pre-install end"}>'
        f'?filter_entity_id={cfg.entity_id}&significant_changes_only=0',
        'HA GET /api/history/period/<same time>?filter_entity_id=<heat-request sensor> (when HA has one)',
        f'E32 GET {cfg.e32_url}/auth/session (401), POST /auth/login once, GET /auth/session',
        'E32 GET /status/version, /updates/status, /status, /status/logs, /status/heating, /auth/session',
        'E32 GET ' + ', '.join(acc.SETTINGS_ROUTES) + ' and /config/programs/<each program>',
        'E32 POST /config/backup {"action":"export"} (no passphrase; 403 with the factory password is recorded)',
        'E32 POST /auth/logout (also after an error)',
        ('no MQTT' if args.no_mqtt else f'MQTT subscribe {cfg.mqtt_prefix}/# on {cfg.mqtt_host}:{cfg.mqtt_port} for '
         f'{args.listen} s (read-only, login on the listener\'s stdin)')],
        [f'release {cfg.previous_tag} -> {cfg.tag}, integration {cfg.ha_previous_version} -> {cfg.ha_version}'],
        token_file=args.token_file)

post_only = args.post_only
pre = pre_summary = base_dir = baseline = pre_entries = pre_export = None
if not post_only:
    pre = Path(args.preinstall).resolve()
    acc.verify_manifest(pre, 'CAPTURE-MANIFEST.json')
    pre_summary = json.loads((pre / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
    if pre_summary.get('kind') != 'installer_preinstall_capture' or pre_summary.get('tag') != cfg.tag:
        raise SystemExit(f'{pre} is not a ready pre-install capture for {cfg.tag} (kind {pre_summary.get("kind")})')
    base_dir = Path(pre_summary['baseline']['folder'])
    acc.verify_manifest(base_dir, 'CAPTURE-MANIFEST.json')
    assert acc.file_digest(base_dir / 'CAPTURE-MANIFEST.json') == pre_summary['baseline']['manifest_sha256'], 'baseline changed'
    baseline = json.loads((base_dir / 'CAPTURE-SUMMARY.json').read_text(encoding='utf-8'))
    pre_entries = json.loads((pre / 'backup' / 'BACKUP-MANIFEST.json').read_text(encoding='utf-8'))['files']
elif args.pre_backup:
    pre_export = acc.export_document(Path(args.pre_backup).read_bytes())
    if pre_export is None:
        raise SystemExit(f'{args.pre_backup} is not an E32 settings export (format openthermostat-e32-backup, schema 1)')
password = acc.e32_password(args.factory_password)  # secrets before any network: no half runs
credentials = acc.mqtt_credentials(args, cfg)
out = acc.new_folder(args.out)
cache = Path(args.cache).resolve() if args.cache else (pre.parent if pre else out.parent) / 'release-cache'
cache.mkdir(parents=True, exist_ok=True)
findings, info, gaps, substitutes = [], {}, [], {}
owned = pre_summary['e32_before']['owned_boiler'] if pre_summary else {'yes': True, 'no': False}.get(args.owned_before)


def check(name, ok, detail=None):
    findings.append({'check': name, 'ok': bool(ok), 'detail': detail})
    return bool(ok)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else None


if post_only:
    gaps.append('No pre-install capture: nothing from before the install is known except what is named below.')
    for name, value in (('history_since', args.history_since), ('pre_backup', args.pre_backup),
                        ('owned_before', args.owned_before)):
        if value:
            substitutes[name] = value
    if args.pre_backup:
        substitutes['pre_backup_sha256'] = acc.file_digest(args.pre_backup)
        substitutes['pre_backup_at'] = args.pre_backup_at or pre_export.get('created')

# 1. GitHub: the release and its assets.
raw_release, github_release = acc.release(cfg, cfg.tag, record=out / 'github-release-raw.json')
public, image, descriptor, files_ok = acc.release_files(raw_release, cache, github_release)
if pre_summary:
    check('github.release_is_the_capture_one', github_release == pre_summary['github_release'],
          {'now': github_release, 'preinstall': pre_summary['github_release']})
else:
    check('github.release_is_published', acc.release_published(cfg, github_release), github_release)
check('github.firmware_digest_and_size', files_ok and len(image) == github_release['asset']['size'],
      {'sha256': acc.digest(image), 'bytes': len(image)})
# The descriptor's version field holds the IDF string (Arduino build); the release marker is the build marker.
check('github.descriptor', descriptor['magic'] == '0xabcd5432'
      and ('OT_E32V2_OTA_V1:' + cfg.tag + ':' + str(public.get('source_commit')) + ':').encode() in image, descriptor)

# 2. Home Assistant (GET only, LAN address).
token = acc.ha_token(args.token_file)
snapshot = acc.ha_snapshot(cfg, token, out / 'ha')
entity = snapshot['entity']
since = pre_summary['finished_at_utc'] if pre_summary else args.history_since
history = acc.ha_history(cfg, token, cfg.entity_id, since, record=out / 'ha' / 'update-entity-history.json') if since else None
states = (history[0] if history else []) if since else []
progress_starts, previous, starts = 0, False, set()
offered_before = None  # post-only: the recorder shows the entity offering this tag before the install started
for state in states:
    attributes = state.get('attributes') or {}
    running = attributes.get('in_progress') not in (None, False, 0)
    progress_starts += running and not previous
    previous = running
    last = attributes.get('last_install') or {}
    if last.get('started_at') and last['started_at'] >= since:
        starts.add(last['started_at'])
install_actions = max(progress_starts, len(starts)) if since else None
last = entity['last_install'] or {}
if post_only and since:
    offered_before = any((s.get('attributes') or {}).get('latest_version') == cfg.tag
                         and (s.get('attributes') or {}).get('installed_version') == cfg.previous_tag
                         and (s.get('last_changed') or s.get('last_updated') or '') < (last.get('started_at') or '')
                         for s in states)
now_states = load(out / 'ha' / 'states-reduced.json')['entities']
now_diag = snapshot['diagnostics']
check('ha.integration_version', snapshot['integration_version'] == cfg.ha_version, snapshot['integration_version'])
if pre_summary:
    base_states = load(base_dir / 'ha' / 'states-reduced.json')['entities']
    pre_states = load(pre / 'ha' / 'states-reduced.json')['entities']
    changes_base = acc.entity_changes(base_states, now_states, load(base_dir / 'ha' / 'diagnostics-extract.json'), now_diag)
    changes_pre = acc.entity_changes(pre_states, now_states, load(pre / 'ha' / 'diagnostics-extract.json'), now_diag)
    check('ha.single_config_entry', acc.single_entry({'config_entries': baseline['ha']['config_entries']}, snapshot),
          {'baseline': baseline['ha']['config_entries'], 'now': snapshot['config_entries']})
    check('ha.no_new_duplicate_or_stale_entities', changes_base['ok'] and changes_pre['ok'],
          {'since_baseline': changes_base, 'since_preinstall': {k: changes_pre[k] for k in (
              'new_duplicate_ids', 'new_stale_ids', 'new_possible_duplicate_groups')}})
else:
    check('ha.single_config_entry', acc.one_loaded_entry(snapshot), {'now': snapshot['config_entries']})
    gaps.append('No Home Assistant baseline: new duplicate or stale entities cannot be told from old ones.')
check('ha.entity_reports_new_version', entity['installed_version'] == cfg.tag and entity['state'] == 'off',
      {k: entity[k] for k in ('state', 'installed_version', 'latest_version', 'in_progress')})
check('ha.install_actions==1', install_actions == 1,
      {'in_progress_starts': progress_starts, 'last_install_starts': sorted(starts), 'history_states': len(states),
       'since': since})
install_ok = (last.get('result') == 'installed' and last.get('uploads') == 1 and last.get('tag') == cfg.tag
              and last.get('from_version') == cfg.previous_tag and last.get('sha256') == acc.digest(image)
              and last.get('size') == len(image) and isinstance(last.get('duration_s'), (int, float))
              and 0 < last['duration_s'] <= 900
              and github_release['published_at'] <= last.get('started_at', '') <= last.get('finished_at', ''))
if since:
    install_ok = install_ok and last.get('started_at', '') >= since
check('ha.last_install', install_ok, last)
if post_only:
    check('ha.offered_before_install', offered_before is True,
          'the recorder history shows the entity offering this tag before the install' if offered_before
          else 'not shown by the recorder history (give --history-since from before the install)')
control_history = []
for sensor in snapshot['control_sensors']:
    rows = acc.ha_history(cfg, token, sensor['entity_id'], since) if since else None
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
if post_only and not since:
    gaps.append('No --history-since: install actions, the offer before the install and the control phases after '
                'it cannot be read from the recorder.')

# 3. The E32 (one session, always logged out): identity, health, active control, password, learned, settings.
e, client = acc.e32(cfg, out, 'post-session.cookies', password)
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
      version.get('version') == public.get('version') == cfg.tag and version.get('source') == public.get('source_commit')
      and version.get('web_sha256') == public.get('web_sha256') and version.get('sha256') == descriptor['elf_sha256']
      and reported == {'version': cfg.tag, 'source_commit': version.get('source'), 'web_sha256': version.get('web_sha256'),
                       'elf_sha256': version.get('sha256')}
      and updates.get('build_marker') == f'OT_E32V2_OTA_V1:{cfg.tag}:{version.get("source")}:{version.get("web_sha256")}:END',
      {'version': version, 'public': public, 'descriptor_elf': descriptor['elf_sha256'], 'reported': reported})
check('e32.boot_confirmed', updates.get('boot_pending') is False and updates.get('reboot_required') is False
      and not updates.get('busy'), {k: updates.get(k) for k in ('boot_pending', 'reboot_required', 'busy', 'phase')})
since_install = (acc.stamp(at) - acc.stamp(last['started_at'])).total_seconds() if last.get('started_at') else None
check('e32.new_boot_after_install', since_install is not None and isinstance(uptime, int)
      and uptime <= since_install + 5 and last.get('from_version') == cfg.previous_tag,
      {'uptime_seconds': uptime, 'seconds_since_install_start': since_install})
control = acc.control_state(heating, owned if owned is not None else False)
if owned is None:
    control = {**control, 'ok': False}
    gaps.append('Not known whether the E32 controlled the boiler before the update (--owned-before): the control '
                'state cannot be called safe.')
check('e32.control_state_safe', control['ok'], {**control, 'owned_before_update': owned})
if pre_summary:
    differences, compare_notes = acc.compare_settings(pre / 'backup', out / 'settings', pre_entries)
    check('e32.settings_programs_bindings_preserved',
          *acc.settings_finding(differences, compare_notes, export, access['default_password']))
elif pre_export is not None:
    # Only the export can be compared: it holds the settings, programs and bindings, not every route.
    after_export = acc.export_document((out / 'settings' / 'config-backup-export.json').read_bytes()) \
        if export.get('compared') else None
    differences = acc.compare_export(pre_export, after_export) if after_export else []
    compare_notes = {'export_compared': after_export is not None, 'substitute': 'pre_backup',
                     'pre_backup_created': pre_export.get('created')}
    check('e32.settings_programs_bindings_preserved',
          *acc.settings_finding(differences, compare_notes, export, access['default_password']))
    gaps.append('Settings were compared with the named export only, not with every settings route.')
else:
    differences, compare_notes = [], {}
    gaps.append('No settings backup from before the install: nothing to compare the settings with.')
summary = acc.learned_summary(heating)
learned_before = pre_summary['e32_before']['learned'] if pre_summary else None
info['learned'] = {'summary': summary, 'fresh': acc.learned_fresh(summary), 'before_update': learned_before,
                   'kept_over_update': acc.learned_kept(learned_before, summary)}
info['password'] = {**access, 'before_update': pre_summary['e32_before']['password'] if pre_summary else None}
observation = {'at_utc': at, 'version': version.get('version'), 'boot_pending': updates.get('boot_pending'),
               'uptime_seconds': uptime, 'mqtt_counters': {k: runtime.get(k) for k in runtime if k.startswith('mqtt_')},
               'control_phase': control['phase'], 'default_password': access['default_password'],
               'export_http_status': export['http_status'], 'logout_http_status': logged_out}
boot = acc.boot_instant(at, uptime)
observation['boot_at_utc'] = boot.strftime('%Y-%m-%dT%H:%M:%SZ') if boot else None

# 4. MQTT: availability, heartbeat and the active block (read-only listener; credentials stay in the pipe).
mqtt_names = ('availability_online', 'heartbeat_every_60s', 'heartbeat_counters_steady', 'heartbeat_uptime_rising',
              'boiler_fields_seen')
if credentials is None:
    for name in mqtt_names:
        check('mqtt.' + name, False, 'not run (--no-mqtt)')
else:
    text = acc.mqtt_listen(cfg, credentials, args.listen)
    del credentials
    (out / 'mqtt').mkdir(exist_ok=True)
    (out / 'mqtt' / 'listen.txt').write_bytes(text)
    result = acc.mqtt_evaluate(acc.parse_mqtt(text.decode('utf-8', 'replace')), args.listen)
    for name in mqtt_names:
        check('mqtt.' + name, result[name], result['detail'] if name != 'boiler_fields_seen' else result['detail']['messages'])
    info['mqtt_state_heating_active'] = result['detail']['state_heating_active']

failed = [f['check'] for f in findings if not f['ok']]
acc.save(out / 'OBSERVATION.json', {'schema': 1, 'kind': 'installer_post_observation', 'tag': cfg.tag,
                                    'config': cfg.as_dict(), 'mode': 'post_only' if post_only else 'full',
                                    'preinstall': str(pre) if pre else None, 'gaps': gaps, 'substitutes': substitutes,
                                    'observation': observation, 'install_actions': install_actions,
                                    'offered_before_install': offered_before,
                                    'ha_entity': entity, 'ha_core_version': snapshot['ha_core_version'],
                                    'ha_integration_version': snapshot['integration_version'],
                                    'ha_config_entries': snapshot['config_entries'], 'github_release': github_release,
                                    'public_manifest': public, 'firmware_descriptor': descriptor,
                                    'firmware_sha256': acc.digest(image), 'firmware_bytes': len(image),
                                    'control': control, 'owned_before': owned, 'settings_differences': differences,
                                    'export': export, 'info': info, 'findings': findings, 'failed': failed})
sha = acc.write_manifest(out, 'OBS-MANIFEST.json', 'installer_post_observation')
print(json.dumps({'out': str(out), 'mode': 'post_only' if post_only else 'full', 'observation': observation,
                  'failed': failed, 'gaps': gaps, 'obs_manifest_sha256': sha, 'ha_issues': info['ha_issues'],
                  'learned_fresh': info['learned']['fresh'], 'learned_kept': info['learned']['kept_over_update']},
                 indent=1))
sys.exit(0 if not failed else 2)
