"""Publish a GitHub release so that a failed or repeated run can be completed (R5-14).

`gh release create <tag> <287 MB of assets>` in one step cannot be repeated: when the upload fails midway, a
re-run finds a release that exists and cannot repair it. This script works in small steps that may be repeated:

  1. verify the local assets against the checksum file that was packaged with them;
  2. find the release of the tag (drafts included);
  3. none: create it as a DRAFT without assets; a draft: bring its title and notes up to date;
  4. upload the assets that are missing, or that differ from the local file (a draft may replace them);
  5. read the release back: every asset complete, with the size (and digest, when GitHub reports one) of the
     local file, and nothing else on it;
  6. publish the draft.

A release that is already published is never overwritten: a complete one is left alone, a missing asset is
uploaded (no --clobber), and an asset that differs from the local file stops the run.

Usage: publish_github_release.py --repository OWNER/NAME --tag TAG --title TITLE --notes-file FILE
           --assets-dir DIR --sums SHA256SUMS-NAME --channel prerelease|stable [--dry-run]
The checksum file lists every other file of the assets directory ("<sha256>  <name>"). gh reads GH_TOKEN.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


class Failure(Exception):
    """A reason to stop; the message is meant for the log of the job."""


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def local_assets(assets_dir, sums_name):
    """{name: {path, size, sha256}} of the files to publish, after checking them against the checksum file."""
    assets_dir = Path(assets_dir)
    files = {p.name: p for p in sorted(assets_dir.iterdir()) if p.is_file()}
    if sums_name not in files:
        raise Failure(f'{sums_name} is not in {assets_dir}')
    sums = {}
    for line in files[sums_name].read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition('  ')
        if len(digest) != 64 or not name or name in sums or Path(name).name != name:
            raise Failure(f'{sums_name}: unreadable line {line!r}')
        sums[name] = digest
    for name, digest in sums.items():
        if name not in files:
            raise Failure(f'{name} is listed in {sums_name} but is not in {assets_dir}')
        if sha256_file(files[name]) != digest:
            raise Failure(f'{name} does not match {sums_name}')
    unlisted = sorted(set(files) - set(sums) - {sums_name})
    if unlisted:
        raise Failure(f'not listed in {sums_name}: {", ".join(unlisted)}')
    return {name: {'path': path, 'size': path.stat().st_size, 'sha256': sums.get(name) or sha256_file(path)}
            for name, path in files.items()}


def compare(remote_assets, expected):
    """Which expected assets are complete on the release, missing (or incomplete), or different from the local file."""
    by_name = {asset.get('name'): asset for asset in remote_assets}
    complete, missing, incomplete, different = [], [], [], []
    for name, local in expected.items():
        remote = by_name.get(name)
        if remote is None:
            missing.append(name)
        elif remote.get('state', 'uploaded') != 'uploaded':
            incomplete.append(name)
        elif remote.get('size') != local['size'] or remote.get('digest') not in (None, 'sha256:' + local['sha256']):
            different.append(name)
        else:
            complete.append(name)
    extra = sorted(set(by_name) - set(expected))
    return {'complete': complete, 'missing': missing, 'incomplete': incomplete, 'different': different, 'extra': extra}


def find_release(gh, repository, tag):
    pages = json.loads(gh(['api', '--paginate', '--slurp', f'repos/{repository}/releases?per_page=100']))
    found = [release for page in pages for release in page if release.get('tag_name') == tag]
    if len(found) > 1:
        raise Failure(f'{len(found)} releases (drafts included) have the tag {tag}; remove the extra ones first')
    return found[0] if found else None


def publish(gh, repository, tag, title, notes_file, assets_dir, sums_name, prerelease, dry_run=False):
    expected = local_assets(assets_dir, sums_name)
    summary = {'tag': tag, 'channel': 'prerelease' if prerelease else 'stable', 'assets': sorted(expected),
               'uploaded': [], 'actions': []}

    def run(args, note):
        summary['actions'].append(note)
        if dry_run:
            print('DRY RUN would: gh ' + ' '.join(args))
            return ''
        return gh(args)

    release = find_release(gh, repository, tag)
    if release is None:
        run(['release', 'create', tag, '--repo', repository, '--verify-tag', '--draft',
             *(['--prerelease'] if prerelease else []), '--title', title, '--notes-file', str(notes_file)],
            'created as a draft')
        if dry_run:
            release = {'draft': True, 'prerelease': prerelease, 'assets': []}
        else:
            release = find_release(gh, repository, tag)
            if release is None:
                raise Failure(f'release {tag} was not found after creating it')
    if release.get('prerelease') is not prerelease:
        raise Failure(f'release {tag} is {"a pre-release" if release.get("prerelease") else "a normal release"}, '
                      f'expected {"a pre-release" if prerelease else "a normal release"}')
    draft = release.get('draft') is True
    state = compare(release.get('assets') or [], expected)
    if state['extra']:
        raise Failure(f'release {tag} has assets that are not part of this package: {", ".join(state["extra"])}')
    if draft:
        if summary['actions'] != ['created as a draft']:
            run(['release', 'edit', tag, '--repo', repository, '--title', title, '--notes-file', str(notes_file)],
                'draft title and notes brought up to date')
        upload = state['missing'] + state['incomplete'] + state['different']
    else:
        if state['incomplete'] or state['different']:
            raise Failure(f'release {tag} is published and its asset(s) {", ".join(state["incomplete"] + state["different"])}'
                          ' differ from the local files: nothing is overwritten; fix the release by hand')
        upload = state['missing']
    if upload:
        paths = [str(expected[name]['path']) for name in sorted(upload)]
        run(['release', 'upload', tag, '--repo', repository, *paths, *(['--clobber'] if draft else [])],
            f'uploaded {len(paths)} asset(s)')
        summary['uploaded'] = sorted(upload)
        if not dry_run:
            release = find_release(gh, repository, tag)
            state = compare(release.get('assets') or [], expected)
    if not dry_run and (state['missing'] or state['incomplete'] or state['different'] or state['extra']):
        raise Failure('after the upload the release is not complete: ' + json.dumps(
            {k: v for k, v in state.items() if v and k != 'complete'}))
    if draft:
        run(['release', 'edit', tag, '--repo', repository, '--draft=false'], 'published')
        if not dry_run:
            release = find_release(gh, repository, tag)
            if release is None or release.get('draft') is not False:
                raise Failure(f'release {tag} is still a draft after publishing it')
    elif not upload:
        summary['actions'].append('already published and complete: nothing to do')
    summary['digest_checked'] = bool(release.get('assets')) and all(a.get('digest') for a in release.get('assets') or [])
    return summary


def gh_command(arguments):
    """Runs gh (GH_BIN overrides the program) and returns its output; any failure becomes a Failure."""
    result = subprocess.run([os.environ.get('GH_BIN', 'gh'), *arguments], capture_output=True, text=True)
    if result.returncode != 0:
        raise Failure(f'gh {" ".join(arguments[:2])} failed ({result.returncode}): {(result.stderr or result.stdout).strip()[-600:]}')
    return result.stdout


def main(argv=None, gh=gh_command):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--notes-file', required=True)
    parser.add_argument('--assets-dir', required=True)
    parser.add_argument('--sums', required=True, help='name of the checksum file inside the assets directory')
    parser.add_argument('--channel', required=True, choices=('prerelease', 'stable'))
    parser.add_argument('--dry-run', action='store_true', help='read, but create, edit and upload nothing')
    args = parser.parse_args(argv)
    try:
        summary = publish(gh, args.repository, args.tag, args.title, args.notes_file, args.assets_dir, args.sums,
                          args.channel == 'prerelease', args.dry_run)
    except Failure as error:
        print(f'FAIL {error}', file=sys.stderr)
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
