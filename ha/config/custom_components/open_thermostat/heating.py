"""Bounded observation-window room models, never delivered-heat metering."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging
import math
import re

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later

from .const import CONF_TOPIC_PREFIX
from .room_identity import room_key

_LOGGER = logging.getLogger(__name__)
DEFAULT_RADIATOR_EXPONENT = 1.3
DEFAULT_RETURN_TEMPERATURE_DROP = 10.0
EMS_TTL = 30.0
ROOM_TTL = 45.0
TEMPERATURE_TTL = 300.0
MAX_RATED_POWER = 20000.0
DEFINITION = "bounded-room-model-v2"


def boolean_state(value: object) -> bool | None:
    """Normalize current and older boolean states (not source qualification)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("on", "true", "1"):
            return True
        if normalized in ("off", "false", "0"):
            return False
    return None


def finite(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def millis(value):
    return type(value) is int and 0 <= value <= 2**53-1


def context(value):
    if (not isinstance(value, dict) or type(value.get("schema")) is not int
            or value["schema"] != 2 or not isinstance(value.get("boot_id"), str)
            or re.fullmatch("[0-9a-f]{32}", value["boot_id"]) is None
            or not millis(value.get("source_ms"))):
        return None
    return value["boot_id"], value["source_ms"]


@dataclass
class RoomHeating:
    key: str
    index: int
    name: str | None
    current_temperature: float | None = None
    requested: bool = False
    rated_power: float = 0.0
    heating_seconds: float = 0.0
    estimated_energy_kwh: float = 0.0
    present: bool = True
    temperature_deadline: float = 0.0


class HeatingTracker:
    """Receipt/source-age bounded model. No authority for control or actuation."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, *, clock=None) -> None:
        self.hass, self.entry = hass, entry
        self.prefix = entry.data[CONF_TOPIC_PREFIX]
        self.rooms: dict[str, RoomHeating] = {}
        self.online = False
        self.heating_active: bool | None = None
        self.hot_water_active: bool | None = None
        self.flow_temperature: float | None = None
        self.radiator_exponent = DEFAULT_RADIATOR_EXPONENT
        self.return_temperature_drop = DEFAULT_RETURN_TEMPERATURE_DROP
        self._clock = clock or hass.loop.time
        self._last_update = self._clock()
        self._room_boot = self._ems_boot = None
        self._room_source = self._ems_source = -1
        self._ems_sequence = -1
        self._room_offset = self._ems_offset = 0.0
        self._room_deadline = self._ems_deadline = 0.0
        self._listeners: set[Callable[[], None]] = set()
        self._unsubscribers: list[Callable[[], None]] = []
        self._timer_cancel = None
        self._started = False
        self._boiler_values = {}

    async def async_start(self) -> None:
        await mqtt.async_wait_for_mqtt_client(self.hass)
        try:
            for topic, handler in (("status", self._handle_status),
                    ("room_data", self._handle_rooms), ("ems_status", self._handle_ems)):
                self._unsubscribers.append(await mqtt.async_subscribe(
                    self.hass, f"{self.prefix}/{topic}", handler))
        except BaseException:
            await self.async_stop()
            raise
        self._started = True
        self._notify()

    async def async_stop(self) -> None:
        self._integrate()
        self._started = False
        if self._timer_cancel:
            self._timer_cancel()
            self._timer_cancel = None
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._listeners.clear()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        listener()
        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)
        return remove_listener

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()
        if self._timer_cancel:
            self._timer_cancel()
            self._timer_cancel = None
        if self._started and self.online and (self.rooms or self._ems_deadline > self._clock()):
            now = self._clock()
            deadlines = [d for d in (self._room_deadline, self._ems_deadline,
                *(r.temperature_deadline for r in self.rooms.values())) if d > now]
            delay = min(30.0, min(deadlines)-now) if deadlines else 30.0
            self._timer_cancel = async_call_later(self.hass, max(0.001, delay), self._tick)

    @callback
    def _tick(self, _=None):
        self._timer_cancel = None
        self._integrate()
        self._notify()

    def _deadline(self, room):
        return min(self._room_deadline, self._ems_deadline, room.temperature_deadline)

    def _qualified(self, room, at):
        return (self.online and room.present and self._room_boot is not None
                and self._room_boot == self._ems_boot and at < self._deadline(room))

    def _heating(self, room, at):
        return bool(self._qualified(room, at) and room.requested
                    and self.heating_active is True and self.hot_water_active is False)

    def _power(self, room, at):
        if (not self._qualified(room, at) or not finite(room.rated_power, 1, MAX_RATED_POWER)
                or room.current_temperature is None or self.flow_temperature is None):
            return None
        if not self._heating(room, at):
            return 0.0
        mean = self.flow_temperature-self.return_temperature_drop/2
        value = room.rated_power * (max(mean-room.current_temperature, 0)/50)**self.radiator_exponent
        return value if finite(value, 0, 200000) else None

    def _integrate(self) -> None:
        now = self._clock()
        start = self._last_update
        self._last_update = now
        if now < start:
            self._room_deadline = self._ems_deadline = 0
            return
        for room in self.rooms.values():
            elapsed = max(0.0, min(now, self._deadline(room))-start)
            if elapsed <= 0 or not self._heating(room, start):
                continue
            room.heating_seconds += elapsed
            power = self._power(room, start)
            if power is not None:
                room.estimated_energy_kwh += power*elapsed/3_600_000

    def room_available(self, key: str) -> bool:
        room = self.rooms.get(key)
        return bool(self.online and room and room.present)

    def ems_available(self) -> bool:
        return self.online and self._clock() < self._ems_deadline and self._ems_boot is not None

    def boiler_reading(self, field):
        return self._boiler_values.get(field) if self.ems_available() else None

    def estimate_available(self, key: str) -> bool:
        room = self.rooms.get(key)
        return bool(room and self._qualified(room, self._clock()))

    def is_heating(self, key: str) -> bool:
        """Qualified room request + boiler-reported CH mode; NOT heat delivery."""
        room = self.rooms.get(key)
        return bool(room and self._heating(room, self._clock()))

    def estimated_power(self, key: str) -> float | None:
        room = self.rooms.get(key)
        return self._power(room, self._clock()) if room else None

    @callback
    def set_rated_power(self, key: str, value: float) -> None:
        if not finite(value, 0, MAX_RATED_POWER):
            raise HomeAssistantError("Rated radiator power must be finite, 0..20000 W")
        self._integrate()
        if room := self.rooms.get(key):
            room.rated_power = value
            self._notify()

    @callback
    def restore_totals(self, key: str, seconds: float | None = None, energy: float | None = None) -> None:
        """Only new definition-v2 entity identities may call this restore."""
        if room := self.rooms.get(key):
            if finite(seconds, 0, 1e12):
                room.heating_seconds = max(room.heating_seconds, seconds)
            if finite(energy, 0, 1e9):
                room.estimated_energy_kwh = max(room.estimated_energy_kwh, energy)
            self._notify()

    @callback
    def _handle_status(self, message: ReceiveMessage) -> None:
        self._integrate()
        # Retained status is only a connectivity hint. It cannot revive any
        # observation window; fresh non-retained data is still required. This
        # permits normal late subscription without demanding a device reconnect.
        self.online = message.payload == "on"
        if not self.online or getattr(message, "retain", False):
            self._room_deadline = self._ems_deadline = 0
        self._notify()

    @callback
    def _handle_rooms(self, message: ReceiveMessage) -> None:
        if not isinstance(message.payload, str) or len(message.payload) > 65536:
            return
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError):
            return
        rooms = payload.get("rooms") if isinstance(payload, dict) else None
        if not isinstance(rooms, list):
            return
        self._integrate()
        now = self._clock()
        stamp = context(payload.get("roomObservation"))
        qualified = self.online and stamp is not None and not getattr(message, "retain", False)
        if qualified:
            boot, source = stamp
            if boot == self._room_boot and source <= self._room_source:
                return  # duplicate or backwards snapshot never renews a deadline
            if boot != self._room_boot:
                self._room_offset = now-source/1000
            self._room_boot, self._room_source = boot, source
            self._room_deadline = min(now+ROOM_TTL, self._room_offset+source/1000+ROOM_TTL)
        else:
            self._room_deadline = 0
        boiler_started = boolean_state(payload.get("boilerStarted"))
        active_keys = set()
        for index, value in enumerate(rooms):
            if not isinstance(value, dict) or (key := room_key(value)) is None:
                continue
            active_keys.add(key)
            room = self.rooms.get(key)
            if room is None:
                room = self.rooms[key] = RoomHeating(key, index, value.get("name"))
            room.present, room.index = True, index
            room.name = value.get("name") if isinstance(value.get("name"), str) else room.name
            temperature, age = value.get("currentTemp"), value.get("currentTempAgeMs")
            room.current_temperature = temperature/100 if finite(temperature, -2000, 6000) else None
            room.temperature_deadline = (
                min(now+(TEMPERATURE_TTL-age/1000), self._room_offset+(source-age)/1000+TEMPERATURE_TTL)
                if qualified and millis(age) and age <= source and age < TEMPERATURE_TTL*1000
                and room.current_temperature is not None else 0)
            requested = value.get("isBeingHeated", value.get("isBeingHeatedState"))
            room.requested = (boolean_state(requested) is True or (boiler_started is True
                and boolean_state(value.get("shouldContinueHeating")) is True))
        for key in self.rooms.keys()-active_keys:
            self.rooms[key].requested = False
            self.rooms[key].present = False
        self._notify()

    @callback
    def _handle_ems(self, message: ReceiveMessage) -> None:
        if not isinstance(message.payload, str) or len(message.payload) > 65536:
            return
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        self._integrate()
        value = payload.get("roomEstimateObservation")
        stamp = context(value)
        now = self._clock()
        valid = self.online and stamp is not None and not getattr(message, "retain", False)
        if valid:
            boot, source = stamp
            sequence, observed = value.get("sequence"), value.get("observed_ms")
            valid = (millis(sequence) and sequence > 0 and millis(observed) and observed <= source
                and type(value.get("ttl_ms")) is int and value["ttl_ms"] == 30000
                and value.get("quality") == "reported_plus_not_delivery_proof"
                and value.get("valid") is True and type(value.get("ch")) is bool
                and type(value.get("dhw")) is bool and type(value.get("flame")) is bool
                and type(value.get("pump")) is bool
                and finite(value.get("supply_c"), 0, 110)
                and finite(value.get("selected_flow_c"), 0, 110)
                and finite(value.get("modulation_pct"), 0, 100))
            if valid and boot == self._ems_boot and sequence <= self._ems_sequence:
                return  # reads can change source_ms, not the observation sequence
        if not valid:
            self._ems_deadline = 0
            self._boiler_values = {}
            self.heating_active = self.hot_water_active = self.flow_temperature = None
        else:
            if boot != self._ems_boot:
                self._ems_offset = now-source/1000
            elif source < self._ems_source:
                self._ems_deadline = 0
                self._notify()
                return
            self._ems_boot, self._ems_source, self._ems_sequence = boot, source, sequence
            self._ems_deadline = min(now+(EMS_TTL-(source-observed)/1000),
                self._ems_offset+observed/1000+EMS_TTL)
            self._boiler_values = {key:value[key] for key in
                ("ch","dhw","flame","pump","selected_flow_c","supply_c","modulation_pct")}
            self.heating_active = value["ch"]
            self.hot_water_active = value["dhw"]
            self.flow_temperature = value["supply_c"]
        self._notify()
