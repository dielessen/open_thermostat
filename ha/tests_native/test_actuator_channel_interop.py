"""Actual C++ request -> existing HA wire -> C++ command -> guarded service.

Finite pipes with synthetic qualified local sources. No broker or device IO.
"""
import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path

import pytest

from custom_components.open_thermostat.actuator_wire import REQUEST, COMMAND
from custom_components.open_thermostat.v1_wire import canonical
from test_actuator_wire import fixture
from test_source_entry_composed import composed


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['normal', 'expired', 'offline', 'retained', 'wrong_request'])
async def test_cpp_owns_original_request_and_checks_actual_wire_reply(hass, mode):
    wire, receiver, scope, clock, calls, pubs, _, _ = fixture(hass)
    runner = Path(os.environ.get('OPENTHERMOSTAT_ACTUATOR_CHANNEL_RUNNER',
        Path(__file__).resolve().parents[2] / 'out/actuator-channel-runner'))
    assert runner.is_file(), 'Build exact-source actuator-channel-runner first'
    process = await asyncio.create_subprocess_exec(str(runner), mode,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)
    try:
        process.stdin.write((canonical(asdict(scope))+'\n').encode())
        await process.stdin.drain()
        request_raw = (await asyncio.wait_for(process.stdout.readline(), 5)).decode().strip()
        assert json.loads(request_raw)['request_sequence'] == 1
        await wire.receive(REQUEST+scope.binding_id, request_raw, received_at=clock[0])
        topic, grant = pubs.pop()
        assert topic == 'ha/actuator_grant/'+scope.binding_id
        assert grant['request_sequence'] == 1
        deadline = receiver.grant_deadline
        await wire.receive(REQUEST+scope.binding_id, request_raw, received_at=clock[0])
        assert pubs.pop()[1] == grant and receiver.grant_deadline == deadline
        process.stdin.write((canonical(grant)+'\n').encode())
        await process.stdin.drain()
        result = json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
        process.stdin.close()
        assert await asyncio.wait_for(process.wait(), 5) == 0
        assert (await process.stderr.read()) == b''
        if mode == 'normal':
            assert result['accepted'] and result['handoffs'] == 2 and result['deadline'] == 6000
            await wire.receive(COMMAND+scope.binding_id, result['command'], received_at=clock[0])
            _, receipt = pubs.pop()
            assert receipt['status'] == 'ha_action_accepted' and len(calls) == 1
            assert not any(receipt[k] for k in ('device_reported', 'valve_ready', 'control_qualified'))
            await wire.receive(COMMAND+scope.binding_id, result['command'], received_at=clock[0])
            assert pubs.pop()[1]['duplicate'] and len(calls) == 1
        else:
            assert not result['accepted'] and result['command'] == '' and result['handoffs'] == 1
            assert not calls
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.asyncio
@pytest.mark.parametrize('disconnect', [False, True])
async def test_whole_cpp_request_roundtrip_uses_existing_native_worker(composed, hass, disconnect):
    from types import SimpleNamespace
    from custom_components.open_thermostat.actuator_receiver import ActuatorReceiver
    from custom_components.open_thermostat.v1_profile_c import ProfileCActuator
    from test_actuator_clock_lifetime import LocalClockHass

    n = composed
    worker, session = n.native.worker, dict(n.client.session)
    binding = n.client.desired[0]['actuator_id']
    scope = n.client.actuator_scope(binding)
    room_id = n.client.desired[0]['zone_id']
    entity = next(row for row in n.bindings if row.room_id == room_id).actuators[0].entity_id
    clock, calls = [n.client.clock()], []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    def factory(local):
        adapter = ProfileCActuator(LocalClockHass(hass, clock), entity,
            qualified_profile=True, authorize=lambda: True)
        return ActuatorReceiver(adapter, local, qualified_profile=True, authorize=lambda: True)
    n.native.actuator_wire._factory = factory  # Synthetic local qualification ONLY.
    async def deliver(topic, raw):
        n.callbacks['message'](SimpleNamespace(topic=n.native.prefix+topic, payload=raw, retain=False))
        await n.native.queue.join()
    runner = Path(os.environ.get('OPENTHERMOSTAT_ACTUATOR_CHANNEL_RUNNER',
        Path(__file__).resolve().parents[2] / 'out/actuator-channel-runner'))
    process = await asyncio.create_subprocess_exec(str(runner),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        process.stdin.write((canonical(asdict(scope))+'\n').encode())
        await process.stdin.drain()
        request_raw = (await asyncio.wait_for(process.stdout.readline(), 5)).decode().strip()
        await deliver(REQUEST+binding, request_raw)
        topic, grant_raw = n.publications.pop()
        assert topic == 'ha/actuator_grant/'+binding
        assert json.loads(grant_raw)['request_sequence'] == 1
        process.stdin.write((grant_raw+'\n').encode())
        await process.stdin.drain()
        result = json.loads(await asyncio.wait_for(process.stdout.readline(), 5))
        process.stdin.close()
        assert await asyncio.wait_for(process.wait(), 5) == 0
        assert await process.stderr.read() == b''
        assert result['accepted'] and result['handoffs'] == 2
        if disconnect:
            n.callbacks['status'](False)
            await n.native.queue.join()
        await deliver(COMMAND+binding, result['command'])
        if disconnect:
            assert calls == [] and n.native.actuator_wire._closed
        else:
            topic, raw = n.publications.pop()
            receipt = json.loads(raw)
            assert topic == 'ha/actuator_result/'+binding and receipt['status'] == 'ha_action_accepted'
            assert not any(receipt[k] for k in ('device_reported', 'valve_ready', 'control_qualified'))
            assert len(calls) == 1 and calls[0]['entity_id'] == entity
            await deliver(COMMAND+binding, result['command'])
            assert json.loads(n.publications.pop()[1])['duplicate'] and len(calls) == 1
            assert n.client.ready and n.client.session == session and n.native.worker is worker
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
