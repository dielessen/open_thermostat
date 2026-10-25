"""Release integrity, dirty source, symlink and failed-test denial checks."""
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
import zipfile

from package_ha_release import package
from ha_test_evidence import snapshot
import xml.etree.ElementTree as ET


class HARelease(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.integration = self.root/'ha/config/custom_components/open_thermostat'
        self.integration.mkdir(parents=True)
        (self.integration/'__init__.py').write_text('# fixture integration\n')
        (self.integration/'product.py').write_text('SUPPORTED_HA_VERSIONS=("2026.10.2","2026.10.3","2026.10.4")\n')
        (self.integration/'manifest.json').write_text(json.dumps(dict(domain='open_thermostat', version='0.4.0.dev11')))
        (self.root/'LICENSE').write_text('Original fixture license\n')
        notes = self.root/'docs/modern-thermostat/HA-RELEASE-NOTES.md'; notes.parent.mkdir(parents=True)
        notes.write_text('Fixture testrelease\n'); (self.root/'.gitignore').write_text('out/\n')
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        self.commit()
        self.results = self.root/'out/native.xml'; self.results.parent.mkdir()
        suite=ET.Element('testsuite',tests='5',errors='0',failures='0',skipped='1')
        props=ET.SubElement(suite,'properties')
        values={**snapshot(self.root),'unchanged_source':True,'ha_core':'2026.10.4'}
        for name,value in values.items():
            ET.SubElement(props,'property',name='opth.'+name,value=str(value).lower() if isinstance(value,bool) else value)
        ET.ElementTree(suite).write(self.results)

    def refresh_evidence(self):
        tree=ET.parse(self.results)
        for prop in tree.getroot().iter('property'):
            field=prop.get('name','').removeprefix('opth.')
            if field in snapshot(self.root):
                value=snapshot(self.root)[field]
                prop.set('value',str(value).lower() if isinstance(value,bool) else value)
        tree.write(self.results)

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

    def test_only_canonical_ha_release_versions_can_be_packaged(self):
        for version in ('0.4.0.beta1','0.4.0b01','00.4.0b1','0.4.0bogus','0.4.0b4294967296'):
            with self.subTest(version=version):
                (self.integration/'manifest.json').write_text(json.dumps(dict(domain='open_thermostat',version=version)))
                self.commit()
                with self.assertRaisesRegex(ValueError,'invalid_HA_release_identity'):
                    package(self.root,self.root/'out/a',self.results)

    def test_dirty_worktree_denied(self):
        (self.integration/'__init__.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'requires_clean_source'):
            package(self.root, self.root/'out/a', self.results)

    def test_failing_native_suite_denied(self):
        self.results.write_text('<testsuite tests="5" errors="0" failures="1" skipped="0"/>')
        with self.assertRaisesRegex(ValueError, 'suite_not_passed'):
            package(self.root, self.root/'out/a', self.results)

    def test_negative_counts_cannot_cancel_failures_or_fabricate_executed_cases(self):
        for document in [
            '<testsuite tests="-5" errors="0" failures="0" skipped="-6"/>',
            '<testsuites><testsuite tests="5" failures="1"/><testsuite tests="5" failures="-1"/></testsuites>',
        ]:
            self.results.write_text(document)
            with self.assertRaisesRegex(ValueError,'suite_not_passed'):
                package(self.root,self.root/'out/a',self.results)

    def test_all_skipped_native_suite_denied(self):
        self.results.write_text('<testsuite tests="5" errors="0" failures="0" skipped="5"/>')
        with self.assertRaisesRegex(ValueError, 'suite_not_passed'):
            package(self.root, self.root/'out/a', self.results)

    def test_committed_external_symlink_denied(self):
        (self.integration/'leak.py').symlink_to(self.root/'LICENSE'); self.commit(); self.refresh_evidence()
        with self.assertRaisesRegex(ValueError, 'source_evidence_missing_or_stale|symlink_not_allowed'):
            package(self.root, self.root/'out/a', self.results)

    def test_committed_private_or_unknown_payload_denied(self):
        (self.integration/'.storage').write_text('private fixture'); self.commit(); self.refresh_evidence()
        with self.assertRaisesRegex(ValueError, 'unexpected_HA_source_file'):
            package(self.root, self.root/'out/a', self.results)

    def test_missing_stale_or_inconsistent_native_evidence_denied(self):
        original=self.results.read_bytes()
        for field,value in [('source_commit','a'*40),('source_sha256','b'*64),
                            ('clean_source','false'),('unchanged_source','false')]:
            with self.subTest(field=field):
                tree=ET.parse(self.results)
                for prop in tree.getroot().iter('property'):
                    if prop.get('name')=='opth.'+field:prop.set('value',value)
                tree.write(self.results)
                with self.assertRaisesRegex(ValueError,'source_evidence_missing_or_stale'):
                    package(self.root,self.root/'out/a',self.results)
                self.results.write_bytes(original)
        self.results.write_text('<testsuite tests="5" errors="0" failures="0" skipped="0"/>')
        with self.assertRaisesRegex(ValueError,'source_evidence_missing_or_stale'):
            package(self.root,self.root/'out/a',self.results)

    def test_duplicate_and_unreviewed_core_evidence_denied(self):
        original=self.results.read_bytes();tree=ET.parse(self.results)
        for prop in tree.getroot().iter('property'):
            if prop.get('name')=='opth.ha_core':prop.set('value','2026.11.0')
        tree.write(self.results)
        with self.assertRaisesRegex(ValueError,'core_not_reviewed'):
            package(self.root,self.root/'out/a',self.results)
        self.results.write_bytes(original);tree=ET.parse(self.results)
        ET.SubElement(tree.getroot().find('properties'),'property',name='opth.ha_core',value='2026.10.4')
        tree.write(self.results)
        with self.assertRaisesRegex(ValueError,'duplicate_source_evidence'):
            package(self.root,self.root/'out/a',self.results)

    def test_existing_release_output_not_overwritten(self):
        target = self.root/'out/a'; package(self.root, target, self.results)
        with self.assertRaisesRegex(ValueError, 'output_must_be_empty'):
            package(self.root, target, self.results)


if __name__ == '__main__': unittest.main()
