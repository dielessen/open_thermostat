"""Every room runs its E32 week program; HA shows it on the room's setting device and takes the knob as an override."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import e32_setting_device as module
from custom_components.open_thermostat.e32_setting_device import (
    SettingDevicePusher, apply_room_program_changes, default_program, describe_changes, room_program_changes)
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.room_plan import RoomPlanLink
from test_e32_comfort import FakeE32

TADO, TV02 = "climate.tado_woonkamer", "climate.thermostaat_badkamer"
PROGRAM = default_program()
WOONKAMER = {"id": "woonkamer", "name": "Woonkamer", "state": "active", "inactive_until": 0, "emitter": "floor",
             "sources": [{"type": "ha", "id": TADO}, {"type": "ble", "id": "a4c138a3e8db"}], "setpoint_entity": TADO,
             "fallback_centi_c": 2000, "minimum_centi_c": 500, "maximum_centi_c": 2500}
BADKAMER = {**WOONKAMER, "id": "badkamer", "name": "Badkamer", "emitter": "radiator",
            "sources": [{"type": "ha", "id": TV02}], "setpoint_entity": ""}
SLAAPKAMER = {**WOONKAMER, "id": "slaapkamer", "name": "Slaapkamer", "sources": [{"type": "ble", "id": "a4c138000002"}],
              "setpoint_entity": "input_number.slaapkamer_doel"}


def plan(*rooms):
    return {"schema": 1, "revision": 3, "mode": "shadow", "minimum_flow_c": 30, "maximum_flow_c": 60,
            "rooms": [deepcopy(r) for r in rooms]}


def room(room_id, setpoint, **extra):
    return {"id": room_id, "name": room_id.title(), "state": "active", "status": "ok", "temperature": 19.5,
            "setpoint": setpoint, "setpoint_source": "schedule", "demand": False, **extra}


def status(*rooms):
    return {"schema": 1, "revision": 3, "mode": "shadow", "request": {"heat": False, "flow_c": 0, "reason": "idle"},
            "ha_entities": [], "rooms": list(rooms)}


def devices(hass):
    """The owner's tado and TV02 (other integrations), and a °F helper; service calls recorded and applied."""
    hass.states.async_set(TADO, "heat", {"temperature": 19.0, "target_temp_step": 0.1, "min_temp": 5, "max_temp": 25})
    hass.states.async_set(TV02, "heat", {"temperature": 21.0, "target_temp_step": 0.5, "min_temp": 5, "max_temp": 29.5})
    hass.states.async_set("input_number.slaapkamer_doel", "64.4", {"unit_of_measurement": "°F", "step": 0.1,
                                                                    "min": 41, "max": 86})
    calls = []

    async def handler(call):
        calls.append((call.domain, call.service, dict(call.data)))
        state = hass.states.get(call.data["entity_id"])
        if call.domain == "climate":
            hass.states.async_set(state.entity_id, state.state, {**state.attributes, "temperature": call.data["temperature"]})
        else:
            hass.states.async_set(state.entity_id, str(call.data["value"]), state.attributes)
    hass.services.async_register("climate", "set_temperature", handler)
    hass.services.async_register("input_number", "set_value", handler)
    hass.services.async_register("number", "set_value", handler)
    return calls


async def setup(hass, e32_plan, *rooms):
    e32 = FakeE32()
    e32.plan = e32_plan
    hub = HeatingHub("fixture")
    link = RoomPlanLink(hass, "http://192.168.1.206", "secret", hub)
    link._client = e32.client
    hub.plan = link
    await link.async_read()
    hub.update(status(*rooms))
    clock = [1000.0]
    entry = SimpleNamespace(entry_id="e1", options={})
    pusher = SettingDevicePusher(hass, entry, hub, clock=lambda: clock[0])
    stop = pusher.start()
    await hass.async_block_till_done()
    return e32, hub, link, pusher, clock, stop


def knob(hass, entity_id, value):
    state = hass.states.get(entity_id)
    hass.states.async_set(entity_id, state.state, {**state.attributes, "temperature": value})


@pytest.mark.asyncio
async def test_the_program_target_is_shown_on_the_device_at_each_switch_point(hass):
    calls = devices(hass)
    e32, hub, link, pusher, clock, stop = await setup(hass, plan({**WOONKAMER, "schedule": PROGRAM}), room("woonkamer", 20.0))
    assert calls == [("climate", "set_temperature", {"entity_id": TADO, "temperature": 20.0})]
    # The same target again: nothing is written.
    hub.update(status(room("woonkamer", 20.0)))
    await hass.async_block_till_done()
    assert len(calls) == 1
    # A switch point (08:30: away 18 °C) within a minute of the last write waits for the rate limit ...
    clock[0] += 30
    hub.update(status(room("woonkamer", 18.0)))
    await hass.async_block_till_done()
    assert len(calls) == 1
    # ... and is written once the minute has passed.
    clock[0] += 31
    hub.update(status(room("woonkamer", 18.0)))
    await hass.async_block_till_done()
    assert calls[-1] == ("climate", "set_temperature", {"entity_id": TADO, "temperature": 18.0})
    assert e32.commands == []  # our own write is no override
    stop()
    link.stop()


@pytest.mark.asyncio
async def test_a_knob_change_is_an_override_until_the_next_switch_point_then_the_program_returns(hass):
    calls = devices(hass)
    e32, hub, link, pusher, clock, stop = await setup(hass, plan({**WOONKAMER, "schedule": PROGRAM}), room("woonkamer", 20.0))
    assert len(calls) == 1
    clock[0] += 5
    knob(hass, TADO, 20.0)  # the echo of our write (also within the settle time): nothing
    await hass.async_block_till_done()
    assert e32.commands == []
    clock[0] += 120
    knob(hass, TADO, 22.0)  # somebody turns the tado
    await hass.async_block_till_done()
    assert e32.commands == [{"room": "woonkamer", "override": "next", "temperature": 22.0}]
    # Until the E32 reports it, the program's 20 °C is not written back over the knob.
    hub.update(status(room("woonkamer", 20.0)))
    await hass.async_block_till_done()
    assert len(calls) == 1
    hub.update(status(room("woonkamer", 22.0, comfort={"mode": "next", "target_c": 22, "override": "next"})))
    await hass.async_block_till_done()
    assert len(calls) == 1
    # The next switch point ends it on the E32: the program's target goes back to the tado.
    clock[0] += 3600
    hub.update(status(room("woonkamer", 18.0)))
    await hass.async_block_till_done()
    assert calls[-1] == ("climate", "set_temperature", {"entity_id": TADO, "temperature": 18.0})
    stop()
    link.stop()


@pytest.mark.asyncio
async def test_a_number_device_in_its_own_unit_and_rooms_that_are_left_alone(hass):
    calls = devices(hass)
    rooms = plan({**SLAAPKAMER, "schedule": PROGRAM}, {**BADKAMER, "setpoint_entity": TV02, "schedule": PROGRAM},
                 {**WOONKAMER, "schedule": PROGRAM})
    e32, hub, link, pusher, clock, stop = await setup(
        hass, rooms, room("slaapkamer", 20.0), room("badkamer", 16.0, comfort={"mode": "window_open", "window": "open"}),
        room("woonkamer", 20.0, state="inactive"))
    # 20 °C on a °F helper, in its step; the open window and the inactive room are not written.
    assert calls == [("input_number", "set_value", {"entity_id": "input_number.slaapkamer_doel", "value": 68.0})]
    clock[0] += 120
    hass.states.async_set("input_number.slaapkamer_doel", "71.6", hass.states.get("input_number.slaapkamer_doel").attributes)
    await hass.async_block_till_done()
    assert e32.commands == [{"room": "slaapkamer", "override": "next", "temperature": 22.0}]
    stop()
    link.stop()


@pytest.mark.asyncio
async def test_without_the_e32_program_or_home_assistant_nothing_is_written(hass):
    calls = devices(hass)
    e32, hub, link, pusher, clock, stop = await setup(
        hass, plan({**WOONKAMER, "schedule": PROGRAM}), room("woonkamer", 19.0, setpoint_source="ha"))
    assert calls == []  # the E32 has no clock yet: its program is not running
    hub.update(None)    # the E32 is offline
    knob(hass, TADO, 23.0)
    await hass.async_block_till_done()
    assert calls == [] and e32.commands == []
    # Back: the E32's current target is shown again (the knob turned meanwhile is not taken over).
    hub.update(status(room("woonkamer", 20.0)))
    await hass.async_block_till_done()
    assert calls == [("climate", "set_temperature", {"entity_id": TADO, "temperature": 20.0})]
    assert e32.commands == []
    stop()
    link.stop()


@pytest.mark.asyncio
async def test_a_device_running_its_own_schedule_is_reported(hass):
    calls = devices(hass)
    e32, hub, link, pusher, clock, stop = await setup(hass, plan({**WOONKAMER, "schedule": PROGRAM}), room("woonkamer", 20.0))
    day = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
    for d in range(3):
        pusher.now = lambda d=d: day + timedelta(days=d)
        clock[0] += 3600
        hub.update(status(room("woonkamer", 20.0)))  # the program again on the tado
        await hass.async_block_till_done()
        clock[0] += 60
        knob(hass, TADO, 21.5 + d * 0.5)              # and at 06:00 it changes by itself
        await hass.async_block_till_done()
    issue = ir.async_get(hass).async_get_issue("open_thermostat", "device_own_schedule_e1_woonkamer")
    assert issue is not None and issue.translation_placeholders["room"] == "Woonkamer"
    # Still running its own schedule the next update: the item stays.
    hub.update(status(room("woonkamer", 20.0)))
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue("open_thermostat", "device_own_schedule_e1_woonkamer") is not None
    # Its own schedule turned off: no unasked change for the whole window, and the item goes by itself.
    pusher.now = lambda: day + timedelta(days=2 + 8)
    hub.update(status(room("woonkamer", 20.5)))
    await hass.async_block_till_done()
    assert ir.async_get(hass).async_get_issue("open_thermostat", "device_own_schedule_e1_woonkamer") is None
    stop()
    link.stop()


@pytest.mark.asyncio
async def test_the_own_schedule_item_goes_with_the_setting_device(hass):
    devices(hass)
    e32, hub, link, pusher, clock, stop = await setup(hass, plan({**WOONKAMER, "schedule": PROGRAM}), room("woonkamer", 20.0))
    ir.async_create_issue(hass, "open_thermostat", "device_own_schedule_e1_woonkamer", is_fixable=False,
                          severity=ir.IssueSeverity.WARNING, translation_key="device_own_schedule")
    ir.async_create_issue(hass, "open_thermostat", "device_own_schedule_e1_zolder", is_fixable=False,
                          severity=ir.IssueSeverity.WARNING, translation_key="device_own_schedule")
    hub.update(status(room("woonkamer", 20.5)))
    await hass.async_block_till_done()
    # No unasked changes known (for example after a restart) and a room that is gone: both go.
    assert ir.async_get(hass).async_get_issue("open_thermostat", "device_own_schedule_e1_woonkamer") is None
    assert ir.async_get(hass).async_get_issue("open_thermostat", "device_own_schedule_e1_zolder") is None
    stop()
    link.stop()


def test_the_owners_two_rooms_get_a_program_and_badkamer_its_tv02():
    owner = plan(WOONKAMER, BADKAMER)
    changes = room_program_changes(owner)
    assert changes == [("woonkamer", "Woonkamer", True, None), ("badkamer", "Badkamer", True, TV02)]
    assert describe_changes(changes, "nl") == ("- Woonkamer: weekprogramma Werkdagen en weekend (20 °C)\n"
                                               f"- Badkamer: weekprogramma Werkdagen en weekend (20 °C), instelapparaat {TV02}")
    done = apply_room_program_changes(owner)
    assert done["rooms"][0]["schedule"] == PROGRAM and done["rooms"][0]["setpoint_entity"] == TADO
    assert done["rooms"][1]["schedule"] == PROGRAM and done["rooms"][1]["setpoint_entity"] == TV02
    assert done["rooms"][1]["sources"] == BADKAMER["sources"]  # the TV02 stays a source too
    assert room_program_changes(done) == []
    # A room with a program whose owner left the setting device empty raises no Repairs change.
    left = plan({**BADKAMER, "schedule": PROGRAM})
    assert room_program_changes(left) == []
    assert not apply_room_program_changes(left)["rooms"][0].get("setpoint_entity")
    # Workdays 06:30 20, 08:30 18, 17:00 20, 22:30 16; weekend 08:00 20, 23:00 16; within the room's limits.
    assert PROGRAM[0] == [[390, 2000], [510, 1800], [1020, 2000], [1350, 1600]] and PROGRAM[6] == [[480, 2000], [1380, 1600]]
    assert default_program(1700, 1900)[0] == [[390, 1900], [510, 1800], [1020, 1900], [1350, 1700]]


@pytest.mark.asyncio
async def test_the_repairs_fix_writes_the_programs_once_confirmed(hass):
    devices(hass)
    e32, hub, link, pusher, clock, stop = await setup(hass, plan(WOONKAMER, BADKAMER), room("woonkamer", 20.0),
                                                      room("badkamer", 21.0))
    issue = ir.async_get(hass).async_get_issue("open_thermostat", "room_programs_e1")
    assert issue is not None and issue.translation_placeholders["rooms"] == "Woonkamer, Badkamer"
    assert e32.plan_posts == []  # nothing changes before the user confirms
    flow = module.RoomProgramsRepairFlow("room_programs_e1", {"entry_id": "e1"})
    flow.hass = hass
    hass.config_entries.async_get_entry = lambda entry_id: SimpleNamespace(entry_id=entry_id)
    hass.data.setdefault("open_thermostat", {})["e1"] = {"heating_hub": hub}
    form = await flow.async_step_init()
    assert form["step_id"] == "room_programs" and "Badkamer" in form["description_placeholders"]["changes"]
    await flow.async_step_room_programs({})
    assert [r["schedule"] for r in e32.plan["rooms"]] == [PROGRAM, PROGRAM]
    assert e32.plan["rooms"][1]["setpoint_entity"] == TV02
    assert ir.async_get(hass).async_get_issue("open_thermostat", "room_programs_e1") is None
    stop()
    link.stop()
