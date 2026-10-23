"""Complete room/week transaction on real native HA stores, registries and events."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
import pytest_asyncio
from homeassistant import config_entries
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot, central_entry, INSTALLATION
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from test_product_flow import product, new_room
from test_v1_native import room

@pytest_asyncio.fixture
async def configured(hass, monkeypatch):
    monkeypatch.setattr(config_entries,'_async_get_flow_handler',AsyncMock(return_value=OpenThermostatConfigFlow))
    p=product(hass);b=room(hass);manager=hass.config_entries.subentries
    f=await new_room(manager,p,b);f=await manager.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save'});await manager.async_configure(f['flow_id'],{})
    sub=next(s for s in p.subentries.values() if s.subentry_type=='zone')
    return p,sub,ui.read_room(hass,p.entry_id,sub.data['room_id'])

def changed(model):
    s=deepcopy(model['settings']);s['name']='New room name';s['base_centi_c']=1950;s['week']['monday']=[dict(start=25200,end=32400,target_centi_c=2300)]
    return s

@pytest.mark.asyncio
async def test_atomic_full_room_week_and_new_binding_preserve_all_other_data(hass,configured):
    p,sub,m=configured;s=changed(m);other=room(hass,room_id='aaaa1111',suffix='new')
    s['temperature_entity']=other.temperature.entity_id;s['radiator_entities']=[other.actuators[0].entity_id]
    before=configuration_snapshot(p);seen=[]
    async def listener(hass,entry):seen.append((entry.subentries[sub.subentry_id].data['base_centi_c'],entry.subentries[sub.subentry_id].data['week_program']['monday'][0]['target_centi_c'],entry.data[INSTALLATION]['draft']['actuators'][0]['output']['entity_id']))
    p.add_update_listener(listener)
    out=await ui.save_room(hass,p.entry_id,m['room_id'],m['token'],s);await hass.async_block_till_done()
    assert seen and all(x==(1950,2300,other.actuators[0].entity_id) for x in seen)
    assert out['settings']==s and out['token']!=m['token']
    assert p.subentries[sub.subentry_id].unique_id==sub.unique_id
    assert p.options==before[2] and p.data[INSTALLATION]['draft']['central']==before[1][INSTALLATION]['draft']['central']
    assert ui.read_room(hass,p.entry_id,m['room_id'])['settings']==s

@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['overlap','limits','boolean','empty_valves','duplicate_valves','floor','missing_sensor','loop','helper_conflict','unknown_key'])
async def test_invalid_complete_edit_never_partially_saves(hass,configured,fault):
    p,sub,m=configured;s=changed(m);before=configuration_snapshot(p)
    if fault=='overlap':s['week']['monday']*=2
    if fault=='limits':s['maximum_centi_c']=1800
    if fault=='boolean':s['base_centi_c']=True
    if fault=='empty_valves':s['radiator_entities']=[]
    if fault=='duplicate_valves':s['radiator_entities']*=2
    if fault=='floor':s['emitter']='floor'
    if fault=='missing_sensor':s['temperature_entity']='sensor.no_such_device'
    if fault=='loop':s['temperature_entity']=s['radiator_entities'][0]
    if fault=='helper_conflict':s['program_source']='helper'
    if fault=='unknown_key':s['trust']=True
    with pytest.raises((ValueError,KeyError)):await ui.save_room(hass,p.entry_id,m['room_id'],m['token'],s)
    assert configuration_snapshot(p)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['config','unload','registry','runtime','replace'])
async def test_full_room_final_await_fences_no_partial_commit(hass,configured,monkeypatch,fault):
    p,sub,m=configured
    async def executor(*args):
        if fault=='config':hass.config_entries.async_update_entry(p,title='Concurrent')
        if fault=='unload':hass.data['open_thermostat'].pop(p.entry_id)
        if fault=='registry':er.async_get(hass).async_update_entity(m['settings']['temperature_entity'],disabled_by=er.RegistryEntryDisabler.USER)
        if fault=='runtime':hass.data['open_thermostat'][p.entry_id]['v1_runtime']=SimpleNamespace(enabled=True)
        if fault=='replace':hass.config_entries._entries.pop(p.entry_id)
    monkeypatch.setattr(hass,'async_add_executor_job',executor)
    original=deepcopy(dict(sub.data));central=deepcopy(p.data[INSTALLATION])
    with pytest.raises(ValueError):await ui.save_room(hass,p.entry_id,m['room_id'],m['token'],changed(m))
    assert dict(p.subentries[sub.subentry_id].data)==original and p.data[INSTALLATION]==central

@pytest.mark.asyncio
async def test_conflicting_edit_and_helper_source_require_explicit_change(hass,configured):
    p,sub,m=configured;helper=er.async_get(hass).async_get_or_create('schedule','schedule','helper')
    s=changed(m);s['program_source']='helper';s['schedule_entity']=helper.entity_id;s['week']={d:[] for d in s['week']}
    with pytest.raises(ValueError,match='confirm_program_source_change'):await ui.save_room(hass,p.entry_id,m['room_id'],m['token'],s)
    out=await ui.save_room(hass,p.entry_id,m['room_id'],m['token'],s,confirm_source_change=True)
    assert out['settings']['program_source']=='helper' and not any(out['settings']['week'].values())
    before=configuration_snapshot(p)
    with pytest.raises(ValueError,match='setup_changed'):await ui.save_room(hass,p.entry_id,m['room_id'],m['token'],changed(m))
    assert configuration_snapshot(p)==before and p.subentries[sub.subentry_id].data['schedule']['entity_id']==helper.entity_id

@pytest.mark.asyncio
async def test_new_api_requires_admin_before_access(hass,configured):
    p,sub,m=configured
    for user in (None,SimpleNamespace(is_admin=False)):
        c=SimpleNamespace(user=user,send_result=Mock(),send_error=Mock())
        for handler in (ui.ws_room_get,ui.ws_room_save,ui.ws_room_device_metadata):
            with pytest.raises(Unauthorized):handler(hass,c,{'id':1,'entry_id':p.entry_id,'room_id':m['room_id'],'token':m['token'],'settings':changed(m)})
        c.send_result.assert_not_called();c.send_error.assert_not_called()


@pytest.mark.asyncio
async def test_metadata_endpoint_reads_only_current_saved_bindings_without_save_or_activation(hass,configured,monkeypatch):
    import inspect
    from custom_components.open_thermostat import device_metadata
    p,sub,m=configured;before=configuration_snapshot(p)
    read=AsyncMock(return_value={'metadata_only':True,'physical_control_qualified':False})
    monkeypatch.setattr(device_metadata,'async_read_selected_metadata',read)
    c=SimpleNamespace(send_result=Mock(),send_error=Mock())
    message={'id':1,'entry_id':p.entry_id,'room_id':m['room_id'],'token':m['token']}
    await inspect.unwrap(ui.ws_room_device_metadata)(hass,c,message)
    read.assert_awaited_once()
    args=read.await_args.args
    assert args[0] is hass and args[1] is p
    assert [x['entity_id'] for x in args[2]]==[m['settings']['temperature_entity'],*m['settings']['radiator_entities']]
    assert configuration_snapshot(p)==before and not p.options['shadow_enabled']
    c.send_error.assert_not_called()
    read.reset_mock();c.send_result.reset_mock()
    message['token']='f'*64
    await inspect.unwrap(ui.ws_room_device_metadata)(hass,c,message)
    read.assert_not_called();c.send_result.assert_not_called()
    assert c.send_error.call_args.args[1]=='setup_changed'
