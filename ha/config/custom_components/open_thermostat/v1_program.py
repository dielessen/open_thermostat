"""Pure local week editing model; native HA flow is the editor, firmware evaluates."""
from __future__ import annotations

from copy import deepcopy
from datetime import time
from .schedule_compiler import WEEKDAYS, MAX_WEEK_BLOCKS

def normalize_program(value, minimum=500, maximum=3500):
    """Persist integer-only day blocks, independent of HA/cache/wire/runtime."""
    if not isinstance(value, dict) or set(value) - set(WEEKDAYS):
        raise ValueError("invalid_program")
    normalized = {}
    count = 0
    for day in WEEKDAYS:
        blocks = value.get(day, [])
        if not isinstance(blocks, list):
            raise ValueError("invalid_program")
        day_blocks = []
        for block in blocks:
            if not isinstance(block, dict) or set(block) != {"start", "end", "target_centi_c"}:
                raise ValueError("invalid_program")
            start, end, target = (block[k] for k in ("start", "end", "target_centi_c"))
            if (any(type(v) is not int for v in (start, end, target))
                    or not 0 <= start < end <= 86400):
                raise ValueError("invalid_program_time")
            if not minimum <= target <= maximum:
                raise ValueError("invalid_target_range")
            day_blocks.append(dict(block))
        day_blocks.sort(key=lambda b: b["start"])
        if any(b["start"] < a["end"] for a, b in zip(day_blocks, day_blocks[1:])):
            raise ValueError("program_overlap")
        count += len(day_blocks)
        if count > MAX_WEEK_BLOCKS:
            raise ValueError("program_limit")
        normalized[day] = day_blocks
    return normalized

def native_week(program):
    """Convert accepted integer storage to the existing compiler's native shape."""
    program = normalize_program(program)
    def clock(second):
        return "24:00:00" if second == 86400 else time(second // 3600, second % 3600 // 60, second % 60).isoformat()
    return {day: [{"from": clock(b["start"]), "to": clock(b["end"]),
                   "data": {"temperature": b["target_centi_c"] / 100}} for b in blocks]
            for day, blocks in program.items()}

def clock_second(value):
    # HA's TimeSelector returns an ISO local-time string; seconds only, no offset.
    if not isinstance(value, str):
        raise ValueError("invalid_program_time")
    try:
        result = time.fromisoformat(value)
    except ValueError as err:
        raise ValueError("invalid_program_time") from err
    if result.tzinfo is not None or result.microsecond or value.startswith("24:"):
        raise ValueError("invalid_program_time")
    return result.hour * 3600 + result.minute * 60 + result.second

def change_block(program, days, start, end, target, minimum, maximum, replace=None):
    if (not isinstance(days, list) or not days or len(set(days)) != len(days)
            or any(day not in WEEKDAYS for day in days)):
        raise ValueError("invalid_program")
    candidate = deepcopy(program)
    if replace is not None:
        day, index = replace
        candidate[day].pop(index)
    for day in days:
        candidate.setdefault(day, []).append({"start": start, "end": end, "target_centi_c": target})
    return normalize_program(candidate, minimum, maximum)
