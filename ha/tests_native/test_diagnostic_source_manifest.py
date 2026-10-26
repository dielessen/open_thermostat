"""Private receive-only deployment pins through actual HA registries/startup."""
import json
import os
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er, device_registry as dr
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.diagnostic_source_manifest import FILE_NAME, decode_manifest, _read, async_selected_sources, MAX_BYTES
from custom_components.open_thermostat.v1_model import EntityReference, RoomBinding, MODE_LEGACY
from test_device_metadata import devices
from test_original_tv02_lifecycle import TOPIC, mqtt_boundary
from test_v1_native import entry


def source(**changes):
    value=dict(entry_unique_id='fixture',room_id='a1b2c3d4',entity_id='climate.valve',
               platform='mqtt',unique_id='private-native-fixture',manufacturer='_TZE200_hue3yfsn',endpoint=1)
    value.update(changes)
    return value


def document(sources=None):
    return dict(schema=1,kind='original_tv02_receive_only',sources=[source()] if sources is None else sources)


def raw(value=None):
    return json.dumps(document() if value is None else value).encode()


def install(hass, data=None):
    from pathlib import Path
    path=Path(hass.config.path(FILE_NAME));path.write_bytes(raw() if data is None else data);path.chmod(0o600)
    return path


@pytest.mark.parametrize('change', [
    {'entry_unique_id':False},{'entry_unique_id':'a\x00b'},{'room_id':'not-a-room'},
    {'entity_id':'switch.valve'},{'entity_id':'climate.a,climate.b'},
    {'platform':'template'},{'unique_id':''},{'unique_id':'a'*513},
    {'manufacturer':'_TZE200_other'},{'endpoint':True},{'endpoint':0},{'endpoint':241},
    {'control_qualified':True},{'valve_ready':True},
])
def test_invalid_identity_or_control_flags_rejected(change):
    with pytest.raises(ValueError):decode_manifest(raw(document([source(**change)])))


@pytest.mark.parametrize('value', [
    {},dict(schema=True,kind='original_tv02_receive_only',sources=[]),
    dict(schema=1,kind='control',sources=[]),dict(schema=1,kind='original_tv02_receive_only',sources={}),
    document([source(),source()]),document([source()]*65),
])
def test_manifest_schema_budget_and_duplicate_binding_rejected(value):
    with pytest.raises(ValueError):decode_manifest(raw(value))


@pytest.mark.parametrize('payload', [b'{"schema":1,"schema":1}',b'{"x":NaN}',b'[]',b'\xff',b'x'*(MAX_BYTES+1)])
def test_malformed_duplicate_or_nonfinite_bytes_rejected(payload):
    with pytest.raises((ValueError,UnicodeError)):decode_manifest(payload)


def test_immutable_exact_source_refs_no_authority_fields():
    pins=decode_manifest(raw())
    assert type(pins) is tuple and len(pins)==1
    assert pins[0].reference==EntityReference('climate.valve','mqtt','private-native-fixture')
    assert not hasattr(pins[0],'control_qualified')
    assert decode_manifest(raw(document([])))==()


@pytest.mark.asyncio
async def test_absence_privacy_entry_scope_and_no_sensitive_logs(hass,caplog):
    parent=entry(hass,enabled=True)
    assert await async_selected_sources(hass,parent)==()
    path=install(hass)
    assert len(await async_selected_sources(hass,parent))==1
    path.write_bytes(raw(document([source(entry_unique_id='another-installation')])));path.chmod(0o600)
    assert await async_selected_sources(hass,parent)==()
    path.write_bytes(b'private-native-fixture bad JSON')
    assert await async_selected_sources(hass,parent)==()
    assert 'private-native-fixture' not in caplog.text
    path.write_bytes(raw());path.chmod(0o644)
    assert await async_selected_sources(hass,parent)==()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['symlink','directory','fifo','oversize','changed_during_read'])
async def test_special_oversize_or_mutating_file_cannot_block_or_load(hass,monkeypatch,kind):
    parent=entry(hass,enabled=True);path=install(hass);data=path.read_bytes();path.unlink()
    if kind=='symlink':
        other=path.with_name('source.json');other.write_bytes(data);other.chmod(0o600);path.symlink_to(other)
    elif kind=='directory':path.mkdir()
    elif kind=='fifo':os.mkfifo(path,0o600)
    else:
        path.write_bytes(b'x'*(MAX_BYTES+1) if kind=='oversize' else data);path.chmod(0o600)
        if kind=='changed_during_read':
            read=os.read
            def changed(fd,length):
                result=read(fd,length)
                with path.open('ab') as stream:stream.write(b' ')
                return result
            monkeypatch.setattr(os,'read',changed)
    assert await async_selected_sources(hass,parent)==()


@pytest.mark.asyncio
async def test_compiled_source_precedence_and_legacy_do_not_read_file(hass,monkeypatch):
    parent=entry(hass,enabled=True)
    monkeypatch.setattr(hass,'async_add_executor_job',AsyncMock(side_effect=AssertionError('unexpected file access')))
    monkeypatch.setattr(integration,'_ORIGINAL_TV02_DIAGNOSTIC_SOURCES',(object(),))
    assert await integration._async_selected_original_tv02_sources(hass,parent)==()
    monkeypatch.setattr(integration,'_ORIGINAL_TV02_DIAGNOSTIC_SOURCES',())
    hass.config_entries.async_update_entry(parent,options={**parent.options,'integration_mode':MODE_LEGACY})
    assert await integration._async_selected_original_tv02_sources(hass,parent)==()


@pytest.mark.asyncio
@pytest.mark.parametrize('manifest',['valid','wrong_model','wrong_room','malformed','options_only'])
async def test_normal_startup_keeps_controller_and_native_guards(hass,devices,monkeypatch,manifest):
    _,refs,_=devices;ref=EntityReference.from_dict(refs[1]);entity=er.async_get(hass).async_get(ref.entity_id)
    if manifest!='wrong_model':dr.async_get(hass).async_update_device(entity.device_id,model_id='TV02-Zigbee')
    room=RoomBinding('a1b2c3d4','Original',EntityReference.from_dict(refs[0]),(ref,))
    parent=entry(hass,enabled=True,room=room)
    pin=source(entity_id=ref.entity_id,platform=ref.platform,unique_id=ref.unique_id,
               room_id='00000000' if manifest=='wrong_room' else room.room_id)
    if manifest=='options_only':
        hass.config_entries.async_update_entry(parent,options={**parent.options,'tv02_manifest':document([pin]),'tv02_control_qualified':True})
    else:install(hass,b'private-native-fixture broken' if manifest=='malformed' else raw(document([pin])))
    subscriptions,_,_=mqtt_boundary(monkeypatch)
    monkeypatch.setattr(hass.config_entries,'async_forward_entry_setups',AsyncMock())
    monkeypatch.setattr(hass.config_entries,'async_unload_platforms',AsyncMock(return_value=True))
    try:
        assert await integration.async_setup_entry(hass,parent)
        assert (TOPIC in subscriptions)==(manifest=='valid')
        runtime=hass.data['open_thermostat'][parent.entry_id]['v1_runtime']
        assert runtime.measurement_status(room.room_id)['status']=='profile_missing'
        assert not runtime._profiles and not runtime._pending
        if manifest=='valid':
            from types import SimpleNamespace
            from test_original_tv02 import packet
            payload=json.dumps(packet(device_ieee='0x0000000000000002'))
            subscriptions[TOPIC](SimpleNamespace(topic=TOPIC,payload=payload,retain=False))
            connection=hass.data['open_thermostat'][parent.entry_id]['v1_connection']
            await connection.queue.join()
            status=runtime.actuator_report_status(room.room_id)[ref.entity_id]
            assert status['fields']=={'target_centi_c':2100}
            assert status['control_qualified'] is status['valve_ready'] is status['command_correlated'] is False
            assert runtime.measurement_status(room.room_id)['status']=='profile_missing'
    finally:
        if parent.entry_id in hass.data.get('open_thermostat',{}):assert await integration.async_unload_entry(hass,parent)


@pytest.mark.asyncio
async def test_valid_compiled_pins_keep_precedence_over_private_file(hass,monkeypatch):
    parent=entry(hass,enabled=True);pins=decode_manifest(raw())
    monkeypatch.setattr(integration,'_ORIGINAL_TV02_DIAGNOSTIC_SOURCES',pins)
    monkeypatch.setattr(hass,'async_add_executor_job',AsyncMock(side_effect=AssertionError('unexpected file access')))
    assert await integration._async_selected_original_tv02_sources(hass,parent)==pins


def test_repeated_invalid_regular_path_checks_close_owned_descriptors(tmp_path):
    from pathlib import Path
    descriptors=Path('/proc/self/fd')
    if not descriptors.exists():pytest.skip('Descriptor accounting is Linux-only')
    path=tmp_path/'not-a-source';path.mkdir()
    before=len(list(descriptors.iterdir()))
    for _ in range(32):
        with pytest.raises(ValueError):_read(path)
    assert len(list(descriptors.iterdir()))==before
