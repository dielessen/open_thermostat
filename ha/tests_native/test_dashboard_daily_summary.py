"""Yesterday in figures (rc.5): the daily summary in words, once, on the Learning view, with the missed comfort per
day; the burner hours per day are on the Boiler view under "Today and this week"."""
import json

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template

from custom_components.open_thermostat.dashboard import RoomDashboard
from test_dashboard_heating import installation, walk


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
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": {**day, "complete": False, "rooms": []}})
    assert Template(card["content"], hass).async_render(parse_result=False).endswith(
        "\n\n_Partial day: the E32 was not heard all day, so the figures are incomplete._")
    hass.states.async_set(hub["daily_summary"], "unknown", {})
    assert Template(card["content"], hass).async_render(parse_result=False) == (
        "The first full day appears here tomorrow.")


@pytest.mark.asyncio
async def test_one_gas_line_and_tomorrow_only_while_the_scoreboard_has_nothing_either(hass):
    """With the scoreboard (E32 rc.4) next to the summary: its gas line is the one gas line, and "tomorrow" only
    shows while neither has a figure."""
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
    card = section["cards"][1]
    day = {"complete": True, "burner_hours": 6.3, "burner_starts": 14, "short_runs": 2,
           "gas": {"heating": 1.2, "hot_water": 0.8}, "outdoor": None, "rooms": []}
    hass.states.async_set(hub["daily_summary"], "2026-11-03", {"last_day": day})
    hass.states.async_set(hub["heating_gas_yesterday"], "18.2")
    text = Template(card["content"], hass).async_render(parse_result=False)
    assert text == ("- Gas for heating (estimate): 18.2 kWh\n"
                    "- Burner 6.3 h, 14 starts (2 shorter than 10 minutes).")
    hass.states.async_set(hub["heating_gas_yesterday"], "unknown")  # the scoreboard has no gas: the summary says it
    assert "Gas: heating 1.2, hot water 0.8." in Template(card["content"], hass).async_render(parse_result=False)
    hass.states.async_set(hub["daily_summary"], "unknown", {})
    assert Template(card["content"], hass).async_render(parse_result=False) == (
        "The first full day appears here tomorrow.")
    hass.states.async_set(hub["heating_gas_yesterday"], "18.2")
    assert Template(card["content"], hass).async_render(parse_result=False) == (
        "- Gas for heating (estimate): 18.2 kWh")


@pytest.mark.asyncio
async def test_yesterday_in_figures_in_dutch(hass):
    config, hub = with_summary(hass, "nl")
    cards = heading_section(view(config, "learned"), "Gisteren in cijfers")
    assert "Brander {{ d.burner_hours }} uur" in cards[1]["content"]
    assert [c["title"] for c in cards if c.get("type") == "statistics-graph"] == ["Gemiste comfort per dag (minuten)"]
    today = heading_section(view(config, "boiler"), "Vandaag en deze week")
    assert "Branderuren per dag" in [c.get("title") for c in today]


@pytest.mark.asyncio
async def test_no_yesterday_in_figures_without_the_summary_and_the_scoreboard(hass):
    e, rooms, sensors, hub, fields = installation(hass, "en")
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert heading_section(view(config, "learned"), "Yesterday in figures") is None
    assert "Yesterday" not in json.dumps(config)
