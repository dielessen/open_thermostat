"""One-generation explicitly reviewed SOURCE change; actual HA and finite C++core."""
from copy import deepcopy
from dataclasses import replace
import json,os
from pathlib import Path
import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.native_provisioning import (
    SOURCE_OPTION,source_selection,source_from_selection,local_device_descriptor,
    propose_local_shadow_source,reviewed_profile_evolution)
from custom_components.open_thermostat.graph_shadow_validation import canonical,digest
from custom_components.open_thermostat.v1_model import CONF_ENABLED,EntityReference
from test_native_control_plan import native_plan,native_two
from test_native_source_options import source_flow

async def prepare(n,hass,monkeypatch,*,binding=False,confirm=True):
    first=await n.apply()
    before=await n.peer.request("durable_readback")
    await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,
        CONF_ENABLED:False,SOURCE_OPTION:source_selection(n.source)})
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    sub=next(v for v in n.parent.subentries.values() if v.subentry_type=="zone"
        and v.data["room_id"]==n.floor.room_id)
    if binding:
        sensor=er.async_get(hass).async_get_or_create("sensor","profile_evolution_fixture","floor_sensor_new")
        hass.states.async_set(sensor.entity_id,"20",{"device_class":"temperature","unit_of_measurement":"°C"})
        data={**sub.data,"temperature":EntityReference(sensor.entity_id,sensor.platform,sensor.unique_id).as_dict()}
    else:data={**sub.data,"minimum_target_centi_c":1500}
    hass.config_entries.async_update_subentry(n.parent,sub,data=data)
    manager,form=await source_flow(hass,n.parent)
    assert form["step_id"]=="installation_source_review"
    old=source_from_selection(n.parent)
    shown=form["description_placeholders"]
    assert old.policy.profile_digest in shown["scope"] and "READBACK ONLY" in shown["scope"]
    result=await manager.async_configure(form["flow_id"],form["data_schema"]({
        "confirm_source":True,"confirm_replacement":confirm}))
    if not confirm:
        assert result["type"]=="abort";assert source_from_selection(n.parent)==old
        return first,before,None
    assert result["type"]=="create_entry",result
    new=source_from_selection(n.parent);assert new.predecessor==old
    assert new.policy.profile_digest!=old.policy.profile_digest
    assert new.documents()[0]["mapping_revision"]==old.documents()[0]["mapping_revision"]+1
    assert not n.pending
    # Actual local endpoint helper checks same previous descriptor + total existing
    # settings budget. In-memory boot seam, NOT live settings/reboot evidence.
    previous={"mqtt":{"adapter_id":"test_owner","modern_shadow":True,"native_shadow_source":local_device_descriptor(old)}}
    candidate=deepcopy(previous);candidate["mqtt"]["native_shadow_source"]=local_device_descriptor(new)
    allowed=await n.peer.request("check_native_settings",raw=canonical(candidate),previous=canonical(previous),controller="e32_test")
    assert allowed["accepted"] and allowed["within_budget"]
    initialized=await n.peer.request("initialize_native_local_source",controller="e32_test",owner="test_owner",
        boot="profile_evolution_boot",stored=before["stored"],local_source=canonical(local_device_descriptor(new)))
    assert not initialized["fault"] and initialized["revision"]==first["config"]["revision"]
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:True})
    n.source=new;n.policy=new.policy
    await n.start();await n.event("connect");await n.handshake()
    return first,before,new

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("binding",[False,True],ids=["profile_limits","sensor_binding"])
async def test_explicit_native_review_migrates_exact_old_profile_then_full_plan_readback(native_plan,hass,monkeypatch,binding):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch,binding=binding)
    assert n.client.journal["accepted"]==first and not n.client.ready
    assert n.client.error=="native_plan_profile_review_required",n.client.error
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    await n.samples(16,16);await n.event("tick");await n.drain()
    state=await n.peer.request("status")
    assert not n.client.ready and not n.runtime.transport_ready
    assert not n.runtime.decisions or not any(d.demand for d in n.runtime.decisions.values())
    second=await n.apply()
    assert second["config"]["revision"]==2 and second["config"]["profile_digest"]==new.policy.profile_digest
    after=await n.peer.request("durable_readback")
    assert after["writes"]==2 and after["stored"]==canonical(second["config"])
    assert n.client.journal=={"accepted":second,"staged":None}
    if binding:
        assert first["config"]["mapping_digest"]!=second["config"]["mapping_digest"]
    # New exact config boots normally; predecessor is never restored as an active
    # controller, nor a grant, observation, override, model or safety producer.
    await n.stop();await n.peer.request("reboot",boot="new_profile_exact_boot");await n.start()
    assert n.client.session is None and not n.client.ready
    await n.event("connect");await n.handshake()
    assert n.client.ready and (await n.peer.request("status"))["writes"]==2
    assert not any(d.demand for d in n.runtime.decisions.values())
    if target:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(target).open("a") as f:f.write(canonical(dict(scenario="explicit_native_profile_evolution",
            changed_binding=binding,previous_revision=1,new_revision=2,
            old_profile=new.policy.predecessor_profile_digest,new_profile=new.policy.profile_digest,
            descriptor_bytes=len(canonical(local_device_descriptor(new)).encode()),
            selection_bytes=len(canonical(source_selection(new)).encode()),config_bytes=after["store_bytes"],
            physical_outputs=False,actual_safety="UNKNOWN"))+"\n")

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_replacement_requires_separate_confirmation_preserves_old_journal(native_plan,hass,monkeypatch):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch,confirm=False)
    after=await n.peer.request("durable_readback")
    assert new is None and before["stored"]==after["stored"] and after["writes"]==1
    saved=await Store(hass,1,"open_thermostat.v1."+n.parent.entry_id).async_load()
    assert saved=={"accepted":first,"staged":None}

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("bad",["owner","device","unknown_version","recursive","same_profile","wrong_old","too_large"])
async def test_descriptor_evolution_failclosed_without_IO(native_plan,hass,monkeypatch,bad):
    n=native_plan
    plain=local_device_descriptor(n.source)
    next_doc=deepcopy(plain);next_doc[4]+=1;next_doc[6][1][7]-=100
    wrapped=["native.source.evolution.v1",deepcopy(plain),next_doc]
    if bad=="owner":wrapped[1][2]="other"
    elif bad=="device":wrapped[1][1]="other"
    elif bad=="unknown_version":wrapped[0]="native.source.evolution.v9"
    elif bad=="recursive":wrapped[1]=deepcopy(wrapped)
    elif bad=="same_profile":wrapped[2]=deepcopy(plain)
    elif bad=="wrong_old":wrapped[1][4]+=2
    elif bad=="too_large":wrapped[0]="x"*2049
    before=await n.peer.request("durable_readback")
    decoded=await n.peer.request("decode_local_source",raw=canonical(wrapped),controller="e32_test",owner="test_owner")
    assert not decoded["accepted"]
    after=await n.peer.request("durable_readback")
    assert before["stored"]==after["stored"] and after["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("drift",["owner_final_load","registry_final_load","source_final_load","save_failure"])
async def test_evolved_profile_last_await_and_failed_save_never_stage_or_send(native_plan,hass,monkeypatch,drift):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    actual_load=n.client.store.async_load
    actual_save=n.client.store.async_save
    fired=False
    async def load():
        nonlocal fired
        value=await actual_load();fired=True
        if drift=="owner_final_load":
            hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"other_owner"})
        elif drift=="registry_final_load":
            er.async_get(hass).async_remove(n.rad.temperature.entity_id)
        elif drift=="source_final_load":
            hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,SOURCE_OPTION:source_selection(new.predecessor)})
        return value
    async def save(v):raise OSError("synthetic Store save failure")
    monkeypatch.setattr(n.client.store,"async_load",load)
    if drift=="save_failure":monkeypatch.setattr(n.client.store,"async_save",save)
    with pytest.raises(Exception):await n.client.async_prepare_native_plan()
    assert fired and not n.client.ready and not n.pending
    assert n.client.journal=={"accepted":first,"staged":None}
    monkeypatch.setattr(n.client.store,"async_load",actual_load)
    monkeypatch.setattr(n.client.store,"async_save",actual_save)
    assert await actual_load()=={"accepted":first,"staged":None}
    after=await n.peer.request("durable_readback")
    assert after["stored"]==before["stored"] and after["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_evolution_never_adopts_unknown_remote_config_or_old_grant(native_plan,hass,monkeypatch):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    await n.stop()
    # Exact old profile but unknown locally modified config is not authorized by
    # naming a predecessor. Preserve durable old journal and remote bytes.
    remote=deepcopy(first["config"]);remote["zones"][0]["base_centi_c"]+=100
    boot=await n.peer.request("initialize_native_local_source",controller="e32_test",owner="test_owner",
        boot="unknown_prior_config",stored=canonical(remote),local_source=canonical(local_device_descriptor(new)))
    assert not boot["fault"]
    await n.start();await n.event("connect")
    for _ in range(6):await n.event("tick");await n.client.poll();await n.drain()
    assert not n.client.ready and not n.client._native_remote_known and n.client.error=="native_plan_remote_conflict"
    with pytest.raises(Exception):await n.client.async_prepare_native_plan()
    assert n.client.journal=={"accepted":first,"staged":None} and not n.pending
    assert (await n.peer.request("durable_readback"))["stored"]==canonical(remote)

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("fault",["save_failure","ambiguous"])
async def test_migration_failed_or_ambiguous_device_save_keeps_journal_until_actual_boot_readback(native_plan,hass,monkeypatch,fault):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    await n.client.async_prepare_native_plan();stage=deepcopy(n.client.journal["staged"])
    await n.peer.request(fault);await n.client.async_apply(n.client.review_candidate());await n.drain()
    actual=await n.peer.request("durable_readback")
    assert actual["fault"] and not n.client.ready
    assert n.client.journal=={"accepted":first,"staged":stage}
    assert actual["stored"]==canonical(stage["config"] if fault=="ambiguous" else first["config"])
    await n.stop();await n.peer.request("reboot",boot="profile_failed_save_boot");await n.start()
    await n.event("connect");await n.handshake()
    if fault=="ambiguous":
        assert n.client.ready and n.client.journal=={"accepted":stage,"staged":None}
    else:
        assert not n.client.ready and n.client.journal=={"accepted":first,"staged":stage}
        assert n.client.error=="native_plan_recovery_review_required" and not n.pending
    assert (await n.peer.request("status"))["writes"]==2

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_migration_lost_ACK_duplicate_apply_and_reload_never_resend_or_fabricate_success(native_plan,hass,monkeypatch):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    await n.client.async_prepare_native_plan();stage=deepcopy(n.client.journal["staged"]);review=n.client.review_candidate()
    await n.client.async_apply(review)
    with pytest.raises(Exception):await n.client.async_apply(review)
    assert len(n.pending)==1
    topic,raw=n.pending.popleft()
    actual=await n.peer.request("receive",topic=topic,raw=raw) # Intentionally lose all reply frames.
    assert actual["writes"]==2 and not n.client.ready and n.client.journal["accepted"]==first
    await n.stop();await n.start();await n.handshake()
    assert n.client.ready and n.client.journal=={"accepted":stage,"staged":None} and not n.pending
    assert (await n.peer.request("status"))["writes"]==2

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("bad",["missing_capability","missing_previous","wrong_previous","future_schema","physical_enabled"])
async def test_evolution_metadata_cannot_be_forged_from_old_or_unsupported_firmware(native_plan,hass,monkeypatch,bad):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    hello=deepcopy(next(json.loads(f["raw"]) for _,_,r in reversed(n.peer.trace) for f in r["frames"] if f["topic"]=="fw/hello"))
    await n.client.async_disconnected()
    if bad=="missing_capability":hello["control_capabilities"]=[c for c in hello["control_capabilities"] if c!="control.plan.profile_evolution.v1"]
    elif bad=="missing_previous":hello["source_policy"].pop("predecessor_profile_digest")
    elif bad=="wrong_previous":hello["source_policy"]["predecessor_profile_digest"]="f"*64
    elif bad=="future_schema":hello["source_policy"]["schema"]=99
    else:hello["source_policy"]["physical_outputs_enabled"]=True
    await n.client.receive("fw/hello",canonical(hello))
    assert n.client.session is None and not n.client.ready and not n.pending
    assert n.client.journal=={"accepted":first,"staged":None}
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("wrong",["retained","request","grant","profile","sequence_bool"])
async def test_predecessor_snapshot_requires_fresh_typed_request_and_never_restores_control(native_plan,hass,monkeypatch,wrong):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    await n.client.message("ha/snapshot_request","snapshot",{})
    topic,raw=n.pending.popleft();actual=await n.peer.request("receive",topic=topic,raw=raw)
    snap=next(json.loads(f["raw"]) for f in actual["frames"] if f["topic"]=="fw/config_snapshot")
    if wrong=="request":snap["request_sequence"]+=1
    elif wrong=="grant":snap["grant_id"]="old_grant"
    elif wrong=="profile":snap["profile_digest"]="f"*64
    elif wrong=="sequence_bool":snap["request_sequence"]=True
    proof=n.client._native_snapshot_request
    await n.client.receive("fw/config_snapshot",canonical(snap),retained=wrong=="retained")
    assert n.client._native_snapshot_request==proof and not n.client.ready
    assert n.client.journal=={"accepted":first,"staged":None} and not n.pending
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("wrong",["profile","mapping","future_schema","malformed","oversize"])
async def test_actual_core_refuses_incompatible_old_bytes_without_rewriting_them(native_plan,hass,monkeypatch,wrong):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    await n.stop();old=deepcopy(first["config"])
    if wrong=="profile":old["profile_digest"]="f"*64
    elif wrong=="mapping":old["mapping"]["channels"][0]["resource_id"]="f"*64
    elif wrong=="future_schema":old["schema"]=99
    elif wrong=="malformed":old["zones"][0]["base_centi_c"]=True
    else:old["extra"]="x"*4100
    raw=canonical(old)
    actual=await n.peer.request("initialize_native_local_source",controller="e32_test",owner="test_owner",
        boot="invalid_previous_config",stored=raw,local_source=canonical(local_device_descriptor(new)))
    assert actual["fault"] and actual["writes"]==1
    assert (await n.peer.request("durable_readback"))["stored"]==raw

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_known_old_staged_journal_promotes_only_from_exact_readback_and_stays_quarantined(native_plan,hass,monkeypatch):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    await n.stop()
    await Store(hass,1,"open_thermostat.v1."+n.parent.entry_id).async_save({"accepted":None,"staged":first})
    await n.start();await n.handshake()
    assert not n.client.ready and n.client.journal=={"accepted":first,"staged":None}
    assert n.client.error=="native_plan_profile_review_required"
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_second_explicit_profile_change_is_flat_bounded_and_never_revives_older_history(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat.native_provisioning import current_profile_only
    n=native_plan;first,before,second_source=await prepare(n,hass,monkeypatch)
    second=await n.apply();await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    # Reopening unchanged source review is idempotent: no phantom revision.
    manager,form=await existing_manager_source_flow(hass,n.parent)
    assert form["description_placeholders"]["fingerprint"]==second_source.policy.profile_digest
    result=await manager.async_configure(form["flow_id"],form["data_schema"]({"confirm_source":True}))
    assert result["type"]=="create_entry" and source_from_selection(n.parent)==second_source
    sub=next(v for v in n.parent.subentries.values() if v.subentry_type=="zone" and v.data["room_id"]==n.floor.room_id)
    hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"minimum_target_centi_c":1400})
    manager,form=await existing_manager_source_flow(hass,n.parent)
    result=await manager.async_configure(form["flow_id"],form["data_schema"]({"confirm_source":True,"confirm_replacement":True}))
    assert result["type"]=="create_entry"
    third_source=source_from_selection(n.parent)
    assert third_source.predecessor==current_profile_only(second_source) and third_source.predecessor.predecessor is None
    descriptor=local_device_descriptor(third_source)
    assert len(canonical(descriptor).encode())<2048 and descriptor[1][0]=="native.source.local.v1"
    old_settings={"mqtt":{"adapter_id":"test_owner","modern_shadow":True,"native_shadow_source":local_device_descriptor(second_source)}}
    new_settings=deepcopy(old_settings);new_settings["mqtt"]["native_shadow_source"]=descriptor
    checked=await n.peer.request("check_native_settings",raw=canonical(new_settings),previous=canonical(old_settings),controller="e32_test")
    assert checked["accepted"]
    initialized=await n.peer.request("initialize_native_local_source",controller="e32_test",owner="test_owner",
        boot="third_profile",stored=canonical(second["config"]),local_source=canonical(descriptor))
    assert not initialized["fault"]
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:True})
    n.source=third_source;await n.start();await n.event("connect");await n.handshake()
    assert not n.client.ready and n.client.journal["accepted"]==second
    third=await n.apply()
    assert third["config"]["revision"]==3 and n.client.ready
    assert third["config"]["mapping"]["mapping_revision"]==3
    assert (await n.peer.request("status"))["writes"]==3

async def existing_manager_source_flow(hass,parent):
    # Loader/platform initialized by prepare. Repeated loader.async_setup wipes
    # native loader state; real options revisions reuse the same manager.
    from custom_components.open_thermostat.v1_model import CONF_MODE,MODE_SHADOW
    manager=hass.config_entries.options
    result=await manager.async_init(parent.entry_id)
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({
        "information":"installation_source",CONF_MODE:MODE_SHADOW,CONF_ENABLED:False,"adapter_id":"test_owner"}))
    assert result["step_id"]=="installation_source"
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({"controller_id":"e32_test","legacy_readback":False}))
    assert result["step_id"]=="installation_source_review"
    return manager,result

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_actual_two_profile_codec_allocation_faults_are_bounded_and_leakfree(native_plan,hass,monkeypatch):
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    reply=await n.peer.request("probe_local_source_allocations",raw=canonical(local_device_descriptor(new)),
        controller="e32_test",owner="test_owner")
    assert reply["accepted"] and not reply["leaks"]
    assert 0<reply["allocation_faults"]==reply["rejected_faults"]<=512 and reply["writes"]==1
    if target:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(target).open("a") as f:f.write(canonical(dict(scenario="evolution_codec_allocation_faults",**reply))+"\n")

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_native_migration_status_form_names_quarantine_without_claiming_applied(native_plan,hass,monkeypatch):
    from test_native_plan_gui import rendered,record
    n=native_plan;first,before,new=await prepare(n,hass,monkeypatch)
    form=await n.flow().async_step_graph_status()
    text=await rendered(hass,form);record("profile_quarantine",form,text)
    assert "Previous profile configuration read back in quarantine" in text
    assert "explicitly review and apply the new profile plan" in text
    assert "No verified native-plan control; physical outputs disabled" in text
    assert form["description_placeholders"]["verified"]=="False"
    assert n.client.journal=={"accepted":first,"staged":None} and not n.pending
