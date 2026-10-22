"""Actual native entry caller after explicit SOURCE phase selection; no live IO.
Same finite C++ process/backing key changes owner; SOURCE/safety/report are fixtures.
"""
import asyncio,json,os
from collections import deque
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path
import pytest
import pytest_asyncio
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import ConfigEntryError,HomeAssistantError
from homeassistant.helpers.storage import Store
from custom_components.open_thermostat.graph_control_source import GraphControllerEntrySource
from custom_components.open_thermostat.comfort_sources import ControllerPolicySourceProfile
from custom_components.open_thermostat.v1_wire import canonical,digest
from custom_components.open_thermostat.v1_climate import ShadowRoom
import custom_components.open_thermostat as integration
from test_graph_draft_apply import saved_graph
from test_graph_control_handoff import accepted,fixture_source
from test_v1_native import physical_state,source_profile

def emit(row):
    if path:=os.environ.get("OPENTHERMOSTAT_CALLER_EVIDENCE"):
        with Path(path).open("a") as f:f.write(json.dumps(row,sort_keys=True)+"\n")

@pytest_asyncio.fixture
async def native_caller(saved_graph,hass,monkeypatch,request):
    graph=saved_graph
    record,key=await accepted(graph)
    reviewed=await graph.client.async_reviewed_handoff_data(key)
    source,projected=fixture_source(reviewed,graph.profile.qualification_digest)
    pin=ControllerPolicySourceProfile(graph.parent.unique_id,"e32_test","test_owner",
        source["profile_digest"],digest(projected))
    profile=GraphControllerEntrySource(graph.profile,pin,canonical(reviewed))
    profile.validate()
    previous=await graph.peer.request("durable_readback");original=previous["stored"]
    old_worker=graph.connection.worker
    await graph.runtime.async_stop();await graph.peer.request("disconnect")
    assert old_worker.done() and graph.connection.closed
    mode=getattr(request,"param","ok")
    if mode=="wrong_remote_profile":source["profile_digest"]="0"*64
    if mode=="wrong_remote_config":source["config_digest"]="0"*64
    selected=await graph.peer.request("select_control_source",source=source)
    assert selected["source_control_mode"]
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_CONTROLLER_POLICY_SOURCE_PROFILES",())
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(profile,))
    monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",AsyncMock())
    monkeypatch.setattr(hass.config_entries,"async_unload_platforms",AsyncMock(return_value=True))
    callbacks={};publications=deque();removed=[];calls=[]
    hass.services.async_register("climate","set_temperature",lambda call:calls.append(call))
    async def subscribe(_hass,topic,cb,**kwargs):
        assert topic=="fixture/v1/fw/#";callbacks["message"]=cb
        return lambda:removed.append("mqtt")
    def status(_hass,cb):callbacks["status"]=cb;return lambda:removed.append("status")
    async def publish(_hass,topic,payload,**kwargs):
        assert topic.startswith("fixture/v1/") and kwargs=={"qos":0,"retain":False}
        publications.append((topic.removeprefix("fixture/v1/"),payload))
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    monkeypatch.setattr(mqtt,"async_subscribe_connection_status",status)
    monkeypatch.setattr(mqtt,"async_publish",publish)
    runtime=connection=client=None
    holder={}
    async def start():
        nonlocal runtime,connection,client
        assert await integration.async_setup_entry(hass,graph.parent)
        state=hass.data["open_thermostat"][graph.parent.entry_id]
        runtime,connection=state["v1_runtime"],state["v1_connection"];client=connection.client
        client.clock=lambda:graph.peer.clock[0]
        runtime.set_report_profile(graph.binding.room_id,source_profile)
        if n:=holder.get("n"):n.runtime,n.connection,n.client=runtime,connection,client
    async def stop():
        assert await integration.async_unload_entry(hass,graph.parent)
        await graph.parent._async_process_on_unload(hass)
        assert connection.worker.done() and connection.timer is None
        assert not runtime._subscriptions and not runtime._expiries
    async def deliver(frames,drop=None):
        for frame in frames:
            if frame["topic"]==drop or (holder.get("n") and holder["n"].drop_snapshot and frame["topic"]=="fw/config_snapshot"):continue
            callbacks["message"](SimpleNamespace(topic="fixture/v1/"+frame["topic"],payload=frame["raw"],retain=False))
            await connection.queue.join()
    async def event(op,**kwargs):
        result=await graph.peer.request(op,**kwargs);await deliver(result["frames"]);return result
    async def drain():
        for _ in range(100):
            await connection.queue.join();await hass.async_block_till_done()
            if not publications:return
            topic,raw=publications.popleft();await event("receive",topic=topic,raw=raw)
        raise AssertionError("bounded caller worker loop")
    serial=0
    async def observe(value=16):
        nonlocal serial
        serial+=1;physical_state(hass,graph.binding,key=f"caller_sample_{serial}",value=str(value))
        await hass.async_block_till_done();await drain()
    async def command(awaitable):
        task=asyncio.create_task(awaitable)
        for _ in range(100):
            await drain()
            if task.done():return await task
            await asyncio.sleep(.001)
        task.cancel();raise AssertionError("native command deadline")
    await start()
    staged=await client.store.async_load()
    assert staged["accepted"] is None and staged["staged"]["config"]==projected
    n=SimpleNamespace(graph=graph,record=record,profile=profile,source=source,projected=projected,
        runtime=runtime,connection=connection,client=client,callbacks=callbacks,publications=publications,
        start=start,stop=stop,event=event,deliver=deliver,drain=drain,observe=observe,command=command,
        original=original,removed=removed,services=calls,old_worker=old_worker,
        drop_snapshot=mode=="drop_snapshot")
    holder["n"]=n
    try:
        await event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
        await event("connect");await event("tick");await drain()
        yield n
    finally:
        if graph.parent.entry_id in hass.data.get("open_thermostat",{}):await stop()
        after=await graph.peer.request("durable_readback")
        assert after["stored"]==original and after["writes"]==1
        assert removed.count("mqtt")==removed.count("status")
        assert not calls

@pytest.mark.asyncio
async def test_native_source_entry_stages_only_then_fresh_same_store_cpp_readback_is_ready(native_caller):
    n=native_caller
    assert n.client.ready and n.runtime.transport_ready
    assert n.runtime.graph_data_profile is None
    assert n.runtime.graph_controller_source==n.profile
    assert n.client.journal["accepted"]["config"]==n.projected and n.client.journal["staged"] is None
    assert n.old_worker.done()
    await n.observe();await n.observe()
    row=n.runtime.decisions[n.graph.binding.room_id]
    assert row.demand and row.target_centi_c==n.projected["zones"][0]["base_centi_c"]
    entity=ShadowRoom("fixture",n.graph.binding,n.runtime)
    assert entity.available and entity.min_temp==16 and entity.max_temp==24
    attrs=entity.extra_state_attributes
    assert attrs["actuator_profile"]=="source_graph_shadow_only"
    assert attrs["boiler_output_enabled"] is attrs["actuator_output_enabled"] is False
    emit(dict(scenario="native_graph_room_entry_staged_fresh_cpp_readback_admitted_shadow",
        same_cpp_store=True,old_worker_stopped=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_native_room_target_command_and_off_dhw_source_expiry_preserve_graph(native_caller):
    n=native_caller;await n.observe();await n.observe()
    await n.command(n.runtime.async_set_temperature(n.graph.binding.room_id,22))
    assert n.runtime.decisions[n.graph.binding.room_id].target_centi_c==2200
    with pytest.raises(HomeAssistantError):
        await n.runtime.async_set_temperature(n.graph.binding.room_id,25)
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,all_off=True)
    await n.observe();assert not n.runtime.decisions[n.graph.binding.room_id].demand
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,dhw_active=True)
    await n.observe();assert not n.runtime.decisions[n.graph.binding.room_id].demand
    n.graph.peer.clock[0]+=2
    await n.event("tick");await n.drain()
    assert not n.runtime.decisions[n.graph.binding.room_id].demand
    emit(dict(scenario="native_graph_controller_command_limits_off_dhw_source_expiry",physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("native_caller",["wrong_remote_profile","wrong_remote_config"],indirect=True)
async def test_bad_actual_source_profile_or_tuple_never_promotes_staged_control_record(native_caller):
    n=native_caller
    assert not n.client.ready and not n.runtime.transport_ready
    assert n.client.journal["accepted"] is None
    assert n.client.journal["staged"]["config"]==n.projected
    assert not any(x.demand for x in n.runtime.decisions.values())
    emit(dict(scenario="remote_source_rejected_staged_not_accepted",physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_control_entry_reload_boot_and_old_observation_do_not_restore_grant_or_heat(native_caller):
    n=native_caller;await n.observe();await n.observe()
    await n.command(n.runtime.async_set_temperature(n.graph.binding.room_id,22))
    old=n.client.session["grant_id"]
    old_observation=next(args["raw"] for op,args,_ in reversed(n.graph.peer.trace)
        if op=="receive" and args.get("topic")=="ha/observations")
    await n.stop();await n.start()
    assert not n.client.ready
    await n.event("disconnect");await n.event("reboot",boot="control_boot2")
    await n.event("connect");await n.event("tick");await n.drain()
    assert n.client.ready and n.client.session["grant_id"]!=old
    assert not any(x.demand for x in n.runtime.decisions.values())
    await n.event("receive",topic="ha/observations",raw=old_observation);await n.drain()
    assert not any(x.demand for x in n.runtime.decisions.values())
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
    await n.observe();await n.observe()
    assert n.runtime.decisions[n.graph.binding.room_id].target_centi_c==n.projected["zones"][0]["base_centi_c"]
    emit(dict(scenario="native_source_reload_boot_fresh_readback_no_old_grant_or_sample",physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_registry_change_and_native_draft_edit_stop_and_require_new_source_review(native_caller,hass):
    n=native_caller;await n.observe();await n.observe()
    er.async_get(hass).async_update_entity(n.graph.output.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done();await n.connection.queue.join()
    assert not n.client.ready and not n.runtime.decisions
    assert n.client.error=="graph_control_source_review_required"
    # Reconnect and an otherwise valid old SOURCE hello cannot clear this fence.
    await n.event("disconnect");await n.event("connect");await n.event("tick");await n.drain()
    assert not n.client.ready and not n.runtime.decisions
    emit(dict(scenario="native_graph_registry_change_fences_control_until_review",physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_second_native_setup_cannot_create_another_owner(native_caller,hass):
    n=native_caller
    with pytest.raises(ConfigEntryError,match="graph_control_existing_owner_active"):
        await integration.async_setup_entry(hass,n.graph.parent)
    assert n.client.ready and n.connection.worker and not n.connection.worker.done()
    emit(dict(scenario="no_parallel_native_owner",physical_outputs_enabled=False))
