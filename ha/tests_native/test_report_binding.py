"""Synthetic report evidence on real native registries; no physical qualification."""
import asyncio
from dataclasses import replace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat.v1_model import QualifiedReport, EntityReference
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from test_v1_native import room, entry, physical_state, source_profile, LocalTransport


async def setup(hass, *, raw=False):
    binding=room(hass)
    if raw: binding=replace(binding, temperature=EntityReference(binding.temperature.entity_id))
    parent=entry(hass, enabled=True)
    device=dr.async_get(hass).async_get_or_create(config_entry_id=parent.entry_id,
        identifiers={('fixture','source')}, model_id='source-model')
    er.async_get(hass).async_update_entity(binding.temperature.entity_id,device_id=device.id)
    await hass.async_block_till_done()
    runtime=ShadowRuntime(hass,parent,[binding]);transport=LocalTransport()
    runtime.attach_transport(transport);await runtime.async_start()
    release=runtime.set_report_profile(binding.room_id,source_profile)
    physical_state(hass,binding);await hass.async_block_till_done()
    assert runtime.measurement_status(binding.room_id)['usable']
    return binding,runtime,transport,release,device,parent


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['model','device','disabled','device_disabled'])
async def test_native_drift_withdraws_without_new_temperature_event(hass,change):
    binding,runtime,transport,release,device,parent=await setup(hass)
    try:
        old_time=runtime._sample_times[binding.room_id]
        if change=='model':dr.async_get(hass).async_update_device(device.id,model_id='different-model')
        elif change=='disabled':er.async_get(hass).async_update_entity(binding.temperature.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
        elif change=='device_disabled':dr.async_get(hass).async_update_device(device.id,disabled_by=dr.DeviceEntryDisabler.USER)
        else:
            other=dr.async_get(hass).async_get_or_create(config_entry_id=parent.entry_id,identifiers={('fixture','other')})
            er.async_get(hass).async_update_entity(binding.temperature.entity_id,device_id=other.id)
        # A read before the queued registry listener must already deny usability.
        assert not runtime.measurement_status(binding.room_id)['usable']
        await hass.async_block_till_done()
        assert not runtime.measurement_status(binding.room_id)['report_profile_configured']
        assert release() is False
        assert transport.observations[-1][1].quality!='qualified'
        assert runtime._sample_times[binding.room_id]==old_time
    finally:await runtime.async_stop()


@pytest.mark.asyncio
async def test_pending_qualification_is_checked_before_transport_even_before_registry_callback(hass):
    binding,runtime,transport,_,device,_=await setup(hass)
    gate=asyncio.Event()
    original=transport.async_observation
    async def held(room_id,observation):
        await original(room_id,observation)
        if observation.source_key=='in-flight':await gate.wait()
    transport.async_observation=held
    try:
        physical_state(hass,binding,key='in-flight')
        runtime._observe(binding,'reported')
        before=len(transport.observations)
        assert transport.observations[-1][1].source_key=='in-flight'
        physical_state(hass,binding,key='queued-new')
        runtime._observe(binding,'reported')  # queue flush ahead of device-change callback
        dr.async_get(hass).async_update_device(device.id,model_id='different-model')
        gate.set()
        await hass.async_block_till_done()
        assert transport.observations[before:]
        assert all(o.quality!='qualified' for _,o in transport.observations[before:])
        assert not runtime.measurement_status(binding.room_id)['usable']
    finally:await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('raises',[False,True])
async def test_callback_cannot_rebind_then_return_or_raise_under_old_source(hass,raises):
    binding,runtime,_,_,device,_=await setup(hass)
    try:
        def change(*_):
            dr.async_get(hass).async_update_device(device.id,model_id='different-model')
            if raises:raise RuntimeError('old observer')
            return QualifiedReport('old-binding-result',dt_util.utcnow())
        runtime.set_report_profile(binding.room_id,change)
        runtime._observe(binding,'reported')
        assert not runtime.measurement_status(binding.room_id)['usable']
        assert runtime._sample_keys[binding.room_id]!='old-binding-result'
        await hass.async_block_till_done()
        assert not runtime.measurement_status(binding.room_id)['report_profile_configured']
    finally:await runtime.async_stop()


@pytest.mark.asyncio
async def test_same_native_sensor_rename_and_display_label_keep_registration_without_reaging_cache(hass):
    binding,runtime,_,release,_,_=await setup(hass)
    try:
        old_time=runtime._sample_times[binding.room_id]
        old=hass.states.get(binding.temperature.entity_id)
        new_id='sensor.renamed_measurement'
        er.async_get(hass).async_update_entity(binding.temperature.entity_id,new_entity_id=new_id,name='New display label')
        await hass.async_block_till_done()
        assert runtime.measurement_status(binding.room_id)['report_profile_configured']
        hass.states.async_set(new_id,old.state,old.attributes)
        await hass.async_block_till_done()
        assert not runtime.measurement_status(binding.room_id)['usable']
        assert runtime._sample_times[binding.room_id]==old_time
        attrs={**old.attributes,'physical_sample_key':'new-after-rename','physical_sample_at':dt_util.utcnow()}
        hass.states.async_set(new_id,'20.5',attrs);await hass.async_block_till_done()
        assert runtime.measurement_status(binding.room_id)['usable']
        assert release() is True
    finally:await runtime.async_stop()


@pytest.mark.asyncio
async def test_legacy_raw_entity_reference_does_not_transfer_profile_to_replacement_row(hass):
    binding,runtime,_,_,_,_=await setup(hass,raw=True)
    try:
        entity_id=binding.temperature.entity_id;old=hass.states.get(entity_id)
        registry=er.async_get(hass);registry.async_remove(entity_id);hass.states.async_remove(entity_id)
        replacement=registry.async_get_or_create('sensor','fixture_driver','replacement-source',suggested_object_id=entity_id.split('.')[1])
        assert replacement.entity_id==entity_id
        attrs={**old.attributes,'physical_sample_key':'replacement-report','physical_sample_at':dt_util.utcnow()}
        hass.states.async_set(entity_id,'23',attrs);runtime._observe(binding,'reported')
        assert not runtime.measurement_status(binding.room_id)['usable']
        await hass.async_block_till_done()
        assert not runtime.measurement_status(binding.room_id)['report_profile_configured']
    finally:await runtime.async_stop()


@pytest.mark.asyncio
async def test_device_display_name_does_not_invalidate_or_renew_original_report(hass):
    binding,runtime,_,release,device,_=await setup(hass)
    try:
        original=runtime.observations[binding.room_id]
        dr.async_get(hass).async_update_device(device.id,name_by_user='New label')
        await hass.async_block_till_done()
        assert runtime.measurement_status(binding.room_id)['usable']
        assert runtime.observations[binding.room_id] is original
        assert release() is True
    finally:await runtime.async_stop()
