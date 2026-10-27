"""Native editor/wizard comfort selection and atomic identity handling."""
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

PROFILE={'away_centi_c':1700,'frost_centi_c':500,'temporary_ms':600000}


def person(hass,key='room_presence'):
    tracker=er.async_get(hass).async_get_or_create('device_tracker','presence_fixture','tracker_'+key)
    hass.states.async_set(tracker.entity_id,'home',{'source_type':'router'})
    source=er.async_get(hass).async_get_or_create('person','person',key)
    hass.states.async_set(source.entity_id,'home',{'source':tracker.entity_id,'device_trackers':[tracker.entity_id]})
    return source


@pytest.mark.asyncio
async def test_editor_enables_preserves_and_removes_comfort_and_presence(hass,configured):
    parent,sub,model=configured;source=person(hass)
    model=ui.read_room(hass,parent.entry_id,model['room_id']);settings=deepcopy(model['settings'])
    assert source.entity_id in [c['value'] for c in model['choices']['person']]
    settings.update(comfort=deepcopy(PROFILE),presence_entity=source.entity_id)
    saved=await ui.save_room(hass,parent.entry_id,model['room_id'],model['token'],settings)
    binding=RoomBinding.from_dict(dict(parent.subentries[sub.subentry_id].data))
    assert binding.comfort==PROFILE and binding.presence.unique_id==source.unique_id
    legacy=deepcopy(saved['settings']);legacy.pop('comfort');legacy.pop('presence_entity');legacy['name']='Legacy rename'
    saved=await ui.save_room(hass,parent.entry_id,model['room_id'],saved['token'],legacy)
    assert saved['settings']['comfort']==PROFILE and saved['settings']['presence_entity']==source.entity_id
    settings=deepcopy(saved['settings']);settings.update(comfort=None,presence_entity='')
    saved=await ui.save_room(hass,parent.entry_id,model['room_id'],saved['token'],settings)
    raw=parent.subentries[sub.subentry_id].data
    assert saved['settings']['comfort'] is None and not {'comfort','window','presence'}&raw.keys()
    assert raw['temperature']==sub.data['temperature'] and raw['room_id']==sub.data['room_id']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['missing_person','wrong_domain','without_comfort','profile_boolean','target_boolean','outside_bounds','frost_profile','duration','extra_key','partial_fields','race'])
async def test_bad_or_racing_comfort_edit_never_partially_saves(hass,configured,monkeypatch,fault):
    parent,sub,model=configured;source=person(hass);settings=deepcopy(model['settings'])
    settings.update(comfort=deepcopy(PROFILE),presence_entity=source.entity_id)
    if fault=='missing_person':settings['presence_entity']='person.missing'
    if fault=='wrong_domain':settings['presence_entity']=settings['temperature_entity']
    if fault=='without_comfort':settings['comfort']=None
    if fault=='profile_boolean':settings['comfort']=True
    if fault=='target_boolean':settings['comfort']['away_centi_c']=True
    if fault=='outside_bounds':settings['comfort']['away_centi_c']=4000
    if fault=='frost_profile':settings['comfort']['frost_centi_c']=600
    if fault=='duration':settings['comfort']['temporary_ms']=43200001
    if fault=='extra_key':settings['comfort']['trusted']=True
    if fault=='partial_fields':settings.pop('presence_entity')
    if fault=='race':
        async def executor(*args):er.async_get(hass).async_remove(source.entity_id)
        monkeypatch.setattr(hass,'async_add_executor_job',executor)
    before=configuration_snapshot(parent)
    with pytest.raises(ValueError):await ui.save_room(hass,parent.entry_id,model['room_id'],model['token'],settings)
    assert configuration_snapshot(parent)==before


@pytest.mark.asyncio
async def test_wizard_reviews_preserves_and_explicitly_disables_presence_comfort(hass,manager):
    binding=room(hass);parent=entry(hass);source=person(hass);form=await start(manager,parent)
    review=await manager.async_configure(form['flow_id'],values(binding,advanced={
        'comfort_enabled':True,'presence_entity':source.entity_id,'away_temperature':17,'frost_temperature':5,'override_minutes':10}))
    assert review['step_id']=='room_review' and not parent.subentries
    assert review['description_placeholders']['presence']==hass.states.get(source.entity_id).name
    await manager.async_configure(form['flow_id'],{})
    sub=next(s for s in parent.subentries.values() if s.subentry_type=='zone')
    before=deepcopy(dict(sub.data));saved_binding=RoomBinding.from_dict(before)
    assert saved_binding.comfort==PROFILE and saved_binding.presence.unique_id==source.unique_id
    form=await start(manager,parent,sub.subentry_id);assert form['step_id']=='radiator'
    await manager.async_configure(form['flow_id'],values(binding));await manager.async_configure(form['flow_id'],{})
    assert dict(parent.subentries[sub.subentry_id].data)==before
    form=await start(manager,parent,sub.subentry_id)
    await manager.async_configure(form['flow_id'],values(binding,advanced={'comfort_enabled':False}))
    await manager.async_configure(form['flow_id'],{})
    raw=parent.subentries[sub.subentry_id].data
    assert not {'comfort','presence','window'}&raw.keys() and raw['temperature']==before['temperature']


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['removed','replaced','disabled'])
async def test_final_wizard_save_requires_original_presence_identity(hass,manager,fault):
    binding=room(hass);parent=entry(hass);source=person(hass);form=await start(manager,parent)
    review=await manager.async_configure(form['flow_id'],values(binding,advanced={'comfort_enabled':True,'presence_entity':source.entity_id}))
    assert review['step_id']=='room_review'
    registry=er.async_get(hass)
    if fault in ('removed','replaced'):
        registry.async_remove(source.entity_id)
        if fault=='replaced':registry.async_get_or_create('person','person','new_identity',suggested_object_id=source.entity_id.split('.')[1])
    else:registry.async_update_entity(source.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    result=await manager.async_configure(form['flow_id'],{})
    assert result['step_id']=='room_review' and result['errors'] and not parent.subentries


@pytest.mark.asyncio
async def test_disabling_comfort_preserves_legacy_window_as_explicit_contact(hass,configured):
    parent,sub,model=configured
    window=er.async_get(hass).async_get_or_create('binary_sensor','fixture','legacy_window')
    hass.states.async_set(window.entity_id,'off',{'device_class':'window'})
    original=replace(RoomBinding.from_dict(dict(sub.data)),comfort=dict(PROFILE),window=reference(hass,window.entity_id))
    hass.config_entries.async_update_subentry(parent,sub,data=original.as_dict())
    model=ui.read_room(hass,parent.entry_id,model['room_id']);settings=deepcopy(model['settings'])
    settings.update(comfort=None,presence_entity='')
    old_client=deepcopy(settings);old_client.pop('contact_entities');old_client.pop('contact_policy')
    before=configuration_snapshot(parent)
    with pytest.raises(ValueError,match='^comfort_window_requires_contacts$'):
        await ui.save_room(hass,parent.entry_id,model['room_id'],model['token'],old_client)
    assert configuration_snapshot(parent)==before
    saved=await ui.save_room(hass,parent.entry_id,model['room_id'],model['token'],settings)
    binding=RoomBinding.from_dict(dict(parent.subentries[sub.subentry_id].data))
    assert saved['settings']['comfort'] is None and binding.window is None
    assert len(binding.contacts)==1 and binding.contacts[0].entity.unique_id==window.unique_id
