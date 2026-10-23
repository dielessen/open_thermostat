"""Synthetic discovery/retained fixtures on real HA registries; no device claims."""
import asyncio
from copy import deepcopy
import json
import os
import socket
from types import MappingProxyType
from unittest.mock import Mock

import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import DATA_MQTT, MqttData, ReceiveMessage
from homeassistant.components.mqtt.discovery import MQTTDiscoveryPayload
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat import device_metadata as metadata
from custom_components.open_thermostat.native_plan import native_entry_state
from test_product_flow import product

REAL_CONNECT = socket.socket.connect


@pytest_asyncio.fixture
async def devices(hass):
    parent = product(hass)
    broker = ConfigEntry(domain='mqtt', title='offline fixture', version=1, minor_version=1,
        data={}, options={}, source='user', unique_id='offline',
        discovery_keys=MappingProxyType({}), subentries_data=[])
    hass.config_entries._entries[broker.entry_id] = broker
    data = hass.data[DATA_MQTT] = MqttData(client=Mock(), config=[])
    references = []; discoveries = []
    for index, domain in enumerate(('sensor', 'climate'), 1):
        ieee = f'0x{index:016x}'; identifier = 'zigbee2mqtt_' + ieee
        device = dr.async_get(hass).async_get_or_create(config_entry_id=broker.entry_id,
            identifiers={('mqtt', identifier)})
        entity = er.async_get(hass).async_get_or_create(domain, 'mqtt', f'selected_{index}',
            config_entry=broker, device_id=device.id)
        discovery = MQTTDiscoveryPayload({'origin': {'name': 'Zigbee2MQTT'},
            'device': {'identifiers': [identifier], 'name': f'Fixture {index}'},
            'state_topic': f'custom-z2m/Fixture {index}',
            'availability': [{'topic': 'custom-z2m/bridge/state'}],
            'value_template': '{{ value_json["device_temperature"] }}' if index == 1 else ''})
        data.debug_info_entities[entity.entity_id] = {'discovery_data': {'discovery_payload': discovery},
            'transmitted': {'private history': 'must not be read or exported'}}
        references.append({'entity_id': entity.entity_id, 'platform': 'mqtt', 'unique_id': entity.unique_id})
        discoveries.append(discovery)
    yield parent, references, discoveries


def messages():
    def definition(model, features):
        return {'model': model, 'vendor': 'Synthetic fixture', 'exposes': features,
                'private_key': 'private-not-for-output'}
    return {'custom-z2m/bridge/info': {'version': 'fixture-version', 'commit': 'fixture-commit',
                'coordinator': {'password': 'private-coordinator-not-for-output'}},
        'custom-z2m/bridge/devices': [
            {'ieee_address': '0x0000000000000001', 'definition': definition('sensor fixture', [
                {'property': 'device_temperature', 'access': 1, 'type': 'numeric', 'unit': '°C'}])},
            {'ieee_address': '0x0000000000000002', 'definition': definition('valve fixture', [
                {'type': 'climate', 'features': [
                    {'property': 'current_heating_setpoint', 'access': 7, 'value_min': 5, 'value_max': 30, 'value_step': .5},
                    {'property': 'local_temperature', 'access': 5, 'unit': '°C'},
                    {'property': 'preset', 'access': 7, 'values': ['auto', 'manual']},
                    {'property': 'schedule_monday', 'access': 3}]}])},
            {'ieee_address': '0x0000000000000099', 'friendly_name': 'UNRELATED_PRIVATE_DEVICE',
             'definition': definition('unrelated fixture', [{'property': 'external_temperature_input', 'access': 7}])}]}


def subscriptions(monkeypatch, hass, *, mode=None, parent=None, refs=None):
    payloads = messages(); calls = []; removed = []; ready = asyncio.Event()
    async def subscribe(h, topic, callback, **options):
        assert h is hass and topic in payloads and options == {'qos': 0, 'encoding': None}
        calls.append(topic)
        if mode == 'subscribe_failure' and len(calls) == 2:
            raise RuntimeError('private broker exception')
        def remove():
            removed.append(topic)
            if mode == 'cleanup_failure' and len(removed) == 1:
                raise RuntimeError('private cleanup exception')
        if mode not in ('timeout', 'cancel'):
            raw = json.dumps(payloads[topic]).encode()
            if mode == 'corrupt': raw = b'{"key":1,"key":2}'
            if mode == 'oversize': raw = b' ' * (metadata.MAX_BYTES + 1)
            callback(ReceiveMessage(topic, raw, 0, True, topic, hass.loop.time()))
        if len(calls) == 2:
            if mode == 'entry_change':
                hass.config_entries.async_update_entry(parent,
                    data={**parent.data, 'topic_prefix': 'concurrent_owner'})
            if mode == 'entity_rename':
                er.async_get(hass).async_update_entity(refs[0]['entity_id'], new_entity_id='sensor.renamed_fixture')
            ready.set()
        return remove
    monkeypatch.setattr(mqtt, 'async_subscribe', subscribe)
    monkeypatch.setattr(mqtt, 'async_publish', Mock(side_effect=AssertionError('metadata must never publish')))
    return calls, removed, ready


@pytest.mark.asyncio
async def test_selected_native_discovery_and_filtered_converter_declarations_no_secrets_or_other_devices(
        hass, devices, monkeypatch):
    parent, refs, _ = devices; before = native_entry_state(parent)
    calls, removed, _ = subscriptions(monkeypatch, hass)
    result = await metadata.async_read_selected_metadata(hass, parent, refs)
    assert set(calls) == set(removed) == set(messages())
    assert result['metadata_only'] and not result['physical_control_qualified']
    assert not result['measurement_acquisition_verified']
    assert result['devices'][0]['sensor_property'] == 'device_temperature'
    valve = result['devices'][1]
    assert valve['model'] == 'valve fixture'
    assert {x['role'] for x in valve['declared_features']} == {'setpoint', 'local_temperature', 'preset', 'local_schedule'}
    setpoint = next(x for x in valve['declared_features'] if x['role'] == 'setpoint')
    assert setpoint['access'] == 7 and setpoint['settable_declared'] and setpoint['value_step'] == .5
    rendered = json.dumps(result)
    assert all(s not in rendered for s in ('0x0000', 'private-', 'UNRELATED', 'custom-z2m', 'coordinator'))
    assert native_entry_state(parent) == before
    mqtt.async_publish.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['corrupt', 'oversize', 'entry_change', 'entity_rename', 'timeout', 'subscribe_failure', 'cleanup_failure'])
async def test_failures_always_remove_all_obtained_native_subscriptions(hass, devices, monkeypatch, mode):
    parent, refs, _ = devices
    calls, removed, _ = subscriptions(monkeypatch, hass, mode=mode, parent=parent, refs=refs)
    if mode == 'timeout': monkeypatch.setattr(metadata, 'TIMEOUT', .01)
    expected = RuntimeError if mode in ('subscribe_failure', 'cleanup_failure') else metadata.MetadataUnavailable
    with pytest.raises(expected):
        await metadata.async_read_selected_metadata(hass, parent, refs)
    assert set(removed) == set(calls[:1] if mode == 'subscribe_failure' else calls)
    mqtt.async_publish.assert_not_called()


@pytest.mark.asyncio
async def test_cancellation_unsubscribes_without_mutation(hass, devices, monkeypatch):
    parent, refs, _ = devices; before = native_entry_state(parent)
    calls, removed, ready = subscriptions(monkeypatch, hass, mode='cancel')
    task = asyncio.create_task(metadata.async_read_selected_metadata(hass, parent, refs))
    await ready.wait(); task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert set(removed) == set(calls) and native_entry_state(parent) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['identity', 'published_identity', 'provider', 'prefix', 'different_bridge', 'non_mqtt', 'missing'])
async def test_unknown_discovery_does_not_guess_or_subscribe(hass, devices, monkeypatch, fault):
    parent, refs, discoveries = devices
    if fault == 'identity':
        device = dr.async_get(hass).async_get(er.async_get(hass).async_get(refs[0]['entity_id']).device_id)
        dr.async_get(hass).async_update_device(device.id, new_identifiers={('mqtt', 'unrecognized fixture')})
    if fault == 'published_identity': discoveries[0]['device']['identifiers'] = ['zigbee2mqtt_0x0000000000000099']
    if fault == 'provider': discoveries[0]['origin']['name'] = 'Unknown provider'
    if fault == 'prefix': discoveries[0].update(state_topic='custom-z2m/anything/#')
    if fault == 'different_bridge': discoveries[1].update(state_topic='other/Fixture 2', availability=[{'topic': 'other/bridge/state'}])
    if fault == 'non_mqtt': refs[0]['platform'] = 'unrelated_driver'
    if fault == 'missing': er.async_get(hass).async_remove(refs[0]['entity_id'])
    calls, removed, _ = subscriptions(monkeypatch, hass)
    with pytest.raises(metadata.MetadataUnavailable):
        await metadata.async_read_selected_metadata(hass, parent, refs)
    assert not calls and not removed


@pytest.mark.asyncio
async def test_actual_discovery_base_expansion_and_friendly_name_prefix_without_default_guess(hass, devices):
    _, refs, discoveries = devices
    d = discoveries[0]; d['~'] = 'another-prefix/Fixture 1'; d['state_topic'] = '~/state'
    d['availability'] = [{'topic': 'another-prefix/bridge/state'}]
    assert metadata.selected_device(hass, refs[0]).prefix == 'another-prefix'
    d.pop('availability'); d['state_topic'] = 'another-prefix/Fixture 1'
    assert metadata.selected_device(hass, refs[0]).prefix == 'another-prefix'
    d['device']['name'] = 'wrong name'
    with pytest.raises(metadata.MetadataUnavailable): metadata.selected_device(hass, refs[0])


@pytest.mark.parametrize('fault', ['boolean_access', 'invalid_features', 'no_definition', 'depth', 'too_many'])
def test_malformed_or_unbounded_definitions_cannot_appear_supported(fault):
    row = deepcopy(messages()['custom-z2m/bridge/devices'][1])
    if fault == 'boolean_access': row['definition']['exposes'][0]['features'][0]['access'] = True
    if fault == 'no_definition': row['definition'] = None
    if fault == 'depth':
        for _ in range(10): row['definition']['exposes'] = [{'features': row['definition']['exposes']}]
    if fault == 'too_many': row['definition']['exposes'] = [{}] * 513
    if fault == 'invalid_features': row['definition']['exposes'][0]['features'] = 'invalid'
    with pytest.raises(metadata.MetadataUnavailable): metadata.project_definition(row)


def test_converter_options_are_separate_from_device_command_declarations():
    row = deepcopy(messages()['custom-z2m/bridge/devices'][1])
    row['definition']['options'] = [{'property': 'temperature_calibration', 'access': 2,
        'value_min': -10, 'value_max': 10, 'unit': '°C'}]
    result = metadata.project_definition(row)
    assert not any(x['role'] == 'calibration' for x in result['declared_features'])
    assert result['declared_options'][0]['role'] == 'calibration'
    assert not result['physical_control_qualified']


@pytest.mark.asyncio
async def test_real_existing_ha_mqtt_client_reads_exact_retained_fixture_metadata(hass, devices, monkeypatch):
    """Opt-in localhost broker; Paho is a TEST producer, never product code."""
    setting = os.environ.get('OPENTHERMOSTAT_TEST_MQTT_PORT')
    if not setting:
        pytest.skip('opt-in isolated localhost MQTT fixture not supplied')
    port = int(setting); assert 1024 <= port <= 65535
    def loopback_only(sock, address):
        assert address == ('127.0.0.1', port)
        return REAL_CONNECT(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', loopback_only)
    from homeassistant.components.mqtt.client import MQTT
    from homeassistant.components.mqtt.models import DATA_MQTT_AVAILABLE
    import paho.mqtt.client as paho
    parent, refs, discoveries = devices
    prefix = 'test_therm/v1/fw/metadata'
    for i,d in enumerate(discoveries, 1):
        d.update(state_topic=f'{prefix}/Fixture {i}', availability=[{'topic': prefix+'/bridge/state'}])
    broker = hass.config_entries.async_get_entry(er.async_get(hass).async_get(refs[0]['entity_id']).config_entry_id)
    conf = {'broker':'127.0.0.1','port':port,'username':'ha-test','password':'fixture-only',
        'protocol':'5','discovery':False,'client_id':'opth-ha-metadata-test','birth_message':{},'will_message':{}}
    hass.config_entries.async_update_entry(broker, data=conf)
    native = MQTT(hass, broker, conf); data = hass.data[DATA_MQTT]; data.client = native
    available = hass.data[DATA_MQTT_AVAILABLE] = hass.loop.create_future()
    producer = paho.Client(paho.CallbackAPIVersion.VERSION2, client_id='opth-metadata-fixture-producer',
        reconnect_on_failure=False)
    producer.username_pw_set('fw-test','fixture-only')
    network = None; fixture_topics = []
    async def pump():
        while True:
            for action in (producer.loop_read, producer.loop_write, producer.loop_misc):
                if action() != paho.MQTT_ERR_SUCCESS: return
            await asyncio.sleep(.01)
    async def published(messages):
        async with asyncio.timeout(5):
            while not all(m.is_published() for m in messages): await asyncio.sleep(.01)
    try:
        await native.async_start(data); await hass.async_start(); await native.async_connect(available)
        assert await asyncio.wait_for(available,5)
        await asyncio.to_thread(producer.connect,'127.0.0.1',port,10)
        network = asyncio.create_task(pump())
        frames = []
        for topic,payload in messages().items():
            topic = topic.replace('custom-z2m',prefix); fixture_topics.append(topic)
            frames.append(producer.publish(topic,json.dumps(payload),qos=1,retain=True))
        await published(frames)
        result = await metadata.async_read_selected_metadata(hass,parent,refs)
        assert result['devices'][1]['model'] == 'valve fixture'
        assert result['metadata_only'] and not result['physical_control_qualified']
        assert native.connected
        assert not data.subscriptions_to_restore
    finally:
        if network:
            await published([producer.publish(topic,b'',qos=1,retain=True) for topic in fixture_topics])
            producer.disconnect();network.cancel();await asyncio.gather(network,return_exceptions=True)
        if hasattr(native,'_mqttc'): await native.async_disconnect()
        native.cleanup()
