"""A configuration the E32 cannot save is not rewritten every few seconds (HA 0.4.0b12).

On a storage_fault result HA resets the session; the next hello reopens it and
the snapshot proposes ha/config again. With a flash save that keeps failing that
was an endless 15-30 s write loop. Now the same configuration waits 1, 5, 15,
then 60 minutes; a changed configuration may go out at once, once.
"""
import logging

import pytest

from custom_components.open_thermostat.v1_wire import CONFIG_FAULT_BACKOFF, canonical
from test_modern_metrics import system


def reopen(c, now):
    """The next hello and session after the reset (the firmware's side is not under test)."""
    c.session = {"adapter_session_id": "session1", "grant_id": "grant1", "grant_sequence": 1,
                 "config_revision": 1, "config_digest": "a" * 64, "mapping_ready": True}
    c.identity = ("e32_lab", "boot1", 1)
    c.grant_until, c.lease_until, c.last_rx = now[0] + 10, now[0] + 15, now[0]


def configs(c):
    return [call for call in c.send.await_args_list if call.args[0] == "ha/config"]


async def fault(c):
    sequence = c.sequence["config"]
    await c.receive("fw/config_result", canonical({
        "api": 1, "controller_id": "e32_lab", "boot_id": "boot1", "epoch": 1, "config_revision": 1,
        "config_digest": "a" * 64, "adapter_id": "ha1", "adapter_session_id": "session1",
        "binding_id": "config", "sequence": sequence, "status": "storage_fault"}))


@pytest.mark.asyncio
async def test_repeated_storage_faults_back_off_instead_of_a_write_loop(hass, caplog):
    e, r, c, now = await system(hass)
    assert CONFIG_FAULT_BACKOFF == (60, 300, 900, 3600)
    with caplog.at_level(logging.WARNING):
        await c.propose(0)
        assert len(configs(c)) == 1
        await fault(c)
        assert c.session is None  # session handling unchanged: reset, then a new hello
        # The E32 reopens every 15-30 s and HA would propose again each time: now it waits.
        for _ in range(3):  # 45 s of reopening
            now[0] += 15
            reopen(c, now)
            await c.propose(0)
        assert len(configs(c)) == 1 and c.error == "firmware_storage_fault"
        now[0] += 15  # one minute after the fault
        reopen(c, now)
        await c.propose(0)
        assert len(configs(c)) == 2
        await fault(c)
        for _ in range(10):  # the second fault: five minutes
            now[0] += 25
            reopen(c, now)
            await c.propose(0)
        assert len(configs(c)) == 2
        now[0] += 60
        reopen(c, now)
        await c.propose(0)
        assert len(configs(c)) == 3
    assert caplog.text.count("could not save the Home Assistant configuration") == 1  # warned once
    await r.async_stop()


@pytest.mark.asyncio
async def test_a_changed_configuration_goes_out_at_once_but_only_once(hass):
    e, r, c, now = await system(hass)
    await c.propose(0)
    await fault(c)
    now[0] += 10
    reopen(c, now)
    c.mapping = {"changed": 1}  # the user changed something: one immediate attempt
    await c.propose(0)
    assert len(configs(c)) == 2
    now[0] += 10
    reopen(c, now)
    c.mapping = {"changed": 2}  # another change during the backoff waits
    await c.propose(0)
    assert len(configs(c)) == 2
    await r.async_stop()


@pytest.mark.asyncio
async def test_a_saved_configuration_ends_the_backoff(hass):
    e, r, c, now = await system(hass)
    await c.propose(0)
    await fault(c)
    now[0] += 60
    reopen(c, now)
    await c.propose(0)
    sequence = c.sequence["config"]
    await c.receive("fw/config_result", canonical({
        "api": 1, "controller_id": "e32_lab", "boot_id": "boot1", "epoch": 1, "config_revision": 1,
        "config_digest": "a" * 64, "adapter_id": "ha1", "adapter_session_id": "session1",
        "binding_id": "config", "sequence": sequence, "status": "accepted"}))
    assert c._config_fault is None
    await c.propose(0)
    assert len(configs(c)) == 3
    await r.async_stop()
