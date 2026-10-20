import asyncio
from unittest.mock import AsyncMock
import pytest
from homeassistant.helpers import entity_registry as er
from test_v1_bench_actions import action_system, action, arguments
from test_v1_native import entry, room
from custom_components.open_thermostat import async_setup_entry
from custom_components.open_thermostat.v1_bench_actions import KEY
from custom_components.open_thermostat.v1_bench_mqtt import NativeBenchListener

@pytest.mark.asyncio
async def test_failed_entry_setup_unregisters_manager_and_actions(hass, monkeypatch):
    e = entry(hass, enabled=False, room=room(hass))
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups",
                        AsyncMock(side_effect=RuntimeError("platform setup failed")))
    with pytest.raises(RuntimeError):
        await async_setup_entry(hass, e)
    assert e.entry_id not in hass.data.get(KEY, {})
    assert not hass.services.has_service("open_thermostat", "source_bench_start")
    assert e.entry_id not in hass.data.get("open_thermostat", {})

@pytest.mark.asyncio
async def test_binding_registry_edit_closes_and_restores(action_system):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    await action(hass, "start", arguments(e))
    er.async_get(hass).async_update_entity(runtime.resolved(binding.temperature),
                                         new_entity_id="sensor.bench_renamed")
    manager = hass.data[KEY][e.entry_id]
    async with asyncio.timeout(5):
        while manager.phase != "stopped": await asyncio.sleep(0.01)
    assert manager.reason == "binding_changed"
    assert manager.restored and runtime._bench_owner is None

@pytest.mark.asyncio
async def test_source_listener_setup_failure_restores_mapping(action_system, monkeypatch):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    monkeypatch.setattr(NativeBenchListener, "async_start",
                        AsyncMock(side_effect=RuntimeError("subscribe failed")))
    with pytest.raises(RuntimeError):
        await action(hass, "start", arguments(e))
    manager = hass.data[KEY][e.entry_id]
    assert manager.phase == "stopped" and manager.restored
    assert runtime._bench_owner is None
    assert connection.bench is None
