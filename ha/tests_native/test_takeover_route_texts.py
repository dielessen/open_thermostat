"""E32 rc.2 onboarding texts: a new plan's route follows the boiler bus, and nothing is sent before the takeover.

A trial run beside an old thermostat that still asks the boiler, otherwise straight to the guided boiler
test; the owner can always choose the other route on the E32 Rooms page (EN/NL/PL).
"""
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "config" / "custom_components" / "open_thermostat"
WORDS = {
    "strings.json": ("trial run beside it", "boiler test", "sends nothing to the boiler until you say so", "boiler"),
    "translations/en.json": ("trial run beside it", "boiler test", "sends nothing to the boiler until you say so", "boiler"),
    "translations/nl.json": ("proefrun ernaast", "keteltest", "stuurt niets naar de ketel", "ketel"),
    "translations/pl.json": ("próbę obok niego", "test kotła", "nie wysyła nic do kotła", "kotłem"),
}


@pytest.mark.parametrize("name", sorted(WORDS))
def test_the_setup_says_which_route_a_new_e32_takes(name):
    step = json.loads((BASE / name).read_text(encoding="utf-8"))["config"]["step"]
    user, shadow = step["user"]["description"], step["shadow"]["description"]
    trial, test, nothing, boiler = WORDS[name]
    # First run: short and calm; the route words live on the E32 step, the trial run only beside an old thermostat.
    assert boiler in user and len(user) < 140, user
    assert trial in shadow and test in shadow and nothing in shadow, shadow
    assert "Rooms" in shadow or "Ruimtes" in shadow or "Pomieszczenia" in shadow
    for old in ("calculates along; your current thermostat keeps controlling the boiler until you switch over",
                "rekent de E32 mee; je huidige thermostaat blijft de ketel regelen tot je overstapt",
                "During the trial run the E32 only calculates", "Tijdens de proefperiode rekent de E32 alleen"):
        assert old not in user and old not in shadow


# rc.3: an installation never needs a thermostat on the bus, so no text takes one for granted.
PRESUMED = {
    "strings.json": ("your old thermostat", "the old thermostat is", "back to the thermostat", "to my thermostat"),
    "translations/en.json": ("your old thermostat", "the old thermostat is", "back to the thermostat",
                             "to my thermostat"),
    "translations/nl.json": ("je oude thermostaat", "de oude thermostaat is", "terug aan de thermostaat",
                             "aan mijn thermostaat"),
    "translations/pl.json": ("stary termostat jest", "staremu termostatowi", "sterowanie termostatowi",
                             "to my thermostat"),
}


@pytest.mark.parametrize("name", sorted(PRESUMED))
def test_no_text_presumes_an_old_thermostat(name):
    issues = json.loads((BASE / name).read_text(encoding="utf-8"))["issues"]
    # The thermostat words only where the E32 heard one on the bus (rc.3 active.thermostat_seen).
    neutral = json.loads((BASE / name).read_text(encoding="utf-8"))
    del neutral["issues"]["reconfirm_takeover_thermostat"]
    text = json.dumps(neutral, ensure_ascii=False)
    assert [phrase for phrase in PRESUMED[name] if phrase in text] == []
    confirm = issues["reconfirm_takeover"]["fix_flow"]["step"]["reconfirm_takeover"]["description"]
    # The safety rule stays: never two thermostats on the boiler.
    assert {"strings.json": "never connect two thermostats", "translations/en.json": "never connect two thermostats",
            "translations/nl.json": "sluit nooit twee thermostaten",
            "translations/pl.json": "nigdy nie podłączaj dwóch termostatów"}[name] in confirm


def test_the_hot_water_advice_does_not_presume_a_thermostat():
    from custom_components.open_thermostat.heating_advice import TEXT
    for language, phrase in (("en", "your thermostat"), ("nl", "je thermostaat"), ("pl", "w termostacie.")):
        assert phrase not in json.dumps(TEXT[language], ensure_ascii=False), language


def test_the_dashboard_shows_the_next_step_before_the_takeover():
    from custom_components.open_thermostat.dashboard import TEXT
    assert TEXT["en"]["next"].startswith("Next step: run the boiler test and confirm the takeover")
    assert TEXT["nl"]["next"].startswith("Volgende stap: doe de keteltest en bevestig de overname")


def test_the_boiler_request_names_the_active_control_state():
    """``control`` on the boiler request sensor: the dashboard tells awaiting_confirmation from real control."""
    from custom_components.open_thermostat.heating_link import HeatingHub, HeatRequestSensor
    hub = HeatingHub("fixture", clock=lambda: 1000.0)
    status = {"schema": 1, "revision": 1, "mode": "active", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
              "ha_entities": [], "rooms": [], "active": {"state": "awaiting_confirmation", "warnings": []}}
    hub.update(status)
    sensor = HeatRequestSensor(hub)
    assert sensor.extra_state_attributes["control"] == "awaiting_confirmation"
    hub.update({**status, "active": None})
    assert sensor.extra_state_attributes["control"] is None
