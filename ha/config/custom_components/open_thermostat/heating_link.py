"""The one route between the E32 room control and Home Assistant.

The E32 owns the room plan. It reports its state in small retained MQTT
topics (E32 beta.19, docs/modern-thermostat/TELEMETRIEBUDGET.nl.md), each at
most 1.5 KB, sent on a real change (deadbands), at most every 10 s, else every
5 minutes:

- ``fw/state/heating``: the computed boiler request, mode, the active-control
  block (``active``), burner starts and the HA link;
- ``fw/state/room/<id>`` and ``fw/state/ble/<id>``: one room, one paired
  Bluetooth sensor;
- ``fw/config/plan``: the plan's room and sensor ids and how many parts the
  entity list has; ``fw/config/entities`` (and ``.../entities/<k>``): the HA
  entities the plan reads (``ha_entities``);
- ``fw/telemetry/learned/<id>`` (every 15 min or on a new result),
  ``fw/telemetry/summary`` (learned header, hot water; 5 min) and
  ``fw/telemetry/shadow`` (today's comparison; 5 min);
- ``fw/availability`` (retained online/offline, the LWT) and ``fw/heartbeat``
  every 60 s.

The hub assembles them into the status the entities always read (``status``,
the shape of ``/status/heating``), so a restarted Home Assistant is complete at
once from the retained messages. Values stay available until the E32 says it
is offline or three heartbeats are missed (``STALE_SECONDS``). HA forwards
exactly the listed entities' temperature and target to ``ha/heating_input`` on
every change and every five minutes, so a steady thermostat stays fresh.

One ``HeatingHub`` per entry holds the latest state. Every platform (sensor,
binary_sensor, select, number, datetime) creates its entities from it for the
room and Bluetooth ids it actually reports; all of them are unavailable while
the E32 is offline or silent.
"""
import json
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import CONF_TOPIC_PREFIX, DOMAIN

_LOGGER = logging.getLogger(__name__)
REFRESH_SECONDS = 300
MAX_ENTITIES = 40  # the E32 plan: 8 rooms x (4 sources + setpoint entity)
# fw/heartbeat every 60 s: unavailable after three missed ones (or fw/availability offline).
HEARTBEAT_SECONDS = 60
STALE_SECONDS = 3 * HEARTBEAT_SECONDS + 15
STALE_CHECK = timedelta(seconds=15)
ROOM_ID = re.compile(r"[a-z0-9_]{1,32}")
BLE_ID = re.compile(r"[0-9a-f]{12}")
ROOM_STATUSES = ["ok", "fallback", "stale", "lost", "inactive"]
LEARNING_STATES = ["collecting", "learning", "ready"]
# The highest flow the E32 requests: its plan maximum goes up to 80 °C (RoomPlan 21..80).
FLOW_REQUEST_MAX_C = 80
# A hard bound for the assembled status (the parts are each at most MAX_DOC_BYTES).
MAX_STATUS_BYTES = 8192
# Every E32 telemetry message (the E32's hard limit; usually <= 1 KB).
MAX_DOC_BYTES = 1536
MAX_SUMMARY_BYTES = 2048
MAX_ENTITY_PARTS = 8
MAX_BLE = 16
HEATING_TOPIC = "fw/state/heating"
ROOM_TOPIC = "fw/state/room/"
BLE_TOPIC = "fw/state/ble/"
PLAN_TOPIC = "fw/config/plan"
ENTITIES_TOPIC = "fw/config/entities"
LEARNED_TOPIC = "fw/telemetry/learned/"
SUMMARY_TOPIC = "fw/telemetry/summary"
SHADOW_TOPIC = "fw/telemetry/shadow"
# The flow policy's part of the summary ("flow", "night_gas"), sent apart to keep both within 1 KB.
FLOW_TOPIC = "fw/telemetry/flow"
FLOW_KEYS = ("flow", "night_gas")
HEARTBEAT_TOPIC = "fw/heartbeat"
AVAILABILITY_TOPIC = "fw/availability"


def decode_document(payload, max_bytes=MAX_DOC_BYTES):
    """One schema 1 JSON object of at most max_bytes, or None."""
    if not isinstance(payload, (str, bytes)) or len(payload) > max_bytes:
        return None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    return value if type(value) is dict and value.get("schema") == 1 else None


def _ids(value, pattern, limit):
    return (type(value) is list and len(value) <= limit and len(set(value)) == len(value)
            and all(type(i) is str and pattern.fullmatch(i) for i in value))


def decode_plan(payload):
    """``fw/config/plan``: {"revision","mode","rooms":[ids],"ble":[ids],"entity_parts"}, or None."""
    value = decode_document(payload)
    if (value is None or type(value.get("revision")) is not int or value.get("mode") not in ("shadow", "active")
            or not _ids(value.get("rooms"), ROOM_ID, 8) or not _ids(value.get("ble"), BLE_ID, MAX_BLE)
            or type(value.get("entity_parts")) is not int or not 1 <= value["entity_parts"] <= MAX_ENTITY_PARTS):
        return None
    return value


def decode_entities(payload, part):
    """One ``fw/config/entities[/<part>]`` part, or None."""
    value = decode_document(payload)
    entities = value.get("entities") if value else None
    if (value is None or value.get("part") != part or type(value.get("parts")) is not int
            or not 1 <= value["parts"] <= MAX_ENTITY_PARTS or not 0 <= part < value["parts"]
            or type(value.get("revision")) is not int or type(entities) is not list or len(entities) > MAX_ENTITIES
            or any(type(e) is not str or "." not in e or len(e) > 80 for e in entities)):
        return None
    return value


def decode_item(payload, topic_id, pattern):
    """One ``fw/state/room/<id>`` or ``fw/state/ble/<id>`` document whose id is the topic's, or None."""
    value = decode_document(payload)
    if value is None or type(topic_id) is not str or not pattern.fullmatch(topic_id) or value.get("id") != topic_id:
        return None
    value = dict(value)
    del value["schema"]
    return value


def decode_heartbeat(payload):
    value = decode_document(payload)
    return value if value is not None and type(value.get("uptime_s")) is int and value["uptime_s"] >= 0 else None


def decode_status(payload):
    """The E32 heating status, or None when it is not a schema 1 document."""
    if not isinstance(payload, (str, bytes)) or len(payload) > MAX_STATUS_BYTES:
        return None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    return valid_status(value)


def valid_status(value):
    """The (assembled) status when it is well-formed, else None."""
    if type(value) is not dict or value.get("schema") != 1 or value.get("mode") not in ("shadow", "active"):
        return None
    request, entities, rooms = value.get("request"), value.get("ha_entities"), value.get("rooms")
    if (type(request) is not dict or type(request.get("heat")) is not bool or type(request.get("flow_c")) is not int
            or not 0 <= request["flow_c"] <= FLOW_REQUEST_MAX_C or type(request.get("reason")) is not str
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


def decode_learned(topic_room, payload):
    """(learned room, plan or None) of one ``learned/<room id>`` message, or None.

    The payload's id must be the topic's room id; ``plan`` is null without a trusted clock.
    """
    if (not isinstance(payload, (str, bytes)) or len(payload) > MAX_STATUS_BYTES
            or type(topic_room) is not str or not ROOM_ID.fullmatch(topic_room)):
        return None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    if type(value) is not dict or value.get("schema") != 1 or value.get("id") != topic_room:
        return None
    learned, plan = value.get("learned"), value.get("plan")
    if type(learned) is not dict or (plan is not None and type(plan) is not dict):
        return None
    if plan is not None and plan.get("id", topic_room) != topic_room:  # the plan may carry its room id
        return None
    return {**learned, "id": topic_room}, ({**plan, "id": topic_room} if plan is not None else None)


def decode_summary(payload):
    """The ``summary`` document (schema 1: ``learned`` header, ``dhw``), or None.

    Either part may be missing; a part that is there must be an object.
    """
    if not isinstance(payload, (str, bytes)) or len(payload) > MAX_SUMMARY_BYTES:
        return None
    try:
        value = json.loads(payload)
    except (ValueError, TypeError, UnicodeError):
        return None
    if type(value) is not dict or value.get("schema") != 1:
        return None
    if any(value.get(key) is not None and type(value.get(key)) is not dict for key in ("learned", "dhw")):
        return None
    return value


def learned_inputs(header):
    """The energy inputs the learner uses (``learned.inputs``), or {} on firmware without them."""
    inputs = header.get("inputs") if type(header) is dict else None
    return inputs if type(inputs) is dict else {}


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


# A broadcast name: letters, then the end of the sensor's address (BTE_A3E8DB, ATC_E8DB, LYWSD03MMC excluded).
_BROADCAST_NAME = re.compile(r"[A-Za-z][A-Za-z0-9]{1,11}[ _-]?([0-9A-Fa-f]{6}|[0-9A-Fa-f]{4})")
_THERMOMETER = "Thermometer "  # the same word in English and Dutch


def ble_broadcast_name(sensor):
    """True while the E32 still has the name the sensor broadcasts (no own name was given)."""
    name = sensor.get("name")
    name = name.strip() if type(name) is str else ""
    if not name or name.lower() == sensor["id"]:
        return True
    match = _BROADCAST_NAME.fullmatch(name)
    return match is not None and sensor["id"].endswith(match.group(1).lower())


def ble_device_name(sensor, rooms, current=None):
    """The device name of a Bluetooth sensor, or None to keep ``current``.

    A name given on the E32 wins. A sensor with its broadcast name that exactly
    one room measures with reads "Thermometer <room>". While no room reports it
    as its source for a moment (lost, fallback), a "Thermometer <room>" name of
    a room that still exists stays, so the name never flips back and forth.
    A name the user gives in Home Assistant (name_by_user) is never touched.
    """
    if not ble_broadcast_name(sensor):
        return label(sensor)
    using = [room for room in rooms.values() if room.get("source") == sensor["id"]]
    if len(using) == 1:
        return (_THERMOMETER + label(using[0]))[:64]
    if (not using and type(current) is str and current.startswith(_THERMOMETER)
            and any(_THERMOMETER + label(room) == current for room in rooms.values())):
        return None
    return label(sensor)


TEMPERATURE_UNITS = (UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.KELVIN)


def celsius(value, unit, low, high):
    """``value`` in ``unit`` (°C, °F or K; none means °C) as °C within low..high, else None."""
    if unit in (None, "", UnitOfTemperature.CELSIUS):
        return number(value, low, high)
    if unit not in TEMPERATURE_UNITS or number(value, -1e6, 1e6) is None:
        return None
    from homeassistant.util.unit_conversion import TemperatureConverter
    return number(round(TemperatureConverter.convert(float(value), unit, UnitOfTemperature.CELSIUS), 2),
                  low, high)


def input_payload(state, temperature_unit=UnitOfTemperature.CELSIUS):
    """{"entity","temperature","target"} in °C for a climate, temperature sensor or setpoint number state.

    An input_number/number is only ever a room's setpoint entity: its value is the target.
    Climate attributes are in Home Assistant's unit system (``temperature_unit``);
    sensors and numbers carry their own ``unit_of_measurement``. The E32 works in °C.
    """
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    if state.domain == "climate":
        temperature = celsius(state.attributes.get("current_temperature"), temperature_unit, -40, 85)
        target = celsius(state.attributes.get("temperature"), temperature_unit, 5, 30)
    elif state.domain in ("input_number", "number"):
        unit = state.attributes.get("unit_of_measurement")
        temperature, target = None, celsius(state.state, unit, 5, 30)
    else:
        unit = state.attributes.get("unit_of_measurement")
        temperature, target = celsius(state.state, unit, -40, 85), None
    if temperature is None and target is None:
        return None
    return json.dumps({"entity": state.entity_id, "temperature": temperature, "target": target})


class HeatingHub:
    """The latest E32 heating state of one entry and who listens to it.

    ``status`` is assembled from the retained parts (``receive``); ``update``
    sets it directly (and is what the rest of the integration and its tests
    call). ``fresh`` while the E32 is online and its heartbeat is current.
    """

    def __init__(self, prefix, clock=time.monotonic):
        self.prefix = prefix
        self.clock = clock
        self.status = None
        # The E32's active-control block (``fw/state/heating`` ``active``), or None (heating_problem reads it).
        self.active = None
        self.rooms = {}
        self.ble = {}
        self.learned = {}
        self.warmup = {}
        # {room id: (received, learned room, plan or None)} from learned/<room id>
        self.learned_messages = {}
        # The latest summary (decode_summary) and when it arrived (monotonic).
        self.summary = None
        self.summary_received = None
        # fw/telemetry/summary and fw/telemetry/flow as received; summary is the two merged.
        self.summary_doc = None
        self.flow_doc = None
        self.received = None
        # The last live sign of the E32 (monotonic), kept while it is silent.
        self.last_seen = None
        self.plan = None  # room_plan.RoomPlanLink when the E32 credentials are stored
        # The retained parts the status is assembled from.
        self.heating = None
        self.room_states = {}
        self.ble_states = {}
        self.config = None
        self.entity_parts = {}
        self.entities = None  # the last complete entity list
        self.shadow = None
        self.online = None  # fw/availability: None until known
        self.heartbeat = None
        self.heartbeat_received = None
        self.started = clock()
        self._listeners = []
        self._trackers = []  # each track_entities' forget_rooms(room_ids)

    @property
    def fresh(self):
        return self.status is not None

    @property
    def revision(self):
        revision = self.status.get("revision") if self.status else None
        return revision if type(revision) is int else None

    @property
    def alive(self):
        """Online and heard: a heartbeat within STALE_SECONDS (from HA start until the first one)."""
        if self.online is False:
            return False
        since = self.heartbeat_received if self.heartbeat_received is not None else self.started
        return 0 <= self.clock() - since <= STALE_SECONDS

    @property
    def learned_header(self):
        """The learner's header (applied, status, heating periods, inputs): the summary, else the status."""
        header = learned_status(self.summary)
        return header if header is not None else learned_status(self.status)

    @property
    def dhw(self):
        """Today's hot water: the summary, else inside the status (older firmware)."""
        dhw = dhw_status(self.summary)
        return dhw if dhw is not None else dhw_status(self.status)

    @callback
    def add_listener(self, listener, first=False):
        """first: called before the others (the ha/heating_input forwarding)."""
        if first:
            self._listeners.insert(0, listener)
        else:
            self._listeners.append(listener)

        @callback
        def remove():
            if listener in self._listeners:
                self._listeners.remove(listener)
        return remove

    @callback
    def notify(self):
        # One failing listener (an entity, a forwarder) never stops the others.
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("OpenThermostat: an E32 telemetry listener failed")

    @callback
    def forget_removed_rooms(self, room_ids):
        """Rooms back in the plan whose entities were removed: every tracker adds them again."""
        for forget_rooms in list(self._trackers):
            forget_rooms(frozenset(room_ids))

    def _merge_learned(self):
        """The learned rooms and plans: from the status (older firmware) and the per-room messages."""
        learned, warmup = learned_rooms(self.status), plan_rooms(self.status)
        plan_ids = set(self.config["rooms"]) if self.config else None
        for room_id, (_, room, plan) in self.learned_messages.items():
            if plan_ids is not None and room_id not in plan_ids:
                continue
            learned[room_id] = room
            if plan is not None:
                warmup[room_id] = plan
            else:
                warmup.pop(room_id, None)
        self.learned, self.warmup = learned, warmup

    @callback
    def update(self, status):
        self.status = status
        active = status.get("active") if status else None
        self.active = active if type(active) is dict else None
        self.rooms = status_rooms(status)
        self.ble = status_ble(status)
        self.received = self.clock() if status is not None else None
        if status is not None:
            self.last_seen = self.received
        self._merge_learned()
        self.notify()

    def _assemble(self):
        """The status from the parts, or None while the E32 is not alive or a part is missing."""
        config, heating = self.config, self.heating
        if not self.alive or config is None or heating is None:
            return None
        parts = [self.entity_parts.get(k) for k in range(config["entity_parts"])]
        if all(p is not None and p["parts"] == config["entity_parts"] and p["revision"] == config["revision"] for p in parts):
            entities = [e for p in parts for e in p["entities"]]
            if len(entities) <= MAX_ENTITIES:
                self.entities = entities
        status = {key: value for key, value in heating.items() if key not in ("rooms", "ble_sensors", "ha_entities", "shadow")}
        status["ha_entities"] = list(self.entities or [])
        status["rooms"] = [self.room_states[i] for i in config["rooms"] if i in self.room_states]
        status["ble_sensors"] = [self.ble_states[i] for i in config["ble"] if i in self.ble_states]
        if self.shadow is not None:
            status["shadow"] = {key: value for key, value in self.shadow.items() if key != "schema"}
        return valid_status(status)

    @callback
    def refresh(self):
        """Assemble again after a part changed (or the E32 went quiet)."""
        status = self._assemble()
        if status is None and self.status is None:
            return
        live = self.last_seen
        self.update(status)
        if status is not None and live is not None and self.received is not None:
            self.last_seen = max(live, self.last_seen)

    @callback
    def receive(self, suffix, payload, retained=False):
        """One E32 message (topic after the prefix). A retained one is state too."""
        empty = payload in ("", b"")
        if suffix == AVAILABILITY_TOPIC:
            if payload not in ("online", "offline"):
                return
            self.online = payload == "online"
            if self.online and not retained:
                self.last_seen = self.clock()
        elif suffix == HEARTBEAT_TOPIC:
            beat = decode_heartbeat(payload)
            if beat is None or retained:
                return
            self.heartbeat, self.heartbeat_received = beat, self.clock()
            self.online = True if self.online is None else self.online
            self.last_seen = self.heartbeat_received
        elif suffix == HEATING_TOPIC:
            self.heating = None if empty else decode_document(payload)
        elif suffix == PLAN_TOPIC:
            plan = decode_plan(payload)
            if plan is None and not empty:
                return  # a malformed plan never drops the rooms
            self.config = plan
            if plan is not None:
                for key, store in ((tuple(plan["rooms"]), self.room_states), (tuple(plan["ble"]), self.ble_states)):
                    for item in [i for i in store if i not in key]:
                        del store[item]
                for room_id in [r for r in self.learned_messages if r not in plan["rooms"]]:
                    del self.learned_messages[room_id]
                for part in [k for k in self.entity_parts if k >= plan["entity_parts"]]:
                    del self.entity_parts[part]
        elif suffix == ENTITIES_TOPIC or suffix.startswith(ENTITIES_TOPIC + "/"):
            tail = suffix[len(ENTITIES_TOPIC) + 1:]
            part = 0 if suffix == ENTITIES_TOPIC else int(tail) if tail.isdigit() and len(tail) == 1 else None
            if part is None:
                return
            value = None if empty else decode_entities(payload, part)
            if value is None:
                self.entity_parts.pop(part, None)
            else:
                self.entity_parts[part] = value
        elif suffix.startswith(ROOM_TOPIC) or suffix.startswith(BLE_TOPIC):
            room = suffix.startswith(ROOM_TOPIC)
            key = suffix[len(ROOM_TOPIC if room else BLE_TOPIC):]
            store = self.room_states if room else self.ble_states
            value = None if empty else decode_item(payload, key, ROOM_ID if room else BLE_ID)
            if value is None:
                store.pop(key, None)
            else:
                store[key] = value
        elif suffix.startswith(LEARNED_TOPIC):
            room_id = suffix[len(LEARNED_TOPIC):]
            if empty:
                self.learned_messages.pop(room_id, None)
            else:
                value = decode_learned(room_id, payload)
                if value is None:
                    return
                self.learned_messages[room_id] = (self.clock(), *value)
        elif suffix in (SUMMARY_TOPIC, FLOW_TOPIC):
            if suffix == SUMMARY_TOPIC:
                self.summary_doc = None if empty else decode_summary(payload)
            else:
                flow = None if empty else decode_document(payload)
                self.flow_doc = ({k: flow[k] for k in FLOW_KEYS if type(flow.get(k)) is dict}
                                 if flow is not None else None)
            summary = self.summary_doc
            if summary is not None and self.flow_doc:
                summary = {**summary, **self.flow_doc}
            self.summary = summary
            self.summary_received = self.clock() if summary is not None else None
        elif suffix == SHADOW_TOPIC:
            self.shadow = None if empty else decode_document(payload)
        else:
            return
        if not retained and suffix != AVAILABILITY_TOPIC:
            self.last_seen = self.clock()
        self.refresh()

    @callback
    def update_learned(self, room_id, value):
        """One room's learned message (decode_learned); None (invalid) is ignored."""
        if value is None:
            return
        self.learned_messages[room_id] = (self.clock(), *value)
        self._merge_learned()
        self.notify()

    @callback
    def update_summary(self, summary):
        """The latest summary (decode_summary); None (invalid) drops the previous one."""
        if summary is None and self.summary is None:
            return
        self.summary = summary
        self.summary_received = self.clock() if summary is not None else None
        self.notify()

    @callback
    def check_stale(self, _now=None):
        """Periodically: three missed heartbeats make every value unavailable; a heartbeat restores them."""
        if self.status is not None and not self.alive:
            self.update(None)
        elif self.status is None and self.alive and self.heating is not None:
            self.refresh()

    @callback
    def stop(self):
        if self.plan is not None:
            self.plan.stop()
        self._listeners.clear()


def topic_base(hass, entry):
    """The E32's MQTT topic base of an entry: the running link's, else ``<topic_prefix>/v1/``.

    The E32 publishes its retained telemetry there whether or not this entry
    runs its shadow link, so the telemetry never depends on that link.
    """
    connection = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("v1_connection")
    prefix = getattr(connection, "prefix", None)
    return prefix if type(prefix) is str and prefix else entry.data[CONF_TOPIC_PREFIX] + "/v1/"


class _RetainedLink:
    """Stands in for the link's connection without a running link: its client is the
    retained boiler source (v1_boiler_fields), looked up when read, so the order in
    which the sensor setup steps run does not matter."""

    def __init__(self, state, prefix):
        self._state, self.prefix = state, prefix

    @property
    def client(self):
        from .v1_boiler_fields import SOURCE_KEY
        return self._state.get(SOURCE_KEY)


def heating_hub(hass, entry):
    """The entry's one hub, created by whichever platform asks first."""
    state = hass.data[DOMAIN][entry.entry_id]
    hub = state.get("heating_hub")
    if hub is None:
        hub = state["heating_hub"] = HeatingHub(entry.data[CONF_TOPIC_PREFIX])
        from .room_plan import RoomPlanLink
        hub.plan = RoomPlanLink.for_entry(hass, entry, hub)
        entry.async_on_unload(hub.stop)
        from .room_groups import attach_hub
        attach_hub(hass, entry, hub)  # product entries: each room's entities in its own group
        from .e32_access import clear
        entry.async_on_unload(lambda: clear(hass, entry))
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
    """Add each entity wanted(hub) yields ((key, factory) pairs) once, when first seen.

    A key whose entity was removed from Home Assistant (its room left the plan,
    the user deleted the device) is forgotten once wanted(hub) no longer yields
    it, so the same key coming back (a room added again with the same id) gets
    a new entity, without a reload. While the E32 still reports it (its status
    trails a plan change), a removed entity is not created again;
    hub.forget_removed_rooms() adds the rooms that are back in the plan.
    """
    known, current = set(), set()
    removed = {}  # key: the removed entity, while wanted(hub) still yields the key

    @callback
    def forget(key, entity):
        if key in current:
            removed[key] = entity
        else:
            known.discard(key)

    @callback
    def refresh():
        nonlocal current
        new, keys = [], set()
        for key, factory in wanted(hub):
            keys.add(key)
            if key not in known:
                known.add(key)
                entity = factory()
                entity.async_on_remove(lambda key=key, entity=entity: forget(key, entity))
                new.append(entity)
        current = keys
        for key in [key for key in removed if key not in keys]:
            del removed[key]
            known.discard(key)
        if new:
            from .room_groups import add_grouped
            add_grouped(hub, async_add_entities, new, options)

    @callback
    def forget_rooms(room_ids):
        returned = [key for key, entity in removed.items() if getattr(entity, "room_id", None) in room_ids]
        for key in returned:
            del removed[key]
            known.discard(key)
        if returned:
            refresh()

    remove_listener = hub.add_listener(refresh)
    hub._trackers.append(forget_rooms)
    refresh()

    @callback
    def remove():
        remove_listener()
        if forget_rooms in hub._trackers:
            hub._trackers.remove(forget_rooms)
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
        registry = dr.async_get(self.hass)
        product = registry.async_get_device_by_identifier((DOMAIN, self.hub.prefix), entry.entry_id)
        extra = {"via_device_id": product.id} if product is not None else {}
        item = self._named_item()
        if item is not None:
            # The same name _follow_name keeps: adding the entity again (a restart) never resets it.
            current = registry.async_get_device_by_identifier(next(iter(info["identifiers"])), entry.entry_id)
            name = self._device_name(item, current.name if current is not None else None)
            if name is None and current is not None:
                name = current.name
            if name is not None:
                extra["name"] = name
        return {**info, **extra}

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
        name = self._device_name(item, current.name) if current is not None else None
        if name is not None and current.name != name:
            registry.async_update_device(current.id, name=name)

    def _named_item(self):
        return None

    def _device_name(self, item, current):
        """The device's own name for ``item`` (None: keep ``current``); name_by_user is never changed."""
        return label(item)


def _own_device(identifier, item):
    """A device of its own (one room, one Bluetooth sensor); device_info adds the product device link."""
    return DeviceInfo(identifiers={identifier}, name=label(item), manufacturer="OpenThermostat")


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
        # Newer firmware leaves inactive_until out of the MQTT rooms: the plan has it.
        until = room.get("inactive_until") if "inactive_until" in room else (
            (self.hub.plan.room(self.room_id) or {}).get("inactive_until") if self.hub.plan is not None else None)
        return {"room_id": self.room_id, "source": room.get("source"), "state": room.get("state"),
                "inactive_until": until, "demand": room.get("demand"),
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
        device["name"] = ble_device_name(sensor, hub.rooms) or label(sensor)  # a new device's first name
        self._attach(hub, f"e32_ble_{self.sensor_id}_{metric}", device)
        self._attr_device_class, self._attr_native_unit_of_measurement, self._low, self._high = BLE_METRICS[metric]
        self._attr_translation_key = f"ble_{metric}"

    def _device_name(self, item, current):
        return ble_device_name(item, self.hub.rooms, current)

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


def shadow_has_thermostat(status):
    """Whether today's comparison has seen a thermostat on the bus (its 0x1A flow request).

    A home without an EMS thermostat reports the thermostat side unknown all day
    (``tado_unknown_s == s``) and never any heat; it gets no comparison entities.
    """
    today = shadow_today(status)
    if today is None:
        return False
    side = today.get("tado")
    if type(side) is dict and ((_count(side.get("heat_s")) or 0) > 0 or (_count(side.get("starts")) or 0) > 0
                               or any(number(side.get(key), 0, 100) is not None
                                      for key in ("flow_min_c", "flow_mean_c", "flow_max_c"))):
        return True
    known, unknown = _count(today.get("s")), _count(today.get("tado_unknown_s"))
    return known is not None and unknown is not None and unknown < known


class ShadowSensor(HubEntity, SensorEntity):
    """One value of today's shadow comparison: the E32's decision next to the thermostat's (0x1A).

    The counters restart every day (and when the E32 restarts): total_increasing.
    Diagnostic: the generated dashboard shows them on its Comparison subview, the device page
    keeps them out of the main list.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        return (self.hub.learned_header or {}).get("applied") is True


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
        whole = self.hub.learned_header or {}
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
        # The value is the advice for a 1 °C shortfall.
        return {"room_id": self.room_id, "shortfall_c": 1, "applied": self._applied(),
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
        # MQTT carries the compact form (no next_switch, no strategies); /status/heating the full one.
        # The E32 names the night setpoint recommended_night_c (recommended_c in early beta.18 builds).
        recommended_c = night.get("recommended_night_c", night.get("recommended_c"))
        result = {"room_id": self.room_id, "reason": _text(start, "reason"),
                  "lead_minutes": _whole(start.get("lead_minutes"), 0, 1440),
                  "flow_c": _whole(start.get("flow_c"), 0, 90), "confidence": _text(start, "confidence"),
                  "reachable": _flag(start, "reachable"), "start_now": _flag(start, "start_now"),
                  "night_reason": _text(night, "reason"), "night_recommended": _text(night, "recommended"),
                  "night_recommended_c": _whole(recommended_c, 0, 35),
                  "night_saving_m3": number(night.get("saving_m3"), 0, 100),
                  "night_saving_eur": number(night.get("saving_eur"), 0, 1000)}
        if "confidence" in night:
            result["night_confidence"] = _text(night, "confidence")
        if type(start.get("next_switch")) is dict:
            switch = start["next_switch"]
            at = _utc(switch.get("utc"))
            result.update(switch_at=at.isoformat() if at is not None else None,
                          from_c=_whole(switch.get("from_c"), 0, 35), target_c=_whole(switch.get("target_c"), 0, 35))
        if type(night.get("strategies")) is list:
            result["night_strategies"] = [
                {"name": _text(item, "name"), "night_c": _whole(item.get("night_c"), 0, 35),
                 "kwh": number(item.get("kwh"), 0, 1000), "m3": number(item.get("m3"), 0, 100),
                 "eur": number(item.get("eur"), 0, 1000), "end_c": _whole(item.get("end_c"), -10, 40),
                 "on_time": _flag(item, "on_time")}
                for item in night["strategies"] if type(item) is dict]
        return result


def dhw_status(status):
    """Today's hot water (``dhw`` with ``today``) of a status or summary, or None without it."""
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
        if key != "dhw_taps_today":  # the taps are the everyday value; the rest is detail
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if key == "dhw_burner_time_today":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_suggested_display_precision = 0

    @property
    def dhw(self):
        return self.hub.dhw if self.hub.fresh else None

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
    # Firmware that compares (E32 beta.18), and only once a thermostat to compare with shows up.
    if shadow_has_thermostat(hub.status):
        for key in SHADOW_SENSORS:
            yield ("shadow", key), lambda key=key: ShadowSensor(hub, key)
    if burner_status(hub.status) is not None:  # firmware that counts burner starts
        yield ("burner",), lambda: BurnerStartsSensor(hub)
    if hub.dhw is not None:  # firmware that sorts the hot-water episodes
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
    options = add_options(hass, entry)
    from .heating_problem import HeatingProblemSensor
    async_add_entities([HeatingProblemSensor(entry, hub)], **options)  # "is my heating OK?"
    entry.async_on_unload(track_entities(hub, async_add_entities, options, wanted_demand))


async def async_setup_heating_link(hass, entry, async_add_entities, **options):
    """The E32 telemetry, its entities and the ha/heating_input forwarding.

    Product entries need only the MQTT prefix and the broker, not the shadow
    link: a stopped link (shadow off, an interrupted Connect E32) never hides
    the E32 rooms or stops the forwarding. Other entries keep needing the link.
    """
    from .product import is_product
    state = hass.data[DOMAIN][entry.entry_id]
    connection = state.get("v1_connection")
    if connection is None or connection.client is None:
        from .room_plan import has_room_plan
        if not has_room_plan(entry):  # only an installation with a connected E32 (no rows before that)
            return
        # The advice reads the boiler values of the retained source instead.
        connection = _RetainedLink(state, topic_base(hass, entry))
    base = topic_base(hass, entry)
    hub = heating_hub(hass, entry)
    options = add_options(hass, entry, options)
    sensor = HeatRequestSensor(hub)
    async_add_entities([sensor], **options)
    entry.async_on_unload(track_entities(hub, async_add_entities, options, wanted_sensors))
    if is_product(entry):  # the tuning advice (advice only) on the product device
        from .heating_advice import async_setup_heating_advice
        try:
            await async_setup_heating_advice(hass, entry, async_add_entities, options, hub, connection)
        except Exception:  # noqa: BLE001 - the advice is optional; the rooms and forwarding are not
            _LOGGER.exception("OpenThermostat: setting up the heating advice and gas use failed; "
                              "the E32 rooms still load")
    forwarded = []
    unsubscribe_states = None
    was_fresh = False

    def send(payload):
        hass.async_create_task(mqtt.async_publish(hass, base + "ha/heating_input", payload, 0, False))

    def publish(entity_id):
        payload = input_payload(hass.states.get(entity_id), hass.config.units.temperature_unit)
        if payload is not None:
            send(payload)

    # The optional gas meter, gas price, outdoor temperature and boiler power
    # (energy options) go the same route as typed payloads.
    from .energy_input import EnergyForwarder
    energy = state["energy_forwarder"] = EnergyForwarder(
        hass, entry, send, lambda hass, ids, action: async_track_state_change_event(hass, ids, action))

    @callback
    def state_changed(event):
        publish(event.data["entity_id"])

    @callback
    def refresh(_now=None):
        for entity_id in forwarded:
            publish(entity_id)
        energy.publish()

    @callback
    def follow():
        """After every hub change: track exactly the plan's entities; send all at once when new or back."""
        nonlocal forwarded, unsubscribe_states, was_fresh
        status = hub.status
        back = status is not None and not was_fresh
        was_fresh = status is not None
        if status is None:
            return
        if status["ha_entities"] == forwarded:
            if back:
                energy.publish()  # the E32 is (back) online: send the energy values at once
            return
        forwarded = list(status["ha_entities"])
        if unsubscribe_states is not None:
            unsubscribe_states()
            unsubscribe_states = None
        if forwarded:
            unsubscribe_states = async_track_state_change_event(hass, forwarded, state_changed)
        refresh()

    @callback
    def receive(message):
        topic = getattr(message, "topic", "")
        if type(topic) is str and topic.startswith(base):
            hub.receive(topic[len(base):], message.payload, retained=getattr(message, "retain", False))

    @callback
    def unload():
        if unsubscribe_states is not None:
            unsubscribe_states()

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(hub.add_listener(follow, first=True))
    for topic in (AVAILABILITY_TOPIC, HEARTBEAT_TOPIC, HEATING_TOPIC, ROOM_TOPIC + "+", BLE_TOPIC + "+", PLAN_TOPIC,
                  ENTITIES_TOPIC, ENTITIES_TOPIC + "/+", LEARNED_TOPIC + "+", SUMMARY_TOPIC, FLOW_TOPIC, SHADOW_TOPIC):
        entry.async_on_unload(await mqtt.async_subscribe(hass, base + topic, receive))
    entry.async_on_unload(async_track_time_interval(hass, refresh, timedelta(seconds=REFRESH_SECONDS)))
    entry.async_on_unload(async_track_time_interval(hass, hub.check_stale, STALE_CHECK))
    entry.async_on_unload(unload)
    energy.reconfigure()
    entry.async_on_unload(energy.stop)
