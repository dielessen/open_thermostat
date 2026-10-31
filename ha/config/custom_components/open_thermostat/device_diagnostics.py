"""Read-only ESP resources over the existing HA MQTT client; no control admission.

The values come from ``fw/heartbeat`` (E32 beta.21 and later, every 60 s) and from
``fw/telemetry/device_status`` (every 15 s; beta.19, and beta.21 while no compact
session is open). Whichever arrived last is shown.
"""
import json
import math
import time

from homeassistant.components import mqtt
from homeassistant.core import callback

from .const import CONF_TOPIC_PREFIX, DOMAIN

FIELDS = {"mem_free", "mem_min_free", "mem_max_alloc", "temperature", "cpu_temperature", "uptime"}
# device_status every 15 s: three missed. fw/heartbeat every 60 s: three missed, as heating_link.
DEVICE_STATUS_STALE_SECONDS = 45
HEARTBEAT_STALE_SECONDS = 3 * 60 + 15
MAX_HEARTBEAT_BYTES = 1536


def valid(value):
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


def decode(payload):
    if not isinstance(payload, (str, bytes)) or len(payload) > 512:
        return None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    return valid(value)


def decode_heartbeat(payload):
    """The device diagnostics in a beta.21 fw/heartbeat; None for an older heartbeat."""
    if not isinstance(payload, (str, bytes)) or len(payload) > MAX_HEARTBEAT_BYTES:
        return None
    try:
        beat = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    if type(beat) is not dict or beat.get("schema") != 1 or "heap_max_alloc" not in beat:
        return None
    cpu = beat.get("cpu_deci_c")
    if cpu is not None and (type(cpu) is not int or not -400 <= cpu <= 1500):
        return None
    return valid({"mem_free": beat.get("heap_free"), "mem_min_free": beat.get("heap_min_free"),
                  "mem_max_alloc": beat["heap_max_alloc"], "temperature": None,
                  "cpu_temperature": None if cpu is None else cpu / 10, "uptime": beat.get("uptime_s")})


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
    received = None      # (monotonic receipt of the last packet, current until)
    available = False

    @callback
    def refresh():
        nonlocal available, received
        now = time.monotonic()
        if received is not None and now < received[0]:
            received = None
        current = online and received is not None and now < received[1]
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

    def receiver(decoder, stale_seconds):
        @callback
        def receive(message):
            nonlocal received, available, online
            if getattr(message, "retain", False):
                return  # Retained diagnostics never establish current freshness.
            payload = decoder(message.payload)
            if payload is None:
                return
            now = time.monotonic()
            # A device_status after a heartbeat never shortens the heartbeat's window.
            until = now + stale_seconds
            received = (now, until if received is None or now < received[0] else max(until, received[1]))
            # Non-retained native availability is emitted on firmware connect only.
            # A new live packet also proves liveness after an HA-only restart.
            online = True
            available = True
            for entity in entities:
                entity.update_payload(payload, online)
        return receive

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, topic_base + "fw/availability", availability))
    entry.async_on_unload(await mqtt.async_subscribe(hass, topic_base + "fw/telemetry/device_status",
                                                     receiver(decode, DEVICE_STATUS_STALE_SECONDS)))
    entry.async_on_unload(await mqtt.async_subscribe(hass, topic_base + "fw/heartbeat",
                                                     receiver(decode_heartbeat, HEARTBEAT_STALE_SECONDS)))
    # Existing native runtime tick supplies expiry, without another polling task.
    entry.async_on_unload(runtime.add_listener(refresh))
