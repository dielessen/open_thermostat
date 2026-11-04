"""prepare_rc5.py on a throwaway copy of the files it touches (never on the real tree).

    python3 -I -m unittest discover -s tools/dev -p "test_*.py" -v

The tree is synthetic (rc.4 / 1.0.0rc5 files with the strings the script rewrites); the repository's own
scripts/organize_releases.py and scripts/verify_e32_update_gate.py are copied in, so the end result is judged by the
real publication-notes check and the real update gate, and install-config.json by the acceptance kit's own loader.
Every test runs twice: with the five versioned frontend URL files of the real integration, and with a sixth card
added (the script finds the URLs, it does not list them). RealTreeRehearsal prepares copies of this repository's own
files while the real tree is still at rc.4, so the version commit is rehearsed with the real notes skeletons, the
real planning record and the real card files; it is skipped once the tree has been prepared.
"""
import argparse
import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'tools' / 'acceptance'))
import acceptance  # noqa: E402  the acceptance kit's own configuration loader
import prepare_rc5 as prep  # noqa: E402
import test_verify_e32_update_gate as gate_fixtures  # noqa: E402

HA = 'ha/config/custom_components/open_thermostat'
DOCS = 'docs/modern-thermostat'
BETA22 = 'v0.1.0-e32v2-beta.22'
DATE = '20261110'
OLD, NEW = '1.0.0rc5', '1.0.0rc6'

E32_NOTES = """# E32 V2 1.0.0-rc.5 — the fifth 1.0 candidate: a fixture
<!-- user-release-notes:v2:en -->

Fixture introduction.

## New

- Something new.

## Fixed

- Something fixed.

## Updating

From rc.4, first HA 1.0.0rc6 through HACS, then Install on the Firmware entity.

## Limitations

None worth listing.
"""
HA_NOTES = E32_NOTES.replace('# E32 V2 1.0.0-rc.5 — the fifth 1.0 candidate: a fixture', '# HA 1.0.0rc6 — the companion of E32 rc.5')
OLD_E32 = '# E32 V2 1.0.0-rc.4 — the fourth 1.0 candidate\n<!-- user-release-notes:v2:en -->\n\nOld notes.\n'
OLD_HA = '# HA 1.0.0rc5 — holidays, yesterday in figures\n<!-- user-release-notes:v2:en -->\n\nOld notes.\n'
SKELETON = E32_NOTES.replace('Fixture introduction.', '<!-- pending: the docs package replaces this introduction -->')
CHANGES = {'changes': ['The first change, in plain words.', 'The second change.']}

# The versioned frontend URLs of the real integration: six URLs in five files, naming four served files (two of them
# cards). {v} is the HA version. The legacy URL and the test URL of another version must stay as they are.
URL_FILES = {
    f'{HA}/e32_week.py': 'CARD_URL = "/open_thermostat/e32-week-card-{v}.js"\nEDITOR_URL = "/open_thermostat/week-editor-{v}.js"\n',
    f'{HA}/frontend/e32-week-card.js': "const EDITOR = '/open_thermostat/week-editor-{v}.js';\n",
    f'{HA}/room_overview.py': 'CARD_URL = "/open_thermostat/room-status-card-{v}.js"\n',
    f'{HA}/week_planner.py': 'URL = "/open_thermostat/week-planner-{v}.js"\nLEGACY_URLS = ("/open_thermostat/week-planner-0.4.0b4.js",)\n',
    'test/week-editor-browser.cjs': "if(p==='/open_thermostat/week-editor-{v}.js')return 1;\nconst outdated='/open_thermostat/e32-week-card-0.0.0.js';\n",
}
FRONTEND_FILES = ('e32-week-card.js', 'room-status-card.js', 'week-editor.js', 'week-planner.js')
# A sixth card, as the heating curve card may come: its file in the frontend folder, the module that serves it and the
# browser test that routes it.
SIXTH_URL_FILES = {
    f'{HA}/heating_curve.py': 'CARD_URL = "/open_thermostat/heating-curve-card-{v}.js"\n',
    'test/heating-curve-card-browser.cjs': "if(p==='/open_thermostat/heating-curve-card-{v}.js')return 2;\n",
}

RC4_PLAN = {
    'schema': 1, 'date': '2026-11-04', 'planned_tag': 'v1.0.0-e32v2-rc.4', 'previous_published_tag': 'v1.0.0-e32v2-rc.3',
    'state': 'FROZEN_AWAITING_EXACT_TAG_CI', 'formal_freeze': True, 'published': True, 'installed': True,
    'github_prerelease': True, 'ha_tag': 'ha-v1.0.0rc5', 'ha_installed': True, 'install_together': True,
    'install_order': ['ha-v1.0.0rc5 (HACS)'], 'observed_installed_e32': 'v1.0.0-e32v2-rc.3',
    'observed_installed_ha': '1.0.0rc4', 'active_control_since': '2026-11-01T20:05Z', 'publication_condition': 'x',
    'owner_instruction': f'{DOCS}/RC4-OWNER-INSTRUCTION-20261104.json',
    'publication_exception': f'{DOCS}/RC4-PUBLICATION-EXCEPTION-20261104.json',
    'last_accepted_native_e32': 'v0.1.0-e32v2-beta.4', 'predecessor_acceptance': {'tag': BETA22},
    'planned_acceptance': {'method': 'home_assistant', 'receipt': f'{DOCS}/update-acceptance/e32-rc4-<YYYYMMDD>.json'},
    'release_notes': {'e32': f'{DOCS}/RELEASE-NOTES.md (# E32 V2 1.0.0-rc.4)', 'ha': f'{DOCS}/HA-RELEASE-NOTES.md (# HA 1.0.0rc5)'},
    'changes': ['old'], 'not_included': ['old'], 'software_validation': {'physical_test_performed': False},
    'active_gate_open_in_build': True, 'physical_outputs_automatically_enabled': False,
    'radiator_valve_control_default_on': False, 'persistent_boiler_setting_writes_enabled': False,
    'full_ten_minute_physical_success_claimed': False, 'native_https_root_cause_fixed': False}
INSTALL_CONFIG = {
    'comment': 'The release and the installation the acceptance scripts work on.',
    'tag': 'v1.0.0-e32v2-rc.4', 'previous_tag': 'v1.0.0-e32v2-rc.3', 'ha_version': '1.0.0rc5', 'ha_previous_version': '1.0.0rc4',
    'entity_id': 'update.e32_firmware', 'ha_url': 'https://192.168.1.10:8123', 'e32_url': 'http://192.168.1.20',
    'mqtt_prefix': 'ib-therm'}
INSTALL_STEPS = ('# Installatie met vastlegging: stappen\n\n'
                 'Deze stappen gelden voor de release in `install-config.json` (nu E32 **v1.0.0-e32v2-rc.4** met HA\n'
                 '**1.0.0rc5**, vanaf rc.3 en 1.0.0rc4). De opdrachten staan in [README.md](README.md).\n\n'
                 '3. Klap **Need a different version?** open en kies de versie uit `install-config.json` (nu **1.0.0rc5**).\n'
                 '2. Controleer dat er de geplande versie staat (nu **v1.0.0-e32v2-rc.4**).\n')


def lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


def tree_snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob('*')) if p.is_file()}


def python(root, script, *arguments):
    """A script of the throwaway tree, run the way CI runs it (isolated, UTF-8 whatever the console says)."""
    return subprocess.run([sys.executable, '-I', '-X', 'utf8', '-B', str(root / script), *arguments], capture_output=True,
                          text=True, encoding='utf-8')


def published_catalog(directory, *tags):
    path = Path(directory) / 'published.json'
    path.write_text(json.dumps(list(tags)), encoding='utf-8')
    return path


PUBLISHED = ('v0.1.0-e32v2-beta.22', 'v1.0.0-e32v2-rc.1', 'v1.0.0-e32v2-rc.2', 'v1.0.0-e32v2-rc.3', 'v1.0.0-e32v2-rc.4')


class PrepareTests(unittest.TestCase):
    SIXTH = False  # the subclass below adds a sixth card

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'tree'
        self.build_tree()
        self.changes = Path(self.temp.name) / 'changes.json'
        lf(self.changes, json.dumps(CHANGES))

    def url_files(self, version=OLD):
        files = {**URL_FILES, **(SIXTH_URL_FILES if self.SIXTH else {})}
        return {name: text.replace('{v}', version) for name, text in files.items()}

    def build_tree(self):
        root = self.root
        for name in ('organize_releases.py', 'verify_e32_update_gate.py'):
            (root / 'scripts').mkdir(parents=True, exist_ok=True)
            (root / 'scripts' / name).write_bytes((REPO / 'scripts' / name).read_bytes())
        lf(root / 'release.json', '{\n  "version": "v1.0.0-e32v2-rc.4",\n  "board": "bbqkees_e32v2"\n}\n')
        lf(root / HA / 'manifest.json', '{\n  "domain": "open_thermostat",\n  "version": "1.0.0rc5"\n}\n')
        for name in FRONTEND_FILES + (('heating-curve-card.js',) if self.SIXTH else ()):
            lf(root / HA / 'frontend' / name, f'// {name}\n')
        for name, text in self.url_files().items():
            lf(root / name, text)
        lf(root / DOCS / 'RELEASE-NOTES.md', OLD_E32)
        lf(root / DOCS / 'HA-RELEASE-NOTES.md', OLD_HA)
        lf(root / prep.DEFAULT_E32_NOTES, E32_NOTES)
        lf(root / prep.DEFAULT_HA_NOTES, HA_NOTES)
        receipt = gate_fixtures.ha_record(BETA22, 'v0.1.0-e32v2-beta.21')
        raw = (json.dumps(receipt, indent=2) + '\n').encode()
        lf(root / DOCS / 'update-acceptance/e32-beta22-20261031.json', raw.decode())
        lf(root / prep.PLAN_TEMPLATE, json.dumps(RC4_PLAN, indent=2) + '\n')
        lf(root / DOCS / 'RC4-PUBLICATION-EXCEPTION-20261104.json', json.dumps({'schema': 1, 'status': 'APPROVED'}, indent=2) + '\n')
        gate = {'schema': 1, 'required_for_successor_release': True,
                'accepted': {'tag': BETA22, 'receipt': f'{DOCS}/update-acceptance/e32-beta22-20261031.json',
                             'sha256': hashlib.sha256(raw).hexdigest()},
                'pending_tag': 'v1.0.0-e32v2-rc.4', 'candidate_plan': prep.PLAN_TEMPLATE,
                'publication_exception': {'receipt': f'{DOCS}/RC4-PUBLICATION-EXCEPTION-20261104.json', 'sha256': '0' * 64}}
        lf(root / prep.GATE, json.dumps(gate, indent=2) + '\n')
        lf(root / prep.ACCEPTANCE_CONFIG, json.dumps(INSTALL_CONFIG, indent=2) + '\n')
        lf(root / prep.INSTALL_STEPS, INSTALL_STEPS)

    def snapshot(self):
        return tree_snapshot(self.root)

    def read(self, name):
        return (self.root / name).read_text(encoding='utf-8')

    def run_prepare(self, *extra, check=True):
        """The output of the run; with check=False the run must be refused, and the refusal text is returned."""
        arguments = [str(self.root), '--date', DATE, '--changes-file', str(self.changes), *extra]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            if check:
                prep.main(arguments)
                return out.getvalue()
            with self.assertRaises(prep.Refusal) as caught:
                prep.main(arguments)
        return str(caught.exception)

    def run_rebind(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            prep.main([str(self.root), '--rebind'])
        return out.getvalue()

    def gate(self, candidate=prep.E32_TAG, published=None):
        extra = ['--published-file', str(published)] if published else ['--offline']
        return python(self.root, 'scripts/verify_e32_update_gate.py', '--candidate', candidate, *extra)

    def names(self):
        return {'gap': f'{DOCS}/RC4-UPDATE-GAP-{DATE}.json', 'exception': f'{DOCS}/RC5-PUBLICATION-EXCEPTION-{DATE}.json',
                'owner': f'{DOCS}/RC5-OWNER-INSTRUCTION-{DATE}.json', 'plan': prep.PLAN}

    # ---- the content of the version commit ---------------------------------------------------------------------

    def test_the_template_has_the_fields_the_script_knows(self):
        self.assertEqual(set(RC4_PLAN), set(prep.RELEASE_FIELDS) | set(prep.CARRIED_FIELDS))
        self.assertFalse(set(prep.RELEASE_FIELDS) & set(prep.CARRIED_FIELDS))

    def test_the_version_commit_content(self):
        before = self.snapshot()
        self.run_prepare()
        changed = sorted(name for name, data in self.snapshot().items() if before.get(name) != data)
        names = self.names()
        expected = {'release.json', f'{HA}/manifest.json', f'{DOCS}/RELEASE-NOTES.md', f'{DOCS}/HA-RELEASE-NOTES.md', prep.GATE,
                    prep.ACCEPTANCE_CONFIG, prep.INSTALL_STEPS, *self.url_files(), *names.values()}
        self.assertEqual(changed, sorted(expected))
        self.assertEqual(len(changed), 18 if self.SIXTH else 16)
        self.assertIn('"version": "v1.0.0-e32v2-rc.5"', self.read('release.json'))
        self.assertIn('"version": "1.0.0rc6"', self.read(f'{HA}/manifest.json'))
        for name, text in self.url_files().items():
            self.assertEqual(self.read(name), text.replace(f'-{OLD}.js', f'-{NEW}.js'), name)
            self.assertNotIn(OLD, self.read(name), name)
        self.assertEqual(self.read(f'{HA}/e32_week.py').count(f'-{NEW}.js'), 2)
        self.assertIn('week-planner-0.4.0b4.js', self.read(f'{HA}/week_planner.py'), 'the legacy URL stays')
        self.assertIn('e32-week-card-0.0.0.js', self.read('test/week-editor-browser.cjs'), 'a URL of another version stays')
        self.assertTrue(self.read(f'{DOCS}/RELEASE-NOTES.md').startswith(E32_NOTES.rstrip('\n') + '\n\n' + OLD_E32))
        self.assertTrue(self.read(f'{DOCS}/HA-RELEASE-NOTES.md').startswith(HA_NOTES.rstrip('\n') + '\n\n' + OLD_HA))
        for name in changed:
            self.assertNotIn(b'\r', (self.root / name).read_bytes(), name + ' has CRLF')

    def test_the_planning_record_sets_every_release_field_and_carries_the_fixed_flags(self):
        self.run_prepare()
        plan = json.loads(self.read(prep.PLAN))
        self.assertEqual(set(plan), set(RC4_PLAN))
        self.assertEqual((plan['planned_tag'], plan['previous_published_tag'], plan['ha_tag']),
                         ('v1.0.0-e32v2-rc.5', 'v1.0.0-e32v2-rc.4', 'ha-v1.0.0rc6'))
        self.assertEqual((plan['observed_installed_e32'], plan['observed_installed_ha']), ('v1.0.0-e32v2-rc.4', '1.0.0rc5'))
        self.assertEqual((plan['state'], plan['published'], plan['installed'], plan['ha_installed']),
                         ('FROZEN_AWAITING_EXACT_TAG_CI', False, False, False))
        self.assertEqual(plan['date'], '2026-11-10')
        self.assertEqual(plan['changes'], CHANGES['changes'])
        self.assertEqual(plan['not_included'], prep.NOT_INCLUDED)
        self.assertNotIn('the room heat-loss house model (1.1)', plan['not_included'], 'the house model is part of rc.5')
        self.assertEqual(plan['owner_instruction'], f'{DOCS}/RC5-OWNER-INSTRUCTION-{DATE}.json')
        self.assertEqual(plan['publication_exception'], f'{DOCS}/RC5-PUBLICATION-EXCEPTION-{DATE}.json')
        self.assertEqual(plan['predecessor_acceptance']['tag'], BETA22)
        self.assertEqual(plan['planned_acceptance']['receipt'], f'{DOCS}/update-acceptance/e32-rc5-<YYYYMMDD>.json')
        self.assertEqual(plan['release_notes'], {'e32': f'{DOCS}/RELEASE-NOTES.md (# E32 V2 1.0.0-rc.5)',
                                                 'ha': f'{DOCS}/HA-RELEASE-NOTES.md (# HA 1.0.0rc6)'})
        self.assertEqual(plan['install_order'][0], 'ha-v1.0.0rc6 (HACS, then a Home Assistant restart)')
        self.assertTrue(plan['install_order'][1].startswith('v1.0.0-e32v2-rc.5 (Home Assistant Firmware update entity'))
        for key in prep.CARRIED_FIELDS:
            self.assertEqual(plan[key], RC4_PLAN[key], key)
        self.assertIn('unaccepted rc.4', plan['publication_condition'])

    def test_the_changes_file_may_bring_its_own_not_included_list(self):
        lf(self.changes, json.dumps({'changes': ['One change.'], 'not_included': ['The weather forecast (after 1.0)']}))
        self.run_prepare()
        plan = json.loads(self.read(prep.PLAN))
        self.assertEqual((plan['changes'], plan['not_included']), (['One change.'], ['The weather forecast (after 1.0)']))

    def test_the_drafts_may_be_somewhere_else(self):
        lf(self.root / 'docs/other-e32.md', E32_NOTES)
        lf(self.root / 'docs/other-ha.md', HA_NOTES)
        (self.root / prep.DEFAULT_E32_NOTES).unlink()
        (self.root / prep.DEFAULT_HA_NOTES).unlink()
        self.run_prepare('--e32-notes', 'docs/other-e32.md', '--ha-notes', 'docs/other-ha.md')
        self.assertTrue(self.read(f'{DOCS}/RELEASE-NOTES.md').startswith(E32_NOTES.rstrip('\n') + '\n\n' + OLD_E32))

    def test_nothing_of_the_rc4_records_is_left_in_the_rc5_records(self):
        self.run_prepare()
        names = self.names()
        for name in (*names.values(), prep.GATE, prep.ACCEPTANCE_CONFIG):
            text = self.read(name)
            for stale in prep.STALE:
                self.assertNotIn(stale, text, f'{name} keeps {stale}')
        # the previous release is named where it belongs
        self.assertEqual(json.loads(self.read(names['gap']))['candidate_tag'], 'v1.0.0-e32v2-rc.4')
        self.assertEqual(json.loads(self.read(names['exception']))['unaccepted_predecessor'], 'v1.0.0-e32v2-rc.4')

    def test_the_update_gap_report_says_what_happened_to_rc4(self):
        self.run_prepare()
        gap = json.loads(self.read(self.names()['gap']))
        self.assertEqual((gap['status'], gap['candidate_tag'], gap['installed_tag'], gap['last_accepted']),
                         ('INCOMPLETE', 'v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2-rc.4', BETA22))
        self.assertEqual((gap['install_route'], gap['installed_at_utc']), ('home_assistant_update_entity', '2026-11-04T13:38:00Z'))
        self.assertEqual((gap['native_install_commands'], gap['manual_upload_commands']), (0, 0))
        self.assertEqual((gap['acceptance_receipt'], gap['acceptance_receipt_status']), (None, 'NOT_CAPTURED'))
        self.assertIn('4 Nov 2026 at 13:38 UTC', gap['manual_result'])
        self.assertIn('no pre-install capture', gap['manual_result'])
        self.assertEqual(gap['date'], '2026-11-10')

    def test_the_gate_judges_the_prepared_tree_against_the_published_releases(self):
        statement = Path(self.temp.name) / 'statement.txt'
        lf(statement, 'Yes.\n')
        self.run_prepare('--statement-file', str(statement), '--approved-at-utc', '2026-11-10T09:30:00Z')
        passed = self.gate(published=published_catalog(self.temp.name, *PUBLISHED))
        self.assertEqual(passed.returncode, 0, passed.stderr)
        result = json.loads(passed.stdout)
        self.assertEqual((result['publication_basis'], result['previous_published_checked']),
                         ('operator_approved_one_time_exception', True))
        # rc.4 is the highest published release below rc.5: a catalog without it names rc.3, and the gate refuses
        missing = self.gate(published=published_catalog(self.temp.name, *PUBLISHED[:-1]))
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('previous_published_tag is v1.0.0-e32v2-rc.4, but the latest published release below '
                      'v1.0.0-e32v2-rc.5 is v1.0.0-e32v2-rc.3', missing.stderr)

    # ---- the exception and the owner's words -------------------------------------------------------------------

    def test_the_exception_is_a_draft_the_gate_refuses_until_the_owner_has_answered(self):
        self.run_prepare()
        exception_path = self.root / self.names()['exception']
        exception = json.loads(exception_path.read_text(encoding='utf-8'))
        self.assertEqual((exception['status'], exception['approval']), ('DRAFT_NOT_APPROVED', None))
        self.assertEqual((exception['candidate_tag'], exception['unaccepted_predecessor'], exception['accepted_basis_tag']),
                         ('v1.0.0-e32v2-rc.5', 'v1.0.0-e32v2-rc.4', BETA22))
        self.assertEqual(exception['gap_report'], self.names()['gap'])
        self.assertEqual(exception['gap_report_sha256'], hashlib.sha256((self.root / exception['gap_report']).read_bytes()).hexdigest())
        self.assertIs(exception['device_installation_authorized'], False)
        self.assertIs(exception['boiler_trial_authorized'], False)
        self.assertIn('rc.4 is installed and runs', exception['reason'])
        self.assertIn('Publish this one rc.5 pre-release', exception['reason'])
        refused = self.gate()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('no explicit approval', refused.stderr)
        # The owner answers: status and approval by hand, then the hash chain is redone, nothing else changes.
        exception['status'] = 'APPROVED'
        exception['approval'] = {'actor': 'repository_owner', 'method': 'explicit_user_instruction',
                                 'decision': 'approve_one_prerelease_publication', 'statement': 'Yes, publish rc.5.',
                                 'at_utc': '2026-11-10T09:30:00Z'}
        exception_path.write_bytes((json.dumps(exception, indent=2) + '\n').encode())
        stale = self.gate()
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn('publication exception changed', stale.stderr)
        before = self.snapshot()
        self.assertIn('the exception is approved by the owner', self.run_rebind())
        changed = sorted(name for name, data in self.snapshot().items() if before.get(name) != data)
        self.assertEqual(changed, [prep.GATE], 'only the digest of the exception in the gate changes')
        passed = self.gate()
        self.assertEqual(passed.returncode, 0, passed.stderr)
        result = json.loads(passed.stdout)
        self.assertEqual(result['publication_basis'], 'operator_approved_one_time_exception')
        self.assertEqual(result['pending'], prep.E32_TAG)

    def test_rebind_follows_an_edited_gap_report_through_exception_and_gate(self):
        statement = Path(self.temp.name) / 'statement.txt'
        lf(statement, 'Yes.\n')
        self.run_prepare('--statement-file', str(statement), '--approved-at-utc', '2026-11-10T09:30:00Z')
        gap_path = self.root / self.names()['gap']
        gap = json.loads(gap_path.read_text(encoding='utf-8'))
        gap['manual_result'] += ' The owner added a detail.'
        gap_path.write_bytes((json.dumps(gap, indent=2) + '\n').encode())
        self.assertIn('evidence-gap report changed', self.gate().stderr)
        before = self.snapshot()
        self.run_rebind()
        changed = sorted(name for name, data in self.snapshot().items() if before.get(name) != data)
        self.assertEqual(changed, [prep.GATE, self.names()['exception']])
        self.assertEqual(self.gate().returncode, 0)

    def test_rebind_says_when_the_owner_has_not_answered(self):
        self.run_prepare()
        self.assertIn('NOT yet approved by the owner', self.run_rebind())

    def test_rebind_refuses_the_exception_of_another_candidate(self):
        self.run_prepare()
        path = self.root / self.names()['exception']
        exception = json.loads(path.read_text(encoding='utf-8'))
        exception['candidate_tag'] = 'v1.0.0-e32v2-rc.4'
        path.write_bytes((json.dumps(exception, indent=2) + '\n').encode())
        before = self.snapshot()
        with self.assertRaisesRegex(prep.Refusal, 'is the exception of v1.0.0-e32v2-rc.4, not of v1.0.0-e32v2-rc.5'):
            prep.main([str(self.root), '--rebind'])
        self.assertEqual(self.snapshot(), before)

    def test_rebind_needs_a_prepared_tree(self):
        with self.assertRaisesRegex(prep.Refusal, 'has no v1.0.0-e32v2-rc.5 publication exception to rebind'):
            prep.main([str(self.root), '--rebind'])

    def test_the_owners_words_given_at_the_start_make_an_approved_exception(self):
        statement = Path(self.temp.name) / 'statement.txt'
        lf(statement, 'Ja, publiceer rc.5 als eenmalige uitzondering.\n')
        self.run_prepare('--statement-file', str(statement), '--approved-at-utc', '2026-11-10T09:30:00Z')
        exception = json.loads(self.read(self.names()['exception']))
        self.assertEqual(exception['status'], 'APPROVED')
        self.assertEqual(exception['approval']['statement'], 'Ja, publiceer rc.5 als eenmalige uitzondering.')
        result = self.gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['publication_basis'], 'operator_approved_one_time_exception')

    def test_the_owner_request_is_recorded_verbatim_and_no_approval_is_invented(self):
        request = Path(self.temp.name) / 'request.txt'
        lf(request, "Owner, 4 Nov: 'ik wil top of the build self learning voor de 1.0 erin hebben zitten'\n")
        self.run_prepare('--owner-request-file', str(request))
        owner = json.loads(self.read(self.names()['owner']))
        self.assertEqual(owner['requests'], ["Owner, 4 Nov: 'ik wil top of the build self learning voor de 1.0 erin hebben zitten'"])
        self.assertEqual((owner['publication_approval_reply'], owner['publication_approval_at_utc'],
                          owner['installation_approval_reply']), (None, None, None))
        self.assertIn('v1.0.0-e32v2-rc.5 + HA ha-v1.0.0rc6', owner['scope'])
        self.assertIn('14 days', owner['scope'])

    def test_the_owner_without_a_request_file_is_told_so(self):
        self.assertIn('no --owner-request-file', self.run_prepare())
        self.assertEqual(json.loads(self.read(self.names()['owner']))['requests'], [])

    def test_the_owners_own_words_are_quoted_not_judged(self):
        request, statement = Path(self.temp.name) / 'request.txt', Path(self.temp.name) / 'statement.txt'
        lf(request, 'Owner: the RC4-OWNER-INSTRUCTION-20261104.json stays as it is, rc4 is installed.\n')
        lf(statement, 'Yes, as in RC4-PUBLICATION-EXCEPTION-20261104.json.\n')
        self.run_prepare('--owner-request-file', str(request), '--statement-file', str(statement),
                         '--approved-at-utc', '2026-11-10T09:30:00Z')
        self.assertIn('RC4-OWNER-INSTRUCTION-20261104.json', self.read(self.names()['owner']))
        self.assertIn('RC4-PUBLICATION-EXCEPTION-20261104.json', self.read(self.names()['exception']))
        self.assertEqual(self.gate().returncode, 0)

    # ---- everything or nothing ---------------------------------------------------------------------------------

    def test_nothing_is_written_when_a_check_fails(self):
        before = self.snapshot()
        lf(self.root / prep.DEFAULT_HA_NOTES, HA_NOTES.replace('## Limitations', '## Limits'))
        broken = self.snapshot()
        self.assertIn('not a valid publication note', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), broken)
        lf(self.root / prep.DEFAULT_HA_NOTES, HA_NOTES + '\n<!-- pending -->\n')
        self.assertIn('pending', self.run_prepare(check=False))
        lf(self.root / prep.DEFAULT_HA_NOTES, HA_NOTES)
        lf(self.root / prep.DEFAULT_E32_NOTES, E32_NOTES.replace('# E32 V2 1.0.0-rc.5', '# E32 V2 1.0.0-rc.6'))
        self.assertIn('not a valid publication note', self.run_prepare(check=False))
        lf(self.root / prep.DEFAULT_E32_NOTES, E32_NOTES)
        self.assertEqual(self.snapshot(), before)
        lf(self.changes, json.dumps({'changes': []}))
        self.assertIn('at least one change', self.run_prepare(check=False))
        lf(self.changes, json.dumps({'changes': ['see RC4-OWNER-INSTRUCTION-20261104.json']}))
        self.assertIn('keep strings of the rc.4 records', self.run_prepare(check=False))
        lf(self.changes, json.dumps({'changes': ['the rc.4 plan RC4-KANDIDAAT.json said so']}))
        self.assertIn('the planning record would keep strings of the rc.4 records', self.run_prepare(check=False))
        lf(self.changes, json.dumps({'changes': ['an old pair, e32-rc4-20261104.json']}))
        self.assertIn('keep strings of the rc.4 records', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_a_missing_draft_is_refused_with_a_reason(self):
        (self.root / prep.DEFAULT_E32_NOTES).unlink()
        before = self.snapshot()
        self.assertIn('does not exist (the docs package writes', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_a_tree_that_is_not_at_rc4_or_is_prepared_already_is_refused(self):
        self.run_prepare()
        prepared = self.snapshot()
        self.assertIn('does not have', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), prepared)
        lf(self.root / 'release.json', '{\n  "version": "v1.0.0-e32v2-rc.3"\n}\n')
        lf(self.root / prep.GATE, json.dumps({**json.loads(self.read(prep.GATE)), 'pending_tag': prep.E32_PREVIOUS}))
        self.assertIn('release.json is not at', self.run_prepare(check=False))

    def test_a_manifest_that_is_not_at_the_previous_version_is_refused(self):
        lf(self.root / HA / 'manifest.json', '{\n  "version": "1.0.0rc4"\n}\n')
        before = self.snapshot()
        self.assertIn('manifest.json is not at 1.0.0rc5', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        out = self.run_prepare('--dry-run')
        self.assertEqual(self.snapshot(), before)
        self.assertIn('DRY RUN: would write', out)
        self.assertNotIn('next:', out)
        self.assertNotIn('prepared', out)

    def test_existing_records_are_never_overwritten(self):
        for name in self.names().values():
            with self.subTest(name):
                lf(self.root / name, '{}\n')
                before = self.snapshot()
                self.assertIn('exists already', self.run_prepare(check=False))
                self.assertEqual(self.snapshot(), before)
                (self.root / name).unlink()

    def test_the_output_names_the_next_steps_and_the_urls_it_moved(self):
        out = self.run_prepare()
        self.assertIn('prepared v1.0.0-e32v2-rc.5 and ha-v1.0.0rc6', out)
        self.assertIn('next: python3 -B scripts/verify_e32_update_gate.py --candidate v1.0.0-e32v2-rc.5', out)
        self.assertIn('tools/dev/refresh_beta19_inventory.py . --apply', out)
        urls, files = (8, 7) if self.SIXTH else (6, 5)
        cards = 'cards: e32-week-card, heating-curve-card, room-status-card' if self.SIXTH else 'cards: e32-week-card, room-status-card'
        self.assertIn(f'frontend URLs: {urls} moved to -1.0.0rc6.js in {files} file(s)', out)
        self.assertIn(cards, out)

    # ---- placeholders: the skeleton the docs package replaces ----------------------------------------------------

    def test_a_draft_with_placeholders_is_refused_unless_a_rehearsal_says_so(self):
        lf(self.root / prep.DEFAULT_E32_NOTES, SKELETON)
        before = self.snapshot()
        self.assertIn('would be published', self.run_prepare(check=False))
        self.assertIn('would be published', self.run_prepare('--dry-run', check=False))
        self.assertEqual(self.snapshot(), before)
        out = self.run_prepare('--allow-placeholders', '--dry-run')
        self.assertIn('WARNING', out)
        self.assertIn('1 placeholder line(s) remain', out)
        self.assertEqual(self.snapshot(), before)
        out = self.run_prepare('--allow-placeholders')
        self.assertIn('never the version commit', out)
        self.assertIn('<!-- pending', self.read(f'{DOCS}/RELEASE-NOTES.md'))
        # a skeleton is still a valid publication note: the real check accepts its shape
        result = python(self.root, 'scripts/organize_releases.py', '--publication-notes-for', 'v1.0.0-e32v2-rc.5',
                        '--output', str(Path(self.temp.name) / 'notes.md'))
        self.assertEqual(result.returncode, 0, result.stderr)

    # ---- the frontend URLs are found, not listed -----------------------------------------------------------------

    def test_the_real_publication_check_accepts_the_prepared_notes(self):
        self.run_prepare()
        for tag in ('v1.0.0-e32v2-rc.5', 'ha-v1.0.0rc6'):
            result = python(self.root, 'scripts/organize_releases.py', '--publication-notes-for', tag,
                            '--output', str(Path(self.temp.name) / f'{tag}.md'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['tag'], tag)

    def test_a_card_whose_url_was_not_there_stops_the_script(self):
        lf(self.root / HA / 'room_overview.py', 'CARD_URL = "/open_thermostat/room-status-card-1.0.0rc3.js"\n')
        before = self.snapshot()
        self.assertIn('room-status-card.js has no versioned URL', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_a_card_file_without_any_versioned_url_stops_the_script(self):
        lf(self.root / HA / 'frontend' / 'ghost-card.js', '// a card that nobody serves under a versioned URL\n')
        before = self.snapshot()
        message = self.run_prepare(check=False)
        self.assertIn('ghost-card.js has no versioned URL', message)
        self.assertIn('/open_thermostat/ghost-card-1.0.0rc5.js', message)
        self.assertEqual(self.snapshot(), before)

    def test_a_versioned_url_without_its_file_stops_the_script(self):
        lf(self.root / HA / 'ghost.py', 'URL = "/open_thermostat/ghost-card-1.0.0rc5.js"\n')
        before = self.snapshot()
        self.assertIn('ghost-card-1.0.0rc5.js in ' + HA + '/ghost.py has no ' + HA + '/frontend/ghost-card.js', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_a_name_that_ends_in_the_previous_version_but_is_no_url_stops_the_script(self):
        lf(self.root / HA / 'odd.py', 'NAME = "something-1.0.0rc5.js"\n')
        before = self.snapshot()
        self.assertIn('odd.py: 1 occurrence(s) of -1.0.0rc5.js are not an /open_thermostat/<file>-1.0.0rc5.js URL',
                      self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_a_tree_without_any_versioned_url_is_not_at_the_previous_version(self):
        for name in self.url_files():
            (self.root / name).unlink()
        self.assertIn('this tree is not at HA 1.0.0rc5', self.run_prepare(check=False))

    def test_files_that_carry_no_url_are_not_judged_and_a_url_file_must_be_lf(self):
        lf(self.root / 'test' / 'unrelated.cjs', 'line one\r\nline two\r\n')
        lf(self.root / 'ha/tests_native/test_other.py', '# no url here, and 1.0.0rc5 alone is no URL\r\n')
        self.run_prepare('--dry-run')
        lf(self.root / HA / 'room_overview.py', 'CARD_URL = "/open_thermostat/room-status-card-1.0.0rc5.js"\r\n')
        before = self.snapshot()
        self.assertIn('room_overview.py has CRLF line endings', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_files_of_the_native_tests_and_the_browser_tests_follow_too(self):
        lf(self.root / 'ha/tests_native/test_card.py', 'assert URL.endswith("/open_thermostat/week-planner-1.0.0rc5.js")\n')
        lf(self.root / 'test/tools/route.mjs', "route('/open_thermostat/room-status-card-1.0.0rc5.js')\n")
        lf(self.root / 'test/node_modules/dep/index.js', "x('/open_thermostat/week-planner-1.0.0rc5.js')\n")
        self.run_prepare()
        self.assertIn('week-planner-1.0.0rc6.js', self.read('ha/tests_native/test_card.py'))
        self.assertIn('room-status-card-1.0.0rc6.js', self.read('test/tools/route.mjs'))
        self.assertIn('1.0.0rc5.js', self.read('test/node_modules/dep/index.js'), 'vendored folders are left alone')

    def test_a_card_that_already_carries_the_new_version_needs_nothing(self):
        lf(self.root / HA / 'frontend' / 'new-card.js', '// a card whose author used the new version already\n')
        lf(self.root / HA / 'new.py', 'URL = "/open_thermostat/new-card-1.0.0rc6.js"\n')
        self.run_prepare()
        self.assertEqual(self.read(f'{HA}/new.py'), 'URL = "/open_thermostat/new-card-1.0.0rc6.js"\n')

    def test_the_sixth_card_is_found_when_it_is_there(self):
        out = self.run_prepare('--dry-run')
        self.assertEqual('heating-curve-card' in out, self.SIXTH)

    # ---- the planning record, the acceptance kit and the install steps ---------------------------------------------

    def test_a_planning_record_with_an_unknown_or_missing_field_stops_the_script(self):
        plan = {**RC4_PLAN, 'cleanup_done': True}
        lf(self.root / prep.PLAN_TEMPLATE, json.dumps(plan, indent=2) + '\n')
        before = self.snapshot()
        self.assertIn("unknown: ['cleanup_done']", self.run_prepare(check=False))
        plan = dict(RC4_PLAN)
        del plan['physical_outputs_automatically_enabled']
        lf(self.root / prep.PLAN_TEMPLATE, json.dumps(plan, indent=2) + '\n')
        before = self.snapshot()
        self.assertIn("missing: ['physical_outputs_automatically_enabled']", self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_the_acceptance_kit_gets_the_new_release_and_keeps_the_installation(self):
        before = json.loads(self.read(prep.ACCEPTANCE_CONFIG))
        self.run_prepare()
        text = self.read(prep.ACCEPTANCE_CONFIG)
        config = json.loads(text)
        self.assertEqual({key: config[key] for key in ('tag', 'previous_tag', 'ha_version', 'ha_previous_version')},
                         {'tag': 'v1.0.0-e32v2-rc.5', 'previous_tag': 'v1.0.0-e32v2-rc.4', 'ha_version': '1.0.0rc6',
                          'ha_previous_version': '1.0.0rc5'})
        self.assertEqual({k: v for k, v in config.items() if k not in before or before[k] != v},
                         {'tag': 'v1.0.0-e32v2-rc.5', 'previous_tag': 'v1.0.0-e32v2-rc.4', 'ha_version': '1.0.0rc6',
                          'ha_previous_version': '1.0.0rc5'}, 'only the four release keys change')
        self.assertEqual(list(config), list(before), 'the key order stays')
        self.assertEqual(text, json.dumps(config, indent=2, ensure_ascii=False) + '\n')
        # the kit's own loader accepts it, and derives the names the install uses
        cfg = acceptance.load_config(argparse.Namespace(config=str(self.root / prep.ACCEPTANCE_CONFIG)))
        self.assertEqual((cfg.tag, cfg.previous_tag, cfg.ha_version, cfg.ha_previous_version),
                         ('v1.0.0-e32v2-rc.5', 'v1.0.0-e32v2-rc.4', '1.0.0rc6', '1.0.0rc5'))
        self.assertEqual((cfg.ha_tag, cfg.hacs_tag, cfg.expect_prerelease), ('ha-v1.0.0rc6', '1.0.0rc6', True))
        self.assertEqual(acceptance.receipt_stem(cfg.tag), prep.RECEIPT_STEM)

    def test_an_acceptance_config_that_is_not_at_rc4_is_refused(self):
        lf(self.root / prep.ACCEPTANCE_CONFIG, json.dumps({**INSTALL_CONFIG, 'tag': 'v1.0.0-e32v2-rc.5'}, indent=2) + '\n')
        before = self.snapshot()
        self.assertIn('install-config.json is not at v1.0.0-e32v2-rc.4 / 1.0.0rc5', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_the_install_steps_name_the_new_pair(self):
        self.run_prepare()
        steps = self.read(prep.INSTALL_STEPS)
        self.assertEqual(steps, INSTALL_STEPS.replace('v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2-rc.5')
                         .replace('**1.0.0rc5**, vanaf rc.3 en 1.0.0rc4', '**1.0.0rc6**, vanaf rc.4 en 1.0.0rc5')
                         .replace('(nu **1.0.0rc5**)', '(nu **1.0.0rc6**)'))
        self.assertIn('(nu E32 **v1.0.0-e32v2-rc.5** met HA\n**1.0.0rc6**, vanaf rc.4 en 1.0.0rc5)', steps)

    def test_install_steps_that_name_the_new_pair_already_are_left_alone(self):
        current = (INSTALL_STEPS.replace('v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2-rc.5')
                   .replace('**1.0.0rc5**, vanaf rc.3 en 1.0.0rc4', '**1.0.0rc6**, vanaf rc.4 en 1.0.0rc5')
                   .replace('(nu **1.0.0rc5**)', '(nu **1.0.0rc6**)'))
        lf(self.root / prep.INSTALL_STEPS, current)
        before = self.snapshot()
        self.run_prepare()
        self.assertEqual(self.read(prep.INSTALL_STEPS), current)
        self.assertEqual(self.snapshot()[prep.INSTALL_STEPS], before[prep.INSTALL_STEPS])

    def test_install_steps_that_name_neither_pair_stop_the_script(self):
        lf(self.root / prep.INSTALL_STEPS, INSTALL_STEPS.replace('(nu **1.0.0rc5**)', '(nu **1.0.0rc9**)'))
        before = self.snapshot()
        self.assertIn("INSTALL-STEPS.nl.md: expected exactly one '(nu **1.0.0rc5**)', found 0", self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    # ---- the command line --------------------------------------------------------------------------------------

    def test_the_command_line_is_checked(self):
        cases = (['--date', '2026-11-10'], ['--statement-file', 'x'], ['--approved-at-utc', '2026-11-10T09:30:00Z'])
        for extra in cases:
            with self.subTest(extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                prep.main([str(self.root), '--changes-file', str(self.changes), *extra])
            self.assertEqual(caught.exception.code, 2)
        statement = Path(self.temp.name) / 'statement.txt'
        lf(statement, 'Yes.\n')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            prep.main([str(self.root), '--changes-file', str(self.changes), '--statement-file', str(statement),
                       '--approved-at-utc', '10 Nov 09:30'])
        self.assertEqual(caught.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            prep.main([str(self.root)])
        self.assertEqual(caught.exception.code, 2)
        lf(statement, 'x' * 2001)
        with self.assertRaisesRegex(prep.Refusal, 'owner.s words'):
            prep.main([str(self.root), '--changes-file', str(self.changes), '--statement-file', str(statement),
                       '--approved-at-utc', '2026-11-10T09:30:00Z'])


class PrepareWithASixthCardTests(PrepareTests):
    """The same tests with the heating curve card added: nothing in the script lists the cards."""
    SIXTH = True


REAL_FILES = ('release.json', f'{HA}/manifest.json', f'{DOCS}/RELEASE-NOTES.md', f'{DOCS}/HA-RELEASE-NOTES.md',
              prep.DEFAULT_E32_NOTES, prep.DEFAULT_HA_NOTES, prep.PLAN_TEMPLATE, prep.GATE, prep.ACCEPTANCE_CONFIG,
              prep.INSTALL_STEPS, 'scripts/organize_releases.py', 'scripts/verify_e32_update_gate.py')
REAL_DIRECTORIES = (HA, 'ha/tests_native', 'test')


def drafts_are_skeletons():
    """True while the real drafts still have the placeholder lines the docs package replaces."""
    return any(mark in (REPO / draft).read_text(encoding='utf-8') for draft in (prep.DEFAULT_E32_NOTES, prep.DEFAULT_HA_NOTES)
               for mark in prep.PLACEHOLDERS)


def real_tree_is_at_rc4():
    try:
        gate = json.loads((REPO / prep.GATE).read_text(encoding='utf-8'))
        release = json.loads((REPO / 'release.json').read_text(encoding='utf-8'))
        manifest = json.loads((REPO / HA / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return (gate.get('pending_tag'), release.get('version'), manifest.get('version')) == (
        prep.E32_PREVIOUS, prep.E32_PREVIOUS, prep.HA_PREVIOUS)


@unittest.skipUnless(real_tree_is_at_rc4(), 'the real tree has been prepared for rc.5 already (or is not at rc.4)')
class RealTreeRehearsal(unittest.TestCase):
    """The version commit on copies of this repository's own files: the real skeleton drafts, the real planning record,
    the real card files and the real acceptance kit, judged by the real gate, publication check and kit loader."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'tree'
        for name in REAL_FILES:
            (self.root / name).parent.mkdir(parents=True, exist_ok=True)
            (self.root / name).write_bytes((REPO / name).read_bytes())
        for name in REAL_DIRECTORIES:
            shutil.copytree(REPO / name, self.root / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', 'node_modules'))
        accepted = json.loads((REPO / prep.GATE).read_text(encoding='utf-8'))['accepted']['receipt']
        (self.root / accepted).parent.mkdir(parents=True, exist_ok=True)
        (self.root / accepted).write_bytes((REPO / accepted).read_bytes())
        self.changes = Path(self.temp.name) / 'changes.json'
        lf(self.changes, json.dumps(CHANGES))

    def old_url_files(self):
        """An independent look (no regular expression of the script): the files that carry a -1.0.0rc5.js name."""
        found = set()
        for directory, suffixes in prep.URL_SCAN:
            for path in (self.root / directory).rglob('*'):
                parts = set(path.relative_to(self.root).parts)
                if path.suffix in suffixes and path.is_file() and not {'__pycache__', 'node_modules'} & parts:
                    if f'-{OLD}.js'.encode() in path.read_bytes():
                        found.add(path.relative_to(self.root).as_posix())
        return found

    def test_the_real_tree_can_be_prepared_and_the_result_is_judged_by_the_real_checks(self):
        url_files = self.old_url_files()
        self.assertTrue(url_files, 'the real integration has versioned frontend URLs')
        before = tree_snapshot(self.root)
        if drafts_are_skeletons():  # the version commit does not take the skeletons: their lines would be published
            with self.assertRaisesRegex(prep.Refusal, 'still has pending or TODO markers'):
                prep.main([str(self.root), '--date', DATE, '--changes-file', str(self.changes)])
            self.assertEqual(tree_snapshot(self.root), before)
        statement = Path(self.temp.name) / 'statement.txt'
        lf(statement, 'A rehearsal statement; it exists only in this throwaway copy.\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            prep.main([str(self.root), '--date', DATE, '--changes-file', str(self.changes), '--statement-file', str(statement),
                       '--approved-at-utc', '2026-11-10T09:30:00Z', '--allow-placeholders'])
        after = tree_snapshot(self.root)
        changed = {name for name, data in after.items() if before.get(name) != data}
        names = {f'{DOCS}/RC4-UPDATE-GAP-{DATE}.json', f'{DOCS}/RC5-PUBLICATION-EXCEPTION-{DATE}.json',
                 f'{DOCS}/RC5-OWNER-INSTRUCTION-{DATE}.json', prep.PLAN}
        fixed = {'release.json', f'{HA}/manifest.json', f'{DOCS}/RELEASE-NOTES.md', f'{DOCS}/HA-RELEASE-NOTES.md', prep.GATE,
                 prep.ACCEPTANCE_CONFIG, prep.INSTALL_STEPS}
        self.assertEqual(changed, fixed | names | url_files)
        # every card of the frontend folder is served under the new version, and nothing under the old one is left
        self.assertEqual(self.old_url_files(), set())
        urls = ''.join((self.root / name).read_text(encoding='utf-8') for name in url_files)
        for card in sorted((self.root / HA / 'frontend').glob('*-card.js')):
            self.assertIn(f'/open_thermostat/{card.stem}-{NEW}.js', urls, card.name)
        self.assertEqual('WARNING' in out.getvalue(), drafts_are_skeletons(), 'a warning for the placeholder lines of a skeleton')
        # the real gate, with the catalog of the releases that exist
        catalog = published_catalog(self.temp.name, *PUBLISHED)
        gate = python(self.root, 'scripts/verify_e32_update_gate.py', '--candidate', prep.E32_TAG, '--published-file', str(catalog))
        self.assertEqual(gate.returncode, 0, gate.stderr)
        self.assertEqual(json.loads(gate.stdout)['publication_basis'], 'operator_approved_one_time_exception')
        # the real publication check accepts the skeletons (their shape), for both tags
        for tag in (prep.E32_TAG, prep.HA_TAG):
            result = python(self.root, 'scripts/organize_releases.py', '--publication-notes-for', tag,
                            '--output', str(Path(self.temp.name) / f'{tag}.md'))
            self.assertEqual(result.returncode, 0, result.stderr)
        # the acceptance kit's own loader
        cfg = acceptance.load_config(argparse.Namespace(config=str(self.root / prep.ACCEPTANCE_CONFIG)))
        self.assertEqual((cfg.tag, cfg.previous_tag, cfg.ha_version, cfg.ha_previous_version),
                         (prep.E32_TAG, prep.E32_PREVIOUS, prep.HA_VERSION, prep.HA_PREVIOUS))
        self.assertEqual(json.loads((self.root / prep.PLAN).read_text(encoding='utf-8'))['previous_published_tag'], prep.E32_PREVIOUS)


if __name__ == '__main__':
    unittest.main()
