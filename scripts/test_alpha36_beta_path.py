"""Fixtures exercise retained source; these are not release or hardware proofs."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from verify_alpha36_beta_path import verify


class Alpha36BetaPathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.root=Path(__file__).resolve().parents[1]
        self.manifest=dict(update_schema=1,settings_schema=1,board='bbqkees_e32v2',
            layout='e32v2-dual-app-spiffs-v1',ui='embedded',asset='firmware.bin',
            version='v0.1.0-e32v2-beta.1',source_commit='a'*40,web_sha256='b'*64)
        self.image=(f"OT_E32V2_OTA_V1:{self.manifest['version']}:{'a'*40}:{'b'*64}:END".encode()+b'\0'*1024)
        self.manifest.update(size=len(self.image),sha256=hashlib.sha256(self.image).hexdigest())

    def run_fixture(self):
        (self.work/'manifest.json').write_text(json.dumps(self.manifest))
        (self.work/'firmware.bin').write_bytes(self.image)
        return verify(self.root,self.work/'manifest.json',self.work/'firmware.bin')

    def test_retained_fallback_and_all_twelve_positions(self):
        report=self.run_fixture()
        self.assertEqual(report['result'],'PASS')
        self.assertEqual(report['release_positions_tested'],12)
        self.assertFalse(report['physical_update_tested'])
        self.assertFalse(report['network_used'])

    def test_image_hash_size_and_embedded_identity_must_all_agree(self):
        for field,value in [('size',1024),('sha256','f'*64),('source_commit','c'*40),('web_sha256','d'*64)]:
            with self.subTest(field=field):
                saved=self.manifest.copy();self.manifest[field]=value
                with self.assertRaisesRegex(ValueError,'identity_mismatch'):self.run_fixture()
                self.manifest=saved

    def test_wrong_manifest_layout_still_rejected_by_unmodified_predecessor(self):
        import subprocess
        self.manifest['layout']='unreviewed-layout'
        with self.assertRaises(subprocess.CalledProcessError) as caught:self.run_fixture()
        self.assertEqual(caught.exception.returncode,3)

    def test_noncanonical_beta_is_rejected_before_compilation(self):
        for tag in ['v0.1.0-e32v2-alpha.37','v0.1.0-e32v2-beta.01','ha-v0.4.0b1','v1.0.0','v1.0.0-e32v2-stable.1']:
            self.manifest['version']=tag
            with self.assertRaisesRegex(ValueError,'expected_beta'):self.run_fixture()

    def test_release_candidate_and_stable_version_one_are_proved_too(self):
        for tag in ['v0.1.0-e32v2-rc.1','v1.0.0-e32v2']:
            with self.subTest(tag=tag):
                self.manifest['version']=tag
                self.image=(f"OT_E32V2_OTA_V1:{tag}:{'a'*40}:{'b'*64}:END".encode()+b'\0'*1024)
                self.manifest.update(size=len(self.image),sha256=hashlib.sha256(self.image).hexdigest())
                report=self.run_fixture()
                self.assertEqual((report['result'],report['candidate']),('PASS',tag))
