"""Actual saved native draft -> explicit SOURCE2 view -> real controller.
Preloaded review is a SOURCE fixture, NOT current API2 graph-writer/apply support.
"""
import asyncio,json,os
from collections import deque
from copy import deepcopy
from dataclasses import asdict,replace
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import ConfigEntryError
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.graph_topology_review import native_topology_plan,prepare_saved_topology_review,TopologyReviewContext
from custom_components.open_thermostat.topology_control_source import TopologyControllerEntrySource
from custom_components.open_thermostat.comfort_sources import ControllerPolicySourceProfile
from custom_components.open_thermostat.v1_wire import canonical,digest
from test_graph_topology_review import native_two
from test_graph_owner_interop import pair
from test_v1_native import physical_state,source_profile

def record(row):
    if path:=os.environ.get("OPENTHERMOSTAT_TWO_CONTROLLER_EVIDENCE"):
        with Path(path).open("a") as f:f.write(json.dumps(row,sort_keys=True)+"\n")

@pytest_asyncio.fixture
async def two_controller(native_two,hass,monkeypatch,request):
    parent,rad,floor,central,output=native_two
    floor=replace(floor,base_centi_c=1900)
    sub=next(s for s in parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==floor.room_id)
    hass.config_entries.async_update_subentry(parent,sub,data=floor.as_dict())
    hass.config_entries.async_update_entry(parent,options={**parent.options,"shadow_enabled":True,"adapter_id":"test_owner"})
    saved={k:deepcopy(dict(v.data)) for k,v in parent.subentries.items()}
    plan=native_topology_plan(hass,parent)
    cx=TopologyReviewContext("e32_test","review_boot","review_session",1,0,1,1,digest(plan))
    raw=prepare_saved_topology_review(hass,parent,cx)
    independent_policy="c"*64 # Explicit synthetic SOURCE identity, not DATA qualification.
    cp=ControllerPolicySourceProfile(parent.unique_id,"e32_test","test_owner",independent_policy,"0"*64)
    source=TopologyControllerEntrySource(cp,cx,raw,("physical_report","physical_report"))
    source=replace(source,controller=replace(cp,config_digest=digest(source.projection())));source.validate()
    ctor=dict(profile_version=source.profile_version,review_digest=digest(json.loads(raw)),
        expected_profile_digest=independent_policy,profile_digest=independent_policy,
        control_digest=source.controller.config_digest,context=asdict(cx),
        zones=[dict(zone_id=r["zone_id"],sensor_id="s_"+r["zone_id"],actuator_id=r["actuator_id"],
            minimum=r["minimum_target_centi_c"],maximum=r["maximum_target_centi_c"],evidence="physical_report",
            emitter=r["emitter"]) for r in plan["rooms"]])
    if out:=os.environ.get("OPENTHERMOSTAT_TWO_CONTROLLER_EVIDENCE"):
        (Path(out).parent/"SOURCE-FIXTURE.json").write_text(canonical(dict(stored=raw,source=ctor))+chr(10))
    mode=getattr(request,"param","ok")
    if mode=="wrong_profile":ctor["profile_digest"]="0"*64
    elif mode=="wrong_config":ctor["control_digest"]="0"*64
    elif mode=="future_version":ctor["profile_version"]="two-room-targets.v999"
    elif mode=="wrong_source_revision":ctor["context"]["source_revision"]+=1
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_CONTROLLER_POLICY_SOURCE_PROFILES",())
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(source,))
    monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",AsyncMock())
    monkeypatch.setattr(hass.config_entries,"async_unload_platforms",AsyncMock(return_value=True))
    reload=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    callbacks={};pending=deque();removed=[];services=[]
    hass.services.async_register("climate","set_temperature",lambda call:services.append(call))
    async def subscribe(_h,topic,cb,**kw):
        assert topic=="fixture/v1/fw/#";callbacks["message"]=cb
        return lambda:removed.append("mqtt")
    def status(_h,cb):callbacks["status"]=cb;return lambda:removed.append("status")
    async def publish(_h,topic,payload,**kw):
        assert topic.startswith("fixture/v1/") and kw==dict(qos=0,retain=False)
        pending.append((topic.removeprefix("fixture/v1/"),payload))
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe);monkeypatch.setattr(mqtt,"async_publish",publish)
    monkeypatch.setattr(mqtt,"async_subscribe_connection_status",status)
    async with pair(hass) as peer:
        initial=await peer.request("initialize_topology_source",controller="e32_test",boot="control_boot",
                                   owner="test_owner",stored=raw,source=ctor)
        holder={};runtime=connection=client=None
        async def start():
            nonlocal runtime,connection,client
            assert await integration.async_setup_entry(hass,parent)
            state=hass.data["open_thermostat"][parent.entry_id];runtime=state["v1_runtime"];connection=state["v1_connection"];client=connection.client
            client.clock=lambda:peer.clock[0]
            for r in (rad,floor):runtime.set_report_profile(r.room_id,source_profile)
            if n:=holder.get("n"):n.runtime,n.connection,n.client=runtime,connection,client
        async def stop():
            assert await integration.async_unload_entry(hass,parent)
            await parent._async_process_on_unload(hass)
            assert connection.worker.done() and connection.timer is None
            assert not runtime._subscriptions and not runtime._expiries
        async def deliver(frames):
            for frame in frames:
                callbacks["message"](SimpleNamespace(topic="fixture/v1/"+frame["topic"],payload=frame["raw"],retain=False))
                await connection.queue.join()
        async def event(op,**kw):
            response=await peer.request(op,**kw);await deliver(response["frames"]);return response
        async def drain():
            for _ in range(100):
                await connection.queue.join();await hass.async_block_till_done()
                if not pending:return
                topic,raw_=pending.popleft();await event("receive",topic=topic,raw=raw_)
            raise AssertionError("bounded existing native worker loop")
        serial=0
        async def samples(a,b):
            nonlocal serial
            # Two independently qualified reports per room; no DATA/cache proof.
            for _ in range(2):
                serial+=1
                for r,value in ((rad,a),(floor,b)):
                    physical_state(hass,r,key=f"two_{r.room_id}_{serial}",value=str(value))
                await hass.async_block_till_done();await drain()
        async def settle(a,b):
            # The existing regulator anchors minimum-off at its last denied/
            # reset step, NOT boot0. Keep120s policy unchanged; feed121seconds
            # of continuous fresh reports/heartbeats/safety after qualification.
            for _ in range(121):
                peer.clock[0]+=1
                await client.poll();await drain()
                await event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
                await samples(a,b);await event("tick");await drain()
        async def command(awaitable):
            task=asyncio.create_task(awaitable)
            for _ in range(100):
                await drain()
                if task.done():return await task
                await asyncio.sleep(.001)
            task.cancel();raise AssertionError("native command deadline")
        await start()
        journal=await client.store.async_load()
        assert journal["accepted"] is None and journal["staged"]["config"]==source.projection()
        n=SimpleNamespace(parent=parent,rad=rad,floor=floor,central=central,output=output,
            plan=plan,source=source,ctor=ctor,raw=raw,initial=initial,peer=peer,runtime=runtime,
            connection=connection,client=client,event=event,drain=drain,samples=samples,settle=settle,command=command,
            start=start,stop=stop,pending=pending,callbacks=callbacks)
        holder["n"]=n
        try:
            await event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
            await event("connect");await event("tick");await drain()
            yield n
        finally:
            if parent.entry_id in hass.data.get("open_thermostat",{}):await stop()
            state=await peer.request("durable_readback")
            assert state["stored"]==raw and state["writes"]==0
            assert removed.count("mqtt")==removed.count("status") and not services
            assert not any(op=="receive" and kw.get("topic")=="ha/config" for op,kw,_ in peer.trace)
            if mode!="mutated_native":
                assert saved=={k:dict(v.data) for k,v in parent.subentries.items()}

@pytest.mark.asyncio
@pytest.mark.parametrize("temperatures,expected",[((16,22),(True,False)),((23,16),(False,True)),((16,16),(True,True)),((23,22),(False,False))],
 ids=["A-only","B-only","together","all-idle"])
async def test_saved_native_two_targets_reach_actual_existing_controller(two_controller,temperatures,expected):
    n=two_controller;assert n.client.ready and n.runtime.transport_ready,(n.initial,n.client.error)
    assert n.client.journal["accepted"]["config"]==n.source.projection()
    await n.samples(*temperatures)
    if temperatures[1]<19:
        assert not n.runtime.decisions[n.floor.room_id].demand  # original minimum-off
    await n.settle(*temperatures)
    states=[n.runtime.decisions[r.room_id] for r in (n.rad,n.floor)]
    assert tuple(s.demand for s in states)==expected
    assert tuple(s.target_centi_c for s in states)==(2100,1900)
    from custom_components.open_thermostat.v1_climate import ShadowRoom
    for room in (n.rad,n.floor):
        attrs=ShadowRoom("fixture",room,n.runtime).extra_state_attributes
        assert attrs["boiler_output_enabled"] is attrs["actuator_output_enabled"] is False
    record(dict(scenario="two_targets",temperatures=temperatures,demand=expected,targets=[2100,1900],
        source_profile_version=n.source.profile_version,review_bytes=len(n.raw.encode()),
        config_bytes=len(canonical(n.source.projection()).encode()),
        mirror_record_bytes=len(canonical(n.source.record()).encode()),
        view_object_bytes=n.initial["topology_view_object_bytes"],writes=0,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_stop_dhw_and_source_expiry_never_leave_phantom_second_room_demand(two_controller):
    n=two_controller;await n.settle(16,16)
    assert all(x.demand for x in n.runtime.decisions.values())
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,all_off=True)
    await n.samples(16,16);assert all(not x.demand for x in n.runtime.decisions.values())
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,dhw_active=True)
    await n.samples(16,16);assert all(not x.demand for x in n.runtime.decisions.values())
    n.peer.clock[0]+=2;await n.event("tick");await n.drain()
    assert all(not x.demand for x in n.runtime.decisions.values())

@pytest.mark.asyncio
@pytest.mark.parametrize("two_controller",["wrong_profile","wrong_config","future_version","wrong_source_revision"],indirect=True)
async def test_source_or_store_profile_mismatch_never_promotes_mirror(two_controller):
    n=two_controller
    assert not n.client.ready and not n.runtime.transport_ready
    assert n.client.journal["accepted"] is None
    assert not any(d.demand for d in n.runtime.decisions.values())

@pytest.mark.asyncio
async def test_two_room_native_reload_boot_reconnect_does_not_restore_old_grant_or_override(two_controller):
    n=two_controller;await n.samples(16,16)
    await n.command(n.runtime.async_set_temperature(n.rad.room_id,22))
    assert n.runtime.decisions[n.rad.room_id].target_centi_c==2200
    assert n.runtime.decisions[n.floor.room_id].target_centi_c==1900
    old=n.client.session["grant_id"]
    old_sample=next(args["raw"] for op,args,_ in reversed(n.peer.trace) if op=="receive" and args.get("topic")=="ha/observations")
    await n.stop();await n.start();assert not n.client.ready
    await n.event("disconnect");await n.event("reboot",boot="two_room_boot2")
    await n.event("connect");await n.event("tick");await n.drain()
    assert n.client.ready and n.client.session["grant_id"]!=old
    await n.event("receive",topic="ha/observations",raw=old_sample);await n.drain()
    assert all(not x.demand for x in n.runtime.decisions.values())
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
    await n.samples(16,16)
    assert [n.runtime.decisions[r.room_id].target_centi_c for r in (n.rad,n.floor)]==[2100,1900]

@pytest.mark.asyncio
async def test_registry_loss_fences_existing_owner_and_reconnect_cannot_adopt(two_controller,hass):
    n=two_controller;await n.samples(16,16)
    er.async_get(hass).async_update_entity(n.output.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done();await n.connection.queue.join()
    assert not n.client.ready and not n.runtime.decisions
    await n.event("disconnect");await n.event("connect");await n.event("tick");await n.drain()
    assert not n.client.ready and not n.runtime.decisions

@pytest.mark.asyncio
async def test_unknown_second_room_sample_stops_only_that_room_without_adopting_cache(two_controller):
    n=two_controller;await n.settle(16,16)
    assert all(x.demand for x in n.runtime.decisions.values())
    await n.samples(16,"unknown")
    assert n.runtime.decisions[n.rad.room_id].demand
    assert not n.runtime.decisions[n.floor.room_id].demand

@pytest.mark.asyncio
@pytest.mark.parametrize("bad",["none","future_version","config_pin","owner","missing_registry"])
async def test_source2_native_setup_cannot_qualify_itself_from_saved_draft(two_controller,hass,monkeypatch,bad):
    n=two_controller;await n.stop()
    source=n.source
    if bad=="none":monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",())
    elif bad=="future_version":monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(replace(source,profile_version="two-room-targets.v999"),))
    elif bad=="config_pin":monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(replace(source,controller=replace(source.controller,config_digest="0"*64)),))
    elif bad=="owner":
        source=replace(source,controller=replace(source.controller,adapter_id="other_owner"))
        monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(source,))
    else:er.async_get(hass).async_update_entity(n.output.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    with pytest.raises((ConfigEntryError,ValueError)):
        await integration.async_setup_entry(hass,n.parent)
    # No new worker/config send may survive rejected setup.
    state=hass.data.get("open_thermostat",{}).get(n.parent.entry_id,{})
    assert "v1_connection" not in state
    assert not n.pending

@pytest.mark.asyncio
@pytest.mark.parametrize("two_controller",["mutated_native"],indirect=True)
async def test_two_source_control_draft_change_fences_current_owner_on_next_explicit_preflight(two_controller,hass):
    n=two_controller
    sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.floor.room_id)
    hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2000})
    await hass.async_block_till_done()
    assert not n.client.ready and not n.runtime.decisions
    assert n.client.error=="graph_control_source_review_required"
    with pytest.raises(ValueError):
        await n.source.async_configuration(hass,n.parent)
    assert not n.pending

@pytest.mark.asyncio
@pytest.mark.parametrize("field,value",[("epoch",True),("registry_revision",1.0),
    ("source_revision",True),("config_revision",-1),("config_revision",4294967295)])
async def test_typed_source_context_never_coerces_bool_float_future_or_negative(two_controller,field,value):
    n=two_controller
    bad=replace(n.source,context=replace(n.source.context,**{field:value}))
    with pytest.raises(ValueError):bad.validate()

@pytest.mark.asyncio
async def test_existing_owned_wire_off_stops_each_room_independently(two_controller):
    n=two_controller;await n.settle(16,16)
    assert all(d.demand for d in n.runtime.decisions.values())
    async def off(room_id):
        # Same Future/ack contract as the existing async_setpoint caller.
        future=n.runtime.hass.loop.create_future()
        await n.client.message("ha/user_command",room_id,dict(mode="off",temperature_centi_c=500,duration_ms=60000),future)
        await future
    await n.command(off(n.rad.room_id))
    assert not n.runtime.decisions[n.rad.room_id].demand
    assert n.runtime.decisions[n.floor.room_id].demand
    await n.command(off(n.floor.room_id))
    assert all(not d.demand for d in n.runtime.decisions.values())
    assert all(d.target_centi_c is None for d in n.runtime.decisions.values())
    record(dict(scenario="owned_wire_off_both",target_a=None,target_b=None,demand_a=False,demand_b=False,writes=0,physical_outputs_enabled=False))
