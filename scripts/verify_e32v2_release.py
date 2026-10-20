"""Independent release-payload checks; no device or network access."""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile


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
        release = json.loads(archive.extractfile(members["release.json"]).read())
        check(release["version"] == m["version"], "version frozen in source")
        web = hashlib.sha256()
        for name in sorted(n for n in members if n.startswith("data/html/")):
            data = archive.extractfile(members[name]).read()
            web.update(name.removeprefix("data/html/").encode() + b"\0")
            web.update(hashlib.sha256(data).digest())
            check(data in firmware, "embedded exact webasset " + name)
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
