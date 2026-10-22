"""Native entry/subentry/worker/Store + actual C++ SOURCE controller.
MQTT IO and local clock are finite test boundaries; no broker/device/physical proof.
"""
import asyncio
from collections import deque
from dataclasses import replace
import hashlib,json,os
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
from homeassistant import loader
from homeassistant.components import mqtt
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView
from custom_components.open_thermostat import comfort_sources
from custom_components.open_thermostat.comfort_sources import ControllerPolicySourceProfile
from custom_components.open_thermostat.v1_model import RoomBinding
from custom_components.open_thermostat.v1_climate import ShadowRoom
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_wire import canonical,digest
import custom_components.open_thermostat as integration
from test_v1_native import room,entry,physical_state,source_profile
from test_v1_wire_interop import FirmwareBus,RUNNER


def evidence(row):
    if path:=os.environ.get("OPENTHERMOSTAT_ENTRY_EVIDENCE"):
        with open(path,"a") as f:f.write(json.dumps(row,sort_keys=True)+"\n")

@pytest_asyncio.fixture
async def composed(hass,monkeypatch,tmp_path,request):
    mode=getattr(request,"param","selected")
    loader.async_setup(hass)
    component=await loader.async_get_integration(hass,"open_thermostat")
    await component.async_get_platform("config_flow")
    parent=entry(hass,enabled=True)
    original=[room(hass),room(hass,"11223344","second")]
    for binding,target in zip(original,(21,19)):
        manager=hass.config_entries.subentries
        form=await manager.async_init((parent.entry_id,"zone"),context={"source":"user"})
        rendered=FlowManagerIndexView(manager)._prepare_result_json(form)
        assert rendered["data_schema"]
        result=await manager.async_configure(form["flow_id"],{
            "room_id":binding.room_id,"name":binding.name,
            "temperature_entity":binding.temperature.entity_id,
            "actuator_entities":[binding.actuators[0].entity_id],
            "base_temperature":target,"comfort_enabled":True,"override_minutes":1})
        assert result["type"]=="create_entry",result
    assert not hass.config_entries.subentries.async_progress()
    # Flush the existing native ConfigEntries Store, not a new journal/schema.
    await hass.config_entries._store.async_save(hass.config_entries._data_to_save())
    disk=await hass.config_entries._store.async_load()
    assert len(disk["entries"][0]["subentries"])==2
    bindings=[RoomBinding.from_dict(dict(s.data)) for s in parent.subentries.values()]
    compiler=ShadowRuntime(hass,parent,bindings)
    zones,mapping=await async_build_configuration(compiler)
    approved=dict(schema=1,mode="shadow",revision=1,mapping_digest=digest(mapping),zones=zones)
    pin=digest(approved)
    identity=digest({"declared_source_fixture_only":True,"profile":"seasonal.shadow.v1",
        "config_pin":pin,"hysteresis_centi_c":20,"maximum_safety_age_ms":2000,
        "maximum_sensor_age_ms":120000,"maximum_step_gap_ms":300000})
    profile=ControllerPolicySourceProfile(parent.unique_id,"other" if mode=="wrong_controller" else "e32_lab","ha1",identity,pin)
    selected=mode not in ("plain","unselected")
    monkeypatch.setattr(integration,"_CONTROLLER_POLICY_SOURCE_PROFILES",(profile,) if selected else ())
    monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",AsyncMock())
    monkeypatch.setattr(hass.config_entries,"async_unload_platforms",AsyncMock(return_value=True))
    reload_call=AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries,"async_reload",reload_call)
    callbacks={};publications=deque();removed=[];services=[]
    hass.services.async_register("climate","set_temperature",lambda call:services.append(call))
    async def subscribe(_hass,topic,callback,**kwargs):
        assert topic=="fixture/v1/fw/#";callbacks["message"]=callback
        return lambda:removed.append("mqtt")
    def connection(_hass,callback):
        callbacks["status"]=callback
        return lambda:removed.append("status")
    async def publish(_hass,topic,payload,**kwargs):
        assert kwargs=={"qos":0,"retain":False}
        publications.append((topic.removeprefix("fixture/v1/"),payload))
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    monkeypatch.setattr(mqtt,"async_subscribe_connection_status",connection)
    monkeypatch.setattr(mqtt,"async_publish",publish)
    raw=json.loads(canonical(approved))
    if mode=="wrong_pin":raw["zones"][0]["base_centi_c"]+=50
    source=tmp_path/"reviewed-source-config.json";source.write_text(canonical(raw))
    argv=[str(RUNNER),"other" if mode=="wrong_owner" else "ha1"]
    if mode not in ("plain","missing"):
        argv+=["seasonal",str(source)]
        if mode!="anonymous":argv+=["0"*64 if mode=="wrong_profile" else identity]
    process=await asyncio.create_subprocess_exec(*argv,stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    bus=FirmwareBus(process,hass.loop.time)
    bus.now=1000;bus.clock_base=hass.loop.time()-1
    class Receiver:
        async def receive(self,topic,raw):
            callbacks["message"](SimpleNamespace(topic="fixture/v1/"+topic,payload=raw,retain=False))
            await native.queue.join()
    bus.client=Receiver()
    async def start_native():
        nonlocal runtime,native,client
        assert await integration.async_setup_entry(hass,parent)
        state=hass.data["open_thermostat"][parent.entry_id]
        runtime=state["v1_runtime"];native=state["v1_connection"];client=native.client
        client.clock=bus.clock  # Existing receiver-local monotone clock test boundary.
        for binding in bindings:runtime.set_report_profile(binding.room_id,source_profile)
        if current:=holder.get("value"):
            current.runtime,current.native,current.client=runtime,native,client
    async def stop_native():
        assert await integration.async_unload_entry(hass,parent)
        await parent._async_process_on_unload(hass)
        assert native.worker.done() and native.timer is None
        assert not runtime._subscriptions and not runtime._expiries
    async def drain():
        for _ in range(128):
            await native.queue.join();await hass.async_block_till_done()
            if not publications:return
            topic,body=publications.popleft();bus.transcript.append(("ha",topic,body))
            await bus.event("receive",topic=topic,raw=body)
        raise AssertionError("bounded native worker did not drain")
    serial=0
    async def observe(values=(18,20)):
        nonlocal serial
        for binding,value in zip(bindings,values):
            serial+=1;physical_state(hass,binding,key=f"actual-fixture-{serial}",value=str(value))
        await hass.async_block_till_done();await drain()
    async def command(awaitable):
        task=asyncio.create_task(awaitable)
        for _ in range(128):
            await drain()
            if task.done():return await task
            await asyncio.sleep(.001)
        task.cancel();raise AssertionError("native command did not finish")
    holder={}
    runtime=native=client=None
    await start_native()
    n=SimpleNamespace(parent=parent,bindings=bindings,approved=approved,profile=profile,
        runtime=runtime,native=native,client=client,bus=bus,callbacks=callbacks,
        publications=publications,services=services,removed=removed,drain=drain,
        observe=observe,command=command,start_native=start_native,stop_native=stop_native,
        reload_call=reload_call)
    holder["value"]=n
    try:
        if mode not in ("plain","missing"):
            await bus.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,dhw_active=False)
        await bus.event("connect");await bus.event("tick");await drain()
        yield n
    finally:
        if parent.entry_id in hass.data.get("open_thermostat",{}):await stop_native()
        process.stdin.close();await asyncio.wait_for(process.wait(),5)
        assert process.returncode==0
        assert not services
        assert removed.count("mqtt")==removed.count("status")

@pytest.mark.asyncio
async def test_native_two_zone_source_apply_persist_exact_readback_and_status(composed):
    n=composed
    assert n.client.ready and n.client.source_policy_matched
    opens=[json.loads(raw) for who,topic,raw in n.bus.transcript if who=="ha" and topic=="ha/open_session"]
    assert opens and all(p["source_profile_digest"]==n.profile.profile_digest and p["source_config_pin"]==n.profile.config_digest for p in opens)
    assert n.client.journal["accepted"]["config"]==n.approved
    assert (await n.client.store.async_load())["accepted"]==n.client.journal["accepted"]
    await n.observe();await n.observe()
    rows=n.runtime.decisions
    assert {z:state.target_centi_c for z,state in rows.items()}=={"a1b2c3d4":2100,"11223344":1900}
    assert rows["a1b2c3d4"].demand and not rows["11223344"].demand
    snapshots=[json.loads(raw) for who,topic,raw in n.bus.transcript if who=="fw" and topic=="fw/config_snapshot"]
    assert any(p["config"]==n.approved for p in snapshots)
    states=[json.loads(raw) for who,topic,raw in n.bus.transcript if who=="fw" and topic=="fw/state/zones"]
    assert all(p["boiler_output_enabled"] is p["actuator_output_enabled"] is False for p in states)
    assert all(p["supervisor"]["physical_outputs_enabled"] is False for p in states)
    evidence(dict(scenario="native_entry_two_zones_source_readback",targets=[2100,1900],
        actual_store_readback=True,exact_cpp_snapshot=True,profile_identity_verified=True,
        physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("composed",["missing","anonymous","wrong_controller","wrong_profile","wrong_owner","wrong_pin","unselected"],indirect=True)
async def test_wrong_missing_or_unselected_firmware_profile_never_stages_or_sends_config(composed):
    n=composed
    assert not n.client.ready and not n.runtime.transport_ready
    assert n.client.journal=={"accepted":None,"staged":None}
    assert not any(who=="ha" and topic=="ha/config" for who,topic,_ in n.bus.transcript)
    assert n.client.error in ("controller_policy_mismatch","controller_policy_not_selected")
    assert n.client.grant_until==n.client.lease_until==0
    attrs=ShadowRoom("fixture",n.bindings[0],n.runtime).extra_state_attributes
    assert attrs["transport_status"]==n.client.error
    assert attrs["boiler_output_enabled"] is attrs["actuator_output_enabled"] is False
    evidence(dict(scenario="reject_"+n.client.error,config_publications=0,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_explicit_alloff_and_dhw_preempt_local_boost_without_physical_output(composed):
    n=composed
    await n.observe();await n.observe()
    await n.command(n.runtime.async_comfort("a1b2c3d4","boost",temperature=23,duration_ms=60000))
    assert n.runtime.decisions["a1b2c3d4"].target_centi_c==2300
    await n.bus.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,summer=True)
    await n.observe()
    assert not any(x.demand for x in n.runtime.decisions.values())
    await n.bus.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,all_off=True)
    await n.observe()
    assert not any(x.demand for x in n.runtime.decisions.values())
    await n.bus.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,dhw_active=True)
    await n.observe()
    assert not any(x.demand for x in n.runtime.decisions.values())
    assert all(x.reason=="seasonal_dhw_priority" for x in n.runtime.decisions.values())
    evidence(dict(scenario="summer_alloff_and_dhw_win_boost",source_pin_unchanged=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_restart_old_grant_not_restored_and_source_readback_is_not_old_temperature(composed):
    n=composed
    await n.observe();await n.observe()
    await n.command(n.runtime.async_comfort("a1b2c3d4","boost",temperature=23,duration_ms=60000))
    assert n.runtime.decisions["a1b2c3d4"].target_centi_c==2300
    old=next(raw for who,topic,raw in reversed(n.bus.transcript) if who=="ha" and topic=="ha/observations")
    accepted=n.client.journal["accepted"]
    old_grant=json.loads(old)["grant_id"]
    await n.bus.event("boot",boot_id="boot2")
    await n.bus.event("connect");await n.bus.event("tick");await n.drain()
    assert n.client.ready and n.client.source_policy_matched
    assert n.client.journal["accepted"]==accepted
    assert n.client.session["grant_id"]!=old_grant
    assert not any(x.demand for x in n.runtime.decisions.values())
    await n.bus.event("receive",topic="ha/observations",raw=old);await n.drain()
    assert not any(x.demand for x in n.runtime.decisions.values())
    assert not n.services
    await n.observe();await n.observe()
    assert n.runtime.decisions["a1b2c3d4"].target_centi_c==2100
    evidence(dict(scenario="boot_keeps_config_not_grant_sample_or_boost",exact_readback=True,old_grant_rejected=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_selected_source_changed_configuration_is_not_implicitly_requalified(composed):
    n=composed
    accepted=n.client.journal["accepted"]
    desired=json.loads(canonical(n.client.desired));desired[0]["base_centi_c"]+=50
    n.client.desired=desired
    await n.client.propose(1);await n.drain()
    assert n.client.error=="controller_policy_config_mismatch"
    assert not n.client.ready and n.client.grant_until==n.client.lease_until==0
    assert n.client.journal["accepted"]==accepted and n.client.journal["staged"] is None
    assert sum(who=="ha" and topic=="ha/config" for who,topic,_ in n.bus.transcript)==1
    evidence(dict(scenario="config_edit_requires_new_reviewed_source_pin",no_implicit_requalification=True,physical_outputs_enabled=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("composed",["plain"],indirect=True)
async def test_existing_api1_native_reconfigure_unload_reload_persists_changed_readback(composed,hass):
    n=composed
    assert n.client.ready and n.client.controller_policy is None
    await n.observe()
    before=n.client.journal["accepted"]
    old_native=n.native
    await n.stop_native()
    assert old_native.worker.done() and old_native.timer is None
    sub=next(s for s in n.parent.subentries.values() if s.data["room_id"]=="a1b2c3d4")
    room_data=RoomBinding.from_dict(dict(sub.data))
    manager=hass.config_entries.subentries
    form=await manager.async_init((n.parent.entry_id,"zone"),context={"source":"reconfigure","subentry_id":sub.subentry_id})
    assert FlowManagerIndexView(manager)._prepare_result_json(form)["data_schema"]
    result=await manager.async_configure(form["flow_id"],{
        "name":room_data.name,"temperature_entity":room_data.temperature.entity_id,
        "actuator_entities":[x.entity_id for x in room_data.actuators],
        "base_temperature":22,"comfort_enabled":True,"override_minutes":1})
    assert result["type"]=="abort" and result["reason"]=="reconfigure_successful",result
    assert sub.data["base_centi_c"]==2200
    await n.start_native()
    assert n.client.journal["accepted"]==before and not n.client.ready
    await n.bus.event("disconnect");await n.bus.event("connect");await n.bus.event("tick");await n.drain()
    assert n.client.ready and n.client.journal["accepted"]["config"]["revision"]==2
    await n.observe()
    assert n.runtime.decisions["a1b2c3d4"].target_centi_c==2200
    assert n.runtime.decisions["11223344"].target_centi_c==1900
    assert (await n.client.store.async_load())["accepted"]==n.client.journal["accepted"]
    evidence(dict(scenario="native_reconfigure_unload_reload_exact_revision2",targets=[2200,1900],
        source_selected=False,prior_journal_kept=True,old_worker_stopped=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("fault",["schema","profile","owner","pin","physical","missing"])
async def test_current_scope_profile_corruption_withdraws_admission_without_deadline_extension(composed,fault):
    n=composed
    await n.observe();await n.observe()
    frame=next(json.loads(raw) for who,topic,raw in reversed(n.bus.transcript) if who=="fw" and topic=="fw/state/zones")
    if fault=="schema":frame["source_policy"]["schema"]=2
    elif fault=="profile":frame["source_policy"]["profile_digest"]="0"*64
    elif fault=="owner":frame["source_policy"]["adapter_id"]="other"
    elif fault=="pin":frame["source_policy"]["config_pin"]="0"*64
    elif fault=="physical":frame["source_policy"]["physical_outputs_enabled"]=True
    else:frame.pop("source_policy")
    n.callbacks["message"](SimpleNamespace(topic="fixture/v1/fw/state/zones",payload=canonical(frame),retain=False))
    await n.native.queue.join()
    assert not n.client.ready and not n.runtime.decisions
    assert n.client.error=="controller_policy_mismatch"
    assert n.client.grant_until==n.client.lease_until==0
    evidence(dict(scenario="reject_source_state_"+fault,no_cached_admission=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_retained_valid_profile_state_cannot_refresh_or_recover_after_disconnect(composed):
    n=composed
    await n.observe();await n.observe()
    raw=next(raw for who,topic,raw in reversed(n.bus.transcript) if who=="fw" and topic=="fw/state/zones")
    before=(n.client.grant_until,n.client.lease_until,n.client.last_rx)
    n.callbacks["message"](SimpleNamespace(topic="fixture/v1/fw/state/zones",payload=raw,retain=True))
    await n.native.queue.join()
    assert before==(n.client.grant_until,n.client.lease_until,n.client.last_rx)
    n.callbacks["status"](False);await n.native.queue.join()
    assert not n.client.ready and not n.client.source_policy_matched
    n.callbacks["message"](SimpleNamespace(topic="fixture/v1/fw/state/zones",payload=raw,retain=False))
    await n.native.queue.join()
    assert not n.client.ready and not n.runtime.decisions
    evidence(dict(scenario="retained_or_old_scoped_profile_cannot_restore_after_disconnect",physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("bad",["duplicate","wrong_adapter","schema","graph","direct_graph_connection","other_transport"])
async def test_source_entry_binding_rejects_unsupported_profile_before_transport(hass,monkeypatch,bad):
    from custom_components.open_thermostat.graph_wire import GraphSourceProfile
    binding=room(hass);parent=entry(hass,enabled=True,room=binding)
    profile=ControllerPolicySourceProfile(parent.unique_id,"e32_lab","ha1","1"*64,"2"*64)
    if bad=="schema":profile=replace(profile,schema=2)
    if bad=="wrong_adapter":profile=replace(profile,adapter_id="other")
    if bad in ("direct_graph_connection","other_transport"):
        from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
        from homeassistant.exceptions import HomeAssistantError
        from test_v1_native import LocalTransport
        runtime=ShadowRuntime(hass,parent,[binding],controller_policy_source_profile=profile)
        if bad=="direct_graph_connection":
            with pytest.raises(ConfigEntryError,match="controller_policy_graph_conflict"):
                await NativeShadowConnection(runtime,GraphSourceProfile("e32_lab","a"*64)).async_start()
        else:
            with pytest.raises(HomeAssistantError,match="controller_policy_transport_mismatch"):
                runtime.attach_transport(LocalTransport())
        return
    if bad=="graph":
        with pytest.raises(ValueError,match="controller_policy_profile_binding"):
            ShadowRuntime(hass,parent,[binding],graph_data_profile=GraphSourceProfile("e32_lab","a"*64),controller_policy_source_profile=profile)
        return
    monkeypatch.setattr(integration,"_CONTROLLER_POLICY_SOURCE_PROFILES",(profile,profile) if bad=="duplicate" else (profile,))
    subscribe=AsyncMock();monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    with pytest.raises(ConfigEntryError):await integration.async_setup_entry(hass,parent)
    assert not subscribe.called and parent.entry_id not in hass.data.get("open_thermostat",{})


@pytest.mark.asyncio
async def test_selected_source_native_entry_unload_reload_requalifies_identity_but_not_cached_sample(composed):
    n=composed
    await n.observe();await n.observe()
    accepted=n.client.journal["accepted"];old_grant=n.client.session["grant_id"]
    old=n.native
    await n.stop_native();assert old.worker.done() and old.timer is None
    await n.start_native()
    assert n.client.journal["accepted"]==accepted and not n.client.ready and not n.client.source_policy_matched
    await n.bus.event("disconnect");await n.bus.event("connect");await n.bus.event("tick");await n.drain()
    assert n.client.ready and n.client.source_policy_matched and n.client.session["grant_id"]!=old_grant
    assert n.client.journal["accepted"]==accepted
    assert not any(state.demand for state in n.runtime.decisions.values())
    attrs=ShadowRoom("fixture",n.bindings[0],n.runtime).extra_state_attributes
    assert attrs["controller_policy_status"]=="source_identity_verified_shadow_only"
    assert attrs["boiler_output_enabled"] is attrs["actuator_output_enabled"] is False
    evidence(dict(scenario="source_native_unload_reload_requires_new_session_and_reports",profile_reverified=True,physical_outputs_enabled=False))
