"""The release publication can be repeated: a partial release is completed, a published one is never overwritten (R5-14)."""
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == '__main__':
    unittest.main()
