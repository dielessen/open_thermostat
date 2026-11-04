"""The holiday planner (E32 rc.4, F8, house.holidays.v1) in Home Assistant.

The E32 announces it as the list away.holidays (the next two holidays) with away.holiday_temperature_c.
Then Configure → House → House mode and holiday is a menu: the house mode, plan a holiday, change or
remove one, and the temperature on holiday; the number "Temperature on holiday" sets the same value,
and the Overview names the next holiday under House. An older E32: the house mode form as before and
none of the rest.
"""
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat.controller_link import HeatingPlanRejected
from custom_components.open_thermostat.dashboard import TEXT, RoomDashboard, _holiday_card
from custom_components.open_thermostat.e32_house import (
    HolidayTemperature, HouseModeSelect, holiday_periods, holiday_temperature, house_state, merge_periods,
    supports_holidays)
from custom_components.open_thermostat.options_house_heating import holiday_line
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import STATUS, FakeE32

DAY = 86400
COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"


class E32WithHolidays(FakeE32):
    """The room-plan E32 with the holiday planner, as RoomOverrides answers GET/POST /config/heating/comfort."""

    def __init__(self, holidays=(), mode="auto", holiday_c=None, announce=True):
        super().__init__()
        self.holidays = sorted(tuple(h) for h in holidays)
        self.mode, self.holiday_c, self.away_c, self.announce = mode, holiday_c, 15.0, announce
        self.commands, self.reads_comfort, self.refuse = [], 0, None

    def running(self):
        now = int(time.time())
        return next((h for h in self.holidays if h[0] <= now < h[1]), None)

    def away(self):
        running = self.running()
        away = {"on": bool(running) or self.mode == "away", "source": "manual" if running or self.mode == "away" else "none",
                "target_c": self.away_c, "until": running[1] if running else None, "presence": "home",
                "mode": "holiday" if running else self.mode, "room_presence": True}
        if self.announce:
            away["holiday_temperature_c"] = self.holiday_c if self.holiday_c is not None else self.away_c
            away["holidays"] = [{"from": f, "until": u} for f, u in self.holidays[:2]]
        return away

    def state(self):
        state = {"schema": 1, "away": self.away(), "rooms": []}
        if self.announce:
            state["holidays"] = [{"from": f, "until": u} for f, u in self.holidays]
            state["holiday_temperature"] = self.away()["holiday_temperature_c"]
        return state

    def client(self, address):
        client, e32 = super().client(address), self

        async def async_comfort_state():
            e32.reads_comfort += 1
            return deepcopy(e32.state())

        async def async_comfort_command(command):
            e32.commands.append(deepcopy(command))
            if e32.refuse:
                raise HeatingPlanRejected(400, e32.refuse)
            if "holidays" in command:
                periods = [(h["from"], h["until"]) for h in command["holidays"]]
                if len(periods) > 8 or any(f >= u for f, u in periods):
                    raise HeatingPlanRejected(400, "invalid_holidays")
                if any(u <= int(time.time()) for _, u in periods):
                    raise HeatingPlanRejected(400, "holiday_in_past")
                e32.holidays = merge_periods(periods)
            if "holiday_temperature" in command:
                e32.holiday_c = command["holiday_temperature"]
            if "house_mode" in command:
                e32.mode = command["house_mode"]
            return deepcopy(e32.state())
        client.async_comfort_state = async_comfort_state
        client.async_comfort_command = async_comfort_command
        return client


def installed(hass, e32):
    parent, hub = product(hass, e32)
    hub.update({**STATUS, "away": e32.away()})
    return parent, hub


def future(days, hour=10):
    """A local moment `days` ahead at `hour`:00, as unix seconds and as the form's text."""
    moment = dt_util.as_local(dt_util.utcnow() + dt_util.dt.timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return int(moment.timestamp()), moment.strftime("%Y-%m-%d %H:%M:%S")


async def holidays_menu(manager, parent):
    flow = await manager.async_init(parent.entry_id)
    house = await manager.async_configure(flow["flow_id"], {"next_step_id": "house"})
    return await manager.async_configure(house["flow_id"], {"next_step_id": "house_mode"})


def test_the_capability_and_the_lists():
    assert supports_holidays({"on": False, "holidays": []}) and not supports_holidays({"on": False}) and not supports_holidays(None)
    assert holiday_periods([{"from": 5, "until": 1}, {"from": 3, "until": 4}, {"from": 1, "until": 2}, {"from": "x"}, 7]) == [(1, 2), (3, 4)]
    assert merge_periods([(5, 9), (1, 3), (3, 4), (10, 12), (8, 10)]) == [(1, 4), (5, 12)]
    assert holiday_temperature({"holidays": [], "holiday_temperature_c": 12.5}) == 12.5
    assert holiday_temperature({"holiday_temperature_c": 12.5}) is None  # an older E32 announces no holidays
    assert holiday_temperature({"holidays": [], "holiday_temperature_c": 40}) is None


@pytest.mark.asyncio
async def test_the_number_sets_the_temperature_on_holiday(hass):
    e32 = E32WithHolidays()
    parent, hub = installed(hass, e32)
    house = house_state(hass, parent, hub)
    number = HolidayTemperature(house)
    assert number.unique_id == "fixture_holiday_temperature" and number.translation_key == "holiday_temperature"
    assert number.entity_category == "config" and number.available
    assert number.native_value == 15  # the away temperature until the owner sets one
    await number.async_set_native_value(12.5)
    assert e32.commands == [{"holiday_temperature": 12.5}]
    assert number.native_value == 12.5  # the E32's read-back, before its next status
    with pytest.raises(ServiceValidationError) as error:
        await number.async_set_native_value(30)
    assert error.value.translation_key == "holiday_temperature_invalid" and len(e32.commands) == 1
    # The house mode select lists the next holidays for the dashboard.
    e32.holidays = [future(10, 10)[0:1] + future(14, 18)[0:1], future(30)[0:1] + future(31)[0:1]]
    hub.update({**STATUS, "away": e32.away()})
    house.answer = None
    attributes = HouseModeSelect(house).extra_state_attributes
    assert attributes["holiday_temperature"] == 12.5
    assert [list(h) for h in attributes["holidays"]] == [["from", "until"]] * 2
    assert attributes["holidays"][0]["until"] == dt_util.utc_from_timestamp(future(14, 18)[0]).isoformat()
    # An older E32: no holidays, the number is unavailable.
    e32.announce = False
    hub.update({**STATUS, "away": e32.away()})
    assert not number.available and number.native_value is None
    assert "holidays" not in HouseModeSelect(house).extra_state_attributes


@pytest.mark.asyncio
async def test_a_change_reads_and_writes_the_whole_list_in_one_session(hass):
    first, other = (future(10)[0], future(14)[0]), (future(30)[0], future(31)[0])
    e32 = E32WithHolidays([first])
    parent, hub = installed(hass, e32)
    house = house_state(hass, parent, hub)
    logins = e32.logins
    await house.async_holidays(lambda periods: [*periods, other, (first[1], first[1] + DAY)])  # the last one touches the first
    assert e32.logins == logins + 1 and e32.reads_comfort == 1
    assert e32.commands[-1] == {"holidays": [{"from": first[0], "until": first[1] + DAY}, {"from": other[0], "until": other[1]}]}
    # Nine separate ones: refused here already, nothing sent.
    many = [(future(40 + 2 * i)[0], future(41 + 2 * i)[0]) for i in range(9)]
    with pytest.raises(ServiceValidationError) as error:
        await house.async_holidays(lambda periods: many)
    assert error.value.translation_key == "house_holiday_too_many" and len(e32.commands) == 1
    # The E32's refusal names its reason.
    e32.refuse = "holiday_in_past"
    with pytest.raises(ServiceValidationError) as error:
        await house.async_holidays(lambda periods: periods)
    assert error.value.translation_placeholders == {"error": "holiday_in_past"}


@pytest.mark.asyncio
async def test_house_mode_and_holiday_plans_changes_and_removes_holidays(hass, manager):
    e32 = E32WithHolidays()
    parent, hub = installed(hass, e32)
    await hass.async_block_till_done()
    menu = await holidays_menu(manager, parent)
    assert menu["type"] == FlowResultType.MENU and menu["step_id"] == "house_holidays"
    assert menu["menu_options"] == ["house_mode_set", "house_holiday_add", "house_holiday_temperature", "back"]
    assert menu["description_placeholders"]["holidays"] == "No holidays planned."
    # Plan one: checked in the form first.
    form = await manager.async_configure(menu["flow_id"], {"next_step_id": "house_holiday_add"})
    assert form["step_id"] == "house_holiday_add" and {str(k) for k in form["data_schema"].schema} == {"holiday_from", "holiday_to"}
    start, end = future(20, 10), future(34, 18)
    result = await manager.async_configure(form["flow_id"], {"holiday_from": end[1], "holiday_to": start[1]})
    assert result["errors"] == {"holiday_to": "house_holiday_order"}
    result = await manager.async_configure(form["flow_id"], {"holiday_from": "2020-01-01 10:00:00", "holiday_to": "2020-01-02 10:00:00"})
    assert result["errors"] == {"holiday_to": "house_holiday_past"}
    result = await manager.async_configure(form["flow_id"], {"holiday_from": start[1], "holiday_to": future(400)[1]})
    assert result["errors"] == {"holiday_to": "house_holiday_too_far"}
    assert e32.commands == []
    result = await manager.async_configure(form["flow_id"], {"holiday_from": start[1], "holiday_to": end[1]})
    assert result["type"] == FlowResultType.MENU and result["step_id"] == "house_holidays"
    assert "Saved" in result["description_placeholders"]["saved"]
    assert e32.commands[-1] == {"holidays": [{"from": start[0], "until": end[0]}]}
    assert result["description_placeholders"]["holidays"] == "- " + holiday_line((start[0], end[0]))
    assert "house_holiday_change" in result["menu_options"]
    # Change it: the form holds its own local times.
    pick = await manager.async_configure(result["flow_id"], {"next_step_id": "house_holiday_change"})
    choice = pick["data_schema"].schema[next(iter(pick["data_schema"].schema))].config["options"]
    assert [o["label"] for o in choice] == [holiday_line((start[0], end[0]))]
    edit = await manager.async_configure(pick["flow_id"], {"holiday": choice[0]["value"]})
    assert edit["step_id"] == "house_holiday_edit"
    defaults = {str(k): k.default() for k in edit["data_schema"].schema}
    assert defaults == {"holiday_from": start[1], "holiday_to": end[1], "remove": False}
    later = future(36, 18)
    result = await manager.async_configure(edit["flow_id"], {"holiday_from": start[1], "holiday_to": later[1], "remove": False})
    assert result["type"] == FlowResultType.MENU and result["step_id"] == "house_holidays", result
    assert e32.commands[-1] == {"holidays": [{"from": start[0], "until": later[0]}]}
    # Changed elsewhere while the form was open: said so, nothing overwritten.
    pick = await manager.async_configure(result["flow_id"], {"next_step_id": "house_holiday_change"})
    edit = await manager.async_configure(pick["flow_id"], {"holiday": pick["data_schema"].schema[
        next(iter(pick["data_schema"].schema))].config["options"][0]["value"]})
    e32.holidays = [(start[0], later[0] + DAY)]
    sent = len(e32.commands)
    result = await manager.async_configure(edit["flow_id"], {"holiday_from": start[1], "holiday_to": end[1], "remove": False})
    assert result["errors"] == {"base": "house_holiday_changed"} and len(e32.commands) == sent
    # Remove it.
    menu = await holidays_menu(manager, parent)
    pick = await manager.async_configure(menu["flow_id"], {"next_step_id": "house_holiday_change"})
    edit = await manager.async_configure(pick["flow_id"], {"holiday": pick["data_schema"].schema[
        next(iter(pick["data_schema"].schema))].config["options"][0]["value"]})
    result = await manager.async_configure(edit["flow_id"], {"holiday_from": start[1], "holiday_to": later[1], "remove": True})
    assert result["type"] == FlowResultType.MENU and e32.commands[-1] == {"holidays": []}
    assert result["menu_options"] == ["house_mode_set", "house_holiday_add", "house_holiday_temperature", "back", "done"]


@pytest.mark.asyncio
async def test_the_temperature_on_holiday_and_the_house_mode_inside_the_menu(hass, manager):
    e32 = E32WithHolidays()
    parent, hub = installed(hass, e32)
    await hass.async_block_till_done()
    menu = await holidays_menu(manager, parent)
    form = await manager.async_configure(menu["flow_id"], {"next_step_id": "house_holiday_temperature"})
    field = next(iter(form["data_schema"].schema))
    assert str(field) == "holiday_temperature" and field.default() == 15.0
    config = form["data_schema"].schema[field].config
    assert (config["min"], config["max"], config["step"]) == (5, 25, 0.5)  # as the number entity
    result = await manager.async_configure(form["flow_id"], {"holiday_temperature": 12})
    assert result["type"] == FlowResultType.MENU and result["step_id"] == "house_holidays"
    assert e32.commands == [{"holiday_temperature": 12.0}]
    assert HolidayTemperature(house_state(hass, parent, hub)).native_value == 12  # the number shows it at once
    form = await manager.async_configure(result["flow_id"], {"next_step_id": "house_holiday_temperature"})
    result = await manager.async_configure(form["flow_id"], {"holiday_temperature": 12})
    assert result["type"] == FlowResultType.MENU and len(e32.commands) == 1  # unchanged: nothing sent
    # The house mode itself: the same form as before, now inside this menu.
    form = await manager.async_configure(result["flow_id"], {"next_step_id": "house_mode_set"})
    assert form["step_id"] == "house_mode_set" and {str(k) for k in form["data_schema"].schema} == {"house_mode", "holiday_until"}
    result = await manager.async_configure(form["flow_id"], {"house_mode": "home"})
    assert result["type"] == FlowResultType.MENU and result["step_id"] == "house_holidays"
    assert e32.commands[-1] == {"house_mode": "home"}
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        document = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
        step = document["options"]["step"]["house_holiday_temperature"]
        assert step["data"]["holiday_temperature"] == document["entity"]["number"]["holiday_temperature"]["name"], name
        assert "5–25 °C" in step["description"], name
        assert set(document["options"]["step"]["house_holidays"]["menu_options"]) == {
            "house_mode_set", "house_holiday_add", "house_holiday_change", "house_holiday_temperature", "back", "done"}, name


@pytest.mark.asyncio
async def test_stop_holiday_ends_the_running_one_and_keeps_the_mode(hass, manager):
    now = int(time.time())
    running, later = (now - DAY, now + 3 * DAY), (now + 30 * DAY, now + 31 * DAY)
    e32 = E32WithHolidays([running, later], mode="home")
    parent, hub = installed(hass, e32)
    await hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    house = await manager.async_configure(flow["flow_id"], {"next_step_id": "house"})
    assert "house_holiday_stop" in house["menu_options"]
    result = await manager.async_configure(house["flow_id"], {"next_step_id": "house_holiday_stop"})
    assert result["type"] == FlowResultType.MENU and result["step_id"] == "house"
    assert e32.commands == [{"holidays": [{"from": later[0], "until": later[1]}]}]  # the running one ended, not the mode
    assert e32.mode == "home"


@pytest.mark.asyncio
async def test_an_older_e32_keeps_the_house_mode_form(hass, manager):
    e32 = E32WithHolidays(announce=False)
    parent, hub = installed(hass, e32)
    await hass.async_block_till_done()
    form = await holidays_menu(manager, parent)
    assert form["type"] == FlowResultType.FORM and form["step_id"] == "house_mode"
    assert {str(k) for k in form["data_schema"].schema} == {"house_mode", "holiday_until"}


@pytest.mark.asyncio
async def test_the_overview_names_the_next_holiday(hass):
    select = "select.e32_house_mode"
    first = (int(dt_util.parse_datetime("2030-12-20 10:00:00").replace(tzinfo=dt_util.get_default_time_zone()).timestamp()),
             int(dt_util.parse_datetime("2031-01-03 18:00:00").replace(tzinfo=dt_util.get_default_time_zone()).timestamp()))
    holidays = [{"from": dt_util.utc_from_timestamp(f).isoformat(), "until": dt_util.utc_from_timestamp(u).isoformat()}
                for f, u in (first,)]
    hass.states.async_set(select, "auto", {"holidays": holidays})
    # Strictly, as Home Assistant's markdown card renders it: an undefined value (the first of no holidays) is an error
    # there, an empty box with an error logged on every render, not an empty text.
    render = lambda language: Template(_holiday_card(TEXT[language], select)["content"], hass).async_render(  # noqa: E731
        strict=True)
    assert render("en") == "Holiday from 20 Dec to 3 Jan"
    assert render("nl") == "Vakantie vanaf 20 dec t/m 3 jan"
    assert render("pl") == "Urlop od 20 gru do 3 sty"
    now = dt_util.utcnow()
    hass.states.async_set(select, "holiday", {"holidays": [{"from": (now - dt_util.dt.timedelta(days=1)).isoformat(),
                                                            "until": dt_util.as_local(now + dt_util.dt.timedelta(days=2)).isoformat()}]})
    until = dt_util.as_local(now + dt_util.dt.timedelta(days=2))
    assert render("en") == f"On holiday until {until.day} {TEXT['en']['months'].split(',')[until.month - 1]}"
    hass.states.async_set(select, "auto", {"holidays": []})
    assert render("en") == ""
    hass.states.async_set(select, "auto", {})  # an older E32
    assert render("en") == ""
    # Home Assistant's markdown card renders strictly: still "" (so the card hides), no error.
    for holidays in ([], None):
        hass.states.async_set(select, "auto", {"holidays": holidays} if holidays is not None else {})
        assert Template(_holiday_card(TEXT["nl"], select)["content"], hass).async_render(strict=True) == ""
    hass.states.async_set(select, "auto", {"holidays": [{"from": dt_util.utc_from_timestamp(first[0]).isoformat(),
                                                         "until": dt_util.utc_from_timestamp(first[1]).isoformat()}]})
    assert Template(_holiday_card(TEXT["nl"], select)["content"], hass).async_render(strict=True) == (
        "Vakantie vanaf 20 dec t/m 3 jan")
    assert _holiday_card(TEXT["en"], None) is None and _holiday_card(TEXT["en"], select)["show_empty"] is False


@pytest.mark.asyncio
async def test_the_card_sits_under_house_on_the_overview(hass):
    from test_dashboard_heating import installation
    e, *_ = installation(hass)
    product_device = dr.async_get(hass).async_get_device_by_identifier(("open_thermostat", "fixture"), e.entry_id)
    select = er.async_get(hass).async_get_or_create("select", "open_thermostat", "fixture_house_mode", config_entry=e,
                                                    device_id=product_device.id, suggested_object_id="house_mode").entity_id
    overview = RoomDashboard(hass, "fixture", e.entry_id)._dashboard_config()["views"][0]
    # rc.5: the house card on top shows the house mode as a chip; the House section (the owner's sketch: home or
    # away, the holiday planner, outside) has the next holiday under its rows.
    assert overview["sections"][0]["cards"][0]["type"] == "custom:openthermostat-house"
    assert overview["sections"][0]["cards"][0]["mode"] == select
    house = overview["sections"][-1]["cards"]
    assert house[0]["heading"] == "House" and house[1]["entities"][0]["row"]["entity"] == select
    assert house[2]["type"] == "markdown" and house[2]["show_empty"] is False and select in house[2]["content"]

