"""Central-heating tuning advice (advice only), the optional energy inputs and their route to the E32."""
import json
import string
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.open_thermostat import heating_advice as advice
from custom_components.open_thermostat.boiler_fields import BoilerFieldCache, spec
from custom_components.open_thermostat.energy_input import (
    CONF_BOILER_KW, CONF_GAS_KWH_PER_M3, CONF_GAS_METER, CONF_GAS_PRICE, CONF_GAS_PRICE_ENTITY, CONF_OUTDOOR,
    ENERGY_ONLY_UPDATE,
    EnergyError, EnergyForwarder, energy_only_update, energy_payloads, save_energy, validate_energy)

TODAY = date(2026, 10, 29)
CTX = {"today": TODAY, "days": {}, "floor": True, "max_flow": None, "names": {"woonkamer": "Woonkamer"},
       "gas_meter": False, "price": None, "boiler_kw": 22, "learning": False}


def series(count, start=0, **fields):
    """count five-minute samples with the same fields."""
    return [{"t": start + i * advice.SAMPLE_SECONDS, **fields} for i in range(count)]


def ids(result):
    assert not isinstance(result, advice.Missing), result.reason
    return [item["id"] for item in result]


def rendered(items):
    """Every item renders completely in English and Dutch."""
    for item in items:
        for lang in ("en", "nl"):
            text = advice.render(item, lang)
            for field in advice.FIELDS:
                assert text[field].strip() and "{" not in text[field] and "?" not in text[field], (item, field)
    return items


# -- 1. short cycling --------------------------------------------------------------


def test_short_cycling_needs_six_starts_an_hour_for_two_hours():
    two_hours = 2 * 3600 // advice.SAMPLE_SECONDS
    assert ids(advice.rule_short_cycling(series(two_hours, hs=7), CTX)) == ["short_cycling"]
    assert ids(advice.rule_short_cycling(series(two_hours - 1, hs=7), CTX)) == []
    assert ids(advice.rule_short_cycling(series(two_hours, hs=5), CTX)) == []
    # A gap in the observation breaks the stretch.
    broken = series(12, hs=8) + series(12, start=12 * 300 + 1200, hs=8)
    assert ids(advice.rule_short_cycling(broken, CTX)) == []
    # The E32's own flag counts too, without a start count.
    item, = rendered(advice.rule_short_cycling(series(two_hours, sc=True), CTX))
    assert "flagonly" in item["parts"] and item["severity"] == "suggestion" and item["confidence"] == "medium"
    # The reported minimum burner period and hysteresis show up, with a concrete target.
    item, = rendered(advice.rule_short_cycling(series(4 * 12, hs=11, mb=10, hn=6, hf=-6, mx=80), CTX))
    assert item["severity"] == "warning" and item["confidence"] == "high"
    assert item["values"]["mbp_target"] == 15 and {"mbp", "hyst", "maxch"} <= set(item["parts"])
    text = advice.render(item, "en")
    assert "Minimum burner period: 10 min" in text["observed"] and "15 min" in text["action"]
    assert "hysteresis" in text["action"] and "service menu" in text["where"]
    assert isinstance(advice.rule_short_cycling(series(30), CTX), advice.Missing)


# -- 2. maximum CH temperature ---------------------------------------------------


def days(*peaks, n=200, heat=40):
    return {date.fromordinal(TODAY.toordinal() - i).isoformat(): {"n": n, "heat": heat, "max": peak}
            for i, peak in enumerate(peaks)}


def test_max_ch_lowers_to_observed_peak_plus_margin_over_three_days_with_a_floor():
    window = series(3, mx=80)
    item, = rendered(advice.rule_max_ch(window, {**CTX, "days": days(44, 45, 41)}))
    assert item["values"] == {"max_ch": 80, "days": 3, "peak": 45, "suggest": 55}
    assert item["confidence"] == "medium"
    assert advice.rule_max_ch(window, {**CTX, "days": days(48, 40, 40)})[0]["values"]["suggest"] == 60
    assert advice.rule_max_ch(window, {**CTX, "days": days(*[40] * 7)})[0]["confidence"] == "high"
    # Not when a day asked more than 50 °C, without a floor room, or with a moderate setting.
    assert ids(advice.rule_max_ch(window, {**CTX, "days": days(44, 52, 41)})) == []
    assert ids(advice.rule_max_ch(window, {**CTX, "days": days(44, 45, 41), "floor": False})) == []
    assert ids(advice.rule_max_ch(series(3, mx=60), {**CTX, "days": days(44, 45, 41)})) == []
    # Too little evidence: short days, days without heating, or old days do not count.
    few = advice.rule_max_ch(window, {**CTX, "days": days(44, 45)})
    assert few.reason == "few_days" and few.values == {"days": 2, "needed": 3}
    assert advice.rule_max_ch(window, {**CTX, "days": days(44, 45, 41, n=100)}).reason == "few_days"
    assert advice.rule_max_ch(window, {**CTX, "days": days(44, 45, 41, heat=2)}).reason == "few_days"
    old = {date.fromordinal(TODAY.toordinal() - 10 - i).isoformat(): {"n": 200, "heat": 40, "max": 40}
           for i in range(3)}
    assert advice.rule_max_ch(window, {**CTX, "days": old}).reason == "few_days"
    assert advice.rule_max_ch(series(3), CTX).reason == "no_max_ch"


def test_history_keeps_bounded_samples_and_daily_peaks_and_restores_them():
    history = advice.AdviceHistory()
    for i in range(400):
        history.add({"t": i * 300, "re": 38 if i % 2 else 0, "rt": 41 if i == 5 else None}, TODAY)
    assert len(history.samples) <= advice.MAX_SAMPLES
    assert history.samples[0]["t"] > 399 * 300 - advice.HISTORY_SECONDS
    assert history.days[TODAY.isoformat()] == {"n": 400, "heat": 200, "max": 41}
    for i in range(20):
        history.add({"t": 400 * 300 + i}, date.fromordinal(TODAY.toordinal() + i + 1))
    assert len(history.days) == advice.DAYS_KEPT
    restored = advice.AdviceHistory()
    restored.restore(json.loads(json.dumps(history.export())))
    assert restored.days == history.days and restored.samples == []
    restored.restore({"schema": 2, "days": {"x": 1}})
    restored.restore({"schema": 1, "days": {"not a date": {"n": 1, "heat": 0, "max": None},
                                            "2026-01-01": {"n": "1"}}})
    assert restored.days == history.days


# -- 3. return temperature ---------------------------------------------------------


def test_return_too_warm_needs_an_hour_of_heating_without_hot_water():
    item, = rendered(advice.rule_return(series(12, ha=True, rn=58, fl=70), CTX))
    assert item["values"] == {"median": 58, "hours": 1, "flow": 70} and item["confidence"] == "medium"
    assert ids(advice.rule_return(series(12, ha=True, rn=50, fl=60), CTX)) == []
    # Hot water periods do not count; neither does a boiler that is not heating.
    assert advice.rule_return(series(12, ha=True, da=True, rn=70), CTX).reason == "few_heating"
    assert advice.rule_return(series(12, ha=False, rn=70), CTX).reason == "few_heating"
    assert advice.rule_return(series(11, ha=True, rn=70), CTX).reason == "few_heating"
    assert advice.rule_return(series(12, ha=True), CTX).reason == "no_return"


# -- 4. flow against the learned need ------------------------------------------------


def learned(rule, readiness="ready", need=34, rule_flow=40):
    return {"woonkamer": {"r": readiness, "rule": rule, "need": need, "rf": rule_flow}}


def test_learned_flow_advice_only_for_ready_rooms_held_an_hour():
    item, = rendered(advice.rule_learned_flow(series(12, rooms=learned("higher_wasteful")), {**CTX, "max_flow": 50}))
    assert item["id"] == "flow_higher_wasteful:woonkamer" and item["values"]["lower_by"] == 6
    assert "Woonkamer" in advice.render(item, "nl")["title"] and "50 °C" in advice.render(item, "en")["action"]
    assert ids(advice.rule_learned_flow(series(11, rooms=learned("higher_wasteful")), CTX)) == []
    assert ids(advice.rule_learned_flow(series(12, rooms=learned("similar")), CTX)) == []
    # The E32 already applies the learned flow: nothing to lower.
    assert ids(advice.rule_learned_flow(series(12, rooms=learned("higher_wasteful"), ap=True), CTX)) == []
    item, = rendered(advice.rule_learned_flow(series(12, rooms=learned("lower_too_slow", need=45, rule_flow=38)),
                                              {**CTX, "max_flow": 40}))
    assert item["id"] == "flow_lower_too_slow:woonkamer" and "cap" in item["parts"]
    assert advice.rule_learned_flow(series(12, rooms=learned("higher_wasteful", "learning")), CTX).reason == "not_learned"
    assert advice.rule_learned_flow(series(12), CTX).reason == "no_learning"


# -- 5. night setback (and the degraded estimate without a gas meter) ---------------------


def nights(m3=0.12, c=17.5, name="hold_0_5", **extra):
    return {"woonkamer": {"c": c, "m3": m3, "name": name, **extra}}


def test_night_setback_without_gas_meter_is_a_low_confidence_kwh_estimate():
    item, = rendered(advice.rule_night(series(6, nights=nights()), CTX))
    assert item["severity"] == "info" and item["confidence"] == "low"
    assert {"kwh", "no_gas"} <= set(item["parts"]) and item["values"]["saving_kwh"] == 1.2
    en, nl = advice.render(item, "en"), advice.render(item, "nl")
    assert "1.2 kWh" in en["observed"] and "m³" not in en["observed"] and "gas meter" in en["action"]
    assert "1,2 kWh" in nl["observed"] and "17,5 °C" in nl["action"]


def test_night_setback_with_gas_meter_and_price_shows_m3_and_euro():
    ctx = {**CTX, "gas_meter": True, "price": 1.40, "currency": "GBP"}
    item, = rendered(advice.rule_night(series(6, nights=nights()), ctx))
    assert item["severity"] == "suggestion" and item["confidence"] == "medium" and item["parts"] == ("money",)
    assert "0.12 m³" in advice.render(item, "en")["observed"] and "0.17 GBP" in advice.render(item, "en")["observed"]
    assert "€" not in json.dumps(advice.TEXT, ensure_ascii=False)
    calibrated, = advice.rule_night(series(6, nights=nights(m3=0.25, conf="calibrated", eur=0.33)), ctx)
    assert calibrated["confidence"] == "high" and calibrated["values"]["saving_money"] == 0.33
    # Without the boiler's power the E32 assumes a default: only a rough, low-confidence estimate.
    rough, = rendered(advice.rule_night(series(6, nights=nights()), {**ctx, "boiler_kw": None}))
    assert rough["confidence"] == "low" and "rough" in rough["parts"] and rough["severity"] == "info"
    assert "rough estimate" in advice.render(rough, "en")["action"]
    # The calorific value converts the kWh estimate.
    kwh, = advice.rule_night(series(6, nights=nights(m3=0.2)), {**CTX, "kwh_per_m3": 10.5})
    assert kwh["values"]["saving_kwh"] == 2.1
    uncalibrated, = rendered(advice.rule_night(series(6, nights=nights(conf="low")), {**CTX, "gas_meter": True}))
    assert uncalibrated["confidence"] == "low" and "calibrating" in uncalibrated["parts"]
    # Too small, the current program, or not held long enough: no advice.
    assert ids(advice.rule_night(series(6, nights=nights(m3=0.04)), ctx)) == []
    assert ids(advice.rule_night(series(6, nights=nights(name="program")), ctx)) == []
    assert ids(advice.rule_night(series(5, nights=nights()), ctx)) == []
    assert advice.rule_night(series(6), ctx).reason == "no_plans"


# -- 6. hot water, 7. pressure, 8. pump run-on, boiler power -------------------------------


def test_hot_water_temperature_held_six_hours():
    six_hours = 6 * 3600 // advice.SAMPLE_SECONDS
    item, = rendered(advice.rule_dhw(series(six_hours, dw=65, ds=70), CTX))
    assert item["id"] == "dhw_high" and item["parts"] == ("disinfection",)
    assert "55 °C" in advice.render(item, "en")["action"] and "70 °C" in advice.render(item, "en")["observed"]
    item, = rendered(advice.rule_dhw(series(six_hours, dw=45), CTX))
    assert item["id"] == "dhw_low" and item["severity"] == "info" and "legionella" in advice.render(item, "en")["why"].lower()
    assert ids(advice.rule_dhw(series(six_hours, dw=58), CTX)) == []
    # A disinfection run (shorter than 6 h) does not trigger the advice.
    assert ids(advice.rule_dhw(series(six_hours - 1, dw=70), CTX)) == []
    assert advice.rule_dhw(series(3), CTX).reason == "no_dhw"


def test_pressure_low_and_high():
    item, = rendered(advice.rule_pressure(series(6, p=0.8), CTX))
    assert item["id"] == "pressure_low" and item["severity"] == "warning" and item["values"]["minutes"] == 30
    assert "1,5–2,0 bar" in advice.render(item, "nl")["action"]
    assert ids(advice.rule_pressure(series(5, p=0.8), CTX)) == []
    assert ids(advice.rule_pressure(series(6, p=0.1), CTX)) == []  # no sensor rather than an empty system
    assert ids(advice.rule_pressure(series(12, p=2.8), CTX)) == ["pressure_high"]
    assert ids(advice.rule_pressure(series(11, p=2.8), CTX)) == []
    assert ids(advice.rule_pressure(series(12, p=1.6), CTX)) == []
    assert advice.rule_pressure(series(3), CTX).reason == "no_pressure"


def test_pump_run_on_only_when_reported():
    assert ids(rendered(advice.rule_pump_run_on(series(1, pr=15), CTX))) == ["pump_run_on_long"]
    assert ids(advice.rule_pump_run_on(series(1, pr=15), {**CTX, "floor": False})) == []
    assert ids(advice.rule_pump_run_on(series(1, pr=1), CTX)) == []
    assert ids(rendered(advice.rule_pump_run_on(series(1, pr=1), {**CTX, "short_cycling": True}))) == [
        "pump_run_on_short"]
    assert advice.rule_pump_run_on(series(1), CTX).reason == "no_pump_run_on"
    # Through evaluate: the short-cycling result feeds the pump rule.
    items, _ = advice.evaluate(series(24, hs=8, pr=1), {**CTX, "floor": False})
    assert [item["id"] for item in items] == ["short_cycling", "pump_run_on_short"]


def test_boiler_power_advice_only_while_the_e32_estimates_without_it():
    assert ids(rendered(advice.rule_boiler_power([], {**CTX, "boiler_kw": None, "learning": True}))) == [
        "boiler_power_missing"]
    assert ids(advice.rule_boiler_power([], {**CTX, "learning": True})) == []
    assert ids(advice.rule_boiler_power([], {**CTX, "boiler_kw": None})) == []
    # Newer firmware says which power it estimates with: that wins over the energy option.
    learning = {**CTX, "learning": True}
    assert ids(advice.rule_boiler_power([], {**learning, "boiler_kw_source": "default"})) == ["boiler_power_missing"]
    assert ids(advice.rule_boiler_power([], {**learning, "boiler_kw": None, "boiler_kw_source": "ha"})) == []
    assert ids(advice.rule_boiler_power([], {**learning, "boiler_kw_source": None})) == []
    # The night estimate is rough while the E32 uses its default power.
    night = {"c": 17.5, "m3": 0.2, "conf": None}
    assert advice.night_saving(night, {**learning, "gas_meter": True, "boiler_kw_source": "default"})[2] == "low"
    assert advice.night_saving(night, {**learning, "gas_meter": True, "boiler_kw": None,
                                       "boiler_kw_source": "ha"})[2] == "medium"


@pytest.mark.asyncio
async def test_boiler_power_advice_follows_the_heating_summary(hass):
    from custom_components.open_thermostat.heating_link import decode_summary
    clock = [1_800_000_000.0]
    sensor, hub, client = sensor_with(hass, clock)
    sensor.entry.options = {CONF_BOILER_KW: 24}
    hub.update({"schema": 1, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
                "ha_entities": [], "rooms": []})
    context = sensor.context(clock[0])
    assert context["boiler_kw_source"] is None and context["learning"] is False  # older firmware: the option
    header = {"schema": 1, "applied": True, "status": "learning", "heating_periods": 37,
              "inputs": {"gas_meter": False, "gas_price": False, "outdoor": "boiler", "boiler_kw": 22,
                         "boiler_kw_source": "default", "gas_kwh_per_m3": 9.77, "gas_kwh_per_m3_source": "default"}}
    hub.update_summary(decode_summary(json.dumps({"schema": 1, "learned": header})))
    context = sensor.context(clock[0])
    assert context["boiler_kw_source"] == "default" and context["learning"] is True
    assert advice.rule_boiler_power([], context)[0]["id"] == "boiler_power_missing"  # set, not yet on the E32
    assert advice.take_sample(hub, client, clock[0])["ap"] is True
    hub.update_summary(decode_summary(json.dumps(
        {"schema": 1, "learned": {**header, "inputs": {**header["inputs"], "boiler_kw_source": "ha"}}})))
    assert advice.rule_boiler_power([], sensor.context(clock[0])) == []
    hub.update_summary(decode_summary(json.dumps(
        {"schema": 1, "learned": {**header, "inputs": {**header["inputs"], "boiler_kw_source": "bogus"}}})))
    assert sensor.context(clock[0])["boiler_kw_source"] is None


def test_no_data_means_no_advice_and_says_what_is_missing():
    items, missing = advice.evaluate([], {"today": TODAY})
    assert items == []
    assert [name for name, _ in missing] == ["short_cycling", "max_ch_high", "return_too_warm", "learned_flow",
                                             "night_setback", "dhw", "pressure", "pump_run_on"]
    for lang in ("en", "nl"):
        reasons = [advice.render_missing(name, reason, lang)["reason"] for name, reason in missing]
        assert all(reason.strip() and "{" not in reason for reason in reasons)


def test_items_are_ordered_warning_first():
    items, _ = advice.evaluate(series(72, p=0.8, dw=65), CTX)
    assert [item["id"] for item in items] == ["pressure_low", "dhw_high"]


# -- texts ---------------------------------------------------------------------------------


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_english_and_dutch_texts_are_complete_and_use_the_same_placeholders():
    en, nl = advice.TEXT["en"], advice.TEXT["nl"]
    assert set(en) == set(nl) == {"rules", "missing"}
    assert set(en["rules"]) == set(nl["rules"])
    for rule, template in en["rules"].items():
        assert set(template) == set(nl["rules"][rule]), rule
        assert all(field in template for field in advice.FIELDS), rule
        for key, text in template.items():
            assert placeholders(text) == placeholders(nl["rules"][rule][key]), (rule, key)
            assert text != nl["rules"][rule][key] or "{" in text, (rule, key)
    assert set(en["missing"]) == set(nl["missing"])
    for key, text in en["missing"].items():
        assert placeholders(text) == placeholders(nl["missing"][key])
    assert advice.fmt(0.12, "nl") == "0,12" and advice.fmt(0.12, "en") == "0.12" and advice.fmt(55, "nl") == "55"


def test_advice_never_writes_a_setting():
    source = (advice.__file__)
    text = open(source, encoding="utf-8").read()
    for forbidden in ("async_publish", "async_write_heating_plan", "async_change", "async_call(", "boiler_write"):
        assert forbidden not in text


# -- the sensor ------------------------------------------------------------------------------


class FakeCache(BoilerFieldCache):
    """Boiler-field readings by name (in engineering units)."""

    def __init__(self):
        super().__init__()
        self.values = {}

    def reading(self, index, now):
        name, _, divisor, _ = spec(index)
        if name not in self.values:
            return None
        return {"raw": int(round(self.values[name] * divisor)), "usable": True}


def sensor_with(hass, clock):
    from custom_components.open_thermostat.heating_link import HeatingHub
    hub = HeatingHub("fixture", clock=lambda: clock[0])
    client = SimpleNamespace(boiler_fields=FakeCache(), ready=True, boiler_fields_supported=True, clock=lambda: clock[0])
    entry = SimpleNamespace(entry_id="e1", options={})
    sensor = advice.HeatingAdviceSensor(entry, hub, SimpleNamespace(client=client), clock=lambda: clock[0],
                                        local_date=lambda now: TODAY)
    sensor.hass = hass
    return sensor, hub, client


@pytest.mark.asyncio
async def test_sensor_samples_the_boiler_fields_and_raises_one_repairs_issue_for_low_pressure(hass):
    from homeassistant.helpers import issue_registry as ir
    clock = [1_800_000_000.0]
    sensor, hub, client = sensor_with(hass, clock)
    assert sensor.unique_id == "fixture_hub_heating_advice" and sensor.native_value == 0
    client.boiler_fields.values.update(pressure=0.8, selected_dhw_temperature=55)
    for _ in range(6):
        sensor.sample()
        clock[0] += advice.SAMPLE_SECONDS
    assert sensor.native_value == 1
    attributes = sensor.extra_state_attributes
    item, = attributes["items"]
    assert item["id"] == "pressure_low" and item["title"] == "Water pressure low" and item["since"].endswith("+00:00")
    assert set(item) == {"id", "severity", "title", "observed", "why", "action", "where", "confidence", "since"}
    assert attributes["advice_only"] is True and {m["id"] for m in attributes["not_evaluated"]} >= {"short_cycling"}
    issue = ir.async_get(hass).async_get_issue("open_thermostat", "low_boiler_pressure_e1")
    assert issue is not None and issue.translation_placeholders == {"pressure": "0.8"}
    hass.config.language = "nl"
    assert sensor.extra_state_attributes["items"][0]["title"] == "Waterdruk laag"
    client.boiler_fields.values["pressure"] = 1.6
    sensor.sample()
    assert sensor.native_value == 0
    assert ir.async_get(hass).async_get_issue("open_thermostat", "low_boiler_pressure_e1") is None
    # The daily aggregates survive a restart through the restore data.
    assert sensor.extra_restore_state_data.as_dict()["days"][TODAY.isoformat()]["n"] == 7
    hass.config.language = "en"


@pytest.mark.asyncio
async def test_sensor_reads_the_e32_telemetry(hass):
    clock = [1_800_000_000.0]
    sensor, hub, client = sensor_with(hass, clock)
    status = {"schema": 1, "mode": "shadow", "request": {"heat": True, "flow_c": 38, "reason": "heating"},
              "ha_entities": [], "rooms": [{"id": "woonkamer", "name": "Woonkamer", "emitter": "floor"}],
              "burner": {"starts_last_hour": 9, "heating_starts_last_hour": 8, "short_cycling": True},
              "learned": {"schema": 1, "applied": False, "rooms": [
                  {"id": "woonkamer", "emitter": "floor", "readiness": "ready",
                   "advice": [{"shortfall_c": 1, "flow_c": 34, "rule_flow_c": 40, "rule": "higher_wasteful"}]}]}}
    hub.update(status)
    sample = advice.take_sample(hub, client, clock[0])
    assert sample["re"] == 38 and sample["sc"] is True and sample["hs"] == 8 and sample["ap"] is False
    assert sample["rooms"] == {"woonkamer": {"r": "ready", "rule": "higher_wasteful", "need": 34, "rf": 40}}
    assert advice.floor_present(hub)
    for _ in range(24):
        sensor.sample()
        clock[0] += advice.SAMPLE_SECONDS
    assert [item["id"] for item in sensor.items] == ["short_cycling", "flow_higher_wasteful:woonkamer",
                                                     "boiler_power_missing"]
    # Without telemetry or boiler fields every value is simply absent.
    assert advice.take_sample(None, object(), 5) == {"t": 5}


# -- the dashboard ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_advice_section_lists_title_action_and_where_and_hides_when_empty(hass):
    from homeassistant.helpers.template import Template
    from custom_components.open_thermostat.dashboard import TEXT, _advice_section
    assert _advice_section(TEXT["en"], None) is None
    section = _advice_section(TEXT["nl"], "sensor.cv_advies")
    hidden = [{"condition": "numeric_state", "entity": "sensor.cv_advies", "above": 0}]
    assert section["visibility"] == hidden and all(card["visibility"] == hidden for card in section["cards"])
    heading, markdown = section["cards"]
    assert heading["heading"] == "Advies"
    hass.states.async_set("sensor.cv_advies", "1", {"items": [
        {"id": "pressure_low", "severity": "warning", "title": "Waterdruk laag", "action": "Vul bij.",
         "where": "Vulkraan", "confidence": "high"}]})
    text = Template(markdown["content"], hass).async_render()
    assert "**Waterdruk laag**" in text and "Vul bij." in text and "*Waar: Vulkraan · Zekerheid: hoog*" in text
    assert 'icon="mdi:alert-outline"' in text and "Alleen advies" in text


# -- energy inputs: validation, the options step, forwarding --------------------------------------


def set_inputs(hass):
    hass.states.async_set("sensor.gas", "1234.5678", {"unit_of_measurement": "m³", "state_class": "total_increasing",
                                                     "device_class": "gas"})
    hass.states.async_set("sensor.gas_rate", "0.4", {"unit_of_measurement": "m³/h", "state_class": "measurement"})
    hass.states.async_set("sensor.gas_now", "3", {"unit_of_measurement": "m³", "state_class": "measurement"})
    hass.states.async_set("sensor.price", "1.3214", {"unit_of_measurement": "EUR/m³"})
    hass.states.async_set("sensor.price_kwh", "0.12", {"unit_of_measurement": "GBP/kWh"})
    hass.states.async_set("sensor.price_flat", "1.3", {"unit_of_measurement": "EUR"})
    hass.states.async_set("sensor.gas_kwh", "21100", {"unit_of_measurement": "kWh", "device_class": "gas",
                                                     "state_class": "total_increasing"})
    hass.states.async_set("sensor.power_kwh", "500", {"unit_of_measurement": "kWh", "device_class": "power",
                                                      "state_class": "total_increasing"})
    hass.states.async_set("sensor.outside", "7.42", {"unit_of_measurement": "°C", "device_class": "temperature"})
    hass.states.async_set("sensor.outside_f", "50", {"unit_of_measurement": "°F", "device_class": "temperature"})
    hass.states.async_set("sensor.humidity", "50", {"unit_of_measurement": "%"})
    hass.states.async_set("weather.home", "cloudy", {"temperature": 6.5, "temperature_unit": "°C"})


@pytest.mark.asyncio
async def test_energy_validation(hass):
    set_inputs(hass)
    assert validate_energy(hass, {}) == {}
    assert validate_energy(hass, {"gas_meter": "sensor.gas", "gas_price": 1.35, "outdoor_entity": "weather.home",
                                  "boiler_kw": 22.0}) == {
        CONF_GAS_METER: "sensor.gas", CONF_GAS_PRICE: 1.35, CONF_OUTDOOR: "weather.home", CONF_BOILER_KW: 22}
    assert validate_energy(hass, {"gas_price_entity": "sensor.price", "outdoor_entity": "sensor.outside_f"}) == {
        CONF_GAS_PRICE_ENTITY: "sensor.price", CONF_OUTDOOR: "sensor.outside_f"}
    # Energy meters in kWh, prices per kWh and in any currency, a high price: all fine.
    assert validate_energy(hass, {"gas_meter": "sensor.gas_kwh", "gas_price_entity": "sensor.price_kwh",
                                  "gas_kwh_per_m3": 10.55}) == {
        CONF_GAS_METER: "sensor.gas_kwh", CONF_GAS_PRICE_ENTITY: "sensor.price_kwh", CONF_GAS_KWH_PER_M3: 10.55}
    assert validate_energy(hass, {"gas_price": 250})[CONF_GAS_PRICE] == 250
    for user_input, field, code in (
            ({"gas_meter": "sensor.missing"}, "gas_meter", "entity_not_found"),
            ({"gas_meter": "sensor.gas_rate"}, "gas_meter", "gas_meter_unit"),
            ({"gas_meter": "sensor.gas_now"}, "gas_meter", "gas_meter_not_total"),
            ({"gas_price_entity": "sensor.price_flat"}, "gas_price_entity", "gas_price_unit"),
            ({"gas_meter": "sensor.power_kwh"}, "gas_meter", "gas_meter_unit"),
            ({"gas_price_entity": "sensor.price", "gas_price": 1.2}, "gas_price", "gas_price_twice"),
            ({"gas_price": 0}, "gas_price", "gas_price_invalid"),
            ({"gas_price": 1001}, "gas_price", "gas_price_invalid"),
            ({"gas_kwh_per_m3": 4}, "gas_kwh_per_m3", "gas_kwh_per_m3_invalid"),
            ({"outdoor_entity": "sensor.humidity"}, "outdoor_entity", "outdoor_unit"),
            ({"boiler_kw": 2}, "boiler_kw", "boiler_kw_invalid"),
            ({"boiler_kw": 61}, "boiler_kw", "boiler_kw_invalid")):
        with pytest.raises(EnergyError) as err:
            validate_energy(hass, user_input)
        assert (err.value.field, err.value.code) == (field, code)


@pytest.mark.asyncio
async def test_energy_payloads_and_forwarder(hass):
    set_inputs(hass)
    assert energy_payloads(hass, {}) == []
    options = {CONF_GAS_METER: "sensor.gas", CONF_GAS_PRICE_ENTITY: "sensor.price", CONF_OUTDOOR: "sensor.outside_f",
               CONF_BOILER_KW: 22}
    assert energy_payloads(hass, options) == [
        {"kind": "gas_m3", "entity": "sensor.gas", "value": 1234.568},
        {"kind": "gas_price", "entity": "sensor.price", "value": 1.3214},
        {"kind": "outdoor_c", "entity": "sensor.outside_f", "value": 10},
        {"kind": "boiler_kw", "value": 22}]
    assert energy_payloads(hass, {CONF_GAS_PRICE: 1.32}) == [{"kind": "gas_price", "value": 1.32}]
    # A kWh meter and a price per kWh become m³ with the calorific value (sent too, once configured).
    assert energy_payloads(hass, {CONF_GAS_METER: "sensor.gas_kwh", CONF_GAS_PRICE_ENTITY: "sensor.price_kwh",
                                  CONF_GAS_KWH_PER_M3: 10.55}) == [
        {"kind": "gas_m3", "entity": "sensor.gas_kwh", "value": 2000},
        {"kind": "gas_price", "entity": "sensor.price_kwh", "value": 1.266},
        {"kind": "gas_kwh_per_m3", "value": 10.55}]
    assert energy_payloads(hass, {CONF_GAS_METER: "sensor.gas_kwh"})[0]["value"] == round(21100 / 9.77, 3)
    assert energy_payloads(hass, options, only="sensor.outside_f") == [
        {"kind": "outdoor_c", "entity": "sensor.outside_f", "value": 10}]
    hass.states.async_set("sensor.gas", "unavailable", {"unit_of_measurement": "m³"})
    assert [p["kind"] for p in energy_payloads(hass, options)] == ["gas_price", "outdoor_c", "boiler_kw"]

    # Nothing configured: nothing tracked, nothing sent.
    sent, tracked = [], []
    track = lambda hass, ids, action: tracked.append((list(ids), action)) or (lambda: tracked.append("stop"))
    entry = SimpleNamespace(options={"create_dashboard": True})
    forwarder = EnergyForwarder(hass, entry, sent.append, track)
    forwarder.reconfigure()
    forwarder.publish()
    assert sent == [] and tracked == []
    # Configured: sent at once, then only the changed entity.
    entry.options = {CONF_OUTDOOR: "sensor.outside", CONF_BOILER_KW: 24.5}
    forwarder.reconfigure()
    assert [json.loads(p) for p in sent] == [{"kind": "outdoor_c", "entity": "sensor.outside", "value": 7.4},
                                             {"kind": "boiler_kw", "value": 24.5}]
    (entities, action), = tracked
    assert entities == ["sensor.outside"]
    sent.clear()
    action(SimpleNamespace(data={"entity_id": "sensor.outside"}))
    assert [json.loads(p) for p in sent] == [{"kind": "outdoor_c", "entity": "sensor.outside", "value": 7.4}]
    forwarder.stop()
    assert tracked[-1] == "stop"


@pytest.mark.asyncio
async def test_heating_route_forwards_energy_values_next_to_the_room_inputs(hass, monkeypatch):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat import heating_link as module
    from custom_components.open_thermostat.const import DOMAIN
    set_inputs(hass)
    callbacks, published = {}, []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

    async def subscribe(hass, topic, callback):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)

    async def publish(hass, topic, payload, qos, retain):
        published.append((topic, json.loads(payload)))
    monkeypatch.setattr(mqtt, "async_publish", publish)
    monkeypatch.setattr(module, "async_track_state_change_event", lambda hass, ids, cb: lambda: None)
    monkeypatch.setattr(module, "async_track_time_interval", lambda hass, cb, interval: lambda: None)
    hass.data[DOMAIN] = {"e": {"v1_connection": SimpleNamespace(client=object(), prefix="fixture/v1/")}}
    entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture"}, options={CONF_GAS_PRICE: 1.32},
                            async_on_unload=lambda f: None)
    await module.async_setup_heating_link(hass, entry, lambda entities, **kw: None)
    await hass.async_block_till_done()
    assert published == [("fixture/v1/ha/heating_input", {"kind": "gas_price", "value": 1.32})]
    assert "fixture/v1/fw/telemetry/learned/+" in callbacks
    # The E32 comes online: the values go at once (also without room inputs).
    status = {"schema": 1, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
              "ha_entities": [], "rooms": []}
    from e32_telemetry import FakeE32  # the beta.19 topics (fw/state/*, fw/config/*)
    FakeE32(callbacks).status(status)
    await hass.async_block_till_done()
    assert len(published) == 2
    assert hass.data[DOMAIN]["e"]["energy_forwarder"] is not None


from test_product_flow import managers, option, product  # noqa: E402,F401


@pytest.mark.asyncio
async def test_energy_options_step_validates_saves_without_reload(hass, managers, monkeypatch):
    import custom_components.open_thermostat as integration
    set_inputs(hass)
    _, m = managers
    p = product(hass)
    before = {key: value for key, value in p.options.items()}
    f = await option(m, p, "energy")
    assert f["step_id"] == "energy"
    assert {str(key) for key in f["data_schema"].schema} == {"gas_meter", "gas_price_entity", "gas_price",
                                                             "gas_kwh_per_m3", "outdoor_entity", "boiler_kw"}
    f = await m.async_configure(f["flow_id"], {"gas_meter": "sensor.gas_rate"})
    assert f["errors"] == {"gas_meter": "gas_meter_unit"}
    f = await m.async_configure(f["flow_id"], {"gas_meter": "sensor.gas", "gas_price": 1.35, "boiler_kw": 22})
    assert f["type"] == "abort" and f["reason"] == "energy_saved"
    assert dict(p.options) == {**before, CONF_GAS_METER: "sensor.gas", CONF_GAS_PRICE: 1.35, CONF_BOILER_KW: 22}
    state = hass.data["open_thermostat"][p.entry_id]
    assert state[ENERGY_ONLY_UPDATE] == dict(p.options)
    # The update listener follows the energy inputs without a reload (no plan review).
    reloaded, followed = [], []
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(side_effect=lambda *a: reloaded.append(a)))
    state["energy_forwarder"] = SimpleNamespace(reconfigure=lambda: followed.append("energy"))
    state["heating_advice"] = SimpleNamespace(reevaluate=lambda: followed.append("advice"))
    await integration._async_options_updated(hass, p)
    assert followed == ["energy", "advice"] and reloaded == [] and ENERGY_ONLY_UPDATE not in state
    # Clearing a field removes it; an unchanged save changes nothing.
    f = await option(m, p, "energy")
    await m.async_configure(f["flow_id"], {"gas_meter": "sensor.gas"})
    assert dict(p.options) == {**before, CONF_GAS_METER: "sensor.gas"}
    state.pop(ENERGY_ONLY_UPDATE, None)
    assert save_energy(hass, p, {CONF_GAS_METER: "sensor.gas"}) is False and ENERGY_ONLY_UPDATE not in state
    # Any other change still reloads as before.
    assert not energy_only_update(state, p)
