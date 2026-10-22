"""NativeHA+actualCpppeer; declared synthetic clock/typed fixture producer, not hardware."""
from datetime import timedelta
import pytest
from homeassistant.util import dt as dt_util
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_wire import ShadowClient
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from test_context_source_binding import context,publish,both,emit
from test_comfort_interop import observe,command

class NativeClock:
    """Coherent finite fixture time, no product clock adapter/service."""
    def __init__(self,hass,bus,monkeypatch):
        self.hass,self.bus=hass,bus;self.offset=0;self.ms=0
        self.real=hass.loop.time;self.utc=dt_util.utcnow()
        monkeypatch.setattr(hass.loop,"time",lambda:self.real()+self.offset)
        monkeypatch.setattr(dt_util,"utcnow",lambda:self.utc+timedelta(milliseconds=self.ms))
    async def step(self,ms=2000):
        self.ms+=ms;self.offset+=ms/1000
        await self.bus.advance(ms)

@pytest.mark.asyncio
@pytest.mark.parametrize("missing",["window","presence"])
async def test_stable_closed_home_for_eight_minutes_then_report_gap_never_keeps_demand(context,hass,monkeypatch,missing):
    r,c,b,room,other,_=context
    with monkeypatch.context() as patch:
        clock=NativeClock(hass,b,patch)
        original=clock.utc-timedelta(days=1)
        for ref in (room.window,room.presence):hass.states.get(ref.entity_id).last_changed=original
        await both(context)
        frames=0
        for t in range(2000,480001,2000):
            await clock.step()
            if t%60000==0:
                for kind in ("window","presence"):await publish(context,kind=kind,key="periodic-"+str(t))
            d=await observe(r,c,b,room);frames+=1
            assert c.ready and d.target_centi_c==2100 and d.demand
            assert r.comfort_context(room)["window_open"] is False
            assert r.comfort_context(room)["presence_away"] is False
            assert all(hass.states.get(ref.entity_id).last_changed==original for ref in (room.window,room.presence))
        assert clock.ms==480000 and frames==240
        # Stop ONLY one logical producer, keep temperature/owner/other source fresh.
        for elapsed in range(2000,126001,2000):
            await clock.step()
            if elapsed%60000==0:
                other_kind="presence" if missing=="window" else "window"
                await publish(context,kind=other_kind,key="remaining-"+str(clock.ms))
            d=await observe(r,c,b,room)
            if elapsed>=120000:
                assert c.ready and d.current_centi_c==1900
                assert not d.demand and d.target_centi_c is None
                assert d.reason==missing+"_state_unknown"
        assert c.ready and d.current_centi_c==1900 and not d.demand
        assert d.target_centi_c is None and d.reason==missing+"_state_unknown"
        emit(dict(scenario="stable_480s_then_"+missing+"_gap",synthetic_stable_ms=480000,frames=frames,
                  missing_gap_ms=126000,temperature_fresh=True,unknown_not_away=True,physical_outputs_enabled=False))
        await r.async_stop() # Clear all native pending lifecycle before restoring fixture time.

@pytest.mark.asyncio
async def test_typed_source_availability_and_unknown_contact_win_over_boost(context):
    r,c,b,room,_,_=context
    await both(context)
    await command(b,r.async_comfort(room.room_id,"boost",temperature=23,duration_ms=60000))
    assert r.decisions[room.room_id].target_centi_c==2300
    for i,value in enumerate(("unavailable","unknown","on")):
        await publish(context,value=value,key="contact-loss-"+str(i))
        d=r.decisions[room.room_id]
        assert d.target_centi_c is None and not d.demand
        assert d.comfort_mode=="boost"
    await publish(context,value="off",key="new-qualified-close")
    assert r.decisions[room.room_id].target_centi_c==2300
    emit(dict(scenario="typed_contact_availability_unknown_open_vs_boost",override_retained_but_inhibited=True,
              unknown_not_closed=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_heartbeat_gap_reconnect_and_new_runtime_fw_boot_cannot_restore_cached_context(context,hass,monkeypatch):
    r,c,b,room,other,pins=context
    with monkeypatch.context() as patch:
        clock=NativeClock(hass,b,patch);await both(context)
        await command(b,r.async_comfort(room.room_id,"boost",temperature=23,duration_ms=60000))
        # No native packet/heartbeat during interval; actual firmware lease expires.
        clock.ms+=16000;clock.offset+=16;b.now+=16000;b.utc+=16
        await b.event("tick");await c.poll();await b.pump()
        assert r.comfort_context(room)["window_open"] is None
        assert r.comfort_context(room)["presence_away"] is None
        await clock.step(3000)
        if not c.ready:await b.start()
        assert c.ready
        await observe(r,c,b,room)
        assert not r.decisions[room.room_id].demand
        assert r.decisions[room.room_id].target_centi_c is None
        await publish(context,key="post-gap")
        await publish(context,kind="presence",key="post-gap")
        await observe(r,c,b,room)
        assert r.decisions[room.room_id].target_centi_c==2100
        assert r.decisions[room.room_id].comfort_mode=="auto"
        await r.async_stop()
        # Native Store/config survive; source proofs/override/sample do NOT.
        new=ShadowRuntime(hass,r.entry,[room,other],context_source_profiles=pins)
        zones,mapping=await async_build_configuration(new)
        client=ShadowClient(new,"ha1",b.send,c.store,zones,mapping,b.clock)
        b.client=client;new.attach_transport(client)
        await client.async_start();await new.async_start()
        try:
            assert new.comfort_context(room)["window_open"] is None
            assert new.comfort_context(room)["presence_away"] is None
            await b.event("boot",boot_id="context-new-boot");await b.start()
            assert client.ready and client.journal["accepted"]["config"]["revision"]==1
            assert not new.decisions[room.room_id].demand
            renewed=(new,client,b,room,other,pins)
            await publish(renewed,key="post-HA-and-FW-boot")
            await publish(renewed,kind="presence",key="post-HA-and-FW-boot")
            d=await observe(new,client,b,room)
            assert d.target_centi_c==2100 and d.comfort_mode=="auto" and d.override_remaining_ms==0
            emit(dict(scenario="heartbeat_gap_reconnect_runtime_fw_restart",original_config_preserved=True,
                      cache_never_qualified=True,new_report_required=True,old_override_restored=False,
                      physical_outputs_enabled=False))
        finally:await new.async_stop()

@pytest.mark.asyncio
async def test_original_monotonic_context_deadline_survives_wall_clock_backstep(context,hass,monkeypatch):
    r,c,b,room,*_=context
    with monkeypatch.context() as patch:
        clock=NativeClock(hass,b,patch);await both(context)
        # A backward wall jump cannot turn the original proof into a new report.
        clock.utc-=timedelta(hours=1)
        for _ in range(63):
            await clock.step();d=await observe(r,c,b,room)
        assert clock.ms==126000 and c.ready and d.current_centi_c==1900
        assert d.target_centi_c is None and not d.demand
        assert r.comfort_context(room)["window_open"] is None
        assert r.comfort_context(room)["presence_away"] is None
        emit(dict(scenario="utc_backstep_does_not_renew_logical_proof",synthetic_monotonic_ms=126000,
                  temperature_fresh=True,original_deadline_preserved=True,physical_outputs_enabled=False))
        await r.async_stop()
