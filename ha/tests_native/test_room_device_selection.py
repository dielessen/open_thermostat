"""Real native registry lifecycle: UI observations and atomic identity fencing."""
from copy import deepcopy
import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from test_room_editor import configured, changed


def identities(model, settings=None):
    settings = settings or model['settings']
    ids = [settings['temperature_entity'], *settings['radiator_entities']]
    if settings['schedule_entity']:
        ids.append(settings['schedule_entity'])
    choices = {x['value']: x for values in model['choices'].values() for x in values}
    return {entity_id: choices[entity_id]['identity'] for entity_id in ids}


def selected(model, role):
    return model['settings']['temperature_entity'] if role == 'sensor' else model['settings']['radiator_entities'][0]


def reuse(hass, entity_id):
    registry = er.async_get(hass)
    registry.async_remove(entity_id); hass.states.async_remove(entity_id)
    domain, object_id = entity_id.split('.', 1)
    replacement = registry.async_get_or_create(domain, 'fixture_driver', 'replacement_' + object_id,
                                               suggested_object_id=object_id)
    assert replacement.entity_id == entity_id
    attrs = {'device_class': 'temperature', 'unit_of_measurement': '°C'} if domain == 'sensor' else {
        'supported_features': 1, 'min_temp': 5, 'max_temp': 30, 'target_temp_step': .5}
    hass.states.async_set(entity_id, '20' if domain == 'sensor' else 'heat', attrs)
    return replacement


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['sensor', 'climate'])
@pytest.mark.parametrize('state', ['unknown', 'unavailable', 'no_state'])
async def test_offline_bound_device_remains_visible_with_identity_and_no_config_changes(hass, configured, role, state):
    parent, sub, model = configured; before = configuration_snapshot(parent)
    entity_id = selected(model, role)
    if state == 'no_state': hass.states.async_remove(entity_id)
    else: hass.states.async_set(entity_id, state)
    result = ui.read_room(hass, parent.entry_id, model['room_id'])
    choice = next(x for x in result['choices'][role] if x['value'] == entity_id)
    assert choice['status'] == state and choice['identity'] == identities(model)[entity_id]
    assert selected(result, role) == entity_id
    assert configuration_snapshot(parent) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['sensor', 'climate'])
async def test_disabled_binding_is_retained_as_explicit_unresolved_selection(hass, configured, role):
    parent, sub, model = configured; before = configuration_snapshot(parent)
    entity_id = selected(model, role)
    er.async_get(hass).async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    result = ui.read_room(hass, parent.entry_id, model['room_id']); marker = selected(result, role)
    assert marker.startswith('unresolved:')
    choice = next(x for x in result['choices'][role] if x['value'] == marker)
    assert choice['status'] == 'disabled' and 'identity' not in choice
    with pytest.raises(ValueError):
        await ui.save_room(hass, parent.entry_id, model['room_id'], result['token'], changed(result))
    assert configuration_snapshot(parent) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['sensor', 'climate'])
async def test_missing_identity_cannot_be_replaced_by_same_id_on_old_or_new_client_save(hass, configured, role):
    parent, sub, model = configured; before = configuration_snapshot(parent)
    entity_id = selected(model, role); replacement = reuse(hass, entity_id)
    for provided in [None, identities(model)]:
        with pytest.raises(ValueError, match='binding_missing'):
            await ui.save_room(hass, parent.entry_id, model['room_id'], model['token'], changed(model),
                               binding_identities=provided)
        assert configuration_snapshot(parent) == before
    result = ui.read_room(hass, parent.entry_id, model['room_id']); marker = selected(result, role)
    assert marker.startswith('unresolved:')
    assert next(x for x in result['choices'][role] if x['value'] == marker)['status'] == 'identity_changed'
    assert next(x for x in result['choices'][role] if x['value'] == entity_id)['identity']['unique_id'] == replacement.unique_id
    # Explicit new selection is allowed; there is no implicit adoption of the old display ID.
    settings = changed(result)
    if role == 'sensor': settings['temperature_entity'] = entity_id
    else: settings['radiator_entities'] = [entity_id]
    saved = await ui.save_room(hass, parent.entry_id, result['room_id'], result['token'], settings,
                               binding_identities=identities(result, settings))
    assert saved['settings'] == settings
    assert identities(saved)[entity_id]['unique_id'] == replacement.unique_id
    assert saved['settings']['week']['monday'] == settings['week']['monday']


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['sensor', 'climate'])
async def test_registry_rename_retains_binding_identity_and_config_without_guessing_by_old_id(hass, configured, role):
    parent, sub, model = configured; before = configuration_snapshot(parent)
    entity_id = selected(model, role); renamed = entity_id + '_renamed'
    er.async_get(hass).async_update_entity(entity_id, new_entity_id=renamed)
    result = ui.read_room(hass, parent.entry_id, model['room_id'])
    assert selected(result, role) == renamed
    assert identities(result)[renamed] == identities(model)[entity_id]
    assert configuration_snapshot(parent) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['sensor', 'climate'])
async def test_identity_rechecked_after_last_compilation_await_without_partial_commit(hass, configured, monkeypatch, role):
    parent, sub, model = configured; before = configuration_snapshot(parent)
    async def replace_during_compile(*args): reuse(hass, selected(model, role))
    monkeypatch.setattr(hass, 'async_add_executor_job', replace_during_compile)
    with pytest.raises(ValueError, match='binding_missing'):
        await ui.save_room(hass, parent.entry_id, model['room_id'], model['token'], changed(model),
                           binding_identities=identities(model))
    assert configuration_snapshot(parent) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('value', ['nan', 'inf', 'not a number'])
async def test_unusable_temperature_is_observation_not_available_measurement(hass, configured, value):
    parent, sub, model = configured; entity_id = selected(model, 'sensor')
    hass.states.async_set(entity_id, value, {'device_class':'temperature', 'unit_of_measurement':'°C'})
    result = ui.read_room(hass, parent.entry_id, model['room_id'])
    assert next(x for x in result['choices']['sensor'] if x['value'] == entity_id)['status'] == 'invalid_temperature'


@pytest.mark.asyncio
async def test_replacement_cannot_steal_an_output_owned_by_another_room(hass, configured):
    from dataclasses import replace
    from test_v1_native import entry, room
    from custom_components.open_thermostat.v1_config_flow import reference
    parent, sub, model = configured; before = configuration_snapshot(parent)
    entity_id = selected(model, 'climate'); reuse(hass, entity_id)
    other = room(hass, room_id='bbbb1111', suffix='other')
    other = replace(other, actuators=(reference(hass, entity_id),))
    entry(hass, room=other)
    result = ui.read_room(hass, parent.entry_id, model['room_id']); settings = changed(result)
    settings['radiator_entities'] = [entity_id]
    with pytest.raises(ValueError, match='output_has_multiple_owners'):
        await ui.save_room(hass, parent.entry_id, result['room_id'], result['token'], settings,
                           binding_identities=identities(result, settings))
    assert configuration_snapshot(parent) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['missing', 'extra', 'wrong_identity'])
async def test_explicit_selection_identities_must_match_the_whole_atomic_selection(hass, configured, fault):
    parent, sub, model = configured; before = configuration_snapshot(parent); expected = identities(model)
    entity_id = selected(model, 'sensor')
    if fault == 'missing': expected.pop(entity_id)
    if fault == 'extra': expected['sensor.extra'] = dict(platform='fixture_driver', unique_id='extra')
    if fault == 'wrong_identity': expected[entity_id]['unique_id'] = 'other_identity'
    with pytest.raises(ValueError, match='binding_missing'):
        await ui.save_room(hass, parent.entry_id, model['room_id'], model['token'], changed(model),
                           binding_identities=expected)
    assert configuration_snapshot(parent) == before
