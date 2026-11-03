"""Everything this integration lets a user write has a place in Configure (Settings -> Devices & services ->
OpenThermostat -> Configure): "otherwise you search yourself silly". The entities on the E32 device and the
dashboard stay as quick controls; the same setting is a step (or a field of a step) in Configure.

The test walks every writable entity class of the integration (select, number, switch, datetime, text, button),
by its translation key, and checks that its Configure step exists, is offered in a menu and has a title in every
language. A new writable entity fails this test until it is mapped here or put on the allow-list with a reason.
"""
import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
LANGUAGES = ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json")

# entity class -> (platform, translation key / unique-id kind)
WRITABLE_CLASSES = {
    "FlowOptionSwitch": ("switch", "flow_weather_curve"),   # also flow_apply_learned (same class, two keys)
    "FlowDesignSelect": ("select", "flow_curve_design_flow_c"),
    "HouseModeSelect": ("select", "house_mode"),
    "HolidayUntil": ("datetime", "holiday_until"),
    "AwayTemperature": ("number", "away_temperature"),
    "RoomStateSelect": ("select", "room_state"),
    "RoomInactiveUntil": ("datetime", "room_inactive_until"),
    "RoomFallbackSetpoint": ("number", "room_fallback_setpoint"),
    "ValveControlSwitch": ("switch", "room_valve_control"),
    "E32BackupButton": ("button", "e32_backup_now"),
    "E32RestartButton": ("button", "e32_restart"),
    "RadiatorPower": ("number", "radiator_rated_power"),
    "OverrideDuration": ("number", None),
}

# (platform, translation key) -> the Configure step that sets it (a field of that step).
CONFIGURE_STEP = {
    ("switch", "flow_weather_curve"): "heating_weather",
    ("switch", "flow_apply_learned"): "heating_warm_up",
    ("select", "flow_curve_design_flow_c"): "heating_weather",      # under Advanced in that step
    ("select", "house_mode"): "house_mode",
    ("datetime", "holiday_until"): "house_mode",
    ("number", "away_temperature"): "house_presence",
    ("select", "room_state"): "e32_room",
    ("datetime", "room_inactive_until"): "e32_room",
    ("number", "room_fallback_setpoint"): "e32_room",
    ("switch", "room_valve_control"): "e32_room",                    # the Radiator valves section
}

# Real exceptions, each with its reason.
ALLOWED_WITHOUT_STEP = {
    ("button", "e32_backup_now"): "one-shot action; the backups themselves are restored under Advanced",
    ("button", "e32_restart"): "one-shot action",
    ("number", "radiator_rated_power"): "only the older Home Assistant rooms (ib-therm route), no E32 room plan",
    ("number", None): "only the older Home Assistant rooms (ib-therm route): temperature override duration",
}

# Where a step is offered: its menu (Configure -> ... ), or the room list for the room form.
OFFERED_IN = {"heating_weather": "heating_boiler", "heating_warm_up": "heating_boiler", "house_mode": "house",
              "house_presence": "house", "e32_room": "e32_rooms"}


def classes():
    found = {}
    for path in COMPONENT.glob("*.py"):
        for name, bases in re.findall(r"^class (\w+)\(([^)]*)\)", path.read_text(encoding="utf-8"), re.M):
            if re.search(r"\b(Select|Number|Switch|Button|Text|DateTime)Entity\b", bases):
                found[name] = path.name
    return found


def test_every_writable_entity_class_is_known():
    assert set(classes()) == set(WRITABLE_CLASSES), "a writable entity class was added or removed: map it above"


@pytest.mark.parametrize("filename", LANGUAGES)
def test_every_writable_entity_has_a_configure_step(filename):
    from custom_components.open_thermostat.product_flow import ProductOptionsFlow
    document = json.loads((COMPONENT / filename).read_text(encoding="utf-8"))
    keys = {(domain, key) for domain in ("select", "number", "switch", "datetime", "text", "button")
            for key in document["entity"].get(domain, {})}
    assert keys == set(CONFIGURE_STEP) | {k for k in ALLOWED_WITHOUT_STEP if k[1] is not None}, keys
    steps = document["options"]["step"]
    for key in sorted(keys):
        if key in ALLOWED_WITHOUT_STEP:
            assert ALLOWED_WITHOUT_STEP[key].strip()
            continue
        step = CONFIGURE_STEP[key]
        assert hasattr(ProductOptionsFlow, f"async_step_{step}"), key
        assert steps[step]["title"].strip(), (key, step)
        menu = OFFERED_IN[step]
        assert step in steps[menu]["menu_options"] or step == "e32_room", (key, step, menu)
