"""Real HA registries/lifecycle and actual Node producer; isolated MQTT boundary."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.original_temperature import OriginalTemperatureReports, decode, MAX_RUNS
from custom_components.open_thermostat.v1_model import RoomBinding, EntityReference
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from test_device_metadata import devices
from test_v1_native import entry

RUN = '00000000-0000-4000-8000-000000000001'
TOPIC = 'custom-z2m/bridge/openthermostat/original_temperature'


def packet(sequence=1, run=RUN, **changes):
    value = dict(schema=1, producer='openthermostat.z2m.original_temperature',
        producer_run_id=run, sequence=sequence, device_ieee='0x0000000000000001',
        model='WSDCGQ11LM', zigbee_model='lumi.weather', endpoint=1,
        cluster='msTemperatureMeasurement', message_kind='attributeReport', property='temperature',
        raw_value=2137, value_centi_c=2137, zcl_transaction=255,
        received_at_unix_ms=10000000, sampled_at_unix_ms=None,
        acquisition_age_verified=False, control_qualified=False, dropped_reports=0)
    return {**value, **changes}


async def system(hass, devices, *, diagnostic=False):
    _, refs, discoveries = devices
    discoveries[0]['value_template'] = '{{ value_json.device_temperature }}' if diagnostic else '{{ value_json["temperature"] }}'
    entity = er.async_get(hass).async_get(refs[0]['entity_id'])
    dr.async_get(hass).async_update_device(entity.device_id, model_id='WSDCGQ11LM')
    binding = RoomBinding('a1b2c3d4', 'Original report fixture', EntityReference.from_dict(refs[0]),
        (EntityReference.from_dict(refs[1]),), maximum_age_ms=10000)
    now = [100.0]
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding], clock=lambda: now[0])
    await runtime.async_start()
    reports = OriginalTemperatureReports(runtime)
    runtime.original_temperature_reports = reports
    return runtime, binding, reports, now


def receive(reports, value=None, *, retained=False, received_at=100, received_unix_ms=10000000,
            topic=TOPIC, epoch=None):
    return reports.receive(topic, json.dumps(value or packet()), retained=retained,
        received_at=received_at, received_unix_ms=received_unix_ms,
        epoch=reports.epoch if epoch is None else epoch)


@pytest.mark.asyncio
async def test_selected_original_value_reaches_diagnostics_without_promoting_cached_state(hass, devices):
    runtime, binding, reports, now = await system(hass, devices)
    try:
        hass.states.async_set(binding.temperature.entity_id, '99', {'unit_of_measurement': '°C'})
        assert receive(reports)
        result = runtime.measurement_status(binding.room_id)
        assert result['status'] == 'profile_missing' and not result['usable']
        assert result['sample_age_ms'] is None
        assert result['original_report'] == dict(status='received_unqualified', control_qualified=False,
            acquisition_age_verified=False, received_age_ms=0, value_centi_c=2137,
            message_kind='attributeReport')
        assert runtime.observations[binding.room_id].quality != 'qualified'
        assert not runtime._profiles and not runtime._pending
        # Neither identity, raw packet, topic nor producer key reaches public status.
        assert all(text not in json.dumps(result) for text in (RUN, '0x0000', 'custom-z2m'))
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_optional_diagnostic_subscribe_failure_does_not_break_native_startup(hass, devices, monkeypatch):
    runtime, binding, _, now = await system(hass, devices)
    removed = []
    async def subscribe(_hass, topic, callback, **kwargs):
        if topic == TOPIC:
            raise RuntimeError('private broker refusal')
        return lambda: removed.append(topic)
    monkeypatch.setattr(mqtt, 'async_subscribe', subscribe)
    monkeypatch.setattr(mqtt, 'async_subscribe_connection_status', lambda *_: lambda: removed.append('status'))
    monkeypatch.setattr(mqtt, 'async_publish', AsyncMock())
    connection = NativeShadowConnection(runtime)
    try:
        await connection.async_start()
        assert not connection.closed and not connection.worker.done()
        assert runtime.measurement_status(binding.room_id)['original_report']['status'] == 'unavailable'
        assert not runtime.measurement_status(binding.room_id)['usable']
    finally:
        await connection.async_close()
        assert set(removed) == {'fixture/v1/fw/#', 'status'}
        assert runtime.original_temperature_reports is None
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_queue_delay_duplicate_and_new_publication_do_not_renew_original_receive_time(hass, devices):
    runtime, binding, reports, now = await system(hass, devices)
    try:
        now[0] = 104
        assert receive(reports, received_unix_ms=10001000)
        assert reports.status(binding.room_id)['received_age_ms'] == 5000
        now[0] = 106
        assert not receive(reports, received_at=106, received_unix_ms=10006000)
        assert reports.status(binding.room_id)['received_age_ms'] == 7000
        assert receive(reports, packet(2), received_at=106, received_unix_ms=10007000)
        assert reports.status(binding.room_id)['received_age_ms'] == 7000
        now[0] = 110
        assert reports.status(binding.room_id)['status'] == 'stale'
        assert reports.status(binding.room_id)['value_centi_c'] is None
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_retained_foreign_stale_future_and_old_connection_events_are_not_admitted(hass, devices):
    runtime, binding, reports, now = await system(hass, devices)
    try:
        for options in ({'retained': True}, {'topic': 'foreign'+TOPIC},
                {'received_unix_ms': 9999999}, {'received_unix_ms': 10010000},
                {'received_at': 101}, {'epoch': -1}):
            assert not receive(reports, **options)
        assert not receive(reports, packet(device_ieee='0x0000000000000002'))
        assert reports.status(binding.room_id)['status'] == 'waiting'
        assert receive(reports)
        reports.invalidate()
        assert reports.status(binding.room_id)['status'] == 'disconnected'
        assert not receive(reports)  # Watermark survives disconnect.
        assert not receive(reports, packet(2), epoch=0)  # Queued old epoch.
        assert receive(reports, packet(2))
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_producer_rotation_is_bounded_and_retired_run_cannot_return(hass, devices):
    runtime, binding, reports, now = await system(hass, devices)
    try:
        for n in range(1, MAX_RUNS+1):
            assert receive(reports, packet(run=f'00000000-0000-4000-8000-{n:012x}'))
        assert not receive(reports, packet(999, run=RUN))
        assert not receive(reports, packet(run='00000000-0000-4000-8000-999999999999'))
        assert reports.status(binding.room_id)['status'] == 'run_limit'
        assert len(reports.runs[binding.room_id]) == MAX_RUNS
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['model', 'disabled', 'replacement', 'discovery'])
async def test_native_binding_or_discovery_drift_withdraws_diagnostic(hass, devices, change):
    runtime, binding, reports, now = await system(hass, devices)
    try:
        assert receive(reports)
        registry = er.async_get(hass); entity = registry.async_get(binding.temperature.entity_id)
        if change == 'model':
            dr.async_get(hass).async_update_device(entity.device_id, model_id='RTCGQ11LM')
        elif change == 'disabled':
            registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        elif change == 'replacement':
            registry.async_remove(entity.entity_id)
            registry.async_get_or_create('sensor', 'mqtt', entity.unique_id, device_id=entity.device_id)
        else:
            devices[2][0]['value_template'] = '{{ value_json.device_temperature }}'
        assert reports.status(binding.room_id)['status'] == 'binding_changed'
        assert not receive(reports, packet(2))
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_diagnostic_property_has_no_subscription_and_clock_reversal_never_revives_records(hass, devices):
    runtime, binding, reports, now = await system(hass, devices, diagnostic=True)
    try:
        assert not reports.topics and reports.status(binding.room_id) is None
        devices[2][0]['value_template'] = '{{ value_json.temperature }}'
        reports = OriginalTemperatureReports(runtime)
        assert receive(reports)
        now[0] = 99
        assert reports.status(binding.room_id)['status'] == 'clock_invalid'
        now[0] = 101
        assert reports.status(binding.room_id)['status'] == 'clock_invalid'
        assert not receive(reports, packet(2), received_at=101)
    finally:
        await runtime.async_stop()


@pytest.mark.parametrize('changes', [dict(schema=True), dict(sequence=True), dict(sequence=0),
    dict(value_centi_c=1), dict(raw_value=21.37), dict(raw_value=-6500, value_centi_c=-6500),
    dict(control_qualified=True), dict(acquisition_age_verified=True), dict(sampled_at_unix_ms=1),
    dict(message_kind='stateChange'), dict(producer_run_id='A0000000-0000-4000-8000-000000000001'), dict(endpoint=0),
    dict(zcl_transaction=True), dict(zcl_transaction=256), dict(extra='private')])
def test_strict_wire_schema_rejects_forged_quality_and_malformed_fields(changes):
    with pytest.raises(ValueError): decode(json.dumps(packet(**changes)))


@pytest.mark.parametrize('raw', ['null', '[]', '{"schema":1,"schema":1}', 'NaN', ' '*1025])
def test_malformed_duplicate_or_oversized_json_rejected(raw):
    with pytest.raises(ValueError): decode(raw)


@pytest.mark.asyncio
async def test_actual_node_producer_packet_passes_native_ha_binding_and_keeps_acquisition_unknown(hass, devices):
    runtime, binding, reports, now = await system(hass, devices)
    source = Path(__file__).resolve().parents[2] / 'integrations/zigbee2mqtt/original-temperature.cjs'
    code = '''const Base=require(process.argv[1]);
    class Selected extends Base {get bindings(){return [{ieee:'0x0000000000000001',model:'WSDCGQ11LM'}];}}
    let listener; const mqtt={isConnected:()=>true,publish:(_t,p)=>process.stdout.write(p)};
    const eventBus={onDeviceMessage:(_o,f)=>listener=f,removeListeners:()=>{}};
    (async()=>{const p=new Selected(null,mqtt,null,null,eventBus);await p.start();
    listener({device:{ieeeAddr:'0x0000000000000001',definition:{model:'WSDCGQ11LM'},zh:{modelID:'lumi.weather'},interviewed:true},
    endpoint:{ID:1},cluster:'msTemperatureMeasurement',type:'readResponse',data:{measuredValue:1987}});await p.stop();})()
    .catch(()=>{process.exitCode=1;});'''
    process = await asyncio.create_subprocess_exec('node', '-e', code, str(source),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        raw, error = await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode == 0, error
        value = decode(raw)
        assert receive(reports, value, received_unix_ms=value['received_at_unix_ms']+1)
        status = runtime.measurement_status(binding.room_id)
        assert status['original_report']['value_centi_c'] == 1987
        assert status['original_report']['message_kind'] == 'readResponse'
        assert not status['usable'] and status['status'] == 'profile_missing'
    finally:
        if process.returncode is None: process.kill(); await process.wait()
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_existing_mqtt_worker_subscription_lifecycle_without_control_or_extra_worker(hass, devices, monkeypatch):
    runtime, binding, _, now = await system(hass, devices)
    subscriptions = {}; removed = []; statuses = []
    async def subscribe(_hass, topic, callback, **kwargs):
        subscriptions[topic] = callback
        return lambda: removed.append(topic)
    monkeypatch.setattr(mqtt, 'async_subscribe', subscribe)
    monkeypatch.setattr(mqtt, 'async_subscribe_connection_status', lambda _h, cb: statuses.append(cb) or (lambda: removed.append('status')))
    monkeypatch.setattr(mqtt, 'async_publish', AsyncMock())
    connection = NativeShadowConnection(runtime)
    try:
        await connection.async_start()
        client = connection.client
        client.receive = AsyncMock(wraps=client.receive)
        assert set(subscriptions) == {'fixture/v1/fw/#', TOPIC}
        original = subscriptions[TOPIC]
        from custom_components.open_thermostat import v1_mqtt
        monkeypatch.setattr(v1_mqtt.dt_util, 'utcnow', lambda: SimpleNamespace(timestamp=lambda: 10000))
        msg = SimpleNamespace(topic=TOPIC, payload=json.dumps(packet()), retain=False)
        original(msg)
        for _ in range(100): original(msg)
        assert connection.queue.qsize() == 1
        await connection.queue.join()
        client.receive.assert_not_awaited()
        assert runtime.measurement_status(binding.room_id)['original_report']['status'] == 'received_unqualified'
        # Malformed/large diagnostic traffic is rejected before queuing.
        original(SimpleNamespace(topic=TOPIC, payload=b' '*1025, retain=False))
        original(SimpleNamespace(topic=TOPIC, payload=json.dumps(packet(2)), retain=True))
        assert connection.queue.empty()
        # Reserve half the existing queue for the native control path.
        for _ in range(32): connection.queue.put_nowait(('noop', None))
        original(msg)
        assert connection.queue.qsize() == 32 and not connection.original_pending
        await connection.queue.join()
        # Even an unexpected diagnostic SDK/registry exception has no control
        # session/lease/error effect; no packet enters the ShadowClient.
        before = client.last_rx, client.grant_until, client.lease_until, client.error
        with monkeypatch.context() as patch:
            patch.setattr(connection.original_reports, 'receive', Mock(side_effect=RuntimeError('private diagnostic error')))
            original(msg); await connection.queue.join()
        assert (client.last_rx, client.grant_until, client.lease_until, client.error) == before
        client.receive.assert_not_awaited()
        assert connection.original_reports.status(binding.room_id)['status'] == 'unavailable'
        old_epoch = connection.original_reports.epoch
        original(SimpleNamespace(topic=TOPIC, payload=json.dumps(packet(2)), retain=False))
        statuses[0](False)  # Invalidates immediately before queued packet runs.
        assert connection.original_reports.epoch != old_epoch
        await connection.queue.join()
        assert connection.original_reports.status(binding.room_id)['status'] == 'disconnected'
    finally:
        await connection.async_close()
        assert runtime.original_temperature_reports is None
        assert set(removed) == {'fixture/v1/fw/#', TOPIC, 'status'}
        assert connection.queue.empty() and connection.worker.done()
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('maximum_age_ms', [1000, 20000])
@pytest.mark.parametrize('first_check', ['status', 'receive'])
async def test_changed_room_freshness_policy_retires_original_temperature_owner(hass, devices, maximum_age_ms, first_check):
    runtime, room, reports, now = await system(hass, devices)
    try:
        assert receive(reports)
        runtime.rooms[room.room_id] = replace(room, maximum_age_ms=maximum_age_ms)
        if first_check == 'receive':
            assert not receive(reports, packet(2))
        status = reports.status(room.room_id)
        assert status['status'] == 'binding_changed'
        assert status['value_centi_c'] is None
        assert not receive(reports, packet(2))
        runtime.rooms[room.room_id] = room
        assert not receive(reports, packet(3))
        assert reports.status(room.room_id)['status'] == 'binding_changed'
        runtime.rooms[room.room_id] = replace(room, maximum_age_ms=maximum_age_ms)
        rebuilt = OriginalTemperatureReports(runtime)
        assert rebuilt.status(room.room_id)['status'] == 'waiting'
        assert receive(rebuilt)
        now[0] += maximum_age_ms / 1000
        assert rebuilt.status(room.room_id)['status'] == 'stale'
        assert rebuilt.status(room.room_id)['value_centi_c'] is None
        assert not rebuilt.status(room.room_id)['control_qualified']
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_room_display_rename_preserves_original_temperature_lifetime(hass, devices):
    runtime, room, reports, now = await system(hass, devices)
    try:
        assert receive(reports)
        runtime.rooms[room.room_id] = replace(room, name='Changed display name')
        now[0] += 1
        assert reports.status(room.room_id)['status'] == 'received_unqualified'
        assert reports.status(room.room_id)['received_age_ms'] == 1000
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_clock', [None, '101', object(), float('nan'), float('inf')])
async def test_invalid_clock_retires_original_temperature_without_diagnostic_exception(hass, devices, bad_clock):
    runtime, room, reports, now = await system(hass, devices)
    try:
        assert receive(reports)
        now[0] = bad_clock
        assert reports.status(room.room_id)['status'] == 'clock_invalid'
        assert reports.status(room.room_id)['value_centi_c'] is None
        assert not receive(reports, packet(2))
        now[0] = 101
        assert reports.status(room.room_id)['status'] == 'clock_invalid'
        assert not receive(reports, packet(3), received_at=101)
    finally:
        now[0] = 101
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_overflowing_arrival_delta_rejects_temperature_packet_without_exception(hass, devices):
    runtime, room, reports, now = await system(hass, devices)
    try:
        now[0] = 1e308
        assert not receive(reports, received_at=-1e308)
        assert reports.status(room.room_id)['status'] == 'waiting'
        assert not runtime._profiles
    finally:
        now[0] = 101
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_clock', [None, '100', True, float('nan'), float('inf')])
async def test_invalid_initial_temperature_clock_cannot_be_repaired_by_later_time(hass, devices, bad_clock):
    runtime, room, _, now = await system(hass, devices)
    try:
        now[0] = bad_clock
        reports = OriginalTemperatureReports(runtime)
        now[0] = 101
        assert reports.status(room.room_id)['status'] == 'clock_invalid'
        assert not receive(reports, received_at=101)
        assert reports.status(room.room_id)['value_centi_c'] is None
    finally:
        now[0] = 101
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['model', 'entity_disabled', 'device_disabled', 'replacement'])
async def test_native_events_retire_temperature_source_before_registry_is_restored(hass, devices, change):
    runtime, binding, reports, now = await system(hass, devices)
    registry = er.async_get(hass)
    entity = registry.async_get(binding.temperature.entity_id)
    device_registry = dr.async_get(hass)
    try:
        assert receive(reports)
        if change == 'model': device_registry.async_update_device(entity.device_id, model_id='RTCGQ11LM')
        elif change == 'entity_disabled': registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
        elif change == 'device_disabled': device_registry.async_update_device(entity.device_id, disabled_by=dr.DeviceEntryDisabler.USER)
        else:
            registry.async_remove(entity.entity_id)
            registry.async_get_or_create('sensor', 'mqtt', entity.unique_id, device_id=entity.device_id)
        await hass.async_block_till_done()
        if change == 'model': device_registry.async_update_device(entity.device_id, model_id='WSDCGQ11LM')
        elif change == 'entity_disabled': registry.async_update_entity(entity.entity_id, disabled_by=None)
        elif change == 'device_disabled': device_registry.async_update_device(entity.device_id, disabled_by=None)
        await hass.async_block_till_done()
        status = reports.status(binding.room_id)
        assert status['status'] == 'binding_changed' and status['value_centi_c'] is None
        assert not receive(reports, packet(2))
        assert not reports.records
        assert not status['control_qualified'] and not status['acquisition_age_verified']
        assert runtime.measurement_status(binding.room_id)['status'] == 'profile_missing'
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_room_display_name_update_keeps_original_temperature_evidence(hass, devices):
    runtime, binding, reports, now = await system(hass, devices)
    entity = er.async_get(hass).async_get(binding.temperature.entity_id)
    try:
        assert receive(reports)
        er.async_get(hass).async_update_entity(entity.entity_id, name='New display name')
        dr.async_get(hass).async_update_device(entity.device_id, name_by_user='New device label')
        await hass.async_block_till_done()
        assert reports.status(binding.room_id)['status'] == 'received_unqualified'
        assert receive(reports, packet(2))
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_optional_observer_error_does_not_skip_other_registry_guard(hass, devices, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    runtime, binding, reports, now = await system(hass, devices)
    second = SimpleNamespace(recheck=Mock(return_value=True), invalidate=Mock())
    runtime.original_tv02_reports = second
    try:
        monkeypatch.setattr(reports, 'recheck', Mock(side_effect=RuntimeError('private observer error')))
        entity = er.async_get(hass).async_get(binding.temperature.entity_id)
        dr.async_get(hass).async_update_device(entity.device_id, name_by_user='Harmless label')
        await hass.async_block_till_done()
        second.recheck.assert_called()
        assert reports.status(binding.room_id)['status'] == 'unavailable'
        assert runtime.measurement_status(binding.room_id)['status'] == 'profile_missing'
        assert not runtime._profiles and not runtime._pending
    finally:
        runtime.original_tv02_reports = None
        await runtime.async_stop()
