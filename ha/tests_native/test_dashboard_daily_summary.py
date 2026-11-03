"""The Heating view's "Yesterday" section (1.0): the daily summary in words, burner hours and missed comfort per day."""
import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.dashboard import RoomDashboard
from test_dashboard_heating import installation, walk


def boiler(config):
    return next(v for v in config["views"] if v["path"] == "boiler")


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


@pytest.mark.asyncio
async def test_yesterday_section_with_the_summary_and_two_daily_bar_charts(hass):
    config, hub = with_summary(hass, "en")
    cards = heading_section(boiler(config), "Yesterday")
    assert cards is not None
    text = cards[1]["content"]
    assert f"state_attr(\"{hub['daily_summary']}\", 'last_day')" in text
    assert "{{ d.burner_hours }}" in text and "{{ d.burner_starts }}" in text and "{{ d.short_runs }}" in text
    assert "~ ' m³'" in text  # the gas in the gas sensor's unit
    assert "The first full day appears here tomorrow." in text
    charts = [card for card in cards if card.get("type") == "statistics-graph"]
    assert [c["entities"][0]["entity"] for c in charts] == [hub["daily_burner_time"], hub["daily_missed_comfort"]]
    assert all(c["stat_types"] == ["change"] and c["period"] == "day" and c["days_to_show"] == 7
               and c["chart_type"] == "bar" for c in charts)


@pytest.mark.asyncio
async def test_yesterday_section_in_dutch(hass):
    config, hub = with_summary(hass, "nl")
    cards = heading_section(boiler(config), "Gisteren")
    assert "Brander {{ d.burner_hours }} uur" in cards[1]["content"]
    assert [c["title"] for c in cards if c.get("type") == "statistics-graph"] == [
        "Branderuren per dag", "Gemiste comfort per dag (minuten)"]


@pytest.mark.asyncio
async def test_no_yesterday_section_without_the_summary(hass):
    e, rooms, sensors, hub, fields = installation(hass, "en")
    config = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()
    assert heading_section(boiler(config), "Yesterday") is None
