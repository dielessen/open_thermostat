"""Read-only existing hub telemetry; never imports E32 rooms or publishes commands."""
import json
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from .const import CONF_TOPIC_PREFIX, DOMAIN
from .installation_group import ensure_installation_group


async def async_setup_sensors(hass, entry, async_add_entities, *, native_metrics=False):
    from .sensor import HUB_METRICS, VERSIONED_METRICS, HubMetric, DhwStatus
    group_id = ensure_installation_group(hass, entry)
    prefix = entry.data[CONF_TOPIC_PREFIX]
    if native_metrics:
        from .device_diagnostics import async_setup_device_diagnostics
        await async_setup_device_diagnostics(hass, entry, async_add_entities, config_subentry_id=group_id)
    tracker = hass.data[DOMAIN][entry.entry_id]["heating_tracker"]
    online = False
    entities = {}
    dhw = DhwStatus(prefix, tracker)
    async_add_entities([dhw], config_subentry_id=group_id)

    @callback
    def refresh():
        dhw.update_from_tracker()
        for entity in entities.values():
            if entity._observation_field:
                entity.update_from_tracker()

    entry.async_on_unload(tracker.async_add_listener(refresh))

    @callback
    def availability(message):
        nonlocal online
        online = message.payload == "on"
        for entity in entities.values():
            entity.set_online(online)

    def handler(topic):
        @callback
        def receive(message):
            if len(message.payload) > 8192:
                return
            try:
                payload = json.loads(message.payload)
            except (TypeError, ValueError):
                return
            if not isinstance(payload, dict):
                return
            added = []
            for metric in HUB_METRICS[topic]:
                key = topic, metric
                if key not in entities:
                    entities[key] = HubMetric(prefix, topic, metric, entry.entry_id, tracker=tracker)
                    added.append(entities[key])
                entities[key].update_payload(payload, online)
                # Preserve old statistic identities as quarantined history.
                old_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{prefix}_hub_{metric}")
                old = er.async_get(hass).async_get(old_id) if old_id else None
                if topic == "ems_metrics" and metric in VERSIONED_METRICS and old and old.config_entry_id == entry.entry_id:
                    legacy_key = topic, metric + "_legacy"
                    if legacy_key not in entities:
                        entities[legacy_key] = HubMetric(prefix, topic, metric, entry.entry_id, definition_version=1)
                        added.append(entities[legacy_key])
                    entities[legacy_key].update_payload(payload, online)
            if added:
                async_add_entities(added, config_subentry_id=group_id)
        return receive

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, f"{prefix}/status", availability))
    for topic in HUB_METRICS:
        if native_metrics and topic in {"ems_metrics", "device_status"}:
            continue  # Single owner: validated native cache preserves v2 identities.
        entry.async_on_unload(await mqtt.async_subscribe(hass, f"{prefix}/{topic}", handler(topic)))


async def async_setup_binary_sensors(hass, entry, async_add_entities):
    from .binary_sensor import BOILER_STATES, BoilerState, HubConnection
    group_id = ensure_installation_group(hass, entry)
    prefix = entry.data[CONF_TOPIC_PREFIX]
    tracker = hass.data[DOMAIN][entry.entry_id]["heating_tracker"]
    connection = HubConnection(prefix)
    states = {key: BoilerState(prefix, key, tracker=tracker) for key in BOILER_STATES}
    async_add_entities([connection, *states.values()], config_subentry_id=group_id)
    online = False

    @callback
    def refresh():
        for entity in states.values():
            if entity._observation_field:
                entity.update_from_tracker()

    entry.async_on_unload(tracker.async_add_listener(refresh))

    @callback
    def availability(message):
        nonlocal online
        online = message.payload == "on"
        connection.update_value(online)
        for entity in states.values():
            entity.set_online(online)

    @callback
    def status(message):
        if len(message.payload) > 8192:
            return
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError):
            return
        if not isinstance(payload, dict):
            return
        for key, entity in states.items():
            entity.update_value(payload.get(BOILER_STATES[key][0]), online)

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, f"{prefix}/status", availability))
    entry.async_on_unload(await mqtt.async_subscribe(hass, f"{prefix}/ems_status", status))
