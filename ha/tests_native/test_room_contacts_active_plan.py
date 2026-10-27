"""Contact edits on the existing native HA worker and real C++ complete plan."""
from copy import deepcopy
import json
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from test_native_control_plan import native_plan, native_two
from test_controller_connection import drive


def sources(hass):
    result=[]
    for kind in ('window','door'):
        row=er.async_get(hass).async_get_or_create('binary_sensor','plan_contacts','pinned_'+kind)
        hass.states.async_set(row.entity_id,'off',{'device_class':kind})
        result.append(row)
    return result


def install_reload(hass,n):
    async def reload(entry_id):
        assert entry_id==n.parent.entry_id
        n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None)
        await n.stop()
        n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None)
        await n.start()
        n.parent._async_set_state(hass,ConfigEntryState.LOADED,None)
        return True
    n.reload.side_effect=reload


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_active_contacts_apply_and_remove_through_same_source_with_exact_durable_readback(native_plan,hass):
    n=native_plan;await n.apply();source=n.source;install_reload(hass,n)
    sensors=sources(hass);model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    settings=deepcopy(model['settings']);settings['contact_entities']=[c.entity_id for c in sensors]
    settings['contact_policy']={'maximum_age_ms':3600000,'open_delay_ms':0,'close_delay_ms':0}
    before=deepcopy(n.client.journal['accepted']['config']);previous=n.connection
    # Each real reload retires the previous 15-second lease before a new
    # session can own the bus. Allow the finite peer to cross that deadline.
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=1600)
    assert saved['settings']==settings and not saved['apply_pending']
    assert previous.worker.done() and n.connection is not previous and n.source is source
    accepted=n.client.journal['accepted']['config']
    assert accepted['mapping']==before['mapping'] and accepted['profile_digest']==before['profile_digest']
    assert accepted['revision']==before['revision']+1
    assert accepted['zones'][0]['contacts']=={'maximum_age_ms':3600000}
    assert 'comfort' not in accepted['zones'][0]
    assert n.runtime.rooms[n.rad.room_id].comfort is None
    assert json.loads((await n.peer.request('durable_readback'))['stored'])==accepted
    assert [c.entity.unique_id for c in n.runtime.rooms[n.rad.room_id].contacts]==[c.unique_id for c in sensors]
    await n.settle(16,22)
    assert n.runtime.decisions[n.rad.room_id].demand
    original=n.runtime.observations[n.rad.room_id]
    hass.states.async_set(sensors[0].entity_id,'on',{'device_class':'window'})
    await hass.async_block_till_done();await n.drain()
    assert n.runtime.observations[n.rad.room_id] is original
    assert not n.runtime.decisions[n.rad.room_id].demand
    assert n.runtime.decisions[n.rad.room_id].reason=='window_open'
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings']);settings['contact_entities']=[]
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=1600)
    assert saved['settings']['contact_entities']==[] and not saved['apply_pending']
    assert n.source is source and not n.runtime.rooms[n.rad.room_id].contacts
    accepted=n.client.journal['accepted']['config']
    assert 'contacts' not in accepted['zones'][0] and 'comfort' not in accepted['zones'][0]
    assert accepted['mapping']==before['mapping'] and accepted['revision']==before['revision']+2
    assert json.loads((await n.peer.request('durable_readback'))['stored'])==accepted


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_older_peer_cannot_save_contact_intent_or_trigger_reload(native_plan,hass):
    n=native_plan;await n.apply();sensors=sources(hass)
    n.client.contacts_supported=False
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings['contact_entities']=[sensors[0].entity_id];before=configuration_snapshot(n.parent)
    with pytest.raises(ValueError,match='^contact_capability_unavailable$'):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    assert configuration_snapshot(n.parent)==before and n.runtime.enabled
    assert (await n.peer.request('durable_readback'))['writes']==1
    n.reload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_contact_loss_during_active_compile_refuses_entire_edit_before_reload(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat import v1_mqtt
    n=native_plan;await n.apply();sensor=sources(hass)[0]
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings['contact_entities']=[sensor.entity_id];before=configuration_snapshot(n.parent)
    original=v1_mqtt.async_room_schedule
    async def compile(*args,**kwargs):
        result=await original(*args,**kwargs)
        er.async_get(hass).async_remove(sensor.entity_id)
        return result
    monkeypatch.setattr(v1_mqtt,'async_room_schedule',compile)
    with pytest.raises(ValueError):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    assert configuration_snapshot(n.parent)==before and n.runtime.enabled
    assert (await n.peer.request('durable_readback'))['writes']==1
    n.reload.assert_not_awaited()
