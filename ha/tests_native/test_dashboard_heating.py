"""The generated "Heating" dashboard: sections of built-in cards from the real registry, in English or Dutch."""
import json
from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.room_overview import HOUSE_CARD_TYPE
from test_v1_native import entry

BUILT_IN = {"heading", "tile", "thermostat", "history-graph", "statistics-graph", "entities", "glance",
            "markdown", "button", "gauge", "statistic"}
STATUS = {"schema": 1, "revision": 3, "mode": "shadow", "request": {"heat": True, "flow_c": 38, "reason": "heating"},
          "ha_entities": ["climate.tado_woonkamer"],
          "rooms": [{"id": "woonkamer", "name": "Woonkamer", "status": "ok", "source": "climate.tado_woonkamer",
                     "temperature": 20.4, "setpoint": 21.0, "demand": True},
                    {"id": "badkamer", "name": "Badkamer", "status": "fallback", "source": "a4c138a3e8db",
                     "temperature": 19.0, "setpoint": 20.0, "demand": False}],
          "ble_sensors": [{"id": "a4c138a3e8db", "name": "Thermometer badkamer", "temperature": 19.0,
                           "humidity": 60, "battery": 90}]}


def walk(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)
    else:
        yield value


def installation(hass, language="en", *, with_hub=True):
    e = entry(hass)
    hass.config.language = language
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_or_create(config_entry_id=e.entry_id, identifiers={("open_thermostat", "fixture")},
                                          name="OpenThermostat")

    def add(domain, unique_id, device=None, **kwargs):
        return entities.async_get_or_create(domain, "open_thermostat", unique_id, config_entry=e,
                                            device_id=(device or product).id, suggested_object_id=unique_id,
                                            **kwargs).entity_id
    rooms = {}
    for room_id, name in (("badkamer", "Badkamer"), ("woonkamer", "Woonkamer")):
        device = devices.async_get_or_create(config_entry_id=e.entry_id, name=name,
                                             identifiers={("open_thermostat", f"fixture_e32_room_{room_id}")})
        rooms[room_id] = {key: add(domain, f"fixture_e32_room_{room_id}_{key}", device) for domain, key in (
            ("sensor", "temperature"), ("sensor", "setpoint"), ("sensor", "status"), ("binary_sensor", "demand"),
            ("select", "state"), ("datetime", "inactive_until"), ("number", "fallback_setpoint"))}
    ble = devices.async_get_or_create(config_entry_id=e.entry_id, name="Thermometer badkamer",
                                      identifiers={("open_thermostat", "fixture_e32_ble_a4c138a3e8db")})
    sensors = {metric: add("sensor", f"fixture_e32_ble_a4c138a3e8db_{metric}", ble)
               for metric in ("temperature", "humidity", "battery")}
    hub = {key: add(domain, f"fixture_hub_{key}") for domain, key in (
        ("sensor", "heat_request"), ("sensor", "shadow_agreement_today"),
        ("sensor", "shadow_e32_heating_time_today"), ("sensor", "shadow_tado_heating_time_today"),
        ("sensor", "shadow_e32_starts_today"), ("sensor", "shadow_tado_starts_today"),
        ("sensor", "burner_starts_last_hour"), ("binary_sensor", "burner_short_cycling"))}
    fields = {name: add("sensor", f"fixture_boiler_fields_v1_{name}") for name in (
        "measured_flow_temperature", "measured_return_temperature", "reported_burner_modulation", "pressure",
        "measured_dhw_temperature", "display_code", "thermostat_requested_flow_temperature")}
    if with_hub:
        heating = HeatingHub("fixture")
        heating.update(STATUS)
        hass.data.setdefault("open_thermostat", {})[e.entry_id] = {"heating_hub": heating}
        hass.states.async_set("climate.tado_woonkamer", "heat", {"temperature": 21, "current_temperature": 20.4})
    return e, rooms, sensors, hub, fields


@pytest.mark.asyncio
async def test_the_views_are_overview_rooms_boiler_learning_and_diagnostics(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    config = dashboard._dashboard_config()
    # The trial-run comparison is a subview, last.
    assert [v["path"] for v in config["views"]] == ["heating", "rooms", "boiler", "learned", "diagnostics", "comparison"]
    overview, rooms_view, boiler_view, learning, diagnostics, comparison = config["views"]
    # rc.5 (the owner's sketch): three columns, the house card across them and Rooms, Today and House one each.
    assert (overview["title"], overview["type"], overview["max_columns"]) == ("Overview", "sections", 3)
    assert [v["title"] for v in config["views"]] == [
        "Overview", "Rooms", "Boiler", "Learning and settings", "Diagnostics", "Comparison"]
    assert comparison["subview"] is True and comparison["back_path"] == "/" + dashboard.path + "/heating"
    # Built-in cards, and on the Overview the integration's own house card (rc.5).
    assert {card["type"] for view in config["views"] for card in view_cards(view)} <= BUILT_IN | {HOUSE_CARD_TYPE}
    assert None not in list(walk(config))
    # Every section starts with its heading, except the house card alone on top of the Overview (it says what it is).
    assert all(s["cards"][0]["type"] == "heading" for v in config["views"] for s in v["sections"]
               if [c["type"] for c in s["cards"]] != [HOUSE_CARD_TYPE])

    # Overview: the house card (what the boiler does, the rooms that want heat with the boiler request), then one card
    # per room. Nothing else here (no Today without its sensors, no House without the house mode or outside). Two
    # rooms switched on: both have their own card.
    assert [s["cards"][0].get("heading") for s in overview["sections"]] == [None, "Rooms"]
    house = overview["sections"][0]["cards"]
    assert house[0]["type"] == HOUSE_CARD_TYPE and house[0]["request"] == hub["heat_request"] and "rooms" not in house[0]
    assert not any(c["type"] == "markdown" and "set wanting" in c["content"] for c in view_cards(overview))
    assert len(overview["sections"][1]["cards"]) == 3  # heading and two rooms, in the E32's order
    assert not any(c["type"] in ("history-graph", "statistics-graph", "entities") for c in view_cards(overview))
    # The comparison link and the takeover check are in the learning view, not here.
    assert not any(c.get("heading") == "E32 compared with your thermostat" for c in view_cards(overview))

    # Rooms: in the E32's order, by name, never the id.
    assert [s["cards"][0]["heading"] for s in rooms_view["sections"]] == [
        "Woonkamer", "Badkamer", "Bluetooth sensors"]
    living = rooms_view["sections"][0]["cards"]
    active = [{"condition": "state", "entity": rooms["woonkamer"]["state"], "state_not": "inactive"}]
    inactive = [{"condition": "state", "entity": rooms["woonkamer"]["state"], "state": "inactive"}]
    badges = living[0]["badges"]
    assert [b["entity"] for b in badges] == [rooms["woonkamer"][k] for k in ("demand", "status", "state")]
    assert badges[0]["visibility"] == active
    # A problem is amber; an inactive room is a plain grey "Off", never a warning.
    assert badges[1]["visibility"] == [{"condition": "state", "entity": rooms["woonkamer"]["status"],
                                        "state_not": ["ok", "inactive"]}]
    assert badges[2]["visibility"] == inactive and "color" not in badges[2]
    # The thermostat it follows; only while the room is on (an inactive room stays compact).
    assert living[1] == {"type": "thermostat", "entity": "climate.tado_woonkamer", "visibility": active}
    tiles = {c["entity"]: c for c in living if c["type"] == "tile"}
    # The mode and the temperature without Home Assistant stay on the room's device page. The E32 measures the
    # living room with the thermostat it follows only: its temperature shows once, on the dial (rc.5).
    assert list(tiles) == [rooms["woonkamer"]["inactive_until"]]
    assert "Measured by E32" not in json.dumps(living)
    # A lone tile takes the whole width, never half a row.
    assert all(c["grid_options"] == {"columns": 12} for c in tiles.values())
    day = next(c for c in living if c["type"] == "history-graph")
    assert [x["entity"] for x in day["entities"]] == [rooms["woonkamer"][k] for k in ("temperature", "setpoint")]
    assert day["visibility"] == active and "title" not in day
    off = next(c for c in living if c["type"] == "markdown")
    assert off == {"type": "markdown", "content": "This room is off and never asks for heat.", "visibility": inactive}
    # A Bluetooth-only room has no thermostat card, so it shows its measurement and target as a pair.
    bathroom = rooms_view["sections"][1]["cards"]
    assert not any(c["type"] == "thermostat" for c in bathroom)
    pair = [c for c in bathroom if c["type"] == "tile" and c["entity"] != rooms["badkamer"]["inactive_until"]]
    assert [c["entity"] for c in pair] == [rooms["badkamer"][k] for k in ("temperature", "setpoint")]
    assert not any("grid_options" in c for c in pair)
    # No plan read yet: the Bluetooth sensor feeds no known room, so it has its own section.
    bluetooth = rooms_view["sections"][2]["cards"]
    assert bluetooth[0]["heading"] == "Bluetooth sensors"
    assert bluetooth[1]["type"] == "glance" and bluetooth[1]["title"] == "Thermometer badkamer"
    assert [x["entity"] for x in bluetooth[1]["entities"]] == [sensors[k] for k in ("temperature", "humidity", "battery")]

    # Boiler, first "Now": the boiler in words, the water to the heating next to the water back, and the burner
    # power next to its starts in the last hour; nothing of it on the other views.
    known = lambda entity: [{"condition": "state", "entity": entity, "state_not": ["unavailable", "unknown"]}]
    now_section = boiler_view["sections"][0]
    now = now_section["cards"]
    assert (now[0]["heading"], now[0]["icon"]) == ("Now", "mdi:water-boiler")
    words = [c for c in now if c["type"] == "markdown" and "'meaning'" in c["content"]]
    assert len(words) == 1 and words[0]["visibility"] == known(fields["display_code"])
    flow, back, gauge, starts = now[2:]
    assert (flow["entity"], flow["name"], flow["icon"]) == (
        fields["measured_flow_temperature"], "Water to heating", "mdi:thermometer-chevron-up")
    assert (back["entity"], back["name"], back["icon"]) == (
        fields["measured_return_temperature"], "Water back", "mdi:thermometer-chevron-down")
    assert flow["visibility"] == back["visibility"] == known(fields["measured_flow_temperature"])
    assert "grid_options" not in flow and "grid_options" not in back  # one row of two tiles
    assert gauge == {"type": "gauge", "entity": fields["reported_burner_modulation"], "name": "Burner power",
                     "min": 0, "max": 100, "needle": False, "grid_options": {"columns": 6, "rows": 2},
                     "visibility": known(fields["reported_burner_modulation"])}
    assert (starts["entity"], starts["name"], starts["icon"], starts["grid_options"], starts["visibility"]) == (
        hub["burner_starts_last_hour"], "Starts per hour", "mdi:counter", {"columns": 6, "rows": 2},
        known(fields["reported_burner_modulation"]))
    # The section hides as a whole while the boiler reports none of it: never a heading over nothing.
    assert now_section["visibility"] == [{"condition": "or", "conditions": [
        known(fields[name])[0] for name in ("display_code", "measured_flow_temperature", "reported_burner_modulation")]}]
    assert hub["burner_short_cycling"] not in json.dumps(boiler_view)
    assert fields["display_code"] not in [c.get("entity") for v in (overview, rooms_view, learning) for c in view_cards(v)]

    # Learning and settings: the control line, short cycling as information, the takeover check and the comparison link.
    control = next(s["cards"] for s in learning["sections"] if s["cards"][0]["heading"] == "Who controls the boiler")
    explain, cycling = control[1], control[2]
    assert "<details>" in explain["content"] and "also without Home Assistant" in explain["content"]
    assert "Trial run" in explain["content"] and hub["heat_request"] in explain["content"]
    assert "Switching on and off too often" in cycling["content"]
    assert "lengthens the burner rest step by step" in cycling["content"] and "problem" not in cycling["content"].lower()
    link = control[-1]
    assert (link["type"], link["heading"]) == ("heading", "E32 compared with your thermostat")
    assert link["tap_action"] == {"action": "navigate", "navigation_path": "/" + dashboard.path + "/comparison"}
    # Trial run (the E32's mode), and only while a thermostat is heard (the agreement has a value).
    assert link["visibility"] == [{"condition": "state", "entity": hub["shadow_agreement_today"],
                                   "state_not": ["unavailable", "unknown"]}]

    compare = comparison["sections"][0]["cards"]
    assert compare[0]["heading"] == "E32 and thermostat"
    history = next(c for c in compare if c["type"] == "history-graph")
    assert [x["entity"] for x in history["entities"]] == [
        hub["heat_request"], fields["thermostat_requested_flow_temperature"], fields["measured_flow_temperature"]]
    assert [x["name"] for x in history["entities"]] == ["Boiler request E32", "Thermostat request", "Water to heating (flow)"]
    per_day = comparison["sections"][1]["cards"]
    assert per_day[0]["heading"] == "Heating time per day"
    assert per_day[1]["type"] == "statistics-graph" and "title" not in per_day[1]
    assert {c["entity"] for c in compare if c["type"] == "tile"} == {
        hub[k] for k in ("shadow_agreement_today", "shadow_e32_heating_time_today", "shadow_tado_heating_time_today",
                         "shadow_e32_starts_today", "shadow_tado_starts_today")}


@pytest.mark.asyncio
async def test_each_room_says_why_in_one_status_card_on_the_overview(hass):
    """1.1: the room status card (now against target, why it heats or not) is the room's card on the Overview."""
    from custom_components.open_thermostat.dashboard import ROOM_STATUS_CARD_TYPE
    e, rooms, sensors, hub, fields = installation(hass)
    device = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    reason = er.async_get(hass).async_get_or_create("sensor", "open_thermostat", "fixture_e32_room_woonkamer_reason",
                                                    config_entry=e, device_id=device.id,
                                                    suggested_object_id="woonkamer_reason").entity_id
    overview = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][0]
    cards = overview["sections"][1]["cards"]
    assert cards[0]["heading"] == "Rooms"
    assert cards[1] == {"type": ROOM_STATUS_CARD_TYPE, "entity": reason, "name": "Woonkamer"}
    # A room without its Reason sensor (an older integration's registry) shows its temperature as a tile.
    assert cards[2]["type"] == "tile" and cards[2]["name"] == "Badkamer" and cards[2]["grid_options"] == {"columns": 12}
    assert [c["type"] for c in view_cards(overview)].count(ROOM_STATUS_CARD_TYPE) == 1
    # The Rooms view has its own settings link and the "room is off" line, not a second status card.
    rooms_view = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][1]
    assert all(c["type"] != ROOM_STATUS_CARD_TYPE for c in view_cards(rooms_view))
    assert any(c.get("heading") == "Woonkamer settings" for c in view_cards(rooms_view))


@pytest.mark.asyncio
async def test_now_shows_what_the_boiler_does_as_one_coloured_tile(hass):
    """rc.5 (dashboard-spec §5.1): heating (deep orange), hot water (blue) or resting (grey) as one wide tile:
    exactly one shows for every state the boiler activity has. An older integration without the activity uses the
    boiler's own heating bit, on and off."""
    from custom_components.open_thermostat.dashboard import ACTIVITY_TILES
    from custom_components.open_thermostat.heating_link import BOILER_ACTIVITIES
    e, rooms, sensors, hub, fields = installation(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    fields["heating_active"] = entities.async_get_or_create(
        "sensor", "open_thermostat", "fixture_boiler_fields_v1_heating_active", config_entry=e, device_id=product.id,
        suggested_object_id="boiler_heating_active").entity_id

    def now():
        config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
        section = next(v for v in config["views"] if v["path"] == "boiler")["sections"][0]
        assert section["cards"][0]["heading"] in ("Now", "Teraz")
        return section
    bit = [c for c in now()["cards"] if c.get("entity") == fields["heating_active"]]
    assert [(c["name"], c["icon"], c["color"], c["grid_options"], c["visibility"]) for c in bit] == [
        ("Reported heating", "mdi:fire", "deep-orange", {"columns": 12},
         [{"condition": "state", "entity": fields["heating_active"], "state": ["on"]}]),
        ("Reported heating", "mdi:water-boiler", "grey", {"columns": 12},
         [{"condition": "state", "entity": fields["heating_active"], "state": ["off"]}])]
    hub["boiler_activity"] = entities.async_get_or_create(
        "sensor", "open_thermostat", "fixture_hub_boiler_activity", config_entry=e, device_id=product.id,
        suggested_object_id="boiler_activity").entity_id
    section = now()
    tiles = [c for c in section["cards"] if c.get("entity") == hub["boiler_activity"]]
    assert [(c["name"], c["icon"], c["color"], c["grid_options"]) for c in tiles] == [
        ("Boiler", "mdi:fire", "deep-orange", {"columns": 12}), ("Boiler", "mdi:faucet", "blue", {"columns": 12}),
        ("Boiler", "mdi:water-boiler", "grey", {"columns": 12})]
    shown = [state for c in tiles for state in c["visibility"][0]["state"]]
    assert sorted(shown) == sorted(BOILER_ACTIVITIES) and len(shown) == len(set(shown))  # one tile per state
    assert len(ACTIVITY_TILES) == 3 and not any(c.get("entity") == fields["heating_active"] for c in section["cards"])
    assert {"condition": "state", "entity": hub["boiler_activity"], "state_not": ["unavailable", "unknown"]} in (
        section["visibility"][0]["conditions"])
    hass.config.language = "pl"
    assert now()["cards"][0]["heading"] == "Teraz"


@pytest.mark.asyncio
async def test_measured_by_e32_shows_only_what_the_dial_does_not(hass):
    """rc.5 (dashboard-spec §3): next to the thermostat a room follows, the E32's own measurement only while it
    measures (also) elsewhere; a room measured by that thermostat alone shows its temperature once, on the dial."""
    e, rooms, sensors, hub, fields = installation(hass)
    heating = hass.data["open_thermostat"][e.entry_id]["heating_hub"]

    def measured(plan):
        heating.plan = SimpleNamespace(plan=plan, room=lambda room_id: next(
            (r for r in plan["rooms"] if r["id"] == room_id), None))
        living = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][1]["sections"][0]["cards"]
        assert living[1] == {"type": "thermostat", "entity": "climate.tado_woonkamer", "visibility": [
            {"condition": "state", "entity": rooms["woonkamer"]["state"], "state_not": "inactive"}]}
        return [c["name"] for c in living if c.get("entity") == rooms["woonkamer"]["temperature"] and c["type"] == "tile"]
    tado, ble = {"type": "ha", "id": "climate.tado_woonkamer"}, {"type": "ble", "id": "a4c138a3e8db"}
    assert measured({"rooms": [{"id": "woonkamer", "sources": [tado]}]}) == []
    assert measured({"rooms": [{"id": "woonkamer", "sources": [tado, ble]}]}) == ["Measured by E32"]
    assert measured({"rooms": [{"id": "woonkamer", "setpoint_entity": "climate.tado_woonkamer",
                                "sources": [ble]}]}) == ["Measured by E32"]


@pytest.mark.asyncio
async def test_a_room_heading_carries_at_most_its_five_badges_in_a_fixed_order(hass):
    """Demand, a problem, off, a radiator valve that needs attention and a low sensor battery; nothing more."""
    e, rooms, sensors, hub, fields = installation(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    device = devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    rooms["woonkamer"]["valve_problem"] = entities.async_get_or_create(
        "binary_sensor", "open_thermostat", "fixture_e32_room_woonkamer_valve_problem", config_entry=e,
        device_id=device.id, suggested_object_id="woonkamer_valve_problem").entity_id
    plan = {"rooms": [{"id": "woonkamer", "sources": [{"type": "ble", "id": "a4c138a3e8db"}]}]}
    hass.data["open_thermostat"][e.entry_id]["heating_hub"].plan = SimpleNamespace(
        plan=plan, room=lambda room_id: next((r for r in plan["rooms"] if r["id"] == room_id), None))
    living = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][1]["sections"][0]["cards"]
    assert [b["entity"] for b in living[0]["badges"]] == [
        *(rooms["woonkamer"][k] for k in ("demand", "status", "state", "valve_problem")), sensors["battery"]]
    assert all(b.get("visibility") for b in living[0]["badges"])  # each only while it says something


@pytest.mark.asyncio
async def test_no_comparison_without_a_thermostat_on_the_bus(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    entities = er.async_get(hass)
    for key in [k for k in hub if k.startswith("shadow_")]:
        entities.async_remove(hub.pop(key))
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    # No comparison and no readiness check: no subview.
    assert [v["path"] for v in config["views"]] == ["heating", "rooms", "boiler", "learned", "diagnostics"]
    text = json.dumps(config)
    assert "Thermostat request" not in text and "Agreement" not in text and "shadow_agreement" not in text
    assert "/comparison" not in text and "compared with your thermostat" not in text
    learning = config["views"][3]
    explain = next(c for c in view_cards(learning) if c["type"] == "markdown" and "'mode'" in c["content"])
    assert "your thermostat controls" not in explain["content"]
    assert "current thermostat or the boiler's own control" in explain["content"]


@pytest.mark.asyncio
async def test_a_room_in_the_plan_shows_its_e32_thermostat_and_its_own_sensor(hass):
    """The E32 room climate is the room's dial; the Bluetooth sensor that feeds only this room is listed in its section."""
    e, rooms, sensors, hub, fields = installation(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    device = devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    own = entities.async_get_or_create("climate", "open_thermostat", "fixture_e32_room_woonkamer_thermostat",
                                       config_entry=e, device_id=device.id, suggested_object_id="woonkamer").entity_id
    plan = {"rooms": [{"id": "woonkamer", "sources": [{"type": "ble", "id": "a4c138a3e8db"},
                                                      {"type": "ha", "id": "sensor.living_temperature"}]},
                      {"id": "badkamer", "state": "inactive", "sources": [{"type": "ha", "id": "climate.gone"}]}]}
    hass.data["open_thermostat"][e.entry_id]["heating_hub"].plan = SimpleNamespace(
        plan=plan, room=lambda room_id: next((r for r in plan["rooms"] if r["id"] == room_id), None))
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    rooms_view = config["views"][1]
    living = rooms_view["sections"][0]["cards"]
    assert living[1] == {"type": "thermostat", "entity": own, "visibility": [
        {"condition": "state", "entity": rooms["woonkamer"]["state"], "state_not": "inactive"}]}
    # Its own climate shows the measurement: no second "Measured by E32" tile.
    assert rooms["woonkamer"]["temperature"] not in [c.get("entity") for c in living if c["type"] == "tile"]
    badges = living[0]["badges"]
    # The humidity is a row below, not a second time as a badge; a low battery is a badge.
    assert [b["entity"] for b in badges] == [rooms["woonkamer"]["demand"], rooms["woonkamer"]["status"],
                                             rooms["woonkamer"]["state"], sensors["battery"]]
    assert badges[3]["visibility"] == [{"condition": "numeric_state", "entity": sensors["battery"], "below": 20}]
    # Sensors, windows and people: the sensor's values with their names, then the other sources of the room.
    heading = next(i for i, c in enumerate(living) if c.get("heading") == "Sensors, windows and people")
    assert living[heading]["heading_style"] == "subtitle" and living[heading + 1]["type"] == "entities"
    assert living[heading + 1]["entities"] == [
        {"entity": sensors["temperature"], "name": "Temperature"}, {"entity": sensors["humidity"], "name": "Humidity"},
        {"entity": sensors["battery"], "name": "Battery"}, {"entity": "sensor.living_temperature"}]
    assert "Bluetooth sensors" not in json.dumps(config)  # the sensor is in its room
    # The bathroom follows an entity that no longer exists: when it is off, a hint to choose a source
    # first, removing the room second (both in Home Assistant's own pages).
    bathroom = rooms_view["sections"][1]["cards"]
    inactive = [{"condition": "state", "entity": rooms["badkamer"]["state"], "state": "inactive"}]
    hint = [c for c in bathroom if c.get("visibility") == inactive and c["type"] in ("markdown", "heading")]
    assert [c.get("heading") or c["content"] for c in hint] == [
        "Badkamer is off and has no working temperature source.\n\n<details><summary>More</summary>\n\n"
        "Choose a source to use it again, or remove the room if you no longer need it.\n\n</details>",
        "Choose a source", "Remove room"]
    integration = "/config/integrations/integration/open_thermostat"
    assert [c["tap_action"]["navigation_path"] for c in hint[1:]] == [integration, integration]
    # With the Repairs item for it, "Choose a source" opens Repairs.
    from homeassistant.helpers import issue_registry as ir
    ir.async_create_issue(hass, "open_thermostat", f"e32_room_choose_source_{e.entry_id}_badkamer", is_fixable=True,
                          severity=ir.IssueSeverity.WARNING, translation_key="e32_room_choose_source")
    bathroom = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][1]["sections"][1]["cards"]
    choose = next(c for c in bathroom if c.get("heading") == "Choose a source")
    assert choose["tap_action"]["navigation_path"] == "/config/repairs"
    hass.config.language = "nl"
    text = json.dumps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config(), ensure_ascii=False)
    assert "Badkamer staat uit en heeft geen werkende temperatuurbron" in text and "Kies een bron" in text


def _add_learned(hass, e, rooms, hub):
    """The entities firmware that learns creates: per room, and today's hot water on the product."""
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    room = devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    for key in ("learning", "flow_advice", "heating_start"):
        rooms["woonkamer"][key] = entities.async_get_or_create(
            "sensor", "open_thermostat", f"fixture_e32_room_woonkamer_{key}", config_entry=e, device_id=room.id,
            suggested_object_id=f"woonkamer_{key}").entity_id
    for key in ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today"):
        hub[key] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_hub_{key}", config_entry=e,
                                                device_id=product.id, suggested_object_id=key).entity_id


@pytest.mark.asyncio
async def test_learning_area_per_room_and_hot_water_today_only_once_reported(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    before = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert '"heading": "Learning"' not in json.dumps(before) and "dhw_taps" not in json.dumps(before)  # older firmware
    _add_learned(hass, e, rooms, hub)
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    overview, rooms_view, boiler_view, learning = config["views"][:4]
    # The learned values sit inside the room they belong to.
    living = rooms_view["sections"][0]["cards"]
    room = rooms["woonkamer"]
    area = living[next(i for i, c in enumerate(living) if c.get("heading") == "Learning"):]
    # Then the "room is off" line and the link to the room's settings.
    assert [c["type"] for c in area] == ["heading", "tile", "tile", "markdown", "heading"]
    heading, advice, start = area[:3]
    assert heading["heading_style"] == "subtitle" and heading["icon"] == "mdi:school-outline"
    assert heading["badges"] == [{"type": "entity", "entity": room["learning"], "show_state": True,
                                  "show_icon": True, "color": "teal"}]
    known = lambda entity: {"condition": "state", "entity": entity, "state_not": ["unavailable", "unknown"]}
    on = {"condition": "state", "entity": room["state"], "state_not": "inactive"}
    # Hidden while the E32 reports none, and while the room is off.
    assert heading["visibility"] == [on, known(room["learning"])]
    assert (advice["entity"], advice["name"]) == (room["flow_advice"], "Recommended water temperature")
    assert advice["visibility"] == [on, {"condition": "state", "entity": room["learning"], "state": "ready"},
                                    known(room["flow_advice"])]
    assert (start["entity"], start["name"], start["visibility"]) == (
        room["heating_start"], "Heating starts", [on, known(room["heating_start"])])
    # A room without learned entities gets no learning area.
    assert not any(c.get("heading") == "Learning" for c in rooms_view["sections"][1]["cards"])
    # How the learning works: the note under what it learned (rc.5: no section of its own), only while the E32
    # reports it; without the learned overview it stands alone under that heading.
    how = next(x for x in learning["sections"] if x["cards"][0]["heading"] == "What the thermostat has learned")
    note = how["cards"][-1]
    assert "learns how fast each room warms up" in note["content"] and room["learning"] in note["content"]
    assert "advice only" in note["content"] and "'applied'" in note["content"] and "<details>" in note["content"]
    assert note["visibility"] == how["visibility"] == [known(room["learning"])]
    assert "learns how fast" not in json.dumps([overview, rooms_view, boiler_view])
    assert "How it learns" not in json.dumps(config)
    # Today's hot water is in the Boiler view's "Hot water" (rows that appear once they have a value), nowhere else.
    hot_water = next(x for x in boiler_view["sections"] if x["cards"][0]["heading"] == "Hot water")
    rows = next(c for c in hot_water["cards"]
                if c.get("entities") and c["entities"][0]["row"]["entity"] == hub["dhw_taps_today"])
    assert [row["row"]["entity"] for row in rows["entities"]] == [
        hub[k] for k in ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today")]
    assert all(row["conditions"] == [known(row["row"]["entity"])] for row in rows["entities"])
    # The section hides as a whole while neither the hot water temperature nor today's figures have a value.
    assert hot_water["visibility"] == [{"condition": "or", "conditions": [known(fields["measured_dhw_temperature"]), *(
        known(hub[k]) for k in ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today"))]}]
    assert not any(c.get("heading") == "Hot water today" for c in view_cards(boiler_view))
    assert hub["dhw_taps_today"] not in json.dumps(config["views"][4])
    # In Dutch.
    hass.config.language = "nl"
    text = json.dumps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config(), ensure_ascii=False)
    for words in ('"Leren"', "Geadviseerde watertemperatuur", "Start verwarmen", '"Warm water"',
                  "Wat de thermostaat heeft geleerd", "leert ook hoe snel elke ruimte opwarmt", "alleen advies"):
        assert words in text, words


def test_dashboard_text_has_the_same_keys_in_every_language():
    from custom_components.open_thermostat.dashboard import TEXT
    assert set(TEXT["en"]) == set(TEXT["nl"]) == set(TEXT["pl"])
    assert all(TEXT[language][key].strip() for language in ("nl", "pl") for key in TEXT[language])
    # rc.5: the keys of the new Boiler and Learning sections, and the ones they replaced are gone.
    assert {"today_week", "gas_heating_today", "gas_hot_water_today", "starts_today", "burner_today", "boiler_values",
            "who_controls", "yesterday_figures", "dhw_target_short"} <= set(TEXT["en"])
    assert not {"gas_per_post", "control", "learning_how"} & set(TEXT["en"])
    # No "Heating page" any more: the gas per day is on the Boiler tab and the E32's Home page (named as the other
    # Home Assistant texts name it).
    assert [all(page in TEXT[language]["estimates_empty"] for page in pages) for language, pages in (
        ("en", ("The Boiler tab", "the E32's Home page")), ("nl", ("Het tabblad Ketel", "de pagina Huis van de E32")),
        ("pl", ("Karta Kocioł", "strona Dom w E32")))] == [True, True, True]


@pytest.mark.asyncio
async def test_dutch_headings_and_only_existing_enabled_entities(hass):
    e, rooms, sensors, hub, fields = installation(hass, "nl", with_hub=False)
    registry = er.async_get(hass)
    for entity_id in (hub["heat_request"], rooms["woonkamer"]["fallback_setpoint"], sensors["humidity"],
                      fields["thermostat_requested_flow_temperature"]):
        registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    registry.async_remove(hub["burner_short_cycling"])
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    # No E32 status yet, so no trial run known: no Comparison subview (its records lead nowhere).
    assert [v["title"] for v in config["views"]] == ["Overzicht", "Ruimtes", "Ketel", "Leren en instellingen", "Diagnose"]
    overview, rooms_view = config["views"][:2]
    assert [s["cards"][0]["heading"] for s in overview["sections"]] == ["Ruimtes"]
    assert [s["cards"][0]["heading"] for s in rooms_view["sections"]] == [
        "Badkamer", "Woonkamer", "Bluetooth-sensoren"]
    text = json.dumps(config, ensure_ascii=False)
    for gone in (hub["heat_request"], rooms["woonkamer"]["fallback_setpoint"], sensors["humidity"],
                 fields["thermostat_requested_flow_temperature"], hub["burner_short_cycling"]):
        assert gone not in text
    assert "Gemeten door E32" in text and "Proefperiode" not in text  # no request entity: no mode line
    assert "Zo werkt het" not in text
    assert "thermostat" not in [c["type"] for c in view_cards(rooms_view)]  # no hub status: no thermostat link
    assert None not in list(walk(config))
    # A user name on the room device is the heading.
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("open_thermostat", "fixture_e32_room_badkamer"), e.entry_id)
    dr.async_get(hass).async_update_device(device.id, name_by_user="Badkamer boven")
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert config["views"][1]["sections"][0]["cards"][0]["heading"] == "Badkamer boven"
    assert config["views"][0]["sections"][0]["cards"][1]["name"] == "Badkamer boven"


@pytest.mark.asyncio
async def test_empty_installation_has_no_empty_sections(hass):
    e = entry(hass)
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    # Views without anything to show are left out; the boiler and diagnostics views stay, empty.
    assert [v["path"] for v in config["views"]] == ["boiler", "diagnostics"]
    assert all(v["sections"] == [] for v in config["views"])
    assert None not in list(walk(config))


@pytest.mark.asyncio
async def test_dashboard_rebuilds_for_new_rooms_or_language_but_not_every_reading(hass, monkeypatch):
    from custom_components.open_thermostat import dashboard as module
    later = []
    monkeypatch.setattr(module, "async_call_later", lambda hass, delay, action: later.append(action) or (lambda: None))
    e, rooms, sensors, hub, fields = installation(hass)
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    saved = []

    class Store:
        async def async_load(self, force):
            return saved[-1] if saved else None

        async def async_save(self, config):
            saved.append(config)
    dashboard._store = Store()
    dashboard._watch_hub()
    heating = hass.data["open_thermostat"][e.entry_id]["heating_hub"]
    heating.update(STATUS)
    await hass.async_block_till_done()
    assert len(saved) == 1
    reading = json.loads(json.dumps(STATUS))
    reading["rooms"][0]["temperature"] = 20.5  # a new reading: same dashboard, no rebuild
    heating.update(reading)
    await hass.async_block_till_done()
    assert len(saved) == 1
    hass.config.language = "nl"
    dashboard._registry_updated(SimpleNamespace(data={}))  # core config update (language)
    dashboard._registry_updated(SimpleNamespace(data={}))  # ... and more events of the same burst
    await hass.async_block_till_done()
    assert len(saved) == 1 and len(later) == 1  # one rebuild, once the burst settled (R4-11)
    later.pop()(None)
    await hass.async_block_till_done()
    assert saved[-1]["views"][0]["title"] == "Overzicht" and len(saved) == 2
    # A room or sensor the E32 no longer reports leaves the dashboard.
    heating.update({**STATUS, "rooms": STATUS["rooms"][:1], "ble_sensors": []})
    await hass.async_block_till_done()
    headings = [section["cards"][0]["heading"] for section in saved[-1]["views"][1]["sections"]]
    assert "Badkamer" not in headings and "Woonkamer" in headings and "Bluetooth-sensoren" not in headings
    dashboard._unwatch_hub()
    assert dashboard._heating_hub() is heating and heating._listeners == []


@pytest.mark.asyncio
async def test_the_house_card_names_the_problem_and_leads_to_the_fix_only_while_there_is_one(hass):
    """The night-time check: the Overview says what is wrong, in a few words, and a tap opens Repairs.

    rc.5: the house card carries the problem (its strip turns red with the reason, a tap opens Repairs and "All
    reasons" lists them, frontend/house-card.js); no problem tile or reasons card of its own any more."""
    e, rooms, sensors, hub, fields = installation(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    for domain, key in (("binary_sensor", "heating_problem"), ("sensor", "heating_advice")):
        hub[key] = entities.async_get_or_create(domain, "open_thermostat", f"fixture_hub_{key}", config_entry=e,
                                                device_id=product.id, suggested_object_id=key).entity_id
    field = entities.async_get_or_create("sensor", "open_thermostat",
                                         "fixture_boiler_fields_v1_configured_heating_temperature", config_entry=e,
                                         device_id=product.id, suggested_object_id="boiler_maximum").entity_id
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    overview, boiler_view = config["views"][0], config["views"][2]
    assert [s["cards"][0].get("heading") for s in overview["sections"]] == [None, "Rooms"]
    # The advice belongs to the boiler, second after "Now".
    assert [s["cards"][0]["heading"] for s in boiler_view["sections"]][:2] == ["Now", "Advice"]
    assert hub["heating_advice"] not in json.dumps(overview)
    house = overview["sections"][0]["cards"]
    assert house[0]["type"] == HOUSE_CARD_TYPE and house[0]["problem"] == hub["heating_problem"]
    # The card reads the problem; no native tile or markdown card shows it a second time.
    assert [c["type"] for c in house] == [HOUSE_CARD_TYPE]
    assert [c for c in view_cards(overview) if c.get("entity") == hub["heating_problem"]] == []
    assert "'reasons'" not in json.dumps(overview)
    # The boiler's own maximum (a knob on some boilers, a menu on others) is a boiler value, in the Boiler view only.
    assert field in json.dumps(boiler_view) and field not in json.dumps(overview)
    hass.config.language = "nl"
    text = json.dumps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config(), ensure_ascii=False)
    # "All reasons" is the card's own text now (translations, entity.sensor.heat_request.state_attributes.card).
    assert '"Ruimtes"' in text and '"Overzicht"' in text and "Alle redenen" not in text


@pytest.mark.asyncio
async def test_rooms_wanting_heat_card_lists_the_rooms_and_the_request(hass):
    """Under Now, like the E32's dashboard: how many rooms want heat, which, and the boiler request."""
    from homeassistant.helpers.template import Template
    from custom_components.open_thermostat.dashboard import TEXT, _wanting_card
    rooms = [{"id": "woonkamer", "name": "Woonkamer", "demand": True, "temperature": 20.1, "setpoint": 21},
             {"id": "badkamer", "name": "Badkamer", "demand": False, "temperature": 19.0, "setpoint": 20},
             {"id": "zolder", "name": "Zolder", "demand": True, "temperature": None, "setpoint": 18}]
    request = "sensor.e32_heat_request"
    assert _wanting_card(TEXT["en"], None) is None
    hass.states.async_set(request, "54", {"rooms": rooms})
    nl = Template(_wanting_card(TEXT["nl"], request)["content"], hass).async_render()
    assert nl == "### 2 ruimtes vragen warmte\n- **Woonkamer**: 20,1 → 21,0 °C\n- **Zolder**\n\nKetelvraag: 54,0 °C"
    hass.states.async_set(request, "0", {"rooms": rooms[:2]})
    en = Template(_wanting_card(TEXT["en"], request)["content"], hass).async_render()
    # Home Assistant strips the rendered text's trailing newline.
    assert en == "### 1 room wants heat\n- **Woonkamer**: 20.1 → 21.0 °C"
    hass.states.async_set(request, "unavailable", {})
    assert Template(_wanting_card(TEXT["en"], request)["content"], hass).async_render() == "### No room wants heat"


@pytest.mark.asyncio
async def test_registry_events_of_other_integrations_never_rebuild_the_dashboard(hass, monkeypatch):
    """R4-11: 150 entities of another integration were 150 rebuilds; now none, and a burst of our own is one."""
    from homeassistant.const import EVENT_CORE_CONFIG_UPDATE
    from custom_components.open_thermostat import dashboard as module
    from test_e32_room_flow import other_entry
    later = []
    monkeypatch.setattr(module, "async_call_later", lambda hass, delay, action: later.append((delay, action))
                        or (lambda: None))
    # Never a deprecated registry read (DeviceEntry.config_entries, Core 2026.10): each one is a repair for the user.
    deprecated = []
    monkeypatch.setattr(dr, "report_usage", lambda what, **kwargs: deprecated.append(what))
    e, rooms, sensors, hub, fields = installation(hass)
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    built = []
    build = dashboard._dashboard_config

    def counted():
        built.append(True)
        return build()
    dashboard._dashboard_config = counted
    saved = []

    class Store:
        async def async_load(self, force):
            return saved[-1] if saved else None

        async def async_save(self, config):
            saved.append(config)
    dashboard._store = Store()
    build()  # what the start builds: this entry's entities and devices are known
    dashboard._listen()
    other = other_entry(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    for n in range(150):
        device = devices.async_get_or_create(config_entry_id=other.entry_id, identifiers={("other_integration", str(n))})
        entities.async_get_or_create("sensor", "other_integration", f"other_{n}", config_entry=other, device_id=device.id)
    hass.bus.async_fire(EVENT_CORE_CONFIG_UPDATE, {"latitude": 52.1})  # not the language or units
    await hass.async_block_till_done()
    assert later == [] and built == [] and saved == []
    # This entry's own new entities (and a rename of one): one rebuild once the burst settled.
    for n in range(20):
        entities.async_get_or_create("sensor", "open_thermostat", f"fixture_extra_{n}", config_entry=e)
    entities.async_update_entity(rooms["woonkamer"]["temperature"], new_entity_id="sensor.living_room_temperature")
    await hass.async_block_till_done()
    assert [delay for delay, _ in later] == [module.REGISTRY_SETTLE_SECONDS] and built == []
    later.pop()[1](None)
    await hass.async_block_till_done()
    assert len(built) == 1 and len(saved) == 1
    assert "sensor.living_room_temperature" in json.dumps(saved[-1])
    hass.bus.async_fire(EVENT_CORE_CONFIG_UPDATE, {"language": "nl"})
    await hass.async_block_till_done()
    assert len(later) == 1
    # A new device of this entry (a room the E32 reports) rebuilds it too: known by its one config entry, read without
    # the deprecated DeviceEntry.config_entries (none of the 150 other devices read it either).
    later.pop()[1](None)
    await hass.async_block_till_done()
    devices.async_get_or_create(config_entry_id=e.entry_id, identifiers={("open_thermostat", "fixture_e32_room_zolder")},
                                name="Zolder")
    await hass.async_block_till_done()
    assert len(later) == 1 and deprecated == []
    for unsubscribe in dashboard._unsubscribe:
        unsubscribe()
