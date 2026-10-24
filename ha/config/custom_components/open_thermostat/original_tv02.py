"""Original TV02 reception evidence. Never a command ACK or valve readiness.

Pure bounded ingestion; the existing MQTT owner must supply the selected exact
binding, monotonic arrival and connection generation. No client/timer or writes.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re

from .original_temperature import _constant, _pairs

MAX_BYTES = 2048
MAX_RUNS = 8
PRODUCER = "openthermostat.z2m.original_tv02"
MANUFACTURERS = frozenset(("_TZE200_hue3yfsn", "_TZE200_lllliz3p"))
KINDS = frozenset(("commandDataResponse", "commandDataReport",
    "commandActiveStatusReport", "commandActiveStatusReportAlt"))
_KEYS = frozenset(("schema", "producer", "producer_run_id", "sequence", "device_ieee",
    "model", "zigbee_model", "manufacturer", "endpoint", "cluster", "message_kind",
    "tuya_sequence", "zcl_transaction", "received_at_unix_ms", "sampled_at_unix_ms",
    "command_correlated", "valve_ready", "control_qualified", "fields", "dropped_reports"))
_FIELD_KEYS = frozenset(("dp", "datatype", "raw_hex", "property", "value"))


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def decode(raw):
    """Validate the entire exact producer schema and independently decode raw DP."""
    if type(raw) not in (str, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("invalid TV02 report")
    if type(raw) is str and len(raw.encode()) > MAX_BYTES:
        raise ValueError("invalid TV02 report")
    report = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if type(report) is not dict or report.keys() != _KEYS:
        raise ValueError("invalid TV02 report")
    fixed = {"producer": PRODUCER, "model": "TV02-Zigbee", "zigbee_model": "TS0601",
        "cluster": "manuSpecificTuya"}
    if any(report[key] != value for key, value in fixed.items()):
        raise ValueError("invalid TV02 identity")
    if (type(report["producer_run_id"]) is not str or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", report["producer_run_id"])
            or type(report["device_ieee"]) is not str
            or not re.fullmatch(r"0x[0-9a-f]{16}", report["device_ieee"])
            or type(report["manufacturer"]) is not str or report["manufacturer"] not in MANUFACTURERS
            or type(report["message_kind"]) is not str or report["message_kind"] not in KINDS
            or report["sampled_at_unix_ms"] is not None
            or any(report[key] is not False for key in ("command_correlated", "valve_ready", "control_qualified"))):
        raise ValueError("invalid TV02 provenance")
    for key, low, high in (("schema", 1, 1), ("sequence", 1, 2**53-1),
            ("endpoint", 1, 240), ("received_at_unix_ms", 0, 2**53-1),
            ("dropped_reports", 0, 2**53-1)):
        if not _integer(report[key], low, high):
            raise ValueError("invalid TV02 integer")
    for key, maximum in (("tuya_sequence", 65535), ("zcl_transaction", 255)):
        if report[key] is not None and not _integer(report[key], 0, maximum):
            raise ValueError("invalid TV02 transaction")
    fields = report["fields"]
    if type(fields) is not list or not 1 <= len(fields) <= 5:
        raise ValueError("invalid TV02 fields")
    seen = set()
    for field in fields:
        if type(field) is not dict or field.keys() != _FIELD_KEYS:
            raise ValueError("invalid TV02 field")
        dp, datatype, raw_hex = field["dp"], field["datatype"], field["raw_hex"]
        if (not _integer(dp, 0, 255) or dp in seen or not _integer(datatype, 0, 5)
                or type(raw_hex) is not str or not re.fullmatch(r"(?:[0-9a-f]{2}){1,4}", raw_hex)):
            raise ValueError("invalid TV02 raw datapoint")
        seen.add(dp)
        raw_bytes = bytes.fromhex(raw_hex)
        raw_value = int.from_bytes(raw_bytes, "big")
        if dp in (16, 24):
            if datatype != 2 or len(raw_bytes) != 4:
                raise ValueError("invalid TV02 number")
            if dp == 16:
                if not 50 <= raw_value <= 300 or raw_value % 5:
                    raise ValueError("invalid TV02 target")
                prop = "target_centi_c"
            else:
                if raw_value > 600:
                    raise ValueError("invalid TV02 temperature")
                prop = "local_temperature_centi_c"
            expected = raw_value * 10
        elif dp == 2:
            if datatype != 4 or len(raw_bytes) != 1 or raw_value > 3:
                raise ValueError("invalid TV02 preset")
            prop, expected = "preset", ("auto", "manual", "holiday", "holiday")[raw_value]
        elif dp in (107, 10):
            if datatype != 1 or len(raw_bytes) != 1 or raw_value > 1:
                raise ValueError("invalid TV02 flag")
            prop = "heating_stop" if dp == 107 else "frost_protection"
            expected = bool(raw_value)
        else:
            raise ValueError("unsupported TV02 datapoint")
        if (field["property"] != prop or type(field["value"]) is not type(expected)
                or field["value"] != expected):
            raise ValueError("inconsistent TV02 datapoint")
    return report


class Tv02Reception:
    """One exact immutable selected source, bounded replay memory, no field cache.

    Arrival timestamps describe reception only. A matching target never becomes
    a command correlation: the future native owner must implement that separately.
    """

    def __init__(self, *, ieee, manufacturer, endpoint, maximum_age_ms, clock):
        if (type(ieee) is not str or not re.fullmatch(r"0x[0-9a-f]{16}", ieee)
                or type(manufacturer) is not str or manufacturer not in MANUFACTURERS
                or not _integer(endpoint, 1, 240)
                or not _integer(maximum_age_ms, 1, 86400000)):
            raise ValueError("invalid TV02 binding")
        self.identity = ieee, manufacturer, endpoint
        self.maximum_age_ms = maximum_age_ms
        self.clock = clock
        self.watermark = None
        self.clock_failed = False
        self.epoch = 0
        self.runs = {}
        self.record = None
        self.reason = "waiting"

    def invalidate(self, reason="disconnected"):
        self.epoch += 1
        self.record = None
        self.reason = reason

    def _now(self):
        now = self.clock()
        if (self.clock_failed or type(now) not in (int, float) or not math.isfinite(now)
                or self.watermark is not None and now < self.watermark):
            self.clock_failed = True
            self.invalidate("clock_invalid")
            return None
        self.watermark = now
        return now

    def receive(self, raw, *, retained, received_at, received_unix_ms, epoch):
        if retained is not False or type(epoch) is not int or epoch != self.epoch:
            return False
        try:
            report = decode(raw)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return False
        if (report["device_ieee"], report["manufacturer"], report["endpoint"]) != self.identity:
            return False
        now = self._now()
        if (now is None or type(received_at) not in (int, float) or not math.isfinite(received_at)
                or received_at > now or not _integer(received_unix_ms, 0, 2**53-1)):
            return False
        source_age = received_unix_ms - report["received_at_unix_ms"]
        elapsed_ms = (now - received_at) * 1000
        if not math.isfinite(elapsed_ms):
            return False
        age = source_age + math.ceil(elapsed_ms)
        if source_age < 0 or age >= self.maximum_age_ms:
            return False
        run, sequence = report["producer_run_id"], report["sequence"]
        current = next(reversed(self.runs), None)
        if run in self.runs:
            if run != current or sequence <= self.runs[run]:
                return False
        elif len(self.runs) >= MAX_RUNS:
            self.record = None
            self.reason = "run_limit"
            return False
        self.runs[run] = sequence
        self.record = report, source_age, received_at
        self.reason = "received_unqualified"
        return True

    def status(self):
        result = dict(status=self.reason, received_age_ms=None, fields={},
            command_correlated=False, valve_ready=False, control_qualified=False)
        now = self._now()
        if now is None:
            result["status"] = "clock_invalid"
        elif self.record:
            report, source_age, received_at = self.record
            elapsed_ms = (now - received_at) * 1000
            age = source_age + math.ceil(elapsed_ms) if math.isfinite(elapsed_ms) else None
            if age is None or age >= self.maximum_age_ms:
                result["status"] = "stale"
            else:
                result.update(status="received_unqualified", received_age_ms=age,
                    fields={field["property"]: field["value"] for field in report["fields"]})
        return result


@dataclass(frozen=True)
class Tv02DiagnosticSource:
    """Explicit source-owned receive pin; never loaded from options or broker JSON.

    The producer uses this same reviewed manufacturer/endpoint. A matching source
    is diagnostic metadata only and cannot authorize a valve action.
    """

    entry_unique_id: str
    room_id: str
    reference: object
    manufacturer: str
    endpoint: int


class OriginalTv02Reports:
    """Selected native TV02 ownership around the pure bounded receiver.

    Default pins are empty. No fingerprint or endpoint is guessed from a friendly
    name, HA state, first arriving packet or a different TS0601 device.
    """

    SUFFIX = "/bridge/openthermostat/original_tv02"

    def __init__(self, runtime, sources=()):
        from homeassistant.helpers import device_registry as dr
        from .device_metadata import MetadataUnavailable, selected_device
        from .native_binding import native_binding_identity
        from .v1_model import EntityReference

        if type(sources) is not tuple or len(sources) > 64:
            raise ValueError("invalid TV02 diagnostic sources")
        self.runtime = runtime
        self.epoch = 0
        self.bindings = {}
        self.retired = set()
        self.by_ieee = {}
        seen_devices = set()
        for source in sources:
            if (type(source) is not Tv02DiagnosticSource
                    or type(source.entry_unique_id) is not str
                    or not source.entry_unique_id
                    or source.entry_unique_id != runtime.entry.unique_id
                    or type(source.reference) is not EntityReference
                    or type(source.room_id) is not str):
                raise ValueError("invalid TV02 diagnostic source")
            room = runtime.rooms.get(source.room_id)
            if room is None or source.reference not in room.actuators:
                raise ValueError("TV02 source is not a selected actuator")
            try:
                selected = selected_device(runtime.hass, source.reference.as_dict())
            except (MetadataUnavailable, ValueError) as error:
                raise ValueError("TV02 native source unavailable") from error
            identity = native_binding_identity(runtime.hass, selected.entity_id)
            device = dr.async_get(runtime.hass).async_get(selected.device_id)
            key = (source.room_id, source.reference)
            if (not selected.entity_id.startswith("climate.") or identity is None
                    or device is None or device.model_id != "TV02-Zigbee"
                    or key in self.bindings or selected.ieee in seen_devices):
                raise ValueError("invalid TV02 native identity")
            core = Tv02Reception(ieee=selected.ieee, manufacturer=source.manufacturer,
                endpoint=source.endpoint, maximum_age_ms=room.maximum_age_ms,
                clock=runtime.clock)
            self.bindings[key] = (selected, identity, core)
            self.by_ieee[selected.ieee] = key
            seen_devices.add(selected.ieee)
        self.topics = frozenset(selected.prefix + self.SUFFIX
            for selected, _, _ in self.bindings.values())

    def _current(self, key):
        from .device_metadata import MetadataUnavailable, selected_device
        from .native_binding import native_binding_identity

        if key in self.retired:
            return False
        room_id, reference = key
        room = self.runtime.rooms.get(room_id)
        selected, identity, core = self.bindings[key]
        try:
            current = (room is not None and reference in room.actuators
                and selected_device(self.runtime.hass, reference.as_dict()) == selected
                and native_binding_identity(self.runtime.hass, selected.entity_id) == identity)
        except (MetadataUnavailable, ValueError):
            current = False
        if not current:
            self.retired.add(key)
            core.invalidate("binding_changed")
        return current

    def invalidate(self, reason="disconnected"):
        self.epoch += 1
        for _, _, core in self.bindings.values():
            core.invalidate(reason)

    def recheck(self):
        """Use existing native registry events; no additional listeners."""
        before = len(self.retired)
        for key in self.bindings:
            self._current(key)
        return len(self.retired) != before

    def receive(self, topic, raw, *, retained, received_at, received_unix_ms, epoch):
        if (topic not in self.topics or retained is not False
                or type(epoch) is not int or epoch != self.epoch):
            return False
        try:
            report = decode(raw)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return False
        key = self.by_ieee.get(report["device_ieee"])
        if key is None:
            return False
        selected, _, core = self.bindings[key]
        if topic != selected.prefix + self.SUFFIX or not self._current(key):
            return False
        return core.receive(raw, retained=retained, received_at=received_at,
            received_unix_ms=received_unix_ms, epoch=core.epoch)

    def status(self, room_id):
        result = {}
        for key, (selected, _, core) in self.bindings.items():
            if key[0] == room_id:
                self._current(key)
                result[selected.entity_id] = core.status()
        return result
