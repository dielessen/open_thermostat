"""The generated "Heating" dashboard: sections of built-in cards from the real registry, in English or Dutch."""
import json
from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.dashboard import RoomDashboard, view_cards
from custom_components.open_thermostat.heating_link import HeatingHub
from test_v1_native import entry

BUILT_IN = {"heading", "tile", "thermostat", "history-graph", "statistics-graph", "entities", "glance",
            "markdown", "button"}
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
async def test_heating_view_is_sections_of_built_in_cards_per_room_with_the_essentials(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    config = dashboard._dashboard_config()
    # The shadow comparison and the loose Bluetooth sensor live on a subview reached from "Now".
    assert [v["path"] for v in config["views"]] == ["heating", "boiler", "diagnostics", "comparison"]
    heating, comparison = config["views"][0], config["views"][3]
    assert (heating["title"], heating["type"], heating["max_columns"]) == ("Heating", "sections", 3)
    assert (comparison["title"], comparison["subview"], comparison["type"]) == ("Comparison", True, "sections")
    assert {card["type"] for view in config["views"] for card in view_cards(view)} <= BUILT_IN
    assert None not in list(walk(config))
    headings = [section["cards"][0]["heading"] for section in heating["sections"]]
    # For a quick look: "Now" (status, what the heating does, the boiler at a glance), then the rooms
    # (in the E32's order, by name, never the id), then the rest of the boiler.
    assert headings == ["Now", "Woonkamer", "Badkamer", "Boiler"]
    now = heating["sections"][0]["cards"]
    assert [c.get("entity") for c in now if c["type"] == "tile"] == [
        hub["heat_request"], fields["measured_flow_temperature"], fields["measured_dhw_temperature"],
        hub["shadow_agreement_today"]]
    agreement = next(c for c in now if c.get("entity") == hub["shadow_agreement_today"])
    assert agreement["name"] == "Agreement"
    assert agreement["tap_action"] == {"action": "navigate", "navigation_path": "/" + dashboard.path + "/comparison"}
    explain = next(c for c in now if c["type"] == "markdown")
    # One short line instead of a "How it works" block.
    assert "How it works" not in explain["content"] and "You set the rooms" not in explain["content"]
    assert "also without Home Assistant" in explain["content"] and "Shadow mode" in explain["content"]
    assert hub["heat_request"] in explain["content"]  # the mode line follows the E32's own status

    living = heating["sections"][1]["cards"]
    active = [{"condition": "state", "entity": rooms["woonkamer"]["state"], "state_not": "inactive"}]
    inactive = [{"condition": "state", "entity": rooms["woonkamer"]["state"], "state": "inactive"}]
    badges = living[0]["badges"]
    assert [b["entity"] for b in badges] == [rooms["woonkamer"]["demand"], rooms["woonkamer"]["status"]]
    assert badges[0]["visibility"] == active
    assert badges[1]["visibility"] == [{"condition": "state", "entity": rooms["woonkamer"]["status"],
                                        "state_not": "ok"}]
    assert living[1] == {"type": "thermostat", "entity": "climate.tado_woonkamer"}  # the thermostat it follows
    tiles = {c["entity"]: c for c in living if c["type"] == "tile"}
    # The thermostat card shows the target; the mode and the temperature without Home Assistant
    # (easy to change by accident at night) stay on the room's device page.
    assert list(tiles) == [rooms["woonkamer"][k] for k in ("temperature", "inactive_until")]
    assert not any(c.get("features") for c in living)
    assert tiles[rooms["woonkamer"]["inactive_until"]]["visibility"] == inactive + [
        {"condition": "state", "entity": rooms["woonkamer"]["inactive_until"], "state_not": ["unavailable", "unknown"]}]
    assert tiles[rooms["woonkamer"]["temperature"]]["name"] == "Measured by E32"
    assert tiles[rooms["woonkamer"]["temperature"]]["visibility"] == active
    # One graph per room: measured and target over the last 24 hours, only while the room is on.
    day = next(c for c in living if c["type"] == "history-graph")
    assert [x["entity"] for x in day["entities"]] == [rooms["woonkamer"][k] for k in ("temperature", "setpoint")]
    assert day["visibility"] == active and "title" not in day
    # An inactive room says so in one calm line (its sources work, so no hint to choose one).
    off = next(c for c in living if c["type"] == "markdown")
    assert off == {"type": "markdown", "content": "This room is off and never asks for heat.", "visibility": inactive}
    # A Bluetooth-only room has no thermostat card, so it shows its target.
    bathroom = heating["sections"][2]["cards"]
    assert not any(c["type"] == "thermostat" for c in bathroom)
    assert [c["entity"] for c in bathroom if c["type"] == "tile"] == [
        rooms["badkamer"][k] for k in ("temperature", "setpoint", "inactive_until")]

    compare = comparison["sections"][0]["cards"]
    assert compare[0]["heading"] == "E32 and thermostat"
    history = next(c for c in compare if c["type"] == "history-graph")
    assert [x["entity"] for x in history["entities"]] == [
        hub["heat_request"], fields["thermostat_requested_flow_temperature"], fields["measured_flow_temperature"]]
    assert [x["name"] for x in history["entities"]] == ["Boiler request E32", "Thermostat request", "Flow temperature"]
    statistics = next(c for c in compare if c["type"] == "statistics-graph")
    assert statistics["entities"] == [hub["shadow_e32_heating_time_today"], hub["shadow_tado_heating_time_today"]]
    assert {c["entity"] for c in compare if c["type"] == "tile"} == {
        hub[k] for k in ("shadow_agreement_today", "shadow_e32_heating_time_today", "shadow_tado_heating_time_today",
                         "shadow_e32_starts_today", "shadow_tado_starts_today")}

    # The boiler: what "Now" does not show yet (no duplicate flow or hot water tile), then its day.
    boiler = heating["sections"][3]["cards"]
    assert [c["entity"] for c in boiler if c["type"] == "tile"] == [
        fields["measured_return_temperature"], fields["reported_burner_modulation"], fields["pressure"],
        fields["display_code"], hub["burner_starts_last_hour"], hub["burner_short_cycling"]]
    shown = [c["entity"] for c in view_cards(heating) if c["type"] == "tile"]
    assert len(shown) == len(set(shown)), "no tile twice on the Heating view"
    graph = next(c for c in boiler if c["type"] == "history-graph")
    assert [x["entity"] for x in graph["entities"]] == [
        fields["measured_flow_temperature"], fields["measured_return_temperature"], hub["heat_request"]]
    # No plan read yet: the sensor feeds no known room, so it is listed on the subview.
    bluetooth = comparison["sections"][1]["cards"][1]
    assert bluetooth["type"] == "glance" and bluetooth["title"] == "Thermometer badkamer"
    assert [x["entity"] for x in bluetooth["entities"]] == [sensors[k] for k in ("temperature", "humidity", "battery")]


@pytest.mark.asyncio
async def test_no_comparison_without_a_thermostat_on_the_bus(hass):
    e, rooms, sensors, hub, fields = installation(hass)
    entities = er.async_get(hass)
    for key in [k for k in hub if k.startswith("shadow_")]:
        entities.async_remove(hub.pop(key))
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    heating = config["views"][0]
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == ["Now", "Woonkamer", "Badkamer", "Boiler"]
    text = json.dumps(config)
    assert "Thermostat request" not in text and "Agreement" not in text
    # The subview keeps only the loose Bluetooth sensor.
    assert [s["cards"][0]["heading"] for s in config["views"][3]["sections"]] == ["Bluetooth sensors"]
    explain = next(c for c in heating["sections"][0]["cards"] if c["type"] == "markdown")
    assert "your thermostat controls" not in explain["content"]
    assert "current thermostat or the boiler's own control" in explain["content"]


@pytest.mark.asyncio
async def test_a_room_in_the_plan_shows_its_e32_thermostat_and_its_own_sensor(hass):
    """The E32 room climate is the room's dial; the Bluetooth sensor that feeds only this room is in its heading."""
    e, rooms, sensors, hub, fields = installation(hass)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    device = devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    own = entities.async_get_or_create("climate", "open_thermostat", "fixture_e32_room_woonkamer_thermostat",
                                       config_entry=e, device_id=device.id, suggested_object_id="woonkamer").entity_id
    plan = {"rooms": [{"id": "woonkamer", "sources": [{"type": "ble", "id": "a4c138a3e8db"}]},
                      {"id": "badkamer", "state": "inactive", "sources": [{"type": "ha", "id": "climate.gone"}]}]}
    hass.data["open_thermostat"][e.entry_id]["heating_hub"].plan = SimpleNamespace(
        plan=plan, room=lambda room_id: next((r for r in plan["rooms"] if r["id"] == room_id), None))
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    heating = config["views"][0]
    living = heating["sections"][1]["cards"]
    assert living[1] == {"type": "thermostat", "entity": own}
    # Its own climate shows the measurement: no second "Measured by E32" tile.
    assert rooms["woonkamer"]["temperature"] not in [c.get("entity") for c in living if c["type"] == "tile"]
    badges = living[0]["badges"]
    assert [b["entity"] for b in badges] == [rooms["woonkamer"]["demand"], rooms["woonkamer"]["status"],
                                             sensors["humidity"], sensors["battery"]]
    assert badges[3]["visibility"] == [{"condition": "numeric_state", "entity": sensors["battery"], "below": 20}]
    assert "Bluetooth sensors" not in json.dumps(config)  # the sensor is in its room
    # The bathroom follows an entity that no longer exists: when it is off, a hint to choose a source
    # first, removing the room second (both in Home Assistant's own pages).
    bathroom = heating["sections"][2]["cards"]
    inactive = [{"condition": "state", "entity": rooms["badkamer"]["state"], "state": "inactive"}]
    hint = [c for c in bathroom if c.get("visibility") == inactive and c["type"] in ("markdown", "heading")]
    assert [c.get("heading") or c["content"] for c in hint] == [
        "Badkamer is off and has no working temperature source. Choose a source to use it again, "
        "or remove the room if you no longer need it.", "Choose a source", "Remove room"]
    integration = "/config/integrations/integration/open_thermostat"
    assert [c["tap_action"]["navigation_path"] for c in hint[1:]] == [integration, integration]
    # With the Repairs item for it, "Choose a source" opens Repairs.
    from homeassistant.helpers import issue_registry as ir
    ir.async_create_issue(hass, "open_thermostat", f"e32_room_choose_source_{e.entry_id}_badkamer", is_fixable=True,
                          severity=ir.IssueSeverity.WARNING, translation_key="e32_room_choose_source")
    bathroom = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][0]["sections"][2]["cards"]
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
    assert "Learning" not in json.dumps(before) and "dhw_taps" not in json.dumps(before)  # older firmware
    _add_learned(hass, e, rooms, hub)
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    heating = config["views"][0]
    # Same sections; the learned values sit inside the room they belong to.
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == ["Now", "Woonkamer", "Badkamer", "Boiler"]
    living = heating["sections"][1]["cards"]
    room = rooms["woonkamer"]
    area = living[next(i for i, c in enumerate(living) if c.get("heading") == "Learning"):]
    assert [c["type"] for c in area] == ["heading", "tile", "tile", "markdown"]  # then the "room is off" line
    heading, advice, start = area[:3]
    assert heading["heading_style"] == "subtitle" and heading["icon"] == "mdi:school-outline"
    assert heading["badges"] == [{"type": "entity", "entity": room["learning"], "show_state": True,
                                  "show_icon": True, "color": "teal"}]
    known = lambda entity: {"condition": "state", "entity": entity, "state_not": ["unavailable", "unknown"]}
    assert heading["visibility"] == [known(room["learning"])]  # hidden while the E32 reports none
    assert (advice["entity"], advice["name"]) == (room["flow_advice"], "Recommended flow")
    assert advice["visibility"] == [{"condition": "state", "entity": room["learning"], "state": "ready"},
                                    known(room["flow_advice"])]
    assert (start["entity"], start["name"], start["visibility"]) == (
        room["heating_start"], "Heating starts", [known(room["heating_start"])])
    # A room without learned entities gets no learning area.
    assert not any(c.get("heading") == "Learning" for c in heating["sections"][2]["cards"])
    # How the learning works: one note on the Comparison subview, only while the E32 reports it.
    note = next(c for c in config["views"][3]["sections"][0]["cards"] if c["type"] == "markdown")
    assert "learns how fast each room warms up" in note["content"] and room["learning"] in note["content"]
    assert "advice only" in note["content"] and "'applied'" in note["content"]
    assert note["visibility"] == [known(room["learning"])]
    assert "learns how fast" not in json.dumps(heating)
    # Today's hot-water taps are a boiler tile; the day's details in Diagnostics.
    taps = next(c for c in heating["sections"][3]["cards"] if c.get("entity") == hub["dhw_taps_today"])
    assert (taps["name"], taps["visibility"]) == ("Taps today", [known(hub["dhw_taps_today"])])
    today = next(c for c in config["views"][2]["cards"] if c.get("title") == "Hot water today")
    assert today["entities"] == [hub[k] for k in ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today")]
    # In Dutch.
    hass.config.language = "nl"
    text = json.dumps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config(), ensure_ascii=False)
    for words in ('"Leren"', "Geadviseerde aanvoer", "Start verwarmen", "Tappen vandaag",
                  "Warm water vandaag", "leert ook hoe snel elke ruimte opwarmt", "alleen advies"):
        assert words in text, words


def test_dashboard_text_has_the_same_keys_in_both_languages():
    from custom_components.open_thermostat.dashboard import TEXT
    assert set(TEXT["en"]) == set(TEXT["nl"])
    assert all(TEXT["nl"][key].strip() for key in TEXT["nl"])


@pytest.mark.asyncio
async def test_dutch_headings_and_only_existing_enabled_entities(hass):
    e, rooms, sensors, hub, fields = installation(hass, "nl", with_hub=False)
    registry = er.async_get(hass)
    for entity_id in (hub["heat_request"], rooms["woonkamer"]["fallback_setpoint"], sensors["humidity"],
                      fields["thermostat_requested_flow_temperature"]):
        registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    registry.async_remove(hub["burner_short_cycling"])
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    heating = config["views"][0]
    assert [v["title"] for v in config["views"]] == ["Verwarming", "Ketel", "Diagnose", "Vergelijking"]
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == ["Nu", "Badkamer", "Woonkamer", "Ketel"]
    assert [s["cards"][0]["heading"] for s in config["views"][3]["sections"]] == [
        "E32 en thermostaat vergeleken", "Bluetooth-sensoren"]
    text = json.dumps(config, ensure_ascii=False)
    for gone in (hub["heat_request"], rooms["woonkamer"]["fallback_setpoint"], sensors["humidity"],
                 fields["thermostat_requested_flow_temperature"], hub["burner_short_cycling"]):
        assert gone not in text
    assert "Gemeten door E32" in text and "Schaduwmodus" not in text  # no request entity: no mode line
    assert "Zo werkt het" not in text and "ook zonder Home Assistant" in text
    assert "thermostat" not in [c["type"] for c in view_cards(heating)]  # no hub status: no thermostat link
    assert None not in list(walk(config))
    # A user name on the room device is the heading.
    device = dr.async_get(hass).async_get_device_by_identifier(
        ("open_thermostat", "fixture_e32_room_badkamer"), e.entry_id)
    dr.async_get(hass).async_update_device(device.id, name_by_user="Badkamer boven")
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert config["views"][0]["sections"][1]["cards"][0]["heading"] == "Badkamer boven"


@pytest.mark.asyncio
async def test_empty_installation_has_no_empty_sections(hass):
    e = entry(hass)
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert config["views"][0]["sections"] == [] and config["views"][1]["sections"] == []
    assert [c["type"] for c in config["views"][2]["cards"]] == ["markdown"]  # only the hot water note
    assert None not in list(walk(config))


@pytest.mark.asyncio
async def test_dashboard_rebuilds_for_new_rooms_or_language_but_not_every_reading(hass):
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
    await hass.async_block_till_done()
    assert saved[-1]["views"][0]["title"] == "Verwarming" and len(saved) == 2
    # A room or sensor the E32 no longer reports leaves the dashboard.
    heating.update({**STATUS, "rooms": STATUS["rooms"][:1], "ble_sensors": []})
    await hass.async_block_till_done()
    headings = [section["cards"][0]["heading"] for section in saved[-1]["views"][0]["sections"]]
    assert "Badkamer" not in headings and "Woonkamer" in headings and "Bluetooth-sensoren" not in headings
    dashboard._unwatch_hub()
    assert dashboard._heating_hub() is heating and heating._listeners == []


@pytest.mark.asyncio
async def test_status_comes_first_with_the_reasons_only_while_there_is_a_problem(hass):
    """The night-time check: "Heating: OK" (or "Problem" and why) is the first thing on the phone."""
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
    heating = config["views"][0]
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == [
        "Now", "Advice", "Woonkamer", "Badkamer", "Boiler"]
    status = heating["sections"][0]["cards"]
    # The problem sensor's own icon: a check when all is well, a warning when not.
    assert status[1] == {"type": "tile", "entity": hub["heating_problem"], "name": "Heating"}
    reasons = next(c for c in status if c["type"] == "markdown" and "'reasons'" in c["content"])
    assert reasons["type"] == "markdown" and hub["heating_problem"] in reasons["content"]
    assert "'reasons'" in reasons["content"]
    assert reasons["visibility"] == [{"condition": "state", "entity": hub["heating_problem"], "state": "on"}]
    # The boiler's own maximum (a knob on some boilers, a menu on others) is a boiler essential.
    boiler = next(s for s in heating["sections"] if s["cards"][0]["heading"] == "Boiler")["cards"]
    maximum = next(c for c in boiler if c.get("entity") == field)
    assert (maximum["name"], maximum["icon"]) == ("Boiler maximum", "mdi:thermometer-high")
    hass.config.language = "nl"
    text = json.dumps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config(), ensure_ascii=False)
    assert '"Nu"' in text and '"Verwarming"' in text and '"Ketelmaximum"' in text
