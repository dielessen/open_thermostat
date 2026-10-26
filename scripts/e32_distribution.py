"""Resolve only the reviewed E32 source-distribution gate with actual material.

The global framework closure flag stays unchanged. No proof flag or JSON report
alone can skip current input validation and exact/changed-library relinking.
"""
from pathlib import Path
import copy
import json
import re
import subprocess

from e32_relink import create, filehash, require
from e32_source_closure import verify as verify_current_inputs
from release_notices import canonical, digest


def checked_reproduction(root, head, report):
    review_path = root / 'docs/third-party/e32v2-link-review.json'
    review = json.loads(review_path.read_text())
    require(report.get('status') == 'PASS_SDK_RUNTIME_REPRODUCTION_ONLY', 'sdk_reproduction_not_verified')
    require(report.get('source_commit') == head and report.get('source_checkout_clean') is True,
            'sdk_reproduction_source_identity_conflict')
    require(report.get('firmware_release_approved') is False
            and report.get('independent_original_ar_and_source_checks') is True,
            'unsupported_sdk_reproduction_receipt')
    require(report.get('input_review_sha256') == filehash(review_path)
            and report.get('source_policy_sha256') == filehash(root / 'docs/third-party/e32v2-source-inputs.json')
            and report.get('recipe_manifest_sha256') == filehash(root / 'docs/third-party/e32v2-reproduction/MANIFEST.json'),
            'sdk_reproduction_review_identity_conflict')
    require(tuple(report.get(k) for k in ('sdk_c_cpp', 'sdk_assembly', 'runtime_units', 'startup_objects'))
            == (346, 11, 269, 3), 'sdk_reproduction_incomplete')
    proof = report.get('proof')
    require(isinstance(proof, list) and len(proof) == 629, 'sdk_reproduction_proof_missing')
    for row in proof:
        require(set(row) == {'archive', 'member', 'source', 'original_sha256', 'stripped_sha256'},
                'unsupported_sdk_object_proof')
        require(all(isinstance(row.get(key), str) and re.fullmatch('[0-9a-f]{64}', row[key])
                    for key in ('original_sha256', 'stripped_sha256')), 'invalid_sdk_object_identity')
    rows = sorted(proof, key=lambda row: (row['archive'] or '', row['member'], row['source']))
    require(digest(canonical(rows).encode()) == review['reproduction_proof_sha256'],
            'sdk_reproduction_objects_differ_from_review')
    return report


def prepare(root, core, archive, reproduction, notices, working):
    root, core, archive = Path(root).resolve(), Path(core).resolve(), Path(archive).resolve()
    require(notices['environment'] == 'e32v2', 'scoped_distribution_requires_e32')
    require(notices['blocked'] == ['sdk_binary_notice_source_closure_unverified'],
            'scoped_distribution_cannot_resolve_other_notice_blockers')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=root),
            'distribution_source_checkout_dirty')
    sdk = checked_reproduction(root, head, json.loads(Path(reproduction).read_text()))
    inputs = verify_current_inputs(root, core, archive)
    link = create(root, core, working, json.loads((root / 'docs/third-party/e32v2-link-review.json').read_text()))
    require(link['source_commit'] == head and link['candidate_elf_sha256'] == inputs['elf_sha256']
            and link['exact']['exact_original_elf'] is True
            and link['modified']['modified_library'] is True
            and link['changed_library_code_retained'] is True,
            'current_application_relink_not_verified')
    spec = json.loads((root / 'docs/third-party/e32v2-source-distribution.json').read_text())
    evidence = dict(scope='Exact current e32v2 application plus reviewed pinned vendor inputs only',
                    source_commit=head, firmware_sha256=inputs['firmware_sha256'],
                    elf_sha256=inputs['elf_sha256'], source_distribution=spec,
                    current_input_correspondence=inputs, application_relink=link,
                    sdk_reproduction_receipt_sha256=filehash(reproduction),
                    sdk_reproduction_proof_sha256=json.loads((root / 'docs/third-party/e32v2-link-review.json').read_text())['reproduction_proof_sha256'],
                    sdk_reproduction_source_commit=sdk['source_commit'],
                    global_framework_closure_changed=False, physical_acceptance=False)
    qualified = copy.deepcopy(notices)
    qualified['unqualified_inventory_sha256'] = qualified.pop('inventory_sha256')
    qualified['resolved_target_specific_blockers'] = qualified['blocked']
    qualified['blocked'] = []
    qualified['status'] = 'READY_FOR_NOTICES_PACKAGING_ONLY'
    qualified['e32_distribution_evidence'] = evidence
    qualified['inventory_sha256'] = digest(canonical(qualified).encode())
    return qualified, evidence
