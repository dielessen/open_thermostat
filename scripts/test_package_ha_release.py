"""Release integrity, dirty source, symlink and failed-test denial checks."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
import zipfile

from package_ha_release import package


class HARelease(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.integration = self.root/'ha/config/custom_components/open_thermostat'
        self.integration.mkdir(parents=True)
        (self.integration/'__init__.py').write_text('# fixture integration\n')
        (self.integration/'manifest.json').write_text(json.dumps(dict(domain='open_thermostat', version='0.4.0.dev11')))
        (self.root/'LICENSE').write_text('Original fixture license\n')
        notes = self.root/'docs/modern-thermostat/HA-RELEASE-NOTES.md'; notes.parent.mkdir(parents=True)
        notes.write_text('Fixture testrelease\n'); (self.root/'.gitignore').write_text('out/\n')
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        self.commit()
        self.results = self.root/'out/native.xml'; self.results.parent.mkdir()
        self.results.write_text('<testsuites><testsuite tests="5" errors="0" failures="0" skipped="1"/></testsuites>')

    def commit(self):
        subprocess.run(['git', 'add', '-A'], cwd=self.root, check=True)
        subprocess.run(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@local.invalid',
                        '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'fixture'], cwd=self.root, check=True)

    def test_exact_repeatable_source_and_archive(self):
        first = package(self.root, self.root/'out/a', self.results)
        second = package(self.root, self.root/'out/b', self.results)
        self.assertEqual(first, second)
        self.assertEqual((self.root/'out/a'/first['asset']).read_bytes(), (self.root/'out/b'/second['asset']).read_bytes())
        with zipfile.ZipFile(self.root/'out/a'/first['asset']) as zip:
            self.assertEqual(zip.read('custom_components/open_thermostat/__init__.py'), (self.integration/'__init__.py').read_bytes())
            self.assertFalse(any('.storage' in name or name.endswith('.bin') for name in zip.namelist()))

    def test_dirty_worktree_denied(self):
        (self.integration/'__init__.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'requires_clean_source'):
            package(self.root, self.root/'out/a', self.results)

    def test_failing_native_suite_denied(self):
        self.results.write_text('<testsuite tests="5" errors="0" failures="1" skipped="0"/>')
        with self.assertRaisesRegex(ValueError, 'suite_not_passed'):
            package(self.root, self.root/'out/a', self.results)

    def test_all_skipped_native_suite_denied(self):
        self.results.write_text('<testsuite tests="5" errors="0" failures="0" skipped="5"/>')
        with self.assertRaisesRegex(ValueError, 'suite_not_passed'):
            package(self.root, self.root/'out/a', self.results)

    def test_committed_external_symlink_denied(self):
        (self.integration/'leak.py').symlink_to(self.root/'LICENSE'); self.commit()
        with self.assertRaisesRegex(ValueError, 'symlink_not_allowed'):
            package(self.root, self.root/'out/a', self.results)

    def test_committed_private_or_unknown_payload_denied(self):
        (self.integration/'.storage').write_text('private fixture'); self.commit()
        with self.assertRaisesRegex(ValueError, 'unexpected_HA_source_file'):
            package(self.root, self.root/'out/a', self.results)

    def test_existing_release_output_not_overwritten(self):
        target = self.root/'out/a'; package(self.root, target, self.results)
        with self.assertRaisesRegex(ValueError, 'output_must_be_empty'):
            package(self.root, target, self.results)


if __name__ == '__main__': unittest.main()
