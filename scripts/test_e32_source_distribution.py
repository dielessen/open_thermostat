"""Receipt identity checks cannot bypass actual input and application relink work."""
from pathlib import Path
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from e32_distribution import checked_reproduction, prepare
from e32_relink import RelinkError, filehash
from release_notices import canonical, digest


class DistributionChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        base = self.root / 'docs/third-party'
        (base / 'e32v2-reproduction').mkdir(parents=True)
        (base / 'e32v2-source-inputs.json').write_text('{}')
        (base / 'e32v2-reproduction/MANIFEST.json').write_text('{}')
        self.head = '1' * 40
        rows = [dict(archive='libfixture.a', member=str(n) + '.o', source='sources/vendor/' + str(n) + '.c',
                     original_sha256='0' * 64, stripped_sha256=f'{n:064x}') for n in range(629)]
        ordered = sorted(rows, key=lambda row: (row['archive'], row['member'], row['source']))
        (base / 'e32v2-link-review.json').write_text(json.dumps(dict(
            reproduction_proof_sha256=digest(canonical(ordered).encode()))))
        self.report = dict(status='PASS_SDK_RUNTIME_REPRODUCTION_ONLY', source_commit=self.head,
                           source_checkout_clean=True, firmware_release_approved=False,
                           independent_original_ar_and_source_checks=True,
                           input_review_sha256=filehash(base / 'e32v2-link-review.json'),
                           source_policy_sha256=filehash(base / 'e32v2-source-inputs.json'),
                           recipe_manifest_sha256=filehash(base / 'e32v2-reproduction/MANIFEST.json'),
                           sdk_c_cpp=346, sdk_assembly=11, runtime_units=269, startup_objects=3, proof=rows)
        self.receipt = self.root / 'receipt.json'
        self.receipt.write_text(json.dumps(self.report))
        self.notices = dict(environment='e32v2', blocked=['sdk_binary_notice_source_closure_unverified'])

    def test_valid_receipt_is_only_input_evidence(self):
        result = checked_reproduction(self.root, self.head, self.report)
        self.assertIs(result, self.report)
        self.assertFalse(result['firmware_release_approved'])

    def test_stale_dirty_or_selfapproved_receipt_is_denied(self):
        for key, value in [('source_commit', '2' * 40), ('source_checkout_clean', False),
                           ('firmware_release_approved', True), ('independent_original_ar_and_source_checks', False),
                           ('status', 'READY')]:
            with self.subTest(key=key), self.assertRaises(RelinkError):
                checked_reproduction(self.root, self.head, {**self.report, key: value})

    def test_other_source_policy_or_recipe_is_denied(self):
        for key in ['input_review_sha256', 'source_policy_sha256', 'recipe_manifest_sha256']:
            with self.subTest(key=key), self.assertRaisesRegex(RelinkError, 'review_identity_conflict'):
                checked_reproduction(self.root, self.head, {**self.report, key: 'f' * 64})

    def test_missing_or_changed_proof_cannot_be_replaced_by_counts(self):
        with self.assertRaisesRegex(RelinkError, 'proof_missing'):
            checked_reproduction(self.root, self.head, {**self.report, 'proof': []})
        changed = copy.deepcopy(self.report)
        changed['proof'][0]['original_sha256'] = 'f' * 64
        with self.assertRaisesRegex(RelinkError, 'objects_differ_from_review'):
            checked_reproduction(self.root, self.head, changed)

    def test_duplicate_record_cannot_replace_a_required_unit(self):
        changed = copy.deepcopy(self.report)
        changed['proof'][1] = changed['proof'][0]
        with self.assertRaisesRegex(RelinkError, 'objects_differ_from_review'):
            checked_reproduction(self.root, self.head, changed)

    def test_other_board_and_additional_notice_blockers_cannot_be_resolved(self):
        for notices in [dict(environment='esp32s3', blocked=self.notices['blocked']),
                        dict(environment='e32v2', blocked=self.notices['blocked'] + ['other_blocker'])]:
            with self.subTest(notices=notices), self.assertRaises(RelinkError):
                prepare(self.root, self.root, self.root / 'inputs.zip', self.receipt, notices, self.root / 'work')

    def test_all_receipt_metadata_still_requires_actual_current_input_verification(self):
        with patch('e32_distribution.subprocess.check_output', side_effect=[self.head, b'']), \
                patch('e32_distribution.verify_current_inputs', side_effect=RelinkError('actual_inputs_denied')) as inputs, \
                patch('e32_distribution.create') as relink:
            with self.assertRaisesRegex(RelinkError, 'actual_inputs_denied'):
                prepare(self.root, self.root, self.root / 'inputs.zip', self.receipt, self.notices, self.root / 'work')
            inputs.assert_called_once()
            relink.assert_not_called()

    def test_verified_receipt_and_inputs_still_require_actual_application_relink(self):
        with patch('e32_distribution.subprocess.check_output', side_effect=[self.head, b'']), \
                patch('e32_distribution.verify_current_inputs', return_value={}), \
                patch('e32_distribution.create', side_effect=RelinkError('actual_relink_denied')) as relink:
            with self.assertRaisesRegex(RelinkError, 'actual_relink_denied'):
                prepare(self.root, self.root, self.root / 'inputs.zip', self.receipt, self.notices, self.root / 'work')
            relink.assert_called_once()


if __name__ == '__main__':
    unittest.main()
