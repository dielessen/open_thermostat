"""Preserve and independently bind exact E32 panic symbols to the OTA image.

This never executes an ELF or creates a firmware/flash operation. The existing
full release verifier remains mandatory and unchanged.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import stat
from organize_releases import classify

FILES={'firmware.elf':128*1024*1024,'firmware.map':64*1024*1024,'embedded-web.json':1024*1024}


def require(value,reason):
    if not value:raise ValueError(reason)


def read_file(path,maximum):
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode),'symbol_input_not_regular')
        require(0<before.st_size<=maximum,'symbol_input_size')
        raw=stream.read(maximum+1);after=os.fstat(stream.fileno())
        require((before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns),'symbol_input_changed')
    require(len(raw)==before.st_size,'symbol_input_read_incomplete')
    return raw


def digest(raw):return hashlib.sha256(raw).hexdigest()


def bound_report(manifest,image,files):
    require(type(manifest) is dict,'invalid_symbol_manifest')
    for name,length in [('source_commit',40),('web_sha256',64),('sha256',64)]:
        require(type(manifest.get(name)) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',manifest[name]),'invalid_symbol_identity')
    require(type(manifest.get('version')) is str and classify(manifest['version'])[0]=='firmware','invalid_symbol_version')
    require(type(manifest.get('size')) is int and 1024<=manifest['size']<=3670016,'invalid_symbol_image_size')
    require(len(image)==manifest['size'] and digest(image)==manifest['sha256'],'symbol_firmware_conflict')
    require(image[0]==0xe9,'symbol_image_not_ESP')
    elf=files['firmware.elf'];require(elf[:6]==b'\x7fELF\x01\x01','symbol_elf_not_32bit_little_endian')
    require(hashlib.sha256(elf).digest()==image[0xb0:0xd0],'symbol_elf_descriptor_conflict')
    meta=json.loads(files['embedded-web.json'])
    require(meta.get('source')==manifest['source_commit'] and meta.get('version')==manifest['version']
        and meta.get('web_sha256')==manifest['web_sha256'],'symbol_web_identity_conflict')
    marker=f"OT_E32V2_OTA_V1:{manifest['version']}:{manifest['source_commit']}:{manifest['web_sha256']}:END".encode()
    require(marker in image,'symbol_image_marker_conflict')
    require(b'Linker script and memory map' in files['firmware.map'],'symbol_link_map_invalid')
    return dict(schema=1,status='PASS_EXACT_BUILD_SYMBOLS_ONLY',version=manifest['version'],
        source_commit=manifest['source_commit'],web_sha256=manifest['web_sha256'],
        firmware_sha256=manifest['sha256'],elf_sha256=digest(elf),
        files={name:dict(sha256=digest(raw),bytes=len(raw)) for name,raw in files.items()},
        executable_for_installation=False,physical_acceptance=False)


def verify(package):
    package=Path(package);directory=package/'symbols'
    require(directory.is_dir() and not directory.is_symlink(),'symbol_directory_invalid')
    require({p.name for p in directory.iterdir()}==set(FILES)|{'SYMBOLS.json'},'symbol_file_inventory_conflict')
    manifest=json.loads(read_file(package/'e32v2-update.json',4096))
    image=read_file(package/'firmware.bin',3670016)
    files={name:read_file(directory/name,maximum) for name,maximum in FILES.items()}
    actual=bound_report(manifest,image,files)
    require(json.loads(read_file(directory/'SYMBOLS.json',16384))==actual,'symbol_report_conflict')
    return actual


def export(build,package):
    build=Path(build);package=Path(package);directory=package/'symbols'
    require(not directory.exists() and not directory.is_symlink(),'symbol_output_already_exists')
    manifest=json.loads(read_file(package/'e32v2-update.json',4096))
    image=read_file(package/'firmware.bin',3670016)
    require(read_file(build/'firmware.bin',3670016)==image,'symbol_build_image_conflict')
    files={name:read_file(build/name,maximum) for name,maximum in FILES.items()}
    report=bound_report(manifest,image,files) # All preflight checks before output.
    directory.mkdir()
    for name,raw in files.items():(directory/name).write_bytes(raw)
    (directory/'SYMBOLS.json').write_text(json.dumps(report,indent=2)+'\n')
    require(verify(package)==report,'symbol_copy_readback_conflict')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(verify(args.package),indent=2))
