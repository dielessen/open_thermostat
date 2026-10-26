"""Verify the dated public CA snapshot, original source/notices and binary offline.

This is a source correspondence check, not a browser trust-policy or release gate.
No downloads or installed-device changes are performed.
"""
from pathlib import Path
import argparse
import base64
import gzip
import hashlib
import json
import re
import subprocess
import sys
import tempfile


class CAError(ValueError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def inside(root, relative):
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise CAError('unsafe_ca_path')
    target = (root/path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise CAError('external_ca_path')
    return target


def checked(root, record):
    data = inside(root, record['path']).read_bytes()
    if sha(data) != record['sha256']:
        raise CAError('ca_file_identity_conflict:'+record['path'])
    if record.get('git_blob') and blob(data) != record['git_blob']:
        raise CAError('ca_original_git_blob_conflict:'+record['path'])
    return data


def source_certificates(data):
    """Read original NSS certificate DER and its following explicit trust object."""
    result = {}; pending = None
    for obj in re.split(r'^CKA_CLASS CK_OBJECT_CLASS ', data.decode(), flags=re.M)[1:]:
        label = re.search(r'^CKA_LABEL UTF8 "(.*)"$', obj, re.M)
        if obj.startswith('CKO_CERTIFICATE\n'):
            value = re.search(r'^CKA_VALUE MULTILINE_OCTAL\n(.*?)\nEND$', obj, re.M | re.S)
            if not label or not value:
                raise CAError('invalid_nss_certificate_object')
            octets = re.findall(r'\\([0-7]{3})', value[1])
            pending = (label[1], bytes(int(o, 8) for o in octets))
        elif obj.startswith('CKO_NSS_TRUST\n'):
            if not pending or not label or label[1] != pending[0]:
                raise CAError('nss_certificate_trust_pair_conflict')
            trusted = bool(re.search(r'^CKA_TRUST_SERVER_AUTH CK_TRUST CKT_NSS_TRUSTED_DELEGATOR$', obj, re.M))
            result[pending[1]] = dict(label=pending[0], server_auth_trusted=trusted)
            pending = None
    return result


def verify(root):
    root = Path(root).resolve()
    manifest_path = root/'docs/third-party/ca-provenance.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest['schema'] != 1:
        raise CAError('unsupported_ca_schema')
    pem = checked(root, manifest['snapshot'])
    expected_binary = checked(root, manifest['binary'])
    checked(root, manifest['converter'])
    checked(root, manifest['generator'])
    for notice in manifest['notices']:
        if notice.get('original_bytes') is not True:
            raise CAError('original_ca_notice_required')
        checked(root, notice)
    original = manifest['source']
    compressed = inside(root, original['compressed_path'])
    if sha(compressed.read_bytes()) != original['compressed_sha256']:
        raise CAError('ca_compressed_source_conflict')
    with gzip.open(compressed, 'rb') as file:
        source = file.read(4*1024*1024+1)
    if len(source) > 4*1024*1024 or sha(source) != original['sha256'] or blob(source) != original['git_blob']:
        raise CAError('ca_source_identity_conflict')
    if original['sha256'].encode() not in pem.split(b'-----BEGIN CERTIFICATE-----', 1)[0]:
        raise CAError('ca_snapshot_source_header_conflict')
    certificates = [base64.b64decode(re.sub(rb'\s', b'', value), validate=True)
                    for value in re.findall(rb'-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----', pem, re.S)]
    if len(certificates) != manifest['snapshot']['certificates'] or len(set(certificates)) != len(certificates):
        raise CAError('ca_certificate_count_or_duplicate_conflict')
    nss = source_certificates(source)
    for der in certificates:
        if der not in nss or not nss[der]['server_auth_trusted']:
            raise CAError('ca_certificate_not_in_original_server_auth_source')
    # The original generator only accepts its supported input suffixes. Always
    # use .pem, and check both certificate count and bytes; a zero-certificate
    # invocation can otherwise return success.
    with tempfile.TemporaryDirectory(prefix='ot-ca-verify-') as directory:
        work = Path(directory); (work/'cacert.pem').write_bytes(pem)
        run = subprocess.run([sys.executable, str(inside(root, manifest['generator']['path'])),
                              '--input', str(work/'cacert.pem')], cwd=work,
                             capture_output=True, text=True, timeout=45)
        generated = work/'x509_crt_bundle'
        if run.returncode:
            raise CAError('ca_generator_failed_exit_'+str(run.returncode)+': '+run.stderr[-1200:])
        if not generated.is_file() or generated.read_bytes() != expected_binary:
            raise CAError('ca_generated_binary_conflict')
    return dict(status='PASS', scope='dated CA source/notice/binary correspondence only',
                snapshot_sha256=sha(pem), original_source_git_blob=blob(source),
                certificates=len(certificates), server_auth_source_matches=len(certificates),
                binary_sha256=sha(expected_binary), original_notices=len(manifest['notices']),
                manifest_sha256=sha(manifest_path.read_bytes()), downloads=0,
                installed_device_changes=False, browser_constraints_not_asserted=True,
                whole_release_approval=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = verify(args.root)
    text = json.dumps(report, indent=2)+'\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end='')
