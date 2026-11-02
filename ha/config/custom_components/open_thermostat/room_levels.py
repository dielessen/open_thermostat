"""The week planner's levels in the E32 room plan (E32 beta.23, "plan.levels.v1").

Per room the plan can carry ``levels`` {comfort, eco, night} (centi °C, set
independently: equal values and any order are allowed) and, with a week
program, ``schedule_levels``: one digit per switch point (0 own temperature,
1 Comfort, 2 Eco, 3 Night), days separated by '.'. A marked point always has
its level's temperature; control only uses the temperatures. The E32 names
the feature in ``features`` of GET /config/heating; older firmware ignores
both fields, so HA only sends them to firmware that names it.

Every plan HA writes goes through ``normalize``: a program changed elsewhere
(options flow, setting device) gets marks that fit it again, so the E32 never
refuses a plan for stale marks.
"""
from __future__ import annotations

FEATURE = "plan.levels.v1"
LEVELS = ("comfort", "eco", "night")


def supported(plan):
    """True when the E32 that answered this plan stores levels."""
    features = plan.get("features") if type(plan) is dict else None
    return type(features) is list and FEATURE in features


def valid_levels(value, low=500, high=3000):
    """The levels as a dict of three whole centi °C within the room's limits, else None."""
    if type(value) is not dict:
        return None
    out = {key: value.get(key) for key in LEVELS}
    if any(type(v) is not int or not low <= v <= high for v in out.values()):
        return None
    return out


def _program(room):
    schedule = room.get("schedule")
    return schedule if type(schedule) is list and len(schedule) == 7 and any(schedule) else None


def mark_text(schedule, levels, text=None):
    """The "schedule_levels" for this program: the given digits when they fit the program and the
    levels (as the planner stored them), otherwise the first level with each point's temperature."""
    days = text.split(".") if type(text) is str else None
    fits = (days is not None and len(days) == 7 and all(
        len(digits) == len(schedule[d]) and all(ch in "0123" for ch in digits)
        and all(ch == "0" or schedule[d][i][1] == levels[LEVELS[int(ch) - 1]] for i, ch in enumerate(digits))
        for d, digits in enumerate(days)))
    if fits:
        return text
    return ".".join("".join(next((str(n + 1) for n, key in enumerate(LEVELS) if levels[key] == point[1]), "0")
                            for point in day) for day in schedule)


def room_levels(room):
    """The room's stored levels (validated against its limits), or None."""
    return valid_levels(room.get("levels"), room.get("minimum_centi_c", 500), room.get("maximum_centi_c", 3000))


def normalize(plan):
    """The plan as HA posts it: levels only for an E32 that stores them, marks that fit each program,
    and without the read-only "features"."""
    keep = supported(plan)
    plan.pop("features", None)
    for room in plan.get("rooms", []):
        if type(room) is not dict:
            continue
        levels = room_levels(room) if keep else None
        if levels is None:
            room.pop("levels", None)
            room.pop("schedule_levels", None)
            continue
        room["levels"] = levels
        schedule = _program(room)
        if schedule is None:
            room.pop("schedule_levels", None)
        else:
            room["schedule_levels"] = mark_text(schedule, levels, room.get("schedule_levels"))
    return plan
