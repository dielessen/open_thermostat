"""Check current E32 inputs against reviewed source correspondence, offline.

This target-specific check cannot qualify S3 or arbitrary framework versions.
Application relink material and the remaining release gates are separate.
"""
from pathlib import Path
import json

from e32_relink import filehash, inside, require
from e32_source_inputs import verify as verify_source_archive
from release_shipped import descriptor, elf_allocations, map_inputs


def source_inventory(base, expected, scopes):
    base = Path(base).resolve()
    actual = set()
    for scope in scopes:
        for path in inside(base, scope).rglob('*'):
            relative = path.relative_to(base)
            if '.git' in relative.parts or path.name == '.piopm':
                continue
            require(not (path.is_symlink() and path.is_dir()), 'unreviewed_source_directory_link')
            if path.is_file():
                actual.add(relative.as_posix())
    require(actual == set(expected), 'source_inventory_missing_or_unreviewed')
    for name, digest in expected.items():
        require(filehash(inside(base, name)) == digest, 'reviewed_source_bytes_changed:' + name)
    return len(actual)


def retained_inventory(rows, review):
    approved = {(r['path'], r['member']) for r in review['retained_vendor_inputs']}
    vendor = []
    for row in rows:
        path, member = row['path'], row['member']
        if path.startswith(('packages/framework-arduinoespressif32/tools/sdk/esp32/',
                            'packages/toolchain-xtensa-esp32/')):
            require((path, member) in approved, 'unreviewed_retained_vendor_input:' + path)
            vendor.append(dict(path=path, member=member))
        elif path.startswith('.pio/build/e32v2/'):
            if row['archive']:
                require(row['archive'] in review['build_archives'],
                        'unreviewed_linked_library:' + row['archive'])
            else:
                require(member is None and path.endswith('.o'), 'unrecognized_application_input')
        else:
            require(False, 'unqualified_retained_input:' + path)
    require(bool(vendor), 'missing_retained_vendor_inputs')
    return vendor


def verify(root, core, archive):
    root, core, archive = Path(root).resolve(), Path(core).resolve(), Path(archive).resolve()
    review = json.loads((root / 'docs/third-party/e32v2-link-review.json').read_text())
    require(review['schema'] == 1 and review['environment'] == 'e32v2', 'unsupported_input_review_scope')
    policy_path = root / 'docs/third-party/e32v2-source-inputs.json'
    require(filehash(policy_path) == review['source_policy_sha256'], 'source_policy_review_changed')
    spec = json.loads((root / 'docs/third-party/e32v2-source-distribution.json').read_text())
    require(spec['schema'] == 1 and spec['environment'] == 'e32v2'
            and spec['firmware_release_approved'] is False, 'unsupported_source_distribution')
    require(archive.stat().st_size == spec['bytes'] and filehash(archive) == spec['sha256'],
            'source_distribution_digest_conflict')
    source_report = verify_source_archive(json.loads(policy_path.read_text()), archive)
    framework = core / 'packages/framework-arduinoespressif32'
    framework_count = source_inventory(framework, review['framework_files'],
                                       ['cores', 'libraries', 'variants', 'tools/sdk/esp32'])
    # Unity is included as source in the vendor bundle but is host-only. It is
    # neither required in the E32 cache nor admitted to retained firmware inputs.
    external = {k: v for k, v in review['external_files'].items() if not k.startswith('Unity/')}
    library_count = source_inventory(root / '.pio/libdeps/e32v2', external,
                                     sorted({p.split('/')[0] for p in external}))
    for relative, digest in review['core_files'].items():
        require(filehash(inside(core, relative)) == digest, 'reviewed_core_bytes_changed:' + relative)
    build = root / '.pio/build/e32v2'
    elf, binary = (build / 'firmware.elf').read_bytes(), (build / 'firmware.bin').read_bytes()
    app = descriptor(binary, elf)
    rows = map_inputs((build / 'firmware.map').read_text(), elf_allocations(elf))
    vendor = retained_inventory(rows, review)
    return dict(status='PASS_CURRENT_E32_INPUT_CORRESPONDENCE_ONLY', environment='e32v2',
                elf_sha256=app['elf_sha256'], firmware_sha256=filehash(build / 'firmware.bin'),
                framework_files=framework_count, external_runtime_source_files=library_count,
                core_pins=len(review['core_files']), retained_vendor_inputs=len(vendor),
                source_archive=source_report, source_archive_sha256=spec['sha256'],
                firmware_release_approved=False, current_application_relink_package_required=True)
