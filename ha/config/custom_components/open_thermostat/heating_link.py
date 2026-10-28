"""The one route between the E32 room control and Home Assistant.

The E32 owns the room plan. It publishes ``fw/telemetry/heating`` with its
computed boiler request, its rooms, its paired Bluetooth sensors and the HA
entities it reads (``ha_entities``). HA forwards exactly those entities'
temperature and target to ``ha/heating_input`` on every change and every five
minutes, so a steady tado stays fresh.

One ``HeatingHub`` per entry holds the latest status. Every platform (sensor,
binary_sensor, select, number, datetime) creates its entities from it for the
room and Bluetooth ids it actually reports; all of them are unavailable while
the telemetry is missing or stale.
"""
import json
import math
import re
import time
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import CONF_TOPIC_PREFIX, DOMAIN

REFRESH_SECONDS = 300
MAX_ENTITIES = 40  # the E32 plan: 8 rooms x (4 sources + setpoint entity)
# The E32 publishes every 15 s; four missed messages make every value stale.
STALE_SECONDS = 60
STALE_CHECK = timedelta(seconds=15)
ROOM_ID = re.compile(r"[a-z0-9_]{1,32}")
BLE_ID = re.compile(r"[0-9a-f]{12}")
ROOM_STATUSES = ["ok", "fallback", "stale", "lost", "inactive"]


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
    if type(value) is bool:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and low <= result <= high else None


def status_rooms(status):
    """{room id: room} for the well-formed rooms of a status; others are skipped."""
    rooms = {}
    items = status.get("rooms") if status else None
    for room in items if type(items) is list else []:
        if type(room) is dict and type(room.get("id")) is str and ROOM_ID.fullmatch(room["id"]):
            rooms.setdefault(room["id"], room)
    return rooms


def status_ble(status):
    """{sensor id: sensor} for the well-formed Bluetooth sensors of a status."""
    sensors = {}
    items = status.get("ble_sensors") if status else None
    for sensor in items if type(items) is list else []:
        if type(sensor) is dict and type(sensor.get("id")) is str and BLE_ID.fullmatch(sensor["id"]):
            sensors.setdefault(sensor["id"], sensor)
    return sensors


def label(item):
    name = item.get("name")
    return name.strip()[:64] if type(name) is str and name.strip() else item["id"]


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


class HeatingHub:
    """The latest E32 heating status of one entry and who listens to it."""

    def __init__(self, prefix, clock=time.monotonic):
        self.prefix = prefix
        self.clock = clock
        self.status = None
        self.rooms = {}
        self.ble = {}
        self.received = None
        self.plan = None  # room_plan.RoomPlanLink when the E32 credentials are stored
        self._listeners = []

    @property
    def fresh(self):
        return self.status is not None

    @property
    def revision(self):
        revision = self.status.get("revision") if self.status else None
        return revision if type(revision) is int else None

    @callback
    def add_listener(self, listener):
        self._listeners.append(listener)

        @callback
        def remove():
            if listener in self._listeners:
                self._listeners.remove(listener)
        return remove

    @callback
    def notify(self):
        for listener in list(self._listeners):
            listener()

    @callback
    def update(self, status):
        self.status = status
        self.rooms = status_rooms(status)
        self.ble = status_ble(status)
        self.received = self.clock() if status is not None else None
        self.notify()

    @callback
    def check_stale(self, _now=None):
        if self.status is not None and self.clock() - self.received > STALE_SECONDS:
            self.update(None)

    @callback
    def stop(self):
        if self.plan is not None:
            self.plan.stop()
        self._listeners.clear()


def heating_hub(hass, entry):
    """The entry's one hub, created by whichever platform asks first."""
    state = hass.data[DOMAIN][entry.entry_id]
    hub = state.get("heating_hub")
    if hub is None:
        hub = state["heating_hub"] = HeatingHub(entry.data[CONF_TOPIC_PREFIX])
        from .room_plan import RoomPlanLink
        hub.plan = RoomPlanLink.for_entry(hass, entry, hub)
        entry.async_on_unload(hub.stop)
    return hub


def add_options(hass, entry, options=None):
    """Product entities belong to the installation group, like the hub device."""
    options = dict(options or {})
    from .product import is_product
    if is_product(entry) and "config_subentry_id" not in options:
        from .installation_group import ensure_installation_group
        options["config_subentry_id"] = ensure_installation_group(hass, entry)
    return options


@callback
def track_entities(hub, async_add_entities, options, wanted):
    """Add each entity wanted(hub) yields ((key, factory) pairs) once, when first seen."""
    known = set()

    @callback
    def refresh():
        new = []
        for key, factory in wanted(hub):
            if key not in known:
                known.add(key)
                new.append(factory())
        if new:
            async_add_entities(new, **options)
    remove = hub.add_listener(refresh)
    refresh()
    return remove


class HubEntity:
    """Mixin: properties read the hub; every hub change writes the state."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def _attach(self, hub, suffix):
        self.hub = hub
        self._attr_unique_id = f"{hub.prefix}_{suffix}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, hub.prefix)})

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.hub.add_listener(self._hub_changed))

    @callback
    def _hub_changed(self):
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()


class RoomEntity(HubEntity):
    """One E32 room; its name is part of the entity name."""

    def _attach_room(self, hub, room, key):
        self.room_id = room["id"]
        self._attach(hub, f"e32_room_{self.room_id}_{key}")
        self._attr_translation_key = f"room_{key}"
        self._attr_translation_placeholders = {"room": label(room)}

    @property
    def room(self):
        return self.hub.rooms.get(self.room_id)

    @property
    def available(self):
        return self.hub.fresh and self.room is not None


class HeatRequestSensor(HubEntity, SensorEntity):
    """The E32's computed boiler flow request (0 when it does not ask for heat)."""

    _attr_name = "Heat request"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, hub):
        self._attach(hub, "hub_heat_request")

    @property
    def available(self):
        return self.hub.fresh

    @property
    def native_value(self):
        if not self.hub.fresh:
            return None
        request = self.hub.status["request"]
        return request["flow_c"] if request["heat"] else 0

    @property
    def extra_state_attributes(self):
        if not self.hub.fresh:
            return None
        status = self.hub.status
        return {"mode": status["mode"], "reason": status["request"]["reason"], "rooms": status["rooms"],
                "revision": self.hub.revision}


class RoomTemperatureSensor(RoomEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, hub, room, key="temperature", low=-40, high=85):
        self._key, self._low, self._high = key, low, high
        self._attach_room(hub, room, key)

    @property
    def native_value(self):
        room = self.room
        return number(room.get(self._key), self._low, self._high) if room and self.hub.fresh else None

    @property
    def extra_state_attributes(self):
        room = self.room
        return {"room_id": self.room_id, "source": room.get("source")} if room and self.hub.fresh else None


class RoomStatusSensor(RoomEntity, SensorEntity):
    """How the E32 runs the room: ok, fallback, stale, lost or inactive, and from which source."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ROOM_STATUSES

    def __init__(self, hub, room):
        self._attach_room(hub, room, "status")

    @property
    def native_value(self):
        room = self.room
        value = room.get("status") if room and self.hub.fresh else None
        return value if value in ROOM_STATUSES else None

    @property
    def extra_state_attributes(self):
        room = self.room
        if not room or not self.hub.fresh:
            return None
        return {"room_id": self.room_id, "source": room.get("source"), "state": room.get("state"),
                "inactive_until": room.get("inactive_until"), "demand": room.get("demand"),
                "temperature": room.get("temperature"), "setpoint": room.get("setpoint"),
                "revision": self.hub.revision}


class RoomDemandBinarySensor(RoomEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, hub, room):
        self._attach_room(hub, room, "demand")

    @property
    def is_on(self):
        room = self.room
        value = room.get("demand") if room and self.hub.fresh else None
        return value if type(value) is bool else None


# metric: (device class, unit, lowest and highest plausible value)
BLE_METRICS = {
    "temperature": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, -40, 85),
    "humidity": (SensorDeviceClass.HUMIDITY, PERCENTAGE, 0, 100),
    "battery": (SensorDeviceClass.BATTERY, PERCENTAGE, 0, 100),
}


class BleSensor(HubEntity, SensorEntity):
    """One reading of a Bluetooth sensor paired on the E32."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub, sensor, metric):
        self.sensor_id, self.metric = sensor["id"], metric
        self._attach(hub, f"e32_ble_{self.sensor_id}_{metric}")
        self._attr_device_class, self._attr_native_unit_of_measurement, self._low, self._high = BLE_METRICS[metric]
        self._attr_translation_key = f"ble_{metric}"
        self._attr_translation_placeholders = {"sensor": label(sensor)}

    @property
    def sensor(self):
        return self.hub.ble.get(self.sensor_id)

    @property
    def available(self):
        return self.hub.fresh and self.sensor is not None

    @property
    def native_value(self):
        sensor = self.sensor
        return number(sensor.get(self.metric), self._low, self._high) if sensor and self.hub.fresh else None

    @property
    def extra_state_attributes(self):
        sensor = self.sensor
        if not sensor or not self.hub.fresh:
            return None
        age = sensor.get("age_s")
        return {"sensor_id": self.sensor_id, "profile": sensor.get("profile"),
                "age_s": age if type(age) is int else None}


def wanted_sensors(hub):
    for room_id, room in hub.rooms.items():
        yield ("room", room_id, "temperature"), lambda room=room: RoomTemperatureSensor(hub, room)
        yield ("room", room_id, "setpoint"), lambda room=room: RoomTemperatureSensor(hub, room, "setpoint", 5, 30)
        yield ("room", room_id, "status"), lambda room=room: RoomStatusSensor(hub, room)
    for sensor_id, sensor in hub.ble.items():
        for metric in BLE_METRICS:
            # Only readings the sensor actually reports (not every profile has humidity).
            if sensor.get(metric) is not None:
                yield ("ble", sensor_id, metric), lambda sensor=sensor, metric=metric: BleSensor(hub, sensor, metric)


def wanted_demand(hub):
    for room_id, room in hub.rooms.items():
        yield room_id, lambda room=room: RoomDemandBinarySensor(hub, room)


async def async_setup_demand(hass, entry, async_add_entities):
    """Binary sensor platform (product entries): one heat demand per E32 room."""
    hub = heating_hub(hass, entry)
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), wanted_demand))


async def async_setup_heating_link(hass, entry, async_add_entities, **options):
    state = hass.data[DOMAIN][entry.entry_id]
    connection = state.get("v1_connection")
    if connection is None or connection.client is None:
        return
    topic_base = connection.prefix
    hub = heating_hub(hass, entry)
    options = add_options(hass, entry, options)
    sensor = HeatRequestSensor(hub)
    async_add_entities([sensor], **options)
    entry.async_on_unload(track_entities(hub, async_add_entities, options, wanted_sensors))
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
        hub.update(status)
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
    entry.async_on_unload(async_track_time_interval(hass, hub.check_stale, STALE_CHECK))
    entry.async_on_unload(unload)
