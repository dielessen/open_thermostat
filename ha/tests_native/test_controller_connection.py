"""Normal explicit apply over real HA Store/worker and actual C++ packet peer."""
import asyncio
import pytest

from test_native_control_plan import native_plan, native_two
from custom_components.open_thermostat import controller_connection as operation
from custom_components.open_thermostat.controller_link import ControllerLinkError
from custom_components.open_thermostat.product import configuration_snapshot


async def drive(n, awaitable, *, drop_snapshots=False):
    task=asyncio.create_task(awaitable)
    try:
        for count in range(800):
            await n.connection.queue.join()
            while n.pending:
                topic,raw=n.pending.popleft()
                reply=await n.peer.request('receive',topic=topic,raw=raw)
                frames=[f for f in reply['frames'] if not (drop_snapshots and f['topic']=='fw/config_snapshot')]
                await n.deliver(frames)
            if task.done():
                return await task
            # Slow monotone peer time, never overwrite a grant/readiness flag.
            if count and count%50==0:n.peer.clock[0]+=1
            await n.event('tick')
            await n.client.poll()
            await asyncio.sleep(.001)
        raise AssertionError('bounded real packet operation did not finish')
    finally:
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_explicit_saved_plan_uses_same_native_worker_and_verified_cpp_readback(native_plan,hass):
    n=native_plan;before=configuration_snapshot(n.parent)
    old_worker=n.connection.worker
    result=await drive(n,operation.async_synchronise_controller_plan(hass,n.parent,n.source,before))
    assert result['room_plan_applied'] and result['mqtt_session_verified']
    assert result['revision']==1 and result['qualified_temperature_rooms']==[]
    assert result['authorizes_physical_outputs'] is False
    assert n.connection.worker is old_worker and n.client.current_native_room_state_verified
    assert n.client.ready and n.client.journal['staged'] is None
    assert configuration_snapshot(n.parent)==before
    assert sum(op=='receive' and fields.get('topic')=='ha/config' for op,fields,_ in n.peer.trace)==1
    assert not n.runtime.observations[n.rad.room_id].quality=='qualified'


@pytest.mark.asyncio
async def test_cpp_ack_without_snapshots_never_completes_normal_apply(native_plan,hass,monkeypatch):
    n=native_plan;before=configuration_snapshot(n.parent)
    monkeypatch.setattr(operation,'CONNECTION_TIMEOUT',.15)
    with pytest.raises(ControllerLinkError,match='^controller_plan_unconfirmed$'):
        await drive(n,operation.async_synchronise_controller_plan(hass,n.parent,n.source,before),drop_snapshots=True)
    assert not n.client.current_native_room_state_verified and not n.client.ready
    assert configuration_snapshot(n.parent)==before
    assert any(f['topic']=='fw/config_result' for _,_,reply in n.peer.trace for f in reply['frames'])
    assert sum(op=='receive' and fields.get('topic')=='ha/config' for op,fields,_ in n.peer.trace)==1


@pytest.mark.asyncio
async def test_changed_native_owner_after_prepare_cannot_send_config(native_plan,hass,monkeypatch):
    n=native_plan;before=configuration_snapshot(n.parent)
    original=n.connection.async_graph_command
    state=hass.data['open_thermostat'][n.parent.entry_id]
    async def replace_owner(command,*args):
        result=await original(command,*args)
        if command=='prepare':state['v1_connection']=None
        return result
    monkeypatch.setattr(n.connection,'async_graph_command',replace_owner)
    try:
        with pytest.raises(ControllerLinkError,match='^controller_connection_changed$'):
            await drive(n,operation.async_synchronise_controller_plan(hass,n.parent,n.source,before))
        assert not any(op=='receive' and fields.get('topic')=='ha/config' for op,fields,_ in n.peer.trace)
        assert configuration_snapshot(n.parent)==before
    finally:
        state['v1_connection']=n.connection


@pytest.mark.asyncio
async def test_room_state_receipt_cannot_outlive_deadline_or_reconnect(native_plan,hass):
    n=native_plan;before=configuration_snapshot(n.parent)
    await drive(n,operation.async_synchronise_controller_plan(hass,n.parent,n.source,before))
    assert n.client.current_native_room_state_verified
    scope,received=n.client._native_state_receipt
    # Age a real verified receipt conservatively; no permission is created.
    n.client._native_state_receipt=(scope,n.client.clock()-15)
    assert n.client.ready and not n.client.current_native_room_state_verified
    n.client._native_state_receipt=(scope,received)
    n.client.reset_session()
    assert n.client._native_state_receipt is None and not n.client.current_native_room_state_verified
    assert configuration_snapshot(n.parent)==before
