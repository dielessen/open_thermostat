"""Retire the MQTT discovery entities that pre-v1 E32 firmware left on the broker (beta.23).

Before the v1 link the firmware announced its own Home Assistant entities with
MQTT discovery (homeassistant/<component>/<prefix>/<object>/config, retained):
"opth_*" boiler, metric and device values, per-room values and a status
sensor, on a device "OpenThermostat". A v1 E32 never sends them again (the
legacy MQTT reporter is not started in modern mode), but the retained configs
stay on the broker, so the MQTT integration keeps re-creating some 45
"unavailable" entities next to this integration's own (the owner's HA, 1 Nov
2026: sensor.ib_therm_opth_warm_water_usage and friends).

They belong to the MQTT integration, so this integration never touches their
registry entries. It retires them the way MQTT discovery itself defines: an
empty retained payload on the config topic, after which the MQTT integration
removes the entity (its history stays in the recorder). Only configs this E32's
old firmware wrote (node ID = the prefix, device identifiers exactly [prefix],
unique ID the prefix or prefix_..., state topic under the old prefix/ and not
prefix/v1/), only on a product (v1) entry, once, RETIRE_AFTER_S after setup, and
never for an entity the user changed (name, icon, area, labels, own entity ID,
or disabled or hidden by the user): that one stays as it is.
"""
import json
import logging

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later

from .const import CONF_TOPIC_PREFIX, DOMAIN

_LOGGER = logging.getLogger(__name__)
RETIRE_AFTER_S = 600
COMPONENTS = ("sensor", "binary_sensor", "button", "climate", "number", "select", "switch")


def discovery_prefix(hass):
    for entry in hass.config_entries.async_entries("mqtt"):
        prefix = (entry.options or {}).get("discovery_prefix") or (entry.data or {}).get("discovery_prefix")
        if isinstance(prefix, str) and prefix:
            return prefix
    return "homeassistant"


def legacy_config(topic, payload, base, prefix):
    """(component, unique_id, default_entity_id) of an old-firmware config of this E32, else None."""
    parts = topic.split("/")
    if len(parts) != 5 or parts[0] != base or parts[2] != prefix or parts[4] != "config" or parts[1] not in COMPONENTS:
        return None
    try:
        config = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if type(config) is not dict:
        return None
    device = config.get("dev") or config.get("device") or {}
    ids = device.get("ids") or device.get("identifiers") if type(device) is dict else None
    unique_id = config.get("uniq_id") or config.get("unique_id")
    state = config.get("stat_t") or config.get("state_topic")
    if ids != [prefix] or type(unique_id) is not str or not (unique_id == prefix or unique_id.startswith(f"{prefix}_")):
        return None
    if type(state) is not str or not state.startswith(f"{prefix}/") or state.startswith(f"{prefix}/v1/"):
        return None
    default = config.get("default_entity_id")
    return parts[1], unique_id, default if type(default) is str else None


def user_changed(record, default_entity_id):
    """The user made this MQTT entity their own: it is left alone."""
    return (record.name is not None or record.icon is not None or record.area_id is not None or bool(record.labels)
            or record.disabled_by is er.RegistryEntryDisabler.USER or record.hidden_by is er.RegistryEntryHider.USER
            or (default_entity_id is not None and record.entity_id != default_entity_id))


async def async_setup_legacy_discovery_retirement(hass, entry, delay=RETIRE_AFTER_S):
    """Collect this E32's old retained discovery configs; clear the untouched ones once, after a delay."""
    from .product import is_product
    if not is_product(entry):
        return
    prefix = entry.data[CONF_TOPIC_PREFIX]
    base = discovery_prefix(hass)
    found = {}

    @callback
    def received(message):
        if not getattr(message, "retain", False) or not message.payload:
            return
        legacy = legacy_config(message.topic, message.payload, base, prefix)
        if legacy is not None:
            found[message.topic] = legacy

    async def retire(_now=None):
        registry = er.async_get(hass)
        cleared, kept = [], []
        for topic, (component, unique_id, default_entity_id) in sorted(found.items()):
            entity_id = registry.async_get_entity_id(component, "mqtt", unique_id)
            record = registry.async_get(entity_id) if entity_id else None
            if record is not None and user_changed(record, default_entity_id):
                kept.append(entity_id)
                continue
            await mqtt.async_publish(hass, topic, "", 0, True)
            cleared.append(entity_id or unique_id)
        if cleared:
            _LOGGER.info("Retired %d MQTT discovery entities the E32 firmware announced before the v1 link "
                         "(their history stays): %s", len(cleared), ", ".join(cleared))
        if kept:
            _LOGGER.info("Kept %d old MQTT discovery entities you changed yourself: %s", len(kept), ", ".join(kept))
        hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})["legacy_discovery_retired"] = {
            "cleared": len(cleared), "kept": len(kept)}

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, f"{base}/+/{prefix}/+/config", received))
    entry.async_on_unload(async_call_later(hass, delay, retire))
    return retire
