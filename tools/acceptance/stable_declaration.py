"""The owner's stable declaration: a release becomes stable on his word, and the gate records it.

The owner decides that a release is stable without the 14-day readiness window, the attended failure tests or the
install by someone else (docs/modern-thermostat/STABLE-RELEASE-TAGS.en.md, "Owner-declared stable release"). This
tool writes that record and binds it; scripts/verify_e32_update_gate.py checks it. Nothing is requested from Home
Assistant, the E32 or GitHub, and nothing is committed or pushed.

  python -I stable_declaration.py init <declaration> --tag <stable tag> --follows <release it follows>
         [--ha-tag ha-vX.Y.Z] [--ha-follows <integration version>] [--repo <worktree>]
      writes a new declaration with the placeholder "<OWNER STATEMENT>" where the owner's own words go (one entry
      per message: the text exactly as he wrote it, the local time and the UTC time), the criteria it declares and
      why (edit them), and empty bindings. Never overwrites. The gate refuses it while the placeholder is there.

  python -I stable_declaration.py seal <declaration> --receipt <receipt> --readiness <readiness report>
         [--repo <worktree>] [--apply-gate] [--dry-run]
      after write_receipt.py and release_ready.py --stage final --declaration <declaration>: binds the receipt, the
      readiness report and every evidence file they name by SHA-256, copies the receipt's declared checks and their
      reasons, and checks the result with the gate's own rules (the placeholder is refused here too). With
      --apply-gate it also sets E32-UPDATE-GATE.json: accepted <- the receipt (tag, path, digest), pending_tag
      null, the publication exception removed, stable_declaration <- this declaration (path, digest); then it
      runs the gate. The readiness report is bound in the gate by tools/dev/prepare_release.py (the version
      commit), as for every stable release.

All paths are relative to --repo (default: the worktree of this kit). Afterwards refresh the release inventory
(tools/dev/refresh_beta19_inventory.py . --apply) and commit the declaration, the receipt, the evidence, the
readiness report and the gate together with explicit paths.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script folder; these modules are ours
import acceptance as acc  # noqa: E402
from write_receipt import load_verifier  # noqa: E402

GATE = 'docs/modern-thermostat/E32-UPDATE-GATE.json'


def dump(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def inside(repo, name, label):
    """A repository file named relative to the repository, with /."""
    path = (repo / name).resolve()
    if '\\' in name or Path(name).is_absolute() or not path.is_relative_to(repo):
        raise SystemExit(f'{label} {name}: give a path in {repo}, relative to it, with /')
    return path


def template(tag, follows, ha_tag, ha_follows, gate):
    """A new declaration: the owner's words still to be given (the placeholder), nothing bound yet."""
    return {
        'schema': 1, 'kind': 'owner_declared_stable', 'tag': tag, 'ha_tag': ha_tag, 'follows': follows,
        'ha_follows': ha_follows, 'date': None,
        'owner': {'actor': 'repository_owner', 'name': None, 'method': 'explicit_user_instruction', 'channel': None,
                  'statements': [{'at_local': None, 'at_utc': None, 'text': gate.DECLARATION_PLACEHOLDER}]},
        'decision': f'The owner declares {follows} stable as {tag}. (Describe what he decided; his own words go in '
                    'owner.statements, exactly as given.)',
        'declared_criteria': {name: '<why this criterion is declared instead of measured>'
                              for name in gate.DECLARABLE_CRITERIA},
        'declared_receipt_checks': {},
        'receipt': None, 'readiness_report': None, 'evidence': [],
        'limits': ['Declared is not measured: every criterion and check listed here was not shown by evidence; the '
                   'owner decided the release is stable without it.'],
    }


def seal(repo, gate, name, receipt_name, readiness_name):
    """The declaration with its bindings filled in and checked by the gate's own rules (raises otherwise)."""
    declaration_path = inside(repo, name, 'declaration')
    declaration = json.loads(declaration_path.read_text(encoding='utf-8'))
    receipt_path = inside(repo, receipt_name, 'receipt')
    readiness_path = inside(repo, readiness_name, 'readiness report')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    readiness = json.loads(readiness_path.read_text(encoding='utf-8'))
    if receipt.get('tag') != declaration.get('follows') or readiness.get('release') != declaration.get('follows'):
        raise SystemExit(f'the receipt ({receipt.get("tag")}) and the readiness report ({readiness.get("release")}) '
                         f'must be about {declaration.get("follows")}, the release the declaration follows')
    if receipt.get('status') != 'PASS':
        raise SystemExit(f'{receipt_name} is {receipt.get("status")}, not PASS: {receipt.get("acceptance_decision")}')
    if (readiness.get('declaration') or {}).get('file') != name:
        raise SystemExit(f'{readiness_name} does not name {name} (release_ready.py --declaration {name})')
    basis = receipt.get('check_basis') or {}
    declaration['declared_receipt_checks'] = {check: basis.get(check, 'declared by the owner')
                                              for check in receipt.get('declared_checks') or []}
    declaration['receipt'] = {'path': receipt_name, 'sha256': acc.file_digest(receipt_path)}
    declaration['readiness_report'] = {'path': readiness_name, 'sha256': acc.file_digest(readiness_path)}
    evidence = []
    for item in (receipt.get('evidence_files') or []) + (readiness.get('evidence_files') or []):
        path = inside(repo, item.get('path', ''), 'evidence file')
        entry = {'path': item['path'], 'sha256': acc.file_digest(path), 'kind': item.get('kind')}
        if entry['sha256'] != item.get('sha256'):
            raise SystemExit(f'{item["path"]} changed after it was read (its digest differs from the one recorded)')
        if entry not in evidence:
            evidence.append(entry)
    declaration['evidence'] = evidence
    gate.declaration_record(repo, declaration, name)  # the placeholder, the declared names, every binding
    return declaration


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('action', choices=('init', 'seal'))
    parser.add_argument('declaration', help='the declaration file, a path in --repo')
    parser.add_argument('--repo', default=str(acc.REPO))
    parser.add_argument('--tag')
    parser.add_argument('--follows')
    parser.add_argument('--ha-tag')
    parser.add_argument('--ha-follows')
    parser.add_argument('--receipt')
    parser.add_argument('--readiness')
    parser.add_argument('--apply-gate', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    gate = load_verifier(repo)
    path = inside(repo, args.declaration, 'declaration')
    if args.action == 'init':
        if not (args.tag and args.follows):
            parser.error('init needs --tag and --follows')
        if not gate.stable(args.tag) or not gate.valid_tag(args.follows) or gate.version(args.follows) >= gate.version(args.tag):
            parser.error('--tag must be a stable E32 tag after --follows')
        if path.exists():
            raise SystemExit(f'{args.declaration} exists already; never overwritten')
        data = dump(template(args.tag, args.follows, args.ha_tag, args.ha_follows, gate))
        if args.dry_run:
            print(f'DRY RUN: would write {path}')
            return 0
        path.write_bytes(data)
        print('wrote', path, '(the owner statement is a placeholder: the gate refuses it until his words are in it)')
        return 0
    if not (args.receipt and args.readiness):
        parser.error('seal needs --receipt and --readiness')
    declaration = seal(repo, gate, args.declaration, args.receipt, args.readiness)
    data = dump(declaration)
    if args.dry_run:
        print(f'DRY RUN: would write {path}' + (f' and {GATE}' if args.apply_gate else ''))
        print(json.dumps({key: declaration[key] for key in ('receipt', 'readiness_report', 'evidence',
                                                             'declared_receipt_checks')}, indent=1, ensure_ascii=False))
        return 0
    path.write_bytes(data)
    print('wrote', path, acc.file_digest(path))
    if not args.apply_gate:
        return 0
    gate_path = repo / GATE
    policy = json.loads(gate_path.read_text(encoding='utf-8'))
    receipt = json.loads((repo / args.receipt).read_text(encoding='utf-8'))
    policy['accepted'] = {'tag': receipt['tag'], 'receipt': args.receipt, 'sha256': declaration['receipt']['sha256']}
    policy['pending_tag'] = None
    policy.pop('publication_exception', None)
    policy['stable_declaration'] = {'declaration': args.declaration, 'sha256': acc.file_digest(path)}
    gate_path.write_bytes((json.dumps(policy, indent=2) + '\n').encode())
    result = gate.verify(repo, policy)
    bound = declaration['readiness_report']
    report = gate.readiness_report(repo, {'report': bound['path'], 'sha256': bound['sha256']}, receipt['tag'],
                                   (receipt.get('ha_install_record') or {}).get('finished_at'))
    print('gate', json.dumps(result, ensure_ascii=False))
    print('readiness report', args.readiness, report.get('overall'), 'declared:', ', '.join(report.get('_declared', [])))
    print('Next: refresh the release inventory, commit, then tools/dev/prepare_release.py --spec', declaration['tag']
          .removeprefix('v').split('-')[0], '(it binds the readiness report and sets pending_tag).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
