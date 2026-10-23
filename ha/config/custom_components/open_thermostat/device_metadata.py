"""Bounded selected-device observations on HA's existing MQTT connection.

Discovery and converter declarations are information, never measurement evidence
or permission to control a valve. No credentials, second client or publications.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from contextlib import ExitStack
import json
import math
import re

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import DATA_MQTT
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .native_plan import native_entry_state
from .v1_model import EntityReference

TIMEOUT = 12
MAX_BYTES = 2 * 1024 * 1024
_IEEE = re.compile(r"zigbee2mqtt_(0x[0-9a-fA-F]{16})")
_ROLES = {
    "device_temperature": "device_temperature", "temperature": "temperature",
    "local_temperature": "local_temperature", "local_temperature_calibration": "calibration",
    "temperature_calibration": "calibration",
    "external_temperature": "external_temperature", "external_temperature_input": "external_temperature",
    "temperature_sensor_select": "temperature_source", "temperature_source": "temperature_source",
    "current_heating_setpoint": "setpoint", "occupied_heating_setpoint": "setpoint",
    "heating_setpoint": "setpoint", "position": "valve_position", "valve_position": "valve_position",
    "valve_opening_degree": "valve_position", "system_mode": "system_mode", "preset": "preset",
    "running_state": "running_state", "running_mode": "running_state",
}


class MetadataUnavailable(ValueError):
    """Static public reason; never wraps raw broker or discovery content."""


@dataclass(frozen=True)
class SelectedDevice:
    entity_id: str
    platform: str
    unique_id: str = field(repr=False)
    device_id: str = field(repr=False)
    ieee: str = field(repr=False)
    prefix: str = field(repr=False)
    sensor_property: str | None


def _text(value, maximum=160):
    return value if type(value) is str and len(value) <= maximum and not any(ord(c) < 32 for c in value) else None


def _topic(value):
    return (type(value) is str and 0 < len(value.encode()) <= 256
            and not any(ord(c) < 32 or c in "#+" for c in value)
            and all(value.split("/")))


def selected_device(hass, ref):
    """Read ONLY the selected entity's native discovery, without debug histories."""
    reference = EntityReference.from_dict(ref)
    registry = er.async_get(hass)
    domain = reference.entity_id.split(".")[0]
    entity_id = registry.async_get_entity_id(domain, reference.platform, reference.unique_id)
    entity = registry.async_get(entity_id) if entity_id else None
    if entity is None or entity.disabled_by is not None or entity.platform != "mqtt" or not entity.device_id:
        raise MetadataUnavailable("device_metadata_unavailable")
    device = dr.async_get(hass).async_get(entity.device_id)
    mqtt_data = hass.data.get(DATA_MQTT)
    # Pinned HA native debug storage, already used by mqtt/device/debug_info.
    # Copy neither subscriptions nor transmitted/received application messages.
    stored = getattr(mqtt_data, "debug_info_entities", {}).get(entity_id, {})
    discovery = stored.get("discovery_data", {}).get("discovery_payload")
    # HA stores MQTTDiscoveryPayload, its native dict subclass. This is the
    # trusted in-process cache; incoming broker JSON keeps strict validation.
    if not isinstance(discovery, dict) or device is None:
        raise MetadataUnavailable("device_metadata_unavailable")
    identities = {match.group(1).lower() for source, value in device.identifiers if source == "mqtt"
                  and (match := _IEEE.fullmatch(value))}
    if len(identities) != 1:
        raise MetadataUnavailable("device_metadata_identity_unknown")
    published_device = discovery.get("device", discovery.get("dev", {}))
    origin = discovery.get("origin", discovery.get("o", {}))
    if type(published_device) is not dict or type(origin) is not dict or origin.get("name") != "Zigbee2MQTT":
        raise MetadataUnavailable("device_metadata_provider_unknown")
    published_ids = published_device.get("identifiers", published_device.get("ids", []))
    if type(published_ids) is str:
        published_ids = [published_ids]
    if type(published_ids) is not list or not identities <= {
            m.group(1).lower() for value in published_ids if type(value) is str and (m := _IEEE.fullmatch(value))}:
        raise MetadataUnavailable("device_metadata_identity_unknown")
    base = discovery.get("~")
    def expanded(value):
        if type(value) is str and value.startswith("~/") and _topic(base):
            return base + value[1:]
        return value
    state_topic = expanded(discovery.get("state_topic", discovery.get("stat_t")))
    if not _topic(state_topic):
        raise MetadataUnavailable("device_metadata_prefix_unknown")
    availability = discovery.get("availability", discovery.get("avty", []))
    if type(availability) is dict:
        availability = [availability]
    prefixes = set()
    if type(availability) is list:
        for row in availability:
            topic = expanded(row.get("topic", row.get("t"))) if type(row) is dict else None
            if _topic(topic) and topic.endswith("/bridge/state"):
                prefix = topic[:-len("/bridge/state")]
                if _topic(prefix) and state_topic.startswith(prefix + "/"):
                    prefixes.add(prefix)
    # Z2M may disable the global bridge availability entity. Derive only from
    # the ACTUAL published friendly name suffix, never guess a default prefix.
    name = published_device.get("name")
    if not prefixes and _text(name) and state_topic.endswith("/" + name):
        prefix = state_topic[:-len(name)-1]
        if _topic(prefix):
            prefixes.add(prefix)
    if len(prefixes) != 1:
        raise MetadataUnavailable("device_metadata_prefix_unknown")
    template = discovery.get("value_template", discovery.get("val_tpl", ""))
    sensor_property = "device_temperature" if (domain == "sensor" and type(template) is str
                                                and re.fullmatch(r'''\s*\{\{\s*value_json\["device_temperature"\]\s*\}\}\s*''', template)) else None
    return SelectedDevice(entity_id, entity.platform, entity.unique_id, entity.device_id,
                          identities.pop(), prefixes.pop(), sensor_property)


def project_definition(value):
    """Whitelist declarations; don't return other-device config or raw exposes."""
    if type(value) is not dict or type(value.get("definition")) is not dict:
        raise MetadataUnavailable("device_metadata_definition_unknown")
    definition = value["definition"]
    exposes = definition.get("exposes")
    if type(exposes) is not list:
        raise MetadataUnavailable("device_metadata_definition_unknown")
    options = definition.get("options", [])
    if type(options) is not list:
        raise MetadataUnavailable("device_metadata_definition_invalid")
    stack = [(row, 0, "exposes") for row in exposes] + [(row, 0, "options") for row in options]
    observed = {"exposes": [], "options": []}; count = 0
    while stack:
        row, depth, source = stack.pop(); count += 1
        if count > 512 or depth > 8 or type(row) is not dict:
            raise MetadataUnavailable("device_metadata_definition_invalid")
        features = row.get("features", [])
        if type(features) is not list:
            raise MetadataUnavailable("device_metadata_definition_invalid")
        stack.extend((item, depth + 1, source) for item in features)
        prop = row.get("property")
        role = _ROLES.get(prop) if type(prop) is str else None
        if role is None and type(prop) is str and re.fullmatch(r"(?:weekly_)?schedule(?:_[a-z]+)?", prop):
            role = "local_schedule"
        if role is None:
            continue
        access = row.get("access")
        if type(access) is not int or not 0 <= access <= 7:
            raise MetadataUnavailable("device_metadata_definition_invalid")
        result = {"role": role, "property": prop, "access": access,
                  "published": bool(access & 1), "settable_declared": bool(access & 2),
                  "gettable_declared": bool(access & 4)}
        for key in ("value_min", "value_max", "value_step"):
            number = row.get(key)
            if type(number) in (int, float) and math.isfinite(number) and abs(number) <= 1e6:
                result[key] = number
        for key in ("type", "unit"):
            if (text := _text(row.get(key), 32)) is not None:
                result[key] = text
        values = row.get("values")
        if type(values) is list and len(values) <= 32 and all(_text(x, 64) is not None for x in values):
            result["values"] = values[:]
        observed[source].append(result)
    return {"model": _text(definition.get("model")), "vendor": _text(definition.get("vendor")),
            "declared_features": sorted(observed["exposes"], key=lambda x: (x["role"], x["property"])),
            "declared_options": sorted(observed["options"], key=lambda x: (x["role"], x["property"])),
            "converter_source": definition.get("source") if definition.get("source") in ("native", "external", "generated") else None,
            "definition_observed": True, "physical_control_qualified": False}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(_):
    raise ValueError


async def async_read_selected_metadata(hass, entry, references):
    """One bounded subscription pair on the existing native HA client, no Store."""
    if not 1 <= len(references) <= 9:
        raise MetadataUnavailable("device_metadata_unavailable")
    before = native_entry_state(entry)
    selected = tuple(selected_device(hass, ref) for ref in references)
    prefixes = {item.prefix for item in selected}
    if len(prefixes) != 1:
        raise MetadataUnavailable("device_metadata_prefix_unknown")
    prefix = prefixes.pop()
    topics = {prefix + "/bridge/info", prefix + "/bridge/devices"}
    pending = set(topics); observed = {}; changed = asyncio.Event(); cleanup = ExitStack()
    errors = []
    def receive(message):
        if message.topic not in pending:
            return
        try:
            raw = message.payload
            if type(raw) not in (bytes, str) or len(raw) > MAX_BYTES or (type(raw) is str and len(raw.encode()) > MAX_BYTES):
                raise ValueError
            payload = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
            if message.topic.endswith("/bridge/info"):
                if type(payload) is not dict:
                    raise ValueError
                observed["bridge"] = {key: _text(payload.get(key)) for key in ("version", "commit")}
            else:
                if type(payload) is not list or len(payload) > 1024:
                    raise ValueError
                selected_ieees = {item.ieee for item in selected}; rows = {}
                for row in payload:
                    ieee = row.get("ieee_address") if type(row) is dict else None
                    if type(ieee) is str and ieee.lower() in selected_ieees:
                        if ieee.lower() in rows:
                            raise ValueError
                        rows[ieee.lower()] = project_definition(row)
                observed["devices"] = rows
            pending.remove(message.topic)
        except (ValueError, UnicodeError, RecursionError):
            errors.append("device_metadata_response_invalid")
        changed.set()
    def guard():
        if (hass.config_entries.async_get_entry(entry.entry_id) is not entry
                or native_entry_state(entry) != before
                or tuple(selected_device(hass, ref) for ref in references) != selected):
            raise MetadataUnavailable("setup_changed")
    try:
        async with asyncio.timeout(TIMEOUT):
            for topic in sorted(topics):
                guard()
                cleanup.callback(await mqtt.async_subscribe(hass, topic, receive, qos=0, encoding=None))
                guard()
            while pending and not errors:
                changed.clear(); guard()
                if pending and not errors:
                    await changed.wait()
            guard()
            if errors:
                raise MetadataUnavailable(errors[0])
    except TimeoutError:
        raise MetadataUnavailable("device_metadata_timeout") from None
    finally:
        cleanup.close()
    devices = observed["devices"]
    return {"bridge": observed["bridge"], "devices": [
        {"entity_id": item.entity_id, "sensor_property": item.sensor_property,
         **devices.get(item.ieee, {"definition_observed": False, "physical_control_qualified": False})}
        for item in selected], "physical_control_qualified": False,
        "measurement_acquisition_verified": False, "metadata_only": True}
