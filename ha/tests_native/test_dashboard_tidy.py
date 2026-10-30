"""The Heating dashboard as the owner saw it on 30 Oct 2026, tidied: no "Unavailable" rows of tiles, no
"0,0 °C" request, no bare "98 %", an inactive room without a dial, whole names and no gap under "Now".

Shaped like the live installation: the living room follows a thermostat and a Bluetooth sensor, the
bathroom is inactive with a working source of its own (it stays off and is never switched on here).
"""
import json
from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from test_dashboard_heating import installation, walk

PLAN = {"rooms": [
    {"id": "woonkamer", "state": "active", "sources": [{"type": "ha", "id": "climate.tado_woonkamer"},
                                                       {"type": "ble", "id": "a4c138a3e8db"}]},
    {"id": "badkamer", "state": "inactive", "sources": [{"type": "ha", "id": "climate.thermostaat_badkamer"}]}]}


def known(entity_id):
    return {"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown"]}


def live(hass, language="en"):
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    for room_id in ("woonkamer", "badkamer"):
        device = devices.async_get_device_by_identifier(("open_thermostat", f"fixture_e32_room_{room_id}"), e.entry_id)
        for domain, key in (("climate", "thermostat"), ("sensor", "learning"), ("sensor", "flow_advice"),
                            ("sensor", "heating_start")):
            rooms[room_id][key] = entities.async_get_or_create(
                domain, "open_thermostat", f"fixture_e32_room_{room_id}_{key}", config_entry=e, device_id=device.id,
                suggested_object_id=f"{room_id}_{key}").entity_id
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    hub["heating_problem"] = entities.async_get_or_create(
        "binary_sensor", "open_thermostat", "fixture_hub_heating_problem", config_entry=e, device_id=product.id,
        suggested_object_id="heating_problem").entity_id
    flow = {key: entities.async_get_or_create(domain, "open_thermostat", f"fixture_flow_{key}", config_entry=e,
                                              device_id=product.id, suggested_object_id=f"flow_{key}").entity_id
            for domain, key in (("sensor", "source"), ("switch", "weather_curve"),
                                ("select", "curve_design_flow_c"), ("switch", "apply_learned"))}
    hass.states.async_set("climate.thermostaat_badkamer", "heat", {"current_temperature": 18.4, "temperature": 19})
    hass.data["open_thermostat"][e.entry_id]["heating_hub"].plan = SimpleNamespace(
        plan=PLAN, room=lambda room_id: next((r for r in PLAN["rooms"] if r["id"] == room_id), None))
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    return config, rooms, sensors, hub, fields, flow


def section(view, heading):
    return next(s["cards"] for s in view["sections"] if s["cards"][0].get("heading") == heading)


@pytest.mark.asyncio
async def test_boiler_values_are_hidden_while_they_have_none_instead_of_showing_unavailable(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    heating = config["views"][0]
    values = [fields[k] for k in ("measured_flow_temperature", "measured_dhw_temperature",
                                  "measured_return_temperature", "reported_burner_modulation", "pressure",
                                  "display_code")]
    tiles = {c["entity"]: c for c in view_cards(heating) if c["type"] == "tile" and c["entity"] in values}
    assert set(tiles) == set(values)
    for entity_id, tile in tiles.items():
        assert tile["visibility"] == [known(entity_id)], entity_id
    # The "Heating" status stays always visible: it says when the E32 has not reported.
    status = next(c for c in section(heating, "Now") if c.get("entity") == hub["heating_problem"])
    assert status["name"] == "Heating" and "visibility" not in status


@pytest.mark.asyncio
async def test_the_boiler_request_says_no_request_instead_of_zero_degrees(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    now = section(config["views"][0], "Now")
    request, idle = [c for c in now if c.get("entity") == hub["heat_request"]]
    assert request["name"] == "Boiler request (E32)" and "hide_state" not in request
    assert request["visibility"] == [{"condition": "numeric_state", "entity": hub["heat_request"], "above": 0}]
    assert (idle["name"], idle["icon"], idle["hide_state"]) == ("No boiler request", "mdi:fire-off", True)
    assert idle["visibility"] == [{"condition": "numeric_state", "entity": hub["heat_request"], "below": 0.1}]
    nl, *_ = live(hass, "nl")
    assert "Geen ketelvraag" in json.dumps(nl, ensure_ascii=False)


@pytest.mark.asyncio
async def test_the_comparison_is_a_link_that_explains_it_not_a_bare_percentage(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    now = section(config["views"][0], "Now")
    assert hub["shadow_agreement_today"] not in [c.get("entity") for c in now]
    link = next(c for c in now if c.get("heading") == "E32 compared with your thermostat")
    assert link["tap_action"]["navigation_path"].endswith("/comparison")
    # The subview names it in full.
    compare = config["views"][-1]["sections"][0]["cards"]
    agreement = next(c for c in compare if c.get("entity") == hub["shadow_agreement_today"])
    assert agreement["name"] == "Agreement with thermostat"


@pytest.mark.asyncio
async def test_an_inactive_room_is_compact_without_a_dial_or_learning_and_links_to_its_settings(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    bathroom = section(config["views"][0], "Badkamer")
    off = [{"condition": "state", "entity": rooms["badkamer"]["state"], "state": "inactive"}]
    on = {"condition": "state", "entity": rooms["badkamer"]["state"], "state_not": "inactive"}
    # Its own climate (which could switch it on) and its learning area only while it is on.
    dial = next(c for c in bathroom if c["type"] == "thermostat")
    assert dial == {"type": "thermostat", "entity": rooms["badkamer"]["thermostat"], "visibility": [on]}
    learning = [c for c in bathroom if rooms["badkamer"]["learning"] in json.dumps(c)
                or rooms["badkamer"]["flow_advice"] in json.dumps(c) or rooms["badkamer"]["heating_start"] in json.dumps(c)]
    assert learning and all(c["visibility"][0] == on for c in learning)
    # While off: the heading's "Off" badge, one calm line and a link to its settings; nothing to switch.
    shown_off = [c for c in bathroom if c.get("visibility") == off]
    assert [c["type"] for c in shown_off] == ["markdown", "heading"]
    assert shown_off[0]["content"] == "This room is off and never asks for heat."
    assert shown_off[1]["heading"] == "Badkamer settings"
    assert shown_off[1]["tap_action"] == {"action": "navigate",
                                          "navigation_path": "/config/integrations/integration/open_thermostat"}
    assert not any(c.get("features") for c in bathroom)
    assert "Choose a source" not in json.dumps(bathroom)  # its source works: no hint to choose one
    # The room that is on keeps its dial.
    living = section(config["views"][0], "Woonkamer")
    assert any(c["type"] == "thermostat" for c in living)


@pytest.mark.asyncio
async def test_the_humidity_badge_says_what_it_is(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    badge = next(b for b in section(config["views"][0], "Woonkamer")[0]["badges"] if b["entity"] == sensors["humidity"])
    assert (badge["name"], badge["icon"]) == ("Humidity", "mdi:water-percent")


@pytest.mark.asyncio
async def test_long_choices_get_the_whole_width_and_no_gap_is_left_under_now(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    heating = config["views"][0]
    assert heating["dense_section_placement"] is True
    settings = section(heating, "Heating curve and learning")
    design = next(c for c in settings if c.get("entity") == flow["curve_design_flow_c"])
    assert design["grid_options"] == {"columns": 12}
    assert all("grid_options" not in c for c in settings if c.get("entity") != flow["curve_design_flow_c"])


@pytest.mark.asyncio
async def test_rows_in_entities_cards_are_named_by_the_entity_alone(hass):
    """Without the device name in front ("E32 controller — boiler and diagnostics …") the names fit."""
    config, rooms, sensors, hub, fields, flow = live(hass)
    rows = [row for view in config["views"] for card in view_cards(view) if card["type"] == "entities"
            for row in card["entities"]]
    assert rows
    # Boiler rows show only while they have a value: a conditional row around the same plain row.
    plain = [row["row"] if row.get("type") == "conditional" else row for row in rows]
    assert all(row == {"entity": row["entity"], "name": {"type": "entity"}} for row in plain)
    assert all(row["conditions"] == [known(row["row"]["entity"])] for row in rows if row.get("type") == "conditional")
