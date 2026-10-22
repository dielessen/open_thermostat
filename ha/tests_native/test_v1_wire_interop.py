
"""Real pinned HA + provided actual C++ ShadowController process, no network."""
import asyncio
from collections import deque
import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from homeassistant.helpers.storage import Store
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.climate.const import HVACAction

from custom_components.open_thermostat.v1_wire import ShadowClient, canonical, digest, parse
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_model import Observation
from custom_components.open_thermostat.v1_climate import ShadowRoom

from test_v1_native import room, entry

RUNNER = Path(os.environ.get("OPENTHERMOSTAT_TEST_FW_RUNNER",
    str(Path(__file__).resolve().parents[2] / "out/shadow-runner")))


class FirmwareBus:
    """Finite test harness, not a bridge/service or fake FW implementation."""
    def __init__(self, process, clock):
        self.process = process
        self.clock_base = clock()
        self.now = 0
        self.utc = 1792368000
        self.outbox = deque()
        self.transcript = []
        self.client = None
        self.drop = None

    def clock(self):
        return self.clock_base + self.now / 1000

    async def send(self, topic, raw):
        self.transcript.append(("ha", topic, raw))
        self.outbox.append((topic, raw))

    async def event(self, op, **extra):
        event = dict(op=op, now=self.now, utc=self.utc, **extra)
        self.process.stdin.write((json.dumps(event) + "\n").encode())
        await self.process.stdin.drain()
        result = []
        while True:
            line = await asyncio.wait_for(self.process.stdout.readline(), 5)
            assert line, "FW runner exited"
            item = json.loads(line)
            if item.get("event_done"):
                break
            self.transcript.append(("fw", item["topic"], canonical(item["payload"])))
            result.append(item)
        for item in result:
            if self.drop and self.drop(item):
                continue
            await self.client.receive(item["topic"], canonical(item["payload"]))
        return result

    async def pump(self):
        count = 0
        while self.outbox:
            count += 1
            assert count < 100, "protocol loop"
            topic, raw = self.outbox.popleft()
            await self.event("receive", topic=topic, raw=raw)
        await asyncio.sleep(0)

    async def start(self):
        await self.event("connect")
        await self.event("tick")
        await self.pump()

    async def advance(self, ms):
        self.now += ms
        self.utc += ms // 1000
        await self.event("tick")
        await self.client.poll()
        await self.pump()


@pytest_asyncio.fixture
async def integrated(hass):
    binding = room(hass, age=10000)
    config_entry = entry(hass, enabled=True, room=binding)
    runtime = ShadowRuntime(hass, config_entry, [binding])
    zones, mapping = await async_build_configuration(runtime)
    library_dir = RUNNER.parents[1] / ".runtime/runner-libs/extracted/usr/lib/x86_64-linux-gnu"
    loader = library_dir / "ld-linux-x86-64.so.2"
    argv = [str(loader), "--library-path", str(library_dir), str(RUNNER)] if loader.exists() else [str(RUNNER)]
    process = await asyncio.create_subprocess_exec(*argv,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    bus = FirmwareBus(process, hass.loop.time)
    client = ShadowClient(runtime, "ha1", bus.send,
        Store(hass, 1, f"test.shadow.{config_entry.entry_id}"), zones, mapping, bus.clock)
    bus.client = client
    runtime.attach_transport(client)
    await client.async_start()
    await runtime.async_start()
    yield runtime, client, bus, binding
    await runtime.async_stop()
    process.stdin.close()
    await asyncio.wait_for(process.wait(), 5)
    assert process.returncode == 0


@pytest.mark.asyncio
async def test_actual_fw_durable_first_config_then_qualified_sample_and_shadow_display(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    assert client.ready
    assert client.journal["staged"] is None
    assert client.journal["accepted"]["config"]["revision"] == 1
    assert runtime.decisions[binding.room_id].current_centi_c is None  # HA cache not a sample
    observation = Observation(19.5, "qualified", 10, "physical-1", bus.clock())
    await client.async_observation(binding.room_id, observation)
    await bus.pump()
    decision = runtime.decisions[binding.room_id]
    assert decision.current_centi_c == 1950
    assert decision.target_centi_c == 2100
    assert decision.demand is True
    entity = ShadowRoom("fixture", binding, runtime)
    assert entity.hvac_action == HVACAction.IDLE
    assert entity.extra_state_attributes["simulated_demand"] is True
    assert entity.extra_state_attributes["actuator_output_enabled"] is False
    assert entity.extra_state_attributes["boiler_output_enabled"] is False


@pytest.mark.asyncio
async def test_actual_fw_ack_is_not_optimistic_and_duplicate_does_not_restart_override(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    old_target = runtime.decisions[binding.room_id].target_centi_c
    pending = asyncio.create_task(runtime.async_set_temperature(binding.room_id, 22))
    await asyncio.sleep(0)
    assert runtime.decisions[binding.room_id].target_centi_c == old_target
    command = next(raw for who, topic, raw in reversed(bus.transcript)
                   if who == "ha" and topic == "ha/user_command")
    await bus.pump()
    await pending
    assert runtime.decisions[binding.room_id].target_centi_c == 2200
    await bus.event("receive", topic="ha/user_command", raw=command)
    assert any(topic == "fw/user_command_result" and json.loads(raw)["status"] == "duplicate"
               for who, topic, raw in bus.transcript if who == "fw")
    await bus.advance(6000)  # Grant rotation must preserve stream sequence.
    await bus.event("receive", topic="ha/user_command", raw=command)
    assert runtime.decisions[binding.room_id].target_centi_c == 2200


@pytest.mark.asyncio
async def test_actual_fw_stale_source_heartbeat_never_refreshes_measurement(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    await client.async_observation(binding.room_id, Observation(18, "qualified", 0, "sample1", bus.clock()))
    await bus.pump()
    assert runtime.decisions[binding.room_id].demand
    for _ in range(6):
        await bus.advance(2000)
    assert client.ready
    assert runtime.decisions[binding.room_id].current_centi_c is None
    assert runtime.decisions[binding.room_id].demand is False
    assert runtime.decisions[binding.room_id].reason == "source_unverified_or_stale"


@pytest.mark.asyncio
async def test_actual_fw_reconnect_rejects_previous_boot_epoch_command(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    await client.async_observation(binding.room_id, Observation(18, "qualified", 0, "sample1", bus.clock()))
    await bus.pump()
    old = next(raw for who, topic, raw in reversed(bus.transcript)
               if who == "ha" and topic == "ha/observations")
    await bus.event("disconnect")
    await client.async_disconnected()
    assert not client.ready
    await bus.event("connect")
    await bus.event("tick")
    await bus.pump()
    assert client.ready
    assert runtime.decisions[binding.room_id].current_centi_c is None
    await bus.event("receive", topic="ha/observations", raw=old)
    assert runtime.decisions[binding.room_id].current_centi_c is None


@pytest.mark.asyncio
async def test_actual_fw_commit_ack_lost_recovers_from_durable_stage(integrated):
    runtime, client, bus, binding = integrated
    bus.drop = lambda item: item["topic"] == "fw/config_result"
    await bus.start()
    assert client.ready
    assert client.journal["accepted"]["config"]["revision"] == 1
    assert client.journal["staged"] is None
    # Recreate HA client using real persisted Store while FW keeps config.
    await client.async_close()
    replacement = ShadowClient(runtime, "ha1", bus.send, client.store,
                               client.desired, client.mapping, bus.clock)
    await replacement.async_start()
    runtime._transport = replacement
    bus.client = replacement
    await bus.event("disconnect")
    await bus.event("connect")
    await bus.event("tick")
    await bus.pump()
    assert replacement.ready
    assert replacement.journal["accepted"]["config"]["revision"] == 1


@pytest.mark.asyncio
async def test_actual_fw_unknown_mapping_not_silently_adopted(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    # Simulate missing/old HA backup; valid remote config must stay diagnostic.
    client.journal = {"accepted": None, "staged": None}
    await bus.event("disconnect")
    await client.async_disconnected()
    await bus.event("connect")
    await bus.event("tick")
    await bus.pump()
    assert not client.ready
    assert client.error == "mapping_conflict"
    assert not any(topic == "ha/config" for topic, _ in bus.outbox)

@pytest.mark.asyncio
async def test_transport_lwt_is_expected_lifecycle_not_malformed_json(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    await client.receive("fw/availability", "offline")
    assert not client.ready and not runtime.decisions
    assert client.error == "firmware_offline"
    await client.receive("fw/availability", "online")
    assert not client.ready and client.identity is None
    assert client.error == "awaiting_firmware_handshake"
    await bus.event("disconnect")
    await bus.event("connect")
    await bus.event("tick")
    await bus.pump()
    assert client.ready


@pytest.mark.asyncio
async def test_retained_invalid_and_live_output_messages_cannot_apply(integrated):
    runtime, client, bus, binding = integrated
    await bus.start()
    state = next(raw for who, topic, raw in reversed(bus.transcript)
                 if who == "fw" and topic == "fw/state/zones")
    runtime.decisions.clear()
    await client.receive("fw/state/zones", state, retained=True)
    assert not runtime.decisions
    malicious = json.loads(state)
    malicious["actuator_output_enabled"] = True
    await client.receive("fw/state/zones", canonical(malicious))
    assert not runtime.decisions
    assert client.error == "invalid_firmware_message"


@pytest.mark.parametrize("raw", [
    '{"api":1,"api":2}', '{"x":NaN}', '{"x":"\\u0061"}',
    "[" * 20 + "]" * 20, '{"x":"' + "a" * 8192 + '"}', '{"x":"é"}'])
def test_raw_wire_rejects_ambiguous_or_unbounded_messages(raw):
    with pytest.raises(ValueError):
        parse(raw)
