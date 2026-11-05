"""The Overview's house card (E32 rc.5, frontend/house-card.js): where it sits, what it reads, the one-room rule.

The card stands alone on top of the Overview, without a heading (the owner's sketch, P18: the House section with the
house mode is further down, test_dashboard_overview_sketch.py), and reads only Home Assistant: the heat request, what
the boiler does, the boiler's heating and hot-water bits, the water temperature to heating, today's taps, the gas
sensors, today's burner starts, the house mode and the heating problem; a key is in its config only when its entity is
in the registry. It takes the place of the rooms-that-want-heat card and the problem tile with its reasons, which stay
only for a house card that cannot be built (no heat request and no boiler activity). A house with exactly one room
switched on shows that room in the card as a summary; as the sketch, every room keeps its status card under Rooms too,
the rooms that are on first. What the card draws from these entities is checked in a browser by
test/ha-house-card-browser.cjs.
"""
import json
import re
import string
from pathlib import Path

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat import week_planner
from custom_components.open_thermostat.dashboard import ROOM_STATUS_CARD_TYPE, TEXT, RoomDashboard, view_cards
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.room_overview import HOUSE_CARD_TYPE, HOUSE_CARD_URL, YESTERDAY_CARD_TYPE
from test_dashboard_heating import STATUS, installation, walk

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "ha/config/custom_components/open_thermostat"
CARD = (COMPONENT / "frontend/house-card.js").read_text(encoding="utf-8")
# The house card's own entities on the product device, beside those of test_dashboard_heating.installation.
HUB = (("sensor", "boiler_activity"), ("sensor", "dhw_taps_today"), ("sensor", "heating_gas"), ("sensor", "hot_water_gas"),
       ("sensor", "daily_burner_starts"), ("binary_sensor", "heating_problem"))
FIELDS = ("heating_active", "dhw_active")


def house(hass, language="en", *, hub_keys=HUB, fields_keys=FIELDS, reasons=("woonkamer", "badkamer"), states=None,
          remove=(), no_fields=False):
    """The fixture installation with the house card's entities, the house mode and the rooms' Reason sensors.

    states: {room id: state} the E32 reports (rooms not named are "active"); remove: hub keys to take out of the
    registry; no_fields: no boiler fields at all (an older E32)."""
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    for domain, key in hub_keys:
        hub[key] = entities.async_get_or_create(domain, "open_thermostat", f"fixture_hub_{key}", config_entry=e,
                                                device_id=product.id, suggested_object_id=key).entity_id
    for name in fields_keys:
        fields[name] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_boiler_fields_v1_{name}",
                                                    config_entry=e, device_id=product.id, suggested_object_id=name).entity_id
    hub["house_mode"] = entities.async_get_or_create("select", "open_thermostat", "fixture_house_mode", config_entry=e,
                                                     device_id=product.id, suggested_object_id="house_mode").entity_id
    for room_id in reasons:
        device = devices.async_get_device_by_identifier(("open_thermostat", f"fixture_e32_room_{room_id}"), e.entry_id)
        rooms[room_id]["reason"] = entities.async_get_or_create(
            "sensor", "open_thermostat", f"fixture_e32_room_{room_id}_reason", config_entry=e, device_id=device.id,
            suggested_object_id=f"{room_id}_reason").entity_id
    for key in remove:
        entities.async_remove(hub.pop(key))
    if no_fields:
        for name in list(fields):
            entities.async_remove(fields.pop(name))
    heating = hass.data["open_thermostat"][e.entry_id]["heating_hub"]
    if states:
        heating.update(reported(states))
    board = RoomDashboard(hass, "fixture", e.entry_id)
    config = board._dashboard_config()
    assert None not in list(walk(config))
    return config, rooms, hub, fields, board, heating


def reported(states, rooms=None):
    """The fixture's E32 status with each room's state (switched on: "active", off: "inactive")."""
    status = json.loads(json.dumps(STATUS))
    status["rooms"] = [{**room, "state": states.get(room["id"], "active")} for room in status["rooms"]
                       if rooms is None or room["id"] in rooms]
    return status


def overview(config):
    return config["views"][0]


def section(config, number):
    return overview(config)["sections"][number]["cards"]


def card(config):
    """The house card: alone in the Overview's first section, without a heading (rc.5, the owner's sketch)."""
    cards = section(config, 0)
    assert len(cards) == 1 and cards[0]["type"] == HOUSE_CARD_TYPE
    return cards[0]


@pytest.mark.asyncio
async def test_the_house_card_heads_the_overview_and_reads_every_entity_it_needs(hass):
    config, rooms, hub, fields, board, _ = house(hass)
    # The house card alone across the top, without a heading (rc.5, the owner's sketch: P18); the house mode and the
    # holiday line are in the House section further down (test_dashboard_overview_sketch.py). Across the whole view on
    # a wide screen (its section spans every column: 12 grid columns each, so 12 would be a part of it).
    assert card(config) == {
        "type": HOUSE_CARD_TYPE, "grid_options": {"columns": "full"}, "request": hub["heat_request"],
        "activity": hub["boiler_activity"], "heating": fields["heating_active"],
        "flow": fields["measured_flow_temperature"], "hot_water": fields["dhw_active"], "taps": hub["dhw_taps_today"],
        "gas": [hub["heating_gas"], hub["hot_water_gas"]], "starts": hub["daily_burner_starts"],
        "mode": hub["house_mode"], "problem": hub["heating_problem"]}
    assert "visibility" not in card(config)  # always there: it says itself when the E32 has not reported yet
    assert overview(config)["sections"][0]["column_span"] == 3 and "visibility" not in overview(config)["sections"][0]
    house_section = overview(config)["sections"][-1]["cards"]
    assert house_section[0]["heading"] == "House" and house_section[2]["show_empty"] is False
    assert hub["house_mode"] in house_section[2]["content"]
    # What it absorbs is gone: the rooms that want heat, the problem tile and its reasons.
    text = json.dumps(overview(config))
    assert "set wanting" not in text and "'reasons'" not in text and "/config/repairs" not in text
    assert not any(card.get("entity") == hub["heating_problem"] for card in view_cards(overview(config)))
    # Both rooms are switched on: the card shows no room and the Rooms section keeps both status cards.
    rooms_section = section(config, 1)
    assert rooms_section[0]["heading"] == "Rooms"
    assert rooms_section[1:] == [{"type": ROOM_STATUS_CARD_TYPE, "entity": rooms[key]["reason"], "name": name,
                                  "mode": hub["house_mode"]}
                                 for key, name in (("woonkamer", "Woonkamer"), ("badkamer", "Badkamer"))]
    # The card is the only one of its kind, on the Overview only.
    assert [card["type"] for view in config["views"] for card in view_cards(view)].count(HOUSE_CARD_TYPE) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["no gas", "no boiler activity", "no boiler fields", "older firmware", "no request"])
async def test_the_card_reads_only_what_the_registry_has(hass, case):
    """Each key is there only with its entity: another boiler, another E32 or a disabled sensor draws less."""
    hub_keys, missing, extra = HUB, set(), {}
    if case == "no gas":
        hub_keys, missing = tuple(item for item in HUB if not item[1].endswith("_gas")), {"gas"}
    elif case == "no boiler activity":
        hub_keys, missing = tuple(item for item in HUB if item[1] != "boiler_activity"), {"activity"}
    elif case == "no boiler fields":
        extra, missing = {"no_fields": True, "fields_keys": ()}, {"heating", "hot_water", "flow"}
    elif case == "older firmware":  # no hot water today and no daily figures (before beta.23 and 1.0)
        hub_keys = tuple(item for item in HUB if item[1] not in ("dhw_taps_today", "daily_burner_starts"))
        missing = {"taps", "starts"}
    else:
        extra, missing = {"remove": ("heat_request",)}, {"request"}
    config, rooms, hub, fields, board, _ = house(hass, hub_keys=hub_keys, **extra)
    keys = {"request", "activity", "heating", "flow", "hot_water", "taps", "gas", "starts", "mode", "problem"}
    assert set(card(config)) - {"type", "grid_options"} == keys - missing


@pytest.mark.asyncio
async def test_gas_today_is_heating_and_hot_water_only(hass):
    """Tapping and keeping warm are parts of hot water: never added to the figure a second time."""
    hub_keys = (*(item for item in HUB if item[1] != "hot_water_gas"), ("sensor", "tapping_gas"),
                ("sensor", "keep_warm_gas"))
    config, rooms, hub, fields, board, _ = house(hass, hub_keys=hub_keys)
    assert card(config)["gas"] == [hub["heating_gas"]]


@pytest.mark.asyncio
async def test_without_request_and_activity_no_card_and_the_cards_it_replaces_stay(hass):
    """No heat request and no boiler activity (both disabled, or a registry from before them): no house card; the
    rooms-that-want-heat card (nothing without its request) and the problem tile with its reasons, as before."""
    hub_keys = tuple(item for item in HUB if item[1] != "boiler_activity")
    config, rooms, hub, fields, board, _ = house(hass, hub_keys=hub_keys, remove=("heat_request",))
    cards = section(config, 0)
    assert HOUSE_CARD_TYPE not in json.dumps(config)
    on = [{"condition": "state", "entity": hub["heating_problem"], "state": "on"}]
    # In the house card's place on top (rc.5, P18), without a heading, while there is a problem; across every column
    # of the view, as the card would be.
    assert [card["type"] for card in cards] == ["tile", "markdown"]
    assert cards[0] == {"type": "tile", "entity": hub["heating_problem"], "name": "Heating", "visibility": on,
                        "state_content": ["reason"], "grid_options": {"columns": "full"},
                        "tap_action": {"action": "navigate", "navigation_path": "/config/repairs"}}
    assert cards[1]["visibility"] == on and "'reasons'" in cards[1]["content"] and cards[1]["grid_options"] == {
        "columns": "full"}
    # And every room keeps its own card, the one switched on first.
    hass.data["open_thermostat"][board.entry_id]["heating_hub"].update(reported({"badkamer": "inactive"}))
    rooms_section = section(board._dashboard_config(), 1)
    assert rooms_section[0]["heading"] == "Rooms" and len(rooms_section) == 3


@pytest.mark.asyncio
async def test_one_room_switched_on_is_in_the_house_card_and_first_under_rooms(hass):
    """The owner's house: the living room is on, the bathroom off. The living room is in the card (its Reason sensor:
    now against target and why) as a summary, and, as the owner's sketch, its status card stands first under Rooms
    (its line, its chips and the tap to its history), the bathroom's after it."""
    config, rooms, hub, fields, board, _ = house(hass, states={"badkamer": "inactive", "woonkamer": "active"})
    assert card(config)["rooms"] == [{"entity": rooms["woonkamer"]["reason"], "name": "Woonkamer"}]
    assert section(config, 1) == [
        {"type": "heading", "heading": "Rooms", "heading_style": "title", "icon": "mdi:thermostat"},
        *({"type": ROOM_STATUS_CARD_TYPE, "entity": rooms[key]["reason"], "name": name, "mode": hub["house_mode"]}
          for key, name in (("woonkamer", "Woonkamer"), ("badkamer", "Badkamer")))]
    # The Rooms view still has every room in full.
    assert [s["cards"][0]["heading"] for s in config["views"][1]["sections"]][:2] == ["Woonkamer", "Badkamer"]
    for language, heading in (("nl", "Ruimtes"), ("pl", "Pomieszczenia")):
        hass.config.language = language
        assert section(board._dashboard_config(), 1)[0]["heading"] == heading
    # The room that is on comes first, wherever the E32 lists it.
    hass.config.language = "en"
    heating = hass.data["open_thermostat"][board.entry_id]["heating_hub"]
    heating.update(reported({"woonkamer": "inactive", "badkamer": "active"}))
    assert [c["name"] for c in section(board._dashboard_config(), 1)[1:]] == ["Badkamer", "Woonkamer"]


@pytest.mark.asyncio
async def test_a_one_room_house_shows_its_room_in_the_card_and_under_rooms(hass):
    config, rooms, hub, fields, board, heating = house(hass)
    heating.update(reported({}, rooms=("woonkamer",)))  # the E32 reports only the living room
    config = board._dashboard_config()
    assert [s["cards"][0].get("heading") for s in overview(config)["sections"]] == [None, "Rooms", "House"]
    assert card(config)["rooms"] == [{"entity": rooms["woonkamer"]["reason"], "name": "Woonkamer"}]
    assert [c["entity"] for c in section(config, 1)[1:]] == [rooms["woonkamer"]["reason"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("states, reasons", [
    ({}, ("woonkamer", "badkamer")),                                     # two rooms on
    ({"woonkamer": "inactive", "badkamer": "inactive"}, ("woonkamer", "badkamer")),  # every room off
    ({"badkamer": "inactive"}, ("badkamer",)),                           # the one room on has no Reason sensor
])
async def test_otherwise_every_room_keeps_its_own_card(hass, states, reasons):
    config, rooms, hub, fields, board, _ = house(hass, states=states, reasons=reasons)
    assert "rooms" not in card(config)
    cards = section(config, 1)
    assert cards[0]["heading"] == "Rooms" and len(cards) == 3
    # A room without its Reason sensor (an older integration's registry) keeps its temperature tile.
    assert {card["type"] for card in cards[1:]} == ({ROOM_STATUS_CARD_TYPE} if len(reasons) == 2
                                                    else {ROOM_STATUS_CARD_TYPE, "tile"})


@pytest.mark.asyncio
async def test_switching_a_room_on_or_off_rebuilds_the_overview(hass):
    """_signature follows each room's state: off, the other room moves into the card; a new reading rebuilds nothing."""
    config, rooms, hub, fields, board, heating = house(hass)
    saved = []

    class Store:
        async def async_load(self, force):
            return saved[-1] if saved else None

        async def async_save(self, config):
            saved.append(config)
    board._store = Store()
    board._watch_hub()
    heating.update(reported({}))
    await hass.async_block_till_done()
    assert len(saved) == 1 and "rooms" not in card(saved[-1])
    heating.update(reported({"badkamer": "inactive"}))
    await hass.async_block_till_done()
    assert len(saved) == 2
    assert card(saved[-1])["rooms"] == [{"entity": rooms["woonkamer"]["reason"], "name": "Woonkamer"}]
    reading = reported({"badkamer": "inactive"})
    reading["rooms"][0]["temperature"] = 20.6
    heating.update(reading)
    await hass.async_block_till_done()
    assert len(saved) == 2
    board._unwatch_hub()
    hub_only = HeatingHub("other")
    hub_only.update(reported({}))
    before = RoomDashboard._signature(hub_only)
    hub_only.update(reported({"woonkamer": "inactive"}))
    assert RoomDashboard._signature(hub_only) != before


def test_the_card_module_is_served_with_the_others_and_carries_the_version():
    version = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))["version"]
    assert HOUSE_CARD_URL == f"/open_thermostat/house-card-{version}.js"
    assert HOUSE_CARD_TYPE == "custom:openthermostat-house"
    assert HOUSE_CARD_URL in week_planner.card_modules()
    assert '(HOUSE_CARD_URL, "house-card.js")' in (COMPONENT / "week_planner.py").read_text(encoding="utf-8")
    # The static step of scripts/final_check.sh checks it with the other six versioned URLs.
    assert """'room_overview.py|HOUSE_CARD_URL = "/open_thermostat/house-card-'""" in (
        ROOT / "scripts/final_check.sh").read_text(encoding="utf-8")
    assert "ensureDefined('openthermostat-house', OpenThermostatHouse);" in CARD
    assert "getGridOptions() { return {columns: 12, min_columns: 12}; }" in CARD and "getCardSize() { return 5; }" in CARD
    # The Learning view's Yesterday figures (rc.5, P15) come from the same module: no eighth URL.
    assert YESTERDAY_CARD_TYPE == "custom:openthermostat-yesterday"
    assert "ensureDefined('openthermostat-yesterday', OpenThermostatYesterday);" in CARD
    assert re.findall(r"\['(openthermostat-[\w-]+)', 'OpenThermostat", CARD) == ["openthermostat-house", "openthermostat-yesterday"]


def test_the_card_asks_home_assistant_only_and_sparingly():
    """Never the E32 (session hygiene): Home Assistant's history and statistics, throttled, dropped on disconnect."""
    assert re.findall(r"callWS\(\{type: '([\w/]+)'", CARD) == [
        "history/history_during_period", "recorder/statistics_during_period", "recorder/statistic_during_period"]
    assert CARD.count("callWS(") == 3 and "subscribe" not in CARD  # no stream that keeps running
    assert re.findall(r"https?://[^'\"\s]+", CARD) == ["http://www.w3.org/2000/svg"]
    for word in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "192.168.", "/api/"):
        assert word not in CARD, word
    assert "HISTORY_MS = 5 * 60000, STATS_MS = 10 * 60000" in CARD
    assert "disconnectedCallback() {\n  clearInterval(this._timer)" in CARD and "this._gen++;" in CARD


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def card_texts(name):
    sensor = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["entity"]["sensor"]
    return sensor["heat_request"]["state_attributes"]["card"]["state"]


def test_the_card_texts_are_in_every_language_with_the_same_placeholders():
    english = card_texts("strings.json")
    # The card's own English last resort is the same text, key for key.
    fallback = dict(re.findall(r"(\w+): '([^']*)'", re.search(r"const TEXT = \{(.*?)\};", CARD, re.S)[1]))
    assert fallback == english
    assert card_texts("translations/en.json") == english
    for language in ("nl", "pl"):
        words = card_texts(f"translations/{language}.json")
        assert set(words) == set(english), language
        for key, text in words.items():
            assert text.strip() and placeholders(text) == placeholders(english[key]), (language, key)
    nl, pl = card_texts("translations/nl.json"), card_texts("translations/pl.json")
    # The words of the proposal and docs/UX-GLOSSARY.md.
    assert (nl["status_heating"], nl["gas_today"], nl["starts_today"], nl["idle"]) == (
        "Verwarmt · water {flow} °C", "Gas vandaag", "Branderstarts vandaag", "Ketel in rust")
    assert nl["attention"].startswith("Let op: ") and nl["request"].startswith("Ketelvraag")
    assert nl["legend_keep_warm"] == "Warmhouden" and pl["legend_keep_warm"] == "Podtrzymanie"
    # The words of the owner's sketch (rc.5 design, Main and Leren).
    assert (nl["today_since"], nl["now"], nl["target"], nl["per_day"]) == (
        "Vandaag sinds middernacht", "nu", "doel {t} °C", "{n} dagen: {value} per dag")
    assert (nl["warm"], nl["early"], nl["late"], nl["degree_days"]) == (
        "{room} warm", "{m} min te vroeg", "{m} min te laat", "Graaddagen")
    # The Yesterday figures are labelled by their sensors' own names; the card's English last resort is the same.
    names = dict(re.findall(r"(\w+): '([^']*)'", re.search(r"const NAMES = \{(.*?)\};", CARD, re.S)[1]))
    sensors = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))["entity"]["sensor"]
    assert names == {key: sensors[key]["name"] for key in ("burner_starts_per_heating_hour", "heating_gas_yesterday")}
    assert pl["request"].startswith("Żądanie do kotła") and pl["all_reasons"] == TEXT["pl"]["problem_more"]
    for words in (english, nl, pl):
        assert not any(term in text.lower() for text in words.values()
                       for term in ("shadow", "digest", "schema", "setpoint", "modulation")), words
    # Every room has its card under Rooms (rc.5, the owner's sketch): no "Other rooms" heading any more.
    assert all("other_rooms" not in TEXT[language] for language in ("en", "nl", "pl"))
