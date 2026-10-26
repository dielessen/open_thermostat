"""Retained accepted updater with host HTTP/flash fixtures; no hardware proof."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from verify_accepted_update_path import accepted_source, verify, verify_report, RETAINED
from verify_e32_update_gate import POLICY, version


class AcceptedUpdatePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.directory = tempfile.TemporaryDirectory()
        cls.work = Path(cls.directory.name)
        accepted,_=accepted_source(cls.root)
        major,minor,patch,stage,sequence=version(accepted['tag'])
        target=(f'v{major}.{minor}.{patch}-e32v2-beta.{sequence+1}' if stage==1
                else f'v{major}.{minor}.{patch+1}-e32v2')
        cls.base = dict(update_schema=1, settings_schema=1, board='bbqkees_e32v2',
                        layout='e32v2-dual-app-spiffs-v1', ui='embedded', asset='firmware.bin',
                        version=target, source_commit='a'*40, web_sha256='b'*64)
        header = bytearray(32); header[0]=0xe9; header[3]=0x40
        cls.image = bytes(header)+(f"OT_E32V2_OTA_V1:{cls.base['version']}:{'a'*40}:{'b'*64}:END".encode())+b'\0'*1024
        cls.base.update(size=len(cls.image), sha256=hashlib.sha256(cls.image).hexdigest())
        (cls.work/'manifest.json').write_text(json.dumps(cls.base))
        (cls.work/'firmware.bin').write_bytes(cls.image)
        cls.report = verify(cls.root, cls.work/'manifest.json', cls.work/'firmware.bin')

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def setUp(self):
        self.manifest = copy.deepcopy(self.base)
        (self.work/'manifest.json').write_text(json.dumps(self.manifest))
        (self.work/'firmware.bin').write_bytes(self.image)

    def run_fixture(self):
        (self.work/'manifest.json').write_text(json.dumps(self.manifest))
        return verify(self.root,self.work/'manifest.json',self.work/'firmware.bin')

    def test_actual_accepted_catalog_and_commit_gate_are_retained_unchanged(self):
        accepted, receipt_sha = accepted_source(self.root)
        self.assertEqual(self.report['accepted_source'], accepted['source_commit'])
        self.assertEqual(self.report['acceptance_receipt_sha256'], receipt_sha)
        self.assertEqual(set(self.report['retained_sources']), set(RETAINED))
        self.assertEqual(self.report['indexed_catalog_cases'],3)
        self.assertEqual(self.report['fallback_positions_tested'],12)
        self.assertEqual(self.report['image_commit_gate_cases'],5)
        self.assertFalse(self.report['physical_update_tested'])
        self.assertFalse(self.report['successor_publication_approved'])
        verify_report(self.root,self.report,self.work/'manifest.json',source_root=self.root)

    def test_image_size_digest_and_marker_must_agree_before_compilation(self):
        for field,value in [('size',1024),('sha256','f'*64),('source_commit','c'*40),('web_sha256','d'*64)]:
            with self.subTest(field=field):
                self.manifest = {**self.base,field:value}
                with self.assertRaisesRegex(ValueError,'identity_mismatch'):
                    self.run_fixture()

    def test_same_or_older_target_cannot_count_as_an_update(self):
        accepted,_=accepted_source(self.root)
        for tag in (accepted['tag'],'v0.1.0-e32v2-alpha.1','ha-v0.4.0b3'):
            self.manifest = {**self.base,'version':tag}
            with self.assertRaisesRegex(ValueError,'newer_than_accepted'):
                self.run_fixture()

    def test_wrong_layout_is_rejected_by_unmodified_accepted_parser(self):
        self.manifest['layout']='unreviewed-layout'
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.run_fixture()
        self.assertEqual(caught.exception.returncode,3)

    def test_no_receipt_cannot_fall_back_to_current_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);policy=root/POLICY;policy.parent.mkdir(parents=True)
            policy.write_text(json.dumps({'schema':1,'required_for_successor_release':True,
                                         'accepted':None,'pending_tag':'v0.1.0-e32v2-beta.3'}))
            with self.assertRaisesRegex(ValueError,'accepted_update_receipt_required'):
                accepted_source(root)

    def test_delivered_report_cannot_change_identity_scope_or_skip_cases(self):
        for field,value in [('accepted_source','f'*40),('source_commit','f'*40),
                            ('acceptance_receipt_sha256','f'*64),('manifest_sha256','f'*64),
                            ('firmware_sha256','f'*64),('image_commit_gate_cases',4),
                            ('fallback_positions_tested',True),('network_used',True),
                            ('physical_update_tested',True),('successor_publication_approved',True)]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'scope_mismatch'):
                verify_report(self.root,{**self.report,field:value},self.work/'manifest.json')

    def test_delivered_retained_hashes_are_checked_against_original_git_source(self):
        report=copy.deepcopy(self.report)
        report['retained_sources'][RETAINED[0]]='f'*64
        with self.assertRaisesRegex(ValueError,'retained_source_mismatch'):
            verify_report(self.root,report,self.work/'manifest.json',source_root=self.root)
        report['retained_sources']={}
        with self.assertRaisesRegex(ValueError,'sources_missing'):
            verify_report(self.root,report,self.work/'manifest.json')


if __name__ == '__main__':
    unittest.main()
