"""Normal product routes against the actual HA options/subentry Store managers."""
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries

import custom_components.open_thermostat as integration
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.product import PRODUCT_CONFIG, configuration_snapshot, central_entry
from custom_components.open_thermostat.product_flow import ProductOptionsFlow, ProductRoomFlow
from test_v1_native import entry, room

@pytest.fixture
def managers(hass, monkeypatch):
    monkeypatch.setattr(config_entries, '_async_get_flow_handler', AsyncMock(return_value=OpenThermostatConfigFlow))
    return hass.config_entries.subentries, hass.config_entries.options


def product(hass, binding=None):
    p=entry(hass,room=binding)
    hass.config_entries.async_update_entry(p,data={**p.data,PRODUCT_CONFIG:1})
    hass.data.setdefault("open_thermostat", {})[p.entry_id] = {}
    return p

async def option(manager,parent,step):
    from custom_components.open_thermostat.room_plan import has_room_plan
    f=await manager.async_init(parent.entry_id)
    # A stored E32 connection makes the E32 room plan the room editor.
    rooms='e32_rooms' if has_room_plan(parent) else 'room_settings'
    base=['installation','controller_connection',rooms,'configuration_status','energy','advanced_settings']
    assert f['menu_options'] in [base,base[:4]+['graph_prepare']+base[4:]]
    return await manager.async_configure(f['flow_id'],{'next_step_id':step})

async def new_room(manager,parent,binding):
    f=await manager.async_init((parent.entry_id,'zone'),context={'source':'user'})
    assert f['step_id']=='room',f
    f=await manager.async_configure(f['flow_id'],{'name':binding.name,'emitter':'radiator'})
    assert f['step_id']=='devices',f
    f=await manager.async_configure(f['flow_id'],{'temperature_entity':binding.temperature.entity_id,'radiator_entities':[binding.actuators[0].entity_id]})
    assert f['step_id']=='room_temperature',f
    assert 'schedule_entity' not in str(f['data_schema'])
    return f

@pytest.mark.asyncio
async def test_user_flow_is_ordinary_installation_no_internal_mode_or_owner(hass):
    f=OpenThermostatConfigFlow();f.hass=hass;f.handler='open_thermostat';f.context={'source':'user'}
    start=await f.async_step_user();assert start['step_id']=='installation'
    assert set(str(k) for k in start['data_schema'].schema)=={'name','create_dashboard','advanced'}
    result=await f.async_step_installation({'name':'My home'})
    assert result['title']=='My home' and result['data'][PRODUCT_CONFIG]==1
    assert len(result['data']['adapter_id'])==32 and result['options']['shadow_enabled'] is False
    assert OpenThermostatConfigFlow.async_get_supported_subentry_types(type('E',(),{'data':result['data'],'options':result['options']})())=={'zone':ProductRoomFlow}

@pytest.mark.asyncio
async def test_product_options_selector_and_migration_preserve_all_existing_configuration(hass):
    b=room(hass);p=entry(hass,room=b);before=configuration_snapshot(p)
    assert await integration.async_migrate_entry(hass,p)
    assert p.version==3 and p.minor_version==1 and p.data[PRODUCT_CONFIG]==1
    assert dict(p.options)==before[2] and {k:s.as_dict() for k,s in p.subentries.items()}==before[3]
    assert isinstance(OpenThermostatConfigFlow.async_get_options_flow(p),ProductOptionsFlow)

@pytest.mark.asyncio
async def test_central_options_creates_one_owner_preserves_options_no_activation(hass,managers):
    _,m=managers;p=product(hass);before_options=deepcopy(dict(p.options))
    f=await option(m,p,'installation');assert set(str(k) for k in f['data_schema'].schema)=={'name','weather_enabled','outdoor_source','create_dashboard','advanced'}
    result=await m.async_configure(f['flow_id'],{'name':'Home','weather_enabled':False,'create_dashboard':False})
    assert result['reason']=='installation_saved',result
    c=central_entry(p);assert c and c.title=='Installation' and len(p.subentries)==0
    assert p.title=='Home' and dict(p.options)=={**before_options,'create_dashboard':False}
    stored=deepcopy(dict(c.data))
    f=await option(m,p,'installation');await m.async_configure(f['flow_id'],{'name':'Renamed','weather_enabled':False,'create_dashboard':False})
    assert len(p.subentries)==0 and central_entry(p).subentry_id==c.subentry_id and dict(central_entry(p).data)==stored

@pytest.mark.asyncio
async def test_central_validation_and_abort_do_not_mutate_store(hass,managers):
    _,m=managers;p=product(hass);before=configuration_snapshot(p)
    f=await option(m,p,'installation')
    f=await m.async_configure(f['flow_id'],{'name':'Home','weather_enabled':True})
    assert f['errors']['base']=='weather_requires_outdoor_source',f
    assert configuration_snapshot(p)==before
    m.async_abort(f['flow_id']);assert configuration_snapshot(p)==before

@pytest.mark.asyncio
async def test_guided_room_pair_and_presentation(hass,managers):
    m,_=managers;p=product(hass);b=room(hass);f=await new_room(m,p,b)
    assert not p.subentries
    f=await m.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save'})
    assert f['step_id']=='room_review',f
    result=await m.async_configure(f['flow_id'],{});assert result['reason']=='room_saved',result
    assert [s.subentry_type for s in p.subentries.values()]==['zone']
    assert central_entry(p).title=='Installation'
    assert p.options['shadow_enabled'] is False

@pytest.mark.asyncio
async def test_existing_room_edit_from_central_options_reuses_identity(hass,managers):
    sub,opts=managers;p=product(hass);b=room(hass);f=await new_room(sub,p,b)
    f=await sub.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save'});await sub.async_configure(f['flow_id'],{})
    z=next(s for s in p.subentries.values() if s.subentry_type=='zone')
    f=await option(opts,p,'room_settings');f=await opts.async_configure(f['flow_id'],{'room':z.subentry_id,'action':'edit'})
    assert f['step_id']=='edit_room',f
    assert 'editor_url' in f['description_placeholders']
    assert 'schedule_entity' not in str(f['data_schema'])
    assert 'confirm_source_change' not in str(f['data_schema'])
    result=await opts.async_configure(f['flow_id'],{'name':'Renamed','emitter':'radiator',
        'temperature_entity':b.temperature.entity_id,'radiator_entities':[b.actuators[0].entity_id],
        'base_temperature':19})
    assert result['reason']=='room_saved',result
    assert p.subentries[z.subentry_id].title=='Renamed' and len(p.subentries)==1
    assert p.subentries[z.subentry_id].data['base_centi_c']==1900

@pytest.mark.asyncio
async def test_room_remove_is_atomic_and_preserves_other_room(hass,managers):
    sub,opts=managers;p=product(hass)
    for suffix,rid in [('a','00000001'),('b','00000002')]:
        b=room(hass,room_id=rid,suffix=suffix);f=await new_room(sub,p,b)
        f=await sub.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save'});await sub.async_configure(f['flow_id'],{})
    z=next(s for s in p.subentries.values() if s.subentry_type=='zone');before=configuration_snapshot(p)
    f=await option(opts,p,'room_settings');f=await opts.async_configure(f['flow_id'],{'room':z.subentry_id,'action':'remove'})
    assert configuration_snapshot(p)==before
    result=await opts.async_configure(f['flow_id'],{'confirm_remove':True});assert result['reason']=='room_removed',result
    assert len(p.subentries)==1 and z.subentry_id not in p.subentries
    assert len(central_entry(p).data['draft']['actuators'])==1 and len(central_entry(p).data['draft']['groups'])==1

@pytest.mark.asyncio
async def test_unsupported_floor_is_not_silently_a_radiator(hass,managers):
    sub,_=managers;p=product(hass);f=await sub.async_init((p.entry_id,'zone'),context={'source':'user'})
    f=await sub.async_configure(f['flow_id'],{'name':'Floor','emitter':'floor'})
    assert f['step_id']=='room' and f['errors']['emitter']=='emitter_not_available' and not p.subentries

@pytest.mark.asyncio
async def test_copy_day_preserves_temperatures_and_cancel_never_saves(hass,managers):
    sub,_=managers;p=product(hass);b=room(hass);f=await new_room(sub,p,b)
    f=await sub.async_configure(f['flow_id'],{'base_temperature':20,'program_action':'edit_week'})
    assert 'copy_day' in f['menu_options'],f
    f=await sub.async_configure(f['flow_id'],{'next_step_id':'add_block'})
    f=await sub.async_configure(f['flow_id'],{'days':['monday'],'start_time':'07:00:00','end_time':'08:00:00','end_at_midnight':False,'temperature':22})
    f=await sub.async_configure(f['flow_id'],{'next_step_id':'copy_day'})
    f=await sub.async_configure(f['flow_id'],{'source_day':'monday','target_days':['tuesday']})
    f=await sub.async_configure(f['flow_id'],{'next_step_id':'save_program'});assert f['step_id']=='room_review',f
    result=await sub.async_configure(f['flow_id'],{});assert result['reason']=='room_saved'
    z=next(s for s in p.subentries.values() if s.subentry_type=='zone')
    assert z.data['week_program']['monday']==z.data['week_program']['tuesday']
    assert z.data['week_program']['tuesday'][0]['target_centi_c']==2200

@pytest.mark.asyncio
async def test_migration_moves_central_bytes_once_without_an_extra_ha_subentry(hass,managers):
    from custom_components.open_thermostat.product import INSTALLATION
    from test_v1_heating_graph_gui import create_central,heating
    sub,_=managers;b=room(hass);p=entry(hass,room=b)
    await create_central(sub,p);c=heating(p);central_data=deepcopy(dict(c.data));room_ids={k for k,s in p.subentries.items() if s.subentry_type=='zone'}
    observations=[]
    p.add_update_listener(lambda hass,p:observe(hass,p))
    async def observe(hass,p):
        observations.append((p.version,len(p.subentries),p.data.get(INSTALLATION)))
    assert await integration.async_migrate_entry(hass,p)
    await hass.async_block_till_done()
    assert p.data[INSTALLATION]==central_data
    assert set(p.subentries)==room_ids
    assert all(v==3 and n==1 and data==central_data for v,n,data in observations)
    assert await integration.async_migrate_entry(hass,p)
    assert p.data[INSTALLATION]==central_data

@pytest.mark.asyncio
async def test_cross_installation_ownership_includes_central_entry_data(hass,managers):
    sub,_=managers;first=product(hass);b=room(hass)
    f=await new_room(sub,first,b);f=await sub.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save'});await sub.async_configure(f['flow_id'],{})
    second=product(hass);hass.config_entries.async_update_entry(second,unique_id='second',data={**second.data,'topic_prefix':'second','adapter_id':'second'})
    f=await sub.async_init((second.entry_id,'zone'),context={'source':'user'})
    f=await sub.async_configure(f['flow_id'],{'name':'Other','emitter':'radiator'})
    f=await sub.async_configure(f['flow_id'],{'temperature_entity':b.temperature.entity_id,'radiator_entities':[b.actuators[0].entity_id]})
    assert f['step_id']=='devices' and f['errors']['base']=='output_has_multiple_owners',f
    assert not second.subentries

@pytest.mark.asyncio
async def test_room_age_seconds_keeps_exact_milliseconds(hass,managers):
    sub,_=managers;p=product(hass);b=room(hass);f=await new_room(sub,p,b)
    f=await sub.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save','advanced':{'minimum_target_temperature':5,'maximum_target_temperature':35,'maximum_age_seconds':1.5}})
    assert f['step_id']=='room_review',f
    await sub.async_configure(f['flow_id'],{})
    assert next(iter(p.subentries.values())).data['maximum_age_ms']==1500

@pytest.mark.asyncio
async def test_central_save_conflict_keeps_other_writer_values(hass,managers):
    _,opts=managers;p=product(hass);f=await option(opts,p,'installation')
    hass.config_entries.async_update_entry(p,title='Changed elsewhere')
    before=configuration_snapshot(p)
    result=await opts.async_configure(f['flow_id'],{'name':'My draft','weather_enabled':False})
    assert result['errors']['base']=='setup_changed',result
    assert configuration_snapshot(p)==before

@pytest.mark.asyncio
async def test_product_telemetry_has_no_legacy_room_subscription_or_commands(hass,monkeypatch):
    import json
    from types import SimpleNamespace
    from homeassistant.components import mqtt
    from custom_components.open_thermostat.product_telemetry import async_setup_sensors,async_setup_binary_sensors
    from custom_components.open_thermostat.heating import HeatingTracker
    from custom_components.open_thermostat.product import INSTALLATION
    p=product(hass);tracker=HeatingTracker(hass,p)
    hass.data.setdefault('open_thermostat',{})[p.entry_id]={'heating_tracker':tracker}
    callbacks={};added=[]
    async def subscribe(hass,topic,callback,*args,**kwargs):
        callbacks.setdefault(topic,[]).append(callback)
        return lambda:None
    monkeypatch.setattr(mqtt,'async_wait_for_mqtt_client',AsyncMock())
    monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    publish=AsyncMock();monkeypatch.setattr(mqtt,'async_publish',publish)
    def add(values, *, config_subentry_id=None):
        assert config_subentry_id in p.subentries
        added.extend(values)
    await async_setup_sensors(hass,p,add);await async_setup_binary_sensors(hass,p,add)
    assert 'fixture/room_data' not in callbacks
    for callback in callbacks['fixture/status']:callback(SimpleNamespace(payload='on'))
    callbacks['fixture/device_status'][0](SimpleNamespace(payload=json.dumps({'mem_free':12345})))
    metric=next(e for e in added if e.unique_id=='fixture_hub_memory_free')
    assert metric.native_value==12345 and metric.available
    assert not any('room_' in e.unique_id for e in added)
    for callback in callbacks['fixture/status']:callback(SimpleNamespace(payload='off'))
    assert not metric.available
    callbacks['fixture/device_status'][0](SimpleNamespace(payload='x'*8193))
    assert metric.native_value==12345
    publish.assert_not_called()
    await tracker.async_stop()

@pytest.mark.asyncio
async def test_normal_room_edit_preserves_existing_external_program_without_exposing_source_choice(hass,managers):
    from homeassistant.helpers import entity_registry as er
    from custom_components.open_thermostat.room_editor import read_room, save_room
    sub,_=managers;p=product(hass);b=room(hass);f=await new_room(sub,p,b)
    f=await sub.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save'});await sub.async_configure(f['flow_id'],{})
    z=next(s for s in p.subentries.values() if s.subentry_type=='zone')
    m=read_room(hass,p.entry_id,z.data['room_id']);helper=er.async_get(hass).async_get_or_create('schedule','schedule','previous_program')
    settings=deepcopy(m['settings']);settings.update(program_source='helper',schedule_entity=helper.entity_id)
    await save_room(hass,p.entry_id,z.data['room_id'],m['token'],settings,confirm_source_change=True)
    saved=deepcopy(dict(p.subentries[z.subentry_id].data)['schedule'])
    f=await sub.async_init((p.entry_id,'zone'),context={'source':'reconfigure','subentry_id':z.subentry_id})
    assert f['step_id']=='edit_room'
    assert 'schedule_entity' not in str(f['data_schema'])
    result=await sub.async_configure(f['flow_id'],{'name':'Renamed existing room','emitter':'radiator','temperature_entity':b.temperature.entity_id,'radiator_entities':[b.actuators[0].entity_id],'base_temperature':19})
    assert result['reason']=='room_saved',result
    assert dict(p.subentries[z.subentry_id].data)['schedule']==saved
    assert read_room(hass,p.entry_id,z.data['room_id'])['settings']['program_source']=='helper'


@pytest.mark.asyncio
async def test_native_product_removes_dead_legacy_identities_without_overriding_users(hass,monkeypatch):
    from homeassistant.helpers import entity_registry as er
    from homeassistant.components import mqtt
    from custom_components.open_thermostat.native_entity_cleanup import cleanup_stale_entities
    from custom_components.open_thermostat.product_telemetry import async_setup_binary_sensors
    p=product(hass);reg=er.async_get(hass)
    def record(domain,uid,**kw):return reg.async_get_or_create(domain,'open_thermostat',uid,config_entry=p,**kw).entity_id
    legacy=[record('binary_sensor','fixture_hub_connected'),record('binary_sensor','fixture_hub_boiler_burner_active'),
            record('sensor','fixture_hub_boiler_pressure'),record('sensor','fixture_hub_dhw_capabilities'),
            record('sensor','fixture_hub_rtc_temperature')]
    kept=[record('sensor','fixture_hub_cpu_temperature'),record('sensor','fixture_hub_energy_v2'),
          record('sensor','fixture_boiler_fields_v1_measured_flow_temperature')]
    user=record('sensor','fixture_hub_boiler_service_code',disabled_by=er.RegistryEntryDisabler.USER)
    renamed=record('sensor','fixture_hub_boiler_display_code')
    reg.async_update_entity(renamed,name='My display code')
    total=len(reg.entities)
    cleanup_stale_entities(hass,p,'fixture')
    assert all(reg.async_get(x) is None for x in legacy) and len(reg.entities)==total-len(legacy)
    assert all(reg.async_get(x).disabled_by is None for x in kept)
    assert reg.async_get(user).disabled_by is er.RegistryEntryDisabler.USER
    # A customised legacy record stays, but disabled: native firmware never feeds it.
    assert reg.async_get(renamed).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    subscribe=AsyncMock();monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    hass.data['open_thermostat'][p.entry_id]={'v1_runtime':object()};added=[]
    await async_setup_binary_sensors(hass,p,lambda entities,**kw:added.extend(entities))
    assert not added and not subscribe.called
