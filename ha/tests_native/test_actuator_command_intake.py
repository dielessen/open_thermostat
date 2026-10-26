"""Native HA services/registries only; no MQTT, real device or actuation admission."""
import asyncio
from dataclasses import FrozenInstanceError, asdict, replace

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.open_thermostat.v1_profile_c import (
    ActuatorServiceReceipt, ProfileCActuator, RoomTargetCommand,
)
from test_v1_native import room


def setup(hass):
    binding = room(hass)
    calls = []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    actuator = ProfileCActuator(hass, binding.actuators[0].entity_id,
                                qualified_profile=True, authorize=lambda: True)
    return actuator, calls


def command(hass, sequence=1, target=2050, budget=1):
    return RoomTargetCommand(sequence, target, hass.loop.time() + budget)


@pytest.mark.asyncio
async def test_duplicate_returns_immutable_historical_receipt_without_another_service_call(hass):
    actuator, calls = setup(hass)
    original = command(hass, target=2010)
    result = await actuator.async_apply_command(original)
    assert asdict(result) == dict(sequence=1, requested_centi_c=2010, native_target=20.0,
        native_unit='°C', duplicate=False, status='ha_action_accepted', scope='service_acceptance_only',
        device_reported=False, valve_ready=False, control_qualified=False)
    with pytest.raises(FrozenInstanceError):
        result.valve_ready = True
    with pytest.raises(TypeError):
        ActuatorServiceReceipt(1, 2010, 20, '°C', valve_ready=True)
    # Later device metadata cannot reinterpret the unit of this historical result.
    state = hass.states.get(actuator.entity_id)
    hass.states.async_set(actuator.entity_id, 'unavailable', dict(state.attributes))
    replay = await actuator.async_apply_command(original)
    assert replay == replace(result, duplicate=True)
    assert len(calls) == 1 and calls[0]['temperature'] == 20


@pytest.mark.asyncio
async def test_receipt_uses_actual_native_fahrenheit_target_not_requested_celsius(hass):
    actuator, calls = setup(hass)
    state = hass.states.get(actuator.entity_id)
    attrs = dict(state.attributes, unit_of_measurement='°F', min_temp=41, max_temp=86, target_temp_step=1)
    hass.states.async_set(actuator.entity_id, 'heat', attrs)
    result = await actuator.async_apply_command(command(hass, target=2010))
    assert (result.requested_centi_c, result.native_target, result.native_unit) == (2010, 68, '°F')
    assert calls[0]['temperature'] == 68
    assert not result.device_reported and not result.valve_ready and not result.control_qualified


@pytest.mark.asyncio
async def test_pending_exact_duplicate_shares_one_dispatch_and_original_outcome(hass):
    actuator, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        started.set()
        await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    original = command(hass)
    first = asyncio.create_task(actuator.async_apply_command(original))
    await started.wait()
    duplicate = asyncio.create_task(actuator.async_apply_command(original))
    await asyncio.sleep(0)
    assert len(calls) == 1 and actuator._request == 1
    release.set()
    result, repeated = await asyncio.gather(first, duplicate)
    assert repeated == replace(result, duplicate=True)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['target', 'deadline'])
async def test_same_sequence_with_changed_payload_never_dispatches(hass, changed):
    actuator, calls = setup(hass)
    original = command(hass)
    await actuator.async_apply_command(original)
    altered = replace(original, target_centi_c=2100) if changed == 'target' else replace(original, deadline=original.deadline+.01)
    with pytest.raises(HomeAssistantError, match='payload changed'):
        await actuator.async_apply_command(altered)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_highwater_rejects_evicted_old_commands_and_sequence_wrap(hass):
    actuator, calls = setup(hass)
    old = command(hass)
    await actuator.async_apply_command(old)
    last = command(hass, sequence=4294967295, target=1900)
    await actuator.async_apply_command(last)
    for stale in (old, command(hass, sequence=2)):
        with pytest.raises(HomeAssistantError, match='high-water'):
            await actuator.async_apply_command(stale)
    assert (await actuator.async_apply_command(last)).duplicate
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_original_deadline_includes_queue_time_and_expired_repeat_cannot_retry(hass):
    actuator, calls = setup(hass)
    original = command(hass, budget=.02)
    await actuator._lock.acquire()
    task = asyncio.create_task(actuator.async_apply_command(original))
    try:
        await asyncio.sleep(.04)
        assert task.done()
        with pytest.raises(HomeAssistantError, match='before dispatch'):
            await task
        with pytest.raises(HomeAssistantError, match='before dispatch'):
            await actuator.async_apply_command(original)
        assert calls == [] and not actuator._outcome_unknown
    finally:
        actuator._lock.release()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('patch', [
    {'sequence':0}, {'sequence':True}, {'sequence':4294967296},
    {'target_centi_c':True}, {'target_centi_c':20.5}, {'target_centi_c':499}, {'target_centi_c':3501},
    {'deadline':True}, {'deadline':float('nan')}, {'deadline':float('inf')},
    {'deadline':2**10000}, {'deadline':0},
])
async def test_invalid_commands_never_consume_admission_or_call_a_service(hass, patch):
    actuator, calls = setup(hass)
    with pytest.raises(HomeAssistantError):
        await actuator.async_apply_command(replace(command(hass), **patch))
    assert actuator._command_sequence == 0 and actuator._request == 0 and calls == []


@pytest.mark.asyncio
async def test_expired_or_overlong_new_command_cannot_invent_a_new_budget(hass):
    actuator, calls = setup(hass)
    for value in (None, {}, command(hass, budget=-.01), command(hass, budget=60)):
        with pytest.raises(HomeAssistantError):
            await actuator.async_apply_command(value)
    assert calls == [] and actuator._command_sequence == 0


@pytest.mark.asyncio
async def test_cancelling_duplicate_does_not_cancel_dispatched_original(hass):
    actuator, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        started.set()
        await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    original = command(hass)
    first = asyncio.create_task(actuator.async_apply_command(original))
    await started.wait()
    duplicate = asyncio.create_task(actuator.async_apply_command(original))
    await asyncio.sleep(0)
    duplicate.cancel()
    assert isinstance((await asyncio.gather(duplicate, return_exceptions=True))[0], asyncio.CancelledError)
    release.set()
    result = await first
    assert result.status == 'ha_action_accepted' and not actuator._outcome_unknown
    assert (await actuator.async_apply_command(original)).duplicate
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_service_failure_is_cached_and_new_command_cannot_clear_uncertainty(hass):
    actuator, calls = setup(hass)
    async def fail(call):
        calls.append(call.data)
        raise HomeAssistantError('synthetic device path failure')
    hass.services.async_register('climate', 'set_temperature', fail)
    original = command(hass)
    for value in (original, original, command(hass, sequence=2)):
        with pytest.raises(HomeAssistantError):
            await actuator.async_apply_command(value)
    assert actuator._outcome_unknown and len(calls) == 1


@pytest.mark.asyncio
async def test_pre_dispatch_failure_is_cached_without_requalifying_a_duplicate(hass):
    actuator, calls = setup(hass)
    actuator._qualified = False
    original = command(hass)
    with pytest.raises(HomeAssistantError, match='disabled'):
        await actuator.async_apply_command(original)
    actuator._qualified = True
    with pytest.raises(HomeAssistantError, match='disabled'):
        await actuator.async_apply_command(original)
    assert calls == [] and not actuator._outcome_unknown
    assert (await actuator.async_apply_command(command(hass, sequence=2))).sequence == 2
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('first_mode', ['sequenced', 'unsequenced'])
async def test_owner_cannot_mix_command_watermark_with_unsequenced_actions(hass, first_mode):
    actuator, calls = setup(hass)
    if first_mode == 'sequenced':
        await actuator.async_apply_command(command(hass))
        with pytest.raises(HomeAssistantError, match='unsequenced action refused'):
            await actuator.async_set_room_target(21)
    else:
        await actuator.async_set_room_target(20)
        with pytest.raises(HomeAssistantError, match='unsequenced actions'):
            await actuator.async_apply_command(command(hass))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_newer_queued_command_retires_older_without_cache_result_misattribution(hass):
    actuator, calls = setup(hass)
    first, latest = command(hass), command(hass, sequence=2, target=1900)
    await actuator._lock.acquire()
    older = asyncio.create_task(actuator.async_apply_command(first))
    await asyncio.sleep(0)
    newer = asyncio.create_task(actuator.async_apply_command(latest))
    await asyncio.sleep(0)
    actuator._lock.release()
    replies = await asyncio.gather(older, newer, return_exceptions=True)
    assert isinstance(replies[0], HomeAssistantError) and 'superseded' in str(replies[0])
    assert replies[1].sequence == 2 and replies[1].native_target == 19
    assert (await actuator.async_apply_command(latest)).sequence == 2
    assert len(calls) == 1 and calls[0]['temperature'] == 19


@pytest.mark.asyncio
async def test_completed_duplicate_after_deadline_is_historical_without_new_admission(hass):
    actuator, calls = setup(hass)
    original = command(hass, budget=.1)
    first = await actuator.async_apply_command(original)
    await asyncio.sleep(.12)
    replay = await actuator.async_apply_command(original)
    assert replay == replace(first, duplicate=True)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_cancelling_inflight_owner_settles_duplicate_and_requires_outcome_review(hass):
    actuator, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        started.set()
        await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    original = command(hass)
    first = asyncio.create_task(actuator.async_apply_command(original))
    await started.wait()
    duplicate = asyncio.create_task(actuator.async_apply_command(original))
    await asyncio.sleep(0)
    first.cancel()
    try:
        replies = await asyncio.gather(first, duplicate, return_exceptions=True)
        assert isinstance(replies[0], asyncio.CancelledError)
        assert isinstance(replies[1], HomeAssistantError) and 'owner cancelled' in str(replies[1])
        with pytest.raises(HomeAssistantError, match='requalification required'):
            await actuator.async_apply_command(command(hass, sequence=2))
        assert actuator._outcome_unknown and len(calls) == 1
    finally:
        release.set()
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_cancelling_queued_owner_caches_failure_but_does_not_invent_uncertain_dispatch(hass):
    actuator, calls = setup(hass)
    original = command(hass)
    await actuator._lock.acquire()
    first = asyncio.create_task(actuator.async_apply_command(original))
    await asyncio.sleep(0)
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    actuator._lock.release()
    with pytest.raises(HomeAssistantError, match='owner cancelled'):
        await actuator.async_apply_command(original)
    assert not actuator._outcome_unknown and calls == []
    assert (await actuator.async_apply_command(command(hass, sequence=2))).sequence == 2
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_changed_pending_duplicate_does_not_supersede_original_action(hass):
    actuator, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        started.set()
        await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    original = command(hass)
    first = asyncio.create_task(actuator.async_apply_command(original))
    await started.wait()
    try:
        with pytest.raises(HomeAssistantError, match='payload changed'):
            await actuator.async_apply_command(replace(original, target_centi_c=1900))
        release.set()
        assert (await first).requested_centi_c == 2050
        assert (await actuator.async_apply_command(original)).native_target == 20.5
        assert len(calls) == 1 and not actuator._outcome_unknown
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)


@pytest.mark.asyncio
async def test_inflight_and_newer_command_keep_their_own_receipts_and_only_latest_cache(hass):
    actuator, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        if len(calls) == 1:
            started.set()
            await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    first_command, latest = command(hass), command(hass, sequence=2, target=1900)
    first = asyncio.create_task(actuator.async_apply_command(first_command))
    await started.wait()
    second = asyncio.create_task(actuator.async_apply_command(latest))
    await asyncio.sleep(0)
    release.set()
    a, b = await asyncio.gather(first, second)
    assert (a.sequence, a.native_target) == (1, 20.5)
    assert (b.sequence, b.native_target) == (2, 19)
    assert await actuator.async_apply_command(latest) == replace(b, duplicate=True)
    with pytest.raises(HomeAssistantError, match='high-water'):
        await actuator.async_apply_command(first_command)
    assert [call['temperature'] for call in calls] == [20.5, 19]


@pytest.mark.asyncio
async def test_original_service_timeout_settles_all_duplicates_without_renewing_budget(hass):
    actuator, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        started.set()
        await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    original = command(hass, budget=.03)
    first = asyncio.create_task(actuator.async_apply_command(original))
    await started.wait()
    duplicate = asyncio.create_task(actuator.async_apply_command(original))
    try:
        results = await asyncio.gather(first, duplicate, return_exceptions=True)
        assert all(isinstance(r, HomeAssistantError) and 'physical outcome unknown' in str(r) for r in results)
        assert actuator._outcome_unknown and len(calls) == 1
        with pytest.raises(HomeAssistantError, match='physical outcome unknown'):
            await actuator.async_apply_command(original)
        assert len(calls) == 1
    finally:
        release.set()
        await hass.async_block_till_done()
