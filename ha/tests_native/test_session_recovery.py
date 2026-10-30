"""The native shadow session recovers by itself, without a reload (beta.19 + HA 0.4.0b11).

Real C++ ShadowController (out/shadow-runner) against the real HA ShadowClient.
Each case must be ready again within one slow refresh (60 s) and never wait on
a stale challenge, lease or nonce: (a) an HA restart, (b) a broker restart,
(c) an E32 reboot, (d) an E32-side disconnect and reconnect, (e) a long Wi-Fi
outage, and the b10 field case: a session whose first heartbeats are lost.
"""
import asyncio
from contextlib import asynccontextmanager

import pytest
from homeassistant.helpers.storage import Store

from custom_components.open_thermostat.v1_wire import ShadowClient
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from test_v1_native import room, entry
from test_v1_wire_interop import FirmwareBus, RUNNER

SLOW_REFRESH_MS = 60000


class Bus(FirmwareBus):
    """The FirmwareBus with a broker in between that can lose messages and retains hello."""

    def __init__(self, process, clock):
        super().__init__(process, clock)
        self.link_up = True          # False: nothing passes in either direction
        self.drop_ha = None          # predicate on (topic) for HA -> E32
        self.retained_hello = None

    async def send(self, topic, raw):
        if self.link_up and not (self.drop_ha and self.drop_ha(topic)):
            await super().send(topic, raw)

    async def event(self, op, **extra):
        import json
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
            result.append(item)
        from custom_components.open_thermostat.v1_wire import canonical
        for item in result:
            raw = canonical(item["payload"])
            if item["topic"] == "fw/hello":
                self.retained_hello = raw  # the E32 publishes hello retained (beta.19)
            if self.link_up:
                self.transcript.append(("fw", item["topic"], raw))
                await self.client.receive(item["topic"], raw)
        return result

    async def run(self, ms, step=1000):
        """The E32 loop and HA's 2 s poll, until `ms` passed; True once the client is ready."""
        for t in range(0, ms, step):
            self.now += step
            self.utc += step // 1000
            await self.event("tick")
            if (t // step) % 2:
                await self.client.poll()
            await self.pump()
            if self.client.ready:
                return True
        return self.client.ready


def new_client(runtime, bus, store_key):
    client = ShadowClient(runtime, "ha1", bus.send, Store(runtime.hass, 1, store_key), bus.zones, bus.mapping, bus.clock)
    bus.client = client
    runtime.attach_transport(client)
    return client


@asynccontextmanager
async def system(hass):
    binding = room(hass, age=10000)
    config_entry = entry(hass, enabled=True, room=binding)
    runtime = ShadowRuntime(hass, config_entry, [binding])
    zones, mapping = await async_build_configuration(runtime)
    process = await asyncio.create_subprocess_exec(str(RUNNER), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    bus = Bus(process, hass.loop.time)
    bus.zones, bus.mapping, bus.binding, bus.entry = zones, mapping, binding, config_entry
    client = new_client(runtime, bus, f"recovery.{config_entry.entry_id}")
    await client.async_start()
    await runtime.async_start()
    try:
        await bus.start()
        assert await bus.run(10000), client.error
        yield runtime, bus
    finally:
        await runtime.async_stop()
        process.stdin.close()
        await asyncio.wait_for(process.wait(), 5)
        assert process.returncode == 0, await process.stderr.read()


@pytest.mark.asyncio
async def test_a_ha_restart_gets_a_new_session_at_once(hass):
    async with system(hass) as (runtime, bus):
        old = bus.client
        old_session = old.session["adapter_session_id"]
        old.closed = True                                   # the old HA process is gone mid-session
        await runtime.async_stop()
        restarted = ShadowRuntime(hass, bus.entry, [bus.binding])
        client = new_client(restarted, bus, f"recovery.{bus.entry.entry_id}")  # the same Store
        await client.async_start()
        await restarted.async_start()
        # A restarted HA first gets the retained hello (its challenge may be old).
        await client.receive("fw/hello", bus.retained_hello, retained=True)
        await bus.pump()
        assert await bus.run(SLOW_REFRESH_MS), client.error
        assert client.session["adapter_session_id"] != old_session
        await restarted.async_stop()


@pytest.mark.asyncio
async def test_b_a_broker_restart_recovers_both_sides(hass):
    async with system(hass) as (runtime, bus):
        bus.link_up = False
        await bus.client.async_disconnected()               # HA's MQTT client lost the broker
        await bus.event("disconnect")                       # the E32 too
        bus.now += 20000
        bus.link_up = True
        await bus.event("connect")                          # both reconnect to the new broker
        assert await bus.run(SLOW_REFRESH_MS), bus.client.error


@pytest.mark.asyncio
async def test_c_an_e32_reboot_gets_a_new_session(hass):
    async with system(hass) as (runtime, bus):
        before = bus.client.identity
        await bus.event("boot", boot_id="boot2")
        await bus.event("connect")
        assert await bus.run(SLOW_REFRESH_MS), bus.client.error
        assert bus.client.identity[1] == "boot2" and before[1] == "boot1"


@pytest.mark.asyncio
async def test_d_an_e32_side_disconnect_and_reconnect(hass):
    async with system(hass) as (runtime, bus):
        await bus.event("disconnect")
        await bus.client.receive("fw/availability", "offline")   # its will
        bus.now += 5000
        await bus.event("connect")
        await bus.client.receive("fw/availability", "online")
        assert await bus.run(SLOW_REFRESH_MS), bus.client.error


@pytest.mark.asyncio
@pytest.mark.parametrize("outage_s", [45, 600])
async def test_e_a_long_wifi_outage_without_reconnect(hass, outage_s):
    """Nothing passes for minutes but neither MQTT client noticed: both leases run out."""
    async with system(hass) as (runtime, bus):
        bus.link_up = False
        for _ in range(outage_s):
            bus.now += 1000
            bus.utc += 1
            await bus.event("tick")
            await bus.client.poll()
            bus.outbox.clear()
        assert not bus.client.ready
        bus.link_up = True
        assert await bus.run(SLOW_REFRESH_MS), bus.client.error


@pytest.mark.asyncio
async def test_lost_first_heartbeats_never_leave_a_session_open_forever(hass):
    """b10 field case (5.5 h without session): HA held a session whose lease was never
    confirmed, the E32 ended it, and its hellos kept HA's last_rx fresh."""
    async with system(hass) as (runtime, bus):
        bus.drop_ha = lambda topic: topic == "ha/heartbeat"
        await bus.event("disconnect")
        await bus.event("connect")                          # a new session whose heartbeats are lost
        for _ in range(40):
            bus.now += 1000
            await bus.event("tick")
            await bus.client.poll()
            await bus.pump()
        assert not bus.client.ready
        bus.drop_ha = None
        assert await bus.run(SLOW_REFRESH_MS), bus.client.error
