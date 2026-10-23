"""Finite actual SDK source compile samples; failures/differences retained, never installed."""
from pathlib import Path
import concurrent.futures,hashlib,json,shlex,subprocess,re,os
from functools import lru_cache

out=Path(__file__).resolve().parent
core=Path(os.environ.get('PLATFORMIO_CORE_DIR',str(Path.home()/'.platformio'))).resolve()
prefix=str(core/'packages/toolchain-xtensa-esp32/bin/xtensa-esp32-elf-')
rows=json.loads((out/'ARCHIVE-SOURCE-DECLARATIONS.json').read_text())['rows']
includes=json.loads((out/'COMPILE-INCLUDES.json').read_text())
# Stored includes refer to the installation that produced the evidence. Relocate
# only the PlatformIO-root prefix; repository inputs remain separately bound.
includes=[str(core/('packages/'+p.split('/packages/',1)[1])) if '/packages/' in p else p for p in includes]
sources=out/'sources'
submodules=json.loads((out/'SUBMODULE-TREE-RECEIPTS.json').read_text())

@lru_cache(maxsize=64)
def archive_objects(path):
    data=(core/path).read_bytes()
    table=subprocess.check_output([prefix+'ar','tO',str(core/path)],text=True)
    objects={}
    for line in table.splitlines():
        match=re.fullmatch(r'(\S+) 0x([0-9a-f]+)',line);assert match
        name,offset=match[1],int(match[2],16)
        assert data[offset-2:offset]==b'`\n'
        size=int(data[offset-12:offset-2]);body=data[offset:offset+size]
        assert body.startswith(b'\x7fELF')
        objects.setdefault(name,[]).append(body)
    return objects

def original_object(row,unit):
    candidates=archive_objects(row['path'])[unit['member']]
    if len(candidates)==1:return candidates[0]
    # GNU ar can contain two same-named efuse objects from different directories.
    # Never let `ar p` silently compare only the first occurrence.
    candidates=[body for body in candidates if unit['name'].encode()+b'\0' in body]
    if len(candidates)!=1:raise ValueError('ambiguous_original_member')
    return candidates[0]

def resolve(name):
    marker='/esp-idf/'
    if marker in name:
        relative=name.split(marker,1)[1]
        for row in sorted(submodules,key=lambda r:-len(r['path'])):
            if relative.startswith(row['path']+'/'):
                path=sources/row['repository'].split('/')[-1]/relative[len(row['path'])+1:]
                return path if path.is_file() else None
        path=sources/'esp-idf'/relative
        return path if path.is_file() else None
    marker='/components/esp-rainmaker/components/esp-insights/'
    if marker in name:
        path=sources/'esp-insights'/name.split(marker,1)[1]
        return path if path.is_file() else None
    return None

def build_sample(row, *, unit=None, group='recompile-samples'):
    units=[unit] if unit is not None else [u for u in row['compilation_units'] if u.get('name','').endswith(('.c','.cpp','.cc')) and resolve(u['name'])]
    if not units:return dict(archive=Path(row['path']).name,status='NO_SOURCE_SAMPLE')
    unit=unit or units[0];source=resolve(unit['name']);dest=out/group/Path(row['path']).name
    if group!='recompile-samples':dest=dest/(unit['member']+'-'+hashlib.sha256(unit['name'].encode()).hexdigest()[:8])
    dest.mkdir(parents=True,exist_ok=True)
    flags=(['-mlongcalls','-mfix-esp32-psram-cache-issue','-ggdb','-x','assembler-with-cpp']
           if source.suffix=='.S' else shlex.split(unit['producer'].split('8.4.0 ',1)[1]))
    compiler=prefix+('gcc' if source.suffix in ('.c','.S') else 'g++')
    command=[compiler,*flags,'-DESP_PLATFORM','-D_GNU_SOURCE','-D_POSIX_READER_WRITER_LOCKS','-DIDF_VER="v4.4.7-dirty"',
             '-DMBEDTLS_CONFIG_FILE="mbedtls/esp_config.h"']
    # IDF's original macro prefix map is visible in actual assertion strings.
    command.extend(['-fmacro-prefix-map='+str(sources/'esp-idf')+'=IDF',
                    '-fmacro-prefix-map='+str(core/'packages/framework-arduinoespressif32/tools/sdk/esp32/include')+'=IDF/components'])
    for binding in submodules:
        source_root=sources/binding['repository'].split('/')[-1]
        if source_root.is_dir():command.append('-fmacro-prefix-map='+str(source_root)+'=IDF/'+binding['path'])
    # Generic prebuilt SDK assembly uses the original QIO configuration. The
    # application's DIO header differs only in two PSRAM/cache delay constants.
    # This is a reproduction input; no project or installed configuration changes.
    actual_includes=([str(core/'packages/framework-arduinoespressif32/tools/sdk/esp32/qio_qspi/include')]+includes
                     if source.suffix=='.S' else includes)
    for inc in actual_includes:command.extend(['-I',inc])
    # The same upstream source's local private includes may not be exported into
    # the public cached SDK. Add only its own component's original directories.
    rel=source.relative_to(sources/'esp-idf') if source.is_relative_to(sources/'esp-idf') else None
    if rel and rel.parts[0]=='components':
        component=sources/'esp-idf'/'components'/rel.parts[1]
        for inc in ('include','private_include','priv_include','esp32/private_include','include/driver','include/spi_flash',
                    'include_bootloader','include_core_dump','include_core_dump/port/xtensa','port/include','port/include/freertos',
                    'port/esp32','esp32','port/xtensa/include','port/xtensa/include/freertos','port/priv_include',
                    'include/freertos','esp_additions/private_include','src','src/utils','esp_supplicant/src'):
            if (component/inc).is_dir():command.extend(['-I',str(component/inc)])
        if component.name=='heap':command.append('-DMULTI_HEAP_FREERTOS')
        if component.name=='spiffs':command.extend(['-I',str(sources/'spiffs/src')])
        if component.name=='wpa_supplicant':
            command.extend('-D'+name for name in ('__ets__ ESP_SUPPLICANT IEEE8021X_EAPOL EAP_PEER_METHOD EAP_MSCHAPv2 EAP_TTLS EAP_TLS EAP_PEAP EAP_FAST USE_WPA2_TASK CONFIG_WPS2 CONFIG_WPS_PIN USE_WPS_TASK ESPRESSIF_USE ESP32_WORKAROUND CONFIG_ECC CONFIG_IEEE80211W CONFIG_SHA256 CONFIG_WNM CONFIG_FAST_PBKDF2').split())
            config=(core/'packages/framework-arduinoespressif32/tools/sdk/esp32/sdkconfig').read_text()
            for key,name in (('CONFIG_ESP32_WIFI_ENABLE_WPA3_SAE','CONFIG_WPA3_SAE'),('CONFIG_WPA_WPS_STRICT','CONFIG_WPS_STRICT'),
                             ('CONFIG_WPA_SUITE_B_192','CONFIG_SUITEB192'),('CONFIG_WPA_SUITE_B','CONFIG_SUITEB'),
                             ('CONFIG_ESP_WIFI_GCMP_SUPPORT','CONFIG_GCMP'),('CONFIG_ESP_WIFI_GMAC_SUPPORT','CONFIG_GMAC'),
                             ('CONFIG_WPA_MBO_SUPPORT','CONFIG_MBO'),('CONFIG_WPA_DPP_SUPPORT','CONFIG_DPP')):
                if key+'=y' in config.splitlines():command.append('-D'+name)
        if component.name=='app_update' and source.name=='esp_app_desc.c':
            # Reproduce ORIGINAL SDK metadata inputs, not a new image timestamp.
            descriptor=json.loads((out/'SDK-BUILDER-DESCRIPTOR.json').read_text())
            for macro,key in (('PROJECT_VER','version'),('PROJECT_NAME','project'),('__DATE__','build_date'),('__TIME__','build_time')):
                command.append('-D'+macro+'='+json.dumps(descriptor[key]))
    command.extend(['-c',str(source),'-o',str(dest/'rebuilt.o')])
    result=subprocess.run(command,capture_output=True,text=True,timeout=45)
    (dest/'COMPILE.log').write_text(result.stdout+result.stderr);(dest/'COMMAND.json').write_text(json.dumps(command,indent=2)+'\n')
    report=dict(archive=Path(row['path']).name,member=unit['member'],evidence=str(dest.relative_to(out)),source=str(source.relative_to(out)),
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),compile_exit=result.returncode)
    if result.returncode:
        report.update(status='COMPILE_FAILED',diagnostic='\n'.join(result.stderr.splitlines()[:8]));return report
    original=original_object(row,unit);(dest/'original.o').write_bytes(original)
    report['original_object_sha256']=hashlib.sha256(original).hexdigest()
    for label in ('original','rebuilt'):
        subprocess.run([prefix+'objcopy','--strip-debug','--remove-section=.comment',str(dest/(label+'.o')),str(dest/(label+'.stripped.o'))],check=True,capture_output=True)
    same=(dest/'original.stripped.o').read_bytes()==(dest/'rebuilt.stripped.o').read_bytes()
    report['status']='EXACT_STRIPPED_OBJECT' if same else 'OBJECT_DIFFERS'
    report['whole_archive_qualified']=False
    return report

if __name__=='__main__':
    results=[r for r in json.loads((out/'RECOMPILE-SAMPLES-REVIEWED-RECIPE.json').read_text()) if r['status'] in ('EXACT_STRIPPED_OBJECT','NO_SOURCE_SAMPLE')]
    skip={r['archive'] for r in results}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(build_sample,row):row for row in rows if Path(row['path']).name not in skip}
        for future in concurrent.futures.as_completed(futures):
            try:r=future.result()
            except Exception as error:r=dict(archive=Path(futures[future]['path']).name,status='ERROR',error=type(error).__name__,detail=str(error))
            results.append(r)
            (out/'RECOMPILE-SAMPLES.json').write_text(json.dumps(sorted(results,key=lambda r:r['archive']),indent=2)+'\n')
            print(r['archive'],r['status'],flush=True)
