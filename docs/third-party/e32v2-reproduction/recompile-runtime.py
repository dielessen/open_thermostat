"""Finite public-source/runtime comparisons; does not replace installed runtime files."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,importlib.util,json,re,shlex,subprocess

out=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sdk_recipe',out/'recompile-samples.py');recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
rows=json.loads((out/'TOOLCHAIN-RUNTIME-SOURCE-DECLARATIONS.json').read_text())['rows']
prefix=recipe.prefix

def source_for(unit):
    name=unit.get('name','')
    for component in ('newlib','gcc'):
        marker='/src/'+component+'/'
        if marker in name:
            source=out/'sources'/component/name.split(marker,1)[1]
            return source if source.is_file() else None
    # libstdc++'s immutable Makefile.am creates these configure-time source
    # aliases. newlib is selected in acinclude.m4 for this target.
    if '/' not in name and name.endswith('.cc'):
        base=out/'sources/gcc/libstdc++-v3'
        stem=name.removesuffix('_cow.cc')+'.cc' if name.endswith('_cow.cc') else name
        if name=='c++locale.cc':return base/'config/locale/generic/c_locale.cc'
        if name=='ctype_members.cc':return base/'config/locale/newlib/ctype_members.cc'
        if name=='ctype_configure_char.cc':return base/'config/os/newlib/ctype_configure_char.cc'
        path=base/'config/locale/generic'/stem
        if path.is_file():return path
    return None

def build(row,unit,group='runtime-recompile'):
    source=source_for(unit);name=Path(row['path']).name
    if name=='libgcc.a' and source and source.name.startswith('ieee754-'):source=source.with_name('lib1funcs.S')
    result=dict(archive=name,member=unit['member'],source=str(source.relative_to(out)) if source else None)
    if source is None:return {**result,'status':'SOURCE_MISSING'}
    folder=out/group/name/(unit['member']+'-'+hashlib.sha256(unit['name'].encode()).hexdigest()[:8]);folder.mkdir(parents=True,exist_ok=True)
    result['evidence']=str(folder.relative_to(out));result['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    assembler=source.suffix=='.S'
    flags=['-mlongcalls','-g','-x','assembler-with-cpp'] if assembler else shlex.split(unit['producer'].split('8.4.0 ',1)[1])
    compiler=prefix+('g++' if source.suffix in ('.cc','.cpp') else 'gcc')
    command=[compiler,*flags]
    if name=='libgcc.a':command+=['-I',str(out/'sources/xtensa-overlays/xtensa_esp32/gcc/include')]
    if '/newlib/' in unit['name']:
        command+=['-I',str(out/'runtime-config')]
        # Literal target flags from the pinned newlib/configure.host Xtensa case.
        command.extend('-D'+name for name in ('HAVE_FCNTL HAVE_BLKSIZE GETREENT_PROVIDED REENTRANT_SYSCALLS_PROVIDED SIGNAL_PROVIDED').split())
        original_root=unit['name'].split('/src/newlib/',1)[0]+'/src/newlib'
        command.append('-fmacro-prefix-map='+str(out/'sources/newlib')+'='+original_root)
        for inc in ('newlib/libc/include','newlib/libc/stdio','newlib/libm/common'):
            command+=['-I',str(out/'sources/newlib'/inc)]
        if unit['member'] in ('lib_a-svfprintf.o','lib_a-svfprintf_r.o'):command.append('-DSTRING_ONLY')
        if unit['member'] in ('lib_a-vfiprintf.o','lib_a-svfiprintf.o'):command.append('-DINTEGER_ONLY')
        if unit['member']=='lib_a-svfiprintf.o':command.append('-DSTRING_ONLY')
        if unit['member'] in ('lib_a-svfscanf.o','lib_a-svfiscanf.o','lib_a-svfwprintf.o'):command.append('-DSTRING_ONLY')
        if unit['member']=='lib_a-svfiscanf.o':command.append('-DINTEGER_ONLY')
    else:
        if unit['member'].endswith('_cow.o'):command.append('-D_GLIBCXX_USE_CXX11_ABI=0')
        for inc in ('libstdc++-v3/libsupc++','libstdc++-v3/src','libgcc','include'):
            command+=['-I',str(out/'sources/gcc'/inc)]
        if name=='libgcc.a':
            if unit['member'].startswith('_'):command.append('-DL'+Path(unit['member']).stem)
            for inc in (out/'sources/xtensa-overlays/xtensa_esp32/gcc/include',out/'runtime-config/libgcc',out/'sources/gcc/gcc',out/'sources/gcc/gcc/config',out/'sources/gcc/gcc/config/xtensa',recipe.core/'packages/toolchain-xtensa-esp32/lib/gcc/xtensa-esp32-elf/8.4.0/plugin/include'):
                command+=['-I',str(inc)]
            command+=['-DIN_GCC','-DIN_LIBGCC2']
    command+=['-c',str(source),'-o',str(folder/'rebuilt.o')]
    (folder/'COMMAND.json').write_text(json.dumps(command,indent=2)+'\n')
    run=subprocess.run(command,capture_output=True,text=True,timeout=45);(folder/'COMPILE.log').write_text(run.stdout+run.stderr)
    if run.returncode:return {**result,'status':'COMPILE_FAILED','compile_exit':run.returncode,'diagnostic':run.stderr[-1200:]}
    original=recipe.original_object(row,unit);(folder/'original.o').write_bytes(original);result['original_object_sha256']=hashlib.sha256(original).hexdigest()
    for label in ('original','rebuilt'):
        subprocess.run([prefix+'objcopy','--strip-debug','--remove-section=.comment',str(folder/(label+'.o')),str(folder/(label+'.stripped.o'))],check=True,capture_output=True)
    equal=(folder/'original.stripped.o').read_bytes()==(folder/'rebuilt.stripped.o').read_bytes()
    return {**result,'status':'EXACT_STRIPPED_OBJECT' if equal else 'OBJECT_DIFFERS'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--all',action='store_true',help='Recompile every unit without reusing successful records')
    parser.add_argument('--group',default='runtime-recompile')
    parser.add_argument('--report',default='RUNTIME-RECOMPILE.json')
    args=parser.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.group)
    assert re.fullmatch(r'[A-Za-z0-9_.-]+\.json',args.report)
    results=[] if args.all else [r for r in json.loads((out/'RUNTIME-RECOMPILE-260-BASELINE.json').read_text()) if r['status']=='EXACT_STRIPPED_OBJECT']
    done={(r['archive'],r['member']) for r in results}
    total=sum(len(r['compilation_units']) for r in rows)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(build,row,unit,args.group):(row,unit) for row in rows for unit in row['compilation_units'] if (Path(row['path']).name,unit['member']) not in done}
        for future in concurrent.futures.as_completed(futures):
            row,unit=futures[future]
            try:r=future.result()
            except Exception as error:r=dict(archive=Path(row['path']).name,member=unit['member'],status='ERROR',error=type(error).__name__,detail=str(error))
            results.append(r);(out/args.report).write_text(json.dumps(results,indent=2)+'\n')
            if len(results)%25==0 or len(results)==total:print(len(results),'/',total,flush=True)
    if len(results)!=total or any(r['status']!='EXACT_STRIPPED_OBJECT' for r in results):raise SystemExit(1)

if __name__=='__main__':main()
