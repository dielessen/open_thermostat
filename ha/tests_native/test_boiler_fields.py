"""Bounded passive field transport, source age and HA entity lifecycle."""
from copy import deepcopy
import pytest
from custom_components.open_thermostat.boiler_fields import FIELDS, QUALITIES, validate_group
from custom_components.open_thermostat.v1_wire import canonical
from custom_components.open_thermostat.v1_boiler_fields import async_setup_boiler_fields
from test_modern_metrics import system, packet as metric_packet


def values(group=0, sampled=10000, observed=9000):
    fields=[]
    for i in range(group*10,min(group*10+10,69)):
        raw = None if i==24 else (4500 if FIELDS[i][1]=='degC' else 0)
        fields.append([i,raw,observed,QUALITIES[i],FIELDS[i][4]])
    return {"schema":1,"sampled_at_ms":sampled,"profile":"classic_observed","fields":fields}


def packet(c,sequence=1,group=0,**kw):
    p=metric_packet(c,sequence);p.pop('metrics');p.update(group=group,values=values(group,**kw));return p


@pytest.mark.asyncio
async def test_source_deadline_duplicate_and_republication_cannot_refresh_measurement(hass):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True
    before=(c.last_rx,c.lease_until,c.grant_until,deepcopy(r.observations),deepcopy(r.decisions))
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    deadline=c.boiler_fields.records[1][1];assert deadline==129
    assert c.boiler_fields.reading(1,100)['usable']
    assert before==(c.last_rx,c.lease_until,c.grant_until,r.observations,r.decisions)
    now[0]=104
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    assert c.boiler_fields.received==100
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,2,sampled=14000)))
    assert c.boiler_fields.records[1][1]==deadline
    now[0]=130;c.grant_until=140;c.lease_until=145;c.last_rx=130
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,3,sampled=40000)))
    assert not c.boiler_fields.reading(1,130)['usable']
    c.send.assert_not_awaited();await r.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('key,value', [('boot_id','other'),('adapter_id','other'),('epoch',2),
    ('adapter_session_id','old'),('grant_id','old'),('config_revision',2),('config_digest','b'*64)])
async def test_foreign_scope_and_retained_data_never_enter_cache(hass,key,value):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True;p=packet(c)
    await c.receive('fw/telemetry/boiler_fields',canonical(p),retained=True)
    assert not c.boiler_fields.records
    p[key]=value;await c.receive('fw/telemetry/boiler_fields',canonical(p))
    assert not c.boiler_fields.records and c.ready
    await r.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['oversize','extra','bool_id','source','future','quality','secret','display','grant_bool','reverse','mutated'])
async def test_bad_fields_fail_readonly_without_resetting_control(hass,kind):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    p=packet(c,2);f=p['values']['fields'][0]
    if kind=='extra':p['values']['extra']='not_allowed'
    if kind=='bool_id':f[0]=False
    if kind=='source':f[4]=52
    if kind=='future':f[2]=10001
    if kind=='quality':p['values']['fields'][7][3]=0
    if kind=='secret':p['values']['fields'][0][1]='SECRET_DO_NOT_RELAY'
    if kind=='display':p=packet(c,2,group=2);p['values']['fields'][4][1]=-1
    if kind=='grant_bool':p['grant_sequence']=True
    if kind=='reverse':f[2]=8000
    if kind=='mutated':f[1]=4600
    session=c.session
    await c.receive('fw/telemetry/boiler_fields','x'*2049 if kind=='oversize' else canonical(p))
    assert c.boiler_fields.invalid and c.session is session and c.ready
    assert not c.boiler_fields.reading(1,100)['usable']
    assert c.last_rx==100 and c.grant_until==110 and c.lease_until==115
    c.send.assert_not_awaited();await r.async_stop()


@pytest.mark.asyncio
async def test_missing_groups_disconnect_capability_and_quality_suppress_entities(hass):
    e,r,c,now=await system(hass);added=[]
    await async_setup_boiler_fields(hass,e,lambda entities:added.extend(entities))
    assert not added
    c.boiler_fields_supported=True;r._notify();assert len(added)==69
    assert all(not x.available for x in added)
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    assert added[1].native_value==45 and added[1].native_unit_of_measurement=='°C'
    assert not added[7].available and added[7].extra_state_attributes['quality']=='unreliable'
    assert not added[50].available and not added[1].extra_state_attributes['control_qualified']
    assert all(x.state_class is None for x in added)
    now[0]=121;c.grant_until=130;c.lease_until=135;c.last_rx=121
    assert not added[1].available # Missing field-group stream cannot look alive via control heartbeat.
    c.reset_session();assert not c.boiler_fields.records and all(not x.available for x in added)
    await e._async_process_on_unload(hass);assert not r._listeners
    await r.async_stop()


@pytest.mark.asyncio
async def test_all_groups_scaling_zero_and_raw_schema_metadata_match(hass):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True;added=[]
    await async_setup_boiler_fields(hass,e,lambda entities:added.extend(entities))
    for group in range(7):
        p=packet(c,group+1,group=group);validate_group(p['values'],group)
        await c.receive('fw/telemetry/boiler_fields',canonical(p))
    assert len(c.boiler_fields.records)==len(added)==69
    assert added[4].native_value==0 and added[4].available
    assert added[32].native_unit_of_measurement=='µA'
    assert not added[18].available # OEM starts explicitly unqualified.
    assert len({x.unique_id for x in added})==69
    await r.async_stop()


@pytest.mark.asyncio
async def test_disabled_runtime_has_no_field_entities_or_listener(hass):
    e,r,c,now=await system(hass,False);added=[]
    await async_setup_boiler_fields(hass,e,lambda entities:added.extend(entities))
    assert not added and not r._listeners
    await r.async_stop()

@pytest.mark.asyncio
async def test_local_queue_delay_counts_against_original_field_deadline(hass):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True;now[0]=104
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)),received_at=100)
    assert c.boiler_fields.records[1][1]==129
    assert c.boiler_fields.received==100
    now[0]=106
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,2)),received_at=107)
    assert c.boiler_fields.invalid
    await r.async_stop()

@pytest.mark.asyncio
async def test_existing_worker_forwards_arrival_time_without_additional_io(hass):
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
    connection=NativeShadowConnection.__new__(NativeShadowConnection)
    connection.queue=asyncio.Queue(maxsize=64)
    connection.client=SimpleNamespace(receive=AsyncMock())
    message=SimpleNamespace(payload='field-fixture',retain=False)
    connection.queue.put_nowait(('boiler_message',(message,100.0)))
    worker=asyncio.create_task(connection.run())
    try:
        await asyncio.wait_for(connection.queue.join(),2)
        connection.client.receive.assert_awaited_once_with('fw/telemetry/boiler_fields','field-fixture',retained=False,received_at=100.0)
    finally:
        worker.cancel();await asyncio.gather(worker,return_exceptions=True)


@pytest.mark.asyncio
async def test_reversed_local_clock_cannot_revive_cached_or_new_field_deadlines(hass):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    now[0]=99
    assert not c.boiler_fields.reading(1,99)['usable']
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,2,sampled=11000,observed=10000)))
    assert c.session is None and c.error == 'local_monotonic_clock_invalid'
    assert c.boiler_fields.reading(1,99) is None
    c.send.assert_not_awaited();await r.async_stop()

@pytest.mark.asyncio
async def test_same_acquisition_null_retires_only_affected_entity_without_renewing_age(hass):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True;added=[]
    await async_setup_boiler_fields(hass,e,lambda entities:added.extend(entities))
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    deadline=c.boiler_fields.records[4][1]
    p=packet(c,2);p['values']['fields'][4][1]=None
    await c.receive('fw/telemetry/boiler_fields',canonical(p))
    assert not c.boiler_fields.invalid
    assert not added[4].available and added[4].native_value is None
    assert added[1].available and added[1].native_value==45
    assert c.boiler_fields.records[4][1]==deadline
    c.send.assert_not_awaited();await r.async_stop()


@pytest.mark.asyncio
async def test_null_retirement_cannot_reappear_after_other_group_or_same_acquisition_cache(hass):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    p=packet(c,2);p['values']['fields'][4][1]=None
    await c.receive('fw/telemetry/boiler_fields',canonical(p))
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,3,group=1)))
    assert not c.boiler_fields.reading(4,100)['usable']
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,4)))
    assert not c.boiler_fields.reading(4,100)['usable']
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,5,sampled=11000,observed=10000)))
    assert c.boiler_fields.reading(4,100)['usable']
    c.send.assert_not_awaited();await r.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['changed','future','reordered','oversize'])
async def test_invalid_group_cannot_revive_old_fields_via_unrelated_group(hass,fault):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c)))
    p=packet(c,2)
    if fault=='changed':p['values']['fields'][4][1]=30
    if fault=='future':p['values']['fields'][4][2]=10001
    if fault=='reordered':p['values']['fields'][4][2]=8000
    await c.receive('fw/telemetry/boiler_fields','x'*2049 if fault=='oversize' else canonical(p))
    assert c.boiler_fields.invalid
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,3,group=1)))
    assert not c.boiler_fields.reading(4,100)['usable']
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,4)))
    assert not c.boiler_fields.reading(4,100)['usable']
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,5,sampled=11000,observed=10000)))
    assert c.boiler_fields.reading(4,100)['usable'] and c.ready
    assert c.last_rx==100 and c.grant_until==110 and c.lease_until==115
    c.send.assert_not_awaited();await r.async_stop()


@pytest.mark.asyncio
async def test_absent_invalid_expired_and_session_reasons_remain_distinct(hass):
    e,r,c,now=await system(hass);c.boiler_fields_supported=True;added=[]
    await async_setup_boiler_fields(hass,e,lambda entities:added.extend(entities))
    pressure=added[6]
    assert pressure.extra_state_attributes['availability_reason']=='not_received'
    p=packet(c);p['values']['fields'][6]=[6,None,9000,0,24]
    await c.receive('fw/telemetry/boiler_fields',canonical(p))
    attrs=pressure.extra_state_attributes
    assert not pressure.available and pressure.native_value is None
    assert (attrs['measurement_state'],attrs['availability_reason'])==('invalid','invalid_value')
    assert (attrs['source_type'],attrs['source_observed_at_ms'])==(24,9000)
    assert (attrs['field_name'],attrs['raw_divisor'],attrs['source_ttl_ms'])==('pressure',10,30000)
    p=packet(c,2,group=1);p['values']['fields'][6]=[16,None,None,0,0]
    await c.receive('fw/telemetry/boiler_fields',canonical(p))
    enabled=added[16]
    assert not enabled.available and enabled.native_value is None
    assert enabled.extra_state_attributes['measurement_state']=='unknown'
    assert enabled.extra_state_attributes['availability_reason']=='not_observed'
    p=packet(c,3,sampled=11000,observed=10000);p['values']['fields'][6][1]=15
    await c.receive('fw/telemetry/boiler_fields',canonical(p))
    assert pressure.available and pressure.native_value==1.5
    assert pressure.extra_state_attributes['availability_reason']=='ready'
    now[0]=130;c.last_rx=130;c.grant_until=140;c.lease_until=145
    # Fresh publication cannot renew the unchanged original acquisition.
    await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,4,sampled=41000,observed=40000,group=1)))
    assert not pressure.available
    assert pressure.extra_state_attributes['measurement_state']=='stale'
    assert pressure.extra_state_attributes['availability_reason']=='source_expired'
    c.boiler_fields.invalidate()
    assert pressure.extra_state_attributes['availability_reason']=='invalid_packet'
    c.reset_session()
    assert pressure.extra_state_attributes['availability_reason']=='session_unavailable'
    assert not pressure.extra_state_attributes['control_qualified']
    c.send.assert_not_awaited();await r.async_stop()


@pytest.mark.asyncio
async def test_diagnostic_export_preserves_original_invalid_unknown_and_deadlines(hass):
    from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
    e,r,c,now=await system(hass);c.boiler_fields_supported=True
    p=packet(c);p['values']['fields'][6]=[6,None,9000,0,24]
    await c.receive('fw/telemetry/boiler_fields',canonical(p))
    p=packet(c,2,group=1);p['values']['fields'][6]=[16,None,None,0,0]
    await c.receive('fw/telemetry/boiler_fields',canonical(p))
    before=(deepcopy(c.boiler_fields.__dict__),c.last_rx,c.grant_until,c.lease_until)
    data=await async_get_config_entry_diagnostics(hass,e)
    snapshot=data['read_only_boiler_fields']['snapshot'];fields=snapshot['fields']
    assert set(fields)=={f[0] for f in FIELDS} and len(fields)==69
    assert fields['pressure']['measurement_state']=='invalid'
    assert fields['pressure']['source_type']==24 and fields['pressure']['source_observed_at_ms']==9000
    assert fields['pressure']['raw'] is None and fields['pressure']['estimated_source_age_ms']==1000
    assert fields['heating_enabled']['measurement_state']=='unknown'
    assert fields['heating_enabled']['source_observed_at_ms'] is None
    assert fields['heating_enabled']['estimated_source_age_ms'] is None
    assert fields['measured_flow_temperature']['raw']==4500
    assert fields['measured_flow_temperature']['raw_divisor']==100
    assert snapshot['source_snapshot_at_ms']==10000 and snapshot['snapshot_received_age_ms']==0
    assert not snapshot['control_qualified'] and not data['read_only_boiler_fields']['control_qualified']
    assert before==(c.boiler_fields.__dict__,c.last_rx,c.grant_until,c.lease_until)
    assert 'session1' not in str(data) and 'grant1' not in str(data)
    now[0]=104
    later=c.boiler_fields.diagnostic_snapshot(now[0])
    assert later['fields']['pressure']['estimated_source_age_ms']==5000
    assert later['fields']['pressure']['source_observed_at_ms']==9000
    assert later['source_snapshot_at_ms']==10000
    assert before[0]==c.boiler_fields.__dict__
    later['fields']['pressure']['raw']=99
    assert c.boiler_fields.reading(6,104)['raw'] is None
    c.send.assert_not_awaited();await r.async_stop()


@pytest.mark.parametrize('clock',[None,False,float('nan'),float('inf'),-1,99])
def test_diagnostic_export_invalid_local_clock_is_bounded_and_has_no_side_effect(clock):
    from custom_components.open_thermostat.boiler_fields import BoilerFieldCache
    cache=BoilerFieldCache();cache.accept(values(),0,1,100)
    before=deepcopy(cache.__dict__)
    result=cache.diagnostic_snapshot(clock)
    assert not result['local_clock_valid'] and result['snapshot_received_age_ms'] is None
    assert len(result['fields'])==69
    assert all(f['raw'] is None and not f['source_usable']
               and f['availability_reason']=='local_clock_invalid' for f in result['fields'].values())
    assert before==cache.__dict__


def test_diagnostic_export_expiry_and_republication_preserve_original_source_age():
    from custom_components.open_thermostat.boiler_fields import BoilerFieldCache
    cache=BoilerFieldCache();cache.accept(values(),0,1,100)
    cache.accept(values(sampled=15000),0,2,105)
    result=cache.diagnostic_snapshot(110)
    assert result['source_snapshot_at_ms']==15000
    assert result['fields']['pressure']['source_observed_at_ms']==9000
    assert result['fields']['pressure']['estimated_source_age_ms']==11000
    cache.accept(values(group=1,sampled=41000,observed=40000),1,3,131)
    field=cache.diagnostic_snapshot(131)['fields']['pressure']
    assert field['measurement_state']=='stale' and field['availability_reason']=='source_expired'
    assert field['estimated_source_age_ms']==32000 and not field['source_usable']
    cache.invalidate()
    assert cache.diagnostic_snapshot(131)['fields']['pressure']['availability_reason']=='invalid_packet'


@pytest.mark.asyncio
async def test_real_entity_platform_unavailable_state_keeps_evidence_in_diagnostic_download(hass):
    from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
    from custom_components.open_thermostat.v1_boiler_fields import BoilerFieldEntity
    from test_room_sensor_restore import platform
    e,r,c,now=await system(hass);c.boiler_fields_supported=True
    actual=await platform(hass,e)
    flow,pressure,enabled=[BoilerFieldEntity('fixture',c,i) for i in (1,6,16)]
    entities=[flow,pressure,enabled]
    await actual.async_add_entities(entities)
    try:
        assert all(hass.states.get(entity.entity_id).state=='unavailable' for entity in entities)
        p=packet(c);p['values']['fields'][6]=[6,None,9000,0,24]
        await c.receive('fw/telemetry/boiler_fields',canonical(p))
        p=packet(c,2,group=1);p['values']['fields'][6]=[16,None,None,0,0]
        await c.receive('fw/telemetry/boiler_fields',canonical(p))
        for entity in entities:entity.async_write_ha_state()
        await hass.async_block_till_done()
        state=hass.states.get(flow.entity_id)
        assert float(state.state)==45.0
        assert state.attributes['measurement_state']=='valid'
        assert state.attributes['source_observed_at_ms']==9000
        for entity in (pressure,enabled):
            state=hass.states.get(entity.entity_id)
            assert state.state=='unavailable'
            # Native HA deliberately omits extra attributes while unavailable.
            assert 'measurement_state' not in state.attributes
            assert 'availability_reason' not in state.attributes
        data=await async_get_config_entry_diagnostics(hass,e)
        fields=data['read_only_boiler_fields']['snapshot']['fields']
        assert fields['pressure']['measurement_state']=='invalid'
        assert fields['pressure']['source_observed_at_ms']==9000
        assert fields['heating_enabled']['measurement_state']=='unknown'
        assert fields['heating_enabled']['source_observed_at_ms'] is None
        now[0]=130;c.last_rx=130;c.grant_until=140;c.lease_until=145
        await c.receive('fw/telemetry/boiler_fields',canonical(packet(c,3,group=1,sampled=40000,observed=39000)))
        flow.async_write_ha_state();await hass.async_block_till_done()
        assert hass.states.get(flow.entity_id).state=='unavailable'
        data=await async_get_config_entry_diagnostics(hass,e)
        value=data['read_only_boiler_fields']['snapshot']['fields']['measured_flow_temperature']
        assert value['measurement_state']=='stale' and value['availability_reason']=='source_expired'
        assert value['source_observed_at_ms']==9000 and value['estimated_source_age_ms']==31000
        assert not data['read_only_boiler_fields']['control_qualified']
        c.send.assert_not_awaited()
    finally:
        for entity in entities:
            await actual.async_remove_entity(entity.entity_id)
        await r.async_stop()
