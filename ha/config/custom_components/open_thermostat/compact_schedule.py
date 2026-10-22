"""Versioned UTC schedule representation; the existing firmware evaluates it.

Each point uses six URL-safe base64 digits: 24 bits of second offset followed
by 12 bits of temperature. Chunks contain at most ten points, so every JSON
string stays below the existing 64-byte bound. No padding or truncation.
"""
from .graph_shadow_validation import GraphValidationError

POLICY = "wall-clock-packed/v1"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
MAX_TRANSITIONS = 128


def _require(ok):
    if not ok:
        raise GraphValidationError("native_compact_schedule")


def expand_schedule(schedule):
    _require(type(schedule) is dict and set(schedule) == {
        "base_centi_c", "policy", "timezone", "transitions", "valid_from_utc", "valid_until_utc"})
    _require(schedule["policy"] == POLICY and schedule["timezone"] in ("UTC", "Europe/Amsterdam"))
    start, end, base = (schedule[k] for k in ("valid_from_utc", "valid_until_utc", "base_centi_c"))
    _require(type(start) is type(end) is type(base) is int
             and 946684800 <= start < end <= 4102444800
             and end-start <= 16*86400 and 500 <= base <= 3500)
    chunks = schedule["transitions"]
    _require(type(chunks) is list and 1 <= len(chunks) <= 13)
    points = []
    previous = start-1
    for index, chunk in enumerate(chunks):
        _require(type(chunk) is str and 6 <= len(chunk) <= 60 and len(chunk) % 6 == 0
                 and (index == len(chunks)-1 or len(chunk) == 60))
        for offset in range(0, len(chunk), 6):
            value = 0
            for char in chunk[offset:offset+6]:
                _require(char in ALPHABET)
                value = (value << 6) | ALPHABET.index(char)
            at, target = start+(value >> 12), value & 4095
            _require(start <= at < end and at > previous and 500 <= target <= 3500)
            points.append([at, target])
            previous = at
    _require(1 <= len(points) <= MAX_TRANSITIONS and points[0][0] == start)
    return {**schedule, "policy": "wall-clock-membership/v1", "transitions": points}


def compact_schedule(schedule):
    _require(type(schedule) is dict and schedule.get("policy") == "wall-clock-membership/v1")
    points = schedule.get("transitions")
    _require(type(points) is list and 1 <= len(points) <= MAX_TRANSITIONS)
    start = schedule.get("valid_from_utc")
    _require(type(start) is int)
    encoded = []
    for point in points:
        _require(type(point) is list and len(point) == 2 and all(type(v) is int for v in point))
        at, target = point
        _require(0 <= at-start < 1 << 24 and 500 <= target <= 3500)
        value = ((at-start) << 12) | target
        encoded.append("".join(ALPHABET[(value >> shift) & 63] for shift in (30, 24, 18, 12, 6, 0)))
    chunks = ["".join(encoded[i:i+10]) for i in range(0, len(encoded), 10)]
    result = {**schedule, "policy": POLICY, "transitions": chunks}
    _require(expand_schedule(result) == schedule)
    return result
