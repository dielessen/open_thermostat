"""Test the real HA manager schema-validation step before the flow callback."""
from dataclasses import replace
import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat.v1_config_flow import ZoneSubentryFlow
from test_v1_native import room, entry, reference

@pytest.mark.asyncio
@pytest.mark.parametrize("clear", [True, False])
async def test_optional_schema_clear_or_preserve(hass, clear):
    binding = room(hass)
    registry = er.async_get(hass)
    wall = registry.async_get_or_create("number", "fixture_driver", "wall_control")
    schedule = registry.async_get_or_create("schedule", "schedule", "week")
    binding = replace(binding, setpoint=reference(hass, wall.entity_id),
                      schedule=reference(hass, schedule.entity_id))
    parent = entry(hass, room=binding)
    old = next(iter(parent.subentries.values()))
    stable_id = old.subentry_id
    flow = ZoneSubentryFlow()
    flow.hass, flow.handler = hass, (parent.entry_id, "zone")
    flow.context = {"source": "reconfigure", "subentry_id": stable_id}
    form = await flow.async_step_reconfigure()
    payload = {"name": "Edited", "temperature_entity": binding.temperature.entity_id,
               "actuator_entities": [binding.actuators[0].entity_id]}
    if not clear:
        payload.update(setpoint_entity=wall.entity_id, schedule_entity=schedule.entity_id)
    validated = form["data_schema"](payload)
    if clear:
        assert "setpoint_entity" not in validated
        assert "schedule_entity" not in validated
    result = await flow.async_step_reconfigure(validated)
    assert result["type"] == "abort"
    assert old.subentry_id == stable_id and old.data["room_id"] == binding.room_id
    assert (old.data["setpoint"] is None) is clear
    assert (old.data["schedule"] is None) is clear
