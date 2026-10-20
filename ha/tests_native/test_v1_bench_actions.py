"""Registered native HA actions through actual supplied C++ shadow core."""
import asyncio
import copy
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.climate.const import HVACAction
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_climate import ShadowRoom
from custom_components.open_thermostat.v1_bench_actions import (
    async_register_entry, async_unregister_entry, KEY, Bench)
from custom_components.open_thermostat.v1_wire import canonical
from test_v1_native import room, entry, reference
from test_v1_wire_interop import FirmwareBus, RUNNER
IEEE = "0xbench"

def baseline():
    return {"device_options": {}, "devices": {IEEE: {"friendly_name": "selected"}},
            "advanced": {"cache_state": True, "last_seen": "ISO_8601"}}

def discovery():
    return {"device": {"model_id": "WSDCGQ11LM"}, "origin": {"sw_version": "2.14.2"},
            "state_topic": "zigbee2mqtt/selected", "unit_of_measurement": "°C",
            "unique_id": IEEE + "_temperature_zigbee2mqtt",
            "value_template": '{{ value_json["temperature"] }}'}

def arguments(e):
    return {"entry_id": e.entry_id, "baseline": baseline(), "discovery": discovery(),
            "ieee": IEEE, "discovery_topic": "homeassistant/sensor/selected/config",
            "ha_status_topic": "homeassistant/status", "transaction": "unique_bench_tx",
            "duration_s": 300}

@pytest_asyncio.fixture
async def action_system(hass, monkeypatch):
    source = er.async_get(hass).async_get_or_create("sensor", "mqtt", discovery()["unique_id"])
    hass.states.async_set(source.entity_id, "19.5", {"unit_of_measurement": "°C"})
    binding = replace(room(hass), temperature=reference(hass, source.entity_id))
    e = entry(hass, enabled=True, room=binding)
    runtime = ShadowRuntime(hass, e, [binding])
    await runtime.async_start()
    callbacks, publications, removed = {}, [], []
    async def subscribe(_hass, topic, cb, **kwargs):
        callbacks[topic] = cb
        return lambda: (removed.append(topic), callbacks.pop(topic, None))
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_subscribe_connection_status",
                        lambda hass, cb: lambda: removed.append("status"))
    async def publish(hass, topic, raw, **kwargs):
        assert topic.startswith("fixture/v1/")  # NO device/bridge mutation
        publications.append((topic.removeprefix("fixture/v1/"), raw))
    monkeypatch.setattr(mqtt, "async_publish", publish)
    connection = NativeShadowConnection(runtime)
    await connection.async_start()
    hass.data.setdefault("open_thermostat", {})[e.entry_id] = {
        "v1_runtime": runtime, "v1_connection": connection}
    async_register_entry(hass, e)
    library = RUNNER.parents[1] / ".runtime/runner-libs/extracted/usr/lib/x86_64-linux-gnu"
    loader = library / "ld-linux-x86-64.so.2"
    argv = [str(loader), "--library-path", str(library), str(RUNNER)] if loader.exists() else [str(RUNNER)]
    process = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE,
                                                   stdout=asyncio.subprocess.PIPE)
    bus = FirmwareBus(process, hass.loop.time)
    class Receiver:
        async def receive(self, topic, raw):
            cb = callbacks.get("fixture/v1/fw/#")
            if cb:
                cb(SimpleNamespace(topic="fixture/v1/"+topic, payload=raw, retain=False))
                await connection.queue.join()
    bus.client = Receiver()
    await bus.event("connect")
    errors = []
    async def drive():
        try:
            while True:
                await bus.event("tick")
                await connection.client.poll()
                for _ in range(100):
                    if not publications: break
                    topic, raw = publications.pop(0)
                    await bus.event("receive", topic=topic, raw=raw)
                else: raise AssertionError("wire loop")
                await asyncio.sleep(0.01)
                bus.now += 10
        except asyncio.CancelledError:
            raise
        except Exception as err:
            errors.append(err)
            raise
    driver = asyncio.create_task(drive())
    async with asyncio.timeout(5):
        while not connection.client.ready:
            await asyncio.sleep(0.01)
    def emit(topic, payload, retain=False, raw=False):
        cb = callbacks.get(topic)
        if cb is None and topic.startswith("fixture/v1/fw/"):
            cb = callbacks.get("fixture/v1/fw/#")
        if cb is None and topic.startswith("zigbee2mqtt/bridge/request/"):
            cb = callbacks.get("zigbee2mqtt/bridge/request/#")
        assert cb is not None, topic
        cb(SimpleNamespace(topic=topic, payload=payload if raw else json.dumps(payload), retain=retain))
    yield hass, e, runtime, binding, connection, emit, removed, bus
    await async_unregister_entry(hass, e.entry_id)
    await runtime.async_stop()
    driver.cancel()
    await asyncio.gather(driver, return_exceptions=True)
    process.stdin.close()
    await asyncio.wait_for(process.wait(), 5)
    assert not errors
    assert process.returncode == 0

async def action(hass, name, data):
    return await hass.services.async_call("open_thermostat", "source_bench_"+name, data,
                                         blocking=True, return_response=True)

def cutover(manager, emit):
    g = manager.listener.gate
    emit("homeassistant/sensor/selected/config", discovery(), True)
    inf = {"version": "2.14.2", "zigbee_herdsman_converters": {"version": "26.115.1"},
           "restart_required": False, "config": copy.deepcopy(g.baseline)}
    emit("zigbee2mqtt/bridge/info", inf, True)
    emit("zigbee2mqtt/bridge/request/device/options", g.request)
    inf["config"] = copy.deepcopy(g.expected)
    emit("zigbee2mqtt/bridge/info", inf)
    from custom_components.open_thermostat.v1_bench_source import clean, effective
    emit("zigbee2mqtt/bridge/response/device/options", {
        "status": "ok", "transaction": g.request["transaction"], "data": {
            "from": clean(effective(g.baseline, IEEE)),
            "to": clean(effective(g.expected, IEEE)), "id": IEEE, "restart_required": False}})
    assert g.phase == "draining"

@pytest.mark.asyncio
async def test_registered_actions_durable_mapping_exclusion_raw_fw_and_restore(action_system):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    status = await action(hass, "status", {"entry_id": e.entry_id})
    assert status["phase"] == "inactive"
    original = copy.deepcopy(connection.client.journal["accepted"]["mapping"])
    result = await action(hass, "start", arguments(e))
    assert result["phase"] == "listening"
    manager = hass.data[KEY][e.entry_id]
    assert runtime._bench_owner == binding.room_id
    accepted = connection.client.journal["accepted"]
    assert accepted["config"]["zones"][0]["report_evidence"] == "validated_integration_report"
    assert accepted["mapping"]["source_policy"] == "finite-native-source-bench/v1"
    assert connection.client.journal["staged"] is None
    assert await connection.client.store.async_load() == connection.client.journal
    # Actual native state events/cache reads cannot race the owned raw source.
    hass.states.async_set(runtime.resolved(binding.temperature), "25", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert binding.room_id not in runtime._pending
    assert runtime.decisions[binding.room_id].current_centi_c is None
    cutover(manager, emit)
    def report():
        return {"temperature": 19.5, "last_seen": datetime.now(timezone.utc).isoformat()}
    emit("zigbee2mqtt/selected", report())  # carryover discarded
    await asyncio.sleep(0.02)
    emit("zigbee2mqtt/selected", report())
    async with asyncio.timeout(5):
        while runtime.decisions[binding.room_id].current_centi_c != 1950:
            await asyncio.sleep(0.01)
    climate = ShadowRoom("fixture", binding, runtime)
    assert climate.hvac_action == HVACAction.IDLE
    assert climate.extra_state_attributes["simulated_demand"] is True
    assert climate.extra_state_attributes["boiler_output_enabled"] is False
    assert climate.extra_state_attributes["actuator_output_enabled"] is False
    stopped = await action(hass, "stop", {"entry_id": e.entry_id})
    assert stopped["normal_mapping_restored"] is True
    assert runtime._bench_owner is None and connection.bench is None
    assert connection.client.journal["accepted"]["mapping"] == original
    assert runtime.decisions[binding.room_id].current_centi_c is None
    assert "zigbee2mqtt/selected" in removed

@pytest.mark.asyncio
async def test_source_fault_autostop_restores_no_restart_or_option_writes(action_system):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    await action(hass, "start", arguments(e))
    manager = hass.data[KEY][e.entry_id]
    cutover(manager, emit)
    emit("homeassistant/status", "online")
    async with asyncio.timeout(5):
        while manager.phase != "stopped":
            await asyncio.sleep(0.01)
    assert manager.restored and runtime._bench_owner is None
    assert manager.reason == "lifecycle_changed"

@pytest.mark.asyncio
async def test_explicit_unload_withdraws_and_unregisters(action_system):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    await action(hass, "start", arguments(e))
    await async_unregister_entry(hass, e.entry_id)
    assert runtime._bench_owner is None
    assert not hass.services.has_service("open_thermostat", "source_bench_start")
    assert "zigbee2mqtt/selected" in removed

@pytest.mark.asyncio
async def test_wrong_binding_and_duplicate_start_fail(action_system):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    data = arguments(e); data["discovery"]["unique_id"] = "other"
    with pytest.raises(HomeAssistantError):
        await action(hass, "start", data)
    assert runtime._bench_owner is None
    await action(hass, "start", arguments(e))
    with pytest.raises(HomeAssistantError):
        await action(hass, "start", arguments(e))

@pytest.mark.asyncio
async def test_restore_failure_keeps_generic_source_fenced(action_system, monkeypatch):
    hass, e, runtime, binding, connection, emit, removed, bus = action_system
    await action(hass, "start", arguments(e))
    manager = hass.data[KEY][e.entry_id]
    monkeypatch.setattr(manager, "reconfigure", AsyncMock(side_effect=TimeoutError))
    status = await action(hass, "stop", {"entry_id": e.entry_id})
    assert status["phase"] == "blocked"
    assert runtime._bench_owner == binding.room_id
    with pytest.raises(HomeAssistantError):
        await action(hass, "start", arguments(e))
