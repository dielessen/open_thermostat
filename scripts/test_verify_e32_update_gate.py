import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from verify_e32_update_gate import HA_REQUIRED, REQUIRED, stable, verify, version

class GateFixture(unittest.TestCase):
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
            pending_tag='v0.1.0-e32v2-alpha.36',candidate_plan='candidate.json',publication_exception=None)
        self.plan('v0.1.0-e32v2-alpha.37','v0.1.0-e32v2-alpha.36')
    def plan(self,candidate,previous):
        (self.root/'candidate.json').write_text(json.dumps(dict(planned_tag=candidate,previous_published_tag=previous)))
    def accept(self):
        raw=json.dumps(self.record).encode();(self.root/'receipt.json').write_bytes(raw)
        self.policy['accepted']=dict(tag=self.record['tag'],receipt='receipt.json',sha256=hashlib.sha256(raw).hexdigest())
        self.policy['pending_tag']='v0.1.0-e32v2-alpha.37'
        self.plan('v0.1.0-e32v2-alpha.37',self.record['tag'])

class UpdateGateTests(GateFixture):
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
        self.plan('v0.1.0-e32v2-beta.1',self.record['tag'])
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

class PublicationExceptionTests(GateFixture):
    def setUp(self):
        super().setUp()
        self.record['tag']='v0.1.0-e32v2-beta.1';self.accept()
        self.target='v0.1.0-e32v2-beta.4';self.previous='v0.1.0-e32v2-beta.3'
        self.policy['pending_tag']=self.target;self.plan(self.target,self.previous)
        gap=json.dumps({'status':'INCOMPLETE'}).encode();(self.root/'gap.json').write_bytes(gap)
        # Synthetic authority exists only in this temporary test repository.
        self.exception=dict(schema=1,status='APPROVED',scope='one_prerelease_publication',
            candidate_tag=self.target,unaccepted_predecessor=self.previous,
            accepted_basis_tag=self.record['tag'],accepted_basis_receipt_sha256=self.policy['accepted']['sha256'],
            predecessor_acceptance_status='INCOMPLETE',gap_report='gap.json',gap_report_sha256=hashlib.sha256(gap).hexdigest(),
            reason='Synthetic fixture: original receipts unavailable',device_installation_authorized=False,
            boiler_trial_authorized=False,approval=dict(actor='repository_owner',method='explicit_user_instruction',
                decision='approve_one_prerelease_publication',statement='Synthetic fixture approval for beta.4 publication only',
                at_utc='2026-10-26T00:00:00Z'))
    def activate(self,record=None):
        raw=json.dumps(self.exception if record is None else record).encode()
        (self.root/'exception.json').write_bytes(raw)
        self.policy['publication_exception']=dict(receipt='exception.json',sha256=hashlib.sha256(raw).hexdigest())
    def test_pending_rewrite_cannot_skip_published_predecessor(self):
        with self.assertRaisesRegex(ValueError,'Previous published release is not accepted'):
            verify(self.root,self.policy,self.target)
    def test_clearing_pending_does_not_claim_successor_readiness(self):
        self.policy['pending_tag']=None
        self.assertFalse(verify(self.root,self.policy)['successor_ready'])
    def test_explicit_exception_preserves_real_acceptance_and_does_not_claim_installation(self):
        self.activate();before=copy.deepcopy(self.policy['accepted']);raw=(self.root/'receipt.json').read_bytes()
        result=verify(self.root,self.policy,self.target)
        self.assertEqual(result['publication_basis'],'operator_approved_one_time_exception')
        self.assertEqual(result['accepted'],'v0.1.0-e32v2-beta.1')
        self.assertFalse(result['physical_test_performed_by_verifier'])
        self.assertEqual(self.policy['accepted'],before);self.assertEqual((self.root/'receipt.json').read_bytes(),raw)
    def test_draft_record_cannot_authorize_publication_even_if_its_hash_matches(self):
        record={**self.exception,'status':'DRAFT_NOT_APPROVED','approval':None};self.activate(record)
        with self.assertRaisesRegex(ValueError,'no explicit approval'):verify(self.root,self.policy,self.target)
    def test_missing_or_changed_exception_digest_blocks(self):
        self.activate();original=copy.deepcopy(self.policy['publication_exception'])
        for value in [None,'','b'*64]:
            self.policy['publication_exception']={**original,'sha256':value}
            with self.subTest(value=value),self.assertRaises(ValueError):verify(self.root,self.policy,self.target)
        self.policy['publication_exception']=original;(self.root/'exception.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'publication exception changed'):verify(self.root,self.policy)
    def test_exception_and_plan_paths_cannot_escape_repository(self):
        self.activate();self.policy['publication_exception']['receipt']='../outside.json'
        with self.assertRaisesRegex(ValueError,'Missing/outside'):verify(self.root,self.policy)
        self.activate();self.policy['candidate_plan']='../outside.json'
        with self.assertRaisesRegex(ValueError,'Missing/outside'):verify(self.root,self.policy,self.target)
    def test_original_evidence_gap_must_remain_bound_and_incomplete(self):
        self.activate();(self.root/'gap.json').write_text('{"status":"INCOMPLETE","changed":true}')
        with self.assertRaisesRegex(ValueError,'evidence-gap report changed'):verify(self.root,self.policy)
        for status in ['PASS','FAIL']:
            raw=json.dumps({'status':status}).encode();(self.root/'gap.json').write_bytes(raw)
            record={**self.exception,'gap_report_sha256':hashlib.sha256(raw).hexdigest()};self.activate(record)
            with self.subTest(status=status),self.assertRaisesRegex(ValueError,'incomplete predecessor evidence'):
                verify(self.root,self.policy)
    def test_scope_cannot_grant_device_or_boiler_commands(self):
        for field,value in [('scope','publish_and_install'),('device_installation_authorized',True),
                            ('device_installation_authorized',0),('boiler_trial_authorized',True),
                            ('predecessor_acceptance_status','PASS'),('schema',True)]:
            self.activate({**self.exception,field:value})
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):verify(self.root,self.policy,self.target)
    def test_actual_operator_statement_and_valid_utc_time_are_required(self):
        for field,value in [('actor','assistant'),('method','inferred_from_continue'),('decision','approve_installation'),
                            ('statement','  '),('statement',True),('at_utc',None),('at_utc','2026-02-30T00:00:00Z')]:
            record={**self.exception,'approval':{**self.exception['approval'],field:value}};self.activate(record)
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):verify(self.root,self.policy,self.target)
        self.activate({**self.exception,'approval':None})
        with self.assertRaises(ValueError):verify(self.root,self.policy)
    def test_other_candidate_predecessor_or_accepted_basis_cannot_reuse_approval(self):
        for field,value in [('candidate_tag','v0.1.0-e32v2-beta.5'),('unaccepted_predecessor','v0.1.0-e32v2-beta.2'),
                            ('accepted_basis_tag','v0.1.0-e32v2-beta.0'),('accepted_basis_receipt_sha256','c'*64)]:
            self.activate({**self.exception,field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):verify(self.root,self.policy,self.target)
    def test_later_release_cannot_replay_the_beta4_approval(self):
        self.activate();target='v0.1.0-e32v2-beta.5';self.policy['pending_tag']=target;self.plan(target,self.target)
        with self.assertRaisesRegex(ValueError,'another candidate/predecessor'):verify(self.root,self.policy,target)
    def test_stable_or_rc_publication_cannot_use_a_beta_exception(self):
        for tag in ['v0.1.0-e32v2','v0.1.0-e32v2-rc.1']:
            self.activate({**self.exception,'candidate_tag':tag})
            with self.subTest(tag=tag),self.assertRaisesRegex(ValueError,'limited to a beta'):verify(self.root,self.policy)
    def test_all_thirteen_checks_of_the_actual_accepted_basis_still_apply(self):
        self.activate()
        for key in REQUIRED:
            record={**self.record,'checks':{**self.record['checks'],key:False}}
            raw=json.dumps(record).encode();(self.root/'receipt.json').write_bytes(raw)
            self.policy['accepted']['sha256']=hashlib.sha256(raw).hexdigest()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Incomplete physical update acceptance'):
                verify(self.root,self.policy,self.target)
    def test_no_real_accepted_basis_cannot_be_waived(self):
        self.activate();self.policy['accepted']=None
        with self.assertRaisesRegex(ValueError,'No physically accepted'):verify(self.root,self.policy,self.target)
    def test_candidate_plan_must_match_even_with_an_approved_exception(self):
        self.activate()
        for plan in [None,{'planned_tag':self.previous,'previous_published_tag':'v0.1.0-e32v2-beta.1'},
                     {'planned_tag':self.target,'previous_published_tag':'v0.1.0-e32v2-beta.5'}]:
            if plan is None:self.policy.pop('candidate_plan',None)
            else:
                self.policy['candidate_plan']='candidate.json';(self.root/'candidate.json').write_text(json.dumps(plan))
            with self.subTest(plan=plan),self.assertRaises(ValueError):verify(self.root,self.policy,self.target)
    def test_normal_acceptance_needs_no_exception(self):
        self.record['tag']=self.previous;self.accept();self.policy['pending_tag']=self.target;self.plan(self.target,self.previous)
        result=verify(self.root,self.policy,self.target)
        self.assertEqual(result['publication_basis'],'accepted_previous_release')
    def test_accepted_candidate_is_ready_for_the_next_planning_cycle(self):
        self.record['tag']=self.target;self.accept();self.policy['pending_tag']=None;self.plan(self.target,self.previous)
        self.assertTrue(verify(self.root,self.policy)['successor_ready'])

def ha_record(tag='v0.1.0-e32v2-beta.19',before='v0.1.0-e32v2-beta.18'):
    """A complete synthetic Home Assistant route receipt (fixture only, no device)."""
    digest='c'*64
    return dict(schema=1,status='PASS',tag=tag,method='home_assistant',checks=dict.fromkeys(HA_REQUIRED,True),
        source_commit='a'*40,elf_sha256='d'*64,web_sha256='e'*64,firmware_sha256=digest,firmware_bytes=2900000,
        installer_receipt_sha256='1'*64,independent_receipt_sha256='2'*64,backup_manifest_sha256='3'*64,
        github_release=dict(tag_name=tag,draft=False,prerelease=not stable(tag),published_at='2026-10-30T08:00:00Z',
            asset=dict(name='firmware.bin',size=2900000,digest='sha256:'+digest)),
        ha_entity_id='update.open_thermostat_firmware',ha_installed_version_before=before,
        ha_latest_version_before=tag,ha_installed_version_after=tag,install_actions=1,
        ha_integration_version='0.4.0b11',ha_core_version='2026.10.4',
        ha_install_record=dict(tag=tag,from_version=before,sha256=digest,size=2900000,uploads=1,result='installed',
            started_at='2026-10-30T09:00:00Z',finished_at='2026-10-30T09:02:10Z',duration_s=130.4,
            reported=dict(version=tag,source_commit='a'*40,web_sha256='e'*64,elf_sha256='d'*64)),
        observations=[dict(at_utc='2026-10-30T09:02:30Z',uptime_seconds=25,boot_pending=False,version=tag),
                      dict(at_utc='2026-10-30T09:15:00Z',uptime_seconds=775,boot_pending=False,version=tag)])

class HomeAssistantRouteTests(GateFixture):
    def setUp(self):
        super().setUp();self.record=ha_record()
        self.candidate='v0.1.0-e32v2-beta.20'
    def accept(self):
        super().accept();self.policy['pending_tag']=self.candidate;self.plan(self.candidate,self.record['tag'])
    def blocked(self,message=None,candidate=None):
        self.accept()
        with self.assertRaisesRegex(ValueError,message or '.'):verify(self.root,self.policy,candidate or self.candidate)
    def test_complete_home_assistant_receipt_is_physical_acceptance(self):
        self.accept();result=verify(self.root,self.policy,self.candidate)
        self.assertEqual(result['accepted'],'v0.1.0-e32v2-beta.19')
        self.assertEqual(result['publication_basis'],'accepted_previous_release')
        self.assertFalse(result['physical_test_performed_by_verifier'])
    def test_native_fields_are_not_required_and_native_receipt_rules_stay(self):
        for key in ('install_http_status','install_commands','catalog_check_commands'):self.assertNotIn(key,self.record)
        self.accept();verify(self.root,self.policy,self.candidate)
        self.record={**self.record,'method':'native_github'}
        self.blocked('Incomplete physical update acceptance')
    def test_each_missing_or_false_home_assistant_check_blocks(self):
        original=copy.deepcopy(self.record)
        for key in HA_REQUIRED:
            for value in (False,None,1):
                self.record=copy.deepcopy(original);self.record['checks'][key]=value
                with self.subTest(key=key,value=value):self.blocked('Incomplete physical update acceptance')
        # The native check list is no substitute (it says nothing about the HA install).
        self.record=copy.deepcopy(original);self.record['checks']=dict.fromkeys(REQUIRED,True)
        self.blocked('Incomplete physical update acceptance')
    def test_digest_size_and_release_identity_must_match_github(self):
        cases=[(('github_release','asset','digest'),'sha256:'+'f'*64,'GitHub digest'),
               (('github_release','asset','digest'),'c'*64,'GitHub digest'),
               (('github_release','asset','size'),2900001,'size differs'),
               (('github_release','asset','size'),999999,'size differs'),
               (('github_release','asset','name'),'e32v2-factory.bin','firmware.bin asset'),
               (('github_release','tag_name'),'v0.1.0-e32v2-beta.18','published one'),
               (('github_release','draft'),True,'published one'),
               (('github_release','prerelease'),False,'channel'),
               (('github_release','published_at'),'2026-10-30 08:00','UTC time'),
               (('firmware_bytes',),'2900000','size differs'),
               (('firmware_sha256',),'C'*64,'identity: firmware_sha256')]
        original=copy.deepcopy(self.record)
        for path,value,message in cases:
            self.record=copy.deepcopy(original);target=self.record
            for key in path[:-1]:target=target[key]
            target[path[-1]]=value
            with self.subTest(path=path,value=value):self.blocked(message)
    def test_update_entity_must_have_offered_and_installed_exactly_this_release_once(self):
        cases=[('ha_installed_version_before','v0.1.0-e32v2-beta.19','not older'),
               ('ha_installed_version_before','v0.1.0-e32v2-beta.20','not older'),
               ('ha_installed_version_before',None,'not older'),
               ('ha_latest_version_before','v0.1.0-e32v2-beta.18','offer'),
               ('ha_installed_version_after','v0.1.0-e32v2-beta.18','new version'),
               ('install_actions',2,'missing/repeated'),('install_actions',True,'missing/repeated'),
               ('install_actions',0,'missing/repeated'),('ha_entity_id','sensor.firmware','update entity'),
               ('ha_integration_version','latest','integration version'),('ha_core_version',None,'Core version'),
               ('installer_receipt_sha256','2'*64,'separate receipt'),('elf_sha256','','identity: elf_sha256'),
               ('source_commit','a'*39,'identity: source_commit'),('backup_manifest_sha256',None,'identity')]
        original=copy.deepcopy(self.record)
        for key,value,message in cases:
            self.record={**copy.deepcopy(original),key:value}
            with self.subTest(key=key,value=value):self.blocked(message)
    def test_install_record_from_home_assistant_must_belong_to_this_install(self):
        cases=[('result','failed','missing/failed'),('result',None,'missing/failed'),
               ('tag','v0.1.0-e32v2-beta.18','another install'),('from_version','v0.1.0-e32v2-beta.17','another install'),
               ('sha256','f'*64,'another install'),('size',2900001,'another install'),('uploads',2,'another install'),
               ('uploads',0,'another install'),('uploads',True,'another install'),
               ('started_at','2026-10-30T07:00:00Z','timing'),('finished_at','2026-10-30T08:59:00Z','timing'),
               ('duration_s',0,'timing'),('duration_s',901,'timing'),('duration_s','130','timing'),
               ('started_at','2026-02-30T09:00:00Z','UTC time')]
        original=copy.deepcopy(self.record)
        for key,value,message in cases:
            self.record=copy.deepcopy(original);self.record['ha_install_record'][key]=value
            with self.subTest(key=key,value=value):self.blocked(message)
        for key,value in [('version','v0.1.0-e32v2-beta.18'),('source_commit','b'*40),('web_sha256','f'*64),('elf_sha256','f'*64)]:
            self.record=copy.deepcopy(original);self.record['ha_install_record']['reported'][key]=value
            with self.subTest(reported=key):self.blocked('E32-reported identity')
        self.record=copy.deepcopy(original);self.record['ha_install_record']=None;self.blocked('missing/failed')
    def test_boot_must_be_confirmed_without_a_restart_and_with_stable_uptime(self):
        original=copy.deepcopy(self.record)
        for index,key,value,message in [(0,'boot_pending',True,'Boot not confirmed'),(1,'boot_pending',None,'Boot not confirmed'),
                                        (1,'version','v0.1.0-e32v2-beta.18','Boot not confirmed'),
                                        (1,'uptime_seconds',20,'restarted'),(1,'uptime_seconds',599,'too short'),
                                        (0,'at_utc','2026-10-30T09:01:00Z','before the install ended')]:
            self.record=copy.deepcopy(original);self.record['observations'][index][key]=value
            with self.subTest(index=index,key=key,value=value):self.blocked(message)
        self.record=copy.deepcopy(original);self.record['observations']=self.record['observations'][1:]
        self.blocked('Missing boot observations')
    def test_unknown_route_or_status_blocks(self):
        for key,value in [('method','home-assistant'),('method',None),('method','esphome'),('status','PENDING'),('schema',2)]:
            self.record={**ha_record(),key:value}
            with self.subTest(key=key,value=value):self.blocked()

class StableVersionTests(GateFixture):
    def test_stable_tag_form_and_order(self):
        order=['v0.1.0-e32v2-alpha.36','v0.1.0-e32v2-beta.18','v0.1.0-e32v2-beta.19','v1.0.0-e32v2-alpha.1',
               'v1.0.0-e32v2-beta.1','v1.0.0-e32v2-rc.1','v1.0.0-e32v2-rc.2','v1.0.0-e32v2','v1.0.1-e32v2-beta.1',
               'v1.0.1-e32v2','v1.1.0-e32v2','v10.0.0-e32v2']
        self.assertEqual(sorted(reversed(order),key=version),order)
        self.assertTrue(stable('v1.0.0-e32v2'));self.assertFalse(stable('v1.0.0-e32v2-rc.1'))
        for bad in ['v1.0.0','v1.0.0-e32v2-','v1.0.0-e32v2-stable','v01.0.0-e32v2','v1.0.0-e32v2-rc.01','ha-v1.0.0','1.0.0-e32v2']:
            self.assertIsNone(version(bad),bad)
    def test_version_one_needs_the_beta_accepted_on_the_home_assistant_route(self):
        self.record=ha_record();self.accept();self.policy['pending_tag']='v1.0.0-e32v2'
        self.plan('v1.0.0-e32v2',self.record['tag'])
        self.assertEqual(verify(self.root,self.policy,'v1.0.0-e32v2')['publication_basis'],'accepted_previous_release')
    def test_version_one_is_not_published_on_a_native_acceptance(self):
        self.record['tag']='v0.1.0-e32v2-beta.19';self.accept();self.policy['pending_tag']='v1.0.0-e32v2'
        self.plan('v1.0.0-e32v2',self.record['tag'])
        with self.assertRaisesRegex(ValueError,'stable release needs an accepted Home Assistant update'):
            verify(self.root,self.policy,'v1.0.0-e32v2')
        # A native acceptance still permits the next pre-release.
        self.policy['pending_tag']='v1.0.0-e32v2-rc.1';self.plan('v1.0.0-e32v2-rc.1',self.record['tag'])
        verify(self.root,self.policy,'v1.0.0-e32v2-rc.1')
    def test_version_one_cannot_skip_an_unaccepted_predecessor(self):
        self.record=ha_record();self.accept();self.policy['pending_tag']='v1.0.0-e32v2'
        self.plan('v1.0.0-e32v2','v0.1.0-e32v2-beta.20')
        with self.assertRaisesRegex(ValueError,'explicit exception required'):verify(self.root,self.policy,'v1.0.0-e32v2')
    def test_stable_accepted_release_orders_after_its_release_candidates(self):
        self.record=ha_record('v1.0.0-e32v2','v1.0.0-e32v2-rc.1');self.accept()
        self.policy['pending_tag']='v1.0.1-e32v2-beta.1';self.plan('v1.0.1-e32v2-beta.1','v1.0.0-e32v2')
        verify(self.root,self.policy,'v1.0.1-e32v2-beta.1')
        for older in ['v1.0.0-e32v2-rc.2','v0.1.0-e32v2-beta.99']:
            self.policy['pending_tag']=older;self.plan(older,'v1.0.0-e32v2')
            with self.subTest(older=older),self.assertRaises(ValueError):verify(self.root,self.policy,older)
    def test_stable_receipt_must_not_be_a_github_prerelease(self):
        self.record=ha_record('v1.0.0-e32v2','v0.1.0-e32v2-beta.19');self.record['github_release']['prerelease']=True
        self.accept()
        with self.assertRaisesRegex(ValueError,'channel'):verify(self.root,self.policy)

if __name__=='__main__':unittest.main()
