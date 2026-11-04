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

Every failure names the step it comes from ("FAIL step 4 of 6 (upload the assets): ..."), so a first attempt that
fails within seconds says where. --verbose adds a log on stderr, for the job log: the environment, the start and
the end of every step with what it found and decided, and for every gh command the command line before it runs,
then its exit code, duration and the tails of its stderr and stdout (a successful `gh api` read shows only the
size of its answer: the step logs what it made of it). The value of GH_TOKEN / GITHUB_TOKEN is never printed.

Usage: publish_github_release.py --repository OWNER/NAME --tag TAG --title TITLE --notes-file FILE
           --assets-dir DIR --sums SHA256SUMS-NAME --channel prerelease|stable [--dry-run] [--verbose]
The checksum file lists every other file of the assets directory ("<sha256>  <name>"). gh reads GH_TOKEN.
"""
import argparse
import contextlib
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
import traceback
from pathlib import Path

STEP_COUNT = 6
TAIL_CHARS = 600  # how much of a command's stderr and stdout --verbose logs


class Failure(Exception):
    """A reason to stop; the message is meant for the log of the job.

    `step` names where it happened ("step 4 of 6 (upload the assets)"), set by publish(); `result` is the output of
    the gh command that failed, when there was one (its exit code, stderr and duration).
    """

    def __init__(self, message, step=None, result=None):
        super().__init__(message)
        self.message, self.step, self.result = message, step, result

    def __str__(self):
        return f'{self.step}: {self.message}' if self.step else self.message


class Output(str):
    """What a gh command printed on stdout, carrying its exit code, its stderr and how long it ran."""
    returncode, stderr, seconds = 0, '', 0.0


def output(stdout, returncode=0, stderr='', seconds=0.0):
    value = Output(stdout)
    value.returncode, value.stderr, value.seconds = returncode, stderr, seconds
    return value


def redact(text):
    """The job log must never show the token, whatever a command or an error message quotes."""
    for name in ('GH_TOKEN', 'GITHUB_TOKEN'):
        secret = os.environ.get(name)
        if secret and len(secret) >= 8:
            text = text.replace(secret, '***')
    return text


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


def describe(release):
    """One line for the log: what GitHub says about a release, and one per asset."""
    kind = ('draft' if release.get('draft') else 'published') + (', pre-release' if release.get('prerelease') else '')
    assets = release.get('assets') or []
    lines = [f'release {release.get("id")} {release.get("tag_name")!r} ({kind}): {len(assets)} asset(s)']
    for asset in assets[:20]:
        lines.append(f'    {asset.get("name")}  {asset.get("size")} bytes  {asset.get("state", "uploaded")}  '
                     f'{asset.get("digest") or "no digest"}')
    return '\n'.join(lines)


def find_release(gh, repository, tag, log=None):
    text = gh(['api', '--paginate', '--slurp', f'repos/{repository}/releases?per_page=100'])
    try:
        pages = json.loads(text)
        releases = [release for page in pages for release in page]
    except (TypeError, ValueError) as error:
        raise Failure(f'GitHub did not answer with a list of releases ({type(error).__name__}: {error}); '
                      f'the answer starts with {str(text)[:200]!r}') from error
    found = [release for release in releases if release.get('tag_name') == tag]
    if log:
        drafts = [release for release in releases if release.get('draft')]
        log(f'read {len(releases)} release(s) on {len(pages)} page(s), {len(drafts)} of them drafts; '
            f'{len(found)} with the tag {tag}')
        if found:
            log(describe(found[0]))
        elif drafts:
            log('drafts: ' + ', '.join(f'{d.get("tag_name")!r} named {d.get("name")!r}' for d in drafts[:5]))
    if len(found) > 1:
        raise Failure(f'{len(found)} releases (drafts included) have the tag {tag}; remove the extra ones first')
    return found[0] if found else None


def make_step(log):
    """step(number, name): names the step a Failure comes from and logs where it starts and ends."""
    @contextlib.contextmanager
    def step(number, name):
        label = f'step {number} of {STEP_COUNT} ({name})' if number else f'preflight ({name})'
        log(f'{label}: start')
        started = time.monotonic()
        try:
            yield
        except Failure as error:
            if error.step is None:
                error.step = label
            log(f'{label}: FAILED after {time.monotonic() - started:.1f} s: {error.message}')
            raise
        except Exception as error:  # an answer nobody expected: still say where
            log(f'{label}: FAILED after {time.monotonic() - started:.1f} s: {type(error).__name__}: {error}')
            raise Failure(f'unexpected {type(error).__name__}: {error}', label) from error
        log(f'{label}: done in {time.monotonic() - started:.1f} s')
    return step


def publish(gh, repository, tag, title, notes_file, assets_dir, sums_name, prerelease, dry_run=False, log=None):
    """Brings the release of `tag` to published and complete. `log` (a function of one line) turns on the verbose
    log; the failures name their step either way."""
    verbose = log is not None
    log = log or (lambda line: None)
    step = make_step(log)
    channel = 'prerelease' if prerelease else 'stable'
    if verbose:
        with step(0, 'check the environment'):
            log(f'{repository} {tag} as a {channel} release{" (dry run)" if dry_run else ""}; notes {notes_file}; '
                f'assets {assets_dir}')
            ci = ''.join(f'; {name} {os.environ[name]}' for name in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT', 'RUNNER_OS')
                         if os.environ.get(name))
            log(f'python {sys.version.split()[0]} on {sys.platform}; GH_TOKEN '
                f'{"set" if os.environ.get("GH_TOKEN") else "NOT set"}{ci}')
            gh(['--version'])
    with step(1, 'verify the local assets'):
        expected = local_assets(assets_dir, sums_name)
        log(f'{len(expected)} file(s), {sum(a["size"] for a in expected.values())} bytes; every checksum in '
            f'{sums_name} matches')
    summary = {'tag': tag, 'channel': channel, 'assets': sorted(expected), 'uploaded': [], 'actions': []}

    def run(args, note):
        summary['actions'].append(note)
        if dry_run:
            print('DRY RUN would: gh ' + ' '.join(args))
            return ''
        return gh(args)

    with step(2, 'find the release of the tag'):
        release = find_release(gh, repository, tag, log)
    with step(3, 'prepare the release'):
        if release is None:
            log(f'no release has the tag {tag}: creating it as a draft without assets')
            run(['release', 'create', tag, '--repo', repository, '--verify-tag', '--draft',
                 *(['--prerelease'] if prerelease else []), '--title', title, '--notes-file', str(notes_file)],
                'created as a draft')
            if dry_run:
                release = {'draft': True, 'prerelease': prerelease, 'assets': []}
            else:
                release = find_release(gh, repository, tag, log)
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
        log(f'the release is {"a draft" if draft else "published"}; assets complete {len(state["complete"])}, '
            f'to upload {len(upload)}' + (f' ({", ".join(sorted(upload))})' if upload else ''))
    with step(4, 'upload the assets'):
        if upload:
            paths = [str(expected[name]['path']) for name in sorted(upload)]
            run(['release', 'upload', tag, '--repo', repository, *paths, *(['--clobber'] if draft else [])],
                f'uploaded {len(paths)} asset(s)')
            summary['uploaded'] = sorted(upload)
        else:
            log('nothing to upload')
    with step(5, 'read the release back'):
        if upload and not dry_run:
            release = find_release(gh, repository, tag, log)
            if release is None:
                raise Failure(f'release {tag} was not found after the upload')
            state = compare(release.get('assets') or [], expected)
        if not dry_run and (state['missing'] or state['incomplete'] or state['different'] or state['extra']):
            raise Failure('after the upload the release is not complete: ' + json.dumps(
                {k: v for k, v in state.items() if v and k != 'complete'}))
        log('every asset is on the release with the size (and digest) of the local file' if not dry_run else 'dry run: not read')
    with step(6, 'publish the draft'):
        if draft:
            run(['release', 'edit', tag, '--repo', repository, '--draft=false'], 'published')
            if not dry_run:
                release = find_release(gh, repository, tag, log)
                if release is None or release.get('draft') is not False:
                    raise Failure(f'release {tag} is still a draft after publishing it')
        elif not upload:
            summary['actions'].append('already published and complete: nothing to do')
            log('already published and complete: nothing to do')
        else:
            log('already published: only the missing asset(s) were added')
    summary['digest_checked'] = bool(release.get('assets')) and all(a.get('digest') for a in release.get('assets') or [])
    return summary


def gh_command(arguments, run=subprocess.run):
    """Runs gh (GH_BIN overrides the program) and returns its output (an Output: the stdout text that also
    carries the exit code, the stderr and the duration); any failure becomes a Failure."""
    program = os.environ.get('GH_BIN', 'gh')
    started = time.monotonic()
    try:
        done = run([program, *arguments], capture_output=True, text=True, encoding='utf-8', errors='replace')
    except OSError as error:
        raise Failure(f'cannot run {program}: {error}') from error
    result = output(done.stdout or '', done.returncode, done.stderr or '', time.monotonic() - started)
    if done.returncode != 0:
        raise Failure(f'gh {" ".join(arguments[:2])} failed ({done.returncode}): {(result.stderr or result).strip()[-600:]}',
                      result=result)
    return result


def tail(text, limit=TAIL_CHARS):
    text = text.strip()
    return ('[...] ' + text[-limit:]) if len(text) > limit else text


def report(log, result, quiet_stdout=False):
    """The log lines of a finished gh command: exit code, duration, sizes and the tails of stderr and stdout."""
    stderr = getattr(result, 'stderr', '')
    seconds = getattr(result, 'seconds', None)
    log(f'  exit code {getattr(result, "returncode", 0)}' + ('' if seconds is None else f' after {seconds:.1f} s')
        + f'; stdout {len(result)} bytes, stderr {len(stderr)} bytes')
    for name, text in (('stderr', stderr), ('stdout', str(result))):
        shown = tail(text)
        if shown and not (name == 'stdout' and quiet_stdout):
            log(f'  {name} tail:\n      ' + shown.replace('\n', '\n      '))


def traced(gh, log):
    """A gh runner that logs every command before it runs (a hung command is then named in the log), and after it
    its exit code, duration and output tails; a failed one is logged the same way before the Failure goes on."""
    def run(arguments):
        log(f'$ {os.environ.get("GH_BIN", "gh")} ' + shlex.join(arguments))
        try:
            result = gh(arguments)
        except Failure as error:
            if error.result is not None:
                report(log, error.result)
            else:
                log(f'  failed without an exit code: {error.message}')
            raise
        report(log, result, quiet_stdout=arguments[:1] == ['api'])
        return result
    return run


def stderr_log(text):
    for line in redact(text).splitlines() or ['']:
        print('[publish] ' + line, file=sys.stderr, flush=True)


def main(argv=None, gh=gh_command, log=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--notes-file', required=True)
    parser.add_argument('--assets-dir', required=True)
    parser.add_argument('--sums', required=True, help='name of the checksum file inside the assets directory')
    parser.add_argument('--channel', required=True, choices=('prerelease', 'stable'))
    parser.add_argument('--dry-run', action='store_true', help='read, but create, edit and upload nothing')
    parser.add_argument('--verbose', action='store_true',
                        help='log every gh command with its exit code and output tails, and every step, on stderr')
    args = parser.parse_args(argv)
    sink = None
    if args.verbose:
        sink = log or stderr_log
        gh = traced(gh, sink)
    try:
        summary = publish(gh, args.repository, args.tag, args.title, args.notes_file, args.assets_dir, args.sums,
                          args.channel == 'prerelease', args.dry_run, log=sink)
    except Failure as error:
        print(f'FAIL {redact(str(error))}', file=sys.stderr)
        if args.verbose and error.__cause__ is not None:
            print(redact(''.join(traceback.format_exception(error.__cause__))), file=sys.stderr, end='')
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
