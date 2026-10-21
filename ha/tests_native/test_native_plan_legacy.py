"""Explicit SOURCE-v2 old-journal quarantine through real HA/C++owner, offline."""
import json,os
from pathlib import Path
import pytest
from custom_components.open_thermostat.graph_shadow_validation import canonical
from test_native_control_plan import native_plan,native_two

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True},{"legacy":True,"old_stage":True}],indirect=True)
async def test_known_legacy_requires_explicit_review_then_same_profile_commits_full_new_plan(native_plan):
    n=native_plan;old=n.legacy_record;source=n.source
    assert old and n.client.journal["accepted"]==old and n.client.journal["staged"] is None
    assert n.client._native_legacy_verified and not n.client.ready and not n.runtime.transport_ready
    assert n.client.error=="native_plan_legacy_review_required" and not n.pending
    before=await n.peer.request("durable_readback")
    assert before["stored"]==canonical(old["config"]) and before["writes"]==0 and before["revision"]==1
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
    await n.samples(16,16);await n.event("tick");await n.drain()
    assert not n.client.ready and not any(d.demand for d in n.runtime.decisions.values())
    actual=await n.apply()
    assert actual["config"]["revision"]==2 and actual["config"]["schema"]==2 and len(actual["config"]["zones"])==2
    assert n.source is source and actual["config"]["profile_digest"]==source.policy.profile_digest
    assert n.client.journal["accepted"]==actual and n.client.journal["staged"] is None
    await n.settle(16,22)
    assert tuple(n.runtime.decisions[r.room_id].target_centi_c for r in (n.rad,n.floor))==(2100,1900)
    assert tuple(n.runtime.decisions[r.room_id].demand for r in (n.rad,n.floor))==(True,False)
    stored=await n.peer.request("durable_readback")
    assert json.loads(stored["stored"])==actual["config"] and stored["writes"]==1
    assert sum(op=="initialize_native_plan" for op,_,_ in n.peer.trace)==1
    if p:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(p).open("a") as f:f.write(canonical(dict(scenario="explicit_legacy_to_full_plan",
            old_revision=1,new_revision=2,old_store_bytes=before["store_bytes"],new_store_bytes=stored["store_bytes"],
            durable_writes=1,source_unchanged=True,no_factory_swap=True,physical_outputs=False))+"\n")

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
@pytest.mark.parametrize("fault",["save_failure","ambiguous"])
async def test_legacy_upgrade_storage_uncertainty_preserves_pending_and_recovers_only_from_exact_readback(native_plan,fault):
    n=native_plan;old=n.legacy_record
    await n.client.async_prepare_native_plan();new=n.client.journal["staged"]
    await n.peer.request(fault);await n.client.async_apply(n.client.review_candidate());await n.drain()
    failed=await n.peer.request("durable_readback")
    assert failed["fault"] and not n.client.ready and n.client.journal["accepted"]==old
    assert n.client.journal["staged"]==new
    assert failed["stored"]==canonical(new["config"] if fault=="ambiguous" else old["config"])
    await n.stop();await n.peer.request("reboot",boot="legacy_recovery");await n.start()
    await n.event("connect");await n.handshake()
    if fault=="ambiguous":
        assert n.client.ready and n.client.journal["accepted"]==new and n.client.journal["staged"] is None
    else:
        assert not n.client.ready and n.client.journal["accepted"]==old and n.client.journal["staged"]==new
        assert n.client.error=="native_plan_recovery_review_required" and not n.pending
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
@pytest.mark.parametrize("bad",["default_profile","future_schema","unknown_room","oversize","comfort","too_old_source"])
async def test_actual_cpp_legacy_quarantine_is_optin_bounded_and_preserves_rejected_bytes(native_plan,bad):
    from copy import deepcopy
    n=native_plan;cfg=deepcopy(n.legacy_record["config"])
    await n.stop()
    if bad=="future_schema":cfg["schema"]=9
    elif bad=="unknown_room":cfg["zones"][0]["zone_id"]="deadbeef"
    elif bad=="oversize":cfg["extra"]="x"*4100
    elif bad=="comfort":cfg["zones"][0]["comfort"]=dict(away_centi_c=1800,frost_centi_c=1600,
        maximum_centi_c=2400,minimum_centi_c=1600,presence=False,temporary_ms=3600000,window=False)
    elif bad=="too_old_source":cfg["zones"][0]["max_age_ms"]=120001
    raw=canonical(cfg)
    actual=await n.peer.request("initialize_native_plan",controller="e32_test",boot="oldbytes",
        owner="test_owner",stored=raw,source=dict(profile_digest=n.policy.profile_digest,
            mapping_revision=1,zones=n.profile["zones"],legacy_readback_reviewed=bad!="default_profile"))
    assert actual["fault"] and actual["writes"]==0
    assert (await n.peer.request("durable_readback"))["stored"]==raw

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
async def test_unknown_remote_legacy_never_adopted_or_overwritten(native_plan,hass):
    from homeassistant.helpers.storage import Store
    n=native_plan;await n.stop()
    await Store(hass,1,"open_thermostat.v1."+n.parent.entry_id).async_save({"accepted":None,"staged":None})
    await n.start()
    for _ in range(25):
        await n.event("tick");await n.client.poll();await n.drain()
        if n.client.error=="native_plan_remote_conflict":break
        n.peer.clock[0]+=1
    assert n.client.error=="native_plan_remote_conflict" and not n.client.ready
    assert not n.client._native_remote_known
    with pytest.raises(ValueError):await n.client.async_prepare_native_plan()
    assert (await n.peer.request("status"))["writes"]==0
    assert n.client.journal=={"accepted":None,"staged":None}

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
async def test_dropped_legacy_upgrade_ACK_requires_actual_current_readback_not_resend(native_plan):
    n=native_plan;await n.client.async_prepare_native_plan();stage=n.client.journal["staged"]
    await n.client.async_apply(n.client.review_candidate())
    topic,raw=n.pending.popleft();actual=await n.peer.request("receive",topic=topic,raw=raw)
    assert actual["writes"]==1 and n.client.journal["accepted"]==n.legacy_record and not n.client.ready
    await n.stop();await n.start();await n.handshake()
    assert n.client.ready and n.client.journal["accepted"]==stage and n.client.journal["staged"] is None
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
@pytest.mark.parametrize("cause",["adapter","selected_profile","registration"])
async def test_final_store_await_during_legacy_prepare_cannot_stage_after_owner_loss(native_plan,hass,monkeypatch,cause):
    import inspect
    from homeassistant.helpers.storage import Store
    from copy import deepcopy
    import custom_components.open_thermostat as integration
    n=native_plan;old=deepcopy(n.client.journal);real=Store.async_load;fired=False
    async def load(store):
        nonlocal fired
        value=await real(store)
        if not fired and store.key=="open_thermostat.v1."+n.parent.entry_id and any(f.function=="async_prepare_native_plan" for f in inspect.stack()):
            fired=True
            if cause=="adapter":
                hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"other_owner"})
            elif cause=="selected_profile":monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
            else:monkeypatch.setattr(hass.config_entries,"async_get_entry",lambda entry_id:None)
        return value
    monkeypatch.setattr(Store,"async_load",load)
    with pytest.raises(ValueError):await n.client.async_prepare_native_plan()
    assert fired and n.client.journal==old
    assert (await n.peer.request("status"))["writes"]==0
    await n.drain()
    assert not any(op=="receive" and kw.get("topic")=="ha/config" for op,kw,_ in n.peer.trace)

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
@pytest.mark.parametrize("wrong",["retained","request","grant","profile","sequence_bool"])
async def test_legacy_snapshot_needs_own_current_typed_proof_and_cannot_restore_control(native_plan,wrong):
    n=native_plan;old=n.client.journal
    await n.client.message("ha/snapshot_request","snapshot",{})
    topic,raw=n.pending.popleft();actual=await n.peer.request("receive",topic=topic,raw=raw)
    snap=next(json.loads(f["raw"]) for f in actual["frames"] if f["topic"]=="fw/config_snapshot")
    if wrong=="request":snap["request_sequence"]+=1
    elif wrong=="grant":snap["grant_id"]="old_grant"
    elif wrong=="profile":snap["profile_digest"]="f"*64
    elif wrong=="sequence_bool":snap["request_sequence"]=True
    proof=n.client._native_snapshot_request
    await n.client.receive("fw/config_snapshot",canonical(snap),retained=wrong=="retained")
    assert n.client._native_snapshot_request==proof and n.client.journal==old
    assert not n.client.ready and (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
@pytest.mark.parametrize("wrong",["capability_missing","old_profile_kind","future_profile_schema","profile_digest","physical_flag"])
async def test_old_or_unknown_profile_metadata_never_bootstraps_legacy_authority(native_plan,wrong):
    n=native_plan
    hello=next(json.loads(f["raw"]) for _,_,r in n.peer.trace for f in r["frames"] if f["topic"]=="fw/hello")
    await n.client.async_disconnected()
    if wrong=="capability_missing":hello["control_capabilities"]=[c for c in hello["control_capabilities"] if c!="control.plan.legacy_readback.v1"]
    elif wrong=="old_profile_kind":hello["source_policy"]["kind"]="installation.shadow.v1"
    elif wrong=="future_profile_schema":hello["source_policy"]["schema"]=99
    elif wrong=="profile_digest":hello["source_policy"]["profile_digest"]="c"*64
    else:hello["source_policy"]["physical_outputs_enabled"]=True
    await n.client.receive("fw/hello",canonical(hello))
    assert n.client.session is None and not n.client.ready and not n.pending
    assert n.client.journal["accepted"]==n.legacy_record
    assert (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
async def test_after_legacy_upgrade_ordinary_next_revision_uses_same_profile_and_store(native_plan,hass):
    n=native_plan;first=await n.apply();source=n.source
    sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.floor.room_id)
    hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2000})
    await hass.async_block_till_done();assert not n.client.ready
    await n.stop();await n.start();await n.handshake()
    assert not n.client.ready and n.client.journal["accepted"]==first
    second=await n.apply()
    assert second["config"]["revision"]==3 and n.source is source
    assert second["config"]["profile_digest"]==first["config"]["profile_digest"]
    assert second["config"]["zones"][1]["base_centi_c"]==2000
    actual=await n.peer.request("durable_readback")
    assert actual["writes"]==2 and json.loads(actual["stored"])==second["config"]

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"legacy":True}],indirect=True)
@pytest.mark.parametrize("confirm",[False,True])
async def test_actual_options_manager_legacy_review_cancel_or_explicit_upgrade(native_plan,hass,confirm):
    from homeassistant import loader
    from custom_components.open_thermostat.v1_model import CONF_MODE,CONF_ENABLED,MODE_SHADOW
    n=native_plan;old=n.legacy_record;source=n.source
    loader.async_setup(hass)
    integration=await loader.async_get_integration(hass,"open_thermostat")
    await integration.async_get_platform("config_flow")
    manager=hass.config_entries.options
    result=await manager.async_init(n.parent.entry_id)
    assert result["step_id"]=="init"
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({
        "graph_action":"prepare",CONF_MODE:MODE_SHADOW,CONF_ENABLED:True,"adapter_id":"test_owner"}))
    assert result["step_id"]=="graph_review"
    assert n.client.journal["accepted"]==old and n.client.journal["staged"]["config"]["revision"]==2
    assert not n.client.ready and (await n.peer.request("status"))["writes"]==0
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({"confirm_apply":confirm}))
    if not confirm:
        assert result["type"]=="abort" and result["reason"]=="graph_review_cancelled"
        assert not n.pending and (await n.peer.request("durable_readback"))["stored"]==canonical(old["config"])
    else:
        assert result["step_id"]=="graph_status" and not n.client.ready
        await n.drain();await n.handshake()
        result=await manager.async_configure(result["flow_id"],result["data_schema"]({"status_action":"refresh"}))
        assert result["description_placeholders"]["verified"]=="True"
        assert n.client.ready and n.client.journal["accepted"]["config"]["revision"]==2
        assert n.source is source and (await n.peer.request("status"))["writes"]==1
        await manager.async_configure(result["flow_id"],result["data_schema"]({"status_action":"close"}))
