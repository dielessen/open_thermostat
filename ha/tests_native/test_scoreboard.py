"""Yesterday's scoreboard (scoreboard.py, E32 rc.4): is the thermostat getting better at its job?

Per room "Warm on time" and "Overshoot", per house the burner starts per heating hour, the hours of
short cycling, the gas for heating and per degree-day; each from fw/telemetry/summary "scoreboard",
only once the E32 reported a value, and "Yesterday in figures" on the Learning and settings view.
"""
from copy import deepcopy

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template

from custom_components.open_thermostat import scoreboard as module
from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.heating_link import HeatingHub, wanted_sensors
from custom_components.open_thermostat.room_overview import YESTERDAY_CARD_TYPE

STATUS = {"schema": 1, "revision": 3, "mode": "active", "request": {"heat": True, "flow_c": 38, "reason": "heating"},
          "ha_entities": [],
          "rooms": [{"id": "woonkamer", "name": "Woonkamer", "status": "ok", "temperature": 20.4, "setpoint": 21.0,
                     "demand": True},
                    {"id": "badkamer", "name": "Badkamer", "status": "ok", "temperature": 19.0, "setpoint": 20.0,
                     "demand": False}]}
# The E32's contract (rc.4): every number may be null (not measured).
BOARD = {"yesterday": {"day": "2026-11-04", "heating_h": 9, "heating_starts_per_h": 2.1, "short_cycle_h": 0.5,
                       "heating_kwh": 18.2, "degree_days": 9.4,
                       "rooms": [{"id": "woonkamer", "on_time_min": 12, "overshoot_c": 0.3},
                                 {"id": "badkamer", "on_time_min": None, "overshoot_c": None}]},
         "today": {"day": "2026-11-05", "heating_h": 3, "heating_starts_per_h": 1.5, "short_cycle_h": 0,
                   "heating_kwh": 6.1, "degree_days": None,
                   "rooms": [{"id": "woonkamer", "on_time_min": -4, "overshoot_c": None}]}}
HOUSE = ["burner_starts_per_heating_hour", "short_cycling_hours", "heating_gas_yesterday", "gas_per_degree_day"]


def hub(board=BOARD):
    h = HeatingHub("fixture")
    h.update(STATUS)
    summary = {"schema": 1, "learned": {"schema": 1, "applied": True, "status": "learning"}}
    if board is not None:
        summary["scoreboard"] = deepcopy(board)
    h.update_summary(summary)
    return h


def scoreboard_entities(h):
    return {key: factory() for key, factory in wanted_sensors(h)
            if key[0] == "scoreboard" or key[-1] in module.ROOM_FIGURES}


def test_firmware_before_rc4_gets_no_scoreboard_entities():
    assert scoreboard_entities(hub(None)) == {}
    assert scoreboard_entities(hub({"yesterday": None, "today": None})) == {}
    # Reported, but nothing measured yet: still no entity that would stay "unknown".
    empty = {"yesterday": {"day": "2026-11-04", "heating_h": None, "heating_starts_per_h": None, "short_cycle_h": None,
                           "heating_kwh": None, "degree_days": None, "rooms": [{"id": "woonkamer", "on_time_min": None,
                                                                               "overshoot_c": None}]}, "today": None}
    assert scoreboard_entities(hub(empty)) == {}


def test_each_figure_appears_once_the_e32_reported_a_value():
    entities = scoreboard_entities(hub())
    assert list(entities) == [("scoreboard", key) for key in HOUSE] + [("room", "woonkamer", "warm_on_time"),
                                                                       ("room", "woonkamer", "overshoot")]
    # A figure only today has creates nothing yet (1.0.0rc7): the state is yesterday's, so it would read
    # "unknown" all through the first day after the update; today's figure is an attribute once it exists.
    today_only = deepcopy(BOARD)
    today_only["yesterday"] = None
    assert scoreboard_entities(hub(today_only)) == {}
    yesterday_empty = deepcopy(BOARD)
    yesterday_empty["yesterday"]["heating_kwh"] = None
    assert ("scoreboard", "heating_gas_yesterday") not in scoreboard_entities(hub(yesterday_empty))
    assert ("scoreboard", "burner_starts_per_heating_hour") in scoreboard_entities(hub(yesterday_empty))


def test_the_room_figures():
    entities = scoreboard_entities(hub())
    on_time, overshoot = entities[("room", "woonkamer", "warm_on_time")], entities[("room", "woonkamer", "overshoot")]
    assert on_time.unique_id == "fixture_e32_room_woonkamer_warm_on_time"
    assert on_time.translation_key == "room_warm_on_time" and on_time.available
    assert on_time.native_value == 12 and on_time.native_unit_of_measurement == "min" and on_time.device_class is None
    assert on_time.extra_state_attributes == {"room_id": "woonkamer", "day": "2026-11-04", "today": -4}
    assert overshoot.native_value == 0.3 and overshoot.device_class == SensorDeviceClass.TEMPERATURE_DELTA
    assert overshoot.native_unit_of_measurement == "°C" and overshoot.extra_state_attributes["today"] is None
    for entity in (on_time, overshoot):  # history through the Recorder; today's figure is not recorded
        assert entity.state_class == SensorStateClass.MEASUREMENT and "today" in entity._unrecorded_attributes


def test_the_house_figures():
    entities = scoreboard_entities(hub())
    starts, short, gas, per_degree_day = (entities[("scoreboard", key)] for key in HOUSE)
    assert [e.unique_id for e in (starts, short, gas, per_degree_day)] == [f"fixture_hub_{key}" for key in HOUSE]
    assert [e.translation_key for e in (starts, short, gas, per_degree_day)] == HOUSE
    assert (starts.native_value, short.native_value, gas.native_value, per_degree_day.native_value) == (2.1, 0.5, 18.2, 1.94)
    assert starts.extra_state_attributes == {"day": "2026-11-04", "today": 1.5, "heating_hours": 9}
    assert short.device_class == SensorDeviceClass.DURATION and short.native_unit_of_measurement == "h"
    assert gas.native_unit_of_measurement == "kWh" and gas.device_class is None  # a day's figure, not a meter
    assert per_degree_day.native_unit_of_measurement == "kWh/°C·d"  # per degree-day, not kWh (1.0.0rc7)
    assert gas.extra_state_attributes == {"day": "2026-11-04", "today": 6.1}
    assert per_degree_day.extra_state_attributes == {"day": "2026-11-04", "today": None, "heating_kwh": 18.2,
                                                     "degree_days": 9.4}
    assert all(e.state_class == SensorStateClass.MEASUREMENT for e in (starts, short, gas, per_degree_day))
    # Diagnostic: the Learning view shows them, the device page keeps them out of the main list.
    assert all(e.entity_category == EntityCategory.DIAGNOSTIC for e in entities.values())


def test_odd_figures_are_left_out():
    board = deepcopy(BOARD)
    board["yesterday"].update(degree_days=0.6, heating_starts_per_h=-1, short_cycle_h="lots")
    board["yesterday"]["rooms"][0].update(on_time_min=5000, overshoot_c=True)
    yesterday = board["yesterday"]
    assert module.house_figure(yesterday, "gas_per_degree_day") is None  # a mild day: no per degree-day figure
    assert module.house_figure(yesterday, "burner_starts_per_heating_hour") is None
    assert module.house_figure(yesterday, "short_cycling_hours") is None
    assert module.room_figure(yesterday, "woonkamer", "warm_on_time") is None
    assert module.room_figure(yesterday, "woonkamer", "overshoot") is None
    assert module.room_figure(yesterday, "zolder", "overshoot") is None
    assert module.day_name({"day": 20261104}) is None


def test_the_figures_are_unavailable_while_the_e32_is_silent():
    h = hub()
    entities = scoreboard_entities(h)
    h.update(None)
    assert not any(entity.available for entity in entities.values())
    assert all(entity.extra_state_attributes is None for entity in entities.values())


def scoreboard_installation(hass, language):
    from test_dashboard_heating import installation
    e, rooms, sensors, hub_entities, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    device = devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"), e.entry_id)
    for key in ("warm_on_time", "overshoot"):
        rooms["woonkamer"][key] = entities.async_get_or_create(
            "sensor", "open_thermostat", f"fixture_e32_room_woonkamer_{key}", config_entry=e, device_id=device.id,
            suggested_object_id=f"woonkamer_{key}").entity_id
    for key in HOUSE:
        hub_entities[key] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_hub_{key}",
                                                         config_entry=e, suggested_object_id=key).entity_id
    return yesterday_section(hass, e.entry_id), rooms, hub_entities, e.entry_id


def yesterday_section(hass, entry_id):
    config = RoomDashboard(hass, "fixture", entry_id)._dashboard_config()
    learning = next(view for view in config["views"] if view["path"] == "learned")
    return next(s for s in learning["sections"] if s["cards"][0].get("icon") == "mdi:scoreboard-outline")


@pytest.mark.asyncio
async def test_the_yesterday_card_says_it_in_words(hass):
    """rc.5 (P15, the owner's sketch): the living room warm on time, burner starts per heating hour, gas for heating
    and the degree-days large on the figures card (frontend/house-card.js); the rest in words under it."""
    section, rooms, house, _ = scoreboard_installation(hass, "en")
    heading, figures, card, note = section["cards"]
    assert heading["heading"] == "Yesterday in figures" and note["type"] == "markdown"
    assert note["content"].startswith("Every day the thermostat checks whether each room was warm on time")
    large = [rooms["woonkamer"]["warm_on_time"], house["burner_starts_per_heating_hour"], house["heating_gas_yesterday"],
             house["gas_per_degree_day"]]
    assert figures == {"type": YESTERDAY_CARD_TYPE, "grid_options": {"columns": 12},
                       "room": {"entity": rooms["woonkamer"]["warm_on_time"], "name": "Woonkamer"},
                       "starts": house["burner_starts_per_heating_hour"], "gas": house["heating_gas_yesterday"],
                       "degree_days": house["gas_per_degree_day"], "visibility": [{"condition": "or", "conditions": [
                           {"condition": "state", "entity": entity, "state_not": ["unavailable", "unknown"]}
                           for entity in large]}]}
    # Hidden until one of its figures has a value (firmware before rc.4 never shows it); the lines while they have
    # nothing to add.
    assert [c for c in section["cards"] if "visibility" in c] == [figures] and card["show_empty"] is False
    assert {c["entity"] for c in section["visibility"][0]["conditions"]} == {
        rooms["woonkamer"]["warm_on_time"], rooms["woonkamer"]["overshoot"], *(house[key] for key in HOUSE)}
    # The heating hours and the degree-days are attributes of the burner-starts and gas-per-degree-day sensors.
    for entity_id, value, attributes in (
            (rooms["woonkamer"]["warm_on_time"], "12", None), (rooms["woonkamer"]["overshoot"], "0.3", None),
            (house["burner_starts_per_heating_hour"], "2.1", {"heating_hours": 9}), (house["short_cycling_hours"], "0.5", None),
            (house["heating_gas_yesterday"], "18.2", None), (house["gas_per_degree_day"], "1.94", {"degree_days": 9.4})):
        hass.states.async_set(entity_id, value, attributes)
    text = Template(card["content"], hass).async_render(parse_result=False)
    assert text == ("- **Woonkamer**: 0.3 °C too warm\n"
                    "- Heating time: 9.0 h · Short burner runs: 0.5 h\n"
                    "- 1.94 kWh per degree-day")
    hass.states.async_set(rooms["woonkamer"]["warm_on_time"], "-4")
    hass.states.async_set(rooms["woonkamer"]["overshoot"], "unknown")
    hass.states.async_set(house["gas_per_degree_day"], "unknown")  # and no degree_days attribute
    hass.states.async_set(house["short_cycling_hours"], "unavailable")
    hass.states.async_set(house["burner_starts_per_heating_hour"], "2.1", {"heating_hours": None})
    # Everything left is on the figures card: no lines, and no "tomorrow" under figures that have a value.
    assert Template(card["content"], hass).async_render(parse_result=False) == ""
    for text in ("Burner starts per heating hour", "Gas for heating", "Degree-days"):
        assert text not in card["content"], text  # said once, on the card


@pytest.mark.asyncio
async def test_the_yesterday_card_in_dutch_and_polish(hass):
    section, rooms, house, entry_id = scoreboard_installation(hass, "nl")
    card = section["cards"][2]
    assert section["cards"][0]["heading"] == "Gisteren in cijfers" and section["cards"][1]["type"] == YESTERDAY_CARD_TYPE
    for entity_id, value in ((rooms["woonkamer"]["warm_on_time"], "12"), (rooms["woonkamer"]["overshoot"], "0.3"),
                             (house["heating_gas_yesterday"], "18.2")):
        hass.states.async_set(entity_id, value)
    hass.states.async_set(house["gas_per_degree_day"], "1.94", {"degree_days": 9.4})
    text = Template(card["content"], hass).async_render(parse_result=False)
    assert text == ("- **Woonkamer**: 0,3 °C te warm\n"
                    "- 1,94 kWh per graaddag")
    hass.config.language = "pl"
    card = yesterday_section(hass, entry_id)["cards"][2]
    assert Template(card["content"], hass).async_render(parse_result=False).startswith(
        "- **Woonkamer**: 0,3 °C za ciepło\n")
