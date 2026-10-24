"""Read-only supervisor projection, actual C++ state and HA diagnostics lifecycle."""
import copy
import json

import pytest
from custom_components.open_thermostat.supervisor_status import supervisor_status
from custom_components.open_thermostat.v1_wire import canonical
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
    bus.now+=14999;client.last_rx=bus.clock();client.grant_until=client.lease_until=bus.clock()+100
    assert client.supervisor_payload is not None
    bus.now+=1
    assert client.supervisor_payload is None
    bus.now=start-1
    assert client.supervisor_payload is None
    bus.now=start
    wire["adapter_alive"]=False
    await client.receive("fw/state/zones",canonical(wire))
    assert client.supervisor_payload is None
    await client.receive("fw/state/zones",canonical(frame(bus)))
    assert client.supervisor_payload is not None
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
