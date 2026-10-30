"""The "Heating problem" sensor: on for real problems only, with the reasons in plain English or Dutch."""
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.heating_problem import (
    ACTIVE_WARNING_SECONDS, AWAITING_CONFIRMATION_SECONDS, ROOM_LOST_SECONDS, SHORT_CYCLING_SECONDS, TELEMETRY_STALE_SECONDS, TEXT,
    HeatingProblemSensor, ProblemTracker, render)

MIN = 60


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def status(rooms=None, burner=None, mode="shadow", active=None):
    value = {"schema": 1, "revision": 1, "mode": mode, "request": {"heat": False, "flow_c": 0, "reason": "idle"},
             "ha_entities": [], "rooms": rooms if rooms is not None else [
                 {"id": "woonkamer", "name": "Woonkamer", "state": "active", "status": "ok"},
                 {"id": "zolder", "name": "Zolder", "state": "inactive", "status": "inactive"}]}
    if burner is not None:
        value["burner"] = burner
    if active is not None:
        value["active"] = active
    return value


def setup(expect_telemetry=False):
    clock = Clock()
    hub = HeatingHub("fixture", clock=clock)
    return clock, hub, ProblemTracker(clock(), expect_telemetry=expect_telemetry)


def problems(tracker, hub, clock, advice=()):
    tracker.observe(hub, clock())
    return [key for key, _ in tracker.problems(hub, clock(), advice)]


def test_a_normal_day_has_no_problem():
    clock, hub, tracker = setup(expect_telemetry=True)
    hub.update(status(burner={"short_cycling": False}))
    for _ in range(10):
        clock.now += 30 * MIN
        hub.update(status(burner={"short_cycling": False}))
        assert problems(tracker, hub, clock) == []


def test_a_room_without_a_measurement_for_more_than_30_minutes():
    clock, hub, tracker = setup()
    lost = [{"id": "woonkamer", "name": "Woonkamer", "state": "active", "status": "stale"},
            {"id": "zolder", "name": "Zolder", "state": "inactive", "status": "inactive"}]
    hub.update(status(lost))
    assert problems(tracker, hub, clock) == []
    clock.now += ROOM_LOST_SECONDS - MIN
    lost[0]["status"] = "lost"  # the E32 itself calls it lost after 30 min
    hub.update(status(lost))
    assert problems(tracker, hub, clock) == []  # a short gap never raises it
    clock.now += 2 * MIN
    hub.update(status(lost))
    assert problems(tracker, hub, clock) == ["room_without_measurement"]
    found = tracker.problems(hub, clock())
    assert render(found, "en") == [TEXT["en"]["room_without_measurement"].format(room="Woonkamer")]
    assert render(found, "nl")[0].startswith("Woonkamer: al meer dan 30 minuten geen temperatuurmeting")
    # Measured again: gone at once. An inactive room never counts.
    lost[0]["status"] = "ok"
    hub.update(status(lost))
    assert problems(tracker, hub, clock) == []


def test_the_e32_silent_for_more_than_10_minutes():
    clock, hub, tracker = setup()
    assert problems(tracker, hub, clock) == []
    clock.now += TELEMETRY_STALE_SECONDS + MIN
    assert problems(tracker, hub, clock) == []  # never heard of an E32: no alarm
    hub.update(status())
    clock.now += 70
    hub.check_stale()  # four missed messages: the values go unavailable
    assert not hub.fresh and problems(tracker, hub, clock) == []
    clock.now += TELEMETRY_STALE_SECONDS
    assert problems(tracker, hub, clock) == ["e32_offline"]
    hub.update(status())
    assert problems(tracker, hub, clock) == []
    # With a stored E32 connection, an E32 that never reports after a restart counts too.
    clock, hub, tracker = setup(expect_telemetry=True)
    clock.now += TELEMETRY_STALE_SECONDS + MIN
    assert problems(tracker, hub, clock) == ["e32_offline"]


def test_pressure_advice_and_hours_of_short_cycling():
    clock, hub, tracker = setup()
    hub.update(status(burner={"short_cycling": True}))
    low = [{"id": "pressure_low", "values": {"pressure": 0.8}}]
    assert problems(tracker, hub, clock, low) == ["pressure_low"]
    assert render(tracker.problems(hub, clock(), low), "nl") == ["De waterdruk is laag (0,8 bar). Vul de "
                                                                 "cv-installatie bij."]
    clock.now += SHORT_CYCLING_SECONDS - MIN
    hub.update(status(burner={"short_cycling": True}))
    assert problems(tracker, hub, clock) == []
    clock.now += 2 * MIN
    hub.update(status(burner={"short_cycling": None}))  # unknown for a moment: the stretch goes on
    assert problems(tracker, hub, clock) == ["short_cycling"]
    hub.update(status(burner={"short_cycling": False}))
    assert problems(tracker, hub, clock) == []
    # Other advice (suggestions) is not a problem.
    assert problems(tracker, hub, clock, [{"id": "max_ch_high", "values": {}}]) == []


def test_active_control_warnings_count_only_in_active_mode():
    clock, hub, tracker = setup()
    active = {"state": "active", "warnings": ["foreign_controller", "boiler_limit_unknown"]}
    hub.update(status(mode="shadow", active=active))
    clock.now += ACTIVE_WARNING_SECONDS + MIN
    hub.update(status(mode="shadow", active=active))
    assert problems(tracker, hub, clock) == []  # shadow mode: the thermostat is in charge
    hub.update(status(mode="active", active=active))
    assert problems(tracker, hub, clock) == []
    clock.now += ACTIVE_WARNING_SECONDS + MIN
    hub.update(status(mode="active", active=active))
    assert problems(tracker, hub, clock) == ["active_foreign_controller"]
    hub.update(status(mode="active", active={"state": "active", "warnings": []}))
    assert problems(tracker, hub, clock) == []


def test_active_control_waiting_for_the_owners_confirmation_for_10_minutes():
    clock, hub, tracker = setup()
    waiting = {"state": "awaiting_confirmation", "awaiting_confirmation": True, "enabled": True,
               "confirmation": None, "warnings": []}
    hub.update(status(mode="active", active=waiting))
    assert problems(tracker, hub, clock) == []
    clock.now += AWAITING_CONFIRMATION_SECONDS - MIN
    hub.update(status(mode="active", active=waiting))
    assert problems(tracker, hub, clock) == []
    clock.now += MIN
    hub.update(status(mode="active", active=waiting))
    assert problems(tracker, hub, clock) == ["awaiting_confirmation"]
    found = tracker.problems(hub, clock())
    assert render(found, "en") == [
        "The E32 is waiting for you to confirm that the old thermostat is disconnected; it is not heating until "
        "you do. Open the E32 Rooms page → Active control."]
    assert render(found, "nl")[0].startswith("De E32 wacht tot je bevestigt dat de oude thermostaat is losgekoppeld")
    # Confirmed (active) or back to the thermostat (shadow): over at once, and the 10 minutes start again.
    hub.update(status(mode="active", active={"state": "active", "awaiting_confirmation": False, "warnings": []}))
    assert problems(tracker, hub, clock) == []
    hub.update(status(mode="active", active=waiting))
    clock.now += 5 * MIN
    assert problems(tracker, hub, clock) == []
    hub.update(status(mode="shadow", active={"state": "shadow", "awaiting_confirmation": False, "warnings": []}))
    assert problems(tracker, hub, clock) == []
    # The state alone counts too; shadow mode and firmware without the field never raise it.
    hub.update(status(mode="active", active={"state": "awaiting_confirmation", "warnings": []}))
    tracker.observe(hub, clock())
    clock.now += AWAITING_CONFIRMATION_SECONDS
    assert problems(tracker, hub, clock) == ["awaiting_confirmation"]
    hub.update(status())
    tracker.observe(hub, clock())
    clock.now += AWAITING_CONFIRMATION_SECONDS
    assert problems(tracker, hub, clock) == []
    # A hub that keeps the active-control block apart (``hub.active``) is read the same way.
    hub.update(status(mode="active"))
    hub.active = waiting
    tracker.observe(hub, clock())
    clock.now += AWAITING_CONFIRMATION_SECONDS
    assert problems(tracker, hub, clock) == ["awaiting_confirmation"]
    # While the E32 is silent only that is reported (its last confirmation state is not current).
    hub.update(None)
    assert "awaiting_confirmation" not in problems(tracker, hub, clock)


def test_every_reason_has_plain_english_and_dutch():
    assert set(TEXT["en"]) == set(TEXT["nl"])
    for key, text in TEXT["en"].items():
        assert "_" not in text and "0x" not in text, key


@pytest.mark.asyncio
async def test_the_sensor_is_a_problem_entity_with_reasons_for_an_automation(hass):
    from test_v1_native import entry
    e = entry(hass)
    clock = Clock()
    hub = HeatingHub("fixture", clock=clock)
    advice = SimpleNamespace(items=[{"id": "pressure_high", "values": {"pressure": 2.9}}])
    hass.data.setdefault("open_thermostat", {})[e.entry_id] = {"heating_hub": hub, "heating_advice": advice}
    sensor = HeatingProblemSensor(e, hub)
    sensor.hass = hass
    assert sensor.unique_id == "fixture_hub_heating_problem" and sensor.device_class == "problem"
    assert sensor.device_info["identifiers"] == {("open_thermostat", "fixture")}  # the product device
    sensor.evaluate()
    assert sensor.is_on is True
    hass.config.language = "en"
    attributes = sensor.extra_state_attributes
    assert attributes["problems"] == ["pressure_high"]
    assert attributes["reasons"] == ["The water pressure is high (2.9 bar). Have the expansion vessel checked."]
    hass.config.language = "nl"
    assert sensor.extra_state_attributes["reasons"][0].startswith("De waterdruk is hoog (2,9 bar)")
    advice.items = []
    sensor.evaluate()
    assert sensor.is_on is False and sensor.extra_state_attributes == {"problems": [], "reasons": [], "rooms": []}
    assert "reasons" in sensor._unrecorded_attributes


def test_the_notification_blueprint_is_a_valid_automation_blueprint():
    from pathlib import Path
    from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
    from homeassistant.components.blueprint.models import Blueprint
    from homeassistant.util import yaml as yaml_util
    path = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat/blueprints/heating_problem.yaml"
    blueprint = Blueprint(yaml_util.load_yaml(path), expected_domain="automation", schema=AUTOMATION_BLUEPRINT_SCHEMA)
    assert set(blueprint.inputs) == {"problem", "delay", "notify_when_solved", "notification"}
    raw = yaml_util.load_yaml(path)["blueprint"]["input"]["problem"]["selector"]["entity"]["filter"]
    assert raw == {"integration": "open_thermostat", "domain": "binary_sensor", "device_class": "problem"}
    text = path.read_text(encoding="utf-8")
    assert "state_attr(problem, 'reasons')" in text  # the plain-language reasons of the sensor
    assert "old thermostat is disconnected" in text  # awaiting_confirmation is in its description
