"""Offline, deterministic installed-dependency/notice inventory. Never downloads.

Scope is the supplied PlatformIO installation and selected cached environment,
NOT proof that every transitive binary component has a complete license/source
mapping. Known unresolved closure explicitly blocks release packaging.
"""
from pathlib import Path
import argparse,gzip,hashlib,json,os,shutil,sys

class NoticeError(ValueError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def filehash(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)

def _is_notice(name):
    n=name.upper()
    return n.startswith(("LICENSE","LICENCE","COPYING","COPYRIGHT","NOTICE"))

def inside(base, relative):
    relative=Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise NoticeError("unsafe_relative_path")
    try:
        resolved=(base/relative).resolve()
        resolved.relative_to(base.resolve())
    except (ValueError,RuntimeError):
        raise NoticeError("external_or_cyclic_path")
    return resolved

def component(path,label):
    result=dict(component=label,resolved={},metadata_sha256={},files=[],notices=[],blocked=[])
    if not path.is_dir():
        result["blocked"].append("installed_component_missing")
        return result
    for name in ("package.json","platform.json","library.json",".piopm","library.properties"):
        f=path/name
        if not f.is_file():
            continue
        try:
            inside(path,name)
        except NoticeError:
            result["blocked"].append("unsafe_metadata_path:"+name)
            continue
        result["metadata_sha256"][name]=filehash(f)
        if name.endswith(".json") or name==".piopm":
            data=json.loads(f.read_text())
            result["resolved"][name]={k:data[k] for k in ("name","version","license") if k in data}
        else:
            properties=dict(line.split("=",1) for line in f.read_text().splitlines() if "=" in line and not line.startswith("#"))
            result["resolved"][name]={k:properties[k] for k in ("name","version","license") if k in properties}
    for f in sorted(path.rglob("*")):
        relative=f.relative_to(path).as_posix()
        if any(n in (".git","__pycache__") for n in f.relative_to(path).parts) or f.suffix in (".pyc",".pyo"):
            continue
        link={}
        if f.is_symlink():
            try:
                target=inside(path,relative)
                if not target.is_file():
                    raise NoticeError("nonfile_or_missing_target")
                link=dict(symlink_target=os.readlink(f),
                          resolved_path=target.relative_to(path.resolve()).as_posix())
            except NoticeError:
                result["blocked"].append("unresolved_symlink:"+relative)
                continue
        if not f.is_file():
            continue
        row=dict(path=relative,size=f.stat().st_size,sha256=filehash(f),**link)
        result["files"].append(row)
        if _is_notice(f.name):
            result["notices"].append(dict(row))
    result["tree_sha256"]=digest(canonical(result["files"]).encode())
    result["file_count"]=len(result["files"])
    result["total_bytes"]=sum(f["size"] for f in result["files"])
    # Complete discovery of the defined filename scope is NOT full legal closure.
    result["notice_discovery_complete"]=not result["blocked"]
    return result

def collect(root,core,environment="e32v2"):
    root=Path(root);core=Path(core)
    if not environment or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in environment):
        raise NoticeError("invalid_environment")
    proof=json.loads((root/"docs/third-party/provenance.json").read_text())
    if proof.get("schema")!=1:
        raise NoticeError("unsupported_provenance_schema")
    report=dict(schema=1,scope="Exact installed source/package inventory excluding .git and Python caches; selected environment only. No build/physical/legal-completeness assertion.",
        environment=environment,platformio_ini_sha256=filehash(root/"platformio.ini"),
        project_license_sha256=filehash(root/"LICENSE"),assets=[],original_upstream_notices=[],components=[],blocked=[])
    for expected in proof["assets"]:
        if not expected["path"].startswith("data/html/deps/"):
            raise NoticeError("unsafe_asset_path")
        f=inside(root,expected["path"]);raw=f.read_bytes()
        if digest(raw)!=expected["gzip_sha256"] or len(raw)!=expected["gzip_bytes"]:
            raise NoticeError("ui_asset_hash_conflict:"+expected["path"])
        try:
            body=gzip.decompress(raw)
        except (OSError,EOFError) as exc:
            raise NoticeError("invalid_ui_gzip:"+expected["path"]) from exc
        if digest(body)!=expected["body_sha256"] or len(body)!=expected["body_bytes"]:
            raise NoticeError("ui_asset_hash_conflict:"+expected["path"])
        upstream=body
        if expected["proof"]=="EXACT_AFTER_SOURCE_MAP_BASENAME_RENAME":
            local=expected["local_source_map"].encode()
            original=expected["upstream_source_map"].encode()
            if body.count(local)!=1 or not body.rstrip().endswith(local):
                raise NoticeError("asset_source_map_conflict")
            upstream=body.replace(local,original)
        elif expected["proof"]!="EXACT_DECOMPRESSED_BYTES":
            raise NoticeError("unsupported_asset_proof")
        if digest(upstream)!=expected["upstream_sha256"]:
            raise NoticeError("upstream_asset_hash_conflict")
        report["assets"].append(dict(expected))
    for n in proof["original_upstream_notices"]:
        path=Path(n["path"])
        if path.is_absolute() or ".." in path.parts:
            raise NoticeError("unsafe_notice_path")
        if not path.as_posix().startswith("docs/third-party/"):
            raise NoticeError("unsafe_notice_path")
        if filehash(inside(root,path))!=n["sha256"]:
            raise NoticeError("original_notice_hash_conflict:"+str(path))
        report["original_upstream_notices"].append(dict(n))
    framework=core/"packages/framework-arduinoespressif32"
    packages=[("arduino-sdk",framework),("platform-espressif32",core/"platforms/espressif32"),
              ("xtensa-toolchain",core/"packages/toolchain-xtensa-esp32")]
    libs=root/".pio/libdeps"/environment
    if not libs.is_dir():
        report["blocked"].append("selected_cached_libdeps_missing")
    else:
        packages.extend(("library-"+p.name,p) for p in sorted(libs.iterdir()) if p.is_dir() and p.name!=".git")
    roots={}
    for label,path in packages:
        c=component(path,label);roots[label]=path;report["components"].append(c)
        report["blocked"].extend(label+":"+reason for reason in c["blocked"])
    try:
        package=json.loads((framework/"package.json").read_text())
        resolved=json.loads((framework/".piopm").read_text())
        if package["version"]!=proof["framework"]["resolved_version"] or resolved["version"]!=package["version"]:
            raise NoticeError("framework_resolved_version_conflict")
        if ("framework-arduinoespressif32@"+package["version"]) not in (root/"platformio.ini").read_text():
            raise NoticeError("framework_declared_pin_conflict")
        for n,h in proof["framework"]["pins"].items():
            if filehash(inside(framework,n))!=h:
                raise NoticeError("framework_provenance_pin_conflict:"+n)
    except FileNotFoundError:
        report["blocked"].append("framework_package_or_pin_missing")
    report["framework_provenance"]=dict(proof["framework"])
    report["bundled_components"]=proof.get("bundled_components",[])
    if proof["framework"]["closure"]!="VERIFIED":
        report["blocked"].append("sdk_binary_notice_source_closure_unverified")
    report["blocked"]=sorted(set(report["blocked"]))
    report["status"]="BLOCKED" if report["blocked"] else "READY_FOR_NOTICES_PACKAGING_ONLY"
    report["inventory_sha256"]=digest(canonical(report).encode())
    return report,roots

def require_publishable(report):
    if report["status"]!="READY_FOR_NOTICES_PACKAGING_ONLY" or report["blocked"]:
        raise NoticeError("Release notice/provenance BLOCKED: "+",".join(report["blocked"]))

def export(report,roots,root,output):
    """Inventory/original text export, not a release or certification."""
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise NoticeError("notice_output_must_be_empty")
    output.mkdir(parents=True,exist_ok=True)
    for c in report["components"]:
        for n in c["notices"]:
            relative=Path(n["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise NoticeError("unsafe_discovered_notice_path")
            src=inside(roots[c["component"]],relative)
            dest=output/"installed"/c["component"]/relative
            if filehash(src)!=n["sha256"]:
                raise NoticeError("notice_changed_after_inventory")
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    for n in report["original_upstream_notices"]:
        dest=output/"originals"/Path(n["path"]).name
        src=inside(Path(root),n["path"])
        if filehash(src)!=n["sha256"]:
            raise NoticeError("original_notice_changed_after_inventory")
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    (output/"NOTICE-INVENTORY.json").write_text(json.dumps(report,indent=2)+"\n")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core",type=Path,default=Path(os.environ.get("PLATFORMIO_CORE_DIR",str(Path.home()/".platformio"))))
    parser.add_argument("--environment",default="e32v2")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--allow-blocked-inventory",action="store_true",help="Export evidence ONLY; cannot make a release publishable")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    report,roots=collect(root,args.core,args.environment)
    export(report,roots,root,args.output)
    print(json.dumps({k:report[k] for k in ("status","environment","inventory_sha256","blocked")},indent=2))
    if not args.allow_blocked_inventory:
        require_publishable(report)
