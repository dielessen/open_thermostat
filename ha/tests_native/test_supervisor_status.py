"""Read-only supervisor projection, actual C++ state and HA diagnostics lifecycle."""
import copy
import json

import pytest
from custom_components.open_thermostat.supervisor_status import supervisor_status, MAX_AGE_SECONDS
from custom_components.open_thermostat.v1_wire import canonical, LEASE_SECONDS
from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
from custom_components.open_thermostat.const import DOMAIN
from test_v1_wire_interop import integrated


def status(**changes):
    return dict(phase="heating", reason="shadow_heat_intent", requested_heat=True,
                physical_outputs_enabled=False, feedback_status="hydraulic_feedback_received",
                heat_intent=True, pump_intent=True, path_intent="request_qualified_path",
                opening_command=2, water_target_centi_c=4000, **changes)


@pytest.mark.parametrize("key,bad", [
    ("phase", []), ("phase", "running"), ("reason", 1), ("reason", "a"*65),
    ("requested_heat", 1), ("physical_outputs_enabled", True), ("physical_outputs_enabled", 0),
    ("feedback_status", []), ("feedback_status", "physical_ready"), ("heat_intent", 1),
    ("pump_intent", None), ("path_intent", []), ("path_intent", "open_valve"),
    ("opening_command", True), ("opening_command", -1), ("opening_command", 4294967296),
    ("water_target_centi_c", True), ("water_target_centi_c", 499), ("water_target_centi_c", 9001),
    ("water_target_centi_c", 4000.0),
])
def test_invalid_or_physical_claim_never_becomes_diagnostic(key, bad):
    value=status();value[key]=bad
    with pytest.raises(ValueError):supervisor_status(value)


@pytest.mark.parametrize("key", ["feedback_status", "heat_intent", "pump_intent", "path_intent", "opening_command", "water_target_centi_c"])
def test_partial_new_intent_group_is_not_accepted(key):
    value=status();del value[key]
    with pytest.raises(ValueError):supervisor_status(value)


def test_projection_is_flat_allowlist_never_infers_qualification_or_exports_unknown_text():
    value=status();value.update(reason="private-fixture", device="private-fixture", raw={"token":"private-fixture"})
    out=supervisor_status(value)
    assert "private-fixture" not in json.dumps(out)
    assert out["reason"]=="unknown_reason" and out["control_qualified"] is False
    assert out["scope"]=="reported_shadow_intent_only"
    value["opening_command"]=3
    assert out["opening_command"]==2
    value=status();value["phase"]="idle"
    with pytest.raises(ValueError):supervisor_status(value)


def frame(bus):
    return json.loads(next(raw for who, topic, raw in reversed(bus.transcript)
                          if who=="fw" and topic=="fw/state/zones"))


@pytest.mark.asyncio
async def test_actual_cpp_default_status_and_ha_diagnostic_are_read_only(integrated):
    runtime,client,bus,_=integrated
    await bus.start()
    out=client.supervisor_payload
    assert out["reason"]=="hydraulic_profile_unqualified"
    assert out["physical_outputs_enabled"] is False and out["control_qualified"] is False
    assert "heat_intent" not in out
    runtime.hass.data.setdefault(DOMAIN,{})[runtime.entry.entry_id]={"v1_runtime":runtime}
    diagnostic=await async_get_config_entry_diagnostics(runtime.hass,runtime.entry)
    assert diagnostic["read_only_supervisor"]["snapshot"]==out
    assert diagnostic["read_only_supervisor"]["control_qualified"] is False


@pytest.mark.asyncio
async def test_extended_intent_does_not_change_room_decision_or_emit_any_command(integrated):
    runtime,client,bus,_=integrated
    await bus.start();before=copy.deepcopy(runtime.decisions);sent=len(bus.transcript)
    wire=frame(bus);wire["supervisor"]=status()
    await client.receive("fw/state/zones",canonical(wire))
    out=client.supervisor_payload
    assert out["heat_intent"] is True and out["physical_outputs_enabled"] is False
    assert runtime.decisions==before and len(bus.transcript)==sent
    out["heat_intent"]=False
    assert client.supervisor_payload["heat_intent"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [None, {}, {"physical_outputs_enabled":True}])
async def test_missing_or_invalid_diagnostic_clears_old_intent_but_keeps_room_state(integrated,replacement):
    runtime,client,bus,_=integrated
    await bus.start();before=copy.deepcopy(runtime.decisions);wire=frame(bus)
    if replacement is None:wire.pop("supervisor")
    else:wire["supervisor"]=replacement
    await client.receive("fw/state/zones",canonical(wire))
    assert client.supervisor_payload is None and runtime.decisions==before and client.ready


@pytest.mark.asyncio
async def test_expiry_clock_reversal_disconnect_and_adapter_loss_hide_cached_intents(integrated):
    _,client,bus,_=integrated
    await bus.start();wire=frame(bus);start=bus.now
    bus.now+=MAX_AGE_SECONDS*1000-1;client.last_rx=bus.clock();client.grant_until=client.lease_until=bus.clock()+100
    assert client.supervisor_payload is not None
    bus.now+=1
    assert client.supervisor_payload is None
    # Exercise adapter loss/recovery while time still moves forwards.
    wire["adapter_alive"]=False
    await client.receive("fw/state/zones",canonical(wire))
    assert client.supervisor_payload is None
    await client.receive("fw/state/zones",canonical(frame(bus)))
    assert client.supervisor_payload is not None
    bus.now=start-1
    assert client.supervisor_payload is None and not client.ready
    bus.now=start+15001
    await client.receive("fw/state/zones",canonical(wire))
    assert client.session is None and client.supervisor_payload is None
    client.reset_session()
    assert client._supervisor is None and client.supervisor_payload is None


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign", ["retained", "config_revision", "clock_reversed"])
async def test_foreign_or_clock_invalid_state_cannot_replace_or_revive_status(integrated,foreign):
    _,client,bus,_=integrated
    await bus.start();wire=frame(bus);wire["supervisor"]=status()
    original=client.supervisor_payload
    if foreign=="clock_reversed":
        bus.now-=1
        assert client.supervisor_payload is None
        bus.now+=1
        assert client.supervisor_payload is None
    else:
        if foreign=="config_revision":wire["config_revision"]+=1
        await client.receive("fw/state/zones",canonical(wire),retained=foreign=="retained")
        assert client.supervisor_payload==original


def rejection_reply(client, sequence=1, reason='expired_grant'):
    return dict(api=1, controller_id='e32_lab', boot_id='boot1', epoch=1,
        config_revision=1, config_digest='a'*64, adapter_session_id='session1',
        binding_id='adapter', sequence=sequence, status='rejected', rejection_reason=reason)


def pending_rejection(client, now, sequence=1):
    client.pending[('fw/heartbeat_result', 'adapter', sequence)] = dict(
        sent=now, deadline=now+5, future=None)


@pytest.mark.asyncio
async def test_last_rejection_retains_safe_reason_without_admission_or_command(hass):
    from test_modern_metrics import system
    _, runtime, client, now = await system(hass)
    try:
        assert client.last_rejection_payload is None
        pending_rejection(client, now[0])
        before=(client.grant_until, client.lease_until, client.verified, copy.deepcopy(client.journal),
                copy.deepcopy(runtime.observations), copy.deepcopy(runtime.decisions))
        await client.receive('fw/heartbeat_result', canonical(rejection_reply(client)))
        out=client.last_rejection_payload
        assert out==dict(stream='heartbeat', status='rejected', reason='expired_grant',
            scope='historical_matching_reply_only', control_qualified=False, received_age_ms=0)
        assert before==(client.grant_until, client.lease_until, client.verified, client.journal,
                        runtime.observations, runtime.decisions)
        client.send.assert_not_awaited()
        assert client.error=='rejected'
        diagnostic=await async_get_config_entry_diagnostics(hass, runtime.entry)
        assert diagnostic['read_only_last_rejection']==out
        assert all(token not in json.dumps(out) for token in ['session1','e32_lab','adapter','a'*64])
        out['reason']='modified'
        now[0]+=1
        assert client.last_rejection_payload['reason']=='expired_grant'
        assert client.last_rejection_payload['received_age_ms']==1000
        # A later normal state may recover; this remains explicitly historical.
        client.error='shadow_ready';client.changed()
        assert client.last_rejection_payload['status']=='rejected'
        assert client.error=='shadow_ready'
        await client.async_disconnected()
        assert client.last_rejection_payload is None
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', ['private-token', 'accepted', ['expired_grant'], None, 1])
async def test_last_rejection_never_exports_unreviewed_peer_text(hass, reason):
    from test_modern_metrics import system
    _, runtime, client, now = await system(hass)
    try:
        pending_rejection(client, now[0])
        await client.receive('fw/heartbeat_result', canonical(rejection_reply(client,reason=reason)))
        assert client.last_rejection_payload['reason']=='unknown_reason'
        assert client.last_rejection_payload['control_qualified'] is False
        client.send.assert_not_awaited()
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['retained','foreign_session','foreign_boot','foreign_config',
                                   'unrequested','expired','late'])
async def test_last_rejection_ignores_unmatched_or_expired_reply(hass, fault):
    from test_modern_metrics import system
    _, runtime, client, now = await system(hass)
    try:
        pending_rejection(client, now[0])
        await client.receive('fw/heartbeat_result', canonical(rejection_reply(client)))
        pending_rejection(client, now[0], 2)
        p=rejection_reply(client, 2, 'changed_duplicate')
        if fault=='foreign_session':p['adapter_session_id']='old_session'
        elif fault=='foreign_boot':p['boot_id']='old_boot'
        elif fault=='foreign_config':p['config_digest']='b'*64
        elif fault=='unrequested':p['sequence']=3
        elif fault=='expired':now[0]+=5
        elif fault=='late':
            client.pending[('fw/heartbeat_result','adapter',2)]['deadline']+=10
            now[0]+=8
        await client.receive('fw/heartbeat_result',canonical(p),retained=fault=='retained')
        assert client.last_rejection_payload['reason']=='expired_grant'
        client.send.assert_not_awaited()
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('clock', [99, float('nan'), float('inf'), None])
async def test_last_rejection_invalid_read_clock_withdraws_without_revival(hass, clock):
    from test_modern_metrics import system
    _, runtime, client, now = await system(hass)
    try:
        pending_rejection(client, now[0])
        await client.receive('fw/heartbeat_result', canonical(rejection_reply(client)))
        now[0]=clock
        assert client.last_rejection_payload is None
        now[0]=101
        assert client.last_rejection_payload is None
        client.send.assert_not_awaited()
    finally:
        now[0]=101
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_last_rejection_clock_reversal_after_a_read_retires_history(hass):
    from test_modern_metrics import system
    _, runtime, client, now = await system(hass)
    try:
        pending_rejection(client, now[0])
        await client.receive('fw/heartbeat_result', canonical(rejection_reply(client)))
        now[0]=102
        assert client.last_rejection_payload['received_age_ms']==2000
        now[0]=101
        assert client.last_rejection_payload is None
        now[0]=103
        assert client.last_rejection_payload is None
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize('reason', [None, 'expired_grant', 'private-token'])
async def test_native_config_rejection_optional_reason_does_not_hide_failure(hass, reason, monkeypatch):
    from test_modern_metrics import system
    _, runtime, client, now = await system(hass)
    try:
        monkeypatch.setattr(client, 'native_source_current', lambda: True)
        p=rejection_reply(client);p['binding_id']='config'
        if reason is None:p.pop('rejection_reason')
        else:p['rejection_reason']=reason
        client.pending[('fw/config_result','config',1)]=dict(sent=now[0],deadline=now[0]+5,future=None,
            raw=canonical(dict(config=dict(revision=2),config_digest='b'*64)))
        journal=copy.deepcopy(client.journal)
        assert client.native_config_result(p) is False
        assert client._native_device_result=='rejected'
        assert client.journal==journal
        client.send.assert_not_awaited()
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_last_rejection_is_single_history_and_success_keeps_normal_lease_semantics(hass):
    from test_modern_metrics import system
    _, runtime, client, now = await system(hass)
    try:
        pending_rejection(client, now[0])
        await client.receive('fw/heartbeat_result', canonical(rejection_reply(client)))
        now[0]+=1
        pending_rejection(client, now[0], 2)
        await client.receive('fw/heartbeat_result', canonical(rejection_reply(client,2,'old_sequence')))
        assert client.last_rejection_payload['reason']=='old_sequence'
        assert client.last_rejection_payload['received_age_ms']==0
        pending_rejection(client, now[0], 3)
        p=rejection_reply(client,3);p['status']='accepted';p.pop('rejection_reason')
        await client.receive('fw/heartbeat_result',canonical(p))
        assert client.lease_until==now[0]+LEASE_SECONDS
        assert client.last_rejection_payload['reason']=='old_sequence'
        assert client.pending=={}
        client.send.assert_not_awaited()
    finally:
        await runtime.async_stop()


@pytest.mark.asyncio
async def test_fractional_monotonic_epoch_does_not_extend_supervisor_receipt(integrated):
    _,client,bus,_=integrated
    # Straddles a binary exponent boundary; subtracting clocks yields
    # 99.99999999999909 instead of exactly 100 at this integer-ms deadline.
    # The new epoch must also be ahead of the runtime fixture clock.
    bus.clock_base=2**(int(bus.clock_base).bit_length()+1)-0.6666666667
    await bus.start()
    bus.now+=MAX_AGE_SECONDS*1000-1
    client.last_rx=bus.clock();client.grant_until=client.lease_until=bus.clock()+100
    assert client.supervisor_payload is not None
    bus.now+=1
    assert client.supervisor_payload is None


def test_feedback_clock_fault_is_diagnostic_only_and_keeps_outputs_disabled():
    value=status()
    value.update(phase="fault",reason="limits_unknown",feedback_status="hydraulic_feedback_clock_invalid",
                 heat_intent=False,pump_intent=False,path_intent="none",water_target_centi_c=None)
    out=supervisor_status(value)
    assert out["feedback_status"]=="hydraulic_feedback_clock_invalid"
    assert out["control_qualified"] is False and out["physical_outputs_enabled"] is False
    assert out["heat_intent"] is False and out["water_target_centi_c"] is None
