"""E32 rooms: the HA options flow that adds, edits and removes rooms in the E32 room plan."""
from copy import deepcopy
import json
from pathlib import Path
import re
from unittest.mock import AsyncMock

import probatio as vol
import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import InvalidData, section
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat import e32_room_flow as module
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.controller_link import ControllerLinkError, HeatingPlanRejected
from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.e32_room_flow import format_program, parse_program, unique_room_id
from custom_components.open_thermostat.heating_link import HeatingHub, input_payload
from custom_components.open_thermostat.product import PRODUCT_CONFIG
from custom_components.open_thermostat.room_plan import RoomPlanLink, has_room_plan
from test_room_plan import PLAN, STATUS, FakeE32, _Failing, other_side
from test_v1_native import entry, room

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
CREDENTIALS = {CONTROLLER_ADDRESS: "http://192.168.1.206", CONTROLLER_PASSWORD: "secret"}
BLE = [{"id": "a4c138a3e8db", "name": "Slaapkamer", "profile": "atc", "temperature": 19.4},
       {"id": "112233445566", "name": "Zolder", "profile": "atc", "temperature": 17.0}]
MENU = ["installation", "controller_connection", "e32_rooms", "configuration_status", "energy", "advanced_settings"]


@pytest.fixture
def manager(hass, monkeypatch):
    monkeypatch.setattr(config_entries, "_async_get_flow_handler", AsyncMock(return_value=OpenThermostatConfigFlow))
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.1, "temperature": 20.5})
    hass.states.async_set("climate.no_reading", "heat", {"temperature": 20})
    hass.states.async_set("sensor.hal", "19.2", {"device_class": "temperature", "unit_of_measurement": "°C"})
    hass.states.async_set("sensor.gang", "18.7", {"device_class": "temperature", "unit_of_measurement": "°C"})
    hass.states.async_set("sensor.zolder_f", "64", {"device_class": "temperature", "unit_of_measurement": "°F"})
    hass.states.async_set("input_number.badkamer_doel", "21", {"unit_of_measurement": "°C"})
    return hass.config_entries.options


def product(hass, e32, *, credentials=True, binding=None):
    parent = entry(hass, room=binding)
    hass.config_entries.async_update_entry(parent, data={
        **parent.data, PRODUCT_CONFIG: 1, **(CREDENTIALS if credentials else {})})
    hub = HeatingHub("fixture")
    hub.plan = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    hub.plan._client = lambda: e32.client("http://192.168.1.206")
    hub.update({**STATUS, "ble_sensors": BLE})
    hass.data.setdefault("open_thermostat", {})[parent.entry_id] = {"heating_hub": hub}
    return parent, hub


async def rooms_menu(manager, parent):
    await manager.hass.async_block_till_done()  # the hub's own plan read after its first status
    flow = await manager.async_init(parent.entry_id)
    assert flow["menu_options"] == MENU
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_rooms"})
    assert flow["type"] == "menu" and flow["step_id"] == "e32_rooms", flow
    return flow


async def room_form(manager, parent, room_id=None):
    flow = await rooms_menu(manager, parent)
    if room_id is None:
        return await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_room_add"})
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_room_pick"})
    assert flow["step_id"] == "e32_room_pick"
    return await manager.async_configure(flow["flow_id"], {"room": room_id, "action": "edit"})


def shown(form):
    """The values the form shows (defaults and suggestions), as the frontend would submit them."""
    def values(schema):
        result = {}
        for marker, value in schema.schema.items():
            if isinstance(value, section):
                result[str(marker)] = values(value.schema)
                continue
            suggested = (marker.description or {}).get("suggested_value")
            if suggested is not None:
                result[str(marker)] = suggested
            elif marker.default is not vol.UNDEFINED:
                result[str(marker)] = marker.default()
        return result
    return values(form["data_schema"])


NEW_ROOM = {"name": "Slaapkamer Zoë", "state": "active", "emitter": "radiator",
            "ha_sources": ["sensor.hal", "climate.woonkamer"], "ble_sources": ["a4c138a3e8db"],
            "bluetooth_first": True, "setpoint_entity": "input_number.badkamer_doel", "fallback_temperature": 19,
            "program": "mon-fri: 06:30 20.5, 22:30 18\nsat,sun: 08:00 20,5; 23:00 18",
            "limits": {"minimum_temperature": 10, "maximum_temperature": 24}}


@pytest.mark.asyncio
async def test_a_room_with_home_assistant_and_bluetooth_sources_is_added_to_the_e32_plan(hass, manager):
    e32 = FakeE32()
    parent, hub = product(hass, e32)
    menu = await rooms_menu(manager, parent)
    assert menu["menu_options"] == ["e32_room_add", "e32_room_pick"]
    assert menu["description_placeholders"]["revision"] == "4"
    assert "- Woonkamer: climate.woonkamer, Bluetooth Slaapkamer (a4c138a3e8db)" in menu["description_placeholders"]["rooms"]
    form = await manager.async_configure(menu["flow_id"], {"next_step_id": "e32_room_add"})
    assert form["step_id"] == "e32_room"
    keys = [str(k) for k in form["data_schema"].schema]
    assert keys == ["name", "state", "emitter", "ha_sources", "ble_sources", "bluetooth_first",
                    "setpoint_entity", "fallback_temperature", "program", "limits"]
    ble = next(v for k, v in form["data_schema"].schema.items() if str(k) == "ble_sources")
    assert [o["value"] for o in ble.config["options"]] == ["a4c138a3e8db", "112233445566"]
    assert ble.config["options"][0]["label"] == "Slaapkamer (a4c138a3e8db) 19.4 °C"
    sources = next(v for k, v in form["data_schema"].schema.items() if str(k) == "ha_sources")
    assert sources.config["reorder"] and sources.config["multiple"]
    posts = len(e32.posts)
    result = await manager.async_configure(form["flow_id"], NEW_ROOM)
    assert result["type"] == "abort" and result["reason"] == "e32_room_saved", result
    assert result["description_placeholders"] == {"name": "Slaapkamer Zoë"}
    assert len(e32.posts) == posts + 1 and e32.posts[-1]["revision"] == 4
    assert e32.plan["rooms"][:2] == PLAN["rooms"]  # the other rooms travel back unchanged
    assert e32.plan["rooms"][2] == {
        "id": "slaapkamer_zoe", "name": "Slaapkamer Zoë", "state": "active", "inactive_until": 0,
        "emitter": "radiator",
        "sources": [{"type": "ble", "id": "a4c138a3e8db"}, {"type": "ha", "id": "sensor.hal"},
                    {"type": "ha", "id": "climate.woonkamer"}],
        "setpoint_entity": "input_number.badkamer_doel", "fallback_centi_c": 1900,
        "minimum_centi_c": 1000, "maximum_centi_c": 2400,
        "schedule": [[[390, 2050], [1350, 1800]]] * 5 + [[[480, 2050], [1380, 1800]]] * 2}
    assert hub.plan.plan == e32.plan  # the writer's cache follows the stored plan

    # The same name again gets its own id; a room without a program has no schedule key.
    form = await room_form(manager, parent)
    result = await manager.async_configure(form["flow_id"], {
        **NEW_ROOM, "ble_sources": [], "program": "", "bluetooth_first": False})
    assert result["reason"] == "e32_room_saved", result
    added = e32.plan["rooms"][3]
    assert added["id"] == "slaapkamer_zoe_2" and "schedule" not in added
    assert added["sources"] == [{"type": "ha", "id": "sensor.hal"}, {"type": "ha", "id": "climate.woonkamer"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("sources,error", [
    (["sensor.zolder_f"], "e32_source_not_celsius"),
    (["climate.no_reading"], "e32_source_no_temperature"),
    (["sensor.missing"], "e32_source_not_found"),
    (["sensor." + "x" * 80], "e32_source_invalid_id"),
])
async def test_a_source_the_e32_cannot_read_is_refused_with_a_clear_message(hass, manager, sources, error):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    posts = len(e32.posts)
    form = await manager.async_configure(form["flow_id"], {**NEW_ROOM, "ha_sources": sources, "ble_sources": []})
    assert form["type"] == "form" and form["errors"] == {"ha_sources": error}, form
    assert form["description_placeholders"]["source"] == sources[0]
    assert len(e32.posts) == posts
    # The form keeps what was entered; a corrected source saves.
    assert shown(form)["name"] == "Slaapkamer Zoë"
    result = await manager.async_configure(form["flow_id"], {**NEW_ROOM, "ha_sources": ["sensor.hal"]})
    assert result["reason"] == "e32_room_saved", result


@pytest.mark.asyncio
async def test_fahrenheit_home_assistant_climate_and_setpoints_are_refused(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    hass.states.async_set("input_number.doel_f", "70", {"unit_of_measurement": "°F"})
    form = await room_form(manager, parent)
    form = await manager.async_configure(form["flow_id"], {**NEW_ROOM, "setpoint_entity": "input_number.doel_f"})
    assert form["errors"] == {"setpoint_entity": "e32_source_not_celsius"}
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
    hass.config.units = US_CUSTOMARY_SYSTEM
    form = await manager.async_configure(form["flow_id"], {**NEW_ROOM, "ha_sources": ["climate.woonkamer"]})
    assert form["errors"] == {"ha_sources": "e32_source_not_celsius"}


@pytest.mark.asyncio
async def test_own_e32_entities_are_not_offered_as_home_assistant_sources(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    registry = er.async_get(hass)
    own = registry.async_get_or_create("sensor", "open_thermostat", "fixture_e32_ble_a4c138a3e8db_temperature",
                                       config_entry=parent, suggested_object_id="slaapkamer_bluetooth")
    hass.states.async_set(own.entity_id, "19.4", {"device_class": "temperature", "unit_of_measurement": "°C"})
    form = await room_form(manager, parent)
    sources = next(v for k, v in form["data_schema"].schema.items() if str(k) == "ha_sources")
    assert sources.config["exclude_entities"] == [own.entity_id]
    with pytest.raises(InvalidData):
        await manager.async_configure(form["flow_id"], {**NEW_ROOM, "ha_sources": [own.entity_id]})


@pytest.mark.asyncio
@pytest.mark.parametrize("change,field,error", [
    ({"name": "  "}, "name", "e32_name_invalid"),
    ({"name": "Ä" * 21}, "name", "e32_name_invalid"),  # 42 bytes: the E32 counts UTF-8 bytes
    ({"ha_sources": [], "ble_sources": []}, "base", "e32_sources_count"),
    ({"ha_sources": ["sensor.hal", "climate.woonkamer"], "ble_sources": ["a4c138a3e8db", "112233445566"],
      "setpoint_entity": None}, None, None),
    ({"ha_sources": ["sensor.hal", "climate.woonkamer", "sensor.gang"],
      "ble_sources": ["a4c138a3e8db", "112233445566"]}, "base", "e32_sources_count"),
    ({"fallback_temperature": 25}, "fallback_temperature", "e32_limits_invalid"),
    ({"limits": {"minimum_temperature": 22, "maximum_temperature": 18}}, "fallback_temperature", "e32_limits_invalid"),
    ({"program": "07:00 26"}, "program", "e32_program_outside_limits"),
    ({"program": "7 uur 20"}, "program", "e32_program_invalid"),
    ({"program": "mon: 07:00 20\nmon-tue: 08:00 19"}, "program", "e32_program_invalid"),
    ({"program": ", ".join(f"{h:02d}:00 20" for h in range(7))}, "program", "e32_program_too_many"),
])
async def test_room_fields_are_checked_before_the_plan_is_written(hass, manager, change, field, error):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    posts = len(e32.posts)
    submitted = {key: value for key, value in {**NEW_ROOM, **change}.items() if value is not None}
    result = await manager.async_configure(form["flow_id"], submitted)
    if error is None:
        assert result["reason"] == "e32_room_saved" and len(e32.plan["rooms"][-1]["sources"]) == 4
        assert e32.plan["rooms"][-1]["setpoint_entity"] == ""
        return
    assert result["errors"] == {field: error}, result
    assert len(e32.posts) == posts


@pytest.mark.asyncio
async def test_editing_changes_only_the_edited_fields_and_sources_can_be_reordered_or_removed(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent, "woonkamer")
    values = shown(form)
    assert values == {"name": "Woonkamer", "state": "active", "emitter": "floor",
                      "ha_sources": ["climate.woonkamer"], "ble_sources": ["a4c138a3e8db"], "bluetooth_first": False,
                      "setpoint_entity": "climate.woonkamer", "fallback_temperature": 20.0,
                      "limits": {"minimum_temperature": 10.0, "maximum_temperature": 24.0}}
    posts = len(e32.posts)
    result = await manager.async_configure(form["flow_id"], values)
    assert result["reason"] == "e32_room_unchanged" and len(e32.posts) == posts  # nothing written

    # Bluetooth first: the same two sources in the other order.
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "bluetooth_first": True})
    assert result["reason"] == "e32_room_saved"
    expected = deepcopy(PLAN["rooms"][0])
    expected["sources"] = [{"type": "ble", "id": "a4c138a3e8db"}, {"type": "ha", "id": "climate.woonkamer"}]
    assert e32.plan["rooms"][0] == expected and e32.plan["rooms"][1] == PLAN["rooms"][1]

    # Drop the Bluetooth sensor, add the hall sensor in front, rename and pause the room.
    form = await room_form(manager, parent, "woonkamer")
    assert shown(form)["bluetooth_first"] is True
    e32.plan["rooms"][0]["inactive_until"] = 1900000000  # stays unless the state changes
    result = await manager.async_configure(form["flow_id"], {
        **shown(form), "ha_sources": ["sensor.hal", "climate.woonkamer"], "ble_sources": [], "name": "Huiskamer"})
    assert result["reason"] == "e32_room_saved"
    room_ = e32.plan["rooms"][0]
    assert room_["id"] == "woonkamer" and room_["name"] == "Huiskamer"  # the id (and its entities) stay
    assert room_["sources"] == [{"type": "ha", "id": "sensor.hal"}, {"type": "ha", "id": "climate.woonkamer"}]
    assert room_["inactive_until"] == 1900000000
    form = await room_form(manager, parent, "woonkamer")
    result = await manager.async_configure(form["flow_id"], {**shown(form), "state": "inactive", "program": "07:00 21"})
    assert result["reason"] == "e32_room_saved"
    room_ = e32.plan["rooms"][0]
    assert (room_["state"], room_["inactive_until"], room_["schedule"]) == ("inactive", 0, [[[420, 2100]]] * 7)
    # Clearing the program removes the schedule: fallback only.
    form = await room_form(manager, parent, "woonkamer")
    assert shown(form)["program"] == "07:00 21"
    values = shown(form)
    del values["program"]
    result = await manager.async_configure(form["flow_id"], values)
    assert result["reason"] == "e32_room_saved" and "schedule" not in e32.plan["rooms"][0]


@pytest.mark.asyncio
async def test_a_stale_revision_is_read_again_and_the_same_edit_applied_once(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent, "woonkamer")
    other_side("emitter", "radiator", room="woonkamer")(e32.plan)  # saved on the E32 page while the form was open
    e32.before_save.append(other_side("fallback_centi_c", 1800))  # badkamer, saved between our read and write
    posts, reads = len(e32.posts), e32.reads
    result = await manager.async_configure(form["flow_id"], {**shown(form), "name": "Huiskamer"})
    assert result["reason"] == "e32_room_saved", result
    assert len(e32.posts) == posts + 2 and e32.reads == reads + 2
    assert [p["revision"] for p in e32.posts[-2:]] == [5, 6]
    rooms = {r["id"]: r for r in e32.plan["rooms"]}
    # Both concurrent changes survive; only the name was ours.
    assert rooms["woonkamer"]["name"] == "Huiskamer" and rooms["woonkamer"]["emitter"] == "radiator"
    assert rooms["badkamer"]["fallback_centi_c"] == 1800 and e32.plan["revision"] == 7

    # A second conflict: nothing saved, a clear error and the form stays open.
    form = await room_form(manager, parent, "woonkamer")
    e32.before_save += [other_side("state", "inactive"), other_side("state", "active")]
    result = await manager.async_configure(form["flow_id"], {**shown(form), "name": "Woonkamer"})
    assert result["type"] == "form" and result["errors"] == {"base": "e32_plan_changed"}
    assert {r["id"]: r for r in e32.plan["rooms"]}["woonkamer"]["name"] == "Huiskamer"


@pytest.mark.asyncio
async def test_a_room_added_twice_at_once_gets_unique_ids_after_the_re_read(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)

    def other_add(plan):
        plan["rooms"].append({**deepcopy(PLAN["rooms"][1]), "id": "slaapkamer_zoe", "name": "Slaapkamer Zoë"})
        plan["revision"] += 1
    e32.before_save.append(other_add)
    result = await manager.async_configure(form["flow_id"], NEW_ROOM)
    assert result["reason"] == "e32_room_saved"
    assert [r["id"] for r in e32.plan["rooms"]] == ["woonkamer", "badkamer", "slaapkamer_zoe", "slaapkamer_zoe_2"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,kind,key", [
    (HeatingPlanRejected(413, "plan_too_large"), "form", "e32_plan_too_large"),
    (HeatingPlanRejected(400, "invalid_room_limits"), "form", "e32_rejected"),
    (ControllerLinkError("controller_unreachable"), "form", "e32_unreachable"),
    (HeatingPlanRejected(503, "save_unconfirmed"), "abort", "e32_unconfirmed"),
])
async def test_refusals_are_clear_messages_without_a_retry(hass, manager, failure, kind, key):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await room_form(manager, parent)
    posts = len(e32.posts)
    e32.fail = failure
    result = await manager.async_configure(form["flow_id"], NEW_ROOM)
    assert result["type"] == kind, result
    assert (result["errors"] == {"base": key}) if kind == "form" else (result["reason"] == key)
    assert len(e32.posts) == posts + 1 and len(e32.plan["rooms"]) == 2
    if key == "e32_rejected":
        assert result["description_placeholders"]["error"] == "invalid_room_limits"


@pytest.mark.asyncio
async def test_a_room_is_removed_after_confirmation_and_the_others_stay(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    flow = await rooms_menu(manager, parent)
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_room_pick"})
    flow = await manager.async_configure(flow["flow_id"], {"room": "badkamer", "action": "remove"})
    assert flow["step_id"] == "e32_room_remove" and flow["description_placeholders"]["name"] == "Badkamer"
    e32.before_save.append(other_side("fallback_centi_c", 1900, room="woonkamer"))
    result = await manager.async_configure(flow["flow_id"], {"confirm_remove": True})
    assert result["reason"] == "e32_room_removed", result
    assert [r["id"] for r in e32.plan["rooms"]] == ["woonkamer"]
    assert e32.plan["rooms"][0]["fallback_centi_c"] == 1900  # the concurrent change survived the retry

    flow = await rooms_menu(manager, parent)
    flow = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_room_pick"})
    flow = await manager.async_configure(flow["flow_id"], {"room": "woonkamer", "action": "remove"})
    posts = len(e32.posts)
    result = await manager.async_configure(flow["flow_id"], {"confirm_remove": False})
    assert result["reason"] == "cancelled" and len(e32.posts) == posts


@pytest.mark.asyncio
async def test_menu_offers_no_add_with_eight_rooms_and_an_unreachable_e32_aborts(hass, manager):
    e32 = FakeE32({**PLAN, "rooms": [{**PLAN["rooms"][0], "id": f"room_{n}"} for n in range(8)]})
    parent, hub = product(hass, e32)
    menu = await rooms_menu(manager, parent)
    assert menu["menu_options"] == ["e32_room_pick"]
    attempts = []
    hub.plan._client = lambda: _Failing(attempts)
    flow = await manager.async_init(parent.entry_id)
    result = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_rooms"})
    assert result["type"] == "abort" and result["reason"] == "e32_unreachable"
    assert result["description_placeholders"]["error"] == "controller_unreachable"


@pytest.mark.asyncio
async def test_without_a_stored_e32_connection_the_older_room_settings_stay(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32, credentials=False)
    assert not has_room_plan(parent)
    flow = await manager.async_init(parent.entry_id)
    assert "room_settings" in flow["menu_options"] and "e32_rooms" not in flow["menu_options"]
    from custom_components.open_thermostat.product_flow import ProductOptionsFlow
    handler = ProductOptionsFlow()
    handler.hass, handler.handler = hass, parent.entry_id
    result = await handler.async_step_e32_rooms()
    assert result["type"] == "abort" and result["reason"] == "e32_rooms_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("credentials", [True, False])
async def test_dashboard_has_no_old_room_settings_view_when_the_e32_plan_is_the_editor(hass, credentials):
    parent, _ = product(hass, FakeE32(), credentials=credentials, binding=room(hass))
    from custom_components.open_thermostat.dashboard import view_cards
    config = RoomDashboard(hass, "fixture", parent.entry_id)._dashboard_config()
    paths = [view["path"] for view in config["views"]]
    buttons = [card["name"] for card in view_cards(config["views"][0]) if card["type"] == "button"]
    assert "room-a1b2c3d4" in paths  # the old record's own subview, linked from its reconfigure dialog
    if credentials:
        assert "week" not in paths and buttons == ["Set up rooms"]
    else:
        assert "week" in paths and buttons == ["room settings"]


def test_program_text_round_trips_and_accepts_dutch_days():
    week = [[[390, 2050], [1350, 1800]]] * 5 + [[[480, 2050], [1380, 1800]]] * 2
    assert format_program(week) == "mon-fri: 06:30 20.5, 22:30 18\nsat-sun: 08:00 20.5, 23:00 18"
    assert format_program(week, "nl") == "ma-vr: 06:30 20.5, 22:30 18\nza-zo: 08:00 20.5, 23:00 18"
    for text in (format_program(week), format_program(week, "nl"),
                 "ma-vr: 22:30 18; 06:30 20,5\nzaterdag, zondag: 08.00 20,5, 23:00 18"):
        assert parse_program(text, 500, 3000) == week
    odd = [[[0, 1855]], [], [[420, 2100]], [], [], [], [[420, 2100]]]
    assert format_program(odd) == "mon: 00:00 18.55\nwed,sun: 07:00 21"
    assert parse_program(format_program(odd), 500, 3000) == odd
    assert parse_program("sat-mon: 07:00 20", 500, 3000) == [[[420, 2000]], [], [], [], [], [[420, 2000]], [[420, 2000]]]
    assert parse_program("  \n", 500, 3000) is None and format_program(None) == ""
    for bad in ("24:00 20", "07:60 20", "07:00 20, 07:00 21", "07:00", "mon 07:00 20", "foo: 07:00 20", "07:00 20 x"):
        with pytest.raises(module.FlowError) as error:
            parse_program(bad, 500, 3000)
        assert error.value.key == "e32_program_invalid", bad


def test_room_ids_come_from_the_name_and_are_unique():
    assert unique_room_id("Woonkamer", set()) == "woonkamer"
    assert unique_room_id("Woonkamer", {"woonkamer", "woonkamer_2"}) == "woonkamer_3"
    assert unique_room_id("🙂", set()) == "room"
    long = unique_room_id("Een heel erg lange naam voor een kamer", set())
    assert len(long) <= 32 and re.fullmatch(r"[a-z0-9_]{1,32}", long)
    taken = {long}
    assert len(unique_room_id("Een heel erg lange naam voor een kamer", taken)) <= 32


def test_a_number_setpoint_entity_is_forwarded_as_its_target():
    from types import SimpleNamespace
    state = SimpleNamespace(entity_id="input_number.badkamer_doel", domain="input_number", state="21.5", attributes={})
    assert json.loads(input_payload(state)) == {"entity": "input_number.badkamer_doel", "temperature": None, "target": 21.5}
    assert input_payload(SimpleNamespace(**{**vars(state), "state": "45"})) is None


@pytest.mark.parametrize("filename", ["strings.json", "translations/en.json", "translations/nl.json"])
def test_every_flow_key_has_a_translation(filename):
    document = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))
    options = document["options"]
    source = (COMPONENT / "e32_room_flow.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'"(e32_[a-z_]+)"', source)) - {"e32_room_flow"}
    steps = {"e32_rooms", "e32_room", "e32_room_add", "e32_room_pick", "e32_room_remove"}
    selectors = {"e32_room_state", "e32_room_emitter", "e32_room_action"}
    for key in keys - steps - selectors:
        assert key in options["error"] or key in options["abort"], key
    for key in selectors:
        assert document["selector"][key]["options"], key
    assert set(options["step"]["e32_rooms"]["menu_options"]) == {"e32_room_add", "e32_room_pick"}
    assert options["step"]["init"]["menu_options"]["e32_rooms"]
    room_step = options["step"]["e32_room"]
    assert set(room_step["data"]) == {"name", "state", "emitter", "ha_sources", "ble_sources", "bluetooth_first",
                                      "setpoint_entity", "fallback_temperature", "program"}
    assert set(room_step["sections"]["limits"]["data"]) == {"minimum_temperature", "maximum_temperature"}
    assert document["exceptions"]["room_plan_too_large"]["message"]
