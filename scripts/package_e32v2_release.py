"""Package the already-built, verified E32 app and independent clean-install kit."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from verify_e32v2_release import verify
from release_notices import collect, require_publishable, export as export_notices
from e32_distribution import prepare as prepare_distribution

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--output",type=Path,default=root/"out/e32v2")
parser.add_argument("--release-output",type=Path,default=root/"out/release")
parser.add_argument("--source-inputs",type=Path,help="Exact pinned vendor source/notice ZIP; never an approval flag")
parser.add_argument("--sdk-reproduction",type=Path,help="Successful current-commit independently checked CI reproduction receipt")
args = parser.parse_args()
pkg = args.output.resolve();assets = args.release_output.resolve()
if (pkg.exists() and any(pkg.iterdir())) or (assets.exists() and any(assets.iterdir())):
    raise RuntimeError("Use empty release output directories; do not mix old assets")
core_root = Path(__import__('os').environ.get("PLATFORMIO_CORE_DIR",str(Path.home()/".platformio")))
notices, notice_roots = collect(root,core_root,"e32v2")
distribution = None
if bool(args.source_inputs) != bool(args.sdk_reproduction):
    raise RuntimeError("Both the source distribution and current SDK reproduction receipt are required")
if args.source_inputs:
    relink_work = pkg.parent/(pkg.name+"-relink-proof")
    notices, distribution = prepare_distribution(root,core_root,args.source_inputs,
        args.sdk_reproduction,notices,relink_work)
# Evidence export may be BLOCKED; release packaging must never bypass that gate.
require_publishable(notices)
pkg.mkdir(parents=True,exist_ok=True);assets.mkdir(parents=True,exist_ok=True)
# Distribution notices have their own tree; docs/ remains the exact source tree.
export_notices(notices,notice_roots,root,pkg/"third-party/installed-notices")
if distribution:
    shutil.copy2(args.source_inputs,pkg/"third-party/vendor-source-inputs.zip")
    shutil.copy2(args.sdk_reproduction,pkg/"third-party/sdk-reproduction.json")
    (pkg/"third-party/E32-DISTRIBUTION.json").write_text(json.dumps(distribution,indent=2)+"\n")
    shutil.copytree(relink_work,pkg/"relink",
        ignore=lambda base,names:["proof"] if Path(base)==relink_work else [])
    (pkg/"relink/verification").mkdir()
    for name in ("original-millis.txt","modified-millis.txt"):
        shutil.copy2(relink_work/"proof"/name,pkg/"relink/verification"/name)
head = subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
if subprocess.check_output(["git","status","--porcelain"],cwd=root):
    raise RuntimeError("Release requires a clean source checkout")
meta = json.loads((root/".pio/build/e32v2/embedded-web.json").read_text())
release = json.loads((root/"release.json").read_text())
assert meta["source"] == head and meta["version"] == release["version"]
build = root/".pio/build/e32v2"
core = core_root/"packages"
for name in ["bootloader.bin","partitions.bin","firmware.bin","spiffs.bin"]:
    shutil.copy2(build/name,pkg/name)
shutil.copy2(core/"framework-arduinoespressif32/tools/partitions/boot_app0.bin",pkg/"boot_app0.bin")
shutil.copy2(root/"partitions_e32v2.csv",pkg/"partitions_e32v2.csv")
shutil.copy2(root/"LICENSE",pkg/"LICENSE")
(pkg/"SOURCE_COMMIT.txt").write_text(head+"\n")
subprocess.run(["git","archive","--format=tar.gz","-o",str(pkg/"source.tar.gz"),head],cwd=root,check=True)
with tarfile.open(pkg/"source.tar.gz") as archive:
    for member in archive.getmembers():
        if not member.isfile():continue
        dest = None
        if member.name.startswith("docs/"):dest=pkg/member.name
        elif member.name.startswith("ha/config/custom_components/open_thermostat/"):
            dest=pkg/"home-assistant/custom_components/open_thermostat"/member.name.removeprefix("ha/config/custom_components/open_thermostat/")
        if dest:
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.extractfile(member).read())
firmware = (pkg/"firmware.bin").read_bytes()
manifest = {**release,"ui":"embedded","asset":"firmware.bin","source_commit":head,"web_sha256":meta["web_sha256"],"size":len(firmware),"sha256":hashlib.sha256(firmware).hexdigest()}
(pkg/"e32v2-update.json").write_text(json.dumps(manifest,indent=2)+"\n")
from e32_symbols import export as export_symbols
export_symbols(build,pkg)
subprocess.run([sys.executable,str(core/"tool-esptoolpy/esptool.py"),"--chip","esp32","merge_bin","--output",str(pkg/"e32v2-factory.bin"),"--target-offset","0","--flash_mode","dio","--flash_freq","80m","--flash_size","16MB","0x1000",str(pkg/"bootloader.bin"),"0x8000",str(pkg/"partitions.bin"),"0xe000",str(pkg/"boot_app0.bin"),"0x10000",str(pkg/"firmware.bin"),"0x710000",str(pkg/"spiffs.bin")],check=True)
(pkg/"README.md").write_text("# OpenThermostat E32 V2 — "+release["version"]+"\n\nRead docs/modern-thermostat/GITHUB-UPDATES.nl.md.\n\nfirmware.bin: settings-preserving application-only bootstrap/OTA; includes web UI.\ne32v2-factory.bin: separate clean USB installation at0x0; full erase DELETES SETTINGS. Never offer this factory file as an OTA app.\n\nsymbols/: exact firmware.elf, firmware.map and embedded-web.json with independently checked SYMBOLS.json; ELF SHA256 must match the OTA image descriptor. For panic decoding, never installation.\nthird-party/vendor-source-inputs.zip: pinned original vendor source snapshots and notices.\nthird-party/installed-notices: unchanged installed/original notices and inventory.\nrelink/: exact application source, actual objects, link recipe and verified changed-library relink evidence. Read relink/README.md. Altered proof ELF files are excluded from this package.\nSDK/runtime reproduction recipes and safe source preparation are included in source.tar.gz; see docs/third-party/e32v2-reproduction/README.md.\n\nExperimental prerelease, outputs remain blocked, keep EMS disconnected.\nSoftware verification is not physical update/failure/recovery acceptance.\n")
factory=(pkg/"e32v2-factory.bin").read_bytes()
(pkg/"FACTORY-CHECK.txt").write_text("Offset:0x0; full clean installation deletes settings\nLength:"+str(len(factory))+"\nMD5 before first boot:"+hashlib.md5(factory).hexdigest()+"\n")
if "-e32v2-beta." in release["version"]:
    from verify_alpha36_beta_path import verify as verify_predecessor
    compatibility = verify_predecessor(root,pkg/"e32v2-update.json",pkg/"firmware.bin")
    (pkg/"alpha36-beta-compatibility.json").write_text(json.dumps(compatibility,indent=2)+"\n")
    shutil.copy2(pkg/"alpha36-beta-compatibility.json",assets/"alpha36-beta-compatibility.json")
    from verify_accepted_update_path import verify as verify_accepted
    accepted_compatibility = verify_accepted(root,pkg/"e32v2-update.json",pkg/"firmware.bin")
    (pkg/"accepted-predecessor-compatibility.json").write_text(json.dumps(accepted_compatibility,indent=2)+"\n")
    shutil.copy2(pkg/"accepted-predecessor-compatibility.json",assets/"accepted-predecessor-compatibility.json")
(pkg/"SHA256SUMS.txt").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+str(p.relative_to(pkg))+"\n" for p in sorted(pkg.rglob("*")) if p.is_file() and p.name!="SHA256SUMS.txt"))
report = verify(pkg,root)
(assets/"software-verification.json").write_text(json.dumps(report,indent=2)+"\n")
for name in ["firmware.bin","e32v2-update.json"]:shutil.copy2(pkg/name,assets/name)
zip_path = assets/("open-thermostat-e32v2-"+release["version"]+".zip")
with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for p in sorted(pkg.rglob("*")):
        if p.is_file():archive.write(p,p.relative_to(pkg))
with zipfile.ZipFile(zip_path) as archive:
    assert archive.testzip() is None
    assert set(archive.namelist()) == {str(p.relative_to(pkg)) for p in pkg.rglob("*") if p.is_file()}
    assert all(archive.read(str(p.relative_to(pkg))) == p.read_bytes() for p in pkg.rglob("*") if p.is_file())
(assets/"RELEASE-SHA256SUMS.txt").write_text("".join(hashlib.sha256(p.read_bytes()).hexdigest()+"  "+p.name+"\n" for p in sorted(assets.iterdir()) if p.is_file() and p.name!="RELEASE-SHA256SUMS.txt"))
print(json.dumps({k:v for k,v in report.items() if k!="checks"},indent=2))
