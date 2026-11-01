"""Radiator valves per E32 room (E32 beta.24) in Home Assistant: telemetry, entities, Repairs, the control switch."""
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


# -- the room settings step ------------------------------------------------------------------

from test_e32_room_flow import manager, product, rooms_menu  # noqa: E402,F401 - the fixture and helpers
from test_room_plan import FakeE32 as PlanE32  # noqa: E402


class E32WithValves(PlanE32):
    def __init__(self, config=None):
        super().__init__()
        self.valves = FakeE32(config or {"schema": 1, "base_topic": "zigbee2mqtt", "rooms": []})

    def client(self, address):
        client = super().client(address)
        client.async_valves = self.valves.client(address).async_valves
        return client


async def valves_form(manager, parent, room_id="woonkamer"):
    flow = await rooms_menu(manager, parent)
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_room_pick"})
    return await manager.async_configure(flow["flow_id"], {"room": room_id, "action": "valves"})


@pytest.mark.asyncio
async def test_valves_are_chosen_in_the_room_settings_with_control_off_by_default(hass, manager):
    e32 = E32WithValves()
    parent, _ = product(hass, e32)
    form = await valves_form(manager, parent)
    assert form["type"] == "form" and form["step_id"] == "e32_room_valves", form
    defaults = {str(k): k.default() for k in form["data_schema"].schema if hasattr(k, "default") and callable(k.default)}
    assert defaults["control"] is False
    result = await manager.async_configure(form["flow_id"], {"control": False, "valve_1": "Kraan woonkamer", "model_1": "bosch_bth_ra"})
    assert result["type"] == "menu" and result["step_id"] == "e32_rooms_saved", result
    assert e32.valves.config["rooms"] == [{"room": "woonkamer", "control": False,
                                           "valves": [{"name": "Kraan woonkamer", "model": "bosch_bth_ra"}]}]


@pytest.mark.asyncio
async def test_valve_names_are_checked_before_the_e32_is_written(hass, manager):
    e32 = E32WithValves({"schema": 1, "base_topic": "zigbee2mqtt",
                         "rooms": [{"room": "badkamer", "control": False, "valves": [{"name": "Kraan bad", "model": "generic"}]}]})
    parent, _ = product(hass, e32)
    for change, field, error in (({"valve_1": "a#b"}, "valve_1", "e32_valve_name_invalid"),
                                 ({"valve_1": "Kraan bad"}, "valve_1", "e32_valve_duplicate"),
                                 ({"valve_1": "K", "valve_2": "K"}, "valve_2", "e32_valve_duplicate")):
        form = await valves_form(manager, parent)
        result = await manager.async_configure(form["flow_id"], {"control": True, **change})
        assert result["type"] == "form" and result["errors"] == {field: error}, (change, result)
    assert [c for c in e32.valves.calls if c is not None] == []   # nothing was written


@pytest.mark.asyncio
async def test_firmware_without_valves_says_to_update_first(hass, manager):
    e32 = E32WithValves()
    e32.valves.missing = True
    parent, _ = product(hass, e32)
    result = await valves_form(manager, parent)
    assert result["type"] == "abort" and result["reason"] == "e32_valves_update_required"


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
    assert tile["type"] == "tile" and tile["name"] == "Radiator valves open" and tile["icon"] == "mdi:valve"
    badge = next(b for b in living[0]["badges"] if b["entity"] == made["valve_problem"])
    assert badge["visibility"] == [{"condition": "state", "entity": made["valve_problem"], "state": "on"}]
    assert "valve" not in json.dumps(sections["Badkamer"])           # the bathroom has no valves


@pytest.mark.parametrize("text, model", [
    ("Bosch Radiator thermostat II BTH-RA", "bosch_bth_ra"),
    ("SONOFF Zigbee thermostatic radiator valve TRV-ZBT", "sonoff_trv_zbt"),
    ("SONOFF Zigbee thermostatic radiator valve TRVZB", "sonoff_trvzb"),
    ("TuYa Radiator valve TV02-Zigbee", "tuya_tv02"),
    ("Aqara Radiator thermostat E1 SRTS-A01", None),
])
def test_the_valve_model_is_guessed_from_the_zigbee2mqtt_device(text, model):
    assert module.guess_model(text) == model
    assert model is None or model in module.MODELS
