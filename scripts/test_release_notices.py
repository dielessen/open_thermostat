"""Focused offline provenance/notice and release-denial regressions (stdlib)."""
from pathlib import Path
import copy
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import release_notices as n

REPO=Path(__file__).resolve().parents[1]

class Notices(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"source";self.core=Path(self.tmp.name)/"core"
        self.root.mkdir();self.core.mkdir()
        shutil.copytree(REPO/"docs/third-party",self.root/"docs/third-party")
        shutil.copytree(REPO/"data/html/deps",self.root/"data/html/deps")
        shutil.copy2(REPO/"LICENSE",self.root/"LICENSE")
        self.proof=json.loads((self.root/"docs/third-party/provenance.json").read_text())
        self.version=self.proof["framework"]["resolved_version"]
        (self.root/"platformio.ini").write_text("framework-arduinoespressif32@"+self.version)
        sdk=self.core/"packages/framework-arduinoespressif32";sdk.mkdir(parents=True)
        for name in self.proof["framework"]["pins"]:
            f=sdk/name;f.parent.mkdir(parents=True,exist_ok=True)
            data=(json.dumps(dict(name="framework-arduinoespressif32",version=self.version)).encode()
                  if name in ("package.json",".piopm") else b"explicit native fixture header\n")
            f.write_bytes(data);self.proof["framework"]["pins"][name]=n.digest(data)
        for part in ("platforms/espressif32","packages/toolchain-xtensa-esp32"):
            p=self.core/part;p.mkdir(parents=True);(p/"LICENSE").write_bytes(b"original fixture notice\n")
        p=self.root/".pio/libdeps/e32v2/fixture";p.mkdir(parents=True)
        (p/"library.properties").write_text("name=fixture\nversion=1.2.3\nlicense=fixture-only\n")
        (p/"COPYING").write_bytes(b"original fixture library notice\n")
        self.save()

    def save(self):
        (self.root/"docs/third-party/provenance.json").write_text(json.dumps(self.proof))

    def collect(self):
        return n.collect(self.root,self.core)

    def test_repeatable_inventory_and_exact_original_export(self):
        a,roots=self.collect();b,_=self.collect();self.assertEqual(a,b)
        self.assertEqual(a["blocked"],["sdk_binary_notice_source_closure_unverified"])
        self.assertEqual(len(a["assets"]),6)
        out=Path(self.tmp.name)/"export";n.export(a,roots,self.root,out)
        for text in self.proof["original_upstream_notices"]:
            self.assertEqual((self.root/text["path"]).read_bytes(),(out/"originals"/Path(text["path"]).name).read_bytes())
        self.assertEqual((out/"installed/library-fixture/COPYING").read_bytes(),b"original fixture library notice\n")
        self.assertEqual(json.loads((out/"NOTICE-INVENTORY.json").read_text()),a)

    def test_asset_and_upstream_proof_conflicts_rejected(self):
        for asset in self.proof["assets"]:
            with self.subTest(path=asset["path"]):
                f=self.root/asset["path"];old=f.read_bytes();f.write_bytes(old+b"tampered")
                with self.assertRaises(n.NoticeError):self.collect()
                f.write_bytes(old)
        self.proof["assets"][0]["upstream_sha256"]="0"*64;self.save()
        with self.assertRaisesRegex(n.NoticeError,"upstream_asset_hash_conflict"):self.collect()

    def test_source_map_rename_is_the_only_permitted_bootstrap_difference(self):
        asset=next(a for a in self.proof["assets"] if a["path"].endswith("bs.bundle.min.js.gz"))
        f=self.root/asset["path"];body=gzip.decompress(f.read_bytes()).replace(b"jQuery",b"jQuerZ",1)
        raw=gzip.compress(body,mtime=0);f.write_bytes(raw)
        asset["gzip_sha256"]=n.digest(raw);asset["body_sha256"]=n.digest(body)
        asset["gzip_bytes"]=len(raw);asset["body_bytes"]=len(body);self.save()
        with self.assertRaisesRegex(n.NoticeError,"upstream_asset_hash_conflict"):self.collect()

    def test_notice_tamper_and_export_time_change_rejected(self):
        report,roots=self.collect();p=self.root/self.proof["original_upstream_notices"][0]["path"]
        p.write_bytes(p.read_bytes()+b"edited")
        with self.assertRaisesRegex(n.NoticeError,"original_notice_hash_conflict"):self.collect()
        with self.assertRaisesRegex(n.NoticeError,"original_notice_changed_after_inventory"):
            n.export(report,roots,self.root,Path(self.tmp.name)/"bad-export")

    def test_unqualified_sdk_cannot_package_even_after_evidence_export(self):
        report,roots=self.collect();n.export(report,roots,self.root,Path(self.tmp.name)/"blocked-evidence")
        with self.assertRaisesRegex(n.NoticeError,"BLOCKED"):n.require_publishable(report)
        forged=copy.deepcopy(report);forged["status"]="READY_FOR_NOTICES_PACKAGING_ONLY"
        with self.assertRaises(n.NoticeError):n.require_publishable(forged)

    def test_missing_environment_and_metadata_version_conflict(self):
        shutil.rmtree(self.root/".pio/libdeps/e32v2")
        report,_=self.collect();self.assertIn("selected_cached_libdeps_missing",report["blocked"])
        f=self.core/"packages/framework-arduinoespressif32/package.json"
        f.write_text(json.dumps(dict(version="future")))
        with self.assertRaisesRegex(n.NoticeError,"framework_resolved_version_conflict"):self.collect()

    def test_unknown_schema_and_escaping_paths_rejected(self):
        baseline=copy.deepcopy(self.proof)
        self.proof["schema"]=99;self.save()
        with self.assertRaises(n.NoticeError):self.collect()
        for target in ("../LICENSE","/tmp/LICENSE","data/html/deps/../../../../LICENSE"):
            self.proof=copy.deepcopy(baseline);self.proof["assets"][0]["path"]=target;self.save()
            with self.assertRaises(n.NoticeError):self.collect()
        self.proof=baseline;self.save()
        with self.assertRaises(n.NoticeError):n.collect(self.root,self.core,"../e32v2")

    def test_internal_symlink_notice_preserved_external_dangling_and_cycle_block(self):
        p=Path(self.tmp.name)/"links";p.mkdir();(p/"COPYING").write_bytes(b"unaltered original\n")
        (p/"LICENSE").symlink_to("COPYING")
        c=n.component(p,"fixture");self.assertEqual(c["blocked"],[])
        self.assertEqual(len(c["notices"]),2)
        self.assertEqual(c["files"][1]["symlink_target"],"COPYING")
        report=dict(components=[c],original_upstream_notices=[])
        out=Path(self.tmp.name)/"links-export";n.export(report,{"fixture":p},self.root,out)
        self.assertEqual((out/"installed/fixture/LICENSE").read_bytes(),b"unaltered original\n")
        (p/"external").symlink_to(self.root/"LICENSE")
        (p/"missing").symlink_to("absent")
        (p/"cyclic").symlink_to("cyclic")
        c=n.component(p,"fixture");self.assertEqual(len(c["blocked"]),3)

    def test_export_does_not_follow_a_notice_rebound_outside_component(self):
        report,roots=self.collect();notice=self.root/".pio/libdeps/e32v2/fixture/COPYING"
        notice.unlink();notice.symlink_to(self.root/"LICENSE")
        with self.assertRaisesRegex(n.NoticeError,"external_or_cyclic_path"):
            n.export(report,roots,self.root,Path(self.tmp.name)/"rebound")

    def test_real_packager_denies_before_creating_any_release_outputs(self):
        scripts=self.root/"scripts";scripts.mkdir()
        for name in ("package_e32v2_release.py","release_notices.py","verify_e32v2_release.py",
                     "e32_distribution.py","e32_relink.py","e32_source_closure.py",
                     "e32_source_inputs.py","release_shipped.py"):
            shutil.copy2(REPO/"scripts"/name,scripts/name)
        pkg=Path(self.tmp.name)/"package";release=Path(self.tmp.name)/"release"
        env={**os.environ,"PLATFORMIO_CORE_DIR":str(self.core),"PYTHONDONTWRITEBYTECODE":"1"}
        result=subprocess.run([sys.executable,str(scripts/"package_e32v2_release.py"),"--output",str(pkg),"--release-output",str(release)],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn("sdk_binary_notice_source_closure_unverified",result.stderr)
        self.assertFalse(pkg.exists());self.assertFalse(release.exists())

if __name__=="__main__":unittest.main()
