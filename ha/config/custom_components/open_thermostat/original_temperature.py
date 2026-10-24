"""Original Zigbee reception evidence, never a QualifiedReport/control input.

No listener, timer, task, Store or state write lives here. The native MQTT owner
feeds its existing worker and owns teardown. Fixed selected bindings only.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re

from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .device_metadata import MetadataUnavailable, selected_device
from .native_binding import native_binding_identity

MAX_BYTES = 1024
MAX_RUNS = 8
SUFFIX = "/bridge/openthermostat/original_temperature"
_KEYS = frozenset(("schema", "producer", "producer_run_id", "sequence", "device_ieee",
    "model", "zigbee_model", "endpoint", "cluster", "message_kind", "property",
    "raw_value", "value_centi_c", "zcl_transaction", "received_at_unix_ms",
    "sampled_at_unix_ms", "acquisition_age_verified", "control_qualified", "dropped_reports"))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(_):
    raise ValueError("invalid constant")


def decode(raw):
    """The exact producer schema; no broker-supplied qualification flags."""
    if type(raw) not in (bytes, str) or len(raw) > MAX_BYTES:
        raise ValueError("report invalid")
    if type(raw) is str and len(raw.encode()) > MAX_BYTES:
        raise ValueError("report invalid")
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if type(value) is not dict or value.keys() != _KEYS:
        raise ValueError("report invalid")
    fixed = {"producer": "openthermostat.z2m.original_temperature",
        "model": "WSDCGQ11LM", "zigbee_model": "lumi.weather",
        "cluster": "msTemperatureMeasurement", "property": "temperature"}
    if any(value[key] != expected for key, expected in fixed.items()):
        raise ValueError("report invalid")
    if (type(value["schema"]) is not int or value["schema"] != 1
            or type(value["producer_run_id"]) is not str
            or not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value["producer_run_id"])
            or type(value["device_ieee"]) is not str
            or not re.fullmatch(r"0x[0-9a-f]{16}", value["device_ieee"])
            or value["message_kind"] not in ("attributeReport", "readResponse")
            or value["sampled_at_unix_ms"] is not None
            or value["acquisition_age_verified"] is not False
            or value["control_qualified"] is not False):
        raise ValueError("report invalid")
    for key, low, high in (("sequence", 1, 2**53-1), ("endpoint", 1, 240),
            ("received_at_unix_ms", 0, 2**53-1), ("dropped_reports", 0, 2**53-1),
            ("raw_value", -6499, 6499), ("value_centi_c", -6499, 6499)):
        if type(value[key]) is not int or not low <= value[key] <= high:
            raise ValueError("report invalid")
    transaction = value["zcl_transaction"]
    if (transaction is not None and (type(transaction) is not int or not 0 <= transaction <= 255)
            or value["raw_value"] != value["value_centi_c"]):
        raise ValueError("report invalid")
    return value


@dataclass(frozen=True)
class Binding:
    selected: object
    identity: tuple
    maximum_age_ms: int


class OriginalTemperatureReports:
    def __init__(self, runtime):
        self.runtime = runtime
        self.hass = runtime.hass
        self.bindings = {}
        self.epoch = 0
        self.records = {}
        self.runs = {}
        self.reasons = {}
        self.retired = set()
        self.clock_watermark = runtime.clock()
        self.clock_failed = (type(self.clock_watermark) not in (int, float)
            or not math.isfinite(self.clock_watermark))
        for room in runtime.rooms.values():
            try:
                selected = selected_device(self.hass, room.temperature.as_dict())
            except (MetadataUnavailable, ValueError):
                continue
            entity = er.async_get(self.hass).async_get(selected.entity_id)
            device = dr.async_get(self.hass).async_get(selected.device_id)
            identity = native_binding_identity(self.hass, selected.entity_id)
            if (selected.sensor_property == "temperature" and identity is not None
                    and entity is not None and device is not None
                    and device.model_id == "WSDCGQ11LM"):
                self.bindings[room.room_id] = Binding(selected, identity, room.maximum_age_ms)
        self.topics = frozenset(binding.selected.prefix + SUFFIX for binding in self.bindings.values())

    def _now(self):
        now = self.runtime.clock()
        if (self.clock_failed or type(now) not in (int, float)
                or not math.isfinite(now) or now < self.clock_watermark):
            self.clock_failed = True
            self.invalidate("clock_invalid")
            return None
        self.clock_watermark = now
        return now

    def _current(self, room_id):
        if room_id in self.retired:
            return False
        binding = self.bindings[room_id]
        room = self.runtime.rooms.get(room_id)
        try:
            selected = selected_device(self.hass, room.temperature.as_dict()) if room else None
        except (MetadataUnavailable, ValueError):
            self.retired.add(room_id)
            return False
        # Entity rename can change its display id; the captured diagnostic owner
        # is deliberately withdrawn until the next native connection rebuild.
        current = (room is not None and room.maximum_age_ms == binding.maximum_age_ms
            and selected == binding.selected and native_binding_identity(
            self.hass, selected.entity_id) == binding.identity)
        if not current:
            self.retired.add(room_id)
        return current

    def recheck(self):
        """Retire changed native identities on existing registry events.

        Restoring registry fields must not revive earlier reception evidence.
        No new owner, discovery fallback or source qualification is created.
        """
        before = len(self.retired)
        for room_id in self.bindings:
            if not self._current(room_id):
                self.records.pop(room_id, None)
                self.reasons[room_id] = "binding_changed"
        return len(self.retired) != before

    def invalidate(self, reason="disconnected"):
        self.epoch += 1
        self.records.clear()
        self.reasons = {room_id: reason for room_id in self.bindings}
        # Replay watermarks survive reconnect. No cache requalification.

    def receive(self, topic, raw, *, retained, received_at, received_unix_ms, epoch):
        if topic not in self.topics or retained or epoch != self.epoch:
            return False
        try:
            value = decode(raw)
        except (ValueError, UnicodeError, RecursionError, TypeError):
            return False
        now = self._now()
        if (type(received_at) not in (int, float) or not math.isfinite(received_at)
                or now is None or received_at > now
                or type(received_unix_ms) is not int):
            return False
        source_age = received_unix_ms - value["received_at_unix_ms"]
        accepted = False
        for room_id, binding in self.bindings.items():
            if (topic != binding.selected.prefix + SUFFIX
                    or value["device_ieee"] != binding.selected.ieee):
                continue
            if not self._current(room_id):
                self.records.pop(room_id, None)
                self.reasons[room_id] = "binding_changed"
                continue
            elapsed_ms = (now - received_at) * 1000
            if not math.isfinite(elapsed_ms):
                continue
            age = source_age + math.ceil(elapsed_ms)
            if source_age < 0 or age >= binding.maximum_age_ms:
                continue
            run = value["producer_run_id"]
            history = self.runs.setdefault(room_id, {})
            current = next(reversed(history), None)
            if run in history:
                if run != current or value["sequence"] <= history[run]:
                    continue
            elif len(history) >= MAX_RUNS:
                self.records.pop(room_id, None)
                self.reasons[room_id] = "run_limit"
                continue
            history[run] = value["sequence"]
            self.records[room_id] = (value["value_centi_c"], value["message_kind"],
                source_age, received_at)
            self.reasons.pop(room_id, None)
            accepted = True
        return accepted

    def status(self, room_id):
        if room_id not in self.bindings:
            return None
        result = {"status": "waiting", "control_qualified": False,
            "acquisition_age_verified": False, "received_age_ms": None,
            "value_centi_c": None, "message_kind": None}
        now = self._now()
        if now is None:
            result["status"] = "clock_invalid"
        elif not self._current(room_id):
            self.records.pop(room_id, None)
            result["status"] = "binding_changed"
        elif record := self.records.get(room_id):
            value, kind, source_age, received_at = record
            elapsed = now - received_at
            age = source_age + math.ceil(max(0, elapsed) * 1000) if math.isfinite(elapsed) else None
            if age is None or elapsed < 0 or age >= self.bindings[room_id].maximum_age_ms:
                result["status"] = "stale"
            else:
                result.update(status="received_unqualified", received_age_ms=age,
                    value_centi_c=value, message_kind=kind)
        else:
            result["status"] = self.reasons.get(room_id, "waiting")
        return result
