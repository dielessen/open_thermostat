"""Final native dispatch checks; synthetic authorization, never hardware IO."""
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, device_registry as dr

from custom_components.open_thermostat.v1_profile_c import ProfileCActuator
from test_v1_native import room, entry


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['replace', 'rename', 'disable', 'capability', 'unavailable', 'feature', 'unit', 'device'])
async def test_final_authorization_cannot_dispatch_to_changed_binding_or_capability(hass, mutation):
    binding = room(hass)
    entity_id = binding.actuators[0].entity_id
    registry = er.async_get(hass)
    parent = entry(hass, room=binding)
    replacement_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=parent.entry_id, identifiers={('fixture', 'replacement')})
    calls, checks = [], []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))

    saved_state = hass.states.get(entity_id)

    def authorize():
        checks.append(True)
        if len(checks) != 2:
            return True
        if mutation == 'replace':
            registry.async_remove(entity_id)
            hass.states.async_remove(entity_id)
            replacement = registry.async_get_or_create('climate', 'fixture_driver', 'replacement',
                suggested_object_id=entity_id.split('.')[1])
            assert replacement.entity_id == entity_id
            hass.states.async_set(entity_id, 'heat', dict(saved_state.attributes))
        elif mutation == 'rename':
            registry.async_update_entity(entity_id, new_entity_id='climate.renamed')
        elif mutation == 'disable':
            registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        elif mutation == 'device':
            # Rebind the exact entity row to a different physical device.
            registry.async_update_entity(entity_id, device_id=replacement_device.id)
        else:
            state = hass.states.get(entity_id)
            attrs = dict(state.attributes)
            if mutation == 'capability': attrs['max_temp'] = 19
            if mutation == 'feature': attrs['supported_features'] = 0
            if mutation == 'unit': attrs['unit_of_measurement'] = '°F'
            hass.states.async_set(entity_id, 'unavailable' if mutation == 'unavailable' else 'heat', attrs)
        return True

    actuator = ProfileCActuator(hass, entity_id, qualified_profile=True, authorize=authorize)
    with pytest.raises(HomeAssistantError):
        await actuator.async_set_room_target(21)
    assert calls == []


@pytest.mark.asyncio
async def test_adapter_does_not_follow_replacement_before_next_action(hass):
    binding = room(hass)
    entity_id = binding.actuators[0].entity_id
    calls = []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    actuator = ProfileCActuator(hass, entity_id, qualified_profile=True, authorize=lambda: True)
    registry = er.async_get(hass)
    original = registry.async_get(entity_id)
    saved_state = hass.states.get(entity_id)
    registry.async_remove(entity_id)
    hass.states.async_remove(entity_id)
    replacement = registry.async_get_or_create('climate', 'fixture_driver', 'new-device',
        suggested_object_id=entity_id.split('.')[1])
    assert original.id != replacement.id and replacement.entity_id == entity_id
    hass.states.async_set(entity_id, 'heat', dict(saved_state.attributes))
    with pytest.raises(HomeAssistantError):
        await actuator.async_set_room_target(21)
    assert calls == []


@pytest.mark.asyncio
async def test_display_name_change_preserves_original_binding(hass):
    binding = room(hass)
    entity_id = binding.actuators[0].entity_id
    calls = []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    actuator = ProfileCActuator(hass, entity_id, qualified_profile=True, authorize=lambda: True)
    er.async_get(hass).async_update_entity(entity_id, name='New display label')
    assert await actuator.async_set_room_target(21) == 21
    assert len(calls) == 1
