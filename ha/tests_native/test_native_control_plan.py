"""Actual native HA forms/Store -> same C++controller complete plan, no devices."""
import asyncio,json,os
from collections import deque
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest,pytest_asyncio
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.native_plan import (
    NativePlanSource,NativeInstallationPolicy,CONTRACT,_native_layout)
from custom_components.open_thermostat.graph_shadow_validation import canonical,digest,GraphValidationError
from custom_components.open_thermostat.v1_model import EntityReference
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow
from custom_components.open_thermostat.v1_climate import ShadowRoom
from test_graph_topology_review import native_two
from test_graph_owner_interop import pair
from test_v1_native import physical_state,source_profile

@pytest_asyncio.fixture
async def native_plan(native_two,hass,monkeypatch,request):
    options=request.param if hasattr(request,"param") and type(request.param) is dict else {}
    legacy=options.get("legacy",False)
    parent,rad,floor,heating,output=native_two
    floor=replace(floor,base_centi_c=1900)
    sub=next(s for s in parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==floor.room_id)
    hass.config_entries.async_update_subentry(parent,sub,data=floor.as_dict())
    if options.get("single",False):
        assert hass.config_entries.async_remove_subentry(parent,sub.subentry_id)
        draft=deepcopy(heating.data["draft"])
        draft["groups"]=[g for g in draft["groups"] if g["group_id"]=="radiators"]
        draft["actuators"]=[a for a in draft["actuators"] if a["room_id"]==rad.room_id]
        hass.config_entries.async_update_subentry(parent,heating,data={"draft":draft})
    hass.config_entries.async_update_entry(parent,options={**parent.options,"shadow_enabled":True,"adapter_id":"test_owner"})
    rooms,draft,layout=_native_layout(hass,parent,allow_single=options.get("week",False))
    # Independent synthetic SOURCE fixture, selected once before ANY plan.
    # This helper is deliberately test-only: production has NO GUI qualification.
    rows=[];bindings={}
    for room in rooms:
        a=next(a for a in layout["actuators"] if a["room_id"]==room.room_id)
        group=next(g for g in layout["groups"] if g["group_id"]==a["group_id"])
        output_ref=draft.bindings_document()[a["output_channel"]]
        sensor_id=(options.get("sensor_prefix","s_") if options else getattr(request,"param","s_"))+room.room_id
        bindings[sensor_id]=room.temperature.as_dict();bindings[a["actuator_id"]]=output_ref
        control=dict(mode="local_trv",hysteresis_centi_c=20,kp_permille_per_c=0,ki_permille_per_c_minute=0,
            cycle_ms=0,minimum_on_ms=0,minimum_off_ms=0)
        if group["emitter"]=="floor":
            control.update(mode="slow_binary_pi",kp_permille_per_c=500,ki_permille_per_c_minute=10,
                cycle_ms=a["settings"]["cycle_s"]*1000,minimum_on_ms=a["settings"]["minimum_on_s"]*1000,
                minimum_off_ms=a["settings"]["minimum_off_s"]*1000)
        rows.append(dict(zone_id=room.room_id,sensor_id=sensor_id,actuator_id=a["actuator_id"],group_id=a["group_id"],
            emitter=group["emitter"],actuator_profile=a["profile"],control=control,
            sensor_resource=digest({"native_registry_identity":list(room.temperature.identity())}),
            output_resource=digest({"native_registry_identity":list(EntityReference.from_dict(output_ref).identity())}),
            minimum_target_centi_c=room.minimum_target_centi_c,maximum_target_centi_c=room.maximum_target_centi_c,
            maximum_sensor_age_ms=120000,report_evidence="physical_report",
            minimum_supply_centi_c=group["supply_limits"]["minimum_centi_c"],
            maximum_supply_centi_c=group["supply_limits"]["maximum_centi_c"]))
    body=dict(schema=1,kind="native_profile.shadow.v1",controller_id="e32_test",adapter_id="test_owner",
        layout_digest=digest(layout),mapping_revision=1,zones=rows)
    if legacy:body.update(schema=2,kind="native_profile.shadow.v2",legacy_readback="schema1_quarantine_only")
    week=options.get("week",False)
    if week:body.update(schema=3,kind="native_profile.week.v1")
    policy=NativeInstallationPolicy(parent.unique_id,"e32_test","test_owner",digest(body),legacy_readback_reviewed=legacy,week_reviewed=week)
    source=NativePlanSource(policy,canonical(body),canonical(bindings));source.validate()
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",(source,))
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",())
    monkeypatch.setattr(integration,"_CONTROLLER_POLICY_SOURCE_PROFILES",())
    monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",AsyncMock())
    monkeypatch.setattr(hass.config_entries,"async_unload_platforms",AsyncMock(return_value=True))
    reload=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    callbacks={};pending=deque();removed=[];physical_calls=[]
    hass.services.async_register("climate","set_temperature",lambda call:physical_calls.append(call))
    async def subscribe(_h,topic,cb,**kw):callbacks["mqtt"]=cb;return lambda:removed.append("mqtt")
    def status(_h,cb):callbacks["status"]=cb;return lambda:removed.append("status")
    async def publish(_h,topic,payload,**kw):
        assert kw==dict(qos=0,retain=False) and topic.startswith("fixture/v1/")
        pending.append((topic[len("fixture/v1/"):],payload))
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    monkeypatch.setattr(mqtt,"async_subscribe_connection_status",status);monkeypatch.setattr(mqtt,"async_publish",publish)
    legacy_record=None
    if legacy:
        from homeassistant.helpers.storage import Store
        from custom_components.open_thermostat.v1_model import ROOM_CLIMATE_TRV
        oldroom=replace(rad,binding_mode=ROOM_CLIMATE_TRV,
            actuators=(EntityReference.from_dict(bindings[rows[0]["actuator_id"]]),))
        mapping=dict(rooms=[oldroom.as_dict()],source_policy="qualified-physical-report/v1",actuation="disabled-shadow")
        cfg=dict(schema=1,mode="shadow",revision=1,mapping_digest=digest(mapping),zones=[
            dict(zone_id=rad.room_id,sensor_id="s_"+rad.room_id,actuator_id="a_"+rad.room_id,
                base_centi_c=rad.base_centi_c,max_age_ms=rad.maximum_age_ms,
                report_evidence="physical_report",schedule=None)])
        legacy_record=dict(config=cfg,config_digest=digest(cfg),mapping=mapping)
        await Store(hass,1,"open_thermostat.v1."+parent.entry_id).async_save(
            {"accepted":None,"staged":legacy_record} if options.get("old_stage") else {"accepted":legacy_record,"staged":None})
    async with pair(hass) as peer:
        if options.get("local_source",False):
            from custom_components.open_thermostat.native_provisioning import local_device_descriptor
            initial=await peer.request("initialize_native_local_source",controller="e32_test",boot="native_boot",
                owner="test_owner",stored=canonical(legacy_record["config"]) if legacy else "",
                local_source=canonical(local_device_descriptor(source)))
        else:
            initial=await peer.request("initialize_native_plan",controller="e32_test",boot="native_boot",
                owner="test_owner",stored=canonical(legacy_record["config"]) if legacy else "",
                source=dict(profile_digest=policy.profile_digest,mapping_revision=1,zones=rows,legacy_readback_reviewed=legacy))
        assert not initial["fault"] and initial["writes"]==0 and initial["revision"]==(1 if legacy else 0)
        runtime=connection=client=None;holder={};serial=0;epoch=int(dt.utcnow().timestamp());receive_errors=[]
        async def start():
            nonlocal runtime,connection,client
            assert await integration.async_setup_entry(hass,parent)
            state=hass.data["open_thermostat"][parent.entry_id]
            runtime=state["v1_runtime"];connection=state["v1_connection"];client=connection.client
            client.clock=lambda:peer.clock[0]
            actual_receive=client._receive
            async def audited_receive(topic,payload):
                try:return await actual_receive(topic,payload)
                except Exception as error:
                    receive_errors.append(dict(topic=topic,payload=payload,error=type(error).__name__,message=str(error)))
                    raise
            client._receive=audited_receive # Transparent diagnostic boundary only.
            for r in runtime.rooms.values():runtime.set_report_profile(r.room_id,source_profile)
            if n:=holder.get("n"):n.runtime,n.connection,n.client=runtime,connection,client
        async def stop():
            assert await integration.async_unload_entry(hass,parent);await parent._async_process_on_unload(hass)
            assert connection.worker.done() and connection.timer is None
            assert not runtime._subscriptions and not runtime._expiries
        async def deliver(frames,drop=None,retained=False):
            for f in frames:
                if f["topic"]==drop:continue
                callbacks["mqtt"](SimpleNamespace(topic="fixture/v1/"+f["topic"],payload=f["raw"],retain=retained))
                await connection.queue.join()
        async def event(op,**kw):
            result=await peer.request(op,utc=epoch+int(peer.clock[0]-100),**kw)
            await deliver(result["frames"]);return result
        async def drain():
            for _ in range(120):
                await connection.queue.join()
                if not pending:return
                topic,raw=pending.popleft();await event("receive",topic=topic,raw=raw)
            raise AssertionError("bounded existing worker/finite peer")
        async def handshake():
            for _ in range(22):
                await event("tick");await client.poll();await drain()
                if client._native_remote_known:return
                peer.clock[0]+=1
            raise AssertionError(dict(error=client.error,identity=client.identity,session=client.session))
        def flow():
            f=ShadowOptionsFlow();f.hass=hass;f.handler=parent.entry_id;return f
        async def apply():
            form=flow();review=await form.async_step_init({"graph_action":"prepare"})
            assert review["type"]=="form" and review["step_id"]=="graph_review",review
            staged=deepcopy(client.journal["staged"])
            assert staged is not None and not client.ready
            result=await form.async_step_graph_review({"confirm_apply":True});await drain()
            await handshake()
            assert client.ready and runtime.transport_ready,dict(error=client.error,result=result)
            return staged
        async def samples(ta,tb):
            nonlocal serial
            for _ in range(2):
                serial+=1
                for r,t in ((rad,ta),(floor,tb)):
                    physical_state(hass,r,key=f"native_{r.room_id}_{serial}",value=str(t))
                await hass.async_block_till_done();await drain()
        async def settle(ta,tb):
            for _ in range(121):
                peer.clock[0]+=1
                await client.poll();await drain()
                await event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
                await samples(ta,tb);await event("tick");await drain()
        async def command(awaitable):
            task=asyncio.create_task(awaitable)
            try:
                for _ in range(300):
                    await connection.queue.join()
                    if pending:
                        topic,raw=pending.popleft();await event("receive",topic=topic,raw=raw)
                    elif task.done():return await task
                    else:await asyncio.sleep(.001)
                raise AssertionError("bounded native command")
            finally:
                if not task.done():task.cancel()
                await asyncio.gather(task,return_exceptions=True)
        await start()
        n=SimpleNamespace(parent=parent,rad=rad,floor=floor,heating=heating,source=source,policy=policy,
            profile=body,bindings=bindings,legacy_record=legacy_record,peer=peer,runtime=runtime,connection=connection,client=client,
            callbacks=callbacks,pending=pending,start=start,stop=stop,event=event,deliver=deliver,drain=drain,
            handshake=handshake,flow=flow,apply=apply,samples=samples,settle=settle,command=command,reload=reload)
        holder["n"]=n
        try:
            await event("connect");await handshake()
            assert not client.ready and not runtime.transport_ready
            yield n
        finally:
            if path:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
                target=Path(path).parent/(request.node.name.replace("/","_")+".TRACE.json")
                target.write_text(json.dumps(dict(receive_errors=receive_errors,peer_trace=peer.trace,
                    source=body,status=client.error,journal=client.journal),indent=2)+"\n")
            if hass.data.get("open_thermostat",{}).get(parent.entry_id,{}).get("v1_runtime") is not None:await stop()
            assert not physical_calls and not pending
            assert removed.count("mqtt")==removed.count("status")

@pytest.mark.asyncio
async def test_normal_HA_review_apply_commits_TWO_complete_rooms_and_same_controller_targets(native_plan):
    n=native_plan
    assert not n.client.ready and not n.pending
    before=await n.peer.request("durable_readback")
    assert before["stored"]=="" and before["writes"]==0
    record=await n.apply()
    actual=await n.peer.request("durable_readback");config=json.loads(actual["stored"])
    assert config==record["config"] and config["schema"]==2 and config["mode"]=="shadow_plan"
    assert len(config["zones"])==len(config["groups"])==2 and len(config["mapping"]["channels"])==4
    assert actual["writes"]==1 and actual["store_bytes"]<=4096
    assert [z["base_centi_c"] for z in config["zones"]]==[2100,1900]
    assert n.client.journal["accepted"]==record and n.client.journal["staged"] is None
    assert n.runtime.graph_controller_source is None and n.runtime.graph_data_profile is None
    assert actual["status"]=="native_complete_plan"
    await n.settle(16,22)
    assert tuple(n.runtime.decisions[r.room_id].demand for r in (n.rad,n.floor))==(True,False)
    assert tuple(n.runtime.decisions[r.room_id].target_centi_c for r in (n.rad,n.floor))==(2100,1900)
    for r in (n.rad,n.floor):
        attrs=ShadowRoom("fixture",r,n.runtime).extra_state_attributes
        assert attrs["control_scope"]==CONTRACT and attrs["source_config_readback_verified"]
        assert attrs["graph_DATA_grants_control"] is attrs["actuator_output_enabled"] is False
    if path:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(path).open("a") as f:f.write(canonical(dict(scenario="native_full_two_room_plan",store_bytes=actual["store_bytes"],
            zones=2,groups=2,channels=4,targets=[2100,1900],writes=1,no_projection=True,physical_outputs=False))+chr(10))


@pytest.mark.asyncio
async def test_same_installation_profile_accepts_target_schedule_edit_readback_and_OFF(native_plan,hass):
    from custom_components.open_thermostat.v1_program import normalize_program
    from custom_components.open_thermostat.schedule_compiler import WEEKDAYS
    n=native_plan;first=await n.apply();source=n.source
    old_digest=source.policy.profile_digest
    program=normalize_program({day:[{"start":0,"end":86400,"target_centi_c":2200}] for day in WEEKDAYS},1600,2400)
    sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
    # Ordinary native edit/update-listener/reload, not a SOURCE factory change.
    hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2300,"week_program":program})
    await hass.async_block_till_done()
    assert not n.client.ready
    await n.stop();await n.start()
    assert integration._selected_native_plan_source(n.parent) is source
    await n.handshake()
    assert not n.client.ready and n.client.journal["accepted"]==first
    second=await n.apply()
    assert second["config"]["revision"]==2 and second["config_digest"]!=first["config_digest"]
    assert source.policy.profile_digest==old_digest==second["config"]["profile_digest"]
    assert len(second["config"]["zones"])==2 and second["config"]["mapping"]==first["config"]["mapping"]
    rad=second["config"]["zones"][0]
    assert rad["base_centi_c"]==2300 and rad["schedule"]["transitions"][0][1]==2200
    await n.settle(16,22)
    assert n.runtime.decisions[n.rad.room_id].target_centi_c==2200
    await n.command(n.runtime.async_hvac_mode(n.rad.room_id,"off"));await n.samples(16,22)
    assert n.runtime.decisions[n.rad.room_id].demand is False
    durable=await n.peer.request("durable_readback")
    assert json.loads(durable["stored"])==second["config"] and durable["writes"]==2
    assert sum(op=="initialize_native_plan" for op,_,_ in n.peer.trace)==1

@pytest.mark.asyncio
@pytest.mark.parametrize("temperatures,expected",[((16,22),(True,False)),((24,16),(False,True)),((16,16),(True,True)),((24,22),(False,False))])
async def test_two_independent_rooms_no_phantom_demand(native_plan,temperatures,expected):
    n=native_plan;await n.apply();await n.settle(*temperatures)
    assert tuple(n.runtime.decisions[r.room_id].demand for r in (n.rad,n.floor))==expected

@pytest.mark.asyncio
async def test_review_cancel_expiry_duplicate_apply_are_not_writes(native_plan):
    n=native_plan
    f=n.flow();assert (await f.async_step_init({"graph_action":"prepare"}))["step_id"]=="graph_review"
    staged=deepcopy(n.client.journal["staged"])
    assert (await f.async_step_graph_review({"confirm_apply":False}))["reason"]=="graph_review_cancelled"
    assert (await n.peer.request("status"))["writes"]==0 and not n.pending and not n.client.ready
    # Cancellation never manufactures a config send, nor silently deletes a durable draft.
    assert n.client.journal["staged"]==staged
    n.client._native_review=(n.client.native_context(),staged["config_digest"],n.peer.clock[0]-301)
    with pytest.raises(ValueError):n.client.review_candidate()
    await n.client.async_prepare_native_plan()
    key=n.client.review_candidate()
    await n.client.async_apply(key)
    with pytest.raises(ValueError):await n.client.async_apply(key)
    assert sum(t=="ha/config" for t,_ in n.pending)==1
    await n.drain();await n.handshake()
    assert n.client.ready and (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("phase",["prepare","apply"])
@pytest.mark.parametrize("cause",["adapter","entry","registry","selected_source","policy","native_room","journal","unregistered"])
async def test_last_native_Store_await_cannot_stage_or_send_after_drift(native_plan,hass,monkeypatch,phase,cause):
    import inspect
    from homeassistant.helpers.storage import Store
    n=native_plan
    if phase=="apply":await n.client.async_prepare_native_plan()
    before=deepcopy(n.client.journal);real=Store.async_load;fired=False
    wanted="async_prepare_native_plan" if phase=="prepare" else "async_apply"
    async def load(store):
        nonlocal fired
        value=await real(store)
        if not fired and store.key=="open_thermostat.v1."+n.parent.entry_id and any(f.function==wanted for f in inspect.stack()):
            fired=True
            if cause=="adapter":n.runtime.adapter_id="another_owner";n.client.adapter_id="another_owner"
            elif cause=="entry":hass.config_entries.async_update_entry(n.parent,unique_id="another_entry")
            elif cause=="unregistered":monkeypatch.setattr(hass.config_entries,"async_get_entry",lambda entry_id:None)
            elif cause=="registry":er.async_get(hass).async_remove(n.rad.temperature.entity_id)
            elif cause=="selected_source":monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
            elif cause=="policy":n.runtime.controller_policy_source_profile=replace(n.policy,profile_digest="c"*64)
            elif cause=="native_room":
                sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
                hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2200})
            else:return {"accepted":None,"staged":{"unknown":"concurrent change"}}
        return value
    monkeypatch.setattr(Store,"async_load",load)
    with pytest.raises(ValueError):
        if phase=="prepare":await n.client.async_prepare_native_plan()
        else:await n.client.async_apply(n.client.review_candidate())
    assert fired and n.client.journal==before
    assert (await n.peer.request("status"))["writes"]==0
    await n.drain()
    assert not any(op=="receive" and kw.get("topic")=="ha/config" for op,kw,_ in n.peer.trace)

@pytest.mark.asyncio
@pytest.mark.parametrize("fault",["save_failure","ambiguous"])
async def test_actual_cpp_commit_failure_retains_pending_until_explicit_fresh_readback(native_plan,fault):
    n=native_plan;await n.client.async_prepare_native_plan();stage=deepcopy(n.client.journal["staged"])
    await n.peer.request(fault)
    await n.client.async_apply(n.client.review_candidate());await n.drain()
    result=await n.peer.request("durable_readback")
    assert result["fault"] and result["writes"]==1 and not n.client.ready
    assert n.client.journal["staged"]==stage and n.client.journal["accepted"] is None
    assert result["stored"]==(canonical(stage["config"]) if fault=="ambiguous" else "")
    await n.stop();await n.peer.request("reboot",boot="recovered_boot");await n.start()
    await n.event("connect");await n.handshake()
    if fault=="ambiguous":
        assert n.client.journal["accepted"]==stage and n.client.journal["staged"] is None and n.client.ready
    else:
        assert n.client.journal["accepted"] is None and n.client.journal["staged"]==stage
        assert not n.client.ready and n.client.error=="native_plan_recovery_review_required"
        assert not any(t=="ha/config" for t,_ in n.pending)
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
async def test_lost_ACK_without_readback_is_never_local_apply(native_plan):
    n=native_plan;await n.client.async_prepare_native_plan();stage=deepcopy(n.client.journal["staged"])
    await n.client.async_apply(n.client.review_candidate())
    topic,raw=n.pending.popleft();assert topic=="ha/config"
    committed=await n.peer.request("receive",topic=topic,raw=raw)
    assert committed["writes"]==1
    # Drop all result/hello frames: actual C++commit alone is not HA acceptance.
    assert n.client.journal["accepted"] is None and n.client.journal["staged"]==stage and not n.client.ready
    await n.stop();await n.start();await n.handshake()
    assert n.client.ready and n.client.journal["accepted"]==stage
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
async def test_reboot_keeps_complete_plan_but_never_override_or_samples(native_plan):
    n=native_plan;record=await n.apply();await n.settle(16,16)
    await n.command(n.runtime.async_set_temperature(n.rad.room_id,23))
    await n.samples(16,16)
    old_session=n.client.session["adapter_session_id"]
    await n.stop();await n.peer.request("reboot",boot="new_boot");await n.start()
    assert not n.client.ready and not n.runtime.decisions
    await n.event("connect");await n.handshake()
    assert n.client.ready and n.client.session["adapter_session_id"]!=old_session
    await n.event("tick")
    assert not any(d.demand for d in n.runtime.decisions.values())
    await n.settle(16,16)
    assert n.runtime.decisions[n.rad.room_id].target_centi_c==2100
    assert n.client.journal["accepted"]==record and (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
async def test_SOURCE_selection_loss_immediately_stops_ready_and_retry(native_plan,monkeypatch):
    n=native_plan;await n.apply()
    assert n.client.ready
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    assert not n.client.ready
    await n.client.poll()
    assert not n.pending and not n.client.ready and n.client.session is None

@pytest.mark.asyncio
@pytest.mark.parametrize("mutation",["future_schema","zero_zones","three_zones","mapping_owner","mapping_resource",
    "mapping_revision","source_profile","group_profile","target_range","source_age","reversed_zones","zone_extra","too_many_transitions","invalid_schedule","oversize"])
async def test_real_cpp_and_HA_reject_invalid_complete_plans_without_changing_bytes(native_plan,mutation):
    n=native_plan;cfg,_=await n.source.async_configuration(n.runtime.hass,n.parent)
    if mutation=="future_schema":cfg["schema"]=3
    elif mutation=="zero_zones":cfg["zones"]=[]
    elif mutation=="three_zones":cfg["zones"].append(deepcopy(cfg["zones"][0]))
    elif mutation=="mapping_owner":cfg["mapping"]["channels"][0]["owner_id"]="another_owner"
    elif mutation=="mapping_resource":cfg["mapping"]["channels"][0]["resource_id"]="f"*64
    elif mutation=="mapping_revision":cfg["mapping"]["mapping_revision"]+=1
    elif mutation=="source_profile":cfg["profile_digest"]="c"*64
    elif mutation=="group_profile":cfg["groups"][0]["maximum_supply_centi_c"]-=100
    elif mutation=="target_range":cfg["zones"][0]["base_centi_c"]=3500
    elif mutation=="source_age":cfg["zones"][0]["max_age_ms"]=120001
    elif mutation=="reversed_zones":cfg["zones"].reverse()
    elif mutation=="zone_extra":cfg["zones"][0]["physical_ready"]=True
    elif mutation in ("too_many_transitions","invalid_schedule"):
        cfg["zones"][0]["schedule"]=dict(base_centi_c=2100,policy="wall-clock-membership/v1",timezone="UTC",
            valid_from_utc=1790000000,valid_until_utc=1790001000,
            transitions=[[1790000000+i*10,2100] for i in range(9 if mutation=="too_many_transitions" else 1)])
        if mutation=="invalid_schedule":cfg["zones"][0]["schedule"]["transitions"][0][0]-=1
    else:cfg["extra"]="x"*4100
    cfg["mapping_digest"]=digest(cfg["mapping"])
    with pytest.raises(ValueError):n.source.validate_plan(cfg)
    before=await n.peer.request("durable_readback")
    await n.client.message("ha/config","config",dict(expected_revision=0,config_digest=digest(cfg),config=cfg))
    await n.drain()
    after=await n.peer.request("durable_readback")
    assert after["stored"]==before["stored"]=="" and after["writes"]==0 and not after["fault"]
    assert not n.client.ready

@pytest.mark.asyncio
@pytest.mark.parametrize("cause",["contract_missing","wrong_source","physical_true","boolean_limit"])
async def test_unqualified_hello_cannot_select_contract(native_plan,cause):
    n=native_plan;hello=next(json.loads(f["raw"]) for _,_,r in n.peer.trace for f in r["frames"] if f["topic"]=="fw/hello")
    await n.client.async_disconnected()
    if cause=="contract_missing":hello["control_capabilities"]=[]
    elif cause=="wrong_source":hello["source_policy"]["profile_digest"]="e"*64
    elif cause=="physical_true":hello["source_policy"]["physical_outputs_enabled"]=True
    else:hello["source_policy"]["limits"]["zones"]=True
    await n.client.receive("fw/hello",canonical(hello))
    assert n.client.session is None and not n.pending and not n.client.ready

@pytest.mark.asyncio
@pytest.mark.parametrize("cause",["retained","boolean_grant","float_sequence","wrong_profile","wrong_request","wrong_owner"])
async def test_snapshot_needs_exact_current_requested_typed_proof(native_plan,cause):
    n=native_plan
    await n.client.message("ha/snapshot_request","snapshot",{})
    topic,raw=n.pending.popleft();response=await n.peer.request("receive",topic=topic,raw=raw)
    snap=next(json.loads(f["raw"]) for f in response["frames"] if f["topic"]=="fw/config_snapshot")
    if cause=="boolean_grant":snap["grant_sequence"]=True
    elif cause=="float_sequence":snap["request_sequence"]=float(snap["request_sequence"])
    elif cause=="wrong_profile":snap["profile_digest"]="d"*64
    elif cause=="wrong_request":snap["request_sequence"]+=1
    elif cause=="wrong_owner":snap["adapter_id"]="another_owner"
    before=n.client._native_snapshot_request
    await n.client.receive("fw/config_snapshot",canonical(snap),retained=cause=="retained")
    assert n.client._native_snapshot_request==before and not n.client.ready
    assert (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
async def test_unknown_remote_plan_never_auto_adopted_or_overwritten(native_plan,hass):
    from homeassistant.helpers.storage import Store
    n=native_plan;await n.apply();await n.stop()
    # Explicit isolated fixture: lose only HA journal, not device durable bytes.
    await Store(hass,1,"open_thermostat.v1."+n.parent.entry_id).async_save({"accepted":None,"staged":None})
    await n.start()
    # Reach a requested conflict response, not a new admission or autooverwrite.
    for _ in range(26):
        await n.event("tick");await n.client.poll();await n.drain()
        if n.client.error=="native_plan_remote_conflict":break
        n.peer.clock[0]+=1
    assert n.client.error=="native_plan_remote_conflict" and not n.client.ready
    with pytest.raises(ValueError):await n.client.async_prepare_native_plan()
    assert (await n.peer.request("status"))["writes"]==1
    assert n.client.journal=={"accepted":None,"staged":None}

@pytest.mark.asyncio
@pytest.mark.parametrize("fault",["hash_failure","hash_reentry","read_failure","readback_mismatch"])
async def test_native_cpp_fail_latch_prevents_success_or_retry_after_hash_or_storage_fault(native_plan,fault):
    n=native_plan;await n.client.async_prepare_native_plan()
    stage=deepcopy(n.client.journal["staged"])
    await n.peer.request(fault)
    await n.client.async_apply(n.client.review_candidate());await n.drain()
    before=await n.peer.request("durable_readback")
    assert before["fault"] and not n.client.ready and n.client.journal["staged"]==stage
    assert n.client.journal["accepted"] is None
    for _ in range(2):
        n.peer.clock[0]+=2;await n.client.poll();await n.drain();await n.event("tick");await n.drain()
    after=await n.peer.request("durable_readback")
    assert after["fault"] and after["writes"]==before["writes"] and after["reads"]==before["reads"]
    assert after["stored"]==before["stored"]
    assert before["writes"]==(0 if fault in ("hash_failure","hash_reentry") else 1)

@pytest.mark.asyncio
async def test_existing_seasonal_stop_and_fresh_safety_preempt_two_room_plan(native_plan):
    n=native_plan;await n.apply();await n.settle(16,16)
    assert all(n.runtime.decisions[r.room_id].demand for r in (n.rad,n.floor))
    for flags in (dict(all_off=True),dict(summer=True),dict(dhw_active=True),dict(limits_known_safe=False)):
        n.peer.clock[0]+=3
        await n.event("safety_snapshot",**{**dict(limits_known_safe=True,dhw_state_known=True),**flags})
        await n.samples(16,16);await n.event("tick");await n.drain()
        assert not any(d.demand for d in n.runtime.decisions.values()),flags
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
async def test_eight_transition_fixture_measures_complete_actual_wire_and_store(native_plan):
    n=native_plan;cfg,_=await n.source.async_configuration(n.runtime.hass,n.parent)
    for zone in cfg["zones"]:
        zone["schedule"]=dict(base_centi_c=zone["base_centi_c"],policy="wall-clock-membership/v1",timezone="UTC",
            valid_from_utc=1790000000,valid_until_utc=1790001000,
            transitions=[[1790000000+i*100,zone["base_centi_c"]] for i in range(4)])
    n.source.validate_plan(cfg)
    await n.client.message("ha/config","config",dict(expected_revision=0,config_digest=digest(cfg),config=cfg))
    topic,raw=n.pending.popleft();result=await n.peer.request("receive",topic=topic,raw=raw)
    assert result["writes"]==1 and result["store_bytes"]==len(canonical(cfg).encode())
    assert result["store_bytes"]<=4096 and len(raw.encode())<=8192
    assert not result["fault"] and n.client.journal["accepted"] is None
    if path:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(path).open("a") as f:f.write(canonical(dict(scenario="two_room_eight_transition_fixture",
            store_bytes=result["store_bytes"],wire_bytes=len(raw.encode()),transitions=8,physical_outputs=False))+chr(10))

@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["future_schema","legacy_schema","corrupt_digest"])
async def test_native_HA_load_rejects_unknown_journal_without_overwrite(native_plan,hass,kind):
    from homeassistant.helpers.storage import Store
    n=native_plan;record=await n.apply();await n.stop()
    journal=deepcopy({"accepted":record,"staged":None})
    cfg=journal["accepted"]["config"]
    cfg["schema"]=3 if kind=="future_schema" else 1 if kind=="legacy_schema" else 2
    if kind=="corrupt_digest":journal["accepted"]["config_digest"]="f"*64
    else:journal["accepted"]["config_digest"]=digest(cfg)
    store=Store(hass,1,"open_thermostat.v1."+n.parent.entry_id);await store.async_save(journal)
    with pytest.raises(ValueError):await n.start()
    assert await store.async_load()==journal
    assert (await n.peer.request("status"))["writes"]==1 and not n.pending

@pytest.mark.asyncio
async def test_normal_reload_and_disconnect_require_fresh_exact_readback_not_old_session(native_plan):
    n=native_plan;record=await n.apply();old=deepcopy(n.client.session)
    await n.client.async_disconnected();await n.peer.request("disconnect")
    assert not n.client.ready
    await n.client.receive("fw/session",canonical(old),retained=True)
    assert n.client.session is None
    await n.event("connect");await n.handshake()
    assert n.client.ready and n.client.session["adapter_session_id"]!=old["adapter_session_id"]
    assert n.client.journal["accepted"]==record
    assert (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",["sample_"],indirect=True)
async def test_native_observations_use_accepted_source_binding_not_hardcoded_legacy_name(native_plan):
    n=native_plan;record=await n.apply();await n.settle(16,22)
    assert tuple(n.runtime.decisions[r.room_id].demand for r in (n.rad,n.floor))==(True,False)
    messages=[json.loads(kw["raw"]) for op,kw,_ in n.peer.trace if op=="receive" and kw.get("topic")=="ha/observations"]
    expected={z["zone_id"]:z["sensor_id"] for z in record["config"]["zones"]}
    assert messages and all(m["binding_id"]==expected[m["zone_id"]] for m in messages)
