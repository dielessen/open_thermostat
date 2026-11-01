"""Radiator valves Home Assistant controls (model ha_climate): driven by HA on the E32's rules."""
from copy import deepcopy
import logging
from types import MappingProxyType, SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir

from custom_components.open_thermostat import e32_valves, ha_valves as module
from custom_components.open_thermostat.heating_link import HeatingHub
from test_e32_telemetry_topics import STATUS

TRV = "climate.trv_woonkamer"


def status(output=True, control=True, setpoint=21.0, state="active", valves=None):
    value = deepcopy(STATUS)
    room = value["rooms"][0]
    room.update(setpoint=setpoint, state=state, status="inactive" if state == "inactive" else "ok")
    value["trv"] = {"output": output, "flow_offset_c": 0, "rooms": [{
        "room": "woonkamer", "control": control, "degraded": False, "single_source": False,
        "valves": valves if valves is not None else [
            {"name": "Kraan raam", "model": "bosch_bth_ra", "health": "ok", "position_pct": 60, "battery_pct": 80},
            {"name": TRV, "model": "ha_climate", "health": "unknown"}]}]}
    return value


class Valve:
    """A climate entity of another integration and the service calls it receives."""

    def __init__(self, hass, state="auto", **attributes):
        self.hass, self.calls, self.fail = hass, [], None
        self.attributes = {"hvac_modes": ["off", "heat", "auto"], "temperature": 17, "min_temp": 5, "max_temp": 30,
                           "target_temp_step": 0.5, **attributes}
        self.set(state)
        for service in ("set_temperature", "set_hvac_mode", "turn_off", "turn_on"):
            hass.services.async_register("climate", service, self.handle)

    def set(self, state, **attributes):
        self.attributes.update(attributes)
        self.hass.states.async_set(TRV, state, self.attributes)

    async def handle(self, call):
        assert call.data["entity_id"] == TRV
        self.calls.append((call.service, {k: v for k, v in call.data.items() if k != "entity_id"}))
        if self.fail:
            raise self.fail


async def started(hass, value):
    now = [10000.0]
    hub = HeatingHub("fixture", clock=lambda: now[0])
    hub.update(value)
    driver = hub.ha_valves = module.HaValveDriver(hass, hub, clock=lambda: now[0])
    stop = driver.start()
    await hass.async_block_till_done()
    return hub, driver, now, stop


async def step(hass, hub, value, now=None, seconds=0):
    if now is not None:
        now[0] += seconds
    hub.update(value)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_nothing_is_sent_without_output_or_control_and_never_turn_off(hass):
    valve = Valve(hass)
    hub, _, now, stop = await started(hass, status(output=False))
    await step(hass, hub, status(output=False, setpoint=23), now, 3600)
    await step(hass, hub, status(output=True, control=False, setpoint=23), now, 3600)
    hub.update(None)  # the E32 offline: nothing either
    await hass.async_block_till_done()
    assert valve.calls == []
    stop()


@pytest.mark.asyncio
async def test_the_room_target_goes_out_on_the_firmware_rules(hass):
    valve = Valve(hass)
    hub, _, now, stop = await started(hass, status())
    # The control period starts: heat mode once, then the room's target.
    assert valve.calls == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 21.0})]
    valve.calls.clear()
    valve.set("heat", temperature=21.0)
    # Below 0.5 °C: nothing; a 0.5 °C change waits for the minute, then goes out once.
    await step(hass, hub, status(setpoint=21.2), now, 10)
    await step(hass, hub, status(setpoint=21.5), now, 20)
    assert valve.calls == []
    await step(hass, hub, status(setpoint=21.5), now, 31)
    await step(hass, hub, status(setpoint=21.5), now, 60)
    assert valve.calls == [("set_temperature", {"temperature": 21.5})]
    valve.calls.clear()
    # The room off: frost protection, within the entity's limits.
    valve.set("heat", min_temp=10)
    await step(hass, hub, status(state="inactive"), now, 61)
    assert valve.calls == [("set_temperature", {"temperature": 10})]
    valve.calls.clear()
    # The same target is sent again after 6 h, and only then.
    for _ in range(5):
        await step(hass, hub, status(state="inactive"), now, 3600)
    assert valve.calls == []
    await step(hass, hub, status(state="inactive"), now, 3600)
    assert valve.calls == [("set_temperature", {"temperature": 10})]
    valve.calls.clear()
    # Output off: nothing more, the valve keeps its setpoint; back on: a new control period, heat mode again.
    await step(hass, hub, status(output=False, setpoint=24), now, 120)
    assert valve.calls == []
    valve.set("auto")
    await step(hass, hub, status(setpoint=24), now, 120)
    assert valve.calls == [("set_hvac_mode", {"hvac_mode": "heat"}), ("set_temperature", {"temperature": 24.0})]
    assert not [c for c in valve.calls if c[0] in ("turn_off", "turn_on")]
    stop()


@pytest.mark.asyncio
async def test_step_already_set_targets_and_no_heat_mode(hass):
    # A whole-degree valve without a heat mode that already shows the target (HA restarted): nothing to send.
    valve = Valve(hass, "auto", hvac_modes=["auto"], target_temp_step=1, temperature=21)
    hub, _, now, stop = await started(hass, status(setpoint=20.6))
    assert valve.calls == []
    await step(hass, hub, status(setpoint=19.4), now, 61)
    assert valve.calls == [("set_temperature", {"temperature": 19})]
    stop()


@pytest.mark.asyncio
async def test_an_unavailable_valve_is_waited_for_and_offline_after_two_hours(hass):
    valve = Valve(hass, "unavailable")
    hub, driver, now, stop = await started(hass, status())
    assert valve.calls == []
    assert driver.view(TRV)["health"] == "unknown"
    await step(hass, hub, status(), now, 2 * 3600)
    assert driver.view(TRV)["health"] == "offline"
    raised = set()
    e32_valves.sync_issues(hass, SimpleNamespace(entry_id="e"), hub, raised)
    issue = ir.async_get(hass).async_get_issue("open_thermostat", "valve_offline_e_woonkamer")
    assert issue.translation_placeholders == {"room": "Woonkamer", "valves": TRV}
    # Back: driven at once (its state change), healthy again.
    valve.set("heat")
    await hass.async_block_till_done()
    assert valve.calls == [("set_temperature", {"temperature": 21.0})]
    assert driver.view(TRV)["health"] == "ok"
    stop()


def device(hass, *entities):
    entry = ConfigEntry(domain="zha", title="other integration", version=1, minor_version=1, data={}, options={},
                        source="user", unique_id="zha_fixture", discovery_keys=MappingProxyType({}), subentries_data=[])
    hass.config_entries._entries[entry.entry_id] = entry
    item = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, identifiers={("zha", "trv")}, name="TRV")
    registry = er.async_get(hass)
    made = []
    for domain, unique_id, object_id, device_class, name in entities:
        made.append(registry.async_get_or_create(domain, "zha", unique_id, suggested_object_id=object_id, config_entry=entry,
                                                 device_id=item.id, original_device_class=device_class,
                                                 original_name=name).entity_id)
    return made


@pytest.mark.asyncio
async def test_battery_and_opening_come_from_the_valves_own_device(hass):
    climate, battery, low, demand, other = device(
        hass, ("climate", "c", "trv_woonkamer", None, None), ("sensor", "b", "trv_battery", "battery", "Battery"),
        ("binary_sensor", "l", "trv_battery_low", "battery", "Battery low"),
        ("sensor", "p", "trv_heating_demand", None, "Pi heating demand"), ("sensor", "t", "trv_temperature", "temperature", None))
    assert climate == TRV
    Valve(hass, "heat", temperature=21)
    hass.states.async_set(battery, "15", {"device_class": "battery", "unit_of_measurement": "%"})
    hass.states.async_set(low, "off", {"device_class": "battery"})
    hass.states.async_set(demand, "42", {"unit_of_measurement": "%"})
    hass.states.async_set(other, "19.5", {"device_class": "temperature"})
    hub, driver, _, stop = await started(hass, status(output=False))
    assert driver.view(TRV) == {"setpoint_c": 21.0, "position_pct": 42, "battery_pct": 15, "battery_low": False,
                                "health": "low_battery"}
    # The room's entities and Repairs include it beside the Zigbee2MQTT valve.
    position = e32_valves.ValvePositionSensor(hub, hub.rooms["woonkamer"])
    batteries = e32_valves.ValveBatterySensor(hub, hub.rooms["woonkamer"])
    problem = e32_valves.ValveProblemBinarySensor(hub, hub.rooms["woonkamer"])
    assert (position.native_value, batteries.native_value, problem.is_on) == (51, 15, True)
    assert problem.extra_state_attributes == {"problems": [{"name": TRV, "health": "low_battery"}]}
    assert position.extra_state_attributes["valves"][0]["name"] == "Kraan raam"   # the E32's own valve unchanged
    raised = set()
    e32_valves.sync_issues(hass, SimpleNamespace(entry_id="e"), hub, raised)
    assert raised == {"valve_battery_low_e_woonkamer"}
    # Without a battery sensor the binary one tells; an attribute is the last resort.
    hass.states.async_set(battery, "unavailable")
    hass.states.async_set(low, "on", {"device_class": "battery"})
    assert driver.view(TRV)["health"] == "low_battery" and "battery_pct" not in driver.view(TRV)
    hass.states.async_set(low, "unavailable")
    Valve(hass, "heat", temperature=21, battery_level=90, valve_position=70)
    assert driver.view(TRV) == {"setpoint_c": 21.0, "position_pct": 70, "battery_pct": 90, "health": "ok"}
    stop()


@pytest.mark.asyncio
async def test_a_failing_call_warns_once_and_is_retried_a_minute_later(hass, caplog):
    valve = Valve(hass, "heat")
    valve.fail = HomeAssistantError("cloud unreachable")
    caplog.set_level(logging.WARNING)
    hub, _, now, stop = await started(hass, status())
    for _ in range(5):
        await step(hass, hub, status(), now, 10)
    assert valve.calls == [("set_temperature", {"temperature": 21.0})]
    await step(hass, hub, status(), now, 20)
    await step(hass, hub, status(), now, 61)
    assert len(valve.calls) == 3
    warnings = [r for r in caplog.records if r.name == module.__name__ and r.levelno == logging.WARNING]
    assert len(warnings) == 1 and TRV in warnings[0].getMessage()
    # A new value is a new warning; success clears it.
    await step(hass, hub, status(setpoint=22), now, 61)
    assert len([r for r in caplog.records if r.name == module.__name__]) == 2
    valve.fail = None
    await step(hass, hub, status(setpoint=22), now, 61)
    assert valve.calls[-1] == ("set_temperature", {"temperature": 22.0})
    await step(hass, hub, status(setpoint=22), now, 61)
    assert valve.calls[-1] == ("set_temperature", {"temperature": 22.0}) and len(valve.calls) == 5
    stop()


@pytest.mark.asyncio
async def test_zigbee_valves_and_a_room_without_ha_valves_are_left_alone(hass):
    valve = Valve(hass)
    only_zigbee = [{"name": "Kraan raam", "model": "bosch_bth_ra", "health": "ok", "position_pct": 60}]
    hub, driver, now, stop = await started(hass, status(valves=only_zigbee))
    assert valve.calls == []
    room = hub.valves["woonkamer"]
    assert driver.overlay(room) is room
    stop()


def test_the_record_takes_climate_entities_for_ha_valves_only():
    record = {"schema": 1, "base_topic": "zigbee2mqtt", "rooms": [{"room": "woonkamer", "control": True, "valves": [
        {"name": TRV, "model": "ha_climate"}, {"name": "climate.as_zigbee_name", "model": "generic"}]}]}
    assert e32_valves.decode_config(record) == record
    for name in ("Kraan woonkamer", "climate.", "climate.Kraan", "climate.a-b", "sensor.trv", "climate." + "x" * 57):
        bad = deepcopy(record)
        bad["rooms"][0]["valves"][0]["name"] = name
        assert e32_valves.decode_config(bad) is None, name
        assert not e32_valves.valid_entity(name), name
    assert e32_valves.valid_entity("climate." + "x" * 56)
    assert "ha_climate" in e32_valves.MODELS and "ha_climate" not in e32_valves.ZIGBEE_MODELS
