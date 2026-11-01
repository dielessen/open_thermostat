"""Hot water split into tapping and keeping warm (universal), the keep-warm gas sensor and counts across E32 restarts."""
import json
from datetime import date
from pathlib import Path

import pytest

from custom_components.open_thermostat import energy_use as module
from custom_components.open_thermostat.energy_use import valid_data
from custom_components.open_thermostat.heating_link import DhwCarry
from custom_components.open_thermostat.weekly_summary import figures, message
from test_energy_use import DAY0, STATUS, make, run

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "dhw_owner_20261031.json").read_text())


def today(tapping=0, keep_warm=0, charging=0, unknown=0, burner_s=0):
    return {"tapping": {"count": tapping, "s": 60 * tapping}, "keep_warm": {"count": keep_warm, "s": 180 * keep_warm},
            "charging": {"count": charging, "s": 0}, "unknown": {"count": unknown, "s": 0}, "burner_s": burner_s}


def summary(method="dhw_temperature_fall", **counts):
    return {"schema": 1, "dhw": {"method": method, "clock_known": True, "today": today(**counts)}}


# -- counts across E32 restarts ---------------------------------------------------------------------

def test_a_restart_keeps_todays_counts_in_either_order_and_a_new_e32_day_starts_at_zero():
    carry = DhwCarry(today=lambda: DAY0)
    assert carry.apply(today(tapping=3, keep_warm=20), boot=0)["keep_warm"]["count"] == 20
    # Counts first fall, then the heartbeat shows the restart.
    assert carry.apply(today(tapping=0, keep_warm=1), boot=0)["keep_warm"]["count"] == 1
    assert carry.apply(today(tapping=0, keep_warm=1), boot=1)["keep_warm"]["count"] == 21
    assert carry.apply(today(tapping=1, keep_warm=4), boot=1)["tapping"]["count"] == 4
    # The heartbeat first, then the counts.
    assert carry.apply(today(tapping=1, keep_warm=4), boot=2)["keep_warm"]["count"] == 24
    result = carry.apply(today(tapping=0, keep_warm=0), boot=2)
    assert (result["tapping"]["count"], result["keep_warm"]["count"], result["keep_warm"]["s"]) == (4, 24, 24 * 180)
    # The E32's own new day (no restart): the counts start at zero.
    fresh = DhwCarry(today=lambda: DAY0)
    fresh.apply(today(keep_warm=30), boot=5)
    assert fresh.apply(today(keep_warm=0), boot=5)["keep_warm"]["count"] == 0
    # A new day in Home Assistant forgets yesterday.
    day = [DAY0]
    carry = DhwCarry(today=lambda: day[0])
    carry.apply(today(keep_warm=9), boot=0)
    day[0] = date.fromordinal(DAY0.toordinal() + 1)
    assert carry.apply(today(keep_warm=0), boot=1)["keep_warm"]["count"] == 0


# -- gas for keeping warm ------------------------------------------------------------------------------

def setup(hass, method="dhw_temperature_fall", options=None):
    use, values, clock, added = make(hass, options)
    use.hub.update(STATUS)
    use.hub._dhw_carry = DhwCarry(today=lambda: DAY0)
    use.hub.summary = summary(method)
    return use, values, clock, added


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["flow", "dhw_temperature_fall", "storage"])
async def test_an_episode_the_e32_counts_as_keeping_warm_goes_to_keeping_warm_whatever_the_boiler_reports(hass, method):
    use, values, clock, added = setup(hass, method)
    values.update(reported_burner_modulation=40, dhw_active=0)
    use.tick(); run(use, clock, 600)                        # heating
    values.update(reported_burner_modulation=80, dhw_active=1)
    run(use, clock, 180)                                     # a hot-water episode ...
    values.update(reported_burner_modulation=0, dhw_active=0)
    run(use, clock, 20)
    use.hub.summary = summary(method, keep_warm=1)           # ... the E32 counts it as keeping warm
    run(use, clock, 20)
    values.update(reported_burner_modulation=90, dhw_active=1)
    run(use, clock, 120)                                     # a tap
    values.update(reported_burner_modulation=0, dhw_active=0)
    use.hub.summary = summary(method, keep_warm=1, tapping=1)
    run(use, clock, 30)
    day = use.data["days"][DAY0.isoformat()]
    assert day["keep_warm_rounds"] == 1 and day["keep_warm_s"] == 180
    share = day["keep_warm_burner_kwh"] / day["hot_water_burner_kwh"]
    assert share == pytest.approx(80 * 180 / (80 * 180 + 90 * 120), rel=0.08)
    totals = use.data["totals"]
    assert 0 < totals["keep_warm"] < totals["hot_water"]
    assert totals["keep_warm"] == pytest.approx(totals["hot_water"] * share, rel=0.01)
    by_kind = {sensor.kind: sensor for sensor in added}
    assert {k: s.unique_id for k, s in by_kind.items()} == {
        "heating": "fixture_hub_heating_gas", "hot_water": "fixture_hub_hot_water_gas",  # unchanged
        "keep_warm": "fixture_hub_keep_warm_gas"}
    attributes = use.attributes("keep_warm")
    assert attributes["dhw_method"] == method and attributes["rounds_today"] == 1
    assert attributes["burner_minutes_today"] == 3 and DAY0.isoformat() in attributes["days"]
    hot = use.attributes("hot_water")
    assert hot["keep_warm_today"] + hot["tapping_today"] == pytest.approx(hot["today"], abs=0.002)


@pytest.mark.asyncio
async def test_older_firmware_without_sorted_hot_water_gets_no_keep_warm_sensor(hass):
    use, values, clock, added = make(hass)
    values.update(reported_burner_modulation=50, dhw_active=1)
    use.tick(); run(use, clock, 300)
    assert sorted(sensor.kind for sensor in added) == ["heating", "hot_water"]
    assert use.data["totals"]["keep_warm"] == 0


def test_a_store_from_before_keeps_its_totals_and_gains_an_empty_keep_warm():
    old = {"schema": 1, "created": True, "unit": "m³", "totals": {"heating": 12.5, "hot_water": 30.25},
           "days": {"2026-10-30": {"heating_m3": 0.5, "hot_water_m3": 3.5, "taps": 7}}, "meter": None,
           "pending": {"heating": 0.0, "hot_water": 0.0}, "pending_since": None}
    data = valid_data(old)
    assert data["totals"] == {"heating": 12.5, "hot_water": 30.25, "keep_warm": 0.0}
    assert data["days"]["2026-10-30"]["taps"] == 7 and data["days"]["2026-10-30"]["keep_warm_m3"] == 0.0


@pytest.mark.asyncio
async def test_the_owners_day_with_a_gas_meter_splits_hot_water_into_tapping_and_keeping_warm(hass):
    """31 Oct 2026, the owner's comfort mode: about 41 keep-warm rounds, roughly 60 % of the hot-water burner energy."""
    from test_energy_use import gas_meter
    gas_meter(hass, "1000.000")
    use, values, clock, added = setup(hass, options={module.CONF_GAS_METER: "sensor.gas"})
    samples = [tuple(map(int, item.split(","))) for item in FIXTURE["samples"].split(";")]
    episodes = list(FIXTURE["episodes"])
    counts = {"tapping": 0, "keep_warm": 0}
    meter, burner_since_meter, last_keep = 1000.0, 0.0, 0.0
    use.tick()
    for index, (modulation, dhw) in enumerate(samples):
        second = index * 10
        values.update(reported_burner_modulation=modulation, dhw_active=dhw)
        while episodes and episodes[0][0] + 10 <= second:  # the E32's summary a moment after the episode closes
            counts[episodes.pop(0)[1]] += 1
            use.hub.summary = summary(**counts)
        burner_since_meter += modulation / 100 * 22 * 10 / 3600 / 9.769
        if burner_since_meter >= 0.05:                     # a smart meter in 0.05 m³ steps
            meter += 0.05; burner_since_meter -= 0.05
            gas_meter(hass, f"{meter:.3f}")
        clock[0] += 10
        use.tick()
        assert use.data["totals"]["keep_warm"] >= last_keep  # total_increasing: never down
        last_keep = use.data["totals"]["keep_warm"]
    day = use.data["days"][DAY0.isoformat()]
    assert day["keep_warm_rounds"] == 41
    share = day["keep_warm_m3"] / day["hot_water_m3"]
    assert 0.55 <= share <= 0.68, share
    assert day["hot_water_m3"] > day["heating_m3"]          # the day the owner noticed
    assert use.data["totals"]["keep_warm"] <= use.data["totals"]["hot_water"]


def test_the_weekly_summary_names_the_keep_warm_part():
    days = {DAY0.isoformat(): {"heating_m3": 0.5, "heating_kwh": 4.9, "hot_water_m3": 4.0, "hot_water_kwh": 39.1,
                               "keep_warm_m3": 2.4, "keep_warm_rounds": 41, "heating_s": 2000, "hot_water_s": 10000,
                               "observed_s": 86400, "meter": True, "taps": 16}}
    result = figures(days, DAY0)
    assert (result["keep_warm_m3"], result["keep_warm_rounds"]) == (2.4, 41)
    text = message(result, [], "en")
    assert "Of that, keeping the hot water warm: 2.4 m³ (41 rounds)." in text
    assert "Daarvan voor warmhouden van het warme water: 2,4 m³ (41 keer)." in message(result, [], "nl")


def test_the_dashboard_shows_keeping_warm_as_a_third_bar_next_to_hot_water():
    from custom_components.open_thermostat.dashboard import TEXT, _energy_section
    for lang, name in (("en", "Of which keeping warm"), ("nl", "Waarvan warmhouden")):
        section = _energy_section(TEXT[lang], "sensor.heating_gas", "sensor.hot_water_gas", "sensor.keep_warm_gas")
        graph = next(card for card in section["cards"] if card["type"] == "statistics-graph")
        assert [item["entity"] for item in graph["entities"]] == ["sensor.heating_gas", "sensor.hot_water_gas",
                                                                  "sensor.keep_warm_gas"]
        assert graph["entities"][2]["name"] == name
    without = _energy_section(TEXT["en"], "sensor.heating_gas", "sensor.hot_water_gas")
    assert len(next(card for card in without["cards"] if card["type"] == "statistics-graph")["entities"]) == 2
