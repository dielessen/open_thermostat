"""Recompile the exact shared HA/firmware fixtures; no live HA or C++ mocks.

Repository-relative fixture path matches the parent's shared test/fixtures tree.
The production compiler is imported without loading the HA integration package.
Run under pytest or standard unittest discovery together with the baseline suite.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPILER_PATH = (
    REPOSITORY_ROOT
    / "ha/config/custom_components/open_thermostat/schedule_compiler.py"
)
FIXTURE_PATH = REPOSITORY_ROOT / "test/fixtures/compiled-schedule-cases.json"

SPEC = importlib.util.spec_from_file_location("shared_fixture_schedule_compiler", COMPILER_PATH)
assert SPEC is not None and SPEC.loader is not None
compiler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compiler)


def canonical_bytes(document: dict) -> bytes:
    """Canonical encoding used when the shared fixture hashes were generated."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")


class SharedScheduleFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise AssertionError("shared fixture must be a list")
        cls.cases = {}
        for row in rows:
            name = row["case"]
            if name in cls.cases:
                raise AssertionError(f"duplicate shared fixture case: {name}")
            cls.cases[name] = row
        if set(cls.cases) != {"spring_wholly_gap", "fall_both_folds"}:
            raise AssertionError("expected both original shared DST fixtures")

    def assert_shared_case(self, name):
        row = self.cases[name]
        expected = row["output"]
        actual = compiler.compile_week(
            row["week"],
            expected["base_centi_c"],
            expected["timezone"],
            expected["valid_from_utc"],
            expected["valid_until_utc"],
        )
        self.assertEqual(actual, expected, "recompiled wire output differs from C++ fixture")
        self.assertEqual(
            hashlib.sha256(canonical_bytes(actual)).hexdigest(),
            row["canonical_json_sha256"],
            "recompiled canonical digest differs from shared fixture",
        )
        self.assertEqual(
            hashlib.sha256(canonical_bytes(expected)).hexdigest(),
            row["canonical_json_sha256"],
            "stored fixture output/hash inconsistent",
        )

    def test_shared_spring_gap_output_and_canonical_sha256(self):
        self.assert_shared_case("spring_wholly_gap")

    def test_shared_fall_folds_output_and_canonical_sha256(self):
        self.assert_shared_case("fall_both_folds")


class CompilerEpochBoundaryTests(unittest.TestCase):
    def test_2038_epoch_is_not_narrowed_to_signed_32_bit(self):
        result = compiler.compile_week({}, 1700, "UTC", 2147483647, 2147483649)
        self.assertEqual(result["valid_until_utc"], 2147483649)
        self.assertEqual(result["transitions"], [[2147483647, 1700]])
        self.assertIs(type(result["valid_until_utc"]), int)

    def test_exact_upper_bound_is_exclusive_not_a_rejected_valid_end(self):
        result = compiler.compile_week({}, 1700, "UTC", 4102444799, 4102444800)
        self.assertEqual(result["valid_until_utc"], 4102444800)
        self.assertEqual(result["transitions"], [[4102444799, 1700]])
        self.assertNotIn([4102444800, 1700], result["transitions"])


if __name__ == "__main__":
    unittest.main()
