"""Finite offline identity joins. Fixture hashes are NOT source/build proof."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,tempfile,unittest
from release_notices import NoticeError
import release_shipped as r

def sha(data):return hashlib.sha256(data).hexdigest()

class SDKLinks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"source";self.root.mkdir()
        self.core=Path(self.tmp.name)/"core";self.fw=self.core/"packages/framework-arduinoespressif32"
        self.ledger=dict(schema=1,scope="finite fixture, not corresponding source",receipt_source="same-source",
            inventory=dict(inventory_sha256="a"*64,file_sha256="b"*64,framework_tree_sha256="c"*64),
            package_metadata={},boards={})
        self.policy=dict(receipt_source="same-source",artifacts={},cached_sdk_component_evidence=[
            dict(linked_archive="libfreertos.a",scope="header only",component="FreeRTOS")])
        pins={}
        for name in ("package.json",".piopm"):
            data=b"finite package metadata";self.write(self.fw/name,data)
            self.ledger["package_metadata"][name]=dict(sha256=sha(data),bytes=len(data))
            pins[name]=sha(data)
        self.write(self.root/"docs/third-party/provenance.json",json.dumps(dict(framework=dict(pins=pins))).encode())
        self.boards=[]
        for env,target in (("e32v2","esp32"),("esp32s3","esp32s3")):
            cfg="tools/sdk/"+target+"/sdkconfig";cfgdata=b"CONFIG_FIXTURE=y";self.write(self.fw/cfg,cfgdata)
            path="packages/framework-arduinoespressif32/tools/sdk/"+target+"/lib/libfreertos.a"
            relative=path.removeprefix("packages/framework-arduinoespressif32/")
            data=b"finite archive fixture:"+target.encode();self.write(self.fw/relative,data)
            identity=dict(path=path,bytes=len(data),sha256=sha(data))
            self.ledger["boards"][env]=dict(sdk_target=target,descriptor_idf="dirty-fixture",
                map_sha256="d"*64,elf_sha256="e"*64,
                cached_sdkconfig=dict(path=cfg,sha256=sha(cfgdata),bytes=len(cfgdata)),archives=[identity])
            for suffix,h in (("map","d"),("elf","e")):
                self.policy["artifacts"][f"build-evidence/{env}/firmware.{suffix}"]=dict(sha256=h*64)
            item=dict(path=path,archive="libfreertos.a",member="task.o",
                      classification=dict(kind="prebuilt_sdk_runtime_unqualified"))
            self.boards.append(dict(environment=env,descriptor=dict(idf="dirty-fixture"),retained_inputs=[item,dict(item)]))
        self.save()
    def write(self,path,data):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    def save(self):
        path=self.root/"docs/third-party/sdk-linked-archives.json"
        self.write(path,json.dumps(self.ledger).encode())
        self.policy["linked_sdk_evidence"]=dict(path=path.relative_to(self.root).as_posix(),sha256=sha(path.read_bytes()))
    def run_join(self,core=True):
        return r.linked_sdk_inventory(self.root,self.policy,self.boards,self.core if core else None)

    def test_exact_current_bytes_join_is_positive_identity_but_closure_stays_blocked(self):
        report=self.run_join()
        self.assertEqual(report["installed_bytes_check"],"EXACT_CURRENT_CACHE_MATCH")
        self.assertEqual(report["current_files_checked"],6)
        self.assertEqual(report["status"],"BLOCKED")
        self.assertEqual(len(report["blocked"]),2)
        for b in report["boards"]:
            self.assertEqual(b["archives"][0]["retained_members"],["task.o"])
            a=b["archives"][0]
            for key in ("source_commit","matching_binary_build_recipe","build_time_archive_digest","applicable_binary_notices"):
                self.assertIsNone(a[key])
            self.assertEqual(a["status"],"BLOCKED")
            self.assertEqual(len(a["missing"]),4)
        self.assertEqual(len(report["boards"][0]["archives"][0]["header_only_references_not_binary_qualification"]),1)
        self.assertEqual(report["boards"][1]["archives"][0]["header_only_references_not_binary_qualification"],[])

    def test_without_current_cache_no_claim_of_current_byte_verification(self):
        report=self.run_join(core=False)
        self.assertEqual(report["current_files_checked"],0)
        self.assertEqual(report["installed_bytes_check"],"NOT_CHECKED_CORE_NOT_SUPPLIED")
        self.assertEqual(report["source_offer_state"],"BLOCKED")

    def test_missing_reference_bad_ledger_hash_and_unknown_schema_fail(self):
        original=deepcopy(self.policy)
        self.policy.pop("linked_sdk_evidence")
        with self.assertRaisesRegex(NoticeError,"evidence_missing"):self.run_join()
        self.policy=deepcopy(original);self.policy["linked_sdk_evidence"]["sha256"]="0"*64
        with self.assertRaisesRegex(NoticeError,"ledger_conflict"):self.run_join()
        self.policy=original;self.ledger["schema"]=True;self.save()
        with self.assertRaisesRegex(NoticeError,"unsupported_linked_sdk_schema"):self.run_join()

    def test_missing_or_unretained_archive_and_duplicate_identity_fail(self):
        original=deepcopy(self.ledger)
        for archives in ([],original["boards"]["e32v2"]["archives"]*2,
                         [dict(original["boards"]["e32v2"]["archives"][0],path="unretained/lib.a")]):
            self.ledger=deepcopy(original);self.ledger["boards"]["e32v2"]["archives"]=archives;self.save()
            with self.assertRaisesRegex(NoticeError,"archive_set_conflict"):self.run_join()

    def test_new_actual_retained_archive_cannot_be_omitted(self):
        item=deepcopy(self.boards[0]["retained_inputs"][0])
        item["path"]=item["path"].replace("libfreertos.a","libunknown.a");item["archive"]="libunknown.a"
        self.boards[0]["retained_inputs"].append(item)
        with self.assertRaisesRegex(NoticeError,"archive_set_conflict"):self.run_join()

    def test_same_basename_in_other_sdk_path_needs_separate_byte_identity(self):
        item=deepcopy(self.boards[0]["retained_inputs"][0])
        item["path"]=item["path"].replace("/lib/","/dio_qspi/")
        self.boards[0]["retained_inputs"].append(item)
        with self.assertRaisesRegex(NoticeError,"archive_set_conflict"):self.run_join()
        data=b"other actual archive, same basename"
        self.write(self.fw/item["path"].removeprefix("packages/framework-arduinoespressif32/"),data)
        self.ledger["boards"]["e32v2"]["archives"].append(dict(path=item["path"],bytes=len(data),sha256=sha(data)));self.save()
        self.assertEqual(len(self.run_join()["boards"][0]["archives"]),2)

    def test_current_archive_config_and_metadata_byte_mismatch_fail(self):
        for relative in ("tools/sdk/esp32/lib/libfreertos.a","tools/sdk/esp32/sdkconfig","package.json"):
            f=self.fw/relative;original=f.read_bytes();f.write_bytes(b"changed")
            with self.assertRaisesRegex(NoticeError,"current_sdk_file_conflict"):self.run_join()
            f.write_bytes(original)
        f=self.fw/"tools/sdk/esp32/lib/libfreertos.a";f.unlink()
        with self.assertRaisesRegex(NoticeError,"current_sdk_file_conflict"):self.run_join()

    def test_package_pin_must_match_original_provenance_not_ledger_self_assertion(self):
        self.ledger["package_metadata"]["package.json"]["sha256"]="f"*64;self.save()
        with self.assertRaisesRegex(NoticeError,"metadata_pin_conflict"):self.run_join(core=False)

    def test_source_map_elf_descriptor_and_target_config_mismatch_fail(self):
        original=deepcopy(self.ledger)
        for key,value in (("descriptor_idf","clean-not-dirty"),("map_sha256","0"*64),
                          ("elf_sha256","0"*64),("sdk_target","esp32s3")):
            self.ledger=deepcopy(original);self.ledger["boards"]["e32v2"][key]=value;self.save()
            with self.assertRaises(NoticeError):self.run_join()
        self.ledger=deepcopy(original);self.ledger["receipt_source"]="different";self.save()
        with self.assertRaisesRegex(NoticeError,"source_conflict"):self.run_join()
        self.ledger=deepcopy(original)
        self.ledger["boards"]["esp32s3"]["cached_sdkconfig"]["path"]="tools/sdk/esp32/sdkconfig";self.save()
        with self.assertRaisesRegex(NoticeError,"config_target_conflict"):self.run_join()

    def test_root_notice_header_or_ledger_claim_cannot_create_binary_qualification(self):
        original=deepcopy(self.ledger)
        for key,value in (("source_commit","clean-header-commit"),("closure","VERIFIED"),
                          ("build_time_archive_digest","a"*64),("license","Apache-2.0")):
            self.ledger=deepcopy(original);self.ledger["boards"]["e32v2"]["archives"][0][key]=value;self.save()
            with self.assertRaisesRegex(NoticeError,"unsupported_linked_sdk_evidence"):self.run_join()
        self.ledger=original;self.save()
        self.policy["blocked"]=[] # Removing prior policy flags cannot close the join.
        self.assertEqual(self.run_join()["status"],"BLOCKED")

    def test_zero_bool_negative_size_bad_digest_and_escape_are_rejected(self):
        original=deepcopy(self.ledger)
        for key,value in (("bytes",False),("bytes",0),("bytes",-1),("sha256","bad")):
            self.ledger=deepcopy(original);self.ledger["boards"]["e32v2"]["archives"][0][key]=value;self.save()
            with self.assertRaisesRegex(NoticeError,"invalid_linked_sdk_identity"):self.run_join()
        self.ledger=deepcopy(original);self.save()
        f=self.fw/"tools/sdk/esp32/lib/libfreertos.a";f.unlink()
        outside=Path(self.tmp.name)/"outside.a";outside.write_bytes(b"external")
        f.symlink_to(outside)
        with self.assertRaisesRegex(NoticeError,"external_or_cyclic_path"):self.run_join()
        self.policy["linked_sdk_evidence"]["path"]="../escape.json"
        with self.assertRaisesRegex(NoticeError,"unsafe_relative_path"):self.run_join()

if __name__=="__main__":unittest.main()
