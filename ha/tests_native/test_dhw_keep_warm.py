"""Hot water split into tapping and keeping warm (universal): the tapping and keep-warm gas sensors, the boiler
activity timeline, the Boiler view's hot-water cards and counts across E32 restarts."""
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
    baseline = "default" if method == "dhw_temperature_fall" else None
    return {"schema": 1, "dhw": {"method": method, "baseline": baseline, "clock_known": True, "today": today(**counts)}}


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


def test_the_e32s_own_midnight_drop_is_never_carried_into_a_later_restart():
    day, clock = [DAY0], [0.0]
    carry = DhwCarry(today=lambda: day[0], clock=lambda: clock[0])
    carry.apply(today(keep_warm=40), boot=0)                     # yesterday evening
    day[0] = date.fromordinal(DAY0.toordinal() + 1)              # Home Assistant's date rolls over first ...
    carry.apply(today(keep_warm=40), boot=0)                     # ... a heartbeat redraws the old counts
    clock[0] += 30
    assert carry.apply(today(keep_warm=0), boot=0)["keep_warm"]["count"] == 0   # the E32's new day
    clock[0] += 4 * 3600
    carry.apply(today(keep_warm=10), boot=0)                     # the morning: 10 rounds
    clock[0] += 4 * 3600
    after = carry.apply(today(keep_warm=10), boot=1)["keep_warm"]["count"]      # a firmware update: heartbeat first
    clock[0] += 20
    later = carry.apply(today(keep_warm=2), boot=1)["keep_warm"]["count"]       # then its counts start again
    assert (after, later) == (10, 12)


def test_a_drop_and_a_restart_far_apart_are_not_one_restart():
    clock = [0.0]
    carry = DhwCarry(today=lambda: DAY0, clock=lambda: clock[0])
    carry.apply(today(keep_warm=30), boot=0)
    carry.apply(today(keep_warm=0), boot=0)                      # the E32's new day, nothing counted since
    clock[0] += DhwCarry.RESTART_WINDOW_S + 1
    assert carry.apply(today(keep_warm=0), boot=1)["keep_warm"]["count"] == 0   # a restart much later
    carry.apply(today(keep_warm=5), boot=1)
    clock[0] += 3600
    carry.apply(today(keep_warm=5), boot=2)                      # a restart with nothing dropped yet ...
    clock[0] += DhwCarry.RESTART_WINDOW_S + 1
    assert carry.apply(today(keep_warm=0), boot=2)["keep_warm"]["count"] == 0   # ... and a drop long after it


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
        "tapping": "fixture_hub_tapping_gas", "keep_warm": "fixture_hub_keep_warm_gas"}
    attributes = use.attributes("keep_warm")
    assert attributes["dhw_method"] == method and attributes["rounds_today"] == 1
    assert attributes["dhw_baseline"] == ("default" if method == "dhw_temperature_fall" else None)
    assert attributes["burner_minutes_today"] == 3 and DAY0.isoformat() in attributes["days"]
    tapping = use.attributes("tapping")
    assert tapping["rounds_today"] == 1 and tapping["burner_minutes_today"] == 2
    assert totals["tapping"] + totals["keep_warm"] == pytest.approx(totals["hot_water"], rel=0.01)
    hot = use.attributes("hot_water")
    assert hot["keep_warm_today"] + hot["tapping_today"] == pytest.approx(hot["today"], abs=0.002)


@pytest.mark.asyncio
async def test_older_firmware_without_sorted_hot_water_gets_no_keep_warm_sensor(hass):
    use, values, clock, added = make(hass)
    values.update(reported_burner_modulation=50, dhw_active=1)
    use.tick(); run(use, clock, 300)
    assert sorted(sensor.kind for sensor in added) == ["heating", "hot_water"]
    assert use.data["totals"]["keep_warm"] == use.data["totals"]["tapping"] == 0


def test_a_store_from_before_keeps_its_totals_and_gains_an_empty_keep_warm():
    old = {"schema": 1, "created": True, "unit": "m³", "totals": {"heating": 12.5, "hot_water": 30.25},
           "days": {"2026-10-30": {"heating_m3": 0.5, "hot_water_m3": 3.5, "taps": 7}}, "meter": None,
           "pending": {"heating": 0.0, "hot_water": 0.0}, "pending_since": None}
    data = valid_data(old)
    assert data["totals"] == {"heating": 12.5, "hot_water": 30.25, "tapping": 0.0, "keep_warm": 0.0}
    assert data["days"]["2026-10-30"]["taps"] == 7 and data["days"]["2026-10-30"]["keep_warm_m3"] == 0.0


@pytest.mark.asyncio
async def test_the_owners_day_with_a_gas_meter_splits_hot_water_into_tapping_and_keeping_warm(hass):
    """31 Oct 2026, the owner's comfort mode: 40 keep-warm rounds and 17 taps, roughly 60 % of the hot-water burner energy."""
    from test_energy_use import gas_meter
    gas_meter(hass, "1000.000")
    use, values, clock, added = setup(hass, options={module.CONF_GAS_METER: "sensor.gas"})
    samples = [tuple(map(int, item.split(","))) for item in FIXTURE["samples"].split(";")]
    episodes = list(FIXTURE["episodes"])
    counts = {"tapping": 0, "keep_warm": 0}
    meter, burner_since_meter, last = 1000.0, 0.0, {"tapping": 0.0, "keep_warm": 0.0}
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
        for kind in last:  # total_increasing: never down
            assert use.data["totals"][kind] >= last[kind]
            last[kind] = use.data["totals"][kind]
    day = use.data["days"][DAY0.isoformat()]
    assert (day["keep_warm_rounds"], day["taps"]) == (40, 17)
    share = day["keep_warm_m3"] / day["hot_water_m3"]
    assert 0.55 <= share <= 0.68, share
    # Every episode of that day is a tap or keeping warm: together they are the hot water (the meter's last step aside).
    assert day["tapping_m3"] + day["keep_warm_m3"] == pytest.approx(day["hot_water_m3"], rel=0.03)
    assert day["hot_water_m3"] > day["heating_m3"]          # the day the owner noticed
    totals = use.data["totals"]
    assert totals["tapping"] + totals["keep_warm"] <= totals["hot_water"] + 1e-9


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


@pytest.mark.asyncio
async def test_a_cylinder_charging_counts_to_hot_water_only(hass):
    use, values, clock, added = setup(hass, "storage")
    values.update(reported_burner_modulation=70, dhw_active=1)
    use.tick(); run(use, clock, 600)
    values.update(reported_burner_modulation=0, dhw_active=0)
    use.hub.summary = summary("storage", charging=1)
    run(use, clock, 60)
    totals = use.data["totals"]
    assert totals["hot_water"] > 0 and totals["tapping"] == totals["keep_warm"] == 0


# -- what the boiler does now ------------------------------------------------------------------------------

def owner_activity():
    """The owner's 31 Oct as the E32 reports it at the end of each episode: (second, activity) every 10 s."""
    samples = [tuple(map(int, item.split(","))) for item in FIXTURE["samples"].split(";")]
    episodes, states = list(FIXTURE["episodes"]), []
    for index, (modulation, dhw) in enumerate(samples):
        second = index * 10
        while episodes and episodes[0][0] < second and not dhw:
            episodes.pop(0)
        states.append((second, episodes[0][1] if dhw and episodes else "heating" if modulation else "idle"))
    return states


@pytest.mark.asyncio
async def test_the_boiler_activity_follows_the_e32_and_draws_the_owners_day(hass, monkeypatch):
    from homeassistant.components.sensor import SensorDeviceClass
    from custom_components.open_thermostat import heating_link as module
    from test_heating_link import FULL, _setup
    entry, hub, added, send = await _setup(hass, monkeypatch)
    send({**FULL, "burner": {"starts_last_hour": 2, "short_cycling": False}})
    assert not any(e.unique_id == "fixture_hub_boiler_activity" for e in added)  # older firmware: none
    send({**FULL, "burner": {"starts_last_hour": 2, "short_cycling": False, "activity": None}})
    activity = next(e for e in added if e.unique_id == "fixture_hub_boiler_activity")
    assert activity.device_class == SensorDeviceClass.ENUM and activity.translation_key == "boiler_activity"
    assert activity.options == ["idle", "heating", "tapping", "keep_warm", "charging", "hot_water"]
    assert activity.native_value is None
    runs, last = {}, None
    for _, state in owner_activity():
        send({**FULL, "burner": {"starts_last_hour": 2, "short_cycling": False, "activity": state}})
        assert activity.available and activity.native_value == state
        if state != last:
            runs[state] = runs.get(state, 0) + 1
        last = state
    assert (runs["tapping"], runs["keep_warm"]) == (17, 40) and runs["heating"] > 0 and runs["idle"] > 0
    send({**FULL, "burner": {"activity": "boiling"}})  # unknown values are unknown, never a new state
    assert activity.native_value is None
    now = [hub.received + module.STALE_SECONDS + 1]
    hub.clock = lambda: now[0]
    hub.check_stale()
    assert not activity.available


def test_every_boiler_activity_has_a_name_in_english_dutch_and_polish():
    from custom_components.open_thermostat.heating_link import BOILER_ACTIVITIES
    component = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    names = {}
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        sensor = json.loads((component / name).read_text(encoding="utf-8"))["entity"]["sensor"]
        assert set(sensor["boiler_activity"]["state"]) == set(BOILER_ACTIVITIES), name
        assert sensor["tapping_gas"]["name"] and sensor["keep_warm_gas"]["name"]
        names[name] = sensor["boiler_activity"]["state"]
    assert names["strings.json"] == names["translations/en.json"]
    assert (names["translations/nl.json"]["tapping"], names["translations/nl.json"]["keep_warm"]) == ("Tappen", "Warmhouden")
    assert (names["translations/pl.json"]["tapping"], names["translations/pl.json"]["keep_warm"]) == (
        "Pobór wody", "Podtrzymanie ciepła")


# -- the Boiler view's hot-water section ------------------------------------------------------------------

HUB = {"boiler_activity": "sensor.boiler_activity", "heating_gas": "sensor.heating_gas",
       "tapping_gas": "sensor.tapping_gas", "keep_warm_gas": "sensor.keep_warm_gas"}


@pytest.mark.parametrize("lang", ["en", "nl"])
def test_the_hot_water_cards_are_a_timeline_and_the_gas_per_post_once_there_are_statistics(lang):
    from custom_components.open_thermostat.dashboard import TEXT, _hot_water_use_cards
    t = TEXT[lang]
    timeline, gas, note = _hot_water_use_cards(t, HUB, "sensor.heating_active")
    assert (timeline["type"], timeline["hours_to_show"]) == ("history-graph", 24)
    assert [item["entity"] for item in timeline["entities"]] == ["sensor.boiler_activity", "sensor.heating_active"]
    assert (gas["type"], gas["chart_type"], gas["period"], gas["days_to_show"], gas["stat_types"]) == (
        "statistics-graph", "bar", "day", 7, ["change"])
    assert [(item["entity"], item["name"]) for item in gas["entities"]] == [
        ("sensor.heating_gas", t["gas_heating"]), ("sensor.tapping_gas", t["gas_tapping"]),
        ("sensor.keep_warm_gas", t["gas_keeping_warm"])]
    assert gas["visibility"] == [{"condition": "or", "conditions": [
        {"condition": "numeric_state", "entity": "sensor.tapping_gas", "above": 0},
        {"condition": "numeric_state", "entity": "sensor.keep_warm_gas", "above": 0}]}]
    assert note["type"] == "markdown" and t["gas_tapping"] in note["content"]
    assert {"Tapping": "en", "Tappen": "nl"}[t["gas_tapping"]] == lang
    # Firmware without the activity: the gas alone; without the split: nothing.
    assert [card["type"] for card in _hot_water_use_cards(t, {**HUB, "boiler_activity": None})] == [
        "statistics-graph", "markdown"]
    assert _hot_water_use_cards(t, {"heating_gas": "sensor.heating_gas", "hot_water_gas": "sensor.hot_water_gas"}) == []


@pytest.mark.asyncio
async def test_the_boiler_views_hot_water_section_holds_the_timeline_and_the_gas_per_post(hass):
    from homeassistant.helpers import entity_registry as er
    from test_dashboard_redesign import headed, setup as dashboard, view
    from custom_components.open_thermostat.dashboard import RoomDashboard
    from test_dashboard_heating import walk
    config, hub, fields = dashboard(hass)
    assert not any(card["type"] == "statistics-graph" for card in headed(view(config, "boiler"))["Hot water"])
    entities = er.async_get(hass)
    entry = next(iter(hass.config_entries.async_entries("open_thermostat")))
    device = entities.async_get(fields["dhw_active"]).device_id
    for key in HUB:
        entities.async_get_or_create("sensor", "open_thermostat", f"fixture_hub_{key}", config_entry=entry,
                                     device_id=device, suggested_object_id=key)
    config = RoomDashboard(hass, "fixture", entry.entry_id)._dashboard_config()
    assert None not in list(walk(config))
    sections = headed(view(config, "boiler"))
    assert list(sections) == ["Heating", "Hot water", "Status and faults", "Boiler settings",
                              "Thermostat on the bus", "Last 24 hours"]  # no extra section
    cards = sections["Hot water"]
    timeline = next(card for card in cards if card["type"] == "history-graph")
    assert [item["entity"] for item in timeline["entities"]] == ["sensor.boiler_activity", fields["heating_active"]]
    gas = next(card for card in cards if card["type"] == "statistics-graph")
    assert [item["entity"] for item in gas["entities"]] == ["sensor.heating_gas", "sensor.tapping_gas",
                                                           "sensor.keep_warm_gas"]


# -- an optional water meter ------------------------------------------------------------------------------

WATER = json.loads((Path(__file__).parent / "fixtures" / "water_owner_20261031.json").read_text())


def water(hass, value, unit="L/min", entity="sensor.water", state_class="measurement"):
    hass.states.async_set(entity, str(value), {"unit_of_measurement": unit, "state_class": state_class})


@pytest.mark.asyncio
async def test_a_water_meter_is_an_optional_flow_or_reading_that_stays_in_home_assistant(hass):
    from custom_components.open_thermostat.energy_input import (CONF_WATER_METER, EnergyError, energy_payloads,
                                                                energy_schema, validate_energy, water_reading)
    import voluptuous as vol
    water(hass, 6.2)
    water(hass, 7.629, "m³", "sensor.water_total", "total_increasing")
    water(hass, 7.629, "m³", "sensor.water_rate_m3", "measurement")
    water(hass, 20, "°C", "sensor.water_temp")
    assert validate_energy(hass, {"water_meter": "sensor.water"}) == {CONF_WATER_METER: "sensor.water"}
    assert validate_energy(hass, {"water_meter": "sensor.water_total"}) == {CONF_WATER_METER: "sensor.water_total"}
    assert validate_energy(hass, {}) == {}                                  # optional
    for entity, code in (("sensor.water_rate_m3", "water_meter_not_total"), ("sensor.water_temp", "water_meter_unit"),
                         ("sensor.none", "entity_not_found")):
        with pytest.raises(EnergyError) as error:
            validate_energy(hass, {"water_meter": entity})
        assert (error.value.field, error.value.code) == ("water_meter", code)
    assert "water_meter" in [str(key) for key in energy_schema(vol, {}).schema]
    assert water_reading(hass.states.get("sensor.water")) == ("flow", 6.2)
    assert water_reading(hass.states.get("sensor.water_total")) == ("total", 7629.0)
    assert energy_payloads(hass, {CONF_WATER_METER: "sensor.water"}) == []  # nothing goes to the E32
    component = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        options = json.loads((component / name).read_text(encoding="utf-8"))["options"]
        assert options["step"]["energy"]["data"]["water_meter"] and options["step"]["energy"]["data_description"]["water_meter"]
        assert options["error"]["water_meter_unit"] and options["error"]["water_meter_not_total"]


@pytest.mark.asyncio
@pytest.mark.parametrize("meter", ["flow", "total"])
async def test_with_a_water_meter_a_round_with_water_is_tapping_and_one_without_keeping_warm(hass, meter):
    from custom_components.open_thermostat.energy_input import CONF_WATER_METER
    total = [7.0]

    def flowing(on):
        if meter == "flow":
            water(hass, 6.5 if on else 0.0)
        else:
            total[0] += 0.002 if on else 0.0
            water(hass, f"{total[0]:.3f}", "m³", state_class="total_increasing")
    flowing(False)
    use, values, clock, added = setup(hass, options={CONF_WATER_METER: "sensor.water"})
    values.update(reported_burner_modulation=0, dhw_active=0)
    use.tick(); run(use, clock, 300)
    # A keep-warm round: no water. The E32 calls it a tap; the meter decides.
    use.hub.summary = summary(tapping=1)
    values.update(reported_burner_modulation=70, dhw_active=1); run(use, clock, 120)
    values.update(reported_burner_modulation=0, dhw_active=0); run(use, clock, 300)
    # A small tap before the round (the round starts once it has ended), then one during a round.
    flowing(True); run(use, clock, 30); flowing(False); run(use, clock, 30)
    values.update(reported_burner_modulation=60, dhw_active=1); run(use, clock, 90)
    values.update(reported_burner_modulation=0, dhw_active=0); run(use, clock, 300)
    values.update(reported_burner_modulation=80, dhw_active=1); run(use, clock, 20)
    flowing(True); run(use, clock, 60); flowing(False); run(use, clock, 20)
    values.update(reported_burner_modulation=0, dhw_active=0); run(use, clock, 300)
    day = use.data["days"][DAY0.isoformat()]
    assert day["water"] is True and (day["taps"], day["keep_warm_rounds"]) == (2, 1)
    assert day["keep_warm_s"] == 120 and day["tapping_s"] == 190
    assert 0 < use.data["totals"]["keep_warm"] < use.data["totals"]["tapping"]
    attributes = use.attributes("keep_warm")
    assert (attributes["dhw_method"], attributes["dhw_baseline"], attributes["rounds_today"]) == ("water_meter", None, 1)
    assert use.attributes("tapping")["rounds_today"] == 2
    # The meter stops reporting: a round it did not cover only counts as hot water.
    hass.states.async_set("sensor.water", "unavailable", {})
    values.update(reported_burner_modulation=70, dhw_active=1); run(use, clock, 60)
    values.update(reported_burner_modulation=0, dhw_active=0); run(use, clock, 300)
    assert (day["taps"], day["keep_warm_rounds"]) == (2, 1)


@pytest.mark.asyncio
async def test_without_the_e32_sorting_a_water_meter_alone_splits_hot_water(hass):
    from custom_components.open_thermostat.energy_input import CONF_WATER_METER
    water(hass, 0.0)
    use, values, clock, added = make(hass, {CONF_WATER_METER: "sensor.water"})  # older firmware: no dhw summary
    values.update(reported_burner_modulation=0, dhw_active=0)
    use.tick(); run(use, clock, 300)
    values.update(reported_burner_modulation=70, dhw_active=1); run(use, clock, 120)
    values.update(reported_burner_modulation=0, dhw_active=0); run(use, clock, 300)
    assert sorted(sensor.kind for sensor in added) == ["heating", "hot_water", "keep_warm", "tapping"]
    assert use.data["days"][DAY0.isoformat()]["keep_warm_rounds"] == 1


@pytest.mark.asyncio
async def test_the_owners_day_with_the_water_meter(hass):
    """31 Oct 2026 with the owner's water meter (L/min): water from 2 min before to 1 min after a round makes it a tap.

    The DHW temperature rule counted 40 keep-warm rounds that day; the meter shows water around 34 of the 57 rounds."""
    from custom_components.open_thermostat.energy_input import CONF_WATER_METER
    water(hass, 0.0)
    use, values, clock, added = setup(hass, options={CONF_WATER_METER: "sensor.water"})
    samples = [tuple(map(int, item.split(","))) for item in FIXTURE["samples"].split(";")]
    flowing = WATER["flowing_s"]
    use.tick()
    for index, (modulation, dhw) in enumerate(samples):
        second = index * 10
        values.update(reported_burner_modulation=modulation, dhw_active=dhw)
        water(hass, 6.0 if any(a <= second < b for a, b in flowing) else 0.0)
        clock[0] += 10
        use.tick()
    run(use, clock, 120)
    day = use.data["days"][DAY0.isoformat()]
    print("owner 31 Oct with the water meter:", day["taps"], "taps,", day["keep_warm_rounds"], "keep-warm rounds,",
          round(day["keep_warm_m3"] / day["hot_water_m3"] * 100), "% of the hot-water gas keeping warm")
    assert day["water"] is True
    assert (day["taps"], day["keep_warm_rounds"]) == (33, 23)  # the first (00:00, wet) began before the first reading
