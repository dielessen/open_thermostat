"""Validate update acceptance and any scoped prerelease publication decision.

This validates evidence correspondence; it never performs an update or claims
that synthetic/CI tests prove a physical installation. A hash-bound owner
exception can permit one beta publication while preserving the evidence gap.
"""
from pathlib import Path
import argparse
from datetime import datetime
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


def document(root, name, label, expected_sha=None):
    require(isinstance(name, str) and bool(name), 'Missing '+label)
    path = (root / name).resolve()
    require(path.is_relative_to(root) and path.is_file(), 'Missing/outside '+label)
    raw = path.read_bytes()
    require(0 < len(raw) <= 65536, 'Oversized '+label)
    if expected_sha is not None:
        require(isinstance(expected_sha, str) and re.fullmatch('[0-9a-f]{64}', expected_sha),
                'Missing digest for '+label)
        require(hashlib.sha256(raw).hexdigest() == expected_sha, label+' changed')
    value = json.loads(raw)
    require(isinstance(value, dict), 'Invalid '+label)
    return value


def publication_exception(root, reference):
    if reference is None:
        return None
    require(isinstance(reference, dict) and set(reference) == {'receipt', 'sha256'},
            'Invalid publication exception reference')
    require(isinstance(reference['sha256'], str) and re.fullmatch('[0-9a-f]{64}', reference['sha256']),
            'Missing publication exception digest')
    record = document(root, reference['receipt'], 'publication exception', reference['sha256'])
    require(type(record.get('schema')) is int and record['schema'] == 1 and record.get('status') == 'APPROVED',
            'Publication exception has no explicit approval')
    require(record.get('scope') == 'one_prerelease_publication', 'Wrong exception scope')
    tags = [record.get(key) for key in ('accepted_basis_tag', 'unaccepted_predecessor', 'candidate_tag')]
    require(all(valid_tag(tag) for tag in tags), 'Invalid exception release identity')
    require(version(tags[0]) < version(tags[1]) < version(tags[2]), 'Invalid exception release order')
    require(version(tags[2])[3] == 1, 'Exception is limited to a beta prerelease')
    require(record.get('predecessor_acceptance_status') == 'INCOMPLETE',
            'Exception must retain incomplete predecessor acceptance')
    require(record.get('device_installation_authorized') is False
            and record.get('boiler_trial_authorized') is False, 'Exception grants publication only')
    require(isinstance(record.get('accepted_basis_receipt_sha256'), str)
            and re.fullmatch('[0-9a-f]{64}', record['accepted_basis_receipt_sha256']),
            'Missing accepted basis receipt identity')
    reason = record.get('reason')
    require(isinstance(reason, str) and 1 <= len(reason.strip()) <= 2000, 'Missing exception reason')
    gap_sha = record.get('gap_report_sha256')
    require(isinstance(gap_sha, str) and re.fullmatch('[0-9a-f]{64}', gap_sha), 'Missing evidence-gap digest')
    gap = document(root, record.get('gap_report'), 'predecessor evidence-gap report', gap_sha)
    require(gap.get('status') == 'INCOMPLETE', 'Missing incomplete predecessor evidence')
    approval = record.get('approval')
    require(isinstance(approval, dict) and approval.get('actor') == 'repository_owner'
            and approval.get('method') == 'explicit_user_instruction'
            and approval.get('decision') == 'approve_one_prerelease_publication',
            'Missing explicit operator decision')
    statement = approval.get('statement')
    require(isinstance(statement, str) and 1 <= len(statement.strip()) <= 2000,
            'Missing original approval statement')
    at = approval.get('at_utc')
    require(isinstance(at, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', at),
            'Missing UTC approval time')
    datetime.strptime(at, '%Y-%m-%dT%H:%M:%SZ')
    return record


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
    exception = publication_exception(root, policy.get('publication_exception'))
    plan = None
    if policy.get('candidate_plan') is not None:
        plan = document(root, policy['candidate_plan'], 'candidate plan')
        require(valid_tag(plan.get('planned_tag')) and valid_tag(plan.get('previous_published_tag'))
                and version(plan['previous_published_tag']) < version(plan['planned_tag']),
                'Invalid candidate plan release order')
    basis = None
    if candidate is not None:
        require(valid_tag(candidate), 'Unsupported release candidate')
        require(accepted is not None, 'No physically accepted E32 predecessor; successor publication blocked')
        require(pending == candidate, 'Another release is pending or candidate freeze is missing')
        require(version(candidate) > version(accepted['tag']),
                'Candidate must be newer than accepted predecessor')
        require(plan is not None, 'Missing candidate plan')
        previous = plan.get('previous_published_tag')
        require(plan.get('planned_tag') == candidate and valid_tag(previous)
                and version(previous) < version(candidate), 'Candidate plan identity/order mismatch')
        basis = 'accepted_previous_release'
        if accepted['tag'] != previous:
            require(exception is not None, 'Previous published release is not accepted; explicit exception required')
            require(exception['candidate_tag'] == candidate and exception['unaccepted_predecessor'] == previous,
                    'Exception belongs to another candidate/predecessor')
            require(exception['accepted_basis_tag'] == accepted['tag']
                    and exception['accepted_basis_receipt_sha256'] == accepted['sha256'],
                    'Exception belongs to another accepted basis')
            basis = 'operator_approved_one_time_exception'
    ready = accepted is not None and pending is None
    if plan is not None:
        ready = ready and accepted['tag'] in {plan.get('previous_published_tag'), plan.get('planned_tag')}
    result = {'result': 'PASS', 'accepted': accepted['tag'] if accepted else None,
              'pending': pending, 'successor_ready': ready,
              'physical_test_performed_by_verifier': False}
    if basis is not None:
        result['publication_basis'] = basis
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(json.dumps(verify(root, json.loads((root / POLICY).read_text()), args.candidate)))
