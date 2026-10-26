"""Independently check reproduced E32 SDK/runtime objects against actual archives."""
from pathlib import Path
import argparse
import json
import os
import subprocess

from e32_relink import filehash, inside, require


def ar_members(path):
    data = path.read_bytes()
    require(data[:8] == b'!<arch>\n', 'invalid_original_ar_header')
    position, names, result = 8, b'', {}
    while position < len(data):
        header = data[position:position + 60]
        require(len(header) == 60 and header[58:60] == b'`\n', 'invalid_original_ar_member')
        size = int(header[48:58])
        body = data[position + 60:position + 60 + size]
        require(size >= 0 and len(body) == size, 'truncated_original_ar_member')
        name = header[:16].decode('ascii').strip()
        position += 60 + size + size % 2
        if name == '//':
            names = body
            continue
        if name in ('/', '/SYM64/'):
            continue
        if name.startswith('/'):
            offset = int(name[1:])
            require(0 <= offset < len(names), 'invalid_original_ar_long_name')
            name = names[offset:names.index(b'/\n', offset)].decode('ascii')
        else:
            name = name.rstrip('/')
        require(body.startswith(b'\x7fELF'), 'non_elf_original_ar_member')
        result.setdefault(name, []).append(body)
    require(position == len(data), 'invalid_original_ar_alignment')
    return result


def declared_sdk_source(name, submodules, prepared):
    if '/esp-idf/' in name:
        relative = name.split('/esp-idf/', 1)[1]
        for binding in sorted(submodules, key=lambda row: -len(row['path'])):
            prefix = binding['path'] + '/'
            if relative.startswith(prefix):
                return 'sources/' + binding['repository'].split('/')[-1] + '/' + relative[len(prefix):]
        return 'sources/esp-idf/' + relative
    prefix = '/components/esp-rainmaker/components/esp-insights/'
    if prefix in name:
        return 'sources/esp-insights/' + name.split(prefix, 1)[1]
    return None


def verify(root, core, prepared):
    root, core, prepared = Path(root).resolve(), Path(core).resolve(), Path(prepared).resolve()
    review = json.loads((root / 'docs/third-party/e32v2-link-review.json').read_text())
    policy_path = root / 'docs/third-party/e32v2-source-inputs.json'
    require(filehash(policy_path) == review['source_policy_sha256'], 'source_review_policy_conflict')
    for path, digest in review['core_files'].items():
        require(filehash(inside(core, path)) == digest, 'original_reproduction_input_changed:' + path)
    recipes = root / 'docs/third-party/e32v2-reproduction'
    manifest = json.loads((recipes / 'MANIFEST.json').read_text())
    for path, digest in manifest['files'].items():
        require(filehash(inside(recipes, path)) == digest and
                filehash(inside(prepared, path)) == digest, 'reproduction_recipe_changed:' + path)
    source_hashes = {}
    for archive in json.loads(policy_path.read_text())['archives']:
        if not archive['repository']:
            continue
        for path, digest in archive['required_sources'].items():
            relative = '/'.join(Path(path).parts[1:])
            source_hashes['sources/' + archive['component'] + '/' + relative] = digest
    sdk_rows = json.loads((prepared / 'ARCHIVE-SOURCE-DECLARATIONS.json').read_text())['rows']
    runtime_rows = json.loads((prepared / 'TOOLCHAIN-RUNTIME-SOURCE-DECLARATIONS.json').read_text())['rows']
    submodules = json.loads((prepared / 'SUBMODULE-TREE-RECEIPTS.json').read_text())
    sdk = json.loads((prepared / 'SDK-REPRODUCED.json').read_text())['results']
    assembly = json.loads((prepared / 'RECOMPILE-ASSEMBLY.json').read_text())
    runtime = json.loads((prepared / 'RUNTIME-REPRODUCED.json').read_text())
    startup = json.loads((prepared / 'RUNTIME-STARTUP-RECOMPILE.json').read_text())
    require((len(sdk), len(assembly), len(runtime), len(startup)) == (346, 11, 269, 3),
            'incomplete_reproduction_counts')
    expected_sdk = set()
    for row in sdk_rows:
        for unit in row['compilation_units']:
            name = unit.get('name', '')
            source = declared_sdk_source(name, submodules, prepared)
            if source and name.endswith(('.c', '.cpp', '.cc')) and inside(prepared, source).is_file():
                expected_sdk.add((Path(row['path']).name, unit['member'], source))
    actual_sdk = {(row['archive'], row['member'], row['source']) for row in sdk}
    require(len(expected_sdk) == 346 and actual_sdk == expected_sdk, 'incomplete_sdk_unit_coverage')
    expected_assembly = {(Path(row['path']).name, row['unit']['member'],
                          declared_sdk_source(row['unit']['name'], submodules, prepared))
                         for row in json.loads((prepared / 'ASSEMBLY-QUEUE.json').read_text())}
    require({(r['archive'], r['member'], r['source']) for r in assembly} == expected_assembly,
            'incomplete_assembly_unit_coverage')
    expected_runtime = {(Path(row['path']).name, unit['member'])
                        for row in runtime_rows for unit in row['compilation_units']}
    require(len(expected_runtime) == 269 and {(r['archive'], r['member']) for r in runtime} == expected_runtime,
            'incomplete_runtime_unit_coverage')
    require({r['member'] for r in startup} == {'crti.o', 'crtbegin.o', 'crtend.o'},
            'incomplete_startup_coverage')
    originals = {}
    for row in sdk_rows + runtime_rows:
        # GCC reports its library search path with internal bin/../ segments.
        # Canonicalize that spelling and still require the reviewed core path.
        relative = os.path.normpath(row['path'])
        require(relative in review['core_files'], 'unreviewed_original_archive_path')
        originals[Path(relative).name] = ar_members(inside(core, relative))
    tools = core / 'packages/toolchain-xtensa-esp32/bin'
    scratch = prepared / 'independent-object-check'
    require(not scratch.exists(), 'reproduction_verification_output_already_exists')
    scratch.mkdir()
    verified = []
    for record in sdk + assembly + runtime + startup:
        require(record['status'] == 'EXACT_STRIPPED_OBJECT', 'unsuccessful_reproduction_unit')
        source, folder = inside(prepared, record['source']), inside(prepared, record['evidence'])
        require(record['source'] in source_hashes and filehash(source) == source_hashes[record['source']],
                'reproduced_source_not_in_pinned_offer:' + record['source'])
        require(filehash(source) == record['source_sha256'], 'reproduction_source_receipt_conflict')
        original = (folder / 'original.o').read_bytes()
        if 'archive' in record:
            require(original in originals[record['archive']][record['member']], 'original_ar_object_conflict')
        else:
            path = core / 'packages/toolchain-xtensa-esp32/lib/gcc/xtensa-esp32-elf/8.4.0/no-rtti' / record['member']
            require(original == path.read_bytes(), 'original_startup_object_conflict')
        require(filehash(folder / 'original.o') == record['original_object_sha256'],
                'original_object_receipt_conflict')
        command = json.loads((folder / 'COMMAND.json').read_text())
        require(command[0] in {str(tools / 'xtensa-esp32-elf-gcc'), str(tools / 'xtensa-esp32-elf-g++')}
                and '-c' in command and command[-3] == str(source), 'reproduction_command_source_conflict')
        for label in ('original', 'rebuilt'):
            subprocess.run([str(tools / 'xtensa-esp32-elf-objcopy'), '--strip-debug',
                            '--remove-section=.comment', str(folder / (label + '.o')),
                            str(scratch / (label + '.o'))], check=True, capture_output=True)
        require((scratch / 'original.o').read_bytes() == (scratch / 'rebuilt.o').read_bytes(),
                'independent_reproduced_object_conflict')
        verified.append(dict(archive=record.get('archive'), member=record['member'],
                             source=record['source'], original_sha256=filehash(folder / 'original.o'),
                             stripped_sha256=filehash(scratch / 'rebuilt.o')))
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    clean = not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root)
    return dict(status='PASS_SDK_RUNTIME_REPRODUCTION_ONLY', source_commit=head,
                source_checkout_clean=clean,
                input_review_sha256=filehash(root / 'docs/third-party/e32v2-link-review.json'),
                source_policy_sha256=filehash(policy_path),
                recipe_manifest_sha256=filehash(recipes / 'MANIFEST.json'),
                sdk_c_cpp=346, sdk_assembly=11,
                runtime_units=269, startup_objects=3, independent_original_ar_and_source_checks=True,
                normalization='Remove debug and .comment only; no instruction/data/symbol rewriting',
                proof=verified, firmware_release_approved=False, firmware_installed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--core', type=Path, default=Path(os.environ.get('PLATFORMIO_CORE_DIR', str(Path.home()/'.platformio'))))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'reproduction_report_already_exists')
    result = verify(Path(__file__).resolve().parents[1], args.core, args.prepared)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'proof'}, indent=2))
