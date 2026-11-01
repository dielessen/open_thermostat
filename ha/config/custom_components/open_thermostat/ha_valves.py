"""Radiator valves Home Assistant controls (model ``ha_climate``), driven on the E32's rules.

A valve in ZHA, Z-Wave, Shelly or a cloud integration is a ``climate`` entity in
Home Assistant, not a Zigbee2MQTT device the E32 can reach. The E32 lists it in
its valve record (the name is the entity id) and in its ``trv`` status, and never
sends anything for it; Home Assistant drives it with the E32's own rules
(src/control/TrvControl.h):

- only while the E32 reports ``trv.output`` (it controls the boiler itself) and the
  room's valve control is on. Otherwise nothing is sent and the valve keeps its
  last setpoint, as a Zigbee2MQTT valve does without the E32;
- the room's effective target from the E32 telemetry, frost protection (8 °C) while
  the room is off; clamped to the entity's min_temp/max_temp and rounded to its
  target_temp_step (else 0.5);
- ``climate.set_temperature`` only on a change of at least 0.5 °C, at most once a
  minute, and again after 6 h; ``climate.set_hvac_mode`` heat once per control
  period when the entity has it and is in another mode. Never ``turn_off``;
- health: unavailable or unknown for 2 h is offline; the battery is a battery
  sensor on the same device (else its low-battery binary sensor, else a battery
  attribute of the entity), low at 20 % or on; the opening is a ``valve_position``/``position`` attribute or a position /
  pi_heating_demand sensor on the device, when there is one.

A failing service call is logged once per value and tried again a minute later at
the earliest: never an exception into the telemetry listeners, never a write storm.
"""
from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .heating_link import celsius, number

_LOGGER = logging.getLogger(__name__)

HA_MODEL = "ha_climate"
FROST_C = 8.0              # TrvControl::frostCentiC
STEP_C = 0.5               # TrvControl::setpointStepCentiC
MIN_GAP = 60               # s, TrvControl::setpointMinGapMs
REFRESH = 6 * 3600         # s, TrvControl::setpointRefreshMs
STALE = 2 * 3600           # s, TrvControl::staleMs
LOW_BATTERY = 20           # %, TrvControl::lowBatteryPct
CALL_TIMEOUT = 30          # s for one service call (a cloud integration may hang)
GONE = ("unavailable", "unknown")
POSITION_WORDS = ("position", "pi_heating_demand")


def ha_valve_names(room):
    """The ha_climate valves (entity ids) of one room's ``trv`` document."""
    return [v["name"] for v in (room or {}).get("valves", []) if v.get("model") == HA_MODEL and type(v.get("name")) is str]


def room_target(status_room):
    """The room's effective target in °C; frost protection while it is off or has none (TrvControl::step)."""
    if status_room.get("status") == "inactive" or status_room.get("state") == "inactive":
        return FROST_C
    value = number(status_room.get("setpoint"), 0, 50)
    return value if value is not None else FROST_C


def _fahrenheit(hass):
    return hass.config.units.temperature_unit == UnitOfTemperature.FAHRENHEIT


def planned(hass, state, target_c):
    """The setpoint for the entity in its unit: rounded to its step (else 0.5), within its limits."""
    value = target_c * 9 / 5 + 32 if _fahrenheit(hass) else target_c
    step = number(state.attributes.get("target_temp_step"), 0.01, 5) or STEP_C
    value = round(round(value / step) * step, 2)
    low, high = number(state.attributes.get("min_temp"), -100, 1000), number(state.attributes.get("max_temp"), -100, 1000)
    if low is not None:
        value = max(value, low)
    if high is not None:
        value = min(value, high)
    return value


class HaValveDriver:
    """One per entry: drives the ha_climate valves and tells their health (e32_valves.room_valves)."""

    def __init__(self, hass, hub, clock=time.monotonic):
        self.hass, self.hub, self.clock = hass, hub, clock
        self.sent = {}        # entity -> (value in its unit, clock) of the last setpoint it took
        self.attempt = {}     # entity -> clock of the last setpoint call, also a failed one
        self.mode_done = set()  # the entities whose hvac mode was handled this control period
        self.missing = {}     # entity -> clock since it is unavailable, unknown or gone
        self.warned = {}      # (entity, service) -> the value last warned about
        self.busy = set()
        self._tracked, self._unsubscribe, self._retry = (), None, None

    # -- what Home Assistant knows of a valve -----------------------------------------------
    def _device_entities(self, entity_id):
        registry = er.async_get(self.hass)
        entry = registry.async_get(entity_id)
        if entry is None or entry.device_id is None:
            return []
        return [e for e in er.async_entries_for_device(registry, entry.device_id) if e.entity_id != entity_id]

    def _related(self, entity_id):
        """(battery %, battery low, position %) from the valve's own device, each None when unknown."""
        pct = low = position = None
        for entry in self._device_entities(entity_id):
            state = self.hass.states.get(entry.entity_id)
            if state is None or state.state in GONE:
                continue
            kind = entry.device_class or entry.original_device_class or state.attributes.get("device_class")
            if entry.domain == "sensor" and kind == "battery" and pct is None:
                value = number(state.state, 0, 100)
                pct = round(value) if value is not None else None
            elif entry.domain == "binary_sensor" and kind == "battery" and low is None and state.state in ("on", "off"):
                low = state.state == "on"
            elif entry.domain == "sensor" and position is None and any(
                    word in " ".join(str(x or "") for x in (entry.entity_id, entry.original_name, entry.translation_key))
                    .lower().replace(" ", "_") for word in POSITION_WORDS):
                value = number(state.state, 0, 100)
                position = round(value) if value is not None else None
        return pct, low, position

    def view(self, entity_id):
        """The valve as the ``trv`` status shows a Zigbee2MQTT valve: health and what is known."""
        state, now = self.hass.states.get(entity_id), self.clock()
        gone = state is None or state.state in GONE
        if gone:
            since = self.missing.setdefault(entity_id, now)
        else:
            self.missing.pop(entity_id, None)
        pct, low, position = self._related(entity_id)
        found = {}
        if not gone:
            for key in ("valve_position", "position"):
                value = number(state.attributes.get(key), 0, 100)
                if value is not None:
                    position = round(value)
                    break
            if pct is None:  # some integrations put it on the climate entity itself
                value = number(state.attributes.get("battery_level", state.attributes.get("battery")), 0, 100)
                pct = round(value) if value is not None else None
            setpoint = celsius(state.attributes.get("temperature"), self.hass.config.units.temperature_unit, 0, 50)
            if setpoint is not None:
                found["setpoint_c"] = setpoint
        if position is not None:
            found["position_pct"] = position
        if pct is not None:
            found["battery_pct"] = pct
        if low is not None:
            found["battery_low"] = low
        if gone and now - since >= STALE:
            health = "offline"
        elif (pct is not None and pct <= LOW_BATTERY) or low:
            health = "low_battery"
        else:
            health = "unknown" if gone else "ok"
        return {**found, "health": health}

    def overlay(self, room):
        """The room's ``trv`` document with this view of its ha_climate valves (the others unchanged)."""
        if not ha_valve_names(room):
            return room
        return {**room, "valves": [{**v, **self.view(v["name"])} if v.get("model") == HA_MODEL else v
                                   for v in room.get("valves", [])]}

    # -- driving -------------------------------------------------------------------------------
    @callback
    def _timer(self, _now=None):
        self._retry = None
        self.evaluate()

    @callback
    def evaluate(self):
        hub, now = self.hub, self.clock()
        self._follow()
        trv = (hub.status or {}).get("trv") if hub.fresh else None
        output = type(trv) is dict and trv.get("output") is True
        if not output:
            self.mode_done.clear()  # every control period ended (also with the E32 offline)
        threshold = STEP_C * 9 / 5 if _fahrenheit(self.hass) else STEP_C
        wait = None
        for room_id, room in hub.valves.items():
            names = ha_valve_names(room)
            status_room = hub.rooms.get(room_id)
            for name in names:
                self.view(name)  # keeps the time it went missing, also while nothing is driven
            if not (output and room.get("control") is True and status_room is not None):
                self.mode_done.difference_update(names)  # the control period ended
                continue
            target = room_target(status_room)
            for name in names:
                state = self.hass.states.get(name)
                if name in self.busy or state is None or state.state in GONE:
                    continue
                modes = state.attributes.get("hvac_modes") or ()
                mode = name not in self.mode_done and "heat" in modes and state.state != "heat"
                if name not in self.mode_done and not mode:
                    self.mode_done.add(name)  # already heating, or no heat mode to choose
                value = planned(self.hass, state, target)
                last, tried = self.sent.get(name), self.attempt.get(name)
                if last is None and not mode and number(state.attributes.get("temperature"), -100, 1000) == value:
                    self.sent[name] = (value, now)  # it already has it (an HA restart): nothing to send
                    continue
                changed = last is None or abs(last[0] - value) >= threshold - 1e-6
                refresh = last is not None and now - last[1] >= REFRESH
                gap = MIN_GAP - (now - tried) if tried is not None else 0
                setpoint = (changed or refresh) and gap <= 0
                if (changed or refresh) and gap > 0:
                    wait = min(wait or MIN_GAP, gap)
                if not (mode or setpoint):
                    continue
                if mode:
                    self.mode_done.add(name)
                self.busy.add(name)
                self.hass.async_create_task(self._send(name, room_id, value if setpoint else None, mode),
                                            f"OpenThermostat valve {name}")
        if wait is not None and self._retry is None:
            self._retry = async_call_later(self.hass, wait + 1, self._timer)

    async def _call(self, name, service, data, value):
        try:
            async with asyncio.timeout(CALL_TIMEOUT):
                await self.hass.services.async_call("climate", service, {"entity_id": name, **data}, blocking=True)
        except Exception as err:  # noqa: BLE001 - any integration's failure; never into the listeners
            if self.warned.get((name, service)) != value:
                self.warned[(name, service)] = value
                _LOGGER.warning("OpenThermostat could not %s on radiator valve %s (%s): %s",
                                service.replace("_", " "), name, value, str(err) or type(err).__name__)
            return False
        self.warned.pop((name, service), None)
        return True

    async def _send(self, name, room_id, value, mode):
        try:
            if mode:
                await self._call(name, "set_hvac_mode", {"hvac_mode": "heat"}, "heat")
            if value is not None:
                self.attempt[name] = self.clock()
                if await self._call(name, "set_temperature", {"temperature": value}, value):
                    self.sent[name] = (value, self.clock())
                    _LOGGER.debug("E32 room %s: radiator valve %s set to %s", room_id, name, value)
        finally:
            self.busy.discard(name)

    # -- lifecycle -----------------------------------------------------------------------------
    @callback
    def _follow(self):
        """Evaluate again as soon as a valve changes (back online, another target)."""
        names = tuple(sorted({n for room in self.hub.valves.values() for n in ha_valve_names(room)}))
        if names == self._tracked:
            return
        self._stop_tracking()
        self._tracked = names
        if names:
            self._unsubscribe = async_track_state_change_event(self.hass, list(names), self._changed)

    @callback
    def _changed(self, event):
        old, new = event.data.get("old_state"), event.data.get("new_state")
        # Only availability matters here; the targets follow the E32 telemetry.
        if (old is None or old.state in GONE) != (new is None or new.state in GONE):
            self.evaluate()

    @callback
    def _stop_tracking(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._tracked = ()

    @callback
    def start(self):
        remove = self.hub.add_listener(self.evaluate)
        self.evaluate()

        @callback
        def stop():
            remove()
            self._stop_tracking()
            if self._retry is not None:
                self._retry()
                self._retry = None
        return stop
