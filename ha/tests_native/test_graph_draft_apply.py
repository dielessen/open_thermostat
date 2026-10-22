"""Saved native graph/room -> source-pinned existing owner -> actual C++ DATA.
All qualification/device facts explicitly SYNTHETIC fixture; never inferred by GUI.
"""
import asyncio
from collections import deque
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace,MappingProxyType
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import ConfigEntryError,HomeAssistantError

from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow,reference
from custom_components.open_thermostat.v1_model import RoomBinding,ROOM_GRAPH_DRAFT
from custom_components.open_thermostat.graph_wire import GraphSourceProfile
from custom_components.open_thermostat.graph_draft_compile import GraphDraftSource,async_compile_saved_graph
from custom_components.open_thermostat.graph_shadow_validation import canonical,digest,GraphValidationError
from test_v1_native import room,entry
from test_graph_owner_interop import pair
from test_graph_review_flow import native_graph
from test_graph_shadow_storage import FIXTURE

@pytest_asyncio.fixture
async def saved_graph(hass,monkeypatch,request):
    base=room(hass,age=120000)
    binding=replace(base,actuators=(),binding_mode=ROOM_GRAPH_DRAFT,
                    minimum_target_centi_c=1600,maximum_target_centi_c=2400)
    parent=entry(hass,enabled=True,room=binding)
    hass.config_entries.async_update_entry(parent,options={**parent.options,"adapter_id":"test_owner"})
    registry=er.async_get(hass)
    output=registry.async_get_or_create("switch","draft_fixture","floor")
    feedback=registry.async_get_or_create("binary_sensor","draft_fixture","feedback")
    raw=json.loads(FIXTURE["raw"])["config"]
    actuator=deepcopy(raw["actuators"][0])
    actuator.pop("output_channel");actuator["output"]=reference(hass,output.entity_id).as_dict()
    central=deepcopy(raw["central"]);central.pop("outdoor_channel");central.pop("outdoor_kind");central.pop("outdoor_axis_centi_c")
    central["outdoor_source"]=None
    group=deepcopy(raw["groups"][0]);group.pop("pump_channel");group["pump"]=None;group["name"]="Synthetic floor"
    stored=dict(draft_schema=1,central=central,groups=[group],actuators=[actuator])
    sub=ConfigSubentry(data=MappingProxyType({"draft":stored}),subentry_type="heating",
        title="Synthetic saved graph",unique_id="saved_heating")
    hass.config_entries.async_add_subentry(parent,sub)
    record=raw["qualification"]
    refs={
      "s_"+binding.room_id:binding.temperature.as_dict(),
      raw["actuators"][0]["output_channel"]:reference(hass,output.entity_id).as_dict(),
      record["devices"][0]["feedback_channel"]:reference(hass,feedback.entity_id).as_dict()}
    source=GraphDraftSource(canonical(record),canonical(refs))
    profile=GraphSourceProfile("e32_test",FIXTURE["context"]["qualification_digest"],source,entry_unique_id=parent.unique_id)
    native_entry=getattr(request,"param",False) is True
    callbacks={};publications=deque();removed=[]
    async def subscribe(_hass,topic,callback,qos=0,encoding=None):
        assert topic=="fixture/v2/fw/#" and qos==0
        callbacks["message"]=callback
        return lambda:removed.append("mqtt")
    def status(_hass,cb):
        callbacks["status"]=cb
        return lambda:removed.append("status")
    async def publish(_hass,topic,raw,qos=0,retain=False):
        assert topic.startswith("fixture/v2/") and qos==0 and retain is False
        publications.append((topic.removeprefix("fixture/v2/"),raw))
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    monkeypatch.setattr(mqtt,"async_subscribe_connection_status",status)
    monkeypatch.setattr(mqtt,"async_publish",publish)
    reload=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    if native_entry:
        import custom_components.open_thermostat as integration
        monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",profile) # explicit synthetic source only
        monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",AsyncMock())
        monkeypatch.setattr(hass.config_entries,"async_unload_platforms",AsyncMock(return_value=True))
        assert await integration.async_setup_entry(hass,parent)
        state=hass.data["open_thermostat"][parent.entry_id]
        runtime,connection=state["v1_runtime"],state["v1_connection"]
        assert runtime.graph_data_profile==connection.graph_profile==profile
    else:
        runtime=ShadowRuntime(hass,parent,[binding],graph_data_profile=profile)
        await runtime.async_start()
        connection=NativeShadowConnection(runtime,profile);await connection.async_start()
        hass.data.setdefault("open_thermostat",{}).setdefault(parent.entry_id,{}).update(
            v1_runtime=runtime,v1_connection=connection)
    worker=connection.worker
    async with pair(hass) as peer:
        client=connection.client
        client.clock=client.journal.clock=lambda:peer.clock[0]
        async def deliver(frames):
            for f in frames:
                callbacks["message"](SimpleNamespace(topic="fixture/v2/"+f["topic"],payload=f["raw"],retain=False))
                await connection.queue.join()
        async def drain():
            for _ in range(50):
                await connection.queue.join()
                if not publications:return
                topic,raw=publications.popleft()
                result=await peer.request("receive",topic=topic,raw=raw)
                await deliver(result["frames"])
            raise AssertionError("bounded protocol loop")
        def flow():
            f=ShadowOptionsFlow();f.hass=hass;f.handler=parent.entry_id;return f
        initial=await peer.request("connect");await deliver(initial["frames"]);await drain()
        try:
            yield SimpleNamespace(parent=parent,binding=binding,heating=sub,stored=stored,
                source=source,profile=profile,runtime=runtime,connection=connection,client=client,
                callbacks=callbacks,publications=publications,peer=peer,drain=drain,deliver=deliver,
                flow=flow,output=output,feedback=feedback)
        finally:
            if native_entry:
                assert await integration.async_unload_entry(hass,parent)
                await parent._async_process_on_unload(hass) # native lifecycle hook
            else:
                await runtime.async_stop()
            assert worker is connection.worker and worker.done()
            assert not runtime._subscriptions and not runtime._expiries
            assert connection.queue.empty() and not connection.unsubs and connection.timer is None
            assert removed==["mqtt","status"]
            reload.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize("saved_graph",[True],indirect=True)
async def test_native_saved_graph_prepares_then_requires_separate_exact_review_before_actual_commit(saved_graph,hass):
    n=saved_graph
    f=n.flow()
    review=await f.async_step_init({"graph_action":"prepare"})
    assert review["type"]=="form" and review["step_id"]=="graph_review"
    assert review["description_placeholders"]["revision"]=="1"
    assert n.client.journal.status=="graph_staged_not_applied"
    assert not n.publications and (await n.peer.request("status"))["writes"]==0
    staged=n.client.journal.state["staged"]
    assert staged["config"]["rooms"][0]["zone_id"]==n.binding.room_id
    assert staged["config"]["groups"][0]["emitter"]=="floor"
    assert staged["config"]["qualification"]==json.loads(n.source.qualification_json)
    assert len(canonical(staged["config"]))<=4096
    wire=canonical(staged)
    for entity in (n.binding.temperature.entity_id,n.output.entity_id,n.feedback.entity_id):
        assert entity not in wire
    await f.async_step_graph_review({"confirm_apply":True});await n.drain()
    state=await n.peer.request("status")
    assert state["writes"]==1 and state["revision"]==1
    assert n.client.graph_ready and not n.runtime.transport_ready and n.client.ready is False
    assert not n.runtime._subscriptions and not n.runtime._expiries
    assert n.runtime.decisions=={}
    assert n.runtime.observations[n.binding.room_id].quality=="disabled"
    from custom_components.open_thermostat.v1_climate import ShadowRoom
    assert not ShadowRoom("fixture",n.binding,n.runtime).available
    with pytest.raises(HomeAssistantError):
        await n.runtime.async_set_temperature(n.binding.room_id,22)
    before=state["writes"]
    hass.states.async_set(n.binding.temperature.entity_id,"20",{"unit_of_measurement":"°C","device_class":"temperature"})
    await hass.async_block_till_done();await n.drain()
    assert (await n.peer.request("status"))["writes"]==before

@pytest.mark.asyncio
async def test_source_registry_rename_preserves_resource_identity_and_never_grants_feedback(saved_graph,hass):
    n=saved_graph
    await n.connection.async_graph_command("prepare")
    first=n.client.journal.state["staged"]
    await n.connection.async_graph_command("apply");await n.drain()
    registry=er.async_get(hass)
    registry.async_update_entity(n.output.entity_id,new_entity_id="switch.renamed_synthetic_floor")
    # Native stable registry reference, not name matching or invented safe state.
    await n.connection.async_graph_command("prepare")
    second=n.client.journal.state["staged"]
    assert first["mapping"]==second["mapping"]
    assert second["config"]["revision"]==2
    assert not second["config"]["qualification"]["outputs_ready"]
    assert not n.runtime.transport_ready

@pytest.mark.asyncio
@pytest.mark.parametrize("mutation",["source_changed","source_missing","output_disabled","feedback_missing","extra_room","wrong_profile","bad_qualification"])
async def test_native_draft_source_or_binding_mismatch_fails_before_store_or_publish(saved_graph,hass,mutation):
    n=saved_graph;registry=er.async_get(hass)
    if mutation=="source_changed":
        replacement=registry.async_get_or_create("sensor","draft_fixture","different")
        data=dict(next(s for s in n.parent.subentries.values() if s.subentry_type=="zone").data)
        data["temperature"]=reference(hass,replacement.entity_id).as_dict()
        sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone")
        hass.config_entries.async_update_subentry(n.parent,sub,data=data)
    elif mutation=="source_missing":
        registry.async_remove(n.binding.temperature.entity_id)
    elif mutation=="output_disabled":
        registry.async_update_entity(n.output.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    elif mutation=="feedback_missing":
        registry.async_remove(n.feedback.entity_id)
    elif mutation=="extra_room":
        other=replace(n.binding,room_id="11223344",name="extra")
        sub=ConfigSubentry(data=MappingProxyType(other.as_dict()),subentry_type="zone",title="extra",unique_id=other.room_id)
        hass.config_entries.async_add_subentry(n.parent,sub)
    elif mutation=="wrong_profile":
        changed=deepcopy(n.stored);changed["groups"][0]["emitter"]="radiator"
        hass.config_entries.async_update_subentry(n.parent,n.heating,data={"draft":changed})
    else:
        q=json.loads(n.source.qualification_json);q["outputs_ready"]=True
        # Even caller-supplied "readiness" cannot override source anchor.
        bad=replace(n.profile,draft_source=GraphDraftSource(canonical(q),n.source.bindings_json))
        with pytest.raises(GraphValidationError,match="qualification"):bad.validate()
        return
    with pytest.raises((GraphValidationError,ValueError)):
        await n.connection.async_graph_command("prepare")
    assert n.client.journal.state["staged"] is None and not n.publications
    assert (await n.peer.request("status"))["writes"]==0
    assert not n.runtime.transport_ready

@pytest.mark.asyncio
async def test_saved_draft_change_during_shared_schedule_await_rejects_candidate_atomically(saved_graph,hass,monkeypatch):
    n=saved_graph
    from custom_components.open_thermostat import v1_mqtt
    real=v1_mqtt.async_room_schedule
    entered=asyncio.Event();release=asyncio.Event()
    async def blocked(*args,**kwargs):
        entered.set();await release.wait()
        return await real(*args,**kwargs)
    monkeypatch.setattr(v1_mqtt,"async_room_schedule",blocked)
    task=asyncio.create_task(n.connection.async_graph_command("prepare"))
    await asyncio.wait_for(entered.wait(),2)
    changed=deepcopy(n.stored);changed["groups"][0]["name"]="edited while compiling"
    hass.config_entries.async_update_subentry(n.parent,n.heating,data={"draft":changed})
    release.set()
    with pytest.raises(GraphValidationError,match="draft_changed"):
        await task
    assert not n.publications and n.client.journal.state["staged"] is None
    assert (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
async def test_source_data_runtime_cannot_attach_default_or_duck_typed_transport(saved_graph):
    n=saved_graph
    with pytest.raises(HomeAssistantError,match="graph_profile_unsupported"):
        n.runtime.attach_transport(SimpleNamespace(ready=True))
    default=NativeShadowConnection(n.runtime)
    with pytest.raises(ConfigEntryError,match="graph_profile_unsupported"):
        await default.async_start()
    assert default.worker is None and default.client is None
    assert not n.runtime.transport_ready

@pytest.mark.asyncio
async def test_default_graph_room_runtime_still_rejected_and_pin_alone_remains_data_only(saved_graph,hass):
    n=saved_graph
    unselected=ShadowRuntime(hass,n.parent,[n.binding])
    with pytest.raises(HomeAssistantError,match="graph_room_contract_unavailable"):
        await unselected.async_start()
    await unselected.async_stop()
    # Source pin without complete native bindings is still not a draft adapter.
    source=replace(n.profile,draft_source=None)
    runtime=ShadowRuntime(hass,n.parent,[n.binding],graph_data_profile=source)
    await runtime.async_start();assert not runtime.transport_ready
    await runtime.async_stop()


@pytest.mark.asyncio
async def test_pin_without_complete_source_bundle_cannot_prepare_from_native_gui_or_worker(native_graph):
    n=native_graph
    result=await n.flow().async_step_init({"graph_action":"prepare"})
    assert result["type"]=="abort" and result["reason"]=="graph_prepare_unavailable"
    with pytest.raises(ConfigEntryError,match="graph_draft_source_unavailable"):
        await n.connection.async_graph_command("prepare")
    assert n.client.journal.state["staged"] is None and not n.publications
    assert (await n.peer.request("status"))["writes"]==0


@pytest.mark.asyncio
async def test_native_saved_week_uses_same_bounded_UTC_compiler_and_real_cpp_readback(saved_graph,hass):
    n=saved_graph
    from custom_components.open_thermostat.v1_program import normalize_program
    from custom_components.open_thermostat.schedule_compiler import WEEKDAYS
    program=normalize_program({day:[{"start":0,"end":86400,"target_centi_c":2200}] for day in WEEKDAYS},1600,2400)
    sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone")
    data=dict(sub.data);data["week_program"]=program
    hass.config_entries.async_update_subentry(n.parent,sub,data=data)
    await n.connection.async_graph_command("prepare")
    schedule=n.client.journal.state["staged"]["config"]["rooms"][0]["schedule"]
    assert 1<=len(schedule["transitions"])<=8 and schedule["transitions"][0][1]==2200
    assert schedule["valid_from_utc"]<schedule["valid_until_utc"]
    await n.connection.async_graph_command("apply");await n.drain()
    assert n.client.journal.state["accepted"]["config"]["rooms"][0]["schedule"]==schedule
    assert n.client.graph_ready and (await n.peer.request("status"))["writes"]==1
    assert not n.runtime.transport_ready

@pytest.mark.asyncio
async def test_native_week_exceeding_real_peer_budget_is_rejected_not_truncated(saved_graph,hass):
    n=saved_graph
    from custom_components.open_thermostat.v1_program import normalize_program
    from custom_components.open_thermostat.schedule_compiler import WEEKDAYS
    program=normalize_program({day:[{"start":3600,"end":7200,"target_centi_c":2200}] for day in WEEKDAYS},1600,2400)
    sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone")
    data=dict(sub.data);data["week_program"]=program
    hass.config_entries.async_update_subentry(n.parent,sub,data=data)
    with pytest.raises(GraphValidationError):
        await n.connection.async_graph_command("prepare")
    assert n.client.journal.state["staged"] is None and not n.publications
    assert (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
async def test_disconnect_during_native_calendar_compile_cannot_stage_old_owner_DATA(saved_graph,monkeypatch):
    n=saved_graph
    from custom_components.open_thermostat import v1_mqtt
    real=v1_mqtt.async_room_schedule
    entered=asyncio.Event();release=asyncio.Event()
    async def blocked(*args,**kwargs):
        entered.set();await release.wait();return await real(*args,**kwargs)
    monkeypatch.setattr(v1_mqtt,"async_room_schedule",blocked)
    prepare=asyncio.create_task(n.connection.async_graph_command("prepare"))
    await asyncio.wait_for(entered.wait(),2)
    n.callbacks["status"](False)
    release.set()
    with pytest.raises(GraphValidationError,match="stale_capability"):
        await prepare
    await n.connection.queue.join()
    assert n.client.journal.state["staged"] is None and not n.publications
    assert (await n.peer.request("status"))["writes"]==0

@pytest.mark.parametrize("false_lookalike",[True,0,None])
def test_source_bundle_never_converts_readiness_claim_or_false_lookalike_to_permission(false_lookalike):
    q=json.loads(FIXTURE["raw"])["config"]["qualification"]
    q["outputs_ready"]=false_lookalike
    refs={"room":{"entity_id":"sensor.room","platform":"fixture","unique_id":"room"},
          "output":{"entity_id":"switch.floor","platform":"fixture","unique_id":"floor"},
          "feedback":{"entity_id":"binary_sensor.feedback","platform":"fixture","unique_id":"feedback"}}
    bundle=GraphDraftSource(canonical(q),canonical(refs))
    with pytest.raises(GraphValidationError,match="qualification"):
        bundle.validate(FIXTURE["context"]["qualification_digest"])


@pytest.mark.asyncio
@pytest.mark.parametrize("bad",["legacy","unknown_feature"])
async def test_native_compiler_cannot_reinterpret_legacy_owner_or_unknown_room_policy(saved_graph,hass,bad):
    n=saved_graph
    if bad=="legacy":
        hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"integration_mode":"legacy"})
    else:
        sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone")
        hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"future_comfort_override":"must_not_drop"})
    with pytest.raises(GraphValidationError):
        await n.connection.async_graph_command("prepare")
    assert n.client.journal.state["staged"] is None and not n.publications
    assert (await n.peer.request("status"))["writes"]==0


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_pin",[None,"different_hub"])
async def test_product_source_selection_requires_exact_native_entry_pin_before_any_io(saved_graph,hass,monkeypatch,entry_pin):
    n=saved_graph
    import custom_components.open_thermostat as integration
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",replace(n.profile,entry_unique_id=entry_pin))
    state=hass.data["open_thermostat"][n.parent.entry_id]
    worker=n.connection.worker
    with pytest.raises(ConfigEntryError):
        await integration.async_setup_entry(hass,n.parent)
    assert hass.data["open_thermostat"][n.parent.entry_id] is state
    assert n.connection.worker is worker and not worker.done()
    assert not n.publications and (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
async def test_native_options_can_select_DATA_only_when_complete_source_entry_pin_already_exists(saved_graph,monkeypatch):
    n=saved_graph
    import custom_components.open_thermostat as integration
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",n.profile)
    result=await n.flow().async_step_init({"integration_mode":"v1_shadow","shadow_enabled":True,"adapter_id":"test_owner"})
    assert result["type"]=="create_entry"
    assert result["data"]["shadow_enabled"] is True
    assert set(result["data"])=={"integration_mode","shadow_enabled","create_dashboard","adapter_id"}
    assert not n.runtime.transport_ready
    assert not n.publications and (await n.peer.request("status"))["writes"]==0
