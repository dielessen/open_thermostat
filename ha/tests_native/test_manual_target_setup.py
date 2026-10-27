"""Native helper selection, ownership and atomic room edits, no device IO."""
from copy import deepcopy
from dataclasses import replace
import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from custom_components.open_thermostat.v1_model import RoomBinding
from custom_components.open_thermostat.v1_config_flow import reference
from test_room_editor import configured
from test_room_setup_flow import manager, start, values
from test_v1_native import room, entry


def helper(hass, key='target', platform='input_number', unit='°C'):
    row=er.async_get(hass).async_get_or_create('input_number',platform,key)
    hass.states.async_set(row.entity_id,'21',{'unit_of_measurement':unit})
    return row


@pytest.mark.asyncio
async def test_editor_add_preserve_and_remove_helper_without_changing_temperature_or_week(hass,configured):
    parent,sub,model=configured;source=helper(hass)
    model=ui.read_room(hass,parent.entry_id,model['room_id'])
    assert source.entity_id in [c['value'] for c in model['choices']['input_number']]
    settings=deepcopy(model['settings']);settings.update(setpoint_entity=source.entity_id,setpoint_duration_ms=600000)
    saved=await ui.save_room(hass,parent.entry_id,model['room_id'],model['token'],settings)
    binding=RoomBinding.from_dict(dict(parent.subentries[sub.subentry_id].data))
    assert binding.setpoint==reference(hass,source.entity_id) and binding.setpoint_duration_ms==600000
    assert binding.temperature.as_dict()==sub.data['temperature'] and not any(binding.week_program.values())
    legacy=deepcopy(saved['settings']);legacy.pop('setpoint_entity');legacy.pop('setpoint_duration_ms');legacy['name']='Legacy rename'
    saved=await ui.save_room(hass,parent.entry_id,model['room_id'],saved['token'],legacy)
    assert saved['settings']['setpoint_entity']==source.entity_id and saved['settings']['setpoint_duration_ms']==600000
    settings=deepcopy(saved['settings']);settings['setpoint_entity']=''
    saved=await ui.save_room(hass,parent.entry_id,model['room_id'],saved['token'],settings)
    assert saved['settings']['setpoint_entity']=='' and 'setpoint_duration_ms' not in parent.subentries[sub.subentry_id].data


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['platform','unit','missing','boolean','short','long','partial','shared','race'])
async def test_invalid_or_racing_helper_selection_cannot_partially_save(hass,configured,monkeypatch,fault):
    parent,sub,model=configured;source=helper(hass,platform='mqtt' if fault=='platform' else 'input_number',unit='%' if fault=='unit' else '°C')
    settings=deepcopy(model['settings']);settings.update(setpoint_entity=source.entity_id,setpoint_duration_ms=600000)
    if fault=='missing':er.async_get(hass).async_remove(source.entity_id)
    if fault=='boolean':settings['setpoint_duration_ms']=True
    if fault=='short':settings['setpoint_duration_ms']=59999
    if fault=='long':settings['setpoint_duration_ms']=43200001
    if fault=='partial':settings.pop('setpoint_duration_ms')
    if fault=='shared':entry(hass,room=replace(room(hass,'aabb7788','other'),setpoint=reference(hass,source.entity_id)))
    if fault=='race':
        async def executor(*args):er.async_get(hass).async_remove(source.entity_id)
        monkeypatch.setattr(hass,'async_add_executor_job',executor)
    before=configuration_snapshot(parent)
    with pytest.raises(ValueError):await ui.save_room(hass,parent.entry_id,model['room_id'],model['token'],settings)
    assert configuration_snapshot(parent)==before


@pytest.mark.asyncio
async def test_wizard_reviews_pins_preserves_and_removes_helper(hass,manager):
    binding=room(hass);parent=entry(hass);source=helper(hass)
    form=await start(manager,parent)
    review=await manager.async_configure(form['flow_id'],values(binding,advanced={'setpoint_entity':source.entity_id,'setpoint_minutes':10}))
    assert review['step_id']=='room_review' and not parent.subentries
    assert review['description_placeholders']['manual_target']==hass.states.get(source.entity_id).name
    await manager.async_configure(form['flow_id'],{})
    sub=next(s for s in parent.subentries.values() if s.subentry_type=='zone')
    saved=RoomBinding.from_dict(dict(sub.data));assert saved.setpoint==reference(hass,source.entity_id) and saved.setpoint_duration_ms==600000
    before=deepcopy(dict(sub.data));form=await start(manager,parent,sub.subentry_id)
    await manager.async_configure(form['flow_id'],values(binding));await manager.async_configure(form['flow_id'],{})
    assert dict(parent.subentries[sub.subentry_id].data)==before
    form=await start(manager,parent,sub.subentry_id)
    await manager.async_configure(form['flow_id'],values(binding,advanced={}))
    await manager.async_configure(form['flow_id'],{})
    saved=RoomBinding.from_dict(dict(parent.subentries[sub.subentry_id].data))
    assert saved.setpoint is None and 'setpoint_duration_ms' not in parent.subentries[sub.subentry_id].data


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['removed','reused','unit','duration'])
async def test_wizard_rechecks_original_helper_at_final_save(hass,manager,fault):
    binding=room(hass);parent=entry(hass);source=helper(hass);form=await start(manager,parent)
    review=await manager.async_configure(form['flow_id'],values(binding,advanced={'setpoint_entity':source.entity_id,'setpoint_minutes':1.5 if fault=='duration' else 10}))
    if fault=='duration':
        assert review['step_id']=='radiator' and review['errors'] and not parent.subentries
        return
    assert review['step_id']=='room_review'
    if fault in ('removed','reused'):
        er.async_get(hass).async_remove(source.entity_id)
        if fault=='reused':helper(hass,'new_identity')
    if fault=='unit':hass.states.async_set(source.entity_id,'21',{'unit_of_measurement':'%'})
    result=await manager.async_configure(form['flow_id'],{})
    assert result['step_id']=='room_review' and result['errors'] and not parent.subentries
