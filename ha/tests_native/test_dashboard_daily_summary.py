"""Yesterday in figures (rc.5): the four headline figures large on their own card (the lead room warm on time, burner
starts per heating hour, gas for heating, degree-days; frontend/house-card.js, as the owner's sketch), under them the
rest of the scoreboard and the daily summary in words, once, on the Learning view, with the missed comfort per day; the
burner hours per day are on the Boiler view under "Today and this week". What the figures card draws is checked in a
browser by test/ha-house-card-browser.cjs."""
import json

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template

from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.room_overview import YESTERDAY_CARD_TYPE
from test_dashboard_heating import installation, walk
from test_dashboard_house import reported
from test_dashboard_tidy import live


def view(config, path):
    return next(v for v in config["views"] if v["path"] == path)


def heading_section(view, heading):
    return next((s["cards"] for s in view["sections"] if s["cards"][0].get("heading") == heading), None)


def with_summary(hass, language):
    e, rooms, sensors, hub, fields = installation(hass, language)
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    for key in ("daily_summary", "daily_burner_time", "daily_burner_starts", "daily_missed_comfort", "heating_gas"):
        hub[key] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_hub_{key}", config_entry=e,
                                                device_id=product.id, suggested_object_id=key).entity_id
    hass.states.async_set(hub["heating_gas"], "12.5", {"unit_of_measurement": "m³"})
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    return config, hub


def known(entity_id):
    return [{"condition": "state", "entity": entity_id, "state_not": ["unavailable", "unknown"]}]


@pytest.mark.asyncio
async def test_yesterday_in_figures_is_on_the_learning_view_once_with_the_missed_comfort_per_day(hass):
    config, hub = with_summary(hass, "en")
    cards = heading_section(view(config, "learned"), "Yesterday in figures")
    assert cards is not None
    text = cards[1]["content"]
    assert f"state_attr(\"{hub['daily_summary']}\", 'last_day')" in text
    assert "{{ d.burner_hours }}" in text and "{{ d.burner_starts }}" in text and "{{ d.short_runs }}" in text
    assert "~ ' m³'" in text  # the gas in the gas sensor's unit
    assert "The first full day appears here tomorrow." in text and "d.date" not in text  # no date header
    charts = [card for card in cards if card.get("type") == "statistics-graph"]
    assert [c["entities"][0]["entity"] for c in charts] == [hub["daily_missed_comfort"]]
    assert charts[0]["visibility"] == known(hub["daily_missed_comfort"])
    assert all(c["stat_types"] == ["change"] and c["period"] == "day" and c["days_to_show"] == 7
               and c["chart_type"] == "bar" for c in charts)
    # "Yesterday" once: not on the Boiler view any more; its burner hours per day are under "Today and this week".
    boiler = view(config, "boiler")
    assert "'last_day'" not in json.dumps(boiler) and hub["daily_missed_comfort"] not in json.dumps(boiler)
    today = heading_section(boiler, "Today and this week")
    burner = next(c for c in today if c["type"] == "statistics-graph" and c["title"] == "Burner hours per day")
    assert burner["entities"] == [{"entity": hub["daily_burner_time"]}] and burner["visibility"] == known(
        hub["daily_burner_time"])
    assert sum(json.dumps(v).count("'last_day'") for v in config["views"]) == 1


@pytest.mark.asyncio
async def test_yesterday_in_figures_renders_the_summary_as_list_lines(hass):
    config, hub = with_summary(hass, "en")
    card = heading_section(view(config, "learned"), "Yesterday in figures")[1]
    day = {"date": "2026-11-03", "complete": True, "burner_hours": 6.3, "burner_starts": 14, "short_runs": 2,
           "gas": {"heating": 1.2, "hot_water": 0.8}, "outdoor": {"min": 3.1, "max": 9.4},
           "rooms": [{"room": "woonkamer", "name": "Woonkamer", "heat_hours": 6.0, "time_to_target_minutes": 25,
                      "missed_minutes": 0},
                     {"room": "badkamer", "name": "Badkamer", "heat_hours": 0.0, "time_to_target_minutes": None,
                      "missed_minutes": 0}]}
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": day})
    text = Template(card["content"], hass).async_render(parse_result=False)
    assert text == ("- Burner 6.3 h, 14 starts (2 shorter than 10 minutes). Gas: heating 1.2 m³, hot water 0.8 m³. "
                    "Outdoor 3.1 to 9.4 °C.\n"
                    "- Woonkamer: asked for heat 6.0 h; warm after 25 min on average; missed comfort 0 min.\n"
                    "- Badkamer: asked for heat 0.0 h; missed comfort 0 min.")
    # rc7: one outdoor temperature all day is that temperature, not "Outdoor 5.0 to 5.0 °C".
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": {**day, "outdoor": {"min": 5.0, "max": 5.0}}})
    assert "Outdoor 5.0 °C.\n" in Template(card["content"], hass).async_render(parse_result=False)
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": {**day, "complete": False, "rooms": []}})
    assert Template(card["content"], hass).async_render(parse_result=False).endswith(
        "\n\n_Partial day: the E32 was not heard all day, so the figures are incomplete._")
    hass.states.async_set(hub["daily_summary"], "unknown", {})
    assert Template(card["content"], hass).async_render(parse_result=False) == (
        "The first full day appears here tomorrow.")


@pytest.mark.asyncio
async def test_one_gas_figure_as_a_tile_and_tomorrow_only_while_nothing_has_a_value(hass):
    """With the scoreboard (E32 rc.4) next to the summary: its gas for heating is the one gas figure, large on the
    figures card above the lines, which do not say it again; the summary's gas line only while the scoreboard has no
    gas. "Tomorrow" only shows while no figure, on the card or in the lines, has a value."""
    e, rooms, sensors, hub, fields = installation(hass, "en")
    entities, devices = er.async_get(hass), dr.async_get(hass)
    product = devices.async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    for key in ("daily_summary", "heating_gas_yesterday", "gas_per_degree_day"):
        hub[key] = entities.async_get_or_create("sensor", "open_thermostat", f"fixture_hub_{key}", config_entry=e,
                                                device_id=product.id, suggested_object_id=key).entity_id
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    section = next(s for s in view(config, "learned")["sections"] if s["cards"][0]["heading"] == "Yesterday in figures")
    assert {c["entity"] for c in section["visibility"][0]["conditions"]} == {
        hub["daily_summary"], hub["heating_gas_yesterday"], hub["gas_per_degree_day"]}
    # The figures this house has (no room warm on time, no burner starts per heating hour): gas and degree-days.
    figures, card = section["cards"][1:3]
    assert figures == {"type": YESTERDAY_CARD_TYPE, "grid_options": {"columns": 12}, "gas": hub["heating_gas_yesterday"],
                       "degree_days": hub["gas_per_degree_day"], "visibility": [{"condition": "or", "conditions": [
                           known(hub["heating_gas_yesterday"])[0], known(hub["gas_per_degree_day"])[0]]}]}
    assert card["type"] == "markdown" and card["show_empty"] is False  # nothing to add: no empty card
    assert "Gas for heating" not in card["content"] and "Degree-days" not in card["content"]
    day = {"complete": True, "burner_hours": 6.3, "burner_starts": 14, "short_runs": 2,
           "gas": {"heating": 1.2, "hot_water": 0.8}, "outdoor": None, "rooms": []}
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": day})
    hass.states.async_set(hub["heating_gas_yesterday"], "18.2")
    text = Template(card["content"], hass).async_render(parse_result=False)
    assert text == "- Burner 6.3 h, 14 starts (2 shorter than 10 minutes)."  # the gas is on the card
    hass.states.async_set(hub["heating_gas_yesterday"], "unknown")  # the scoreboard has no gas: the summary says it
    assert "Gas: heating 1.2, hot water 0.8." in Template(card["content"], hass).async_render(parse_result=False)
    hass.states.async_set(hub["daily_summary"], "unknown", {})
    assert Template(card["content"], hass).async_render(parse_result=False) == (
        "The first full day appears here tomorrow.")
    hass.states.async_set(hub["heating_gas_yesterday"], "18.2")  # a figure on the card: no "tomorrow" under it
    assert Template(card["content"], hass).async_render(parse_result=False) == ""


@pytest.mark.asyncio
async def test_the_four_headline_figures_are_large_and_the_lines_do_not_repeat_them(hass):
    """The owner's sketch (Leren): the lead room warm on time, burner starts per heating hour, gas for heating and the
    degree-days, two by two on one card, each from its own sensor; the lines under it keep the rest (the other room,
    overshoot, heating time, short runs, gas per degree-day) and say none of the four again."""
    config, rooms, sensors, hub, fields, flow = live(hass)
    cards = heading_section(view(config, "learned"), "Yesterday in figures")
    entities = [rooms["woonkamer"]["warm_on_time"], hub["burner_starts_per_heating_hour"], hub["heating_gas_yesterday"],
                hub["gas_per_degree_day"]]
    assert cards[1] == {"type": YESTERDAY_CARD_TYPE, "grid_options": {"columns": 12},
                        "room": {"entity": rooms["woonkamer"]["warm_on_time"], "name": "Woonkamer"},
                        "starts": hub["burner_starts_per_heating_hour"], "gas": hub["heating_gas_yesterday"],
                        "degree_days": hub["gas_per_degree_day"],
                        "visibility": [{"condition": "or", "conditions": [known(entity)[0] for entity in entities]}]}
    assert sum(json.dumps(v).count(YESTERDAY_CARD_TYPE) for v in config["views"]) == 1
    lines = cards[2]
    for state, entity, attributes in (("-4", rooms["woonkamer"]["warm_on_time"], {}),
                                      ("0.3", rooms["woonkamer"]["overshoot"], {}),
                                      ("12", rooms["badkamer"]["warm_on_time"], {}),
                                      ("0.0", rooms["badkamer"]["overshoot"], {}),
                                      ("1.3", hub["burner_starts_per_heating_hour"], {"heating_hours": 6.2}),
                                      ("0.4", hub["short_cycling_hours"], {}), ("18.2", hub["heating_gas_yesterday"], {}),
                                      ("1.98", hub["gas_per_degree_day"], {"degree_days": 9.2, "heating_kwh": 18.2})):
        hass.states.async_set(entity, state, attributes)
    assert Template(lines["content"], hass).async_render(parse_result=False) == (
        "- **Woonkamer**: 0.3 °C too warm\n"
        "- **Badkamer**: warm 12 min late · 0.0 °C too warm\n"
        "- Heating time: 6.2 h · Short burner runs: 0.4 h\n"
        "- 1.98 kWh per degree-day")
    for text in ("Burner starts per heating hour", "Gas for heating", "Degree-days"):
        assert text not in lines["content"], text
    # Only the four on the card: with them alone known, the lines are empty and hide (no "tomorrow" under figures).
    for entity in (rooms["woonkamer"]["overshoot"], rooms["badkamer"]["warm_on_time"], rooms["badkamer"]["overshoot"],
                   hub["short_cycling_hours"]):
        hass.states.async_set(entity, "unknown")
    hass.states.async_set(hub["burner_starts_per_heating_hour"], "1.3")  # no heating time
    hass.states.async_set(hub["gas_per_degree_day"], "unknown", {"degree_days": 0.6})  # a mild day: degree-days only
    assert Template(lines["content"], hass).async_render(parse_result=False) == ""
    assert lines["show_empty"] is False


@pytest.mark.asyncio
async def test_the_lead_room_is_the_first_room_switched_on_that_has_a_warm_on_time(hass):
    """In the owner's house the living room (the one room switched on, inside the house card); with it off, the next
    room that is on; with every room off, the first that has the figure. In Dutch the same."""
    config, rooms, sensors, hub, fields, flow = live(hass)
    entry = hass.config_entries.async_entries("open_thermostat")[0]
    heating = hass.data["open_thermostat"][entry.entry_id]["heating_hub"]

    def room(heading="Yesterday in figures"):
        config = RoomDashboard(hass, "fixture", entry.entry_id)._dashboard_config()
        return heading_section(view(config, "learned"), heading)[1]["room"]
    assert room() == {"entity": rooms["woonkamer"]["warm_on_time"], "name": "Woonkamer"}
    heating.update(reported({"badkamer": "inactive"}))
    assert room() == {"entity": rooms["woonkamer"]["warm_on_time"], "name": "Woonkamer"}
    heating.update(reported({"woonkamer": "inactive"}))
    assert room() == {"entity": rooms["badkamer"]["warm_on_time"], "name": "Badkamer"}
    heating.update(reported({"woonkamer": "inactive", "badkamer": "inactive"}))
    assert room() == {"entity": rooms["woonkamer"]["warm_on_time"], "name": "Woonkamer"}
    hass.config.language = "nl"
    assert room("Gisteren in cijfers") == {"entity": rooms["woonkamer"]["warm_on_time"], "name": "Woonkamer"}


@pytest.mark.asyncio
async def test_yesterday_in_figures_in_dutch(hass):
    config, hub = with_summary(hass, "nl")
    cards = heading_section(view(config, "learned"), "Gisteren in cijfers")
    # In the language's decimal sign, as the rest of the Dutch dashboard ("7,4 uur", not "7.4 uur"; P16's real render).
    day = {"date": "2026-11-03", "complete": True, "burner_hours": 7.4, "burner_starts": 21, "short_runs": 0,
           "gas": {"heating": 1.25, "hot_water": 0.5}, "outdoor": {"min": 4.5, "max": 10.0},
           "rooms": [{"room": "woonkamer", "name": "Woonkamer", "heat_hours": 7.0, "time_to_target_minutes": 25.0,
                      "missed_minutes": 4}]}
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": day})
    assert Template(cards[1]["content"], hass).async_render(parse_result=False) == (
        "- Brander 7,4 uur, 21 starts (0 korter dan 10 minuten). Gas: verwarmen 1,25 m³, warm water 0,5 m³. "
        "Buiten 4,5 tot 10,0 °C.\n"
        "- Woonkamer: vroeg 7,0 uur warmte; gemiddeld na 25 min op temperatuur; gemiste comfort 4 min.")
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": {**day, "outdoor": {"min": 4.5, "max": 4.5}}})
    assert " Buiten 4,5 °C." in Template(cards[1]["content"], hass).async_render(parse_result=False)
    assert [c["title"] for c in cards if c.get("type") == "statistics-graph"] == ["Gemiste comfort per dag (minuten)"]
    today = heading_section(view(config, "boiler"), "Vandaag en deze week")
    assert "Branderuren per dag" in [c.get("title") for c in today]


@pytest.mark.asyncio
async def test_no_yesterday_in_figures_without_the_summary_and_the_scoreboard(hass):
    e, rooms, sensors, hub, fields = installation(hass, "en")
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert heading_section(view(config, "learned"), "Yesterday in figures") is None
    assert "Yesterday" not in json.dumps(config)
