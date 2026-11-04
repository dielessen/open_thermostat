"""Prepare E32 v1.0.0-e32v2-rc.5 / HA 1.0.0rc6 in a worktree: the content of the version commit (Checklist A, part 1).

From prepare_rc4.py, with the same rules: every field of the planning records is set here (nothing is copied from the
rc.4 files and patched), the user-visible notes come from draft files that are validated before anything is written,
nothing about the owner's approval is ever invented, nothing is overwritten, and either everything is written or
nothing. What is new since rc.4: the versioned frontend URLs are found, not listed (a sixth card needs no change here),
the acceptance kit's install-config.json and the "nu ..." lines of its Dutch install steps follow the release pair,
the planning record is refused when it has a field this script does not know, and no string of the rc.4 records may be
left in the rc.5 records.

Run it once, in the release worktree, on a clean tree that is still at E32 rc.4 / HA 1.0.0rc5 (the script refuses
otherwise and writes nothing when any check fails). Never on a tree you want to keep as it is: --dry-run first.

  python -I tools/dev/prepare_rc5.py <worktree> --date 20261110 --changes-file <changes.json>
         [--e32-notes docs/modern-thermostat/RELEASE-1.0-RC5-NOTES-DRAFT.en.md]
         [--ha-notes docs/modern-thermostat/HA-RC6-NOTES-DRAFT.en.md]
         [--owner-request-file <the owner's request, verbatim>]
         [--statement-file <the owner's answer, verbatim> --approved-at-utc 2026-11-10T09:30:00Z]
         [--allow-placeholders] [--dry-run]

It changes, as LF bytes:
  release.json, ha/config/custom_components/open_thermostat/manifest.json     the two versions
  every /open_thermostat/<file>-1.0.0rc5.js URL                               to -1.0.0rc6.js: the cards of the frontend
                                                                              folder, the week editor, the planner and the
                                                                              browser test that routes one of them
  docs/modern-thermostat/RELEASE-NOTES.md and HA-RELEASE-NOTES.md             the drafts are prepended
  docs/modern-thermostat/E32-UPDATE-GATE.json                                 pending_tag, candidate_plan, publication_exception
  tools/acceptance/install-config.json                                        tag, previous_tag, ha_version, ha_previous_version
  tools/acceptance/INSTALL-STEPS.nl.md                                        the three "nu ..." mentions of the release pair
and creates RC5-KANDIDAAT.json, RC5-OWNER-INSTRUCTION-<date>.json, RC4-UPDATE-GAP-<date>.json and
RC5-PUBLICATION-EXCEPTION-<date>.json. --changes-file is JSON: {"changes": [...], "not_included": [...]}
(not_included is optional).

The exception is a draft ("DRAFT_NOT_APPROVED", no approval) unless --statement-file and --approved-at-utc give the
owner's own words and the time of his answer; the gate refuses a draft. When the owner has answered later, set
"status": "APPROVED" and fill "approval.statement" and "approval.at_utc" in that file by hand and run

  python -I tools/dev/prepare_rc5.py <worktree> --rebind

which redoes the hash chain (gap report, exception, gate) and nothing else. Afterwards, in this order:
  python3 -B scripts/verify_e32_update_gate.py --candidate v1.0.0-e32v2-rc.5
  python tools/dev/refresh_beta19_inventory.py . --apply   (last edit), then scripts/verify_beta_release_inventory.py
and stage the files with explicit paths (Checklist A, step 12).

A draft that still has "<!-- pending" or "TODO" lines (the skeleton the docs package replaces) is refused, because
those lines would be published. --allow-placeholders accepts them for a rehearsal on a throwaway copy of the
worktree, with a warning; never use it for the version commit.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

E32_TAG, E32_PREVIOUS, E32_BEFORE = 'v1.0.0-e32v2-rc.5', 'v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2-rc.3'
HA_VERSION, HA_PREVIOUS, HA_BEFORE = '1.0.0rc6', '1.0.0rc5', '1.0.0rc4'
HA_TAG = 'ha-v' + HA_VERSION
RECEIPT_STEM = 'e32-rc5'  # tools/acceptance names the receipt after the tag: v1.0.0-e32v2-rc.5 -> e32-rc5-<YYYYMMDD>.json
# The owner installed rc.4 himself through the Home Assistant update entity; nothing was captured (the gap report).
RC4_INSTALLED_AT = '2026-11-04T13:38:00Z'
DOCS = 'docs/modern-thermostat'
HA_DIR = 'ha/config/custom_components/open_thermostat'
FRONTEND = f'{HA_DIR}/frontend'
GATE = f'{DOCS}/E32-UPDATE-GATE.json'
PLAN = f'{DOCS}/RC5-KANDIDAAT.json'
PLAN_TEMPLATE = f'{DOCS}/RC4-KANDIDAAT.json'
DEFAULT_E32_NOTES = f'{DOCS}/RELEASE-1.0-RC5-NOTES-DRAFT.en.md'
DEFAULT_HA_NOTES = f'{DOCS}/HA-RC6-NOTES-DRAFT.en.md'
ACCEPTANCE_CONFIG = 'tools/acceptance/install-config.json'
INSTALL_STEPS = 'tools/acceptance/INSTALL-STEPS.nl.md'
# Where a versioned frontend URL ("/open_thermostat/<file>-<HA version>.js", the cache buster) can be: the integration,
# its native tests and the browser tests that route one of the files.
URL_SCAN = ((HA_DIR, ('.py', '.js')), ('ha/tests_native', ('.py',)), ('test', ('.cjs', '.js', '.mjs')))
SKIPPED_DIRS = {'__pycache__', 'node_modules', '.git', '.pio', 'out'}
PLACEHOLDERS = ('<!-- pending', 'TODO')
# The fields of the planning record. Every release sets its own (RELEASE_FIELDS); the rest is the structure and the
# fixed safety flags, carried from the previous record. A field that is in neither list stops the script: it would be
# copied without anybody having looked at it.
RELEASE_FIELDS = ('date', 'planned_tag', 'previous_published_tag', 'state', 'published', 'installed', 'ha_tag',
                  'ha_installed', 'install_order', 'observed_installed_e32', 'observed_installed_ha',
                  'publication_condition', 'owner_instruction', 'publication_exception', 'predecessor_acceptance',
                  'planned_acceptance', 'release_notes', 'changes', 'not_included')
CARRIED_FIELDS = ('schema', 'formal_freeze', 'github_prerelease', 'install_together', 'active_control_since',
                  'last_accepted_native_e32', 'software_validation', 'active_gate_open_in_build',
                  'physical_outputs_automatically_enabled', 'radiator_valve_control_default_on',
                  'persistent_boiler_setting_writes_enabled', 'full_ten_minute_physical_success_claimed',
                  'native_https_root_cause_fixed')
NOT_INCLUDED = ['v1.0.0 itself (after 14 days with all release_ready.py criteria PASS)',
                'EMS+ boilers (1.1)', 'writable EMS boiler settings (after 1.0)',
                'Bluetooth sensor pairing from Home Assistant (later release)',
                'a read-only API key for assistants (later release)',
                'the weather forecast as a control input, a whole-day plan and presence patterns (after 1.0)',
                'automatic activation (active control still needs the owner\'s confirmed takeover)']
# Strings that can only be left over from the rc.4 (and older) records; the previous release itself may be named, so
# its tag and its version are not in this list.
STALE = ('RC4-OWNER', 'RC4-PUBLICATION', 'RC4-KANDIDAAT', 'RC3-', 'RC2-', 'RC1-', 'e32-rc4-', 'e32-rc3-',
         'v1.0.0-e32v2-rc.3', 'v1.0.0-e32v2-rc.2', 'ha-v1.0.0rc5', 'ha-v1.0.0rc4', '1.0.0rc4', '1.0.0rc3')


class Refusal(SystemExit):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def short(tag):
    """v1.0.0-e32v2-rc.4 -> rc.4"""
    return tag.rsplit('-', 1)[1]


class Tree:
    """Reads the worktree and collects the files to write; nothing is written until write() (all or nothing)."""

    def __init__(self, root):
        self.root, self.pending, self.warnings = Path(root).resolve(), {}, []

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

    def files(self, directory, suffixes):
        """The names (relative, with /) of the files below `directory` with one of `suffixes`, in sorted order;
        caches and vendored folders are left out."""
        names, base = set(), self.root / directory
        if base.is_dir():
            for path in base.rglob('*'):
                relative = path.relative_to(self.root)
                if path.suffix in suffixes and path.is_file() and not SKIPPED_DIRS & set(relative.parts):
                    names.add(relative.as_posix())
        names.update(name for name in self.pending if name.startswith(directory + '/')
                     and PurePosixPath(name).suffix in suffixes)
        return sorted(names)

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


def prepend_notes(tree, name, draft_name, tag, repository, allow_placeholders=False):
    """The draft goes on top of the cumulative notes; the result must pass the publication check."""
    if not tree.exists(draft_name):
        raise Refusal(f'{draft_name} does not exist (the docs package writes the release notes drafts)')
    draft = tree.text(draft_name)
    left = [number for number, line in enumerate(draft.splitlines(), 1) if any(mark in line for mark in PLACEHOLDERS)]
    if left and not allow_placeholders:
        raise Refusal(f'{draft_name} still has pending or TODO markers (line {left[0]}'
                      f'{f" and {len(left) - 1} more" if len(left) > 1 else ""}): they would be published. The docs package '
                      'replaces them; --allow-placeholders is for a rehearsal on a throwaway copy only')
    if left:
        tree.warnings.append(f'{draft_name}: {len(left)} placeholder line(s) remain (--allow-placeholders): a rehearsal '
                             'on a throwaway copy only, never the version commit')
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


def frontend_urls(tree):
    """The cache busters: every "/open_thermostat/<file>-<previous HA version>.js" moves to the new version.

    Found, not listed: the integration, its native tests and the browser tests are scanned, so every card of the
    frontend folder (and the week editor, the planner and the test route that serves one of them) follows, however
    many there are. Refused: a card without a versioned URL (browsers would keep the old file after the update), a
    versioned URL without its file in the frontend folder, and any other name that ends in the previous version."""
    old, new = f'-{HA_PREVIOUS}.js', f'-{HA_VERSION}.js'
    old_url = re.compile(r'/open_thermostat/([a-z0-9_-]+)' + re.escape(old))
    new_url = re.compile(r'/open_thermostat/([a-z0-9_-]+)' + re.escape(new))
    served, current, changed, count = {}, set(), [], 0
    for directory, suffixes in URL_SCAN:
        for name in tree.files(directory, suffixes):
            raw = tree.read(name)
            if new.encode() in raw:
                current.update(new_url.findall(raw.decode('utf-8', 'replace')))
            if old.encode() not in raw:
                continue
            text = tree.text(name)
            for stem in old_url.findall(text):
                served.setdefault(stem, []).append(name)
            count += len(old_url.findall(text))
            moved = old_url.sub(lambda match: f'/open_thermostat/{match.group(1)}{new}', text)
            if old in moved:
                raise Refusal(f'{name}: {moved.count(old)} occurrence(s) of {old} are not an /open_thermostat/<file>{old} URL')
            tree.put(name, moved)
            changed.append(name)
    if not served:
        raise Refusal(f'no /open_thermostat/<file>{old} URL found in {", ".join(directory for directory, _ in URL_SCAN)}: '
                      f'this tree is not at HA {HA_PREVIOUS}')
    ghosts = sorted(stem for stem in served if not tree.exists(f'{FRONTEND}/{stem}.js'))
    if ghosts:
        raise Refusal(f'/open_thermostat/{ghosts[0]}{old} in {served[ghosts[0]][0]} has no {FRONTEND}/{ghosts[0]}.js')
    cards = sorted(PurePosixPath(name).stem for name in tree.files(FRONTEND, ('.js',)) if name.endswith('-card.js'))
    unversioned = [card for card in cards if card not in served and card not in current]
    if unversioned:
        raise Refusal(f'{unversioned[0]}.js has no versioned URL (/open_thermostat/{unversioned[0]}{old} in the integration '
                      'or a test): a card served under a fixed URL stays stale in the browser after an update')
    return {'urls': count, 'files': sorted(set(changed)), 'served': sorted(served), 'cards': cards}


def versions(tree):
    release = tree.text('release.json')
    if release.count(f'"version": "{E32_PREVIOUS}"') != 1:
        raise Refusal(f'release.json is not at {E32_PREVIOUS}')
    tree.put('release.json', release.replace(f'"version": "{E32_PREVIOUS}"', f'"version": "{E32_TAG}"'))
    manifest = tree.text(f'{HA_DIR}/manifest.json')
    if manifest.count(f'"version": "{HA_PREVIOUS}"') != 1:
        raise Refusal(f'manifest.json is not at {HA_PREVIOUS}')
    tree.put(f'{HA_DIR}/manifest.json', manifest.replace(f'"version": "{HA_PREVIOUS}"', f'"version": "{HA_VERSION}"'))


def acceptance_config(tree):
    """The release the acceptance scripts install and capture: the four release keys move, the installation stays."""
    if not tree.exists(ACCEPTANCE_CONFIG):
        raise Refusal(f'{ACCEPTANCE_CONFIG} does not exist')
    config = tree.json(ACCEPTANCE_CONFIG)
    expected = {'tag': E32_PREVIOUS, 'previous_tag': E32_BEFORE, 'ha_version': HA_PREVIOUS, 'ha_previous_version': HA_BEFORE}
    if {key: config.get(key) for key in expected} != expected:
        raise Refusal(f'{ACCEPTANCE_CONFIG} is not at {E32_PREVIOUS} / {HA_PREVIOUS} (from {E32_BEFORE} / {HA_BEFORE})')
    config.update(tag=E32_TAG, previous_tag=E32_PREVIOUS, ha_version=HA_VERSION, ha_previous_version=HA_PREVIOUS)
    tree.put(ACCEPTANCE_CONFIG, dump(config))


def install_steps(tree):
    """The three "nu ..." mentions of the release pair in the Dutch install steps. Left alone when they already name
    this pair (somebody was first); refused when they name neither."""
    if not tree.exists(INSTALL_STEPS):
        raise Refusal(f'{INSTALL_STEPS} does not exist')
    text = tree.text(INSTALL_STEPS)
    pairs = ((f'(nu E32 **{E32_PREVIOUS}** met HA\n**{HA_PREVIOUS}**, vanaf {short(E32_BEFORE)} en {HA_BEFORE})',
              f'(nu E32 **{E32_TAG}** met HA\n**{HA_VERSION}**, vanaf {short(E32_PREVIOUS)} en {HA_PREVIOUS})'),
             (f'(nu **{HA_PREVIOUS}**)', f'(nu **{HA_VERSION}**)'),
             (f'(nu **{E32_PREVIOUS}**)', f'(nu **{E32_TAG}**)'))
    if all(text.count(new) == 1 and old not in text for old, new in pairs):
        return
    for old, _ in pairs:
        if text.count(old) != 1:
            raise Refusal(f'{INSTALL_STEPS}: expected exactly one {old!r}, found {text.count(old)}')
    for old, new in pairs:
        text = text.replace(old, new)
    tree.put(INSTALL_STEPS, text)


def template_plan(tree):
    """The previous planning record, as the structure and the fixed safety flags; every release field is set by
    records(). A field this script neither sets nor knows to carry stops it."""
    template = tree.json(PLAN_TEMPLATE)
    unknown = sorted(set(template) - set(RELEASE_FIELDS) - set(CARRIED_FIELDS))
    lacking = sorted(set(CARRIED_FIELDS) - set(template))
    if unknown or lacking:
        raise Refusal(f'{PLAN_TEMPLATE} does not have the fields this script expects (unknown: {unknown or "none"}; '
                      f'missing: {lacking or "none"}): decide by hand what rc.5 does with them, then change '
                      'RELEASE_FIELDS / CARRIED_FIELDS')
    return template


def leftovers(data, verbatim=()):
    """The strings of the rc.4 (and older) records that are left in a record of this release. The owner's own words
    (his request, his statement) are quoted as he said them and never judged."""
    text = data.decode('utf-8')
    for words in verbatim:
        text = text.replace(json.dumps(words, ensure_ascii=False)[1:-1], '')
    return [word for word in STALE if word in text]


def records(tree, args, day, gate):
    """The planning records and the gate. The hash chain: gap report, then exception, then gate."""
    iso = f'{day[:4]}-{day[4:6]}-{day[6:]}'
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    basis = gate['accepted']
    names = {'gap': f'{DOCS}/RC4-UPDATE-GAP-{day}.json', 'exception': f'{DOCS}/RC5-PUBLICATION-EXCEPTION-{day}.json',
             'owner': f'{DOCS}/RC5-OWNER-INSTRUCTION-{day}.json'}
    for name in (PLAN, *names.values()):
        if tree.exists(name):
            raise Refusal(f'{name} exists already; this script creates it and never overwrites')
    changes = json.loads(Path(args.changes_file).read_text(encoding='utf-8'))
    if not (isinstance(changes.get('changes'), list) and changes['changes'] and all(isinstance(c, str) and c for c in changes['changes'])):
        raise Refusal('--changes-file needs {"changes": ["...", ...]} with at least one change')

    gap = dump({
        'schema': 1, 'date': iso, 'status': 'INCOMPLETE',
        'scope': 'rc.4 update evidence gap; do not replace the accepted beta.22 basis',
        'candidate_tag': E32_PREVIOUS, 'published': True, 'installed_tag': E32_PREVIOUS,
        'installed_at_utc': RC4_INSTALLED_AT,
        'install_route': 'home_assistant_update_entity', 'native_install_commands': 0, 'manual_upload_commands': 0,
        'manual_result': 'Installed by the owner on 4 Nov 2026 at 13:38 UTC through the Home Assistant update entity; no '
                         'pre-install capture was made, so there is no acceptance receipt.',
        'acceptance_receipt': None, 'acceptance_receipt_status': 'NOT_CAPTURED', 'last_accepted': basis['tag']})
    approved = bool(args.statement_file)
    approval, statement = None, None
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
        'reason': 'rc.4 is installed and runs, but no acceptance receipt was captured. Publish this one rc.5 pre-release '
                  'with beta.22 as the last accepted basis. The rc.5 installation is captured as its acceptance (pre- and '
                  'post-install, Home Assistant route); v1.0.0 still needs an accepted rc.5 update and a 14-day PASS '
                  'readiness report.',
        'device_installation_authorized': False, 'boiler_trial_authorized': False, 'approval': approval,
        'separate_installation_instruction': names['owner']}
    exception_bytes = dump(exception)
    request = []
    if args.owner_request_file:
        request = [Path(args.owner_request_file).read_text(encoding='utf-8').strip()]
    owner = dump({
        'schema': 1, 'recorded_at_utc': now, 'requests': request,
        'scope': '1.0 candidate rc.5: E32 v1.0.0-e32v2-rc.5 + HA ha-v1.0.0rc6. Publish after a green check and exact-tag '
                 'CI. Installing is a separate, attended step with pre- and post-install capture (tools/acceptance); the '
                 '14 days of the 1.0 readiness report run on rc.5.',
        'not_included': ['installation (a separate, attended step)',
                         'v1.0.0 itself (after 14 days with all release_ready.py criteria PASS)'],
        'publication_approval_reply': None, 'publication_approval_at_utc': None, 'installation_approval_reply': None})

    plan = template_plan(tree)  # the structure and the fixed safety flags; every release field is set below
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
        'publication_condition': 'the owner\'s explicit go with the one-time exception over the unaccepted rc.4 (recorded) '
                                 'and green exact-tag CI',
        'owner_instruction': names['owner'], 'publication_exception': names['exception'],
        'predecessor_acceptance': {'tag': basis['tag'], 'receipt': basis['receipt'], 'status': 'PASS',
                                   'receipt_sha256': basis['sha256']},
        'planned_acceptance': {'method': 'home_assistant', 'checklist': f'{DOCS}/HA-UPDATE-ACCEPTANCE-BETA19.md',
                               'receipt': f'{DOCS}/update-acceptance/{RECEIPT_STEM}-<YYYYMMDD>.json'},
        'release_notes': {'e32': f'{DOCS}/RELEASE-NOTES.md (# E32 V2 1.0.0-rc.5)', 'ha': f'{DOCS}/HA-RELEASE-NOTES.md (# HA {HA_VERSION})'},
        'changes': changes['changes'], 'not_included': changes.get('not_included') or NOT_INCLUDED})
    plan_bytes = dump(plan)

    gate = dict(gate)
    gate.update({'pending_tag': E32_TAG, 'candidate_plan': PLAN,
                 'publication_exception': {'receipt': names['exception'], 'sha256': sha(exception_bytes)}})
    gate_bytes = dump(gate)
    # Nothing of the rc.4 records may be left where an rc.5 one belongs: judged before anything is put to be written.
    quoted = [words for words in (statement, *request) if words]
    for label, data in (('the planning record', plan_bytes), ('the gap report', gap), ('the exception', exception_bytes),
                        ('the owner instruction', owner), ('the gate', gate_bytes), (ACCEPTANCE_CONFIG, tree.read(ACCEPTANCE_CONFIG))):
        stale = leftovers(data, quoted)
        if stale:
            raise Refusal(f'{label} would keep strings of the rc.4 records: {stale}')
    tree.put(names['gap'], gap)
    tree.put(names['exception'], exception_bytes)
    tree.put(names['owner'], owner)
    tree.put(PLAN, plan_bytes)
    tree.put(GATE, gate_bytes)
    return names


def prepare(args):
    tree = Tree(args.worktree)
    gate = tree.json(GATE)
    if gate.get('pending_tag') != E32_PREVIOUS or not isinstance(gate.get('accepted'), dict):
        raise Refusal(f'{GATE} does not have {E32_PREVIOUS} pending and a physically accepted basis')
    versions(tree)
    urls = frontend_urls(tree)
    acceptance_config(tree)
    install_steps(tree)
    prepend_notes(tree, f'{DOCS}/RELEASE-NOTES.md', args.e32_notes, E32_TAG, args.repository, args.allow_placeholders)
    prepend_notes(tree, f'{DOCS}/HA-RELEASE-NOTES.md', args.ha_notes, HA_TAG, args.repository, args.allow_placeholders)
    names = records(tree, args, args.date, gate)
    if args.dry_run:
        print('DRY RUN: would write', *sorted(tree.pending), sep='\n  ')
    else:
        tree.write()
        print('prepared', E32_TAG, 'and', HA_TAG, 'in', tree.root)
        print('wrote', *sorted(tree.pending), sep='\n  ')
    print(f'frontend URLs: {urls["urls"]} moved to -{HA_VERSION}.js in {len(urls["files"])} file(s); served files: '
          f'{", ".join(urls["served"])}; cards: {", ".join(urls["cards"]) or "none"}')
    print('exception status:', json.loads(tree.pending[names['exception']])['status'])
    if not args.owner_request_file:
        print('note: no --owner-request-file: the owner instruction records no request of his')
    for warning in tree.warnings:
        print('WARNING', warning)
    if not args.dry_run:
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
    if exception.get('candidate_tag') != E32_TAG:
        raise Refusal(f'{reference["receipt"]} is the exception of {exception.get("candidate_tag")}, not of {E32_TAG}')
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
    parser.add_argument('--allow-placeholders', action='store_true',
                        help='accept drafts that still have "<!-- pending" or TODO lines: a rehearsal on a throwaway copy only')
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
