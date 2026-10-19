"""Offline, pytest-discoverable stdlib tests; no HA installation or services.

Run with pytest when present, or:
python3 -m unittest discover -s ha/tests -p 'test_schedule_compiler.py' -v
"""
from __future__ import annotations

import asyncio
from bisect import bisect_right
from copy import deepcopy
from datetime import UTC, datetime, time
import hashlib
import importlib.util
import json
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

MODULE = (
    Path(__file__).resolve().parents[1]
    / "config/custom_components/open_thermostat/schedule_compiler.py"
)
SPEC = importlib.util.spec_from_file_location("offline_schedule_compiler", MODULE)
assert SPEC is not None and SPEC.loader is not None
sc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sc)


def stamp(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def block(start, end, temperature=21):
    return {"from": start, "to": end, "data": {"temperature": temperature}}


def week(**days):
    return {day: days.get(day, []) for day in sc.WEEKDAYS}


def compile_at(raw, start, end, zone="UTC", base=1700):
    return sc.compile_week(raw, base, zone, stamp(start), stamp(end))


def target_at(document, second):
    events = document["transitions"]
    index = bisect_right([event[0] for event in events], second) - 1
    assert document["valid_from_utc"] <= second < document["valid_until_utc"]
    return events[index][1]


class ScheduleCompilerTests(unittest.TestCase):
    def test_empty_week_base_and_exact_wire_shape(self):
        result = compile_at({}, "2026-01-05T00:00Z", "2026-01-20T00:00Z")
        start = stamp("2026-01-05T00:00Z")
        self.assertEqual(result, {
            "timezone": "UTC", "policy": "wall-clock-membership/v1",
            "valid_from_utc": start, "valid_until_utc": start + 15 * 86400,
            "base_centi_c": 1700, "transitions": [[start, 1700]],
        })

    def test_adjacent_on_to_on_temperature_change(self):
        result = compile_at(
            week(monday=[block("06:00", "07:00", 20), block("07:00", "08:00", 21)]),
            "2026-01-05T05:00Z", "2026-01-05T09:00Z",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-01-05T05:00Z"), 1700],
            [stamp("2026-01-05T06:00Z"), 2000],
            [stamp("2026-01-05T07:00Z"), 2100],
            [stamp("2026-01-05T08:00Z"), 1700],
        ])

    def test_first_event_is_actual_mid_block_target(self):
        result = compile_at(
            week(monday=[block("06:00", "07:00", 20.25)]),
            "2026-01-05T06:30Z", "2026-01-05T06:40Z",
        )
        self.assertEqual(result["transitions"], [[stamp("2026-01-05T06:30Z"), 2025]])

    def test_midnight_weekwrap_and_equal_targets_coalesce(self):
        result = compile_at(
            week(sunday=[block("22:00", "24:00", 19)],
                 monday=[block("00:00", "05:00", 19)]),
            "2026-01-04T21:00Z", "2026-01-05T06:00Z",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-01-04T21:00Z"), 1700],
            [stamp("2026-01-04T22:00Z"), 1900],
            [stamp("2026-01-05T05:00Z"), 1700],
        ])

    def test_end_exclusive_no_event_at_expiry(self):
        result = compile_at(
            week(monday=[block("06:00", "07:00")]),
            "2026-01-05T06:00Z", "2026-01-05T07:00Z",
        )
        self.assertEqual(result["transitions"], [[stamp("2026-01-05T06:00Z"), 2100]])
        self.assertEqual(result["valid_until_utc"], stamp("2026-01-05T07:00Z"))

    def test_native_time_max_exactly_end_of_day(self):
        raw = week(monday=[block(time(0), time.max)])
        result = compile_at(raw, "2026-01-05T23:59:58Z", "2026-01-06T00:00:01Z")
        self.assertEqual(result["transitions"], [
            [stamp("2026-01-05T23:59:58Z"), 2100],
            [stamp("2026-01-06T00:00:00Z"), 1700],
        ])

    def test_235959_is_not_time_max(self):
        result = compile_at(
            week(monday=[block(time(0), time(23, 59, 59))]),
            "2026-01-05T23:59:58Z", "2026-01-06T00:00:01Z",
        )
        self.assertEqual(result["transitions"][-1], [stamp("2026-01-05T23:59:59Z"), 1700])

    def test_native_and_wire_end_of_day_representations(self):
        results = []
        for end in [time.max, "24:00", "24:00:00", "23:59:59.999999"]:
            results.append(compile_at(
                week(monday=[block(time(0), end)]),
                "2026-01-05T00:00Z", "2026-01-06T00:00Z"))
        self.assertTrue(all(result == results[0] for result in results))

    def test_no_input_mutation(self):
        raw = week(monday=[block(time(6), time(7), 20.5)])
        previous = deepcopy(raw)
        compile_at(raw, "2026-01-05T00:00Z", "2026-01-06T00:00Z")
        self.assertEqual(raw, previous)

    def test_spring_gap_entire_block_has_no_instant(self):
        result = compile_at(
            week(sunday=[block("02:10", "02:50")]),
            "2026-03-29T00:00Z", "2026-03-29T03:00Z", "Europe/Amsterdam",
        )
        self.assertEqual(result["transitions"], [[stamp("2026-03-29T00:00Z"), 1700]])

    def test_spring_partial_gap_starts_at_real_offset_change(self):
        result = compile_at(
            week(sunday=[block("02:30", "03:30")]),
            "2026-03-29T00:00Z", "2026-03-29T03:00Z", "Europe/Amsterdam",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-03-29T00:00Z"), 1700],
            [stamp("2026-03-29T01:00Z"), 2100],  # Actual 03:00 CEST.
            [stamp("2026-03-29T01:30Z"), 1700],
        ])

    def test_spring_missing_end_stops_at_real_offset_change(self):
        result = compile_at(
            week(sunday=[block("01:30", "02:30")]),
            "2026-03-29T00:00Z", "2026-03-29T03:00Z", "Europe/Amsterdam",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-03-29T00:00Z"), 1700],
            [stamp("2026-03-29T00:30Z"), 2100],
            [stamp("2026-03-29T01:00Z"), 1700],
        ])

    def test_both_fall_folds_and_base_in_repeated_early_hour(self):
        result = compile_at(
            week(sunday=[block("02:30", "03:00")]),
            "2026-10-25T00:00Z", "2026-10-25T03:00Z", "Europe/Amsterdam",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-10-25T00:00Z"), 1700],
            [stamp("2026-10-25T00:30Z"), 2100],
            [stamp("2026-10-25T01:00Z"), 1700],  # Repeated 02:00 CET.
            [stamp("2026-10-25T01:30Z"), 2100],
            [stamp("2026-10-25T02:00Z"), 1700],
        ])

    def test_fall_early_half_hour_also_repeats(self):
        result = compile_at(
            week(sunday=[block("02:00", "02:30")]),
            "2026-10-25T00:00Z", "2026-10-25T02:00Z", "Europe/Amsterdam",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-10-25T00:00Z"), 2100],
            [stamp("2026-10-25T00:30Z"), 1700],
            [stamp("2026-10-25T01:00Z"), 2100],
            [stamp("2026-10-25T01:30Z"), 1700],
        ])

    def test_fall_boundary_exactly_valid_from(self):
        result = compile_at(
            week(sunday=[block("02:30", "03:00")]),
            "2026-10-25T01:00Z", "2026-10-25T02:00Z", "Europe/Amsterdam",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-10-25T01:00Z"), 1700],
            [stamp("2026-10-25T01:30Z"), 2100],
        ])

    def test_utc_has_no_dst(self):
        result = compile_at(
            week(sunday=[block("02:30", "03:00")]),
            "2026-10-25T00:00Z", "2026-10-25T04:00Z",
        )
        self.assertEqual(result["transitions"], [
            [stamp("2026-10-25T00:00Z"), 1700],
            [stamp("2026-10-25T02:30Z"), 2100],
            [stamp("2026-10-25T03:00Z"), 1700],
        ])

    def test_second_by_second_independent_wall_membership_oracle(self):
        # Scalar oracle deliberately does NOT generate endpoint/offset candidates.
        zone = ZoneInfo("Europe/Amsterdam")
        intervals = [(2*3600+30*60, 3*3600, 2100),
                     (4*3600, 4*3600+1, 2300)]
        raw = week(sunday=[block("02:30", "03:00", 21),
                           block("04:00", "04:00:01", 23)])
        for day in ["2026-03-29", "2026-10-25"]:
            with self.subTest(day=day):
                start, end = stamp(day+"T00:00Z"), stamp(day+"T04:00Z")
                result = sc.compile_week(raw, 1700, zone.key, start, end)
                for second in range(start, end):
                    local = datetime.fromtimestamp(second, UTC).astimezone(zone)
                    wall = local.hour*3600+local.minute*60+local.second
                    expected = next((v for a, z, v in intervals if a <= wall < z), 1700)
                    self.assertEqual(target_at(result, second), expected, second)

    def test_seeded_week_independent_membership_samples(self):
        rng = random.Random(20261020)
        raw = week()
        scalar = {}
        for index, day in enumerate(sc.WEEKDAYS):
            scalar[index] = []
            for hour in [1, 6, 15]:
                start = hour*3600 + rng.randrange(60)
                end = start + rng.randrange(1, 1800)
                value = rng.choice([1800, 2050, 2300])
                raw[day].append(block(
                    time(start//3600, start//60 % 60, start % 60),
                    time(end//3600, end//60 % 60, end % 60), value/100))
                scalar[index].append((start, end, value))
        start, end = stamp("2026-10-24T00:00Z"), stamp("2026-10-27T00:00Z")
        result = sc.compile_week(raw, 1700, "Europe/Amsterdam", start, end)
        zone = ZoneInfo("Europe/Amsterdam")
        samples = set(range(start, end, 37))
        for second, _ in result["transitions"]:
            samples.update(t for t in [second-1, second, second+1] if start <= t < end)
        for second in sorted(samples):
            local = datetime.fromtimestamp(second, UTC).astimezone(zone)
            wall = local.hour*3600+local.minute*60+local.second
            expected = next((v for a, z, v in scalar[local.weekday()] if a <= wall < z), 1700)
            self.assertEqual(target_at(result, second), expected, second)

    def test_same_window_canonical_digest_input(self):
        a = week(monday=[block("06:00", "07:00", 20), block("07:00", "08:00", 21)])
        b = dict(reversed(list(a.items())))
        b["monday"] = [block("07:00", "08:00", 21.0), block("06:00", "07:00", 20.0)]
        one = compile_at(a, "2026-01-05T00:00Z", "2026-01-20T00:00Z")
        two = compile_at(b, "2026-01-05T00:00Z", "2026-01-20T00:00Z")
        canonical = lambda x: json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        self.assertEqual(canonical(one), canonical(two))
        self.assertEqual(hashlib.sha256(canonical(one)).digest(), hashlib.sha256(canonical(two)).digest())

    def test_temperature_and_base_limits_inclusive(self):
        for temperature, target in [(5, 500), (35.0, 3500), (20.01, 2001)]:
            with self.subTest(temperature=temperature):
                result = compile_at(week(monday=[block("00:00", "24:00", temperature)]),
                                    "2026-01-05T00:00Z", "2026-01-06T00:00Z", base=500)
                self.assertEqual(result["transitions"][0][1], target)
        self.assertEqual(compile_at({}, "2026-01-05T00:00Z", "2026-01-06T00:00Z",
                                    base=3500)["base_centi_c"], 3500)

    def test_bad_temperatures_rejected_not_rounded(self):
        for value in [True, False, "21", None, float("nan"), float("inf"),
                      -float("inf"), 4.99, 35.01, 20.001, [], {}]:
            with self.subTest(value=value), self.assertRaises(sc.ScheduleValidationError):
                compile_at(week(monday=[block("06:00", "07:00", value)]),
                           "2026-01-05T00:00Z", "2026-01-06T00:00Z")

    def test_bad_base_types_and_limits(self):
        for value in [True, "1700", 1700.0, 499, 3501, None]:
            with self.subTest(value=value), self.assertRaises(sc.ScheduleValidationError):
                compile_at({}, "2026-01-05T00:00Z", "2026-01-06T00:00Z", base=value)

    def test_bad_schema_overlap_and_cross_midnight(self):
        invalid = [
            [], {"monnday": []}, {"monday": None}, {"monday": "bad"},
            week(monday=[None]), week(monday=[{"from": "06:00"}]),
            week(monday=[{"from": "06:00", "to": "07:00", "data": {}}]),
            week(monday=[block("07:00", "06:00")]),
            week(monday=[block("06:00", "06:00")]),
            week(monday=[block("23:00", "01:00")]),
            week(monday=[block("06:00", "08:00"), block("07:00", "09:00")]),
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(sc.ScheduleValidationError):
                compile_at(raw, "2026-01-05T00:00Z", "2026-01-06T00:00Z")

    def test_subseconds_timezone_times_and_bad_times_rejected(self):
        for start, end in [
            (time(6, 0, 0, 1), time(7)), (time(6), time(7, 0, 0, 1)),
            ("06:00:00.000001", "07:00"), ("06:00", "07:00:00.000001"),
            (time.max, time.max), ("24:00", "24:00"), ("6:00", "07:00"),
            ("06:00", "24:01"), (True, "07:00"),
            (time(6, tzinfo=UTC), time(7)),
        ]:
            with self.subTest(start=start, end=end), self.assertRaises(sc.ScheduleValidationError):
                compile_at(week(monday=[block(start, end)]),
                           "2026-01-05T00:00Z", "2026-01-06T00:00Z")

    def test_28_blocks_inclusive_29_rejected(self):
        raw = week(**{day: [block(time(0, 0, n), time(0, 0, n+1))
                           for n in [1, 3, 5, 7]] for day in sc.WEEKDAYS})
        compile_at(raw, "2026-01-05T00:00Z", "2026-01-06T00:00Z")
        raw["monday"].append(block("00:00:09", "00:00:10"))
        with self.assertRaises(sc.ScheduleValidationError):
            compile_at(raw, "2026-01-05T00:00Z", "2026-01-06T00:00Z")

    def test_128_transitions_inclusive_129_rejected(self):
        raw = week(**{day: [block(time(0, 0, n), time(0, 0, n+1))
                           for n in [1, 3, 5, 7]] for day in sc.WEEKDAYS})
        start = stamp("2026-01-05T00:00Z")
        result = sc.compile_week(raw, 1700, "UTC", start, start+15*86400+8)
        self.assertEqual(len(result["transitions"]), 128)
        with self.assertRaises(sc.ScheduleValidationError):
            sc.compile_week(raw, 1700, "UTC", start, start+16*86400)

    def test_horizon_limits_and_integer_utc_bounds(self):
        start = stamp("2026-01-05T00:00Z")
        self.assertEqual(sc.compile_week({}, 1700, "UTC", start, start+16*86400)
                         ["valid_until_utc"], start+16*86400)
        for a, z in [(start, start), (start, start-1),
                     (start, start+16*86400+1), (float(start), start+1),
                     (True, start+1), (start, "2026-01-06"),
                     (sc.MIN_UTC_SECOND-1, sc.MIN_UTC_SECOND+1),
                     (sc.MAX_UTC_SECOND-1, sc.MAX_UTC_SECOND+1)]:
            with self.subTest(start=a, end=z), self.assertRaises(sc.ScheduleValidationError):
                sc.compile_week({}, 1700, "UTC", a, z)

    def test_unsupported_timezone_explicitly_rejected(self):
        for name in ["Europe/London", "America/New_York", "Etc/UTC", "bad", None, True]:
            with self.subTest(name=name), self.assertRaises(sc.ScheduleValidationError):
                compile_at({}, "2026-01-05T00:00Z", "2026-01-06T00:00Z", name)


class NativeExportAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_native_response_action_and_snapshot_copy(self):
        raw = week(monday=[block(time(6), time(7), 20)])
        call = AsyncMock(return_value={"schedule.test_room": raw})
        hass = SimpleNamespace(services=SimpleNamespace(async_call=call))
        result = await sc.async_get_schedule_week(hass, "schedule.test_room")
        call.assert_awaited_once_with(
            "schedule", "get_schedule", {"entity_id": "schedule.test_room"},
            blocking=True, return_response=True,
        )
        self.assertIsInstance(result["monday"][0]["from"], time)
        result["monday"][0]["data"]["temperature"] = 99
        self.assertEqual(raw["monday"][0]["data"]["temperature"], 20)

    async def test_invalid_entity_never_calls_a_service(self):
        call = AsyncMock()
        hass = SimpleNamespace(services=SimpleNamespace(async_call=call))
        for entity in ["all", "climate.room", "schedule.*", "schedule.a,schedule.b", None]:
            with self.subTest(entity=entity), self.assertRaises(sc.ScheduleValidationError):
                await sc.async_get_schedule_week(hass, entity)
        call.assert_not_awaited()

    async def test_missing_or_invalid_action_response(self):
        for response in [None, [], {}, {"schedule.other": {}}, {"schedule.test_room": None}]:
            call = AsyncMock(return_value=response)
            hass = SimpleNamespace(services=SimpleNamespace(async_call=call))
            with self.subTest(response=response), self.assertRaises(sc.ScheduleValidationError):
                await sc.async_get_schedule_week(hass, "schedule.test_room")

    async def test_native_action_error_propagates(self):
        call = AsyncMock(side_effect=RuntimeError("native service unavailable"))
        hass = SimpleNamespace(services=SimpleNamespace(async_call=call))
        with self.assertRaisesRegex(RuntimeError, "native service unavailable"):
            await sc.async_get_schedule_week(hass, "schedule.test_room")

    async def test_export_has_bounded_timeout(self):
        async def never_ready(*args, **kwargs):
            await asyncio.sleep(10)
        hass = SimpleNamespace(services=SimpleNamespace(async_call=never_ready))
        with patch.object(sc, "_EXPORT_TIMEOUT_SECONDS", 0), self.assertRaises(TimeoutError):
            await sc.async_get_schedule_week(hass, "schedule.test_room")

    async def test_adapter_offloads_pure_compile_no_install_or_timer(self):
        raw = week(monday=[block(time(6), time(7), 20)])
        call = AsyncMock(return_value={"schedule.test_room": raw})
        async def execute(fn, *args):
            return await asyncio.to_thread(fn, *args)
        executor = AsyncMock(side_effect=execute)
        hass = SimpleNamespace(services=SimpleNamespace(async_call=call),
                               async_add_executor_job=executor)
        start, end = stamp("2026-01-05T00:00Z"), stamp("2026-01-06T00:00Z")
        result = await sc.async_compile_schedule(
            hass, "schedule.test_room", 1700, "UTC", start, end)
        self.assertEqual(result, sc.compile_week(raw, 1700, "UTC", start, end))
        self.assertEqual(call.await_count, 1)
        self.assertEqual(executor.await_count, 1)


if __name__ == "__main__":
    unittest.main()
