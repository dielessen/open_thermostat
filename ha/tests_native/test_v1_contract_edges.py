
"""Failure/retry/budget gates against the actual FW, plus native schedule reports."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.v1_wire import canonical
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_config_flow import reference
from custom_components.open_thermostat.v1_model import RoomBinding
from test_v1_native import room, entry
from test_v1_wire_interop import integrated


@pytest.mark.asyncio
async def test_config_4096_budget_checked_before_durable_stage_or_publish(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    original = deepcopy(client.journal)
    zones = []
    for i in range(8):
        zone = deepcopy(client.desired[0])
        zone.update(zone_id=f"{i:08x}", sensor_id=f"s_{i:030x}", actuator_id=f"a_{i:030x}")
        zones.append(zone)
    zones[0]["schedule"] = {
        "timezone": "UTC", "policy": "wall-clock-membership/v1",
        "valid_from_utc": 1792368000, "valid_until_utc": 1792454400, "base_centi_c": 2100,
        "transitions": [[1792368000 + i, 2000 + i % 2] for i in range(128)]}
    client.desired = zones
    with pytest.raises(ValueError, match="configuration budget"):
        await client.propose(1)
    assert client.journal == original
    assert not bus.outbox


@pytest.mark.asyncio
async def test_durable_save_failure_never_sends_config(integrated, monkeypatch):
    runtime, client, bus, binding = integrated
    await bus.start()
    original = deepcopy(client.journal)
    client.desired[0]["base_centi_c"] = 2200
    monkeypatch.setattr(client.store, "async_save", AsyncMock(side_effect=OSError("test disk failure")))
    with pytest.raises(OSError):
        await client.propose(1)
    assert client.journal == original
    assert not bus.outbox


@pytest.mark.asyncio
async def test_exact_retry_bytes_after_lost_command_ack(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    bus.drop = lambda item: item["topic"] == "fw/user_command_result"
    task = asyncio.create_task(runtime.async_set_temperature(binding.room_id, 22))
    await asyncio.sleep(0)
    await bus.pump()
    first = [raw for who, topic, raw in bus.transcript if who == "ha" and topic == "ha/user_command"][-1]
    assert not task.done()
    bus.drop = None
    await bus.advance(2000)
    await task
    retries = [raw for who, topic, raw in bus.transcript if who == "ha" and topic == "ha/user_command"]
    assert retries == [first, first]


@pytest.mark.asyncio
async def test_repeated_grant_status_does_not_renew_deadline(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    status = [raw for who, topic, raw in bus.transcript if who == "fw" and topic == "fw/session"][-1]
    old_until = client.grant_until
    bus.now += 1000  # HA receiver monotone clock only, without ticking FW.
    await client.receive("fw/session", status)
    assert client.grant_until == old_until


@pytest.mark.asyncio
async def test_future_only_schedule_write_refreshes_without_state_change(hass, monkeypatch):
    registry = er.async_get(hass)
    schedule = registry.async_get_or_create("schedule", "schedule", "helper-week",
                                           suggested_object_id="heating_week")
    hass.states.async_set(schedule.entity_id, "off", {"next_event": "unchanged"})
    plain = room(hass)
    binding = RoomBinding.from_dict({**plain.as_dict(), "schedule": reference(hass, schedule.entity_id).as_dict()})
    runtime = ShadowRuntime(hass, entry(hass, enabled=True), [binding])
    await runtime.async_start()
    calls = []
    async def build(runtime):
        calls.append(True)
        return [], {"rooms": []}
    monkeypatch.setattr("custom_components.open_thermostat.v1_mqtt.async_build_configuration", build)
    monkeypatch.setattr(mqtt, "async_subscribe", AsyncMock(return_value=lambda: None))
    monkeypatch.setattr(mqtt, "async_subscribe_connection_status", lambda *args: lambda: None)
    connection = NativeShadowConnection(runtime)
    await connection.async_start()
    try:
        assert len(calls) == 1
        old = hass.states.get(schedule.entity_id)
        # Native Schedule.async_update_config->_update always writes state.
        # No changed event occurs when only a future block's data was edited.
        hass.states.async_set(schedule.entity_id, old.state, old.attributes)
        await hass.async_block_till_done()
        await connection.queue.join()
        assert len(calls) == 2
        registry.async_update_entity(schedule.entity_id, new_entity_id="schedule.renamed_week")
        await hass.async_block_till_done()
        await connection.queue.join()
        before = len(calls)
        hass.states.async_set("schedule.renamed_week", "off", {"next_event": "same"})
        await hass.async_block_till_done()
        await connection.queue.join()
        before_report = len(calls)
        hass.states.async_set("schedule.renamed_week", "off", {"next_event": "same"})
        await hass.async_block_till_done()
        await connection.queue.join()
        assert len(calls) > before_report >= before
    finally:
        await runtime.async_stop()
