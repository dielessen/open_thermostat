"""Native HA operations against the actual finite C++ ShadowController peer.
No device/broker/service writes. Native HA lifecycle; process IO is test boundary.
"""
import asyncio
from dataclasses import replace
from datetime import timedelta, datetime, timezone
import logging
import os
import json

import pytest
import pytest_asyncio
from homeassistant.helpers.storage import Store
from homeassistant.helpers import entity_registry as er, device_registry as dr, entity_platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat.v1_wire import ShadowClient, canonical
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_model import RoomBinding, Observation
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_climate import ShadowRoom
from custom_components.open_thermostat.v1_config_flow import reference
from test_v1_native import room, entry, source_profile
from test_v1_wire_interop import FirmwareBus, RUNNER

@pytest_asyncio.fixture
async def comfort(hass,request,monkeypatch):
    registry=er.async_get(hass)
    window=registry.async_get_or_create("binary_sensor","comfort_fixture","window")
    person=registry.async_get_or_create("person","comfort_fixture","presence")
    hass.states.async_set(window.entity_id,"off")
    hass.states.async_set(person.entity_id,"home")
    binding=replace(room(hass,age=120000),maximum_target_centi_c=2500,comfort={"away_centi_c":1600,"frost_centi_c":500,"temporary_ms":60000},
                    window=reference(hass,window.entity_id),presence=reference(hass,person.entity_id))
    options=request.param if hasattr(request,'param') else {}
    if options.get('contacts'):
        from custom_components.open_thermostat.room_contacts import select_contacts,ContactPolicy
        door=registry.async_get_or_create('binary_sensor','comfort_fixture','door')
        hass.states.async_set(window.entity_id,'off',{'device_class':'window'})
        hass.states.async_set(door.entity_id,'off',{'device_class':'door'})
        binding=replace(binding,window=None,presence=None,
            contacts=select_contacts(hass,[window.entity_id,door.entity_id]),
            contact_policy=ContactPolicy(options.get('maximum_age_ms',3600000),0,options.get('close_delay_ms',0)))
        if options.get('contact_only'):binding=replace(binding,comfort=None)
    second=replace(room(hass,"11223344","second"),comfort=dict(binding.comfort) if binding.comfort else None)
    parent=entry(hass,enabled=True,room=binding)
    runtime=ShadowRuntime(hass,parent,[binding,second])
    zones,mapping=await async_build_configuration(runtime)
    process=await asyncio.create_subprocess_exec(str(RUNNER),stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    bus=FirmwareBus(process,hass.loop.time)
    if options.get('contacts'):runtime.clock=bus.clock
    if options.get('contact_timers'):
        import custom_components.open_thermostat.v1_runtime as native_runtime
        native_later=native_runtime.async_call_later
        bus.contact_timers={}
        def schedule(hass,delay,action):
            if action.__name__!='contact_due':return native_later(hass,delay,action)
            bus.contact_timers[action]=bus.clock()+delay
            return lambda:bus.contact_timers.pop(action,None)
        monkeypatch.setattr(native_runtime,'async_call_later',schedule)
    bus.utc=int(dt_util.utcnow().timestamp())
    client=ShadowClient(runtime,"ha1",bus.send,Store(hass,1,"test.comfort."+parent.entry_id),zones,mapping,bus.clock)
    bus.client=client;runtime.attach_transport(client)
    await client.async_start();await runtime.async_start()
    try:
        yield runtime,client,bus,binding,second
    finally:
        await runtime.async_stop()
        process.stdin.close()
        await asyncio.wait_for(process.wait(),5)
        assert process.returncode==0

async def command(bus,awaitable):
    task=asyncio.create_task(awaitable)
    deadline=asyncio.get_running_loop().time()+2
    while not task.done() and asyncio.get_running_loop().time()<deadline:
        await asyncio.sleep(0.001)
        await bus.pump()
    return await asyncio.wait_for(task,0.1)

async def observe(runtime,client,bus,binding):
    # Synthetic temperature evidence isolates comfort/firmware policy here.
    # A native report owner is still required when context events forward it.
    if binding.room_id not in runtime._profiles:
        runtime.set_report_profile(binding.room_id,source_profile)
    runtime.observations[binding.room_id]=Observation(19,"qualified",0,"report",runtime.hass.loop.time())
    await client.async_observation(binding.room_id,Observation(19,"qualified",0,"report",bus.clock()))
    await bus.pump()
    return runtime.decisions[binding.room_id]

@pytest.mark.asyncio
async def test_native_desired_profile_durable_readback_and_visible_local_default_expiry(comfort):
    runtime,client,bus,binding,_=comfort
    await bus.start()
    assert client.ready and client.comfort_supported
    saved=client.journal["accepted"]["config"]
    assert saved["zones"][1]["comfort"]["window"] is True
    assert saved["zones"][1]["comfort"]["presence"] is True
    assert saved["zones"][1]["comfort"]["temporary_ms"]==60000
    await observe(runtime,client,bus,binding)
    await command(bus,runtime.async_set_temperature(binding.room_id,23))
    state=runtime.decisions[binding.room_id]
    assert (state.target_centi_c,state.comfort_mode,state.target_source,state.override_remaining_ms)==(2300,"temporary","temporary",60000)
    entity=ShadowRoom("fixture",binding,runtime)
    assert entity.extra_state_attributes["default_override_minutes"]==1
    assert entity.extra_state_attributes["local_override_ends_on_presence_change"] is False
    # Every original retry keeps bytes; crossing local expiry never replays it.
    for _ in range(30):await bus.advance(2000)
    assert runtime.decisions[binding.room_id].override_remaining_ms==0
    assert runtime.decisions[binding.room_id].target_centi_c==2100
    assert client.ready
    requests=[json.loads(raw) for who,topic,raw in bus.transcript if who=="ha" and topic=="ha/user_command"]
    assert len(requests)==1

@pytest.mark.asyncio
async def test_zone_contact_conflict_manual_survives_presence_and_away_resumes(comfort,hass):
    runtime,client,bus,binding,second=comfort
    await bus.start()
    await observe(runtime,client,bus,binding);await observe(runtime,client,bus,second)
    await command(bus,runtime.async_comfort(binding.room_id,"away"))
    await command(bus,runtime.async_comfort(binding.room_id,"boost",temperature=23,duration_ms=1000))
    hass.states.async_set(binding.presence.entity_id,"not_home")
    await hass.async_block_till_done();await bus.pump()
    assert runtime.decisions[binding.room_id].target_centi_c==2300
    hass.states.async_set(binding.window.entity_id,"on")
    await hass.async_block_till_done();await bus.pump()
    assert runtime.decisions[binding.room_id].target_centi_c is None
    assert runtime.decisions[second.room_id].target_centi_c==2100
    assert runtime.decisions[second.room_id].demand is True
    await bus.advance(1000)
    hass.states.async_set(binding.window.entity_id,"off")
    await hass.async_block_till_done();await bus.pump()
    assert runtime.decisions[binding.room_id].target_centi_c==1600
    assert runtime.decisions[binding.room_id].comfort_mode=="away"

@pytest.mark.asyncio
async def test_unknown_presence_is_not_away_frost_precedes_window_but_off_removes_demand(comfort,hass):
    runtime,client,bus,binding,_=comfort
    await bus.start();await observe(runtime,client,bus,binding)
    hass.states.async_set(binding.presence.entity_id,"unknown")
    await hass.async_block_till_done();await bus.pump()
    decision=runtime.decisions[binding.room_id]
    assert decision.target_centi_c is None and decision.reason=="presence_state_unknown"
    hass.states.async_set(binding.window.entity_id,"on")
    await hass.async_block_till_done();await bus.pump()
    await command(bus,runtime.async_comfort(binding.room_id,"frost"))
    assert runtime.decisions[binding.room_id].target_centi_c==500
    await command(bus,runtime.async_comfort(binding.room_id,"off"))
    assert runtime.decisions[binding.room_id].target_centi_c is None
    assert runtime.decisions[binding.room_id].demand is False
    for who,topic,raw in bus.transcript:
        if topic=="fw/state/zones":
            state=json.loads(raw)
            assert state["boiler_output_enabled"] is False
            assert state["actuator_output_enabled"] is False
            assert state["supervisor"]["physical_outputs_enabled"] is False

@pytest.mark.asyncio
async def test_reconnect_and_new_boot_dont_replay_local_choice(comfort):
    runtime,client,bus,binding,_=comfort
    await bus.start();await observe(runtime,client,bus,binding)
    await command(bus,runtime.async_comfort(binding.room_id,"boost",temperature=23,duration_ms=60000))
    old_commands=[x for x in bus.transcript if x[0:2]==("ha","ha/user_command")]
    await bus.event("disconnect");await client.async_disconnected()
    await bus.start()
    assert client.ready
    assert runtime.decisions[binding.room_id].comfort_mode=="auto"
    assert runtime.decisions[binding.room_id].override_remaining_ms==0
    await bus.event("boot",boot_id="boot2");await client.async_disconnected();await bus.start()
    assert client.ready
    assert runtime.decisions[binding.room_id].comfort_mode=="auto"
    assert [x for x in bus.transcript if x[0:2]==("ha","ha/user_command")]==old_commands

@pytest.mark.asyncio
async def test_vacation_requires_clock_fails_on_loss_and_expires_without_revival(comfort):
    runtime,client,bus,binding,_=comfort
    await bus.start();await observe(runtime,client,bus,binding)
    expiry=bus.utc+60
    await command(bus,runtime.async_comfort(binding.room_id,"vacation",vacation_until_utc=expiry))
    assert runtime.decisions[binding.room_id].target_centi_c==1600
    bus.now+=3000;await bus.event("tick",clock_valid=False)
    assert runtime.decisions[binding.room_id].target_centi_c is None
    assert runtime.decisions[binding.room_id].reason=="vacation_time_invalid"
    bus.utc=expiry;bus.now+=3000;await bus.event("tick")
    assert runtime.decisions[binding.room_id].target_centi_c==2100
    assert runtime.decisions[binding.room_id].vacation_until_utc==0
    bus.utc-=60;bus.now+=3000;await bus.event("tick")
    assert runtime.decisions[binding.room_id].target_centi_c==2100

@pytest.mark.asyncio
async def test_unsupported_peer_refuses_profile_before_any_config_write(comfort):
    runtime,client,bus,binding,_=comfort
    await bus.event("connect")
    # Real C++ hello, remove ONLY feature advertisement to emulate old version.
    bus.drop=lambda item:item["topic"]=="fw/hello"
    rows=await bus.event("tick")
    hello=next(item["payload"] for item in rows if item["topic"]=="fw/hello")
    hello.pop("control_capabilities")
    before=len(bus.transcript)
    await client.receive("fw/hello",canonical(hello))
    assert not client.ready and client.error=="comfort_capability_unavailable"
    assert not any(who=="ha" and topic=="ha/config" for who,topic,_ in bus.transcript[before:])

@pytest.mark.asyncio
async def test_context_reread_and_wall_clock_reversal_never_renews_original_age(comfort,hass,monkeypatch):
    runtime,client,bus,binding,_=comfort
    first=runtime.comfort_context(binding)
    assert first["presence_away"] is False
    cached=runtime._comfort_context_cache[(binding.room_id,"presence")]
    past=dt_util.utcnow()-timedelta(days=1)
    monkeypatch.setattr(dt_util,"utcnow",lambda:past)
    again=runtime.comfort_context(binding)
    assert again["presence_away"] is False
    assert runtime._comfort_context_cache[(binding.room_id,"presence")]==cached
    # Same HA state, local monotonic deadline expired: even reversed UTC cannot revive it.
    runtime._comfort_context_cache[(binding.room_id,"presence")]=(cached[0],cached[1],cached[2]-121,cached[3])
    assert runtime.comfort_context(binding)["presence_away"] is None

@pytest.mark.asyncio
async def test_native_room_config_form_persists_opt_in_bindings_and_validates_bounds(comfort,hass):
    runtime,client,bus,binding,_=comfort
    from test_v1_room_target_bounds import flow,inputs
    f=flow(hass,runtime.entry)
    form=await f.async_step_user()
    raw=inputs(binding,room_id="99887766",minimum_target_temperature=5,maximum_target_temperature=25,
        comfort_enabled=True,away_temperature=16,frost_temperature=5,override_minutes=7,
        window_entity=binding.window.entity_id,presence_entity=binding.presence.entity_id)
    # Isolate create from duplicate native room binding validation.
    new=room(hass,"99887766","newcomfort")
    raw.update(temperature_entity=new.temperature.entity_id,actuator_entities=[new.actuators[0].entity_id])
    result=await f.async_step_user(form["data_schema"](raw))
    assert result["type"]=="create_entry"
    restored=RoomBinding.from_dict(result["data"])
    assert restored.comfort["temporary_ms"]==420000
    assert restored.window==binding.window and restored.presence==binding.presence
    assert RoomBinding.from_dict(restored.as_dict())==restored
    bad=restored.as_dict();bad["comfort"]["away_centi_c"]=2600
    with pytest.raises(ValueError):RoomBinding.from_dict(bad)

@pytest.mark.asyncio
async def test_native_climate_platform_service_and_preset_use_admitted_fw_state(comfort,hass):
    runtime,client,bus,binding,_=comfort
    from custom_components.open_thermostat.climate import async_setup_entry
    dr.async_get(hass).async_get_or_create(config_entry_id=runtime.entry.entry_id,identifiers={("open_thermostat","fixture")})
    hass.data["open_thermostat"]={runtime.entry.entry_id:{"v1_runtime":runtime}}
    platform=entity_platform.EntityPlatform(hass=hass,logger=logging.getLogger(__name__),domain="climate",
        platform_name="open_thermostat",platform=None,scan_interval=timedelta(seconds=30),entity_namespace=None)
    platform.config_entry=runtime.entry
    token=entity_platform.current_platform.set(platform)
    tasks=[]
    def add(entities,*,config_subentry_id=None):
        tasks.append(hass.async_create_task(platform.async_add_entities(entities,config_subentry_id=config_subentry_id)))
    try:
        await async_setup_entry(hass,runtime.entry,add);await asyncio.gather(*tasks)
        await bus.start();await observe(runtime,client,bus,binding)
        entity=next(iter(platform.entities.values()))
        await command(bus,hass.services.async_call("open_thermostat","set_comfort",
            {"entity_id":entity.entity_id,"mode":"boost","temperature":23,"duration_minutes":1},blocking=True))
        await hass.async_block_till_done()
        state=hass.states.get(entity.entity_id)
        assert state.attributes["comfort_mode"]=="boost" and state.attributes["override_remaining_ms"]==60000
        assert state.attributes["temperature"]==23 and state.attributes["hvac_action"]=="idle"
        await command(bus,entity.async_set_preset_mode("away"))
        assert entity.preset_mode=="away"
        end=datetime.fromtimestamp(bus.utc+60,timezone.utc).isoformat()
        await command(bus,hass.services.async_call("open_thermostat","set_comfort",
            {"entity_id":entity.entity_id,"mode":"vacation","vacation_until":end},blocking=True))
        assert runtime.decisions[binding.room_id].vacation_until_utc==bus.utc+60
        with pytest.raises(HomeAssistantError):
            await entity.async_set_comfort("vacation",vacation_until="2026-10-25T02:30:00")
        with pytest.raises(HomeAssistantError):await entity.async_set_comfort("boost",temperature=30)
    finally:
        entity_platform.current_platform.reset(token)
        await platform.async_reset()

@pytest.mark.asyncio
@pytest.mark.parametrize("date",["2026-03-28","2026-10-24"])
async def test_actual_compiled_dst_schedule_and_monotonic_override_independent_of_wall_jump(comfort,date):
    runtime,client,bus,binding,second=comfort
    from custom_components.open_thermostat.schedule_compiler import compile_week,WEEKDAYS
    # Real schedule compiler for Europe/Amsterdam spring and fall; no second scheduler.
    start=int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())
    program={day:[] for day in WEEKDAYS}
    program["sunday"]=[{"from":"01:30","to":"03:30","data":{"temperature":22}}]
    # Existing compiler accepts native float Celsius, not centi editor schema.
    schedule=compile_week(program,2100,"Europe/Amsterdam",start,start+4*86400)
    binding=replace(binding,window=None,presence=None)
    runtime.rooms[binding.room_id]=binding
    zones,mapping=await async_build_configuration(runtime)
    next(z for z in zones if z["zone_id"]==binding.room_id)["schedule"]=schedule
    client.desired,client.mapping=zones,mapping
    bus.utc=start+86400
    await bus.start();await observe(runtime,client,bus,binding)
    await command(bus,runtime.async_comfort(binding.room_id,"temporary",temperature=23,duration_ms=1000))
    bus.utc+=7200;bus.now+=1000
    # Observation forces a state publication exactly at monotone expiry.
    decision=await observe(runtime,client,bus,binding)
    expected=next(value for time,value in reversed(schedule["transitions"]) if time<=bus.utc)
    assert decision.override_remaining_ms==0 and decision.target_centi_c==expected
    assert decision.target_source=="schedule"


@pytest.mark.asyncio
async def test_actual_duplicate_command_does_not_extend_own_expiry_and_invalid_duration_is_local(comfort):
    runtime,client,bus,binding,_=comfort
    await bus.start();await observe(runtime,client,bus,binding)
    await command(bus,runtime.async_comfort(binding.room_id,"boost",temperature=23,duration_ms=1000))
    raw=next(raw for who,topic,raw in reversed(bus.transcript) if who=="ha" and topic=="ha/user_command")
    bus.now+=500
    await bus.event("receive",topic="ha/user_command",raw=raw)
    await client.message("ha/snapshot_request","snapshot",{});await bus.pump()
    assert runtime.decisions[binding.room_id].override_remaining_ms==500
    assert runtime.decisions[binding.room_id].target_centi_c==2300
    before=len(bus.transcript)
    with pytest.raises(HomeAssistantError):
        await runtime.async_comfort(binding.room_id,"boost",temperature=23,duration_ms=True)
    assert len(bus.transcript)==before
    with pytest.raises(HomeAssistantError):
        await runtime.async_comfort(binding.room_id,"boost",temperature=float("nan"))
    bus.now+=500
    await client.message("ha/snapshot_request","snapshot",{});await bus.pump()
    assert runtime.decisions[binding.room_id].override_remaining_ms==0
    assert runtime.decisions[binding.room_id].target_centi_c==2100

def test_native_action_yaml_keeps_off_a_string_and_human_time_fields():
    from pathlib import Path
    from homeassistant.util.yaml import load_yaml
    path=Path(__file__).parents[1]/"config/custom_components/open_thermostat/services.yaml"
    service=load_yaml(str(path))["set_comfort"]
    assert service["fields"]["mode"]["selector"]["select"]["options"]==["auto","off","temporary","boost","away","vacation","frost"]
    assert set(service["fields"])=={"mode","temperature","duration_minutes","vacation_until"}
