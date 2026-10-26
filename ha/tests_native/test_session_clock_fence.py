"""Existing HA transport owner must not revive proofs after clock failure."""
import asyncio
import pytest
from homeassistant.exceptions import HomeAssistantError
from custom_components.open_thermostat.v1_wire import canonical
from test_modern_metrics import system, packet


@pytest.mark.asyncio
async def test_expired_grant_cannot_revive_after_clock_reversal(hass):
    _, runtime, client, now = await system(hass)
    try:
        assert client.ready
        now[0] = 110
        assert not client.ready
        now[0] = 109
        assert not client.ready
        assert client.session is None
        assert client.error == "local_monotonic_clock_invalid"
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["ready", "receive", "message", "poll"])
@pytest.mark.parametrize("bad_clock", [99, -1, float('nan'), float('inf'), True, None, "100", 10**500])
async def test_all_admission_boundaries_retire_proofs(hass, boundary, bad_clock):
    _, runtime, client, now = await system(hass)
    try:
        assert client.ready
        telemetry = canonical(packet(client))
        future = asyncio.get_running_loop().create_future()
        await client.message("ha/user_command", "room1", {"mode": "off"}, future)
        assert client.pending
        client._grant_proofs["proof1"] = 100
        client.send.reset_mock()
        now[0] = bad_clock
        if boundary == "ready":
            assert not client.ready
        elif boundary == "receive":
            await client.receive("fw/telemetry/ems_metrics", telemetry)
        elif boundary == "message":
            with pytest.raises(HomeAssistantError, match="clock invalid"):
                await client.message("ha/heartbeat", "adapter", {})
        else:
            await client.poll()
        assert client.session is None and not client.pending and not client._grant_proofs
        assert future.cancelled()
        assert not client.verified and client.grant_until == client.lease_until == 0
        client.send.assert_not_awaited()
        # Neither clock recovery, an ordinary reset, nor a replayed hello can
        # establish authority again under the failed transport owner.
        now[0] = 101
        client.reset_session()
        await client.async_disconnected()
        await client.receive("fw/hello", canonical(dict(api=1, mode="shadow",
            controller_id="e32_lab", boot_id="boot2", epoch=2,
            challenge_id="challenge2", config_revision=0, config_digest="",
            lease_ms=15000, grant_ms=10000)))
        await client.poll()
        assert not client.ready and client.session is None
        client.send.assert_not_awaited()
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_forward_and_equal_clock_preserve_original_retry_deadlines(hass):
    _, runtime, client, now = await system(hass)
    try:
        assert client.ready and client.ready
        await client.message("ha/heartbeat", "adapter", {})
        original = client.send.await_args
        now[0] = 102
        await client.poll()
        assert client.ready
        assert client.send.await_args == original
        pending = next(iter(client.pending.values()))
        assert pending["sent"] == 100 and pending["deadline"] == 110
        assert pending["tries"] == 2
    finally:
        await runtime.async_stop()
