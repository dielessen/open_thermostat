"""Actual native HA registries and existing MQTT worker; no physical actuation."""
from dataclasses import replace
from datetime import datetime, UTC
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.original_tv02 import OriginalTv02Reports, Tv02DiagnosticSource
from custom_components.open_thermostat.v1_model import RoomBinding, EntityReference
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from test_device_metadata import devices
from test_original_tv02 import packet
from test_v1_native import entry

TOPIC = 'custom-z2m/bridge/openthermostat/original_tv02'


async def system(hass, devices):
    _, refs, discoveries = devices
    ref = EntityReference.from_dict(refs[1])
    entity = er.async_get(hass).async_get(ref.entity_id)
    dr.async_get(hass).async_update_device(entity.device_id, model_id='TV02-Zigbee')
    room = RoomBinding('a1b2c3d4', 'TV02 original', EntityReference.from_dict(refs[0]),
        (ref,), maximum_age_ms=10000)
    now = [100.0]
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [room], clock=lambda: now[0])
    await runtime.async_start()
    source = Tv02DiagnosticSource(runtime.entry.unique_id, room.room_id, ref, '_TZE200_hue3yfsn', 1)
    return runtime, room, source, now


def receive(reports, value=None, **kwargs):
    args = dict(retained=False, received_at=100, received_unix_ms=10000000, epoch=reports.epoch)
    args.update(kwargs)
    return reports.receive(TOPIC, json.dumps(packet(device_ieee='0x0000000000000002') if value is None else value), **args)


@pytest.mark.asyncio
async def test_explicit_native_selection_and_no_implicit_source_or_state_qualification(hass, devices):
    runtime,room,source,now = await system(hass,devices)
    try:
        empty=OriginalTv02Reports(runtime)
        assert not empty.topics and empty.status(room.room_id)=={}
        reports=OriginalTv02Reports(runtime,(source,))
        runtime.original_tv02_reports=reports
        hass.states.async_set(source.reference.entity_id,'heat',{'temperature':99, 'preset_mode':'manual'})
        assert receive(reports)
        status=runtime.actuator_report_status(room.room_id)[source.reference.entity_id]
        assert status['fields']=={'target_centi_c':2100}
        assert not status['control_qualified'] and not status['command_correlated'] and not status['valve_ready']
        assert runtime.measurement_status(room.room_id)['status']=='profile_missing'
        assert not runtime._profiles and not runtime._pending and runtime._bench_owner is None
        assert set(reports.topics)=={TOPIC}
        assert '0x0000' not in json.dumps(status)
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['entry','room','manufacturer','endpoint','reference','model','duplicate','non_tuple'])
async def test_explicit_pins_reject_wrong_owner_binding_and_unreviewed_fingerprints(hass,devices,fault):
    runtime,room,source,_=await system(hass,devices)
    try:
        if fault=='entry': source=replace(source,entry_unique_id='other')
        elif fault=='room': source=replace(source,room_id='deadbeef')
        elif fault=='manufacturer': source=replace(source,manufacturer='unknown')
        elif fault=='endpoint': source=replace(source,endpoint=True)
        elif fault=='reference': source=replace(source,reference=room.temperature)
        elif fault=='model':
            entity=er.async_get(hass).async_get(source.reference.entity_id)
            dr.async_get(hass).async_update_device(entity.device_id,model_id='another-TS0601')
        pins=[source] if fault=='non_tuple' else (source,source) if fault=='duplicate' else (source,)
        with pytest.raises(ValueError): OriginalTv02Reports(runtime,pins)
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['model','disabled','device_disabled','replacement','discovery','room','rename'])
async def test_binding_change_withdraws_until_rebuild_and_never_retakes_cached_evidence(hass,devices,change):
    runtime,room,source,_=await system(hass,devices)
    reports=OriginalTv02Reports(runtime,(source,));runtime.original_tv02_reports=reports
    try:
        assert receive(reports)
        registry=er.async_get(hass); entity=registry.async_get(source.reference.entity_id)
        if change=='model': dr.async_get(hass).async_update_device(entity.device_id,model_id='other')
        elif change=='disabled': registry.async_update_entity(entity.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
        elif change=='device_disabled': dr.async_get(hass).async_update_device(entity.device_id,disabled_by=dr.DeviceEntryDisabler.USER)
        elif change=='replacement':
            registry.async_remove(entity.entity_id)
            registry.async_get_or_create('climate','mqtt',entity.unique_id,device_id=entity.device_id)
        elif change=='discovery': devices[2][1]['state_topic']='foreign/changed'
        elif change=='rename': registry.async_update_entity(entity.entity_id,new_entity_id='climate.changed_original')
        else: runtime.rooms[room.room_id]=replace(room,actuators=())
        assert reports.status(room.room_id)[source.reference.entity_id]['status']=='binding_changed'
        assert not receive(reports,packet(sequence=2,device_ieee='0x0000000000000002'))
        assert reports.status(room.room_id)[source.reference.entity_id]['fields']=={}
        if change=='model':
            dr.async_get(hass).async_update_device(entity.device_id,model_id='TV02-Zigbee')
            assert not receive(reports,packet(sequence=3,device_ieee='0x0000000000000002'))
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_existing_registry_event_withdraws_even_when_model_changes_back_before_packet(hass,devices):
    runtime,room,source,_=await system(hass,devices)
    reports=OriginalTv02Reports(runtime,(source,));runtime.original_tv02_reports=reports
    try:
        assert receive(reports)
        entity=er.async_get(hass).async_get(source.reference.entity_id)
        dr.async_get(hass).async_update_device(entity.device_id,model_id='other')
        await hass.async_block_till_done()
        assert reports.retired
        dr.async_get(hass).async_update_device(entity.device_id,model_id='TV02-Zigbee')
        await hass.async_block_till_done()
        assert reports.status(room.room_id)[source.reference.entity_id]['status']=='binding_changed'
    finally:
        await runtime.async_stop()


def mqtt_boundary(monkeypatch):
    subscriptions={};removed=[];statuses=[]
    async def subscribe(_hass,topic,callback,**kwargs):
        subscriptions[topic]=callback
        return lambda:removed.append(topic)
    monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    monkeypatch.setattr(mqtt,'async_subscribe_connection_status',lambda _h,cb:statuses.append(cb) or (lambda:removed.append('status')))
    monkeypatch.setattr(mqtt,'async_publish',AsyncMock())
    from custom_components.open_thermostat import v1_mqtt
    monkeypatch.setattr(v1_mqtt.dt_util,'utcnow',lambda:datetime.fromtimestamp(10000,UTC))
    return subscriptions,removed,statuses


@pytest.mark.asyncio
async def test_one_native_worker_bounded_pending_slot_disconnect_and_unload(hass,devices,monkeypatch):
    runtime,room,source,now=await system(hass,devices)
    subscriptions,removed,statuses=mqtt_boundary(monkeypatch)
    connection=NativeShadowConnection(runtime,tv02_sources=(source,))
    try:
        await connection.async_start()
        assert set(subscriptions)=={'fixture/v1/fw/#',TOPIC}
        client=connection.client
        client.receive=AsyncMock(wraps=client.receive)
        raw=json.dumps(packet(device_ieee='0x0000000000000002'))
        msg=SimpleNamespace(topic=TOPIC,payload=raw,retain=False)
        original=subscriptions[TOPIC]
        for _ in range(100): original(msg)
        assert connection.queue.qsize()==1
        await connection.queue.join()
        client.receive.assert_not_awaited()
        assert runtime.actuator_report_status(room.room_id)[source.reference.entity_id]['fields']=={'target_centi_c':2100}
        for bad in (SimpleNamespace(topic=TOPIC,payload=b' '*2049,retain=False),
                    SimpleNamespace(topic=TOPIC,payload=raw,retain=True)):
            original(bad)
        assert connection.queue.empty()
        for _ in range(32):connection.queue.put_nowait(('noop',None))
        original(msg)
        assert connection.queue.qsize()==32 and not connection.original_pending
        await connection.queue.join()
        original(SimpleNamespace(topic=TOPIC,payload=json.dumps(packet(sequence=2,device_ieee='0x0000000000000002')),retain=False))
        statuses[0](False)
        await connection.queue.join()
        assert runtime.actuator_report_status(room.room_id)[source.reference.entity_id]['status']=='disconnected'
        assert not receive(connection.tv02_reports)
    finally:
        await connection.async_close()
        assert runtime.original_tv02_reports is None
        assert runtime.actuator_report_status(room.room_id)=={}
        assert connection.worker.done() and connection.queue.empty()
        assert set(removed)=={'fixture/v1/fw/#',TOPIC,'status'}
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_optional_subscribe_and_diagnostic_exception_cannot_reset_control_owner(hass,devices,monkeypatch):
    runtime,room,source,_=await system(hass,devices)
    subscriptions,removed,_=mqtt_boundary(monkeypatch)
    original_subscribe=mqtt.async_subscribe
    async def denied(h,topic,callback,**kwargs):
        if topic==TOPIC:raise RuntimeError('private optional refusal')
        return await original_subscribe(h,topic,callback,**kwargs)
    monkeypatch.setattr(mqtt,'async_subscribe',denied)
    connection=NativeShadowConnection(runtime,tv02_sources=(source,))
    try:
        await connection.async_start()
        assert not connection.worker.done() and not connection.closed
        assert runtime.actuator_report_status(room.room_id)[source.reference.entity_id]['status']=='unavailable'
    finally:
        await connection.async_close();await runtime.async_stop()


@pytest.mark.asyncio
async def test_unexpected_receiver_exception_keeps_native_session_and_releases_pending_slot(hass,devices,monkeypatch):
    runtime,room,source,_=await system(hass,devices)
    subscriptions,removed,_=mqtt_boundary(monkeypatch)
    connection=NativeShadowConnection(runtime,tv02_sources=(source,))
    try:
        await connection.async_start()
        client=connection.client
        before=client.last_rx,client.grant_until,client.lease_until,client.error
        monkeypatch.setattr(connection.tv02_reports,'receive',Mock(side_effect=RuntimeError('private receiver failure')))
        subscriptions[TOPIC](SimpleNamespace(topic=TOPIC,payload='{}',retain=False))
        await connection.queue.join()
        assert not connection.original_pending and not connection.worker.done()
        assert (client.last_rx,client.grant_until,client.lease_until,client.error)==before
        assert runtime.actuator_report_status(room.room_id)[source.reference.entity_id]['status']=='unavailable'
    finally:
        await connection.async_close();await runtime.async_stop()


@pytest.mark.asyncio
async def test_temperature_and_tv02_share_one_diagnostic_slot(hass,devices,monkeypatch):
    runtime,room,source,now=await system(hass,devices)
    from test_original_temperature import packet as temperature_packet
    sensor=er.async_get(hass).async_get(room.temperature.entity_id)
    dr.async_get(hass).async_update_device(sensor.device_id,model_id='WSDCGQ11LM')
    devices[2][0]['value_template']='{{ value_json.temperature }}'
    temperature_topic='custom-z2m/bridge/openthermostat/original_temperature'
    subscriptions,removed,statuses=mqtt_boundary(monkeypatch)
    connection=NativeShadowConnection(runtime,tv02_sources=(source,))
    try:
        await connection.async_start()
        assert set(subscriptions)=={'fixture/v1/fw/#',TOPIC,temperature_topic}
        subscriptions[temperature_topic](SimpleNamespace(topic=temperature_topic,payload=json.dumps(temperature_packet()),retain=False))
        subscriptions[TOPIC](SimpleNamespace(topic=TOPIC,payload=json.dumps(packet(device_ieee='0x0000000000000002')),retain=False))
        assert connection.queue.qsize()==1
        await connection.queue.join()
        assert runtime.measurement_status(room.room_id)['original_report']['status']=='received_unqualified'
        assert runtime.actuator_report_status(room.room_id)[source.reference.entity_id]['status']=='waiting'
        subscriptions[TOPIC](SimpleNamespace(topic=TOPIC,payload=json.dumps(packet(device_ieee='0x0000000000000002')),retain=False))
        await connection.queue.join()
        assert runtime.actuator_report_status(room.room_id)[source.reference.entity_id]['status']=='received_unqualified'
        statuses[0](False)
        assert runtime.measurement_status(room.room_id)['original_report']['status']=='disconnected'
        assert runtime.actuator_report_status(room.room_id)[source.reference.entity_id]['status']=='disconnected'
        await connection.queue.join()
    finally:
        await connection.async_close();await runtime.async_stop()


@pytest.mark.asyncio
async def test_old_connection_close_does_not_remove_new_diagnostic_owner(hass,devices,monkeypatch):
    runtime,room,source,_=await system(hass,devices)
    subscriptions,removed,_=mqtt_boundary(monkeypatch)
    connection=NativeShadowConnection(runtime,tv02_sources=(source,))
    try:
        await connection.async_start()
        old_callback=subscriptions[TOPIC]
        new_owner=OriginalTv02Reports(runtime,(source,))
        runtime.original_tv02_reports=new_owner
        await connection.async_close()
        assert runtime.original_tv02_reports is new_owner
        old_callback(SimpleNamespace(topic=TOPIC,payload='{}',retain=False))
        assert connection.queue.empty()
        assert new_owner.status(room.room_id)[source.reference.entity_id]['status']=='waiting'
    finally:
        await connection.async_close();runtime.original_tv02_reports=None;await runtime.async_stop()


@pytest.mark.asyncio
async def test_actual_node_producer_crosses_native_mqtt_worker_into_runtime_without_ack(hass,devices,monkeypatch):
    from test_original_tv02 import producer_packet
    from custom_components.open_thermostat.original_tv02 import decode
    runtime,room,source,now=await system(hass,devices)
    raw=await hass.async_add_executor_job(producer_packet,'0x0000000000000002')
    value=decode(raw)
    subscriptions,removed,statuses=mqtt_boundary(monkeypatch)
    from custom_components.open_thermostat import v1_mqtt
    monkeypatch.setattr(v1_mqtt.dt_util,'utcnow',lambda:datetime.fromtimestamp(value['received_at_unix_ms']/1000,UTC))
    connection=NativeShadowConnection(runtime,tv02_sources=(source,))
    try:
        await connection.async_start()
        client=connection.client
        client.receive=AsyncMock(wraps=client.receive)
        subscriptions[TOPIC](SimpleNamespace(topic=TOPIC,payload=raw.encode(),retain=False))
        await connection.queue.join()
        result=runtime.actuator_report_status(room.room_id)[source.reference.entity_id]
        assert result['status']=='received_unqualified'
        assert result['fields']==dict(target_centi_c=2100,local_temperature_centi_c=2200,
            preset='manual',heating_stop=False,frost_protection=True)
        assert not any(result[key] for key in ('command_correlated','valve_ready','control_qualified'))
        client.receive.assert_not_awaited()
    finally:
        await connection.async_close();await runtime.async_stop()

@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['room', 'manufacturer', 'endpoint', 'model', 'duplicate', 'non_tuple'])
async def test_invalid_optional_diagnostic_pin_keeps_native_connection_running(hass, devices, monkeypatch, fault, caplog):
    runtime, room, source, _ = await system(hass, devices)
    subscriptions, removed, _ = mqtt_boundary(monkeypatch)
    if fault == 'room': source = replace(source, room_id='deadbeef')
    elif fault == 'manufacturer': source = replace(source, manufacturer='unsupported')
    elif fault == 'endpoint': source = replace(source, endpoint=True)
    elif fault == 'model':
        entity = er.async_get(hass).async_get(source.reference.entity_id)
        dr.async_get(hass).async_update_device(entity.device_id, model_id='another-model')
    pins = [source] if fault == 'non_tuple' else (source, source) if fault == 'duplicate' else (source,)
    connection = NativeShadowConnection(runtime, tv02_sources=pins)
    try:
        await connection.async_start()
        assert set(subscriptions) == {'fixture/v1/fw/#'}
        assert connection.client is not None and not connection.worker.done()
        assert not connection.tv02_reports.topics
        assert runtime.actuator_report_status(room.room_id) == {}
        assert runtime.measurement_status(room.room_id)['status'] == 'profile_missing'
        assert 'source binding unavailable' in caplog.text
        assert '0x0000' not in caplog.text
    finally:
        await connection.async_close()
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_reviewed_source_selection_is_entry_scoped_and_ignores_options(hass, devices, monkeypatch):
    import custom_components.open_thermostat as integration
    runtime, room, source, _ = await system(hass, devices)
    try:
        # Even a correctly typed object in an option is not source selection.
        hass.config_entries.async_update_entry(runtime.entry, options={
            **runtime.entry.options, 'tv02_sources': [{'entry_unique_id': source.entry_unique_id,
                'room_id': source.room_id, 'reference': source.reference.as_dict(),
                'manufacturer': source.manufacturer, 'endpoint': source.endpoint}],
            'tv02_control_qualified': True})
        assert integration._selected_original_tv02_sources(runtime.entry) == ()
        other = replace(source, entry_unique_id='another-installation')
        monkeypatch.setattr(integration, '_ORIGINAL_TV02_DIAGNOSTIC_SOURCES', (other, source))
        assert integration._selected_original_tv02_sources(runtime.entry) == (source,)
        for invalid in ([source], (object(),), (replace(source, entry_unique_id=True),), (source,) * 65):
            monkeypatch.setattr(integration, '_ORIGINAL_TV02_DIAGNOSTIC_SOURCES', invalid)
            assert integration._selected_original_tv02_sources(runtime.entry) == ()
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('reviewed', [False, True])
async def test_normal_integration_startup_passes_only_reviewed_diagnostic_sources(hass, devices, monkeypatch, reviewed):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat import v1_mqtt
    _, refs, _ = devices
    reference = EntityReference.from_dict(refs[1])
    entity = er.async_get(hass).async_get(reference.entity_id)
    dr.async_get(hass).async_update_device(entity.device_id, model_id='TV02-Zigbee')
    room = RoomBinding('a1b2c3d4', 'TV02 original', EntityReference.from_dict(refs[0]), (reference,))
    parent = entry(hass, enabled=True, room=room)
    source = Tv02DiagnosticSource(parent.unique_id, room.room_id, reference, '_TZE200_hue3yfsn', 1)
    monkeypatch.setattr(integration, '_ORIGINAL_TV02_DIAGNOSTIC_SOURCES', (source,) if reviewed else ())
    subscriptions, _, _ = mqtt_boundary(monkeypatch)
    monkeypatch.setattr(hass.config_entries, 'async_forward_entry_setups', AsyncMock())
    monkeypatch.setattr(hass.config_entries, 'async_unload_platforms', AsyncMock(return_value=True))
    captured = []
    def connection(runtime, *args, **kwargs):
        captured.append(kwargs)
        return NativeShadowConnection(runtime, *args, **kwargs)
    monkeypatch.setattr(v1_mqtt, 'NativeShadowConnection', connection)
    try:
        assert await integration.async_setup_entry(hass, parent)
        assert captured == ([{'tv02_sources': (source,)}] if reviewed else [{}])
        assert set(subscriptions) == ({'fixture/v1/fw/#', TOPIC} if reviewed else {'fixture/v1/fw/#'})
        runtime = hass.data['open_thermostat'][parent.entry_id]['v1_runtime']
        assert runtime.measurement_status(room.room_id)['status'] == 'profile_missing'
        assert not runtime._profiles and not runtime._pending
    finally:
        if parent.entry_id in hass.data.get('open_thermostat', {}):
            assert await integration.async_unload_entry(hass, parent)


async def graph_system(hass, devices):
    """Native product rooms own outputs in the installation, not RoomBinding."""
    from custom_components.open_thermostat.product import PRODUCT_CONFIG, INSTALLATION, default_document
    from custom_components.open_thermostat.v1_model import ROOM_GRAPH_DRAFT
    runtime, old, source, now = await system(hass, devices)
    room = replace(old, actuators=(), binding_mode=ROOM_GRAPH_DRAFT)
    runtime.rooms[room.room_id] = room
    document = default_document()
    document['groups'] = [dict(group_id='radiators', name='Radiators', emitter='radiator',
        supply_limits=dict(minimum_centi_c=2000, maximum_centi_c=4500), pump=None,
        pump_start_delay_s=0, postrun_s=0, mixing=None)]
    document['actuators'] = [dict(actuator_id='selected', room_id=room.room_id,
        group_id='radiators', profile='trv_room_setpoint', output=source.reference.as_dict(), settings={})]
    hass.config_entries.async_update_entry(runtime.entry,
        data={**runtime.entry.data, PRODUCT_CONFIG:1, INSTALLATION:dict(draft=document)})
    return runtime,room,source,now,document


@pytest.mark.asyncio
async def test_native_product_graph_selected_output_with_empty_legacy_actuators(hass,devices):
    from custom_components.open_thermostat.product import configuration_snapshot
    runtime,room,source,_,_ = await graph_system(hass,devices)
    before=configuration_snapshot(runtime.entry)
    try:
        assert room.actuators==()
        connection=NativeShadowConnection(runtime,tv02_sources=(source,))
        assert len(connection.tv02_reports.bindings)==1
        runtime.original_tv02_reports=connection.tv02_reports
        assert receive(connection.tv02_reports)
        status=runtime.actuator_report_status(room.room_id)[source.reference.entity_id]
        assert status['fields']=={'target_centi_c':2100}
        assert not status['control_qualified'] and not status['valve_ready'] and not status['command_correlated']
        assert runtime.measurement_status(room.room_id)['status']=='profile_missing'
        assert not runtime._profiles and runtime._bench_owner is None
        assert configuration_snapshot(runtime.entry)==before
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['missing_owner','malformed_owner','malformed_draft','duplicate_output','other_room','removed_output'])
async def test_graph_source_rejects_missing_malformed_or_other_selection_without_legacy_fallback(hass,devices,fault):
    from copy import deepcopy
    from custom_components.open_thermostat.product import INSTALLATION
    runtime,room,source,_,document=await graph_system(hass,devices)
    try:
        # Even a stale legacy tuple cannot authorize a graph-room report source.
        runtime.rooms[room.room_id]=replace(room,actuators=(source.reference,))
        data=deepcopy(dict(runtime.entry.data))
        if fault=='missing_owner':data.pop(INSTALLATION)
        elif fault=='malformed_owner':data[INSTALLATION]=[]
        elif fault=='malformed_draft':data[INSTALLATION]['draft']['extra']=True
        elif fault=='duplicate_output':
            duplicate=deepcopy(data[INSTALLATION]['draft']['actuators'][0]);duplicate['actuator_id']='second'
            data[INSTALLATION]['draft']['actuators'].append(duplicate)
        elif fault=='other_room':
            runtime.rooms['deadbeef']=replace(room,room_id='deadbeef')
            data[INSTALLATION]['draft']['actuators'][0]['room_id']='deadbeef'
        elif fault=='removed_output':data[INSTALLATION]['draft']['actuators']=[]
        hass.config_entries.async_update_entry(runtime.entry,data=data)
        with pytest.raises(ValueError):OriginalTv02Reports(runtime,(source,))
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_graph_output_removal_retires_existing_source_and_readdition_cannot_revive_it(hass,devices):
    from copy import deepcopy
    from custom_components.open_thermostat.product import INSTALLATION
    runtime,room,source,_,_=await graph_system(hass,devices)
    try:
        reports=OriginalTv02Reports(runtime,(source,));assert receive(reports)
        original=deepcopy(dict(runtime.entry.data));removed=deepcopy(original)
        removed[INSTALLATION]['draft']['actuators']=[]
        hass.config_entries.async_update_entry(runtime.entry,data=removed)
        assert reports.recheck()
        assert reports.status(room.room_id)[source.reference.entity_id]['status']=='binding_changed'
        hass.config_entries.async_update_entry(runtime.entry,data=original)
        assert not receive(reports,packet(sequence=2,device_ieee='0x0000000000000002'))
        assert reports.status(room.room_id)[source.reference.entity_id]['fields']=={}
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('maximum_age_ms', [1000, 20000])
@pytest.mark.parametrize('graph', [False, True])
@pytest.mark.parametrize('first_check', ['status', 'receive', 'recheck'])
async def test_changed_room_freshness_policy_retires_original_tv02_owner(hass, devices, maximum_age_ms, graph, first_check):
    if graph:
        runtime, room, source, now, _ = await graph_system(hass, devices)
    else:
        runtime, room, source, now = await system(hass, devices)
    reports = OriginalTv02Reports(runtime, (source,))
    try:
        assert receive(reports)
        runtime.rooms[room.room_id] = replace(room, maximum_age_ms=maximum_age_ms)
        if first_check == 'receive':
            assert not receive(reports, packet(sequence=2, device_ieee='0x0000000000000002'))
        elif first_check == 'recheck':
            assert reports.recheck()
        status = reports.status(room.room_id)[source.reference.entity_id]
        assert status['status'] == 'binding_changed'
        assert status['fields'] == {}
        assert not receive(reports, packet(sequence=2, device_ieee='0x0000000000000002'))
        runtime.rooms[room.room_id] = room
        assert not receive(reports, packet(sequence=3, device_ieee='0x0000000000000002'))
        assert reports.status(room.room_id)[source.reference.entity_id]['status'] == 'binding_changed'
        runtime.rooms[room.room_id] = replace(room, maximum_age_ms=maximum_age_ms)
        rebuilt = OriginalTv02Reports(runtime, (source,))
        assert rebuilt.status(room.room_id)[source.reference.entity_id]['status'] == 'waiting'
        assert receive(rebuilt)
        now[0] += maximum_age_ms / 1000
        status = rebuilt.status(room.room_id)[source.reference.entity_id]
        assert status['status'] == 'stale' and status['fields'] == {}
        assert not status['command_correlated'] and not status['valve_ready'] and not status['control_qualified']
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_room_display_rename_preserves_original_tv02_lifetime(hass, devices):
    runtime, room, source, now = await system(hass, devices)
    reports = OriginalTv02Reports(runtime, (source,))
    try:
        assert receive(reports)
        runtime.rooms[room.room_id] = replace(room, name='Changed display name')
        now[0] += 1
        status = reports.status(room.room_id)[source.reference.entity_id]
        assert status['status'] == 'received_unqualified'
        assert status['received_age_ms'] == 1000
    finally:
        await runtime.async_stop()
