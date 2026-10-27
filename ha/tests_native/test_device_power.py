"""Real native HA registry/state snapshots; battery data has no control role."""
from datetime import timedelta
from types import MappingProxyType
from unittest.mock import patch
import json

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr, entity_registry as er
from custom_components.open_thermostat.device_power import read_selected_power,MAX_AGE_MS
from custom_components.open_thermostat.v1_model import EntityReference
from custom_components.open_thermostat import room_editor
from custom_components.open_thermostat.product import configuration_snapshot
from test_room_editor import configured


def broker(hass,key='one'):
    entry=ConfigEntry(domain='mqtt',title='isolated battery fixture',version=1,minor_version=1,
        data={},options={},source='user',unique_id='battery_'+key,
        discovery_keys=MappingProxyType({}),subentries_data=[])
    hass.config_entries._entries[entry.entry_id]=entry
    return entry


@pytest_asyncio.fixture
async def selected(hass):
    entry=broker(hass)
    device=dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id,
        identifiers={('mqtt','PRIVATE_SELECTED_DEVICE')},name='Selected sensor')
    registry=er.async_get(hass)
    sensor=registry.async_get_or_create('sensor','mqtt','PRIVATE_SENSOR_ID',suggested_object_id='room_temperature',
        config_entry=entry,device_id=device.id,original_device_class='temperature')
    battery=registry.async_get_or_create('sensor','mqtt','PRIVATE_BATTERY_ID',suggested_object_id='room_battery',
        config_entry=entry,device_id=device.id,original_device_class='battery')
    low=registry.async_get_or_create('binary_sensor','mqtt','PRIVATE_LOW_ID',suggested_object_id='room_battery_low',
        config_entry=entry,device_id=device.id,original_device_class='battery')
    hass.states.async_set(sensor.entity_id,'20',{'device_class':'temperature','unit_of_measurement':'°C'})
    hass.states.async_set(battery.entity_id,'12.5',{'device_class':'battery','unit_of_measurement':'%'})
    hass.states.async_set(low.entity_id,'on',{'device_class':'battery'})
    ref=EntityReference(sensor.entity_id,'mqtt',sensor.unique_id)
    return entry,device,sensor,battery,low,ref


def snapshot(hass,selected):return read_selected_power(hass,[selected[-1]])


@pytest.mark.asyncio
async def test_native_percentage_and_device_flag_are_separate_read_only_reports(hass,selected):
    result=snapshot(hass,selected);row=result['devices'][0]
    assert result['scope']=='native_ha_cached_state_only' and result['physical_control_qualified'] is False
    assert row['battery']['value']==12.5 and row['battery']['status']=='reported'
    assert row['battery_low']['value'] is True and row['battery_low']['status']=='reported'
    # A high percentage never overrides the device's own independent flag.
    hass.states.async_set(selected[3].entity_id,'90',{'device_class':'battery','unit_of_measurement':'%'})
    assert snapshot(hass,selected)['devices'][0]['battery_low']['value'] is True
    exported=json.dumps(result)
    for private in ['PRIVATE_SELECTED_DEVICE','PRIVATE_SENSOR_ID','PRIVATE_BATTERY_ID',selected[0].entry_id,selected[1].id]:
        assert private not in exported


@pytest.mark.asyncio
async def test_zero_is_valid_and_repeated_reads_preserve_original_ha_timestamp(hass,selected):
    battery=selected[3];hass.states.async_set(battery.entity_id,'0',{'device_class':'battery','unit_of_measurement':'%'})
    stamp=hass.states.get(battery.entity_id).last_reported
    with patch('custom_components.open_thermostat.device_power.dt_util.utcnow',return_value=stamp+timedelta(minutes=7)):
        results=[snapshot(hass,selected)['devices'][0]['battery'] for _ in range(10)]
    assert all(row['value']==0 and row['age_ms']==420000 and row['status']=='reported' for row in results)
    assert len({row['reported_at'] for row in results})==1
    assert hass.states.get(battery.entity_id).last_reported==stamp


@pytest.mark.asyncio
@pytest.mark.parametrize('value,expected',[('-0',0.0),('1e-14',1e-14)])
async def test_numeric_projection_does_not_turn_small_reports_into_zero(hass,selected,value,expected):
    hass.states.async_set(selected[3].entity_id,value,{'device_class':'battery','unit_of_measurement':'%'})
    report=snapshot(hass,selected)['devices'][0]['battery']
    assert report['status']=='reported' and report['value']==expected
    assert '-0.0' not in json.dumps(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('value,unit,attrs,status',[
    ('unknown','%',{},'unavailable'),('unavailable','%',{},'unavailable'),
    ('NaN','%',{},'invalid'),('inf','%',{},'invalid'),('-1','%',{},'invalid'),('101','%',{},'invalid'),
    ('True','%',{},'invalid'),('12','V',{},'invalid'),('private-value','%',{},'invalid'),
    ('1e-10000','%',{},'invalid'),
    ('12','%',{'restored':True},'restored'),('12','%',{'restored':'false'},'restored'),
])
async def test_unknown_invalid_and_restored_percentages_never_become_zero(hass,selected,value,unit,attrs,status):
    hass.states.async_set(selected[3].entity_id,value,{'device_class':'battery','unit_of_measurement':unit,**attrs,'password':'PRIVATE_IGNORED_ATTRIBUTE'})
    report=snapshot(hass,selected)['devices'][0]['battery']
    assert report['status']==status and report['value'] is None
    assert 'private-value' not in json.dumps(report) and 'PRIVATE_IGNORED_ATTRIBUTE' not in json.dumps(report)


@pytest.mark.asyncio
@pytest.mark.parametrize('age,status',[(MAX_AGE_MS-1,'reported'),(MAX_AGE_MS,'stale'),(MAX_AGE_MS+1,'stale'),(-1,'clock_unknown')])
async def test_age_boundaries_retain_stale_values_but_reject_future_reports(hass,selected,age,status):
    stamp=hass.states.get(selected[3].entity_id).last_reported
    with patch('custom_components.open_thermostat.device_power.dt_util.utcnow',return_value=stamp+timedelta(milliseconds=age)):
        report=snapshot(hass,selected)['devices'][0]['battery']
    assert report['status']==status
    assert report['value']==(None if age<0 else 12.5)


@pytest.mark.asyncio
async def test_selected_identity_rename_is_followed_but_reused_id_is_not_adopted(hass,selected):
    registry=er.async_get(hass);old=selected[2].entity_id
    registry.async_update_entity(old,new_entity_id='sensor.renamed_selected')
    row=snapshot(hass,selected)['devices'][0]
    assert row['selected_entities']==['sensor.renamed_selected'] and row['battery']['value']==12.5
    registry.async_remove('sensor.renamed_selected')
    registry.async_get_or_create('sensor','mqtt','foreign_replacement',suggested_object_id=old.split('.')[1],
        config_entry=selected[0],device_id=selected[1].id)
    result=snapshot(hass,selected)
    assert not result['devices'] and result['unresolved_sources']==[old]


@pytest.mark.asyncio
async def test_duplicate_native_battery_entities_are_ambiguous_until_explicitly_disabled(hass,selected):
    registry=er.async_get(hass)
    extra=registry.async_get_or_create('sensor','mqtt','second_battery',config_entry=selected[0],device_id=selected[1].id,original_device_class='battery')
    hass.states.async_set(extra.entity_id,'99',{'device_class':'battery','unit_of_measurement':'%'})
    report=snapshot(hass,selected)['devices'][0]['battery'];assert report['status']=='ambiguous' and report['value'] is None
    registry.async_update_entity(extra.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    assert snapshot(hass,selected)['devices'][0]['battery']['value']==12.5
    registry.async_update_entity(selected[3].entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    assert snapshot(hass,selected)['devices'][0]['battery']['status']=='disabled'


@pytest.mark.asyncio
async def test_same_device_is_projected_once_for_sensor_and_valve(hass,selected):
    valve=er.async_get(hass).async_get_or_create('climate','mqtt','same_device_valve',config_entry=selected[0],device_id=selected[1].id)
    refs=[selected[-1],EntityReference(valve.entity_id,'mqtt',valve.unique_id)]
    result=read_selected_power(hass,refs)
    assert len(result['devices'])==1 and len(result['devices'][0]['selected_entities'])==2


@pytest.mark.asyncio
async def test_other_devices_and_other_config_entry_owners_cannot_supply_battery(hass,selected):
    registry=er.async_get(hass);registry.async_remove(selected[3].entity_id)
    other=broker(hass,'other')
    foreign_device=dr.async_get(hass).async_get_or_create(config_entry_id=other.entry_id,identifiers={('mqtt','other_device')},name='Selected sensor')
    for device_id,entry in [(foreign_device.id,other),(selected[1].id,other)]:
        item=registry.async_get_or_create('sensor','mqtt','foreign_battery_'+device_id,config_entry=entry,device_id=device_id,original_device_class='battery')
        hass.states.async_set(item.entity_id,'99',{'device_class':'battery','unit_of_measurement':'%'})
    assert snapshot(hass,selected)['devices'][0]['battery']['status']=='missing'


@pytest.mark.asyncio
async def test_disabled_selected_source_and_unpinned_reference_do_not_discover_a_device(hass,selected):
    er.async_get(hass).async_update_entity(selected[2].entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    assert not snapshot(hass,selected)['devices']
    assert not read_selected_power(hass,[EntityReference(selected[2].entity_id)])['devices']
    assert not read_selected_power(hass,[selected[-1]]*10)['devices']


@pytest.mark.asyncio
@pytest.mark.parametrize('value,expected',[('on',True),('off',False),('unknown',None),('unavailable',None),('0',None),('true',None)])
async def test_native_low_battery_flag_is_not_inferred_from_percentage(hass,selected,value,expected):
    hass.states.async_set(selected[4].entity_id,value,{'device_class':'battery'})
    assert snapshot(hass,selected)['devices'][0]['battery_low']['value'] is expected


@pytest.mark.asyncio
async def test_normal_room_model_reuses_saved_devices_without_changing_configuration(hass,configured):
    entry,sub,model=configured;registry=er.async_get(hass);native=broker(hass)
    device=dr.async_get(hass).async_get_or_create(config_entry_id=native.entry_id,identifiers={('mqtt','room_fixture')},name='Room device')
    sensor_id=model['settings']['temperature_entity']
    registry.async_update_entity(sensor_id,device_id=device.id)
    battery=registry.async_get_or_create('sensor',registry.async_get(sensor_id).platform,'room_editor_battery',device_id=device.id,original_device_class='battery')
    hass.states.async_set(battery.entity_id,'66',{'device_class':'battery','unit_of_measurement':'%'})
    before=configuration_snapshot(entry);stamp=hass.states.get(battery.entity_id).last_reported
    for _ in range(3):
        result=room_editor.read_room(hass,entry.entry_id,model['room_id'])
        assert result['device_power']['devices'][0]['battery']['value']==66
    assert configuration_snapshot(entry)==before and result['token']==model['token']
    assert hass.states.get(battery.entity_id).last_reported==stamp
