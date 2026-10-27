"""Real HA room wizard contact selection and atomic final save, no device IO."""
from copy import deepcopy
import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat.v1_model import RoomBinding
from test_room_setup_flow import manager, start, values
from test_v1_native import room, entry


def contacts(hass):
    result = []
    for kind in ('window', 'door'):
        row = er.async_get(hass).async_get_or_create('binary_sensor', 'wizard_fixture', kind)
        hass.states.async_set(row.entity_id, 'off', {'device_class': kind})
        result.append(row)
    return result


@pytest.mark.asyncio
async def test_wizard_saves_two_contacts_at_final_review_and_preserves_them_on_next_edit(hass, manager):
    binding = room(hass); parent = entry(hass); sensors = contacts(hass)
    form = await start(manager, parent)
    data = values(binding, contact_entities=[c.entity_id for c in sensors], advanced={
        'contact_open_delay_s': 5, 'contact_close_delay_s': 60, 'contact_maximum_age_s': 7200})
    review = await manager.async_configure(form['flow_id'], data)
    assert review['step_id'] == 'room_review' and not parent.subentries
    assert all(hass.states.get(c.entity_id).name in review['description_placeholders']['contacts'] for c in sensors)
    result = await manager.async_configure(form['flow_id'], {})
    assert result['reason'] == 'room_saved'
    sub = next(s for s in parent.subentries.values() if s.subentry_type == 'zone')
    saved = RoomBinding.from_dict(dict(sub.data))
    assert [c.entity.unique_id for c in saved.contacts] == [c.unique_id for c in sensors]
    assert saved.contact_policy.as_dict() == {'open_delay_ms': 5000, 'close_delay_ms': 60000, 'maximum_age_ms': 7200000}
    before = deepcopy(dict(sub.data))
    form = await start(manager, parent, sub.subentry_id)
    assert form['step_id'] == 'radiator'
    review = await manager.async_configure(form['flow_id'], values(binding))
    assert review['step_id'] == 'room_review'
    await manager.async_configure(form['flow_id'], {})
    assert dict(parent.subentries[sub.subentry_id].data) == before
    form = await start(manager, parent, sub.subentry_id)
    await manager.async_configure(form['flow_id'], values(binding, contact_entities=[]))
    await manager.async_configure(form['flow_id'], {})
    assert 'contacts' not in parent.subentries[sub.subentry_id].data
    assert 'contact_policy' not in parent.subentries[sub.subentry_id].data
    assert (await start(manager, parent, sub.subentry_id))['step_id'] == 'radiator'


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['duplicate', 'wrong_kind', 'too_many', 'delay_not_whole', 'delay_exceeds_age'])
async def test_invalid_wizard_contacts_do_not_write_a_partial_room(hass, manager, fault):
    binding = room(hass); parent = entry(hass); sensors = contacts(hass)
    form = await start(manager, parent)
    data = values(binding, contact_entities=[sensors[0].entity_id])
    if fault == 'duplicate': data['contact_entities'] *= 2
    if fault == 'wrong_kind': hass.states.async_set(sensors[0].entity_id, 'off', {'device_class': 'motion'})
    if fault == 'too_many': data['contact_entities'] *= 9
    if fault == 'delay_not_whole': data['advanced'] = {'contact_open_delay_s': 0.5}
    if fault == 'delay_exceeds_age': data['advanced'] = {'contact_close_delay_s': 60, 'contact_maximum_age_s': 30}
    result = await manager.async_configure(form['flow_id'], data)
    assert result['step_id'] == 'radiator' and result['errors'] and not parent.subentries


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['removed', 'replaced', 'wrong_kind', 'disabled'])
async def test_final_wizard_save_rechecks_the_selected_contact_identity(hass, manager, fault):
    binding = room(hass); parent = entry(hass); sensors = contacts(hass)
    form = await start(manager, parent)
    review = await manager.async_configure(form['flow_id'], values(binding, contact_entities=[sensors[0].entity_id]))
    assert review['step_id'] == 'room_review'
    registry = er.async_get(hass); eid = sensors[0].entity_id
    if fault in ('removed', 'replaced'):
        registry.async_remove(eid)
        if fault == 'replaced':
            registry.async_get_or_create('binary_sensor', 'wizard_fixture', 'new_identity', suggested_object_id=eid.split('.')[1])
    if fault == 'wrong_kind': hass.states.async_set(eid, 'off', {'device_class': 'motion'})
    if fault == 'disabled': registry.async_update_entity(eid, disabled_by=er.RegistryEntryDisabler.USER)
    result = await manager.async_configure(form['flow_id'], {})
    assert result['step_id'] == 'room_review' and result['errors'] and not parent.subentries
