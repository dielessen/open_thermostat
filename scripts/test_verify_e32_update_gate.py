import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from verify_e32_update_gate import REQUIRED, verify

class UpdateGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = dict(schema=1,status='PASS',tag='v0.1.0-e32v2-alpha.36',
            method='native_github',checks=dict.fromkeys(REQUIRED,True),
            catalog_check_commands=1,install_commands=1,install_http_status=202,
            source_commit='a'*40,**dict.fromkeys(('elf_sha256','web_sha256','firmware_sha256',
                'installer_receipt_sha256','independent_receipt_sha256','backup_manifest_sha256'),'b'*64))
        self.policy=dict(schema=1,required_for_successor_release=True,accepted=None,
            pending_tag='v0.1.0-e32v2-alpha.36')
    def accept(self):
        raw=json.dumps(self.record).encode();(self.root/'receipt.json').write_bytes(raw)
        self.policy['accepted']=dict(tag=self.record['tag'],receipt='receipt.json',sha256=hashlib.sha256(raw).hexdigest())
        self.policy['pending_tag']='v0.1.0-e32v2-alpha.37'
    def test_pending_current_is_valid_policy_but_blocks_successor(self):
        self.assertFalse(verify(self.root,self.policy)['successor_ready'])
        with self.assertRaises(ValueError):verify(self.root,self.policy,'v0.1.0-e32v2-alpha.37')
    def test_exact_accepted_predecessor_permits_only_frozen_candidate(self):
        self.accept();verify(self.root,self.policy,'v0.1.0-e32v2-alpha.37')
        with self.assertRaises(ValueError):verify(self.root,self.policy,'v0.1.0-e32v2-alpha.38')
        self.policy['pending_tag']='v0.1.0-e32v2-alpha.35'
        with self.assertRaises(ValueError):verify(self.root,self.policy,'v0.1.0-e32v2-alpha.35')
    def test_beta_successor_is_newer_than_alpha_and_malformed_versions_block(self):
        self.accept();self.policy['pending_tag']='v0.1.0-e32v2-beta.1'
        verify(self.root,self.policy,'v0.1.0-e32v2-beta.1')
        for value in ['v0.1.0-e32v2-alpha.037','v1.0.0','../v0.1.0-e32v2-beta.1']:
            self.policy['pending_tag']=value
            with self.assertRaises(ValueError):verify(self.root,self.policy,value)
    def test_each_missing_or_false_acceptance_check_blocks(self):
        for key in REQUIRED:
            for value in (False,None,1):
                self.record['checks']=dict.fromkeys(REQUIRED,True);self.record['checks'][key]=value
                self.accept()
                with self.assertRaises(ValueError):verify(self.root,self.policy,'v0.1.0-e32v2-alpha.37')
    def test_changed_receipt_and_wrong_route_or_identity_block(self):
        self.accept();(self.root/'receipt.json').write_text('{}')
        with self.assertRaises(ValueError):verify(self.root,self.policy)
        for key,value in [('method','multipart'),('status','UNKNOWN'),('install_commands',2),
                          ('install_commands',True),('catalog_check_commands',2),
                          ('source_commit','unknown'),('independent_receipt_sha256',''),('install_http_status',200)]:
            original=copy.deepcopy(self.record);self.record[key]=value;self.accept()
            with self.assertRaises(ValueError):verify(self.root,self.policy)
            self.record=original
    def test_gate_cannot_be_disabled_or_accept_another_release(self):
        self.accept();self.policy['required_for_successor_release']=False
        with self.assertRaises(ValueError):verify(self.root,self.policy)
        self.policy['required_for_successor_release']=True;self.policy['accepted']['tag']='v0.1.0-e32v2-alpha.35'
        with self.assertRaises(ValueError):verify(self.root,self.policy)

if __name__=='__main__':unittest.main()
