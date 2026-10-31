"""Configure's menu structure (beta.19): one place per subject, in the order a user needs it.

- An E32 install: Rooms, Comfort, Heating and boiler, Energy, Connect E32, Name and
  dashboard, Advanced (status and repairs at the bottom).
- A new installation before its E32 is connected: Connect E32 first, no older
  Home Assistant "Add room" button (that route led to a room that had to be removed later).
- After Connect E32 without rooms the same dialog goes on to the first room.
- Every menu entry has a label in English, Dutch and Polish.
"""
import asyncio
import json
from pathlib import Path

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.open_thermostat import controller_setup_flow as setup
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.product import PRODUCT_CONFIG
from custom_components.open_thermostat.product_flow import ProductRoomFlow, main_menu
from custom_components.open_thermostat.room_plan import ROOMS_ON_E32, has_room_plan, uses_e32_rooms
from test_e32_room_flow import CREDENTIALS, manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import PLAN, FakeE32
from test_v1_native import entry, room

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
# beta.23: Home holds presence, heating and boiler, and energy (the same order as the E32's Home page).
E32_MENU = ["e32_rooms", "house", "comfort", "controller_connection", "general", "advanced_settings"]


def new_installation(hass):
    """An entry as the beta.19 config flow creates it, before Connect E32."""
    parent = entry(hass)
    hass.config_entries.async_update_entry(parent, data={**parent.data, PRODUCT_CONFIG: 1, ROOMS_ON_E32: True})
    hass.data.setdefault("open_thermostat", {})[parent.entry_id] = {}
    return parent

async def connect_through_the_form(hass, manager, parent, monkeypatch, room_ids):
    """Configure -> Connect E32 with a connection that finishes when released (no device I/O)."""
    release = asyncio.Event()

    async def connect(h, entry_, address, password):
        await release.wait()
        return {"room_ids": room_ids}

    monkeypatch.setattr(setup, "async_connect_installation", connect)
    flow = await manager.async_init(parent.entry_id)
    form = await manager.async_configure(flow["flow_id"], {"next_step_id": "controller_connection"})
    progress = await manager.async_configure(form["flow_id"], {"address": "http://192.168.1.206",
                                                               "password": "secret"})
    assert progress["type"] == FlowResultType.SHOW_PROGRESS
    release.set()
    await hass.async_block_till_done()
    assert manager._progress[form["flow_id"]].cur_step["type"] is FlowResultType.SHOW_PROGRESS_DONE
    return await manager.async_configure(form["flow_id"])


@pytest.mark.asyncio
async def test_a_typical_e32_install_has_rooms_first_and_advanced_last(hass, manager):
    parent, _ = product(hass, FakeE32())
    assert has_room_plan(parent) and main_menu(parent) == E32_MENU
    flow = await manager.async_init(parent.entry_id)
    assert flow["type"] == FlowResultType.MENU and flow["menu_options"] == E32_MENU
    # The legacy "Manage rooms" and the old installation form are not in the main menu.
    assert "room_settings" not in flow["menu_options"] and "installation" not in flow["menu_options"]
    advanced = await manager.async_configure(flow["flow_id"], {"next_step_id": "advanced_settings"})
    assert advanced["menu_options"] == ["hot_water"]  # no older HA rooms: nothing about them


@pytest.mark.asyncio
async def test_rooms_hold_the_rooms_and_heating_and_boiler_opens_the_flow_limits(hass, manager):
    parent, _ = product(hass, FakeE32())
    await hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    rooms = await manager.async_configure(flow["flow_id"], {"next_step_id": "e32_rooms"})
    assert rooms["menu_options"] == ["e32_room_add", "e32_room_pick"]
    flow = await manager.async_init(parent.entry_id)
    house = await manager.async_configure(flow["flow_id"], {"next_step_id": "house"})
    assert house["type"] == FlowResultType.MENU and house["menu_options"] == ["house_presence", "heating_boiler", "energy"]
    form = await manager.async_configure(house["flow_id"], {"next_step_id": "heating_boiler"})
    assert form["type"] == FlowResultType.FORM and form["step_id"] == "e32_flow_limits", form


@pytest.mark.asyncio
async def test_home_presence_takes_several_people_and_the_away_delay(hass, manager):
    parent, _ = product(hass, FakeE32())
    await hass.async_block_till_done()
    hass.states.async_set("person.anna", "home")
    hass.states.async_set("person.ben", "not_home")
    flow = await manager.async_init(parent.entry_id)
    house = await manager.async_configure(flow["flow_id"], {"next_step_id": "house"})
    form = await manager.async_configure(house["flow_id"], {"next_step_id": "house_presence"})
    assert form["type"] == FlowResultType.FORM and form["step_id"] == "house_presence"
    assert {str(k) for k in form["data_schema"].schema} == {"presence_entities", "away_delay"}
    error = await manager.async_configure(form["flow_id"], {"presence_entities": ["person.nobody"], "away_delay": 15})
    assert error["errors"] == {"presence_entities": "presence_entity_invalid"}
    result = await manager.async_configure(form["flow_id"], {"presence_entities": ["person.anna", "person.ben"],
                                                             "away_delay": 10})
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "presence_saved"
    comfort = parent.options["comfort_settings"]
    assert comfort["presence_entities"] == ["person.anna", "person.ben"] and comfort["away_delay_min"] == 10


@pytest.mark.asyncio
async def test_name_and_dashboard_only_change_the_name_and_the_dashboard(hass, manager):
    parent, _ = product(hass, FakeE32())
    data, subentries = dict(parent.data), dict(parent.subentries)
    flow = await manager.async_init(parent.entry_id)
    form = await manager.async_configure(flow["flow_id"], {"next_step_id": "general"})
    assert form["step_id"] == "general"
    assert {str(k) for k in form["data_schema"].schema} == {"name", "create_dashboard"}
    error = await manager.async_configure(form["flow_id"], {"name": "  "})
    assert error["errors"] == {"name": "invalid_name"}
    result = await manager.async_configure(form["flow_id"], {"name": "Thuis", "create_dashboard": True})
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "installation_saved"
    assert parent.title == "Thuis" and parent.options["create_dashboard"] is True
    assert dict(parent.data) == data and dict(parent.subentries) == subentries


@pytest.mark.asyncio
async def test_a_new_installation_starts_with_connect_e32_and_offers_no_older_room_route(hass, manager):
    parent = new_installation(hass)
    assert uses_e32_rooms(parent) and not has_room_plan(parent)
    assert OpenThermostatConfigFlow.async_get_supported_subentry_types(parent) == {}
    flow = await manager.async_init(parent.entry_id)
    assert flow["menu_options"] == ["controller_connection", "energy", "general", "advanced_settings"]
    # A cached "Add room" button explains the way instead of starting the older wizard.
    room_flow = ProductRoomFlow()
    room_flow.hass, room_flow.handler = hass, (parent.entry_id, "zone")
    room_flow.context = {"source": "user"}
    result = await room_flow.async_step_user()
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "e32_connect_first"
    # An older entry (no marker) keeps its Home Assistant room route, unchanged.
    older = entry(hass, room=room(hass))
    hass.config_entries.async_update_entry(older, data={**older.data, PRODUCT_CONFIG: 1})
    assert not uses_e32_rooms(older)
    assert list(OpenThermostatConfigFlow.async_get_supported_subentry_types(older)) == ["zone"]
    assert main_menu(older)[0] == "room_settings"


@pytest.mark.asyncio
async def test_after_connect_e32_without_rooms_the_dialog_goes_on_to_the_first_room(hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32({**PLAN, "rooms": []}))
    connected = await connect_through_the_form(hass, manager, parent, monkeypatch, [])
    assert connected["step_id"] == "controller_connected_first_room", connected
    room_form = await manager.async_configure(connected["flow_id"], {})
    assert room_form["type"] == FlowResultType.FORM and room_form["step_id"] == "e32_room", room_form


@pytest.mark.asyncio
async def test_after_connect_e32_with_rooms_the_dialog_closes_as_before(hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32())
    connected = await connect_through_the_form(hass, manager, parent, monkeypatch, ["woonkamer"])
    assert connected["step_id"] == "controller_connected", connected
    done = await manager.async_configure(connected["flow_id"], {})
    assert done["reason"] == "controller_connection_complete"


@pytest.mark.parametrize("filename", ["strings.json", "translations/en.json", "translations/nl.json",
                                      "translations/pl.json"])
def test_every_menu_entry_and_new_step_has_a_label(filename):
    document = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))
    steps = document["options"]["step"]
    for option in E32_MENU + ["room_settings", "installation"]:
        assert steps["init"]["menu_options"][option].strip(), option
    for option in ("configuration_status", "installation", "hot_water", "graph_prepare", "graph_status",
                   "legacy_rooms"):
        assert steps["advanced_settings"]["menu_options"][option].strip(), option
    assert "e32_flow_limits" not in steps["e32_rooms"]["menu_options"]
    assert set(steps["general"]["data"]) == {"name", "create_dashboard"}
    first = steps["controller_connected_first_room"]
    assert first["title"] and first["description"] and first["submit"]
    assert document["config"]["create_entry"]["e32_next_steps"].strip()
    assert document["config_subentries"]["zone"]["abort"]["e32_connect_first"].strip()
    # No internal words in what a user reads in the main menu.
    labels = " ".join(steps["init"]["menu_options"].values()).lower()
    for word in ("graph", "native", "shadow", "session", "profile"):
        assert word not in labels, word
    # The E32 menu path in the help texts is the new one (Settings, not System → Network).
    text = json.dumps(document, ensure_ascii=False)
    assert "System → Network" not in text and "Systeem → Netwerk" not in text and "System → Sieć" not in text
