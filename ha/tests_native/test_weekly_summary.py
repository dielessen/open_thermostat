"""The weekly summary (advice only) and its opt-in notification blueprint, in English and Dutch."""
import string
from datetime import date
from pathlib import Path

import pytest

from custom_components.open_thermostat import weekly_summary as module
from custom_components.open_thermostat.energy_use import empty_day

TODAY = date(2026, 10, 29)
BLUEPRINT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat/blueprints/weekly_summary.yaml"


def records(days=14, heating=6.0, hot_water=1.0, *, start=0, **extra):
    """Full days of gas (m³) ending ``start`` days before today."""
    result = {}
    for i in range(start, start + days):
        day = empty_day()
        day.update(heating_m3=heating, heating_kwh=heating * 9.77, hot_water_m3=hot_water,
                   hot_water_kwh=hot_water * 9.77, heating_s=3 * 3600, hot_water_s=1800, observed_s=86400)
        day.update({"meter": True, **extra})
        result[date.fromordinal(TODAY.toordinal() - i).isoformat()] = day
    return result


def test_figures_sum_the_last_seven_days_and_compare_with_the_week_before():
    days = records(7, heating=5.0)
    days.update(records(7, heating=6.0, start=7))
    result = module.figures(days, TODAY)
    assert result["period_start"] == "2026-10-23" and result["period_end"] == "2026-10-29"
    assert result["heating_m3"] == 35 and result["hot_water_m3"] == 7 and result["heating_kwh"] == 341.9
    assert result["heating_hours"] == 21 and result["hot_water_hours"] == 3.5 and result["days_observed"] == 7
    assert result["heating_share_pct"] == 83 and result["change_pct"] == -14 and result["method"] == "gas_meter"
    text = module.message(result, ["Water pressure low"], "en")
    assert "Heating: 35 m³ of gas (341.9 kWh), burner 21 h." in text
    assert "That is 14 % less than the week before." in text and "- Water pressure low" in text
    assert "Measured with your gas meter" in text and "Advice only" in text
    nl = module.message(result, ["Waterdruk laag"], "nl")
    assert "Verwarmen: 35 m³ gas (341,9 kWh), brander 21 uur." in nl and "14 % minder" in nl
    assert "Warm water: 7 m³ gas (68,4 kWh)" in nl
    # A week that was not fully observed is not compared and says how long it counted.
    partial = module.figures(records(3), TODAY)
    assert partial["change_pct"] is None and partial["days_observed"] == 3
    assert "Counted over 3 days so far." in module.message(partial, [], "en")


def test_estimate_night_setback_taps_and_no_data():
    days = records(7, meter=False, estimate=True, taps=5,
                   nights={"woonkamer": [0.12, None], "badkamer": [0.0, None]})
    result = module.figures(days, TODAY, rough=True, price=1.5, currency="GBP")
    assert result["method"] == "estimate" and result["rough"] is True and result["hot_water_taps"] == 35
    assert result["night_saving_m3"] == 0.84 and result["night_saving_money"] == 1.26
    text = module.message(result, [], "en")
    assert "35 taps." in text and "about 0.84 m³ of gas this week. That is about 1.26 GBP." in text
    assert "Estimated from the burner modulation" in text and "the estimate is rough" in text
    assert "No advice right now" in text
    # The E32's own money figure wins over the price.
    days = records(7, nights={"woonkamer": [0.1, 0.2]})
    assert module.figures(days, TODAY, price=9.0)["night_saving_money"] == 1.4
    best = module.figures(records(7, nights={"woonkamer": [0.0, None]}), TODAY)
    assert "already the most economical" in module.message(best, [], "en")
    assert "al de zuinigste keuze" in module.message(best, [], "nl")
    none = module.figures({}, TODAY)
    assert none["method"] == "none" and none["night_saving_m3"] is None and none["heating_share_pct"] is None
    assert "No gas use counted yet" in module.message(none, [], "en")
    # A kWh meter: the text says kWh only.
    kwh = module.figures(records(7), TODAY, unit="kWh")
    assert "Heating: 410.3 kWh of gas" in module.message(kwh, [], "en")
    mixed = module.figures({**records(3), **records(3, start=3, meter=False, estimate=True)}, TODAY)
    assert mixed["method"] == "mixed" and "Partly measured" in module.message(mixed, [], "en")


def test_weekly_summary_has_title_message_and_at_most_three_advice_items():
    result = module.weekly_summary(records(7), TODAY, ["a", "b", "c", "d"], "nl")
    assert result["title"] == "OpenThermostat: je week" and result["advice"] == ["a", "b", "c"]
    assert "- c" in result["message"] and "- d" not in result["message"]


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_english_and_dutch_texts_match():
    en, nl = module.TEXT["en"], module.TEXT["nl"]
    assert set(en) == set(nl)
    for key, text in en.items():
        assert placeholders(text) == placeholders(nl[key]), key
        assert text != nl[key], key


@pytest.mark.asyncio
async def test_the_advice_sensor_carries_the_weekly_summary_unrecorded(hass):
    from test_heating_advice import sensor_with
    clock = [1_800_000_000.0]
    sensor, hub, client = sensor_with(hass, clock)
    assert "weekly_summary" in sensor._unrecorded_attributes
    summary = sensor.extra_state_attributes["weekly_summary"]
    assert summary["method"] == "none" and summary["title"] == "OpenThermostat: your week"
    from types import SimpleNamespace
    use = SimpleNamespace(data={"days": records(7)}, unit="m³", power=lambda: (24, True))
    hass.data.setdefault("open_thermostat", {})["e1"] = {"energy_use": use}
    client.boiler_fields.values.update(pressure=0.8)
    for _ in range(7):
        sensor.sample()
        clock[0] += 300
    hass.config.language = "nl"
    summary = sensor.extra_state_attributes["weekly_summary"]
    assert summary["heating_m3"] == 42 and summary["advice"] == ["Waterdruk laag"]
    assert "- Waterdruk laag" in summary["message"] and summary["title"] == "OpenThermostat: je week"
    hass.config.language = "en"
    hass.data["open_thermostat"].pop("e1")


def test_the_weekly_blueprint_is_a_valid_opt_in_automation_blueprint():
    from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
    from homeassistant.components.blueprint.models import Blueprint
    from homeassistant.util import yaml as yaml_util
    raw = yaml_util.load_yaml(BLUEPRINT)
    blueprint = Blueprint(raw, expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)
    assert set(blueprint.inputs) == {"advice", "weekday", "time", "notification"}
    assert raw["blueprint"]["input"]["advice"]["selector"]["entity"]["filter"] == {
        "integration": "open_thermostat", "domain": "sensor"}
    text = BLUEPRINT.read_text(encoding="utf-8")
    assert "weekly_summary" in text and "summary.message" in text and "persistent_notification.create" in text
    # Advice only: the automation sends a message and calls nothing else.
    assert "climate." not in text and "number.set_value" not in text and "select." not in text
