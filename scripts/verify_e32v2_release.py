"""Independent release-payload checks; no device or network access."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
from e32_distribution import checked_reproduction
from e32_relink import filehash, inside
from e32_source_inputs import verify as verify_source_inputs
from release_notices import canonical, digest as canonical_digest


def verify(package, root=None):
    package = Path(package)
    checks = []
    def check(ok, name):
        if not ok:
            raise AssertionError(name)
        checks.append(name)
    m = json.loads((package / "e32v2-update.json").read_text())
    check(set(m) == {"version", "board", "layout", "settings_schema", "update_schema", "ui", "asset", "source_commit", "web_sha256", "sha256", "size"}, "exact manifest schema")
    check(m["board"] == "bbqkees_e32v2" and m["layout"] == "e32v2-dual-app-spiffs-v1", "board/layout")
    check(m["settings_schema"] == m["update_schema"] == 1 and m["ui"] == "embedded" and m["asset"] == "firmware.bin", "settings-compatible app-only OTA")
    firmware = (package / "firmware.bin").read_bytes()
    check(1024 <= len(firmware) <= 0x380000 and len(firmware) == m["size"], "app size fits both existing slots")
    check(hashlib.sha256(firmware).hexdigest() == m["sha256"], "firmware SHA256")
    check(firmware[0] == 0xe9 and firmware[3] >> 4 == 4 and firmware[12:14] == b"\0\0", "actual ESP32/16MB app header, not factory/S3")
    marker = f'OT_E32V2_OTA_V1:{m["version"]}:{m["source_commit"]}:{m["web_sha256"]}:END'.encode()
    check(marker in firmware, "version/source/UI marker in actual image")
    check((package / "SOURCE_COMMIT.txt").read_text().strip() == m["source_commit"], "source identity")
    with tarfile.open(package / "source.tar.gz") as archive:
        members = {a.name:a for a in archive.getmembers() if a.isfile()}
        accepted_path_required = "scripts/verify_accepted_update_path.py" in members and "-e32v2-alpha." not in m["version"]
        release = json.loads(archive.extractfile(members["release.json"]).read())
        check(release["version"] == m["version"], "version frozen in source")
        from verify_e32v2_web_assets import image_sources, source_in_image
        web = hashlib.sha256()
        streams = image_sources(firmware)
        for name in sorted(n for n in members if n.startswith("data/html/")):
            data = archive.extractfile(members[name]).read()
            web.update(name.removeprefix("data/html/").encode() + b"\0")
            web.update(hashlib.sha256(data).digest())
            check(source_in_image(name, data, firmware, streams), "embedded exact webasset (gzip) " + name)
        check(web.hexdigest() == m["web_sha256"], "complete web UI revision hash")
        check(archive.extractfile(members["certs/github-ca-bundle.bin"]).read() in firmware, "public trust bundle embedded")
        for prefix, dest in [("docs/",package / "docs"),("ha/config/custom_components/open_thermostat/",package / "home-assistant/custom_components/open_thermostat")]:
            expected = {n.removeprefix(prefix):a for n,a in members.items() if n.startswith(prefix)}
            actual = {str(p.relative_to(dest)):p for p in dest.rglob("*") if p.is_file()}
            check(actual.keys() == expected.keys(), "package tree inventory " + prefix)
            check(all(actual[n].read_bytes() == archive.extractfile(a).read() for n,a in expected.items()), "package tree bytes " + prefix)
        if root:
            root = Path(root)
            head = subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
            check(head == m["source_commit"], "build/check HEAD matches manifest")
            expected = subprocess.check_output(["git","ls-tree","-r","--name-only",head],cwd=root,text=True).splitlines()
            check(set(expected) == members.keys(), "exact source archive inventory")
            for name in expected:
                check(archive.extractfile(members[name]).read() == subprocess.check_output(["git","show",head+":"+name],cwd=root), "source bytes " + name)
            metadata = json.loads((root / ".pio/build/e32v2/embedded-web.json").read_text())
            check(metadata["source"] == head and metadata["web_sha256"] == m["web_sha256"], "compiled registry revision")
            elf = (root / ".pio/build/e32v2/firmware.elf").read_bytes()
            check(hashlib.sha256(elf).digest() == firmware[0xb0:0xd0], "ELF matches panic hash in app descriptor")
    if accepted_path_required:
        from verify_accepted_update_path import verify_report
        compatibility = json.loads((package / "accepted-predecessor-compatibility.json").read_text())
        verify_report(package,compatibility,package/"e32v2-update.json",source_root=root)
        check(True,"receipt-bound accepted updater catalog and image compatibility")
    # Independently inspect the delivered material, rather than relying on the
    # packager's claim that source/notices/relink objects were supplied.
    third_party = package / "third-party"
    policy = json.loads((package / "docs/third-party/e32v2-source-inputs.json").read_text())
    spec = json.loads((package / "docs/third-party/e32v2-source-distribution.json").read_text())
    vendor = third_party / "vendor-source-inputs.zip"
    check(vendor.stat().st_size == spec["bytes"] and filehash(vendor) == spec["sha256"], "delivered pinned vendor source archive")
    source_proof = verify_source_inputs(policy,vendor)
    check(source_proof["status"] == "PASS_VENDOR_SOURCE_INPUTS_ONLY", "delivered source paths and original notices")
    sdk = json.loads((third_party / "sdk-reproduction.json").read_text())
    checked_reproduction(package,m["source_commit"],sdk)
    check(True,"current clean-commit SDK reproduction matches reviewed original object identities")
    distribution = json.loads((third_party / "E32-DISTRIBUTION.json").read_text())
    check(distribution["source_commit"] == m["source_commit"] and distribution["firmware_sha256"] == m["sha256"], "distribution bound to actual firmware and source")
    check(distribution["elf_sha256"] == firmware[0xb0:0xd0].hex(), "distribution bound to actual app ELF descriptor")
    check(distribution["sdk_reproduction_receipt_sha256"] == filehash(third_party / "sdk-reproduction.json"), "delivered SDK receipt identity")
    check(distribution["global_framework_closure_changed"] is False and distribution["physical_acceptance"] is False, "target-specific scope and pending physical acceptance")
    notices = json.loads((third_party / "installed-notices/NOTICE-INVENTORY.json").read_text())
    stored_inventory_hash = notices.pop("inventory_sha256")
    check(canonical_digest(canonical(notices).encode()) == stored_inventory_hash, "delivered notice inventory hash")
    check(notices["environment"] == "e32v2" and notices["blocked"] == []
          and notices["status"] == "READY_FOR_NOTICES_PACKAGING_ONLY"
          and notices["resolved_target_specific_blockers"] == ["sdk_binary_notice_source_closure_unverified"], "scoped notice packaging qualification")
    check(notices["e32_distribution_evidence"] == distribution, "notice qualification carries exact distribution proof")
    relink = package / "relink"
    link_manifest = json.loads((relink / "RELINK-MANIFEST.json").read_text())
    link_proof = json.loads((relink / "RELINK-VERIFICATION.json").read_text())
    review = json.loads((package / "docs/third-party/e32v2-link-review.json").read_text())
    check(link_manifest["source_commit"] == m["source_commit"] == link_proof["source_commit"], "delivered application relink source identity")
    check(link_manifest["candidate_elf_sha256"] == distribution["elf_sha256"] == link_proof["candidate_elf_sha256"], "delivered application relink candidate identity")
    check(link_proof["status"] == "PASS_APPLICATION_RELINK_ONLY" and link_proof["exact"]["exact_original_elf"] is True
          and link_proof["modified"]["modified_library"] is True and link_proof["changed_library_code_retained"] is True,
          "both original and deliberately changed-library relinks verified")
    check({r["path"]:r["sha256"] for r in link_manifest["core_files"]} == review["core_files"], "delivered relink original core pins")
    for row in link_manifest["object_files"]:
        check(filehash(inside(relink,row["path"])) == row["sha256"], "delivered application object " + row["path"])
    check((relink / "application-source.tar.gz").read_bytes() == (package / "source.tar.gz").read_bytes(), "relink and package supply identical complete application source")
    check(not any(relink.rglob("*.elf")) and not (relink / "proof").exists(), "altered and research ELF images excluded from delivery")
    with tarfile.open(package / "source.tar.gz") as source_archive:
        check((relink / "relink.py").read_bytes() == source_archive.extractfile("scripts/e32_relink.py").read(), "relink runner matches complete source")
    factory = (package / "e32v2-factory.bin").read_bytes()
    check(len(factory) == 0xb80000 and factory[0x9000:0xe000] == b"\xff"*0x5000, "separate clean-install factory span and blank NVS")
    for name, offset in [("bootloader.bin",0x1000),("partitions.bin",0x8000),("boot_app0.bin",0xe000),("firmware.bin",0x10000),("spiffs.bin",0x710000)]:
        data = (package / name).read_bytes()
        check(factory[offset:offset+len(data)] == data, "factory slice " + name)
    sums = {}
    for line in (package / "SHA256SUMS.txt").read_text().splitlines():
        digest, name = line.split("  ",1)
        check(hashlib.sha256((package / name).read_bytes()).hexdigest() == digest, "payload checksum " + name)
        sums[name] = digest
    check(set(sums) == {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"}, "complete checksum inventory")
    return {"status":"PASS","checks_passed":len(checks),"checks":checks,"version":m["version"],"source_commit":m["source_commit"],"firmware_sha256":m["sha256"],"firmware_bytes":m["size"],"web_sha256":m["web_sha256"],"physical_acceptance":"pending actual board update, settings readback, failure and recovery; no heating GO"}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("package",type=Path)
    parser.add_argument("--root",type=Path)
    parser.add_argument("--report",type=Path)
    args = parser.parse_args()
    report = verify(args.package,args.root)
    if args.report:
        args.report.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="checks"},indent=2))
