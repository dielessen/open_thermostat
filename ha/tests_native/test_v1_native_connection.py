
"""Native MQTT API boundary and lifecycle with actual firmware behind the boundary.

MQTT public subscribe/publish are intercepted at the external IO boundary only.
HA MQTT packet client/broker is not exercised by these tests.
"""
import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from homeassistant.components import mqtt

from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_model import RoomDecision
from custom_components.open_thermostat.v1_wire import canonical
from custom_components.open_thermostat import async_setup_entry, async_unload_entry
from test_v1_native import room, entry, physical_state, source_profile, reference
from test_v1_wire_interop import FirmwareBus, RUNNER

from pathlib import Path


@pytest.mark.asyncio
async def test_native_connection_full_sensor_fw_state_and_cleanup(hass, monkeypatch):
    binding = room(hass)
    parent = entry(hass, enabled=True, room=binding)
    runtime = ShadowRuntime(hass, parent, [binding])
    runtime.set_report_profile(binding.room_id, source_profile)
    await runtime.async_start()
    callbacks, publications, removed, service_calls = {}, [], [], []
    hass.services.async_register("climate", "set_temperature", lambda call: service_calls.append(call))

    async def subscribe(_hass, topic, callback, qos=0, encoding=None):
        callbacks["message"] = callback
        assert topic == "fixture/v1/fw/#" and qos == 0
        return lambda: removed.append("mqtt")
    def status(_hass, callback):
        callbacks["status"] = callback
        return lambda: removed.append("status")
    async def publish(_hass, topic, raw, qos=0, retain=False):
        assert topic.startswith("fixture/v1/") and qos == 0 and retain is False
        publications.append((topic.removeprefix("fixture/v1/"), raw))

    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_subscribe_connection_status", status)
    monkeypatch.setattr(mqtt, "async_publish", publish)
    connection = NativeShadowConnection(runtime)
    await connection.async_start()
    # Actual C++ runner; its emissions pass through the native subscription callback.
    library = RUNNER.parents[1] / ".runtime/runner-libs/extracted/usr/lib/x86_64-linux-gnu"
    loader = library / "ld-linux-x86-64.so.2"
    args = [str(loader), "--library-path", str(library), str(RUNNER)] if loader.exists() else [str(RUNNER)]
    process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                                                  stdout=asyncio.subprocess.PIPE)
    bus = FirmwareBus(process, hass.loop.time)

    class SubscriptionReceiver:
        async def receive(self, topic, raw):
            callbacks["message"](SimpleNamespace(
                topic="fixture/v1/" + topic, payload=raw, retain=False))
            await connection.queue.join()

    bus.client = SubscriptionReceiver()

    async def drain():
        for _ in range(100):
            await connection.queue.join()
            await hass.async_block_till_done()
            if not publications:
                return
            topic, raw = publications.pop(0)
            await bus.event("receive", topic=topic, raw=raw)
        raise AssertionError("protocol cycle")

    try:
        await bus.event("connect")
        await bus.event("tick")
        await drain()
        assert runtime.transport_ready
        assert runtime.decisions[binding.room_id].current_centi_c is None
        physical_state(hass, binding, key="real-test-report", value="19")
        await hass.async_block_till_done()
        await drain()
        assert runtime.decisions[binding.room_id].current_centi_c == 1900
        assert runtime.decisions[binding.room_id].demand
        assert service_calls == []  # No profile-C execution from shadow demand.
        callbacks["status"](False)
        await connection.queue.join()
        assert not runtime.transport_ready
    finally:
        await runtime.async_stop()
        process.stdin.close()
        await process.wait()
    assert connection.worker.done()
    assert connection.timer is None
    assert sorted(removed) == ["mqtt", "status"]
    assert not runtime._subscriptions and not runtime._expiries
    before = len(publications)
    callbacks["message"](SimpleNamespace(topic="fixture/v1/fw/hello", payload="{}", retain=False))
    assert len(publications) == before
    assert connection.queue.empty()


@pytest.mark.asyncio
async def test_explicit_disabled_setup_never_creates_mqtt_client(hass, monkeypatch):
    binding = room(hass)
    parent = entry(hass, enabled=False, room=binding)
    forward, unload, subscribe = AsyncMock(), AsyncMock(return_value=True), AsyncMock()
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", unload)
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    assert await async_setup_entry(hass, parent)
    assert not subscribe.called
    assert await async_unload_entry(hass, parent)
    assert forward.call_count == 1


@pytest.mark.asyncio
async def test_enabled_setup_and_teardown_owns_one_native_connection(hass, monkeypatch):
    binding = room(hass)
    parent = entry(hass, enabled=True, room=binding)
    forward, unload = AsyncMock(), AsyncMock(return_value=True)
    unsub = []
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", unload)
    monkeypatch.setattr(mqtt, "async_subscribe", AsyncMock(return_value=lambda: unsub.append("mqtt")))
    monkeypatch.setattr(mqtt, "async_subscribe_connection_status", lambda *a: lambda: unsub.append("status"))
    assert await async_setup_entry(hass, parent)
    runtime = hass.data["open_thermostat"][parent.entry_id]["v1_runtime"]
    assert runtime.enabled
    assert not runtime.transport_ready
    assert await async_unload_entry(hass, parent)
    assert sorted(unsub) == ["mqtt", "status"]
    assert not runtime._subscriptions


@pytest.mark.asyncio
async def test_registry_rename_cannot_reassign_same_actuator_to_second_room(hass):
    from homeassistant.helpers import entity_registry as er
    from custom_components.open_thermostat.v1_config_flow import validate_room
    binding = room(hass)
    parent = entry(hass, room=binding)
    er.async_get(hass).async_update_entity(binding.actuators[0].entity_id,
                                         new_entity_id="climate.renamed_actuator")
    other = room(hass, "deadbeef", "other")
    with pytest.raises(ValueError, match="duplicate_actuator"):
        validate_room(hass, parent, {
            "room_id": other.room_id, "name": "other",
            "temperature_entity": other.temperature.entity_id,
            "actuator_entities": ["climate.renamed_actuator"]})


@pytest.mark.asyncio
async def test_schedule_and_base_target_are_gui_bindings_not_entity_ids_on_wire(hass):
    from homeassistant.helpers import entity_registry as er
    from custom_components.open_thermostat.v1_config_flow import validate_room
    from custom_components.open_thermostat.v1_mqtt import async_build_configuration
    from unittest.mock import patch
    binding = room(hass)
    parent = entry(hass)
    schedule = er.async_get(hass).async_get_or_create("schedule", "schedule", "schedule-id",
                                                    suggested_object_id="heating_week")
    configured = validate_room(hass, parent, {
        "room_id": binding.room_id, "name": "room",
        "temperature_entity": binding.temperature.entity_id,
        "actuator_entities": [binding.actuators[0].entity_id],
        "base_centi_c": 1750, "schedule_entity": schedule.entity_id})
    runtime = ShadowRuntime(hass, parent, [configured])
    fake_schedule = {"timezone": "UTC", "policy": "wall-clock-membership/v1",
                     "valid_from_utc": 1792368000, "valid_until_utc": 1792454400,
                     "base_centi_c": 1750, "transitions": [[1792368000, 1750]]}
    with patch("custom_components.open_thermostat.v1_mqtt.async_compile_schedule",
               AsyncMock(return_value=fake_schedule)) as compile_mock:
        zones, mapping = await async_build_configuration(runtime)
    assert configured.schedule.unique_id == "schedule-id"
    assert compile_mock.call_args.args[1] == schedule.entity_id
    assert zones[0]["base_centi_c"] == 1750
    assert zones[0]["schedule"] == fake_schedule
    assert "schedule.heating_week" not in canonical(zones)
    assert "sensor." not in canonical(zones)
