"""Ready to take over? The E32's readiness check as one Home Assistant sensor."""
import json
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.takeover_readiness import OUTAGE_SECONDS, evaluate, readiness_status
from test_heating_link import FULL, _setup

COMPONENT = Path(__file__).resolve().parents[1] / "config" / "custom_components" / "open_thermostat"
NOW = 1_793_000_000.0
# TakeoverReadiness::json() for the owner's shadow period (1 Nov 2026): waiting, nothing failed.
OWNER = {"state": "waiting", "comparison": True,
         "stable": {"result": "wait", "s": 182160, "restart": "planned"},
         "periods": {"result": "wait", "thermostat": 9, "night_setbacks": 2, "morning_warmups": 1, "no_demand": 3},
         "timing": {"result": "wait", "events": 18, "matched": 18, "within_5min": 16, "within_15min": 18},
         "flow": {"result": "pass", "max_c": 54, "limit_c": 60, "over": 0, "request_s": 41000},
         "cycling": {"result": "wait", "e32": 9, "thermostat": 9},
         "sources": {"result": "pass", "rooms": 1, "working": 1, "backup": 1, "fallback_seen": True}}
PASSED = {**{k: ({**v, "result": "pass"} if type(v) is dict else v) for k, v in OWNER.items()},
          "state": "ready", "stable": {"result": "pass", "s": 300000, "restart": "planned"}}
ALONE = {"state": "waiting", "comparison": False,
         "stable": {"result": "wait", "s": 3600, "restart": "first"},
         "sources": {"result": "pass", "rooms": 2, "working": 2, "backup": 1, "fallback_seen": True},
         "boiler": {"result": "pass", "age_s": 12},
         "boiler_limit": {"result": "fail", "limit_c": None}}


def test_the_owners_period_is_waiting_with_every_criterion_as_an_attribute():
    state, attributes = evaluate(OWNER, now=NOW)
    assert state == "waiting"
    assert attributes == {
        "comparison": True,
        "stable": "wait", "stable_hours": 50.6, "last_outage_end": None, "stable_hours_needed": 72,
        "last_restart": "planned",
        "periods": "wait", "periods_needed": 10, "periods_compared": 9, "night_setbacks": 2, "morning_warmups": 1,
        "no_demand_periods": 3,
        "timing": "wait", "timing_events_needed": 20, "timing_events": 18, "timing_matched": 18,
        "timing_within_5min": 16, "timing_within_15min": 18,
        "flow_limit": "pass", "flow_max_c": 54, "flow_limit_c": 60, "flow_over_limit": 0,
        "cycling": "wait", "heating_periods_e32": 9, "heating_periods_thermostat": 9,
        "sources": "pass", "rooms": 1, "rooms_working": 1, "rooms_with_fallback_source": 1, "fallback_seen": True}


def test_ready_only_when_all_pass_and_not_ready_with_any_failure():
    assert evaluate(PASSED, now=NOW)[0] == "ready"
    for key in ("periods", "timing", "flow", "cycling", "sources"):
        assert evaluate({**PASSED, key: {**PASSED[key], "result": "fail"}}, now=NOW)[0] == "not_ready", key
        assert evaluate({**PASSED, key: {**PASSED[key], "result": "wait"}}, now=NOW)[0] == "waiting", key
    assert evaluate({**OWNER, "flow": {**OWNER["flow"], "result": "fail", "over": 1}}, now=NOW)[0] == "not_ready"
    # Taken over: nothing to judge.
    assert evaluate({"state": "not_applicable"}, now=NOW) == ("not_applicable", None)
    assert evaluate(None) == (None, None)
    # A criterion of an unknown shape is skipped; none left is no verdict.
    assert evaluate({"state": "waiting", "stable": {"result": "maybe"}}, now=NOW) == (None, None)


def test_a_home_without_a_thermostat_lists_the_e32_and_the_boiler_only():
    state, attributes = evaluate(ALONE, now=NOW)
    assert state == "not_ready"
    assert attributes["comparison"] is False
    assert [k for k in ("stable", "periods", "timing", "flow_limit", "cycling", "sources", "boiler", "boiler_limit")
            if k in attributes] == ["stable", "sources", "boiler", "boiler_limit"]
    assert attributes["boiler_heard_age_s"] == 12 and attributes["boiler_limit_c"] is None


def test_an_outage_seen_by_home_assistant_restarts_the_72_hours():
    state, attributes = evaluate(PASSED, outage_end=NOW - 10 * 3600, now=NOW)
    assert state == "waiting"
    assert attributes["stable"] == "wait" and attributes["stable_hours"] == 10.0
    assert attributes["last_outage_end"] == "2026-10-25T21:33+00:00"
    # Long enough ago: the E32's own time counts again.
    assert evaluate(PASSED, outage_end=NOW - 90 * 3600, now=NOW)[1]["stable_hours"] == 83.3


@pytest.mark.asyncio
async def test_the_sensor_follows_the_e32_and_remembers_an_outage(hass, monkeypatch):
    from homeassistant.components.sensor import SensorDeviceClass
    from custom_components.open_thermostat import heating_link as module
    entry, hub, added, send = await _setup(hass, monkeypatch)
    send(FULL)
    assert not any(e.unique_id == "fixture_hub_takeover_readiness" for e in added)  # older firmware: none
    assert readiness_status(hub.status) is None
    send({**FULL, "readiness": PASSED})
    sensor = next(e for e in added if e.unique_id == "fixture_hub_takeover_readiness")
    assert sensor.translation_key == "takeover_readiness" and sensor.device_class == SensorDeviceClass.ENUM
    assert sensor.options == ["ready", "waiting", "not_ready", "not_applicable"]
    assert sensor.device_info["identifiers"] == {("open_thermostat", "fixture")}
    wall = [NOW]
    sensor._wall = lambda: wall[0]
    assert sensor.available and sensor.native_value == "ready"
    assert sensor.extra_state_attributes["stable_hours"] == 83.3
    # The E32 silent: unavailable; heard again after more than 5 minutes: the 72 hours start again.
    mono = [hub.received]
    hub.clock = lambda: mono[0]
    mono[0] += module.STALE_SECONDS + 1
    wall[0] += module.STALE_SECONDS + 1
    hub.check_stale()
    sensor.track()
    assert not sensor.available
    wall[0] += OUTAGE_SECONDS
    mono[0] += OUTAGE_SECONDS
    send({**FULL, "readiness": PASSED})
    sensor.track()
    assert sensor.native_value == "waiting"
    assert sensor.extra_state_attributes["stable_hours"] == 0.0
    assert sensor.extra_state_attributes["last_outage_end"] is not None
    # A short gap (a planned restart) does not count.
    end = sensor._outage_end
    hub.update(None); sensor.track()
    wall[0] += 60
    send({**FULL, "readiness": PASSED}); sensor.track()
    assert sensor._outage_end == end
    # Taken over: not applicable.
    send({**FULL, "readiness": {"state": "not_applicable"}})
    assert sensor.native_value == "not_applicable" and sensor.extra_state_attributes is None


def test_the_sensor_is_translated():
    names, states = {}, {}
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        sensor = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["entity"]["sensor"]["takeover_readiness"]
        names[name], states[name] = sensor["name"], sensor["state"]
    assert (COMPONENT / "strings.json").read_bytes() == (COMPONENT / "translations/en.json").read_bytes()
    assert names == {"strings.json": "Ready for E32 control", "translations/en.json": "Ready for E32 control",
                     "translations/nl.json": "Klaar voor regeling door de E32", "translations/pl.json": "Gotowość do sterowania przez E32"}
    assert states["strings.json"] == {"ready": "Ready", "waiting": "Waiting for more data", "not_ready": "Not ready",
                                      "not_applicable": "Not applicable"}
    assert states["translations/nl.json"]["waiting"] == "Wacht op meer gegevens"
    assert all(set(s) == {"ready", "waiting", "not_ready", "not_applicable"} for s in states.values())
    icons = json.loads((COMPONENT / "icons.json").read_text(encoding="utf-8"))["entity"]["sensor"]["takeover_readiness"]
    assert set(icons["state"]) == set(states["strings.json"])


@pytest.mark.asyncio
async def test_the_dashboard_shows_the_check_next_to_the_comparison(hass):
    from custom_components.open_thermostat.dashboard import RoomDashboard
    from test_dashboard_heating import installation
    e, rooms, sensors, hub, fields = installation(hass)
    readiness = er.async_get(hass).async_get_or_create(
        "sensor", "open_thermostat", "fixture_hub_takeover_readiness", config_entry=e,
        suggested_object_id="fixture_hub_takeover_readiness").entity_id
    dashboard = RoomDashboard(hass, "fixture", e.entry_id)
    config = dashboard._dashboard_config()
    learning = next(v for v in config["views"] if v["path"] == "learned")
    comparison = next(v for v in config["views"] if v["path"] == "comparison")
    hidden = [{"condition": "state", "entity": readiness, "state_not": ["unavailable", "unknown", "not_applicable"]}]
    tile = next(c for s in learning["sections"] for c in s["cards"] if c.get("entity") == readiness)
    assert tile["name"] == "Ready to take over?" and tile["visibility"] == hidden
    assert tile["tap_action"] == {"action": "navigate", "navigation_path": "/" + dashboard.path + "/comparison"}
    check = comparison["sections"][0]["cards"]
    assert check[0]["heading"] == "Ready to take over?" and check[0]["visibility"] == hidden
    assert comparison["sections"][1]["cards"][0]["heading"] == "E32 and thermostat"  # the comparison follows
    card = check[1]
    assert card["type"] == "markdown" and card["visibility"] == hidden
    for text in ("Ready: follow the switch-over steps.", "state_attr(" + json.dumps(readiness) + ", 'stable_hours')",
                 "of {{ state_attr(" + json.dumps(readiness) + ", 'periods_needed') }}", "check the bus cable"):
        assert text in card["content"], text
    # In Dutch.
    hass.config.language = "nl"
    dutch = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][-1]["sections"][0]["cards"]
    assert dutch[0]["heading"] == "Klaar om over te nemen?"
    assert "Klaar: volg de stappen voor de overschakeling." in dutch[1]["content"]


def test_the_guided_boiler_test_is_shown_in_every_state():
    """E32 rc.2: the boiler test's result comes with the readiness, also in active mode (not_applicable)."""
    steps = {"disconnect": "pass", "confirm": "pass", "start": "pass", "hot_water": "skipped", "stop": "pass"}
    passed = {"state": "passed", "at": 1762077600, "steps": steps, "reason": None}
    state, attributes = evaluate({"state": "not_applicable", "takeover_test": passed}, now=NOW)
    assert state == "not_applicable"
    assert attributes == {"boiler_test": "passed", "boiler_test_at": "2025-11-02T10:00+00:00", "boiler_test_steps": steps,
                          "boiler_test_step": None, "boiler_test_reason": None,
                          # rc.2 firmware: no summary, flow or mark (the summary follows the state)
                          "boiler_test_summary": "passed", "boiler_test_flow_c": None, "boiler_test_marked_at": None}
    running = {"state": "running", "at": None, "reason": None, "step": "start", "phase": "waiting_burner",
               "steps": {"disconnect": "pass", "confirm": "pass", "start": "wait", "hot_water": "not_run", "stop": "x"}}
    _, attributes = evaluate({"state": "not_applicable", "takeover_test": running}, now=NOW)
    assert attributes["boiler_test"] == "running" and attributes["boiler_test_step"] == "start"
    assert attributes["boiler_test_at"] is None
    assert attributes["boiler_test_steps"]["stop"] == "not_run"  # an unknown result is not passed on
    # The trial run (shadow) lists it beside the criteria; a failure keeps its reason.
    failed = {"state": "stopped", "at": 0, "steps": {**steps, "hot_water": "fail"}, "reason": "foreign_controller"}
    state, attributes = evaluate({**OWNER, "takeover_test": failed}, now=NOW)
    assert state == "waiting"
    assert attributes["boiler_test"] == "stopped" and attributes["boiler_test_reason"] == "foreign_controller"
    assert attributes["periods"] == "wait"
    # Firmware without the test: nothing new, active mode keeps no attributes.
    assert evaluate({"state": "not_applicable"}, now=NOW) == ("not_applicable", None)
    assert "boiler_test" not in evaluate(OWNER, now=NOW)[1]
    assert evaluate({"state": "not_applicable", "takeover_test": {"state": "bogus"}}, now=NOW) == ("not_applicable", None)


def test_the_one_boiler_test_remembers_itself():
    """E32 rc.3: the kept result with the flow used, the owner's mark (never a pass) and "not needed"."""
    steps = {"disconnect": "pass", "confirm": "pass", "start": "pass", "hot_water": "pass", "stop": "pass"}
    passed = {"state": "passed", "at": 1762029120, "steps": steps, "reason": None, "summary": "passed", "flow_c": 52,
              "marked": False, "marked_at": None}
    _, attributes = evaluate({"state": "not_applicable", "takeover_test": passed}, now=NOW)
    assert attributes["boiler_test_summary"] == "passed" and attributes["boiler_test_flow_c"] == 52
    assert attributes["boiler_test_at"] == "2025-11-01T20:32+00:00" and attributes["boiler_test_marked_at"] is None
    idle = {"state": "idle", "at": None, "steps": {}, "reason": None, "flow_c": None}
    marked = {**idle, "summary": "marked", "marked": True, "marked_at": 1762180000}
    _, attributes = evaluate({"state": "not_applicable", "takeover_test": marked}, now=NOW)
    assert attributes["boiler_test"] == "idle"  # a mark is no measured pass
    assert attributes["boiler_test_summary"] == "marked" and attributes["boiler_test_marked_at"] == "2025-11-03T14:26+00:00"
    assert set(attributes["boiler_test_steps"].values()) == {"not_run"}
    for summary in ("not_needed", "never"):
        _, attributes = evaluate({"state": "not_applicable", "takeover_test": {**idle, "summary": summary, "marked": False}}, now=NOW)
        assert attributes["boiler_test_summary"] == summary and attributes["boiler_test_marked_at"] is None
    # A restart during the test: stopped, its reason kept.
    restarted = {"state": "stopped", "at": 1762029120, "steps": {**steps, "confirm": "fail"}, "reason": "e32_restarted",
                 "summary": "stopped", "flow_c": None, "marked": False, "marked_at": None}
    _, attributes = evaluate({"state": "not_applicable", "takeover_test": restarted}, now=NOW)
    assert attributes["boiler_test_summary"] == "stopped" and attributes["boiler_test_reason"] == "e32_restarted"
    # Unknown or implausible values are not passed on.
    _, attributes = evaluate({"state": "not_applicable", "takeover_test": {**passed, "summary": "great", "flow_c": 200,
                                                                          "marked_at": 1762180000}}, now=NOW)
    assert attributes["boiler_test_summary"] == "passed" and attributes["boiler_test_flow_c"] is None
    assert attributes["boiler_test_marked_at"] is None  # not marked
    _, attributes = evaluate({"state": "not_applicable", "takeover_test": {**idle}}, now=NOW)
    assert attributes["boiler_test_summary"] == "never"
