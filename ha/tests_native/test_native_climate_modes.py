"""Native HA climate commands -> existing finite C++ controller; no hardware."""
import asyncio,json,logging,os
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import pytest
import pytest_asyncio
from homeassistant.components import climate as ha_climate
from homeassistant.components.climate.const import HVACMode,HVACAction
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr,entity_platform
from custom_components.open_thermostat.v1_climate import ShadowRoom,async_setup_entry
from test_two_room_controller import two_controller,native_two

@pytest_asyncio.fixture
async def native_climates(two_controller,hass):
    n=two_controller
    await ha_climate.async_setup(hass,{})
    dr.async_get(hass).async_get_or_create(config_entry_id=n.parent.entry_id,identifiers={("open_thermostat","fixture")})
    platform=entity_platform.EntityPlatform(hass=hass,logger=logging.getLogger(__name__),domain="climate",
        platform_name="open_thermostat",platform=None,scan_interval=timedelta(seconds=30),entity_namespace=None)
    platform.config_entry=n.parent
    token=entity_platform.current_platform.set(platform);tasks=[]
    def add(entities,*,config_subentry_id=None):
        tasks.append(hass.async_create_task(platform.async_add_entities(entities,config_subentry_id=config_subentry_id)))
    try:
        await async_setup_entry(hass,n.parent,add);await asyncio.gather(*tasks)
        entities={e.room.room_id:e for e in platform.entities.values()}
        assert set(entities)=={n.rad.room_id,n.floor.room_id}
        n.entities=entities
        yield n
    finally:
        entity_platform.current_platform.reset(token)
        await platform.async_reset()

async def command(n,awaitable):
    # Native HA services are tracked tasks: block_till_done() before delivering
    # their pending firmware ACK would wait on the very command being pumped.
    # Drive ONLY existing finite worker/peer queues until that task completes.
    task=asyncio.create_task(awaitable)
    try:
        for _ in range(300):
            await n.connection.queue.join()
            if n.pending:
                topic,raw=n.pending.popleft()
                await n.event("receive",topic=topic,raw=raw)
            elif task.done():
                return await task
            else:
                await asyncio.sleep(.001)
        raise AssertionError("bounded native climate service deadline")
    finally:
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)

def record(n,scenario):
    if path:=os.environ.get("OPENTHERMOSTAT_CLIMATE_MODES_EVIDENCE"):
        rows={k:dict(hvac_mode=e.hvac_mode,target=e.target_temperature,
                    demand=n.runtime.decisions[k].demand if k in n.runtime.decisions else None,
                    available=e.available) for k,e in n.entities.items()}
        with Path(path).open("a") as f:f.write(json.dumps(dict(scenario=scenario,rooms=rows,
            physical_outputs_enabled=False,writes=0),sort_keys=True)+"\n")

@pytest.mark.asyncio
async def test_native_entities_offer_owned_heat_off_without_claiming_real_heating(native_climates,hass):
    n=native_climates;await n.settle(16,16)
    for e in n.entities.values():
        assert e.hvac_modes==[HVACMode.HEAT,HVACMode.OFF]
        assert e.hvac_mode==HVACMode.HEAT and e.hvac_action==HVACAction.IDLE
        state=hass.states.get(e.entity_id)
        assert state.attributes["hvac_modes"]==["heat","off"]
        assert state.attributes["actuator_output_enabled"] is False

@pytest.mark.asyncio
@pytest.mark.parametrize("trace_attempt", range(8))
async def test_real_native_climate_services_stop_A_then_B_and_resume_only_A(native_climates,hass,trace_attempt):
    n=native_climates;await n.settle(16,16)
    a,b=n.entities[n.rad.room_id],n.entities[n.floor.room_id]
    async def service(entity,mode):
        await command(n,hass.services.async_call("climate","set_hvac_mode",
            {"entity_id":entity.entity_id,"hvac_mode":mode},blocking=True))
        await hass.async_block_till_done()
    await service(a,"off")
    # Synthetic finite fixture inputs only: keep an exact C++ replay even if
    # the timing assertion fails in a faster/different CI environment.
    trace_path=Path(f"out/climate-warmup-trace-{trace_attempt}.json")
    trace_path.parent.mkdir(parents=True,exist_ok=True)
    trace_path.write_text(json.dumps(dict(clock=n.peer.clock,
        clock_domains=dict(runtime=n.runtime.clock(), transport=n.client.clock(), host_loop=hass.loop.time()),
        observations={key:dict(source_age_ms=value.source_age_ms,
            observed_monotonic=value.observed_monotonic, quality=value.quality)
            for key,value in n.runtime.observations.items()},
        events=[dict(op=op,**args) for op,args,_ in n.peer.trace],
        decisions={k:vars(v) for k,v in n.runtime.decisions.items()}),default=str))
    assert a.hvac_mode==HVACMode.OFF and a.target_temperature is None
    assert not n.runtime.decisions[n.rad.room_id].demand and n.runtime.decisions[n.floor.room_id].demand, n.runtime.decisions
    assert b.hvac_mode==HVACMode.HEAT and b.target_temperature==19
    await service(b,"off")
    assert all(not s.demand for s in n.runtime.decisions.values())
    assert all(e.hvac_mode==HVACMode.OFF for e in n.entities.values())
    assert all(hass.states.get(e.entity_id).state=="off" for e in n.entities.values())
    record(n,"native_services_both_off")
    await service(a,"heat")
    assert a.hvac_mode==HVACMode.HEAT and a.target_temperature==21
    assert b.hvac_mode==HVACMode.OFF and b.target_temperature is None
    assert not n.runtime.decisions[n.floor.room_id].demand
    assert a.hvac_action==b.hvac_action==HVACAction.IDLE
    record(n,"native_service_only_A_resumed")
    assert all(not e.extra_state_attributes["actuation_enabled"] for e in n.entities.values())

@pytest.mark.asyncio
async def test_native_turn_off_on_helpers_reuse_same_command_and_auto_target(native_climates):
    n=native_climates;await n.settle(16,16)
    a=n.entities[n.rad.room_id]
    await command(n,a.async_set_temperature(temperature=22))
    assert a.target_temperature==22
    await command(n,a.async_turn_off())
    assert a.hvac_mode==HVACMode.OFF and a.target_temperature is None
    await command(n,a.async_turn_on())
    assert a.hvac_mode==HVACMode.HEAT and a.target_temperature==21
    assert n.entities[n.floor.room_id].target_temperature==19


@pytest.mark.asyncio
@pytest.mark.parametrize("two_controller", [("runtime_clock_origin", origin) for origin in (50.0, 100.0, 150.0, 500.0)],
    indirect=True, ids=["epoch50", "epoch100", "epoch150", "epoch500"])
async def test_native_room_stop_is_independent_of_host_monotonic_epoch(native_climates, hass, request):
    # Exercise the entire unchanged service/ACK path and its original demand
    # assertions, not an alternate controller or a relaxed warmup deadline.
    await test_real_native_climate_services_stop_A_then_B_and_resume_only_A(
        native_climates, hass, "epoch-" + str(request.node.callspec.params["two_controller"][1]))

@pytest.mark.asyncio
@pytest.mark.parametrize("mode",["cool","heat_cool","auto","",None])
async def test_invalid_hvac_mode_is_rejected_without_wire_or_changed_confirmed_state(native_climates,mode):
    n=native_climates
    before=len(n.peer.trace);states=dict(n.runtime.decisions)
    with pytest.raises(HomeAssistantError):
        await n.entities[n.rad.room_id].async_set_hvac_mode(mode)
    assert len(n.peer.trace)==before and n.runtime.decisions==states and not n.pending

@pytest.mark.asyncio
async def test_offline_rejects_stop_without_optimistic_ui_or_stored_retry(native_climates):
    n=native_climates;await n.settle(16,16)
    await n.event("disconnect");n.callbacks["status"](False)
    await n.connection.queue.join()
    e=n.entities[n.rad.room_id]
    assert not e.available
    before=len(n.peer.trace)
    with pytest.raises(HomeAssistantError):await e.async_set_hvac_mode(HVACMode.OFF)
    assert len(n.peer.trace)==before and not n.pending
    assert not n.client.pending

@pytest.mark.asyncio
async def test_ack_alone_does_not_optimistically_confirm_a_new_hvac_mode(native_climates):
    n=native_climates;await n.settle(16,16)
    e=n.entities[n.rad.room_id];confirmed=n.runtime.decisions.copy()
    task=asyncio.create_task(e.async_set_hvac_mode(HVACMode.OFF))
    try:
        # Let the actual native worker publish, but do not deliver to firmware.
        for _ in range(30):
            await asyncio.sleep(.001)
            if n.pending:break
        assert n.pending and not task.done()
        assert n.runtime.decisions==confirmed and e.hvac_mode==HVACMode.HEAT
        topic,raw=n.pending.popleft()
        assert topic=="ha/user_command"
        reply=await n.peer.request("receive",topic=topic,raw=raw)
        states=[f for f in reply["frames"] if f["topic"]=="fw/state/zones"]
        assert states
        async def deliver(frames):
            for frame in frames:
                n.callbacks["message"](SimpleNamespace(topic="fixture/v1/"+frame["topic"],
                    payload=frame["raw"],retain=False))
                await n.connection.queue.join()
        await deliver([f for f in reply["frames"] if f["topic"]!="fw/state/zones"])
        await task # Real ACK accepted, but no admitted state delivered yet.
        assert n.runtime.decisions==confirmed and e.hvac_mode==HVACMode.HEAT
        await deliver(states)
        assert e.hvac_mode==HVACMode.OFF
    finally:
        if not task.done():task.cancel()
        await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_native_off_is_not_stored_or_replayed_into_a_new_owner_boot(native_climates):
    n=native_climates;await n.settle(16,16)
    e=n.entities[n.rad.room_id]
    await command(n,e.async_set_hvac_mode(HVACMode.OFF))
    assert e.hvac_mode==HVACMode.OFF
    commands=lambda:sum(op=="receive" and k.get("topic")=="ha/user_command" for op,k,_ in n.peer.trace)
    sent=commands()
    await n.event("disconnect");n.callbacks["status"](False);await n.connection.queue.join()
    assert not e.available and e.hvac_mode is None
    await n.event("reboot",boot="native_climate_new_boot")
    await n.event("connect");await n.event("tick");await n.drain()
    assert n.client.ready and commands()==sent
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
    await n.samples(16,16)
    assert e.hvac_mode==HVACMode.HEAT and e.target_temperature==21
    assert commands()==sent
    record(n,"new_owner_no_off_or_override_replay")


@pytest.mark.asyncio
@pytest.mark.parametrize("inhibit",["all_off","summer","dhw_active"])
async def test_native_heat_selection_cannot_clear_existing_source_inhibition(native_climates,hass,inhibit):
    n=native_climates;await n.settle(16,16)
    e=n.entities[n.rad.room_id]
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,**{inhibit:True})
    await n.samples(16,16)
    await command(n,hass.services.async_call("climate","set_hvac_mode",
        {"entity_id":e.entity_id,"hvac_mode":"heat"},blocking=True))
    assert e.hvac_mode==HVACMode.HEAT and e.hvac_action==HVACAction.IDLE
    assert all(not s.demand for s in n.runtime.decisions.values())
    assert all(not x.extra_state_attributes["actuator_output_enabled"] for x in n.entities.values())
