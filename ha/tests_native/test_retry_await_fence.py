"""Publish awaits may consume a budget or retire the original queue owner."""
import pytest
from homeassistant.exceptions import HomeAssistantError
from test_modern_metrics import system


@pytest.mark.asyncio
@pytest.mark.parametrize('after_send', [108, 110, 115])
async def test_retry_checks_original_expiry_again_after_prior_publish(hass, after_send):
    _, runtime, client, now = await system(hass)
    future = hass.loop.create_future()
    try:
        await client.message('ha/heartbeat', 'adapter', {})
        await client.message('ha/user_command', 'room1', {'mode': 'off'}, future)
        original = list(client.pending.values())
        client.send.reset_mock()
        async def delayed_publish(*_):
            now[0] = after_send
        client.send.side_effect = delayed_publish
        now[0] = 102
        await client.poll()
        assert client.send.await_count == 1
        assert client.send.await_args.args == (original[0]['topic'], original[0]['raw'])
        assert future.done()
        if after_send >= 115:
            assert future.cancelled() # Retired session cancels every owned waiter.
        else:
            with pytest.raises(HomeAssistantError, match='effect unknown'):
                future.result()
        assert original[1]['tries'] == 1
        assert original[1]['sent'] == 100 and original[1]['deadline'] == 110
        if after_send >= 115:
            assert client.session is None
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['close', 'disconnect', 'ack', 'replacement', 'source_drift', 'clock_reversal'])
async def test_retry_snapshot_does_not_own_retired_or_replaced_commands(hass, mutation):
    _, runtime, client, now = await system(hass)
    try:
        await client.message('ha/heartbeat', 'adapter', {})
        await client.message('ha/user_command', 'room1', {'mode': 'off'})
        key, original = next((k,v) for k,v in client.pending.items() if k[1]=='room1')
        client.send.reset_mock()
        async def first_publish(*_):
            if mutation == 'close':
                await client.async_close()
            elif mutation == 'disconnect':
                await client.async_disconnected()
            elif mutation == 'ack':
                client.pending.pop(key)
            elif mutation == 'source_drift':
                client.native_plan_source = object()
                client.native_source_current = lambda: False
            elif mutation == 'clock_reversal':
                now[0] = 99
            else:
                # Same key does not make a replacement the original retry owner.
                client.pending[key] = dict(original, sent=102, last=102)
        client.send.side_effect = first_publish
        now[0] = 102
        await client.poll()
        assert client.send.await_count == 1
        assert original['tries'] == 1
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_forward_delay_keeps_original_bytes_and_deadline(hass):
    _, runtime, client, now = await system(hass)
    try:
        await client.message('ha/heartbeat', 'adapter', {})
        await client.message('ha/user_command', 'room1', {'mode': 'off'})
        original = list(client.pending.values())
        client.send.reset_mock()
        async def delayed_publish(*_):
            now[0] += .25
        client.send.side_effect = delayed_publish
        now[0] = 102
        await client.poll()
        assert client.send.await_count == 2
        assert client.send.await_args_list[1].args == (original[1]['topic'], original[1]['raw'])
        assert original[1]['last'] == 102.25
        assert all(item['sent']==100 and item['deadline']==110 for item in original)
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_heartbeat_publish_delay_rechecks_local_lease_before_return(hass):
    _, runtime, client, now = await system(hass)
    try:
        async def delayed_publish(*_):
            now[0] = 115
        client.send.side_effect = delayed_publish
        await client.poll()
        assert client.send.await_count == 1
        assert client.session is None and not client.pending
        assert not client.ready
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('expired', ['lease', 'last_rx'])
async def test_expired_session_cannot_retry_or_renew_heartbeat(hass, expired):
    _, runtime, client, now = await system(hass)
    try:
        # A fresh receiver grant alone cannot renew the separate local lease.
        client.grant_until = 130
        await client.message('ha/user_command', 'room1', {'mode': 'off'})
        now[0] = 102
        if expired == 'lease':
            client.lease_until = 102
        else:
            from custom_components.open_thermostat.v1_wire import RX_STALE_SECONDS
            client.last_rx = 102 - RX_STALE_SECONDS
        client.send.reset_mock()
        await client.poll()
        client.send.assert_not_awaited()
        assert client.session is None and not client.pending
    finally:
        await runtime.async_stop()
