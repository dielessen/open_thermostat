"""Native active room replacement transaction; transport failures preserve intent."""
from copy import deepcopy
from unittest.mock import AsyncMock
import pytest
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.native_plan import native_entry_state, NativePlanSource
from custom_components.open_thermostat.native_provisioning import source_from_selection, current_profile_only
from custom_components.open_thermostat.product import configuration_snapshot
from test_native_control_plan import native_plan, native_two
from test_controller_connection import drive
from test_room_source_change import select_saved_source
from test_v1_native import room


async def saved_connection(hass, monkeypatch, n):
    select_saved_source(hass,monkeypatch,n)
    hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,
        'controller_address':'http://192.168.50.10','controller_password':'test-password',
        'controller_id':n.source.policy.controller_id})
    await n.stop()
    await n.start()
    await n.event("connect")
    await n.handshake()


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_failed_remote_profile_apply_retains_atomic_intent_without_rollback(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat import controller_setup_flow
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    old_source=n.source;accepted=deepcopy(n.client.journal['accepted'])
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    other=room(hass,room_id='bbbb2222',suffix='replacement')
    settings=deepcopy(model['settings']);settings['temperature_entity']=other.temperature.entity_id
    settings['name']='Saved replacement';settings['base_centi_c']=2200
    connect=AsyncMock(side_effect=ValueError('controller_unreachable'))
    monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    with pytest.raises(ValueError,match='^save_uncertain$'):
        await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings))
    connect.assert_awaited_once_with(hass,n.parent,'http://192.168.50.10','test-password')
    selected=source_from_selection(n.parent)
    assert selected.predecessor==current_profile_only(old_source)
    saved=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    assert saved['settings']==settings
    assert saved['profile_apply_pending'] and saved['apply_pending'] and not saved['editable']
    changed=deepcopy(settings);changed['name']='Do not overwrite pending intent'
    with pytest.raises(ValueError,match='setup_changed'):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,saved['token'],changed)
    assert connect.await_count==1
    with pytest.raises(ValueError,match='save_uncertain'):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,saved['token'],settings)
    assert connect.await_count==2
    assert ui.read_room(hass,n.parent.entry_id,n.rad.room_id)['settings']==settings
    assert n.parent.options['shadow_enabled'] is False and not n.runtime.enabled
    assert n.client.journal['accepted']==accepted and n.client.journal['staged'] is None
    assert (await n.peer.request('durable_readback'))['writes']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
@pytest.mark.parametrize('fault',['credentials','registry'])
async def test_profile_final_compile_await_fences_before_stopping_or_saving(native_plan,hass,monkeypatch,fault):
    from custom_components.open_thermostat import controller_setup_flow
    from homeassistant.helpers import entity_registry as er
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    other=room(hass,room_id='cccc3333',suffix='changed')
    settings=deepcopy(model['settings']);settings['temperature_entity']=other.temperature.entity_id
    compile=NativePlanSource.async_prospective_configuration
    async def changed(source,*args,**kwargs):
        result=await compile(source,*args,**kwargs)
        if fault=='credentials':
            hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,'controller_password':'concurrent-secret'})
        else:
            er.async_get(hass).async_update_entity(other.temperature.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
        return result
    monkeypatch.setattr(NativePlanSource,'async_prospective_configuration',changed)
    connect=AsyncMock();monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    before=configuration_snapshot(n.parent)
    with pytest.raises(ValueError):
        await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings))
    assert n.runtime.enabled and n.parent.options['shadow_enabled'] is True
    assert source_from_selection(n.parent)==n.source
    assert configuration_snapshot(n.parent)[3]==before[3]
    connect.assert_not_awaited()
    assert (await n.peer.request('durable_readback'))['writes']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_room_profile_commit_rejoins_native_worker_and_cpp_verified_plan(native_plan,hass,monkeypatch):
    import json
    from homeassistant.config_entries import ConfigEntryState
    from custom_components.open_thermostat import controller_setup_flow
    from custom_components.open_thermostat.controller_connection import async_synchronise_controller_plan
    from custom_components.open_thermostat.native_provisioning import local_device_descriptor
    from custom_components.open_thermostat.graph_shadow_validation import canonical
    from custom_components.open_thermostat.product import commit_configuration
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    previous=n.connection;accepted=deepcopy(n.client.journal['accepted'])
    # Device boot IO and the driver's MQTT clock share one line protocol.
    # Serialize complete requests so neither coroutine consumes another reply.
    import asyncio
    peer_request=n.peer.request;peer_lock=asyncio.Lock()
    async def serial_request(*args,**kwargs):
        async with peer_lock:return await peer_request(*args,**kwargs)
    n.peer.request=serial_request
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    other=room(hass,room_id='dddd4444',suffix='new_sensor')
    settings=deepcopy(model['settings']);settings['temperature_entity']=other.temperature.entity_id
    settings['base_centi_c']=2250
    boot_writes=[]
    async def reconnect(_hass,entry,address,password):
        # Controlled HTTP/device boot boundary. Actual source descriptor parsing,
        # same HA Store/worker, MQTT packets and applied C++ readback run below.
        selected=source_from_selection(entry)
        n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None)
        await n.stop()
        initial=await n.peer.request('initialize_native_local_source',controller=selected.policy.controller_id,
            boot='replacement_boot',owner=selected.policy.adapter_id,
            stored=canonical(accepted['config']),local_source=canonical(local_device_descriptor(selected)))
        assert not initial['fault'] and initial['revision']==accepted['config']['revision']
        boot_writes.append((await n.peer.request('durable_readback'))['writes'])
        commit_configuration(hass,entry,configuration_snapshot(entry),options={**entry.options,'shadow_enabled':True})
        n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None)
        await n.start()
        n.parent._async_set_state(hass,ConfigEntryState.LOADED,None)
        await n.event('connect');await n.handshake()
        return await async_synchronise_controller_plan(hass,entry,selected,configuration_snapshot(entry),
            private_expected=native_entry_state(entry))
    monkeypatch.setattr(controller_setup_flow,'async_connect_installation',reconnect)
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings))
    assert saved['settings']==settings and not saved['apply_pending']
    assert previous.worker.done() and n.connection is not previous
    assert n.client.current_native_room_state_verified and n.client.ready
    final=n.client.journal['accepted']
    assert final['config']['revision']==accepted['config']['revision']+1
    assert final['config']['mapping']['mapping_revision']==accepted['config']['mapping']['mapping_revision']+1
    assert final['config']['profile_digest']==source_from_selection(n.parent).policy.profile_digest
    durable=await n.peer.request('durable_readback')
    assert json.loads(durable['stored'])==final['config'] and durable['writes']==boot_writes[0]+1
    assert n.runtime.observations[n.rad.room_id].quality!='qualified'


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True,
    'controller_id':'e32_123456789abc'}],indirect=True)
async def test_complete_room_save_uses_normal_link_provision_reload_and_cpp_apply(native_plan,hass,monkeypatch):
    import asyncio,json
    from homeassistant.config_entries import ConfigEntryState
    from custom_components.open_thermostat import controller_setup_flow
    from custom_components.open_thermostat.native_provisioning import local_device_descriptor
    from custom_components.open_thermostat.graph_shadow_validation import canonical
    from test_controller_setup_flow import ScopedReceiver
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    accepted=deepcopy(n.client.journal['accepted']);old_connection=n.connection
    peer_request=n.peer.request;peer_lock=asyncio.Lock();reload_lock=asyncio.Lock()
    async def serial_request(*args,**kwargs):
        async with peer_lock:return await peer_request(*args,**kwargs)
    n.peer.request=serial_request
    boot_writes=[]
    class Receiver(ScopedReceiver):
        async def async_login(self,password):
            assert password=='test-password';self.authenticated=True;self.calls.append(('login',))
        async def async_reboot(self):
            await super().async_reboot()
            reply=await n.peer.request('initialize_native_local_source',controller=n.source.policy.controller_id,
                owner=n.source.policy.adapter_id,boot='http_profile_boot',stored=canonical(accepted['config']),
                local_source=canonical(self.readbacks['settings']['mqtt']['native_shadow_source']))
            assert not reply['fault']
            boot_writes.append((await n.peer.request('durable_readback'))['writes'])
    http=Receiver();http.readbacks['status']['controlMode']='shadow'
    http.readbacks['settings']['mqtt'].update(modern_shadow=True,adapter_id=n.source.policy.adapter_id,
        base=n.parent.data['topic_prefix'],native_source_live_apply=True,
        native_shadow_source=local_device_descriptor(n.source))
    monkeypatch.setattr(controller_setup_flow,'ControllerClient',lambda address:http)
    async def reload(entry_id):
        async with reload_lock:
            n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None)
            await n.stop()
            n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None)
            await n.start()
            n.parent._async_set_state(hass,ConfigEntryState.LOADED,None)
            await n.event('connect')
            return True
    n.reload.side_effect=reload
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    other=room(hass,room_id='eeee5555',suffix='full_route')
    settings=deepcopy(model['settings']);settings['temperature_entity']=other.temperature.entity_id
    settings['base_centi_c']=2300
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=1800)
    assert saved['settings']==settings and not saved['apply_pending']
    assert saved['profile_editable'] and not saved['profile_apply_pending']
    assert old_connection.worker.done() and n.client.current_native_room_state_verified
    assert sum(c[0]=='save' for c in http.calls)==sum(c[0]=='reboot' for c in http.calls)==1
    assert http.logout_confirmed and n.parent.options['shadow_enabled'] is True
    final=n.client.journal['accepted'];durable=await n.peer.request('durable_readback')
    assert final['config']['revision']==accepted['config']['revision']+1
    assert json.loads(durable['stored'])==final['config'] and durable['writes']==boot_writes[0]+1
    assert n.runtime.observations[n.rad.room_id].quality!='qualified'


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_stop_await_credential_fence_does_not_commit_or_revive_old_owner(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat import controller_setup_flow
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    other=room(hass,room_id='ffff6666',suffix='stop_race')
    settings=deepcopy(model['settings']);settings['temperature_entity']=other.temperature.entity_id
    before=configuration_snapshot(n.parent);stop=n.runtime.async_stop
    async def changed():
        await stop()
        hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,'controller_password':'new-private-owner'})
    monkeypatch.setattr(n.runtime,'async_stop',changed)
    connect=AsyncMock();monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    with pytest.raises(ValueError,match='setup_changed'):
        await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings))
    assert configuration_snapshot(n.parent)[3]==before[3]
    assert source_from_selection(n.parent)==n.source and not n.runtime.enabled
    assert n.parent.data['controller_password']=='new-private-owner'
    connect.assert_not_awaited()
    assert (await n.peer.request('durable_readback'))['writes']==1
