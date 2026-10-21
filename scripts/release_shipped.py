"""Offline audit of saved local-build receipts, retained inputs and package sources.
Not a publication, runtime/physical acceptance or universal licensing certificate.
Reuses release_notices; requires matching receipts, never rebuilds/downloads.
"""
from pathlib import Path
import argparse,ast,hashlib,json,re,struct,sys
from release_notices import NoticeError,canonical,digest,filehash,inside

TEST_ARCHIVES={"libgtest.a","libgtest_main.a","libgmock.a","libUnity.a","libssl.a","libcrypto.a"}

def elf_allocations(data):
    if len(data)<52 or data[:7]!=b"\x7fELF\x01\x01\x01":
        raise NoticeError("requires_elf32_little_endian")
    header=struct.unpack_from("<16sHHIIIIIHHHHHH",data)
    if header[2]!=94:raise NoticeError("requires_xtensa_elf")
    offset=header[6];entry,count,names_index=header[11:14]
    if entry!=40 or not 0<count<=4096 or names_index>=count or offset+entry*count>len(data):
        raise NoticeError("invalid_elf_section_table")
    rows=[struct.unpack_from("<IIIIIIIIII",data,offset+i*entry) for i in range(count)]
    names=rows[names_index]
    if names[4]+names[5]>len(data):raise NoticeError("invalid_elf_section_names")
    strings=data[names[4]:names[4]+names[5]];result={}
    for row in rows:
        if not row[2]&2 or not row[5]:continue
        end=strings.find(b"\0",row[0])
        if row[0]>=len(strings) or end<0:raise NoticeError("invalid_elf_section_name")
        name=strings[row[0]:end].decode("ascii")
        if name in result:raise NoticeError("duplicate_elf_alloc_section")
        if row[1]!=8 and row[4]+row[5]>len(data):raise NoticeError("invalid_elf_section_data")
        result[name]=dict(address=row[3],size=row[5],nobits=row[1]==8)
    if not result:raise NoticeError("missing_alloc_sections")
    return result

def map_inputs(text,allocations):
    """Only input sections within actual ELF SHF_ALLOC output ranges.
    LOAD/initial archive-member and discarded/debug lists are not shipment proof.
    Reported sizes include retained RAM/NOBITS, NOT image-size attribution.
    """
    rows={};layout=False;current=None;pending=False;seen=set()
    for line in text.splitlines():
        if line=="Linker script and memory map":layout=True;continue
        if not layout:continue
        if line.startswith("Cross Reference Table"):break
        if line.startswith("."):
            name=line.split()[0];current=name if name in allocations else None
            if current:
                seen.add(name);pending=True
                values=re.match(r"^\S+\s+0x([a-fA-F0-9]+)\s+0x([a-fA-F0-9]+)",line)
                if values:
                    if tuple(int(x,16) for x in values.groups())!=(allocations[name]["address"],allocations[name]["size"]):
                        raise NoticeError("map_elf_output_conflict:"+name)
                    pending=False
            continue
        if current is None:continue
        header=re.match(r"^\s+0x([a-fA-F0-9]+)\s+0x([a-fA-F0-9]+)\s*$",line)
        if pending and header:
            if tuple(int(x,16) for x in header.groups())!=(allocations[current]["address"],allocations[current]["size"]):
                raise NoticeError("map_elf_output_conflict:"+current)
            pending=False;continue
        row=re.match(r"^\s+(?:\.\S+\s+)?0x([a-fA-F0-9]+)\s+0x([a-fA-F0-9]+)\s+(.+?)\s*$",line)
        if not row:continue
        address,size=int(row[1],16),int(row[2],16);obj=row[3]
        if not ((".a(" in obj and obj.endswith(")")) or obj.endswith((".o",".obj"))):continue
        if size==0:continue
        section=allocations[current]
        if pending:raise NoticeError("missing_map_output_header")
        if not section["address"]<=address or address+size>section["address"]+section["size"]:
            raise NoticeError("retained_input_outside_elf_output")
        if ".a(" in obj:
            path,member=obj.rsplit("(",1);member=member[:-1]
            archive=Path(path).name
            if archive in TEST_ARCHIVES:raise NoticeError("unexpected_test_only_archive:"+archive)
        else:path=obj;member=None;archive=None
        # No private absolute host paths in the public inventory.
        if "/packages/" in path:identity="packages/"+path.split("/packages/",1)[1]
        elif path.startswith(".pio/build/"):identity=path
        else:identity="unqualified-origin/"+Path(path).name
        key=(identity,member)
        if key not in rows:rows[key]=dict(path=identity,archive=archive,member=member,retained_bytes=0,output_sections=[])
        rows[key]["retained_bytes"]+=size
        if current not in rows[key]["output_sections"]:rows[key]["output_sections"].append(current)
    if not layout or seen!=set(allocations) or not rows:raise NoticeError("incomplete_allocated_linkmap")
    return [rows[k] for k in sorted(rows,key=lambda x:(x[0],x[1] or ""))]

def descriptor(binary,elf):
    if len(binary)<288 or binary[0]!=0xe9:raise NoticeError("invalid_esp_app_image")
    data=binary[32:288]
    if struct.unpack_from("<I",data)[0]!=0xabcd5432:raise NoticeError("missing_app_descriptor")
    if data[144:176]!=hashlib.sha256(elf).digest():raise NoticeError("rawimage_elf_digest_conflict")
    string=lambda x:x.split(b"\0",1)[0].decode("ascii")
    return dict(version=string(data[16:48]),project=string(data[48:80]),idf=string(data[112:144]),elf_sha256=data[144:176].hex())

def classify(row,policy):
    path=row["path"];archive=row["archive"]
    if archive:
        name=archive[3:-2]
        if path.startswith(".pio/build/") and name in policy["external_libraries"]:
            return dict(kind="external_runtime",component=policy["external_libraries"][name]["component"],archive=archive)
        if path.startswith(".pio/build/") and name in policy["arduino_archives"]:
            return dict(kind="arduino_runtime",component="arduino-sdk",archive=archive)
        if path.startswith("packages/framework-arduinoespressif32/tools/sdk/"):
            return dict(kind="prebuilt_sdk_runtime_unqualified",component="arduino-sdk",archive=archive)
        if path.startswith("packages/toolchain-"):
            return dict(kind="toolchain_runtime_unqualified",component="xtensa-runtime",archive=archive)
    elif path.startswith(".pio/build/"):
        if "/src/" in path:return dict(kind="project_runtime",component="project-MIT")
        if path.endswith("github-ca-bundle.bin.txt.o"):return dict(kind="embedded_ca_bundle_unqualified",component="public-CA-data")
        if path.endswith(".txt.o"):return dict(kind="embedded_asset",component="web-assets")
    elif path.startswith("packages/toolchain-"):
        return dict(kind="toolchain_direct_object_unqualified",component="xtensa-runtime")
    return dict(kind="unknown_runtime_input",component="UNKNOWN")

def ha_inventory(root,policy):
    files=policy["source_files"];imports={}
    component_root=inside(root,policy["manifest"]).parent
    actual={p.relative_to(root).as_posix() for p in component_root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts and p.suffix not in (".pyc",".pyo")}
    if set(files)!=actual:raise NoticeError("ha_source_inventory_incomplete")
    for path,sha in files.items():
        data=inside(root,path).read_bytes()
        if digest(data)!=sha:raise NoticeError("ha_source_identity_conflict:"+path)
        if not path.endswith(".py"):continue
        for item in ast.walk(ast.parse(data)):
            names=[]
            if isinstance(item,ast.Import):names=[a.name for a in item.names]
            elif isinstance(item,ast.ImportFrom) and item.level==0 and item.module:names=[item.module]
            for name in names:imports.setdefault(name.split(".")[0],set()).add(path)
    manifest=json.loads(inside(root,policy["manifest"]).read_text())
    platform=set(policy["platform_imports"])&{"homeassistant","voluptuous"}
    native_evidence=None
    if "probatio" in policy["platform_imports"]:
        ref=policy.get("native_platform_evidence")
        if type(ref) is not dict:raise NoticeError("native_platform_evidence_missing")
        path=inside(root,ref["path"])
        if filehash(path)!=ref["sha256"]:raise NoticeError("native_platform_evidence_conflict")
        native_evidence=json.loads(path.read_text())
        ha=native_evidence["homeassistant"];validator=native_evidence["probatio"]
        if (ha["metadata"]["Version"]!=["2026.10.2"] or "probatio==0.13.0" not in ha["requires"]
                or validator["metadata"]["Version"]!=["0.13.0"]
                or validator["metadata"]["License-Expression"]!=["MIT"]
                or not validator["record_license_hash_verified"]):
            raise NoticeError("unqualified_native_validator")
        if filehash(inside(root,validator["original_license_path"]))!=validator["original_license_sha256"]:
            raise NoticeError("native_validator_original_license_conflict")
        platform.add("probatio")
    unknown=sorted(set(imports)-sys.stdlib_module_names-platform)
    return dict(source_candidate=policy["source_candidate"],source_files=files,manifest=manifest,
                platform_provided_imports=sorted(set(imports)&platform),
                native_platform_evidence=native_evidence,
                unqualified_external_imports={k:sorted(imports[k]) for k in unknown},
                separately_declared_requirements=manifest.get("requirements",[]),
                installed_production_versions="UNKNOWN_NOT_INFERRED_FROM_PINNED_TEST_HA",
                package_scope="Native packaging source subtree only; no current release/deployment claim")

def verify_web(root,binary,web,source):
    if web["source"]!=source:raise NoticeError("embedded_web_source_conflict")
    agg=hashlib.sha256()
    for name,sha in sorted(web["assets"].items()):
        data=inside(root,"data/html/"+name).read_bytes()
        if digest(data)!=sha or data not in binary:raise NoticeError("embedded_asset_identity_conflict:"+name)
        agg.update(name.encode()+b"\0");agg.update(bytes.fromhex(sha))
    if agg.hexdigest()!=web["web_sha256"]:raise NoticeError("embedded_web_digest_conflict")
    marker=f"OT_E32V2_OTA_V1:{web['version']}:{web['source']}:{web['web_sha256']}:END".encode()
    if marker not in binary:raise NoticeError("missing_actual_e32_source_web_marker")

def verify_saved_receipts(receipts,policy):
    required={f"build-evidence/{env}/firmware.{suffix}" for env in ("e32v2","esp32s3") for suffix in ("bin","elf","map")}
    required.update(("build-evidence/e32v2/embedded-web.json","build-evidence/e32v2/spiffs.bin"))
    if not required<=set(policy["artifacts"]):raise NoticeError("required_build_receipt_omitted")
    if not {"E32-BUILD.log","esp32s3-BUILD.log"}<=set(policy["build_logs"]):raise NoticeError("required_build_log_omitted")
    saved=json.loads((receipts/"PRESERVED-BUILD-ARTIFACTS.json").read_text())
    if saved["source"]!=policy["receipt_source"] or saved["artifacts"]!=policy["artifacts"]:
        raise NoticeError("saved_build_receipt_identity_conflict")
    artifact_hashes={}
    for name,identity in policy["artifacts"].items():
        path=inside(receipts,name)
        if path.stat().st_size!=identity["bytes"] or filehash(path)!=identity["sha256"]:
            raise NoticeError("actual_build_artifact_conflict:"+name)
        artifact_hashes[name]=identity
    for name,sha in policy["build_logs"].items():
        if filehash(inside(receipts,name))!=sha:raise NoticeError("actual_build_log_conflict")
    return saved,artifact_hashes


def linked_sdk_inventory(root, policy, boards, core=None):
    """Join retained SDK inputs to reviewed installed bytes, NOT corresponding source.
    A current cache/file hash cannot attest the archive used by an older linker.
    Schema1 intentionally cannot encode a VERIFIED source/build/license claim.
    """
    ref=policy.get("linked_sdk_evidence")
    if type(ref) is not dict or set(ref)!={"path","sha256"}:
        raise NoticeError("linked_sdk_evidence_missing")
    ledger_path=inside(root,ref["path"])
    if filehash(ledger_path)!=ref["sha256"]:raise NoticeError("linked_sdk_ledger_conflict")
    ledger=json.loads(ledger_path.read_text())
    def keys(value, expected):
        if type(value) is not dict or set(value)!=set(expected):
            raise NoticeError("unsupported_linked_sdk_evidence")
    def hash_value(value):
        if type(value) is not str or re.fullmatch("[0-9a-f]{64}",value) is None:
            raise NoticeError("invalid_linked_sdk_identity")
    def identity(value):
        keys(value,("sha256","bytes"));hash_value(value["sha256"])
        if type(value["bytes"]) is not int or value["bytes"]<=0:
            raise NoticeError("invalid_linked_sdk_identity")
    keys(ledger,("schema","scope","receipt_source","inventory","package_metadata","boards"))
    if type(ledger["schema"]) is not int or ledger["schema"]!=1:
        raise NoticeError("unsupported_linked_sdk_schema")
    if ledger["receipt_source"]!=policy["receipt_source"]:
        raise NoticeError("linked_sdk_source_conflict")
    keys(ledger["inventory"],("inventory_sha256","file_sha256","framework_tree_sha256"))
    for value in ledger["inventory"].values():hash_value(value)
    keys(ledger["package_metadata"],("package.json",".piopm"))
    provenance=json.loads((root/"docs/third-party/provenance.json").read_text())
    framework=Path(core)/"packages/framework-arduinoespressif32" if core is not None else None
    checked=set()
    def check_current(relative, spec):
        # Both validation branches reject path escape, including local symlinks.
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise NoticeError("unsafe_relative_path")
        identity(spec)
        if framework is not None and relative not in checked:
            f=inside(framework,relative)
            if not f.is_file() or f.stat().st_size!=spec["bytes"] or filehash(f)!=spec["sha256"]:
                raise NoticeError("current_sdk_file_conflict:"+relative)
            checked.add(relative)
    for name,spec in ledger["package_metadata"].items():
        identity(spec)
        if spec["sha256"]!=provenance["framework"]["pins"].get(name):
            raise NoticeError("linked_sdk_metadata_pin_conflict:"+name)
        check_current(name,spec)
    keys(ledger["boards"],("e32v2","esp32s3"))
    by_env={b["environment"]:b for b in boards}
    if set(by_env)!=set(ledger["boards"]) or len(boards)!=len(by_env):
        raise NoticeError("linked_sdk_board_set_conflict")
    output=[]
    for env,b in sorted(by_env.items()):
        row=ledger["boards"][env]
        keys(row,("sdk_target","descriptor_idf","map_sha256","elf_sha256","cached_sdkconfig","archives"))
        target={"e32v2":"esp32","esp32s3":"esp32s3"}[env]
        if row["sdk_target"]!=target or row["descriptor_idf"]!=b["descriptor"]["idf"]:
            raise NoticeError("linked_sdk_target_descriptor_conflict")
        for suffix in ("map","elf"):
            key=suffix+"_sha256";hash_value(row[key])
            if row[key]!=policy["artifacts"][f"build-evidence/{env}/firmware.{suffix}"]["sha256"]:
                raise NoticeError("linked_sdk_receipt_conflict")
        cfg=row["cached_sdkconfig"];keys(cfg,("path","sha256","bytes"))
        if cfg["path"]!="tools/sdk/"+target+"/sdkconfig":
            raise NoticeError("linked_sdk_config_target_conflict")
        check_current(cfg["path"],{k:cfg[k] for k in ("sha256","bytes")})
        retained={}
        for item in b["retained_inputs"]:
            if item["classification"]["kind"]!="prebuilt_sdk_runtime_unqualified":continue
            prefix="packages/framework-arduinoespressif32/tools/sdk/"+target+"/"
            path=item["path"]
            if not path.startswith(prefix) or Path(path).name!=item["archive"]:
                raise NoticeError("linked_sdk_retained_path_conflict")
            if path not in retained:retained[path]=set()
            retained[path].add(item["member"])
        if type(row["archives"]) is not list or not row["archives"]:
            raise NoticeError("linked_sdk_archive_set_conflict")
        archives={}
        for item in row["archives"]:
            keys(item,("path","sha256","bytes"))
            path=item["path"]
            if type(path) is not str or path in archives or path not in retained:
                raise NoticeError("linked_sdk_archive_set_conflict")
            spec={k:item[k] for k in ("sha256","bytes")};identity(spec)
            relative=path.removeprefix("packages/framework-arduinoespressif32/")
            check_current(relative,spec)
            # Never attach the E32 header evidence to an S3 binary as proof.
            headers=[dict(e) for e in policy["cached_sdk_component_evidence"]
                     if env=="e32v2" and e["linked_archive"]==Path(path).name]
            archives[path]=dict(path=path,installed_archive=spec,
                retained_members=sorted(retained[path]),
                source_commit=None,matching_binary_build_recipe=None,
                build_time_archive_digest=None,applicable_binary_notices=None,
                header_only_references_not_binary_qualification=headers,
                status="BLOCKED",
                missing=["build_time_archive_attestation","matching_dirty_binary_source",
                         "matching_component_build_recipe","applicable_original_component_notices"])
        if set(archives)!=set(retained):raise NoticeError("linked_sdk_archive_set_conflict")
        output.append(dict(environment=env,sdk_target=target,descriptor_idf=row["descriptor_idf"],
            receipt_source=ledger["receipt_source"],elf_sha256=row["elf_sha256"],map_sha256=row["map_sha256"],
            cached_target_sdkconfig=cfg,archives=[archives[k] for k in sorted(archives)]))
    return dict(schema=1,status="BLOCKED",ledger_sha256=ref["sha256"],
        source_offer_state="BLOCKED",
        installed_bytes_check="EXACT_CURRENT_CACHE_MATCH" if framework is not None else "NOT_CHECKED_CORE_NOT_SUPPLIED",
        current_files_checked=len(checked),
        inventory_reference=ledger["inventory"],
        inventory_scope="Reference to frozen inventory, not a repeated whole-cache inventory or linker-time receipt.",
        config_scope="Exact cached target sdkconfig only; NOT a proven recipe for the dirty linked archives.",
        package_metadata=ledger["package_metadata"],boards=output,
        blocked=["sdk_build_time_archive_attestation_missing",
                 "sdk_linked_component_source_recipe_notice_closure_unverified"])

def collect_shipped(root,receipts,core=None):
    root=Path(root);receipts=Path(receipts)
    policy=json.loads((root/"docs/third-party/shipped-policy.json").read_text())
    if policy.get("schema")!=1:raise NoticeError("unsupported_shipped_policy")
    original=json.loads((root/"docs/third-party/provenance.json").read_text())
    saved,artifact_hashes=verify_saved_receipts(receipts,policy)
    for notice in policy["original_runtime_notices"]+original["original_upstream_notices"]:
        if filehash(inside(root,notice["path"]))!=notice["sha256"]:raise NoticeError("original_runtime_notice_conflict")
    for component in policy["cached_sdk_component_evidence"]:
        if filehash(inside(root,component["excerpt_path"]))!=component["excerpt_sha256"]:
            raise NoticeError("sdk_header_notice_excerpt_conflict")
    boards=[];blocked=set(policy["blocked"])
    for env,log in (("e32v2","E32-BUILD.log"),("esp32s3","esp32s3-BUILD.log")):
        base=receipts/"build-evidence"/env
        elf=(base/"firmware.elf").read_bytes();binary=(base/"firmware.bin").read_bytes()
        app=descriptor(binary,elf);alloc=elf_allocations(elf)
        rows=map_inputs((base/"firmware.map").read_text(),alloc)
        archives={}
        for row in rows:
            rule=classify(row,policy);row["classification"]=rule
            if rule["kind"]=="unknown_runtime_input":blocked.add("unknown_retained_input:"+row["path"])
            if row["archive"]:
                key=row["archive"]
                if key in archives and archives[key]["classification"]!=rule:raise NoticeError("ambiguous_runtime_archive")
                if key not in archives:archives[key]=dict(classification=rule,members=0,retained_bytes=0)
                archives[key]["members"]+=1;archives[key]["retained_bytes"]+=row["retained_bytes"]
        build_text=(receipts/log).read_text()
        packages=dict(re.findall(r"^ - (\S+) @ (\S+)",build_text,re.MULTILINE))
        expected_toolchain="toolchain-xtensa-esp32"+("s3" if env=="esp32s3" else "")
        if packages.get(expected_toolchain)!=policy["toolchain"]["version"]:
            raise NoticeError("toolchain_build_version_conflict")
        scanned=dict(re.findall(r"^\|-- (.+?) @ (\S+)\s*$",build_text,re.MULTILINE))
        for name,spec in policy["external_libraries"].items():
            if scanned.get(name)!=spec["version"]:raise NoticeError("build_dependency_version_conflict:"+name)
            if spec.get("license") in (None,"","UNKNOWN") or not spec.get("origin"):
                blocked.add("external_component_metadata_missing:"+name)
        for key in archives:
            if key[3:-2] in policy["external_libraries"]:
                component=policy["external_libraries"][key[3:-2]]["component"]
                if not any(n["component"]==component for n in policy["original_runtime_notices"]):blocked.add("runtime_notice_missing:"+component)
        if policy["sdk"]["version"] not in build_text:raise NoticeError("framework_build_version_conflict")
        if app["idf"]!=policy["sdk"]["binary_idf"]:raise NoticeError("sdk_descriptor_identity_conflict")
        web=None
        if env=="e32v2":
            web=json.loads((base/"embedded-web.json").read_text())
            verify_web(root,binary,web,saved["source"])
        else:blocked.add("s3_filesystem_distribution_not_receipted")
        boards.append(dict(environment=env,source=saved["source"],descriptor=app,
            retained_archives=archives,retained_inputs=rows,allocated_sections=alloc,
            dependency_scan_not_retention_proof=scanned,build_packages_not_retention_proof=packages,embedded_web=web,
            retained_bytes_scope="ALLOC input contribution incl RAM/NOBITS, NOT compressed image/flash attribution"))
    sdk_links=linked_sdk_inventory(root,policy,boards,core)
    blocked.update(sdk_links["blocked"])
    ha=ha_inventory(root,policy["ha"])
    blocked.update("unqualified_ha_import:"+name for name in ha["unqualified_external_imports"])
    for key in ("pem","binary"):
        if filehash(inside(root,policy["ca"][key]))!=policy["ca"][key+"_sha256"]:raise NoticeError("ca_identity_conflict")
    return dict(schema=1,status="BLOCKED" if blocked else "REVIEW_REQUIRED_NOT_PUBLICATION",
        state=policy["state"],receipt_source=saved["source"],build_artifacts=artifact_hashes,
        boards=boards,ha=ha,linked_sdk=sdk_links,web_catalog=original["assets"],
        runtime_original_notices=policy["original_runtime_notices"],upstream_originals=original["original_upstream_notices"],
        external_libraries=policy["external_libraries"],ca=policy["ca"],
        cached_sdk_component_evidence=policy["cached_sdk_component_evidence"],
        provider_versions=dict(sdk=policy["sdk"],toolchain=policy["toolchain"]),
        host_only_not_firmware_archives=policy["host_only"],f9=policy["f9"],blocked=sorted(blocked),
        runtime_actions=[],source_offer_state="BLOCKED matching SDK/components and relink/source materials incomplete")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--core",type=Path,help="Check only retained SDK archives/metadata against current installed bytes; never source closure")
    parser.add_argument("--allow-blocked-report",action="store_true",help="Evidence only, never publication approval")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    report=collect_shipped(root,args.receipts,args.core)
    if args.output.exists():raise NoticeError("report_output_must_not_exist")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(dict(status=report["status"],source=report["receipt_source"],
        retained_archives={b["environment"]:len(b["retained_archives"]) for b in report["boards"]},
        blocked=report["blocked"]),indent=2))
    if report["blocked"] and not args.allow_blocked_report:raise NoticeError("shipped_notice_closure_BLOCKED")
