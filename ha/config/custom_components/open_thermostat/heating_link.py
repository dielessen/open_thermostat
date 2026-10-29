"""The one route between the E32 room control and Home Assistant.

The E32 owns the room plan. It publishes ``fw/telemetry/heating`` with its
computed boiler request, its rooms, its paired Bluetooth sensors and the HA
entities it reads (``ha_entities``). HA forwards exactly those entities'
temperature and target to ``ha/heating_input`` on every change and every five
minutes, so a steady tado stays fresh.

Newer firmware adds what it learned per room (``learned``: readiness, flow
advice and, with a trusted clock, ``learned.plans``: optimum start and night
options) and today's hot water (``dhw``); those entities appear only once the
fields do.

One ``HeatingHub`` per entry holds the latest status. Every platform (sensor,
binary_sensor, select, number, datetime) creates its entities from it for the
room and Bluetooth ids it actually reports; all of them are unavailable while
the telemetry is missing or stale.
"""
import json
import math
import re
import time
from datetime import datetime, timedelta, timezone

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
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
LEARNING_STATES = ["collecting", "learning", "ready"]
# The learned advice and hot-water summary make the status larger (the E32
# itself trims its MQTT copy); still a hard bound before parsing.
MAX_STATUS_BYTES = 16384


def decode_status(payload):
    """The E32 heating status, or None when it is not a schema 1 document."""
    if not isinstance(payload, (str, bytes)) or len(payload) > MAX_STATUS_BYTES:
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


def rooms_by_id(items):
    """{room id: room} for the well-formed rooms of a list; others are skipped."""
    rooms = {}
    for room in items if type(items) is list else []:
        if type(room) is dict and type(room.get("id")) is str and ROOM_ID.fullmatch(room["id"]):
            rooms.setdefault(room["id"], room)
    return rooms


def status_rooms(status):
    """{room id: room} for the well-formed rooms of a status; others are skipped."""
    return rooms_by_id(status.get("rooms") if status else None)


def learned_status(status):
    """What the E32 learned (``learned``, schema 1), or None on firmware without it."""
    learned = status.get("learned") if status else None
    return learned if type(learned) is dict and learned.get("schema") == 1 else None


def learned_rooms(status):
    """{room id: learned room}: readiness and flow advice per room."""
    learned = learned_status(status)
    return rooms_by_id(learned.get("rooms")) if learned else {}


def plan_rooms(status):
    """{room id: plan}: optimum start and night strategies (absent without a trusted clock)."""
    learned = learned_status(status)
    plans = learned.get("plans") if learned else None
    return rooms_by_id(plans.get("rooms")) if type(plans) is dict else {}


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
    """{"entity","temperature","target"} for a climate, temperature sensor or setpoint number state.

    An input_number/number is only ever a room's setpoint entity: its value is the target.
    """
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    if state.domain == "climate":
        temperature = number(state.attributes.get("current_temperature"), -40, 85)
        target = number(state.attributes.get("temperature"), 5, 30)
    elif state.domain in ("input_number", "number"):
        temperature, target = None, number(state.state, 5, 30)
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
        self.learned = {}
        self.warmup = {}
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
        self.learned = learned_rooms(status)
        self.warmup = plan_rooms(status)
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


def room_device_identifier(prefix, room_id):
    """The device of one E32 room (its own device, linked via the product device)."""
    return DOMAIN, f"{prefix}_e32_room_{room_id}"


def ble_device_identifier(prefix, sensor_id):
    """The device of one Bluetooth sensor paired on the E32."""
    return DOMAIN, f"{prefix}_e32_ble_{sensor_id}"


class HubEntity:
    """Mixin: properties read the hub; every hub change writes the state."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    _on_own_device = False

    def _attach(self, hub, suffix, device_info=None):
        self.hub = hub
        self._attr_unique_id = f"{hub.prefix}_{suffix}"
        self._on_own_device = device_info is not None
        self._attr_device_info = device_info or DeviceInfo(identifiers={(DOMAIN, hub.prefix)})

    @property
    def device_info(self):
        """An entity on its own device (a room, a Bluetooth sensor) links it via the product device."""
        info = self._attr_device_info
        entry = getattr(getattr(self, "platform", None), "config_entry", None)
        if not self._on_own_device or getattr(self, "hass", None) is None or entry is None:
            return info
        product = dr.async_get(self.hass).async_get_device_by_identifier((DOMAIN, self.hub.prefix), entry.entry_id)
        return {**info, "via_device_id": product.id} if product is not None else info

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(self.hub.add_listener(self._hub_changed))

    @callback
    def _hub_changed(self):
        if self.hass is not None and self.entity_id:
            self._follow_name()
            self.async_write_ha_state()

    @callback
    def _follow_name(self):
        """A room or sensor renamed on the E32 renames its own device (a user's own name stays)."""
        item = self._named_item()
        device = getattr(self, "device_entry", None)
        if item is None or device is None:
            return
        registry = dr.async_get(self.hass)
        current = registry.async_get(device.id)
        if current is not None and current.name != label(item):
            registry.async_update_device(current.id, name=label(item))

    def _named_item(self):
        return None


def _own_device(identifier, item):
    """A device of its own (one room, one Bluetooth sensor); device_info adds the product device link."""
    return DeviceInfo(identifiers={identifier}, name=label(item), manufacturer="intuibase")


class RoomEntity(HubEntity):
    """One E32 room, on the room's own device.

    The device carries the room name, so the entity names are plain
    ("Temperature", "Heat demand") and new entity IDs read like
    ``sensor.living_room_temperature`` (Home Assistant writes them in its own
    language). The unique IDs are the same as before the room devices: an
    existing entity keeps its entity ID and history and only moves device.
    """

    def _attach_room(self, hub, room, key):
        self.room_id = room["id"]
        # No suggested area: Home Assistant puts the area name in front of new
        # entity IDs (sensor.living_room_living_room_temperature); the user picks it.
        device = _own_device(room_device_identifier(hub.prefix, self.room_id), room)
        self._attach(hub, f"e32_room_{self.room_id}_{key}", device)
        self._attr_translation_key = f"room_{key}"

    def _named_item(self):
        return self.room

    @property
    def room(self):
        return self.hub.rooms.get(self.room_id)

    @property
    def available(self):
        return self.hub.fresh and self.room is not None


class HeatRequestSensor(HubEntity, SensorEntity):
    """The E32's computed boiler flow request (0 when it does not ask for heat)."""

    _attr_translation_key = "heat_request"
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
        device = _own_device(ble_device_identifier(hub.prefix, self.sensor_id), sensor)
        self._attach(hub, f"e32_ble_{self.sensor_id}_{metric}", device)
        self._attr_device_class, self._attr_native_unit_of_measurement, self._low, self._high = BLE_METRICS[metric]
        self._attr_translation_key = f"ble_{metric}"

    def _named_item(self):
        return self.sensor

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


def shadow_today(status):
    """Today's E32-vs-thermostat comparison (``shadow.today``), or None."""
    shadow = status.get("shadow") if status else None
    today = shadow.get("today") if type(shadow) is dict else None
    return today if type(today) is dict else None


def _count(value):
    return value if type(value) is int and value >= 0 else None


class ShadowSensor(HubEntity, SensorEntity):
    """One value of today's shadow comparison: the E32's decision next to the thermostat's (0x1A).

    The counters restart every day (and when the E32 restarts): total_increasing.
    """

    def __init__(self, hub, key):
        self.key = key
        self._attach(hub, f"hub_shadow_{key}")
        self._attr_translation_key = f"shadow_{key}"
        if key.endswith("heating_time_today"):
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_suggested_display_precision = 0
        elif key.endswith("starts_today"):
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        else:
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0

    @property
    def today(self):
        return shadow_today(self.hub.status) if self.hub.fresh else None

    @property
    def side(self):
        side = (self.today or {}).get(self.key.split("_", 1)[0])
        return side if type(side) is dict else None

    @property
    def available(self):
        return self.today is not None

    @property
    def native_value(self):
        today = self.today
        if today is None:
            return None
        if self.key == "agreement_today":
            known, agree = _count(today.get("s")), _count(today.get("agree_s"))
            unknown = _count(today.get("tado_unknown_s")) or 0
            if known is None or agree is None or known - unknown <= 0:
                return None
            return round(min(100.0, 100.0 * agree / (known - unknown)), 1)
        value = _count((self.side or {}).get("heat_s" if "heating_time" in self.key else "starts"))
        if value is None or "starts" in self.key:
            return value
        return round(value / 60, 1)

    @property
    def extra_state_attributes(self):
        today = self.today
        if today is None:
            return None
        if self.key == "agreement_today":
            keys = ("s", "tado_unknown_s", "both_s", "agree_s", "e32_only_s", "tado_only_s", "flow_diff_mean_c")
            return {"day": today.get("day"), **{k: today.get(k) for k in keys}}
        if "heating_time" in self.key:
            side = self.side or {}
            return {"day": today.get("day"), **{k: side.get(k) for k in ("flow_min_c", "flow_mean_c", "flow_max_c")}}
        keys = ("starts_paired", "starts_within_5min", "start_offset_mean_s", "start_offset_max_s")
        return {"day": today.get("day"), **{k: today.get(k) for k in keys}}


SHADOW_SENSORS = ("e32_heating_time_today", "tado_heating_time_today", "e32_starts_today", "tado_starts_today",
                  "agreement_today")


def burner_status(status):
    """The E32's own burner-start count (``burner``), or None on firmware without it.

    The boiler's own start counters read 0 on the EasyControl adapter, so
    this is the only real cycling data.
    """
    burner = status.get("burner") if status else None
    return burner if type(burner) is dict else None


class BurnerEntity(HubEntity):
    """Mixin: one value of the E32's burner-start count, on the product device."""

    @property
    def burner(self):
        return burner_status(self.hub.status) if self.hub.fresh else None

    @property
    def extra_state_attributes(self):
        burner = self.burner
        if not burner:
            return None
        return {"starts_last_hour": _count(burner.get("starts_last_hour")),
                "heating_starts_last_hour": _count(burner.get("heating_starts_last_hour"))}


class BurnerStartsSensor(BurnerEntity, SensorEntity):
    """Burner starts in the last hour, counted by the E32 on the bus."""

    _attr_translation_key = "burner_starts_last_hour"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub):
        self._attach(hub, "hub_burner_starts_last_hour")

    @property
    def available(self):
        return self.native_value is not None

    @property
    def native_value(self):
        return _count((self.burner or {}).get("starts_last_hour"))


class BurnerShortCyclingBinarySensor(BurnerEntity, BinarySensorEntity):
    """On while the E32 sees the burner start too often; unavailable while that is unknown."""

    _attr_translation_key = "burner_short_cycling"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, hub):
        self._attach(hub, "hub_burner_short_cycling")

    @property
    def available(self):
        return self.is_on is not None

    @property
    def is_on(self):
        value = (self.burner or {}).get("short_cycling")
        return value if type(value) is bool else None


# -- What the E32 learned: advice only (beta.18 keeps its own flow rule) -----


def _whole(value, low, high):
    """A plausible number; whole numbers stay int (34, not 34.0)."""
    result = number(value, low, high)
    return int(result) if result is not None and result == int(result) else result


def _text(item, key):
    value = item.get(key)
    return value if type(value) is str and len(value) <= 40 else None


def _flag(item, key):
    value = item.get(key)
    return value if type(value) is bool else None


def _utc(value):
    seconds = number(value, 1e9, 4.2e9)
    return datetime.fromtimestamp(seconds, timezone.utc) if seconds is not None else None


def _dict(item, key):
    value = item.get(key) if type(item) is dict else None
    return value if type(value) is dict else {}


def flow_advice(item):
    """One flow advice of the learner: a shortfall and the lowest flow that closes it in time."""
    if type(item) is not dict:
        return None
    return {"shortfall_c": _whole(item.get("shortfall_c"), -10, 30),
            "required_c_per_h": _whole(item.get("required_c_per_h"), 0, 20),
            "flow_c": _whole(item.get("flow_c"), 10, 90), "warmup_h": _whole(item.get("warmup_h"), 0, 48),
            "reason": _text(item, "reason"), "rule_flow_c": _whole(item.get("rule_flow_c"), 0, 90),
            "rule_warmup_h": _whole(item.get("rule_warmup_h"), 0, 48), "rule": _text(item, "rule")}


class LearnedRoomEntity(RoomEntity):
    """One learned value of an E32 room (``learned.rooms``), on the room's device."""

    @property
    def learned(self):
        return self.hub.learned.get(self.room_id) if self.hub.fresh else None

    @property
    def available(self):
        return self.hub.fresh and self.room is not None and self.learned is not None

    def _applied(self):
        """False while the E32 only reports its advice and keeps its own flow rule."""
        return (learned_status(self.hub.status) or {}).get("applied") is True


class RoomLearningSensor(LearnedRoomEntity, SensorEntity):
    """How far the E32 has learned how fast this room warms up: collecting, learning or ready."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = LEARNING_STATES

    def __init__(self, hub, room):
        self._attach_room(hub, room, "learning")

    @property
    def native_value(self):
        value = (self.learned or {}).get("readiness")
        return value if value in LEARNING_STATES else None

    @property
    def extra_state_attributes(self):
        learned = self.learned
        if learned is None:
            return None
        whole = learned_status(self.hub.status) or {}
        return {"room_id": self.room_id, "emitter": _text(learned, "emitter"),
                "segments": _count(learned.get("segments")), "periods": _count(learned.get("periods")),
                "heating_periods": _count(whole.get("heating_periods")), "learner": _text(whole, "status"),
                "loss_per_h": number(learned.get("loss_per_h"), 0, 1),
                "capacity_kwh_per_k": number(learned.get("capacity_kwh_per_k"), 0, 100),
                "applied": self._applied()}


class RoomFlowAdviceSensor(LearnedRoomEntity, SensorEntity):
    """The lowest flow that warms this room 1 °C in an acceptable time (unknown until learned)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 0
    # These follow the room minute by minute: shown, not kept in the history.
    _unrecorded_attributes = frozenset({"now", "other_shortfalls"})

    def __init__(self, hub, room):
        self._attach_room(hub, room, "flow_advice")

    def _advice(self):
        items = (self.learned or {}).get("advice")
        advice = [flow_advice(item) for item in items] if type(items) is list else []
        advice = [item for item in advice if item is not None]
        one = next((item for item in advice if item["shortfall_c"] == 1), None)
        return one, [item for item in advice if item is not one]

    @property
    def native_value(self):
        one, _ = self._advice()
        return one["flow_c"] if one else None

    @property
    def extra_state_attributes(self):
        learned = self.learned
        if learned is None:
            return None
        one, others = self._advice()
        one = one or {}
        return {"room_id": self.room_id, "applied": self._applied(),
                **{key: one.get(key) for key in ("warmup_h", "reason", "rule_flow_c", "rule_warmup_h", "rule")},
                "other_shortfalls": others, "now": flow_advice(learned.get("now"))}


class RoomHeatingStartSensor(RoomEntity, SensorEntity):
    """When the E32 would start heating to reach the next higher setpoint on time, and tonight's options."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _unrecorded_attributes = frozenset({"night_strategies"})

    def __init__(self, hub, room):
        self._attach_room(hub, room, "heating_start")

    @property
    def warmup(self):
        return self.hub.warmup.get(self.room_id) if self.hub.fresh else None

    @property
    def available(self):
        return self.hub.fresh and self.room is not None and self.warmup is not None

    @property
    def native_value(self):
        start = _dict(self.warmup, "optimum_start")
        if start.get("reason") != "planned":
            return None
        if (exact := _utc(start.get("predicted_start_utc"))) is not None:
            return exact
        at, lead = _utc(_dict(start, "next_switch").get("utc")), _whole(start.get("lead_minutes"), 0, 1440)
        return at - timedelta(minutes=lead) if at is not None and lead is not None else None

    @property
    def extra_state_attributes(self):
        if self.warmup is None:
            return None
        start, night = _dict(self.warmup, "optimum_start"), _dict(self.warmup, "night")
        switch = _dict(start, "next_switch")
        at = _utc(switch.get("utc"))
        items = night.get("strategies")
        strategies = [{"name": _text(item, "name"), "night_c": _whole(item.get("night_c"), 0, 35),
                       "kwh": number(item.get("kwh"), 0, 1000), "m3": number(item.get("m3"), 0, 100),
                       "eur": number(item.get("eur"), 0, 1000), "end_c": _whole(item.get("end_c"), -10, 40),
                       "on_time": _flag(item, "on_time")}
                      for item in (items if type(items) is list else []) if type(item) is dict]
        return {"room_id": self.room_id, "reason": _text(start, "reason"),
                "switch_at": at.isoformat() if at is not None else None,
                "from_c": _whole(switch.get("from_c"), 0, 35), "target_c": _whole(switch.get("target_c"), 0, 35),
                "lead_minutes": _whole(start.get("lead_minutes"), 0, 1440),
                "flow_c": _whole(start.get("flow_c"), 0, 90), "confidence": _text(start, "confidence"),
                "reachable": _flag(start, "reachable"), "start_now": _flag(start, "start_now"),
                "night_reason": _text(night, "reason"), "night_confidence": _text(night, "confidence"),
                "night_recommended": _text(night, "recommended"),
                "night_recommended_c": _whole(night.get("recommended_night_c"), 0, 35),
                "night_saving_m3": number(night.get("saving_m3"), 0, 100),
                "night_saving_eur": number(night.get("saving_eur"), 0, 1000),
                "night_strategies": strategies}


def dhw_status(status):
    """Today's hot-water summary (``dhw`` with ``today``), or None on firmware without it."""
    dhw = status.get("dhw") if status else None
    return dhw if type(dhw) is dict and type(dhw.get("today")) is dict else None


DHW_SENSORS = ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today")
DHW_KINDS = {"dhw_taps_today": "tapping", "dhw_keep_warm_today": "keep_warm"}


def _minutes(seconds):
    return round(seconds / 60, 1) if seconds is not None else None


class DhwTodaySensor(HubEntity, SensorEntity):
    """Today's hot water as the E32 sees it on the bus: taps, keeping warm, burner time.

    The counters restart every day (and when the E32 restarts): total_increasing.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, hub, key):
        self.key = key
        self._attach(hub, f"hub_{key}")
        self._attr_translation_key = key
        if key == "dhw_burner_time_today":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_suggested_display_precision = 0

    @property
    def dhw(self):
        return dhw_status(self.hub.status) if self.hub.fresh else None

    @property
    def available(self):
        return self.dhw is not None

    @property
    def native_value(self):
        dhw = self.dhw
        if dhw is None:
            return None
        if self.key == "dhw_burner_time_today":
            return _minutes(_count(dhw["today"].get("burner_s")))
        return _count(_dict(dhw["today"], DHW_KINDS[self.key]).get("count"))

    @property
    def extra_state_attributes(self):
        dhw = self.dhw
        if dhw is None:
            return None
        today, week = dhw["today"], _dict(dhw, "last_7_days")
        result = {"method": _text(dhw, "method"), "clock_known": _flag(dhw, "clock_known")}
        if self.key == "dhw_burner_time_today":
            return {**result, "tapping_minutes": _minutes(_count(_dict(today, "tapping").get("s"))),
                    "keep_warm_minutes": _minutes(_count(_dict(today, "keep_warm").get("s"))),
                    "last_7_days_minutes": _minutes(_count(week.get("burner_s")))}
        kind = DHW_KINDS[self.key]
        result.update(minutes=_minutes(_count(_dict(today, kind).get("s"))),
                      last_7_days=_count(_dict(week, kind).get("count")))
        if self.key == "dhw_taps_today":
            result.update(peak_flow_l_min=number(today.get("peak_flow_l_min"), 0, 60),
                          unknown_count=_count(_dict(today, "unknown").get("count")))
        return result


def wanted_sensors(hub):
    if shadow_today(hub.status) is not None:  # firmware that compares (E32 beta.18)
        for key in SHADOW_SENSORS:
            yield ("shadow", key), lambda key=key: ShadowSensor(hub, key)
    if burner_status(hub.status) is not None:  # firmware that counts burner starts
        yield ("burner",), lambda: BurnerStartsSensor(hub)
    if dhw_status(hub.status) is not None:  # firmware that sorts the hot-water episodes
        for key in DHW_SENSORS:
            yield ("dhw", key), lambda key=key: DhwTodaySensor(hub, key)
    for room_id, room in hub.rooms.items():
        yield ("room", room_id, "temperature"), lambda room=room: RoomTemperatureSensor(hub, room)
        yield ("room", room_id, "setpoint"), lambda room=room: RoomTemperatureSensor(hub, room, "setpoint", 5, 30)
        yield ("room", room_id, "status"), lambda room=room: RoomStatusSensor(hub, room)
        if room_id in hub.learned:  # firmware that learns the rooms (E32 beta.18)
            yield ("room", room_id, "learning"), lambda room=room: RoomLearningSensor(hub, room)
            yield ("room", room_id, "flow_advice"), lambda room=room: RoomFlowAdviceSensor(hub, room)
        if room_id in hub.warmup:  # only while the E32 clock is trusted
            yield ("room", room_id, "heating_start"), lambda room=room: RoomHeatingStartSensor(hub, room)
    for sensor_id, sensor in hub.ble.items():
        for metric in BLE_METRICS:
            # Only readings the sensor actually reports (not every profile has humidity).
            if sensor.get(metric) is not None:
                yield ("ble", sensor_id, metric), lambda sensor=sensor, metric=metric: BleSensor(hub, sensor, metric)


def wanted_demand(hub):
    if burner_status(hub.status) is not None:
        yield ("burner",), lambda: BurnerShortCyclingBinarySensor(hub)
    for room_id, room in hub.rooms.items():
        yield room_id, lambda room=room: RoomDemandBinarySensor(hub, room)


def removable_device(hass, entry, device):
    """Whether the user may delete this device: a room or Bluetooth sensor the E32 no longer reports.

    Only while the telemetry is fresh, so a short outage never makes a live
    room removable. Every other device of the entry stays.
    """
    hub = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub")
    if hub is None or not hub.fresh:
        return False
    for domain, identifier in device.identifiers:
        for kind, reported in (("room", hub.rooms), ("ble", hub.ble)):
            head = f"{hub.prefix}_e32_{kind}_"
            if domain == DOMAIN and identifier.startswith(head):
                return identifier.removeprefix(head) not in reported
    return False


async def async_setup_demand(hass, entry, async_add_entities):
    """Binary sensor platform (product entries): heat demand per E32 room, and burner short cycling."""
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
