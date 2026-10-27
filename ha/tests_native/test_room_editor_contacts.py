"""Full native contact edits: registry identity, atomic storage and old clients."""
from copy import deepcopy
import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from custom_components.open_thermostat.v1_model import RoomBinding
from test_room_editor import configured, changed


def source(hass,key,kind='window'):
    item=er.async_get(hass).async_get_or_create('binary_sensor','mqtt','contact_'+key)
    hass.states.async_set(item.entity_id,'off',{'device_class':kind})
    return item


@pytest.mark.asyncio
async def test_complete_room_save_pins_multiple_contacts_and_reaction_policy(hass,configured):
    entry,sub,model=configured
    window=source(hass,'window');door=source(hass,'door','door')
    model=ui.read_room(hass,entry.entry_id,model['room_id']);settings=changed(model)
    settings['contact_entities']=[window.entity_id,door.entity_id]
    settings['contact_policy']={'maximum_age_ms':3600000,'open_delay_ms':5000,'close_delay_ms':60000}
    result=await ui.save_room(hass,entry.entry_id,model['room_id'],model['token'],settings)
    assert result['settings']==settings
    room=RoomBinding.from_dict(dict(entry.subentries[sub.subentry_id].data))
    assert [(c.kind,c.entity.platform,c.entity.unique_id) for c in room.contacts]==[
        ('window','mqtt',window.unique_id),('door','mqtt',door.unique_id)]
    assert room.contact_policy.as_dict()==settings['contact_policy']
    assert room.comfort and room.window is None
    assert RoomBinding.from_dict(room.as_dict())==room
    assert entry.subentries[sub.subentry_id].data['room_id']==model['room_id']


@pytest.mark.asyncio
async def test_explicit_contact_removal_preserves_temperature_week_valves_and_comfort(hass,configured):
    entry,sub,model=configured;window=source(hass,'remove')
    settings=changed(model);settings['contact_entities']=[window.entity_id]
    saved=await ui.save_room(hass,entry.entry_id,model['room_id'],model['token'],settings)
    before=dict(entry.subentries[sub.subentry_id].data)
    cleared=deepcopy(saved['settings']);cleared['contact_entities']=[]
    result=await ui.save_room(hass,entry.entry_id,model['room_id'],saved['token'],cleared)
    after=dict(entry.subentries[sub.subentry_id].data)
    assert result['settings']['contact_entities']==[] and 'contacts' not in after and 'contact_policy' not in after
    for key in ('temperature','week_program','comfort','base_centi_c','room_id'):
        assert after[key]==before[key]


@pytest.mark.asyncio
async def test_older_room_client_cannot_erase_contacts_it_does_not_know(hass,configured):
    entry,sub,model=configured;window=source(hass,'oldclient')
    settings=changed(model);settings['contact_entities']=[window.entity_id]
    saved=await ui.save_room(hass,entry.entry_id,model['room_id'],model['token'],settings)
    legacy=deepcopy(saved['settings']);legacy.pop('contact_entities');legacy.pop('contact_policy');legacy['name']='Legacy rename'
    result=await ui.save_room(hass,entry.entry_id,model['room_id'],saved['token'],legacy)
    assert result['settings']['contact_entities']==[window.entity_id]
    assert result['settings']['name']=='Legacy rename'


@pytest.mark.asyncio
async def test_contact_registry_rename_follows_unique_identity_and_removed_id_is_not_adopted(hass,configured):
    entry,sub,model=configured;window=source(hass,'rename')
    settings=changed(model);settings['contact_entities']=[window.entity_id]
    await ui.save_room(hass,entry.entry_id,model['room_id'],model['token'],settings)
    registry=er.async_get(hass)
    registry.async_update_entity(window.entity_id,new_entity_id='binary_sensor.renamed_contact')
    hass.states.async_set('binary_sensor.renamed_contact','off',{'device_class':'window'})
    renamed=ui.read_room(hass,entry.entry_id,model['room_id'])
    assert renamed['settings']['contact_entities']==['binary_sensor.renamed_contact']
    registry.async_remove('binary_sensor.renamed_contact')
    registry.async_get_or_create('binary_sensor','mqtt','different_contact',suggested_object_id='renamed_contact')
    missing=ui.read_room(hass,entry.entry_id,model['room_id'])
    assert missing['settings']['contact_entities'][0].startswith('unresolved:')
    before=configuration_snapshot(entry)
    with pytest.raises(ValueError):
        await ui.save_room(hass,entry.entry_id,model['room_id'],missing['token'],missing['settings'])
    assert configuration_snapshot(entry)==before


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['duplicate','unknown','wrong_class','not_binary','policy_boolean','policy_huge','extra_policy'])
async def test_invalid_contacts_never_partially_save_room_or_graph(hass,configured,fault):
    entry,sub,model=configured;window=source(hass,'bad')
    settings=changed(model);settings['contact_entities']=[window.entity_id]
    if fault=='duplicate':settings['contact_entities']*=2
    if fault=='unknown':settings['contact_entities']=['binary_sensor.no_such_contact']
    if fault=='wrong_class':hass.states.async_set(window.entity_id,'off',{'device_class':'motion'})
    if fault=='not_binary':settings['contact_entities']=[settings['temperature_entity']]
    if fault=='policy_boolean':settings['contact_policy']['open_delay_ms']=True
    if fault=='policy_huge':settings['contact_policy']['maximum_age_ms']=86400001
    if fault=='extra_policy':settings['contact_policy']['trust']=True
    before=configuration_snapshot(entry)
    with pytest.raises((ValueError,KeyError)):
        await ui.save_room(hass,entry.entry_id,model['room_id'],model['token'],settings)
    assert configuration_snapshot(entry)==before


@pytest.mark.asyncio
async def test_contact_removed_during_compile_await_refuses_the_whole_edit(hass,configured,monkeypatch):
    entry,sub,model=configured;window=source(hass,'await')
    settings=changed(model);settings['contact_entities']=[window.entity_id]
    async def executor(*args):er.async_get(hass).async_remove(window.entity_id)
    monkeypatch.setattr(hass,'async_add_executor_job',executor)
    before=configuration_snapshot(entry)
    with pytest.raises(ValueError):
        await ui.save_room(hass,entry.entry_id,model['room_id'],model['token'],settings)
    assert configuration_snapshot(entry)==before
