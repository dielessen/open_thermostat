"""prepare_rc4.py on a throwaway copy of the files it touches (never on the real tree).

    python3 -I -m unittest discover -s tools/dev -p "test_*.py" -v

The tree is synthetic (rc.3 / 1.0.0rc4 files with the strings the script rewrites); the repository's own
scripts/organize_releases.py and scripts/verify_e32_update_gate.py are copied in, so the end result is judged by the
real publication-notes check and the real update gate.
"""
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
import prepare_rc4 as prep  # noqa: E402
import test_verify_e32_update_gate as gate_fixtures  # noqa: E402

HA = 'ha/config/custom_components/open_thermostat'
DOCS = 'docs/modern-thermostat'
BETA22 = 'v0.1.0-e32v2-beta.22'

E32_NOTES = """# E32 V2 1.0.0-rc.4 — the fourth 1.0 candidate: a fixture
<!-- user-release-notes:v2:en -->

Fixture introduction.

## New

- Something new.

## Fixed

- Something fixed.

## Updating

From rc.3, first HA 1.0.0rc5 through HACS, then Install on the Firmware entity.

## Limitations

None worth listing.
"""
HA_NOTES = E32_NOTES.replace('# E32 V2 1.0.0-rc.4 — the fourth 1.0 candidate: a fixture', '# HA 1.0.0rc5 — the companion of E32 rc.4')
OLD_E32 = '# E32 V2 1.0.0-rc.3 — the third 1.0 candidate\n<!-- user-release-notes:v2:en -->\n\nOld notes.\n'
OLD_HA = '# HA 1.0.0rc4 — a tidier Configure menu\n<!-- user-release-notes:v2:en -->\n\nOld notes.\n'
CHANGES = {'changes': ['The first change, in plain words.', 'The second change.']}


def lf(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'tree'
        self.build_tree()
        self.changes = Path(self.temp.name) / 'changes.json'
        lf(self.changes, json.dumps(CHANGES))

    def build_tree(self):
        root = self.root
        shutil.copytree(REPO / 'scripts', root / 'scripts', ignore=shutil.ignore_patterns('__pycache__', 'upstream', 'test_*'))
        lf(root / 'release.json', '{\n  "version": "v1.0.0-e32v2-rc.3",\n  "board": "bbqkees_e32v2"\n}\n')
        lf(root / HA / 'manifest.json', '{\n  "domain": "open_thermostat",\n  "version": "1.0.0rc4"\n}\n')
        lf(root / HA / 'e32_week.py', 'CARD_URL = "/open_thermostat/e32-week-card-1.0.0rc4.js"\nEDITOR_URL = "/open_thermostat/week-editor-1.0.0rc4.js"\n')
        lf(root / HA / 'frontend/e32-week-card.js', "const EDITOR = '/open_thermostat/week-editor-1.0.0rc4.js';\n")
        lf(root / HA / 'room_overview.py', 'CARD_URL = "/open_thermostat/room-status-card-1.0.0rc4.js"\n')
        lf(root / HA / 'week_planner.py', 'URL = "/open_thermostat/week-planner-1.0.0rc4.js"\nLEGACY_URLS = ("/open_thermostat/week-planner-0.4.0b4.js",)\n')
        lf(root / 'test/week-editor-browser.cjs', "if(p==='/open_thermostat/week-editor-1.0.0rc4.js')return 1;\n")
        lf(root / DOCS / 'RELEASE-NOTES.md', OLD_E32)
        lf(root / DOCS / 'HA-RELEASE-NOTES.md', OLD_HA)
        lf(root / prep.DEFAULT_E32_NOTES, E32_NOTES)
        lf(root / prep.DEFAULT_HA_NOTES, HA_NOTES)
        receipt = gate_fixtures.ha_record(BETA22, 'v0.1.0-e32v2-beta.21')
        raw = (json.dumps(receipt, indent=2) + '\n').encode()
        lf(root / DOCS / 'update-acceptance/e32-beta22-20261031.json', raw.decode())
        plan = {'schema': 1, 'date': '2026-11-02', 'planned_tag': 'v1.0.0-e32v2-rc.3', 'previous_published_tag': 'v1.0.0-e32v2-rc.2',
                'state': 'FROZEN_AWAITING_EXACT_TAG_CI', 'formal_freeze': True, 'published': True, 'installed': True,
                'github_prerelease': True, 'ha_tag': 'ha-v1.0.0rc3', 'ha_installed': True, 'install_together': True,
                'install_order': ['ha-v1.0.0rc3 (HACS)'], 'observed_installed_e32': BETA22, 'observed_installed_ha': '1.0.0rc2',
                'active_control_since': '2026-11-01T20:05Z', 'publication_condition': 'x',
                'owner_instruction': f'{DOCS}/RC3-OWNER-INSTRUCTION-20261103.json',
                'publication_exception': f'{DOCS}/RC2-PUBLICATION-EXCEPTION-20261102.json',
                'last_accepted_native_e32': 'v0.1.0-e32v2-beta.4',
                'predecessor_acceptance': {'tag': BETA22}, 'planned_acceptance': {'method': 'home_assistant'},
                'release_notes': {}, 'changes': ['old'], 'not_included': ['old'],
                'software_validation': {'physical_test_performed': False}, 'active_gate_open_in_build': True,
                'physical_outputs_automatically_enabled': False}
        lf(root / prep.PLAN_TEMPLATE, json.dumps(plan, indent=2) + '\n')
        old_exception = {'schema': 1, 'status': 'APPROVED'}
        lf(root / DOCS / 'RC3-PUBLICATION-EXCEPTION-20261103.json', json.dumps(old_exception, indent=2) + '\n')
        gate = {'schema': 1, 'required_for_successor_release': True,
                'accepted': {'tag': BETA22, 'receipt': f'{DOCS}/update-acceptance/e32-beta22-20261031.json',
                             'sha256': hashlib.sha256(raw).hexdigest()},
                'pending_tag': 'v1.0.0-e32v2-rc.3', 'candidate_plan': prep.PLAN_TEMPLATE,
                'publication_exception': {'receipt': f'{DOCS}/RC3-PUBLICATION-EXCEPTION-20261103.json', 'sha256': '0' * 64}}
        lf(root / prep.GATE, json.dumps(gate, indent=2) + '\n')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in sorted(self.root.rglob('*')) if p.is_file()}

    def run_prepare(self, *extra, check=True):
        arguments = [str(self.root), '--date', '20261110', '--changes-file', str(self.changes), *extra]
        with contextlib.redirect_stdout(io.StringIO()):
            if check:
                prep.main(arguments)
                return None
            with self.assertRaises(prep.Refusal) as caught:
                prep.main(arguments)
        return str(caught.exception)

    def run_rebind(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            prep.main([str(self.root), '--rebind'])
        return out.getvalue()

    def gate(self, candidate=prep.E32_TAG):
        return subprocess.run([sys.executable, '-B', str(self.root / 'scripts/verify_e32_update_gate.py'), '--candidate', candidate,
                               '--offline'], capture_output=True, text=True)

    def test_the_version_commit_content(self):
        before = self.snapshot()
        self.run_prepare()
        changed = sorted(name for name, data in self.snapshot().items() if before.get(name) != data)
        read = lambda name: (self.root / name).read_text(encoding='utf-8')
        self.assertIn('"version": "v1.0.0-e32v2-rc.4"', read('release.json'))
        self.assertIn('"version": "1.0.0rc5"', read(f'{HA}/manifest.json'))
        self.assertEqual(read(f'{HA}/e32_week.py').count('-1.0.0rc5.js'), 2)
        for name in (f'{HA}/frontend/e32-week-card.js', f'{HA}/room_overview.py', 'test/week-editor-browser.cjs'):
            self.assertEqual(read(name).count('-1.0.0rc5.js'), 1, name)
        self.assertIn('/open_thermostat/week-planner-1.0.0rc5.js', read(f'{HA}/week_planner.py'))
        self.assertIn('week-planner-0.4.0b4.js', read(f'{HA}/week_planner.py'), 'the legacy URL stays')
        for name in ('release.json', f'{HA}/manifest.json', f'{HA}/e32_week.py', f'{HA}/frontend/e32-week-card.js',
                     f'{HA}/room_overview.py', f'{HA}/week_planner.py', 'test/week-editor-browser.cjs'):
            self.assertNotIn('1.0.0rc4', read(name), name)
        self.assertTrue(read(f'{DOCS}/RELEASE-NOTES.md').startswith(E32_NOTES.rstrip('\n') + '\n\n' + OLD_E32))
        self.assertTrue(read(f'{DOCS}/HA-RELEASE-NOTES.md').startswith(HA_NOTES.rstrip('\n') + '\n\n' + OLD_HA))
        plan = json.loads(read(prep.PLAN))
        self.assertEqual((plan['planned_tag'], plan['previous_published_tag'], plan['ha_tag']),
                         ('v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2-rc.3', 'ha-v1.0.0rc5'))
        self.assertEqual((plan['observed_installed_e32'], plan['observed_installed_ha']), ('v1.0.0-e32v2-rc.3', '1.0.0rc4'))
        self.assertEqual(plan['changes'], CHANGES['changes'])
        self.assertEqual(plan['owner_instruction'], f'{DOCS}/RC4-OWNER-INSTRUCTION-20261110.json')
        self.assertEqual(plan['publication_exception'], f'{DOCS}/RC4-PUBLICATION-EXCEPTION-20261110.json')
        self.assertEqual(plan['predecessor_acceptance']['tag'], BETA22)
        self.assertEqual(plan['date'], '2026-11-10')
        text = read(prep.PLAN)
        for stale in prep.STALE:
            self.assertNotIn(stale, text)
        gate = json.loads(read(prep.GATE))
        self.assertEqual((gate['pending_tag'], gate['candidate_plan']), (prep.E32_TAG, prep.PLAN))
        self.assertEqual(gate['publication_exception']['sha256'],
                         hashlib.sha256((self.root / gate['publication_exception']['receipt']).read_bytes()).hexdigest())
        self.assertEqual(len(changed), 14, changed)
        for name in changed:
            self.assertNotIn(b'\r', (self.root / name).read_bytes(), name + ' has CRLF')

    def test_the_exception_is_a_draft_the_gate_refuses_until_the_owner_has_answered(self):
        self.run_prepare()
        exception_path = self.root / f'{DOCS}/RC4-PUBLICATION-EXCEPTION-20261110.json'
        exception = json.loads(exception_path.read_text(encoding='utf-8'))
        self.assertEqual((exception['status'], exception['approval']), ('DRAFT_NOT_APPROVED', None))
        self.assertIs(exception['device_installation_authorized'], False)
        refused = self.gate()
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('no explicit approval', refused.stderr)
        # The owner answers: status and approval by hand, then the hash chain is redone, nothing else changes.
        exception['status'] = 'APPROVED'
        exception['approval'] = {'actor': 'repository_owner', 'method': 'explicit_user_instruction',
                                 'decision': 'approve_one_prerelease_publication', 'statement': 'Yes, publish rc.4.',
                                 'at_utc': '2026-11-10T09:30:00Z'}
        exception_path.write_bytes((json.dumps(exception, indent=2) + '\n').encode())
        stale = self.gate()
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn('publication exception changed', stale.stderr)
        before = self.snapshot()
        self.run_rebind()
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
        gap_path = self.root / f'{DOCS}/RC3-UPDATE-GAP-20261110.json'
        gap = json.loads(gap_path.read_text(encoding='utf-8'))
        gap['manual_result'] += ' The owner added a detail.'
        gap_path.write_bytes((json.dumps(gap, indent=2) + '\n').encode())
        self.assertIn('evidence-gap report changed', self.gate().stderr)
        before = self.snapshot()
        self.run_rebind()
        changed = sorted(name for name, data in self.snapshot().items() if before.get(name) != data)
        self.assertEqual(changed, [prep.GATE, f'{DOCS}/RC4-PUBLICATION-EXCEPTION-20261110.json'])
        self.assertEqual(self.gate().returncode, 0)

    def test_rebind_says_when_the_owner_has_not_answered(self):
        self.run_prepare()
        self.assertIn('NOT yet approved by the owner', self.run_rebind())

    def test_the_owners_words_given_at_the_start_make_an_approved_exception(self):
        statement = Path(self.temp.name) / 'statement.txt'
        lf(statement, 'Ja, publiceer rc.4 als eenmalige uitzondering.\n')
        self.run_prepare('--statement-file', str(statement), '--approved-at-utc', '2026-11-10T09:30:00Z')
        exception = json.loads((self.root / f'{DOCS}/RC4-PUBLICATION-EXCEPTION-20261110.json').read_text(encoding='utf-8'))
        self.assertEqual(exception['status'], 'APPROVED')
        self.assertEqual(exception['approval']['statement'], 'Ja, publiceer rc.4 als eenmalige uitzondering.')
        result = self.gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['publication_basis'], 'operator_approved_one_time_exception')

    def test_the_owner_request_is_recorded_verbatim_and_no_approval_is_invented(self):
        request = Path(self.temp.name) / 'request.txt'
        lf(request, "Owner, 5 Nov: 'zorg dat rc.4 zelf leert'\n")
        self.run_prepare('--owner-request-file', str(request))
        owner = json.loads((self.root / f'{DOCS}/RC4-OWNER-INSTRUCTION-20261110.json').read_text(encoding='utf-8'))
        self.assertEqual(owner['requests'], ["Owner, 5 Nov: 'zorg dat rc.4 zelf leert'"])
        self.assertEqual((owner['publication_approval_reply'], owner['publication_approval_at_utc'],
                          owner['installation_approval_reply']), (None, None, None))

    def test_nothing_is_written_when_a_check_fails(self):
        before = self.snapshot()
        lf(self.root / prep.DEFAULT_HA_NOTES, HA_NOTES.replace('## Limitations', '## Limits'))
        broken = self.snapshot()
        self.assertIn('not a valid publication note', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), broken)
        lf(self.root / prep.DEFAULT_HA_NOTES, HA_NOTES + '\n<!-- pending -->\n')
        self.assertIn('pending', self.run_prepare(check=False))
        lf(self.root / prep.DEFAULT_HA_NOTES, HA_NOTES)
        lf(self.root / prep.DEFAULT_E32_NOTES, E32_NOTES.replace('# E32 V2 1.0.0-rc.4', '# E32 V2 1.0.0-rc.5'))
        self.assertIn('not a valid publication note', self.run_prepare(check=False))
        lf(self.root / prep.DEFAULT_E32_NOTES, E32_NOTES)
        self.assertEqual(self.snapshot(), before)
        lf(self.changes, json.dumps({'changes': []}))
        self.assertIn('at least one change', self.run_prepare(check=False))
        lf(self.changes, json.dumps({'changes': ['see RC3-OWNER-INSTRUCTION-20261103.json']}))
        self.assertIn('keep strings of the rc.3 records', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_a_tree_that_is_not_at_rc3_or_is_prepared_already_is_refused(self):
        self.run_prepare()
        prepared = self.snapshot()
        self.assertIn('does not have', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), prepared)
        lf(self.root / 'release.json', '{\n  "version": "v1.0.0-e32v2-rc.2"\n}\n')
        lf(self.root / prep.GATE, json.dumps({**json.loads((self.root / prep.GATE).read_text(encoding='utf-8')),
                                              'pending_tag': prep.E32_PREVIOUS}))
        self.assertIn('release.json is not at', self.run_prepare(check=False))

    def test_a_card_url_that_was_not_there_stops_the_script(self):
        lf(self.root / HA / 'room_overview.py', 'CARD_URL = "/open_thermostat/room-status-card-1.0.0rc3.js"\n')
        before = self.snapshot()
        self.assertIn('room_overview.py: expected 1 URL', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.run_prepare('--dry-run')
        self.assertEqual(self.snapshot(), before)

    def test_existing_records_are_never_overwritten(self):
        lf(self.root / f'{DOCS}/RC4-OWNER-INSTRUCTION-20261110.json', '{}\n')
        before = self.snapshot()
        self.assertIn('exists already', self.run_prepare(check=False))
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
