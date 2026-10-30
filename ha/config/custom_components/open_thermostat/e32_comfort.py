"""A Home Assistant thermostat per E32 room, temporary overrides, window/door pauses and away.

The rooms live in the E32 room plan and the E32 computes their demand, also
without Home Assistant. This module adds, on top of that plan (E32 beta.19,
``src/control/RoomOverrides.h``):

- one ``climate`` entity per E32 room (thermostat card, voice assistants):
  current temperature, target, mode auto / heat / off and the presets comfort,
  eco (shown as "Night"), away and boost. Comfort and night are the warmest and
  coolest temperature of the room's week program, the levels of the week planner. "Off" makes the room inactive in the room plan; a new
  target becomes an override "until the next switch point" of the room's week
  program (or for the configured time when the room has no program); a room
  with only a fixed target changes that target in the plan.
- the actions ``set_room_override`` / ``clear_room_override`` (boost, "2 h at
  21 °C", until the next switch point) and ``set_away`` / ``clear_away`` (a
  lower temperature for the whole house, optionally until a date). The E32
  ends every override itself, also after a restart, and returns the room to
  its week program; a dated away ends early enough to be warm again on time.
- the optional window/door contacts per room and a presence entity ("everyone
  away"), forwarded to the E32 over ``<base>ha/heating_input``::

      {"kind": "contact", "room": "living", "open": true, "delay_s": 120}
      {"kind": "presence", "home": false}

  on every change and every five minutes. Any open contact of a room counts as
  open; the E32 pauses the room after the delay (its frost limit stays) and
  resumes when all are closed. Unknown states are not sent: the E32 then
  forgets the report after 15 minutes and the room heats normally.

A room whose target comes from a Home Assistant thermostat (its plan
``setpoint_entity`` is a ``climate`` entity, for example a tado or a radiator
valve of another integration) follows that thermostat: our thermostat shows
its target, and a new target is sent to it (``climate.set_temperature``, only
on the user's own action on our entity), so there are never two thermostats
that disagree; the E32 follows it as before. Temporary overrides and presets
are not offered for such a room: restoring the thermostat's own target
afterwards is not reliable (a Home Assistant restart loses the timer, and the
thermostat may run its own schedule), which the attributes say
(``target_control: followed_thermostat``, ``overrides_offered: false``).

The entity reads the room from the E32 telemetry (``fw/state/room/<id>``: the
room's ``temperature``, ``setpoint``, ``state``, ``demand`` and, while it
deviates from its plan, ``comfort``; ``fw/state/heating``: ``away``) through the
entry's HeatingHub. Commands go over the stored controller connection
(``POST /config/heating/comfort``); plan changes through the room-plan writer.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging

from homeassistant.components import mqtt
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    PRESET_AWAY, PRESET_BOOST, PRESET_COMFORT, PRESET_ECO, PRESET_NONE, ClimateEntityFeature, HVACAction, HVACMode)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import selector
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .heating_link import RoomEntity, add_options, celsius, heating_hub, number, track_entities

CONF_COMFORT = "comfort_settings"
DEFAULTS = {"presence_entity": None, "comfort_c": 20.0, "eco_c": 16.0,  # the week planner's defaults
            "contact_delay_s": 120,
            "override_minutes": 120, "contacts": {}}
TEMPERATURE_LIMITS = (5.0, 30.0)
AWAY_LIMITS = (5.0, 25.0)
DELAY_LIMITS = (0, 1800)       # the E32's own bound (RoomOverrides::maxContactDelayS)
MINUTES_LIMITS = (1, 1440)     # the E32's own bound (RoomOverrides::maxMinutes)
MAX_CONTACTS = 8
MAX_AWAY_DAYS = 366
REFRESH = timedelta(minutes=5)
CONTACT_CLASSES = ("window", "door", "opening", "garage_door")
PRESETS = [PRESET_NONE, PRESET_COMFORT, PRESET_ECO, PRESET_AWAY, PRESET_BOOST]
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
    for key, (low, high) in (("comfort_c", TEMPERATURE_LIMITS), ("eco_c", TEMPERATURE_LIMITS)):
        if number(raw.get(key), low, high) is not None:
            out[key] = float(raw[key])
    for key, (low, high) in (("contact_delay_s", DELAY_LIMITS), ("override_minutes", MINUTES_LIMITS)):
        if type(raw.get(key)) is int and low <= raw[key] <= high:
            out[key] = raw[key]
    contacts = raw.get("contacts")
    if type(contacts) is dict:
        out["contacts"] = {room: [e for e in ids if type(e) is str and e.startswith("binary_sensor.")][:MAX_CONTACTS]
                           for room, ids in contacts.items() if type(room) is str and type(ids) is list}
    return out


class ComfortError(ValueError):
    def __init__(self, field, code):
        super().__init__(code)
        self.field, self.code = field, code


def validate_settings(hass, user_input, current):
    """The house settings from the options form (presence, preset temperatures, delay, duration)."""
    out = dict(current)
    presence = user_input.get("presence_entity") or None
    if presence is not None:
        if hass.states.get(presence) is None or presence.split(".")[0] not in PRESENCE_DOMAINS:
            raise ComfortError("presence_entity", "presence_entity_invalid")
    out["presence_entity"] = presence
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


def validate_contacts(hass, selections):
    """Window/door/opening binary sensors for one room (at most eight)."""
    if type(selections) is not list or len(selections) > MAX_CONTACTS or len(set(selections)) != len(selections):
        raise ComfortError("contacts", "contacts_invalid")
    for entity_id in selections:
        state = hass.states.get(entity_id)
        if (type(entity_id) is not str or not entity_id.startswith("binary_sensor.") or state is None
                or state.attributes.get("device_class") not in CONTACT_CLASSES):
            raise ComfortError("contacts", "not_contact_sensor")
    return list(selections)


@callback
def save_comfort(hass, entry, settings):
    """Store the comfort settings without a reload and follow them at once."""
    options = {**entry.options, CONF_COMFORT: settings}
    if options == dict(entry.options):
        return False
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is not None:
        state[ENERGY_ONLY_UPDATE] = dict(options)
    hass.config_entries.async_update_entry(entry, options=options)
    if state is not None and (forwarder := state.get("comfort_forwarder")) is not None:
        forwarder.reconfigure()
    return True


def settings_schema(vol, settings):
    def box(low, high, step, unit):
        return selector.NumberSelector({"min": low, "max": high, "step": step, "mode": "box",
                                        "unit_of_measurement": unit})
    presence = settings["presence_entity"]
    return vol.Schema({
        (vol.Optional("presence_entity", description={"suggested_value": presence}) if presence
         else vol.Optional("presence_entity")): selector.EntitySelector(
            {"filter": [{"domain": list(PRESENCE_DOMAINS)}]}),
        vol.Required("comfort_temperature", default=settings["comfort_c"]): box(*TEMPERATURE_LIMITS, 0.5, "°C"),
        vol.Required("eco_temperature", default=settings["eco_c"]): box(*TEMPERATURE_LIMITS, 0.5, "°C"),
        vol.Required("contact_delay", default=settings["contact_delay_s"]): box(*DELAY_LIMITS, 1, "s"),
        vol.Required("override_minutes", default=settings["override_minutes"]): box(*MINUTES_LIMITS, 1, "min"),
    })


def contacts_schema(vol, rooms, room_id, contacts):
    """Pick a room and its window/door sensors (prefilled for the chosen room)."""
    options = [{"value": rid, "label": name} for rid, name in rooms]
    return vol.Schema({
        vol.Required("room", default=room_id or (rooms[0][0] if rooms else "")): selector.SelectSelector(
            {"options": options, "mode": "dropdown"}),
        vol.Optional("contacts", description={"suggested_value": contacts}): selector.EntitySelector(
            {"filter": [{"domain": "binary_sensor", "device_class": list(CONTACT_CLASSES)}], "multiple": True}),
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


def contacts_open(states):
    """True when any contact is open, False when all are closed, None when unknown."""
    values = [None if s is None else {"on": True, "off": False}.get(s.state) for s in states]
    if any(v is True for v in values):
        return True
    if values and all(v is False for v in values):
        return False
    return None


def comfort_payloads(hass, settings, room_ids, only=None):
    """The typed heating_input payloads (dicts) for the configured contacts and presence."""
    payloads = []
    for room_id, ids in sorted(settings["contacts"].items()):
        if room_id not in room_ids or not ids or (only is not None and only not in ids):
            continue
        value = contacts_open([hass.states.get(e) for e in ids])
        if value is not None:
            payloads.append({"kind": "contact", "room": room_id, "open": value,
                             "delay_s": settings["contact_delay_s"]})
    presence = settings["presence_entity"]
    if presence and only in (None, presence):
        home = presence_home(hass.states.get(presence))
        if home is not None:
            payloads.append({"kind": "presence", "home": home})
    return payloads


class ComfortForwarder:
    """Sends contact and presence states to the E32: on each change, every 5 minutes and when it is back."""

    def __init__(self, hass, entry, hub, send, track_state=async_track_state_change_event):
        self.hass, self.entry, self.hub, self.send, self.track_state = hass, entry, hub, send, track_state
        self._unsubscribe = None
        self._was_fresh = False

    @property
    def settings(self):
        return comfort_options(self.entry)

    def entities(self):
        s = self.settings
        ids = [e for room in sorted(s["contacts"]) for e in s["contacts"][room]]
        return sorted(set(ids + ([s["presence_entity"]] if s["presence_entity"] else [])))

    @callback
    def publish(self, only=None):
        if not self.hub.fresh:
            return
        for payload in comfort_payloads(self.hass, self.settings, set(self.hub.rooms), only):
            self.send(json.dumps(payload, separators=(",", ":")))

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
    """POST one command over the room-plan link's stored connection (one login, its lock)."""
    from .controller_link import ControllerLinkError
    async with link._lock:
        try:
            async with link._client() as client:
                await link._login(client)
                answer = await client.async_comfort_command(command)
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
    """(comfort, night) in °C, as the week planner names them (week-editor.js infer()).

    Comfort is the warmest and night the coolest temperature of the room's week
    program; without a program, the comfort settings (Configure -> Comfort).
    The presets "comfort" and "eco" use these, so the thermostat and the week
    planner speak of the same levels.
    """
    room = plan_room or {}
    lo, hi = room.get("minimum_centi_c"), room.get("maximum_centi_c")
    lo, hi = (lo, hi) if type(lo) is int and type(hi) is int and lo <= hi else (500, 3000)
    schedule = room.get("schedule")
    values = sorted({point[1] for day in schedule if type(day) is list for point in day
                     if type(point) is list and len(point) == 2 and type(point[1]) is int}, reverse=True)         if type(schedule) is list else []
    if not values:
        return settings["comfort_c"], settings["eco_c"]
    clamp = lambda v: max(lo, min(hi, v))  # noqa: E731
    comfort = values[0]
    night = values[-1] if len(values) > 1 else clamp(1600)
    if night == comfort:
        night = clamp(comfort - 300)
    return comfort / 100, night / 100



FOLLOW_DOMAIN = "climate"
_LOGGER = logging.getLogger(__name__)


def followed_entity(plan_room):
    """The HA thermostat (climate entity) whose target this room follows, or None."""
    entity_id = (plan_room or {}).get("setpoint_entity")
    return entity_id if type(entity_id) is str and entity_id.split(".")[0] == FOLLOW_DOMAIN else None


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
        self._following = None      # the entity whose state changes we track
        self._unfollow = None

    # -- the followed thermostat ----------------------------------------------------
    @property
    def followed(self):
        return followed_entity(self.plan_room)

    def _followed_state(self):
        followed = self.followed
        hass = getattr(self, "hass", None)
        state = hass.states.get(followed) if followed and hass is not None else None
        return state if state is not None and state.state not in ("unavailable", "unknown") else None

    def _followed_value(self, key, low=5, high=35):
        state = self._followed_state()
        if state is None:
            return None
        return celsius(state.attributes.get(key), self.hass.config.units.temperature_unit, low, high)

    @callback
    def _track_followed(self):
        """Show the followed thermostat's own changes at once (its target is ours)."""
        followed = self.followed
        if followed == self._following:
            return
        if self._unfollow is not None:
            self._unfollow()
            self._unfollow = None
        self._following = followed
        if followed and self.hass is not None:
            self._unfollow = async_track_state_change_event(self.hass, [followed], self._followed_changed)

    @callback
    def _followed_changed(self, _event):
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._track_followed()
        self.async_on_remove(lambda: self._unfollow() if self._unfollow is not None else None)

    @callback
    def _hub_changed(self):
        if self.hass is not None and self.entity_id:
            self._track_followed()
        super()._hub_changed()

    async def _forward(self, temperature):
        """Set the followed thermostat's target (a normal service call, on the user's action only)."""
        followed, state = self.followed, self._followed_state()
        if state is None or "temperature" not in state.attributes:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="comfort_followed_unavailable",
                                         translation_placeholders={"entity": followed or ""})
        unit = self.hass.config.units.temperature_unit
        value = float(temperature)
        if unit != UnitOfTemperature.CELSIUS:
            from homeassistant.util.unit_conversion import TemperatureConverter
            value = TemperatureConverter.convert(value, UnitOfTemperature.CELSIUS, unit)
        _LOGGER.info("E32 room %s follows %s: setting its target to %.1f %s", self.room_id, followed, value, unit)
        await self.hass.services.async_call(FOLLOW_DOMAIN, "set_temperature",
                                            {"entity_id": followed, "temperature": round(value, 1)},
                                            blocking=True, context=self._context)

    def _not_offered(self):
        return ServiceValidationError(translation_domain=DOMAIN, translation_key="comfort_followed_thermostat",
                                      translation_placeholders={"entity": self.followed or ""})

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
        if self.followed:  # the followed thermostat's own target (the E32 follows it)
            target = self._followed_value("temperature")
            if target is not None:
                return target
        return number((self.room or {}).get("setpoint"), 5, 35)

    @property
    def min_temp(self):
        from .room_plan import setpoint_range
        low = setpoint_range(self.plan_room)[0]
        other = self._followed_value("min_temp", -50, 100) if self.followed else None
        return max(low, other) if other is not None and other <= setpoint_range(self.plan_room)[1] else low

    @property
    def max_temp(self):
        from .room_plan import setpoint_range
        high = setpoint_range(self.plan_room)[1]
        other = self._followed_value("max_temp", -50, 100) if self.followed else None
        return min(high, other) if other is not None and other >= self.min_temp else high

    @property
    def target_temperature_step(self):
        state = self._followed_state() if self.followed else None
        step = number(state.attributes.get("target_temp_step"), 0.01, 5) if state is not None else None
        # The other thermostat's own step (in HA's unit; its Celsius step is close enough for a card).
        return step if step is not None else 0.5

    @property
    def supported_features(self):
        features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        return features if self.followed else features | ClimateEntityFeature.PRESET_MODE

    @property
    def hvac_modes(self):
        return [HVACMode.AUTO, HVACMode.OFF] if self.followed else [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]

    @property
    def hvac_mode(self):
        room = self.room
        if room is None:
            return None
        if room.get("state") == "inactive":
            return HVACMode.OFF
        if self.followed:
            return HVACMode.AUTO
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
            return (PRESET_COMFORT if centi == round(levels[0] * 100) else PRESET_ECO if centi == round(levels[1] * 100)
                    else PRESET_NONE)
        if comfort.get("mode") in AWAY_MODES or self.away.get("on") is True:
            return PRESET_AWAY
        return PRESET_NONE

    @property
    def extra_state_attributes(self):
        room = self.room
        if room is None:
            return None
        comfort, away, followed = self.comfort, self.away, self.followed
        return {"room_id": self.room_id, "comfort_mode": comfort.get("mode", "program"),
                # Who sets the target: the E32 (week program, overrides) or the followed thermostat.
                "target_control": "followed_thermostat" if followed else "e32", "followed_entity": followed,
                "overrides_offered": not followed,
                "e32_setpoint": number(room.get("setpoint"), 5, 35),
                "window": comfort.get("window"), "override": comfort.get("override"),
                "until": _iso(comfort.get("until")), "waiting_for_clock": comfort.get("waiting_for_clock") is True,
                "setpoint_source": room.get("setpoint_source"),
                "away": away.get("on") is True, "away_source": away.get("source"),
                "away_until": _iso(away.get("until"))}

    # -- commands ----------------------------------------------------------------
    async def _command(self, command):
        if self.link is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_unreachable",
                                     translation_placeholders={"error": "no_controller_connection"})
        answer = await async_comfort_command(self.link, command)
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()
        return answer

    async def _change_plan(self, change):
        await self.link.async_change_room(self.room_id, change)

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
            await self._change_plan(set_fallback(int(round(temperature * 2)) * 50))
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
        await self._ensure_active()
        if self.followed:
            return await self._forward(float(temperature))
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
            if self.followed:
                raise self._not_offered()
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
        if self.followed:
            raise self._not_offered()
        if preset_mode == PRESET_BOOST:
            await self._ensure_active()
            await self._command(override_command(self.room_id, "boost"))
        elif preset_mode in (PRESET_COMFORT, PRESET_ECO):
            await self._ensure_active()
            comfort, night = program_levels(self.plan_room, comfort_options(self.entry))  # eco = the night level
            await self.async_hold(comfort if preset_mode == PRESET_COMFORT else night)
        elif preset_mode == PRESET_AWAY:
            await self._command(away_command(True))
        elif preset_mode == PRESET_NONE:
            if self.comfort.get("override") in OVERRIDES:
                await self._command(override_command(self.room_id, "none"))
            # An open-ended away set by hand ends too; a dated away or presence stays.
            if self.away.get("source") == "manual" and self.away.get("until") is None:
                await self._command(away_command(False))
        else:
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="room_state_invalid")

    # -- actions (services.yaml) --------------------------------------------------
    async def async_set_room_override(self, mode, temperature=None, duration_minutes=None):
        if mode not in ("boost", "timed", "until_next"):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="room_state_invalid")
        if self.followed:
            raise self._not_offered()
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

    async def async_set_away(self, temperature=None, until=None):
        await self._command(away_command(True, temperature, until))

    async def async_clear_away(self):
        await self._command(away_command(False))


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
    connection = state.get("v1_connection")
    if connection is None or getattr(connection, "client", None) is None:
        return
    topic = connection.prefix + "ha/heating_input"

    def send(payload):
        hass.async_create_task(mqtt.async_publish(hass, topic, payload, 0, False))

    forwarder = state["comfort_forwarder"] = ComfortForwarder(hass, entry, hub, send)
    entry.async_on_unload(hub.add_listener(forwarder.hub_changed))
    entry.async_on_unload(async_track_time_interval(hass, lambda _now: forwarder.publish(), REFRESH))
    forwarder.reconfigure()
    entry.async_on_unload(forwarder.stop)


# -- options flow (Configure -> Comfort) ---------------------------------------------


class ComfortOptionsSteps:
    """Mixin for the product options flow: house settings and window/door sensors per room."""

    async def async_step_comfort(self, user_input=None):
        return self.async_show_menu(step_id="comfort", menu_options=["comfort_settings", "comfort_contacts"])

    async def async_step_comfort_settings(self, user_input=None):
        import voluptuous as vol
        current = comfort_options(self.config_entry)
        errors = {}
        if user_input is not None:
            try:
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

    async def async_step_comfort_contacts(self, user_input=None):
        import voluptuous as vol
        rooms = self._comfort_rooms()
        if not rooms:
            return self.async_abort(reason="comfort_no_rooms")
        current = comfort_options(self.config_entry)
        errors = {}
        if user_input is not None:
            room_id = user_input.get("room")
            try:
                if room_id not in dict(rooms):
                    raise ComfortError("room", "room_invalid")
                contacts = validate_contacts(self.hass, list(user_input.get("contacts") or []))
            except ComfortError as err:
                errors[err.field] = err.code
            else:
                settings = {**current, "contacts": {**current["contacts"], room_id: contacts}}
                if not contacts:
                    settings["contacts"].pop(room_id, None)
                save_comfort(self.hass, self.config_entry, settings)
                return self.async_abort(reason="comfort_saved")
        room_id = (user_input or {}).get("room") or rooms[0][0]
        return self.async_show_form(
            step_id="comfort_contacts", errors=errors,
            data_schema=contacts_schema(vol, rooms, room_id, current["contacts"].get(room_id, [])),
            description_placeholders={"rooms": ", ".join(
                f"{name}: {len(current['contacts'].get(rid, []))}" for rid, name in rooms)})
