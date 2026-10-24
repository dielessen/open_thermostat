"""Synthetic native HA services, no device/network IO or actuation admission."""
import asyncio
import pytest
from homeassistant.exceptions import HomeAssistantError
from custom_components.open_thermostat.v1_profile_c import ProfileCActuator
from test_v1_native import room


def fixture(hass, monkeypatch, timeout=.02):
    binding=room(hass)
    monkeypatch.setattr('custom_components.open_thermostat.v1_profile_c.ACTION_TIMEOUT_SECONDS',timeout)
    return ProfileCActuator(hass,binding.actuators[0].entity_id,qualified_profile=True,authorize=lambda:True)


@pytest.mark.asyncio
async def test_waiting_for_owner_expires_without_dispatch(hass,monkeypatch):
    actuator=fixture(hass,monkeypatch);calls=[]
    hass.services.async_register('climate','set_temperature',lambda call:calls.append(call.data))
    await actuator._lock.acquire()
    task=asyncio.create_task(actuator.async_set_room_target(21))
    try:
        await asyncio.sleep(.05)
        assert task.done(), 'command waited beyond its original lifetime'
        with pytest.raises(HomeAssistantError,match='before dispatch'):
            await task
        assert calls==[]
    finally:
        actuator._lock.release()
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_newest_queued_target_retires_all_older_targets(hass,monkeypatch):
    actuator=fixture(hass,monkeypatch,1);calls=[]
    hass.services.async_register('climate','set_temperature',lambda call:calls.append(call.data))
    await actuator._lock.acquire();tasks=[]
    try:
        for value in [21,22,19]:
            tasks.append(asyncio.create_task(actuator.async_set_room_target(value)))
            await asyncio.sleep(0)
    finally:actuator._lock.release()
    replies=await asyncio.gather(*tasks,return_exceptions=True)
    assert all(isinstance(r,HomeAssistantError) and 'superseded' in str(r) for r in replies[:2])
    assert replies[2]==19 and [c['temperature'] for c in calls]==[19]


@pytest.mark.asyncio
async def test_cancelled_newest_target_does_not_resurrect_an_older_target(hass,monkeypatch):
    actuator=fixture(hass,monkeypatch,1);calls=[]
    hass.services.async_register('climate','set_temperature',lambda call:calls.append(call.data))
    await actuator._lock.acquire()
    older=asyncio.create_task(actuator.async_set_room_target(21));await asyncio.sleep(0)
    newest=asyncio.create_task(actuator.async_set_room_target(19));await asyncio.sleep(0)
    newest.cancel();await asyncio.gather(newest,return_exceptions=True);actuator._lock.release()
    with pytest.raises(HomeAssistantError,match='superseded'):await older
    assert calls==[]
    assert await actuator.async_set_room_target(20)==20


@pytest.mark.asyncio
async def test_synchronous_authorization_cannot_overrun_original_deadline(hass,monkeypatch):
    import time
    actuator=fixture(hass,monkeypatch);calls=[];checks=[]
    hass.services.async_register('climate','set_temperature',lambda call:calls.append(call.data))
    def authorize():
        checks.append(True)
        if len(checks)==2:time.sleep(.04)
        return True
    actuator._authorize=authorize
    with pytest.raises(HomeAssistantError,match='before dispatch'):
        await actuator.async_set_room_target(21)
    assert calls==[] and not actuator._outcome_unknown
    assert await actuator.async_set_room_target(20)==20


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',['timeout','cancel','service_error','late_completion'])
async def test_uncertain_inflight_action_blocks_queued_and_future_actions(hass,monkeypatch,outcome):
    import time
    actuator=fixture(hass,monkeypatch,.05 if outcome=='timeout' else 1)
    calls=[];started=asyncio.Event();release=asyncio.Event()
    async def handler(call):
        calls.append(call.data);started.set()
        if outcome=='service_error':raise HomeAssistantError('synthetic service failure')
        if outcome=='late_completion':
            time.sleep(1.02)
            return
        await release.wait()
    hass.services.async_register('climate','set_temperature',handler)
    first=asyncio.create_task(actuator.async_set_room_target(21))
    await started.wait()
    second=asyncio.create_task(actuator.async_set_room_target(19))
    if outcome=='cancel':first.cancel()
    try:
        results=await asyncio.gather(first,second,return_exceptions=True)
        if outcome=='cancel':assert isinstance(results[0],asyncio.CancelledError)
        else:assert isinstance(results[0],HomeAssistantError) and 'physical outcome unknown' in str(results[0])
        assert isinstance(results[1],HomeAssistantError)
        with pytest.raises(HomeAssistantError,match='requalification required'):
            await actuator.async_set_room_target(18)
        assert len(calls)==1 and actuator._outcome_unknown
    finally:
        release.set()
        for task in [first,second]:
            if not task.done():task.cancel()
        await asyncio.gather(first,second,return_exceptions=True)


@pytest.mark.asyncio
async def test_inflight_acceptance_is_historical_but_only_newest_waiting_target_dispatches(hass,monkeypatch):
    actuator=fixture(hass,monkeypatch,1);calls=[];started=asyncio.Event();release=asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        if len(calls)==1:
            started.set();await release.wait()
    hass.services.async_register('climate','set_temperature',handler)
    first=asyncio.create_task(actuator.async_set_room_target(21));await started.wait()
    middle=asyncio.create_task(actuator.async_set_room_target(22));await asyncio.sleep(0)
    last=asyncio.create_task(actuator.async_set_room_target(19));await asyncio.sleep(0)
    release.set();results=await asyncio.gather(first,middle,last,return_exceptions=True)
    assert results[0]==21 and isinstance(results[1],HomeAssistantError) and 'superseded' in str(results[1]) and results[2]==19
    assert [c['temperature'] for c in calls]==[21,19]


@pytest.mark.asyncio
async def test_wait_and_service_share_one_budget_not_two_full_windows(hass,monkeypatch):
    actuator=fixture(hass,monkeypatch,.1);calls=[]
    async def handler(call):
        calls.append(call.data);await asyncio.sleep(.07)
    hass.services.async_register('climate','set_temperature',handler)
    await actuator._lock.acquire()
    task=asyncio.create_task(actuator.async_set_room_target(21));await asyncio.sleep(.06)
    actuator._lock.release()
    with pytest.raises(HomeAssistantError,match='physical outcome unknown'):await task
    assert len(calls)==1 and actuator._outcome_unknown
