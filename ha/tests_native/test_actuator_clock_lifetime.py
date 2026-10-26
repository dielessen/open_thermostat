"""Real HA registries/services; local clock proxy only, never physical IO."""
import asyncio
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.open_thermostat.v1_profile_c import ProfileCActuator, RoomTargetCommand
from test_v1_native import room


class LocalClockHass:
    def __init__(self, hass, clock):
        self._hass = hass
        self.loop = SimpleNamespace(time=lambda: clock[0], create_future=hass.loop.create_future)

    def __getattr__(self, name):
        return getattr(self._hass, name)


def setup(hass):
    binding = room(hass)
    clock = [hass.loop.time()]
    actuator = ProfileCActuator(LocalClockHass(hass, clock), binding.actuators[0].entity_id,
                               qualified_profile=True, authorize=lambda: True)
    calls = []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    return actuator, clock, calls


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['backward', float('nan'), float('inf'), -1, True, 10**400])
async def test_clock_loss_at_final_authorization_blocks_dispatch_and_stays_retired(hass, invalid):
    actuator, clock, calls = setup(hass)
    original = clock[0]
    checks = 0

    def authorize():
        nonlocal checks
        checks += 1
        if checks == 2:
            clock[0] = original - 1 if invalid == 'backward' else invalid
        return True

    actuator._authorize = authorize
    with pytest.raises(HomeAssistantError, match='clock'):
        await actuator.async_set_room_target(21)
    assert calls == []
    clock[0] = original + .01
    actuator._authorize = lambda: True
    with pytest.raises(HomeAssistantError, match='requalification'):
        await actuator.async_set_room_target(19)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['backward', float('nan'), float('inf'), True])
async def test_clock_loss_during_service_retires_unknown_physical_outcome(hass, invalid):
    actuator, clock, calls = setup(hass)
    original = clock[0]

    def handler(call):
        calls.append(call.data)
        clock[0] = original - 1 if invalid == 'backward' else invalid

    hass.services.async_register('climate', 'set_temperature', handler)
    with pytest.raises(HomeAssistantError, match='physical outcome unknown'):
        await actuator.async_set_room_target(21)
    assert len(calls) == 1 and actuator._outcome_unknown
    clock[0] = original + .01
    with pytest.raises(HomeAssistantError, match='requalification'):
        await actuator.async_set_room_target(19)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_clock_reversal_between_commands_requires_new_owner_but_keeps_historical_receipt(hass):
    actuator, clock, calls = setup(hass)
    original = clock[0]
    command = RoomTargetCommand(1, 2100, original + 1)
    receipt = await actuator.async_apply_command(command)
    clock[0] = original - .1
    with pytest.raises(HomeAssistantError, match='clock'):
        await actuator.async_apply_command(RoomTargetCommand(2, 1900, original + 1))
    clock[0] = original + .01
    historical = await actuator.async_apply_command(command)
    assert historical.duplicate and historical.native_target == receipt.native_target
    assert not historical.device_reported and not historical.control_qualified
    with pytest.raises(HomeAssistantError, match='requalification'):
        await actuator.async_apply_command(RoomTargetCommand(3, 1900, original + 1))
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('refusal', ['false', 'exception'])
async def test_refusing_authorization_cannot_hide_clock_loss(hass, refusal):
    actuator, clock, calls = setup(hass)
    original = clock[0]

    def authorize():
        clock[0] = original - 1
        if refusal == 'exception':
            raise HomeAssistantError('synthetic owner refusal')
        return False

    actuator._authorize = authorize
    with pytest.raises(HomeAssistantError, match='clock'):
        await actuator.async_set_room_target(21)
    clock[0] = original + .01
    actuator._authorize = lambda: True
    with pytest.raises(HomeAssistantError, match='requalification'):
        await actuator.async_set_room_target(19)
    assert calls == []


@pytest.mark.asyncio
async def test_waiting_commands_share_clock_retirement_without_dispatch(hass):
    actuator, clock, calls = setup(hass)
    original = clock[0]
    await actuator._lock.acquire()
    tasks = []
    try:
        for target in (21, 19):
            tasks.append(asyncio.create_task(actuator.async_set_room_target(target)))
            await asyncio.sleep(0)
        clock[0] = original - 1
    finally:
        actuator._lock.release()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(result, HomeAssistantError) for result in results)
    clock[0] = original + .01
    with pytest.raises(HomeAssistantError, match='requalification'):
        await actuator.async_set_room_target(18)
    assert calls == []
