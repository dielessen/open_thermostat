"""Explicit local SOURCE apply reuses SAME actual C++core/boot/store; no device IO."""
from copy import deepcopy
import json,os
from pathlib import Path
import pytest
from homeassistant.helpers import entity_registry as er
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.native_provisioning import (
    SOURCE_OPTION,source_selection,source_from_selection,local_device_descriptor)
from custom_components.open_thermostat.graph_shadow_validation import canonical
from custom_components.open_thermostat.v1_model import CONF_ENABLED,EntityReference
from test_native_control_plan import native_plan,native_two
from test_native_source_options import source_flow

def latest_hello(n):
    return next(json.loads(f["raw"]) for _,_,r in reversed(n.peer.trace) for f in r["frames"] if f["topic"]=="fw/hello")

async def review_local(n,hass,monkeypatch,*,binding=False,confirm=True):
    first=await n.apply();old_hello=latest_hello(n)
    before=await n.peer.request("durable_readback")
    await n.stop()
    old=n.source
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False,SOURCE_OPTION:source_selection(old)})
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    sub=next(v for v in n.parent.subentries.values() if v.subentry_type=="zone" and v.data["room_id"]==n.floor.room_id)
    if binding:
        ref=er.async_get(hass).async_get_or_create("sensor","native_live_source_fixture","floor_new")
        hass.states.async_set(ref.entity_id,"20",{"device_class":"temperature","unit_of_measurement":"°C"})
        data={**sub.data,"temperature":EntityReference(ref.entity_id,ref.platform,ref.unique_id).as_dict()}
    else:data={**sub.data,"minimum_target_centi_c":1500}
    hass.config_entries.async_update_subentry(n.parent,sub,data=data)
    manager,form=await source_flow(hass,n.parent)
    result=await manager.async_configure(form["flow_id"],form["data_schema"]({"confirm_source":True,"confirm_replacement":confirm}))
    if not confirm:
        assert result["type"]=="abort";assert source_from_selection(n.parent)==old
        return first,before,old,None,old_hello
    assert result["type"]=="create_entry"
    next_source=source_from_selection(n.parent)
    assert next_source.predecessor==old and next_source.policy.profile_digest!=old.policy.profile_digest
    return first,before,old,next_source,old_hello

async def local_apply(n,hass,new):
    descriptor=canonical(local_device_descriptor(new))
    reply=await n.peer.request("replace_native_local_source",local_source=descriptor)
    assert reply["source_selected"] and not reply["fault"],reply
    assert reply["writes"]==1
    n.source=new;n.policy=new.policy
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:True})
    await n.start();await n.handshake()
    return reply

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("binding",[False,True],ids=["profile","sensor_binding"])
async def test_same_actual_core_and_boot_reselects_explicit_profile_then_fresh_full_plan(native_plan,hass,monkeypatch,binding):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch,binding=binding)
    await local_apply(n,hass,new)
    current=latest_hello(n)
    assert current["boot_id"]==hello["boot_id"] and current["epoch"]>hello["epoch"]
    assert not n.client.ready and n.client.journal=={"accepted":first,"staged":None}
    assert n.client.error=="native_plan_profile_review_required"
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    # New ordinary native goal/week revision, within unchanged8-transition scope.
    from custom_components.open_thermostat.v1_program import normalize_program
    from custom_components.open_thermostat.schedule_compiler import WEEKDAYS
    room=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
    program=normalize_program({day:[{"start":0,"end":86400,"target_centi_c":2200}] for day in WEEKDAYS},1600,2400)
    hass.config_entries.async_update_subentry(n.parent,room,data={**room.data,"base_centi_c":2300,"week_program":program})
    await hass.async_block_till_done();await n.stop();await n.start();await n.handshake()
    assert not n.client.ready
    second=await n.apply()
    assert second["config"]["revision"]==2 and n.client.ready
    assert second["config"]["profile_digest"]==new.policy.profile_digest
    assert second["config"]["zones"][0]["base_centi_c"]==2300
    assert second["config"]["zones"][0]["schedule"]["transitions"][0][1]==2200
    if binding:assert second["config"]["mapping_digest"]!=first["config"]["mapping_digest"]
    actual=await n.peer.request("durable_readback")
    assert actual["stored"]==canonical(second["config"]) and actual["writes"]==2
    assert not any(op=="reboot" for op,_,_ in n.peer.trace)
    assert sum(op=="initialize_native_local_source" for op,_,_ in n.peer.trace)==1
    assert sum(op=="replace_native_local_source" for op,_,_ in n.peer.trace)==1
    assert not any(d.demand for d in n.runtime.decisions.values())
    if target:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(target).open("a") as f:f.write(canonical(dict(scenario="same_core_no_device_reboot_source_revision",
            binding_changed=binding,boot_unchanged=True,epoch_increased=True,revision=2,
            config_bytes=actual["store_bytes"],writes=2,physical_outputs=False))+"\n")

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_cancel_local_source_review_never_reconfigures_or_rewrites_anything(native_plan,hass,monkeypatch):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch,confirm=False)
    after=await n.peer.request("durable_readback")
    assert new is None and before["stored"]==after["stored"] and after["writes"]==1
    assert not any(op=="replace_native_local_source" for op,_,_ in n.peer.trace)

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("fault",["read_failure","hash_failure","hash_reentry"])
async def test_failed_local_reselection_latches_fault_never_restores_old_policy(native_plan,hass,monkeypatch,fault):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch)
    if fault!="hash_reentry":await n.peer.request(fault)
    actual=await n.peer.request("replace_native_local_source",local_source=canonical(local_device_descriptor(new)),
        reenter_during_load=fault=="hash_reentry")
    assert not actual["source_selected"] and actual["fault"] and actual["writes"]==1
    again=await n.peer.request("replace_native_local_source",local_source=canonical(local_device_descriptor(new)))
    assert not again["source_selected"] and again["fault"] and again["writes"]==1
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("mixed",["broker","owner","hostname","enabled","profile_only","unchanged","clear"])
async def test_existing_settings_classifier_allows_only_exact_nonnull_source_change(native_plan,mixed):
    n=native_plan
    source=local_device_descriptor(n.source)
    previous={"hostname":"fixture","mqtt":{"adapter_id":"test_owner","modern_shadow":True,"enabled":True,
        "brokerAddress":"fixture-broker","native_shadow_source":source}}
    candidate=deepcopy(previous)
    if mixed=="broker":candidate["mqtt"]["brokerAddress"]="another"
    elif mixed=="owner":candidate["mqtt"]["adapter_id"]="another_owner"
    elif mixed=="hostname":candidate["hostname"]="another"
    elif mixed=="enabled":candidate["mqtt"]["enabled"]=False
    elif mixed=="clear":candidate["mqtt"]["native_shadow_source"]=None
    elif mixed=="profile_only":
        new=deepcopy(source);new[4]+=1
        candidate["mqtt"]["native_shadow_source"]=["native.source.evolution.v1",source,new]
    result=await n.peer.request("check_native_settings",raw=canonical(candidate),previous=canonical(previous),controller="e32_test")
    assert result["source_only"] is (mixed in ("profile_only","unchanged"))
    assert result["requires_source_apply"] is (mixed=="profile_only")
    assert result["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("pending",["broker","hostname","secret","logger","none"])
async def test_pending_saved_network_changes_cannot_be_relabelled_as_live_source_only(native_plan,pending):
    n=native_plan;descriptor=local_device_descriptor(n.source)
    running={"hostname":"fixture","mqtt":{"adapter_id":"test_owner","modern_shadow":True,
        "brokerAddress":"fixture-broker","password":"fixture-secret","native_shadow_source":descriptor}}
    previous=deepcopy(running)
    if pending=="broker":previous["mqtt"]["brokerAddress"]="another"
    elif pending=="hostname":previous["hostname"]="another"
    elif pending=="secret":previous["mqtt"]["password"]="another"
    elif pending=="logger":previous["loggerHost"]="another"
    # Same body relative to SAVED settings still cannot bypass actual boot snapshot.
    candidate=deepcopy(previous)
    new=deepcopy(descriptor);new[4]+=1
    candidate["mqtt"]["native_shadow_source"]=["native.source.evolution.v1",descriptor,new]
    value=await n.peer.request("check_native_settings",raw=canonical(candidate),previous=canonical(previous),
        running_settings=canonical(running),controller="e32_test")
    assert value["source_only"] and value["running_settings_match"] is (pending=="none")
    assert value["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_old_same_boot_epoch_grants_and_config_ACK_never_revive_old_authority(native_plan,hass,monkeypatch):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch)
    old_heartbeat=next(kw["raw"] for op,kw,_ in reversed(n.peer.trace) if op=="receive" and kw.get("topic")=="ha/heartbeat")
    old_ack=next(json.loads(f["raw"]) for _,_,r in reversed(n.peer.trace) for f in r["frames"] if f["topic"]=="fw/config_result")
    await local_apply(n,hass,new)
    journal=deepcopy(n.client.journal);state=n.client._native_device_result
    await n.client.receive("fw/config_result",canonical(old_ack))
    reply=await n.peer.request("receive",topic="ha/heartbeat",raw=old_heartbeat)
    assert not any(json.loads(f["raw"]).get("status")=="accepted" for f in reply["frames"])
    assert not n.client.ready and n.client.journal==journal and n.client._native_device_result==state
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_same_boot_disconnect_reconnect_requires_fresh_readback_and_explicit_new_apply(native_plan,hass,monkeypatch):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch)
    await local_apply(n,hass,new)
    epoch=latest_hello(n)["epoch"]
    await n.client.async_disconnected();await n.event("disconnect")
    assert n.client.session is None and not n.client.ready
    await n.event("connect");await n.handshake()
    assert latest_hello(n)["boot_id"]==hello["boot_id"] and latest_hello(n)["epoch"]>epoch
    assert not n.client.ready and n.client.journal=={"accepted":first,"staged":None} and not n.pending
    second=await n.apply()
    assert second["config"]["revision"]==2 and n.client.ready
    assert (await n.peer.request("status"))["writes"]==2

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("fault",["save_failure","ambiguous"])
async def test_config_save_uncertainty_after_no_boot_reselection_preserves_pending_and_sticky_fault(native_plan,hass,monkeypatch,fault):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch)
    await local_apply(n,hass,new)
    await n.client.async_prepare_native_plan();stage=deepcopy(n.client.journal["staged"])
    await n.peer.request(fault);await n.client.async_apply(n.client.review_candidate());await n.drain()
    actual=await n.peer.request("durable_readback")
    assert actual["fault"] and not n.client.ready
    assert n.client.journal=={"accepted":first,"staged":stage}
    assert actual["stored"]==canonical(stage["config"] if fault=="ambiguous" else first["config"])
    retried=await n.peer.request("replace_native_local_source",local_source=canonical(local_device_descriptor(new)))
    assert retried["fault"] and not retried["source_selected"] and retried["writes"]==2
    assert not any(op=="reboot" for op,_,_ in n.peer.trace)

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("drift",["owner","registry","selected_source","entry"])
async def test_final_native_Store_await_after_hot_reselection_never_stages_for_changed_owner(native_plan,hass,monkeypatch,drift):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch)
    await local_apply(n,hass,new)
    real=n.client.store.async_load;fired=False
    async def load():
        nonlocal fired
        value=await real();fired=True
        if drift=="owner":hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"another"})
        elif drift=="registry":er.async_get(hass).async_remove(n.rad.temperature.entity_id)
        elif drift=="selected_source":hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,SOURCE_OPTION:source_selection(old)})
        else:monkeypatch.setattr(hass.config_entries,"async_get_entry",lambda _:None)
        return value
    monkeypatch.setattr(n.client.store,"async_load",load)
    with pytest.raises(Exception):await n.client.async_prepare_native_plan()
    assert fired and not n.pending and not n.client.ready
    assert n.client.journal=={"accepted":first,"staged":None}
    monkeypatch.setattr(n.client.store,"async_load",real)
    assert await real()=={"accepted":first,"staged":None}
    actual=await n.peer.request("durable_readback")
    assert actual["stored"]==before["stored"] and actual["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_actual_reselection_decode_and_print_allocation_faults_latch_without_success_or_extra_IO(native_plan,hass,monkeypatch):
    n=native_plan;first,before,old,new,hello=await review_local(n,hass,monkeypatch)
    reply=await n.peer.request("probe_native_source_rebind_allocations",raw=canonical(local_device_descriptor(new)))
    assert reply["accepted"] and not reply["leaks"]
    assert 0<reply["allocation_faults"]==reply["rejected_faults"]==reply["sticky_no_IO_retry"]<=512
    assert reply["maximum_reselection_read_attempts"]<=1 and reply["writes"]==1
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    if target:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(target).open("a") as f:f.write(canonical(dict(scenario="actual_source_reselection_allocation_faults",**reply))+"\n")

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True},{"local_source":True,"legacy":True}],indirect=True)
async def test_source_only_capability_refuses_unsupported_legacy_extension(native_plan):
    n=native_plan
    state=await n.peer.request("status")
    assert state["native_source_replaceable"] is (not n.source.policy.legacy_readback_reviewed)
    assert not state["fault"] and state["writes"]==0


async def pending_review(n,hass):
    from test_native_profile_evolution import existing_manager_source_flow
    sub=next(v for v in n.parent.subentries.values() if v.subentry_type=="zone" and v.data["room_id"]==n.floor.room_id)
    hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"minimum_target_centi_c":1400})
    return await existing_manager_source_flow(hass,n.parent)

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_pending_profile_can_be_revised_without_applying_abandoned_intermediate(native_plan,hass,monkeypatch):
    n=native_plan;first,before,old,second,hello=await review_local(n,hass,monkeypatch)
    await local_apply(n,hass,second);await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    manager,form=await pending_review(n,hass)
    done=await manager.async_configure(form["flow_id"],form["data_schema"]({"confirm_source":True,"confirm_replacement":True}))
    assert done["type"]=="create_entry",done
    third=source_from_selection(n.parent)
    assert third.predecessor==old and third.predecessor!=second
    assert third.documents()[0]["mapping_revision"]==old.documents()[0]["mapping_revision"]+1
    assert third.policy.profile_digest!=second.policy.profile_digest
    preview=await n.peer.request("preview_native_local_source",local_source=canonical(local_device_descriptor(third)))
    assert preview["source_selected"] and not preview["fault"] and preview["writes"]==1
    await local_apply(n,hass,third)
    assert latest_hello(n)["boot_id"]==hello["boot_id"]
    assert latest_hello(n)["epoch"]>hello["epoch"]
    assert n.client.journal=={"accepted":first,"staged":None} and not n.client.ready
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    final=await n.apply()
    assert final["config"]["revision"]==2 and final["config"]["profile_digest"]==third.policy.profile_digest
    assert (await n.peer.request("status"))["writes"]==2
    assert sum(op=="replace_native_local_source" for op,_,_ in n.peer.trace)==2
    assert not any(op=="reboot" for op,_,_ in n.peer.trace)
    assert not any(d.demand for d in n.runtime.decisions.values())

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_mixed_accepted_and_staged_profiles_cannot_authorize_another_source(native_plan,hass,monkeypatch):
    from homeassistant.helpers.storage import Store
    from custom_components.open_thermostat.native_provisioning import source_review_predecessor
    n=native_plan;first,before,old,second,hello=await review_local(n,hass,monkeypatch)
    await local_apply(n,hass,second)
    await n.client.async_prepare_native_plan();journal=deepcopy(n.client.journal)
    assert journal["accepted"]==first and journal["staged"]["config"]["profile_digest"]==second.policy.profile_digest
    await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    with pytest.raises(ValueError):await source_review_predecessor(hass,n.parent,second)
    assert await Store(hass,1,"open_thermostat.v1."+n.parent.entry_id).async_load()==journal
    assert source_from_selection(n.parent)==second
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("drift",["owner","registry","selected_source","entry","compiled_source","enabled"])
async def test_source_review_final_new_Store_instance_await_is_owner_fenced(native_plan,hass,monkeypatch,drift):
    from homeassistant.helpers.storage import Store
    from test_native_profile_evolution import existing_manager_source_flow
    n=native_plan;first,before,old,second,hello=await review_local(n,hass,monkeypatch)
    # Selection has changed but actual device still holds old durable config.
    manager,form=await pending_review(n,hass)
    real=Store.async_load;fired=False
    async def load(store):
        nonlocal fired
        value=await real(store)
        if store.key=="open_thermostat.v1."+n.parent.entry_id and not fired:
            fired=True
            if drift=="owner":hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"other_owner"})
            elif drift=="registry":er.async_get(hass).async_remove(n.rad.temperature.entity_id)
            elif drift=="selected_source":hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,SOURCE_OPTION:source_selection(old)})
            elif drift=="entry":monkeypatch.setattr(hass.config_entries,"async_get_entry",lambda _:None)
            elif drift=="compiled_source":monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",(old,))
            else:hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:True})
        return value
    monkeypatch.setattr(Store,"async_load",load)
    done=await manager.async_configure(form["flow_id"],form["data_schema"]({"confirm_source":True,"confirm_replacement":True}))
    assert fired and done["type"]=="abort",done
    assert source_from_selection(n.parent)==(old if drift=="selected_source" else second)
    assert await real(Store(hass,1,"open_thermostat.v1."+n.parent.entry_id))=={"accepted":first,"staged":None}
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    assert (await n.peer.request("status"))["writes"]==1
    assert not n.pending

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_changed_journal_between_display_and_confirm_is_never_silently_adopted(native_plan,hass,monkeypatch):
    from homeassistant.helpers.storage import Store
    from custom_components.open_thermostat.graph_shadow_validation import digest
    n=native_plan;first,before,old,second,hello=await review_local(n,hass,monkeypatch)
    manager,form=await pending_review(n,hass)
    staged=deepcopy(first);staged["config"]["revision"]+=1;staged["config_digest"]=digest(staged["config"])
    changed={"accepted":first,"staged":staged};store=Store(hass,1,"open_thermostat.v1."+n.parent.entry_id)
    await store.async_save(changed)
    done=await manager.async_configure(form["flow_id"],form["data_schema"]({"confirm_source":True,"confirm_replacement":True}))
    assert done["type"]=="abort" and done["reason"]=="native_source_review_changed",done
    assert await store.async_load()==changed and source_from_selection(n.parent)==second
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    assert not n.pending

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_actual_completed_config_rejects_abandoned_predecessor_before_IO(native_plan,hass,monkeypatch):
    from custom_components.open_thermostat.native_provisioning import current_profile_only,reviewed_profile_evolution
    n=native_plan;first,before,old,second,hello=await review_local(n,hass,monkeypatch)
    await local_apply(n,hass,second);applied=await n.apply();await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    manager,form=await pending_review(n,hass)
    proposed=manager._progress[form["flow_id"]]._source_proposal
    wrong=reviewed_profile_evolution(old,current_profile_only(proposed))
    prior=await n.peer.request("durable_readback")
    result=await n.peer.request("preview_native_local_source",local_source=canonical(local_device_descriptor(wrong)))
    assert not result["source_selected"] and not result["fault"]
    actual=await n.peer.request("durable_readback")
    assert actual["stored"]==prior["stored"]==canonical(applied["config"])
    assert actual["writes"]==prior["writes"]==2 and actual["reads"]==prior["reads"]
