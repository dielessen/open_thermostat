import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import verify_e32_update_gate as gate
from verify_e32_update_gate import HA_REQUIRED, POLICY, READINESS_CRITERIA, REQUIRED, stable, verify, version

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

class ExceptionFixture(GateFixture):
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

class PublicationExceptionTests(ExceptionFixture):
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
    def test_stable_publication_cannot_use_an_exception(self):
        for tag in ['v0.1.0-e32v2','v1.0.0-e32v2']:
            self.activate({**self.exception,'candidate_tag':tag})
            with self.subTest(tag=tag),self.assertRaisesRegex(ValueError,'limited to a beta or rc'):verify(self.root,self.policy)
    def test_release_candidate_may_skip_one_unaccepted_candidate(self):
        # rc.2 over a published, never installed rc.1, on the accepted beta basis.
        target,previous='v1.0.0-e32v2-rc.2','v1.0.0-e32v2-rc.1'
        self.policy['pending_tag']=target;self.plan(target,previous)
        self.activate({**self.exception,'candidate_tag':target,'unaccepted_predecessor':previous})
        self.assertEqual(verify(self.root,self.policy,target)['publication_basis'],'operator_approved_one_time_exception')
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
    def shifted(self,**changes):
        """Both observations moved: (at_utc, uptime_seconds) per observation."""
        self.record=ha_record()
        for index,(at,uptime) in changes.items():
            self.record['observations'][int(index)].update(at_utc=at,uptime_seconds=uptime)
    def test_observations_must_come_from_one_boot_the_install_produced(self):
        """R5-08: rising uptimes alone do not tie the reads to the install (the boot instant is the time minus uptime)."""
        # A restart between the reads that still leaves a rising uptime: 09:02:05 and then 09:07:05.
        self.shifted(**{'1':('2026-10-30T09:20:00Z',775)});self.blocked('different boots')
        # Reads of a later boot: consistent with each other, but not the boot of the install.
        self.shifted(**{'0':('2026-10-30T11:02:30Z',25),'1':('2026-10-30T11:15:00Z',775)});self.blocked('not of the boot the install produced')
        # A boot long before the install started (the E32 did not restart for the install).
        self.shifted(**{'0':('2026-10-30T09:12:00Z',1200),'1':('2026-10-30T09:20:00Z',1680)});self.blocked('not of the boot the install produced')
    def test_late_reads_of_the_boot_the_install_produced_are_fine(self):
        """Two days after the install, without a restart since: the boot instant is still the install's."""
        self.shifted(**{'0':('2026-11-01T09:02:30Z',172800+25),'1':('2026-11-01T09:15:00Z',172800+775)})
        self.accept();verify(self.root,self.policy,self.candidate)
    def test_boot_instants_may_differ_by_the_jitter_of_the_reads_only(self):
        limit=gate.BOOT_JITTER_S
        self.shifted(**{'1':('2026-10-30T09:15:00Z',775-limit)});self.accept();verify(self.root,self.policy,self.candidate)
        self.shifted(**{'1':('2026-10-30T09:15:00Z',775-limit-1)});self.blocked('different boots')
    def test_the_real_accepted_receipts_satisfy_the_boot_rule(self):
        root=Path(__file__).resolve().parents[1];checked=0
        for path in sorted((root/'docs/modern-thermostat/update-acceptance').glob('e32-*.json')):
            record=json.loads(path.read_text())
            if record.get('method')=='home_assistant' and record.get('status')=='PASS' and record.get('evidence')!='ha_history':
                gate.home_assistant_acceptance(record);checked+=1
        self.assertGreaterEqual(checked,1)

def releases(*tags,drafts=()):
    return [{'tag_name':tag,'draft':tag in drafts,'prerelease':True} for tag in tags]

class PublishedReleaseTests(ExceptionFixture):
    """R5-07: the plan's previous_published_tag is checked against the releases that really exist."""
    LINEUP=('v0.1.0-e32v2-beta.1','v0.1.0-e32v2-beta.3','v0.1.0-e32v2-beta.4')
    def test_lying_plan_is_found_out(self):
        """The plan says the previous release is beta.1 although beta.3 was published after it and never accepted."""
        self.activate();self.plan(self.target,'v0.1.0-e32v2-beta.1');self.record['tag']='v0.1.0-e32v2-beta.1'
        published=releases('v0.1.0-e32v2-beta.1',self.previous)
        with self.assertRaisesRegex(ValueError,'latest published release below'):verify(self.root,self.policy,self.target,published)
        self.assertEqual(verify(self.root,self.policy,self.target)['previous_published_checked'],False)   # not compared: no list
    def test_honest_plan_passes_and_says_it_was_checked(self):
        self.activate()
        result=verify(self.root,self.policy,self.target,releases('v0.1.0-e32v2-beta.1',self.previous))
        self.assertTrue(result['previous_published_checked'])
        self.assertEqual(result['publication_basis'],'operator_approved_one_time_exception')
    def test_a_previous_release_that_was_never_published_is_refused(self):
        self.activate()
        with self.assertRaisesRegex(ValueError,'latest published release below'):
            verify(self.root,self.policy,self.target,releases('v0.1.0-e32v2-beta.1'))
    def test_drafts_and_other_channels_do_not_count_as_published(self):
        self.activate()
        with self.assertRaisesRegex(ValueError,'latest published release below'):
            verify(self.root,self.policy,self.target,releases('v0.1.0-e32v2-beta.1',self.previous,drafts=(self.previous,)))
        rows=releases('v0.1.0-e32v2-beta.1',self.previous)+[{'tag_name':'ha-v0.4.0b15','draft':False},{'tag_name':'sources-e32v2-20261030.1','draft':False}]
        verify(self.root,self.policy,self.target,rows)
    def test_the_candidate_itself_and_later_releases_are_not_its_predecessor(self):
        self.activate()
        verify(self.root,self.policy,self.target,releases('v0.1.0-e32v2-beta.1',self.previous,self.target,'v0.1.0-e32v2-beta.5'))
        with self.assertRaisesRegex(ValueError,'No published firmware release below'):
            verify(self.root,self.policy,self.target,releases(self.target))
    def test_a_plain_list_of_tags_is_a_catalog_too(self):
        self.activate();verify(self.root,self.policy,self.target,['v0.1.0-e32v2-beta.1',self.previous])
    def test_fetch_reads_all_pages_with_a_token_and_fails_on_any_error(self):
        seen=[]
        def page(rows):
            class Response(io.BytesIO):
                def __enter__(self):return self
                def __exit__(self,*exc):return False
            return Response(json.dumps(rows).encode())
        def urlopen(request,timeout=None):
            seen.append((request.full_url,request.get_header('Authorization')))
            return page([{'tag_name':f'v0.1.0-e32v2-beta.{n}','draft':False} for n in range(100)] if len(seen)==1 else releases('v0.1.0-e32v2-beta.100'))
        rows=gate.fetch_published('o/p','TOKEN',urlopen=urlopen)
        self.assertEqual(len(rows),101);self.assertEqual([url[-6:] for url,_ in seen],['page=1','page=2'])
        self.assertTrue(all(auth=='Bearer TOKEN' for _,auth in seen))
        def broken(request,timeout=None):raise urllib.error.URLError('offline')
        with self.assertRaises(urllib.error.URLError):gate.fetch_published('o/p',urlopen=broken)
        def endless(request,timeout=None):return page([{'tag_name':'v0.1.0-e32v2-beta.1','draft':False}]*100)
        with self.assertRaisesRegex(ValueError,'More release pages'):gate.fetch_published('o/p',urlopen=endless,max_pages=3)
        def object_answer(request,timeout=None):return page({'message':'API rate limit exceeded'})
        with self.assertRaisesRegex(ValueError,'Unexpected answer'):gate.fetch_published('o/p',urlopen=object_answer)

class CommandLineTests(unittest.TestCase):
    """The candidate check of the real policy: it fails closed when the published releases cannot be read."""
    ROOT=Path(__file__).resolve().parents[1]
    def setUp(self):
        policy=json.loads((self.ROOT/POLICY).read_text())
        if not policy.get('pending_tag') or not policy.get('candidate_plan'):self.skipTest('no candidate pending in the policy')
        self.candidate=policy['pending_tag'];self.previous=json.loads((self.ROOT/policy['candidate_plan']).read_text())['previous_published_tag']
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
    def run_main(self,*argv,fetch=None):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=gate.main(list(argv),**({'fetch':fetch} if fetch else {}))
        return code,out.getvalue(),err.getvalue()
    def test_unreadable_release_list_fails_closed(self):
        def offline(repository,token=None):raise urllib.error.URLError('no network')
        code,out,err=self.run_main('--candidate',self.candidate,fetch=offline)
        self.assertEqual(code,1);self.assertEqual(out,'');self.assertIn('--offline only when you mean to skip',err)
        bad=Path(self.temp.name)/'catalog.json';bad.write_text('{not json')
        self.assertEqual(self.run_main('--candidate',self.candidate,'--published-file',str(bad))[0],1)
        self.assertEqual(self.run_main('--candidate',self.candidate,'--published-file',str(Path(self.temp.name)/'missing.json'))[0],1)
    def test_explicit_offline_skips_and_says_so(self):
        code,out,err=self.run_main('--candidate',self.candidate,'--offline')
        self.assertEqual(code,0);self.assertFalse(json.loads(out)['previous_published_checked']);self.assertIn('WARNING --offline',err)
    def test_catalog_file_and_api_are_compared(self):
        catalog=Path(self.temp.name)/'catalog.json';catalog.write_text(json.dumps(releases(self.previous)))
        code,out,_=self.run_main('--candidate',self.candidate,'--published-file',str(catalog))
        self.assertEqual(code,0);self.assertTrue(json.loads(out)['previous_published_checked'])
        code,out,_=self.run_main('--candidate',self.candidate,fetch=lambda repository,token=None:releases(self.previous))
        self.assertEqual(code,0);self.assertTrue(json.loads(out)['previous_published_checked'])
        catalog.write_text(json.dumps(releases('v0.1.0-e32v2-beta.1')))
        with self.assertRaisesRegex(ValueError,'latest published release below'):
            self.run_main('--candidate',self.candidate,'--published-file',str(catalog))
    def test_no_candidate_needs_no_release_list(self):
        code,out,_=self.run_main()
        self.assertEqual(code,0);self.assertNotIn('previous_published_checked',json.loads(out))
        with self.assertRaises(SystemExit):self.run_main('--offline')

class StableVersionTests(GateFixture):
    def test_stable_tag_form_and_order(self):
        order=['v0.1.0-e32v2-alpha.36','v0.1.0-e32v2-beta.18','v0.1.0-e32v2-beta.19','v1.0.0-e32v2-alpha.1',
               'v1.0.0-e32v2-beta.1','v1.0.0-e32v2-rc.1','v1.0.0-e32v2-rc.2','v1.0.0-e32v2','v1.0.1-e32v2-beta.1',
               'v1.0.1-e32v2','v1.1.0-e32v2','v10.0.0-e32v2']
        self.assertEqual(sorted(reversed(order),key=version),order)
        self.assertTrue(stable('v1.0.0-e32v2'));self.assertFalse(stable('v1.0.0-e32v2-rc.1'))
        for bad in ['v1.0.0','v1.0.0-e32v2-','v1.0.0-e32v2-stable','v01.0.0-e32v2','v1.0.0-e32v2-rc.01','ha-v1.0.0','1.0.0-e32v2']:
            self.assertIsNone(version(bad),bad)
    def readiness(self,measured,**changes):
        doc=dict(schema=1,kind='release_readiness',release=measured,stage='final',overall='PASS',
                 **{'from':'2026-11-10T12:00:00Z','to':'2026-11-24T12:00:00Z'},installed_versions=[measured],
                 criteria={c:{'result':'PASS'} for c in READINESS_CRITERIA})
        doc.update(changes);raw=json.dumps(doc).encode();(self.root/'readiness.json').write_bytes(raw)
        self.policy['readiness_report']=dict(report='readiness.json',sha256=hashlib.sha256(raw).hexdigest())
    def test_version_one_needs_the_beta_accepted_on_the_home_assistant_route(self):
        self.record=ha_record();self.accept();self.policy['pending_tag']='v1.0.0-e32v2'
        self.plan('v1.0.0-e32v2',self.record['tag']);self.readiness(self.record['tag'])
        self.assertEqual(verify(self.root,self.policy,'v1.0.0-e32v2')['publication_basis'],'accepted_previous_release')
    def test_version_one_needs_a_final_pass_readiness_report_over_14_days(self):
        self.record=ha_record();self.accept();self.policy['pending_tag']='v1.0.0-e32v2'
        self.plan('v1.0.0-e32v2',self.record['tag'])
        with self.assertRaisesRegex(ValueError,'needs a PASS readiness report'):verify(self.root,self.policy,'v1.0.0-e32v2')
        bad={'stage':('candidate','not final'),'overall':('WAIT','not PASS'),'release':('v0.1.0-e32v2-beta.21','another release'),
             'to':('2026-11-20T12:00:00Z','shorter than 14 days'),'kind':('shadow_exit','Invalid readiness report')}
        for key,(value,message) in bad.items():
            with self.subTest(key=key):
                self.readiness(self.record['tag'],**{key:value})
                with self.assertRaisesRegex(ValueError,message):verify(self.root,self.policy,'v1.0.0-e32v2')
        for criterion in READINESS_CRITERIA:
            with self.subTest(criterion=criterion):
                self.readiness(self.record['tag'],criteria={c:{'result':'WAIT' if c==criterion else 'PASS'} for c in READINESS_CRITERIA})
                with self.assertRaisesRegex(ValueError,'not PASS on every criterion'):verify(self.root,self.policy,'v1.0.0-e32v2')
        self.readiness(self.record['tag']);self.policy['readiness_report']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'changed'):verify(self.root,self.policy,'v1.0.0-e32v2')
    def test_the_window_is_tied_to_the_measured_release(self):
        """R5-09: a 14-day window that includes days on another release, or an install, is not about this release."""
        self.record=ha_record();self.accept();self.policy['pending_tag']='v1.0.0-e32v2'
        self.plan('v1.0.0-e32v2',self.record['tag'])
        tag=self.record['tag']
        for changes,message in [(dict(installed_versions=['v0.1.0-e32v2-beta.18',tag]),'not the measured release only'),
                                (dict(installed_versions=[tag,'v0.1.0-e32v2-beta.20']),'not the measured release only'),
                                (dict(installed_versions=['v0.1.0-e32v2-beta.18']),'not the measured release only'),
                                (dict(installed_versions=[]),'not the measured release only'),
                                (dict(installed_versions=None),'not the measured release only'),
                                (dict(**{'from':'2026-10-30T09:01:00Z','to':'2026-11-13T09:01:00Z'}),'before the accepted install ended')]:
            with self.subTest(changes=changes):
                doc=dict(changes)
                if 'installed_versions' not in doc and 'from' not in doc:doc['installed_versions']=[tag]
                self.readiness(tag,**doc)
                with self.assertRaisesRegex(ValueError,message):verify(self.root,self.policy,'v1.0.0-e32v2')
        # A window that starts exactly when the install ended is fine; the window criteria must all be PASS.
        self.readiness(tag,**{'from':'2026-10-30T09:02:10Z','to':'2026-11-13T09:02:10Z'})
        self.assertEqual(verify(self.root,self.policy,'v1.0.0-e32v2')['publication_basis'],'accepted_previous_release')
        self.readiness(tag,criteria={c:{'result':'WAIT' if c=='release_window' else 'PASS'} for c in READINESS_CRITERIA})
        with self.assertRaisesRegex(ValueError,'not PASS on every criterion'):verify(self.root,self.policy,'v1.0.0-e32v2')
    def test_a_release_candidate_needs_no_readiness_report(self):
        self.record=ha_record();self.accept();self.policy['pending_tag']='v1.0.0-e32v2-rc.1'
        self.plan('v1.0.0-e32v2-rc.1',self.record['tag'])
        self.assertEqual(verify(self.root,self.policy,'v1.0.0-e32v2-rc.1')['publication_basis'],'accepted_previous_release')
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

def history_exports(tag='v1.0.0-e32v2-rc.5',before='v1.0.0-e32v2-rc.4',installs=1):
    """Synthetic Home Assistant recorder exports of an install through the update entity (fixture only, no device):
    the Firmware entity (offer, install record, new version), the integration's update entity and the uptime sensor."""
    entity,uptime,integration='update.e32_firmware','sensor.e32_device_uptime','update.openthermostat_update'
    def record(release,start,end):
        return dict(tag=release,from_version=before,sha256='c'*64,size=2900000,started_at=start,finished_at=end,
            duration_s=80.7,result='installed',uploads=1,
            reported=dict(version=release,source_commit='a'*40,web_sha256='e'*64,elf_sha256='d'*64))
    def row(at,installed,latest,last=None):
        attributes=dict(installed_version=installed,latest_version=latest,release_url=None)
        if last:attributes['last_install']=last
        return dict(entity_id=entity,state='on' if installed!=latest else 'off',attributes=attributes,last_changed=at)
    rows=[row('2026-11-05T04:00:00+00:00',before,before),row('2026-11-05T05:32:00.336794+00:00',before,tag)]
    if installs==2:
        rows.append(row('2026-11-05T05:40:00+00:00',before,tag,record(tag,'2026-11-05T05:38:00Z','2026-11-05T05:39:00Z')))
    rows.append(row('2026-11-05T05:55:12.409432+00:00',tag,tag,record(tag,'2026-11-05T05:53:51Z','2026-11-05T05:55:12Z')))
    hacs=[dict(entity_id=integration,state='off',last_changed='2026-11-05T05:51:28.526907+00:00',
               attributes=dict(installed_version='1.0.0rc6',latest_version='1.0.0rc6',
                               release_url='https://github.com/owner/openthermostat-ha/releases/1.0.0rc6'))]
    up=[dict(entity_id=uptime,state='16.2',attributes=dict(unit_of_measurement='h'),last_changed='2026-11-05T05:50:00+00:00'),
        dict(state='unavailable',last_changed='2026-11-05T05:55:10.303901+00:00')]
    up+=[dict(state=repr(seconds/3600),last_changed=at) for at,seconds in
         (('2026-11-05T05:55:10.424794+00:00',7),('2026-11-05T05:56:10.419826+00:00',67),
          ('2026-11-05T06:06:10.480484+00:00',667),('2026-11-05T08:59:14.068584+00:00',11050))]
    return [[rows,hacs],[up]]

DECLARED_CRITERIA=('stability','active_control','trv_control','failure_tests','install_guide','release_window')
WORDS=['rc5 is 1.0 wat mij betreft','Synthetic fixture: the second message of the owner']

class OwnerDeclarationTests(GateFixture):
    """The owner declares a stable release; the gate records it (synthetic files in a temporary repository)."""
    TAG,STABLE='v1.0.0-e32v2-rc.5','v1.0.0-e32v2'
    def setUp(self):
        super().setUp()
        self.exports=history_exports()
        self.statements=[dict(at_utc='2026-11-06T22:20:00Z',text=WORDS[0]),dict(at_utc='2026-11-06T22:35:00Z',text=WORDS[1])]
        self.criteria={name:'declared: '+name for name in DECLARED_CRITERIA}
        self.build()
    def write(self,name,value):
        raw=(json.dumps(value,indent=1)+'\n').encode();(self.root/name).write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()
    def build(self,receipt_changes=None,report_changes=None,declaration_changes=None,seal=True):
        files=[]
        for index,export in enumerate(self.exports):
            files.append(dict(path=f'history-{index}.json',sha256=self.write(f'history-{index}.json',export),kind='ha_history'))
        facts=gate.ha_history_facts(gate.ha_history_series(self.exports),'update.e32_firmware',self.TAG,
                                    'sensor.e32_device_uptime','update.openthermostat_update')
        checks={name:(True if name in gate.HA_HISTORY_MEASURED else 'declared') for name in HA_REQUIRED}
        declared=sorted(name for name,value in checks.items() if value=='declared')
        self.receipt=dict(schema=1,status='PASS',tag=self.TAG,method='home_assistant',evidence='ha_history',
            acceptance_decision='ACCEPTED_ON_OWNER_DECLARATION',checks=checks,declared_checks=declared,
            owner_declaration=dict(declaration='declaration.json',statements=[s['text'] for s in self.statements]),
            evidence_files=files,github_release=None,uptime_entity_id='sensor.e32_device_uptime',
            ha_integration_entity_id='update.openthermostat_update',ha_core_version=None,**facts)
        self.receipt.update(receipt_changes or {})
        receipt_sha=self.write('receipt.json',self.receipt)
        criteria={name:({'result':'DECLARED','declared':self.criteria[name],'measured':{'result':'WAIT'}}
                        if name in self.criteria else {'result':'PASS'}) for name in READINESS_CRITERIA}
        self.report=dict(schema=1,kind='release_readiness',release=self.TAG,stage='final',overall='PASS_DECLARED',
            **{'from':'2026-11-05T05:55:13Z','to':'2026-11-05T09:00:00Z'},installed_versions=[self.TAG],criteria=criteria,
            declaration=dict(file='declaration.json',statements=[s['text'] for s in self.statements],
                             declared_criteria=sorted(self.criteria)))
        self.report.update(report_changes or {})
        report_sha=self.write('readiness.json',self.report)
        self.declaration=dict(schema=1,kind='owner_declared_stable',tag=self.STABLE,follows=self.TAG,
            owner=dict(actor='repository_owner',method='explicit_user_instruction',statements=self.statements),
            declared_criteria=self.criteria,declared_receipt_checks={name:'why '+name for name in declared},
            receipt=dict(path='receipt.json',sha256=receipt_sha),readiness_report=dict(path='readiness.json',sha256=report_sha),
            evidence=[dict(path=f['path'],sha256=f['sha256']) for f in files])
        self.declaration.update(declaration_changes or {})
        declaration_sha=self.write('declaration.json',self.declaration)
        self.policy.update(accepted=dict(tag=self.TAG,receipt='receipt.json',sha256=receipt_sha),pending_tag=self.STABLE,
            readiness_report=dict(report='readiness.json',sha256=report_sha))
        if seal:self.policy['stable_declaration']=dict(declaration='declaration.json',sha256=declaration_sha)
        else:self.policy.pop('stable_declaration',None)
        self.plan(self.STABLE,self.TAG)
    def refused(self,message,candidate=None):
        with self.assertRaisesRegex(ValueError,message):verify(self.root,self.policy,candidate or self.STABLE)
    def test_the_declaration_is_recorded_and_visible_in_the_result(self):
        result=verify(self.root,self.policy,self.STABLE,[{'tag_name':self.TAG,'draft':False}])
        self.assertEqual(result['publication_basis'],'owner_declared_stable')
        owner=result['owner_declaration']
        self.assertEqual(owner['statements'],WORDS)
        self.assertEqual(owner['declared_criteria'],sorted(DECLARED_CRITERIA))
        self.assertEqual(owner['declared_receipt_checks'],sorted(gate.DECLARABLE_CHECKS))
        self.assertEqual((owner['tag'],owner['follows'],owner['declaration']),(self.STABLE,self.TAG,'declaration.json'))
        self.assertLess(owner['readiness_window_days'],1)
        self.assertEqual(result['accepted_evidence'],'ha_history')
        self.assertFalse(result['physical_test_performed_by_verifier'])
        # Without a candidate the policy verifies too, and still says that the accepted receipt rests on the declaration.
        plain=verify(self.root,self.policy)
        self.assertEqual(plain['accepted_declared_checks'],sorted(gate.DECLARABLE_CHECKS))
        self.assertEqual(plain['stable_declaration'],{'declaration':'declaration.json','tag':self.STABLE})
    def test_a_placeholder_or_empty_statement_is_refused(self):
        for text in (gate.DECLARATION_PLACEHOLDER,'','   ',None,'ja '+gate.DECLARATION_PLACEHOLDER):
            with self.subTest(text=text):
                self.statements=[dict(at_utc='2026-11-06T22:20:00Z',text=text)];self.build()
                with self.assertRaisesRegex(ValueError,'placeholder'):verify(self.root,self.policy)
        self.statements=[];self.build();self.refused('no owner statement')
        self.statements=[dict(at_utc='6 Nov 23:20',text=WORDS[0])];self.build();self.refused('UTC time')
    def test_the_owner_is_the_author(self):
        for owner in (dict(actor='assistant',method='explicit_user_instruction',statements=[]),
                      dict(actor='repository_owner',method='inferred',statements=[]),None):
            with self.subTest(owner=owner):self.build(declaration_changes=dict(owner=owner));self.refused("not the owner's")
    def test_one_declaration_per_stable_tag(self):
        self.build(declaration_changes=dict(tag='v1.0.1-e32v2'));self.refused('belongs to another release')
        # A later stable release with the same declaration still in the policy gets no help from it.
        self.build();self.policy['pending_tag']='v1.0.1-e32v2';self.plan('v1.0.1-e32v2',self.TAG)
        self.refused('belongs to another release','v1.0.1-e32v2')
    def test_the_receipt_is_still_required_and_bound(self):
        self.build(seal=False);self.refused("only on the owner's stable declaration")
        self.build();self.policy['accepted']=None;self.refused('No physically accepted')
        self.build(declaration_changes=dict(receipt=dict(path='receipt.json',sha256='0'*64)));self.refused('declared receipt changed')
        self.build();self.policy['stable_declaration']['sha256']='0'*64;self.refused('stable declaration changed')
        self.build(receipt_changes=dict(status='INCOMPLETE'));self.refused('Update not accepted')
        self.build(receipt_changes=dict(acceptance_decision='ACCEPTED'));self.refused('Update not accepted')
        self.build(declaration_changes=dict(follows='v1.0.0-e32v2-rc.4'));self.refused('follows another release')
    def test_the_install_itself_is_measured_never_declared(self):
        for name in gate.HA_HISTORY_MEASURED:
            with self.subTest(name=name):
                checks={**dict.fromkeys(HA_REQUIRED,'declared'),**dict.fromkeys(gate.HA_HISTORY_MEASURED,True),name:'declared'}
                self.build(receipt_changes=dict(checks=checks,declared_checks=sorted(k for k,v in checks.items() if v=='declared')))
                self.refused('Incomplete physical update acceptance')
        checks={**dict.fromkeys(HA_REQUIRED,True),'backup_verified':False}
        self.build(receipt_changes=dict(checks=checks,declared_checks=[]));self.refused('Incomplete physical update acceptance')
    def test_declared_checks_must_be_the_ones_the_owner_declared(self):
        self.build(declaration_changes=dict(declared_receipt_checks={'backup_verified':'why'}))
        self.refused("declared checks differ")
        self.build(declaration_changes=dict(declared_receipt_checks={'new_boot_observed':'why'}))
        self.refused('checks the history cannot show')
    def test_the_receipt_is_re_derived_from_the_history(self):
        for key,value in [('install_actions',2),('ha_installed_version_before','v1.0.0-e32v2-rc.3'),
                          ('firmware_sha256','f'*64),('ha_integration_version','1.0.0rc7'),('source_commit','b'*40),
                          ('observations',[dict(at_utc='2026-11-05T06:06:10Z',version=self.TAG,uptime_seconds=667,
                                                source='sensor.e32_device_uptime')])]:
            with self.subTest(key=key):self.build(receipt_changes={key:value});self.refused('differs from the Home Assistant history')
    def test_what_the_history_shows_must_hold(self):
        self.exports=history_exports(installs=2);self.build();self.refused('missing/repeated')
        exports=history_exports();exports[1][0]=exports[1][0][:5]  # 67 s and 667 s after the install: enough
        self.exports=exports;self.build();verify(self.root,self.policy,self.STABLE)
        exports=history_exports();exports[1][0]=exports[1][0][:4]  # only 67 s of uptime after the install ended
        self.exports=exports;self.build();self.refused('Missing boot observations')
        exports=history_exports();exports[1][0].insert(5,dict(state=repr(30/3600),last_changed='2026-11-05T06:00:00+00:00'))
        self.exports=exports;self.build()  # a restart after the install ends the boot there: 67 s only
        self.refused('Missing boot observations')
        exports=history_exports();exports[1][0][0]['attributes']['unit_of_measurement']='weeks'
        self.exports=exports
        with self.assertRaisesRegex(ValueError,'Unknown unit'):self.build()
    def test_evidence_files_are_bound(self):
        self.build();(self.root/'history-1.json').write_text('[]');self.refused('declared evidence history-1.json changed')
        self.build(declaration_changes=dict(evidence=[]));self.refused('not covered')
    def test_criteria_are_declared_never_over_a_fail_and_updates_is_measured(self):
        criteria=dict(self.report['criteria']);criteria['stability']=dict(criteria['stability'],measured={'result':'FAIL'})
        self.build(report_changes=dict(criteria=criteria));self.refused('over a measured FAIL')
        self.criteria={**self.criteria,'updates':'declared'};self.build();self.refused('updates is always measured')
    def test_the_report_and_the_declaration_name_the_same_criteria(self):
        self.criteria={k:v for k,v in self.criteria.items() if k!='install_guide'};self.build()
        criteria=dict(self.report['criteria']);criteria['install_guide']={'result':'DECLARED','declared':'x','measured':{'result':'WAIT'}}
        self.build(report_changes=dict(criteria=criteria,declaration=dict(self.report['declaration'])))
        self.refused('not PASS on every criterion')
        self.criteria={name:'declared: '+name for name in DECLARED_CRITERIA}
        self.build(report_changes=dict(overall='PASS'));self.refused('not PASS on every criterion')
        self.build(report_changes=dict(declaration=dict(self.report['declaration'],statements=['something else'])))
        self.refused("does not quote the owner's declaration")
    def test_a_short_window_needs_release_window_declared(self):
        self.criteria={k:v for k,v in self.criteria.items() if k!='release_window'};self.build()
        criteria=dict(self.report['criteria']);criteria['release_window']={'result':'PASS'}
        self.build(report_changes=dict(criteria=criteria));self.refused('shorter than 14 days')
    def test_a_declared_report_needs_its_declaration(self):
        self.build(report_changes=dict(declaration=None));self.refused('not PASS on every criterion')
    def test_the_normal_rule_is_unchanged_without_a_declaration(self):
        self.record=ha_record(self.TAG,'v1.0.0-e32v2-rc.4');GateFixture.accept(self)
        self.policy.pop('stable_declaration',None);self.policy['pending_tag']=self.STABLE;self.plan(self.STABLE,self.TAG)
        doc=dict(schema=1,kind='release_readiness',release=self.TAG,stage='final',overall='PASS',
                 **{'from':'2026-10-30T09:02:10Z','to':'2026-11-13T09:02:10Z'},installed_versions=[self.TAG],
                 criteria={c:{'result':'PASS'} for c in READINESS_CRITERIA})
        self.policy['readiness_report']=dict(report='normal.json',sha256=self.write('normal.json',doc))
        self.assertEqual(verify(self.root,self.policy,self.STABLE)['publication_basis'],'accepted_previous_release')

if __name__=='__main__':unittest.main()
