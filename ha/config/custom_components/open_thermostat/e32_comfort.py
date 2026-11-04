"""A Home Assistant thermostat per E32 room, temporary overrides, window/door pauses and away.

The rooms live in the E32 room plan and the E32 computes their demand, also
without Home Assistant. This module adds, on top of that plan (E32 beta.19,
``src/control/RoomOverrides.h``):

- one ``climate`` entity per E32 room (thermostat card, voice assistants):
  current temperature, target, mode auto / heat / off and the presets comfort,
  eco, sleep (shown as "Night") and boost: the room's week planner levels
  (stored per room since E32 beta.23, see room_levels; inferred for older
  firmware). "Away" is the house mode only, not a room preset. "Off" makes the room inactive in the room plan; a new
  target becomes an override "until the next switch point" of the room's week
  program (or for the configured time when the room has no program); a room
  with only a fixed target changes that target in the plan.
- the actions ``set_room_override`` / ``clear_room_override`` (boost, "2 h at
  21 °C", until the next switch point) and ``set_away`` / ``clear_away`` (a
  lower temperature for the whole house, optionally until a date). The E32
  ends every override itself, also after a restart, and returns the room to
  its week program; a dated away ends early enough to be warm again on time.
- the optional window/door contacts per room and the people of the house
  (beta.23: several person entities; "everyone away" only after all of them
  have been away for the away delay, and never while one of them is unknown),
  forwarded to the E32 over ``<base>ha/heating_input`` as one aggregated value
  (the same message E32 beta.21 understands)::

      {"kind": "contact", "room": "living", "open": true, "delay_s": 120}
      {"kind": "presence", "home": false}
      {"kind": "room_presence", "room": "bedroom", "home": false}

  The last one (beta.23, room.presence.v1) only for a room with its own persons
  (Configure → Rooms → the room → Persons), with the same rule as the house: home
  while one of them is home or unknown, away once all have been away for the
  away delay. It is sent only to an E32 that announces it (away.room_presence);
  an older E32 would not consume it anyway.

  on every change and every five minutes. Any open contact of a room counts as
  open; the E32 pauses the room after the delay (its frost limit stays) and
  resumes when all are closed. Unknown states are not sent: the E32 then
  forgets the report after 15 minutes and the room heats normally.

The entity reads the room from the E32 telemetry (``fw/state/room/<id>``: the
room's ``temperature``, ``setpoint``, ``state``, ``demand`` and, while it
deviates from its plan, ``comfort``; ``fw/state/heating``: ``away``) through the
entry's HeatingHub. Commands go over the stored controller connection
(``POST /config/heating/comfort``); plan changes through the room-plan writer.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import time

from homeassistant.components import mqtt
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    PRESET_BOOST, PRESET_COMFORT, PRESET_ECO, PRESET_NONE, PRESET_SLEEP, ClimateEntityFeature, HVACAction, HVACMode)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import selector
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .heating_link import RoomEntity, add_options, heating_hub, number, track_entities
from .room_levels import room_levels

CONF_COMFORT = "comfort_settings"
DEFAULTS = {"presence_entity": None, "presence_entities": [], "away_delay_min": 15,
            "comfort_c": 20.0, "eco_c": 16.0,  # the week planner's defaults
            "contact_delay_s": 120,
            # Per room (beta.23): {room id: seconds}; a room without its own delay uses contact_delay_s.
            "contact_delays": {},
            "override_minutes": 120, "contacts": {},
            # Persons per room (beta.23): {room id: [person entity ids]}; a room without uses the house.
            "room_persons": {}}
TEMPERATURE_LIMITS = (5.0, 30.0)
AWAY_LIMITS = (5.0, 25.0)
DELAY_LIMITS = (0, 1800)       # the E32's own bound (RoomOverrides::maxContactDelayS)
MINUTES_LIMITS = (1, 1440)     # the E32's own bound (RoomOverrides::maxMinutes)
AWAY_DELAY_LIMITS = (0, 240)   # minutes everyone must be away before the house counts as away
MAX_PRESENCE = 16
MAX_CONTACTS = 8
MAX_AWAY_DAYS = 366
REFRESH = timedelta(minutes=5)
# A new target shows while its write runs (also while it waits for a free E32 web
# session), then at most this long until the telemetry reports it.
PENDING_SECONDS = 60
CONTACT_CLASSES = ("window", "door", "opening", "garage_door")
# No "away" preset per room (owner, 31 Oct 2026): away is the house mode (e32_house.py), not one room's choice.
PRESETS = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_SLEEP, PRESET_BOOST]
# Preset -> index in program_levels(): the planner's Comfort, Eco and Night.
LEVEL_PRESETS = {PRESET_COMFORT: 0, PRESET_ECO: 1, PRESET_SLEEP: 2}
OVERRIDES = ("boost", "timed", "next")
AWAY_MODES = ("away", "presence_away", "away_return")
# The E32's refusals that have their own message; the rest name the E32's code.
E32_ERRORS = {"no_clock": "comfort_no_clock", "room_inactive": "comfort_room_off",
              "no_schedule": "comfort_no_schedule"}
# The same no-reload flag as the energy step (__init__._async_options_updated).
from .energy_input import ENERGY_ONLY_UPDATE  # noqa: E402


# -- options ---------------------------------------------------------------------


def comfort_options(entry):
    """The comfort settings with defaults; unknown or invalid values fall back to the default."""
    raw = (getattr(entry, "options", None) or {}).get(CONF_COMFORT)
    raw = raw if type(raw) is dict else {}
    out = dict(DEFAULTS)
    presence = raw.get("presence_entity")
    if type(presence) is str and "." in presence:
        out["presence_entity"] = presence
    # Several people since beta.23; an older single presence entity becomes a list of one.
    people = raw.get("presence_entities")
    if type(people) is list:
        out["presence_entities"] = [e for e in people if type(e) is str and "." in e][:MAX_PRESENCE]
    elif out["presence_entity"]:
        out["presence_entities"] = [out["presence_entity"]]
    if type(raw.get("away_delay_min")) is int and AWAY_DELAY_LIMITS[0] <= raw["away_delay_min"] <= AWAY_DELAY_LIMITS[1]:
        out["away_delay_min"] = raw["away_delay_min"]
    for key, (low, high) in (("comfort_c", TEMPERATURE_LIMITS), ("eco_c", TEMPERATURE_LIMITS)):
        if number(raw.get(key), low, high) is not None:
            out[key] = float(raw[key])
    for key, (low, high) in (("contact_delay_s", DELAY_LIMITS), ("override_minutes", MINUTES_LIMITS)):
        if type(raw.get(key)) is int and low <= raw[key] <= high:
            out[key] = raw[key]
    delays = raw.get("contact_delays")
    if type(delays) is dict:
        out["contact_delays"] = {room: s for room, s in delays.items()
                                 if type(room) is str and type(s) is int and DELAY_LIMITS[0] <= s <= DELAY_LIMITS[1]}
    contacts = raw.get("contacts")
    if type(contacts) is dict:
        out["contacts"] = {room: [e for e in ids if type(e) is str and e.startswith("binary_sensor.")][:MAX_CONTACTS]
                           for room, ids in contacts.items() if type(room) is str and type(ids) is list}
    persons = raw.get("room_persons")
    if type(persons) is dict:
        out["room_persons"] = {
            room: [e for e in ids if type(e) is str and e.split(".")[0] in PRESENCE_DOMAINS][:MAX_PRESENCE]
            for room, ids in persons.items() if type(room) is str and type(ids) is list}
    return out


class ComfortError(ValueError):
    def __init__(self, field, code):
        super().__init__(code)
        self.field, self.code = field, code


def validate_presence(hass, user_input, current):
    """The people of the house and the away delay (Configure → Home → Presence)."""
    out = dict(current)
    people = user_input.get("presence_entities") or []
    if (type(people) is not list or len(people) > MAX_PRESENCE or len(set(people)) != len(people)
            or any(type(e) is not str or e.split(".")[0] not in PRESENCE_DOMAINS for e in people)):
        raise ComfortError("presence_entities", "presence_entity_invalid")
    for entity_id in people:  # a person already chosen may be unavailable now (a phone off); a new one must exist
        if entity_id not in current["presence_entities"] and hass.states.get(entity_id) is None:
            raise ComfortError("presence_entities", "presence_entity_invalid")
    delay = number(user_input.get("away_delay", out["away_delay_min"]), *AWAY_DELAY_LIMITS)
    if delay is None or delay != int(delay):
        raise ComfortError("away_delay", "whole_number_invalid")
    out["presence_entities"] = list(people)
    # HA 0.4.0b13 and older read one entity: the first person (a downgrade then follows that person only).
    out["presence_entity"] = people[0] if people else None
    out["away_delay_min"] = int(delay)
    return out


def validate_settings(hass, user_input, current):
    """The comfort settings from the options form (preset temperatures, delay, duration)."""
    out = dict(current)
    for field, key, limits in (("comfort_temperature", "comfort_c", TEMPERATURE_LIMITS),
                               ("eco_temperature", "eco_c", TEMPERATURE_LIMITS)):
        value = number(user_input.get(field, out[key]), *limits)
        if value is None:
            raise ComfortError(field, "temperature_invalid")
        out[key] = round(value * 2) / 2
    for field, key, limits in (("contact_delay", "contact_delay_s", DELAY_LIMITS),
                               ("override_minutes", "override_minutes", MINUTES_LIMITS)):
        value = number(user_input.get(field, out[key]), *limits)
        if value is None or value != int(value):
            raise ComfortError(field, "whole_number_invalid")
        out[key] = int(value)
    return out


def validate_contacts(hass, selections, known=()):
    """Window/door/opening binary sensors for one room (at most eight).

    Any brand works: Zigbee, Z-Wave, Shelly, Bluetooth or a template, as long as
    Home Assistant gives it the device class window, door, opening or garage door.
    known: the room's sensors so far; they stay accepted while they are
    unavailable (a sensor with an empty battery never blocks saving the room).
    """
    if type(selections) is not list or len(selections) > MAX_CONTACTS or len(set(selections)) != len(selections):
        raise ComfortError("contacts", "contacts_invalid")
    for entity_id in selections:
        if type(entity_id) is not str or not entity_id.startswith("binary_sensor."):
            raise ComfortError("contacts", "not_contact_sensor")
        if entity_id in known:
            continue
        state = hass.states.get(entity_id)
        if state is None or state.attributes.get("device_class") not in CONTACT_CLASSES:
            raise ComfortError("contacts", "not_contact_sensor")
    return list(selections)


def room_contacts(entry, room_id):
    """The window/door sensors of one E32 room (Configure → Rooms or Comfort)."""
    return list(comfort_options(entry)["contacts"].get(room_id, []))


def room_contact_delay(settings, room_id):
    """Seconds an open window/door waits before this room pauses: its own delay, else the default."""
    return settings.get("contact_delays", {}).get(room_id, settings["contact_delay_s"])


def own_contact_delay(settings, delay_s):
    """What a room stores for a pause delay: None when it is the house default (the room then follows it)."""
    return None if delay_s == settings["contact_delay_s"] else delay_s


def with_room_contacts(settings, room_id, contacts, delay_s=None):
    """The comfort settings with this room's sensors replaced (none: the room has no sensors and no own
    delay); delay_s: the room's own pause delay (None keeps it; the house default drops it, so the room
    follows a later change of the default)."""
    rooms = {**settings["contacts"], room_id: list(contacts)}
    delays = dict(settings.get("contact_delays", {}))
    if delay_s is not None:
        if own_contact_delay(settings, delay_s) is None:
            delays.pop(room_id, None)
        else:
            delays[room_id] = delay_s
    if not contacts:
        rooms.pop(room_id, None)
        delays.pop(room_id, None)
    return {**settings, "contacts": rooms, "contact_delays": delays}


def room_persons(entry, room_id):
    """The persons of one room (persons per room, beta.23); empty: the room follows the house."""
    return list(comfort_options(entry)["room_persons"].get(room_id, []))


def with_room_persons(settings, room_id, persons):
    """The settings with this room's persons replaced (an empty list removes the room)."""
    rooms = dict(settings.get("room_persons", {}))
    if persons:
        rooms[room_id] = list(persons)
    else:
        rooms.pop(room_id, None)
    return {**settings, "room_persons": rooms}


def validate_room_persons(hass, selections, known=()):
    """The room's persons from the room form; a person already chosen may be unavailable now."""
    people = selections or []
    if (type(people) is not list or len(people) > MAX_PRESENCE or len(set(people)) != len(people)
            or any(type(e) is not str or e.split(".")[0] not in PRESENCE_DOMAINS for e in people)):
        raise ComfortError("persons", "presence_entity_invalid")
    for entity_id in people:
        if entity_id not in known and hass.states.get(entity_id) is None:
            raise ComfortError("persons", "presence_entity_invalid")
    return list(people)


def persons_selector():
    """People for a room: persons, device trackers, groups and on/off helpers (zones count a house, not a room)."""
    return selector.EntitySelector({"filter": [{"domain": d} for d in PRESENCE_DOMAINS if d != "zone"],
                                    "multiple": True})


def supports_room_presence(hub):
    """E32 beta.23 and newer announce persons per room as away.room_presence (room.presence.v1)."""
    status = getattr(hub, "status", None)
    away = status.get("away") if type(status) is dict else None
    return type(away) is dict and away.get("room_presence") is True


def contact_delay_text(settings, room_id=None):
    """The pause delay as the forms show it: "2 min" or "45 s" (a room's own delay with room_id)."""
    seconds = room_contact_delay(settings, room_id) if room_id else settings["contact_delay_s"]
    return f"{seconds // 60} min" if seconds >= 60 and seconds % 60 == 0 else f"{seconds} s"


def contact_selector(**extra):
    """The entity picker for window and door sensors of any brand."""
    return selector.EntitySelector({"filter": [{"domain": "binary_sensor", "device_class": list(CONTACT_CLASSES)}],
                                    "multiple": True, **extra})


@callback
def save_comfort(hass, entry, settings):
    """Store the comfort settings without a reload and follow them at once."""
    options = {**entry.options, CONF_COMFORT: settings}
    if options == dict(entry.options):
        return False
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is not None:
        state[ENERGY_ONLY_UPDATE] = dict(options)
    if not hass.config_entries.async_update_entry(entry, options=options) and state is not None:
        state.pop(ENERGY_ONLY_UPDATE, None)  # no listener runs: never leave the marker behind
    if state is not None and (forwarder := state.get("comfort_forwarder")) is not None:
        forwarder.reconfigure()
    return True


def settings_schema(vol, settings):
    def box(low, high, step, unit):
        return selector.NumberSelector({"min": low, "max": high, "step": step, "mode": "box",
                                        "unit_of_measurement": unit})
    return vol.Schema({
        vol.Required("comfort_temperature", default=settings["comfort_c"]): box(*TEMPERATURE_LIMITS, 0.5, "°C"),
        vol.Required("eco_temperature", default=settings["eco_c"]): box(*TEMPERATURE_LIMITS, 0.5, "°C"),
        # In minutes, as in each room's own "Pause after" (stored in seconds, the E32's unit).
        vol.Required("contact_delay", default=settings["contact_delay_s"] / 60): box(
            DELAY_LIMITS[0] / 60, DELAY_LIMITS[1] / 60, 0.5, "min"),
        vol.Required("override_minutes", default=settings["override_minutes"]): box(*MINUTES_LIMITS, 1, "min"),
    })


def presence_schema(vol, settings, away=False):
    """Configure → Home → Presence: the people of the house, how long everyone must be away and the away
    temperature (away: the E32's current one in °C, None when it reports none; False: no E32 field)."""
    people = settings["presence_entities"]
    fields = {
        (vol.Optional("presence_entities", description={"suggested_value": people}) if people
         else vol.Optional("presence_entities")): selector.EntitySelector(
            {"filter": [{"domain": list(PRESENCE_DOMAINS)}], "multiple": True}),
        vol.Required("away_delay", default=settings["away_delay_min"]): selector.NumberSelector(
            {"min": AWAY_DELAY_LIMITS[0], "max": AWAY_DELAY_LIMITS[1], "step": 1, "mode": "box",
             "unit_of_measurement": "min"}),
    }
    if away is not False:  # the same range and step as the number "Temperature when nobody is home"
        fields[vol.Optional("away_temperature", description={"suggested_value": away})] = selector.NumberSelector(
            {"min": AWAY_LIMITS[0], "max": AWAY_LIMITS[1], "step": 0.5, "mode": "box", "unit_of_measurement": "°C"})
    return vol.Schema(fields)


def validate_away_temperature(user_input, current):
    """The away temperature to send (5–25 °C), or None when it is empty or unchanged."""
    value = user_input.get("away_temperature")
    if value is None or value == "":
        return None
    temperature = number(value, *AWAY_LIMITS)
    if temperature is None:
        raise ComfortError("away_temperature", "comfort_away_temperature_invalid")
    return None if current is not None and float(temperature) == float(current) else float(temperature)


def contacts_room_schema(vol, rooms, room_id):
    """Step one: the room whose window/door sensors to change."""
    options = [{"value": rid, "label": name} for rid, name in rooms]
    return vol.Schema({
        vol.Required("room", default=room_id or (rooms[0][0] if rooms else "")): selector.SelectSelector(
            {"options": options, "mode": "dropdown"}),
    })


def contacts_schema(vol, contacts):
    """Step two: that room's window/door sensors, prefilled with the ones it has."""
    return vol.Schema({
        vol.Optional("contacts", description={"suggested_value": contacts or None}): contact_selector(),
    })


# -- presence and contacts (forwarded to the E32) ---------------------------------

PRESENCE_DOMAINS = ("person", "group", "zone", "device_tracker", "binary_sensor", "input_boolean")


def presence_home(state):
    """True: someone is home, False: everyone away, None: unknown.

    person / device_tracker / group: "home" is home, any other place away;
    zone (zone.home): the number of people in it; binary_sensor /
    input_boolean: on = someone home.
    """
    if state is None or state.state in ("unknown", "unavailable", ""):
        return None
    domain = state.entity_id.split(".")[0]
    if domain == "zone":
        count = number(state.state, 0, 10000)
        return None if count is None else count > 0
    if domain in ("binary_sensor", "input_boolean"):
        return {"on": True, "off": False}.get(state.state)
    return state.state == "home"


PRESENCE_MEMORY = DOMAIN + "_presence_memory"
PRESENCE_SAVE_DELAY = 10


class PresenceMemory:
    """When each person last left home, kept across Home Assistant restarts.

    A person's last_changed also moves between two away zones (Work ->
    not_home), from unavailable back to not_home and at every Home Assistant
    start; none of those is someone leaving. "left" is the moment a person
    stopped being home (home -> anything else) and stays until they are home
    again. A person never seen home here falls back to last_changed; one who
    was home when Home Assistant stopped counts from their first state after.
    """

    def __init__(self, hass, store=None):
        self.hass, self.store = hass, store
        self.people = {}  # entity_id -> {"home": True} or {"home": False, "left": datetime}

    async def async_load(self):
        stored = await self.store.async_load() if self.store is not None else None
        people = stored.get("people") if type(stored) is dict else None
        for entity_id, known in people.items() if type(people) is dict else ():
            if type(known) is not dict or entity_id in self.people:
                continue
            if known.get("home") is True:
                self.people[entity_id] = {"home": True}
            elif known.get("home") is False and type(known.get("left")) is str:
                left = dt_util.parse_datetime(known["left"])
                if left is not None and left.tzinfo is not None:
                    self.people[entity_id] = {"home": False, "left": left}

    def _data(self):
        return {"people": {e: {"home": True} if k["home"] else {"home": False, "left": k["left"].isoformat()}
                           for e, k in self.people.items()}}

    @callback
    def observe(self, entity_id, state):
        value = presence_home(state)
        known = self.people.get(entity_id)
        if value is True:
            new = {"home": True}
        elif known is not None and not known["home"]:
            return  # already away: another zone, unavailable, a restart
        elif value is False or known is not None:
            # Home (or first seen) until now: unavailable counts from the moment home was last seen.
            new = {"home": False, "left": state.last_changed if state is not None else dt_util.utcnow()}
        else:
            return
        if new != known:
            self.people[entity_id] = new
            if self.store is not None:
                self.store.async_delay_save(self._data, PRESENCE_SAVE_DELAY)

    def left(self, state):
        known = self.people.get(state.entity_id)
        return known["left"] if known is not None and not known["home"] else state.last_changed


def house_presence(hass, people, delay_min, now=None):
    """(home, wait_s) for the people of the house.

    home is True while anyone is home, while anyone's place is unknown or
    unavailable ("bij twijfel blijft het warm") and while the last person left
    less than the away delay ago (PresenceMemory); then wait_s is the seconds
    until the house counts as away. False: everyone has been away for at least
    the delay. None: no people configured.
    """
    if not people:
        return None, None
    states = [hass.states.get(e) for e in people]
    values = [presence_home(state) for state in states]
    if any(value is not False for value in values):
        return True, None
    now = now or dt_util.utcnow()
    memory = hass.data.get(PRESENCE_MEMORY)
    left = max(memory.left(state) if memory is not None else state.last_changed for state in states)
    remaining = (left + timedelta(minutes=delay_min) - now).total_seconds()
    if remaining > 0:
        return True, remaining
    return False, None


def contacts_open(states):
    """True when any contact is open, False when all are closed, None when unknown."""
    values = [None if s is None else {"on": True, "off": False}.get(s.state) for s in states]
    if any(v is True for v in values):
        return True
    if values and all(v is False for v in values):
        return False
    return None


def comfort_payloads(hass, settings, room_ids, only=None, now=None, room_presence=False):
    """The typed heating_input payloads (dicts) for the configured contacts and presence.

    room_presence: the E32 understands persons per room (supports_room_presence).
    """
    payloads = []
    for room_id, ids in sorted(settings["contacts"].items()):
        if room_id not in room_ids or not ids or (only is not None and only not in ids):
            continue
        value = contacts_open([hass.states.get(e) for e in ids])
        if value is not None:
            payloads.append({"kind": "contact", "room": room_id, "open": value,
                             "delay_s": room_contact_delay(settings, room_id)})
    people = settings["presence_entities"]
    if people and only in (None, *people):
        home, _wait = house_presence(hass, people, settings["away_delay_min"], now)
        if home is not None:
            payloads.append({"kind": "presence", "home": home})
    if room_presence:
        for room_id, persons in sorted(settings.get("room_persons", {}).items()):
            if room_id not in room_ids or not persons or (only is not None and only not in persons):
                continue
            home, _wait = house_presence(hass, persons, settings["away_delay_min"], now)
            if home is not None:
                payloads.append({"kind": "room_presence", "room": room_id, "home": home})
    return payloads


def away_waits(hass, settings, room_ids=None):
    """Seconds until the house or a room with its own persons counts as away (the shortest), or None."""
    groups = [settings["presence_entities"]] + [persons for room_id, persons in settings.get("room_persons", {}).items()
                                                if room_ids is None or room_id in room_ids]
    waits = [wait for people in groups if people
             for _home, wait in [house_presence(hass, people, settings["away_delay_min"])] if wait is not None]
    return min(waits) if waits else None


def people_of(settings):
    """Every person of the house and of the rooms."""
    return sorted(set(settings["presence_entities"]).union(*settings.get("room_persons", {}).values()))


class ComfortForwarder:
    """Sends contact and presence states to the E32: on each change, every 5 minutes and when it is back."""

    def __init__(self, hass, entry, hub, send, track_state=async_track_state_change_event):
        self.hass, self.entry, self.hub, self.send, self.track_state = hass, entry, hub, send, track_state
        self._unsubscribe = None
        self._was_fresh = False
        self._away_timer = None  # sends "everyone away" once the away delay has passed

    @property
    def settings(self):
        return comfort_options(self.entry)

    def entities(self):
        s = self.settings
        ids = [e for room in sorted(s["contacts"]) for e in s["contacts"][room]]
        persons = [e for room in sorted(s["room_persons"]) for e in s["room_persons"][room]]
        return sorted(set(ids + s["presence_entities"] + persons))

    @callback
    def publish(self, only=None):
        settings = self.settings
        memory = self.hass.data.get(PRESENCE_MEMORY)
        if memory is not None:
            for entity_id in people_of(settings):
                memory.observe(entity_id, self.hass.states.get(entity_id))
        if not self.hub.fresh:
            return
        for payload in comfort_payloads(self.hass, settings, set(self.hub.rooms), only,
                                        room_presence=supports_room_presence(self.hub)):
            self.send(json.dumps(payload, separators=(",", ":")))
        self._schedule_away(settings)

    @callback
    def _schedule_away(self, settings):
        """Everyone of the house or of a room left: send "away" exactly when the away delay has passed
        (not at the next 5-minute refresh)."""
        if self._away_timer is not None:
            self._away_timer()
            self._away_timer = None
        rooms = set(self.hub.rooms) if supports_room_presence(self.hub) else set()
        wait = away_waits(self.hass, settings if rooms else {**settings, "room_persons": {}}, rooms)
        if wait is not None:
            @callback
            def due(_now):
                self._away_timer = None
                self.publish()
            self._away_timer = async_call_later(self.hass, wait + 1, due)

    @callback
    def _changed(self, event):
        self.publish(event.data["entity_id"])

    @callback
    def hub_changed(self):
        """The E32 is (back) online: send everything at once."""
        fresh = self.hub.fresh
        if fresh and not self._was_fresh:
            self.publish()
        self._was_fresh = fresh

    @callback
    def reconfigure(self):
        self.stop()
        entities = self.entities()
        if entities:
            self._unsubscribe = self.track_state(self.hass, entities, self._changed)
        self.publish()

    @callback
    def stop(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._away_timer is not None:
            self._away_timer()
            self._away_timer = None


# -- commands ------------------------------------------------------------------------


def comfort_error(err):
    """A clear Home Assistant error for a refused or failed comfort command."""
    from .controller_link import HeatingPlanRejected
    from .room_plan import plan_error
    if isinstance(err, HeatingPlanRejected) and err.error not in ("save_unconfirmed", "storage_full"):
        key = E32_ERRORS.get(err.error)
        if key:
            return ServiceValidationError(translation_domain=DOMAIN, translation_key=key)
        return ServiceValidationError(translation_domain=DOMAIN, translation_key="comfort_rejected",
                                      translation_placeholders={"error": err.error})
    return plan_error(err)


async def async_comfort_command(link, command):
    """POST one command over the room-plan link's stored connection (RoomPlanLink.async_call).

    With every E32 web session in use it waits for one, without holding up
    other requests. A newer command for the same room (or the house mode)
    supersedes it: None, nothing sent; the newest value is the one that goes
    out. House commands go through e32_house.async_house_change, which carries
    the superseded one's fields along (the E32 takes the house mode, away
    temperature and holiday end as one command).
    """
    from .controller_link import ControllerLinkError
    from .room_plan import WriteSuperseded
    room = command.get("room") if type(command) is dict else None
    try:
        answer = await link.async_call(lambda client: client.async_comfort_command(command), write=True,
                                       key=("room", room) if room is not None else ("house",))
    except WriteSuperseded:
        return None
    except ControllerLinkError as err:
        raise comfort_error(err) from None
    if type(answer) is not dict or answer.get("schema") != 1:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_unconfirmed")
    return answer


def override_command(room_id, kind, temperature=None, minutes=None):
    command = {"room": room_id, "override": kind}
    if temperature is not None:
        command["temperature"] = round(float(temperature), 2)
    if minutes is not None:
        command["minutes"] = int(minutes)
    return command


def away_command(on, temperature=None, until=None, now=None):
    """{"away": ...}; until: a datetime (aware), within a year."""
    command = {"away": bool(on)}
    if on and temperature is not None:
        if number(temperature, *AWAY_LIMITS) is None:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="comfort_away_temperature")
        command["temperature"] = round(float(temperature), 2)
    if on and until is not None:
        now = now or dt_util.utcnow()
        if until.tzinfo is None:
            until = until.replace(tzinfo=dt_util.get_default_time_zone())
        if not now < until <= now + timedelta(days=MAX_AWAY_DAYS):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="comfort_away_until")
        command["until"] = int(until.timestamp())
    return command


# -- the climate entity --------------------------------------------------------------


def program_levels(plan_room, settings):
    """(comfort, eco, night) in °C: the room's week planner levels.

    The levels the room stores (E32 beta.23, room_levels) when it has them;
    otherwise inferred from its week program exactly like the planner does for
    older firmware (week-editor.js infer(): warmest = Comfort, coolest = Night,
    the most used in between = Eco). A room without either starts from the
    former house settings: "comfort_c" as Comfort and "eco_c" as Night (the
    one-time migration; the planner stores the room's own levels on save).
    """
    room = plan_room or {}
    stored = room_levels(room)
    if stored is not None:
        return stored["comfort"] / 100, stored["eco"] / 100, stored["night"] / 100
    lo, hi = room.get("minimum_centi_c"), room.get("maximum_centi_c")
    lo, hi = (lo, hi) if type(lo) is int and type(hi) is int and lo <= hi else (500, 3000)
    clamp = lambda v: max(lo, min(hi, v))  # noqa: E731
    half_up = lambda v: int(v + 0.5)  # noqa: E731  (JavaScript Math.round for these positive values)
    schedule = room.get("schedule")
    count = {}
    for day in schedule if type(schedule) is list else []:
        for point in day if type(day) is list else []:
            if type(point) is list and len(point) == 2 and type(point[1]) is int:
                count[point[1]] = count.get(point[1], 0) + 1
    values = sorted(count, reverse=True)
    if not values:
        comfort, night = clamp(round(settings["comfort_c"] * 100)), clamp(round(settings["eco_c"] * 100))
        return comfort / 100, clamp(half_up((comfort + night) / 100) * 50) / 100, night / 100
    comfort = values[0]
    night = values[-1] if len(values) > 1 else clamp(1600)
    middle = sorted(values[1:-1], key=lambda v: -count[v])
    eco = middle[0] if middle else clamp(half_up((comfort + night) / 100) * 50)
    if night == comfort:
        night = clamp(comfort - 300)
    if len({comfort, eco, night}) < 3:
        eco = next((v for v in map(clamp, (comfort - 100, night + 100, comfort + 100)) if v not in (comfort, night)), eco)
    return comfort / 100, eco / 100, night / 100



def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if type(value) is int and value > 0 else None


class E32RoomClimate(RoomEntity, ClimateEntity):
    """One E32 room as a thermostat. Reads the telemetry; writes overrides, away or the plan."""

    _attr_name = None  # the room device's name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = PRESETS
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)

    def __init__(self, hub, room, entry):
        self._attach_room(hub, room, "thermostat")
        self.entry = entry
        self._pending = None  # (°C, None while its write runs, else monotonic time it was sent)

    # -- state ---------------------------------------------------------------------
    @property
    def link(self):
        return self.hub.plan

    @property
    def plan_room(self):
        return self.link.room(self.room_id) if self.link is not None else None

    @property
    def comfort(self):
        room = self.room or {}
        return room.get("comfort") if type(room.get("comfort")) is dict else {}

    @property
    def away(self):
        status = self.hub.status or {}
        return status.get("away") if type(status.get("away")) is dict else {}

    @property
    def available(self):
        return self.hub.fresh and self.room is not None and self.link is not None

    @property
    def current_temperature(self):
        return number((self.room or {}).get("temperature"), -40, 85)

    @property
    def target_temperature(self):
        reported = number((self.room or {}).get("setpoint"), 5, 35)
        if self._pending is not None:
            value, sent = self._pending
            if sent is None or ((reported is None or abs(reported - value) >= 0.05)
                                and time.monotonic() - sent < PENDING_SECONDS):
                return value
            self._pending = None
        return reported

    @property
    def min_temp(self):
        from .room_plan import setpoint_range
        return setpoint_range(self.plan_room)[0]

    @property
    def max_temp(self):
        from .room_plan import setpoint_range
        return setpoint_range(self.plan_room)[1]

    @property
    def hvac_mode(self):
        room = self.room
        if room is None:
            return None
        if room.get("state") == "inactive":
            return HVACMode.OFF
        return HVACMode.HEAT if self.comfort.get("override") in OVERRIDES else HVACMode.AUTO

    @property
    def hvac_action(self):
        room = self.room
        if room is None:
            return None
        if room.get("state") == "inactive":
            return HVACAction.OFF
        return HVACAction.HEATING if room.get("demand") is True else HVACAction.IDLE

    @property
    def preset_mode(self):
        comfort = self.comfort
        if comfort.get("override") == "boost":
            return PRESET_BOOST
        if comfort.get("override") in OVERRIDES:
            target = number(comfort.get("target_c"), 5, 35)
            levels = program_levels(self.plan_room, comfort_options(self.entry))
            centi = round(target * 100) if target is not None else None
            # Equal levels: the first one (Comfort, Eco, Night) names the hold.
            return next((preset for preset, i in LEVEL_PRESETS.items() if centi == round(levels[i] * 100)), PRESET_NONE)
        return PRESET_NONE  # away is the house mode (its own select), not a preset of one room

    @property
    def extra_state_attributes(self):
        room = self.room
        if room is None:
            return None
        comfort, away = self.comfort, self.away
        from .room_away import away_reason, room_away
        own = room_away(self.plan_room)
        return {"room_id": self.room_id, "comfort_mode": comfort.get("mode", "program"),
                "window": comfort.get("window"), "override": comfort.get("override"),
                "until": _iso(comfort.get("until")), "waiting_for_clock": comfort.get("waiting_for_clock") is True,
                "setpoint_source": room.get("setpoint_source"),
                "away": away.get("on") is True, "away_source": away.get("source"),
                "away_until": _iso(away.get("until")),
                # Why this room is cooler (room_persons: only its own persons are out; everyone; house_mode:
                # Away or Holiday), what its own persons are (home/away) and its own away temperature
                # (None: the house value, plan.room_away.v1).
                "away_reason": away_reason(comfort, away), "room_persons": comfort.get("persons"),
                "own_away_temperature": own / 100 if own is not None else None,
                "smart_warm_up": self._smart_warm_up()}

    def _smart_warm_up(self):
        """E32 rc.3: what Smart warm-up does for the next program step, in the Home Assistant language, or None."""
        if self.hass is None:
            return None
        from .e32_flow import smart_warm_up
        from .learned_overview import language, local_clock, smart_warm_up_line
        plan = self.hub.warmup.get(self.room_id) if type(getattr(self.hub, "warmup", None)) is dict else None
        start = plan.get("optimum_start") if type(plan) is dict else None
        line = smart_warm_up_line(start, smart_warm_up(self.hass, self.entry.entry_id), language(self.hass), local_clock(self.hass))
        return line[0] if line else None

    # -- commands ----------------------------------------------------------------
    def _write_state(self):
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()

    @asynccontextmanager
    async def _target_pending(self, temperature):
        """The new target is shown at once and never silently dropped: a failed write
        shows the E32's own target again (and raises); a newer target replaces it."""
        mine = self._pending = (temperature, None)
        self._write_state()
        try:
            yield
        except BaseException:
            if self._pending is mine:
                self._pending = None
                self._write_state()
            raise
        if self._pending is mine:
            self._pending = (temperature, time.monotonic())

    async def _command(self, command, house=None):
        if self.link is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_unreachable",
                                     translation_placeholders={"error": "no_controller_connection"})
        if house is not None:  # the house mode, with the house changes still on their way (e32_house)
            from .e32_house import async_house_change, house_away
            answer = await async_house_change(self.link, house_away(self.hub), **house)
        else:
            answer = await async_comfort_command(self.link, command)
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()
        return answer

    async def _change_plan(self, change, key=None):
        await self.link.async_change_room(self.room_id, change, key)

    async def _ensure_active(self):
        if (self.room or {}).get("state") == "inactive" or (self.plan_room or {}).get("state") == "inactive":
            from .room_plan import set_state
            await self._change_plan(set_state("active"))

    async def async_hold(self, temperature):
        """A new target: until the next switch point, else for the configured time, else the plan's fixed target."""
        plan = self.plan_room or {}
        schedule = plan.get("schedule")
        has_program = (type(schedule) is list and any(day for day in schedule)) or bool(plan.get("week"))
        if not has_program and not plan.get("setpoint_entity"):
            from .room_plan import set_fallback
            await self._change_plan(set_fallback(int(round(temperature * 2)) * 50), ("fallback", self.room_id))
            if self.comfort.get("override") in OVERRIDES:
                await self._command(override_command(self.room_id, "none"))
            return
        if has_program:
            try:
                return await self._command(override_command(self.room_id, "next", temperature))
            except ServiceValidationError as err:
                if err.translation_key not in ("comfort_no_clock", "comfort_no_schedule"):
                    raise
        minutes = comfort_options(self.entry)["override_minutes"]
        return await self._command(override_command(self.room_id, "timed", temperature, minutes))

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        if kwargs.get("hvac_mode") == HVACMode.OFF:
            return await self.async_set_hvac_mode(HVACMode.OFF)
        async with self._target_pending(float(temperature)):
            await self._ensure_active()
            await self.async_hold(float(temperature))

    async def async_set_hvac_mode(self, hvac_mode):
        from .room_plan import set_state
        if hvac_mode == HVACMode.OFF:
            await self._change_plan(set_state("inactive"))
        elif hvac_mode == HVACMode.AUTO:
            await self._ensure_active()
            if self.comfort.get("override") in OVERRIDES:
                await self._command(override_command(self.room_id, "none"))
        elif hvac_mode == HVACMode.HEAT:
            await self._ensure_active()
            target = self.target_temperature
            if self.comfort.get("override") not in OVERRIDES and target is not None:
                await self.async_hold(target)
        else:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="room_state_invalid")

    async def async_turn_on(self):
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode == PRESET_BOOST:
            await self._ensure_active()
            await self._command(override_command(self.room_id, "boost"))
        elif preset_mode in LEVEL_PRESETS:
            levels = program_levels(self.plan_room, comfort_options(self.entry))
            async with self._target_pending(levels[LEVEL_PRESETS[preset_mode]]):
                await self._ensure_active()
                await self.async_hold(levels[LEVEL_PRESETS[preset_mode]])
        elif preset_mode == PRESET_NONE:
            # Back to the week program; the house mode (away, holiday) is its own select (e32_house.py).
            if self.comfort.get("override") in OVERRIDES:
                await self._command(override_command(self.room_id, "none"))
        else:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="room_state_invalid")

    # -- actions (services.yaml) --------------------------------------------------
    async def async_set_room_override(self, mode, temperature=None, duration_minutes=None):
        if mode not in ("boost", "timed", "until_next"):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="room_state_invalid")
        await self._ensure_active()
        if mode == "boost":
            return await self._command(override_command(self.room_id, "boost", None, duration_minutes))
        if temperature is None:
            temperature = self.target_temperature
        if temperature is None or not self.min_temp <= float(temperature) <= self.max_temp:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="room_setpoint_outside_limits",
                translation_placeholders={"minimum": f"{self.min_temp:g}", "maximum": f"{self.max_temp:g}"})
        if mode == "until_next":
            return await self._command(override_command(self.room_id, "next", temperature))
        minutes = duration_minutes or comfort_options(self.entry)["override_minutes"]
        return await self._command(override_command(self.room_id, "timed", temperature, minutes))

    async def async_clear_room_override(self):
        await self._command(override_command(self.room_id, "none"))

    # set_away / clear_away stay for existing automations (beta.23). They set the HOUSE mode, exactly as
    # the House mode select does: Away (or Holiday with an end date), and Auto again; never one room.
    async def async_set_away(self, temperature=None, until=None):
        from .e32_house import holiday_until
        end = holiday_until(until) if until is not None else None
        await self._command(None, {"mode": "holiday" if end else "away", "until": end, "temperature": temperature})

    async def async_clear_away(self):
        await self._command(None, {"mode": "auto"})


def register_services(platform):
    """The entity actions of the E32 room thermostats (see services.yaml)."""
    import voluptuous as vol
    platform.async_register_entity_service("set_room_override", {
        vol.Required("mode"): vol.In(["boost", "timed", "until_next"]),
        vol.Optional("temperature"): vol.All(vol.Coerce(float), vol.Range(min=5, max=30)),
        vol.Optional("duration_minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=1440)),
    }, "async_set_room_override")
    platform.async_register_entity_service("clear_room_override", {}, "async_clear_room_override")
    from homeassistant.helpers import config_validation as cv
    platform.async_register_entity_service("set_away", {
        vol.Optional("temperature"): vol.All(vol.Coerce(float), vol.Range(min=AWAY_LIMITS[0], max=AWAY_LIMITS[1])),
        vol.Optional("until"): cv.datetime,
    }, "async_set_away")
    platform.async_register_entity_service("clear_away", {}, "async_clear_away")


def _wanted(hub, entry):
    for room_id, room in hub.rooms.items():
        yield room_id, lambda room=room: E32RoomClimate(hub, room, entry)


async def async_setup_e32_climates(hass, entry, async_add_entities):
    """Product entries with a stored E32 connection: a thermostat per room and the forwarder."""
    from .product import is_product
    if not is_product(entry):
        return
    hub = heating_hub(hass, entry)
    if hub.plan is None:
        return  # no stored controller connection: nothing can be written
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry),
                                         lambda hub: _wanted(hub, entry)))
    state = hass.data[DOMAIN][entry.entry_id]
    # The E32 program on each room's setting device; its knob as an override (e32_setting_device.py).
    from .e32_setting_device import SettingDevicePusher
    pusher = state["setting_device_pusher"] = SettingDevicePusher(hass, entry, hub)
    entry.async_on_unload(pusher.start())
    # Only the MQTT prefix and the broker, not the shadow link (heating_link.topic_base).
    from .heating_link import topic_base
    topic = topic_base(hass, entry) + "ha/heating_input"

    def send(payload):
        hass.async_create_task(mqtt.async_publish(hass, topic, payload, 0, False))

    if PRESENCE_MEMORY not in hass.data:
        from homeassistant.helpers.storage import Store
        memory = hass.data[PRESENCE_MEMORY] = PresenceMemory(hass, Store(hass, 1, f"{DOMAIN}.presence"))
        await memory.async_load()
    forwarder = state["comfort_forwarder"] = ComfortForwarder(hass, entry, hub, send)
    entry.async_on_unload(hub.add_listener(forwarder.hub_changed))
    entry.async_on_unload(async_track_time_interval(hass, lambda _now: forwarder.publish(), REFRESH))
    forwarder.reconfigure()
    entry.async_on_unload(forwarder.stop)


# -- options flow (Configure -> Comfort) ---------------------------------------------


class ComfortOptionsSteps:
    """Mixin for the product options flow: the house (presence) and comfort settings, window/door sensors per room."""

    async def async_step_house(self, user_input=None):
        """Configure → House: presence and the away temperature, the house mode and holiday, and the comfort defaults.

        Heating and boiler, energy and the E32 connection have their own place in the main menu; the window contacts
        are set per room in Configure → Rooms.
        """
        from .e32_house import house_mode
        house = self._presence_house()
        options = ["house_presence"]
        if house is not None:
            options.append("house_mode")
            if house_mode(house.away) == "holiday":
                options.append("house_holiday_stop")
        options.append("comfort_settings")
        return self.async_show_menu(step_id="house", menu_options=options)

    def _presence_house(self):
        """The house state of the away temperature (e32_house.HouseState), or None without an E32 that reports it."""
        state = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        hub = state.get("heating_hub") if type(state) is dict else None
        if hub is None or getattr(hub, "plan", None) is None:
            return None
        from .e32_house import house_state
        house = house_state(self.hass, self.config_entry, hub)
        return house if house.away is not None else None

    async def async_step_house_presence(self, user_input=None):
        """The people of the house, how long everyone must be away and the away temperature.

        The away temperature is the E32's own setting (the number "Temperature when nobody is
        home" and the E32's Home page): it is sent with the same house command as that number
        (e32_house.HouseState.async_command), so all three show the same value. The house
        mode itself is a select.
        """
        import voluptuous as vol
        current = comfort_options(self.config_entry)
        house = self._presence_house()
        away = number(house.away.get("target_c"), *AWAY_LIMITS) if house is not None else None
        errors, placeholders = {}, {"error": ""}
        if user_input is not None:
            try:
                settings = validate_presence(self.hass, user_input, current)
                temperature = validate_away_temperature(user_input, away) if house is not None else None
            except ComfortError as err:
                errors[err.field] = err.code
            else:
                try:
                    if temperature is not None:  # first: refused by the E32, nothing is saved
                        await house.async_command(temperature=temperature)
                except HomeAssistantError as err:
                    key = getattr(err, "translation_key", None)
                    errors["away_temperature"] = ("away_temperature_update_required" if key == "house_mode_update_required"
                                                  else "away_temperature_not_saved")
                    placeholders["error"] = (getattr(err, "translation_placeholders", None) or {}).get("error") or \
                        key or "unknown"
                else:
                    save_comfort(self.hass, self.config_entry, settings)
                    return self.async_abort(reason="presence_saved")
        schema = presence_schema(vol, current, away if house is not None else False)
        if user_input is not None and errors:  # shown again: what was just entered
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="house_presence", data_schema=schema, errors=errors,
                                    description_placeholders=placeholders)

    async def async_step_comfort(self, user_input=None):
        return self.async_show_menu(step_id="comfort", menu_options=["comfort_settings", "comfort_contacts"])

    async def async_step_comfort_settings(self, user_input=None):
        import voluptuous as vol
        current = comfort_options(self.config_entry)
        errors = {}
        if user_input is not None:
            try:
                minutes = user_input.get("contact_delay")
                if type(minutes) in (int, float):  # the form shows minutes; the settings keep seconds
                    user_input = {**user_input, "contact_delay": round(minutes * 60, 6)}
                settings = validate_settings(self.hass, user_input, current)
            except ComfortError as err:
                errors[err.field] = err.code
            else:
                save_comfort(self.hass, self.config_entry, settings)
                return self.async_abort(reason="comfort_saved")
        return self.async_show_form(step_id="comfort_settings", data_schema=settings_schema(vol, current), errors=errors)

    def _comfort_rooms(self):
        hub = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {}).get("heating_hub")
        rooms = hub.rooms if hub is not None else {}
        return [(room_id, room.get("name") or room_id) for room_id, room in sorted(rooms.items())]

    def _comfort_contact_summary(self, rooms, settings):
        """Per room the names of its window/door sensors (or "none"), one line each."""
        def name(entity_id):
            state = self.hass.states.get(entity_id)
            return (state.attributes.get("friendly_name") if state is not None else None) or entity_id
        none = "geen" if self.hass.config.language == "nl" else "none"
        return "\n".join(f"- {room}: {', '.join(name(e) for e in settings['contacts'].get(rid, [])) or none}"
                         for rid, room in rooms)

    async def async_step_comfort_contacts(self, user_input=None):
        """Pick the room first, so the sensor list below always belongs to the room it shows."""
        import voluptuous as vol
        rooms = self._comfort_rooms()
        if not rooms:
            return self.async_abort(reason="comfort_no_rooms")
        current = comfort_options(self.config_entry)
        errors = {}
        if user_input is not None:
            if user_input.get("room") in dict(rooms):
                self._comfort_room = user_input["room"]
                return await self.async_step_comfort_contacts_room()
            errors["room"] = "room_invalid"
        return self.async_show_form(
            step_id="comfort_contacts", errors=errors,
            data_schema=contacts_room_schema(vol, rooms, (user_input or {}).get("room")),
            description_placeholders={"rooms": self._comfort_contact_summary(rooms, current)})

    async def async_step_comfort_contacts_room(self, user_input=None):
        import voluptuous as vol
        rooms = dict(self._comfort_rooms())
        room_id = getattr(self, "_comfort_room", None)
        if room_id not in rooms:
            return self.async_abort(reason="comfort_no_rooms")
        current = comfort_options(self.config_entry)
        known = current["contacts"].get(room_id, [])
        errors = {}
        if user_input is not None:
            try:
                contacts = validate_contacts(self.hass, list(user_input.get("contacts") or []), known)
            except ComfortError as err:
                errors[err.field] = err.code
            else:
                save_comfort(self.hass, self.config_entry, with_room_contacts(current, room_id, contacts))
                return self.async_abort(reason="comfort_saved")
        return self.async_show_form(
            step_id="comfort_contacts_room", errors=errors,
            data_schema=contacts_schema(vol, (user_input or {}).get("contacts", known) if errors else known),
            description_placeholders={"room": rooms[room_id], "delay": contact_delay_text(current)})
