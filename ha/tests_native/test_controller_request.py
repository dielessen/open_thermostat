"""Command provenance, original completion age and existing shared MQTT reception."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json
import pytest
from custom_components.open_thermostat.controller_request import ControllerRequestSensor,parse,supported,PROFILE

def packet(value=50,sequence=2,at=10000,emitted=9000,boot='000000000000002a'):
    return {'protocolProfile':'classic','selectedFlowTemperature':0,'controller_request':{
        'schema':1,'profile_id':PROFILE,'source':'controller_uart_transmit','boot_id':boot,
        'observed_at_ms':at,'known':value is not None,'boiler_readback':False,
        'value_c':value,'emitted_at_ms':emitted if value is not None else None,
        'sequence':sequence if value is not None else 0}}

def test_completed_request_remains_separate_and_duplicate_status_cannot_renew_age():
    clock=[100.];sensor=ControllerRequestSensor('fixture',lambda:clock[0]);p=packet();original=deepcopy(p)
    sensor.update_payload(p,True);assert sensor.native_value==50 and p==original
    assert sensor.extra_state_attributes['boiler_readback']is False
    assert sensor.extra_state_attributes['last_command_age_ms']==1000
    clock[0]+=5;sensor.update_payload(p,True)
    assert sensor.extra_state_attributes['last_command_age_ms']==6000
    clock[0]+=85;assert not sensor.available and sensor.native_value is None
    p=packet(at=100000);sensor.update_payload(p,True)
    assert sensor.native_value==50 and sensor.extra_state_attributes['last_command_age_ms']==91000
    sensor.update_payload(packet(0,3,100001,100000),True);assert sensor.native_value==0
    sensor.update_payload(packet(None,at=100,boot='000000000000002b'),True)
    assert sensor.native_value is None and sensor.extra_state_attributes['sequence']==0

@pytest.mark.parametrize('key,bad',[
    ('schema',True),('schema',2),('profile_id','other'),('source','boiler_report'),
    ('boiler_readback',True),('known',1),('value_c',True),('value_c',51),('value_c','50'),
    ('sequence',True),('sequence',0),('observed_at_ms',False),('emitted_at_ms',10001),
    ('boot_id','old'),('extra','private')])
def test_bad_command_source_and_numbers_do_not_supply_a_temperature(key,bad):
    p=packet();p['controller_request'][key]=bad
    with pytest.raises(ValueError):parse(p)
    sensor=ControllerRequestSensor('fixture');sensor.update_payload(p,True)
    assert sensor.native_value is None and not sensor.available

@pytest.mark.parametrize('fault',['retained','reordered','changed_sequence','clock_reversed','offline','unsupported'])
def test_unavailable_or_cached_status_cannot_certify_a_command(fault):
    clock=[10.];sensor=ControllerRequestSensor('fixture',lambda:clock[0]);sensor.update_payload(packet(),True)
    p=packet(at=11000);online=True;retained=False
    if fault=='retained':retained=True
    if fault=='reordered':p=packet(at=9999)
    if fault=='changed_sequence':p=packet(value=0,at=11000)
    if fault=='clock_reversed':clock[0]=9.
    if fault=='offline':online=False
    if fault=='unsupported':p['protocolProfile']='plus'
    sensor.update_payload(p,online,retained=retained)
    assert sensor.native_value is None and not sensor.available

@pytest.mark.asyncio
async def test_sensor_uses_existing_product_subscription_without_publishing_or_altering_boiler_report(hass,monkeypatch):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat.product_telemetry import async_setup_sensors
    from custom_components.open_thermostat.heating import HeatingTracker
    from test_product_flow import product
    p=product(hass);tracker=HeatingTracker(hass,p);hass.data['open_thermostat'][p.entry_id]={'heating_tracker':tracker}
    callbacks={};added=[]
    async def subscribe(_h,topic,callback,*args,**kwargs):callbacks[topic]=callback;return lambda:None
    monkeypatch.setattr(mqtt,'async_wait_for_mqtt_client',AsyncMock())
    monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    publish=AsyncMock();monkeypatch.setattr(mqtt,'async_publish',publish)
    await async_setup_sensors(hass,p,lambda values,**kw:added.extend(values))
    callbacks['fixture/status'](SimpleNamespace(payload='on'))
    callbacks['fixture/ems_status'](SimpleNamespace(payload=json.dumps({'protocolProfile':'plus','selectedFlowTemperature':45}),retain=False))
    assert not any(isinstance(e,ControllerRequestSensor)for e in added)
    for value,seq,at in [(None,0,100),(50,1,101),(0,2,102)]:
        payload=packet(value,seq,at,at);before=deepcopy(payload)
        callbacks['fixture/ems_status'](SimpleNamespace(payload=json.dumps(payload),retain=False))
        command=next(e for e in added if isinstance(e,ControllerRequestSensor))
        assert command.native_value==value and payload==before and payload['selectedFlowTemperature']==0
    assert len([e for e in added if isinstance(e,ControllerRequestSensor)])==1
    assert set(callbacks)=={'fixture/status','fixture/ems_status','fixture/ems_metrics','fixture/device_status'}
    publish.assert_not_called();await tracker.async_stop()


def test_invalid_packet_does_not_forget_sequence_or_revive_a_retired_boot():
    sensor=ControllerRequestSensor('fixture');sensor.update_payload(packet(),True)
    bad=packet();bad['controller_request']['value_c']='50';sensor.update_payload(bad,True)
    sensor.update_payload(packet(sequence=1,at=9999,emitted=9000),True)
    assert not sensor.available
    sensor.update_payload(packet(sequence=3,at=11000,emitted=10000),True)
    assert sensor.native_value==50
    sensor.update_payload(packet(None,at=100,boot='000000000000002b'),True)
    sensor.update_payload(packet(at=12000),True)
    assert not sensor.available and sensor.extra_state_attributes['availability_reason']=='retired_command_boot'


@pytest.mark.asyncio
async def test_real_entity_platform_publishes_same_value_command_sequence_and_original_age(hass):
    from test_product_flow import product
    from test_room_sensor_restore import platform
    entry=product(hass);actual=await platform(hass,entry);clock=[100.]
    sensor=ControllerRequestSensor('fixture',lambda:clock[0])
    await actual.async_add_entities([sensor])
    try:
        sensor.update_payload(packet(),True);await hass.async_block_till_done()
        first=hass.states.get(sensor.entity_id)
        assert first.state=='50' and first.attributes['sequence']==2
        clock[0]+=60;sensor.update_payload(packet(sequence=3,at=70000,emitted=69000),True)
        await hass.async_block_till_done();second=hass.states.get(sensor.entity_id)
        assert second.state=='50' and second.attributes['sequence']==3
        assert second.attributes['emitted_at_ms']==69000
        assert second.attributes['last_command_age_ms']==1000
        clock[0]+=15;sensor.update_payload(packet(sequence=3,at=85000,emitted=69000),True)
        await hass.async_block_till_done()
        assert hass.states.get(sensor.entity_id).attributes['last_command_age_ms']==16000
    finally:
        await actual.async_reset()


@pytest.mark.asyncio
async def test_native_product_uses_actual_native_request_and_availability_topics_without_legacy_boiler_entities(hass,monkeypatch):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat.product_telemetry import async_setup_sensors
    from custom_components.open_thermostat.heating import HeatingTracker
    from custom_components.open_thermostat import device_diagnostics
    from test_product_flow import product
    entry=product(hass);tracker=HeatingTracker(hass,entry)
    hass.data['open_thermostat'][entry.entry_id]={'heating_tracker':tracker}
    callbacks={};added=[]
    async def subscribe(_h,topic,callback,*args,**kwargs):callbacks[topic]=callback;return lambda:None
    monkeypatch.setattr(mqtt,'async_wait_for_mqtt_client',AsyncMock())
    monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    monkeypatch.setattr(device_diagnostics,'async_setup_device_diagnostics',AsyncMock())
    publish=AsyncMock();monkeypatch.setattr(mqtt,'async_publish',publish)
    await async_setup_sensors(hass,entry,lambda entities,**kw:added.extend(entities),native_metrics=True)
    assert set(callbacks)=={'fixture/v1/fw/availability','fixture/v1/fw/telemetry/controller_request'}
    callbacks['fixture/v1/fw/availability'](SimpleNamespace(payload='online'))
    receive=callbacks['fixture/v1/fw/telemetry/controller_request']
    for value,seq,at in [(None,0,100),(50,1,101),(50,2,60101),(0,3,600101)]:
        receive(SimpleNamespace(payload=json.dumps(packet(value,seq,at,at)),retain=False))
        sensor=next(e for e in added if isinstance(e,ControllerRequestSensor))
        assert sensor.native_value==value and sensor.extra_state_attributes['sequence']==seq
    from custom_components.open_thermostat.sensor import HubMetric
    assert not any(isinstance(e,HubMetric)for e in added)
    assert len([e for e in added if isinstance(e,ControllerRequestSensor)])==1
    callbacks['fixture/v1/fw/availability'](SimpleNamespace(payload='offline'))
    assert not sensor.available;publish.assert_not_called();await tracker.async_stop()


@pytest.mark.asyncio
async def test_native_live_packet_proves_liveness_after_ha_only_restart_but_retained_does_not(hass,monkeypatch):
    # Firmware publishes non-retained "online" on connect only; HA may restart later.
    from homeassistant.components import mqtt
    from custom_components.open_thermostat.product_telemetry import async_setup_sensors
    from custom_components.open_thermostat.heating import HeatingTracker
    from custom_components.open_thermostat import device_diagnostics
    from test_product_flow import product
    entry=product(hass);tracker=HeatingTracker(hass,entry)
    hass.data['open_thermostat'][entry.entry_id]={'heating_tracker':tracker}
    callbacks={};added=[]
    async def subscribe(_h,topic,callback,*args,**kwargs):callbacks[topic]=callback;return lambda:None
    monkeypatch.setattr(mqtt,'async_wait_for_mqtt_client',AsyncMock())
    monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    monkeypatch.setattr(device_diagnostics,'async_setup_device_diagnostics',AsyncMock())
    await async_setup_sensors(hass,entry,lambda entities,**kw:added.extend(entities),native_metrics=True)
    receive=callbacks['fixture/v1/fw/telemetry/controller_request']
    receive(SimpleNamespace(payload=json.dumps(packet(50,1,100,100)),retain=True))
    sensor=next(e for e in added if isinstance(e,ControllerRequestSensor))
    assert not sensor.available
    receive(SimpleNamespace(payload=json.dumps(packet(50,2,200,200)),retain=False))
    assert sensor.available and sensor.native_value==50
    callbacks['fixture/v1/fw/availability'](SimpleNamespace(payload='offline'))
    assert not sensor.available;await tracker.async_stop()
