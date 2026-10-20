
"""Native entity-platform acceptance, including existing registry identity."""
from datetime import timedelta
import logging

import pytest
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.helpers import entity_registry as er, device_registry as dr

from custom_components.open_thermostat.v1_climate import async_setup_entry as setup_climate
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_model import RoomDecision

from test_v1_native import room, entry, LocalTransport


@pytest.mark.asyncio
async def test_native_entity_platform_preserves_existing_entity_id_and_subentry(hass):
    binding = room(hass)
    parent = entry(hass, enabled=True, room=binding)
    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "climate", "open_thermostat", "fixture_room_a1b2c3d4_climate",
        config_entry=parent, suggested_object_id="existing_bathroom_thermostat")
    original_entity_id = existing.entity_id
    original_id = existing.id
    dr.async_get(hass).async_get_or_create(
        config_entry_id=parent.entry_id, identifiers={("open_thermostat", "fixture")},
        name="OpenThermostat")
    runtime = ShadowRuntime(hass, parent, [binding])
    runtime.attach_transport(LocalTransport())
    hass.data["open_thermostat"] = {parent.entry_id: {"v1_runtime": runtime}}
    await runtime.async_start()
    platform = EntityPlatform(
        hass=hass, logger=logging.getLogger(__name__), domain="climate",
        platform_name="open_thermostat", platform=None,
        scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = parent
    try:
        tasks = []
        def add(entities, *, config_subentry_id=None):
            tasks.append(hass.async_create_task(platform.async_add_entities(
                entities, config_subentry_id=config_subentry_id)))
        await setup_climate(hass, parent, add)
        import asyncio
        await asyncio.gather(*tasks)
        assert original_entity_id in platform.entities
        registered = registry.async_get(original_entity_id)
        assert registered.id == original_id
        assert registered.config_subentry_id == next(iter(parent.subentries))
        runtime.apply_confirmed_state(binding.room_id, RoomDecision(2100, 1950, True, "shadow_demand"))
        await hass.async_block_till_done()
        state = hass.states.get(original_entity_id)
        assert state.attributes["temperature"] == 21
        assert state.attributes["hvac_action"] == "idle"
        assert state.attributes["simulated_demand"] is True
    finally:
        await platform.async_reset()
        await runtime.async_stop()
    assert not runtime._listeners
