"""Synthetic pins only; no live files, JavaScript execution or deployment."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from prepare_original_report_pins import MAX_BYTES,bounded_read,digest,inspect_template,prepare


class OriginalReportPins(unittest.TestCase):
    def fixture(self,profile='original_tv02'):
        old=b"'use strict';\nconst DEVICE_BINDINGS = Object.freeze([]);\n// previous reviewed source\n"
        old+=b'module.exports = class '+(b'OpenThermostatOriginalTv02' if profile=='original_tv02' else b'OpenThermostatOriginalTemperature')+b' {};\n'
        new=old.replace(b'previous',b'candidate')
        pins=[dict(ieee='0x00158d0000000001',model='TV02-Zigbee',manufacturer='_TZE200_hue3yfsn',endpoint=1)]
        if profile=='original_temperature':pins=[dict(ieee='0x00158d0000000001',model='WSDCGQ11LM')]
        installed=old.replace(b'[]',json.dumps(pins).encode())
        return old,installed,new,pins

    def call(self,old,installed,new,profile='original_tv02'):
        return prepare(old,installed,new,profile,expected_previous=digest(old),
            expected_installed=digest(installed),expected_candidate=digest(new))

    def test_exact_private_data_preserved_but_not_returned_in_receipt(self):
        for profile in ('original_temperature','original_tv02'):
            old,installed,new,pins=self.fixture(profile)
            output,report=self.call(old,installed,new,profile)
            self.assertEqual(inspect_template(output,profile)[0],pins)
            self.assertEqual(inspect_template(output,profile)[1],new)
            self.assertFalse(report['installed']);self.assertFalse(report['authorizes_control'])
            self.assertNotIn(pins[0]['ieee'],json.dumps(report))

    def test_real_reviewed_current_templates_are_unconfigured(self):
        root=Path(__file__).resolve().parents[1]
        for profile in ('original_temperature','original_tv02'):
            raw=(root/'integrations/zigbee2mqtt'/ (profile.replace('_','-')+'.cjs')).read_bytes()
            pins,normalized,_=inspect_template(raw,profile)
            self.assertEqual(pins,[]);self.assertEqual(raw,normalized)

    def test_temperature_and_tv02_templates_cannot_be_swapped(self):
        old,installed,new,_=self.fixture('original_tv02')
        with self.assertRaisesRegex(ValueError,'profile_does_not_match_source'):
            self.call(old,installed,new,'original_temperature')

    def test_source_changes_outside_pins_cannot_be_silently_overwritten(self):
        old,installed,new,_=self.fixture()
        with self.assertRaisesRegex(ValueError,'differs_outside'):
            self.call(old,installed+b'// unreviewed change\n',new)

    def test_all_three_exact_input_hashes_are_required(self):
        old,installed,new,_=self.fixture()
        for field in ('expected_previous','expected_installed','expected_candidate'):
            options=dict(expected_previous=digest(old),expected_installed=digest(installed),expected_candidate=digest(new))
            options[field]='0'*64
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):prepare(old,installed,new,'original_tv02',**options)

    def test_duplicate_keys_or_non_data_javascript_and_unknown_fields_are_rejected(self):
        old,_,new,_=self.fixture()
        arrays=[b'[{"ieee":"x","ieee":"x"}]',b'[(()=>{throw 1})()]',
            b'[{"ieee":"0x00158d0000000001","model":"TV02-Zigbee","manufacturer":"_TZE200_hue3yfsn","endpoint":true}]',
            b'[{"ieee":"0x00158d0000000001","model":"TV02-Zigbee","manufacturer":"unknown","endpoint":1}]',
            b'[{"ieee":"0x00158d0000000001","model":"TV02-Zigbee","manufacturer":"_TZE200_hue3yfsn","endpoint":1,"control_qualified":true}]']
        for array in arrays:
            with self.subTest(array=array),self.assertRaises(ValueError):self.call(old,old.replace(b'[]',array),new)

    def test_nonempty_public_templates_and_ambiguous_declarations_are_refused(self):
        old,installed,new,_=self.fixture()
        for previous,candidate in [(installed,new),(old,installed),(old,new+new)]:
            with self.assertRaises(ValueError):self.call(previous,installed,candidate)

    def test_private_input_reads_refuse_symlinks_fifos_and_oversized_files(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'real').write_bytes(b'public fixture')
            (root/'alias').symlink_to(root/'real')
            with self.assertRaises(OSError):bounded_read(root/'alias')
            os.mkfifo(root/'pipe')
            with self.assertRaisesRegex(ValueError,'must_be_regular'):bounded_read(root/'pipe')
            (root/'large').write_bytes(b'x'*(MAX_BYTES+1))
            with self.assertRaisesRegex(ValueError,'too_large'):bounded_read(root/'large')
            self.assertEqual(bounded_read(root/'real'),b'public fixture')

    def test_cli_creates_only_private_new_output_and_refuses_overwrite(self):
        old,installed,new,_=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,raw in [('old',old),('installed',installed),('new',new)]: (root/name).write_bytes(raw)
            command=[sys.executable,str(Path(__file__).with_name('prepare_original_report_pins.py')),
                '--previous-template',str(root/'old'),'--installed-source',str(root/'installed'),
                '--candidate-template',str(root/'new'),'--expected-previous-sha256',digest(old),
                '--expected-installed-sha256',digest(installed),'--expected-candidate-sha256',digest(new),
                '--profile','original_tv02','--output',str(root/'prepared.cjs')]
            result=subprocess.run(command,capture_output=True,text=True,check=True)
            report=json.loads(result.stdout);self.assertEqual(report['preserved_pin_count'],1)
            self.assertEqual((root/'prepared.cjs').stat().st_mode&0o777,0o600)
            before=(root/'prepared.cjs').read_bytes()
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
            self.assertEqual((root/'prepared.cjs').read_bytes(),before)
            self.assertEqual((root/'installed').read_bytes(),installed)
