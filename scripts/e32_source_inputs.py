"""Verify pinned vendor-source inputs. This alone never approves firmware release."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import posixpath
import re
import stat
import tarfile
import zipfile


class SourceInputError(ValueError):
    pass


def relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts
            or str(PurePosixPath(name)) != name):
        raise SourceInputError('unsafe_source_path')
    return name


def sha_stream(stream):
    result = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        result.update(block)
    return result.hexdigest()


def verify(policy, archive):
    if policy.get('schema') != 1 or policy.get('environment') != 'e32v2':
        raise SourceInputError('unsupported_source_input_scope')
    expected = policy['payloads']
    for name, digest in expected.items():
        relative(name)
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise SourceInputError('invalid_source_hash')
    for source in policy['archives']:
        relative(source['path'])
        if source['path'] not in expected:
            raise SourceInputError('unbound_source_archive')
        for name, digest in source['required_sources'].items():
            relative(name)
            if not re.fullmatch('[0-9a-f]{64}', digest):
                raise SourceInputError('invalid_source_hash')
    checked_sources = 0
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        names = [m.filename for m in members]
        for name in names:
            relative(name)
        if len(names) != len(set(names)):
            raise SourceInputError('duplicate_source_payload')
        if set(names) != set(expected) | {'CORRESPONDENCE.json'}:
            raise SourceInputError('unexpected_or_missing_source_payload')
        if (len(members) > 1500 or sum(m.file_size for m in members) > 1024**3
                or any(m.file_size > 512 * 1024**2 for m in members)):
            raise SourceInputError('source_input_budget')
        for member in members:
            kind = stat.S_IFMT(member.external_attr >> 16)
            if kind not in (0, stat.S_IFREG) or member.flag_bits & 1:
                raise SourceInputError('nonregular_or_encrypted_source_payload')
        if package.getinfo('CORRESPONDENCE.json').file_size > 8 * 1024**2:
            raise SourceInputError('source_manifest_budget')
        if json.loads(package.read('CORRESPONDENCE.json')) != policy:
            raise SourceInputError('source_manifest_conflict')
        for name, digest in expected.items():
            with package.open(name) as stream:
                if sha_stream(stream) != digest:
                    raise SourceInputError('source_payload_hash_conflict:' + name)
        for source in policy['archives']:
            wanted = source['required_sources']
            hashes, links, names = {}, {}, set()
            total = entries = 0
            with package.open(source['path']) as stream, tarfile.open(fileobj=stream, mode='r|gz') as tree:
                for member in tree:
                    relative(member.name.rstrip('/'))
                    entries += 1
                    total += member.size
                    if entries > 200000 or total > 3 * 1024**3:
                        raise SourceInputError('source_tree_budget')
                    if member.isdir():
                        continue
                    if member.name in names:
                        raise SourceInputError('ambiguous_required_source')
                    names.add(member.name)
                    if member.isfile():
                        with tree.extractfile(member) as content:
                            hashes[member.name] = sha_stream(content)
                    elif member.issym() or member.islnk():
                        links[member.name] = (member.linkname, member.issym())
            if not set(wanted) <= names:
                raise SourceInputError('required_corresponding_source_missing')
            for name, digest in wanted.items():
                resolved, visited = name, set()
                while resolved in links:
                    if resolved in visited or len(visited) >= 32:
                        raise SourceInputError('cyclic_or_deep_source_link')
                    visited.add(resolved)
                    target, symlink = links[resolved]
                    if PurePosixPath(target).is_absolute() or '\\' in target:
                        raise SourceInputError('unsafe_source_link')
                    resolved = relative(posixpath.normpath(posixpath.join(
                        posixpath.dirname(resolved) if symlink else '', target)))
                if hashes.get(resolved) != digest:
                    raise SourceInputError('corresponding_source_hash_conflict:' + name)
            checked_sources += len(wanted)
    return dict(status='PASS_VENDOR_SOURCE_INPUTS_ONLY', environment='e32v2',
                payloads=len(expected), source_archives=len(policy['archives']),
                required_source_files=checked_sources, firmware_release_approved=False,
                current_application_relink_package_required=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(json.loads(args.policy.read_text()), args.archive), indent=2))
