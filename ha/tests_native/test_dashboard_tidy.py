"""The Heating dashboard as the owner saw it on 30 Oct 2026, tidied: no "Unavailable" rows of tiles, no
"0,0 °C" request, no bare "98 %", an inactive room without a dial, whole names and no gap under "Now".

Shaped like the live installation: the living room follows a thermostat and a Bluetooth sensor, the
bathroom is inactive with a working source of its own (it stays off and is never switched on here); the
boiler fields of the owner's boiler, the gas, the daily summary, today's hot water and what the boiler does.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat import dashboard as module
from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from custom_components.open_thermostat.room_overview import BOILER_NOW_CARD_TYPE, HOUSE_CARD_TYPE
from test_dashboard_heating import installation, walk
from test_dashboard_redesign import LIVE_FIELDS

PLAN = {"rooms": [
    {"id": "woonkamer", "state": "active", "sources": [{"type": "ha", "id": "climate.tado_woonkamer"},
                                                       {"type": "ble", "id": "a4c138a3e8db"}]},
    {"id": "badkamer", "state": "inactive", "sources": [{"type": "ha", "id": "climate.thermostaat_badkamer"}]}]}
# The hub sensors of the owner's E32 and integration that the Boiler, Learning and Diagnostics views draw (rc.5):
# what the boiler does, the gas (split into tapping and keeping warm), the daily summary, today's hot water, the
# advice, the E32 itself, the energy and hot water counters (empty on this boiler) and the hot water capability.
HUB_SENSORS = ("boiler_activity", "heating_gas", "hot_water_gas", "tapping_gas", "keep_warm_gas", "daily_summary",
               "daily_burner_time", "daily_burner_starts", "daily_missed_comfort", "dhw_taps_today",
               "dhw_keep_warm_today", "dhw_burner_time_today", "heating_advice", "memory_free", "memory_min_free",
               "cpu_temperature", "uptime", "energy_v2", "energy_heating_v2", "energy_warm_water_v2",
               "warm_water_usage_v2", "burner_observed_time_v2", "dhw_capabilities")


def known(entity_id):
    return {"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown"]}


def live(hass, language="en"):
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    for room_id in ("woonkamer", "badkamer"):
        device = devices.async_get_device_by_identifier(("open_thermostat", f"fixture_e32_room_{room_id}"), e.entry_id)
        for domain, key in (("climate", "thermostat"), ("sensor", "learning"), ("sensor", "flow_advice"),
                            ("sensor", "heating_start"), ("sensor", "warm_on_time"), ("sensor", "overshoot")):
            rooms[room_id][key] = entities.async_get_or_create(
                domain, "open_thermostat", f"fixture_e32_room_{room_id}_{key}", config_entry=e, device_id=device.id,
                suggested_object_id=f"{room_id}_{key}").entity_id
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    hub["heating_problem"] = entities.async_get_or_create(
        "binary_sensor", "open_thermostat", "fixture_hub_heating_problem", config_entry=e, device_id=product.id,
        suggested_object_id="heating_problem").entity_id
    # Yesterday's scoreboard (E32 rc.4); what the E32 knows, the boiler's response and the learned overview (rc.5).
    for key in ("burner_starts_per_heating_hour", "short_cycling_hours", "heating_gas_yesterday", "gas_per_degree_day",
                "knowledge", "boiler_response", "learned_overview", *HUB_SENSORS):
        hub[key] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_hub_{key}", config_entry=e,
                                                device_id=product.id, suggested_object_id=key).entity_id
    for name in LIVE_FIELDS:
        fields[name] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_boiler_fields_v1_{name}",
                                                    config_entry=e, device_id=product.id,
                                                    suggested_object_id=f"boiler_{name}").entity_id
    flow = {key: entities.async_get_or_create(domain, "open_thermostat", f"fixture_flow_{key}", config_entry=e,
                                              device_id=product.id, suggested_object_id=f"flow_{key}").entity_id
            for domain, key in (("sensor", "source"), ("switch", "weather_curve"),
                                ("select", "curve_design_flow_c"), ("switch", "apply_learned"), ("sensor", "curve"))}
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
    overview, boiler = config["views"][0], next(v for v in config["views"] if v["path"] == "boiler")
    values = [fields[k] for k in ("measured_flow_temperature", "measured_dhw_temperature",
                                  "measured_return_temperature", "reported_burner_modulation", "pressure")]
    # The boiler's values are all in the Boiler view, as rows that appear once they have a value; never on the Overview,
    # except the water temperature to heating that the house card (rc.5) says in its strip ("Heating · water 41 °C").
    rows = {row["row"]["entity"]: row for card in view_cards(boiler) if card["type"] == "entities"
            for row in card["entities"] if row.get("type") == "conditional"}
    for entity_id in values:
        assert rows[entity_id]["conditions"] == [known(entity_id)], entity_id
    house = next(c for c in section(overview, "House") if c["type"] == HOUSE_CARD_TYPE)
    assert house["flow"] == fields["measured_flow_temperature"]
    others = [c for c in view_cards(overview) if c["type"] != HOUSE_CARD_TYPE]
    assert not any(entity_id in json.dumps(others) for entity_id in values)
    # The display code in words: the Now card's (frontend/boiler-now-card.js), which says it only while the code has a
    # value; the section shows while one of its values has one (here the code among them).
    now = section(boiler, "Now")
    assert [c["type"] for c in now] == ["heading", BOILER_NOW_CARD_TYPE] and now[1]["code"] == fields["display_code"]
    assert known(fields["display_code"]) in next(s for s in boiler["sections"] if s["cards"] is now)["visibility"][0]["conditions"]
    assert not any(c["type"] == "markdown" and "'meaning'" in c["content"] for c in view_cards(boiler))
    # The problem is the house card's (its strip turns red with the reason only while there is one); no tile of its own.
    assert house["problem"] == hub["heating_problem"]
    assert not any(c.get("entity") == hub["heating_problem"] for c in view_cards(overview))


@pytest.mark.asyncio
async def test_the_boiler_request_says_no_request_instead_of_zero_degrees(hass):
    """One card whose text follows the E32: "Boiler request 54 °C" or "No boiler request", never "0 °C".

    rc.5: the house card reads the request (frontend/house-card.js; the words are checked in
    test/ha-house-card-browser.cjs); the markdown card stays only for a house card without its sensors."""
    from homeassistant.helpers.template import Template
    from custom_components.open_thermostat.dashboard import TEXT, _wanting_card
    config, rooms, sensors, hub, fields, flow = live(hass)
    house = section(config["views"][0], "House")[1]
    assert house["type"] == HOUSE_CARD_TYPE and house["request"] == hub["heat_request"]
    assert "visibility" not in house  # no card that comes and goes
    hass.states.async_set(hub["heat_request"], "0", {"rooms": []})
    wanting = _wanting_card(TEXT["nl"], hub["heat_request"])
    assert Template(wanting["content"], hass).async_render() == "### Geen ruimte vraagt warmte"
    texts = json.loads((Path(module.__file__).parent / "translations/nl.json").read_text(encoding="utf-8"))
    card = texts["entity"]["sensor"]["heat_request"]["state_attributes"]["card"]["state"]
    assert (card["no_request"], card["request"]) == ("Geen ketelvraag", "Ketelvraag {flow} °C")


@pytest.mark.asyncio
async def test_the_comparison_is_a_link_that_explains_it_not_a_bare_percentage(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    learning = next(v for v in config["views"] if v["path"] == "learned")
    control = section(learning, "Who controls the boiler")
    assert hub["shadow_agreement_today"] not in [c.get("entity") for c in control]
    link = next(c for c in control if c.get("heading") == "E32 compared with your thermostat")
    assert link["tap_action"]["navigation_path"].endswith("/comparison")
    assert link["visibility"] == [known(hub["shadow_agreement_today"])]  # only while a thermostat is heard
    # The subview names it in full.
    compare = config["views"][-1]["sections"][0]["cards"]
    agreement = next(c for c in compare if c.get("entity") == hub["shadow_agreement_today"])
    assert agreement["name"] == "Agreement with thermostat"


@pytest.mark.asyncio
async def test_no_comparison_once_the_e32_controls_the_boiler(hass):
    """The owner's E32 in active mode, the agreement record restored: no link and no Comparison subview."""
    config, rooms, sensors, hub, fields, flow = live(hass)
    entry_id = er.async_get(hass).async_get(hub["heat_request"]).config_entry_id
    heating_hub = hass.data["open_thermostat"][entry_id]["heating_hub"]
    heating_hub.update({**heating_hub.status, "mode": "active"})
    config = RoomDashboard(hass, "fixture", entry_id)._dashboard_config()
    assert [v["path"] for v in config["views"]] == ["heating", "rooms", "boiler", "learned", "diagnostics"]
    text = json.dumps(config)
    assert "compared with your thermostat" not in text and "/comparison" not in text
    assert hub["shadow_agreement_today"] not in text and "Agreement with thermostat" not in text


@pytest.mark.asyncio
async def test_an_inactive_room_is_compact_without_a_dial_or_learning_and_links_to_its_settings(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    bathroom = section(config["views"][1], "Badkamer")
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
    living = section(config["views"][1], "Woonkamer")
    assert any(c["type"] == "thermostat" for c in living)


@pytest.mark.asyncio
async def test_the_humidity_is_a_named_row_in_the_rooms_sensors_not_a_second_badge(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    living = section(config["views"][1], "Woonkamer")
    assert sensors["humidity"] not in [b["entity"] for b in living[0]["badges"]]
    rows = next(c for c in living if c["type"] == "entities")["entities"]
    assert {"entity": sensors["humidity"], "name": "Humidity"} in rows


@pytest.mark.asyncio
async def test_long_choices_get_the_whole_width_and_sections_fill_the_gaps(hass):
    config, rooms, sensors, hub, fields, flow = live(hass)
    learning = next(v for v in config["views"] if v["path"] == "learned")
    assert learning["dense_section_placement"] is True
    settings = section(learning, "Smart warm-up and weather compensation")
    # The settings carry their entities' own long names (as on the device page) and a long choice: rows of one card
    # across the whole width (the owner's sketch, rc.5), none cut short. What sets the water temperature now is no
    # setting (its long state cut a row's name short on a phone): it stays on the E32 device.
    rows, = [c["entities"] for c in settings if c["type"] == "entities"]
    assert not any(c["type"] == "tile" for c in settings)
    assert [row["entity"] for row in rows] == [flow[k] for k in ("apply_learned", "weather_curve", "curve_design_flow_c")]
    assert [row["name"] for row in rows] == ["Smart warm-up", "Weather compensation",
                                             "Water temperature in hard frost (−10 °C)"]
    assert flow["source"] not in json.dumps(learning)


@pytest.mark.asyncio
async def test_rows_in_entities_cards_are_named_by_the_entity_alone(hass):
    """Without the device name in front ("E32 controller — boiler and diagnostics …") the names fit."""
    config, rooms, sensors, hub, fields, flow = live(hass)
    rows = [row for view in config["views"] for card in view_cards(view) if card["type"] == "entities"
            for row in card["entities"]]
    assert rows
    # Boiler rows show only while they have a value: a conditional row around the same plain row.
    plain = [row["row"] if row.get("type") == "conditional" else row for row in rows]
    # The entity's own name (no device name in front) or a name this dashboard chose, written out.
    assert all(row.get("name", {"type": "entity"}) == {"type": "entity"} or isinstance(row["name"], str) for row in plain)
    # (The boiler's maintenance message also hides while it says there is none.)
    hidden = {fields["maintenance_message"]: ["none"]}
    assert all(row["conditions"] == [{**known(row["row"]["entity"]), "state_not": [
        "unavailable", "unknown", *hidden.get(row["row"]["entity"], [])]}] for row in rows if row.get("type") == "conditional")
