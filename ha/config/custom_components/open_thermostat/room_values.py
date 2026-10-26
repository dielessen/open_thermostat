"""Decode reported room values without turning invalid data into measurements."""
import math

_DIVISORS = {'currentTemp': 100, 'tempSet': 100, 'currentHumidity': 100, 'batteryLevel': 1}


def room_value(field: str, value: object) -> float | None:
    """Preserve Celsius/percent scaling; missing, sentinel and bad numbers stay unknown."""
    if type(value) not in (int, float):
        return None
    try:
        if not math.isfinite(value):
            return None
        result = value / _DIVISORS[field]
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    # Use the same conservative physical envelope as the existing temperature
    # telemetry. Wire sentinels (e.g. +/-32768) must never enter HA statistics.
    if field in ('currentTemp', 'tempSet') and not -60 <= result <= 130:
        return None
    if field in ('currentHumidity', 'batteryLevel') and not 0 <= result <= 100:
        return None
    return result
