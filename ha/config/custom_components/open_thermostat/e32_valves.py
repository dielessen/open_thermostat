"""Radiator valves (TRVs) per E32 room: through Zigbee2MQTT by the E32, others by Home Assistant (E32 beta.24).

The E32 owns the valve record (``GET/POST /config/heating/trv``, ``src/control/TrvConfig.h``):
per room the Zigbee2MQTT friendly names and models of its valves, and whether the
E32 drives them ("valve control", off until switched on). The E32 itself talks to
Zigbee2MQTT on the same broker; Home Assistant only shows and configures:

- per room with valves, on the room's device: "Valve position" (the mean opening
  of the valves that report one, each valve in the attributes), "Valve battery"
  (the lowest, diagnostic), "Valve problem" (a low battery or a valve that stopped
  reporting, diagnostic) and the switch "Valve control" (configuration; its entity
  ID ends in ``_valve_control``);
- Repairs: a low battery (about 20 %), a valve that stopped reporting, and a room
  whose valve control is on while the room has a single temperature source (a
  separate sensor keeps it heating when that one fails);
- the valves of a room are chosen in Configure → Rooms → Edit or remove a room →
  Radiator valves (e32_room_flow.py).

A valve Home Assistant controls (ZHA, Z-Wave, Shelly, a cloud integration) is model
``ha_climate`` with its climate entity id as name: the E32 only lists it, Home
Assistant drives it on the E32's rules and reports its health, battery and opening
in the same entities (ha_valves.py).

Everything comes from ``fw/state/trv/<room>`` (HeatingHub.valves): without valves
there is no entity and no issue, and an entity of a room whose valves were removed
is removed again.
"""
from __future__ import annotations

import logging
import re
import time

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er, issue_registry as ir

from .const import DOMAIN
from .heating_link import ROOM_ID, RoomEntity, add_options, heating_hub, label, track_entities

_LOGGER = logging.getLogger(__name__)

KEY = "e32_valves"
# Our model ids (TrvConfig.h trvModels); what each can do is the E32's to know.
ZIGBEE_MODELS = ("bosch_bth_ra", "sonoff_trvzb", "sonoff_trv_zbt", "tuya_tv02", "generic")
HA_MODEL = "ha_climate"  # a climate entity Home Assistant drives (ha_valves.py)
MODELS = (*ZIGBEE_MODELS, HA_MODEL)
CLIMATE_ID = re.compile(r"climate\.[a-z0-9_]+")
MAX_VALVES_PER_ROOM = 4
MAX_VALVES = 16
MAX_NAME = 64
HEALTH = ("ok", "low_battery", "offline", "unknown")
ENTITY_KEYS = ("valve_position", "valve_battery", "valve_problem", "valve_control")
ISSUES = ("valve_battery_low", "valve_offline", "valve_single_source")
# A switched control shows its new state until the E32's telemetry agrees (at most this long).
PENDING_SECONDS = 30


def guess_model(text):
    """Our model id from a Zigbee2MQTT device's manufacturer/model text, or None (the installer chooses)."""
    text = text.lower()
    if "bth-ra" in text or "bosch" in text and "thermostat" in text:
        return "bosch_bth_ra"
    if "trv-zbt" in text:  # Sonoff TRV Gen2, before the TRVZB match
        return "sonoff_trv_zbt"
    if "trvzb" in text:
        return "sonoff_trvzb"
    return "tuya_tv02" if "tv02" in text else None


def valid_name(name):
    """A Zigbee2MQTT friendly name the E32 takes (TrvConfig::validName)."""
    return (type(name) is str and 0 < len(name) <= MAX_NAME and name == name.strip() and not name.startswith("/")
            and not name.endswith("/") and "//" not in name and name != "bridge" and not name.startswith("bridge/")
            and all(0x20 <= ord(c) <= 0x7E and c not in '#+"\\' for c in name))


def valid_entity(name):
    """A climate entity id the E32 takes as an ha_climate valve (TrvConfig::validClimate)."""
    return type(name) is str and len(name) <= MAX_NAME and CLIMATE_ID.fullmatch(name) is not None


def valid_valve(name, model):
    return valid_entity(name) if model == HA_MODEL else valid_name(name)


def decode_config(value):
    """The stored record of a GET/POST answer ({"schema","base_topic","rooms"}), or None."""
    if type(value) is not dict or value.get("schema") != 1 or type(value.get("base_topic")) is not str:
        return None
    rooms = value.get("rooms")
    if type(rooms) is not list or len(rooms) > 8:
        return None
    result = []
    for room in rooms:
        valves = room.get("valves") if type(room) is dict else None
        if (type(room) is not dict or type(room.get("room")) is not str or type(room.get("control")) is not bool
                or type(valves) is not list or len(valves) > MAX_VALVES_PER_ROOM
                or any(type(v) is not dict or v.get("model") not in MODELS or not valid_valve(v.get("name"), v.get("model"))
                       for v in valves)):
            return None
        result.append({"room": room["room"], "control": room["control"],
                       "valves": [{"name": v["name"], "model": v["model"]} for v in valves]})
    return {"schema": 1, "base_topic": value["base_topic"], "rooms": result}


def with_room(config, room_id, control=None, valves=None):
    """The record with one room changed: its control and/or its valves (an empty list removes the room)."""
    rooms = [dict(r) for r in config["rooms"]]
    room = next((r for r in rooms if r["room"] == room_id), None)
    if room is None:
        room = {"room": room_id, "control": False, "valves": []}
        rooms.append(room)
    if valves is not None:
        room["valves"] = [{"name": v["name"], "model": v["model"]} for v in valves]
    if control is not None:
        room["control"] = control
    if not room["valves"]:
        rooms.remove(room)  # the E32 keeps no control without a valve
    return {"schema": 1, "base_topic": config["base_topic"], "rooms": rooms}


def valve_error(err):
    """A clear Home Assistant error for a refused or failed write."""
    from .controller_link import ControllerLoginRejected, HeatingPlanRejected
    if isinstance(err, ControllerLoginRejected):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="room_plan_password")
    if isinstance(err, HeatingPlanRejected):
        if err.error == "save_unconfirmed":
            return HomeAssistantError(translation_domain=DOMAIN, translation_key="valves_unconfirmed")
        return ServiceValidationError(translation_domain=DOMAIN, translation_key="valves_rejected",
                                      translation_placeholders={"error": err.error})
    return HomeAssistantError(translation_domain=DOMAIN, translation_key="valves_unreachable",
                              translation_placeholders={"error": str(err)})


class ValveLink:
    """Reads and writes the E32's valve record over the stored controller connection.

    The record is read right before every change, so another writer (the E32
    page) is never overwritten with an old copy.
    """

    def __init__(self, hass, hub, plan):
        self.hass, self.hub, self.plan = hass, hub, plan
        self.config = None

    async def _call(self, document=None):
        async with self.plan._lock:
            async with self.plan._client() as client:
                await self.plan._login(client)
                return await client.async_valves(document)

    async def async_read(self):
        from .controller_link import ControllerLinkError
        try:
            value = decode_config(await self._call())
        except ControllerLinkError as err:
            raise valve_error(err) from None
        if value is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="valves_unreachable",
                                     translation_placeholders={"error": "controller_response_invalid"})
        self.config = value
        return value

    async def async_change(self, room_id, control=None, valves=None):
        """POST the record with one room changed; the E32 answers with what it stored."""
        from .controller_link import ControllerLinkError
        current = await self.async_read()
        try:
            answer = decode_config(await self._call(with_room(current, room_id, control, valves)))
        except ControllerLinkError as err:
            raise valve_error(err) from None
        if answer is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="valves_unconfirmed")
        self.config = answer
        return answer


def valve_link(hass, entry):
    """The entry's one link; None without a stored controller connection."""
    state = hass.data[DOMAIN][entry.entry_id]
    link = state.get(KEY)
    if link is None:
        hub = heating_hub(hass, entry)
        if hub.plan is None:
            return None
        link = state[KEY] = ValveLink(hass, hub, hub.plan)
    return link


def room_valves(hub, room_id):
    """A room's ``fw/state/trv/<room>`` with Home Assistant's view of its ha_climate valves, or None."""
    room = hub.valves.get(room_id)
    driver = getattr(hub, "ha_valves", None)
    return driver.overlay(room) if room is not None and driver is not None else room


def positions(room):
    return [v["position_pct"] for v in room.get("valves", []) if type(v.get("position_pct")) in (int, float)]


def batteries(room):
    return [v["battery_pct"] for v in room.get("valves", []) if type(v.get("battery_pct")) in (int, float)]


def problems(room):
    """[(valve name, "low_battery" | "offline")] of a room's valves."""
    return [(v["name"], v.get("health")) for v in room.get("valves", []) if v.get("health") in ("low_battery", "offline")]


def valve_attributes(room):
    return {"valves": [{key: v.get(key) for key in ("name", "model", "health", "position_pct", "battery_pct",
                                                    "battery_low", "setpoint_c") if v.get(key) is not None}
                       for v in room.get("valves", [])],
            "control": room.get("control"), "degraded": room.get("degraded"), "single_source": room.get("single_source")}


# -- entities -----------------------------------------------------------------------------


class ValveEntity(RoomEntity):
    """One room's radiator valves; available while the E32 reports them."""

    def __init__(self, hub, room, key):
        self._attach_room(hub, room, key)

    @property
    def valves(self):
        return room_valves(self.hub, self.room_id)

    @property
    def available(self):
        return self.hub.fresh and self.room is not None and self.valves is not None


class ValvePositionSensor(ValveEntity, SensorEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:valve"

    def __init__(self, hub, room):
        super().__init__(hub, room, "valve_position")

    @property
    def native_value(self):
        values = positions(self.valves or {})
        return round(sum(values) / len(values)) if values else None

    @property
    def extra_state_attributes(self):
        return valve_attributes(self.valves or {})


class ValveBatterySensor(ValveEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub, room):
        super().__init__(hub, room, "valve_battery")

    @property
    def native_value(self):
        values = batteries(self.valves or {})
        return min(values) if values else None


class ValveProblemBinarySensor(ValveEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub, room):
        super().__init__(hub, room, "valve_problem")

    @property
    def is_on(self):
        return bool(problems(self.valves or {}))

    @property
    def extra_state_attributes(self):
        return {"problems": [{"name": name, "health": health} for name, health in problems(self.valves or {})]}


class ValveControlSwitch(ValveEntity, SwitchEntity):
    """The room's valve control: on, the E32 drives its valves (while its output is enabled)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hub, room, link, clock=time.monotonic):
        super().__init__(hub, room, "valve_control")  # unique id <prefix>_e32_room_<id>_valve_control
        self.link, self._clock, self._pending = link, clock, None

    @property
    def is_on(self):
        reported = (self.valves or {}).get("control")
        if self._pending is not None:
            value, since = self._pending
            if reported is value or self._clock() - since > PENDING_SECONDS:
                self._pending = None
            else:
                return value
        return reported if type(reported) is bool else None

    @property
    def extra_state_attributes(self):
        trv = (self.hub.status or {}).get("trv")
        return {"output": trv.get("output") if type(trv) is dict else None}

    async def _set(self, value):
        await self.link.async_change(self.room_id, control=value)
        self._pending = (value, self._clock())
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)


def _valve_rooms(hub):
    for room_id, valves in hub.valves.items():
        room = hub.rooms.get(room_id)
        if room is not None and valves.get("valves"):
            yield room_id, room


def wanted_sensors(hub):
    for room_id, room in _valve_rooms(hub):
        yield ("valve", room_id, "position"), lambda room=room: ValvePositionSensor(hub, room)
        yield ("valve", room_id, "battery"), lambda room=room: ValveBatterySensor(hub, room)


def wanted_binary_sensors(hub):
    for room_id, room in _valve_rooms(hub):
        yield ("valve", room_id, "problem"), lambda room=room: ValveProblemBinarySensor(hub, room)


def wanted_switches(link):
    def wanted(hub):
        for room_id, room in _valve_rooms(hub):
            yield ("valve", room_id, "control"), lambda room=room: ValveControlSwitch(hub, room, link)
    return wanted


# -- issues and removed valves --------------------------------------------------------------


def issue_id(kind, entry, room_id):
    return f"{kind}_{entry.entry_id}_{room_id}"


@callback
def sync_issues(hass, entry, hub, raised):
    """Raise and clear the valve issues of the current telemetry; raised: the ids this entry raised."""
    if not hub.fresh:
        return  # an offline E32 says nothing about its valves; "E32 offline" is its own problem
    wanted = {}
    for room_id in hub.valves:
        valves = room_valves(hub, room_id)
        room = hub.rooms.get(room_id) or {"id": room_id}
        name = label(room) or room_id
        found = problems(valves)
        low = [n for n, h in found if h == "low_battery"]
        gone = [n for n, h in found if h == "offline"]
        if low:
            wanted[issue_id("valve_battery_low", entry, room_id)] = ("valve_battery_low", ir.IssueSeverity.WARNING,
                                                                     {"room": name, "valves": ", ".join(low)})
        if gone:
            wanted[issue_id("valve_offline", entry, room_id)] = ("valve_offline", ir.IssueSeverity.WARNING,
                                                                 {"room": name, "valves": ", ".join(gone)})
        if valves.get("control") is True and valves.get("single_source") is True:
            wanted[issue_id("valve_single_source", entry, room_id)] = ("valve_single_source", ir.IssueSeverity.WARNING,
                                                                       {"room": name})
    for issue in [i for i in raised if i not in wanted]:
        ir.async_delete_issue(hass, DOMAIN, issue)
        raised.discard(issue)
    for issue, (key, severity, placeholders) in wanted.items():
        ir.async_create_issue(hass, DOMAIN, issue, is_fixable=False, is_persistent=False, severity=severity,
                              translation_key=key, translation_placeholders=placeholders)
        raised.add(issue)


@callback
def remove_stale_entities(hass, entry, hub):
    """Remove the valve entities of rooms the E32 no longer lists with valves (fw/config/plan ``trv``).

    Only while the E32 is online and its plan known: an offline E32 never removes anything.
    """
    if not hub.fresh or hub.config is None:
        return
    listed = hub.config.get("trv")
    keep = set(listed) if type(listed) is list else set()
    head = f"{hub.prefix}_e32_room_"
    registry = er.async_get(hass)
    for record in er.async_entries_for_config_entry(registry, entry.entry_id):
        uid = record.unique_id or ""
        if record.platform != DOMAIN or not uid.startswith(head):
            continue
        rest = uid[len(head):]
        for key in ENTITY_KEYS:
            room_id = rest[:-len(key) - 1] if rest.endswith("_" + key) else None
            if room_id and ROOM_ID.fullmatch(room_id) and room_id not in keep:
                registry.async_remove(record.entity_id)
                break


def watch(hass, entry):
    """Once per entry: keep the issues and the entities in step with the telemetry."""
    state = hass.data[DOMAIN][entry.entry_id]
    if state.get(KEY + "_watch"):
        return
    state[KEY + "_watch"] = True
    hub = heating_hub(hass, entry)
    raised = set()
    from .ha_valves import HaValveDriver
    driver = hub.ha_valves = HaValveDriver(hass, hub)
    stop_driver = driver.start()

    @callback
    def changed():
        sync_issues(hass, entry, hub, raised)
        remove_stale_entities(hass, entry, hub)

    entry.async_on_unload(hub.add_listener(changed))

    @callback
    def unload():
        stop_driver()
        if hub.ha_valves is driver:
            hub.ha_valves = None
        for issue in list(raised):
            ir.async_delete_issue(hass, DOMAIN, issue)
        raised.clear()
        state.pop(KEY + "_watch", None)
    entry.async_on_unload(unload)
    changed()


def _product(entry):
    from .product import is_product
    return is_product(entry)


async def async_setup_sensors(hass, entry, async_add_entities):
    if not _product(entry):
        return
    hub = heating_hub(hass, entry)
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), wanted_sensors))
    watch(hass, entry)


async def async_setup_binary_sensors(hass, entry, async_add_entities):
    if not _product(entry):
        return
    hub = heating_hub(hass, entry)
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), wanted_binary_sensors))


async def async_setup_switches(hass, entry, async_add_entities):
    if not _product(entry):
        return
    link = valve_link(hass, entry)
    if link is None:
        return  # no stored controller connection: the control cannot be written
    hub = heating_hub(hass, entry)
    entry.async_on_unload(track_entities(hub, async_add_entities, add_options(hass, entry), wanted_switches(link)))
