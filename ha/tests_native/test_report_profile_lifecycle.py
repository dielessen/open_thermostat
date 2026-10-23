"""Real HA events, scoped observer cleanup, original expiry and transport withdrawal.

Synthetic trusted reports exercise lifecycle only, never a production model pin.
"""
from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat.v1_model import QualifiedReport
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from test_v1_native import LocalTransport, entry, physical_state, room, source_profile


async def setup(hass):
    binding = room(hass)
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    transport = LocalTransport()
    runtime.attach_transport(transport)
    await runtime.async_start()
    release = runtime.set_report_profile(binding.room_id, source_profile)
    physical_state(hass, binding)
    await hass.async_block_till_done()
    assert runtime.measurement_status(binding.room_id)["usable"]
    return binding, runtime, transport, release


@pytest.mark.asyncio
async def test_replacement_immediately_withdraws_old_qualified_report_and_transport(hass):
    binding, runtime, transport, old_release = await setup(hass)
    try:
        old_time = runtime._sample_times[binding.room_id]
        release = runtime.set_report_profile(binding.room_id, lambda *_: None)
        assert not runtime.measurement_status(binding.room_id)["usable"]
        assert runtime.observations[binding.room_id].quality == "unverified"
        assert binding.room_id not in runtime._expiries
        await hass.async_block_till_done()
        assert transport.observations[-1][1].quality == "unverified"
        assert runtime._sample_times[binding.room_id] == old_time
        assert old_release() is False
        assert release() is True
        assert runtime.measurement_status(binding.room_id)["status"] == "profile_missing"
        assert release() is False
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_same_callable_registration_gets_new_owner_and_cache_cannot_requalify(hass):
    binding, runtime, transport, old_release = await setup(hass)
    try:
        key = runtime._sample_keys[binding.room_id]
        old_time = runtime._sample_times[binding.room_id]
        release = runtime.set_report_profile(binding.room_id, source_profile)
        assert old_release() is False
        # Reprocess precisely the old state/cache, not a new acquired report.
        runtime._observe(binding, "reported")
        assert not runtime.measurement_status(binding.room_id)["usable"]
        assert runtime._sample_keys[binding.room_id] == key
        assert runtime._sample_times[binding.room_id] == old_time
        physical_state(hass, binding, key="new-2", age=0)
        await hass.async_block_till_done()
        assert runtime.measurement_status(binding.room_id)["usable"]
        assert old_release() is False
        assert runtime.measurement_status(binding.room_id)["usable"]
        assert release() is True
        assert not runtime.measurement_status(binding.room_id)["usable"]
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_different_key_with_older_time_after_replacement_still_rejected(hass):
    binding, runtime, _, _ = await setup(hass)
    try:
        old_time = runtime._sample_times[binding.room_id]
        runtime.set_report_profile(binding.room_id, lambda *_: QualifiedReport("replayed-key", old_time-timedelta(milliseconds=1)))
        runtime._observe(binding, "reported")
        assert runtime.observations[binding.room_id].quality == "out_of_order"
        assert not runtime.measurement_status(binding.room_id)["usable"]
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("raises", [False, True])
async def test_reentrant_replacement_cannot_admit_the_old_callbacks_result(hass, raises):
    binding, runtime, _, _ = await setup(hass)
    try:
        def replace_self(*_):
            runtime.set_report_profile(binding.room_id, lambda *_: None)
            if raises:
                raise RuntimeError("old disposed observer failed")
            return QualifiedReport("late-old-owner", dt_util.utcnow())
        runtime.set_report_profile(binding.room_id, replace_self)
        runtime._observe(binding, "reported")
        assert runtime.observations[binding.room_id].quality == "unverified"
        assert runtime._sample_keys[binding.room_id] != "late-old-owner"
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_queued_old_expiry_cannot_invalidate_new_owner_or_new_report(hass, monkeypatch):
    from custom_components.open_thermostat import v1_runtime
    callbacks = []
    original = v1_runtime.async_call_later
    def capture(*args):
        callbacks.append(args[2])
        return original(*args)
    monkeypatch.setattr(v1_runtime, "async_call_later", capture)
    binding, runtime, _, _ = await setup(hass)
    try:
        first_expiry = callbacks[-1]
        physical_state(hass, binding, key="new-2")
        await hass.async_block_till_done()
        second_expiry = callbacks[-1]
        first_expiry(None)
        assert runtime.measurement_status(binding.room_id)["usable"]
        runtime.set_report_profile(binding.room_id, source_profile)
        physical_state(hass, binding, key="new-3")
        await hass.async_block_till_done()
        second_expiry(None)
        assert runtime.measurement_status(binding.room_id)["usable"]
        callbacks[-1](None)
        assert runtime.measurement_status(binding.room_id)["status"] == "stale"
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_old_cleanup_cannot_detach_new_owner_after_stop_and_restart(hass):
    binding, runtime, _, old_release = await setup(hass)
    await runtime.async_stop()
    assert old_release() is False
    runtime.attach_transport(LocalTransport())
    await runtime.async_start()
    release = runtime.set_report_profile(binding.room_id, source_profile)
    try:
        assert old_release() is False
        assert runtime.measurement_status(binding.room_id)["report_profile_configured"]
        assert not runtime.measurement_status(binding.room_id)["usable"]
        assert release() is True
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [None, 0, {}, "trusted"])
async def test_bad_registration_does_not_replace_existing_owner(hass, invalid):
    binding, runtime, _, release = await setup(hass)
    try:
        with pytest.raises(ValueError, match="callable"):
            runtime.set_report_profile(binding.room_id, invalid)
        assert runtime.measurement_status(binding.room_id)["usable"]
        assert release() is True
    finally:
        await runtime.async_stop()
