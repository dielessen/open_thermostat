"""Actual producer interoperability and adversarial original TV02 ingestion."""
import json
from pathlib import Path
import subprocess

import pytest

from custom_components.open_thermostat.original_tv02 import decode, Tv02Reception, MAX_RUNS

ROOT = Path(__file__).resolve().parents[2]
RUN = '00000000-0000-4000-8000-000000000001'


def packet(**changes):
    return dict(schema=1, producer='openthermostat.z2m.original_tv02', producer_run_id=RUN,
        sequence=1, device_ieee='0x0000000000000001', model='TV02-Zigbee', zigbee_model='TS0601',
        manufacturer='_TZE200_hue3yfsn', endpoint=1, cluster='manuSpecificTuya',
        message_kind='commandDataReport', tuya_sequence=65535, zcl_transaction=255,
        received_at_unix_ms=10000000, sampled_at_unix_ms=None, command_correlated=False,
        valve_ready=False, control_qualified=False, fields=[dict(dp=16, datatype=2,
        raw_hex='000000d2', property='target_centi_c', value=2100)], dropped_reports=0) | changes


def receiver():
    now = [100.0]
    return Tv02Reception(ieee='0x0000000000000001', manufacturer='_TZE200_hue3yfsn',
        endpoint=1, maximum_age_ms=10000, clock=lambda: now[0]), now


def receive(owner, value=None, **kwargs):
    args = dict(retained=False, received_at=100, received_unix_ms=10000000, epoch=owner.epoch)
    args.update(kwargs)
    return owner.receive(json.dumps(packet() if value is None else value), **args)


def producer_packet(ieee='0x0000000000000001'):
    script = r'''
const Producer = require('./integrations/zigbee2mqtt/original-tv02.cjs');
const device = {ieeeAddr:process.argv[1], interviewed:true,
 definition:{model:'TV02-Zigbee'}, zh:{modelID:'TS0601',manufacturerName:'_TZE200_hue3yfsn'}};
const mqtt = {isConnected:()=>true,publish:(_topic,raw)=>{console.log(raw);return Promise.resolve();}};
const bus = {onDeviceMessage(){},removeListeners(){}};
class Bound extends Producer {get bindings(){return [{ieee:device.ieeeAddr,model:'TV02-Zigbee',manufacturer:device.zh.manufacturerName,endpoint:1}];}}
(async()=>{const p=new Bound(null,mqtt,null,null,bus);await p.start();
p.onMessage({device,endpoint:{ID:1},cluster:'manuSpecificTuya',type:'commandDataReport',
 meta:{zclTransactionSequenceNumber:255},data:{seq:65535,dpValues:[
 {dp:16,datatype:2,data:Buffer.from('000000d2','hex')},
 {dp:24,datatype:2,data:Buffer.from('000000dc','hex')},
 {dp:2,datatype:4,data:Buffer.from('01','hex')},
 {dp:107,datatype:1,data:Buffer.from('00','hex')},
 {dp:10,datatype:1,data:Buffer.from('01','hex')}]}});await p.stop();})();
'''
    raw = subprocess.check_output(['node', '-e', script, ieee], cwd=ROOT, text=True).strip()
    return raw


def test_actual_node_producer_not_a_handwritten_wire_fixture():
    result = decode(producer_packet())
    assert {f['property']: f['value'] for f in result['fields']} == dict(
        target_centi_c=2100, local_temperature_centi_c=2200, preset='manual',
        heating_stop=False, frost_protection=True)
    assert not any(result[k] for k in ('control_qualified','command_correlated','valve_ready'))


@pytest.mark.parametrize('key,value', [
    ('schema',True),('sequence',True),('endpoint',True),('sequence',0),('sequence',2**53),
    ('model','TS0601'),('manufacturer','other'),('manufacturer',[]),('message_kind',[]),
    ('message_kind','dataRequest'),('producer_run_id','cached'),('device_ieee','0x1'),
    ('sampled_at_unix_ms',0),('command_correlated',True),('valve_ready',True),
    ('control_qualified',1),('zcl_transaction',256),('tuya_sequence',65536),
    ('fields',[]),('fields',[{}]),('received_at_unix_ms',-1),('unknown',1)])
def test_reject_forged_or_malformed_envelope(key,value):
    with pytest.raises(ValueError):
        decode(json.dumps(packet(**{key:value})))


@pytest.mark.parametrize('change', [dict(value=2101), dict(value=True),dict(raw_hex='000000d3'),
    dict(raw_hex='000000D2'),dict(raw_hex='00'),dict(datatype=True),dict(dp=True),
    dict(dp=200),dict(property='local_temperature_centi_c'),dict(extra=1)])
def test_reject_inconsistent_original_bytes(change):
    report=packet(); report['fields'][0].update(change)
    with pytest.raises(ValueError): decode(json.dumps(report))


def test_duplicates_oversize_nonfinite_and_wrong_type():
    report=packet(); report['fields'] *= 2
    bad=[json.dumps(report), json.dumps(packet()).replace('"schema": 1','"schema": 1, "schema": 1'),
         json.dumps(packet()).replace('2100','NaN'), ' '*2049, '{}', b'\xff', None]
    for raw in bad:
        with pytest.raises((ValueError,UnicodeError)): decode(raw)


def test_no_merged_fields_no_control_promotion_and_private_identity():
    owner,now=receiver()
    assert receive(owner)
    assert owner.status()['fields']=={'target_centi_c':2100}
    report=packet(sequence=2,fields=[dict(dp=2,datatype=4,raw_hex='01',property='preset',value='manual')])
    assert receive(owner,report)
    status=owner.status()
    assert status['fields']=={'preset':'manual'}
    assert not status['command_correlated'] and not status['valve_ready'] and not status['control_qualified']
    assert RUN not in json.dumps(status) and '0x0000' not in json.dumps(status)
    now[0]=110
    assert owner.status()['status']=='stale' and owner.status()['fields']=={}


def test_expired_reception_retains_only_bounded_receive_metadata_not_values_or_identity():
    owner, now = receiver()
    assert owner.status()['last_reception'] is None
    assert receive(owner)
    now[0] = 110
    status = owner.status()
    assert status['last_reception'] == dict(scope='reception_only',
        message_kind='commandDataReport', received_age_ms=10000,
        properties=['target_centi_c'])
    assert status['status'] == 'stale' and status['fields'] == {}
    assert status['received_age_ms'] is None
    metadata = json.dumps(status['last_reception'])
    assert '2100' not in metadata and '0x0000' not in metadata and RUN not in metadata
    assert not any(status[key] for key in ('command_correlated', 'valve_ready', 'control_qualified'))
    owner.invalidate()
    assert owner.status()['last_reception'] is None


def test_receive_metadata_does_not_refresh_from_replay_or_reveal_an_unbounded_age():
    owner, now = receiver()
    assert receive(owner, packet(message_kind='commandDataResponse'))
    now[0] = 105
    assert not receive(owner, received_at=105)
    status = owner.status()
    assert status['last_reception']['received_age_ms'] == 5000
    assert status['last_reception']['message_kind'] == 'commandDataResponse'
    assert status['command_correlated'] is False
    now[0] = 1e20
    status = owner.status()
    assert status['status'] == 'stale' and status['fields'] == {}
    assert status['last_reception']['received_age_ms'] is None
    now[0] = 104
    status = owner.status()
    assert status['status'] == 'clock_invalid' and status['last_reception'] is None


def test_duplicate_does_not_refresh_deadline_and_reconnect_rejects_pending_and_replay():
    owner,now=receiver(); assert receive(owner)
    now[0]=105
    assert not receive(owner,received_at=105)
    assert owner.status()['received_age_ms']==5000
    old_epoch=owner.epoch
    owner.invalidate()
    assert owner.status()['fields']=={}
    assert not receive(owner,packet(sequence=2),epoch=old_epoch)
    assert not receive(owner)
    assert receive(owner,packet(sequence=2))


@pytest.mark.parametrize('kwargs', [dict(retained=True),dict(epoch=True),dict(received_at=float('nan')),
    dict(received_at=101),dict(received_unix_ms=9999999),dict(received_unix_ms=10010000),
    dict(received_at=89.999)])
def test_reject_transport_age_and_future_packets(kwargs):
    owner,_=receiver()
    assert not receive(owner,**kwargs)
    assert owner.status()['fields']=={}


@pytest.mark.parametrize('changes',[dict(device_ieee='0x0000000000000002'),dict(endpoint=2),
    dict(manufacturer='_TZE200_lllliz3p')])
def test_reject_other_exact_binding(changes):
    owner,_=receiver(); assert not receive(owner,packet(**changes))


def test_retired_runs_never_return_bounded_run_memory_and_wrapping_tuya_seq():
    owner,_=receiver()
    for i in range(1,MAX_RUNS+1):
        run=f'00000000-0000-4000-8000-{i:012x}'
        assert receive(owner,packet(producer_run_id=run,tuya_sequence=i%2))
    assert not receive(owner,packet(sequence=999))
    assert not receive(owner,packet(producer_run_id='00000000-0000-4000-8000-000000000099'))
    assert len(owner.runs)==MAX_RUNS and owner.status()['status']=='run_limit'
    assert owner.status()['fields']=={}


def test_clock_rollback_latches_even_after_clock_recovers():
    owner,now=receiver(); assert receive(owner)
    now[0]=99
    assert owner.status()['status']=='clock_invalid'
    now[0]=200
    assert not receive(owner,packet(sequence=2),received_at=200)
    assert owner.status()['fields']=={}


@pytest.mark.parametrize('dp,datatype,raw,prop,value', [
    (16,2,'00000032','target_centi_c',500), (16,2,'0000012c','target_centi_c',3000),
    (24,2,'00000000','local_temperature_centi_c',0),
    (24,2,'00000258','local_temperature_centi_c',6000),
    (2,4,'00','preset','auto'), (2,4,'02','preset','holiday'),
    (2,4,'03','preset','holiday'), (107,1,'01','heating_stop',True),
    (10,1,'00','frost_protection',False)])
def test_supported_datapoint_boundaries(dp,datatype,raw,prop,value):
    report=packet(fields=[dict(dp=dp,datatype=datatype,raw_hex=raw,property=prop,value=value)])
    assert decode(json.dumps(report))==report


@pytest.mark.parametrize('dp,datatype,raw,prop,value', [
    (16,2,'00000031','target_centi_c',490), (16,2,'00000131','target_centi_c',3050),
    (24,2,'00000259','local_temperature_centi_c',6010),
    (24,2,'ffffffff','local_temperature_centi_c',-10),
    (2,4,'04','preset','manual'), (107,1,'02','heating_stop',True),
    (10,2,'00000001','frost_protection',True)])
def test_unsupported_datapoint_boundaries(dp,datatype,raw,prop,value):
    with pytest.raises(ValueError):
        decode(json.dumps(packet(fields=[dict(dp=dp,datatype=datatype,raw_hex=raw,property=prop,value=value)])))


def test_extreme_finite_clock_does_not_overflow_or_revive_evidence():
    owner,now=receiver(); now[0]=1e308
    assert not receive(owner,received_at=-1e308)
    owner,now=receiver(); assert receive(owner)
    now[0]=1e308
    assert owner.status()['status']=='stale'
    assert owner.status()['fields']=={}


def test_queue_delay_counts_against_original_arrival_not_worker_time():
    owner,now=receiver(); now[0]=109.999
    assert receive(owner)
    assert owner.status()['received_age_ms']==9999
    now[0]=110
    assert owner.status()['status']=='stale'
    owner,now=receiver(); now[0]=110
    assert not receive(owner)


def test_oversized_integer_clock_is_latched_without_crashing_status():
    owner, now = receiver()
    assert receive(owner)
    now[0] = 10**1000
    assert owner.status()['status'] == 'clock_invalid'
    now[0] = 101
    assert not receive(owner, packet(sequence=2), received_at=101)
    assert owner.status()['status'] == 'clock_invalid'


def test_finite_clock_scaling_overflow_withdraws_fields():
    owner, now = receiver()
    assert receive(owner)
    now[0] = 1e308
    result = owner.status()
    assert result['status'] == 'stale'
    assert result['fields'] == {}
    assert result['last_reception']['received_age_ms'] is None
