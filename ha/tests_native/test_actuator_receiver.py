"""Prepared receiver contract on real native HA registries/services; no hardware."""
import asyncio
from dataclasses import asdict, replace
import json

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.open_thermostat.actuator_receiver import ActuatorReceiver, ActuatorScope
from custom_components.open_thermostat.v1_profile_c import ProfileCActuator
from test_actuator_clock_lifetime import LocalClockHass
from test_v1_native import room


def setup(hass, *, qualified=True, authorize=None):
    binding = room(hass)
    clock = [hass.loop.time()]
    proxy = LocalClockHass(hass, clock)
    calls = []
    hass.services.async_register('climate', 'set_temperature', lambda call: calls.append(call.data))
    adapter = ProfileCActuator(proxy, binding.actuators[0].entity_id,
                               qualified_profile=True, authorize=lambda: True)
    scope = ActuatorScope('ctrl', 'boot', 1, 'ha', 'session', 4, 'a'*64, 'valve')
    receiver = ActuatorReceiver(adapter, scope, qualified_profile=qualified,
                                authorize=authorize or (lambda: True))
    return receiver, scope, clock, calls


def intent(grant, sequence=1, **changes):
    value = {k: v for k, v in grant.items() if k != 'grant_ms'}
    value.update(sequence=sequence, target_centi_c=2100)
    value.update(changes)
    return json.dumps(value, separators=(',', ':'))


@pytest.mark.asyncio
@pytest.mark.parametrize('origin', [None, 123.456])
async def test_grant_reads_and_command_receipt_cannot_renew_original_window(hass, origin):
    receiver, scope, clock, calls = setup(hass)
    if origin is not None:
        clock[0] = origin
    issued_at = clock[0]
    grant = receiver.issue(scope=scope)
    clock[0] = issued_at + 4.9
    assert receiver.issue(scope=scope) == grant
    # Two fractional increments can land one ULP BEFORE the expiry. Test the
    # exact contract boundary from its original anchor, not elapsed addition.
    clock[0] = issued_at + 5.0
    with pytest.raises(HomeAssistantError, match='expired'):
        await receiver.async_receive(intent(grant), scope=scope)
    assert calls == []
    # Native asyncio.timeout_at uses the real loop epoch. The artificial
    # rounding origin above is admission-only; align forward before real IO.
    clock[0] = max(clock[0], hass.loop.time())
    fresh = receiver.issue(scope=scope)
    assert fresh['grant_id'] != grant['grant_id'] and fresh['grant_sequence'] == 2
    receipt = await receiver.async_receive(intent(fresh), scope=scope)
    assert receipt.status == 'ha_action_accepted' and receipt.scope == 'service_acceptance_only'
    assert not receipt.device_reported and not receipt.valve_ready and not receipt.control_qualified
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['default', 'profile', 'authorization', 'adapter'])
async def test_source_and_adapter_both_default_closed(hass, kind):
    receiver, scope, _, calls = setup(hass, qualified=kind != 'profile', authorize=lambda: kind != 'authorization')
    if kind == 'default':
        fresh_adapter = ProfileCActuator(receiver._adapter.hass, receiver._adapter.entity_id)
        receiver = ActuatorReceiver(fresh_adapter, scope)
    if kind == 'adapter':
        receiver._adapter._qualified = False
        grant = receiver.issue(scope=scope)
        with pytest.raises(HomeAssistantError):
            await receiver.async_receive(intent(grant), scope=scope)
    else:
        with pytest.raises(HomeAssistantError):
            receiver.issue(scope=scope)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [
    ('api', True), ('controller_id', 'other'), ('boot_id', 'other'), ('epoch', True),
    ('adapter_id', 'other'), ('adapter_session_id', 'other'), ('config_revision', True),
    ('config_digest', 'b'*64), ('binding_id', 'other'), ('command_kind', 'open'),
    ('grant_id', 'other'), ('grant_sequence', True), ('sequence', True),
    ('sequence', 0), ('sequence', 4294967296), ('target_centi_c', True),
    ('target_centi_c', 499), ('target_centi_c', 3501), ('extra', 1),
])
async def test_wire_identity_types_and_grant_must_match_exactly(hass, field, value):
    receiver, scope, _, calls = setup(hass)
    grant = receiver.issue(scope=scope)
    with pytest.raises(HomeAssistantError):
        await receiver.async_receive(intent(grant, **{field: value}), scope=scope)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', ['x'*2049, '{"api":1,"api":1}', '{"x":NaN}', '{"x":"\\u0061"}', '[{}]', '{"x":'+ '['*20+'0'+']'*20+'}'])
async def test_bounded_parser_rejects_malformed_payload_without_dispatch(hass, raw):
    receiver, scope, _, calls = setup(hass)
    receiver.issue(scope=scope)
    with pytest.raises(HomeAssistantError):
        await receiver.async_receive(raw, scope=scope)
    assert calls == []


@pytest.mark.asyncio
async def test_retained_and_previous_grant_cannot_dispatch(hass):
    receiver, scope, clock, calls = setup(hass)
    grant = receiver.issue(scope=scope)
    with pytest.raises(HomeAssistantError, match='Retained'):
        await receiver.async_receive(intent(grant), scope=scope, retained=True)
    clock[0] += 5.1
    receiver.issue(scope=scope)
    with pytest.raises(HomeAssistantError):
        await receiver.async_receive(intent(grant), scope=scope)
    assert calls == []


@pytest.mark.asyncio
async def test_consumed_grant_cannot_admit_a_second_new_command(hass):
    receiver, scope, _, calls = setup(hass)
    grant = receiver.issue(scope=scope)
    raw = intent(grant)
    await receiver.async_receive(raw, scope=scope)
    with pytest.raises(HomeAssistantError, match='consumed'):
        await receiver.async_receive(intent(grant, 2), scope=scope)
    assert len(calls) == 1
    assert (await receiver.async_receive(raw, scope=scope)).duplicate
    fresh = receiver.issue(scope=scope)
    assert fresh['grant_sequence'] == grant['grant_sequence'] + 1
    assert fresh['grant_id'] != grant['grant_id']
    await receiver.async_receive(intent(fresh, 2), scope=scope)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_historical_duplicate_never_redispatches_after_grant_expiry(hass):
    receiver, scope, clock, calls = setup(hass)
    grant = receiver.issue(scope=scope)
    raw = intent(grant)
    result = await receiver.async_receive(raw, scope=scope)
    clock[0] += 6
    repeated = await receiver.async_receive(raw, scope=scope)
    assert repeated == replace(result, duplicate=True) and len(calls) == 1
    fresh = receiver.issue(scope=scope)
    with pytest.raises(HomeAssistantError, match='payload changed'):
        await receiver.async_receive(intent(fresh), scope=scope)
    await receiver.async_receive(intent(fresh, 2), scope=scope)
    with pytest.raises(HomeAssistantError, match='high-water'):
        await receiver.async_receive(raw, scope=scope)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_pending_duplicate_shares_original_and_new_targets_are_not_queued(hass):
    receiver, scope, _, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        started.set()
        await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    raw = intent(receiver.issue(scope=scope))
    first = asyncio.create_task(receiver.async_receive(raw, scope=scope))
    await started.wait()
    duplicate = asyncio.create_task(receiver.async_receive(raw, scope=scope))
    await asyncio.sleep(0)
    with pytest.raises(HomeAssistantError, match='pending'):
        await receiver.async_receive(intent(receiver.issue(scope=scope), 2), scope=scope)
    duplicate.cancel()
    await asyncio.gather(duplicate, return_exceptions=True)
    assert not first.done() and len(calls) == 1
    release.set()
    await first
    assert (await receiver.async_receive(raw, scope=scope)).duplicate
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('changed', ['boot_id', 'adapter_session_id', 'config_revision', 'binding_id', 'epoch'])
async def test_changed_local_owner_is_permanently_retired(hass, changed):
    receiver, scope, _, calls = setup(hass)
    grant = receiver.issue(scope=scope)
    value = 5 if changed in ('config_revision', 'epoch') else 'replacement'
    with pytest.raises(HomeAssistantError, match='owner changed'):
        await receiver.async_receive(intent(grant), scope=replace(scope, **{changed:value}))
    with pytest.raises(HomeAssistantError, match='retired'):
        receiver.issue(scope=scope)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['backward', float('nan'), float('inf'), True, 10**400])
async def test_invalid_clock_cannot_revive_by_restoring_time(hass, bad):
    receiver, scope, clock, calls = setup(hass)
    receiver.issue(scope=scope)
    original = clock[0]
    clock[0] = original - 1 if bad == 'backward' else bad
    with pytest.raises(HomeAssistantError, match='clock'):
        receiver.issue(scope=scope)
    clock[0] = original + .01
    with pytest.raises(HomeAssistantError, match='retired'):
        receiver.issue(scope=scope)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('loss', ['authority', 'clock', 'deadline', 'service_error'])
async def test_inflight_loss_retires_owner_without_retry(hass, loss):
    authorized = [True]
    receiver, scope, clock, calls = setup(hass, authorize=lambda: authorized[0])
    def handler(call):
        calls.append(call.data)
        if loss == 'authority': authorized[0] = False
        elif loss == 'clock': clock[0] -= 1
        elif loss == 'deadline': clock[0] += 5
        else: raise HomeAssistantError('synthetic failure')
    hass.services.async_register('climate', 'set_temperature', handler)
    raw = intent(receiver.issue(scope=scope))
    with pytest.raises(HomeAssistantError):
        await receiver.async_receive(raw, scope=scope)
    authorized[0] = True
    clock[0] += 2
    with pytest.raises(HomeAssistantError, match='retired'):
        await receiver.async_receive(raw, scope=scope)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_callback_delay_cannot_create_a_new_budget_at_dispatch(hass):
    receiver, scope, clock, calls = setup(hass)
    grant = receiver.issue(scope=scope)
    count = 0
    def authorize():
        nonlocal count
        count += 1
        if count == 2: clock[0] += 5
        return True
    receiver._authorize = authorize
    with pytest.raises(HomeAssistantError, match='expired before dispatch'):
        await receiver.async_receive(intent(grant), scope=scope)
    assert calls == []


@pytest.mark.asyncio
async def test_cancelled_inflight_owner_is_never_replayed(hass):
    receiver, scope, _, calls = setup(hass)
    started, release = asyncio.Event(), asyncio.Event()
    async def handler(call):
        calls.append(call.data)
        started.set()
        await release.wait()
    hass.services.async_register('climate', 'set_temperature', handler)
    raw = intent(receiver.issue(scope=scope))
    task = asyncio.create_task(receiver.async_receive(raw, scope=scope))
    await started.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    release.set()
    with pytest.raises(HomeAssistantError, match='retired'):
        await receiver.async_receive(raw, scope=scope)
    assert len(calls) == 1 and receiver._adapter._outcome_unknown


@pytest.mark.asyncio
async def test_grant_nonce_collision_does_not_repeat_identity_or_wrap(hass, monkeypatch):
    receiver, scope, clock, calls = setup(hass)
    monkeypatch.setattr('custom_components.open_thermostat.actuator_receiver.secrets.token_hex', lambda _: 'a'*20)
    grant = receiver.issue(scope=scope)
    clock[0] += 6
    fresh = receiver.issue(scope=scope)
    assert fresh['grant_id'] != grant['grant_id']
    receiver._grant_sequence = 4294967295
    clock[0] += 6
    with pytest.raises(HomeAssistantError, match='exhausted'):
        receiver.issue(scope=scope)
    with pytest.raises(HomeAssistantError, match='retired'):
        receiver.issue(scope=scope)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['issue', 'dispatch', 'completion'])
async def test_synchronous_owner_retirement_cannot_be_hidden_by_true_callback(hass, boundary):
    receiver, scope, _, calls = setup(hass)
    checks = 0
    def authorize():
        nonlocal checks
        checks += 1
        at = {'issue': 1, 'dispatch': 3, 'completion': 4}[boundary]
        if checks == at: receiver.retire()
        return True
    receiver._authorize = authorize
    if boundary == 'issue':
        with pytest.raises(HomeAssistantError):
            receiver.issue(scope=scope)
    else:
        grant = receiver.issue(scope=scope)
        with pytest.raises(HomeAssistantError):
            await receiver.async_receive(intent(grant), scope=scope)
    assert len(calls) == (1 if boundary == 'completion' else 0)


@pytest.mark.asyncio
async def test_new_receiver_cannot_reuse_the_same_admitted_adapter(hass):
    receiver, scope, _, calls = setup(hass)
    receiver.retire()
    with pytest.raises(ValueError, match='already'):
        ActuatorReceiver(receiver._adapter, scope, qualified_profile=True, authorize=lambda: True)
    assert calls == []
