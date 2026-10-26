"""Native selected-source metadata only: no subscription/report or control grant."""
from copy import deepcopy

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from custom_components.open_thermostat.v1_model import EntityReference
from test_room_editor import configured
from test_device_metadata import devices


@pytest.mark.asyncio
async def test_selected_diagnostic_sensor_is_explicit_without_changing_binding(hass, configured):
    entry, _, model = configured
    entity_id = model['settings']['temperature_entity']
    er.async_get(hass).async_update_entity(entity_id, entity_category=EntityCategory.DIAGNOSTIC)
    before = configuration_snapshot(entry)
    result = ui.read_room(hass, entry.entry_id, model['room_id'])
    assert result['temperature_source_review'] == {
        'status': 'review_required', 'reason': 'diagnostic_entity',
        'scope': 'native_entity_metadata_only', 'authorizes_control': False}
    assert next(x for x in result['choices']['sensor'] if x['value'] == entity_id)['temperature_role'] == 'diagnostic'
    assert result['settings'] == model['settings'] and result['measurement'] == model['measurement']
    assert configuration_snapshot(entry) == before


@pytest.mark.asyncio
async def test_ordinary_numeric_value_does_not_qualify_room_measurement(hass, configured):
    entry, _, model = configured
    result = ui.read_room(hass, entry.entry_id, model['room_id'])
    assert result['temperature_source_review']['reason'] == 'original_report_required'
    assert result['temperature_source_review']['authorizes_control'] is False
    assert result['measurement']['usable'] is False


@pytest.mark.asyncio
async def test_disabled_selected_source_remains_unresolved_not_replaced(hass, configured):
    entry, _, model = configured
    er.async_get(hass).async_update_entity(model['settings']['temperature_entity'], disabled_by=er.RegistryEntryDisabler.USER)
    result = ui.read_room(hass, entry.entry_id, model['room_id'])
    assert result['settings']['temperature_entity'].startswith('unresolved:')
    assert result['temperature_source_review']['reason'] == 'binding_unavailable'
    assert result['temperature_source_review']['authorizes_control'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('property,reason', [('device_temperature', 'internal_device_temperature'), ('temperature', 'original_report_required')])
async def test_existing_native_discovery_distinguishes_internal_temperature_without_network(hass, devices, monkeypatch, property, reason):
    _, references, discoveries = devices
    ref = EntityReference.from_dict(references[0])
    discoveries[0]['value_template'] = '{{ value_json.' + property + ' }}'
    def forbidden(*args, **kwargs):
        raise AssertionError('source review must not subscribe or publish')
    monkeypatch.setattr('homeassistant.components.mqtt.async_subscribe', forbidden)
    before = deepcopy(discoveries[0])
    review = ui._temperature_source_review(hass, ref, ref.entity_id)
    assert review['reason'] == reason and review['authorizes_control'] is False
    assert discoveries[0] == before
    assert set(review) == {'status', 'reason', 'scope', 'authorizes_control'}


@pytest.mark.asyncio
async def test_native_rename_preserves_internal_role_without_exporting_private_identity(hass, devices):
    _, references, _ = devices
    ref = EntityReference.from_dict(references[0])
    renamed = er.async_get(hass).async_update_entity(ref.entity_id, new_entity_id='sensor.renamed_temperature')
    review = ui._temperature_source_review(hass, ref, renamed.entity_id)
    assert review['reason'] == 'original_report_required'  # native cache has not followed yet
    from homeassistant.components.mqtt.models import DATA_MQTT
    cache = hass.data[DATA_MQTT].debug_info_entities
    cache[renamed.entity_id] = cache.pop(ref.entity_id)
    review = ui._temperature_source_review(hass, ref, renamed.entity_id)
    assert review['reason'] == 'internal_device_temperature'
    assert not any(x in str(review) for x in ['0x0000', 'custom-z2m', ref.unique_id])


@pytest.mark.asyncio
@pytest.mark.parametrize('corrupt', [None, [], {'discovery_data': None}])
async def test_corrupt_optional_native_cache_cannot_break_source_review(hass, devices, corrupt):
    from homeassistant.components.mqtt.models import DATA_MQTT
    _, references, _ = devices
    ref = EntityReference.from_dict(references[0])
    hass.data[DATA_MQTT].debug_info_entities[ref.entity_id] = corrupt
    review = ui._temperature_source_review(hass, ref, ref.entity_id)
    assert review['reason'] == 'original_report_required' and not review['authorizes_control']
