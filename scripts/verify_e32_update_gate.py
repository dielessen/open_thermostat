"""Validate the recorded physical update acceptance before publishing a successor.

This validates evidence correspondence; it never performs an update or claims
that synthetic/CI tests prove a physical installation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

POLICY = 'docs/modern-thermostat/E32-UPDATE-GATE.json'
REQUIRED = ('public_package_exact', 'fresh_preflight_passed', 'backup_verified',
    'single_native_install_command', 'original_admission_recorded',
    'download_checksum_image_readback_passed', 'new_boot_observed',
    'installed_version_source_elf_web_exact', 'boot_confirmed',
    'stable_uptime_observed', 'settings_programs_bindings_preserved',
    'outputs_remained_disabled', 'independent_postcheck_passed')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def version(value):
    if not isinstance(value, str):
        return None
    number = r'(0|[1-9]\d*)'
    match = re.fullmatch('v'+number+r'\.'+number+r'\.'+number+
        r'-e32v2(?:-(alpha|beta|rc)\.'+number+r')?', value)
    if not match:
        return None
    major, minor, patch, stage, sequence = match.groups()
    return (int(major), int(minor), int(patch),
            {'alpha': 0, 'beta': 1, 'rc': 2, None: 3}[stage], int(sequence or 0))


def valid_tag(value):
    return version(value) is not None


def verify(root, policy, candidate=None):
    root = Path(root).resolve()
    require(policy.get('schema') == 1, 'Unknown E32 update-gate schema')
    require(policy.get('required_for_successor_release') is True, 'Mandatory update gate disabled')
    pending = policy.get('pending_tag')
    require(pending is None or valid_tag(pending), 'Invalid pending release')
    accepted = policy.get('accepted')
    if accepted is not None:
        require(valid_tag(accepted.get('tag')), 'Invalid accepted release')
        require(isinstance(accepted.get('receipt'), str), 'Missing acceptance receipt')
        path = (root / accepted['receipt']).resolve()
        require(path.is_relative_to(root) and path.is_file(), 'Missing/outside acceptance receipt')
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == accepted.get('sha256'), 'Acceptance receipt changed')
        record = json.loads(raw)
        require(record.get('schema') == 1 and record.get('status') == 'PASS', 'Update not accepted')
        require(record.get('tag') == accepted['tag'], 'Acceptance belongs to another release')
        require(record.get('method') == 'native_github', 'Wrong update route')
        checks = record.get('checks', {})
        require(all(checks.get(key) is True for key in REQUIRED), 'Incomplete physical update acceptance')
        require(record.get('catalog_check_commands') in (0, 1)
                and type(record.get('catalog_check_commands')) is int, 'Unexpected catalog retries')
        require(type(record.get('install_commands')) is int and record['install_commands'] == 1,
                'Install was missing/repeated')
        require(record.get('install_http_status') == 202, 'Original worker admission missing')
        for key, length in (('source_commit', 40), ('elf_sha256', 64), ('web_sha256', 64),
                            ('firmware_sha256', 64), ('installer_receipt_sha256', 64),
                            ('independent_receipt_sha256', 64), ('backup_manifest_sha256', 64)):
            require(isinstance(record.get(key), str)
                    and re.fullmatch('[0-9a-f]{'+str(length)+'}', record[key]), 'Missing identity: '+key)
    if candidate is not None:
        require(valid_tag(candidate), 'Unsupported release candidate')
        require(accepted is not None, 'No physically accepted E32 predecessor; successor publication blocked')
        require(pending == candidate, 'Another release is pending or candidate freeze is missing')
        require(version(candidate) > version(accepted['tag']),
                'Candidate must be newer than accepted predecessor')
    return {'result': 'PASS', 'accepted': accepted['tag'] if accepted else None,
            'pending': pending, 'successor_ready': accepted is not None and pending is None,
            'physical_test_performed_by_verifier': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(verify(root, json.loads((root / POLICY).read_text()), args.candidate)))
