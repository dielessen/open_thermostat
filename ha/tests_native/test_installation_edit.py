"""Real native HA options/Store and C++ plan readback; no network/devices."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from custom_components.open_thermostat import installation_edit as central
from custom_components.open_thermostat.native_plan import NativePlanSource, native_entry_state
from custom_components.open_thermostat.native_provisioning import source_from_selection, current_profile_only
from custom_components.open_thermostat.product import configuration_snapshot, central_entry, INSTALLATION
from test_native_control_plan import native_plan, native_two
from test_product_flow import managers, option
from test_room_profile_apply import saved_connection
from test_controller_connection import drive

PROFILE = {'week':True,'single':True,'local_source':True,'product':True}


def submitted(n, minimum=25, maximum=45):
    return {'name':n.parent.title,'create_dashboard':False,'advanced':{
        'minimum_supply_temperature':minimum,'maximum_supply_temperature':maximum}}


def test_limit_edit_keeps_custom_circuits_room_bindings_and_stored_draft(hass,native_two):
    parent,*_=native_two
    before=configuration_snapshot(parent)
    old=deepcopy(central_entry(parent).data['draft'])
    graph,anchor=central.prepare_installation_edit(hass,parent,{
        'name':parent.title,'advanced':{'minimum_supply_temperature':25,'maximum_supply_temperature':35}})
    document=graph.storage_document()
    assert document['central']['supply_limits']=={'minimum_centi_c':2500,'maximum_centi_c':3500}
    assert document['central']['curve_centi_c']==[max(2500,v)for v in old['central']['curve_centi_c']]
    floor=next(g for g in document['groups']if g['emitter']=='floor')
    assert floor==next(g for g in old['groups']if g['emitter']=='floor')
    radiators=next(g for g in document['groups']if g['emitter']=='radiator')
    assert radiators['supply_limits']==document['central']['supply_limits']
    assert sorted(document['actuators'],key=lambda a:a['actuator_id'])==sorted(old['actuators'],key=lambda a:a['actuator_id']) and anchor.room_id
    assert configuration_snapshot(parent)==before


@pytest.mark.parametrize('advanced',[
 {'minimum_supply_temperature':True},{'maximum_supply_temperature':float('nan')},
 {'minimum_supply_temperature':40,'maximum_supply_temperature':30},
 {'minimum_supply_temperature':4},{'maximum_supply_temperature':91},
 {'weather_enabled':True},{'curve_0':20},{'outdoor_source':'sensor.outdoor'},
])
def test_invalid_or_unexecuted_settings_never_change_intent(hass,native_two,advanced):
    parent,*_=native_two;before=configuration_snapshot(parent)
    with pytest.raises(ValueError):central.prepare_installation_edit(hass,parent,{'name':parent.title,'advanced':advanced})
    assert configuration_snapshot(parent)==before


def test_narrowing_central_maximum_cannot_silently_rewrite_floor_limits(hass,native_two):
    parent,*_=native_two;before=configuration_snapshot(parent)
    with pytest.raises(ValueError):central.prepare_installation_edit(hass,parent,{
        'name':parent.title,'advanced':{'maximum_supply_temperature':30}})
    assert configuration_snapshot(parent)==before


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
async def test_connected_options_show_only_supported_fields_and_no_visit_io(native_plan,hass,monkeypatch,managers):
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    from custom_components.open_thermostat import controller_setup_flow
    connect=AsyncMock();monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    before=configuration_snapshot(n.parent);writes=(await n.peer.request('durable_readback'))['writes']
    _,manager=managers;form=await option(manager,n.parent,'installation')
    assert form['step_id']=='installation_connected'
    schema=str(form['data_schema'])+str(next(value.schema for key,value in form['data_schema'].schema.items()if str(key)=='advanced'))
    assert 'minimum_supply_temperature' in schema and 'maximum_supply_temperature' in schema
    assert all(key not in schema for key in ['weather_enabled','outdoor_source','curve_0','controller_password'])
    assert configuration_snapshot(n.parent)==before
    assert (await n.peer.request('durable_readback'))['writes']==writes
    connect.assert_not_called()
    result=await manager.async_configure(form['flow_id'],{'name':n.parent.title,'create_dashboard':False})
    assert result['reason']=='installation_saved'
    assert n.runtime.enabled and (await n.peer.request('durable_readback'))['writes']==writes


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
async def test_failed_apply_retains_one_atomic_installation_intent_and_does_not_replay(native_plan,hass,monkeypatch,managers):
    from custom_components.open_thermostat import controller_setup_flow
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    old=n.source;accepted=deepcopy(n.client.journal['accepted']);rooms=deepcopy(configuration_snapshot(n.parent)[3])
    connect=AsyncMock(side_effect=ValueError('controller_unreachable'))
    monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    before,private=configuration_snapshot(n.parent),native_entry_state(n.parent)
    with pytest.raises(ValueError,match='^save_uncertain$'):
        await drive(n,central.save_active_installation(hass,n.parent,before,private,submitted(n)))
    connect.assert_awaited_once_with(hass,n.parent,'http://192.168.50.10','test-password')
    selected=source_from_selection(n.parent)
    assert selected.predecessor==current_profile_only(old)
    assert central_entry(n.parent).data['draft']['central']['supply_limits']=={'minimum_centi_c':2500,'maximum_centi_c':4500}
    assert configuration_snapshot(n.parent)[3]==rooms
    assert n.parent.options['shadow_enabled'] is False and not n.runtime.enabled
    assert n.client.journal['accepted']==accepted and n.client.journal['staged'] is None
    assert (await n.peer.request('durable_readback'))['writes']==1
    _,manager=managers;result=await option(manager,n.parent,'installation')
    assert result['reason']=='installation_apply_pending'
    assert connect.await_count==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
@pytest.mark.parametrize('fault',['credentials','registry','entry'])
async def test_compilation_await_rechecks_private_scope_and_registry_before_stopping(native_plan,hass,monkeypatch,fault):
    from homeassistant.helpers import entity_registry as er
    from custom_components.open_thermostat import controller_setup_flow
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    before,private=configuration_snapshot(n.parent),native_entry_state(n.parent)
    original=NativePlanSource.async_prospective_configuration
    async def changed(self,*args,**kwargs):
        result=await original(self,*args,**kwargs)
        if fault=='credentials':hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,'controller_password':'changed-private-password'})
        elif fault=='entry':hass.config_entries.async_update_entry(n.parent,title='Other operation')
        else:
            registry=er.async_get(hass);row=registry.async_get(n.rad.temperature.entity_id)
            registry.async_remove(row.entity_id)
            registry.async_get_or_create('sensor','other_source','reused_entity',suggested_object_id=row.entity_id.split('.')[1])
        return result
    monkeypatch.setattr(NativePlanSource,'async_prospective_configuration',changed)
    connect=AsyncMock();monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    with pytest.raises(ValueError):
        await drive(n,central.save_active_installation(hass,n.parent,before,private,submitted(n)))
    assert n.runtime.enabled and source_from_selection(n.parent)==n.source
    assert central_entry(n.parent).data['draft']==before[1][INSTALLATION]['draft']
    assert (await n.peer.request('durable_readback'))['writes']==1
    connect.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
async def test_form_open_before_credentials_change_cannot_submit_against_new_owner(native_plan,hass,monkeypatch,managers):
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    _,manager=managers;form=await option(manager,n.parent,'installation')
    hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,'controller_password':'replaced-private-password'})
    result=await manager.async_configure(form['flow_id'],submitted(n))
    assert result['reason']=='setup_changed' and n.runtime.enabled
    assert (await n.peer.request('durable_readback'))['writes']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{**PROFILE,'controller_id':'e32_123456789abc'}],indirect=True)
async def test_normal_options_save_uses_authenticated_link_reload_and_actual_cpp_plan(native_plan,hass,monkeypatch,managers):
    import asyncio,json
    from homeassistant.config_entries import ConfigEntryState
    from custom_components.open_thermostat import controller_setup_flow
    from custom_components.open_thermostat.native_provisioning import local_device_descriptor
    from custom_components.open_thermostat.graph_shadow_validation import canonical
    from test_controller_setup_flow import ScopedReceiver
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    accepted=deepcopy(n.client.journal['accepted']);old_connection=n.connection
    rooms=deepcopy(configuration_snapshot(n.parent)[3])
    peer_request=n.peer.request;peer_lock=asyncio.Lock();reload_lock=asyncio.Lock()
    async def serial_request(*args,**kwargs):
        async with peer_lock:return await peer_request(*args,**kwargs)
    n.peer.request=serial_request;boot_writes=[]
    class Receiver(ScopedReceiver):
        async def async_login(self,password):
            assert password=='test-password';self.authenticated=True;self.calls.append(('login',))
        async def async_reboot(self):
            await super().async_reboot()
            reply=await n.peer.request('initialize_native_local_source',controller=n.source.policy.controller_id,
                owner=n.source.policy.adapter_id,boot='http_central_boot',stored=canonical(accepted['config']),
                local_source=canonical(self.readbacks['settings']['mqtt']['native_shadow_source']))
            assert not reply['fault'];boot_writes.append((await n.peer.request('durable_readback'))['writes'])
    http=Receiver();http.readbacks['status']['controlMode']='shadow'
    http.readbacks['settings']['mqtt'].update(modern_shadow=True,adapter_id=n.source.policy.adapter_id,
        base=n.parent.data['topic_prefix'],native_source_live_apply=True,
        native_shadow_source=local_device_descriptor(n.source))
    monkeypatch.setattr(controller_setup_flow,'ControllerClient',lambda address:http)
    async def reload(entry_id):
        async with reload_lock:
            n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None);await n.stop()
            n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None);await n.start()
            n.parent._async_set_state(hass,ConfigEntryState.LOADED,None);await n.event('connect');return True
    n.reload.side_effect=reload
    _,manager=managers;form=await option(manager,n.parent,'installation')
    result=await drive(n,manager.async_configure(form['flow_id'],submitted(n,minimum=25,maximum=32)),steps=1800)
    assert result['reason']=='installation_applied',result
    assert old_connection.worker.done() and n.client.current_native_room_state_verified and n.client.ready
    assert sum(c[0]=='save'for c in http.calls)==sum(c[0]=='reboot'for c in http.calls)==1
    assert http.logout_confirmed and n.parent.options['shadow_enabled'] is True
    final=n.client.journal['accepted'];durable=await n.peer.request('durable_readback')
    assert final['config']['revision']==accepted['config']['revision']+1
    assert final['config']['mapping']['mapping_revision']==accepted['config']['mapping']['mapping_revision']+1
    assert json.loads(durable['stored'])==final['config'] and durable['writes']==boot_writes[0]+1
    assert configuration_snapshot(n.parent)[3]==rooms
    row=final['config']['groups'][0]
    assert row['minimum_supply_centi_c']==2500 and row['maximum_supply_centi_c']==3200
    assert n.runtime.observations[n.rad.room_id].quality!='qualified'


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
async def test_name_change_reloads_existing_worker_without_source_or_device_settings_write(native_plan,hass,monkeypatch,managers):
    from homeassistant.config_entries import ConfigEntryState
    from custom_components.open_thermostat import controller_setup_flow
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    source=n.source;accepted=deepcopy(n.client.journal['accepted']);previous=n.connection
    connect=AsyncMock();monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    async def reload(entry_id):
        n.parent._async_set_state(hass,ConfigEntryState.UNLOAD_IN_PROGRESS,None);await n.stop()
        n.parent._async_set_state(hass,ConfigEntryState.NOT_LOADED,None);await n.start()
        n.parent._async_set_state(hass,ConfigEntryState.LOADED,None);return True
    n.reload.side_effect=reload
    _,manager=managers;form=await option(manager,n.parent,'installation')
    result=await drive(n,manager.async_configure(form['flow_id'],{'name':'My heating installation','create_dashboard':False}))
    assert result['reason']=='installation_applied',result
    assert n.parent.title=='My heating installation' and source_from_selection(n.parent)==source
    assert previous.worker.done() and n.connection is not previous and n.client.current_native_room_state_verified
    assert n.client.journal['accepted']==accepted
    assert (await n.peer.request('durable_readback'))['writes']==1
    connect.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
async def test_operator_change_during_old_owner_stop_is_not_overwritten(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat import controller_setup_flow
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    before,private=configuration_snapshot(n.parent),native_entry_state(n.parent)
    stop=n.runtime.async_stop
    async def changed():
        await stop()
        hass.config_entries.async_update_entry(n.parent,title='Another saved operation')
    monkeypatch.setattr(n.runtime,'async_stop',changed)
    connect=AsyncMock();monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    with pytest.raises(ValueError,match='setup_changed'):
        await drive(n,central.save_active_installation(hass,n.parent,before,private,submitted(n)))
    assert n.parent.title=='Another saved operation'
    assert central_entry(n.parent).data['draft']==before[1][INSTALLATION]['draft']
    assert source_from_selection(n.parent)==n.source and not n.runtime.enabled
    assert (await n.peer.request('durable_readback'))['writes']==1
    connect.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
async def test_cancellation_after_saved_intent_cannot_restore_or_replay_old_profile(native_plan,hass,monkeypatch):
    import asyncio
    from custom_components.open_thermostat import controller_setup_flow
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    before,private=configuration_snapshot(n.parent),native_entry_state(n.parent)
    accepted=deepcopy(n.client.journal['accepted'])
    connect=AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    with pytest.raises(asyncio.CancelledError):
        await drive(n,central.save_active_installation(hass,n.parent,before,private,submitted(n)))
    assert n.parent.options['shadow_enabled'] is False and not n.runtime.enabled
    assert central_entry(n.parent).data['draft']['central']['supply_limits']=={'minimum_centi_c':2500,'maximum_centi_c':4500}
    assert source_from_selection(n.parent).predecessor==current_profile_only(n.source)
    assert n.client.journal['accepted']==accepted and (await n.peer.request('durable_readback'))['writes']==1
    assert connect.await_count==1


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[PROFILE],indirect=True)
@pytest.mark.parametrize('operation',['installation','room'])
async def test_source_storage_budget_failure_preserves_old_owner_before_any_io(native_plan,hass,monkeypatch,operation):
    from custom_components.open_thermostat import controller_setup_flow, native_profile_apply, room_editor, room_profile_apply
    from test_v1_native import room
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    before,private=configuration_snapshot(n.parent),native_entry_state(n.parent)
    def budget_exhausted(source):raise ValueError('native_source_selection_budget')
    monkeypatch.setattr(native_profile_apply,'source_selection',budget_exhausted)
    monkeypatch.setattr(central if operation=='installation' else room_profile_apply,'source_selection',budget_exhausted)
    connect=AsyncMock();monkeypatch.setattr(controller_setup_flow,'async_connect_installation',connect)
    if operation=='installation':
        action=central.save_active_installation(hass,n.parent,before,private,submitted(n))
    else:
        model=room_editor.read_room(hass,n.parent.entry_id,n.rad.room_id)
        other=room(hass,room_id='ffff6666',suffix='source_budget')
        settings=deepcopy(model['settings']);settings['temperature_entity']=other.temperature.entity_id
        action=room_editor.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    with pytest.raises(ValueError,match='^native_source_selection_budget$'):
        await drive(n,action)
    assert configuration_snapshot(n.parent)==before and native_entry_state(n.parent)==private
    assert n.runtime.enabled and source_from_selection(n.parent)==n.source
    assert (await n.peer.request('durable_readback'))['writes']==1
    connect.assert_not_called()
