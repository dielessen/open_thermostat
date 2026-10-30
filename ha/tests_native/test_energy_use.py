"""Gas for heating and for hot water (Energy dashboard): meter split, estimate, store and entity creation."""
import json
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.open_thermostat import energy_use as module
from custom_components.open_thermostat.energy_input import CONF_BOILER_KW, CONF_GAS_KWH_PER_M3, CONF_GAS_METER
from custom_components.open_thermostat.energy_use import EnergyUse, GasUseSensor, valid_data
from custom_components.open_thermostat.heating_link import HeatingHub
from test_heating_advice import FakeCache

T0 = 1_800_000_000.0
DAY0 = date(2026, 10, 29)
STATUS = {"schema": 1, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
          "ha_entities": [], "rooms": []}


class FakeStore:
    def __init__(self, data=None):
        self.data, self.saved, self.pending = data, [], None

    async def async_load(self):
        return deepcopy(self.data)

    def async_delay_save(self, data, delay):
        self.pending = (data, delay)

    async def async_save(self, data):
        self.saved.append(deepcopy(data))


def make(hass, options=None, stored=None):
    clock = [T0]
    hub = HeatingHub("fixture", clock=lambda: clock[0])
    client = SimpleNamespace(boiler_fields=FakeCache(), ready=True, boiler_fields_supported=True,
                             clock=lambda: clock[0])
    unloads = []
    entry = SimpleNamespace(entry_id="e1", options=dict(options or {}), async_on_unload=unloads.append)
    use = EnergyUse(hass, entry, hub, SimpleNamespace(client=client), clock=lambda: clock[0],
                    local_date=lambda now: date.fromordinal(DAY0.toordinal() + int((now - T0) // 86400)),
                    store=FakeStore(stored))
    added = []
    use._add = added.extend
    return use, client.boiler_fields.values, clock, added


def run(use, clock, seconds, step=module.SAMPLE_SECONDS):
    for _ in range(int(seconds // step)):
        clock[0] += step
        use.tick()


def gas_meter(hass, value, unit="m³"):
    attributes = {"unit_of_measurement": unit, "state_class": "total_increasing",
                  "device_class": "gas" if unit == "m³" else "energy"}
    hass.states.async_set("sensor.gas", str(value), attributes)


@pytest.mark.asyncio
async def test_without_modulation_nothing_is_counted_and_no_entity_appears(hass):
    use, values, clock, added = make(hass)
    use.tick()
    run(use, clock, 600)
    assert added == [] and use.data["created"] is False and use.data["totals"] == {"heating": 0, "hot_water": 0}
    values["reported_burner_modulation"] = 40  # no hot-water state yet: nothing to split
    run(use, clock, 600)
    assert added == [] and use.data["totals"] == {"heating": 0, "hot_water": 0}


@pytest.mark.asyncio
async def test_estimate_without_a_meter_is_modulation_times_power_split_by_hot_water(hass):
    use, values, clock, added = make(hass, {CONF_BOILER_KW: 20})
    values.update(reported_burner_modulation=50, dhw_active=0)
    use.tick()
    heating, hot_water = added
    assert [sensor.unique_id for sensor in added] == ["fixture_hub_heating_gas", "fixture_hub_hot_water_gas"]
    assert heating.translation_key == "heating_gas" and hot_water.translation_key == "hot_water_gas"
    assert heating.state_class == SensorStateClass.TOTAL_INCREASING
    assert heating.native_unit_of_measurement == "m³" and heating.device_class == SensorDeviceClass.GAS
    run(use, clock, 3600)  # one hour at 50 % of 20 kW = 10 kWh
    values["dhw_active"] = 1
    run(use, clock, 360)  # the first 10 s still belong to the heating sample
    day = use.data["days"][DAY0.isoformat()]
    assert day["heating_kwh"] == pytest.approx(10 * 3610 / 3600)
    assert day["hot_water_kwh"] == pytest.approx(10 * 350 / 3600)
    assert heating.native_value == pytest.approx(day["heating_kwh"] / 9.77, abs=1e-3)
    assert hot_water.native_value == pytest.approx(day["hot_water_kwh"] / 9.77, abs=1e-3)
    assert day["heating_s"] == 3610 and day["hot_water_s"] == 350 and day["observed_s"] == 3960
    assert day["estimate"] is True and day["meter"] is False
    attributes = heating.extra_state_attributes
    assert attributes["method"] == "estimate" and attributes["estimate"] is True and attributes["rough"] is False
    assert attributes["today_kwh"] == pytest.approx(10.03, abs=0.01) and attributes["share_last_7_days"] == 91
    # A gap (no telemetry for two minutes) is not counted; the burner off counts no gas.
    before = deepcopy(use.data["totals"])
    clock[0] += 120
    use.tick()
    assert use.data["totals"] == before
    values["reported_burner_modulation"] = 0
    run(use, clock, 600)
    assert use.data["totals"]["hot_water"] == pytest.approx(before["hot_water"] + 0.5 * 20 * 10 / 3600 / 9.77)
    # Without a boiler power the E32's own (or its default) is used and the estimate says it is rough.
    use.entry.options = {}
    assert use.power() == (22.0, False) and heating.extra_state_attributes["rough"] is True
    assert len(added) == 2  # created once


@pytest.mark.asyncio
async def test_a_gas_meter_gives_the_real_values_shared_by_what_the_boiler_did(hass):
    gas_meter(hass, "100.000")
    use, values, clock, added = make(hass, {CONF_GAS_METER: "sensor.gas", CONF_BOILER_KW: 24})
    values.update(reported_burner_modulation=60, dhw_active=0)
    use.tick()
    run(use, clock, 1800)
    values["dhw_active"] = 1
    run(use, clock, 600)
    pending = dict(use.data["pending"])
    assert use.data["totals"] == {"heating": 0, "hot_water": 0} and pending["heating"] > pending["hot_water"] > 0
    pending["hot_water"] += 0.6 * 24 * 10 / 3600  # the next tick counts first, then reads the meter
    gas_meter(hass, "100.900")
    run(use, clock, 10)
    share = pending["heating"] / (pending["heating"] + pending["hot_water"])
    totals = use.data["totals"]
    assert totals["heating"] == pytest.approx(0.9 * share) and totals["hot_water"] == pytest.approx(0.9 * (1 - share))
    assert totals["heating"] + totals["hot_water"] == pytest.approx(0.9)
    day = use.data["days"][DAY0.isoformat()]
    assert day["meter"] is True and day["estimate"] is False and day["other_m3"] == 0
    assert day["heating_kwh"] == pytest.approx(0.9 * share * 9.77)
    assert added[0].extra_state_attributes["method"] == "gas_meter"
    # Gas while the burner was off is another appliance (a gas stove): neither heating nor hot water.
    values["reported_burner_modulation"] = 0
    run(use, clock, 600)
    gas_meter(hass, "100.950")  # the last 10 s of burning before the burner went off
    run(use, clock, 10)
    assert use.data["totals"]["heating"] + use.data["totals"]["hot_water"] == pytest.approx(0.95)
    run(use, clock, 600)
    gas_meter(hass, "101.000")
    run(use, clock, 10)
    assert use.data["totals"]["heating"] + use.data["totals"]["hot_water"] == pytest.approx(0.95)
    assert day["other_m3"] == pytest.approx(0.05)
    # A jump (replaced meter) and a lower reading (reset) count nothing; counting goes on from there.
    values["reported_burner_modulation"] = 60
    run(use, clock, 300)
    gas_meter(hass, "180")
    run(use, clock, 10)
    gas_meter(hass, "5")
    run(use, clock, 10)
    assert use.data["totals"]["heating"] + use.data["totals"]["hot_water"] == pytest.approx(0.95)
    assert use.data["meter"]["value"] == 5


@pytest.mark.asyncio
async def test_a_meter_that_stays_still_while_the_boiler_burns_is_estimated_instead(hass):
    gas_meter(hass, "50")
    use, values, clock, _ = make(hass, {CONF_GAS_METER: "sensor.gas", CONF_BOILER_KW: 20})
    values.update(reported_burner_modulation=50, dhw_active=0)
    use.tick()
    run(use, clock, module.METER_STALE_SECONDS + 60, step=30)
    totals = use.data["totals"]
    assert totals["heating"] == pytest.approx(0.5 * 20 * 6 / 9.77, rel=0.01)
    assert use.data["days"][DAY0.isoformat()]["estimate"] is True
    # The meter starts afresh: its next increase is not counted twice.
    counted = totals["heating"]
    gas_meter(hass, "56")
    run(use, clock, 10)
    assert use.data["totals"]["heating"] == pytest.approx(counted, abs=0.01)


@pytest.mark.asyncio
async def test_a_kwh_meter_makes_the_sensors_kwh_and_converts_the_total_once(hass):
    use, values, clock, added = make(hass, {CONF_BOILER_KW: 20, CONF_GAS_KWH_PER_M3: 10})
    values.update(reported_burner_modulation=50, dhw_active=0)
    use.tick()
    run(use, clock, 3600)
    assert use.data["totals"]["heating"] == pytest.approx(1.0)  # 10 kWh at 10 kWh/m³
    gas_meter(hass, "21100", unit="kWh")
    use.entry.options = {CONF_GAS_METER: "sensor.gas", CONF_BOILER_KW: 20, CONF_GAS_KWH_PER_M3: 10}
    run(use, clock, 10)
    heating = added[0]
    assert use.unit == "kWh" and heating.native_unit_of_measurement == "kWh"
    assert heating.device_class == SensorDeviceClass.ENERGY and heating.suggested_display_precision == 1
    assert use.data["totals"]["heating"] == pytest.approx(10.0)  # those 10 s wait for the meter
    run(use, clock, 600)
    gas_meter(hass, "21103.5", unit="kWh")
    before = use.data["totals"]["heating"]
    run(use, clock, 10)
    assert use.data["totals"]["heating"] == pytest.approx(before + 3.5)
    # Removing the meter again: what waited for it is estimated, the totals stay.
    run(use, clock, 600)
    use.entry.options = {CONF_BOILER_KW: 20, CONF_GAS_KWH_PER_M3: 10}
    run(use, clock, 10)
    assert use.data["meter"] is None and use.data["totals"]["heating"] > before + 3.5


@pytest.mark.asyncio
async def test_days_keep_taps_and_the_night_saving_and_the_store_restores_them(hass):
    use, values, clock, added = make(hass)
    values.update(reported_burner_modulation=30, dhw_active=0)
    use.hub.update(STATUS)
    use.hub.summary = {"schema": 1, "dhw": {"today": {"tapping": {"count": 4, "s": 180}}}}
    use.hub.warmup = {"woonkamer": {"night": {"reason": "estimated", "recommended": "hold_0_5",
                                              "recommended_night_c": 17.5, "saving_m3": 0.12, "saving_eur": 0.16}},
                      "badkamer": {"night": {"reason": "estimated", "recommended": "program", "saving_m3": 0}},
                      "zolder": {"night": {"reason": "not_learned"}}}
    use.tick()
    run(use, clock, 60)
    day = use.data["days"][DAY0.isoformat()]
    assert day["taps"] == 4 and day["nights"] == {"woonkamer": [0.12, 0.16], "badkamer": [0.0, None]}
    assert use.store.pending is not None and use.store.pending[1] == module.SAVE_DELAY_SECONDS
    restored = valid_data(json.loads(json.dumps(use.data)))
    assert restored == use.data
    for broken in (None, [], {"schema": 2}, {**use.data, "unit": "L"}, {**use.data, "totals": {"heating": -1}}):
        assert valid_data(broken) is None
    messy = valid_data({**json.loads(json.dumps(use.data)), "days": {"not a day": {}, "2026-10-01": "x",
                                                                       "2026-10-02": {"heating_m3": "x", "heating_s": -5}}})
    assert set(messy["days"]) == {"2026-10-02"} and messy["days"]["2026-10-02"] == module.empty_day()
    # Only 15 days are kept.
    run(use, clock, 20 * 86400, step=3600)
    assert len(use.data["days"]) == module.DAYS_KEPT
    # Stored as created: the sensors are there at once after a restart, before the boiler reports.
    again, _, _, _ = make(hass, stored=json.loads(json.dumps(use.data)))
    later = []
    await again.async_start(later.extend)
    assert [sensor.unique_id for sensor in later] == ["fixture_hub_heating_gas", "fixture_hub_hot_water_gas"]
    assert later[0].native_value == pytest.approx(use.data["totals"]["heating"], abs=1e-3)
    for remove in again.entry.async_on_unload.__self__:
        if (job := remove()) is not None:
            await job
    assert again.store.saved and again.store.saved[-1]["created"] is True


@pytest.mark.asyncio
async def test_the_product_setup_adds_the_advice_and_registers_the_gas_counting(hass, monkeypatch):
    from custom_components.open_thermostat.heating_advice import async_setup_heating_advice
    stores = []
    monkeypatch.setattr(module, "Store", lambda hass, version, key: stores.append(key) or FakeStore())
    hub = HeatingHub("fixture")
    unloads = []
    entry = SimpleNamespace(entry_id="e9", options={}, async_on_unload=unloads.append)
    hass.data.setdefault("open_thermostat", {})["e9"] = {}
    added = []
    await async_setup_heating_advice(hass, entry, lambda entities, **options: added.append((entities, options)),
                                     {"config_subentry_id": "group"}, hub, SimpleNamespace(client=None))
    assert stores == ["open_thermostat.energy_use.e9"]
    assert [type(entity).__name__ for entity in added[0][0]] == ["HeatingAdviceSensor"]
    use = hass.data["open_thermostat"]["e9"]["energy_use"]
    use.tick()
    assert len(added) == 1  # no boiler fields: no gas entities
    use.connection = SimpleNamespace(client=SimpleNamespace(
        boiler_fields=FakeCache(), ready=True, boiler_fields_supported=True, clock=lambda: 0))
    use.connection.client.boiler_fields.values.update(plus_burner_modulation=20, plus_dhw_valve=0)
    use.tick()
    entities, options = added[1]
    assert [type(entity) for entity in entities] == [GasUseSensor, GasUseSensor]
    assert options == {"config_subentry_id": "group"}
    for remove in unloads:
        if (job := remove()) is not None:
            await job


@pytest.mark.asyncio
async def test_a_total_never_goes_down_after_a_restart(hass):
    from homeassistant.core import State
    use, values, clock, added = make(hass)
    use.data["totals"]["heating"] = 3.0
    sensor = GasUseSensor(use, "heating")
    sensor.hass = hass
    for last, expected in ((State("sensor.x", "4.5", {"unit_of_measurement": "m³"}), 4.5),
                           (State("sensor.x", "9", {"unit_of_measurement": "kWh"}), 4.5),
                           (State("sensor.x", "unavailable", {}), 4.5), (None, 4.5),
                           (State("sensor.x", "2", {"unit_of_measurement": "m³"}), 4.5)):
        async def last_state(last=last):
            return last
        sensor.async_get_last_state = last_state
        await sensor.async_added_to_hass()
        assert use.data["totals"]["heating"] == expected


def test_gas_counting_never_writes_a_setting():
    for path in (module.__file__, module.__file__.replace("energy_use.py", "weekly_summary.py")):
        text = open(path, encoding="utf-8").read()
        for forbidden in ("async_publish", "async_write_heating_plan", "async_call(", "boiler_write", "heating_input"):
            assert forbidden not in text, (path, forbidden)


@pytest.mark.asyncio
async def test_dashboard_gas_section_shows_both_sensors_per_day_and_how_they_are_counted(hass):
    from homeassistant.helpers.template import Template
    from custom_components.open_thermostat.dashboard import TEXT, _energy_section
    assert _energy_section(TEXT["en"], None, None) is None
    section = _energy_section(TEXT["nl"], "sensor.gas_voor_verwarmen", "sensor.gas_voor_warm_water")
    # The days in one bar chart (not the meter totals, which tell a user little), and how it is counted.
    heading, graph, note = section["cards"]
    assert heading["heading"] == "Gas per dag"
    assert graph["type"] == "statistics-graph" and graph["stat_types"] == ["change"] and graph["period"] == "day"
    assert graph["entities"] == [{"entity": "sensor.gas_voor_verwarmen", "name": "Verwarmen"},
                                 {"entity": "sensor.gas_voor_warm_water", "name": "Warm water"}]
    hass.states.async_set("sensor.gas_voor_verwarmen", "1.2", {"estimate": True})
    assert "Geschat" in Template(note["content"], hass).async_render()
    hass.states.async_set("sensor.gas_voor_verwarmen", "1.2", {"estimate": False})
    text = Template(note["content"], hass).async_render()
    assert "Gemeten met je gasmeter" in text and "energiedashboard" in text
