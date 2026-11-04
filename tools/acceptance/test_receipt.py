"""Offline tests for the acceptance kit: no E32, no Home Assistant, no GitHub, no MQTT.

Builds fixture capture folders shaped exactly like capture_preinstall.py (both stages), capture_post.py (also
--post-only) and capture_independent.py write them -- the E32, HA and MQTT verdicts are computed with
acceptance's own evaluators on synthetic documents -- then runs write_receipt.py and proves that a PASS receipt
passes verify_e32_update_gate.py's home_assistant checks (METHODS['home_assistant'] and verify() on a throwaway
root, and verify_accepted_update_path.accepted_source), and that every gap leaves the receipt INCOMPLETE. The
verifier is imported read-only from the repository this kit lives in: its source is compiled in memory, nothing
is written there.

Run: python -I -m unittest discover -s tools/acceptance -p "test_*.py"   (OT_ACCEPTANCE_REPO overrides the repository)
"""
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import acceptance as acc  # noqa: E402
import write_receipt as writer  # noqa: E402

WORKTREE = Path(os.environ.get('OT_ACCEPTANCE_REPO', str(acc.REPO)))
VERIFIER = WORKTREE / 'scripts' / 'verify_e32_update_gate.py'
H = lambda seed: hashlib.sha256(seed.encode()).hexdigest()
SOURCE, WEB, ELF, FW = H('source')[:40], H('web'), H('elf'), H('firmware')
FW_BYTES = 2831000
ENTRY = '01JC0FFEE0000000000000000A'
PUBLISHED, STARTED, FINISHED = '2026-11-08T08:50:00Z', '2026-11-08T09:10:05Z', '2026-11-08T09:11:30Z'
# The E32 booted at 09:10:20 (post 1 at 09:14:10 has an uptime of 230 s, post 2 at 09:24:00 one of 820 s).
AT1, AT2 = '2026-11-08T09:14:10Z', '2026-11-08T09:24:00Z'
SETTINGS_BASE = {'mqtt_port': 1883, 'mqtt_prefix': 'ib-therm', 'repository': 'dielessen/open_thermostat',
                 'hacs_repository': 'dielessen/openthermostat-ha', 'wsl_python': '~/venvs/ha/bin/python',
                 'entity_id': 'update.test_e32_firmware', 'ha_url': 'https://192.168.1.10:8123',
                 'e32_url': 'http://192.168.1.20', 'mqtt_host': '192.168.1.10'}
CFG = acc.Config({**SETTINGS_BASE, 'tag': 'v1.0.0-e32v2-rc.4', 'previous_tag': 'v1.0.0-e32v2-rc.3',
                  'ha_version': '1.0.0rc5', 'ha_previous_version': '1.0.0rc4'})
STABLE = acc.Config({**SETTINGS_BASE, 'tag': 'v1.0.0-e32v2', 'previous_tag': 'v1.0.0-e32v2-rc.4',
                     'ha_version': '1.0.0', 'ha_previous_version': '1.0.0rc5'})


def release(cfg=CFG):
    return {'tag_name': cfg.tag, 'draft': False, 'prerelease': cfg.expect_prerelease, 'published_at': PUBLISHED,
            'asset': {'name': 'firmware.bin', 'size': FW_BYTES, 'digest': 'sha256:' + FW}}


def last_install(cfg=CFG, uploads=1):
    return {'tag': cfg.tag, 'from_version': cfg.previous_tag, 'sha256': FW, 'size': FW_BYTES, 'started_at': STARTED,
            'finished_at': FINISHED, 'duration_s': 85.2, 'result': 'installed', 'uploads': uploads,
            'reported': {'version': cfg.tag, 'source_commit': SOURCE, 'web_sha256': WEB, 'elf_sha256': ELF}}


def states(extra=()):
    base = [('update.test_e32_firmware', 'off', False),
            ('climate.woonkamer', 'heat', False), ('sensor.woonkamer_e32_heat_request', '42', False),
            ('sensor.badkamer_temperatuur', '21.2', False), ('switch.hacs_pre_release', 'on', False)]
    return [{'entity_id': i, 'state': s, 'attributes': {'restored': True} if r else {}} for i, s, r in [*base, *extra]]


def diagnostics(version, duplicates=(), issues=(), previous=CFG.previous_tag):
    return {'home_assistant': {'version': '2026.10.4'},
            'custom_components': {'open_thermostat': {'version': version}, 'hacs': {'version': '2.0.5'}},
            'integration_manifest': {'domain': 'open_thermostat', 'version': version},
            'data': {'e32': {'entities': {'total': 120, 'devices': 4, 'possible_duplicates': list(duplicates),
                                          'disabled': [], 'unavailable': []},
                             'firmware': {'installed_version': previous}}},
            'issues': [{'issue_id': i, 'domain': 'open_thermostat'} for i in issues]}


def entries(count=1, entry_state='loaded'):
    return [{'entry_id': ENTRY if n == 0 else ENTRY[:-1] + 'B', 'domain': 'open_thermostat', 'title': 'Woonkamer',
             'state': entry_state, 'disabled_by': None} for n in range(count)]


def active(phase):
    common = {'last_sent': None, 'foreign_controller': None, 'warnings': [], 'enabled': True,
              'boiler_limit': {'flow_c': 55, 'age_s': 40, 'reads': 2}}
    if phase == 'before_active':
        return {**common, 'state': 'active', 'awaiting_confirmation': False,
                'command': {'send': True, 'flow_c': 41, 'why': 'heating'}, 'confirmation': {'age_s': 90000, 'restored': False},
                'confirmation_stored': True}
    if phase == 'awaiting':
        return {**common, 'state': 'awaiting_confirmation', 'awaiting_confirmation': True, 'reconfirm_required': True,
                'command': {'send': False, 'flow_c': 0, 'why': 'awaiting_confirmation'}, 'confirmation': None,
                'confirmation_stored': False, 'reconfirm_stored': True, 'taken_over_before': True}
    if phase == 'frost':
        return {**active('awaiting'), 'command': {'send': True, 'flow_c': 30, 'why': 'frost_unconfirmed'}}
    if phase == 'reconfirmed':
        return {**common, 'state': 'active', 'awaiting_confirmation': False, 'reconfirm_required': False,
                'command': {'send': True, 'flow_c': 43, 'why': 'heating'}, 'confirmation': {'age_s': 400, 'restored': False},
                'confirmation_stored': True, 'reconfirm_stored': False, 'taken_over_before': True}
    if phase == 'foreign':
        return {**active('awaiting'), 'reconfirm_required': False, 'state': 'blocked_foreign_controller',
                'warnings': ['foreign_controller'], 'reconfirm_stored': False}
    raise ValueError(phase)


def heating(phase, fresh=True):
    learned = {'schema': 1, 'applied': False, 'status': 'collecting', 'heating_periods': 0 if fresh else 14,
               'rooms': [{'id': 'woonkamer', 'readiness': 'collecting', 'segments': 0, 'periods': 0 if fresh else 9}]}
    tuning = {'state': 'waiting', 'values': {}, 'manual': [], 'yesterday': None if fresh else {'starts': 9},
              'today': {'starts': 1, 'heating_h': 1}, 'would': [], 'log': [] if fresh else [[1, 'rest', 1, 2, 'x', 1, '']]}
    return {'schema': 1, 'mode': 'active', 'revision': 7, 'active': active(phase), 'learned': learned, 'tuning': tuning}


SETTINGS = {'config-rooms.json': {'rooms': [{'id': 1, 'name': 'Woonkamer'}]}, 'config-wifi.json': {'ssid': 'thuis'},
            'config-boiler.json': {'max_flow': 55}, 'config-boiler-display.json': {'model': 'nefit'},
            'config-hardware.json': {'board': 'e32v2'}, 'config-debug.json': {'level': 1},
            'config-logging.json': {'syslog': False}, 'config-program-current.json': {'name': 'week'},
            'status-programs.json': ['week'], 'program-000.json': {'name': 'week', 'days': [1, 2, 3]},
            'config-bluetooth.json': {'devices': [{'address': 'a4:c1', 'name': 'bad', 'last_seen': 3}]},
            'config-heating.json': {'schema': 1, 'revision': 7, 'mode': 'active', 'minimum_flow_c': 30, 'rooms': [{'id': 'woonkamer'}]}}
EXPORT = {'format': 'openthermostat-e32-backup', 'schema': 1, 'firmware': CFG.previous_tag, 'created': '2026-11-08T09:00:00Z',
          'secrets': None, 'not_included': ['wifi_password', 'web_password'], 'heating': {'mode': 'active'},
          'bluetooth': {'devices': [{'address': 'a4:c1', 'name': 'bad'}]}}


def write_settings(folder, cfg=CFG, after=False, export=True):
    """The settings documents as the E32 returns them; `after`: schema additions and a new plan revision."""
    entries_ = []
    for name, value in SETTINGS.items():
        value = json.loads(json.dumps(value))
        if after and name == 'config-heating.json':
            value.update(revision=9, features=['levels'])  # device-local history + what the firmware can
        if after and name == 'config-bluetooth.json':
            value['devices'][0]['last_seen'] = 99  # volatile runtime value
        raw = (json.dumps(value) + '\n').encode()
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(raw)
        entries_.append({'path': '/' + name, 'file': name, 'http_status': 200, 'sha256': acc.digest(raw), 'bytes': len(raw)})
    if export:
        value = {**EXPORT, **({'firmware': cfg.tag, 'learned': {'state': 'abcd'}} if after else {})}
        raw = (json.dumps(value) + '\n').encode()
        (folder / 'config-backup-export.json').write_bytes(raw)
        entries_.append({'path': 'POST /config/backup {"action":"export"}', 'file': 'config-backup-export.json',
                         'http_status': 200, 'sha256': acc.digest(raw), 'bytes': len(raw)})
    return entries_


def mqtt_text(listen=150, beats=(36.9, 96.9), disconnects=((0, 0), (0, 0)), online=True, uptime0=700):
    lines = ['connected Success', '   0.0 R ib-therm/v1/fw/availability 6B ' + ('online' if online else 'offline'),
             '   0.0 R ib-therm/v1/fw/state/boiler_fields/flow_c 4B 41.5',
             '   0.0 R ib-therm/v1/fw/state/heating 90B ' + json.dumps({'schema': 1, 'active': {'state': 'active'}})]
    for n, (t, (stalled, socket)) in enumerate(zip(beats, disconnects)):
        payload = json.dumps({'schema': 1, 'uptime_s': uptime0 + 60 * n, 'mqtt': {'disconnects': {'stalled': stalled,
                                                                                                'socket_error': socket}}})
        lines.append(f'{t:6.1f} - ib-therm/v1/fw/heartbeat {len(payload)}B {payload}')
    return '\n'.join(lines) + '\n'


MQTT_NAMES = ('availability_online', 'heartbeat_every_60s', 'heartbeat_counters_steady', 'heartbeat_uptime_rising',
              'boiler_fields_seen')


class Fixture:
    """One complete set of capture folders; keyword arguments switch single pieces of evidence."""

    def __init__(self, root, cfg=CFG, **kw):
        self.root, self.cfg, self.kw = Path(root), cfg, kw
        self.base, self.pre = self.root / 'ha-baseline', self.root / 'preinstall'
        self.obs = [self.root / 'post1', self.root / 'post2']
        self.ind, self.ci = self.root / 'independent', self.root / 'ci.json'
        self.build()

    def get(self, key, default):
        return self.kw.get(key, default)

    def build(self):
        k, cfg = self.get, self.cfg
        # Stage ha-baseline: the previous integration, one entry; no E32 contact.
        self.base.mkdir(parents=True)
        base_states = acc.reduce_states(states())
        acc.save(self.base / 'ha' / 'states-reduced.json', {'sha256': H('s0'), 'bytes': 1, 'count': len(base_states),
                                                           'entities': base_states})
        base_diag = {**acc.diagnostics_extract(diagnostics(k('baseline_version', cfg.ha_previous_version))),
                     'sha256': H('d0'), 'bytes': 1}
        acc.save(self.base / 'ha' / 'diagnostics-extract.json', base_diag)
        base_entries = acc.entries_summary(entries())
        acc.save(self.base / 'CAPTURE-SUMMARY.json', {
            'schema': 1, 'kind': 'ha_baseline_capture', 'tag': cfg.tag, 'finished_at_utc': '2026-11-08T08:55:00Z',
            'ha': {'ha_integration_version': acc.integration_version(base_diag), 'config_entries': base_entries},
            'notes': [], 'ready_for_ha_upgrade': True})
        acc.write_manifest(self.base, 'CAPTURE-MANIFEST.json', 'ha_baseline_capture')

        # Stage e32: the new integration after the upgrade, the E32 still on the previous tag in active control.
        self.pre.mkdir()
        pre_extra = k('pre_extra_states', ())
        pre_states = acc.reduce_states(states(pre_extra))
        acc.save(self.pre / 'ha' / 'states-reduced.json', {'sha256': H('s1'), 'bytes': 1, 'count': len(pre_states),
                                                          'entities': pre_states})
        pre_diag = {**acc.diagnostics_extract(diagnostics(cfg.ha_version, issues=['e32_default_password_' + ENTRY])),
                    'sha256': H('d1'), 'bytes': 1}
        acc.save(self.pre / 'ha' / 'diagnostics-extract.json', pre_diag)
        pre_entries = acc.entries_summary(entries(k('pre_entry_count', 1)))
        upgrade = {'baseline_integration_version': cfg.ha_previous_version,
                   'integration_version': acc.integration_version(pre_diag),
                   'single_entry_kept': acc.single_entry({'config_entries': base_entries}, {'config_entries': pre_entries}),
                   'entities': acc.entity_changes(base_states, pre_states, base_diag, pre_diag)}
        backup = write_settings(self.pre / 'backup', cfg)
        acc.save(self.pre / 'backup' / 'BACKUP-MANIFEST.json', {'schema': 1, 'files': backup})
        pre_heating = heating('before_active', fresh=False)
        acc.save(self.pre / 'e32' / 'heating.json', pre_heating)
        acc.save(self.pre / 'CAPTURE-SUMMARY.json', {
            'schema': 1, 'kind': 'installer_preinstall_capture', 'tag': cfg.tag, 'finished_at_utc': '2026-11-08T09:05:00Z',
            'baseline': {'folder': str(self.base), 'manifest_sha256': acc.file_digest(self.base / 'CAPTURE-MANIFEST.json'),
                         'finished_at_utc': '2026-11-08T08:55:00Z'},
            'github_release': release(cfg),
            'ha_before': {'ha_entity_id': cfg.entity_id, 'ha_installed_version_before': cfg.previous_tag,
                          'ha_latest_version_before': k('latest_before', cfg.tag), 'ha_integration_version': cfg.ha_version,
                          'config_entries': pre_entries},
            'ha_upgrade': upgrade,
            'e32_before': {'version': cfg.previous_tag, 'owned_boiler': acc.owned_before(pre_heating),
                           'password': {'default_password': True, 'reported': True},
                           'learned': acc.learned_summary(pre_heating)},
            'backup_manifest_sha256': acc.file_digest(self.pre / 'backup' / 'BACKUP-MANIFEST.json'),
            'notes': [], 'ready_to_install': True})
        acc.write_manifest(self.pre, 'CAPTURE-MANIFEST.json', 'installer_preinstall_capture')

        # Two post observations: post 1 before the password change and re-confirmation, post 2 after them.
        runs = [dict(at=k('at1', AT1), uptime=k('uptime1', 230), phase=k('phase1', 'awaiting'), default=True,
                     export=False, fresh=k('fresh', False)),
                dict(at=k('at2', AT2), uptime=k('uptime2', 820), phase=k('phase2', 'reconfirmed'),
                     default=k('default_end', False), export=k('export2', True), fresh=k('fresh', False))]
        for folder, run in zip(self.obs, runs):
            self.observation(folder, run, base_states, base_diag, pre_states, pre_diag, base_entries, backup)
        self.independent(with_backup_comparison=True)

    def independent(self, with_backup_comparison):
        k, cfg = self.get, self.cfg
        self.ind.mkdir()
        (self.ind / 'e32').mkdir()
        (self.ind / 'e32' / 'version.json').write_text(json.dumps({'version': cfg.tag, 'source': SOURCE}))
        ind_checks = {'release_published': True, 'identity_matches_public_release': True, 'boot_confirmed': True,
                      'control_state_safe': True, 'takeover_reconfirmed': k('ind_takeover', True),
                      'ha_reports_new_version': True, 'ha_last_install_matches_e32': True,
                      'ha_one_config_entry': True, 'ha_integration_version': True}
        if with_backup_comparison:
            ind_checks.update(settings_same_as_preinstall_backup=True, settings_detail={})
        acc.save(self.ind / 'INDEPENDENT-SUMMARY.json', {
            'schema': 1, 'kind': 'independent_postcheck', 'tag': cfg.tag, 'at_utc': '2026-11-08T09:27:00Z',
            'e32': {'control_phase': 'taken_over', 'default_password': k('default_end', False)},
            'checks': ind_checks, 'passed': all(v is True for n, v in ind_checks.items() if n != 'settings_detail')})
        files = sorted(p for p in self.ind.rglob('*') if p.is_file())
        acc.save(self.ind / 'INDEPENDENT-MANIFEST.json', {'schema': 1, 'kind': 'independent_postcheck', 'files': [
            {'file': p.relative_to(self.ind).as_posix(), 'sha256': acc.file_digest(p)} for p in files]})
        acc.save(self.ci, {'commit': SOURCE, 'runs': [{'id': 1, 'name': 'PlatformIO CI', 'head_branch': cfg.tag,
                                                      'event': 'push', 'status': 'completed',
                                                      'conclusion': k('ci', 'success'), 'html_url': 'x',
                                                      'created_at': '2026-11-08T08:30:00Z'}]})

    def mqtt_findings(self, check, folder):
        k = self.get
        text = mqtt_text(disconnects=k('disconnects', ((0, 0), (0, 0))), uptime0=k('beat_uptime0', 700),
                         beats=k('beats', (36.9, 96.9)))
        (folder / 'mqtt').mkdir()
        (folder / 'mqtt' / 'listen.txt').write_text(text)
        mqtt = acc.mqtt_evaluate(acc.parse_mqtt(text), 150)
        for name in MQTT_NAMES:
            check('mqtt.' + name, mqtt[name])

    def observation(self, folder, run, base_states, base_diag, pre_states, pre_diag, base_entries, backup):
        k, cfg = self.get, self.cfg
        folder.mkdir()
        findings = []
        check = lambda name, ok, detail=None: findings.append({'check': name, 'ok': bool(ok), 'detail': detail})
        for name in ('github.release_is_the_capture_one', 'github.firmware_digest_and_size', 'github.descriptor'):
            check(name, True)
        now_states = acc.reduce_states(states(k('post_extra_states', ())))
        now_diag = {**acc.diagnostics_extract(diagnostics(k('post_version', cfg.ha_version), k('post_dup_groups', ()))),
                    'sha256': H('d2'), 'bytes': 1}
        now_entries = acc.entries_summary(entries(k('post_entry_count', 1)))
        check('ha.integration_version', acc.integration_version(now_diag) == cfg.ha_version)
        check('ha.single_config_entry', acc.single_entry({'config_entries': base_entries}, {'config_entries': now_entries}))
        check('ha.no_new_duplicate_or_stale_entities',
              acc.entity_changes(base_states, now_states, base_diag, now_diag)['ok']
              and acc.entity_changes(pre_states, now_states, pre_diag, now_diag)['ok'])
        check('ha.entity_reports_new_version', True)
        actions = k('install_actions', 1)
        check('ha.install_actions==1', actions == 1)
        check('ha.last_install', True)
        check('e32.version_source_elf_web_exact', True)
        check('e32.boot_confirmed', True)
        check('e32.new_boot_after_install', True)
        doc = heating(run['phase'], fresh=run['fresh'])
        control = acc.control_state(doc, True)
        check('e32.control_state_safe', control['ok'], control)
        write_settings(folder / 'settings', cfg, after=True, export=run['export'])
        if k('settings_change', False):
            (folder / 'settings' / 'config-boiler.json').write_text(json.dumps({'max_flow': 75}) + '\n')
        export = ({'http_status': 200, 'compared': True, 'refusal': None} if run['export'] else
                  {'http_status': 403, 'compared': False, 'refusal': 'password_change_required'})
        differences, notes = acc.compare_settings(self.pre / 'backup', folder / 'settings', backup)
        check('e32.settings_programs_bindings_preserved', *acc.settings_finding(differences, notes, export, run['default']))
        self.mqtt_findings(check, folder)
        summary = acc.learned_summary(doc)
        before = acc.learned_summary(heating('before_active', fresh=False))
        boot = acc.boot_instant(run['at'], run['uptime'])
        acc.save(folder / 'OBSERVATION.json', {
            'schema': 1, 'kind': 'installer_post_observation', 'tag': cfg.tag, 'config': cfg.as_dict(), 'mode': 'full',
            'preinstall': str(self.pre), 'gaps': [], 'substitutes': {},
            'observation': {'at_utc': run['at'], 'version': cfg.tag, 'boot_pending': False, 'uptime_seconds': run['uptime'],
                            'boot_at_utc': boot.strftime('%Y-%m-%dT%H:%M:%SZ'),
                            'mqtt_counters': {'mqtt_stalled_disconnects': 0, 'mqtt_socket_error_disconnects': 0},
                            'control_phase': control['phase'], 'default_password': run['default'],
                            'export_http_status': export['http_status'], 'logout_http_status': 200},
            'install_actions': actions, 'offered_before_install': None,
            'ha_entity': {'entity_id': cfg.entity_id, 'state': 'off', 'installed_version': cfg.tag, 'latest_version': cfg.tag,
                          'in_progress': False, 'last_install': last_install(cfg, k('uploads', 1))},
            'ha_core_version': '2026.10.4', 'ha_integration_version': acc.integration_version(now_diag),
            'ha_config_entries': now_entries, 'github_release': release(cfg), 'firmware_sha256': FW, 'firmware_bytes': FW_BYTES,
            'control': control, 'owned_before': True, 'export': export,
            'info': {'learned': {'summary': summary, 'fresh': acc.learned_fresh(summary), 'before_update': before,
                                 'kept_over_update': acc.learned_kept(before, summary)},
                     'ha_issues': acc.issue_flags(now_diag), 'ha_control_history': k('control_history', [])},
            'findings': findings, 'failed': [f['check'] for f in findings if not f['ok']]})
        acc.write_manifest(folder, 'OBS-MANIFEST.json', 'installer_post_observation')

    def receipt(self):
        ci = json.loads(self.ci.read_text())
        return writer.build(self.cfg, self.pre, self.obs, self.ind, ci)


class PostOnlyFixture(Fixture):
    """An install without a pre-install capture: observations made with capture_post.py --post-only."""

    def __init__(self, root, cfg=CFG, **kw):
        self.root, self.cfg, self.kw = Path(root), cfg, kw
        self.obs = [self.root / 'post1', self.root / 'post2']
        self.ind, self.ci = self.root / 'independent', self.root / 'ci.json'
        self.root.mkdir(parents=True, exist_ok=True)
        self.backup_file = self.root / 'daily-backup.json'
        self.backup_file.write_text(json.dumps({**EXPORT, 'created': '2026-11-08T03:00:00Z'}))
        self.build_post_only()

    def build_post_only(self):
        k, cfg = self.get, self.cfg
        named = k('named', ('history_since', 'pre_backup', 'owned_before'))
        substitutes = {}
        if 'history_since' in named:
            substitutes['history_since'] = '2026-11-08T08:00:00Z'
        if 'pre_backup' in named:
            substitutes['pre_backup'] = str(self.backup_file)
            substitutes['pre_backup_sha256'] = acc.file_digest(self.backup_file)
            substitutes['pre_backup_at'] = k('backup_at', '2026-11-08T03:00:00Z')
        owned = True if 'owned_before' in named else None
        if owned is not None:
            substitutes['owned_before'] = 'yes'
        runs = [dict(at=k('at1', AT1), uptime=k('uptime1', 230), phase=k('phase1', 'awaiting'), default=True,
                     export=False), dict(at=k('at2', AT2), uptime=k('uptime2', 820), phase=k('phase2', 'reconfirmed'),
                                         default=k('default_end', False), export=True)]
        have_history = 'history_since' in named
        for folder, run in zip(self.obs, runs):
            folder.mkdir()
            findings = []
            check = lambda name, ok, detail=None: findings.append({'check': name, 'ok': bool(ok), 'detail': detail})
            for name in ('github.release_is_published', 'github.firmware_digest_and_size', 'github.descriptor',
                         'ha.integration_version', 'ha.single_config_entry', 'ha.entity_reports_new_version',
                         'e32.version_source_elf_web_exact', 'e32.boot_confirmed', 'e32.new_boot_after_install'):
                check(name, True)
            check('ha.install_actions==1', have_history)
            check('ha.last_install', True)
            check('ha.offered_before_install', have_history)
            doc = heating(run['phase'])
            control = acc.control_state(doc, owned if owned is not None else False)
            if owned is None:
                control = {**control, 'ok': False}
            check('e32.control_state_safe', control['ok'], control)
            write_settings(folder / 'settings', cfg, after=True, export=run['export'])
            export = ({'http_status': 200, 'compared': True, 'refusal': None} if run['export'] else
                      {'http_status': 403, 'compared': False, 'refusal': 'password_change_required'})
            if 'pre_backup' in named:
                after = acc.export_document((folder / 'settings' / 'config-backup-export.json').read_bytes()) \
                    if run['export'] else None
                differences = acc.compare_export(json.loads(self.backup_file.read_text()), after) if after else []
                check('e32.settings_programs_bindings_preserved',
                      *acc.settings_finding(differences, {'export_compared': after is not None}, export, run['default']))
            self.mqtt_findings(check, folder)
            summary = acc.learned_summary(doc)
            boot = acc.boot_instant(run['at'], run['uptime'])
            history = [{'entity_id': 'sensor.woonkamer_e32_heat_request', 'sequence': [
                {'at': '2026-11-08T09:12:00Z', 'control': 'awaiting_confirmation'},
                {'at': '2026-11-08T09:19:00Z', 'control': 'active'}]}] if have_history else []
            acc.save(folder / 'OBSERVATION.json', {
                'schema': 1, 'kind': 'installer_post_observation', 'tag': cfg.tag, 'config': cfg.as_dict(),
                'mode': 'post_only', 'preinstall': None, 'gaps': ['No pre-install capture: nothing from before the '
                                                                   'install is known except what is named below.'],
                'substitutes': substitutes,
                'observation': {'at_utc': run['at'], 'version': cfg.tag, 'boot_pending': False,
                                'uptime_seconds': run['uptime'], 'boot_at_utc': boot.strftime('%Y-%m-%dT%H:%M:%SZ'),
                                'mqtt_counters': {'mqtt_stalled_disconnects': 0, 'mqtt_socket_error_disconnects': 0},
                                'control_phase': control['phase'], 'default_password': run['default'],
                                'export_http_status': export['http_status'], 'logout_http_status': 200},
                'install_actions': 1 if have_history else None, 'offered_before_install': have_history or None,
                'ha_entity': {'entity_id': cfg.entity_id, 'state': 'off', 'installed_version': cfg.tag,
                              'latest_version': cfg.tag, 'in_progress': False, 'last_install': last_install(cfg)},
                'ha_core_version': '2026.10.4', 'ha_integration_version': cfg.ha_version,
                'ha_config_entries': acc.entries_summary(entries()), 'github_release': release(cfg),
                'firmware_sha256': FW, 'firmware_bytes': FW_BYTES, 'control': control, 'owned_before': owned,
                'export': export,
                'info': {'learned': {'summary': summary, 'fresh': acc.learned_fresh(summary), 'before_update': None,
                                     'kept_over_update': None}, 'ha_issues': None, 'ha_control_history': history},
                'findings': findings, 'failed': [f['check'] for f in findings if not f['ok']]})
            acc.write_manifest(folder, 'OBS-MANIFEST.json', 'installer_post_observation')
        self.independent(with_backup_comparison=False)

    def receipt(self):
        ci = json.loads(self.ci.read_text())
        return writer.build(self.cfg, None, self.obs, self.ind, ci, post_only=True)


def touched_places():
    """What the writer or the verifier import could change in the repository (no git: a check runs there)."""
    places = [WORKTREE / 'scripts', WORKTREE / 'docs' / 'modern-thermostat' / 'update-acceptance',
              WORKTREE / 'docs' / 'modern-thermostat' / 'E32-UPDATE-GATE.json']
    seen = {}
    for place in places:
        for path in ([place] if place.is_file() else place.rglob('*')):
            if '__pycache__' in path.parts:
                continue
            seen[str(path)] = path.stat().st_mtime_ns
    return seen


def config_file(directory, **overrides):
    path = Path(directory) / 'install-config.json'
    path.write_text(json.dumps({**{k: v for k, v in CFG.as_dict().items() if v is not None}, **overrides}))
    return path


@unittest.skipUnless(VERIFIER.exists(), f'repository with the gate not found: {VERIFIER}')
class ReceiptAgainstGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        before = touched_places()
        cls.gate = writer.load_verifier(WORKTREE)
        assert before == touched_places(), 'loading the verifier changed the repository'

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='acceptance-receipt-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fixture(self, cfg=CFG, **kw):
        return Fixture(self.tmp / 'captures', cfg, **kw)

    def assert_incomplete(self, record, *names):
        self.assertEqual(record['status'], 'INCOMPLETE')
        failing = [n for n, v in {**record['checks'], **record['extra_checks']}.items() if v is not True]
        for name in names:
            self.assertIn(name, failing)
        return failing

    def test_pass_receipt_passes_the_gate(self):
        record, limits = self.fixture().receipt()
        self.assertEqual(record['status'], 'PASS', limits)
        self.assertEqual(sorted(record['checks']), sorted(self.gate.HA_REQUIRED))
        self.assertEqual(sorted(writer.GATE_CHECKS), sorted(self.gate.HA_REQUIRED))
        self.gate.home_assistant_acceptance(record)          # the function the gate calls
        self.gate.METHODS['home_assistant'](record)          # the same rule, through the method table
        self.assertTrue(record['details']['learned']['kept_over_update'])
        self.assertTrue(record['details']['password']['own_password_at_end'])
        self.assertEqual(record['details']['takeover']['phases'], ['awaiting_reconfirm', 'reconfirmed'])
        self.assertEqual(record['details']['mode'], 'full')
        self.assertEqual(record['ha_installed_version_before'], CFG.previous_tag)
        # The whole gate on a throwaway root: accepted <- this receipt (digest-bound), no candidate.
        root = self.tmp / 'root'
        receipt = root / 'docs' / 'modern-thermostat' / 'update-acceptance' / (acc.receipt_stem(CFG.tag) + '-20261108.json')
        receipt.parent.mkdir(parents=True)
        receipt.write_bytes((json.dumps(record, indent=2) + '\n').encode())
        policy = {'schema': 1, 'required_for_successor_release': True, 'pending_tag': None,
                  'accepted': {'tag': CFG.tag, 'receipt': receipt.relative_to(root).as_posix(),
                               'sha256': acc.file_digest(receipt)}}
        result = self.gate.verify(root, policy)
        self.assertEqual((result['result'], result['accepted']), ('PASS', CFG.tag))

    def test_pass_receipt_is_a_valid_accepted_update_path_basis(self):
        """verify_accepted_update_path.accepted_source accepts the receipt as the accepted basis of a repository."""
        record, limits = self.fixture().receipt()
        self.assertEqual(record['status'], 'PASS', limits)
        root = self.tmp / 'root'
        docs = root / 'docs' / 'modern-thermostat'
        (docs / 'update-acceptance').mkdir(parents=True)
        receipt = docs / 'update-acceptance' / 'e32-rc4-20261108.json'
        receipt.write_bytes((json.dumps(record, indent=2) + '\n').encode())
        (docs / 'E32-UPDATE-GATE.json').write_text(json.dumps({
            'schema': 1, 'required_for_successor_release': True, 'pending_tag': None,
            'accepted': {'tag': CFG.tag, 'receipt': receipt.relative_to(root).as_posix(), 'sha256': acc.file_digest(receipt)}}))
        sys.path.insert(0, str(WORKTREE / 'scripts'))
        try:
            import verify_accepted_update_path as path
            accepted, sha = path.accepted_source(root)
        finally:
            sys.path.remove(str(WORKTREE / 'scripts'))
        self.assertEqual((accepted['tag'], accepted['source_commit']), (CFG.tag, SOURCE))
        self.assertEqual(sha, acc.file_digest(receipt))

    def test_stable_tag_receipt_is_a_normal_release_and_passes_the_gate(self):
        record, limits = self.fixture(STABLE).receipt()
        self.assertEqual(record['status'], 'PASS', limits)
        self.assertIs(record['github_release']['prerelease'], False)
        self.gate.home_assistant_acceptance(record)
        self.assertEqual(acc.receipt_stem(STABLE.tag), 'e32-1.0.0')

    def test_prerelease_follows_the_tag(self):
        """A pre-release flag on a stable tag (or a normal release for an rc) is a public release that does not match."""
        fixture = self.fixture(STABLE)
        for folder in fixture.obs:
            doc = json.loads((folder / 'OBSERVATION.json').read_text())
            doc['github_release']['prerelease'] = True
            acc.save(folder / 'OBSERVATION.json', doc)
            acc.write_manifest(folder, 'OBS-MANIFEST.json', 'installer_post_observation')
        record, _ = fixture.receipt()
        self.assert_incomplete(record, 'public_release_exact')

    def test_frost_protection_while_waiting_is_safe(self):
        record, limits = self.fixture(phase1='frost').receipt()
        self.assertEqual(record['status'], 'PASS', limits)

    def test_writer_command_line_writes_only_receipt_out(self):
        fx = self.fixture()
        out = self.tmp / 'receipt.json'
        script = HERE / 'write_receipt.py'
        config = config_file(self.tmp)
        command = [sys.executable, '-I', str(script), '--config', str(config), '--repo', str(WORKTREE),
                   '--preinstall', str(fx.pre), '--obs', str(fx.obs[1]), '--obs', str(fx.obs[0]),
                   '--independent', str(fx.ind), '--ci-json', str(fx.ci), '--receipt-out', str(out)]
        before = touched_places()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.gate.home_assistant_acceptance(json.loads(out.read_text(encoding='utf-8')))
        self.assertEqual(before, touched_places(), 'the writer changed the repository')
        dry = subprocess.run(command[:-2] + ['--dry-run'], capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('DRY RUN', dry.stdout)
        self.assertIn('leave the repository unchanged', dry.stdout)

    def test_writer_apply_gate_changes_only_the_gate_files_of_the_given_repository(self):
        """--write --apply-gate on a copy of the policy files: accepted <- receipt, pending null, exception removed."""
        fx = self.fixture()
        repo = self.tmp / 'repo'
        docs = repo / 'docs' / 'modern-thermostat'
        (docs / 'update-acceptance').mkdir(parents=True)
        shutil.copytree(WORKTREE / 'scripts', repo / 'scripts', ignore=shutil.ignore_patterns('__pycache__', 'upstream'))
        (docs / 'E32-UPDATE-GATE.json').write_text(json.dumps({
            'schema': 1, 'required_for_successor_release': True, 'accepted': None, 'pending_tag': CFG.tag,
            'candidate_plan': 'plan.json', 'publication_exception': {'receipt': 'x.json', 'sha256': '0' * 64}}))
        out = subprocess.run([sys.executable, '-I', str(HERE / 'write_receipt.py'), '--config', str(config_file(self.tmp)),
                              '--repo', str(repo), '--preinstall', str(fx.pre), '--obs', str(fx.obs[0]), '--obs', str(fx.obs[1]),
                              '--independent', str(fx.ind), '--ci-json', str(fx.ci), '--write', '--apply-gate'],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        gate = json.loads((docs / 'E32-UPDATE-GATE.json').read_text())
        self.assertEqual(gate['accepted']['tag'], CFG.tag)
        self.assertIsNone(gate['pending_tag'])
        self.assertNotIn('publication_exception', gate)
        receipt = repo / gate['accepted']['receipt']
        self.assertTrue(receipt.name.startswith('e32-rc4-20261108'), receipt.name)
        self.assertEqual(acc.file_digest(receipt), gate['accepted']['sha256'])
        self.assertNotIn(b'\r\n', receipt.read_bytes())
        self.assertNotIn(b'\r\n', (docs / 'E32-UPDATE-GATE.json').read_bytes())

    def test_no_reconfirmation_is_incomplete_and_the_gate_refuses_it(self):
        record, _ = self.fixture(phase2='awaiting', ind_takeover=False).receipt()
        self.assert_incomplete(record, 'takeover_reconfirmed', 'independent_postcheck_passed')
        root = self.tmp / 'root2'
        receipt = root / 'r.json'
        root.mkdir()
        receipt.write_bytes(json.dumps(record).encode())
        with self.assertRaisesRegex(ValueError, 'Update not accepted'):
            self.gate.verify(root, {'schema': 1, 'required_for_successor_release': True, 'pending_tag': None,
                                    'accepted': {'tag': CFG.tag, 'receipt': 'r.json', 'sha256': acc.file_digest(receipt)}})

    def test_two_install_actions(self):
        record, _ = self.fixture(install_actions=2, uploads=2).receipt()
        self.assert_incomplete(record, 'single_ha_install_action', 'local_upload_accepted')
        with self.assertRaisesRegex(ValueError, 'Incomplete physical update acceptance'):
            self.gate.home_assistant_acceptance(record)

    def test_uptime_short_of_600_s(self):
        record, _ = self.fixture(uptime2=590).receipt()
        self.assert_incomplete(record, 'stable_uptime_observed')

    def test_restart_between_observations(self):
        record, _ = self.fixture(uptime1=230, uptime2=120).receipt()
        self.assert_incomplete(record, 'stable_uptime_observed')

    def test_uptime_rises_but_the_boot_instant_moved(self):
        """R5-08: a restart between the reads that still leaves a rising uptime is a different boot."""
        record, limits = self.fixture(uptime2=700).receipt()  # boot at 09:12:20 instead of 09:10:20
        self.assert_incomplete(record, 'stable_uptime_observed', 'new_boot_observed')
        self.assertTrue(any('do not all belong to the boot' in line for line in limits))

    def test_observations_of_a_later_boot_are_not_the_install(self):
        """R5-08: reads that agree with each other but come from a boot long after the install."""
        record, _ = self.fixture(at1='2026-11-08T11:14:10Z', uptime1=230, at2='2026-11-08T11:24:00Z', uptime2=820).receipt()
        self.assert_incomplete(record, 'stable_uptime_observed', 'new_boot_observed')

    def test_late_reads_of_the_install_boot_are_fine(self):
        """Reads two days after the install, with no restart since, still describe the install's boot."""
        record, limits = self.fixture(at1='2026-11-10T09:14:10Z', uptime1=172_800 + 230,
                                      at2='2026-11-10T09:24:00Z', uptime2=172_800 + 820).receipt()
        self.assertEqual(record['status'], 'PASS', limits)

    def test_foreign_controller_after_restart(self):
        record, _ = self.fixture(phase1='foreign').receipt()
        self.assert_incomplete(record, 'control_state_safe_after_restart')

    def test_duplicate_entity_after_ha_upgrade(self):
        extra = [('sensor.woonkamer_e32_heat_request_2', '42', False)]
        record, _ = self.fixture(pre_extra_states=extra, post_extra_states=extra).receipt()
        self.assert_incomplete(record, 'no_new_duplicate_or_stale_entities')

    def test_stale_entity_after_update(self):
        record, _ = self.fixture(post_extra_states=[('sensor.old_flow', 'unavailable', True)]).receipt()
        self.assert_incomplete(record, 'no_new_duplicate_or_stale_entities')

    def test_new_duplicate_group_in_registry_counts(self):
        record, _ = self.fixture(post_dup_groups=[['sensor.a', 'sensor.b']]).receipt()
        self.assert_incomplete(record, 'no_new_duplicate_or_stale_entities')

    def test_second_config_entry(self):
        record, _ = self.fixture(pre_entry_count=2, post_entry_count=2).receipt()
        self.assert_incomplete(record, 'ha_upgraded_with_one_entry')

    def test_wrong_integration_version(self):
        record, _ = self.fixture(post_version='1.0.0rc1').receipt()
        self.assert_incomplete(record, 'ha_upgraded_with_one_entry')

    def test_baseline_taken_after_the_upgrade(self):
        record, _ = self.fixture(baseline_version=CFG.ha_version).receipt()
        self.assert_incomplete(record, 'ha_upgraded_with_one_entry')

    def test_export_never_compared(self):
        record, limits = self.fixture(export2=False, default_end=True).receipt()
        self.assert_incomplete(record, 'settings_programs_bindings_preserved')
        self.assertTrue(any('factory password at the end' in line for line in limits))

    def test_changed_setting(self):
        record, _ = self.fixture(settings_change=True).receipt()
        self.assert_incomplete(record, 'settings_programs_bindings_preserved')

    def test_mqtt_disconnects_rose(self):
        record, _ = self.fixture(disconnects=((0, 0), (1, 0))).receipt()
        self.assert_incomplete(record, 'control_state_safe_after_restart')

    def test_failed_ci(self):
        record, _ = self.fixture(ci='failure').receipt()
        self.assert_incomplete(record, 'fresh_preflight_passed')

    def test_what_was_learned_is_noted_but_never_a_gate(self):
        record, limits = self.fixture(fresh=True).receipt()  # the E32 reads back less than it had before the update
        self.assertEqual(record['status'], 'PASS')
        self.assertFalse(record['details']['learned']['kept_over_update'])
        self.assertTrue(record['details']['learned']['started_fresh'])
        self.assertTrue(any('did not all survive' in line for line in limits))

    def test_wait_seen_only_in_ha_history(self):
        history = [{'entity_id': 'sensor.woonkamer_e32_heat_request',
                    'sequence': [{'at': '2026-11-08T09:12:00Z', 'control': 'awaiting_confirmation'},
                                 {'at': '2026-11-08T09:19:00Z', 'control': 'active'}]}]
        record, limits = self.fixture(phase1='reconfirmed', control_history=history).receipt()
        self.assertEqual(record['status'], 'PASS', limits)

    def test_no_wait_evidence_at_all(self):
        record, limits = self.fixture(phase1='reconfirmed').receipt()
        self.assert_incomplete(record, 'control_state_safe_after_restart')
        self.assertTrue(any('documented wait' in line for line in limits))

    def test_tampered_capture_is_refused(self):
        fx = self.fixture()
        (fx.obs[1] / 'settings' / 'config-rooms.json').write_text('{"rooms": []}\n')
        with self.assertRaises(SystemExit):
            fx.receipt()

    def test_baseline_changed_after_preinstall(self):
        fx = self.fixture()
        summary = json.loads((fx.base / 'CAPTURE-SUMMARY.json').read_text())
        summary['notes'] = ['edited']
        acc.save(fx.base / 'CAPTURE-SUMMARY.json', summary)
        acc.write_manifest(fx.base, 'CAPTURE-MANIFEST.json', 'ha_baseline_capture')
        with self.assertRaises(SystemExit):
            fx.receipt()

    def test_observations_of_another_release_are_refused(self):
        fx = self.fixture()
        with self.assertRaises(AssertionError):
            writer.build(STABLE, fx.pre, fx.obs, fx.ind, json.loads(fx.ci.read_text()))


@unittest.skipUnless(VERIFIER.exists(), f'repository with the gate not found: {VERIFIER}')
class PostOnly(unittest.TestCase):
    """An install without a pre-install capture: gaps are recorded, substitutes are named, nothing is invented."""

    @classmethod
    def setUpClass(cls):
        cls.gate = writer.load_verifier(WORKTREE)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='acceptance-postonly-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fixture(self, **kw):
        return PostOnlyFixture(self.tmp / 'captures', CFG, **kw)

    def test_without_substitutes_the_three_checks_stay_false(self):
        record, limits = self.fixture(named=()).receipt()
        self.assertEqual(record['status'], 'INCOMPLETE')
        for name in ('backup_verified', 'settings_programs_bindings_preserved', 'control_state_safe_after_restart'):
            self.assertIs(record['checks'][name], False, name)
        self.assertEqual(record['details']['mode'], 'post_only')
        self.assertIsNone(record['extra_checks']['no_new_duplicate_or_stale_entities'])
        self.assertTrue(any('no pre-install capture' in line.lower() for line in limits))
        with self.assertRaises(ValueError):
            self.gate.home_assistant_acceptance(record)

    def test_each_missing_substitute_blocks_its_check(self):
        for dropped, blocked in (('pre_backup', 'backup_verified'), ('pre_backup', 'settings_programs_bindings_preserved'),
                                 ('owned_before', 'control_state_safe_after_restart'),
                                 ('history_since', 'single_ha_install_action')):
            named = tuple(n for n in ('history_since', 'pre_backup', 'owned_before') if n != dropped)
            record, _ = self.fixture(named=named).receipt()
            self.assertIs(record['checks'][blocked], False, f'{blocked} without {dropped}')
            shutil.rmtree(self.tmp / 'captures')

    def test_named_substitutes_can_make_a_pass_and_are_listed_as_limits(self):
        record, limits = self.fixture().receipt()
        self.assertEqual(record['status'], 'PASS', limits)
        self.gate.home_assistant_acceptance(record)
        text = '\n'.join(limits)
        for needle in ('Substitute evidence: the Home Assistant recorder history was read from',
                       'Substitute evidence: the settings were compared with the export',
                       'Substitute evidence: whether the E32 controlled the boiler',
                       'ha_upgraded_with_one_entry: cannot be proven',
                       'no_new_duplicate_or_stale_entities: cannot be proven'):
            self.assertIn(needle, text)
        self.assertEqual(record['ha_installed_version_before'], CFG.previous_tag)
        self.assertEqual(record['ha_latest_version_before'], CFG.tag)
        self.assertEqual(record['backup_manifest_sha256'], record['details']['substitutes']['pre_backup_sha256'])
        self.assertNotEqual(record['installer_receipt_sha256'], record['independent_receipt_sha256'])

    def test_a_backup_newer_than_the_install_is_no_backup(self):
        record, limits = self.fixture(backup_at='2026-11-08T09:12:00Z').receipt()
        self.assertEqual(record['status'], 'INCOMPLETE')
        self.assertIs(record['checks']['backup_verified'], False)
        self.assertIs(record['checks']['settings_programs_bindings_preserved'], False)
        self.assertTrue(any('not older than the install start' in line for line in limits))

    def test_a_post_only_folder_is_not_accepted_as_a_full_observation(self):
        fx = self.fixture()
        with self.assertRaises(AssertionError):
            writer.build(CFG, fx.root / 'x', fx.obs, fx.ind, json.loads(fx.ci.read_text()))

    def test_boot_continuity_applies_to_post_only_too(self):
        record, _ = self.fixture(uptime2=700).receipt()
        self.assertIs(record['checks']['stable_uptime_observed'], False)


class Configuration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='acceptance-config-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def args(self, *argv):
        import argparse
        parser = argparse.ArgumentParser()
        acc.add_config_arguments(parser)
        return parser.parse_args(list(argv))

    def test_file_then_arguments(self):
        path = config_file(self.tmp)
        cfg = acc.load_config(self.args('--config', str(path), '--tag', 'v1.0.0-e32v2-rc.5', '--previous-tag',
                                        'v1.0.0-e32v2-rc.4', '--ha-version', '1.0.0rc6'))
        self.assertEqual((cfg.tag, cfg.previous_tag, cfg.ha_version), ('v1.0.0-e32v2-rc.5', 'v1.0.0-e32v2-rc.4', '1.0.0rc6'))
        self.assertEqual((cfg.ha_tag, cfg.hacs_tag, cfg.mqtt_prefix, cfg.mqtt_port), ('ha-v1.0.0rc6', '1.0.0rc6', 'ib-therm', 1883))
        self.assertTrue(cfg.expect_prerelease)

    def test_mqtt_host_defaults_to_the_home_assistant_host(self):
        path = config_file(self.tmp)
        document = json.loads(path.read_text())
        document.pop('mqtt_host')
        path.write_text(json.dumps(document))
        cfg = acc.load_config(self.args('--config', str(path)))
        self.assertEqual(cfg.mqtt_host, '192.168.1.10')

    def test_problems_are_refused_with_a_reason(self):
        cases = [(dict(tag='v1.0.0'), 'not an E32 firmware tag'), (dict(previous_tag='v1.0.0-e32v2-rc.4'), 'older than tag'),
                 (dict(ha_version='latest'), 'integration version'), (dict(entity_id='sensor.x'), 'update entity'),
                 (dict(ha_url='https://homeassistant.example.com'), 'LAN address'),
                 (dict(e32_url='https://192.168.1.20'), 'LAN address'),
                 (dict(e32_url='http://8.8.8.8'), 'LAN address'),
                 (dict(ha_url='http://user:pw@192.168.1.10'), 'LAN address')]
        for override, message in cases:
            path = config_file(self.tmp, **override)
            with self.subTest(override=override), self.assertRaisesRegex(SystemExit, message):
                acc.load_config(self.args('--config', str(path)))

    def test_unknown_key_and_missing_value(self):
        path = config_file(self.tmp, colour='red')
        with self.assertRaisesRegex(SystemExit, 'unknown keys'):
            acc.load_config(self.args('--config', str(path)))
        path.write_text(json.dumps({'tag': CFG.tag}))
        with self.assertRaisesRegex(SystemExit, 'Missing previous_tag'):
            acc.load_config(self.args('--config', str(path)))
        with self.assertRaisesRegex(SystemExit, 'does not exist'):
            acc.load_config(self.args('--config', str(self.tmp / 'nothing.json')))

    def test_shipped_config_is_valid_and_has_no_secret(self):
        cfg = acc.load_config(self.args('--config', str(acc.DEFAULT_CONFIG)))
        self.assertEqual(cfg.expect_prerelease, not acc.is_stable_tag(cfg.tag))
        raw = acc.DEFAULT_CONFIG.read_text(encoding='utf-8')
        self.assertNotRegex(raw.replace('Addresses must be on the home network; the token is in ha-token.txt (git-ignored), '
                                        'passwords are typed.', ''), r'(?i)password|token|secret')
        self.assertNotIn('\r', raw)

    def test_lan_hosts(self):
        for host in ('192.168.1.130', '10.0.0.4', '172.16.5.5', '127.0.0.1', '169.254.1.1', 'homeassistant', 'ha.local'):
            self.assertTrue(acc.is_lan_host(host), host)
        for host in ('8.8.8.8', 'example.com', 'api.github.com', '172.32.0.1', '', None):
            self.assertFalse(acc.is_lan_host(host), host)

    @unittest.skipUnless(VERIFIER.exists(), 'no gate')
    def test_tag_order_and_stable_agree_with_the_gate(self):
        gate = writer.load_verifier(WORKTREE)
        order = ['v0.1.0-e32v2-alpha.36', 'v0.1.0-e32v2-beta.18', 'v0.1.0-e32v2-beta.19', 'v1.0.0-e32v2-alpha.1',
                 'v1.0.0-e32v2-beta.1', 'v1.0.0-e32v2-rc.1', 'v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2', 'v1.0.1-e32v2-beta.1',
                 'v1.0.1-e32v2', 'v1.1.0-e32v2', 'v10.0.0-e32v2']
        for tag in order:
            self.assertEqual(acc.tag_key(tag), gate.version(tag), tag)
            self.assertEqual(acc.is_stable_tag(tag), gate.stable(tag), tag)
        for bad in ('v1.0.0', 'v1.0.0-e32v2-', 'v01.0.0-e32v2', 'v1.0.0-e32v2-rc.01', 'ha-v1.0.0', '1.0.0-e32v2'):
            self.assertIsNone(acc.tag_key(bad), bad)
            self.assertIsNone(gate.version(bad), bad)
        self.assertEqual(sorted(reversed(order), key=acc.tag_key), order)

    def test_receipt_names(self):
        self.assertEqual(acc.receipt_stem('v1.0.0-e32v2-rc.4'), 'e32-rc4')
        self.assertEqual(acc.receipt_stem('v0.1.0-e32v2-beta.19'), 'e32-beta19')
        self.assertEqual(acc.receipt_stem('v1.0.0-e32v2'), 'e32-1.0.0')
        with self.assertRaises(ValueError):
            acc.receipt_stem('ha-v1.0.0rc5')

    def test_no_release_in_the_code(self):
        """The scripts carry no tag, version, address or entity of a release or a house (docstrings and help excepted)."""
        patterns = [re.compile(p) for p in (r'v\d+\.\d+\.\d+-e32v2', r'\b\d+\.\d+\.\d+(?:rc|a|b)\d+\b', r'\brc\.\d', r'\bbeta\.\d',
                                            r'\b192\.168\.\d', r'update\.woonkamer')]
        found = []
        for path in sorted(HERE.glob('*.py')):
            if path.name.startswith('test_'):
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            skip = set()
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body \
                        and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                    skip.add(id(node.body[0].value))
                if isinstance(node, ast.Call):
                    skip.update(id(kw.value) for kw in node.keywords if kw.arg in ('help', 'description'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                    found += [f'{path.name}:{node.lineno}: {node.value[:60]!r}' for p in patterns if p.search(node.value)]
        self.assertEqual(found, [])

    def test_no_secret_or_machine_path_in_any_file_of_the_kit(self):
        for path in sorted(HERE.iterdir()):
            if path.suffix not in ('.py', '.json', '.md') or path.name.startswith('test_'):
                continue
            text = path.read_text(encoding='utf-8')
            self.assertNotRegex(text, r'(?i)C:\\Users|AppData|scratchpad|/home/\w+/', path.name)
            self.assertNotIn('\r', text, path.name + ' has CRLF')
            self.assertNotRegex(text, r'Bearer [A-Za-z0-9._-]{20,}', path.name)
        ignore = (acc.REPO / '.gitignore')
        if ignore.exists():
            self.assertIn('ha-token.txt', ignore.read_text(encoding='utf-8'))


class Evaluators(unittest.TestCase):
    def test_control_state_phases(self):
        self.assertEqual(acc.control_state(heating('awaiting'), True)['phase'], 'awaiting_reconfirm')
        self.assertTrue(acc.control_state(heating('awaiting'), True)['ok'])
        self.assertTrue(acc.control_state(heating('frost'), True)['ok'])
        heat_while_waiting = heating('awaiting')
        heat_while_waiting['active']['command'] = {'send': True, 'flow_c': 45, 'why': 'heating'}
        self.assertFalse(acc.control_state(heat_while_waiting, True)['ok'])
        self.assertTrue(acc.control_state(heating('reconfirmed'), True)['ok'])
        self.assertFalse(acc.control_state(heating('reconfirmed'), False)['ok'])
        self.assertFalse(acc.control_state(heating('foreign'), True)['ok'])
        self.assertTrue(acc.owned_before(heating('before_active')))

    def test_learned_fresh_and_kept(self):
        self.assertTrue(acc.learned_fresh(acc.learned_summary(heating('awaiting', fresh=True))))
        self.assertFalse(acc.learned_fresh(acc.learned_summary(heating('awaiting', fresh=False))))
        older = {**heating('awaiting'), 'tuning': None}
        self.assertFalse(acc.learned_fresh(acc.learned_summary(older)))  # no tuning block at all
        before = acc.learned_summary(heating('before_active', fresh=False))
        self.assertTrue(acc.learned_kept(before, before))
        self.assertFalse(acc.learned_kept(before, acc.learned_summary(heating('awaiting', fresh=True))))
        self.assertIsNone(acc.learned_kept(acc.learned_summary(heating('awaiting', fresh=True)), before))  # nothing to keep
        self.assertIsNone(acc.learned_kept(None, before))

    def test_integration_version_needs_both_fields(self):
        doc = diagnostics('1.0.0rc5')
        self.assertEqual(acc.integration_version(acc.diagnostics_extract(doc)), '1.0.0rc5')
        doc['custom_components']['open_thermostat']['version'] = '1.0.0rc4'
        self.assertIsNone(acc.integration_version(acc.diagnostics_extract(doc)))
        self.assertIsNone(acc.integration_version(None))

    def test_issue_flags(self):
        flags = acc.issue_flags(acc.diagnostics_extract(diagnostics('1.0.0rc5', issues=[
            'e32_default_password_X', 'reconfirm_takeover_X'])))
        self.assertTrue(flags['default_password'] and flags['reconfirm_takeover'])
        no_list = diagnostics('1.0.0rc5')
        del no_list['issues']
        self.assertIsNone(acc.issue_flags(acc.diagnostics_extract(no_list)))

    def test_mqtt_evaluate(self):
        good = acc.mqtt_evaluate(acc.parse_mqtt(mqtt_text()), 150)
        self.assertTrue(all(good[k] for k in MQTT_NAMES))
        self.assertEqual(good['detail']['state_heating_active'], {'state': 'active'})
        self.assertFalse(acc.mqtt_evaluate(acc.parse_mqtt(mqtt_text(beats=(36.9,))), 150)['heartbeat_every_60s'])
        self.assertFalse(acc.mqtt_evaluate(acc.parse_mqtt(mqtt_text(online=False)), 150)['availability_online'])

    def test_boot_continuity(self):
        window = (STARTED, FINISHED)
        good = [{'at_utc': AT1, 'uptime_seconds': 230}, {'at_utc': AT2, 'uptime_seconds': 820}]
        self.assertTrue(acc.boot_continuity(good, *window)[0])
        within_jitter = [{'at_utc': AT1, 'uptime_seconds': 230}, {'at_utc': AT2, 'uptime_seconds': 825}]
        self.assertTrue(acc.boot_continuity(within_jitter, *window)[0])
        moved = [{'at_utc': AT1, 'uptime_seconds': 230}, {'at_utc': AT2, 'uptime_seconds': 700}]
        self.assertFalse(acc.boot_continuity(moved, *window)[0])
        before = [{'at_utc': '2026-11-08T09:14:10Z', 'uptime_seconds': 900}, {'at_utc': AT2, 'uptime_seconds': 1490}]
        self.assertFalse(acc.boot_continuity(before, *window)[0])  # booted at 08:59:10, before the install began
        self.assertFalse(acc.boot_continuity([{'at_utc': AT1, 'uptime_seconds': None}], *window)[0])
        self.assertFalse(acc.boot_continuity([], *window)[0])
        self.assertFalse(acc.boot_continuity(good, None, None)[0])

    @unittest.skipUnless(VERIFIER.exists(), 'no gate')
    def test_boot_window_matches_the_gate(self):
        gate = writer.load_verifier(WORKTREE)
        if not hasattr(gate, 'BOOT_JITTER_S'):
            self.skipTest('the gate has no boot rule yet')
        for name in ('BOOT_JITTER_S', 'BOOT_BEFORE_S', 'BOOT_AFTER_S'):
            self.assertEqual(getattr(gate, name), getattr(acc, name), name)

    def test_compare_export_ignores_what_describes_the_export(self):
        before = {**EXPORT, 'firmware': 'a', 'created': 'x', 'secrets': {'sealed': 1}, 'rooms': [{'id': 1}]}
        after = {**EXPORT, 'firmware': 'b', 'created': 'y', 'secrets': None, 'rooms': [{'id': 1}], 'added': True}
        self.assertEqual(acc.compare_export(before, after), [])
        after['rooms'] = [{'id': 2}]
        self.assertEqual(len(acc.compare_export(before, after)), 1)

    def test_export_document(self):
        self.assertIsNotNone(acc.export_document(json.dumps(EXPORT)))
        for raw in (b'not json', b'[]', json.dumps({**EXPORT, 'format': 'other'}).encode(),
                    json.dumps({**EXPORT, 'schema': 2}).encode()):
            self.assertIsNone(acc.export_document(raw))

    def test_read_secret_never_prompts_without_a_terminal(self):
        class NoTty:
            def isatty(self):
                return False
        os.environ.pop('OT_TEST_SECRET', None)
        with self.assertRaises(SystemExit):
            acc.read_secret('OT_TEST_SECRET', 'x', stdin=NoTty(), ask=lambda p: self.fail('prompted'))
        os.environ['OT_TEST_SECRET'] = 'from-env'
        try:
            self.assertEqual(acc.read_secret('OT_TEST_SECRET', 'x', stdin=NoTty()), 'from-env')
        finally:
            del os.environ['OT_TEST_SECRET']

    def test_ha_requests_only_go_to_the_configured_lan_address(self):
        outside = acc.Config({**CFG.__dict__, 'ha_url': 'https://8.8.8.8:8123'})
        with self.assertRaises(AssertionError):
            acc.ha_bytes(outside, '/api/config', 'token')

    def test_real_capture_shapes(self):
        """Optional: the evaluators on a real earlier capture (OT_REAL_CAPTURE_DIR = a post folder with mqtt/listen.txt)."""
        folder = os.environ.get('OT_REAL_CAPTURE_DIR')
        if not folder or not (Path(folder) / 'mqtt' / 'listen.txt').exists():
            self.skipTest('no real capture named in OT_REAL_CAPTURE_DIR')
        text = (Path(folder) / 'mqtt' / 'listen.txt').read_text(encoding='utf-8', errors='replace')
        result = acc.mqtt_evaluate(acc.parse_mqtt(text), 150)
        self.assertTrue(result['availability_online'] and result['heartbeat_every_60s'] and result['boiler_fields_seen'])


class DryRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='acceptance-dry-'))
        self.config = config_file(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_dry(self, script, *arguments, out=True):
        target = self.tmp / 'never'
        extra = ['--out', str(target)] if out else []
        result = subprocess.run([sys.executable, '-I', str(HERE / script), '--config', str(self.config), *arguments,
                                 *extra, '--dry-run'], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith('DRY RUN'), result.stdout)
        self.assertFalse(target.exists(), 'a dry run created its output folder')
        return result.stdout

    def test_preinstall_baseline(self):
        text = self.run_dry('capture_preinstall.py', '--stage', 'ha-baseline')
        self.assertIn('no E32 contact', text)
        self.assertNotIn('E32 POST', text)
        self.assertIn(CFG.tag, text)

    def test_preinstall_e32(self):
        text = self.run_dry('capture_preinstall.py', '--stage', 'e32', '--baseline', 'X')
        self.assertIn('POST /config/backup', text)
        self.assertIn('POST /auth/logout', text)
        self.assertIn('firmware.bin', text)

    def test_post(self):
        text = self.run_dry('capture_post.py', '--preinstall', 'X', '--mqtt-user', 'u')
        self.assertIn('MQTT subscribe ib-therm/#', text)
        self.assertIn('POST /auth/logout', text)

    def test_post_only(self):
        text = self.run_dry('capture_post.py', '--post-only', '--history-since', '2026-11-08T08:00:00Z', '--no-mqtt')
        self.assertIn('read no pre-install capture', text)
        self.assertIn('--history-since', text)
        self.assertIn('no MQTT', text)

    def test_independent(self):
        text = self.run_dry('capture_independent.py')
        self.assertIn('/auth/logout', text)
        self.assertIn(CFG.tag, text)

    def test_receipt_writer(self):
        text = self.run_dry('write_receipt.py', '--preinstall', 'P', '--obs', 'A', '--independent', 'I', '--repo', str(WORKTREE),
                            out=False)
        self.assertIn('leave the repository unchanged', text)
        self.assertIn('leave the gate', text)

    def test_conflicting_modes_and_bad_times_are_refused(self):
        for arguments in (('--post-only', '--preinstall', 'X'), (), ('--post-only', '--history-since', 'yesterday'),
                          ('--preinstall', 'X', '--history-since', '2026-11-08T08:00:00Z'),
                          ('--post-only', '--pre-backup-at', '2026-11-08T08:00:00Z')):
            result = subprocess.run([sys.executable, '-I', str(HERE / 'capture_post.py'), '--config', str(self.config),
                                     *arguments, '--out', str(self.tmp / 'never'), '--dry-run'],
                                    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
            self.assertEqual(result.returncode, 2, (arguments, result.stdout, result.stderr))


if __name__ == '__main__':
    unittest.main()
