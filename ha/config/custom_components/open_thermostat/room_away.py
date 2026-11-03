"""A room's own away temperature in the E32 room plan (E32 after 1.0.0-rc.2, "plan.room_away.v1").

Per room the plan can carry ``away_centi_c`` (5–25 °C in centi °C, optional).
The E32 uses it while all of the room's own persons (Configure → Rooms → the
room → Persons) are away and someone else is home. When everyone is away, and
in the house modes Away and Holiday, every room uses the house away
temperature ("Temperature when nobody is home"); a room without its own value
always does. The value is a ceiling, like the house value: a room whose program
is already cooler stays cooler. House mode At home ignores presence.

It lives in the plan, so it works without Home Assistant, is part of the E32's
settings backup and survives a restore. The E32 names the feature in
``features`` of GET /config/heating; older firmware ignores the field (also
after a rollback), so Home Assistant offers and sends it only to firmware that
names it. Its room status says why a room is cooler: ``comfort.away_by``
"room" (its own persons) or "house" (everyone away).
"""
from __future__ import annotations

FEATURE = "plan.room_away.v1"
FIELD = "away_centi_c"
LIMITS_CENTI_C = (500, 2500)  # RoomPlan::minimumAwayCentiC .. maximumAwayCentiC


def supported(plan):
    """True when the E32 that answered this plan stores a room's own away temperature."""
    features = plan.get("features") if type(plan) is dict else None
    return type(features) is list and FEATURE in features


def room_away(room):
    """The room's own away temperature in centi °C, or None (the house value)."""
    value = room.get(FIELD) if type(room) is dict else None
    return value if type(value) is int and LIMITS_CENTI_C[0] <= value <= LIMITS_CENTI_C[1] else None


def normalize(plan, keep):
    """The rooms as Home Assistant posts them: the value only for an E32 that stores it, and only valid."""
    for room in plan.get("rooms", []) if type(plan) is dict else []:
        if type(room) is dict and (not keep or room_away(room) is None):
            room.pop(FIELD, None)
    return plan


def away_reason(comfort, away):
    """Why a room is cooler, for its thermostat: room_persons, everyone, house_mode or None.

    ``comfort``: the room's comfort status; ``away``: the house's away status. Firmware before
    plan.room_away.v1 has no ``away_by``: its own persons away while the house is not counts as the room.
    """
    mode = comfort.get("mode") if type(comfort) is dict else None
    if mode in ("away", "away_return"):
        return "house_mode"
    if mode != "presence_away":
        return None
    by = comfort.get("away_by")
    if by in ("room", "house"):
        return "room_persons" if by == "room" else "everyone"
    house = away.get("presence") if type(away) is dict else None
    return "room_persons" if comfort.get("persons") == "away" and house != "away" else "everyone"
