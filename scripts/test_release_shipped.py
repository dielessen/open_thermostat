"""Finite negative tests for actual-receipt audit semantics; no network/build."""
from pathlib import Path
import hashlib,json,struct,tempfile,unittest
import release_shipped as r
from release_notices import NoticeError

def elf_fixture():
    names=b"\0.shstrtab\0.flash.text\0"
    off=52+3*40
    head=struct.pack("<16sHHIIIIIHHHHHH",b"\x7fELF\x01\x01\x01"+b"\0"*9,2,94,1,0,0,52,0,52,0,0,40,3,1)
    null=b"\0"*40
    strings=struct.pack("<IIIIIIIIII",1,3,0,0,off,len(names),0,0,1,0)
    text=struct.pack("<IIIIIIIIII",11,1,2,0x1000,off+len(names),32,0,0,4,0)
    return head+null+strings+text+names+b"x"*32

def map_fixture(archive="libPubSubClient.a",split=False):
    header=".flash.text\n                0x1000 0x20\n" if split else ".flash.text 0x1000 0x20\n"
    return ("Archive member included to satisfy reference by file (symbol)\n"
      ".pio/build/e32v2/lib/libNotShipped.a(discarded.o)\n"
      "Discarded input sections\n .text.dead 0x0 0x20 .pio/build/e32v2/lib/libDead.a(dead.o)\n"
      "Linker script and memory map\n"
      "LOAD .pio/build/e32v2/lib/libOnlyScanned.a\n"+header+
      " .text.fn\n                0x1000 0x10 .pio/build/e32v2/lib/"+archive+"(fn.o)\n"
      " .text.zero 0x1010 0x0 .pio/build/e32v2/lib/libZero.a(dead.o)\n"
      ".debug_info 0x0 0x20\n .debug_info 0x0 0x20 .pio/build/e32v2/lib/libDebug.a(debug.o)\n"
      "Cross Reference Table\nlibAlsoNotShipped.a\n")

class Shipped(unittest.TestCase):
    def test_only_retained_alloc_inputs_not_load_discarded_debug_or_zero(self):
        alloc=r.elf_allocations(elf_fixture())
        for split in (False,True):
            rows=r.map_inputs(map_fixture(split=split),alloc)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["archive"],"libPubSubClient.a")
            self.assertEqual(rows[0]["retained_bytes"],16)

    def test_invalid_or_non_xtensa_elf_fails_closed(self):
        for bad in (b"not an elf",elf_fixture()[:70],elf_fixture().replace(b"\x7fELF\x01\x01",b"\x7fELF\x02\x02",1)):
            with self.assertRaises(NoticeError):r.elf_allocations(bad)
        bad=bytearray(elf_fixture());struct.pack_into("<H",bad,18,62)
        with self.assertRaisesRegex(NoticeError,"xtensa"):r.elf_allocations(bytes(bad))

    def test_output_conflict_out_of_range_and_missing_layout_rejected(self):
        alloc=r.elf_allocations(elf_fixture())
        for text in (map_fixture().replace(".flash.text 0x1000 0x20",".flash.text 0x1000 0x30"),
                     map_fixture().replace("0x1000 0x10","0x101f 0x10"),
                     map_fixture().replace("Linker script and memory map","not layout")):
            with self.assertRaises(NoticeError):r.map_inputs(text,alloc)

    def test_host_test_archives_cannot_be_silently_treated_as_sdk_runtime(self):
        for name in ("libcrypto.a","libssl.a","libgtest.a","libUnity.a"):
            with self.assertRaisesRegex(NoticeError,"unexpected_test_only_archive"):
                r.map_inputs(map_fixture(archive=name),r.elf_allocations(elf_fixture()))

    def test_unknown_archive_is_not_assumed_arduino_or_permissively_licensed(self):
        row=r.map_inputs(map_fixture(archive="libMystery.a"),r.elf_allocations(elf_fixture()))[0]
        policy=dict(external_libraries={},arduino_archives=["FrameworkArduino"])
        self.assertEqual(r.classify(row,policy)["component"],"UNKNOWN")

    def test_source_families_and_direct_crt_are_distinct(self):
        policy=dict(external_libraries={},arduino_archives=["FrameworkArduino"])
        sdk=dict(path="packages/framework-arduinoespressif32/tools/sdk/esp32/lib/libphy.a",archive="libphy.a")
        tool=dict(path="packages/toolchain-xtensa-esp32/xtensa-esp32-elf/lib/crt0.o",archive=None)
        self.assertEqual(r.classify(sdk,policy)["kind"],"prebuilt_sdk_runtime_unqualified")
        self.assertEqual(r.classify(tool,policy)["kind"],"toolchain_direct_object_unqualified")

    def test_raw_app_descriptor_binds_exact_elf_not_an_image_label(self):
        elf=elf_fixture();image=bytearray(288);image[0]=0xe9;struct.pack_into("<I",image,32,0xabcd5432)
        image[32+144:32+176]=hashlib.sha256(elf).digest()
        image[32+112:32+112+len(b"v4.4.7-dirty")]=b"v4.4.7-dirty"
        self.assertEqual(r.descriptor(bytes(image),elf)["idf"],"v4.4.7-dirty")
        with self.assertRaisesRegex(NoticeError,"elf_digest_conflict"):r.descriptor(bytes(image),elf+b"changed")
        image[32]=0
        with self.assertRaises(NoticeError):r.descriptor(bytes(image),elf)

    def test_web_requires_exact_aggregate_source_and_bytes_in_actual_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/"data/html/index.html";p.parent.mkdir(parents=True);p.write_bytes(b"<p>real source bytes</p>")
            sha=hashlib.sha256(p.read_bytes()).hexdigest()
            aggregate=hashlib.sha256(b"index.html\0"+bytes.fromhex(sha)).hexdigest()
            web=dict(assets={"index.html":sha},source="exactsource",version="alpha6-label-only",web_sha256=aggregate)
            marker=f"OT_E32V2_OTA_V1:{web['version']}:{web['source']}:{aggregate}:END".encode()
            binary=p.read_bytes()+marker
            r.verify_web(root,binary,web,"exactsource")
            for altered,source in ((marker,"exactsource"),(binary,"other-source"),(p.read_bytes(),"exactsource")):
                with self.assertRaises(NoticeError):r.verify_web(root,altered,web,source)
            p.write_bytes(b"changed local source")
            with self.assertRaises(NoticeError):r.verify_web(root,binary,web,"exactsource")

    def test_saved_receipt_source_size_payload_and_omission_conflicts_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            names={f"build-evidence/{env}/firmware.{suffix}" for env in ("e32v2","esp32s3") for suffix in ("bin","elf","map")}
            names.update(("build-evidence/e32v2/embedded-web.json","build-evidence/e32v2/spiffs.bin"))
            identities={}
            for name in names:
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b"finite exact receipt fixture bytes")
                identities[name]=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            logs={}
            for name in ("E32-BUILD.log","esp32s3-BUILD.log"):
                p=root/name;p.write_bytes(b"finite fixture build log");logs[name]=hashlib.sha256(p.read_bytes()).hexdigest()
            policy=dict(receipt_source="frozen",artifacts=identities,build_logs=logs)
            receipt=dict(source="frozen",artifacts=identities)
            p=root/"PRESERVED-BUILD-ARTIFACTS.json";p.write_text(json.dumps(receipt))
            r.verify_saved_receipts(root,policy)
            blob=root/"build-evidence/e32v2/firmware.bin";blob.write_bytes(b"wrong")
            with self.assertRaisesRegex(NoticeError,"actual_build_artifact_conflict"):r.verify_saved_receipts(root,policy)
            receipt["source"]="different";p.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(NoticeError,"receipt_identity_conflict"):r.verify_saved_receipts(root,policy)
            policy["artifacts"].pop("build-evidence/e32v2/firmware.elf")
            with self.assertRaisesRegex(NoticeError,"required_build_receipt_omitted"):r.verify_saved_receipts(root,policy)

    def test_ha_unknown_import_and_production_resolution_never_inferred_from_test_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=root/"candidate.py";f.write_text("import math\nimport homeassistant\nimport probatio\n")
            m=root/"manifest.json";m.write_text(json.dumps(dict(domain="fixture",dependencies=["mqtt","lovelace"])))
            policy=dict(source_files={"candidate.py":hashlib.sha256(f.read_bytes()).hexdigest(),"manifest.json":hashlib.sha256(m.read_bytes()).hexdigest()},
                        manifest="manifest.json",source_candidate="frozen",platform_imports=["homeassistant","voluptuous"])
            report=r.ha_inventory(root,policy)
            self.assertEqual(report["unqualified_external_imports"],{"probatio":["candidate.py"]})
            self.assertEqual(report["separately_declared_requirements"],[])
            self.assertIn("UNKNOWN",report["installed_production_versions"])
            extra=root/"unlisted.py";extra.write_text("import another_unknown")
            with self.assertRaisesRegex(NoticeError,"ha_source_inventory_incomplete"):r.ha_inventory(root,policy)
            extra.unlink()
            f.write_text("import other")
            with self.assertRaisesRegex(NoticeError,"ha_source_identity_conflict"):r.ha_inventory(root,policy)

    def test_native_validator_requires_exact_reviewed_core_evidence_not_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"component").mkdir();f=root/"component/candidate.py";f.write_text("import probatio\nimport mystery\n")
            m=root/"component/manifest.json";m.write_text(json.dumps(dict(domain="fixture")))
            policy=dict(source_files={"component/candidate.py":hashlib.sha256(f.read_bytes()).hexdigest(),
                        "component/manifest.json":hashlib.sha256(m.read_bytes()).hexdigest()},
                        manifest="component/manifest.json",source_candidate="fixture",platform_imports=["homeassistant","voluptuous","probatio","mystery"])
            with self.assertRaisesRegex(NoticeError,"native_platform_evidence_missing"):
                r.ha_inventory(root,policy)
            real=Path(__file__).resolve().parents[1]
            evidence=json.loads((real/"docs/third-party/native-ha-validator.json").read_text())
            license_path=root/evidence["probatio"]["original_license_path"]
            license_path.parent.mkdir(parents=True)
            license_path.write_bytes((real/evidence["probatio"]["original_license_path"]).read_bytes())
            ledger=root/"ledger.json";ledger.write_text(json.dumps(evidence))
            policy["native_platform_evidence"]={"path":"ledger.json","sha256":hashlib.sha256(ledger.read_bytes()).hexdigest()}
            report=r.ha_inventory(root,policy)
            self.assertIn("probatio",report["platform_provided_imports"])
            self.assertEqual(report["unqualified_external_imports"],{"mystery":["component/candidate.py"]})
            self.assertIn("UNKNOWN",report["installed_production_versions"])
            license_path.write_bytes(b"not original")
            with self.assertRaisesRegex(NoticeError,"native_validator_original_license_conflict"):
                r.ha_inventory(root,policy)

    def test_native_validator_missing_requirement_or_changed_ledger_is_not_qualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"component").mkdir();f=root/"component/candidate.py";f.write_text("import probatio\n")
            m=root/"component/manifest.json";m.write_text(json.dumps(dict(domain="fixture")))
            real=Path(__file__).resolve().parents[1]
            evidence=json.loads((real/"docs/third-party/native-ha-validator.json").read_text())
            evidence["homeassistant"]["requires"]=[]
            ledger=root/"ledger.json";ledger.write_text(json.dumps(evidence))
            policy=dict(source_files={"component/candidate.py":hashlib.sha256(f.read_bytes()).hexdigest(),
                        "component/manifest.json":hashlib.sha256(m.read_bytes()).hexdigest()},
                        manifest="component/manifest.json",source_candidate="fixture",platform_imports=["probatio"],
                        native_platform_evidence={"path":"ledger.json","sha256":hashlib.sha256(ledger.read_bytes()).hexdigest()})
            with self.assertRaisesRegex(NoticeError,"unqualified_native_validator"):r.ha_inventory(root,policy)
            ledger.write_text("{}")
            with self.assertRaisesRegex(NoticeError,"native_platform_evidence_conflict"):r.ha_inventory(root,policy)

if __name__=="__main__":unittest.main()
