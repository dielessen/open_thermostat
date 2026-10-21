"""Native HA source events + SAME real firmware peer; no device/network IO.

proof_* fixture attrs stand in for a reviewed integration adapter's actual report
evidence. There is NO production adapter selected or physical freshness claim.
"""
import asyncio
from dataclasses import replace
from datetime import timedelta,datetime
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_report_event
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.exceptions import ConfigEntryError

import custom_components.open_thermostat as integration
from custom_components.open_thermostat.comfort_sources import ContextReport,ContextSourceProfile
from custom_components.open_thermostat.v1_config_flow import reference
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_model import Observation
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_wire import ShadowClient
from custom_components.open_thermostat.v1_climate import ShadowRoom
from test_v1_native import room,entry
from test_v1_wire_interop import FirmwareBus,RUNNER
from test_comfort_interop import observe

def report(state,event_kind):
    assert event_kind in ("changed","reported")
    return ContextReport(state.attributes.get("proof_key"),state.attributes.get("proof_at"))

def emit(row):
    if name:=os.environ.get("OPENTHERMOSTAT_CONTEXT_EVIDENCE"):
        with Path(name).open("a") as f:f.write(json.dumps(row,sort_keys=True)+"\n")

def pinned(parent,binding,kind):
    ref=getattr(binding,kind)
    return ContextSourceProfile(parent.unique_id,binding.room_id,kind,ref.platform,ref.unique_id,
                                "fixture-logical-report-v1",report)

@pytest_asyncio.fixture
async def context(hass):
    reg=er.async_get(hass)
    window=reg.async_get_or_create("binary_sensor","context_fixture","window-secret-identity")
    person=reg.async_get_or_create("person","context_fixture","person-secret-identity")
    hass.states.async_set(window.entity_id,"off")
    hass.states.async_set(person.entity_id,"home")
    binding=replace(room(hass,age=120000),comfort={"away_centi_c":1600,"frost_centi_c":500,"temporary_ms":60000},
                    window=reference(hass,window.entity_id),presence=reference(hass,person.entity_id))
    other=replace(room(hass,"11223344","second"),comfort=dict(binding.comfort))
    parent=entry(hass,enabled=True,room=binding)
    pins=tuple(pinned(parent,binding,k) for k in ("window","presence"))
    runtime=ShadowRuntime(hass,parent,[binding,other],context_source_profiles=pins)
    zones,mapping=await async_build_configuration(runtime)
    process=await asyncio.create_subprocess_exec(str(RUNNER),stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    bus=FirmwareBus(process,hass.loop.time);bus.utc=int(dt_util.utcnow().timestamp())
    client=ShadowClient(runtime,"ha1",bus.send,Store(hass,1,"test.context."+parent.entry_id),zones,mapping,bus.clock)
    bus.client=client;runtime.attach_transport(client)
    await client.async_start();await runtime.async_start();await bus.start()
    try:
        yield runtime,client,bus,binding,other,pins
    finally:
        await runtime.async_stop();process.stdin.close()
        await asyncio.wait_for(process.wait(),5)
        assert process.returncode==0

async def publish(context,*,kind="window",value=None,key="report-1",sampled=None,extra=None):
    runtime,client,bus,binding,*_=context
    ref=getattr(binding,kind)
    entity_id=runtime.resolved(ref)
    if value is None:value="off" if kind=="window" else "home"
    attrs={"proof_key":key,"proof_at":sampled or dt_util.utcnow(),**(extra or {})}
    runtime.hass.states.async_set(entity_id,value,attrs)
    await runtime.hass.async_block_till_done();await bus.pump()

async def both(context):
    await publish(context)
    await publish(context,kind="presence")
    await observe(*context[:4])

@pytest.mark.asyncio
async def test_existing_native_report_path_admits_unchanged_logical_value_not_cached_last_changed(context,hass):
    runtime,client,bus,binding,other,_=context
    for ref in (binding.window,binding.presence):
        hass.states.get(runtime.resolved(ref)).last_changed=dt_util.utcnow()-timedelta(days=1)
    # No source event since active owner: cache is deliberately UNKNOWN.
    assert runtime.comfort_context(binding)["window_open"] is None
    before_temperature=runtime.observations[binding.room_id]
    await publish(context)
    assert hass.states.get(binding.window.entity_id).last_changed<dt_util.utcnow()-timedelta(hours=1)
    assert runtime.comfort_context(binding)["window_open"] is False
    assert runtime.observations[binding.room_id] is before_temperature
    await publish(context,kind="presence")
    await observe(runtime,client,bus,binding)
    d=runtime.decisions[binding.room_id]
    assert d.target_centi_c==2100 and d.demand
    attrs=ShadowRoom("fixture",binding,runtime).extra_state_attributes
    assert attrs["comfort_context_sources"]=={"window":"qualified_logical_report","presence":"qualified_logical_report"}
    assert attrs["boiler_output_enabled"] is attrs["actuator_output_enabled"] is False
    emit(dict(scenario="unchanged_real_native_report",same_last_changed=True,source_temperature_not_renewed=True,
              target=d.target_centi_c,logical_demand=d.demand,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_actual_state_reported_duplicate_poll_and_wall_reversal_do_not_renew(context,hass,monkeypatch):
    runtime,client,bus,binding,*_=context
    await both(context)
    key=(binding.room_id,"window")
    original=runtime._context_source_values[key]
    state=hass.states.get(binding.window.entity_id)
    reports=[]
    @callback
    def reported(event):
        reports.append(event)
    unsub=async_track_state_report_event(hass,[state.entity_id],reported)
    try:
        hass.states.async_set(state.entity_id,state.state,dict(state.attributes))
        await hass.async_block_till_done();await bus.pump()
    finally:unsub()
    assert reports  # Real unchanged native report, not a direct helper call.
    assert runtime._context_source_values[key] is original
    for _ in range(3):runtime.comfort_context(binding)
    assert runtime._context_source_values[key] is original
    past=dt_util.utcnow()-timedelta(days=1)
    monkeypatch.setattr(dt_util,"utcnow",lambda:past)
    assert runtime.comfort_context(binding)["window_open"] is False
    assert runtime._context_source_values[key] is original
    emit(dict(scenario="native_unchanged_report_duplicate_poll_utc_reversal",original_deadline_preserved=True))

@pytest.mark.asyncio
async def test_new_proof_for_same_value_renews_but_context_never_renews_temperature(context):
    runtime,client,bus,binding,*_=context
    await both(context)
    sample=runtime.observations[binding.room_id]
    old=runtime._context_source_values[(binding.room_id,"window")]
    await publish(context,key="report-2")
    assert runtime._context_source_values[(binding.room_id,"window")] is not old
    assert runtime.observations[binding.room_id] is sample
    emit(dict(scenario="new_source_proof_same_value",original_temperature_observation_preserved=True))

@pytest.mark.asyncio
@pytest.mark.parametrize("fault",["unknown","unavailable","restored","missing","future","stale","naive","nonstring","oversized","out_of_order","key_rewrite","callback_exception"])
async def test_invalid_or_lost_evidence_withdraws_and_exact_old_replay_cannot_revive(context,fault):
    runtime,client,bus,binding,*_=context
    await both(context)
    old=runtime.hass.states.get(binding.window.entity_id)
    oldattrs=dict(old.attributes)
    kwargs={}
    if fault in ("unknown","unavailable"):kwargs["value"]=fault
    elif fault=="restored":kwargs["extra"]={"restored":True}
    elif fault=="missing":kwargs["key"]=None
    elif fault=="future":kwargs["sampled"]=dt_util.utcnow()+timedelta(seconds=1)
    elif fault=="stale":kwargs["sampled"]=dt_util.utcnow()-timedelta(seconds=121)
    elif fault=="naive":kwargs["sampled"]=datetime(2026,10,21)
    elif fault=="nonstring":kwargs["key"]=123
    elif fault=="oversized":kwargs["key"]="x"*129
    elif fault=="out_of_order":kwargs.update(key="older",sampled=oldattrs["proof_at"]-timedelta(milliseconds=1))
    elif fault=="key_rewrite":kwargs.update(key=oldattrs["proof_key"],sampled=dt_util.utcnow())
    else:
        bad=replace(runtime._context_source_profiles[(binding.room_id,"window")],report=lambda *_:1/0)
        runtime._context_source_profiles[(binding.room_id,"window")]=bad
    await publish(context,**kwargs)
    assert runtime.comfort_context(binding)["window_open"] is None
    assert runtime.decisions[binding.room_id].target_centi_c is None
    # Replay exact old source proof after error/unknown must not restore it.
    runtime.hass.states.async_set(old.entity_id,"off",oldattrs)
    await runtime.hass.async_block_till_done();await bus.pump()
    assert runtime.comfort_context(binding)["window_open"] is None
    emit(dict(scenario="invalid_"+fault,withdrawn=True,old_replay_refused=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_monotonic_expiry_and_reversal_never_restore_original_proof(context):
    runtime,client,bus,binding,*_=context
    await both(context)
    key=(binding.room_id,"window")
    for shifted in (-121,1):
        await publish(context,key="new-"+str(shifted))
        age,at,val=runtime._context_source_values[key]
        runtime._context_source_values[key]=(age,at+shifted,val)
        assert runtime.comfort_context(binding)["window_open"] is None
        state=runtime.hass.states.get(binding.window.entity_id)
        runtime.hass.states.async_set(state.entity_id,state.state,dict(state.attributes))
        await runtime.hass.async_block_till_done();await bus.pump()
        assert runtime.comfort_context(binding)["window_open"] is None
    emit(dict(scenario="logical_ttl_and_monotonic_reversal",expired_proof_not_restored=True))

@pytest.mark.asyncio
async def test_real_owner_reconnect_drops_context_and_old_report_never_replays(context):
    runtime,client,bus,binding,*_=context
    await both(context)
    old={kind:dict(runtime.hass.states.get(getattr(binding,kind).entity_id).attributes) for kind in ("window","presence")}
    await bus.event("disconnect");await client.async_disconnected();await bus.start()
    assert client.ready
    assert runtime.comfort_context(binding)["window_open"] is None
    for kind in ("window","presence"):
        ref=getattr(binding,kind);state=runtime.hass.states.get(ref.entity_id)
        runtime.hass.states.async_set(ref.entity_id,state.state,old[kind])
    await runtime.hass.async_block_till_done();await bus.pump()
    assert runtime.comfort_context(binding)["presence_away"] is None
    await publish(context,key="post-reconnect")
    await publish(context,kind="presence",key="post-reconnect")
    await observe(*context[:4])
    assert runtime.decisions[binding.room_id].target_centi_c==2100
    emit(dict(scenario="actual_cpp_owner_reconnect",cache_and_old_proof_refused=True,new_proof_required=True))

@pytest.mark.asyncio
async def test_unknown_presence_never_away_and_window_scope_is_one_zone(context):
    runtime,client,bus,binding,other,_=context
    await both(context);await observe(runtime,client,bus,other)
    await publish(context,kind="presence",value="work",key="named-zone")
    assert runtime.decisions[binding.room_id].target_centi_c is None
    assert runtime.decisions[binding.room_id].reason=="presence_state_unknown"
    assert runtime.decisions[other.room_id].target_centi_c==2100
    await publish(context,kind="presence",key="back-home")
    await publish(context,value="on",key="open-window")
    assert runtime.decisions[binding.room_id].reason=="window_open"
    assert runtime.decisions[other.room_id].demand
    for who,topic,raw in bus.transcript:
        if topic=="fw/state/zones":
            state=json.loads(raw)
            assert state["boiler_output_enabled"] is state["actuator_output_enabled"] is False
            assert state["supervisor"]["physical_outputs_enabled"] is False
    emit(dict(scenario="unknown_presence_and_zone_window",unknown_not_away=True,other_zone_unchanged=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_registry_rename_fresh_event_and_unload_cleanup(context,hass):
    runtime,client,bus,binding,*_=context
    await both(context)
    reg=er.async_get(hass)
    reg.async_update_entity(binding.window.entity_id,new_entity_id="binary_sensor.context_renamed")
    await hass.async_block_till_done();await bus.pump()
    assert runtime.resolved(binding.window)=="binary_sensor.context_renamed"
    assert runtime.comfort_context(binding)["window_open"] is None
    await publish(context,key="after-rename")
    assert runtime.comfort_context(binding)["window_open"] is False
    await runtime.async_stop()
    assert not runtime._subscriptions and not runtime._expiries and not runtime._context_source_values
    hass.states.async_set("binary_sensor.context_renamed","on",{"proof_key":"after-stop","proof_at":dt_util.utcnow()})
    await hass.async_block_till_done()
    assert runtime.comfort_context(binding)["window_open"] is None
    emit(dict(scenario="registry_rename_and_native_unload",new_source_event_required=True,listener_task_cleanup=True))

@pytest.mark.asyncio
async def test_source_pins_are_bounded_exact_not_gui_selectable_and_native_setup_installs(context,hass,monkeypatch):
    runtime,client,bus,binding,other,pins=context
    # Stop isolated fixture peer ownership before separate native entry setup seam.
    await runtime.async_stop()
    parent=entry(hass,enabled=True,room=binding)
    monkeypatch.setattr(integration,"_COMFORT_CONTEXT_SOURCE_PROFILES",pins)
    import custom_components.open_thermostat.v1_mqtt as mqtt
    connection=AsyncMock()
    monkeypatch.setattr(mqtt,"NativeShadowConnection",lambda _:connection)
    forward=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",forward)
    monkeypatch.setattr(hass.config_entries,"async_unload_platforms",AsyncMock(return_value=True))
    assert await integration.async_setup_entry(hass,parent)
    actual=hass.data["open_thermostat"][parent.entry_id]["v1_runtime"]
    try:
        assert len(actual._context_source_profiles)==2
        assert actual.comfort_context(binding)["window_open"] is None
        hass.states.async_set(binding.window.entity_id,"off",{"proof_key":"setup","proof_at":dt_util.utcnow()})
        await hass.async_block_till_done()
        assert actual.comfort_context(binding)["window_open"] is False
        assert forward.await_count==1 and connection.async_start.await_count==1
    finally:
        assert await integration.async_unload_entry(hass,parent)
    assert not actual._subscriptions and not actual._context_source_values
    # Source pins NEVER selected by entry option; unrelated native entry is not captured.
    unselected=entry(hass,enabled=True,room=binding)
    hass.config_entries.async_update_entry(unselected,unique_id="another-hub")
    assert integration._selected_context_source_profiles(unselected)==()
    monkeypatch.setattr(integration,"_COMFORT_CONTEXT_SOURCE_PROFILES",())
    hass.config_entries.async_update_entry(parent,options={**parent.options,"context_source_profiles":[{"room_id":binding.room_id,"profile_id":"gui-cannot-qualify"}]})
    assert integration._selected_context_source_profiles(parent)==()
    emit(dict(scenario="actual_native_entry_setup_unload",source_selected=True,options_cannot_qualify=True,unrelated_entry_not_captured=True))

@pytest.mark.asyncio
@pytest.mark.parametrize("fault",["wrong_entry","wrong_room","wrong_identity","unknown_schema","wrong_ttl","duplicate","excess","non_tuple"])
async def test_source_pin_invalid_never_silently_falls_back(context,fault):
    runtime,client,bus,binding,_,pins=context
    profile=pins[0]
    changes={"wrong_entry":{"entry_unique_id":"another"},"wrong_room":{"room_id":"ffffffff"},
             "wrong_identity":{"unique_id":"another"},"unknown_schema":{"schema":2},"wrong_ttl":{"maximum_age_ms":3600000}}
    selected=(replace(profile,**changes[fault]),) if fault in changes else {
        "duplicate":(profile,profile),"excess":(profile,)*17,"non_tuple":[profile]}[fault]
    with pytest.raises(ValueError,match="context_profile"):
        ShadowRuntime(runtime.hass,runtime.entry,[binding],context_source_profiles=selected)
    emit(dict(scenario="source_pin_"+fault,fail_closed=True))

@pytest.mark.asyncio
async def test_default_conservative_unchanged_and_diagnostics_redact_proofs(context,hass,monkeypatch):
    runtime,client,bus,binding,*_=context
    unselected=ShadowRuntime(hass,runtime.entry,[binding])
    hass.states.get(binding.window.entity_id).last_changed=dt_util.utcnow()-timedelta(days=1)
    assert unselected.comfort_context(binding)["window_open"] is None
    await both(context)
    hass.data.setdefault("open_thermostat",{})[runtime.entry.entry_id]={"v1_runtime":runtime}
    from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
    public=await async_get_config_entry_diagnostics(hass,runtime.entry)
    attrs=ShadowRoom("fixture",binding,runtime).extra_state_attributes
    text=json.dumps(public)+json.dumps(attrs)
    assert "qualified_logical_report" in text
    for private in ("window-secret-identity","person-secret-identity","fixture-logical-report-v1","proof_key","proof_at","report-1"):
        assert private not in text
    assert not public["transport_ready"] or client.ready
    emit(dict(scenario="default_conservative_and_public_status",source_proof_identity_redacted=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_unchanged_firmware_ttl_still_expires_context_before_fresh_temperature(context):
    runtime,client,bus,binding,*_=context
    sampled=dt_util.utcnow()-timedelta(seconds=119)
    await publish(context,sampled=sampled)
    await publish(context,kind="presence",sampled=sampled)
    await observe(*context[:4])
    assert runtime.decisions[binding.room_id].target_centi_c==2100
    # Advance the actual finite peer clock without replaying any observation.
    # Temperature TTL120s is still fresh, logical report has crossed120s.
    await bus.advance(3000)
    d=runtime.decisions[binding.room_id]
    assert d.current_centi_c==1900 and d.target_centi_c is None and not d.demand
    assert d.reason=="window_state_unknown"
    emit(dict(scenario="actual_cpp_context_ttl",temperature_still_fresh=True,context_expired=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_native_setup_wrong_source_binding_is_explicit_error_and_no_owner_created(context,hass,monkeypatch):
    runtime,client,bus,binding,_,pins=context
    bad=(replace(pins[0],unique_id="wrong-source"),)
    monkeypatch.setattr(integration,"_COMFORT_CONTEXT_SOURCE_PROFILES",bad)
    parent=entry(hass,enabled=True,room=binding)
    with pytest.raises(ConfigEntryError,match="context_profile_binding"):
        await integration.async_setup_entry(hass,parent)
    assert parent.entry_id not in hass.data.get("open_thermostat",{})
    async def async_callback(*_):return None
    for profile in (replace(pins[0],schema=True),replace(pins[0],report=async_callback)):
        monkeypatch.setattr(integration,"_COMFORT_CONTEXT_SOURCE_PROFILES",(profile,))
        with pytest.raises(ConfigEntryError,match="context_profile_invalid"):
            integration._selected_context_source_profiles(parent)
    emit(dict(scenario="native_setup_invalid_source",explicit_error=True,no_owner_or_fallback=True))
