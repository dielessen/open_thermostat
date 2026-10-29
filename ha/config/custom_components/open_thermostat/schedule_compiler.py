"""Native HA week export and bounded, pure UTC schedule materialization.

Policy wall-clock-membership/v1: evaluate local [start, end) membership at
each real UTC boundary. Missing wall times have no instant; repeated wall
times are evaluated twice. Offset changes are boundaries in their own right.

Supported zones: any IANA zone the system tzdata knows (Home Assistant's own
time zone), UTC windows within 2000..2099. Offsets that are not whole hours
(Asia/Kathmandu +05:45, Australia/Lord_Howe's 30-minute DST) are supported:
the controller only receives UTC transitions; the zone name is metadata.
Offset changes are searched minute by minute, so the compiler only relies on
at most one offset change per minute (true for every tzdb zone). No private
ZoneInfo APIs.

No HA import, I/O, state listeners or timers are needed by compile_week.
The async adapter uses HA's public response action and executor API only.
This module does not implement transport, revisions, acknowledgment, expiry
enforcement, GUI, device actions, or a scheduler. Firmware MUST stop normal
schedule demand when this finite window expires.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
import math
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

POLICY = "wall-clock-membership/v1"
WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
)
# Syntactic IANA name rule shared with the controller and the Python mirrors:
# at most 63 bytes, "/"-separated segments starting with an ASCII letter.
TIMEZONE_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_+-]*(?:/[A-Za-z][A-Za-z0-9_+-]*)*")
MAX_TIMEZONE_NAME_BYTES = 63
_OFFSET_SCAN_SECONDS = 60
MIN_CENTI_C = 500
MAX_CENTI_C = 3500
MAX_WEEK_BLOCKS = 28
MAX_TRANSITIONS = 128
MAX_HORIZON_SECONDS = 16 * 86400
MIN_UTC_SECOND = 946684800  # 2000-01-01T00:00:00Z
MAX_UTC_SECOND = 4102444800  # 2100-01-01T00:00:00Z, exclusive horizon end
_EXPORT_TIMEOUT_SECONDS = 10
_TIME_PATTERN = re.compile(r"[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?")
_ENTITY_PATTERN = re.compile(r"schedule\.[a-z0-9_]+")
Block = tuple[int, int, int]


class ScheduleValidationError(ValueError):
    """A complete schedule/window cannot be safely represented."""


def _centi_base(value: object) -> int:
    if type(value) is not int or not MIN_CENTI_C <= value <= MAX_CENTI_C:
        raise ScheduleValidationError("base_centi_c must be an integer in 500..3500")
    return value


def _temperature(value: object) -> int:
    # HA JSON numerics: neither booleans, numeric strings nor cached UI text.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScheduleValidationError("temperature must be a real JSON number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ScheduleValidationError("temperature must be finite")
    if not 5 <= value <= 35:
        raise ScheduleValidationError("temperature outside 5..35 Celsius")
    scaled = Decimal(str(value)) * 100
    if scaled != scaled.to_integral_value():
        raise ScheduleValidationError("temperature has sub-centi-C precision")
    return int(scaled)


def _second_of_day(value: object, *, is_end: bool) -> int:
    if isinstance(value, str):
        if is_end and value in ("24:00", "24:00:00"):
            return 86400
        if _TIME_PATTERN.fullmatch(value) is None or int(value[:2]) >= 24:
            # Python 3.14 accepts ISO 24:00 and normalizes it to 00:00.
            # Only the explicit end-of-day forms above mean 86400 here.
            raise ScheduleValidationError("invalid time string")
        try:
            value = time.fromisoformat(value)
        except ValueError as err:
            raise ScheduleValidationError("invalid clock time") from err
    if not isinstance(value, time) or value.tzinfo is not None:
        raise ScheduleValidationError("block time must be a local time without timezone")
    # Native schedule.get_schedule returns time.max for end-of-day.
    if is_end and value == time.max:
        return 86400
    if value.microsecond:
        raise ScheduleValidationError("sub-second block times are unsupported")
    return value.hour * 3600 + value.minute * 60 + value.second


def _normalize_week(week: object) -> tuple[tuple[Block, ...], ...]:
    if not isinstance(week, Mapping) or any(key not in WEEKDAYS for key in week):
        raise ScheduleValidationError("week must be a weekday mapping")
    count = 0
    normalized = []
    for weekday in WEEKDAYS:
        raw_blocks = week.get(weekday, [])
        if not isinstance(raw_blocks, (list, tuple)):
            raise ScheduleValidationError("day must be a block list")
        count += len(raw_blocks)
        if count > MAX_WEEK_BLOCKS:
            raise ScheduleValidationError("more than 28 blocks per week")
        blocks = []
        for block in raw_blocks:
            if not isinstance(block, Mapping) or "from" not in block or "to" not in block:
                raise ScheduleValidationError("block needs from and to")
            start = _second_of_day(block["from"], is_end=False)
            end = _second_of_day(block["to"], is_end=True)
            if not 0 <= start < end <= 86400:
                raise ScheduleValidationError("invalid block range; split at midnight")
            data = block.get("data")
            if not isinstance(data, Mapping) or "temperature" not in data:
                raise ScheduleValidationError("block needs data.temperature")
            blocks.append((start, end, _temperature(data["temperature"])))
        blocks.sort()
        previous_end = 0
        for start, end, _ in blocks:
            if start < previous_end:
                raise ScheduleValidationError("overlapping blocks")
            previous_end = end
        normalized.append(tuple(blocks))
    return tuple(normalized)


def _zone_and_window(tz_name: object, start: object, end: object) -> ZoneInfo:
    if (not isinstance(tz_name, str) or len(tz_name) > MAX_TIMEZONE_NAME_BYTES
            or TIMEZONE_NAME_PATTERN.fullmatch(tz_name) is None):
        raise ScheduleValidationError("time zone must be an IANA time zone name such as Europe/Berlin")
    if type(start) is not int or type(end) is not int:
        raise ScheduleValidationError("UTC bounds must be integer POSIX seconds")
    if not MIN_UTC_SECOND <= start < end <= MAX_UTC_SECOND:
        raise ScheduleValidationError("UTC window must lie within 2000..2099")
    if end - start > MAX_HORIZON_SECONDS:
        raise ScheduleValidationError("horizon exceeds 16 UTC days")
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as err:
        raise ScheduleValidationError(
            f"time zone {tz_name} is unknown to the system IANA time zone data") from err


def _offset_at(second: int, zone: ZoneInfo) -> timedelta:
    offset = datetime.fromtimestamp(second, UTC).astimezone(zone).utcoffset()
    assert offset is not None
    return offset


def _offset_boundaries(start: int, end: int, zone: ZoneInfo) -> set[int]:
    if zone.key == "UTC":
        return set()
    result: set[int] = set()
    left = start
    old_offset = _offset_at(left, zone)
    while left < end - 1:
        right = min(left + _OFFSET_SCAN_SECONDS, end - 1)
        new_offset = _offset_at(right, zone)
        if old_offset != new_offset:
            # tzdb never changes an offset twice within one minute.
            lo, hi = left, right
            while hi - lo > 1:
                middle = (lo + hi) // 2
                if _offset_at(middle, zone) == old_offset:
                    lo = middle
                else:
                    hi = middle
            result.add(hi)
        left, old_offset = right, new_offset
    return result


def _local_instants(day: date, second: int, zone: ZoneInfo) -> set[int]:
    naive = datetime.combine(day, time()) + timedelta(seconds=second)
    result = set()
    for fold in (0, 1):
        local = naive.replace(tzinfo=zone, fold=fold)
        utc = local.astimezone(UTC)
        # Reject the synthetic mappings zoneinfo permits for nonexistent times.
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            result.add(int(utc.timestamp()))
    return result


def compile_week(
    week: Mapping[str, Any],
    base_centi_c: int,
    tz_name: str,
    valid_from_utc: int,
    valid_until_utc: int,
) -> dict[str, Any]:
    """Compile a native HA week into a bounded, deterministic wire document.

    Bounds are integer POSIX UTC seconds, start inclusive/end exclusive.
    Missing days and gaps use base_centi_c. Each supplied block MUST have a
    finite numeric data.temperature in Celsius, exactly representable in
    centi-C. Empty days are valid. No input is modified.

    The first transition always occurs at valid_from_utc with the actual
    active target. Equal targets are coalesced; no transition is emitted at
    valid_until_utc. That explicit expiry is NOT an instruction to hold the
    last target forever.
    """
    base = _centi_base(base_centi_c)
    zone = _zone_and_window(tz_name, valid_from_utc, valid_until_utc)
    normalized = _normalize_week(week)
    boundaries = {valid_from_utc}
    boundaries.update(_offset_boundaries(valid_from_utc, valid_until_utc, zone))
    first_day = datetime.fromtimestamp(valid_from_utc, UTC).astimezone(zone).date()
    last_day = datetime.fromtimestamp(valid_until_utc - 1, UTC).astimezone(zone).date()
    day = first_day - timedelta(days=1)
    while day <= last_day + timedelta(days=1):
        for start, end, _ in normalized[day.weekday()]:
            boundaries.update(_local_instants(day, start, zone))
            boundaries.update(_local_instants(day, end, zone))
        day += timedelta(days=1)

    transitions: list[list[int]] = []
    for second in sorted(boundaries):
        if not valid_from_utc <= second < valid_until_utc:
            continue
        local = datetime.fromtimestamp(second, UTC).astimezone(zone)
        wall_second = local.hour * 3600 + local.minute * 60 + local.second
        target = base
        for start, end, temperature in normalized[local.weekday()]:
            if start <= wall_second < end:
                target = temperature
                break
        if not transitions or transitions[-1][1] != target:
            transitions.append([second, target])
            if len(transitions) > MAX_TRANSITIONS:
                raise ScheduleValidationError("more than 128 coalesced transitions")
    return {
        "timezone": tz_name,
        "policy": POLICY,
        "valid_from_utc": valid_from_utc,
        "valid_until_utc": valid_until_utc,
        "base_centi_c": base,
        "transitions": transitions,
    }


async def async_get_schedule_week(hass: Any, entity_id: str) -> dict[str, Any]:
    """Read a selected native helper using HA 2026.10.2's public action.

    This does not create/update helpers or read private storage. Snapshot
    containers are copied because in-process responses contain native times
    and may share nested objects with the helper's current configuration.
    """
    if not isinstance(entity_id, str) or _ENTITY_PATTERN.fullmatch(entity_id) is None:
        raise ScheduleValidationError("select one schedule entity")
    async with asyncio.timeout(_EXPORT_TIMEOUT_SECONDS):
        response = await hass.services.async_call(
            "schedule",
            "get_schedule",
            {"entity_id": entity_id},
            blocking=True,
            return_response=True,
        )
    if not isinstance(response, Mapping) or entity_id not in response:
        raise ScheduleValidationError("native action returned no selected schedule")
    week = response[entity_id]
    if not isinstance(week, Mapping):
        raise ScheduleValidationError("native schedule response must be a mapping")
    return deepcopy(dict(week))


async def async_compile_schedule(
    hass: Any,
    entity_id: str,
    base_centi_c: int,
    tz_name: str,
    valid_from_utc: int,
    valid_until_utc: int,
) -> dict[str, Any]:
    """Read a helper and offload finite CPU work; no timers or listeners."""
    week = await async_get_schedule_week(hass, entity_id)
    return await hass.async_add_executor_job(
        compile_week, week, base_centi_c, tz_name, valid_from_utc, valid_until_utc
    )
