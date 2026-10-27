"""Native HA setup, preservation, cancellation, ownership and paired Store writes."""
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.room_setup_flow import RadiatorRoomSetupFlow
from test_v1_native import entry, room
from test_v1_heating_graph_gui import create_central, open_graph, add_group, add_actuator, menu, heating

@pytest.fixture
def manager(hass, monkeypatch):
    monkeypatch.setattr(config_entries, '_async_get_flow_handler', AsyncMock(return_value=OpenThermostatConfigFlow))
    return hass.config_entries.subentries

async def start(manager, parent, selected='new'):
    f=await manager.async_init((parent.entry_id,'room_setup'), context={'source':'user'})
    return await manager.async_configure(f['flow_id'], {'room':selected})

def values(binding, **kw):
    return dict(name=binding.name, temperature_entity=binding.temperature.entity_id,
                radiator_entities=[binding.actuators[0].entity_id], base_temperature=21, program_action='save', **kw)

async def review(manager, parent, binding, selected='new', **kw):
    f=await start(manager,parent,selected)
    f=await manager.async_configure(f['flow_id'],values(binding,**kw))
    assert f['step_id']=='room_review', f
    return f

@pytest.mark.asyncio
async def test_new_room_pair_commits_only_at_final_save_and_survives_reload(hass,manager):
    b=room(hass);p=entry(hass);old_opts=dict(p.options);old_data=dict(p.data)
    f=await review(manager,p,b)
    assert not p.subentries
    seen=[]
    async def listener(hass, entry):
        seen.append(sorted(s.subentry_type for s in entry.subentries.values()))
    p.add_update_listener(listener)
    result=await manager.async_configure(f['flow_id'],{})
    assert result['reason']=='room_saved'
    await hass.async_block_till_done()
    assert seen and all(s==['heating','zone'] for s in seen)
    z=next(s for s in p.subentries.values() if s.subentry_type=='zone');g=heating(p)
    assert z.data['binding_mode']=='graph_only_draft' and z.data['actuators']==[]
    assert g.data['draft']['actuators'][0]['room_id']==z.data['room_id']
    assert g.data['draft']['actuators'][0]['output']==b.actuators[0].as_dict()
    assert g.data['status']=='draft_not_applied' and g.data['incomplete_group_ids']==[]
    assert dict(p.options)==old_opts and dict(p.data)==old_data
    saved={k:s.as_dict() for k,s in p.subentries.items()}
    await hass.async_stop(force=True)
    second=HomeAssistant(hass.config.config_dir);second.config_entries=ConfigEntries(second,{})
    try:
        await second.config_entries.async_initialize()
        restored=second.config_entries.async_get_entry(p.entry_id)
        assert {k:s.as_dict() for k,s in restored.subentries.items()}==saved
    finally: await second.async_stop(force=True)

@pytest.mark.asyncio
async def test_existing_room_migrates_with_same_identity_week_bounds_and_helper_values(hass,manager):
    b=replace(room(hass),minimum_target_centi_c=1600,maximum_target_centi_c=2400,maximum_age_ms=180000,
              week_program={'monday':[dict(start=3600,end=7200,target_centi_c=2050)]})
    p=entry(hass,room=b);z=next(iter(p.subentries.values()));before=deepcopy(dict(z.data))
    f=await review(manager,p,b,z.subentry_id)
    assert dict(z.data)==before and len(p.subentries)==1
    await manager.async_configure(f['flow_id'],{})
    assert next(s for s in p.subentries.values() if s.subentry_type=='zone') .subentry_id == z.subentry_id
    for k in ('room_id','week_program','minimum_target_centi_c','maximum_target_centi_c','maximum_age_ms','temperature','schedule'):
        assert p.subentries[z.subentry_id].data[k]==before[k],k
    gid=heating(p).data['draft']['groups'][0]['group_id'];aid=heating(p).data['draft']['actuators'][0]['actuator_id']
    f=await review(manager,p,b,z.subentry_id)
    await manager.async_configure(f['flow_id'],{})
    assert len(heating(p).data['draft']['groups'])==1
    assert heating(p).data['draft']['groups'][0]['group_id']==gid
    assert heating(p).data['draft']['actuators'][0]['actuator_id']==aid

@pytest.mark.asyncio
async def test_keeps_other_rooms_shared_group_and_existing_central_settings(hass,manager):
    b=room(hass);p=entry(hass,room=b);z=next(iter(p.subentries.values()))
    await create_central(manager,p)
    f=await open_graph(manager,p);f=await add_group(manager,f)
    f=await add_actuator(manager,f,b.room_id,b.actuators[0].entity_id);await menu(manager,f,'save_graph')
    before=deepcopy(dict(heating(p).data))
    f=await review(manager,p,b,z.subentry_id)
    await manager.async_configure(f['flow_id'],{})
    assert dict(heating(p).data)==before

@pytest.mark.asyncio
@pytest.mark.parametrize('point',['radiator','review','week'])
async def test_cancel_never_writes_room_or_group(hass,manager,point):
    b=room(hass);p=entry(hass,room=b);before={k:s.as_dict() for k,s in p.subentries.items()}
    f=await start(manager,p,next(iter(p.subentries)))
    if point in ('review','week'):
        v=values(b);v['program_action']='edit_week' if point=='week' else 'save'
        f=await manager.async_configure(f['flow_id'],v)
    manager.async_abort(f['flow_id'])
    assert {k:s.as_dict() for k,s in p.subentries.items()}==before

@pytest.mark.asyncio
async def test_local_week_editor_defers_pair_until_final_review(hass,manager):
    b=room(hass);p=entry(hass)
    f=await start(manager,p);v=values(b);v['program_action']='edit_week'
    f=await manager.async_configure(f['flow_id'],v)
    f=await menu(manager,f,'add_block')
    f=await manager.async_configure(f['flow_id'],dict(days=['monday'],start_time='07:00:00',
         end_time='09:00:00',end_at_midnight=False,temperature=22))
    f=await menu(manager,f,'save_program')
    assert f['step_id']=='room_review' and not p.subentries
    await manager.async_configure(f['flow_id'],{})
    z=next(s for s in p.subentries.values() if s.subentry_type=='zone')
    assert z.data['week_program']['monday'][0]['target_centi_c']==2200

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['runtime','room','graph','remove_entry'])
async def test_final_save_rejects_concurrent_change(hass,manager,change):
    b=room(hass);p=entry(hass,room=b);z=next(iter(p.subentries.values()))
    f=await review(manager,p,b,z.subentry_id)
    if change=='runtime':hass.config_entries.async_update_entry(p,options={**p.options,'shadow_enabled':True})
    elif change=='room':hass.config_entries.async_update_subentry(p,z,title='Changed')
    elif change=='graph':await create_central(manager,p)
    else: hass.config_entries._entries.pop(p.entry_id)
    after={k:s.as_dict() for k,s in p.subentries.items()}
    r=await manager.async_configure(f['flow_id'],{})
    assert r['type']=='abort' and r['reason'] in ('setup_runtime_off','setup_changed')
    assert {k:s.as_dict() for k,s in p.subentries.items()}==after

@pytest.mark.asyncio
@pytest.mark.parametrize('existing',[False,True])
async def test_single_native_transaction_failure_leaves_both_unchanged(hass,manager,monkeypatch,existing):
    b=room(hass);p=entry(hass,room=b if existing else None)
    before={k:s.as_dict() for k,s in p.subentries.items()}
    f=await review(manager,p,b,next(iter(p.subentries)) if existing else 'new')
    def fail_save(*args,**kw):raise RuntimeError('injected pre-save failure')
    monkeypatch.setattr(hass.config_entries,'_async_update_entry',fail_save)
    r=await manager.async_configure(f['flow_id'],{})
    assert r['reason']=='setup_save_uncertain'
    assert {k:s.as_dict() for k,s in p.subentries.items()}==before

@pytest.mark.asyncio
async def test_duplicate_or_other_controller_valves_and_missing_final_binding_do_not_save(hass,manager):
    b=room(hass);other=entry(hass,room=b);p=entry(hass)
    f=await start(manager,p)
    r=await manager.async_configure(f['flow_id'],values(b))
    assert r['errors']['base']=='output_has_multiple_owners' and not p.subentries
    hass.config_entries._entries.pop(other.entry_id)
    r=await manager.async_configure(f['flow_id'],values(b))
    assert r['step_id']=='room_review'
    er.async_get(hass).async_remove(b.actuators[0].entity_id)
    r=await manager.async_configure(f['flow_id'],{})
    assert r['errors']['base']=='setup_invalid' and not p.subentries

@pytest.mark.asyncio
async def test_basic_form_hides_technical_fields_and_preserves_program_helper(hass,manager):
    b=room(hass);helper=er.async_get(hass).async_get_or_create('schedule','fixture_driver','week')
    b=replace(b,schedule=replace(b.temperature,entity_id=helper.entity_id,unique_id=helper.unique_id))
    p=entry(hass,room=b);z=next(iter(p.subentries.values()))
    f=await start(manager,p,z.subentry_id)
    assert {str(k) for k in f['data_schema'].schema}=={'name','temperature_entity','radiator_entities','base_temperature','contact_entities','program_action','advanced'}
    advanced=next(v for k,v in f['data_schema'].schema.items() if str(k)=='advanced')
    assert advanced.options['collapsed'] is True
    f=await manager.async_configure(f['flow_id'],values(b))
    await manager.async_configure(f['flow_id'],{})
    assert p.subentries[z.subentry_id].data['schedule']==b.schedule.as_dict()

@pytest.mark.asyncio
async def test_existing_local_comfort_is_preserved_when_editing_ordinary_room(hass,manager):
    b=replace(room(hass),comfort=dict(away_centi_c=1700,frost_centi_c=500,temporary_ms=60000))
    p=entry(hass,room=b);before={k:s.as_dict() for k,s in p.subentries.items()}
    sub=next(iter(p.subentries));f=await review(manager,p,b,sub)
    assert {k:s.as_dict() for k,s in p.subentries.items()}==before
    result=await manager.async_configure(f['flow_id'],{})
    assert result['reason']=='room_saved'
    assert p.subentries[sub].data['comfort']==b.comfort

@pytest.mark.asyncio
async def test_late_cross_entry_valve_claim_blocks_final_commit(hass,manager):
    b=room(hass);p=entry(hass);f=await review(manager,p,b)
    entry(hass,room=b)
    r=await manager.async_configure(f['flow_id'],{})
    assert r['errors']['base']=='setup_invalid' and not p.subentries

@pytest.mark.asyncio
async def test_unsupported_core_never_starts_the_pinned_map_transaction(hass,manager,monkeypatch):
    from custom_components.open_thermostat import room_setup_flow
    p=entry(hass);monkeypatch.setattr(room_setup_flow,'HA_VERSION','2026.11.0')
    r=await manager.async_init((p.entry_id,'room_setup'),context={'source':'user'})
    assert r['reason']=='setup_platform_unsupported' and not p.subentries

@pytest.mark.asyncio
async def test_registry_rename_at_review_preserves_identity(hass,manager):
    b=room(hass);p=entry(hass);f=await review(manager,p,b)
    er.async_get(hass).async_update_entity(b.actuators[0].entity_id,new_entity_id='climate.renamed_radiator')
    r=await manager.async_configure(f['flow_id'],{})
    assert r['reason']=='room_saved'
    assert heating(p).data['draft']['actuators'][0]['output']['entity_id']=='climate.renamed_radiator'
    assert heating(p).data['draft']['actuators'][0]['output']['unique_id']==b.actuators[0].unique_id

@pytest.mark.asyncio
async def test_duplicate_selected_valve_and_invalid_limits_preserve_form_without_save(hass,manager):
    b=room(hass);p=entry(hass);f=await start(manager,p)
    v=values(b);v['radiator_entities']*=2
    r=await manager.async_configure(f['flow_id'],v)
    assert r['errors']['base']=='output_has_multiple_owners' and not p.subentries
    v=values(b);v['advanced']={'minimum_target_temperature':23,'maximum_target_temperature':24}
    r=await manager.async_configure(f['flow_id'],v)
    assert r['errors']['base']=='invalid_target_range' and not p.subentries
