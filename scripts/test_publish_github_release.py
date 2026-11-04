"""The release publication can be repeated: a partial release is completed, a published one is never overwritten (R5-14)."""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_github_release as publisher  # noqa: E402

REPO, TAG = 'owner/project', 'v1.0.0-e32v2-rc.9'


class FakeGitHub:
    """The few gh commands the publisher uses, with the behaviour that matters: drafts, assets, --clobber."""

    def __init__(self, fail_upload_after=None, digests=True):
        self.releases, self.calls, self.next_id = [], [], 1
        self.fail_upload_after, self.digests = fail_upload_after, digests

    def __call__(self, args):
        self.calls.append(list(args))
        if args == ['--version']:
            return 'gh version 2.99.0 (fake)\n'
        if args[:3] == ['api', '--paginate', '--slurp']:
            return json.dumps([[json.loads(json.dumps(r)) for r in self.releases]])
        if args[:2] == ['release', 'create']:
            assert '--repo' in args and '--verify-tag' in args
            tag = args[2]
            if any(r['tag_name'] == tag and not r['draft'] for r in self.releases):
                raise publisher.Failure('a release with the same tag name already exists')
            self.releases.append({'id': self.next_id, 'tag_name': tag, 'draft': '--draft' in args,
                                  'prerelease': '--prerelease' in args, 'name': args[args.index('--title') + 1],
                                  'body': Path(args[args.index('--notes-file') + 1]).read_text(), 'assets': []})
            self.next_id += 1
            return ''
        release = next(r for r in self.releases if r['tag_name'] == args[2])
        if args[:2] == ['release', 'upload']:
            paths = [a for a in args[3:] if not a.startswith('--') and a != REPO]
            for position, path in enumerate(paths):
                if self.fail_upload_after is not None and position >= self.fail_upload_after:
                    raise publisher.Failure('HTTP 502 while uploading ' + Path(path).name)
                name, raw = Path(path).name, Path(path).read_bytes()
                existing = [a for a in release['assets'] if a['name'] == name]
                if existing and '--clobber' not in args:
                    raise publisher.Failure('asset under the same name already exists: ' + name)
                release['assets'] = [a for a in release['assets'] if a['name'] != name]
                asset = {'name': name, 'size': len(raw), 'state': 'uploaded'}
                if self.digests:
                    asset['digest'] = 'sha256:' + hashlib.sha256(raw).hexdigest()
                release['assets'].append(asset)
            return ''
        if args[:2] == ['release', 'edit']:
            if '--draft=false' in args:
                release['draft'] = False
            if '--title' in args:
                release['name'] = args[args.index('--title') + 1]
            if '--notes-file' in args:
                release['body'] = Path(args[args.index('--notes-file') + 1]).read_text()
            return ''
        raise AssertionError(args)

    def verbs(self):
        return [' '.join(c[:2]) for c in self.calls if c[0] == 'release']


class ListLags(FakeGitHub):
    """GitHub's release list does not show a draft that was created a moment ago (it shows an untagged one)."""

    def __call__(self, args):
        if args[:3] == ['api', '--paginate', '--slurp'] and any(c[:2] == ['release', 'create'] for c in self.calls):
            self.calls.append(list(args))
            return json.dumps([[{'id': 9, 'tag_name': 'untagged-8a3f', 'name': 'Title', 'draft': True, 'prerelease': True,
                                 'assets': []}]])
        return super().__call__(args)


class DropsAnAsset(FakeGitHub):
    """An upload that GitHub accepted, but whose last asset is not on the release when it is read back."""

    def __call__(self, args):
        result = super().__call__(args)
        if args[:2] == ['release', 'upload']:
            self.releases[0]['assets'].pop()
        return result


class KeepsTheDraft(FakeGitHub):
    """The edit that publishes the draft has no effect."""

    def __call__(self, args):
        if args[:2] == ['release', 'edit'] and '--draft=false' in args:
            self.calls.append(list(args))
            return ''
        return super().__call__(args)


class Answers(FakeGitHub):
    """The release list is whatever the test says (not JSON, or a list of the wrong things)."""

    def __init__(self, answer):
        super().__init__()
        self.answer = answer

    def __call__(self, args):
        if args[:3] == ['api', '--paginate', '--slurp']:
            self.calls.append(list(args))
            return self.answer
        return super().__call__(args)


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        for name, data in (('firmware.bin', b'F' * 5000), ('e32v2-update.json', b'{"version":"x"}'), ('notes.txt', b'n' * 10)):
            (self.assets / name).write_bytes(data)
        self.write_sums()
        self.notes = self.root / 'notes.md'
        self.notes.write_text('# notes\n')

    def write_sums(self):
        names = sorted(p.name for p in self.assets.iterdir() if p.name != 'SUMS.txt')
        (self.assets / 'SUMS.txt').write_text(''.join(
            hashlib.sha256((self.assets / n).read_bytes()).hexdigest() + '  ' + n + '\n' for n in names))

    def publish(self, gh, prerelease=True, dry_run=False):
        return publisher.publish(gh, REPO, TAG, 'Title', self.notes, self.assets, 'SUMS.txt', prerelease, dry_run)

    def test_fresh_release_is_a_draft_until_everything_is_uploaded_and_checked(self):
        gh = FakeGitHub()
        summary = self.publish(gh)
        release = gh.releases[0]
        self.assertFalse(release['draft'])
        self.assertTrue(release['prerelease'])
        self.assertEqual(sorted(a['name'] for a in release['assets']), ['SUMS.txt', 'e32v2-update.json', 'firmware.bin', 'notes.txt'])
        self.assertEqual(gh.verbs(), ['release create', 'release upload', 'release edit'])
        create = next(c for c in gh.calls if c[:2] == ['release', 'create'])
        self.assertIn('--draft', create)
        self.assertFalse([a for a in create if a in (str(self.assets / 'firmware.bin'),)], 'no asset in the create call')
        self.assertEqual([c for c in gh.calls if c[0] == 'release'][-1][-1], '--draft=false', 'publishing comes last')
        self.assertTrue(summary['digest_checked'])

    def test_stable_release_is_not_a_prerelease(self):
        gh = FakeGitHub()
        self.publish(gh, prerelease=False)
        self.assertFalse(gh.releases[0]['prerelease'])
        self.assertNotIn('--prerelease', next(c for c in gh.calls if c[:2] == ['release', 'create']))

    def test_a_failed_upload_leaves_a_draft_and_a_rerun_completes_it(self):
        gh = FakeGitHub(fail_upload_after=2)
        with self.assertRaises(publisher.Failure):
            self.publish(gh)
        self.assertTrue(gh.releases[0]['draft'], 'a partial release is never published')
        self.assertEqual(len(gh.releases[0]['assets']), 2)
        gh.fail_upload_after = None
        gh.calls.clear()
        summary = self.publish(gh)
        self.assertFalse(gh.releases[0]['draft'])
        self.assertEqual(len(gh.releases), 1, 'no second release')
        self.assertEqual(len(gh.releases[0]['assets']), 4)
        self.assertEqual(len(summary['uploaded']), 2, 'only what was missing is uploaded again')
        self.assertNotIn('release create', gh.verbs())

    def test_a_corrupt_or_incomplete_asset_of_a_draft_is_replaced(self):
        gh = FakeGitHub()
        gh.releases.append({'id': 7, 'tag_name': TAG, 'draft': True, 'prerelease': True, 'name': 'old', 'body': '',
                            'assets': [{'name': 'firmware.bin', 'size': 17, 'state': 'uploaded', 'digest': 'sha256:' + '0' * 64},
                                       {'name': 'notes.txt', 'size': 10, 'state': 'starter'}]})
        self.publish(gh)
        release = gh.releases[0]
        self.assertFalse(release['draft'])
        self.assertEqual(release['name'], 'Title')
        upload = next(c for c in gh.calls if c[:2] == ['release', 'upload'])
        self.assertIn('--clobber', upload)
        sizes = {a['name']: a['size'] for a in release['assets']}
        self.assertEqual(sizes['firmware.bin'], 5000)

    def test_a_complete_published_release_is_left_alone(self):
        gh = FakeGitHub()
        self.publish(gh)
        gh.calls.clear()
        summary = self.publish(gh)
        self.assertEqual(gh.verbs(), [], 'nothing is created, uploaded or edited')
        self.assertIn('already published and complete: nothing to do', summary['actions'])

    def test_a_published_release_missing_an_asset_gets_only_that_asset_without_clobber(self):
        gh = FakeGitHub()
        self.publish(gh)
        gh.releases[0]['assets'] = [a for a in gh.releases[0]['assets'] if a['name'] != 'notes.txt']
        gh.calls.clear()
        summary = self.publish(gh)
        upload = next(c for c in gh.calls if c[:2] == ['release', 'upload'])
        self.assertNotIn('--clobber', upload)
        self.assertEqual(summary['uploaded'], ['notes.txt'])
        self.assertEqual(gh.verbs(), ['release upload'], 'a published release is not edited')

    def test_a_published_asset_that_differs_is_never_overwritten(self):
        gh = FakeGitHub()
        self.publish(gh)
        gh.releases[0]['assets'][0]['size'] += 1
        gh.calls.clear()
        with self.assertRaisesRegex(publisher.Failure, 'nothing is overwritten'):
            self.publish(gh)
        self.assertEqual(gh.verbs(), [])

    def test_the_release_channel_must_match(self):
        gh = FakeGitHub()
        self.publish(gh, prerelease=True)
        gh.calls.clear()
        with self.assertRaisesRegex(publisher.Failure, 'expected a normal release'):
            self.publish(gh, prerelease=False)
        self.assertEqual(gh.verbs(), [])

    def test_without_digests_the_size_is_still_checked(self):
        gh = FakeGitHub(digests=False)
        summary = self.publish(gh)
        self.assertFalse(summary['digest_checked'])
        self.assertFalse(gh.releases[0]['draft'])

    def test_local_files_must_match_their_checksum_file_before_anything_is_sent(self):
        (self.assets / 'firmware.bin').write_bytes(b'tampered')
        gh = FakeGitHub()
        with self.assertRaisesRegex(publisher.Failure, 'does not match'):
            self.publish(gh)
        self.assertEqual(gh.calls, [])
        self.write_sums()
        (self.assets / 'extra.bin').write_bytes(b'x')
        with self.assertRaisesRegex(publisher.Failure, 'not listed in SUMS.txt'):
            self.publish(gh)
        self.assertEqual(gh.calls, [])

    def test_an_unexpected_asset_or_a_duplicate_release_stops_the_run(self):
        gh = FakeGitHub()
        gh.releases.append({'id': 1, 'tag_name': TAG, 'draft': True, 'prerelease': True, 'name': 'x', 'body': '',
                            'assets': [{'name': 'stray.bin', 'size': 1, 'state': 'uploaded'}]})
        with self.assertRaisesRegex(publisher.Failure, 'not part of this package: stray.bin'):
            self.publish(gh)
        gh.releases.append({**gh.releases[0], 'id': 2})
        with self.assertRaisesRegex(publisher.Failure, '2 releases'):
            self.publish(gh)

    def test_dry_run_changes_nothing(self):
        gh = FakeGitHub()
        with contextlib.redirect_stdout(io.StringIO()):
            self.publish(gh, dry_run=True)
        self.assertEqual(gh.releases, [])
        self.assertEqual(gh.verbs(), [])

    def test_command_line_reports_failures_with_a_status(self):
        gh = FakeGitHub(fail_upload_after=1)
        arguments = ['--repository', REPO, '--tag', TAG, '--title', 'Title', '--notes-file', str(self.notes),
                     '--assets-dir', str(self.assets), '--sums', 'SUMS.txt', '--channel', 'prerelease']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(publisher.main(arguments, gh=gh), 1)
            gh.fail_upload_after = None
            self.assertEqual(publisher.main(arguments, gh=gh), 0)
        self.assertFalse(gh.releases[0]['draft'])


    # ---- --verbose: the job log of a first attempt, and a failure that names its step ----------------------------

    def arguments(self, *extra):
        return ['--repository', REPO, '--tag', TAG, '--title', 'Title', '--notes-file', str(self.notes),
                '--assets-dir', str(self.assets), '--sums', 'SUMS.txt', '--channel', 'prerelease', *extra]

    def run_main(self, gh, *extra):
        lines, out, err = [], io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = publisher.main(self.arguments(*extra), gh=gh, log=lines.append)
        return status, lines, out.getvalue(), err.getvalue()

    def test_verbose_logs_every_gh_command_before_it_runs_and_every_step(self):
        gh = FakeGitHub()
        status, lines, out, err = self.run_main(gh, '--verbose')
        self.assertEqual(status, 0)
        commands = [line for line in lines if line.startswith('$ ')]
        self.assertEqual(len(commands), len(gh.calls), 'every gh command is logged, once')
        self.assertTrue(commands[0].endswith(' --version'), commands[0])
        self.assertEqual(len([c for c in commands if ' release create ' in c]), 1)
        text = '\n'.join(lines)
        names = ('verify the local assets', 'find the release of the tag', 'prepare the release', 'upload the assets',
                 'read the release back', 'publish the draft')
        starts = [text.index(f'step {n} of 6 ({name}): start') for n, name in enumerate(names, 1)]
        ends = [text.index(f'step {n} of 6 ({name}): done in') for n, name in enumerate(names, 1)]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(start < end for start, end in zip(starts, ends)))
        self.assertTrue(all(ends[i] < starts[i + 1] for i in range(5)), 'a step ends before the next one starts')
        self.assertIn('preflight (check the environment): done', text)
        self.assertIn('exit code 0', text)
        self.assertIn('no release has the tag', text)
        self.assertIn(f'release 1 {TAG!r} (draft, pre-release): 0 asset(s)', text)
        self.assertIn(f'release 1 {TAG!r} (published, pre-release): 4 asset(s)', text)
        self.assertEqual(json.loads(out)['tag'], TAG, 'the summary stays on stdout')
        self.assertEqual(err, '')

    def test_without_verbose_nothing_is_logged_and_gh_is_not_asked_for_its_version(self):
        gh = FakeGitHub()
        status, lines, out, err = self.run_main(gh)
        self.assertEqual((status, lines, err), (0, [], ''))
        self.assertNotIn(['--version'], gh.calls)

    def test_verbose_names_the_ci_run_and_attempt_and_whether_a_token_is_set(self):
        ci = {'GITHUB_RUN_ID': '41641214816', 'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_OS': 'Linux', 'GH_TOKEN': 'ghs_0123456789abcdef'}
        with mock.patch.dict(os.environ, ci):
            status, lines, out, err = self.run_main(FakeGitHub(), '--verbose')
        text = '\n'.join(lines)
        self.assertIn('GH_TOKEN set; GITHUB_RUN_ID 41641214816; GITHUB_RUN_ATTEMPT 1; RUNNER_OS Linux', text)
        self.assertNotIn('ghs_0123456789abcdef', text)
        with mock.patch.dict(os.environ):
            for name in ci:
                os.environ.pop(name, None)
            status, lines, out, err = self.run_main(FakeGitHub(), '--verbose')
        self.assertIn('GH_TOKEN NOT set', '\n'.join(lines))
        self.assertNotIn('GITHUB_RUN_ID', '\n'.join(lines))

    def test_verbose_goes_to_stderr_by_default(self):
        gh, out, err = FakeGitHub(), io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(publisher.main(self.arguments('--verbose'), gh=gh), 0)
        self.assertIn('[publish] step 1 of 6 (verify the local assets): start', err.getvalue())
        self.assertIn('[publish] $ gh --version', err.getvalue())
        self.assertEqual(json.loads(out.getvalue())['tag'], TAG)

    def test_a_dry_run_can_be_verbose_too(self):
        gh = FakeGitHub()
        status, lines, out, err = self.run_main(gh, '--verbose', '--dry-run')
        self.assertEqual(status, 0)
        self.assertEqual(gh.releases, [])
        self.assertIn('as a prerelease release (dry run)', '\n'.join(lines))
        self.assertIn('dry run: not read', '\n'.join(lines))

    def failing_cases(self):
        """(label, a FakeGitHub, what the failure text starts with), each with the assets of a fresh setUp."""
        def stray():
            gh = FakeGitHub()
            gh.releases.append({'id': 1, 'tag_name': TAG, 'draft': True, 'prerelease': True, 'name': 'x', 'body': '',
                                'assets': [{'name': 'stray.bin', 'size': 1, 'state': 'uploaded'}]})
            return gh

        def duplicate():
            gh = FakeGitHub()
            row = {'id': 1, 'tag_name': TAG, 'draft': True, 'prerelease': True, 'name': 'x', 'body': '', 'assets': []}
            gh.releases += [row, {**row, 'id': 2}]
            return gh

        return [
            ('two releases with the tag', duplicate(), 'step 2 of 6 (find the release of the tag): 2 releases'),
            ('a list that is not JSON', Answers('<html>502 Bad Gateway</html>'),
             'step 2 of 6 (find the release of the tag): GitHub did not answer with a list of releases'),
            ('a list of the wrong things', Answers('[[1, 2]]'),
             'step 2 of 6 (find the release of the tag): unexpected AttributeError'),
            ('a list that lags behind the creation', ListLags(),
             f'step 3 of 6 (prepare the release): release {TAG} was not found after creating it'),
            ('an asset that is not part of the package', stray(),
             f'step 3 of 6 (prepare the release): release {TAG} has assets that are not part of this package'),
            ('a failing upload', FakeGitHub(fail_upload_after=1), 'step 4 of 6 (upload the assets): HTTP 502 while uploading'),
            ('an upload that is not on the release afterwards', DropsAnAsset(),
             'step 5 of 6 (read the release back): after the upload the release is not complete'),
            ('a draft that stays a draft', KeepsTheDraft(),
             f'step 6 of 6 (publish the draft): release {TAG} is still a draft after publishing it'),
        ]

    def test_every_failure_names_the_step_it_came_from(self):
        for label, gh, expected in self.failing_cases():
            with self.subTest(label):
                with self.assertRaises(publisher.Failure) as caught:
                    self.publish(gh)
                self.assertTrue(str(caught.exception).startswith(expected), str(caught.exception))
                self.assertEqual(str(caught.exception), f'{caught.exception.step}: {caught.exception.message}')

    def test_a_tampered_local_file_is_step_one(self):
        (self.assets / 'firmware.bin').write_bytes(b'tampered')
        with self.assertRaises(publisher.Failure) as caught:
            self.publish(FakeGitHub())
        self.assertEqual(str(caught.exception), 'step 1 of 6 (verify the local assets): firmware.bin does not match SUMS.txt')

    def test_a_published_release_with_a_different_asset_fails_in_the_preparation(self):
        gh = FakeGitHub()
        self.publish(gh)
        gh.releases[0]['assets'][0]['size'] += 1
        with self.assertRaisesRegex(publisher.Failure, r'^step 3 of 6 \(prepare the release\): .*nothing is overwritten'):
            self.publish(gh)

    def test_the_failure_line_of_the_command_line_names_the_step_and_the_log_says_what_was_running(self):
        gh = FakeGitHub(fail_upload_after=1)
        status, lines, out, err = self.run_main(gh, '--verbose')
        self.assertEqual(status, 1)
        self.assertIn('FAIL step 4 of 6 (upload the assets): HTTP 502 while uploading', err)
        text = '\n'.join(lines)
        self.assertIn('step 4 of 6 (upload the assets): FAILED after', text)
        upload = [line for line in lines if line.startswith('$ ') and ' release upload ' in line]
        self.assertEqual(len(upload), 1)
        self.assertIn(' --clobber', upload[0], 'the command that failed is in the log')
        self.assertEqual(out, '')

    def test_a_failure_without_verbose_still_names_the_step(self):
        status, lines, out, err = self.run_main(FakeGitHub(fail_upload_after=1))
        self.assertEqual((status, lines), (1, []))
        self.assertTrue(err.startswith('FAIL step 4 of 6 (upload the assets): HTTP 502'), err)

    def test_a_listing_that_lags_shows_the_drafts_it_does_contain(self):
        status, lines, out, err = self.run_main(ListLags(), '--verbose')
        self.assertEqual(status, 1)
        self.assertIn("drafts: 'untagged-8a3f' named 'Title'", '\n'.join(lines))
        self.assertIn('FAIL step 3 of 6 (prepare the release)', err)

    def test_an_unexpected_error_still_names_its_step_and_keeps_its_traceback(self):
        status, lines, out, err = self.run_main(Answers('[[1]]'), '--verbose')
        self.assertEqual(status, 1)
        self.assertIn('FAIL step 2 of 6 (find the release of the tag): unexpected AttributeError', err)
        self.assertIn('Traceback', err)

    def test_the_real_runner_reports_exit_code_stderr_and_stdout_of_a_failed_command(self):
        code = 'import sys; sys.stdout.write("partial answer"); sys.stderr.write("HTTP 422: Validation Failed"); sys.exit(3)'
        lines = []
        with mock.patch.dict(os.environ, {'GH_BIN': sys.executable}):
            with self.assertRaisesRegex(publisher.Failure, r'failed \(3\): HTTP 422: Validation Failed') as caught:
                publisher.traced(publisher.gh_command, lines.append)(['-c', code])
        self.assertEqual((caught.exception.result.returncode, caught.exception.result.stderr), (3, 'HTTP 422: Validation Failed'))
        text = '\n'.join(lines)
        self.assertTrue(lines[0].startswith('$ ' + sys.executable + ' -c '), lines[0])
        self.assertIn('exit code 3 after', text)
        self.assertIn('HTTP 422: Validation Failed', text)
        self.assertIn('partial answer', text)

    def test_the_real_runner_reports_a_successful_command_and_keeps_only_the_tails(self):
        code = 'import sys; sys.stdout.write("x" * 2000 + "END"); sys.stderr.write("a warning")'
        lines = []
        with mock.patch.dict(os.environ, {'GH_BIN': sys.executable}):
            result = publisher.traced(publisher.gh_command, lines.append)(['-c', code])
        self.assertEqual((str(result)[-3:], result.returncode, result.stderr), ('END', 0, 'a warning'))
        text = '\n'.join(lines)
        self.assertIn('exit code 0 after', text)
        self.assertIn('stdout 2003 bytes, stderr 9 bytes', text)
        self.assertIn('[...] ', text)
        self.assertIn('a warning', text)
        self.assertLess(len(text), 1800)

    def test_a_successful_api_read_logs_its_size_and_not_its_tail(self):
        big = json.dumps([[{'tag_name': 'v0.0.1-e32v2', 'body': 'x' * 5000}]])
        lines = []
        publisher.traced(lambda args: big, lines.append)(['api', '--paginate', '--slurp', 'repos/o/p/releases'])
        text = '\n'.join(lines)
        self.assertIn(f'stdout {len(big)} bytes', text)
        self.assertNotIn('stdout tail', text)

    def test_a_missing_gh_program_is_a_failure_that_names_it(self):
        with mock.patch.dict(os.environ, {'GH_BIN': str(self.root / 'no-such-gh')}):
            with self.assertRaisesRegex(publisher.Failure, 'cannot run .*no-such-gh') as caught:
                publisher.gh_command(['--version'])
            lines = []
            with self.assertRaises(publisher.Failure):
                publisher.traced(publisher.gh_command, lines.append)(['--version'])
        self.assertIn('not run: cannot run', '\n'.join(lines))
        self.assertIsNone(caught.exception.result)

    def test_gh_command_failures_keep_their_text_for_the_job_log(self):
        def run(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, stdout='', stderr='gh: HTTP 403: Resource not accessible')
        with mock.patch.dict(os.environ, {'GH_BIN': 'gh-test'}):
            with self.assertRaisesRegex(publisher.Failure, r'^gh release create failed \(1\): gh: HTTP 403: Resource not accessible$'):
                publisher.gh_command(['release', 'create', 'v1'], run=run)

    def test_the_token_is_never_logged(self):
        token = 'ghs_0123456789abcdefABCDEF'
        gh = FakeGitHub(fail_upload_after=0)
        original = gh.__call__

        def leaky(args):
            try:
                return original(args)
            except publisher.Failure as error:
                raise publisher.Failure(f'{error.message} (token {token})') from None

        err = io.StringIO()
        with mock.patch.dict(os.environ, {'GH_TOKEN': token}), contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            publisher.stderr_log(f'gh said: bad credentials {token}\nsecond line')
            self.assertEqual(publisher.main(self.arguments('--verbose'), gh=leaky), 1)
        self.assertNotIn(token, err.getvalue())
        self.assertIn('[publish] gh said: bad credentials ***', err.getvalue())
        self.assertIn('FAIL step 4 of 6 (upload the assets): HTTP 502 while uploading', err.getvalue())

    def test_the_workflow_runs_both_publish_steps_verbosely(self):
        workflow = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'build.yml'
        if not workflow.is_file():
            self.skipTest('no workflow in this tree')
        calls = [line for line in workflow.read_text(encoding='utf-8').splitlines()
                 if 'scripts/publish_github_release.py' in line and '--repository' in line]
        self.assertEqual(len(calls), 2, 'one publish step for the E32 firmware and one for Home Assistant')
        for call in calls:
            self.assertIn(' --verbose', call)


if __name__ == '__main__':
    unittest.main()
