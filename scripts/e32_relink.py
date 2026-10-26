"""Build an offline E32 application relink kit from actual captured build commands.

This module never approves firmware, changes a library installation or flashes a
device. Exact and deliberately modified-library relinks are mandatory evidence.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess


class RelinkError(ValueError):
    pass


def filehash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise RelinkError(message)


def inside(root, relative):
    relative = Path(relative)
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe_relink_path')
    result = (root / relative).resolve()
    require(result.is_relative_to(root.resolve()), 'external_relink_path')
    return result


def command_at(command, kit, core, output):
    values = {'@CORE@': str(core.resolve()), '@KIT@': str(kit.resolve()),
              '@OUTPUT_ELF@': str(output.resolve()),
              '@OUTPUT_MAP@': str(output.with_suffix('.map').resolve())}
    result = []
    for argument in command:
        for marker, value in values.items():
            argument = argument.replace(marker, value)
        result.append(argument)
    return result


def run(command, cwd, log):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180)
    log.write_text(result.stdout + result.stderr)
    require(result.returncode == 0, 'relink_command_failed:' + log.name)


def relink(kit, core, output, replacement=None):
    kit, core, output = Path(kit).resolve(), Path(core).resolve(), Path(output).resolve()
    manifest = json.loads((kit / 'RELINK-MANIFEST.json').read_text())
    require(manifest['schema'] == 1, 'unsupported_relink_schema')
    for base, rows in ((kit, manifest['object_files']), (core, manifest['core_files'])):
        for row in rows:
            require(filehash(inside(base, row['path'])) == row['sha256'],
                    'relink_input_changed:' + row['path'])
    require(not output.exists() and not output.with_suffix('.map').exists(),
            'relink_output_already_exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    command = command_at(manifest['command'], kit, core, output)
    if replacement:
        require(command.count('.pio/build/e32v2/libFrameworkArduino.a') == 1,
                'arduino_replacement_target_missing_or_ambiguous')
        command = [str(Path(replacement).resolve())
                   if item == '.pio/build/e32v2/libFrameworkArduino.a' else item
                   for item in command]
    run(command, kit, output.with_suffix('.log'))
    exact = filehash(output) == manifest['candidate_elf_sha256']
    require(bool(replacement) or exact, 'original_elf_not_reproduced')
    return dict(exact_original_elf=exact, modified_library=bool(replacement),
                elf_sha256=filehash(output))


def create(root, core, output, review):
    root, core, output = Path(root).resolve(), Path(core).resolve(), Path(output).resolve()
    require(not output.exists(), 'relink_kit_already_exists')
    build = root / '.pio/build/e32v2'
    meta = json.loads((build / 'embedded-web.json').read_text())
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root),
            'relink_source_checkout_dirty')
    require(meta['source'] == head, 'relink_build_source_conflict')
    require(review['schema'] == 1 and review['environment'] == 'e32v2', 'unreviewed_relink_scope')
    for relative, digest in review['core_files'].items():
        require(filehash(inside(core, relative)) == digest, 'unreviewed_relink_core:' + relative)

    def portable(command, compiler):
        require(Path(command[0]).name == compiler, 'unexpected_relink_compiler')
        command[0] = '@CORE@/packages/toolchain-xtensa-esp32/bin/' + compiler
        result = []
        for argument in command:
            argument = argument.replace(str(core), '@CORE@').replace(str(root), '@KIT@')
            if argument.startswith('-Wl,-Map='):
                # SCons retains shell quotes around this absolute path. An argv
                # replay must supply the plain output path to the linker.
                value = argument.removeprefix('-Wl,-Map=').strip('"')
                require(value in ('.pio/build/e32v2/firmware.map',
                                  '@KIT@/.pio/build/e32v2/firmware.map'),
                        'unexpected_link_map_output')
                argument = '-Wl,-Map=@OUTPUT_MAP@'
            if argument == '.pio/build/e32v2/firmware.elf':
                argument = '@OUTPUT_ELF@'
            require('/home/' not in argument and '/tmp/' not in argument,
                    'unqualified_host_path_in_relink_recipe')
            result.append(argument)
        return result

    command = portable(json.loads((build / 'relink-command.json').read_text()), 'xtensa-esp32-elf-g++')
    compile_command = portable(json.loads((build / 'arduino-misc-compile-command.json').read_text()),
                               'xtensa-esp32-elf-gcc')
    output.mkdir(parents=True)
    objects = []
    for path in sorted(build.rglob('*')):
        if not path.is_file() or path.suffix not in ('.o', '.a', '.ld'):
            continue
        relative = path.relative_to(root).as_posix()
        dest = output / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        objects.append(dict(path=relative, sha256=filehash(dest)))
    manifest = dict(schema=1, source_commit=head, candidate_elf_sha256=filehash(build / 'firmware.elf'),
                    command=command, compile_command=compile_command,
                    object_files=objects,
                    core_files=[dict(path=p, sha256=h) for p, h in review['core_files'].items()])
    (output / 'RELINK-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n')
    shutil.copyfile(Path(__file__), output / 'relink.py')
    subprocess.run(['git', 'archive', '--format=tar.gz', '-o', str(output / 'application-source.tar.gz'), head],
                   cwd=root, check=True)
    exact = relink(output, core, output / 'proof/original.elf')

    # Change a copy of preferred-form Arduino source, never the installed library.
    source = core / 'packages/framework-arduinoespressif32/cores/esp32/esp32-hal-misc.c'
    text = source.read_text()
    needle = 'unsigned long ARDUINO_ISR_ATTR millis()\n{'
    require(text.count(needle) == 1, 'unrecognized_arduino_millis_source')
    changed = output / 'proof/esp32-hal-misc.c'
    changed.write_text(text.replace(needle, needle + '\n    __asm__ __volatile__("nop");', 1))
    compile_command = command_at(compile_command, output, core, output / 'proof/unused.elf')
    compile_command[compile_command.index('-o') + 1] = str(output / 'proof/esp32-hal-misc.c.o')
    compile_command[-1] = str(changed)
    run(compile_command, output, output / 'proof/compile.log')
    replacement = output / 'proof/libFrameworkArduino-modified.a'
    shutil.copyfile(output / '.pio/build/e32v2/libFrameworkArduino.a', replacement)
    tools = core / 'packages/toolchain-xtensa-esp32/bin'
    run([str(tools / 'xtensa-esp32-elf-ar'), 'r', str(replacement),
         str(output / 'proof/esp32-hal-misc.c.o')], output, output / 'proof/archive.log')
    modified = relink(output, core, output / 'proof/MODIFIED-NOT-FOR-INSTALL.elf', replacement)
    disassemble = [str(tools / 'xtensa-esp32-elf-objdump'), '-d', '--disassemble=millis']
    before = subprocess.check_output(disassemble + [str(output / 'proof/original.elf')], text=True)
    after = subprocess.check_output(disassemble + [str(output / 'proof/MODIFIED-NOT-FOR-INSTALL.elf')], text=True)
    require('<millis>:' in before and '<millis>:' in after, 'retained_millis_missing')
    require(before.split('<millis>:', 1)[1] != after.split('<millis>:', 1)[1]
            and '\tnop' in after, 'modified_library_code_not_retained')
    (output / 'proof/original-millis.txt').write_text(before)
    (output / 'proof/modified-millis.txt').write_text(after)
    report = dict(status='PASS_APPLICATION_RELINK_ONLY', source_commit=head,
                  candidate_elf_sha256=manifest['candidate_elf_sha256'], exact=exact, modified=modified,
                  changed_library_code_retained=True, firmware_release_approved=False)
    (output / 'RELINK-VERIFICATION.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'README.md').write_text('''# E32 application relink material

This kit contains the exact application source and actual application/library
objects. RELINK-MANIFEST.json binds their hashes, the original ELF hash and the
actual expanded compiler/linker commands. It never installs firmware.

Install PlatformIO Core 6.2.0 and the packages pinned in the application source's
platformio.ini. Use the normal PlatformIO package directory as --core. With these
exact packages installed, reproduce the original ELF using:

    python3 relink.py --core /path/to/platformio-core --output relinked/original.elf

The command verifies supplied objects and installed linker/runtime inputs before
linking, and requires the complete ELF to equal the original hash. Choose a fresh
output name: existing candidate or proof files are never overwritten.

To link against a modified Arduino library, rebuild libFrameworkArduino.a from
the preferred-form Arduino source with the recorded environment. Pass that archive
using --arduino-library /path/to/libFrameworkArduino.a. The application source is
also provided and can be rebuilt normally with pio run -e e32v2.

The vendor source inputs and original LGPL/runtime/vendor notices are supplied
separately by the accompanying pinned source distribution. Preserve those notices.
The source/input correspondence check and all firmware release checks remain
separate. This material grants no physical heating authority.

RELINK-VERIFICATION.json records both the exact original relink and a deliberate
source change to the retained Arduino millis() function. proof/ contains research
outputs, including altered ELF files, which must be excluded from install assets.
Never flash a proof ELF or the deliberately modified library.
''')
    return report


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arduino-library', type=Path)
    args = parser.parse_args()
    print(json.dumps(relink(Path(__file__).parent, args.core, args.output, args.arduino_library), indent=2))
