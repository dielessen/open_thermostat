"""Actual native draft/DATA apply/store -> explicit two-target SOURCE phase.
No preloaded firmware review, extra owner, device/broker or source qualification.
"""
import asyncio,json,os
from copy import deepcopy
from collections import deque
from dataclasses import asdict,replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest,pytest_asyncio
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import ConfigEntryError,HomeAssistantError
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.graph_floor_bridge import GraphFloorTopologyDraftSource,GraphFloorControllerEntrySource,VERSION
from custom_components.open_thermostat.graph_topology_review import native_topology_plan,prepare_saved_topology_review,TopologyReviewContext
from custom_components.open_thermostat.graph_shadow_validation import canonical,digest,qualification_record_digest,GraphValidationError
from custom_components.open_thermostat.graph_wire import GraphSourceProfile
from custom_components.open_thermostat.comfort_sources import ControllerPolicySourceProfile
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow,reference
from custom_components.open_thermostat.v1_climate import ShadowRoom
from custom_components.open_thermostat.v1_heating_graph import validated_graph
from test_graph_topology_review import native_two
from test_graph_owner_interop import pair
from test_graph_shadow_storage import FIXTURE
from test_v1_native import physical_state,source_profile

def emit(row):
    if path:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(path).open("a") as f:f.write(json.dumps(row,sort_keys=True)+"\n")

@pytest_asyncio.fixture
async def bridge(native_two,hass,monkeypatch):
    parent,rad,floor,heating,output=native_two
    floor=replace(floor,base_centi_c=1900)
    sub=next(s for s in parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==floor.room_id)
    hass.config_entries.async_update_subentry(parent,sub,data=floor.as_dict())
    hass.config_entries.async_update_entry(parent,options={**parent.options,"shadow_enabled":True,"adapter_id":"test_owner"})
    plan=native_topology_plan(hass,parent);cx=TopologyReviewContext("e32_test","source_review_boot","source_review_session",1,0,1,1,digest(plan))
    review=prepare_saved_topology_review(hass,parent,cx)
    draft=validated_graph(hass,parent,heating.data["draft"]);a=next(a for a in draft.control_proposal()["actuators"] if a["room_id"]==floor.room_id)
    feedback=er.async_get(hass).async_get_or_create("binary_sensor","bridge_fixture","feedback")
    q=deepcopy(json.loads(FIXTURE["raw"])["config"]["qualification"])
    q["sources"][0]["channel_id"]="s_"+floor.room_id;q["devices"][0]["output_channel"]=a["output_channel"]
    q["record_digest"]=qualification_record_digest(q)
    refs={"s_"+floor.room_id:floor.temperature.as_dict(),a["output_channel"]:reference(hass,output.entity_id).as_dict(),
          q["devices"][0]["feedback_channel"]:reference(hass,feedback.entity_id).as_dict()}
    scope=GraphFloorTopologyDraftSource(canonical(q),canonical(refs),cx,review)
    data_profile=GraphSourceProfile("e32_test",q["record_digest"],scope,entry_unique_id=parent.unique_id)
    data_profile.validate()
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",data_profile)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",())
    monkeypatch.setattr(integration,"_CONTROLLER_POLICY_SOURCE_PROFILES",())
    monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",AsyncMock())
    monkeypatch.setattr(hass.config_entries,"async_unload_platforms",AsyncMock(return_value=True))
    reload=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    callbacks={};pending=deque();removed=[];physical_calls=[];phase=["v2"];holder={}
    hass.services.async_register("climate","set_temperature",lambda call:physical_calls.append(call))
    async def subscribe(_h,topic,cb,**kw):
        key=topic.split("/")[1];callbacks[key]=cb
        return lambda:removed.append(key+"_mqtt")
    def status(_h,cb):
        key=phase[0];callbacks[key+"_status"]=cb
        return lambda:removed.append(key+"_status")
    async def publish(_h,topic,payload,**kw):
        assert kw==dict(qos=0,retain=False)
        prefix,key,suffix=topic.split("/",2);assert prefix=="fixture"
        pending.append((key,suffix,payload))
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe);monkeypatch.setattr(mqtt,"async_subscribe_connection_status",status)
    monkeypatch.setattr(mqtt,"async_publish",publish)
    async with pair(hass,anchor=q["record_digest"]) as peer:
        runtime=connection=client=None
        async def start(key):
            nonlocal runtime,connection,client
            phase[0]=key;assert await integration.async_setup_entry(hass,parent)
            state=hass.data["open_thermostat"][parent.entry_id]
            runtime=state["v1_runtime"];connection=state["v1_connection"];client=connection.client
            client.clock=lambda:peer.clock[0]
            if key=="v2":client.journal.clock=lambda:peer.clock[0]
            else:
                for r in (rad,floor):runtime.set_report_profile(r.room_id,source_profile)
            if n:=holder.get("n"):n.runtime,n.connection,n.client=runtime,connection,client
        async def stop():
            assert await integration.async_unload_entry(hass,parent);await parent._async_process_on_unload(hass)
            assert connection.worker.done() and connection.timer is None
            assert not runtime._subscriptions and not runtime._expiries
        async def deliver(frames,drop=None,retained=False):
            for f in frames:
                if f["topic"]==drop:continue
                callbacks[phase[0]](SimpleNamespace(topic="fixture/"+phase[0]+"/"+f["topic"],payload=f["raw"],retain=retained))
                await connection.queue.join()
        async def event(op,**kw):
            r=await peer.request(op,**kw);await deliver(r["frames"]);return r
        async def drain():
            for _ in range(100):
                await connection.queue.join()
                if not pending:return
                key,topic,raw=pending.popleft();assert key==phase[0]
                await event("receive",topic=topic,raw=raw)
            raise AssertionError("bounded existing single worker/peer queues")
        def flow():
            f=ShadowOptionsFlow();f.hass=hass;f.handler=parent.entry_id;return f
        async def apply():
            f=flow();r=await f.async_step_init({"graph_action":"prepare"})
            assert r["step_id"]=="graph_review",r
            assert client.journal.status=="graph_staged_not_applied"
            assert (await peer.request("status"))["writes"]==0
            await f.async_step_graph_review({"confirm_apply":True});await drain()
            assert client.graph_ready and client.ready is False and not runtime.transport_ready
            status_form=await f.async_step_graph_status()
            assert status_form["description_placeholders"]["control_status"]=="DATA verification never grants control; a separate SOURCE review is required"
            record=client.journal.state["accepted"];key=client.journal.review_key(record,client._context())
            assert await client.async_reviewed_handoff_data(key)==record
            return record
        def source(record):
            cp=ControllerPolicySourceProfile(parent.unique_id,"e32_test","test_owner","b"*64,"0"*64)
            result=GraphFloorControllerEntrySource(cp,cx,review,("physical_report","physical_report"),
                graph=data_profile,accepted_record_json=canonical(record))
            result=replace(result,controller=replace(cp,config_digest=digest(result.projection())))
            result.validate()
            return result
        def ctor(profile):
            record=profile.data_record()
            return dict(bridge_version=VERSION,profile_version="two-room-targets.v1",review_json=profile.review_json,
                review_digest=digest(json.loads(profile.review_json)),expected_profile_digest=profile.controller.profile_digest,
                profile_digest=profile.controller.profile_digest,control_digest=profile.controller.config_digest,
                context=asdict(profile.context),graph=dict(qualification_digest=q["record_digest"],
                    config_digest=record["config_digest"],mapping_digest=digest(record["mapping"]),
                    revision=record["config"]["revision"],mapping_revision=record["mapping"]["mapping_revision"]),
                zones=[dict(zone_id=r["zone_id"],sensor_id="s_"+r["zone_id"],actuator_id=r["actuator_id"],
                    minimum=r["minimum_target_centi_c"],maximum=r["maximum_target_centi_c"],evidence="physical_report",
                    emitter=r["emitter"]) for r in plan["rooms"]])
        async def control(record,remote_mutation=None):
            profile=source(record);wire=ctor(profile)
            if remote_mutation:remote_mutation(wire)
            old_worker=connection.worker;await stop();await peer.request("disconnect")
            assert old_worker.done() and not pending
            selected=await peer.request("select_graph_floor_source",source=wire)
            monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
            monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(profile,))
            await start("v1")
            assert client.journal["accepted"] is None and client.journal["staged"]["config"]==profile.projection()
            holder["n"].profile=profile;holder["n"].ctor=wire;holder["n"].selected=selected
            if path:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
                disk=await peer.request("durable_readback")
                (Path(path).parent/"SOURCE-FIXTURE.json").write_text(canonical(dict(stored=disk["stored"],source=wire))+chr(10))
            await event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
            await event("connect");await event("tick");await drain()
            return profile
        serial=0
        async def samples(ta,tb):
            nonlocal serial
            for _ in range(2):
                serial+=1
                for r,t in ((rad,ta),(floor,tb)):
                    physical_state(hass,r,key=f"bridge_{r.room_id}_{serial}",value=str(t))
                await hass.async_block_till_done();await drain()
        async def settle(ta,tb):
            for _ in range(121):
                peer.clock[0]+=1;await client.poll();await drain()
                await event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
                await samples(ta,tb);await event("tick");await drain()
        async def command(awaitable):
            task=asyncio.create_task(awaitable)
            try:
                for _ in range(300):
                    await connection.queue.join()
                    if pending:
                        key,topic,raw=pending.popleft();assert key==phase[0];await event("receive",topic=topic,raw=raw)
                    elif task.done():return await task
                    else:await asyncio.sleep(.001)
                raise AssertionError("bounded existing command")
            finally:
                if not task.done():task.cancel()
                await asyncio.gather(task,return_exceptions=True)
        await start("v2")
        n=SimpleNamespace(parent=parent,rad=rad,floor=floor,heating=heating,output=output,feedback=feedback,
            data_profile=data_profile,scope=scope,cx=cx,review=review,plan=plan,peer=peer,runtime=runtime,
            connection=connection,client=client,phase=phase,callbacks=callbacks,pending=pending,
            start=start,stop=stop,event=event,deliver=deliver,drain=drain,apply=apply,source=source,ctor_for=ctor,
            control=control,samples=samples,settle=settle,command=command,flow=flow)
        holder["n"]=n
        try:
            await event("connect");await event("tick");await drain()
            yield n
        finally:
            if hass.data.get("open_thermostat",{}).get(parent.entry_id,{}).get("v1_runtime") is not None:await stop()
            assert not physical_calls and not pending
            assert removed.count("v1_mqtt")==removed.count("v1_status")
            assert removed.count("v2_mqtt")==removed.count("v2_status")

@pytest.mark.asyncio
@pytest.mark.parametrize("temperature,expected",[((16,22),(True,False)),((23,16),(False,True)),((16,16),(True,True)),((23,22),(False,False))])
async def test_real_saved_two_rooms_floor_DATA_apply_same_store_two_control_targets(bridge,temperature,expected):
    n=bridge;record=await n.apply()
    assert len(record["config"]["rooms"])==1 and record["config"]["rooms"][0]["zone_id"]==n.floor.room_id
    assert not n.runtime.decisions
    original=await n.peer.request("durable_readback")
    assert original["writes"]==1
    await n.control(record)
    assert n.client.ready and n.runtime.transport_ready
    await n.settle(*temperature)
    states=[n.runtime.decisions[r.room_id] for r in (n.rad,n.floor)]
    assert tuple(s.demand for s in states)==expected, states
    assert tuple(s.target_centi_c for s in states)==(2100,1900)
    assert (await n.peer.request("durable_readback"))["stored"]==original["stored"]
    assert (await n.peer.request("durable_readback"))["writes"]==1
    for r in (n.rad,n.floor):
        attrs=ShadowRoom("fixture",r,n.runtime).extra_state_attributes
        assert attrs["control_scope"]==VERSION and attrs["source_config_readback_verified"]
        assert attrs["graph_DATA_grants_control"] is attrs["actuator_output_enabled"] is False
    emit(dict(scenario="actual_apply_then_two_source_targets",temperatures=temperature,demand=expected,
        targets=[2100,1900],data_rooms=1,native_source_targets=2,store_bytes=len(original["stored"].encode()),
        projected_bytes=len(canonical(n.profile.projection()).encode()),writes=1,
        no_firmware_review_preload=True,physical_outputs_enabled=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("change",["rad_target","floor_cycle","schedule","owner","missing_output","unsupported_floor"])
async def test_native_changes_are_rejected_before_DATA_stage_or_publish(bridge,hass,change):
    n=bridge;original=deepcopy(n.client.journal.state)
    if change in ("rad_target","schedule"):
        sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
        data=dict(sub.data)
        if change=="rad_target":data["base_centi_c"]=2200
        else:data["week_program"]={"monday":[]}
        hass.config_entries.async_update_subentry(n.parent,sub,data=data)
    elif change=="owner":
        hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"another_owner"})
    elif change=="missing_output":er.async_get(hass).async_remove(n.output.entity_id)
    else:
        data=deepcopy(dict(n.heating.data))
        a=next(a for a in data["draft"]["actuators"] if a["room_id"]==n.floor.room_id)
        if change=="floor_cycle":a["settings"]["cycle_s"]=1200
        else:a["profile"]="proportional_valve"
        hass.config_entries.async_update_subentry(n.parent,n.heating,data=data)
    await hass.async_block_till_done()
    result=await n.flow().async_step_init({"graph_action":"prepare"})
    assert result["type"]=="abort" and result["reason"]=="graph_prepare_failed"
    assert n.client.journal.state==original and (await n.peer.request("status"))["writes"]==0
    assert not n.pending and not n.runtime.decisions

@pytest.mark.asyncio
@pytest.mark.parametrize("wrong",["data_digest","mapping","revision","version","profile","control_digest","floor_mode"])
async def test_remote_SOURCE_tuple_or_profile_mismatch_never_admits_control(bridge,wrong):
    n=bridge;record=await n.apply();before=await n.peer.request("durable_readback")
    def mutate(src):
        if wrong=="data_digest":src["graph"]["config_digest"]="0"*64
        elif wrong=="mapping":src["graph"]["mapping_digest"]="0"*64
        elif wrong=="revision":src["graph"]["revision"]+=1
        elif wrong=="version":src["bridge_version"]="graph-floor-native-trv.v999"
        elif wrong=="profile":src["profile_digest"]="0"*64
        elif wrong=="control_digest":src["control_digest"]="0"*64
        else:next(r for r in src["zones"] if r["emitter"]=="floor")["emitter"]="radiator"
    await n.control(record,mutate)
    assert not n.client.ready and not n.runtime.decisions
    assert n.client.journal["accepted"] is None
    after=await n.peer.request("durable_readback")
    assert after["stored"]==before["stored"] and after["writes"]==before["writes"]==1

@pytest.mark.asyncio
async def test_staged_or_ACK_only_data_cannot_start_SOURCE_caller(bridge,hass,monkeypatch):
    n=bridge
    result=await n.flow().async_step_init({"graph_action":"prepare"})
    assert result["step_id"]=="graph_review"
    staged=n.client.journal.state["staged"];profile=n.source(staged)
    with pytest.raises(GraphValidationError,match="bridge_exact_readback_required"):
        await profile.async_configuration(hass,n.parent)
    assert (await n.peer.request("status"))["writes"]==0
    assert n.client.journal.state["accepted"] is None and n.runtime.decisions=={}

@pytest.mark.asyncio
async def test_existing_SOURCE_profile_does_not_follow_new_DATA_revision(bridge,hass):
    n=bridge;record=await n.apply();profile=n.source(record)
    second=deepcopy(record);second["config"]["revision"]+=1;second["config_digest"]=digest(second["config"])
    with pytest.raises(GraphValidationError,match="bridge_revision"):
        n.source(second)
    wrong=replace(profile,profile_version="graph-floor-native-trv.v999")
    with pytest.raises(GraphValidationError,match="bridge_profile_version"):wrong.validate()
    assert await profile.async_configuration(hass,n.parent)
    assert (await n.peer.request("status"))["writes"]==1 and not n.runtime.transport_ready

@pytest.mark.asyncio
async def test_control_stop_dhw_and_unknown_second_sensor_keep_isolation(bridge):
    n=bridge;await n.control(await n.apply());await n.settle(16,16)
    assert all(d.demand for d in n.runtime.decisions.values()), n.runtime.decisions
    await n.samples(16,"unknown")
    assert n.runtime.decisions[n.rad.room_id].demand and not n.runtime.decisions[n.floor.room_id].demand
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,all_off=True)
    await n.samples(16,16);assert all(not d.demand for d in n.runtime.decisions.values())
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,dhw_active=True)
    await n.samples(16,16);assert all(not d.demand for d in n.runtime.decisions.values())
    for r in (n.rad,n.floor):
        await n.command(ShadowRoom("fixture",r,n.runtime).async_set_hvac_mode("off"))
    assert all(d.target_centi_c is None for d in n.runtime.decisions.values())
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
async def test_reboot_reload_reconnect_never_restores_old_observation_grant_or_override(bridge):
    n=bridge;await n.control(await n.apply());await n.settle(16,16)
    await n.command(n.runtime.async_set_temperature(n.rad.room_id,22))
    assert n.runtime.decisions[n.rad.room_id].target_centi_c==2200
    grant=n.client.session["grant_id"]
    old=next(k["raw"] for op,k,_ in reversed(n.peer.trace) if op=="receive" and k.get("topic")=="ha/observations")
    disk=await n.peer.request("durable_readback")
    await n.stop();await n.start("v1")
    assert not n.client.ready
    await n.event("disconnect");await n.event("reboot",boot="bridge_new_boot")
    await n.event("connect");await n.event("tick");await n.drain()
    assert n.client.ready and n.client.session["grant_id"]!=grant
    await n.event("receive",topic="ha/observations",raw=old);await n.drain()
    assert all(not d.demand for d in n.runtime.decisions.values())
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
    await n.samples(16,16)
    assert [n.runtime.decisions[r.room_id].target_centi_c for r in (n.rad,n.floor)]==[2100,1900]
    assert (await n.peer.request("durable_readback"))["stored"]==disk["stored"]
    assert (await n.peer.request("durable_readback"))["writes"]==1

@pytest.mark.asyncio
async def test_explicit_rollback_to_DATA_keeps_original_store_and_never_resumes_control(bridge,monkeypatch):
    n=bridge;record=await n.apply();await n.control(record);await n.settle(16,16)
    disk=await n.peer.request("durable_readback")
    await n.stop();await n.event("disconnect")
    await n.peer.request("select_data_source")
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",n.data_profile)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",())
    await n.start("v2");assert not n.client.graph_ready
    await n.event("connect");await n.event("tick");await n.drain()
    assert n.client.graph_ready and n.client.ready is False and not n.runtime.transport_ready
    assert not n.runtime.decisions
    assert (await n.peer.request("durable_readback"))["stored"]==disk["stored"]
    assert (await n.peer.request("durable_readback"))["writes"]==1

@pytest.mark.asyncio
async def test_SOURCE_store_await_and_native_edit_cannot_preserve_old_authority(bridge,hass,monkeypatch):
    n=bridge;record=await n.apply();await n.control(record);assert n.client.ready
    from custom_components.open_thermostat.graph_shadow_storage import native_graph_journal
    journal=native_graph_journal(hass,n.parent,n.data_profile.qualification_digest)
    original=journal.store.async_load;fired=False
    async def load():
        nonlocal fired
        result=await original()
        if not fired:
            fired=True
            sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
            hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2200})
            await hass.async_block_till_done()
        return result
    monkeypatch.setattr(journal.store,"async_load",load)
    with pytest.raises(GraphValidationError):
        await n.profile.async_configuration(hass,n.parent)
    assert fired and not n.client.ready and not n.runtime.decisions
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
async def test_retained_hello_snapshot_never_makes_DATA_or_source_ready(bridge):
    n=bridge;result=await n.peer.request("status")
    n.callbacks["v2_status"](False);await n.connection.queue.join()
    frames=await n.peer.request("connect")
    await n.deliver(frames["frames"],retained=True)
    assert not n.client.graph_ready and n.client.ready is False and not n.pending
    assert not n.runtime.transport_ready and (await n.peer.request("status"))["writes"]==0


@pytest.mark.asyncio
@pytest.mark.parametrize("change",["owner","context","schema","missing","journal"])
async def test_native_SOURCE_review_or_journal_mismatch_rejects_before_control_mirror(bridge,hass,monkeypatch,change):
    n=bridge;record=await n.apply();profile=n.source(record)
    if change=="owner":profile=replace(profile,controller=replace(profile.controller,adapter_id="another_owner"))
    elif change=="context":profile=replace(profile,context=replace(profile.context,source_revision=2))
    elif change=="schema":profile=replace(profile,schema=999)
    elif change=="missing":profile=None
    else:
        state=n.client.journal.state;state["accepted"]["config"]["revision"]+=1
        await n.client.journal.store.async_save(state)
    disk=await n.peer.request("durable_readback")
    await n.stop();await n.peer.request("disconnect")
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",() if profile is None else (profile,))
    with pytest.raises((ConfigEntryError,ValueError)):
        await n.start("v1")
    state=hass.data.get("open_thermostat",{}).get(n.parent.entry_id,{})
    assert "v1_connection" not in state and not n.pending
    after=await n.peer.request("durable_readback")
    assert after["stored"]==disk["stored"] and after["writes"]==1

@pytest.mark.asyncio
async def test_DATA_ACK_without_snapshot_stays_pending_and_cannot_supply_SOURCE_review(bridge,hass):
    n=bridge;f=n.flow()
    assert (await f.async_step_init({"graph_action":"prepare"}))["step_id"]=="graph_review"
    await f.async_step_graph_review({"confirm_apply":True})
    for _ in range(30):
        await n.connection.queue.join()
        if not n.pending:break
        key,topic,raw=n.pending.popleft();assert key=="v2"
        result=await n.peer.request("receive",topic=topic,raw=raw)
        await n.deliver(result["frames"],drop="fw/config_snapshot")
    assert (await n.peer.request("status"))["writes"]==1
    assert n.client.journal.state["accepted"] is None and n.client.journal.state["staged"] is not None
    assert not n.client.graph_ready and not n.runtime.transport_ready
    candidate=n.source(n.client.journal.state["staged"])
    with pytest.raises(GraphValidationError,match="bridge_exact_readback_required"):
        await candidate.async_configuration(hass,n.parent)
    assert not n.runtime.decisions


@pytest.mark.asyncio
async def test_changed_review_registry_revision_does_not_silently_reuse_old_floor_mapping(bridge):
    n=bridge;record=await n.apply();profile=n.source(record)
    context=replace(profile.context,registry_revision=profile.context.registry_revision+1)
    review=json.loads(profile.review_json);review["registry_revision"]=context.registry_revision;review=canonical(review)
    draft=replace(n.scope,context=context,review_json=review)
    graph=replace(n.data_profile,draft_source=draft)
    bad=replace(profile,context=context,review_json=review,graph=graph)
    bad=replace(bad,controller=replace(bad.controller,config_digest=digest(bad.projection())))
    with pytest.raises(GraphValidationError,match="bridge_registry_revision"):bad.validate()
    assert (await n.peer.request("status"))["writes"]==1 and not n.runtime.transport_ready

@pytest.mark.asyncio
async def test_ambiguous_DATA_commit_remains_unconfirmed_no_retry_or_SOURCE_admission(bridge,hass):
    n=bridge;f=n.flow()
    assert (await f.async_step_init({"graph_action":"prepare"}))["step_id"]=="graph_review"
    record=n.client.journal.state["staged"];await n.peer.request("ambiguous")
    await f.async_step_graph_review({"confirm_apply":True});await n.drain()
    status=await n.peer.request("status")
    assert status["fault"] and status["writes"]==1
    assert not n.client.graph_ready and n.client.journal.state["accepted"] is None
    candidate=n.source(record)
    with pytest.raises(GraphValidationError,match="bridge_exact_readback_required"):
        await candidate.async_configuration(hass,n.parent)
    assert (await n.peer.request("status"))["writes"]==1
    assert not n.runtime.decisions and not n.pending


@pytest.mark.asyncio
async def test_native_edit_during_control_Store_load_rejects_before_first_mirror_stage(bridge,hass,monkeypatch):
    from homeassistant.helpers.storage import Store
    import custom_components.open_thermostat.v1_mqtt as connection_module
    n=bridge;record=await n.apply();profile=n.source(record)
    await n.stop();await n.peer.request("disconnect")
    control_store=Store(hass,1,"open_thermostat.v1."+n.parent.entry_id)
    empty={"accepted":None,"staged":None};await control_store.async_save(empty)
    real=control_store.async_load;loads=0
    async def load():
        nonlocal loads
        value=await real();loads+=1
        if loads==2:
            sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
            hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2200})
        return value
    monkeypatch.setattr(control_store,"async_load",load)
    monkeypatch.setattr(connection_module,"Store",lambda *a,**k:control_store)
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(profile,))
    with pytest.raises(ValueError):
        await n.start("v1")
    assert loads>=2
    assert await real()==empty # A post-stage setup failure is NOT enough.
    assert not n.pending and (await n.peer.request("status"))["writes"]==1


@pytest.mark.asyncio
async def test_actual_native_status_form_distinguishes_DATA_and_SOURCE_without_new_IO(bridge,hass):
    from homeassistant.helpers.data_entry_flow import FlowManagerIndexView
    n=bridge;record=await n.apply()
    data_form=await n.flow().async_step_graph_status()
    assert data_form["step_id"]=="graph_status" and data_form["description_placeholders"]["verified"]=="True"
    assert "separate SOURCE review" in data_form["description_placeholders"]["control_status"]
    await n.control(record)
    before=len(n.peer.trace);journal=deepcopy(n.client.journal)
    f=n.flow();form=await f.async_step_init({"graph_action":"status"})
    assert form["step_id"]=="graph_source_status"
    assert form["description_placeholders"]["verified"]=="True"
    assert form["description_placeholders"]["profile"]==VERSION
    assert form["description_placeholders"]["scope"].startswith("2 ")
    rendered=FlowManagerIndexView(hass.config_entries.options)._prepare_result_json(form)
    assert rendered["data_schema"] and rendered["step_id"]=="graph_source_status"
    assert (await f.async_step_graph_source_status({"status_action":"refresh"}))["step_id"]=="graph_source_status"
    assert (await f.async_step_graph_prepare())["reason"]=="graph_prepare_unavailable"
    assert (await f.async_step_graph_source_status({"status_action":"close"}))["reason"]=="graph_review_complete"
    assert n.client.journal==journal and len(n.peer.trace)==before and not n.pending

@pytest.mark.asyncio
async def test_native_source_status_after_review_fence_never_reports_control_ready(bridge):
    n=bridge;await n.control(await n.apply());assert n.client.ready
    n.client.require_graph_source_review()
    before=len(n.peer.trace)
    form=await n.flow().async_step_graph_status()
    assert form["step_id"]=="graph_source_status"
    assert form["description_placeholders"]["verified"]=="False"
    assert "review required" in form["description_placeholders"]["control_status"]
    assert len(n.peer.trace)==before and not n.runtime.decisions and not n.pending
