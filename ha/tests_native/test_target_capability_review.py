"""Saved-target/device capability checks are read-only, never physical authority."""
from dataclasses import replace
from copy import deepcopy
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from homeassistant.exceptions import HomeAssistantError
from custom_components.open_thermostat.v1_profile_c import target_capability, review_room_targets, ProfileCActuator
from custom_components.open_thermostat.product import configuration_snapshot
from custom_components.open_thermostat.room_editor import read_room
from test_v1_native import room
from test_product_flow import managers, product, new_room, option


def review(hass, binding):
    return review_room_targets(hass, binding, [binding.actuators[0].entity_id])


def state(hass, binding, **attrs):
    entity_id = binding.actuators[0].entity_id
    current = hass.states.get(entity_id)
    hass.states.async_set(entity_id, current.state, {**current.attributes, **attrs})


@pytest.mark.asyncio
async def test_actual_tv02_style_limits_mismatch_is_visible_without_modifying_room(hass):
    binding = room(hass); original = deepcopy(binding.as_dict())
    result = review(hass, binding)
    assert result['status'] == 'review_required'
    assert result['actuators'][0]['issues'] == ['room_limits_exceed_actuator']
    assert result['actuators'][0]['capability'] == dict(unit='°C', minimum=5, maximum=30, step=.5)
    assert not result['authorizes_actuation'] and binding.as_dict() == original


@pytest.mark.asyncio
async def test_week_and_base_rounding_and_outside_targets_are_reported(hass):
    binding = replace(room(hass), base_centi_c=2110, week_program={'monday':[
        dict(start=0,end=3600,target_centi_c=2300),dict(start=3600,end=7200,target_centi_c=2310),
        dict(start=7200,end=10800,target_centi_c=3100)]})
    row = review(hass,binding)['actuators'][0]
    assert row['targets'] == [
        dict(where='base',requested_celsius=21.1,issue='target_will_round',native_result=21,unit='°C'),
        dict(where='monday/1',requested_celsius=23.1,issue='target_will_round',native_result=23,unit='°C'),
        dict(where='monday/2',requested_celsius=31,issue='target_outside_actuator')]


@pytest.mark.asyncio
async def test_compatible_targets_are_not_a_profile_qualification(hass):
    binding = replace(room(hass), maximum_target_centi_c=3000)
    result = review(hass,binding)
    assert result['status']=='compatible' and not result['authorizes_actuation']
    actuator = ProfileCActuator(hass,binding.actuators[0].entity_id)
    with pytest.raises(HomeAssistantError,match='disabled'):await actuator.async_set_room_target(21)


@pytest.mark.asyncio
@pytest.mark.parametrize('attrs',[{'supported_features':0},{'min_temp':True},
    {'max_temp':float('inf')},{'max_temp':float('nan')},{'target_temp_step':0},
    {'target_temp_step':-.5},{'target_temp_step':1e-100},{'min_temp':-1e300,'max_temp':1e300},{'min_temp':30,'max_temp':5},{'unit_of_measurement':'K'}])
async def test_invalid_metadata_remains_unknown_not_compatible(hass,attrs):
    binding=room(hass);state(hass,binding,**attrs)
    result=review(hass,binding)
    assert result['status']=='unknown' and not result['authorizes_actuation']
    assert result['actuators'][0]['issues']==['capability_unavailable']


@pytest.mark.asyncio
@pytest.mark.parametrize('status',['unknown','unavailable','missing'])
async def test_unavailable_valve_is_distinct_from_an_unsupported_target(hass,status):
    binding=room(hass)
    if status=='missing':hass.states.async_remove(binding.actuators[0].entity_id)
    else:hass.states.async_set(binding.actuators[0].entity_id,status)
    assert review(hass,binding)['status']=='unknown'


@pytest.mark.asyncio
async def test_fahrenheit_uses_the_same_adapter_grid_not_celsius_step_assumptions(hass):
    binding=replace(room(hass),minimum_target_centi_c=1000,maximum_target_centi_c=3000,base_centi_c=2100)
    state(hass,binding,unit_of_measurement='°F',min_temp=50,max_temp=86,target_temp_step=1)
    row=review(hass,binding)['actuators'][0]
    assert row['capability']==dict(unit='°F',minimum=50,maximum=86,step=1)
    assert row['targets']==[dict(where='base',requested_celsius=21,issue='target_will_round',native_result=70,unit='°F')]
    assert target_capability(hass,hass.states.get(binding.actuators[0].entity_id)).target(21)==70


@pytest.mark.asyncio
async def test_one_incompatible_or_unknown_device_cannot_be_hidden_by_another(hass):
    first=replace(room(hass),maximum_target_centi_c=3000);second=room(hass,suffix='second')
    state(hass,second,max_temp=25)
    result=review_room_targets(hass,first,[first.actuators[0].entity_id,second.actuators[0].entity_id])
    assert result['status']=='review_required'
    hass.states.async_remove(second.actuators[0].entity_id)
    assert review_room_targets(hass,first,[first.actuators[0].entity_id,second.actuators[0].entity_id])['status']=='unknown'
    assert review_room_targets(hass,first,[])['status']=='unknown'


@pytest.mark.asyncio
async def test_status_screen_and_room_readback_explain_bounds_without_services_or_saves(hass,managers,monkeypatch):
    sub,opts=managers;parent=product(hass);binding=room(hass)
    f=await new_room(sub,parent,binding)
    f=await sub.async_configure(f['flow_id'],{'base_temperature':21,'program_action':'save'})
    await sub.async_configure(f['flow_id'],{})
    zone=next(s for s in parent.subentries.values() if s.subentry_type=='zone')
    before=configuration_snapshot(parent)
    calls=[]
    hass.services.async_register('climate','set_temperature',lambda call:calls.append(call.data))
    model=read_room(hass,parent.entry_id,zone.data['room_id'])
    assert model['actuator_target_review']['status']=='review_required'
    form=await option(opts,parent,'configuration_status')
    text=form['description_placeholders']['actuator_checks']
    assert '5–30 °C' in text and '0.5 °C' in text and 'Review' in text
    assert configuration_snapshot(parent)==before
    assert calls==[]


@pytest.mark.asyncio
async def test_raw_boolean_feature_metadata_is_rejected_before_normalization(hass):
    binding=room(hass);attrs=dict(hass.states.get(binding.actuators[0].entity_id).attributes)
    attrs['supported_features']=True
    with pytest.raises(HomeAssistantError):target_capability(hass,SimpleNamespace(state='heat',attributes=attrs))


@pytest.mark.asyncio
async def test_external_program_is_not_reported_compatible_from_base_target_alone(hass):
    from custom_components.open_thermostat.v1_model import EntityReference
    binding=replace(room(hass),maximum_target_centi_c=3000,schedule=EntityReference('schedule.existing','schedule','existing'))
    result=review(hass,binding)
    assert result['status']=='unknown'
    assert result['external_program_present'] and not result['external_program_checked']
    assert result['actuators'][0]['status']=='compatible'
    assert not result['authorizes_actuation']


@pytest.mark.asyncio
@pytest.mark.parametrize('features', [1, 401])
async def test_real_native_climate_feature_flags_are_valid_capability_metadata(hass, features):
    from homeassistant.components.climate.const import ClimateEntityFeature
    from homeassistant.core import State
    attrs = dict(supported_features=ClimateEntityFeature(features), min_temp=5, max_temp=30,
                 target_temp_step=.5, unit_of_measurement='°C')
    current = State('climate.native_flags', 'heat', attrs)
    assert type(current.attributes['supported_features']) is ClimateEntityFeature
    assert target_capability(hass, current).target(21) == 21

@pytest.mark.asyncio
@pytest.mark.parametrize('key',['min_temp','max_temp','target_temp_step'])
async def test_oversized_integer_metadata_is_unavailable_without_crashing_editor(hass,key):
    binding=room(hass)
    state(hass,binding,**{key:10**500})
    result=review(hass,binding)
    assert result['actuators'][0]['issues']==['capability_unavailable']
    assert not result['authorizes_actuation']
