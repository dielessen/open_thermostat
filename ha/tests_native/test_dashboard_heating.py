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
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert [v["path"] for v in config["views"]] == ["heating", "boiler", "diagnostics"]
    heating = config["views"][0]
    assert (heating["title"], heating["type"], heating["max_columns"]) == ("Heating", "sections", 3)
    assert {card["type"] for view in config["views"] for card in view_cards(view)} <= BUILT_IN
    assert None not in list(walk(config))
    headings = [section["cards"][0]["heading"] for section in heating["sections"]]
    # The E32's room order, by room name (never the id); then the comparison, boiler and Bluetooth.
    assert headings == ["Now", "Woonkamer", "Badkamer", "E32 and thermostat", "Boiler", "Bluetooth sensors"]
    now = heating["sections"][0]["cards"]
    assert [c.get("entity") for c in now if c["type"] == "tile"] == [
        hub["heat_request"], fields["measured_flow_temperature"], hub["shadow_agreement_today"]]
    explain = next(c for c in now if c["type"] == "markdown")
    assert explain["content"].startswith("**How it works**\n\nYou set the rooms")
    assert "also without Home Assistant" in explain["content"] and "Shadow mode" in explain["content"]
    assert hub["heat_request"] in explain["content"]  # the mode line follows the E32's own status

    living = heating["sections"][1]["cards"]
    badges = living[0]["badges"]
    assert [b["entity"] for b in badges] == [rooms["woonkamer"]["demand"], rooms["woonkamer"]["status"]]
    assert badges[1]["visibility"] == [{"condition": "state", "entity": rooms["woonkamer"]["status"],
                                        "state_not": "ok"}]
    assert living[1] == {"type": "thermostat", "entity": "climate.tado_woonkamer"}  # the thermostat it follows
    tiles = {c["entity"]: c for c in living if c["type"] == "tile"}
    assert list(tiles) == [rooms["woonkamer"][k] for k in ("temperature", "setpoint", "state", "inactive_until",
                                                           "fallback_setpoint")]
    assert tiles[rooms["woonkamer"]["state"]]["features"] == [{"type": "select-options"}]
    assert tiles[rooms["woonkamer"]["inactive_until"]]["visibility"] == [
        {"condition": "state", "entity": rooms["woonkamer"]["state"], "state": "inactive"}]
    assert tiles[rooms["woonkamer"]["temperature"]]["name"] == "Measured by E32"
    # A Bluetooth-only room has no thermostat card.
    assert not any(c["type"] == "thermostat" for c in heating["sections"][2]["cards"])

    compare = heating["sections"][3]["cards"]
    history = next(c for c in compare if c["type"] == "history-graph")
    assert [x["entity"] for x in history["entities"]] == [
        hub["heat_request"], fields["thermostat_requested_flow_temperature"], fields["measured_flow_temperature"]]
    assert [x["name"] for x in history["entities"]] == ["Boiler request E32", "Thermostat request", "Flow temperature"]
    statistics = next(c for c in compare if c["type"] == "statistics-graph")
    assert statistics["entities"] == [hub["shadow_e32_heating_time_today"], hub["shadow_tado_heating_time_today"]]
    assert {c["entity"] for c in compare if c["type"] == "tile"} == {
        hub[k] for k in ("shadow_e32_heating_time_today", "shadow_tado_heating_time_today",
                         "shadow_e32_starts_today", "shadow_tado_starts_today")}

    boiler = heating["sections"][4]["cards"]
    assert [c["entity"] for c in boiler if c["type"] == "tile"] == [
        fields["measured_flow_temperature"], fields["measured_return_temperature"],
        fields["reported_burner_modulation"], fields["pressure"], fields["measured_dhw_temperature"],
        fields["display_code"], hub["burner_starts_last_hour"], hub["burner_short_cycling"]]
    bluetooth = heating["sections"][5]["cards"][1]
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
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == [
        "Now", "Woonkamer", "Badkamer", "Boiler", "Bluetooth sensors"]
    text = json.dumps(heating)
    assert "Thermostat request" not in text and "Agreement with thermostat" not in text
    explain = next(c for c in heating["sections"][0]["cards"] if c["type"] == "markdown")
    assert "your thermostat controls" not in explain["content"]
    assert "current thermostat or the boiler's own control" in explain["content"]


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
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == [
        "Now", "Woonkamer", "Badkamer", "E32 and thermostat", "Boiler", "Bluetooth sensors"]
    living = heating["sections"][1]["cards"]
    room = rooms["woonkamer"]
    area = living[next(i for i, c in enumerate(living) if c.get("heading") == "Learning"):]
    assert [c["type"] for c in area] == ["heading", "tile", "tile"]
    heading, advice, start = area
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
    # One line in "How it works", only while the E32 reports the learning.
    explain = next(c for c in heating["sections"][0]["cards"] if c["type"] == "markdown")["content"]
    assert "learns how fast each room warms up" in explain and room["learning"] in explain
    assert "advice only" in explain and "'applied'" in explain
    # The hot-water tile sits next to the hot water temperature; the day's details in Diagnostics.
    boiler = [c["entity"] for c in heating["sections"][4]["cards"] if c["type"] == "tile"]
    assert boiler[boiler.index(fields["measured_dhw_temperature"]) + 1] == hub["dhw_taps_today"]
    taps = next(c for c in heating["sections"][4]["cards"] if c.get("entity") == hub["dhw_taps_today"])
    assert (taps["name"], taps["visibility"]) == ("Hot water taps today", [known(hub["dhw_taps_today"])])
    today = next(c for c in config["views"][2]["cards"] if c.get("title") == "Hot water today")
    assert today["entities"] == [hub[k] for k in ("dhw_taps_today", "dhw_keep_warm_today", "dhw_burner_time_today")]
    # In Dutch.
    hass.config.language = "nl"
    text = json.dumps(RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config(), ensure_ascii=False)
    for words in ('"Leren"', "Geadviseerde aanvoer", "Start verwarmen", "Warmwatertappen vandaag",
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
    assert [v["title"] for v in config["views"]] == ["Verwarming", "Ketel", "Diagnose"]
    assert [s["cards"][0]["heading"] for s in heating["sections"]] == [
        "Nu", "Badkamer", "Woonkamer", "E32 en thermostaat vergeleken", "Ketel", "Bluetooth-sensoren"]
    text = json.dumps(config, ensure_ascii=False)
    for gone in (hub["heat_request"], rooms["woonkamer"]["fallback_setpoint"], sensors["humidity"],
                 fields["thermostat_requested_flow_temperature"], hub["burner_short_cycling"]):
        assert gone not in text
    assert "Gemeten door E32" in text and "Schaduwmodus" not in text  # no request entity: no mode line
    assert "**Zo werkt het**" in text and "ook zonder Home Assistant" in text
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
