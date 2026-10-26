"""Active room intent over real HA entry/Store/reload hooks and C++ packet peer."""
from copy import deepcopy
import json

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from test_native_control_plan import native_plan, native_two
from test_controller_connection import drive


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_active_program_save_uses_native_reload_same_source_and_actual_durable_readback(native_plan,hass):
    n=native_plan;await n.apply();source=n.source;first=deepcopy(n.client.journal['accepted'])
    previous=n.connection
    async def reload(entry_id):
        assert entry_id==n.parent.entry_id
        n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None)
        await n.stop()
        n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None)
        await n.start()
        n.parent._async_set_state(hass,ConfigEntryState.LOADED,None)
        return True
    n.reload.side_effect=reload
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    assert model['editable'] and model['program_only'] and not model['apply_pending']
    settings=deepcopy(model['settings']);settings.update(name='Badkamer nieuw',base_centi_c=2300)
    settings['week']={day:[{'start':0,'end':86400,'target_centi_c':2200}] for day in settings['week']}
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings))
    assert previous.worker.done() and n.connection is not previous
    assert saved['settings']['name']=='Badkamer nieuw' and saved['settings']['base_centi_c']==2300
    assert saved['settings']['week']==settings['week'] and not saved['apply_pending']
    assert n.source is source and n.client.native_plan_source==source
    accepted=n.client.journal['accepted'];assert accepted['config']['revision']==2
    assert accepted['config']['mapping']==first['config']['mapping']
    assert accepted['config']['profile_digest']==source.policy.profile_digest
    assert n.client.current_native_room_state_verified and n.client.ready
    durable=await n.peer.request('durable_readback')
    assert json.loads(durable['stored'])==accepted['config'] and durable['writes']==2
    from custom_components.open_thermostat.compact_schedule import expand_schedule
    schedule=expand_schedule(accepted['config']['zones'][0]['schedule'])
    assert {target for _,target in schedule['transitions']}=={2200}
    # A verified saved plan must not manufacture a qualified room measurement.
    assert n.runtime.decisions[n.rad.room_id].target_centi_c is None
    assert n.runtime.decisions[n.rad.room_id].reason=='source_unverified_or_stale'
    assert n.runtime.observations[n.rad.room_id].quality!='qualified' 
    assert sum(op=='initialize_native_local_source' for op,_,_ in n.peer.trace)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
@pytest.mark.parametrize('field,value',[('temperature_entity','sensor.another'),('radiator_entities',[]),
    ('minimum_centi_c',500),('maximum_age_ms',60000),('base_centi_c',True),('base_centi_c',3500)])
async def test_active_program_cannot_silently_change_hardware_profile_or_escape_bounds(native_plan,hass,field,value):
    n=native_plan;await n.apply();before=configuration_snapshot(n.parent)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings']);settings[field]=value
    with pytest.raises(ValueError):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    assert configuration_snapshot(n.parent)==before
    durable=await n.peer.request('durable_readback');assert durable['writes']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_private_credential_change_during_compile_cannot_commit_active_room(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat import v1_mqtt
    n=native_plan;await n.apply();before=configuration_snapshot(n.parent)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings']);settings['base_centi_c']=2300
    original=v1_mqtt.async_room_schedule
    async def compile(*args,**kwargs):
        hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,'controller_password':'test-only-new-value'})
        return await original(*args,**kwargs)
    monkeypatch.setattr(v1_mqtt,'async_room_schedule',compile)
    with pytest.raises(ValueError,match='^setup_changed$'):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    assert configuration_snapshot(n.parent)==before
    assert n.parent.data['controller_password']=='test-only-new-value'
    durable=await n.peer.request('durable_readback');assert durable['writes']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_saved_but_unconfirmed_program_retains_intent_and_explicit_retry_uses_current_worker(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat import controller_connection as operation
    n=native_plan;await n.apply()
    async def reload(entry_id):
        n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None)
        await n.stop();n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None)
        await n.start();n.parent._async_set_state(hass,ConfigEntryState.LOADED,None)
        return True
    n.reload.side_effect=reload
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    settings=deepcopy(model['settings']);settings.update(name='Saved draft',base_centi_c=2300)
    monkeypatch.setattr(operation,'CONNECTION_TIMEOUT',.08)
    with pytest.raises(ValueError,match='^save_uncertain$'):
        await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),drop_snapshots=True)
    pending=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    assert pending['settings']['name']=='Saved draft' and pending['settings']['base_centi_c']==2300
    assert pending['apply_pending'] and not n.client.ready
    assert (await n.peer.request('durable_readback'))['writes']==1
    # Restore ordinary packet delivery and obtain an actual fresh native
    # readback, without granting/patching readiness, lease or qualification.
    monkeypatch.setattr(operation,'CONNECTION_TIMEOUT',90)
    n.peer.clock[0]+=3;await n.handshake()
    assert n.client.native_plan_readback_ready
    same_worker=n.connection;reloads=n.reload.call_count
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,pending['token'],pending['settings']))
    assert not saved['apply_pending'] and n.client.current_native_room_state_verified
    assert n.connection is same_worker and n.reload.call_count==reloads
    durable=await n.peer.request('durable_readback');assert durable['writes']==2
    assert json.loads(durable['stored'])['zones'][0]['base_centi_c']==2300


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_invalid_selected_source_keeps_active_room_read_only_without_breaking_get(native_plan,hass,monkeypatch):
    import custom_components.open_thermostat as integration
    n=native_plan;await n.apply();before=configuration_snapshot(n.parent)
    monkeypatch.setattr(integration,'_NATIVE_PLAN_SOURCE_PROFILES',(object(),))
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    assert model['supported'] and not model['editable'] and not model['program_only']
    assert configuration_snapshot(n.parent)==before


async def idle_with_current_state(n):
    for _ in range(20):
        n.peer.clock[0]+=1
        await n.client.poll();await n.drain();await n.event('tick');await n.drain()
    assert n.client.ready and n.client.current_native_room_state_verified
    assert not n.client.native_plan_readback_ready


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_program_save_after_idle_requests_fresh_real_readback_before_saving(native_plan,hass):
    n=native_plan;await n.apply();await idle_with_current_state(n)
    before_snapshots=sum(op=='receive' and kw.get('topic')=='ha/snapshot_request' for op,kw,_ in n.peer.trace)
    async def reload(entry_id):
        n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None)
        await n.stop();n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None)
        await n.start();n.parent._async_set_state(hass,ConfigEntryState.LOADED,None)
        return True
    n.reload.side_effect=reload
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    assert model['editable'] and not model['apply_pending']
    settings=deepcopy(model['settings']);settings['base_centi_c']=2300
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=2000)
    assert saved['settings']['base_centi_c']==2300 and not saved['apply_pending']
    assert sum(op=='receive' and kw.get('topic')=='ha/snapshot_request' for op,kw,_ in n.peer.trace)>before_snapshots
    durable=await n.peer.request('durable_readback')
    assert durable['writes']==2 and json.loads(durable['stored'])['revision']==2


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_idle_readback_loss_cannot_save_ha_intent_or_stage_any_plan(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat import controller_connection as operation
    n=native_plan;await n.apply();await idle_with_current_state(n)
    before=configuration_snapshot(n.parent);reloads=n.reload.call_count
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    settings=deepcopy(model['settings']);settings['base_centi_c']=2300
    monkeypatch.setattr(operation,'CONNECTION_TIMEOUT',.08)
    with pytest.raises(ValueError,match='^controller_readback_unconfirmed$'):
        await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),drop_snapshots=True)
    assert configuration_snapshot(n.parent)==before and n.reload.call_count==reloads
    assert n.client.journal['staged'] is None and (await n.peer.request('durable_readback'))['writes']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_credential_change_while_fetching_readback_cannot_save_room(native_plan,hass,monkeypatch):
    n=native_plan;await n.apply();await idle_with_current_state(n)
    before=configuration_snapshot(n.parent)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    settings=deepcopy(model['settings']);settings['base_centi_c']=2300
    original=n.connection.async_graph_command
    async def changed(command,*args):
        result=await original(command,*args)
        if command=='readback':
            hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,'controller_password':'new-test-only'})
        return result
    monkeypatch.setattr(n.connection,'async_graph_command',changed)
    with pytest.raises(ValueError,match='^setup_changed$'):
        await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings))
    assert configuration_snapshot(n.parent)==before
    assert n.parent.data['controller_password']=='new-test-only'
    assert (await n.peer.request('durable_readback'))['writes']==1
