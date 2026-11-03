"""Radiator valves per E32 room (E32 beta.24) in Home Assistant: telemetry, entities, Repairs, the control switch."""
import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import e32_valves as module
from custom_components.open_thermostat import heating_link
from custom_components.open_thermostat.controller_link import ControllerLinkError, HeatingPlanRejected
from custom_components.open_thermostat.heating_link import HeatingHub, track_entities
from custom_components.open_thermostat.room_plan import RoomPlanLink
from e32_telemetry import split_status
from test_e32_telemetry_topics import STATUS, UNIQUE_IDS, _setup

VALVE = {"name": "Kraan woonkamer", "model": "bosch_bth_ra", "health": "ok", "position_pct": 40, "battery_pct": 85,
         "setpoint_c": 21.0}
TRV = {"output": False, "flow_offset_c": 0,
       "rooms": [{"room": "woonkamer", "control": False, "degraded": False, "single_source": True,
                  "valves": [VALVE, {**VALVE, "name": "Kraan raam", "position_pct": 60, "battery_pct": 18, "health": "low_battery"}]}]}
CONFIG = {"schema": 1, "base_topic": "zigbee2mqtt",
          "rooms": [{"room": "woonkamer", "control": False,
                     "valves": [{"name": "Kraan woonkamer", "model": "bosch_bth_ra"}, {"name": "Kraan raam", "model": "bosch_bth_ra"}]},
                    {"room": "keuken", "control": True, "valves": [{"name": "Kraan keuken", "model": "sonoff_trvzb"}]}]}


def with_trv(trv=TRV):
    return {**deepcopy(STATUS), "trv": deepcopy(trv)}


def send(e32, status):
    for suffix, doc in split_status(status):
        assert e32.message(suffix, json.dumps(doc), retain=True), suffix
    e32.heartbeat()


@pytest.mark.asyncio
async def test_without_valves_nothing_changes(hass, monkeypatch):
    hub, added, e32, _, _, _ = await _setup(hass, monkeypatch)
    send(e32, STATUS)
    assert hub.valves == {} and "trv" not in hub.status
    assert sorted(e.unique_id for e in added) == UNIQUE_IDS            # the same entities as before valves
    assert [list(w(hub)) for w in (module.wanted_sensors, module.wanted_binary_sensors, module.wanted_switches(None))] == [[], [], []]
    raised = set()
    module.sync_issues(hass, SimpleNamespace(entry_id="e"), hub, raised)
    assert raised == set() and not ir.async_get(hass).issues


@pytest.mark.asyncio
async def test_valve_telemetry_arrives_per_room_and_makes_the_room_entities(hass, monkeypatch):
    hub, _, e32, _, _, _ = await _setup(hass, monkeypatch)
    send(e32, with_trv())
    assert hub.status["trv"]["output"] is False and hub.status["trv"]["flow_offset_c"] == 0
    assert list(hub.valves) == ["woonkamer"]
    added = []
    link = SimpleNamespace()
    for wanted in (module.wanted_sensors, module.wanted_binary_sensors, module.wanted_switches(link)):
        track_entities(hub, added.extend, {}, wanted)
    position, battery, problem, control = added
    assert [e.unique_id for e in added] == [f"fixture_e32_room_woonkamer_{k}" for k in module.ENTITY_KEYS]
    assert control.unique_id.endswith("_valve_control")          # what the readiness check looks for
    assert [e.translation_key for e in added] == [f"room_{k}" for k in module.ENTITY_KEYS]
    assert all(e.available for e in added)
    assert (position.native_value, battery.native_value, problem.is_on, control.is_on) == (50, 18, True, False)
    assert position.extra_state_attributes["valves"][1] == {"name": "Kraan raam", "model": "bosch_bth_ra", "health": "low_battery",
                                                            "position_pct": 60, "battery_pct": 18, "setpoint_c": 21.0}
    assert problem.extra_state_attributes == {"problems": [{"name": "Kraan raam", "health": "low_battery"}]}
    assert (battery.entity_category, problem.entity_category, control.entity_category) == (
        EntityCategory.DIAGNOSTIC, EntityCategory.DIAGNOSTIC, EntityCategory.CONFIG)
    assert all(e.device_info["identifiers"] == {("open_thermostat", "fixture_e32_room_woonkamer")} for e in added)
    # The valves go: their entities become unavailable, and the E32 offline makes them unavailable too.
    send(e32, STATUS)
    assert hub.valves == {} and not any(e.available for e in added)


@pytest.mark.asyncio
async def test_a_room_document_for_another_room_or_malformed_is_dropped(hass, monkeypatch):
    hub, _, e32, _, _, _ = await _setup(hass, monkeypatch)
    send(e32, with_trv())
    e32.message("fw/state/trv/woonkamer", json.dumps({"schema": 1, "room": "keuken", "control": False, "valves": []}), retain=True)
    assert hub.valves == {}
    send(e32, with_trv())
    e32.message("fw/state/trv/woonkamer", json.dumps({"schema": 1, "room": "woonkamer", "control": "yes", "valves": []}), retain=True)
    assert hub.valves == {}
    send(e32, with_trv())
    assert list(hub.valves) == ["woonkamer"]
    assert heating_link.decode_trv(json.dumps({"schema": 1, "room": "woonkamer", "control": True, "valves": [{}] * 5}), "woonkamer") is None


@pytest.mark.asyncio
async def test_repairs_warn_early_and_clear_themselves(hass, monkeypatch):
    hub, _, e32, _, _, _ = await _setup(hass, monkeypatch)
    entry = SimpleNamespace(entry_id="e")
    raised = set()
    issues = ir.async_get(hass)
    send(e32, with_trv())
    module.sync_issues(hass, entry, hub, raised)
    assert raised == {"valve_battery_low_e_woonkamer"}           # control off: no single-source hint yet
    issue = issues.async_get_issue("open_thermostat", "valve_battery_low_e_woonkamer")
    assert issue.translation_placeholders == {"room": "Woonkamer", "valves": "Kraan raam"}
    assert issue.severity == ir.IssueSeverity.WARNING
    trv = deepcopy(TRV)
    room = trv["rooms"][0]
    room["control"] = True
    room["valves"][1].update(health="offline", battery_pct=90)
    send(e32, with_trv(trv))
    module.sync_issues(hass, entry, hub, raised)
    assert raised == {"valve_offline_e_woonkamer", "valve_single_source_e_woonkamer"}
    assert issues.async_get_issue("open_thermostat", "valve_battery_low_e_woonkamer") is None
    room["valves"][1]["health"] = "ok"
    room["single_source"] = False
    send(e32, with_trv(trv))
    module.sync_issues(hass, entry, hub, raised)
    assert raised == set() and not [i for i in issues.issues if i[1].startswith("valve_")]
    # The E32 offline says nothing about its valves: no issue is raised or cleared then.
    room["valves"][1]["health"] = "offline"
    send(e32, with_trv(trv))
    module.sync_issues(hass, entry, hub, raised)
    hub.update(None)
    module.sync_issues(hass, entry, hub, raised)
    assert raised == {"valve_offline_e_woonkamer"}


def test_removed_valves_lose_their_entities_only_while_the_e32_reports(monkeypatch):
    removed = []
    records = [SimpleNamespace(platform="open_thermostat", unique_id=f"fixture_e32_room_{room}_{key}", entity_id=f"x.{room}_{key}")
               for room in ("woonkamer", "keuken") for key in (*module.ENTITY_KEYS, "temperature")]
    monkeypatch.setattr(module.er, "async_get", lambda hass: SimpleNamespace(async_remove=removed.append))
    monkeypatch.setattr(module.er, "async_entries_for_config_entry", lambda registry, entry_id: records)
    hub = HeatingHub("fixture")
    entry = SimpleNamespace(entry_id="e")
    module.remove_stale_entities(None, entry, hub)
    assert removed == []                                        # not online: nothing is removed
    hub.update(STATUS)
    hub.config = {"rooms": ["woonkamer", "keuken"], "trv": ["woonkamer"]}
    module.remove_stale_entities(None, entry, hub)
    assert removed == [f"x.keuken_{key}" for key in module.ENTITY_KEYS]
    removed.clear()
    hub.config = {"rooms": ["woonkamer", "keuken"]}               # no valves at all any more
    module.remove_stale_entities(None, entry, hub)
    assert removed == [f"x.{room}_{key}" for room in ("woonkamer", "keuken") for key in module.ENTITY_KEYS]


class FakeE32:
    """The E32 /config/heating/trv contract: the whole record, refusals by name, 404 on older firmware."""

    def __init__(self, config=CONFIG):
        self.config = deepcopy(config)
        self.calls = []
        self.fail = None
        self.missing = False

    def client(self, address):
        e32 = self

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def async_login(self, password):
                assert password == "secret"

            async def async_read_heating_plan(self):
                return {"schema": 1, "revision": 4, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60, "rooms": []}

            async def async_valves(self, document=None):
                e32.calls.append(deepcopy(document))
                if e32.missing:
                    raise ControllerLinkError("controller_update_required")
                if document is not None and e32.fail:
                    raise e32.fail
                if document is not None:
                    e32.config = deepcopy(document)
                return {**deepcopy(e32.config), "features": ["actuator.output.v1"], "models": [], "status": None}
        return Client()


def valve_link(hass, e32):
    hub = HeatingHub("fixture")
    plan = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    plan._client = lambda: e32.client("http://192.168.1.206")
    hub.plan = plan
    return hub, module.ValveLink(hass, hub, plan)


@pytest.mark.asyncio
async def test_the_switch_reads_then_writes_only_its_rooms_control(hass):
    e32 = FakeE32()
    hub, link = valve_link(hass, e32)
    hub.update(with_trv())
    now = [100.0]
    switch = module.ValveControlSwitch(hub, hub.rooms["woonkamer"], link, clock=lambda: now[0])
    switch.async_write_ha_state = lambda: None
    await switch.async_turn_on()
    read, written = e32.calls
    assert read is None
    assert written == {**CONFIG, "rooms": [{**CONFIG["rooms"][0], "control": True}, CONFIG["rooms"][1]]}
    assert switch.is_on is True                                  # shown at once, until the telemetry agrees
    now[0] += module.PENDING_SECONDS + 1
    assert switch.is_on is False                                 # the E32 still reports off: that is the truth
    e32.fail = HeatingPlanRejected(400, "unknown_room")
    with pytest.raises(ServiceValidationError):
        await switch.async_turn_off()
    e32.fail = HeatingPlanRejected(503, "save_unconfirmed")
    with pytest.raises(HomeAssistantError):
        await switch.async_turn_off()
    e32.missing = True
    with pytest.raises(HomeAssistantError) as err:
        await switch.async_turn_off()
    assert err.value.translation_placeholders == {"error": "controller_update_required"}


class SlowE32(FakeE32):
    """The real E32 answers over the network: every call yields to the event loop."""

    def client(self, address):
        inner = super().client(address)
        original = inner.async_valves

        async def async_valves(document=None):
            await asyncio.sleep(0)
            return await original(document)
        inner.async_valves = async_valves
        return inner


@pytest.mark.asyncio
async def test_two_switches_changed_at_once_both_keep_their_change(hass):
    """One service call for two "Valve control" switches: each change reads the record the other stored."""
    config = deepcopy(CONFIG)
    config["rooms"][1]["control"] = False
    e32 = SlowE32(config)
    hub, link = valve_link(hass, e32)
    hub.update(with_trv())
    a = module.ValveControlSwitch(hub, hub.rooms["woonkamer"], link)
    b = module.ValveControlSwitch(hub, hub.rooms["keuken"], link)
    a.async_write_ha_state = b.async_write_ha_state = lambda: None
    await asyncio.gather(a.async_turn_on(), b.async_turn_on())
    assert {r["room"]: r["control"] for r in e32.config["rooms"]} == {"woonkamer": True, "keuken": True}
    assert [c is None for c in e32.calls] == [True, False, True, False]   # read, write, then the next change


@pytest.mark.asyncio
async def test_the_controller_client_speaks_the_valve_record_contract():
    """The real ControllerClient against an HTTP E32: GET and POST /config/heating/trv pass the allowlist."""
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from custom_components.open_thermostat import controller_link
    seen, state = [], {"config": deepcopy(CONFIG), "missing": False}

    async def login(request):
        return web.json_response({"ok": True})

    async def session(request):
        return web.json_response({"authenticated": True, "csrf": "c" * 64})

    async def logout(request):
        return web.json_response({})

    async def trv(request):
        if state["missing"]:
            return web.Response(status=404, text="Not found")
        if request.method == "POST":
            body = await request.json()
            seen.append((request.headers.get("X-OpenThermostat-CSRF"), request.headers.get("Content-Type"), body))
            if body["rooms"] and body["rooms"][0]["room"] == "zolder":
                return web.json_response({"error": "unknown_room"}, status=400)
            state["config"] = body
        return web.json_response({**state["config"], "features": [], "models": [], "status": None})

    app = web.Application()
    app.router.add_post("/auth/login", login)
    app.router.add_get("/auth/session", session)
    app.router.add_post("/auth/logout", logout)
    app.router.add_route("*", "/config/heating/trv", trv)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        client = controller_link.ControllerClient("http://192.168.1.206")  # loopback is refused by design
        async with client:
            client.address = f"http://127.0.0.1:{server.port}"
            await client.async_login("secret")
            assert module.decode_config(await client.async_valves()) == CONFIG
            changed = module.with_room(CONFIG, "woonkamer", control=True)
            assert module.decode_config(await client.async_valves(changed)) == changed
            with pytest.raises(HeatingPlanRejected) as error:
                await client.async_valves({**CONFIG, "rooms": [{**CONFIG["rooms"][0], "room": "zolder"}]})
            assert (error.value.status, error.value.error) == (400, "unknown_room")
            state["missing"] = True  # firmware before beta.24
            with pytest.raises(ControllerLinkError, match="^controller_update_required$"):
                await client.async_valves()
    finally:
        await server.close()
    assert seen[0] == ("c" * 64, "application/json", changed) and state["config"] == changed


def test_the_record_rules_match_the_e32():
    assert module.decode_config({**CONFIG, "features": [], "models": [], "status": None}) == CONFIG
    for bad in (None, {**CONFIG, "schema": 2}, {**CONFIG, "rooms": [{**CONFIG["rooms"][0], "control": 1}]},
                {**CONFIG, "rooms": [{**CONFIG["rooms"][0], "valves": [{"name": "x", "model": "honeywell"}]}]},
                {**CONFIG, "rooms": [{**CONFIG["rooms"][0], "valves": [{"name": "a", "model": "generic"}] * 5}]}):
        assert module.decode_config(bad) is None
    for name in ("Kraan woonkamer", "a/b", "x" * 64):
        assert module.valid_name(name), name
    for name in ("", " x", "x ", "/x", "x/", "a//b", "bridge", "bridge/state", "a#", "a+", 'a"', "a\\", "x" * 65, "é", "\t"):
        assert not module.valid_name(name), name
    # Removing every valve removes the room; control without a valve is never kept.
    changed = module.with_room(CONFIG, "keuken", valves=[])
    assert [r["room"] for r in changed["rooms"]] == ["woonkamer"]
    added = module.with_room(CONFIG, "slaapkamer", control=True, valves=[{"name": "K", "model": "generic"}])
    assert added["rooms"][-1] == {"room": "slaapkamer", "control": True, "valves": [{"name": "K", "model": "generic"}]}
    assert CONFIG["rooms"][1]["valves"]                          # the input is never changed


# -- the valves section of the room form (rc.3) ----------------------------------------------

from test_e32_room_flow import manager, product, room_form, rooms_menu, shown  # noqa: E402,F401 - the fixture and helpers
from test_room_plan import FakeE32 as PlanE32  # noqa: E402
from custom_components.open_thermostat import valve_routes  # noqa: E402

RECORD = {"schema": 1, "base_topic": "zigbee2mqtt", "rooms": []}


class E32WithValves(PlanE32):
    def __init__(self, config=None):
        super().__init__()
        self.valves = FakeE32(config or RECORD)
        from custom_components.open_thermostat.e32_setting_device import default_program
        for room in self.plan["rooms"]:  # every room has its week program: saving it as shown changes nothing
            room["schedule"] = default_program(room["minimum_centi_c"], room["maximum_centi_c"])

    def client(self, address):
        client = super().client(address)
        client.async_valves = self.valves.client(address).async_valves
        return client


class Zigbee:
    """Home Assistant's registries with Zigbee2MQTT and other valves; topics: what the MQTT debug info says."""

    def __init__(self, hass, monkeypatch):
        from homeassistant.config_entries import ConfigEntry
        from types import MappingProxyType
        self.hass, self.topics = hass, {}
        self.mqtt = ConfigEntry(domain="mqtt", title="MQTT", version=1, minor_version=1, data={}, options={},
                                source="user", unique_id="mqtt", discovery_keys=MappingProxyType({}), subentries_data=[])
        hass.config_entries._entries[self.mqtt.entry_id] = self.mqtt
        monkeypatch.setattr(valve_routes, "device_topics", lambda h, device_id: self.topics.get(device_id, []))

    def valve(self, name, model_id, *, manufacturer="Bosch", model="Radiator thermostat II", renamed=None,
              topic_name=None, base="zigbee2mqtt", platform="mqtt", ieee=None, topics=True, label=None):
        """A climate entity on a Zigbee2MQTT device (Zigbee2MQTT friendly name: topic_name or name)."""
        from homeassistant.helpers import device_registry as dr, entity_registry as er
        ieee = ieee or f"0x{abs(hash(name)) % 16 ** 16:016x}"
        device = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.mqtt.entry_id, identifiers={("mqtt", f"zigbee2mqtt_{ieee}")},
            manufacturer=manufacturer, model=model, model_id=model_id, name=name)
        if renamed:
            device = dr.async_get(self.hass).async_update_device(device.id, name_by_user=renamed)
        entity = er.async_get(self.hass).async_get_or_create(
            "climate", platform, f"{ieee}_climate", device_id=device.id, suggested_object_id=slug(name))
        if topics:
            friendly = topic_name or name
            self.topics[device.id] = [f"{base}/{friendly}", f"{base}/{friendly}/availability", f"{base}/bridge/state",
                                      f"{base}/{friendly}", f"{base}/{friendly}/set"]
        self.hass.states.async_set(entity.entity_id, "heat", {"current_temperature": 20, "temperature": 20,
                                                               "friendly_name": label or renamed or name})
        return entity.entity_id

    def other(self, object_id, platform="zha"):
        """A climate entity of another integration (no Zigbee2MQTT device)."""
        from homeassistant.helpers import entity_registry as er
        entity = er.async_get(self.hass).async_get_or_create("climate", platform, object_id, suggested_object_id=object_id)
        self.hass.states.async_set(entity.entity_id, "heat", {"current_temperature": 20, "temperature": 20})
        return entity.entity_id


def slug(name):
    return name.lower().replace(" ", "_")


def section_of(form, name="valves"):
    """{field: (marker, selector)} of a section of the room form."""
    value = next(v for k, v in form["data_schema"].schema.items() if str(k) == name)
    return {str(k): (k, v) for k, v in value.schema.schema.items()}, value.options


@pytest.mark.asyncio
async def test_route_detection_picks_the_e32_only_for_zigbee2mqtt_valves_it_knows(hass, monkeypatch):
    zigbee = Zigbee(hass, monkeypatch)
    # Renamed in Home Assistant, and named differently by Zigbee2MQTT's discovery: the topic decides.
    bosch = zigbee.valve("Bosch valve", "BTH-RA", renamed="Living room radiator", topic_name="Kraan woonkamer")
    sonoff = zigbee.valve("Kraan keuken", "TRVZB", manufacturer="SONOFF", model="Zigbee thermostatic radiator valve")
    gen2 = zigbee.valve("Kraan zolder", "TRV-ZBT", manufacturer="SONOFF", model="Zigbee thermostatic radiator valve")
    tuya = zigbee.valve("Kraan bad", "TV02-Zigbee", manufacturer="TuYa", model="Thermostat radiator valve")
    old_style = zigbee.valve("Kraan hal", None, model="Radiator thermostat II (BTH-RA)")  # older Zigbee2MQTT: one model text
    aqara = zigbee.valve("Kraan raam", "SRTS-A01", manufacturer="Aqara", model="Radiator thermostat E1")
    wall = zigbee.valve("Thermostaat gang", "BTH-RM", model="Room thermostat II")  # a Bosch wall thermostat, no valve
    elsewhere = zigbee.valve("Kraan schuur", "BTH-RA", base="z2m")                    # another Zigbee2MQTT base topic
    no_topics = zigbee.valve("Kraan studeer", "BTH-RA", renamed="Study", topics=False)
    template = zigbee.valve("Kraan bijkeuken", "BTH-RA", platform="template")       # not the Zigbee2MQTT entity itself
    zha = zigbee.other("zha_trv")
    finder = valve_routes.RouteFinder(hass, "zigbee2mqtt")
    routes = {entity: finder.route(entity) for entity in (bosch, sonoff, gen2, tuya, old_style, aqara, wall, elsewhere,
                                                          no_topics, template, zha)}
    assert routes[bosch].record() == {"name": "Kraan woonkamer", "model": "bosch_bth_ra"} and routes[bosch].direct
    assert routes[sonoff].record() == {"name": "Kraan keuken", "model": "sonoff_trvzb"}
    assert routes[gen2].record() == {"name": "Kraan zolder", "model": "sonoff_trv_zbt"}
    assert routes[tuya].record() == {"name": "Kraan bad", "model": "tuya_tv02"}
    assert routes[old_style].record() == {"name": "Kraan hal", "model": "bosch_bth_ra"}
    assert routes[no_topics].record() == {"name": "Kraan studeer", "model": "bosch_bth_ra"}  # Zigbee2MQTT's name, not "Study"
    for entity in (aqara, wall, elsewhere, template, zha):  # through Home Assistant: its climate entity
        assert routes[entity].record() == {"name": entity, "model": "ha_climate"} and not routes[entity].direct, entity
    assert routes[aqara].friendly == "Kraan raam" and routes[aqara].detected is None   # Zigbee2MQTT, model unknown
    assert routes[elsewhere].friendly is None                                         # the E32 cannot reach it
    # Advanced: a model chosen by hand, or Home Assistant for a valve the E32 knows.
    assert finder.route(aqara, "generic").record() == {"name": "Kraan raam", "model": "generic"}
    assert finder.route(bosch, "ha_climate").record() == {"name": bosch, "model": "ha_climate"}
    assert finder.route(zha, "generic").record() == {"name": zha, "model": "ha_climate"}   # no Zigbee2MQTT name: HA
    assert finder.index()["Kraan woonkamer"] == bosch and "Kraan schuur" not in finder.index()


def test_the_friendly_name_comes_from_the_state_topic():
    topics = ["zigbee2mqtt/Kamer/kraan", "zigbee2mqtt/Kamer/kraan/availability", "zigbee2mqtt/bridge/state",
              "zigbee2mqtt/Kamer/kraan/set", "zigbee2mqtt/Kamer/kraan"]
    assert valve_routes.friendly_from_topics(topics, "zigbee2mqtt") == "Kamer/kraan"   # a / in the name stays
    assert valve_routes.friendly_from_topics(topics, "zigbee2mqtt/") == "Kamer/kraan"
    assert valve_routes.friendly_from_topics(topics, "z2m") is None                    # another base topic
    assert valve_routes.friendly_from_topics(["zigbee2mqtt/A", "zigbee2mqtt/B"], "zigbee2mqtt") is None  # ambiguous
    assert valve_routes.friendly_from_topics(["zigbee2mqtt/a#b"], "zigbee2mqtt") is None    # not a name the E32 takes


def test_the_topics_are_read_from_the_mqtt_debug_info(hass):
    """The MQTT integration's own debug info (subscriptions and discovery) of a device's entities."""
    from homeassistant.components.mqtt.const import ATTR_DISCOVERY_PAYLOAD, ATTR_DISCOVERY_TOPIC
    from homeassistant.components.mqtt.models import DATA_MQTT
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from homeassistant.config_entries import ConfigEntry
    from types import MappingProxyType
    mqtt = ConfigEntry(domain="mqtt", title="MQTT", version=1, minor_version=1, data={}, options={}, source="user",
                       unique_id="mqtt", discovery_keys=MappingProxyType({}), subentries_data=[])
    hass.config_entries._entries[mqtt.entry_id] = mqtt
    device = dr.async_get(hass).async_get_or_create(config_entry_id=mqtt.entry_id,
                                                    identifiers={("mqtt", "zigbee2mqtt_0x01")}, name="Bosch valve")
    entity = er.async_get(hass).async_get_or_create("climate", "mqtt", "0x01_climate", device_id=device.id)
    assert valve_routes.device_topics(hass, device.id) == []        # no MQTT integration: no topics, no error
    payload = {"current_temperature_topic": "zigbee2mqtt/Kraan woonkamer", "json_attributes_topic": "zigbee2mqtt/Kraan woonkamer",
               "temperature_command_topic": "zigbee2mqtt/Kraan woonkamer/set", "name": None}
    hass.data[DATA_MQTT] = SimpleNamespace(debug_info_triggers={}, debug_info_entities={entity.entity_id: {
        "subscriptions": {"zigbee2mqtt/Kraan woonkamer": {"messages": [], "count": 1},
                          "zigbee2mqtt/Kraan woonkamer/availability": {"messages": [], "count": 1}},
        "discovery_data": {ATTR_DISCOVERY_TOPIC: "homeassistant/climate/0x01/climate/config",
                           ATTR_DISCOVERY_PAYLOAD: payload},
        "transmitted": {}}})
    try:
        topics = valve_routes.device_topics(hass, device.id)
        assert "zigbee2mqtt/Kraan woonkamer/set" not in topics       # command topics are left out
        assert valve_routes.friendly_name(hass, dr.async_get(hass).async_get(device.id), "zigbee2mqtt") == "Kraan woonkamer"
    finally:
        hass.data.pop(DATA_MQTT)


@pytest.mark.asyncio
async def test_valves_are_a_section_of_the_room_form_and_each_gets_its_route(hass, manager, monkeypatch):
    zigbee = Zigbee(hass, monkeypatch)
    bosch = zigbee.valve("Kraan woonkamer", "BTH-RA", renamed="Living room radiator")
    aqara = zigbee.valve("Kraan raam", "SRTS-A01", manufacturer="Aqara", model="Radiator thermostat E1")
    zha = zigbee.other("zha_trv")
    e32 = E32WithValves()
    parent, _ = product(hass, e32)
    menu = await rooms_menu(manager, parent)
    pick = await manager.async_configure(menu["flow_id"], {"next_step_id": "e32_room_pick"})
    action = next(v for k, v in pick["data_schema"].schema.items() if str(k) == "action")
    assert action.config["options"] == ["edit", "remove"]                 # no separate valves action any more
    form = await manager.async_configure(pick["flow_id"], {"room": "woonkamer", "action": "edit"})
    keys = [str(k) for k in form["data_schema"].schema]
    assert keys[-4:] == ["window", "persons", "limits", "valves"]
    fields, options = section_of(form)
    assert list(fields) == ["valves", "control", "choose_models"] and options["collapsed"] is True   # no valves yet
    assert fields["valves"][1].config["filter"] == [{"domain": ["climate"]}] and fields["valves"][1].config["multiple"]
    assert fields["control"][0].default() is False                      # valve control stays off until switched on
    assert form["description_placeholders"]["valve_routes"] == "No radiator valves yet."
    posts = len(e32.posts)
    values = shown(form)
    values["valves"] = {"valves": [bosch, aqara, zha], "control": False, "choose_models": False}
    result = await manager.async_configure(form["flow_id"], values)
    assert result["type"] == "menu" and result["step_id"] == "e32_rooms_saved", result
    assert len(e32.posts) == posts                                      # only the valves changed: the plan is not written
    assert e32.valves.config["rooms"] == [{"room": "woonkamer", "control": False, "valves": [
        {"name": "Kraan woonkamer", "model": "bosch_bth_ra"},             # renamed in HA: the Zigbee2MQTT name
        {"name": aqara, "model": "ha_climate"}, {"name": zha, "model": "ha_climate"}]}]
    assert result["description_placeholders"]["valves"] == (
        "\n\nRadiator valves:\n- Living room radiator: works without Home Assistant (Bosch BTH-RA)\n"
        "- Kraan raam: through Home Assistant (model not recognised)\n- climate.zha_trv: through Home Assistant")
    # Opened again: the section is open, with the three valves and their routes.
    form = await room_form(manager, parent, "woonkamer")
    fields, options = section_of(form)
    assert options["collapsed"] is False and (fields["valves"][0].description or {})["suggested_value"] == [bosch, aqara, zha]
    assert "- Living room radiator: works without Home Assistant (Bosch BTH-RA)" in form["description_placeholders"]["valve_routes"]
    result = await manager.async_configure(form["flow_id"], shown(form))
    assert result["type"] == "abort" and result["reason"] == "e32_room_unchanged"   # nothing changed: nothing written


@pytest.mark.asyncio
async def test_existing_valve_records_keep_working_and_map_to_their_entities(hass, manager, monkeypatch):
    zigbee = Zigbee(hass, monkeypatch)
    bosch = zigbee.valve("Kraan woonkamer", "BTH-RA")
    zha = zigbee.other("zha_trv")
    record = {"schema": 1, "base_topic": "zigbee2mqtt", "rooms": [{"room": "woonkamer", "control": True, "valves": [
        {"name": "Kraan woonkamer", "model": "generic"},       # chosen by hand before: stays generic
        {"name": "Kraan oud", "model": "sonoff_trvzb"},        # Home Assistant does not know it: kept as stored
        {"name": zha, "model": "ha_climate"}]}]}
    e32 = E32WithValves(record)
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent, "woonkamer")
    fields, options = section_of(form)
    assert list(fields) == ["valves", "kept", "control", "choose_models"] and options["collapsed"] is False
    assert fields["valves"][0].description["suggested_value"] == [bosch, zha]
    assert fields["kept"][0].description["suggested_value"] == ["Kraan oud"]
    assert fields["kept"][1].config["options"] == [{"value": "Kraan oud", "label": "Kraan oud (Sonoff TRVZB)"}]
    assert fields["control"][0].default() is True
    assert form["description_placeholders"]["valve_routes"] == (
        "- Kraan woonkamer: works without Home Assistant (Zigbee2MQTT)\n"
        "- Kraan oud: works without Home Assistant (not found in Home Assistant, kept as it was)\n"
        "- climate.zha_trv: through Home Assistant")
    result = await manager.async_configure(form["flow_id"], shown(form))
    assert result["type"] == "abort" and result["reason"] == "e32_room_unchanged"
    assert [c for c in e32.valves.calls if c is not None] == []           # the stored record is never rewritten as is
    # Deselecting the kept valve removes it; the others keep their order, model and control.
    form = await room_form(manager, parent, "woonkamer")
    values = shown(form)
    values["valves"]["kept"] = []
    result = await manager.async_configure(form["flow_id"], values)
    assert result["type"] == "menu", result
    assert e32.valves.config["rooms"] == [{"room": "woonkamer", "control": True, "valves": [
        {"name": "Kraan woonkamer", "model": "generic"}, {"name": zha, "model": "ha_climate"}]}]


@pytest.mark.asyncio
async def test_valves_are_checked_before_the_e32_is_written(hass, manager, monkeypatch):
    from homeassistant.data_entry_flow import InvalidData
    from homeassistant.helpers import entity_registry as er
    zigbee = Zigbee(hass, monkeypatch)
    bath = zigbee.valve("Kraan bad", "BTH-RA")
    hal = zigbee.valve("Kraan hal", "BTH-RA")
    twin = zigbee.valve("Kraan hal oud", "BTH-RA", topic_name="Kraan hal")   # a re-paired valve: the same Zigbee2MQTT name
    many = [zigbee.valve(f"Kraan {n}", "TRVZB", manufacturer="SONOFF") for n in range(5)]
    long = zigbee.other("x" * 60)
    others = [{"name": f"V{n}", "model": "generic"} for n in range(13)]
    e32 = E32WithValves({"schema": 1, "base_topic": "zigbee2mqtt", "rooms": [
        {"room": "badkamer", "control": False, "valves": [{"name": "Kraan bad", "model": "bosch_bth_ra"},
                                                          {"name": "climate.bad_ha", "model": "ha_climate"}]}]})
    parent, _ = product(hass, e32)
    own = er.async_get(hass).async_get_or_create("climate", "open_thermostat", "fixture_thermostat", suggested_object_id="ot_woonkamer")
    form = await room_form(manager, parent, "woonkamer")
    fields, _ = section_of(form)
    # Never our own thermostat, the room's thermostat source or another room's valve (by entity or Zigbee2MQTT name).
    assert set(fields["valves"][1].config["exclude_entities"]) == {own.entity_id, "climate.woonkamer", "climate.bad_ha", bath}
    with pytest.raises(InvalidData):                                   # the picker itself refuses them
        await manager.async_configure(form["flow_id"], {**shown(form), "valves": {"valves": [bath]}})
    for chosen, field, error in (([hal, twin], "valves", "e32_valve_duplicate"),
                                 ([long], "valves", "e32_valve_entity_invalid"),
                                 (many, "base", "e32_valve_room_limit")):
        result = await manager.async_configure(form["flow_id"], {**shown(form), "valves": {"valves": chosen}})
        assert result["type"] == "form" and result["errors"] == {field: error}, (chosen, result)
        form = result
    e32.valves.config["rooms"] = [{"room": f"r{n}", "control": False, "valves": others[n * 4:n * 4 + 4]} for n in range(4)]
    form = await room_form(manager, parent, "woonkamer")             # 13 valves elsewhere, 4 more is 17
    result = await manager.async_configure(form["flow_id"], {**shown(form), "valves": {"valves": many[:4]}})
    assert result["type"] == "form" and result["errors"] == {"base": "e32_valve_limit"}, result
    assert [c for c in e32.valves.calls if c is not None] == []       # nothing was written


@pytest.mark.asyncio
async def test_advanced_lets_the_installer_choose_the_model_of_an_unknown_zigbee2mqtt_valve(hass, manager, monkeypatch):
    zigbee = Zigbee(hass, monkeypatch)
    aqara = zigbee.valve("Kraan raam", "SRTS-A01", manufacturer="Aqara", model="Radiator thermostat E1")
    bosch = zigbee.valve("Kraan woonkamer", "BTH-RA")
    zha = zigbee.other("zha_trv")
    e32 = E32WithValves()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent, "woonkamer")
    values = shown(form)
    values["valves"] = {"valves": [aqara, bosch, zha], "control": True, "choose_models": True}
    step = await manager.async_configure(form["flow_id"], values)
    assert step["type"] == "form" and step["step_id"] == "e32_room_valve_models", step
    defaults = {str(k): k.default() for k in step["data_schema"].schema}
    assert defaults == {"model_1": "ha_climate", "model_2": "bosch_bth_ra"}   # unknown: Home Assistant; known: its model
    assert step["description_placeholders"]["valve_1"] == "Kraan raam · Aqara Radiator thermostat E1 SRTS-A01"
    assert step["description_placeholders"]["valve_3"] == ""                  # the ZHA valve has no model to choose
    result = await manager.async_configure(step["flow_id"], {"model_1": "generic", "model_2": "bosch_bth_ra"})
    assert result["type"] == "menu" and result["step_id"] == "e32_rooms_saved", result
    assert e32.valves.config["rooms"] == [{"room": "woonkamer", "control": True, "valves": [
        {"name": "Kraan raam", "model": "generic"}, {"name": "Kraan woonkamer", "model": "bosch_bth_ra"},
        {"name": zha, "model": "ha_climate"}]}]
    # The chosen model is stored on the E32 and stays (a stored valve keeps its route and model).
    form = await room_form(manager, parent, "woonkamer")
    assert section_of(form)[0]["valves"][0].description["suggested_value"] == [aqara, bosch, zha]
    assert "- Kraan raam: works without Home Assistant (Zigbee2MQTT)" in form["description_placeholders"]["valve_routes"]


@pytest.mark.asyncio
async def test_a_new_room_gets_its_valves_after_the_room_and_a_refusal_keeps_the_room(hass, manager, monkeypatch):
    zigbee = Zigbee(hass, monkeypatch)
    bosch = zigbee.valve("Kraan slaapkamer", "BTH-RA")
    e32 = E32WithValves()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    values = {**shown(form), "name": "Slaapkamer", "ha_sources": ["sensor.hal"],
              "valves": {"valves": [bosch], "control": False, "choose_models": False}}
    e32.valves.fail = HeatingPlanRejected(400, "unknown_room")
    result = await manager.async_configure(form["flow_id"], values)
    assert result["type"] == "form" and result["errors"] == {"base": "e32_valves_rejected"}, result
    assert result["description_placeholders"]["error"] == "unknown_room"
    assert [r["id"] for r in e32.plan["rooms"]] == ["woonkamer", "badkamer", "slaapkamer"]   # the room is stored
    assert result["description_placeholders"]["room_name"] == "Slaapkamer"                  # the form now edits it
    e32.valves.fail = None
    result = await manager.async_configure(result["flow_id"], values)
    assert result["type"] == "menu" and result["step_id"] == "e32_rooms_saved", result
    assert [r["id"] for r in e32.plan["rooms"]] == ["woonkamer", "badkamer", "slaapkamer"]   # no second room
    assert e32.valves.config["rooms"] == [{"room": "slaapkamer", "control": False, "valves": [
        {"name": "Kraan slaapkamer", "model": "bosch_bth_ra"}]}]


@pytest.mark.asyncio
async def test_firmware_without_valves_shows_the_room_form_without_them(hass, manager):
    e32 = E32WithValves()
    e32.valves.missing = True
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent, "woonkamer")
    assert form["step_id"] == "e32_room" and "valves" not in [str(k) for k in form["data_schema"].schema]
    result = await manager.async_configure(form["flow_id"], {**shown(form), "name": "Woonkamer beneden"})
    assert result["type"] == "menu" and e32.plan["rooms"][0]["name"] == "Woonkamer beneden"
    assert [c for c in e32.valves.calls if c is not None] == []


# -- the dashboard ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_dashboard_shows_the_valve_opening_and_a_problem_badge_only_for_rooms_with_valves(hass):
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from custom_components.open_thermostat.dashboard import RoomDashboard
    from test_dashboard_heating import installation
    e, rooms, _, _, _ = installation(hass)
    before = json.dumps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config())
    assert "valve" not in before                                   # no valves: the dashboard as before
    device = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    made = {key: er.async_get(hass).async_get_or_create(domain, "open_thermostat", f"fixture_e32_room_woonkamer_{key}",
                                                        config_entry=e, device_id=device.id,
                                                        suggested_object_id=f"woonkamer_{key}").entity_id
            for domain, key in (("sensor", "valve_position"), ("binary_sensor", "valve_problem"), ("switch", "valve_control"))}
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    sections = {s["cards"][0]["heading"]: s for s in config["views"][0]["sections"]}
    living = sections["Woonkamer"]["cards"]
    tile = next(c for c in living if c.get("entity") == made["valve_position"])
    assert tile["type"] == "tile" and tile["name"] == "Valves open" and tile["icon"] == "mdi:valve"
    badge = next(b for b in living[0]["badges"] if b["entity"] == made["valve_problem"])
    assert badge["visibility"] == [{"condition": "state", "entity": made["valve_problem"], "state": "on"}]
    assert "valve" not in json.dumps(sections["Badkamer"])           # the bathroom has no valves


@pytest.mark.parametrize("text, model", [
    ("Bosch Radiator thermostat II BTH-RA", "bosch_bth_ra"),
    ("SONOFF Zigbee thermostatic radiator valve TRV-ZBT", "sonoff_trv_zbt"),
    ("SONOFF Zigbee thermostatic radiator valve TRVZB", "sonoff_trvzb"),
    ("TuYa Radiator valve TV02-Zigbee", "tuya_tv02"),
    ("Aqara Radiator thermostat E1 SRTS-A01", None),
    ("Bosch Room thermostat II BTH-RM", None),              # a wall thermostat, no radiator valve
])
def test_the_valve_model_is_guessed_from_the_zigbee2mqtt_device(text, model):
    assert module.guess_model(text) == model
    assert model is None or model in module.MODELS
