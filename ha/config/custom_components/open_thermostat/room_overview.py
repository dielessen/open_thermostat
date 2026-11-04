"""Per E32 room, in plain words: why it heats or not (OpenThermostat 1.1).

``room_reason`` is a pure function of what the E32 already reports: the room
(``fw/state/room/<id>``: state, status, temperature, setpoint, demand and, while
it deviates from its plan, ``comfort``) and the house (``fw/state/heating``:
mode, request, away, burner activity). Home Assistant adds only the name and
the opening time of an open window or door contact; the E32 decides whether
the room is paused. The E32 overview page (data/html/index.html, roomWhy)
makes the same choice with the same words.

The "Reason" sensor of each room shows the reason as its state (a timeline in
the history) and the sentence variant and its values as attributes; the room
status card (frontend/room-status-card.js) writes the sentence from
strings.json (``entity.sensor.room_reason.state_attributes.line``), so every
viewer reads it in their own language.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity

from .heating_link import RoomEntity, number

# The room status card's module (served and loaded with the week planner's, week_planner.card_modules).
CARD_URL = "/open_thermostat/room-status-card-1.0.0rc5.js"
# The reasons, in the order they win: a room that is off or paused says so before
# anything else; a room that wants heat but waits for the boiler says why it waits;
# then the mode that sets its target (away, boost); then what it does.
REASONS = ["off", "window_open", "window_pending", "no_measurement", "hot_water", "boiler_pause",
           "warm_up", "away_return", "holiday", "away", "room_away", "house_away", "boost", "temporary",
           "heating", "wants_heat", "warm_enough"]
# The sentence of each variant (strings.json state_attributes.line) and the values it uses.
LINES = {
    "off": (), "window_open": (), "window_open_contact": ("contact", "since"),
    "window_pending": (), "window_pending_contact": ("contact",), "no_measurement": (),
    "hot_water": (), "boiler_pause": (), "warm_up": ("time", "target"), "away_return": (), "holiday": ("until", "target"),
    "away": ("target",), "room_away": ("target",), "house_away": ("target",),
    "boost": (), "boost_until": ("until",), "temporary": ("target",), "temporary_until": ("target", "until"),
    "heating": ("temperature", "target"), "wants_heat": ("temperature", "target"),
    "warm_enough": ("temperature", "target"), "no_heat_needed": (),
}
# burner.activity (E32 beta.23) while the boiler serves hot water instead of the rooms.
HOT_WATER = ("tapping", "keep_warm", "charging", "hot_water")
PRESENCE = ["room_home", "room_away", "house_home", "house_away"]


@dataclass(frozen=True, slots=True)
class OpenContact:
    """An open window or door contact of the room as Home Assistant sees it."""
    name: str
    since: datetime | None = None


@dataclass(frozen=True, slots=True)
class RoomReason:
    reason: str
    line: str
    values: dict = field(default_factory=dict)


def _dict(value):
    return value if type(value) is dict else {}


def _utc(value):
    return datetime.fromtimestamp(value, timezone.utc) if type(value) is int and value > 0 else None


def room_reason(room, status=None, contact=None, warmup=None):
    """Why the room heats or not: a RoomReason, or None without a room.

    room: one room of the E32 status; status: the house (mode, request, away,
    burner); contact: the OpenContact HA sees open in this room (only used
    while the E32 itself reports the window open or pending).
    """
    if type(room) is not dict:
        return None
    status, comfort = _dict(status), _dict(room.get("comfort"))
    temperature = number(room.get("temperature"), -40, 85)
    target = number(room.get("setpoint"), 5, 35)
    mode_target = number(comfort.get("target_c"), 5, 35)
    mode = comfort.get("mode")

    def reason(key, line=None, **values):
        line = line or key
        return RoomReason(key, line, {name: values.get(name) for name in LINES[line]})

    if room.get("state") == "inactive":
        return reason("off")  # the E32's frost protection still covers it
    window = comfort.get("window")
    if window == "open" or mode == "window_open":
        if contact is not None:
            return reason("window_open", "window_open_contact", contact=contact.name, since=contact.since)
        return reason("window_open")
    if window == "pending":
        if contact is not None:
            return reason("window_pending", "window_pending_contact", contact=contact.name)
        return reason("window_pending")
    if room.get("status") == "lost" or temperature is None:
        return reason("no_measurement")
    demand = room.get("demand") is True
    active = status.get("mode") == "active"
    if demand and _dict(status.get("burner")).get("activity") in HOT_WATER:
        return reason("hot_water")
    if demand and active and _dict(status.get("request")).get("reason") == "minimum_off":
        return reason("boiler_pause")
    start = _dict(warmup)
    switch = _dict(start.get("next_switch"))
    if (demand and start.get("start_now") is True and start.get("applies") is True and mode in (None, "program")
            and _utc(switch.get("utc")) and number(switch.get("target_c"), 5, 35) is not None):
        return reason("warm_up", time=_utc(switch["utc"]), target=number(switch["target_c"], 5, 35))
    until = _utc(comfort.get("until"))
    away_target = mode_target if mode_target is not None else number(_dict(status.get("away")).get("target_c"), 5, 25)
    if mode == "away_return":
        return reason("away_return")
    if mode == "away":
        return reason("holiday", until=until, target=away_target) if until else reason("away", target=away_target)
    if mode == "presence_away":
        # The room's own persons when the E32 has a fresh report of them, else everyone of the house.
        # rc.3 names it (away_by); older firmware: its own persons away while the house is not.
        own = comfort.get("away_by") == "room" if comfort.get("away_by") in ("room", "house") else comfort.get("persons") == "away"
        return reason("room_away" if own else "house_away", target=away_target)
    if mode == "boost":
        return reason("boost", "boost_until", until=until) if until else reason("boost")
    if mode in ("timed", "next"):
        held = mode_target if mode_target is not None else target
        return (reason("temporary", "temporary_until", target=held, until=until) if until
                else reason("temporary", target=held))
    if demand:
        # In shadow mode the old thermostat still runs the boiler: the room wants heat, the E32 does not heat.
        return reason("heating" if active else "wants_heat", temperature=temperature, target=target)
    if target is None:
        return reason("warm_enough", "no_heat_needed")
    return reason("warm_enough", temperature=temperature, target=target)


def room_presence(room, status=None):
    """Whether someone is home for this room: its own persons (room_*), else the house (house_*), else None."""
    persons = _dict(_dict(room).get("comfort")).get("persons")
    if persons in ("home", "away"):
        return "room_" + persons
    presence = _dict(_dict(status).get("away")).get("presence")
    return "house_" + presence if presence in ("home", "away") else None


def open_contact(hass, entity_ids):
    """The contact of the room that has been open longest (with the others' names), or None."""
    opened = [state for state in (hass.states.get(e) for e in entity_ids) if state is not None and state.state == "on"]
    if not opened:
        return None
    opened.sort(key=lambda state: state.last_changed)
    names = [state.name for state in opened]
    # Two names at most; more open contacts are counted ("Back door, Kitchen window +1").
    name = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
    return OpenContact(name, opened[0].last_changed)


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


class RoomReasonSensor(RoomEntity, SensorEntity):
    """Why the room heats or not; the attributes carry the sentence for the room status card."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = REASONS
    _attr_icon = "mdi:comment-question-outline"
    # The card's live values; the history keeps the reason itself (the room's own sensors keep the rest).
    _unrecorded_attributes = frozenset({"values", "temperature", "setpoint", "presence", "window", "valve_position",
                                        "valve_problem"})

    def __init__(self, hub, room):
        self._attach_room(hub, room, "reason")

    def _contact(self):
        entry = getattr(getattr(self, "platform", None), "config_entry", None)
        if entry is None or self.hass is None:
            return None
        from .e32_comfort import room_contacts
        return open_contact(self.hass, room_contacts(entry, self.room_id))

    def _reason(self):
        room = self.room
        if not room or not self.hub.fresh:
            return None
        window = _dict(room.get("comfort")).get("window")
        warmup = self.hub.warmup.get(self.room_id) if type(getattr(self.hub, "warmup", None)) is dict else None
        start = warmup.get("optimum_start") if type(warmup) is dict else None
        return room_reason(room, self.hub.status, self._contact() if window in ("open", "pending") else None, start)

    @property
    def native_value(self):
        reason = self._reason()
        return reason.reason if reason else None

    @property
    def extra_state_attributes(self):
        reason = self._reason()
        if reason is None:
            return None
        from .e32_valves import positions, problems, room_valves
        room, valves = self.room, room_valves(self.hub, self.room_id) or {}
        moved = positions(valves)
        # values: the sentence's own (an away line's target is the away temperature, not the setpoint).
        return {"room_id": self.room_id, "line": reason.line,
                "values": {key: _iso(value) for key, value in reason.values.items()},
                "temperature": number(room.get("temperature"), -40, 85), "setpoint": number(room.get("setpoint"), 5, 35),
                "presence": room_presence(room, self.hub.status),
                "window": _dict(room.get("comfort")).get("window"),
                "valve_position": round(sum(moved) / len(moved)) if moved else None,
                "valve_problem": bool(problems(valves)) if valves else None}
