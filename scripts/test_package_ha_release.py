"""Release integrity, dirty source, symlink and failed-test denial checks."""
from pathlib import Path
import json
import sys
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
        extensions=self.root/'integrations/zigbee2mqtt';extensions.mkdir(parents=True)
        for name,klass in [('original-temperature.cjs','OpenThermostatOriginalTemperature'),('original-tv02.cjs','OpenThermostatOriginalTv02')]:
            (extensions/name).write_text('const DEVICE_BINDINGS = Object.freeze([]);\nmodule.exports = class '+klass+' {};\n')
        (self.root/'scripts').mkdir();(self.root/'scripts/prepare_original_report_pins.py').write_bytes(Path(__file__).with_name('prepare_original_report_pins.py').read_bytes())
        guide=self.root/'docs/modern-thermostat/Z2M-RELEASE-COMPANION.nl-en.md';guide.parent.mkdir(parents=True)
        guide.write_text('Fixture optional receive-only guide\n')
        (self.root/'LICENSE').write_text('Original fixture license\n')
        notes = self.root/'docs/modern-thermostat/HA-RELEASE-NOTES.md'; notes.parent.mkdir(parents=True,exist_ok=True)
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

    def test_companion_archive_is_exact_separate_and_contains_no_private_pins(self):
        from zigbee_report_companion import SOURCES
        metadata=package(self.root,self.root/'out/a',self.results)
        companion,=metadata['optional_companions']
        self.assertEqual(companion['source_commit'],metadata['source_commit'])
        self.assertFalse(companion['installed']);self.assertFalse(companion['authorizes_control'])
        self.assertFalse(companion['private_bindings_included'])
        with zipfile.ZipFile(self.root/'out/a'/metadata['asset']) as main:
            self.assertNotIn('extensions/original-tv02.cjs',main.namelist())
        with zipfile.ZipFile(self.root/'out/a'/companion['asset']) as archive:
            self.assertEqual(set(archive.namelist()),set(SOURCES)|{'SOURCE.json','SHA256SUMS.txt'})
            for member,source in SOURCES.items():self.assertEqual(archive.read(member),(self.root/source).read_bytes())
            for line in archive.read('SHA256SUMS.txt').decode().splitlines():
                from package_ha_release import digest
                expected,name=line.split('  ',1);self.assertEqual(digest(archive.read(name)),expected)
            self.assertEqual(json.loads(archive.read('SOURCE.json'))['archive_sources'],SOURCES)
        checksum=(self.root/'out/a/HA-SHA256SUMS.txt').read_text()
        self.assertIn('  '+companion['asset']+'\n',checksum)

    def test_private_companion_pins_or_missing_source_deny_the_whole_bundle(self):
        path=self.root/'integrations/zigbee2mqtt/original-tv02.cjs'
        raw=path.read_text()
        row=dict(ieee='0x00158d0000000001',model='TV02-Zigbee',manufacturer='_TZE200_hue3yfsn',endpoint=1)
        path.write_text(raw.replace('[]',json.dumps([row])))
        self.commit();self.refresh_evidence()
        with self.assertRaisesRegex(ValueError,'private_companion_bindings_not_publishable'):
            package(self.root,self.root/'out/a',self.results)
        self.assertFalse((self.root/'out/a').exists())
        path.unlink();self.commit();self.refresh_evidence()
        with self.assertRaisesRegex(ValueError,'invalid_companion_source'):
            package(self.root,self.root/'out/a',self.results)
        self.assertFalse((self.root/'out/a').exists())

    def test_actual_publication_verifier_checks_companion_against_tag_source(self):
        import os,textwrap,hashlib,warnings
        workflow=Path(__file__).resolve().parents[1]/'.github/workflows/build.yml'
        section=workflow.read_text().split('      - name: Verify HA tag, clean source and all download checksums\n',1)[1]
        code=textwrap.dedent(section.split("          python - <<'PYTHON'\n",1)[1].split('\n          PYTHON',1)[0])
        output=self.root/'ha-release-assets';metadata=package(self.root,output,self.results)
        env={**os.environ,'EXPECTED_TAG':metadata['tag'],'EXPECTED_COMMIT':metadata['source_commit'],
             'PYTHONPATH':str(Path(__file__).resolve().parent)}
        def run():return subprocess.run([sys.executable,'-c',code],cwd=self.root,env=env,capture_output=True,text=True)
        result=run();self.assertEqual(result.returncode,0,result.stderr)
        companion=metadata['optional_companions'][0];archive=output/companion['asset'];original=archive.read_bytes()
        def resign():
            companion['sha256']=hashlib.sha256(archive.read_bytes()).hexdigest();companion['size']=archive.stat().st_size
            (output/'ha-release.json').write_text(json.dumps(metadata))
            report=json.loads((output/'ha-software-verification.json').read_text());report['optional_companions']=[companion]
            (output/'ha-software-verification.json').write_text(json.dumps(report))
            (output/'HA-SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(output.iterdir()) if p.name!='HA-SHA256SUMS.txt'))
        # Even a self-consistent newly checksummed bundle cannot change source.
        with zipfile.ZipFile(archive) as source:members={name:source.read(name) for name in source.namelist()}
        members['extensions/original-tv02.cjs']+=b'// unreviewed change\n'
        with zipfile.ZipFile(archive,'w') as changed:
            for name,raw in members.items():changed.writestr(name,raw)
        resign();self.assertNotEqual(run().returncode,0)
        archive.write_bytes(original)
        # Identical duplicate members also fail: unzip implementations may select
        # a different member than zip.read, so set membership alone is insufficient.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(archive,'a') as changed:
                changed.writestr('extensions/original-tv02.cjs',(self.root/'integrations/zigbee2mqtt/original-tv02.cjs').read_bytes())
        resign();self.assertNotEqual(run().returncode,0)

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
