"""Offline tests for the rc.2 acceptance kit: no E32, no Home Assistant, no GitHub, no MQTT.

Builds fixture capture folders shaped exactly like capture_rc2_preinstall.py (both stages),
capture_rc2_post.py and capture_rc2_independent.py write them -- the E32, HA and MQTT verdicts are computed
with rc2_acc's own evaluators on synthetic documents -- then runs write_rc2_receipt.py and proves that a PASS
receipt passes verify_e32_update_gate.py's home_assistant checks (METHODS['home_assistant'] and verify() on
a throwaway root), and that every gap leaves the receipt INCOMPLETE. The verifier is imported read-only from
the release worktree: its source is compiled in memory, nothing is written there.

Run: python -I test_rc2_receipt.py [-v]     (plain unittest; RC2_RELEASE_WORKTREE overrides the worktree path)
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rc2_acc as acc  # noqa: E402
import write_rc2_receipt as writer  # noqa: E402

WORKTREE = Path(os.environ.get('RC2_RELEASE_WORKTREE', str(acc.RELEASE_WORKTREE)))
VERIFIER = WORKTREE / 'scripts' / 'verify_e32_update_gate.py'
BETA22 = Path(r'C:\Users\m.dielessen\Downloads\open_thermostat-vscode-20261021\out\beta22-install')
H = lambda seed: hashlib.sha256(seed.encode()).hexdigest()
SOURCE, WEB, ELF, FW = H('source')[:40], H('web'), H('elf'), H('firmware')
FW_BYTES = 2831000
ENTRY = '01JC0FFEE0000000000000000A'
PUBLISHED, STARTED, FINISHED = '2026-11-08T08:50:00Z', '2026-11-08T09:10:05Z', '2026-11-08T09:11:30Z'


def release():
    return {'tag_name': acc.TAG, 'draft': False, 'prerelease': True, 'published_at': PUBLISHED,
            'asset': {'name': 'firmware.bin', 'size': FW_BYTES, 'digest': 'sha256:' + FW}}


def last_install(uploads=1):
    return {'tag': acc.TAG, 'from_version': acc.PREV, 'sha256': FW, 'size': FW_BYTES, 'started_at': STARTED,
            'finished_at': FINISHED, 'duration_s': 85.2, 'result': 'installed', 'uploads': uploads,
            'reported': {'version': acc.TAG, 'source_commit': SOURCE, 'web_sha256': WEB, 'elf_sha256': ELF}}


def states(extra=()):
    base = [('update.woonkamer_e32_regelaar_ketel_en_diagnose_firmware', 'off', False),
            ('climate.woonkamer', 'heat', False), ('sensor.woonkamer_e32_heat_request', '42', False),
            ('sensor.badkamer_temperatuur', '21.2', False), ('switch.hacs_pre_release', 'on', False)]
    return [{'entity_id': i, 'state': s, 'attributes': {'restored': True} if r else {}} for i, s, r in [*base, *extra]]


def diagnostics(version, duplicates=(), issues=()):
    return {'home_assistant': {'version': '2026.10.4'},
            'custom_components': {'open_thermostat': {'version': version}, 'hacs': {'version': '2.0.5'}},
            'integration_manifest': {'domain': 'open_thermostat', 'version': version},
            'data': {'e32': {'entities': {'total': 120, 'devices': 4, 'possible_duplicates': list(duplicates),
                                          'disabled': [], 'unavailable': []},
                             'firmware': {'installed_version': acc.PREV}}},
            'issues': [{'issue_id': i, 'domain': 'open_thermostat'} for i in issues]}


def entries(count=1, entry_state='loaded'):
    return [{'entry_id': ENTRY if n == 0 else ENTRY[:-1] + 'B', 'domain': 'open_thermostat', 'title': 'Woonkamer',
             'state': entry_state, 'disabled_by': None} for n in range(count)]


def active(phase):
    common = {'last_sent': None, 'foreign_controller': None, 'warnings': [], 'enabled': True,
              'boiler_limit': {'flow_c': 55, 'age_s': 40, 'reads': 2}}
    if phase == 'beta22_active':
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
    doc = {'schema': 1, 'mode': 'active', 'revision': 7, 'active': active(phase), 'learned': learned}
    if phase != 'beta22_active':
        doc['tuning'] = tuning
    return doc


SETTINGS = {'config-rooms.json': {'rooms': [{'id': 1, 'name': 'Woonkamer'}]}, 'config-wifi.json': {'ssid': 'thuis'},
            'config-boiler.json': {'max_flow': 55}, 'config-boiler-display.json': {'model': 'nefit'},
            'config-hardware.json': {'board': 'e32v2'}, 'config-debug.json': {'level': 1},
            'config-logging.json': {'syslog': False}, 'config-program-current.json': {'name': 'week'},
            'status-programs.json': ['week'], 'program-000.json': {'name': 'week', 'days': [1, 2, 3]},
            'config-bluetooth.json': {'devices': [{'address': 'a4:c1', 'name': 'bad', 'last_seen': 3}]},
            'config-heating.json': {'schema': 1, 'revision': 7, 'mode': 'active', 'minimum_flow_c': 30, 'rooms': [{'id': 'woonkamer'}]}}
EXPORT = {'format': 'openthermostat-e32-backup', 'schema': 1, 'firmware': acc.PREV, 'created': '2026-11-08T09:00:00Z',
          'secrets': None, 'not_included': ['wifi_password', 'web_password'], 'heating': {'mode': 'active'},
          'bluetooth': {'devices': [{'address': 'a4:c1', 'name': 'bad'}]}}


def write_settings(folder, after=False, export=True):
    """The settings documents as the E32 returns them; `after`: rc.2 schema additions and a new plan revision."""
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
        value = {**EXPORT, **({'firmware': acc.TAG, 'learned': {'state': 'abcd'}} if after else {})}
        raw = (json.dumps(value) + '\n').encode()
        (folder / 'config-backup-export.json').write_bytes(raw)
        entries_.append({'path': 'POST /config/backup {"action":"export"}', 'file': 'config-backup-export.json',
                         'http_status': 200, 'sha256': acc.digest(raw), 'bytes': len(raw)})
    return entries_


def mqtt_text(listen=150, beats=(36.9, 96.9), disconnects=((0, 0), (0, 0)), online=True):
    lines = ['connected Success', '   0.0 R ib-therm/v1/fw/availability 6B ' + ('online' if online else 'offline'),
             '   0.0 R ib-therm/v1/fw/state/boiler_fields/flow_c 4B 41.5',
             '   0.0 R ib-therm/v1/fw/state/heating 90B ' + json.dumps({'schema': 1, 'active': {'state': 'active'}})]
    for n, (t, (stalled, socket)) in enumerate(zip(beats, disconnects)):
        payload = json.dumps({'schema': 1, 'uptime_s': 700 + 60 * n, 'mqtt': {'disconnects': {'stalled': stalled,
                                                                                            'socket_error': socket}}})
        lines.append(f'{t:6.1f} - ib-therm/v1/fw/heartbeat {len(payload)}B {payload}')
    return '\n'.join(lines) + '\n'


class Fixture:
    """One complete set of capture folders; keyword arguments switch single pieces of evidence."""

    def __init__(self, root, **kw):
        self.root, self.kw = Path(root), kw
        self.base, self.pre = self.root / 'ha-baseline', self.root / 'preinstall'
        self.obs = [self.root / 'post1', self.root / 'post2']
        self.ind, self.ci = self.root / 'independent', self.root / 'ci.json'
        self.build()

    def get(self, key, default):
        return self.kw.get(key, default)

    def build(self):
        k = self.get
        # Stage ha-baseline: HA 0.4.0b15, one entry; no E32 contact.
        self.base.mkdir(parents=True)
        base_states = acc.reduce_states(states())
        acc.save(self.base / 'ha' / 'states-reduced.json', {'sha256': H('s0'), 'bytes': 1, 'count': len(base_states),
                                                           'entities': base_states})
        base_diag = {**acc.diagnostics_extract(diagnostics(k('baseline_version', acc.HA_PREV_VERSION))), 'sha256': H('d0'), 'bytes': 1}
        acc.save(self.base / 'ha' / 'diagnostics-extract.json', base_diag)
        base_entries = acc.entries_summary(entries())
        acc.save(self.base / 'CAPTURE-SUMMARY.json', {
            'schema': 1, 'kind': 'ha_baseline_capture', 'tag': acc.TAG, 'finished_at_utc': '2026-11-08T08:55:00Z',
            'ha': {'ha_integration_version': acc.integration_version(base_diag), 'config_entries': base_entries},
            'notes': [], 'ready_for_hacs': True})
        acc.write_manifest(self.base, 'CAPTURE-MANIFEST.json', 'ha_baseline_capture')

        # Stage e32: HA 1.0.0rc2 after HACS, E32 beta.22 in active control, backup.
        self.pre.mkdir()
        pre_extra = k('pre_extra_states', ())
        pre_states = acc.reduce_states(states(pre_extra))
        acc.save(self.pre / 'ha' / 'states-reduced.json', {'sha256': H('s1'), 'bytes': 1, 'count': len(pre_states),
                                                          'entities': pre_states})
        pre_diag = {**acc.diagnostics_extract(diagnostics(acc.HA_VERSION, issues=['e32_default_password_' + ENTRY])),
                    'sha256': H('d1'), 'bytes': 1}
        acc.save(self.pre / 'ha' / 'diagnostics-extract.json', pre_diag)
        pre_entries = acc.entries_summary(entries(k('pre_entry_count', 1)))
        migration = {'baseline_integration_version': acc.HA_PREV_VERSION, 'integration_version': acc.integration_version(pre_diag),
                     'single_entry_kept': acc.single_entry({'config_entries': base_entries}, {'config_entries': pre_entries}),
                     'entities': acc.entity_changes(base_states, pre_states, base_diag, pre_diag)}
        backup = write_settings(self.pre / 'backup')
        acc.save(self.pre / 'backup' / 'BACKUP-MANIFEST.json', {'schema': 1, 'files': backup})
        pre_heating = heating('beta22_active', fresh=False)
        acc.save(self.pre / 'e32' / 'heating.json', pre_heating)
        acc.save(self.pre / 'CAPTURE-SUMMARY.json', {
            'schema': 1, 'kind': 'installer_preinstall_capture', 'tag': acc.TAG, 'finished_at_utc': '2026-11-08T09:05:00Z',
            'baseline': {'folder': str(self.base), 'manifest_sha256': acc.file_digest(self.base / 'CAPTURE-MANIFEST.json'),
                         'finished_at_utc': '2026-11-08T08:55:00Z'},
            'github_release': release(),
            'ha_before': {'ha_entity_id': acc.ENTITY, 'ha_installed_version_before': acc.PREV,
                          'ha_latest_version_before': k('latest_before', acc.TAG), 'ha_integration_version': acc.HA_VERSION,
                          'config_entries': pre_entries},
            'ha_migration': migration,
            'e32_before': {'version': acc.PREV, 'owned_boiler': acc.owned_before(pre_heating),
                           'password': {'default_password': True, 'reported': True},
                           'learned': acc.learned_summary(pre_heating)},
            'backup_manifest_sha256': acc.file_digest(self.pre / 'backup' / 'BACKUP-MANIFEST.json'),
            'notes': [], 'ready_to_install': True})
        acc.write_manifest(self.pre, 'CAPTURE-MANIFEST.json', 'installer_preinstall_capture')

        # Two post observations: post 1 before the password change and re-confirmation, post 2 after them.
        runs = [dict(at='2026-11-08T09:14:10Z', uptime=k('uptime1', 230), phase=k('phase1', 'awaiting'), default=True,
                     export=False, fresh=k('fresh', True)),
                dict(at='2026-11-08T09:24:00Z', uptime=k('uptime2', 820), phase=k('phase2', 'reconfirmed'),
                     default=k('default_end', False), export=k('export2', True), fresh=True)]
        for folder, run in zip(self.obs, runs):
            self.observation(folder, run, base_states, base_diag, pre_states, pre_diag, base_entries, backup)

        # The independent check (own tool, own manifest).
        self.ind.mkdir()
        (self.ind / 'e32').mkdir()
        (self.ind / 'e32' / 'version.json').write_text(json.dumps({'version': acc.TAG, 'source': SOURCE}))
        ind_checks = {'release_published': True, 'identity_matches_public_release': True, 'boot_confirmed': True,
                      'control_state_safe': True, 'takeover_reconfirmed': k('ind_takeover', True),
                      'settings_same_as_preinstall_backup': True, 'settings_detail': {},
                      'ha_reports_new_version': True, 'ha_last_install_matches_e32': True,
                      'ha_one_config_entry': True, 'ha_integration_version': True}
        acc.save(self.ind / 'INDEPENDENT-SUMMARY.json', {
            'schema': 1, 'kind': 'independent_postcheck', 'tag': acc.TAG, 'at_utc': '2026-11-08T09:27:00Z',
            'e32': {'control_phase': 'taken_over', 'default_password': k('default_end', False)},
            'checks': ind_checks, 'passed': all(v is True for n, v in ind_checks.items() if n != 'settings_detail')})
        files = sorted(p for p in self.ind.rglob('*') if p.is_file())
        acc.save(self.ind / 'INDEPENDENT-MANIFEST.json', {'schema': 1, 'kind': 'independent_postcheck', 'files': [
            {'file': p.relative_to(self.ind).as_posix(), 'sha256': acc.file_digest(p)} for p in files]})
        acc.save(self.ci, {'commit': SOURCE, 'runs': [{'id': 1, 'name': 'PlatformIO CI', 'head_branch': acc.TAG,
                                                      'event': 'push', 'status': 'completed',
                                                      'conclusion': k('ci', 'success'), 'html_url': 'x',
                                                      'created_at': '2026-11-08T08:30:00Z'}]})

    def observation(self, folder, run, base_states, base_diag, pre_states, pre_diag, base_entries, backup):
        k = self.get
        folder.mkdir()
        findings = []
        check = lambda name, ok, detail=None: findings.append({'check': name, 'ok': bool(ok), 'detail': detail})
        for name in ('github.release_is_the_capture_one', 'github.firmware_digest_and_size', 'github.descriptor'):
            check(name, True)
        now_states = acc.reduce_states(states(k('post_extra_states', ())))
        now_diag = {**acc.diagnostics_extract(diagnostics(k('post_version', acc.HA_VERSION), k('post_dup_groups', ()))),
                    'sha256': H('d2'), 'bytes': 1}
        now_entries = acc.entries_summary(entries(k('post_entry_count', 1)))
        check('ha.integration_version', acc.integration_version(now_diag) == acc.HA_VERSION)
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
        write_settings(folder / 'settings', after=True, export=run['export'])
        if k('settings_change', False):
            (folder / 'settings' / 'config-boiler.json').write_text(json.dumps({'max_flow': 75}) + '\n')
        export = ({'http_status': 200, 'compared': True, 'refusal': None} if run['export'] else
                  {'http_status': 403, 'compared': False, 'refusal': 'password_change_required'})
        differences, notes = acc.compare_settings(self.pre / 'backup', folder / 'settings', backup)
        check('e32.settings_programs_bindings_preserved', *acc.settings_finding(differences, notes, export, run['default']))
        text = mqtt_text(disconnects=k('disconnects', ((0, 0), (0, 0))))
        (folder / 'mqtt').mkdir()
        (folder / 'mqtt' / 'listen.txt').write_text(text)
        mqtt = acc.mqtt_evaluate(acc.parse_mqtt(text), 150)
        for name in ('availability_online', 'heartbeat_every_60s', 'heartbeat_counters_steady', 'boiler_fields_seen'):
            check('mqtt.' + name, mqtt[name])
        summary = acc.learned_summary(doc)
        acc.save(folder / 'OBSERVATION.json', {
            'schema': 1, 'kind': 'installer_post_observation', 'tag': acc.TAG, 'preinstall': str(self.pre),
            'observation': {'at_utc': run['at'], 'version': acc.TAG, 'boot_pending': False, 'uptime_seconds': run['uptime'],
                            'mqtt_counters': {'mqtt_stalled_disconnects': 0, 'mqtt_socket_error_disconnects': 0},
                            'control_phase': control['phase'], 'default_password': run['default'],
                            'export_http_status': export['http_status'], 'logout_http_status': 200},
            'install_actions': actions,
            'ha_entity': {'entity_id': acc.ENTITY, 'state': 'off', 'installed_version': acc.TAG, 'latest_version': acc.TAG,
                          'in_progress': False, 'last_install': last_install(k('uploads', 1))},
            'ha_core_version': '2026.10.4', 'ha_integration_version': acc.integration_version(now_diag),
            'ha_config_entries': now_entries, 'github_release': release(), 'firmware_sha256': FW, 'firmware_bytes': FW_BYTES,
            'control': control, 'export': export,
            'info': {'learned': {'summary': summary, 'fresh': acc.learned_fresh(summary)},
                     'ha_issues': acc.issue_flags(now_diag), 'ha_control_history': k('control_history', [])},
            'findings': findings, 'failed': [f['check'] for f in findings if not f['ok']]})
        acc.write_manifest(folder, 'OBS-MANIFEST.json', 'installer_post_observation')

    def receipt(self):
        ci = json.loads(self.ci.read_text())
        return writer.build(self.pre, self.obs, self.ind, ci)


def touched_places():
    """What the writer or the verifier import could change in the release worktree (no git: a check runs there)."""
    places = [WORKTREE / 'scripts', WORKTREE / 'docs' / 'modern-thermostat' / 'update-acceptance',
              WORKTREE / 'docs' / 'modern-thermostat' / 'E32-UPDATE-GATE.json']
    seen = {}
    for place in places:
        for path in ([place] if place.is_file() else place.rglob('*')):
            seen[str(path)] = path.stat().st_mtime_ns
    return seen


@unittest.skipUnless(VERIFIER.exists(), f'release worktree not found: {VERIFIER}')
class ReceiptAgainstGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        before = touched_places()
        cls.gate = writer.load_verifier(WORKTREE)
        assert before == touched_places(), 'loading the verifier changed the release worktree'

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='rc2-receipt-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fixture(self, **kw):
        return Fixture(self.tmp / 'captures', **kw)

    def assert_incomplete(self, record, *names):
        self.assertEqual(record['status'], 'INCOMPLETE')
        failing = [n for n, v in {**record['checks'], **record['rc2_checks']}.items() if v is not True]
        for name in names:
            self.assertIn(name, failing)
        return failing

    def test_pass_receipt_passes_the_gate(self):
        record, limits = self.fixture().receipt()
        self.assertEqual(record['status'], 'PASS', limits)
        self.assertEqual(sorted(record['checks']), sorted(self.gate.HA_REQUIRED))
        self.gate.home_assistant_acceptance(record)          # the function the gate calls
        self.gate.METHODS['home_assistant'](record)          # the same rule, through the method table
        self.assertTrue(record['rc2']['learned']['started_fresh'])
        self.assertTrue(record['rc2']['password']['own_password_at_end'])
        self.assertEqual(record['rc2']['takeover']['phases'], ['awaiting_reconfirm', 'reconfirmed'])
        # The whole gate on a throwaway root: accepted <- this receipt (digest-bound), no candidate.
        root = self.tmp / 'root'
        receipt = root / 'docs' / 'modern-thermostat' / 'update-acceptance' / 'e32-rc2-20261108.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_bytes((json.dumps(record, indent=2) + '\n').encode())
        policy = {'schema': 1, 'required_for_successor_release': True, 'pending_tag': None,
                  'accepted': {'tag': acc.TAG, 'receipt': receipt.relative_to(root).as_posix(),
                               'sha256': acc.file_digest(receipt)}}
        result = self.gate.verify(root, policy)
        self.assertEqual((result['result'], result['accepted']), ('PASS', acc.TAG))

    def test_frost_protection_while_waiting_is_safe(self):
        record, limits = self.fixture(phase1='frost').receipt()
        self.assertEqual(record['status'], 'PASS', limits)

    def test_writer_command_line_writes_only_receipt_out(self):
        fx = self.fixture()
        out = self.tmp / 'receipt.json'
        script = HERE / 'write_rc2_receipt.py'
        command = [sys.executable, '-I', str(script), '--repo', str(WORKTREE), '--preinstall', str(fx.pre),
                   '--obs', str(fx.obs[1]), '--obs', str(fx.obs[0]), '--independent', str(fx.ind),
                   '--ci-json', str(fx.ci), '--receipt-out', str(out)]
        before = touched_places()
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.gate.home_assistant_acceptance(json.loads(out.read_text(encoding='utf-8')))
        self.assertEqual(before, touched_places(), 'the writer changed the release worktree')
        dry = subprocess.run(command[:-2] + ['--dry-run'], capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('DRY RUN', dry.stdout)

    def test_no_reconfirmation_is_incomplete_and_the_gate_refuses_it(self):
        record, _ = self.fixture(phase2='awaiting', ind_takeover=False).receipt()
        self.assert_incomplete(record, 'takeover_reconfirmed', 'independent_postcheck_passed')
        root = self.tmp / 'root2'
        receipt = root / 'r.json'
        root.mkdir()
        receipt.write_bytes(json.dumps(record).encode())
        with self.assertRaisesRegex(ValueError, 'Update not accepted'):
            self.gate.verify(root, {'schema': 1, 'required_for_successor_release': True, 'pending_tag': None,
                                    'accepted': {'tag': acc.TAG, 'receipt': 'r.json', 'sha256': acc.file_digest(receipt)}})

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

    def test_foreign_controller_after_restart(self):
        record, _ = self.fixture(phase1='foreign').receipt()
        self.assert_incomplete(record, 'control_state_safe_after_restart')

    def test_duplicate_entity_after_hacs(self):
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
        self.assert_incomplete(record, 'ha_migrated_with_one_entry')

    def test_wrong_integration_version(self):
        record, _ = self.fixture(post_version='1.0.0rc1').receipt()
        self.assert_incomplete(record, 'ha_migrated_with_one_entry')

    def test_baseline_taken_after_the_migration(self):
        record, _ = self.fixture(baseline_version=acc.HA_VERSION).receipt()
        self.assert_incomplete(record, 'ha_migrated_with_one_entry')

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

    def test_learned_not_fresh_is_a_limit_not_a_gate(self):
        record, limits = self.fixture(fresh=False).receipt()
        self.assertEqual(record['status'], 'PASS')
        self.assertFalse(record['rc2']['learned']['started_fresh'])
        self.assertTrue(any('starting fresh' in line for line in limits))

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
        self.assertTrue(acc.owned_before(heating('beta22_active')))

    def test_learned_fresh(self):
        self.assertTrue(acc.learned_fresh(acc.learned_summary(heating('awaiting', fresh=True))))
        self.assertFalse(acc.learned_fresh(acc.learned_summary(heating('awaiting', fresh=False))))
        self.assertFalse(acc.learned_fresh(acc.learned_summary(heating('beta22_active'))))  # no tuning block: not rc.2

    def test_integration_version_needs_both_fields(self):
        doc = diagnostics('1.0.0rc2')
        self.assertEqual(acc.integration_version(acc.diagnostics_extract(doc)), '1.0.0rc2')
        doc['custom_components']['open_thermostat']['version'] = '0.4.0b15'
        self.assertIsNone(acc.integration_version(acc.diagnostics_extract(doc)))
        self.assertIsNone(acc.integration_version(None))

    def test_issue_flags(self):
        flags = acc.issue_flags(acc.diagnostics_extract(diagnostics('1.0.0rc2', issues=[
            'e32_default_password_X', 'reconfirm_takeover_X'])))
        self.assertTrue(flags['default_password'] and flags['reconfirm_takeover'])
        no_list = diagnostics('1.0.0rc2')
        del no_list['issues']
        self.assertIsNone(acc.issue_flags(acc.diagnostics_extract(no_list)))

    def test_mqtt_evaluate(self):
        good = acc.mqtt_evaluate(acc.parse_mqtt(mqtt_text()), 150)
        self.assertTrue(all(good[k] for k in ('availability_online', 'heartbeat_every_60s', 'heartbeat_counters_steady',
                                              'boiler_fields_seen', 'heartbeat_uptime_rising')))
        self.assertEqual(good['detail']['state_heating_active'], {'state': 'active'})
        self.assertFalse(acc.mqtt_evaluate(acc.parse_mqtt(mqtt_text(beats=(36.9,))), 150)['heartbeat_every_60s'])
        self.assertFalse(acc.mqtt_evaluate(acc.parse_mqtt(mqtt_text(online=False)), 150)['availability_online'])

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

    @unittest.skipUnless((BETA22 / 'post2-20261031T141625Z' / 'mqtt' / 'listen.txt').exists(), 'no beta.22 capture')
    def test_real_beta22_capture_shapes(self):
        """The evaluators on the real beta.22 captures (read-only): MQTT lines and the settings comparison."""
        text = (BETA22 / 'post2-20261031T141625Z' / 'mqtt' / 'listen.txt').read_text(encoding='utf-8', errors='replace')
        result = acc.mqtt_evaluate(acc.parse_mqtt(text), 150)
        self.assertTrue(result['availability_online'] and result['heartbeat_every_60s'] and result['boiler_fields_seen'])
        pre = BETA22 / 'preinstall-20261031T140424Z'
        entries_ = json.loads((pre / 'backup' / 'BACKUP-MANIFEST.json').read_text(encoding='utf-8'))['files']
        differences, notes = acc.compare_settings(pre / 'backup', BETA22 / 'post2-20261031T141625Z' / 'settings', entries_)
        self.assertEqual(differences, [])
        self.assertTrue(notes['export_compared'])


class DryRuns(unittest.TestCase):
    def run_dry(self, script, *arguments):
        out = Path(tempfile.mkdtemp(prefix='rc2-dry-')) / 'never'
        result = subprocess.run([sys.executable, '-I', str(HERE / script), *arguments, '--out', str(out), '--dry-run'],
                                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.startswith('DRY RUN'), result.stdout)
        self.assertFalse(out.exists(), 'a dry run created its output folder')
        shutil.rmtree(out.parent, ignore_errors=True)
        return result.stdout

    def test_preinstall_baseline(self):
        text = self.run_dry('capture_rc2_preinstall.py', '--stage', 'ha-baseline')
        self.assertIn('no E32 contact', text)
        self.assertNotIn('E32 POST', text)

    def test_preinstall_e32(self):
        text = self.run_dry('capture_rc2_preinstall.py', '--stage', 'e32', '--baseline', 'X')
        self.assertIn('POST /config/backup', text)
        self.assertIn('POST /auth/logout', text)

    def test_post(self):
        text = self.run_dry('capture_rc2_post.py', '--preinstall', 'X', '--mqtt-user', 'u')
        self.assertIn('MQTT subscribe', text)

    def test_independent(self):
        text = self.run_dry('capture_rc2_independent.py')
        self.assertIn('/auth/logout', text)


if __name__ == '__main__':
    unittest.main()
