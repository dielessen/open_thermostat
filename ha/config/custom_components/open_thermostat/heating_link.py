"""The one route between the E32 room control and Home Assistant.

The E32 owns the room plan. It reports its state in small retained MQTT
topics (E32 beta.19, docs/modern-thermostat/TELEMETRIEBUDGET.nl.md), each at
most 1.5 KB, sent on a real change (deadbands), at most every 10 s, else every
5 minutes:

- ``fw/state/heating``: the computed boiler request, mode, the active-control
  block (``active``), burner starts and the HA link;
- ``fw/state/room/<id>`` and ``fw/state/ble/<id>``: one room, one paired
  Bluetooth sensor;
- ``fw/state/trv/<room>`` (E32 beta.24, only with radiator valves configured):
  one room's valves (position, battery, health), listed in ``fw/config/plan``
  ``trv``; the valve output and flow offset are ``fw/state/heating`` ``trv``;
- ``fw/config/plan``: the plan's room and sensor ids and how many parts the
  entity list has; ``fw/config/entities`` (and ``.../entities/<k>``): the HA
  entities the plan reads (``ha_entities``);
- ``fw/telemetry/learned/<id>`` (every 15 min or on a new result),
  ``fw/telemetry/summary`` (learned header, hot water; 5 min) with its parts
  sent apart to keep each within 1 KB and merged into it again here:
  ``fw/telemetry/flow`` (the flow policy's ``flow`` and ``night_gas``),
  ``fw/telemetry/tuning`` (the self-tuning's ``tuning``, E32 rc.2) and
  ``fw/telemetry/scoreboard`` (yesterday's and today's ``scoreboard``, E32 rc.4;
  rc.4 preview firmware carried it inside the summary itself) and
  ``fw/telemetry/insight`` (what the E32 knows, the house, the boiler's response and
  yesterday's insights, E32 rc.5; merged as ``insight``, insight.py), and
  ``fw/telemetry/shadow`` (today's comparison; 5 min) and
  ``fw/telemetry/readiness`` (E32 1.0: ready to take over?, takeover_readiness.py; 5 min);
- ``fw/availability`` (retained online/offline, the LWT) and ``fw/heartbeat``
  every 60 s.

The hub assembles them into the status the entities always read (``status``,
the shape of ``/status/heating``), so a restarted Home Assistant is complete at
once from the retained messages. Values stay available until the E32 says it
is offline or three heartbeats are missed (``STALE_SECONDS``). HA forwards
exactly the listed entities' temperature and target to ``ha/heating_input`` on
every change and every five minutes, so a steady thermostat stays fresh. Every
message goes through the entry's ``HeatingInputLink``; ``HeatingInputWatch``
checks against the E32's ``ha.input_age_s`` that they arrive (P22).

One ``HeatingHub`` per entry holds the latest state. Every platform (sensor,
binary_sensor, select, number, datetime) creates its entities from it for the
room and Bluetooth ids it actually reports; all of them are unavailable while
the E32 is offline or silent.
"""
import asyncio
import json
import logging
import math
import re
import threading
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
from homeassistant.util import dt as dt_util

from .const import CONF_TOPIC_PREFIX, DOMAIN

_LOGGER = logging.getLogger(__name__)
REFRESH_SECONDS = 300
# A source that reported nothing for this long froze (an integration that keeps its last state instead of going
# unavailable): the five-minute refresh no longer sends it as fresh, so the E32 ages it out after 15 minutes and
# uses the room's next source. Polled thermostats and sensors report far more often; event-driven ones (a generic
# thermostat, a valve) at least on every change. A setpoint helper (input_number/number) is a setting, never silent.
SOURCE_SILENT_S = 3 * 3600
MAX_ENTITIES = 40  # the E32 plan: 8 rooms x (4 sources + setpoint entity)
# fw/heartbeat every 60 s: unavailable after three missed ones (or fw/availability offline).
HEARTBEAT_SECONDS = 60
STALE_SECONDS = 3 * HEARTBEAT_SECONDS + 15
STALE_CHECK = timedelta(seconds=15)
# A telemetry listener that keeps failing logs its traceback at most this often (R4-10).
LISTENER_LOG_SECONDS = 60
ROOM_ID = re.compile(r"[a-z0-9_]{1,32}")
BLE_ID = re.compile(r"[0-9a-f]{12}")
ROOM_STATUSES = ["ok", "fallback", "stale", "lost", "inactive", "window_open", "window_pending"]
# The E32's own room statuses; the window states come from the room's comfort (RoomOverrides.h).
E32_ROOM_STATUSES = ROOM_STATUSES[:5]


def room_status(room):
    """The room's control status; a window contact shows while the room has a working measurement.

    The E32 reports "window": "open" (paused at frost protection) or "pending"
    (open, the delay still runs) in the room's comfort. A missing or old
    measurement stays visible first: that is a problem to fix.
    """
    value = room.get("status") if type(room) is dict else None
    if value not in E32_ROOM_STATUSES:
        return None
    comfort = room.get("comfort")
    window = comfort.get("window") if type(comfort) is dict else None
    if value in ("ok", "fallback") and window in ("open", "pending"):
        return f"window_{window}"
    return value
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
TRV_TOPIC = "fw/state/trv/"
PLAN_TOPIC = "fw/config/plan"
ENTITIES_TOPIC = "fw/config/entities"
LEARNED_TOPIC = "fw/telemetry/learned/"
SUMMARY_TOPIC = "fw/telemetry/summary"
SHADOW_TOPIC = "fw/telemetry/shadow"
READINESS_TOPIC = "fw/telemetry/readiness"
# The flow policy's part of the summary ("flow", "night_gas"), sent apart to keep both within 1 KB.
# E32 rc.5 adds the boiler's response ("boiler", BoilerResponse) beside "flow"; merged into the summary as "boiler".
FLOW_TOPIC = "fw/telemetry/flow"
FLOW_KEYS = ("flow", "night_gas", "boiler")
# The self-tuning's state, knobs and newest changes (rc.2, AutoTuner), merged into the summary as "tuning".
TUNING_TOPIC = "fw/telemetry/tuning"
# Yesterday's and today's scoreboard (rc.4, Scoreboard), {"schema": 1, "scoreboard": {...}}, merged into the
# summary as "scoreboard" (scoreboard.py reads it there; a summary that still carries it keeps working).
SCOREBOARD_TOPIC = "fw/telemetry/scoreboard"
# What the E32 knows, the house model, the boiler's response and yesterday's insights (E32 rc.5, retained, every
# 5 minutes): {"schema": 1, "knowledge": {..}, "house": {..}, "boiler": {..}, "insights": [..]}, merged into the
# summary as "insight" (insight.py reads it there). The parts may also come in one "insight" object.
INSIGHT_TOPIC = "fw/telemetry/insight"
INSIGHT_KEYS = ("knowledge", "house", "boiler", "insights")
# The E32 sends the insight every 5 minutes: after this many live heartbeats (one a minute) without one, a
# retained insight left on the broker (firmware without the topic, after a downgrade) is dropped.
INSIGHT_MISSED_HEARTBEATS = 16
HEARTBEAT_TOPIC = "fw/heartbeat"
AVAILABILITY_TOPIC = "fw/availability"
# What only the hub reads: the shadow session (v1_mqtt.NativeShadowConnection, subscribed to fw/#)
# drops these at once instead of decoding every E32 message a second time (R4-03).
_HUB_ONLY = (HEATING_TOPIC, PLAN_TOPIC, ENTITIES_TOPIC, SUMMARY_TOPIC, FLOW_TOPIC, TUNING_TOPIC, SCOREBOARD_TOPIC,
             INSIGHT_TOPIC, SHADOW_TOPIC, READINESS_TOPIC)
_HUB_ONLY_PARTS = (ROOM_TOPIC, BLE_TOPIC, TRV_TOPIC, LEARNED_TOPIC, ENTITIES_TOPIC + "/")


def hub_only_topic(suffix):
    """True for an E32 topic (after the prefix) that only the heating hub reads."""
    return suffix in _HUB_ONLY or suffix.startswith(_HUB_ONLY_PARTS)


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


def decode_trv(payload, topic_id):
    """One ``fw/state/trv/<room>`` document whose room is the topic's, or None."""
    value = decode_document(payload)
    if (value is None or type(topic_id) is not str or not ROOM_ID.fullmatch(topic_id) or value.get("room") != topic_id
            or type(value.get("control")) is not bool or type(value.get("valves")) is not list or len(value["valves"]) > 4
            or any(type(v) is not dict or type(v.get("name")) is not str for v in value["valves"])):
        return None
    value = dict(value)
    del value["schema"]
    return value


def status_valves(status):
    """{room id: its radiator valves} from the status ``trv`` (empty without valves)."""
    trv = status.get("trv") if status else None
    return rooms_by_id([{**room, "id": room.get("room")} for room in trv.get("rooms", []) if type(room) is dict]
                       if type(trv) is dict and type(trv.get("rooms")) is list else None)


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
    room = {**learned, "id": topic_room}
    # E32 rc.5 (FreeHeat): "free_heat" belongs to the room, also when it sits beside "learned".
    if "free_heat" not in room and type(value.get("free_heat")) is dict:
        room["free_heat"] = value["free_heat"]
    return room, ({**plan, "id": topic_room} if plan is not None else None)


def decode_insight(payload):
    """``fw/telemetry/insight`` (E32 rc.5): {"knowledge", "house", "boiler", "insights"} (the parts it has), or None.

    The parts sit at the top of the schema 1 document or in one "insight" object; a part of the wrong type
    is left out (insight.py checks every value), and a document without any part is None.
    """
    value = decode_document(payload)
    if value is None:
        return None
    body = value["insight"] if type(value.get("insight")) is dict else value
    parts = {key: body[key] for key in INSIGHT_KEYS
             if type(body.get(key)) is (list if key == "insights" else dict)}
    return parts or None


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


def silent_source(state, now):
    """True for a source state that reported nothing for SOURCE_SILENT_S (``last_reported``, else ``last_updated``)."""
    if state is None or state.domain in ("input_number", "number"):
        return False
    reported = getattr(state, "last_reported", None) or state.last_updated
    return (now - reported).total_seconds() > SOURCE_SILENT_S


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
        self.valves = {}  # {room id: fw/state/trv/<room>}, empty without radiator valves
        self.ha_valves = None  # ha_valves.HaValveDriver: Home Assistant's own valves (e32_valves.watch)
        self.learned = {}
        self.warmup = {}
        # {room id: (received, learned room, plan or None)} from learned/<room id>
        self.learned_messages = {}
        # The latest summary (decode_summary) and when it arrived (monotonic).
        self.summary = None
        self.summary_received = None
        # fw/telemetry/summary, fw/telemetry/flow, fw/telemetry/tuning, fw/telemetry/scoreboard and
        # fw/telemetry/insight as received; summary is the five merged.
        self.summary_doc = None
        self.flow_doc = None
        self.tuning_doc = None
        self.scoreboard_doc = None
        self.insight_doc = None
        # True once an insight the E32 had sent is gone again (an empty or broken message, or none for
        # INSIGHT_MISSED_HEARTBEATS live heartbeats): its notifications go (insight.InsightNotifier).
        self.insight_gone = False
        self._insight_beats = 0  # live heartbeats since the last insight message
        # True once a live (not retained) insight message arrived in this Home Assistant run, until the insight
        # is gone again: a retained one alone may be stale (left by a firmware downgrade), so the insight
        # notifications wait for a live one (insight.InsightNotifier).
        self.insight_live = False
        self.received = None
        # The last live sign of the E32 (monotonic), kept while it is silent.
        self.last_seen = None
        self.plan = None  # room_plan.RoomPlanLink when the E32 credentials are stored
        # Where the E32's telemetry arrives (``<prefix>/v1/``): its ha/heating_input listens there too (P22).
        self.base = None
        self.input_watch = None  # HeatingInputWatch: does the E32 accept what Home Assistant sends?
        # The retained parts the status is assembled from.
        self.heating = None
        self.heating_received = None  # when fw/state/heating last arrived (its ha.input_age_s counts from then)
        self.room_states = {}
        self.ble_states = {}
        self.trv_states = {}
        self.config = None
        self.entity_parts = {}
        self.entities = None  # the last complete entity list
        self.shadow = None
        self.readiness = None
        self.online = None  # fw/availability: None until known
        self.heartbeat = None
        self.boots = 0  # E32 restarts seen as a falling heartbeat uptime (DhwCarry)
        self._dhw_carry = None
        self.heartbeat_received = None
        self.started = clock()
        self._listeners = []
        self._trackers = []  # each track_entities' forget_rooms(room_ids)
        self._failures_logged = {}  # listener: clock time its last failure was logged with a traceback
        self.closed = False  # the entry is unloading: no new entities (close)

    @callback
    def close(self):
        """The entry starts unloading: from now on no tracker adds an entity (track_entities).

        Its platforms are removed before its MQTT subscriptions end, and an entity added in
        between (the first E32 telemetry often arrives then) would outlive its platform: the next
        setup's entity with the same unique ID was refused ("does not generate unique IDs").
        """
        self.closed = True

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

    def dhw_today(self):
        """Today's hot-water counts carried over E32 restarts (DhwCarry), or None without them."""
        dhw = self.dhw
        if dhw is None:
            return None
        if self._dhw_carry is None:
            self._dhw_carry = DhwCarry(clock=self.clock)
        return self._dhw_carry.apply(dhw["today"], self.boots)

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
            self._failures_logged.pop(listener, None)
        return remove

    @callback
    def notify(self):
        """Tell every listener; one failing listener (an entity, a forwarder) never stops the others.

        A listener that fails on every E32 message logs its traceback at most once a minute
        (LISTENER_LOG_SECONDS, R4-10), the failures in between at debug level.
        """
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001
                now, logged = self.clock(), self._failures_logged.get(listener)
                if logged is None or not 0 <= now - logged < LISTENER_LOG_SECONDS:
                    self._failures_logged[listener] = now
                    _LOGGER.exception("OpenThermostat: an E32 telemetry listener failed")
                else:
                    _LOGGER.debug("OpenThermostat: an E32 telemetry listener failed again", exc_info=True)

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
        self.valves = status_valves(status)
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
        status = {key: value for key, value in heating.items() if key not in ("rooms", "ble_sensors", "ha_entities", "shadow", "trv")}
        status["ha_entities"] = list(self.entities or [])
        status["rooms"] = [self.room_states[i] for i in config["rooms"] if i in self.room_states]
        status["ble_sensors"] = [self.ble_states[i] for i in config["ble"] if i in self.ble_states]
        trv = heating.get("trv")
        if type(trv) is dict and _ids(config.get("trv"), ROOM_ID, 8):
            status["trv"] = {**trv, "rooms": [self.trv_states[i] for i in config["trv"] if i in self.trv_states]}
        if self.shadow is not None:
            status["shadow"] = {key: value for key, value in self.shadow.items() if key != "schema"}
        if self.readiness is not None:
            status["readiness"] = {key: value for key, value in self.readiness.items() if key != "schema"}
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
            previous = self.heartbeat
            if previous is not None and beat["uptime_s"] < previous.get("uptime_s", 0):
                self.boots += 1  # the E32 restarted (DhwCarry)
            self.heartbeat, self.heartbeat_received = beat, self.clock()
            self.online = True if self.online is None else self.online
            self.last_seen = self.heartbeat_received
            if self.insight_doc is not None:
                self._insight_beats += 1
                if self._insight_beats > INSIGHT_MISSED_HEARTBEATS:
                    # A live E32 that sends no insight (older firmware): a retained one is not current.
                    self.insight_doc, self.insight_gone, self.insight_live = None, True, False
                    self.summary = self._merged_summary()
        elif suffix == HEATING_TOPIC:
            self.heating = None if empty else decode_document(payload)
            self.heating_received = self.clock() if self.heating is not None else None
        elif suffix == PLAN_TOPIC:
            plan = decode_plan(payload)
            if plan is None and not empty:
                return  # a malformed plan never drops the rooms
            self.config = plan
            if plan is not None:
                valves = tuple(plan["trv"]) if _ids(plan.get("trv"), ROOM_ID, 8) else ()
                for key, store in ((tuple(plan["rooms"]), self.room_states), (tuple(plan["ble"]), self.ble_states),
                                   (valves, self.trv_states)):
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
        elif suffix.startswith(TRV_TOPIC):
            key = suffix[len(TRV_TOPIC):]
            value = None if empty else decode_trv(payload, key)
            if value is None:
                self.trv_states.pop(key, None)
            else:
                self.trv_states[key] = value
        elif suffix.startswith(LEARNED_TOPIC):
            room_id = suffix[len(LEARNED_TOPIC):]
            if empty:
                self.learned_messages.pop(room_id, None)
            else:
                value = decode_learned(room_id, payload)
                if value is None:
                    return
                self.learned_messages[room_id] = (self.clock(), *self._keep_free_heat(room_id, value))
        elif suffix in (SUMMARY_TOPIC, FLOW_TOPIC, TUNING_TOPIC, SCOREBOARD_TOPIC, INSIGHT_TOPIC):
            if suffix == SUMMARY_TOPIC:
                self.summary_doc = None if empty else decode_summary(payload)
            elif suffix == FLOW_TOPIC:
                flow = None if empty else decode_document(payload)
                self.flow_doc = ({k: flow[k] for k in FLOW_KEYS if type(flow.get(k)) is dict}
                                 if flow is not None else None)
            elif suffix == TUNING_TOPIC:
                tuning = None if empty else decode_document(payload)
                self.tuning_doc = tuning["tuning"] if tuning is not None and type(tuning.get("tuning")) is dict else None
            elif suffix == SCOREBOARD_TOPIC:
                board = None if empty else decode_document(payload)
                self.scoreboard_doc = (board["scoreboard"] if board is not None and type(board.get("scoreboard")) is dict
                                       else None)
            else:
                self.insight_doc = None if empty else decode_insight(payload)
                self.insight_gone, self._insight_beats = self.insight_doc is None, 0
                self.insight_live = self.insight_doc is not None and (self.insight_live or not retained)
            summary = self.summary = self._merged_summary()
            self.summary_received = self.clock() if summary is not None else None
        elif suffix == SHADOW_TOPIC:
            self.shadow = None if empty else decode_document(payload)
        elif suffix == READINESS_TOPIC:
            self.readiness = None if empty else decode_document(payload)
        else:
            return
        if not retained and suffix != AVAILABILITY_TOPIC:
            self.last_seen = self.clock()
        self.refresh()

    def _merged_summary(self):
        """fw/telemetry/summary with its parts (flow, tuning, scoreboard, insight); None without the summary itself."""
        summary = self.summary_doc
        if summary is not None and self.flow_doc:
            summary = {**summary, **self.flow_doc}
        if summary is not None and self.tuning_doc is not None:
            summary = {**summary, "tuning": self.tuning_doc}
        if summary is not None and self.scoreboard_doc is not None:
            summary = {**summary, "scoreboard": self.scoreboard_doc}  # the topic wins over an older summary's own
        if summary is not None and self.insight_doc is not None:
            summary = {**summary, "insight": self.insight_doc}
        return summary

    @callback
    def update_learned(self, room_id, value):
        """One room's learned message (decode_learned); None (invalid) is ignored."""
        if value is None:
            return
        self.learned_messages[room_id] = (self.clock(), *self._keep_free_heat(room_id, value))
        self._merge_learned()
        self.notify()

    def _keep_free_heat(self, room_id, value):
        """(learned room, plan) with the room's previous ``free_heat`` when this message has no key at all.

        The E32 (rc.5, HeatingTelemetry) leaves ``free_heat`` out only when the message would exceed its budget, so
        an absent key keeps what the room had; ``null`` still means that no window was judged yet.
        """
        room, plan = value
        previous = self.learned_messages.get(room_id)
        if "free_heat" not in room and previous is not None and "free_heat" in previous[1]:
            room = {**room, "free_heat": previous[1]["free_heat"]}
        return room, plan

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


# Every ha/heating_input message of an entry goes out through its HeatingInputLink (P22). At most
# MAX_PENDING_PUBLISHES wait for the broker at once (R4-07), each at most PUBLISH_TIMEOUT_S (Home Assistant's
# own MQTT publish stops waiting for the broker after 10 s); more are dropped while the broker does not
# answer: every value is sent again on its next change and every five minutes.
MAX_PENDING_PUBLISHES = 50
PUBLISH_TIMEOUT_S = 30
INPUT_LINK = "heating_input_link"  # hass.data[DOMAIN][entry id][INPUT_LINK]: the entry's HeatingInputLink
# The E32 uses a Home Assistant value for 15 minutes (RoomEngine::setpointMaxAgeMs), then its own fallback.
INPUT_LOST_S = 900
INPUT_CHECK = timedelta(seconds=60)
INPUT_ISSUE = "heating_input_lost"
# rc.7 (R2-11): the repair names one likely cause in the Home Assistant language (the placeholders of a repair are
# not translated): the E32 refused the values (HeatingInput.h's reasons), or Home Assistant's own sending failed (the
# kind of failure, HeatingInputLink.error_kind), or nothing ("" leaves the sentence out).
INPUT_CAUSES = {
    "en": {"refused": "The E32 refused them: {reason}.", "timeout": "The MQTT broker does not take them in time.",
           "unreachable": "Home Assistant cannot reach the MQTT broker.",
           "waiting": "Too many messages are waiting for the MQTT broker.",
           "too_large": "the message was too long", "invalid_json": "it could not read the message",
           "no_entity": "the message named no Home Assistant entity",
           "unknown_kind": "it does not know that kind of value; update the E32",
           "invalid_value": "the value was outside what it accepts", "unknown_room": "it does not know that room"},
    "nl": {"refused": "De E32 weigerde ze: {reason}.", "timeout": "De MQTT-broker neemt ze niet op tijd aan.",
           "unreachable": "Home Assistant bereikt de MQTT-broker niet.",
           "waiting": "Er wachten te veel berichten op de MQTT-broker.",
           "too_large": "het bericht was te lang", "invalid_json": "hij kon het bericht niet lezen",
           "no_entity": "het bericht noemde geen Home Assistant-entiteit",
           "unknown_kind": "hij kent dat soort waarde niet; werk de E32 bij",
           "invalid_value": "de waarde lag buiten wat hij aanneemt", "unknown_room": "hij kent die ruimte niet"},
    "pl": {"refused": "E32 je odrzucił: {reason}.", "timeout": "Broker MQTT nie przyjmuje ich na czas.",
           "unreachable": "Home Assistant nie może połączyć się z brokerem MQTT.",
           "waiting": "Zbyt wiele wiadomości czeka na broker MQTT.",
           "too_large": "wiadomość była za długa", "invalid_json": "nie mógł odczytać wiadomości",
           "no_entity": "wiadomość nie wskazywała encji Home Assistant",
           "unknown_kind": "nie zna tego rodzaju wartości; zaktualizuj E32",
           "invalid_value": "wartość była poza dopuszczalnym zakresem", "unknown_room": "nie zna tego pomieszczenia"}}
REFUSAL_REASONS = ("too_large", "invalid_json", "no_entity", "unknown_kind", "invalid_value", "unknown_room")


def _iso_time(moment):
    return moment.isoformat() if moment is not None else None


def _iso_minute(moment):
    """To the minute: an attribute that changes when something happens, not with every E32 message."""
    return moment.replace(second=0, microsecond=0).isoformat() if moment is not None else None


class HeatingInputLink:
    """The route of one entry's room, energy and comfort values to the E32: ``<base>ha/heating_input``.

    P22 (4 Nov 2026): the comfort refresh ran in a worker thread, where ``hass.async_create_task`` raises,
    after the module-wide sender of 1.0.0rc5 had counted the message as pending; fifty such refreshes (four
    hours) kept that count full and every later value was dropped, until Home Assistant restarted. Now:

    - ``send`` never raises and never blocks; from a worker thread it hands the message to the event loop;
    - the pending sends are the live tasks themselves (a send that never started holds no place), each
      with its own deadline, and unloading the entry cancels them: a reload always starts afresh;
    - the topic is resolved at each send: the E32's own base (``hub.base``, where its telemetry arrives),
      else the entry's (``topic_base``); a difference is logged once;
    - what happened is kept for HeatingInputWatch, the diagnostics and the ``ha_input`` attribute.
    """

    def __init__(self, hass, entry, hub=None, clock=time.monotonic):
        self.hass, self.entry, self.hub, self.clock = hass, entry, hub, clock
        self._tasks = set()
        self.attempted = None  # monotonic: the last watched value handed to MQTT (or dropped)
        self.sent = None       # monotonic: the last value the broker took
        self.sent_at = None    # the same as a UTC datetime
        self.error = None      # the last failure in words, kept after a send that works (see error_at)
        self.error_at = None
        self.error_kind = None  # timeout, unreachable or waiting (the repair's cause, INPUT_CAUSES)
        self.failing = False   # the newest send failed: one warning per failure episode
        self.failures = 0
        self.dropped = 0       # values dropped while MAX_PENDING_PUBLISHES still waited
        self._saturated = self._thread_warned = self._topic_warned = self._closed = False

    @property
    def pending(self):
        return len(self._tasks)

    @property
    def topic(self):
        own = topic_base(self.hass, self.entry)
        e32 = getattr(self.hub, "base", None)
        if e32 and e32 != own and not self._topic_warned:
            self._topic_warned = True
            _LOGGER.warning("OpenThermostat: the E32 reports on %s, this entry's topic is %s; room values go "
                            "where the E32 reports", e32, own)
        return (e32 or own) + "ha/heating_input"

    def send(self, payload, watched=True):
        """Send one message in the background: never raises, never blocks, also from a worker thread.

        watched: a value the E32 counts in its ``ha.input_age_s`` (rooms and energy), so HeatingInputWatch may
        expect it to arrive; contacts and presence pass False (E32 rc.4 does not count them).
        """
        hass = self.hass
        if threading.get_ident() != hass.loop_thread_id:
            if not self._thread_warned:
                self._thread_warned = True
                _LOGGER.warning("OpenThermostat: a value for the E32 came from a worker thread; "
                                "it is sent from the event loop instead")
            try:
                hass.loop.call_soon_threadsafe(self.send, payload, watched)
            except RuntimeError:  # the event loop has stopped: Home Assistant shuts down
                pass
            return
        if self._closed:
            return
        if watched:
            self.attempted = self.clock()
        if len(self._tasks) >= MAX_PENDING_PUBLISHES:
            self.dropped += 1
            self._failed(f"{len(self._tasks)} messages still wait for the MQTT broker", dropped=True, kind="waiting")
            return
        task = hass.async_create_task(self._publish(self.topic, payload), "OpenThermostat heating_input")
        if not task.done():
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _publish(self, topic, payload):
        try:
            async with asyncio.timeout(PUBLISH_TIMEOUT_S):
                await mqtt.async_publish(self.hass, topic, payload, 0, False)
        except TimeoutError:
            self._failed(f"the MQTT broker did not take it within {PUBLISH_TIMEOUT_S} s", kind="timeout")
        except Exception as err:  # noqa: BLE001 - a broker failure never reaches the forwarders
            self._failed(str(err) or type(err).__name__, kind="unreachable")
        else:
            self.sent, self.sent_at = self.clock(), dt_util.utcnow()
            if self.failing or self._saturated:
                _LOGGER.info("OpenThermostat sends room values to the E32 again")
            self.failing = self._saturated = False

    def _failed(self, error, dropped=False, kind="unreachable"):
        """One warning per episode (a broker that is down, or one that keeps every place busy), then debug."""
        self.error, self.error_at, self.error_kind = error, dt_util.utcnow(), kind
        if dropped:
            if not self._saturated:
                self._saturated = True
                _LOGGER.warning("OpenThermostat: %s; newer room values for the E32 are dropped until it answers",
                                error)
            return
        self.failures += 1
        if self.failing:
            _LOGGER.debug("OpenThermostat: still no MQTT broker for the E32 (%s)", error)
        else:
            self.failing = True
            _LOGGER.warning("OpenThermostat could not send room values to the E32 over MQTT (%s); "
                            "it sends them again once the broker answers", error)

    @callback
    def restart(self):
        """Start afresh (HeatingInputWatch): what still waits is cancelled; the warnings may come again."""
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        self.failing = self._saturated = False

    @callback
    def close(self):
        """The entry unloads: nothing more goes out, and what still waits is cancelled."""
        self._closed = True
        self.restart()

    def diagnostics(self):
        now = self.clock()
        return {"pending": self.pending, "dropped": self.dropped, "failures": self.failures, "failing": self.failing,
                "last_sent": _iso_time(self.sent_at),
                "last_sent_age_s": round(now - self.sent, 1) if self.sent is not None else None,
                "last_attempt_age_s": round(now - self.attempted, 1) if self.attempted is not None else None,
                "last_error": self.error, "last_error_at": _iso_time(self.error_at)}


def heating_input_link(hass, entry, hub=None):
    """The entry's HeatingInputLink, made on first use; unloading the entry closes it (a reload starts afresh)."""
    state = hass.data[DOMAIN][entry.entry_id]
    link = state.get(INPUT_LINK)
    if link is None:
        link = state[INPUT_LINK] = HeatingInputLink(hass, entry, hub if hub is not None else state.get("heating_hub"))
        entry.async_on_unload(link.close)
    elif link.hub is None and hub is not None:
        link.hub = hub
    return link


def e32_input_age(hub, now):
    """Seconds since the E32 last accepted an ha/heating_input message, as far as its telemetry tells.

    Its ``ha.input_age_s`` counts to when that status was sent, so the time since it arrived is added;
    ``null`` means none since the E32 started: then its uptime. None while the E32 is silent, or on
    firmware without the ``ha`` block.
    """
    ha = hub.status.get("ha") if hub.fresh else None
    if type(ha) is not dict or "input_age_s" not in ha:
        return None
    age = ha["input_age_s"]
    if age is None:
        beat, at = hub.heartbeat, hub.heartbeat_received
        uptime = beat.get("uptime_s") if type(beat) is dict else None
        return uptime + max(0.0, now - at) if type(uptime) is int and at is not None else None
    return _e32_age(hub, age, now)


def _e32_age(hub, age, now):
    """An age from the E32's heating status (seconds when it was sent) as of now, or None when it is no age."""
    if type(age) not in (int, float) or not math.isfinite(age) or age < 0:
        return None
    at = hub.heating_received if hub.heating_received is not None else hub.received
    return age + max(0.0, now - at) if at is not None else float(age)


class HeatingInputWatch:
    """Does the E32 accept what Home Assistant sends? The end-to-end check of ha/heating_input (P22).

    The E32 reports how long ago it accepted a message of any kind (``ha.input_age_s``). Home Assistant
    sends each value on every change and every five minutes, so while both sides work that age stays under
    five minutes. Once it reaches INPUT_LOST_S (the E32's own fallback time) while Home Assistant has values
    to send, they do not arrive: one warning, the link starts afresh and everything goes out again at once
    (``resend``; again every INPUT_LOST_S while it lasts), and a repair says so, with the advice to restart
    Home Assistant if it stays. It clears itself once the E32 accepts again. Nothing is judged within
    INPUT_LOST_S of the start: the E32 may still report an age from before Home Assistant (re)started.
    """

    def __init__(self, hass, entry, hub, link, resend, clock=time.monotonic, wall=None):
        self.hass, self.entry, self.hub, self.link, self.resend, self.clock = hass, entry, hub, link, resend, clock
        self.wall = wall if wall is not None else dt_util.utcnow
        self.started = clock()
        self.lost_since = None  # monotonic: when the check found the values not arriving
        self._resent = None

    @property
    def issue_id(self):
        return f"{INPUT_ISSUE}_{self.entry.entry_id}"

    def _expected(self, now):
        """Home Assistant sends now (the last five minutes), or has a value for an entity the E32 reads."""
        if self.link.attempted is not None and now - self.link.attempted <= REFRESH_SECONDS + 60:
            return True
        unit, wall = self.hass.config.units.temperature_unit, dt_util.utcnow()
        states = [self.hass.states.get(entity_id) for entity_id in (self.hub.status or {}).get("ha_entities") or []]
        # A frozen source is not sent (silent_source): nothing for the E32 to accept, so no repair for it.
        return any(input_payload(state, unit) is not None and not silent_source(state, wall) for state in states)

    def state(self, age):
        if self.lost_since is not None:
            return "not_received"
        if age is None:
            return "unknown"
        return "ok" if age < INPUT_LOST_S else "waiting"

    @callback
    def check(self, _now=None):
        now = self.clock()
        age = e32_input_age(self.hub, now)
        if age is None:
            # The E32 is silent, or its firmware does not say: its own entities show that. A repair raised before
            # goes (rc.7, R2-11): "E32 not reporting" takes over, and the check judges afresh once it is heard.
            if self.lost_since is not None and not self.hub.fresh:
                self.lost_since = self._resent = None
                self._issue(None)
            return
        if age < INPUT_LOST_S:
            if self.lost_since is not None:
                self.lost_since = self._resent = None
                _LOGGER.info("OpenThermostat: the E32 accepts room values from Home Assistant again")
                self._issue(None)
            return
        if now - self.started < INPUT_LOST_S or not self._expected(now):
            return
        if self.lost_since is None:
            self.lost_since = now
            ha = self.hub.status.get("ha")
            _LOGGER.warning(
                "OpenThermostat: the E32 has accepted no room values from Home Assistant for %d min (Home Assistant "
                "last sent one at %s; last send error: %s; E32 MQTT connected: %s; E32 last rejected: %s); "
                "sending everything again. If this stays, restart Home Assistant.",
                age // 60, _iso_time(self.link.sent_at) or "never", self.link.error or "none",
                ha.get("broker_connected"), ha.get("last_rejected") or "nothing")
        elif self._resent is not None and now - self._resent < INPUT_LOST_S:
            return
        self._resent = now
        self.link.restart()
        self.resend()
        self._issue(age)

    def cause(self, age):
        """The likeliest cause in words (INPUT_CAUSES, the Home Assistant language), or "": a value the E32 refused
        after it last took one, else Home Assistant's own newest send failing."""
        from .learned_overview import language
        words = INPUT_CAUSES.get(language(self.hass), INPUT_CAUSES["en"])
        now = self.clock()
        ha = self.hub.status.get("ha") if self.hub.fresh else None
        rejected = ha.get("last_rejected") if type(ha) is dict else None
        refused = _e32_age(self.hub, rejected.get("age_s"), now) if type(rejected) is dict else None
        reason = rejected.get("reason") if type(rejected) is dict else None
        if refused is not None and type(reason) is str and (age is None or refused <= age):
            return words["refused"].format(reason=words.get(reason) if reason in REFUSAL_REASONS else reason)
        link = self.link
        if link.error_at is not None and (link.sent_at is None or link.error_at > link.sent_at):
            return words.get(link.error_kind) or words["unreachable"]
        return ""

    def _issue(self, age):
        from homeassistant.helpers import issue_registry as ir
        try:
            if age is None:
                ir.async_delete_issue(self.hass, DOMAIN, self.issue_id)
                return
            # Since when, as a local time (with the day when not today), not a count of minutes that stands still
            # between the re-creations.
            since = dt_util.as_local(self.wall() - timedelta(seconds=age))
            from .learned_overview import TEXT as LEARNED, language
            months = LEARNED[language(self.hass)]["months"].split()
            # Another day as the dashboard writes it ("4 Nov 22:15"); never "04-11", which also reads as 11 April.
            text = (since.strftime("%H:%M") if since.date() == dt_util.now().date()
                    else f"{since.day} {months[since.month - 1]} {since:%H:%M}")
            ir.async_create_issue(
                self.hass, DOMAIN, self.issue_id, is_fixable=False, is_persistent=False,
                severity=ir.IssueSeverity.WARNING, translation_key=INPUT_ISSUE,
                translation_placeholders={"since": text, "cause": self.cause(age)})
        except Exception:  # noqa: BLE001 - a repair that cannot be shown never stops the check or the sending
            _LOGGER.debug("OpenThermostat: the heating input repair could not be updated", exc_info=True)

    @callback
    def stop(self):
        """The entry unloads: the repair goes with it (the next run judges afresh)."""
        self._issue(None)

    def attributes(self):
        """The ``ha_input`` attribute: does the E32 get Home Assistant's values, when it last took one (and refused
        one, and why), the last send and error. Times to the minute (the diagnostics have the exact ages)."""
        now, wall = self.clock(), self.wall()
        age = e32_input_age(self.hub, now)
        ha = self.hub.status.get("ha") if self.hub.fresh else None
        rejected = ha.get("last_rejected") if type(ha) is dict else None
        refused = _e32_age(self.hub, rejected.get("age_s"), now) if type(rejected) is dict else None
        return {"state": self.state(age),
                "e32_last_input": _iso_minute(wall - timedelta(seconds=age)) if age is not None else None,
                "e32_last_rejected": {"reason": rejected.get("reason"), "at": _iso_minute(wall - timedelta(seconds=refused))}
                if refused is not None and type(rejected.get("reason")) is str else None,
                "last_sent": _iso_minute(self.link.sent_at), "last_error": self.link.error,
                "last_error_at": _iso_minute(self.link.error_at), "last_error_kind": self.link.error_kind,
                "dropped": self.link.dropped}

    def diagnostics(self):
        now = self.clock()
        age = e32_input_age(self.hub, now)
        ha = self.hub.status.get("ha") if self.hub.fresh else None
        return {**self.link.diagnostics(), "state": self.state(age),
                "e32_input_age_s": round(age, 1) if age is not None else None,
                "e32_ha": ha if type(ha) is dict else None,
                "not_received_for_s": round(now - self.lost_since, 1) if self.lost_since is not None else None}


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
        if getattr(hub, "closed", False):
            return  # the entry is unloading (HeatingHub.close): an entity added now would outlive its platform
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
        # No suggested area in the device info: room_groups suggests the existing area
        # named like the room, and async_prepare_to_add_to_hass keeps that area's name
        # out of the new entity IDs.
        device = _own_device(room_device_identifier(hub.prefix, self.room_id), room)
        self._attach(hub, f"e32_room_{self.room_id}_{key}", device)
        self._attr_translation_key = f"room_{key}"

    async def async_prepare_to_add_to_hass(self):
        """A new entity's ID says the room once.

        Home Assistant 2026.10 puts the device's area in front of a new entity ID.
        room_groups gives a new room device the existing area named like the room
        (a Dutch onboarding creates Woonkamer, Keuken, Slaapkamer), so the ID would
        say it twice: sensor.woonkamer_woonkamer_reden, climate.slaapkamer_slaapkamer.
        While the device has no area or one with its own name, the entity suggests
        the room name and its own name instead (sensor.woonkamer_reden), which is
        also the ID it gets without an area. Home Assistant's own ID otherwise: an
        entity already registered keeps its ID (the suggestion is not used then), a
        room in an area of another name gets the area in front, and so does every
        room when the user set an entity ID format of their own.
        """
        await super().async_prepare_to_add_to_hass()
        try:
            object_id = self._room_object_id()
        except Exception:  # an entity ID suggestion only: never stop the entity from being added
            _LOGGER.debug("No entity ID suggested for %s", self.unique_id, exc_info=True)
            return
        if object_id:
            self.entity_id = f"{self.platform.domain}.{object_id}"

    def _room_object_id(self):
        from homeassistant.helpers import area_registry as ar, entity_registry as er
        from homeassistant.util import slugify
        platform = self.platform
        entry = getattr(platform, "config_entry", None)
        entities = er.async_get(self.hass)
        if (entry is None or self.entity_id is not None
                or entities.async_get_entity_id(platform.domain, platform.platform_name, self.unique_id)
                or getattr(getattr(entities, "settings", None), "entity_id_parts", None) is not None):
            return None
        info = self.device_info or {}
        device = dr.async_get(self.hass).async_get_device_by_identifier(
            next(iter(info.get("identifiers") or ())), entry.entry_id)
        device_name = (device.name_by_user or device.name) if device is not None else info.get("name")
        if not device_name:
            return None
        if device is not None and device.area_id is not None:
            area = ar.async_get(self.hass).async_get_area(device.area_id)
            if area is not None and slugify(area.name) != slugify(device_name):
                return None  # the user's own area: Home Assistant's area + room + name
        object_id = slugify(" ".join(part for part in (device_name, self.suggested_object_id) if part))
        return object_id or None

    def _named_item(self):
        return self.room

    @property
    def room(self):
        return self.hub.rooms.get(self.room_id)

    @property
    def available(self):
        return self.hub.fresh and self.room is not None


class HeatRequestSensor(HubEntity, SensorEntity):
    """The E32's computed boiler flow request, "Requested water temperature" (0 when it does not ask for heat).

    0 stays the "no request" state: the house and boiler-now cards read it so (frontend). Diagnostic: the
    cards and the Boiler view show it, the device page keeps it out of the main list.
    """

    _attr_translation_key = "heat_request"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Live only, not in the history: whether the E32 gets Home Assistant's values (HeatingInputWatch.attributes),
    # every room's state (the room entities keep their own history) and the plan revision.
    _unrecorded_attributes = frozenset({"ha_input", "rooms", "revision"})

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
        active = status.get("active") if type(status.get("active")) is dict else {}
        watch = getattr(self.hub, "input_watch", None)
        # control: the active-control state (E32 1.0), e.g. awaiting_confirmation before the takeover.
        return {"mode": status["mode"], "reason": status["request"]["reason"], "rooms": status["rooms"],
                "revision": self.hub.revision, "control": active.get("state") if type(active.get("state")) is str else None,
                "ha_input": watch.attributes() if watch is not None else None}


class RoomTemperatureSensor(RoomEntity, SensorEntity):
    """The room's temperature, or its target (``setpoint``: diagnostic, the thermostat shows it already)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1  # the E32 sends hundredths; the recorder keeps them

    def __init__(self, hub, room, key="temperature", low=-40, high=85):
        self._key, self._low, self._high = key, low, high
        self._attach_room(hub, room, key)
        if key == "setpoint":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        room = self.room
        return number(room.get(self._key), self._low, self._high) if room and self.hub.fresh else None

    @property
    def extra_state_attributes(self):
        room = self.room
        return {"room_id": self.room_id, "source": room.get("source")} if room and self.hub.fresh else None


class RoomStatusSensor(RoomEntity, SensorEntity):
    """How the E32 runs the room: ok, fallback, stale, lost, inactive or paused by a window, and from which source."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ROOM_STATUSES
    _attr_entity_category = EntityCategory.DIAGNOSTIC  # Reason on the Overview says it in words
    _unrecorded_attributes = frozenset({"revision"})  # changes with every plan save

    def __init__(self, hub, room):
        self._attach_room(hub, room, "status")

    @property
    def native_value(self):
        room = self.room
        return room_status(room) if room and self.hub.fresh else None

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
                "window": room["comfort"].get("window") if type(room.get("comfort")) is dict else None,
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
# Shown decimals only ("57 %", not "56,96 %"); the recorded value keeps its precision.
BLE_PRECISION = {"temperature": 1, "humidity": 0, "battery": 0}


class BleSensor(HubEntity, SensorEntity):
    """One reading of a Bluetooth sensor paired on the E32."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub, sensor, metric):
        self.sensor_id, self.metric = sensor["id"], metric
        device = _own_device(ble_device_identifier(hub.prefix, self.sensor_id), sensor)
        device["name"] = ble_device_name(sensor, hub.rooms) or label(sensor)  # a new device's first name
        self._attach(hub, f"e32_ble_{self.sensor_id}_{metric}", device)
        self._attr_device_class, self._attr_native_unit_of_measurement, self._low, self._high = BLE_METRICS[metric]
        self._attr_suggested_display_precision = BLE_PRECISION[metric]
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


BOILER_ACTIVITIES = ("idle", "heating", "tapping", "keep_warm", "charging", "hot_water")


class BoilerActivitySensor(HubEntity, SensorEntity):
    """What the boiler does now, as the E32 sees it on the bus (``burner.activity``, E32 beta.23).

    An enum, so Home Assistant's history draws a coloured timeline: idle, heating, tapping,
    keeping warm, charging a cylinder, or hot water the E32 cannot sort. The E32 decides with the
    most direct signal its boiler reports (DHW flow, a cylinder's charging, else the DHW
    temperature); a tap shows as keeping warm until its fall is clear, usually within half a minute.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(BOILER_ACTIVITIES)
    _attr_translation_key = "boiler_activity"

    def __init__(self, hub):
        self._attach(hub, "hub_boiler_activity")

    @property
    def available(self):
        return self.hub.fresh

    @property
    def native_value(self):
        burner = burner_status(self.hub.status)
        value = burner.get("activity") if burner else None
        return value if value in BOILER_ACTIVITIES else None


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
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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
        result = {"room_id": self.room_id, "emitter": _text(learned, "emitter"),
                  "segments": _count(learned.get("segments")), "periods": _count(learned.get("periods")),
                  "heating_periods": _count(whole.get("heating_periods")), "learner": _text(whole, "status"),
                  "loss_per_h": number(learned.get("loss_per_h"), 0, 1),
                  "capacity_kwh_per_k": number(learned.get("capacity_kwh_per_k"), 0, 100),
                  "applied": self._applied()}
        if "readiness_timing" in learned:  # E32 rc.4: the warm-up time, learned before the coolest water
            result["timing"] = learned["readiness_timing"] if learned["readiness_timing"] in LEARNING_STATES else None
        return result


class RoomFlowAdviceSensor(LearnedRoomEntity, SensorEntity):
    """The lowest flow that warms this room 1 °C in an acceptable time (unknown until learned)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset({"night_strategies"})

    def __init__(self, hub, room):
        self._attach_room(hub, room, "heating_start")

    @property
    def warmup(self):
        return self.hub.warmup.get(self.room_id) if self.hub.fresh else None

    @property
    def available(self):
        return self.hub.fresh and self.room is not None and self.warmup is not None

    def _free_heat_min(self):
        """The minutes the free heat moves this start later (FreeHeat::shorten in FlowPolicy; the telemetry's
        predicted_start_utc is the start without it), 0 without (learned_overview.free_heat_later)."""
        from .learned_overview import free_heat_later
        return free_heat_later(self.hub.learned.get(self.room_id), self.warmup)

    @property
    def native_value(self):
        start = _dict(self.warmup, "optimum_start")
        if start.get("reason") != "planned":
            return None
        if (exact := _utc(start.get("predicted_start_utc"))) is not None:
            # The start the E32 really uses: later by what the free heat gives (rc7, sentences review R1-2).
            return exact + timedelta(minutes=self._free_heat_min())
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
        if "estimate" in start:  # E32 rc.4: a start from the standard warm-up time (it learns from every morning)
            result["estimate"] = _flag(start, "estimate")
        if (later := self._free_heat_min()) and (begin := self.native_value) is not None:
            # E32 rc.5: the free heat moves the start later (the state is that later start); the E32's start_now is for
            # the start without it, so it heats now only once the later start has come.
            result["free_heat_min"] = later
            # The E32's reachable is for the start without the free heat: once that earlier start passed it is always
            # false (WarmupPlanner::lead, "too late already"), which FreeHeat::shorten says is no reason for concern.
            result["reachable"] = None
            if result["start_now"] is True and begin > datetime.now(timezone.utc):
                result["start_now"] = False
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
DHW_EPISODE_KINDS = ("tapping", "keep_warm", "charging", "unknown")


class DhwCarry:
    """Today's hot-water counts across E32 restarts.

    The E32 counts its episodes per day in memory, so an update or any other
    restart starts them at 0 again (31 Oct 2026: two updates left the owner's
    "keeping warm today" at a few rounds). A count that goes down while the E32
    restarted (its heartbeat uptime fell within RESTART_WINDOW_S of the drop)
    keeps what it had reached and adds from there; any other drop is the E32's
    new day. The two may arrive in either order. Home Assistant keeps this in
    memory only; after a Home Assistant restart the E32's own counts carry on.
    """

    RESTART_WINDOW_S = 120

    def __init__(self, today=None, clock=time.monotonic):
        self._today = today or (lambda: __import__("datetime").date.today())
        self.clock = clock
        self.day, self.last, self.base, self.dropped, self.dropped_at = None, {}, {}, {}, None
        self.boot, self.restart_seen = None, None  # restart_seen: when a restart came before its drop

    def _recent(self, since, now):
        return since is not None and now - since <= self.RESTART_WINDOW_S

    def apply(self, today, boot=None):
        """A copy of the E32's ``today`` with every count and duration carried over its restarts.

        boot: a number that changes when the E32 restarts (HeatingHub.boots)."""
        day, now = self._today(), self.clock()
        if day != self.day:
            self.day, self.last, self.base, self.dropped, self.restart_seen = day, {}, {}, {}, None
        if self.dropped and not self._recent(self.dropped_at, now):
            self.dropped = {}  # no restart followed the drop: it was the E32's new day
        if not self._recent(self.restart_seen, now):
            self.restart_seen = None
        if boot is not None and self.boot is not None and boot != self.boot:
            if self.dropped:
                for key, value in self.dropped.items():
                    self.base[key] = self.base.get(key, 0) + value
                self.dropped = {}
            else:
                self.restart_seen = now
        if boot is not None:
            self.boot = boot
        result = dict(today)
        carried = False
        keys = [(kind, field) for kind in DHW_EPISODE_KINDS for field in ("count", "s")] + [(None, "burner_s")]
        for kind, field in keys:
            source = today.get(kind) if kind else today
            value = _count(source.get(field)) if type(source) is dict else None
            if value is None:
                continue
            key = f"{kind}.{field}" if kind else field
            if key in self.last and value < self.last[key]:
                if self.restart_seen is not None:
                    self.base[key] = self.base.get(key, 0) + self.last[key]
                    carried = True
                else:
                    if not self.dropped:
                        self.dropped_at = now
                    self.dropped[key] = self.last[key]
            elif key in self.last and value > self.last[key]:
                self.dropped.pop(key, None)  # counting again after the drop: that was the E32's new day
            self.last[key] = value
            total = value + self.base.get(key, 0)
            if kind:
                result[kind] = {**(result[kind] if result.get(kind) is not source else source), field: total}
            else:
                result[field] = total
        if carried:
            self.restart_seen = None
        return result


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
        """The hub's hot-water summary with today's counts carried over E32 restarts."""
        dhw = self.hub.dhw if self.hub.fresh else None
        return None if dhw is None else {**dhw, "today": self.hub.dhw_today()}

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
        result = {"method": _text(dhw, "method"), "baseline": _text(dhw, "baseline"), "clock_known": _flag(dhw, "clock_known")}
        if self.key == "dhw_burner_time_today":
            return {**result, "tapping_minutes": _minutes(_count(_dict(today, "tapping").get("s"))),
                    "keep_warm_minutes": _minutes(_count(_dict(today, "keep_warm").get("s"))),
                    "last_7_days_minutes": _minutes(_count(week.get("burner_s")))}
        kind = DHW_KINDS[self.key]
        result.update(minutes=_minutes(_count(_dict(today, kind).get("s"))),
                      last_7_days=_count(_dict(week, kind).get("count")))
        if self.key == "dhw_taps_today":
            result.update(peak_flow_l_min=number(today.get("peak_flow_l_min"), 0, 60),
                          unknown_count=_count(_dict(today, "unknown").get("count")),
                          charging_count=_count(_dict(today, "charging").get("count")))
        return result


def wanted_sensors(hub):
    # Firmware that compares (E32 beta.18), and only once a thermostat to compare with shows up.
    # In active mode without one they are removed (native_entity_cleanup.note_heating_status); a
    # removed one is forgotten (track_entities) and comes again with a thermostat in a trial run.
    if shadow_has_thermostat(hub.status):
        for key in SHADOW_SENSORS:
            yield ("shadow", key), lambda key=key: ShadowSensor(hub, key)
    from .takeover_readiness import TakeoverReadinessSensor, readiness_status
    if readiness_status(hub.status) is not None:  # firmware that judges "ready to take over?" (1.0)
        yield ("readiness",), lambda: TakeoverReadinessSensor(hub)
    if burner_status(hub.status) is not None:  # firmware that counts burner starts
        yield ("burner",), lambda: BurnerStartsSensor(hub)
    if "activity" in (burner_status(hub.status) or {}):  # firmware that says what the boiler does (beta.23)
        yield ("activity",), lambda: BoilerActivitySensor(hub)
    if hub.dhw is not None:  # firmware that sorts the hot-water episodes
        for key in DHW_SENSORS:
            yield ("dhw", key), lambda key=key: DhwTodaySensor(hub, key)
    for room_id, room in hub.rooms.items():
        yield ("room", room_id, "temperature"), lambda room=room: RoomTemperatureSensor(hub, room)
        yield ("room", room_id, "setpoint"), lambda room=room: RoomTemperatureSensor(hub, room, "setpoint", 5, 30)
        yield ("room", room_id, "status"), lambda room=room: RoomStatusSensor(hub, room)
        # Why it heats or not, in words (room_overview.py, 1.1): the room status card reads it.
        from .room_overview import RoomReasonSensor
        yield ("room", room_id, "reason"), lambda room=room: RoomReasonSensor(hub, room)
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
    # Yesterday's scoreboard (E32 rc.4): each figure once the E32 reported a value for it.
    from .scoreboard import wanted_scoreboard
    yield from wanted_scoreboard(hub)


def wanted_demand(hub):
    if burner_status(hub.status) is not None:
        yield ("burner",), lambda: BurnerShortCyclingBinarySensor(hub)
    for room_id, room in hub.rooms.items():
        yield room_id, lambda room=room: RoomDemandBinarySensor(hub, room)


def removable_device(hass, entry, device):
    """Whether the user may delete this device: a room, Bluetooth sensor or EMS device the E32 no longer reports.

    Only while the telemetry is fresh, so a short outage never makes a live
    room removable. Every other device of the entry stays.
    """
    hub = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub")
    if hub is None or not hub.fresh:
        return False
    from .ems_devices import device_address, listed
    address = device_address(hub.prefix, device)
    if address is not None:
        present = listed(hass, entry, complete=True)  # never from the partial list of a starting E32
        return present is not None and address not in present
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
    hub.base = base  # the E32's telemetry arrives here, so its ha/heating_input listens here (HeatingInputLink)
    options = add_options(hass, entry, options)
    sensor = HeatRequestSensor(hub)
    async_add_entities([sensor], **options)
    entry.async_on_unload(track_entities(hub, async_add_entities, options, wanted_sensors))
    # The comparison sensors go once the E32 controls the boiler and hears no thermostat to compare
    # with for a while; wanted_sensors creates them again in a trial run with a thermostat on the bus.
    from .native_entity_cleanup import note_heating_status
    entry.async_on_unload(hub.add_listener(lambda: note_heating_status(hass, entry, hub.prefix, hub.status)))
    if is_product(entry):  # the tuning advice (advice only) on the product device
        from .heating_advice import async_setup_heating_advice
        try:
            await async_setup_heating_advice(hass, entry, async_add_entities, options, hub, connection)
        except Exception:  # noqa: BLE001 - the advice is optional; the rooms and forwarding are not
            _LOGGER.exception("OpenThermostat: setting up the heating advice and gas use failed; "
                              "the E32 rooms still load")
        # E32 rc.5: what the E32 knows, the boiler's response and yesterday's insights (notifications).
        from .insight import async_setup_insight
        try:
            await async_setup_insight(hass, entry, async_add_entities, options, hub)
        except Exception:  # noqa: BLE001 - information only; the rooms and forwarding are not
            _LOGGER.exception("OpenThermostat: setting up what the E32 knows failed; the E32 rooms still load")
    forwarded = []
    unsubscribe_states = None
    was_fresh = False
    # Room, energy and comfort values all leave through the entry's link (P22: per entry, never stuck).
    send = heating_input_link(hass, entry, hub).send

    def publish(entity_id, now=None):
        """Send one entity's values; ``now`` (the refresh): not a source that froze (silent_source)."""
        state = hass.states.get(entity_id)
        if now is not None and silent_source(state, now):
            return
        payload = input_payload(state, hass.config.units.temperature_unit)
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
        now = dt_util.utcnow()
        for entity_id in forwarded:
            publish(entity_id, now)
        energy.publish()

    boots = hub.boots

    @callback
    def follow():
        """After every hub change: track exactly the plan's entities; send all at once when new or back.

        Back: the E32 was offline or silent, or it restarted (its uptime went down, ``hub.boots``; a restart
        shorter than STALE_SECONDS never makes it silent). A restarted E32 has no room reading until Home
        Assistant sends one, so the rooms and the energy values go out at once, not at the next refresh. The
        comfort forwarder sends the contacts and presence itself when the E32 is back (hub_changed); after a
        quick restart it is told here.
        """
        nonlocal forwarded, unsubscribe_states, was_fresh, boots
        status = hub.status
        back = status is not None and not was_fresh
        was_fresh = status is not None
        if status is None:
            return
        restarted, boots = hub.boots != boots, hub.boots
        comfort = state.get("comfort_forwarder")
        if restarted and not back and comfort is not None:
            comfort.publish()
        if status["ha_entities"] == forwarded:
            if back or restarted:
                refresh()
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

    @callback
    def resend():
        """Everything at once through the fresh link (HeatingInputWatch): rooms, energy, contacts and presence."""
        refresh()
        comfort = state.get("comfort_forwarder")
        if comfort is not None:
            comfort.publish()

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(hub.add_listener(follow, first=True))
    for topic in (AVAILABILITY_TOPIC, HEARTBEAT_TOPIC, HEATING_TOPIC, ROOM_TOPIC + "+", BLE_TOPIC + "+", TRV_TOPIC + "+", PLAN_TOPIC,
                  ENTITIES_TOPIC, ENTITIES_TOPIC + "/+", LEARNED_TOPIC + "+", SUMMARY_TOPIC, FLOW_TOPIC, TUNING_TOPIC, SCOREBOARD_TOPIC,
                  INSIGHT_TOPIC, SHADOW_TOPIC, READINESS_TOPIC):
        entry.async_on_unload(await mqtt.async_subscribe(hass, base + topic, receive))
    entry.async_on_unload(async_track_time_interval(hass, refresh, timedelta(seconds=REFRESH_SECONDS)))
    entry.async_on_unload(async_track_time_interval(hass, hub.check_stale, STALE_CHECK))
    entry.async_on_unload(unload)
    # Does the E32 accept what is sent? A warning, a fresh resend and a repair when it does not (P22).
    watch = hub.input_watch = HeatingInputWatch(hass, entry, hub, heating_input_link(hass, entry, hub), resend)
    entry.async_on_unload(async_track_time_interval(hass, watch.check, INPUT_CHECK))
    entry.async_on_unload(watch.stop)
    if is_product(entry) and hub.plan is not None:  # a renamed source follows; a removed one gets a repair (R2-4)
        from .room_plan import RoomSourceWatch
        entry.async_on_unload(RoomSourceWatch(hass, entry, hub).start())
    energy.reconfigure()
    entry.async_on_unload(energy.stop)
