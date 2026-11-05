"""The daily summary (1.0): burner time, starts and short runs, time to target and missed comfort per room,
outdoor temperature and gas per post, kept for three weeks; gaps never count."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from custom_components.open_thermostat import daily_summary as module
from custom_components.open_thermostat.const import (SUMMARY_DAYS_KEPT, SUMMARY_TARGET_ON_TIME_MINUTES)
from custom_components.open_thermostat.daily_summary import (DailySummary, DailySummarySensor, SummaryTotalSensor,
                                                             valid_data)
from custom_components.open_thermostat.energy_input import CONF_OUTDOOR
from custom_components.open_thermostat.heating_link import HeatingHub
from test_heating_advice import FakeCache

T0 = 1_800_000_000.0  # local midnight of DAY0 in these tests
DAY0 = date(2026, 10, 31)
MIN = 60
FIXTURE = Path(__file__).parent / "fixtures" / "burner_modulation_20261031.json"


class FakeStore:
    def __init__(self, data=None):
        self.data, self.saved, self.pending = data, [], None

    async def async_load(self):
        return deepcopy(self.data)

    def async_delay_save(self, data, delay):
        self.pending = (data, delay)

    async def async_save(self, data):
        self.saved.append(deepcopy(data))


def room(temperature=None, setpoint=None, demand=False, status="ok", **extra):
    return {"id": "woonkamer", "name": "Woonkamer", "state": "active", "status": status, "demand": demand,
            "temperature": temperature, "setpoint": setpoint, **extra}


def heating(rooms):
    return {"schema": 1, "revision": 1, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
            "ha_entities": [], "rooms": rooms}


def make(hass, options=None, stored=None):
    clock = [T0]
    hub = HeatingHub("fixture", clock=lambda: clock[0])
    client = SimpleNamespace(boiler_fields=FakeCache(), ready=True, boiler_fields_supported=True,
                             clock=lambda: clock[0])
    entry = SimpleNamespace(entry_id="e1", options=dict(options or {}), async_on_unload=lambda _: None)
    hass.data.setdefault("open_thermostat", {})["e1"] = {}
    summary = DailySummary(hass, entry, hub, SimpleNamespace(client=client), clock=lambda: clock[0],
                           local_date=lambda now: date.fromordinal(DAY0.toordinal() + int((now - T0) // 86400)),
                           store=FakeStore(stored))
    added = []
    summary._add = added.extend
    return summary, hub, client.boiler_fields.values, clock, added


def run(summary, hub, clock, seconds, rooms=None, modulation=None, values=None):
    """Advance in 10 s ticks; ``rooms`` (a function of the time) is reported by a fresh E32 every tick."""
    for _ in range(int(seconds // module.SAMPLE_SECONDS)):
        clock[0] += module.SAMPLE_SECONDS
        if modulation is not None:
            value = modulation(clock[0] - T0)
            if value is None:
                values.pop("reported_burner_modulation", None)  # unknown, as the boiler reported it
            else:
                values["reported_burner_modulation"] = value
            values["dhw_active"] = 0
        if rooms is not None:
            hub.update(heating(rooms(clock[0])))
        summary.tick()


@pytest.mark.asyncio
async def test_the_owners_31_october_gives_its_burner_time_starts_and_short_runs(hass):
    """The owner's real burner modulation of 31 Oct 2026, replayed in 10 s samples."""
    changes = json.loads(FIXTURE.read_text(encoding="utf-8"))["changes"]

    def modulation(t):
        value = None
        for at, v in changes:
            if at > t:
                break
            value = v
        return value

    summary, hub, values, clock, added = make(hass)
    run(summary, hub, clock, 86400, rooms=lambda now: [], modulation=modulation, values=values)
    day = summary.data["days"][DAY0.isoformat()]
    # Independently counted from the same changes: 59 runs, 56 of them shorter than 10 minutes (the store's
    # keep-warm rounds), 3.73 burner hours.
    assert day["starts"] == 59 and day["short_runs"] == 56
    assert day["burner_s"] / 3600 == pytest.approx(3.73, abs=0.02)
    # The sensors appear once the boiler reported its modulation; three totals plus the summary.
    assert [type(s) for s in added] == [DailySummarySensor, SummaryTotalSensor, SummaryTotalSensor, SummaryTotalSensor]
    clock[0] += 60
    assert summary.finished_days() == [DAY0.isoformat()]
    figures = summary.summary(DAY0.isoformat())
    assert figures["burner_starts"] == 59 and figures["short_runs"] == 56 and figures["complete"] is True


@pytest.mark.asyncio
async def test_time_to_target_late_and_missed_comfort_per_room(hass):
    summary, hub, values, clock, added = make(hass)
    values["reported_burner_modulation"], values["dhw_active"] = 0, 0
    temperature = {"value": 18.0}

    def rooms(now):
        t = now - T0
        target = 18.0 if t < 3600 else 21.0          # the program steps up at 01:00
        if t >= 3600:
            temperature["value"] = min(21.0, 18.0 + (t - 3600) / 3600)  # warms 1 °C per hour: 3 h to 21 °C
        return [room(temperature["value"], target, demand=t >= 3600 and temperature["value"] < 21.0)]

    run(summary, hub, clock, 6 * 3600, rooms)
    record = summary.data["days"][DAY0.isoformat()]["rooms"]["woonkamer"]
    # Within 0.2 °C after about 168 minutes: late (more than 120), reached.
    assert len(record["steps"]) == 1 and record["steps"][0] == pytest.approx(168, abs=2)
    assert record["late"] == 1 and record["not_reached"] == 0
    # Missed comfort: more than 0.5 °C below for longer than 120 minutes. Below by 0.5 until 02:30 (150 min)
    # after the step: 150 - 120 = about 30 minutes missed.
    assert record["missed_s"] / 60 == pytest.approx(30, abs=2)
    assert record["demand_s"] / 3600 == pytest.approx(3.0, abs=0.05)
    figures = summary.summary(DAY0.isoformat())["rooms"][0]
    assert figures["name"] == "Woonkamer" and figures["time_to_target_minutes"] == pytest.approx(168, abs=2)


@pytest.mark.asyncio
async def test_a_target_lowered_before_it_was_reached_counts_as_not_reached(hass):
    summary, hub, values, clock, added = make(hass)
    target = {"value": 18.0}
    run(summary, hub, clock, 120, lambda now: [room(18.0, target["value"], demand=False)])
    target["value"] = 21.0
    run(summary, hub, clock, 1800, lambda now: [room(18.5, target["value"], demand=True)])
    target["value"] = 17.0  # the program goes down to night before the room got there
    run(summary, hub, clock, 120, lambda now: [room(18.5, target["value"], demand=False)])
    record = summary.data["days"][DAY0.isoformat()]["rooms"]["woonkamer"]
    assert record["steps"] == [] and record["not_reached"] == 1 and record["missed_s"] == 0


@pytest.mark.asyncio
async def test_a_gap_in_the_e32_data_never_counts_and_marks_the_day_partial(hass):
    summary, hub, values, clock, added = make(hass)
    cold = lambda now: [room(18.0, 21.0, demand=True)]
    run(summary, hub, clock, SUMMARY_TARGET_ON_TIME_MINUTES * 60 - 600, cold)
    # Ten hours without the E32: nothing is followed, and the "below since" starts again afterwards.
    clock[0] += 10 * 3600
    hub.check_stale()  # the hub's own timer: the E32's values go stale
    assert not hub.fresh
    summary.tick()
    run(summary, hub, clock, 60 * MIN, cold)
    record = summary.data["days"][DAY0.isoformat()]["rooms"]["woonkamer"]
    assert record["missed_s"] == 0  # 110 min before the gap + 60 after: never longer than 120 in one stretch
    clock[0] = T0 + 86400 + 60
    summary.tick()
    assert summary.summary(DAY0.isoformat())["complete"] is False


@pytest.mark.asyncio
async def test_a_window_or_an_inactive_room_is_not_followed(hass):
    summary, hub, values, clock, added = make(hass)
    run(summary, hub, clock, 4 * 3600, lambda now: [room(18.0, 21.0, demand=True, comfort={"window": "open"}),
                                                     {**room(15.0, 21.0, demand=True, status="inactive"),
                                                      "id": "zolder"}])
    assert summary.data["days"][DAY0.isoformat()]["rooms"] == {}


@pytest.mark.asyncio
async def test_outdoor_temperature_and_gas_per_post(hass):
    hass.states.async_set("sensor.outside", "4.5", {"unit_of_measurement": "°C"})
    summary, hub, values, clock, added = make(hass, {CONF_OUTDOOR: "sensor.outside"})
    run(summary, hub, clock, 300, lambda now: [])
    hass.states.async_set("sensor.outside", "-1.5", {"unit_of_measurement": "°C"})
    run(summary, hub, clock, 300, lambda now: [])
    outdoor = summary.summary(DAY0.isoformat())["outdoor"]
    assert outdoor["min"] == -1.5 and outdoor["max"] == 4.5 and -1.5 < outdoor["mean"] < 4.5
    # Gas comes from the energy use records (never counted twice); any further posts appear as they exist.
    use = SimpleNamespace(unit="m³", data={"days": {DAY0.isoformat(): {
        "heating_m3": 0.544, "hot_water_m3": 4.083, "heating_kwh": 5.3, "keep_warm_m3": 2.37}}})
    hass.data["open_thermostat"]["e1"]["energy_use"] = use
    assert summary.summary(DAY0.isoformat())["gas"] == {"heating": 0.544, "hot_water": 4.083, "keep_warm": 2.37}
    # The day record exactly as energy_use writes it: every post it has, keeping warm too.
    from custom_components.open_thermostat import energy_use
    record = {**energy_use.empty_day(), "heating_m3": 0.5, "hot_water_m3": 4.0, "tapping_m3": 1.5, "keep_warm_m3": 2.5}
    use.data["days"][DAY0.isoformat()] = record
    assert summary.summary(DAY0.isoformat())["gas"] == {"heating": 0.5, "hot_water": 4.0, "tapping": 1.5, "keep_warm": 2.5}


@pytest.mark.asyncio
async def test_three_weeks_are_kept_and_a_damaged_store_starts_afresh(hass):
    summary, hub, values, clock, added = make(hass)
    for _ in range(SUMMARY_DAYS_KEPT + 5):
        clock[0] += 86400
        summary.day()
    assert len(summary.data["days"]) == SUMMARY_DAYS_KEPT
    assert valid_data({"days": [], "totals": {}}) is None
    assert valid_data({"days": {"nonsense": {}}, "totals": {"burner_s": 1, "starts": 2, "missed_s": 0}}) == {
        "days": {}, "totals": {"burner_s": 1, "starts": 2, "missed_s": 0}, "created": False}
    assert valid_data({"days": {}, "totals": {"burner_s": -1, "starts": 0, "missed_s": 0}}) is None


@pytest.mark.asyncio
async def test_the_sensors_and_their_statistics(hass):
    summary, hub, values, clock, added = make(hass)
    values["reported_burner_modulation"], values["dhw_active"] = 50, 0
    run(summary, hub, clock, 3600, lambda now: [])
    sensors = {s.unique_id: s for s in added}
    assert set(sensors) == {"fixture_hub_daily_summary", "fixture_hub_daily_burner_time",
                            "fixture_hub_daily_burner_starts", "fixture_hub_daily_missed_comfort"}
    burner = sensors["fixture_hub_daily_burner_time"]
    assert burner.state_class == SensorStateClass.TOTAL_INCREASING and burner.device_class == SensorDeviceClass.DURATION
    assert burner.native_unit_of_measurement == "h" and burner.native_value == pytest.approx(1.0, abs=0.01)
    assert sensors["fixture_hub_daily_burner_starts"].native_value == 0  # it was burning from the first sample
    summary_sensor = sensors["fixture_hub_daily_summary"]
    assert summary_sensor.native_value is None  # no finished day yet
    clock[0] = T0 + 86400 + 60
    summary.tick()
    assert summary_sensor.native_value == DAY0.isoformat()
    assert summary_sensor.extra_state_attributes["last_day"]["burner_hours"] == pytest.approx(1.0, abs=0.01)
    assert "days" in summary_sensor._unrecorded_attributes


def test_the_daily_sensors_have_names_of_their_own_on_the_e32_device():
    """The boiler's own counters (field_reported_burner_starts, ...) sit on the same device."""
    component = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        sensors = json.loads((component / name).read_text(encoding="utf-8"))["entity"]["sensor"]
        others = {value["name"] for key, value in sensors.items() if not key.startswith("daily_")}
        daily = {key: sensors[key]["name"] for key in ("daily_summary", "daily_burner_time", "daily_burner_starts",
                                                        "daily_missed_comfort")}
        assert not set(daily.values()) & others, (name, set(daily.values()) & others)
        # The three are running totals since the install (total_increasing): no name may call them today's.
        for key in ("daily_burner_time", "daily_burner_starts", "daily_missed_comfort"):
            assert not any(word in daily[key].lower() for word in ("today", "vandaag", "dziś")), (name, daily[key])
    assert json.loads((component / "translations/nl.json").read_text(encoding="utf-8"))["entity"]["sensor"][
        "daily_burner_starts"]["name"] == "Branderstarts (totaal)"
