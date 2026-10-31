"""The house mode (E32 beta.23, house.mode.v1): automatic, at home, away and holiday, from Home Assistant.

Also with E32 beta.21, which has no house modes: then "at home" is not offered and the older away
commands are used.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat import e32_house as module
from custom_components.open_thermostat.e32_house import (
    AwayTemperature, HolidayUntil, HouseModeSelect, HouseState, house_mode, mode_command, supports_house_mode)
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.room_plan import RoomPlanLink

PLAN = {"schema": 1, "revision": 2, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60, "rooms": []}
AUTO = {"on": False, "source": "none", "target_c": 15, "until": None, "presence": "home", "mode": "auto"}
OLD_AUTO = {k: v for k, v in AUTO.items() if k != "mode"}  # E32 beta.21


def status(away):
    return {"schema": 1, "revision": 2, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
            "ha_entities": [], "rooms": [], "away": deepcopy(away)}


class FakeE32:
    """POST /config/heating/comfort as RoomOverrides::command answers it (the stored away state)."""

    def __init__(self, away):
        self.away = deepcopy(away)
        self.commands = []

    def client(self):
        e32 = self

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return None

            async def async_login(self, password):
                assert password == "secret"

            async def async_read_heating_plan(self):
                return deepcopy(PLAN)

            async def async_comfort_command(self, command):
                e32.commands.append(deepcopy(command))
                a = e32.away
                if "house_mode" in command:
                    mode = command["house_mode"]
                    a.update(mode=mode, on=mode in ("away", "holiday"), source="manual" if mode in ("away", "holiday") else "none",
                             until=command.get("until") if mode == "holiday" else None)
                else:
                    a.update(on=command["away"], source="manual" if command["away"] else "none",
                             until=command.get("until") if command["away"] else None)
                if "temperature" in command:
                    a["target_c"] = command["temperature"]
                return {"schema": 1, "away": deepcopy(a), "rooms": []}
        return Client()


async def house(hass, away):
    e32 = FakeE32(away)
    hub = HeatingHub("fixture")
    link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    link._client = e32.client
    hub.plan = link
    await link.async_read()
    hub.update(status(away))
    await hass.async_block_till_done()
    state = HouseState(hub)
    hub.add_listener(state.hub_changed)
    return state, hub, e32, link


def test_the_mode_comes_from_the_e32_or_from_the_older_away_state():
    assert house_mode(AUTO) == "auto" and supports_house_mode(AUTO)
    assert house_mode({**AUTO, "mode": "home"}) == "home"
    assert not supports_house_mode(OLD_AUTO) and house_mode(OLD_AUTO) == "auto"
    assert house_mode({**OLD_AUTO, "on": True, "source": "manual"}) == "away"
    assert house_mode({**OLD_AUTO, "on": True, "source": "manual", "until": 1793700000}) == "holiday"
    assert house_mode({**OLD_AUTO, "on": True, "source": "presence"}) == "auto"  # everyone away in automatic mode


def test_commands_use_the_e32s_own_format():
    assert mode_command(AUTO, "home") == {"house_mode": "home"}
    assert mode_command(AUTO, "auto", temperature=16.5) == {"house_mode": "auto", "temperature": 16.5}
    assert mode_command(AUTO, "holiday", until=1793700000) == {"house_mode": "holiday", "until": 1793700000}
    # E32 beta.21: the older away commands; "at home" needs beta.23.
    assert mode_command(OLD_AUTO, "auto") == {"away": False}
    assert mode_command(OLD_AUTO, "away", temperature=16) == {"away": True, "temperature": 16.0}
    assert mode_command(OLD_AUTO, "holiday", until=1793700000) == {"away": True, "until": 1793700000}
    for away, mode, kwargs, key in ((OLD_AUTO, "home", {}, "house_mode_update_required"),
                                    (OLD_AUTO, "auto", {"temperature": 16}, "house_mode_update_required"),
                                    (AUTO, "holiday", {}, "house_holiday_date_needed"),
                                    (AUTO, "party", {}, "house_mode_invalid"),
                                    (AUTO, "away", {"temperature": 30}, "comfort_away_temperature")):
        with pytest.raises(ServiceValidationError) as error:
            mode_command(away, mode, **kwargs)
        assert error.value.translation_key == key


@pytest.mark.asyncio
async def test_the_house_mode_select_switches_and_shows_the_e32s_read_back(hass):
    state, hub, e32, link = await house(hass, AUTO)
    select = HouseModeSelect(state)
    assert select.unique_id == "fixture_house_mode" and select.translation_key == "house_mode"
    assert select.available and select.options == ["auto", "home", "away", "holiday"] and select.current_option == "auto"
    assert select.extra_state_attributes == {"presence": "home", "away_now": False, "away_temperature": 15, "until": None}
    await select.async_select_option("home")
    assert e32.commands[-1] == {"house_mode": "home"}
    assert select.current_option == "home"   # the E32's answer, before its next status
    hub.update(status(AUTO))                 # an older status (published before the command) does not undo it
    assert select.current_option == "home"
    hub.update(status({**AUTO, "mode": "home"}))
    assert select.current_option == "home" and state.answer is None
    # Holiday needs its end date first.
    with pytest.raises(ServiceValidationError) as error:
        await select.async_select_option("holiday")
    assert error.value.translation_key == "house_holiday_date_needed"
    link.stop()


@pytest.mark.asyncio
async def test_holiday_until_starts_a_holiday_and_the_away_temperature_keeps_the_mode(hass):
    state, hub, e32, link = await house(hass, AUTO)
    until_entity, temperature = HolidayUntil(state), AwayTemperature(state)
    assert until_entity.unique_id == "fixture_holiday_until" and until_entity.native_value is None
    assert temperature.unique_id == "fixture_away_temperature" and temperature.native_value == 15
    end = (dt_util.utcnow() + timedelta(days=7)).replace(microsecond=0)
    await until_entity.async_set_value(end)
    assert e32.commands[-1] == {"house_mode": "holiday", "until": int(end.timestamp())}
    assert until_entity.native_value == end and HouseModeSelect(state).current_option == "holiday"
    await temperature.async_set_native_value(16.5)
    assert e32.commands[-1] == {"house_mode": "holiday", "temperature": 16.5, "until": int(end.timestamp())}
    assert temperature.native_value == 16.5
    for bad in (dt_util.utcnow() - timedelta(minutes=1), dt_util.utcnow() + timedelta(days=400)):
        with pytest.raises(ServiceValidationError):
            await until_entity.async_set_value(bad)
    # The select's "holiday" uses the chosen end date again.
    await HouseModeSelect(state).async_select_option("auto")
    await HouseModeSelect(state).async_select_option("holiday")
    assert e32.commands[-1] == {"house_mode": "holiday", "until": int(end.timestamp())}
    link.stop()


@pytest.mark.asyncio
async def test_with_e32_beta21_at_home_is_not_offered_and_the_older_commands_are_used(hass):
    state, hub, e32, link = await house(hass, OLD_AUTO)
    select = HouseModeSelect(state)
    assert select.options == ["auto", "away", "holiday"] and select.current_option == "auto"
    await select.async_select_option("away")
    assert e32.commands[-1] == {"away": True}
    assert select.current_option == "away"
    await select.async_select_option("auto")
    assert e32.commands[-1] == {"away": False}
    with pytest.raises(ServiceValidationError) as error:
        await AwayTemperature(state).async_set_native_value(17)  # only together with away on beta.21
    assert error.value.translation_key == "house_mode_update_required"
    link.stop()


@pytest.mark.asyncio
async def test_without_the_e32s_away_status_the_controls_are_unavailable(hass):
    state, hub, e32, link = await house(hass, AUTO)
    hub.update({**status(AUTO), "away": None})
    assert not HouseModeSelect(state).available and HouseModeSelect(state).current_option is None
    hub.update(None)
    assert not AwayTemperature(state).available
    link.stop()


def test_the_house_menu_holds_presence_heating_and_energy():
    from custom_components.open_thermostat.product_flow import main_menu
    entry = SimpleNamespace(options={}, data={})
    from custom_components.open_thermostat import room_plan
    original = room_plan.has_room_plan
    room_plan.has_room_plan = lambda entry: True
    try:
        menu = main_menu(entry)
    finally:
        room_plan.has_room_plan = original
    assert menu == ["e32_rooms", "house", "comfort", "controller_connection", "general", "advanced_settings"]
