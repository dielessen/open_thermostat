"""Read-only ESP resources over the existing HA MQTT client; no control admission."""
import json
import math
import time

from homeassistant.components import mqtt
from homeassistant.core import callback

from .const import CONF_TOPIC_PREFIX, DOMAIN

FIELDS = {"mem_free", "mem_min_free", "mem_max_alloc", "temperature", "cpu_temperature", "uptime"}


def decode(payload):
    if not isinstance(payload, (str, bytes)) or len(payload) > 512:
        return None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    if type(value) is not dict or set(value) != FIELDS:
        return None
    for key, item in value.items():
        if item is None and key in {"temperature", "cpu_temperature"}:
            continue
        if type(item) not in (int, float):
            return None
        try:
            if not math.isfinite(item):
                return None
        except OverflowError:
            return None
        if key in {"temperature", "cpu_temperature"}:
            if not -40 <= item <= 150:
                return None
        elif type(item) is not int or not 0 <= item <= (2**53 - 1 if key == "uptime" else 2**32 - 1):
            return None
    return value


async def async_setup_device_diagnostics(hass, entry, async_add_entities, **add_options):
    from .sensor import HUB_METRICS, HubMetric
    state = hass.data[DOMAIN][entry.entry_id]
    runtime = state["v1_runtime"]
    if not runtime.enabled:
        return
    connection = state.get("v1_connection")
    if connection is None or connection.client is None:
        return
    prefix = entry.data[CONF_TOPIC_PREFIX]
    topic_base = connection.prefix
    # E32 has no RTC temperature sensor; firmware always sends null for it.
    entities = [HubMetric(prefix, "device_status", metric, entry.entry_id)
                for metric in HUB_METRICS["device_status"] if metric != "rtc_temperature"]
    async_add_entities(entities, **add_options)
    online = False
    received = None
    available = False

    @callback
    def refresh():
        nonlocal available, received
        now = time.monotonic()
        if received is not None and now < received:
            received = None
        current = online and received is not None and 0 <= now - received < 45
        if current != available:
            available = current
            for entity in entities:
                entity.set_online(current)

    @callback
    def availability(message):
        nonlocal online, received
        online = message.payload == "online"
        if not online:
            received = None
        refresh()

    @callback
    def receive(message):
        nonlocal received, available, online
        if getattr(message, "retain", False):
            return  # Retained diagnostics never establish current freshness.
        payload = decode(message.payload)
        if payload is None:
            return
        received = time.monotonic()
        # Non-retained native availability is emitted on firmware connect only.
        # A new live packet also proves liveness after an HA-only restart.
        online = True
        available = True
        for entity in entities:
            entity.update_payload(payload, online)

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, topic_base + "fw/availability", availability))
    entry.async_on_unload(await mqtt.async_subscribe(hass, topic_base + "fw/telemetry/device_status", receive))
    # Existing native runtime tick supplies expiry, without another polling task.
    entry.async_on_unload(runtime.add_listener(refresh))
