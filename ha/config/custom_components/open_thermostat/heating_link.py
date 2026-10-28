"""The one route between the E32 room control and Home Assistant.

The E32 owns the room plan. It publishes ``fw/telemetry/heating`` with its
computed boiler request and the HA entities it reads (``ha_entities``). HA
forwards exactly those entities' temperature and target to ``ha/heating_input``
on every change and every five minutes, so a steady tado stays fresh.
"""
import json
import math
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import CONF_TOPIC_PREFIX, DOMAIN

REFRESH_SECONDS = 300
MAX_ENTITIES = 16


def decode_status(payload):
    """The E32 heating status, or None when it is not a schema 1 document."""
    if not isinstance(payload, (str, bytes)) or len(payload) > 8192:
        return None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    if type(value) is not dict or value.get("schema") != 1 or value.get("mode") not in ("shadow", "active"):
        return None
    request, entities, rooms = value.get("request"), value.get("ha_entities"), value.get("rooms")
    if (type(request) is not dict or type(request.get("heat")) is not bool or type(request.get("flow_c")) is not int
            or not 0 <= request["flow_c"] <= 60 or type(request.get("reason")) is not str
            or type(entities) is not list or len(entities) > MAX_ENTITIES
            or any(type(e) is not str or "." not in e or len(e) > 80 for e in entities)
            or type(rooms) is not list):
        return None
    return value


def number(value, low, high):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and low <= result <= high else None


def input_payload(state):
    """{"entity","temperature","target"} for a climate or temperature sensor state."""
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    if state.domain == "climate":
        temperature = number(state.attributes.get("current_temperature"), -40, 85)
        target = number(state.attributes.get("temperature"), 5, 30)
    else:
        temperature, target = number(state.state, -40, 85), None
    if temperature is None and target is None:
        return None
    return json.dumps({"entity": state.entity_id, "temperature": temperature, "target": target})


class HeatRequestSensor(SensorEntity):
    """The E32's computed boiler flow request (0 when it does not ask for heat)."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Heat request"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, prefix):
        self._attr_unique_id = f"{prefix}_hub_heat_request"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})
        self._attr_available = False

    @callback
    def update_status(self, status):
        self._attr_available = status is not None
        if status is not None:
            request = status["request"]
            self._attr_native_value = request["flow_c"] if request["heat"] else 0
            self._attr_extra_state_attributes = {"mode": status["mode"], "reason": request["reason"], "rooms": status["rooms"]}
        if self.hass is not None:
            self.async_write_ha_state()


async def async_setup_heating_link(hass, entry, async_add_entities, **add_options):
    state = hass.data[DOMAIN][entry.entry_id]
    connection = state.get("v1_connection")
    if connection is None or connection.client is None:
        return
    topic_base = connection.prefix
    sensor = HeatRequestSensor(entry.data[CONF_TOPIC_PREFIX])
    from .product import is_product
    if is_product(entry) and "config_subentry_id" not in add_options:
        from .installation_group import ensure_installation_group
        add_options = {**add_options, "config_subentry_id": ensure_installation_group(hass, entry)}
    async_add_entities([sensor], **add_options)
    forwarded = []
    unsubscribe_states = None

    def publish(entity_id):
        payload = input_payload(hass.states.get(entity_id))
        if payload is not None:
            hass.async_create_task(mqtt.async_publish(hass, topic_base + "ha/heating_input", payload, 0, False))

    @callback
    def state_changed(event):
        publish(event.data["entity_id"])

    @callback
    def refresh(_now=None):
        for entity_id in forwarded:
            publish(entity_id)

    @callback
    def receive(message):
        nonlocal forwarded, unsubscribe_states
        if getattr(message, "retain", False):
            return
        status = decode_status(message.payload)
        sensor.update_status(status)
        if status is None or status["ha_entities"] == forwarded:
            return
        forwarded = list(status["ha_entities"])
        if unsubscribe_states is not None:
            unsubscribe_states()
            unsubscribe_states = None
        if forwarded:
            unsubscribe_states = async_track_state_change_event(hass, forwarded, state_changed)
        refresh()

    @callback
    def unload():
        if unsubscribe_states is not None:
            unsubscribe_states()

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(await mqtt.async_subscribe(hass, topic_base + "fw/telemetry/heating", receive))
    entry.async_on_unload(async_track_time_interval(hass, refresh, timedelta(seconds=REFRESH_SECONDS)))
    entry.async_on_unload(unload)
