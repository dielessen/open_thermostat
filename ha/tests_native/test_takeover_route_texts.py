"""E32 rc.2 onboarding texts: a new plan's route follows the boiler bus, and nothing is sent before the takeover.

A trial run beside an old thermostat that still asks the boiler, otherwise straight to the guided boiler
test; the owner can always choose the other route on the E32 Rooms page (EN/NL/PL).
"""
import json
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "config" / "custom_components" / "open_thermostat"
WORDS = {
    "strings.json": ("trial run beside it", "boiler test", "sends nothing to the boiler until you confirm"),
    "translations/en.json": ("trial run beside it", "boiler test", "sends nothing to the boiler until you confirm"),
    "translations/nl.json": ("proefperiode mee", "keteltest", "stuurt niets naar de ketel tot je bevestigt"),
    "translations/pl.json": ("w okresie próbnym", "test", "Nic nie wysyła do kotła"),
}


@pytest.mark.parametrize("name", sorted(WORDS))
def test_the_setup_says_which_route_a_new_e32_takes(name):
    step = json.loads((BASE / name).read_text(encoding="utf-8"))["config"]["step"]
    user, shadow = step["user"]["description"], step["shadow"]["description"]
    trial, test, nothing = WORDS[name]
    assert trial in user and test in user and nothing in user, user
    # The E32 step: the takeover on the E32 page, the trial run only beside an old thermostat.
    assert "Rooms" in shadow or "Ruimtes" in shadow
    for old in ("calculates along; your current thermostat keeps controlling the boiler until you switch over",
                "rekent de E32 mee; je huidige thermostaat blijft de ketel regelen tot je overstapt",
                "During the trial run the E32 only calculates", "Tijdens de proefperiode rekent de E32 alleen"):
        assert old not in user and old not in shadow


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
