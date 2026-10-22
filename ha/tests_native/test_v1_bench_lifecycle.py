import asyncio
import pytest
from test_v1_bench_actions import action_system, action, arguments
from custom_components.open_thermostat.v1_bench_actions import KEY
import custom_components.open_thermostat.v1_bench_actions as actions

@pytest.mark.asyncio
async def test_native_deadline_callback_stops_and_restores(action_system, monkeypatch):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    timers = []
    real = actions.async_call_later
    def later(hass, delay, cb):
        timers.append(cb)
        return real(hass, delay, cb)
    monkeypatch.setattr(actions, "async_call_later", later)
    await action(hass, "start", arguments(e))
    timers[0](None)
    manager = hass.data[KEY][e.entry_id]
    async with asyncio.timeout(5):
        while manager.phase != "stopped": await asyncio.sleep(0.01)
    assert manager.reason == "finite_bench_expired"
    assert manager.restored and runtime._bench_owner is None
    assert "zigbee2mqtt/selected" in removed

@pytest.mark.asyncio
async def test_normal_refresh_cannot_replace_bench_mapping(action_system):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    await action(hass, "start", arguments(e))
    connection.enqueue(("refresh", None))
    await connection.queue.join()
    manager = hass.data[KEY][e.entry_id]
    async with asyncio.timeout(5):
        while manager.phase != "stopped": await asyncio.sleep(0.01)
    assert manager.reason == "configuration_or_schedule_changed"
    assert manager.restored

@pytest.mark.asyncio
async def test_disabled_runtime_cannot_start(action_system):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    from homeassistant.exceptions import HomeAssistantError
    runtime._active = False
    with pytest.raises(HomeAssistantError):
        await action(hass, "start", arguments(e))
    assert runtime._bench_owner is None
    runtime._active = True

@pytest.mark.asyncio
async def test_fw_offline_aborts_with_ha_broker_still_connected(action_system, monkeypatch):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    await action(hass, "start", arguments(e))
    manager = hass.data[KEY][e.entry_id]
    from unittest.mock import AsyncMock
    monkeypatch.setattr(manager, "reconfigure", AsyncMock(side_effect=TimeoutError("FW offline")))
    emit("fixture/v1/fw/availability", "offline", raw=True)
    await connection.queue.join()
    assert manager.listener.gate.phase == "closed"
    assert not connection.closed  # HA MQTT path itself was never disconnected
    async with asyncio.timeout(5):
        while manager.phase not in ("stopped", "blocked"):
            await asyncio.sleep(0.01)
    assert "firmware" in manager.reason
    assert "zigbee2mqtt/selected" in removed
    assert manager.closed
    assert manager.samples == 0
    assert manager.phase == "blocked" and runtime._bench_owner == binding.room_id

@pytest.mark.asyncio
async def test_poll_only_readiness_loss_without_notifications(action_system, monkeypatch):
    from unittest.mock import AsyncMock
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    await action(hass, "start", arguments(e))
    manager = hass.data[KEY][e.entry_id]
    monkeypatch.setattr(manager, "reconfigure", AsyncMock(side_effect=TimeoutError("lease expired")))
    async def expire_without_changed():
        connection.client.verified = False
    monkeypatch.setattr(connection.client, "poll", expire_without_changed)
    connection.enqueue(("poll", None))
    await connection.queue.join()
    assert manager.listener.gate.phase == "closed"
    async with asyncio.timeout(5):
        while manager.phase != "blocked": await asyncio.sleep(0.01)
    assert manager.reason.startswith("firmware_availability_or_session_lost")
    assert runtime._bench_owner == binding.room_id
    assert not connection.closed
