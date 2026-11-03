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
    # E32 rc.3: no old thermostat in the words unless the E32 ever heard another controller.
    assert render(found, "en") == [
        "The E32 is waiting for you to confirm that it may control the boiler; it is not heating until you do. "
        "Open the E32 Rooms page → Active control."]
    assert render(found, "nl")[0].startswith("De E32 wacht tot je bevestigt dat hij de ketel mag regelen")
    assert render(found, "pl")[0].startswith("E32 czeka, aż potwierdzisz, że może sterować kotłem")
    for lang in ("en", "nl", "pl"):
        assert "thermostat" not in render(found, lang)[0] and "termostat" not in render(found, lang)[0]
    hub.update(status(mode="active", active={**waiting, "thermostat_seen": True}))
    assert problems(tracker, hub, clock) == ["awaiting_confirmation"]  # the same problem id for automations
    found = tracker.problems(hub, clock())
    assert render(found, "en") == [
        "The E32 is waiting for you to confirm that the old thermostat is disconnected; it is not heating until "
        "you do. Open the E32 Rooms page → Active control."]
    assert render(found, "nl")[0].startswith("De E32 wacht tot je bevestigt dat de oude thermostaat is losgekoppeld")
    assert render(found, "pl")[0].startswith("E32 czeka, aż potwierdzisz, że stary termostat jest odłączony")
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
    assert "no other thermostat is connected" in text  # awaiting_confirmation is in its description


# -- 1.0: a room that does not get warm, a lost session and the Repairs issues -----------------------------

def warm_room(temperature, setpoint=21.0, demand=True, status="ok", **extra):
    return [{"id": "woonkamer", "name": "Woonkamer", "state": "active", "status": status, "demand": demand,
             "temperature": temperature, "setpoint": setpoint, **extra}]


def test_a_room_that_asks_for_heat_but_stays_cold_for_3_hours():
    from custom_components.open_thermostat.heating_problem import ROOM_SLOW_SECONDS
    clock, hub, tracker = setup()
    hub.update(status(warm_room(19.0)))
    assert problems(tracker, hub, clock) == []
    clock.now += ROOM_SLOW_SECONDS - MIN
    hub.update(status(warm_room(19.5)))
    assert problems(tracker, hub, clock) == []          # not yet 3 hours
    clock.now += 2 * MIN
    hub.update(status(warm_room(19.6)))
    assert problems(tracker, hub, clock) == ["room_slow"]
    reason = render(tracker.problems(hub, clock()), "en")[0]
    assert reason.startswith("Woonkamer asks for heat but has stayed more than 0.5 °C below its target for 3 hours")
    assert render(tracker.problems(hub, clock()), "nl")[0].startswith("Woonkamer vraagt warmte, maar blijft al 3 uur")
    # Warm enough (within 0.5 °C): gone at once.
    hub.update(status(warm_room(20.6)))
    assert problems(tracker, hub, clock) == []


def test_a_cold_room_never_warns_across_a_gap_an_open_window_or_without_demand():
    from custom_components.open_thermostat.heating_problem import ROOM_SLOW_SECONDS
    clock, hub, tracker = setup()
    hub.update(status(warm_room(18.0)))
    problems(tracker, hub, clock)
    clock.now += ROOM_SLOW_SECONDS / 2
    hub.check_stale()                                   # the E32 goes quiet: the wait starts again
    assert not hub.fresh and 'room_slow' not in problems(tracker, hub, clock)  # only e32_offline
    hub.update(status(warm_room(18.0)))
    problems(tracker, hub, clock)
    clock.now += ROOM_SLOW_SECONDS / 2 + MIN
    hub.update(status(warm_room(18.0)))
    assert problems(tracker, hub, clock) == []          # 1.5 h + 1.5 h, never 3 h in one stretch
    for rooms in (warm_room(18.0, comfort={"window": "open"}), warm_room(18.0, demand=False),
                  warm_room(18.0, status="inactive")):
        clock, hub, tracker = setup()
        hub.update(status(rooms))
        problems(tracker, hub, clock)
        clock.now += ROOM_SLOW_SECONDS + MIN
        hub.update(status(rooms))
        assert problems(tracker, hub, clock) == []


def test_a_lost_session_while_the_e32_is_online():
    from custom_components.open_thermostat.heating_problem import SESSION_LOST_SECONDS
    clock, hub, tracker = setup()
    hub.update(status())
    tracker.observe(hub, clock(), session_ready=False)
    assert [k for k, _ in tracker.problems(hub, clock())] == []
    clock.now += SESSION_LOST_SECONDS
    hub.update(status())
    tracker.observe(hub, clock(), session_ready=False)
    assert [k for k, _ in tracker.problems(hub, clock())] == ["session_lost"]
    assert "more than 15 minutes" in render(tracker.problems(hub, clock()), "en")[0]
    tracker.observe(hub, clock(), session_ready=True)
    assert tracker.problems(hub, clock()) == []
    # Shadow link switched off (None): never a problem.
    clock.now += 2 * SESSION_LOST_SECONDS
    hub.update(status())
    tracker.observe(hub, clock(), session_ready=None)
    assert tracker.problems(hub, clock()) == []


def test_every_problem_but_the_pressure_becomes_one_repairs_issue_per_room():
    from custom_components.open_thermostat.heating_problem import issues
    found = [("pressure_low", {"pressure": 0.8}), ("room_slow", {"room": "Woonkamer", "room_id": "woonkamer",
                                                                  "hours": 3, "margin": 0.5}),
             ("e32_offline", {})]
    result = issues(found, "nl")
    assert set(result) == {"room_slow_woonkamer", "e32_offline"}  # the pressure has its own issue already
    key, placeholders = result["room_slow_woonkamer"]
    assert key == "heating_problem" and placeholders["reason"].startswith("Woonkamer vraagt warmte")


@pytest.mark.asyncio
async def test_repairs_issues_appear_and_clear_with_the_problems(hass):
    from homeassistant.helpers import issue_registry as ir
    from custom_components.open_thermostat.issue_sync import clear_issues, sync_issues
    registry = ir.async_get(hass)
    sync_issues(hass, "e1", "heating_problem", {"room_slow_woonkamer": ("heating_problem", {"reason": "cold"}),
                                                 "e32_offline": ("heating_problem", {"reason": "quiet"})})
    assert registry.async_get_issue("open_thermostat", "heating_problem_room_slow_woonkamer_e1") is not None
    sync_issues(hass, "e1", "heating_problem", {"e32_offline": ("heating_problem", {"reason": "quiet"})})
    assert registry.async_get_issue("open_thermostat", "heating_problem_room_slow_woonkamer_e1") is None
    issue = registry.async_get_issue("open_thermostat", "heating_problem_e32_offline_e1")
    assert issue.translation_key == "heating_problem" and issue.translation_placeholders == {"reason": "quiet"}
    # Another group (for example radiator valves) is left alone; clearing one group clears only it.
    sync_issues(hass, "e1", "trv", {"battery_bad": ("heating_problem", {"reason": "battery"})})
    clear_issues(hass, "e1", "heating_problem")
    assert registry.async_get_issue("open_thermostat", "heating_problem_e32_offline_e1") is None
    assert registry.async_get_issue("open_thermostat", "trv_battery_bad_e1") is not None


@pytest.mark.asyncio
async def test_the_sensor_raises_and_clears_a_repairs_issue(hass):
    from homeassistant.helpers import issue_registry as ir
    from custom_components.open_thermostat.heating_problem import ROOM_SLOW_SECONDS
    from test_v1_native import entry
    e = entry(hass)
    clock = Clock()
    hub = HeatingHub("fixture", clock=clock)
    hass.data.setdefault("open_thermostat", {})[e.entry_id] = {"heating_hub": hub}
    sensor = HeatingProblemSensor(e, hub)
    sensor.hass, sensor.entity_id = hass, "binary_sensor.heating_problem"
    sensor.async_write_ha_state = lambda: None
    hub.update(status(warm_room(18.0)))
    sensor.evaluate()
    clock.now += ROOM_SLOW_SECONDS + MIN
    hub.update(status(warm_room(18.0)))
    sensor.evaluate()
    issue_id = f"heating_problem_room_slow_woonkamer_{e.entry_id}"
    assert ir.async_get(hass).async_get_issue("open_thermostat", issue_id) is not None
    hub.update(status(warm_room(21.0)))
    sensor.evaluate()
    assert ir.async_get(hass).async_get_issue("open_thermostat", issue_id) is None


def test_the_repairs_texts_exist_in_every_language():
    import json
    from pathlib import Path
    base = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        issue = json.loads((base / name).read_text(encoding="utf-8"))["issues"]["heating_problem"]
        assert set(issue) == {"title", "description"} and "{reason}" in issue["description"], name


def test_a_new_installation_waiting_for_its_first_takeover_is_no_problem():
    """E32 rc.2: a new plan starts active; before the first takeover the confirmation is the next step, not an alarm."""
    clock, hub, tracker = setup(expect_telemetry=True)
    new = {"state": "awaiting_confirmation", "awaiting_confirmation": True, "reconfirm_required": False, "enabled": True,
           "confirmation": None, "warnings": [], "taken_over_before": False}
    hub.update(status(mode="active", active=new))
    for _ in range(6):
        clock.now += AWAITING_CONFIRMATION_SECONDS
        hub.update(status(mode="active", active=new))
        assert problems(tracker, hub, clock) == []
    # An installation the E32 controlled before stays a real problem after 10 minutes of waiting.
    was = {**new, "taken_over_before": True}
    hub.update(status(mode="active", active=was))
    assert problems(tracker, hub, clock) == []
    clock.now += AWAITING_CONFIRMATION_SECONDS
    hub.update(status(mode="active", active=was))
    assert problems(tracker, hub, clock) == ["awaiting_confirmation"]
    # After a firmware update (reconfirm) it is never a first takeover, whatever the flag says.
    clock2, hub2, tracker2 = setup()
    update = {**new, "reconfirm_required": True}
    hub2.update(status(mode="active", active=update))
    tracker2.observe(hub2, clock2())
    clock2.now += AWAITING_CONFIRMATION_SECONDS
    assert problems(tracker2, hub2, clock2) == ["awaiting_confirmation"]
    # Firmware before rc.2 (no flag): as before.
    clock3, hub3, tracker3 = setup()
    older = {k: v for k, v in new.items() if k != "taken_over_before"}
    hub3.update(status(mode="active", active=older))
    tracker3.observe(hub3, clock3())
    clock3.now += AWAITING_CONFIRMATION_SECONDS
    assert problems(tracker3, hub3, clock3) == ["awaiting_confirmation"]
