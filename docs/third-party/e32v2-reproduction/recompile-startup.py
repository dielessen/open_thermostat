"""Reproduce the three actually linked GCC startup objects, without installation."""
from pathlib import Path
import hashlib, json, os, subprocess

out = Path(__file__).resolve().parent
tool = Path(os.environ.get('PLATFORMIO_CORE_DIR', str(Path.home()/'.platformio'))).resolve()/'packages/toolchain-xtensa-esp32'
prefix = str(tool/'bin/xtensa-esp32-elf-')
# Original Makefile.in CRTSTUFF_CFLAGS, xtensa/t-elf longcalls, and producer
# CT_CC_GCC_ENABLE_TARGET_OPTSPACE=y supply these historical build inputs.
flags = ('-O2 -g0 -fno-rtti -finhibit-size-directive -fno-inline -fno-exceptions '
         '-fno-zero-initialized-in-bss -fno-toplevel-reorder -fno-tree-vectorize '
         '-fbuilding-libgcc -fno-stack-protector -mlongcalls -DIN_GCC -Os').split()
includes = [out/'sources/xtensa-overlays/xtensa_esp32/gcc/include',
            out/'runtime-config/libgcc', out/'sources/gcc/gcc',
            out/'sources/gcc/libgcc', out/'sources/gcc/include',
            tool/'lib/gcc/xtensa-esp32-elf/8.4.0/plugin/include']
results = []
for member in ('crti.o', 'crtbegin.o', 'crtend.o'):
    folder = out/'runtime-startup'/member; folder.mkdir(parents=True, exist_ok=True)
    source = out/'sources/gcc/libgcc'/('config/xtensa/crti.S' if member == 'crti.o' else 'crtstuff.c')
    command = [prefix+'gcc', *flags]
    for inc in includes: command += ['-I', str(inc)]
    if member != 'crti.o': command += ['-DCRT_BEGIN' if member == 'crtbegin.o' else '-DCRT_END']
    command += ['-c', str(source), '-o', str(folder/'rebuilt.o')]
    (folder/'COMMAND.json').write_text(json.dumps(command, indent=2)+'\n')
    run = subprocess.run(command, capture_output=True, text=True, timeout=45)
    (folder/'COMPILE.log').write_text(run.stdout+run.stderr)
    record = dict(member=member, source=str(source.relative_to(out)),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  evidence=str(folder.relative_to(out)), compile_exit=run.returncode)
    if run.returncode:
        record['status'] = 'COMPILE_FAILED'
    else:
        original = tool/'lib/gcc/xtensa-esp32-elf/8.4.0/no-rtti'/member
        (folder/'original.o').write_bytes(original.read_bytes())
        record['original_object_sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
        for label in ('original', 'rebuilt'):
            subprocess.run([prefix+'objcopy', '--strip-debug', '--remove-section=.comment',
                            str(folder/(label+'.o')), str(folder/(label+'.stripped.o'))], check=True)
        record['status'] = ('EXACT_STRIPPED_OBJECT' if
                            (folder/'original.stripped.o').read_bytes() == (folder/'rebuilt.stripped.o').read_bytes()
                            else 'OBJECT_DIFFERS')
    results.append(record); print(member, record['status'])
(out/'RUNTIME-STARTUP-RECOMPILE.json').write_text(json.dumps(results, indent=2)+'\n')
if any(r['status'] != 'EXACT_STRIPPED_OBJECT' for r in results): raise SystemExit(1)
