"""Prepare E32 v1.0.0-e32v2-rc.4 / HA 1.0.0rc5 in a worktree: the content of the version commit (Checklist A, part 1).

From prepare_rc3.py, with the lessons of the R5 review: every field of the planning records is set here (nothing is
copied from the rc.3 files and patched, R5-30), the user-visible notes come from draft files that are validated
before anything is written, and nothing about the owner's approval is ever invented.

Run it once, in the release worktree, on a clean tree that is still at E32 rc.3 / HA 1.0.0rc4 (the script refuses
otherwise and writes nothing when any check fails):

  python -I tools/dev/prepare_rc4.py <worktree> --date 20261110 --changes-file <changes.json>
         [--e32-notes docs/modern-thermostat/RELEASE-1.0-RC4-NOTES-DRAFT.en.md]
         [--ha-notes docs/modern-thermostat/HA-RC5-NOTES-DRAFT.en.md]
         [--owner-request-file <the owner's request, verbatim>]
         [--statement-file <the owner's answer, verbatim> --approved-at-utc 2026-11-10T09:30:00Z] [--dry-run]

It changes, as LF bytes:
  release.json, ha/config/custom_components/open_thermostat/manifest.json     the two versions
  the five versioned card URLs and the test route that carries one            -1.0.0rc4.js to -1.0.0rc5.js
  docs/modern-thermostat/RELEASE-NOTES.md and HA-RELEASE-NOTES.md             the drafts are prepended
  docs/modern-thermostat/E32-UPDATE-GATE.json                                 pending_tag, candidate_plan, publication_exception
and creates RC4-KANDIDAAT.json, RC4-OWNER-INSTRUCTION-<date>.json, RC3-UPDATE-GAP-<date>.json and
RC4-PUBLICATION-EXCEPTION-<date>.json. --changes-file is JSON: {"changes": [...], "not_included": [...]}
(not_included is optional).

The exception is a draft ("DRAFT_NOT_APPROVED", no approval) unless --statement-file and --approved-at-utc give the
owner's own words and the time of his answer; the gate refuses a draft. When the owner has answered later, set
"status": "APPROVED" and fill "approval.statement" and "approval.at_utc" in that file by hand and run

  python -I tools/dev/prepare_rc4.py <worktree> --rebind

which redoes the hash chain (gap report, exception, gate) and nothing else. Afterwards, in this order:
  python3 -B scripts/verify_e32_update_gate.py --candidate v1.0.0-e32v2-rc.4
  python tools/dev/refresh_beta19_inventory.py . --apply   (last edit), then scripts/verify_beta_release_inventory.py
and stage the files with explicit paths (Checklist A, step 12).
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

E32_TAG, E32_PREVIOUS = 'v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2-rc.3'
HA_VERSION, HA_PREVIOUS = '1.0.0rc5', '1.0.0rc4'
HA_TAG = 'ha-v' + HA_VERSION
DOCS = 'docs/modern-thermostat'
HA_DIR = 'ha/config/custom_components/open_thermostat'
GATE = f'{DOCS}/E32-UPDATE-GATE.json'
PLAN = f'{DOCS}/RC4-KANDIDAAT.json'
PLAN_TEMPLATE = f'{DOCS}/RC3-KANDIDAAT.json'
DEFAULT_E32_NOTES = f'{DOCS}/RELEASE-1.0-RC4-NOTES-DRAFT.en.md'
DEFAULT_HA_NOTES = f'{DOCS}/HA-RC5-NOTES-DRAFT.en.md'
# The five versioned card URLs, with how often each file names one, and the test that routes one of them.
CARD_FILES = ((f'{HA_DIR}/e32_week.py', 2), (f'{HA_DIR}/frontend/e32-week-card.js', 1), (f'{HA_DIR}/room_overview.py', 1),
              (f'{HA_DIR}/week_planner.py', 1), ('test/week-editor-browser.cjs', 1))
NOT_INCLUDED = ['v1.0.0 itself (after 14 days with all release_ready.py criteria PASS)',
                'EMS+ boilers (1.1)', 'writable EMS boiler settings (after 1.0)',
                'Bluetooth sensor pairing from Home Assistant (later release)',
                'a read-only API key for assistants (later release)', 'the room heat-loss house model (1.1)',
                'automatic activation (active control still needs the owner\'s confirmed takeover)']
# Strings that can only be left over from the rc.3 records (the previous release itself may be named).
STALE = ('RC3-OWNER', 'RC3-PUBLICATION', 'RC3-KANDIDAAT', 'RC2-', 'v1.0.0-e32v2-rc.2', 'e32-rc3-', 'ha-v1.0.0rc3', '1.0.0rc3')


class Refusal(SystemExit):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


class Tree:
    """Reads the worktree and collects the files to write; nothing is written until write() (all or nothing)."""

    def __init__(self, root):
        self.root, self.pending = Path(root).resolve(), {}

    def read(self, name):
        if name in self.pending:
            return self.pending[name]
        return (self.root / name).read_bytes()

    def text(self, name):
        data = self.read(name).decode('utf-8')
        if '\r' in data:
            raise Refusal(f'{name} has CRLF line endings; fix that first')
        return data

    def json(self, name):
        return json.loads(self.text(name))

    def exists(self, name):
        return name in self.pending or (self.root / name).exists()

    def put(self, name, data):
        self.pending[name] = data if isinstance(data, bytes) else data.encode('utf-8')

    def write(self):
        for name, data in self.pending.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


def organize(root):
    sys.path.insert(0, str(Path(root) / 'scripts'))
    import organize_releases
    return organize_releases


def prepend_notes(tree, name, draft_name, tag, repository):
    """The draft goes on top of the cumulative notes; the result must pass the publication check."""
    draft = tree.text(draft_name)
    if '<!-- pending' in draft or 'TODO' in draft:
        raise Refusal(f'{draft_name} still has pending or TODO markers')
    current = tree.text(name)
    first = draft.splitlines()[0] if draft.strip() else ''
    if current.startswith(first):
        raise Refusal(f'{name} already starts with {first!r}: this tree is already prepared')
    combined = draft.rstrip('\n') + '\n\n' + current
    try:
        organize(tree.root).publication_notes(combined, repository, tag, require_user_notes=True)
    except ValueError as error:
        raise Refusal(f'{draft_name} is not a valid publication note for {tag}: {error}') from None
    tree.put(name, combined)


def card_urls(tree):
    for name, count in CARD_FILES:
        text = tree.text(name)
        if text.count(f'-{HA_PREVIOUS}.js') != count:
            raise Refusal(f'{name}: expected {count} URL(s) ending in -{HA_PREVIOUS}.js, found {text.count(f"-{HA_PREVIOUS}.js")}')
        tree.put(name, text.replace(f'-{HA_PREVIOUS}.js', f'-{HA_VERSION}.js'))


def versions(tree):
    release = tree.text('release.json')
    if release.count(f'"version": "{E32_PREVIOUS}"') != 1:
        raise Refusal(f'release.json is not at {E32_PREVIOUS}')
    tree.put('release.json', release.replace(f'"version": "{E32_PREVIOUS}"', f'"version": "{E32_TAG}"'))
    manifest = tree.text(f'{HA_DIR}/manifest.json')
    if manifest.count(f'"version": "{HA_PREVIOUS}"') != 1:
        raise Refusal(f'manifest.json is not at {HA_PREVIOUS}')
    tree.put(f'{HA_DIR}/manifest.json', manifest.replace(f'"version": "{HA_PREVIOUS}"', f'"version": "{HA_VERSION}"'))


def records(tree, args, day, gate):
    """The planning records and the gate. The hash chain: gap report, then exception, then gate."""
    iso = f'{day[:4]}-{day[4:6]}-{day[6:]}'
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    basis = gate['accepted']
    names = {'gap': f'{DOCS}/RC3-UPDATE-GAP-{day}.json', 'exception': f'{DOCS}/RC4-PUBLICATION-EXCEPTION-{day}.json',
             'owner': f'{DOCS}/RC4-OWNER-INSTRUCTION-{day}.json'}
    for name in (PLAN, *names.values()):
        if tree.exists(name):
            raise Refusal(f'{name} exists already; this script creates it and never overwrites')
    changes = json.loads(Path(args.changes_file).read_text(encoding='utf-8'))
    if not (isinstance(changes.get('changes'), list) and changes['changes'] and all(isinstance(c, str) and c for c in changes['changes'])):
        raise Refusal('--changes-file needs {"changes": ["...", ...]} with at least one change')

    gap = dump({
        'schema': 1, 'date': iso, 'status': 'INCOMPLETE',
        'scope': 'rc.3 update evidence gap; do not replace the accepted beta.22 basis',
        'candidate_tag': E32_PREVIOUS, 'published': True, 'installed_tag': E32_PREVIOUS,
        'install_route': 'home_assistant_update_entity', 'native_install_commands': 0, 'manual_upload_commands': 0,
        'manual_result': 'Installed by the owner on 3 Nov 2026 through the Home Assistant update entity; no pre-install '
                         'capture was made, so there is no acceptance receipt.',
        'acceptance_receipt': None, 'acceptance_receipt_status': 'NOT_CAPTURED', 'last_accepted': basis['tag']})
    approved = bool(args.statement_file)
    approval = None
    if approved:
        statement = Path(args.statement_file).read_text(encoding='utf-8').strip()
        if not 1 <= len(statement) <= 2000:
            raise Refusal('--statement-file must hold the owner\'s words (1 to 2000 characters)')
        approval = {'actor': 'repository_owner', 'method': 'explicit_user_instruction',
                    'decision': 'approve_one_prerelease_publication', 'statement': statement, 'at_utc': args.approved_at_utc}
    exception = {
        'schema': 1, 'status': 'APPROVED' if approved else 'DRAFT_NOT_APPROVED', 'scope': 'one_prerelease_publication',
        'candidate_tag': E32_TAG, 'unaccepted_predecessor': E32_PREVIOUS,
        'accepted_basis_tag': basis['tag'], 'accepted_basis_receipt_sha256': basis['sha256'],
        'predecessor_acceptance_status': 'INCOMPLETE', 'gap_report': names['gap'], 'gap_report_sha256': sha(gap),
        'reason': 'rc.3 is installed and runs, but no acceptance receipt was captured. Publish this one rc.4 pre-release '
                  'with beta.22 as the last accepted basis. The rc.4 installation is captured as its acceptance (pre- and '
                  'post-install, Home Assistant route); v1.0.0 still needs an accepted rc.4 update and a 14-day PASS '
                  'readiness report.',
        'device_installation_authorized': False, 'boiler_trial_authorized': False, 'approval': approval,
        'separate_installation_instruction': names['owner']}
    exception_bytes = dump(exception)
    request = []
    if args.owner_request_file:
        request = [Path(args.owner_request_file).read_text(encoding='utf-8').strip()]
    owner = dump({
        'schema': 1, 'recorded_at_utc': now, 'requests': request,
        'scope': '1.0 candidate rc.4: E32 v1.0.0-e32v2-rc.4 + HA ha-v1.0.0rc5 from release-1.0. Publish after a green check and '
                 'exact-tag CI. Installing is a separate, attended step with pre- and post-install capture.',
        'not_included': ['installation (a separate, attended step)',
                         'v1.0.0 itself (after 14 days with all release_ready.py criteria PASS)'],
        'publication_approval_reply': None, 'publication_approval_at_utc': None, 'installation_approval_reply': None})

    plan = tree.json(PLAN_TEMPLATE)  # the structure and the fixed safety flags; every release field is set below
    plan.update({
        'date': iso, 'planned_tag': E32_TAG, 'previous_published_tag': E32_PREVIOUS,
        'state': 'FROZEN_AWAITING_EXACT_TAG_CI', 'published': False, 'installed': False, 'ha_tag': HA_TAG,
        'ha_installed': False,
        'install_order': [
            f'{HA_TAG} (HACS, then a Home Assistant restart)',
            f'{E32_TAG} (Home Assistant Firmware update entity, one Install press), attended, with the owner at home, with '
            'pre- and post-install capture as the acceptance receipt (tools/acceptance)',
            'confirm the takeover again right after the update (Repairs, or Rooms on the E32); until then the E32 keeps '
            'only frost protection'],
        'observed_installed_e32': E32_PREVIOUS, 'observed_installed_ha': HA_PREVIOUS,
        'publication_condition': 'the owner\'s explicit go with the one-time exception over the unaccepted rc.3 (recorded) '
                                 'and green exact-tag CI',
        'owner_instruction': names['owner'], 'publication_exception': names['exception'],
        'predecessor_acceptance': {'tag': basis['tag'], 'receipt': basis['receipt'], 'status': 'PASS',
                                   'receipt_sha256': basis['sha256']},
        'planned_acceptance': {'method': 'home_assistant', 'checklist': f'{DOCS}/HA-UPDATE-ACCEPTANCE-BETA19.md',
                               'receipt': f'{DOCS}/update-acceptance/e32-rc4-<YYYYMMDD>.json'},
        'release_notes': {'e32': f'{DOCS}/RELEASE-NOTES.md (# E32 V2 1.0.0-rc.4)', 'ha': f'{DOCS}/HA-RELEASE-NOTES.md (# HA {HA_VERSION})'},
        'changes': changes['changes'], 'not_included': changes.get('not_included') or NOT_INCLUDED})
    plan_bytes = dump(plan)
    stale = [word for word in STALE if word in plan_bytes.decode('utf-8')]
    if stale:
        raise Refusal(f'RC4-KANDIDAAT.json would keep strings of the rc.3 records: {stale}')

    gate = dict(gate)
    gate.update({'pending_tag': E32_TAG, 'candidate_plan': PLAN,
                 'publication_exception': {'receipt': names['exception'], 'sha256': sha(exception_bytes)}})
    tree.put(names['gap'], gap)
    tree.put(names['exception'], exception_bytes)
    tree.put(names['owner'], owner)
    tree.put(PLAN, plan_bytes)
    tree.put(GATE, dump(gate))
    return names


def prepare(args):
    tree = Tree(args.worktree)
    gate = tree.json(GATE)
    if gate.get('pending_tag') != E32_PREVIOUS or not isinstance(gate.get('accepted'), dict):
        raise Refusal(f'{GATE} does not have {E32_PREVIOUS} pending and a physically accepted basis')
    versions(tree)
    card_urls(tree)
    prepend_notes(tree, f'{DOCS}/RELEASE-NOTES.md', args.e32_notes, E32_TAG, args.repository)
    prepend_notes(tree, f'{DOCS}/HA-RELEASE-NOTES.md', args.ha_notes, HA_TAG, args.repository)
    names = records(tree, args, args.date, gate)
    if args.dry_run:
        print('DRY RUN: would write', *sorted(tree.pending), sep='\n  ')
        return
    tree.write()
    print('prepared', E32_TAG, 'and', HA_TAG, 'in', tree.root)
    print('wrote', *sorted(tree.pending), sep='\n  ')
    print('exception status:', json.loads(tree.pending[names['exception']])['status'])
    print('next: python3 -B scripts/verify_e32_update_gate.py --candidate', E32_TAG,
          '; then tools/dev/refresh_beta19_inventory.py . --apply as the last edit')


def rebind(args):
    """Redo the hash chain after a hand edit of the exception (the owner's statement) or the gap report."""
    tree = Tree(args.worktree)
    gate = tree.json(GATE)
    reference = gate.get('publication_exception')
    if not (isinstance(reference, dict) and gate.get('pending_tag') == E32_TAG):
        raise Refusal(f'{GATE} has no {E32_TAG} publication exception to rebind')
    exception = tree.json(reference['receipt'])
    gap_name = exception['gap_report']
    exception['gap_report_sha256'] = sha(tree.read(gap_name))
    exception_bytes = dump(exception)
    gate['publication_exception'] = {'receipt': reference['receipt'], 'sha256': sha(exception_bytes)}
    tree.put(reference['receipt'], exception_bytes)
    tree.put(GATE, dump(gate))
    approval = exception.get('approval')
    ready = exception.get('status') == 'APPROVED' and isinstance(approval, dict) and approval.get('statement') \
        and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', str(approval.get('at_utc')))
    if args.dry_run:
        print('DRY RUN: would rewrite', *sorted(tree.pending), sep='\n  ')
    else:
        tree.write()
        print('rebound', reference['receipt'], 'and', GATE)
    print('the exception is' + ('' if ready else ' NOT yet') + ' approved by the owner' +
          ('' if ready else ' (status APPROVED, approval.statement and approval.at_utc must be filled in by hand)'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('worktree')
    parser.add_argument('--date', default=datetime.now(timezone.utc).strftime('%Y%m%d'), help='YYYYMMDD of the file names')
    parser.add_argument('--changes-file')
    parser.add_argument('--e32-notes', default=DEFAULT_E32_NOTES)
    parser.add_argument('--ha-notes', default=DEFAULT_HA_NOTES)
    parser.add_argument('--owner-request-file')
    parser.add_argument('--statement-file')
    parser.add_argument('--approved-at-utc')
    parser.add_argument('--repository', default='dielessen/open_thermostat')
    parser.add_argument('--rebind', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'20\d{6}', args.date):
        parser.error('--date is YYYYMMDD')
    if bool(args.statement_file) != bool(args.approved_at_utc):
        parser.error('--statement-file and --approved-at-utc go together (the owner\'s words and the time of his answer)')
    if args.approved_at_utc and not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', args.approved_at_utc):
        parser.error('--approved-at-utc is a UTC time like 2026-11-10T09:30:00Z')
    if args.rebind:
        return rebind(args)
    if not args.changes_file:
        parser.error('--changes-file is required')
    return prepare(args)


if __name__ == '__main__':
    main()
