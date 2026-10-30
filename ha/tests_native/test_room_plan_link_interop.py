"""Real C++ ShadowController with a room-plan-only link: no HA (legacy) rooms."""
import asyncio
import json

import pytest
from homeassistant.helpers.storage import Store

from custom_components.open_thermostat.v1_wire import ShadowClient, canonical
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from test_v1_native import entry
from test_v1_wire_interop import FirmwareBus, RUNNER
from test_boiler_fields import values


@pytest.mark.asyncio
async def test_link_without_ha_rooms_admits_session_and_boiler_fields_with_no_zones(hass):
    e = entry(hass, enabled=True)
    runtime = ShadowRuntime(hass, e, [])
    zones, mapping = await async_build_configuration(runtime)
    assert zones == [] and mapping["rooms"] == []
    process = await asyncio.create_subprocess_exec(str(RUNNER), 'ha1', 'boiler',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    bus = FirmwareBus(process, hass.loop.time)
    client = ShadowClient(runtime, 'ha1', bus.send, Store(hass, 1, 'plan_link_interop'), zones, mapping, bus.clock)
    bus.client = client; runtime.attach_transport(client)
    await client.async_start(); await runtime.async_start()
    try:
        for group in range(7):
            await bus.event('boiler_payload', group=group, raw=canonical(values(group, sampled=1000, observed=0)))
        await bus.start(); await bus.advance(1)
        assert client.ready and client.boiler_fields_supported
        configs = [json.loads(raw) for who, topic, raw in bus.transcript if who == 'ha' and topic == 'ha/config']
        # The one session config the link sends holds no zones at all: nothing to compute or heat.
        assert len(configs) == 1 and configs[0]['config']['zones'] == []
        assert client.journal['accepted']['config']['zones'] == []
        for _ in range(4):
            await bus.advance(2000)
        frames = [json.loads(raw) for who, topic, raw in bus.transcript
                  if who == 'fw' and topic == 'fw/telemetry/boiler_fields']
        assert frames and all(p['boiler_output_enabled'] is p['actuator_output_enabled'] is False for p in frames)
        assert client.ready and runtime.decisions == {}
    finally:
        await runtime.async_stop()
        process.stdin.close(); await asyncio.wait_for(process.wait(), 5)
        assert process.returncode == 0, await process.stderr.read()
