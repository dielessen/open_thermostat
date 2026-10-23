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
    assert c.boiler_fields.invalid and not c.boiler_fields.reading(1,99)['usable']
    c.send.assert_not_awaited();await r.async_stop()
