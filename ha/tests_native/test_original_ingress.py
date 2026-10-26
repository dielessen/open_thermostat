"""Read-only bounded diagnostics on the actual existing receive worker."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.components import mqtt

from custom_components.open_thermostat.original_ingress import (
    OriginalIngressDiagnostics, MAX_COUNT, LANES, OUTCOMES)
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
from test_device_metadata import devices
from test_original_temperature import system, packet, TOPIC


def test_snapshot_is_bounded_detached_and_does_not_claim_device_or_control_evidence():
    counters = OriginalIngressDiagnostics()
    assert counters.record('temperature', 'callback')
    assert counters.record('tv02', 'worker_rejected')
    for lane, outcome in [('private topic/device', 'raw packet'), ([], 'callback'),
                          ('tv02', {}), ('tv02', 'secret error text')]:
        assert not counters.record(lane, outcome)
    snapshot = counters.snapshot()
    assert set(snapshot['lanes']) == set(LANES)
    assert all(set(row['counts']) == set(OUTCOMES) for row in snapshot['lanes'].values())
    assert not snapshot['per_device'] and not snapshot['persistent'] and not snapshot['control_qualified']
    assert 'private' not in json.dumps(snapshot) and 'secret' not in json.dumps(snapshot)
    snapshot['lanes']['tv02']['counts']['worker_rejected'] = 900
    assert counters.snapshot()['lanes']['tv02']['counts']['worker_rejected'] == 1
    assert OriginalIngressDiagnostics().snapshot()['lanes']['tv02']['counts']['worker_rejected'] == 0


def test_saturation_stays_bounded_and_explicit_instead_of_wrapping():
    counters = OriginalIngressDiagnostics()
    counters._counts['tv02']['callback'] = MAX_COUNT - 1
    counters._unrouted = MAX_COUNT - 1
    for _ in range(3):
        counters.record('tv02', 'callback')
        counters.unrouted()
    result = counters.snapshot()
    assert result['lanes']['tv02']['counts']['callback'] == MAX_COUNT
    assert result['lanes']['tv02']['saturated']
    assert result['unrouted_callbacks'] == MAX_COUNT and result['unrouted_saturated']


@pytest.mark.asyncio
async def test_actual_callback_worker_counts_export_privacy_and_lifetime(hass, devices, monkeypatch):
    runtime, binding, _, now = await system(hass, devices)
    subscriptions = {}
    async def subscribe(_hass, topic, callback, **kwargs):
        subscriptions[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, 'async_subscribe', subscribe)
    monkeypatch.setattr(mqtt, 'async_subscribe_connection_status', lambda _h, _cb: lambda: None)
    publish = AsyncMock()
    monkeypatch.setattr(mqtt, 'async_publish', publish)
    connection = NativeShadowConnection(runtime)
    from custom_components.open_thermostat import v1_mqtt
    try:
        await connection.async_start()
        monkeypatch.setattr(v1_mqtt.dt_util, 'utcnow', lambda: SimpleNamespace(timestamp=lambda: 10000))
        hass.data.setdefault('open_thermostat', {})[runtime.entry.entry_id] = {
            'v1_runtime': runtime, 'v1_connection': connection}
        original = subscriptions[TOPIC]
        def send(payload=None, retained=False, topic=TOPIC):
            original(SimpleNamespace(topic=topic,
                payload=json.dumps(packet()) if payload is None else payload, retain=retained))
        send()
        for _ in range(3): send()
        assert connection.queue.qsize() == 1
        await connection.queue.join()
        send(retained=True)
        send(b'x'*1025)
        send('{broken')
        await connection.queue.join()
        send()  # Replay, not another accepted observation.
        await connection.queue.join()
        send(topic='unrelated/private/device')
        with monkeypatch.context() as patch:
            patch.setattr(connection.original_reports, 'receive', Mock(side_effect=RuntimeError('private payload')))
            send(); await connection.queue.join()
        before = (connection.client.last_rx, connection.client.grant_until,
                  connection.client.lease_until, connection.client.error, publish.await_count)
        snapshot = connection.original_ingress_status()
        counters = snapshot['lanes']['temperature']['counts']
        assert counters == dict(callback=9, enqueued=4, dropped_closed=0, dropped_busy=3,
            dropped_retained=1, dropped_payload=1, dropped_queue_full=0, dropped_timestamp=0,
            worker_accepted=1, worker_rejected=2, worker_error=1)
        assert snapshot['unrouted_callbacks'] == 1
        assert snapshot['lanes']['temperature']['configured_topics'] == 1
        assert snapshot['lanes']['tv02']['configured_topics'] == 0
        public = await async_get_config_entry_diagnostics(hass, runtime.entry)
        assert public['read_only_original_ingress'] == dict(available=True, snapshot=snapshot, control_qualified=False)
        exported = json.dumps(public['read_only_original_ingress'])
        assert all(token not in exported for token in (TOPIC, '0x0000', 'private', binding.room_id))
        assert before == (connection.client.last_rx, connection.client.grant_until,
            connection.client.lease_until, connection.client.error, publish.await_count)
        assert not runtime.measurement_status(binding.room_id)['usable']
        assert not runtime._profiles
        await connection.async_close()
        send()
        closed = connection.original_ingress_status()
        assert closed['closed'] and closed['lanes']['temperature']['counts']['dropped_closed'] == 1
        replacement = NativeShadowConnection(runtime)
        assert replacement.original_ingress_status()['lanes']['temperature']['counts']['callback'] == 0
        await replacement.async_close()
    finally:
        await connection.async_close()
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_reserved_queue_timestamp_and_full_queue_drops_do_not_enqueue_or_reset_control(hass, devices, monkeypatch):
    runtime, _, _, now = await system(hass, devices)
    subscriptions = {}
    async def subscribe(_hass, topic, callback, **kwargs):
        subscriptions[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, 'async_subscribe', subscribe)
    monkeypatch.setattr(mqtt, 'async_subscribe_connection_status', lambda _h, _cb: lambda: None)
    monkeypatch.setattr(mqtt, 'async_publish', AsyncMock())
    connection = NativeShadowConnection(runtime)
    try:
        await connection.async_start()
        original = subscriptions[TOPIC]
        msg = SimpleNamespace(topic=TOPIC, payload=json.dumps(packet()), retain=False)
        before = (connection.client.last_rx, connection.client.grant_until, connection.client.error)
        for _ in range(32): connection.queue.put_nowait(('noop', None))
        original(msg)
        assert connection.queue.qsize() == 32 and not connection.original_pending
        await connection.queue.join()
        with monkeypatch.context() as patch:
            patch.setattr(runtime, 'clock', Mock(side_effect=RuntimeError('private clock error')))
            original(msg)
        assert connection.queue.empty() and not connection.original_pending
        import asyncio
        with monkeypatch.context() as patch:
            patch.setattr(connection.queue, 'put_nowait', Mock(side_effect=asyncio.QueueFull))
            original(msg)
        counters = connection.original_ingress_status()['lanes']['temperature']['counts']
        assert counters['dropped_busy'] == counters['dropped_timestamp'] == counters['dropped_queue_full'] == 1
        assert counters['enqueued'] == 0 and not connection.original_pending
        assert before == (connection.client.last_rx, connection.client.grant_until, connection.client.error)
    finally:
        await connection.async_close()
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_missing_or_wrong_connection_exports_unavailable_not_zero_traffic(hass, devices):
    runtime, _, _, _ = await system(hass, devices)
    try:
        state = {'v1_runtime': runtime}
        hass.data.setdefault('open_thermostat', {})[runtime.entry.entry_id] = state
        for connection in (None, SimpleNamespace(runtime=runtime)):
            state['v1_connection'] = connection
            result = await async_get_config_entry_diagnostics(hass, runtime.entry)
            assert result['read_only_original_ingress'] == dict(available=False, snapshot=None, control_qualified=False)
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_actual_selected_tv02_lane_is_distinct_and_never_an_ack(hass, devices, monkeypatch):
    from test_original_tv02_lifecycle import system as valve_system, TOPIC as VALVE_TOPIC
    from test_original_tv02 import packet as valve_packet
    from custom_components.open_thermostat import v1_mqtt
    runtime, room, source, now = await valve_system(hass, devices)
    subscriptions = {}
    async def subscribe(_hass, topic, callback, **kwargs):
        subscriptions[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, 'async_subscribe', subscribe)
    monkeypatch.setattr(mqtt, 'async_subscribe_connection_status', lambda _h, _cb: lambda: None)
    monkeypatch.setattr(mqtt, 'async_publish', AsyncMock())
    connection = NativeShadowConnection(runtime, tv02_sources=(source,))
    try:
        await connection.async_start()
        monkeypatch.setattr(v1_mqtt.dt_util, 'utcnow', lambda: SimpleNamespace(timestamp=lambda: 10000))
        original = subscriptions[VALVE_TOPIC]
        raw = json.dumps(valve_packet(device_ieee='0x0000000000000002'))
        original(SimpleNamespace(topic=VALVE_TOPIC, payload=raw, retain=True))
        original(SimpleNamespace(topic=VALVE_TOPIC, payload=raw, retain=False))
        await connection.queue.join()
        original(SimpleNamespace(topic=VALVE_TOPIC, payload=raw, retain=False))
        await connection.queue.join()
        snapshot = connection.original_ingress_status()
        counts = snapshot['lanes']['tv02']['counts']
        assert counts['callback'] == 3 and counts['enqueued'] == 2
        assert counts['worker_accepted'] == counts['worker_rejected'] == counts['dropped_retained'] == 1
        assert not any(snapshot['lanes']['temperature']['counts'].values())
        assert snapshot['lanes']['tv02']['configured_topics'] == 1
        status = runtime.actuator_report_status(room.room_id)[source.reference.entity_id]
        assert status['status'] == 'received_unqualified'
        assert all(status[key] is False for key in ('command_correlated', 'control_qualified', 'valve_ready'))
        assert not runtime._profiles and runtime._bench_owner is None
    finally:
        await connection.async_close()
        await runtime.async_stop()
