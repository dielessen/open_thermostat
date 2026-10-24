"""Existing native worker + actual HA services; no physical device/network IO."""
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat.actuator_wire import ActuatorWire, REQUEST, COMMAND
from custom_components.open_thermostat.v1_wire import canonical
from test_actuator_receiver import setup, intent
from test_source_entry_composed import composed


def request(scope, sequence=1, **changes):
    return canonical(dict(api=1, **asdict(scope), command_kind='room_target',
                          request_sequence=sequence, **changes))


def fixture(hass):
    receiver, scope, clock, calls = setup(hass)
    publications, factories = [], []
    client = SimpleNamespace(clock=lambda: clock[0], lease_until=clock[0]+15,
        grant_until=clock[0]+10, actuator_scope=lambda binding: scope if binding == scope.binding_id else None)
    async def publish(topic, raw):
        publications.append((topic, json.loads(raw)))
    connection = SimpleNamespace(client=client, closed=False, publish=publish)
    def factory(local):
        factories.append(local)
        return receiver
    wire = ActuatorWire(connection, factory)
    return wire, receiver, scope, clock, calls, publications, factories, client


@pytest.mark.asyncio
async def test_request_duplicate_preserves_grant_deadline_and_command_calls_once(hass):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    arrived = clock[0]
    await w.receive(REQUEST+s.binding_id, request(s), received_at=arrived)
    grant = pubs[-1][1]
    deadline = r.grant_deadline
    clock[0] += 1
    await w.receive(REQUEST+s.binding_id, request(s), received_at=clock[0])
    assert pubs[-1][1] == grant and r.grant_deadline == deadline
    await w.receive(COMMAND+s.binding_id, intent(grant), received_at=clock[0])
    assert len(calls) == 1 and len(factories) == 1
    receipt = pubs[-1][1]
    assert receipt['status'] == 'ha_action_accepted'
    assert receipt['scope'] == 'service_acceptance_only'
    assert not any(receipt[k] for k in ('device_reported', 'valve_ready', 'control_qualified'))
    await w.receive(COMMAND+s.binding_id, intent(grant), received_at=clock[0])
    assert len(calls) == 1 and pubs[-1][1]['duplicate']
    clock[0] = deadline
    count = len(pubs)
    await w.receive(REQUEST+s.binding_id, request(s), received_at=clock[0])
    assert len(pubs) == count and r.grant_deadline == deadline


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['retained', 'oversize', 'scope', 'binding', 'expired', 'future', 'boolean'])
async def test_invalid_request_never_calls_factory_or_publishes(hass, bad):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    raw, binding, arrival = request(s), s.binding_id, clock[0]
    if bad == 'oversize': raw = 'x'*2049
    elif bad == 'scope': raw = raw.replace('"boot"', '"other"')
    elif bad == 'binding': binding = 'unknown'
    elif bad == 'expired': arrival -= 5
    elif bad == 'future': arrival += 1
    elif bad == 'boolean': raw = request(s, True)
    await w.receive(REQUEST+binding, raw, retained=bad == 'retained', received_at=arrival)
    assert not calls and not pubs and not factories


@pytest.mark.asyncio
async def test_queue_age_and_current_lease_narrow_original_receiver_deadline(hass):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    arrival = clock[0]
    clock[0] += 2
    client.lease_until = arrival+3
    await w.receive(REQUEST+s.binding_id, request(s), received_at=arrival)
    assert r.grant_deadline == arrival+3
    grant = pubs[-1][1]
    clock[0] = arrival+3
    await w.receive(COMMAND+s.binding_id, intent(grant), received_at=clock[0])
    assert not calls


@pytest.mark.asyncio
async def test_session_loss_while_waiting_for_existing_service_lock_cannot_send(hass):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    await w.receive(REQUEST+s.binding_id, request(s), received_at=clock[0])
    grant = pubs[-1][1]
    await r._adapter._lock.acquire()
    task = asyncio.create_task(w.receive(COMMAND+s.binding_id, intent(grant), received_at=clock[0]))
    try:
        await asyncio.sleep(0)
        client.actuator_scope = lambda binding: None
        r._adapter._lock.release()
        await task
        assert not calls and len(pubs) == 1
        client.actuator_scope = lambda binding: s
        await w.receive(COMMAND+s.binding_id, intent(grant, 2), received_at=clock[0])
        assert not calls and len(factories) == 1
    finally:
        if r._adapter._lock.locked(): r._adapter._lock.release()
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_disconnect_and_close_retire_without_recreating_owner(hass):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    await w.receive(REQUEST+s.binding_id, request(s), received_at=clock[0])
    w.retire()
    await w.receive(REQUEST+s.binding_id, request(s, 2), received_at=clock[0])
    assert len(factories) == 1 and len(pubs) == 1 and not calls


@pytest.mark.asyncio
async def test_initial_transport_status_without_an_owner_does_not_select_or_revive_authority(hass):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    w.transport_lost()
    assert not factories and not pubs and not calls
    await w.receive(REQUEST+s.binding_id, request(s), received_at=clock[0])
    assert len(factories) == 1 and len(pubs) == 1 and not calls
    w.transport_lost()
    await w.receive(REQUEST+s.binding_id, request(s, 2), received_at=clock[0])
    assert len(factories) == 1 and len(pubs) == 1 and not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [float('nan'), float('inf'), True, -1, 10**400])
async def test_clock_failure_cannot_revive_route_by_restoring_time(hass, bad):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    original = clock[0]
    clock[0] = bad
    await w.receive(REQUEST+s.binding_id, request(s), received_at=original)
    clock[0] = original
    await w.receive(REQUEST+s.binding_id, request(s), received_at=original)
    assert not factories and not pubs and not calls


@pytest.mark.asyncio
async def test_failing_local_factory_is_not_automatically_retried(hass):
    w, r, s, clock, calls, pubs, factories, client = fixture(hass)
    def failed(scope):
        factories.append(scope)
        raise ValueError('local profile unavailable')
    w._factory = failed
    for _ in range(2):
        await w.receive(REQUEST+s.binding_id, request(s), received_at=clock[0])
    assert len(factories) == 1 and not pubs and not calls


@pytest.mark.asyncio
async def test_default_native_worker_ignores_actuator_messages_without_shadow_reset(composed):
    n = composed
    assert n.client.ready
    binding = n.client.desired[0]['actuator_id']
    scope = n.client.actuator_scope(binding)
    assert scope is not None and n.client.actuator_scope('unknown') is None
    session = dict(n.client.session)
    before = n.client.last_rx
    worker = n.native.worker
    for topic, raw in [(REQUEST+binding, request(scope)), (COMMAND+binding, '{"api":1}'),
                       (REQUEST[:-1], '{}'), (COMMAND[:-1], '{}')]:
        n.callbacks['message'](SimpleNamespace(topic=n.native.prefix+topic, payload=raw, retain=False))
        await n.native.queue.join()
    assert n.client.ready and n.client.session == session and n.client.last_rx == before
    assert n.native.worker is worker and not n.services
    assert not any('actuator' in topic for topic, _ in n.publications)


@pytest.mark.asyncio
async def test_actual_worker_delivers_grant_and_command_with_synthetic_local_factory(composed, hass):
    n = composed
    binding = n.client.desired[0]['actuator_id']
    scope = n.client.actuator_scope(binding)
    from custom_components.open_thermostat.actuator_receiver import ActuatorReceiver
    from custom_components.open_thermostat.v1_profile_c import ProfileCActuator
    from test_actuator_clock_lifetime import LocalClockHass
    clock = [n.client.clock()]
    calls = []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    room_id = n.client.desired[0]['zone_id']
    entity = next(row for row in n.bindings if row.room_id == room_id).actuators[0].entity_id
    def factory(local):
        adapter = ProfileCActuator(LocalClockHass(hass, clock), entity,
                                  qualified_profile=True, authorize=lambda: True)
        return ActuatorReceiver(adapter, local, qualified_profile=True, authorize=lambda: True)
    # Explicit SOURCE fixture only. The normal product constructor supplies None.
    n.native.actuator_wire._factory = factory
    async def deliver(topic, raw):
        n.callbacks['message'](SimpleNamespace(topic=n.native.prefix+topic, payload=raw, retain=False))
        await n.native.queue.join()
    await deliver(REQUEST+binding, request(scope))
    topic, raw = n.publications.pop()
    assert topic == 'ha/actuator_grant/'+binding
    grant = json.loads(raw)
    deadline = n.native.actuator_wire._owners[binding]['receiver'].grant_deadline
    hello = next(raw for who, topic, raw in reversed(n.bus.transcript)
                 if who == 'fw' and topic == 'fw/hello')
    await deliver('fw/hello', hello)
    assert n.native.actuator_wire.accepting and n.client.ready
    assert n.native.actuator_wire._owners[binding]['receiver'].grant_deadline == deadline
    runner = Path(os.environ.get('OPENTHERMOSTAT_ACTUATOR_INTENT_RUNNER',
        Path(__file__).resolve().parents[2] / 'out/actuator-intent-runner'))
    encoded = subprocess.run([str(runner), '--fixture-scope'], input=canonical(grant)+'\n',
        text=True, capture_output=True, timeout=5, check=True).stdout.strip()
    await deliver(COMMAND+binding, encoded)
    topic, raw = n.publications.pop()
    result = json.loads(raw)
    assert topic == 'ha/actuator_result/'+binding and result['status'] == 'ha_action_accepted'
    assert not result['valve_ready'] and not result['device_reported']
    assert len(calls) == 1
    assert calls[0]['entity_id'] == entity
    await deliver(COMMAND+binding, encoded)
    n.publications.pop()
    assert len(calls) == 1
    assert n.client.ready and not n.services
    n.callbacks['status'](False)
    await n.native.queue.join()
    assert not n.client.ready and n.native.actuator_wire._closed


@pytest.mark.asyncio
@pytest.mark.parametrize('loss', ['offline', 'new_boot'])
async def test_firmware_offline_fences_lock_waiter_before_worker_processes_offline(composed, hass, loss):
    n = composed
    binding = n.client.desired[0]['actuator_id']
    scope = n.client.actuator_scope(binding)
    from custom_components.open_thermostat.actuator_receiver import ActuatorReceiver
    from custom_components.open_thermostat.v1_profile_c import ProfileCActuator
    from test_actuator_clock_lifetime import LocalClockHass
    clock, calls = [n.client.clock()], []
    room_id = n.client.desired[0]['zone_id']
    entity = next(row for row in n.bindings if row.room_id == room_id).actuators[0].entity_id
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    def factory(local):
        adapter = ProfileCActuator(LocalClockHass(hass, clock), entity,
                                  qualified_profile=True, authorize=lambda: True)
        return ActuatorReceiver(adapter, local, qualified_profile=True, authorize=lambda: True)
    n.native.actuator_wire._factory = factory
    def deliver(topic, raw):
        n.callbacks['message'](SimpleNamespace(topic=n.native.prefix+topic, payload=raw, retain=False))
    deliver(REQUEST+binding, request(scope))
    await n.native.queue.join()
    _, raw = n.publications.pop()
    receiver = n.native.actuator_wire._owners[binding]['receiver']
    await receiver._adapter._lock.acquire()
    try:
        deliver(COMMAND+binding, intent(json.loads(raw)))
        for _ in range(20):
            if receiver._result is not None: break
            await asyncio.sleep(0)
        assert receiver._result is not None and not receiver._result.done()
        if loss == 'offline':
            deliver('fw/availability', 'offline')
        else:
            hello = next(json.loads(raw) for who, topic, raw in reversed(n.bus.transcript)
                         if who == 'fw' and topic == 'fw/hello')
            hello['boot_id'] = 'replacement_boot'
            deliver('fw/hello', canonical(hello))
        fenced_immediately = n.native.actuator_wire._closed
    finally:
        # Baseline reproduction also stops its synthetic waiter before release.
        n.native.actuator_wire.retire()
        receiver._adapter._lock.release()
        await n.native.queue.join()
    assert fenced_immediately, 'offline was queued behind an admitted service-lock waiter'
    assert not calls and not n.client.ready


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['disabled', 'retired', 'enabled_pressure'])
async def test_actuator_burst_does_not_overflow_or_reset_existing_shadow_worker(composed, mode):
    n = composed
    before, last_rx = dict(n.client.session), n.client.last_rx
    factories = []
    if mode != 'disabled':
        def factory(scope):
            factories.append(scope)
            raise AssertionError('burst must not dispatch deferred optional work')
        n.native.actuator_wire._factory = factory
        if mode == 'retired':n.native.actuator_wire.retire()
    # Ordinary worker work is already pending when optional traffic arrives.
    n.native.queue.put_nowait(('poll', None))
    for _ in range(100):
        n.callbacks['message'](SimpleNamespace(topic=n.native.prefix+REQUEST+'valve',
                                              payload='{}', retain=False))
    await n.native.queue.join()
    assert n.client.ready and n.client.session == before and n.client.last_rx == last_rx
    assert not factories and not n.services
    assert not any('actuator' in topic for topic, _ in n.publications)
