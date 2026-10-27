"""Native manual intent against real C++ expiry/admission, no hardware IO."""
import asyncio
import json
import pytest
from homeassistant.core import Context
from custom_components.open_thermostat.v1_wire import canonical
from custom_components.open_thermostat.v1_climate import ShadowRoom
from test_comfort_interop import comfort
from test_room_contact_interop import temperature, contact


async def change(fixture,value):
    runtime,_,bus,room,_=fixture
    runtime.hass.states.async_set(runtime.resolved(room.setpoint),value,
        {'unit_of_measurement':'°C'},context=Context(user_id='manual_fixture'))
    for _ in range(8):await asyncio.sleep(0)
    await bus.pump();await runtime.hass.async_block_till_done()


def commands(bus):
    return [raw for who,topic,raw in bus.transcript if who=='ha' and topic=='ha/user_command']


@pytest.mark.asyncio
@pytest.mark.parametrize('comfort',[{'contacts':True,'contact_only':True,'manual_helper':True}],indirect=True)
async def test_original_manual_helper_expires_in_cpp_without_replay_or_bypassing_contacts(comfort):
    runtime,client,bus,room,other=comfort;await bus.start();await temperature(comfort,room);await temperature(comfort,other)
    assert client.ready and client.manual_target_supported and not commands(bus)
    original=runtime.observations[room.room_id]
    await change(comfort,'23')
    assert runtime.observations[room.room_id] is original
    decision=runtime.decisions[room.room_id]
    assert (decision.target_centi_c,decision.override_remaining_ms)==(2300,60000)
    assert runtime.decisions[other.room_id].target_centi_c==2100
    assert ShadowRoom('fixture',room,runtime).extra_state_attributes['override_remaining_minutes']==1
    assert len(commands(bus))==1 and json.loads(commands(bus)[0])['duration_ms']==60000
    await bus.advance(5000);await bus.event('receive',topic='ha/user_command',raw=commands(bus)[0]);await bus.pump()
    assert runtime.decisions[room.room_id].override_remaining_ms==55000
    await contact(comfort,0,'on')
    assert not runtime.decisions[room.room_id].demand and runtime.decisions[room.room_id].reason=='window_open'
    await contact(comfort,0,'off');assert runtime.decisions[room.room_id].target_centi_c==2300
    for _ in range(11):await bus.advance(5000)
    assert runtime.decisions[room.room_id].override_remaining_ms==0
    assert runtime.decisions[room.room_id].target_centi_c==2100 and len(commands(bus))==1
    # Status reads and the still-visible helper never renew an expired override.
    for _ in range(5):runtime.manual_target_status(room.room_id)
    await bus.advance(2000);assert len(commands(bus))==1
    states=[json.loads(raw) for who,topic,raw in bus.transcript if topic=='fw/state/zones']
    assert all(not s['boiler_output_enabled'] and not s['actuator_output_enabled'] for s in states)


@pytest.mark.asyncio
@pytest.mark.parametrize('comfort',[{'contacts':True,'contact_only':True,'manual_helper':True}],indirect=True)
async def test_old_peer_cannot_admit_manual_helper_before_configuration(comfort):
    _,client,bus,*_=comfort
    await bus.event('connect');bus.drop=lambda item:item['topic']=='fw/hello'
    frames=await bus.event('tick');hello=next(i['payload'] for i in frames if i['topic']=='fw/hello')
    hello['control_capabilities'].remove('control.manual_target.v1')
    await client.receive('fw/hello',canonical(hello))
    assert not client.ready and client.error=='manual_target_capability_unavailable'
    assert not any(who=='ha' and topic=='ha/config' for who,topic,_ in bus.transcript)
