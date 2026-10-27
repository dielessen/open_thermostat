"""Multiple native HA contacts through the actual C++ policy, no hardware IO."""
import json
import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat.v1_model import Observation
from custom_components.open_thermostat.v1_wire import canonical
from test_comfort_interop import comfort
from test_v1_native import source_profile


async def temperature(fixture, room, value=19):
    runtime, client, bus, *_ = fixture
    if room.room_id not in runtime._profiles:
        runtime.set_report_profile(room.room_id, source_profile)
    observation = Observation(value, 'qualified', 0, 'temperature-proof', bus.clock())
    runtime.observations[room.room_id] = observation
    await client.async_observation(room.room_id, observation)
    await bus.pump()
    return runtime.decisions[room.room_id]


async def contact(fixture, index, value):
    runtime, _, bus, room, _ = fixture
    binding = room.contacts[index]
    runtime.hass.states.async_set(runtime.resolved(binding.entity), value, {'device_class': binding.kind})
    await runtime.hass.async_block_till_done()
    await bus.pump()


@pytest.mark.asyncio
@pytest.mark.parametrize('comfort', [{'contacts': True, 'close_delay_ms': 1000, 'contact_only':only} for only in (False,True)], indirect=True)
async def test_two_contacts_pause_only_their_room_and_wait_for_all_closed(comfort):
    runtime, client, bus, room, other = comfort
    await bus.start()
    config = client.journal['accepted']['config']
    zone = next(z for z in config['zones'] if z['zone_id'] == room.room_id)
    if room.comfort:
        assert zone['comfort']['window_max_age_ms'] == 3600000 and zone['comfort']['window'] is True
    else:
        assert zone['contacts']=={'maximum_age_ms':3600000} and 'comfort' not in zone
    for binding in room.contacts:
        assert binding.entity.entity_id not in canonical(config)
    def string_values(value):
        if isinstance(value, dict): return [s for v in value.values() for s in string_values(v)]
        if isinstance(value, list): return [s for v in value for s in string_values(v)]
        return [value] if isinstance(value, str) else []
    assert all(c.entity.unique_id not in string_values(config) for c in room.contacts)
    assert (await temperature(comfort, room)).target_centi_c is None
    await bus.advance(1000)
    assert (await temperature(comfort, room)).demand
    assert (await temperature(comfort, other)).demand
    original = runtime.observations[room.room_id]
    await contact(comfort, 0, 'on')
    assert runtime.observations[room.room_id] is original
    assert not runtime.decisions[room.room_id].demand
    assert runtime.decisions[room.room_id].reason == 'window_open'
    assert runtime.decisions[other.room_id].demand
    await contact(comfort, 1, 'on')
    await contact(comfort, 0, 'off')
    assert not runtime.decisions[room.room_id].demand
    await contact(comfort, 1, 'off')
    assert not runtime.decisions[room.room_id].demand
    assert runtime.context_source_status(room.room_id)['contacts']['reason'] == 'contact_close_delay'
    await bus.advance(999)
    assert not (await temperature(comfort, room)).demand
    await bus.advance(1)
    assert (await temperature(comfort, room)).demand
    states = [json.loads(raw) for who, topic, raw in bus.transcript if topic == 'fw/state/zones']
    assert states and all(s['boiler_output_enabled'] is False and s['actuator_output_enabled'] is False for s in states)


@pytest.mark.asyncio
@pytest.mark.parametrize('comfort', [{'contacts': True, 'maximum_age_ms': 6000, 'contact_only':only} for only in (False,True)], indirect=True)
async def test_expired_or_lost_contact_cannot_be_renewed_by_temperature_or_status_reads(comfort):
    runtime, _, bus, room, _ = comfort
    await bus.start()
    assert (await temperature(comfort, room)).demand
    await bus.advance(2000)
    decision = await temperature(comfort, room)
    assert decision.demand, {'context': runtime.comfort_context(room), 'now': bus.now,
        'packets': [json.loads(raw) for who, topic, raw in bus.transcript if topic == 'ha/observations'][-2:]}
    before = runtime.comfort_context(room)['window_age_ms']
    for _ in range(10):
        runtime.context_source_status(room.room_id)
    assert runtime.comfort_context(room)['window_age_ms'] == before
    # The receiver also adds the existing grant-age delivery envelope. Keep
    # that conservative contract; do not relax it to match a tiny test TTL.
    await bus.advance(4001)
    decision = await temperature(comfort, room)
    assert decision.target_centi_c is None and decision.reason == 'window_state_unknown'
    await contact(comfort, 0, 'on')
    assert runtime.decisions[room.room_id].reason == 'window_open'
    await contact(comfort, 0, 'off')
    assert runtime.decisions[room.room_id].reason == 'window_state_unknown'
    await contact(comfort, 1, 'on')
    await contact(comfort, 1, 'off')
    assert (await temperature(comfort, room)).demand
    er.async_get(runtime.hass).async_remove(room.contacts[0].entity.entity_id)
    await runtime.hass.async_block_till_done()
    assert not (await temperature(comfort, room)).demand


@pytest.mark.asyncio
@pytest.mark.parametrize('comfort', [{'contacts': True, 'contact_only':only} for only in (False,True)], indirect=True)
async def test_old_firmware_without_contact_contract_is_refused_before_config_write(comfort):
    _, client, bus, *_ = comfort
    await bus.event('connect')
    bus.drop = lambda item: item['topic'] == 'fw/hello'
    frames = await bus.event('tick')
    hello = next(item['payload'] for item in frames if item['topic'] == 'fw/hello')
    hello['control_capabilities'].remove('comfort.contacts.v1')
    await client.receive('fw/hello', canonical(hello))
    assert not client.ready and client.error == 'contact_capability_unavailable'
    assert not any(who == 'ha' and topic == 'ha/config' for who, topic, _ in bus.transcript)


@pytest.mark.asyncio
@pytest.mark.parametrize('comfort', [{'contacts': True, 'contact_only': True}], indirect=True)
async def test_contact_only_contract_does_not_require_or_enable_full_comfort_modes(comfort):
    runtime, client, bus, room, _ = comfort
    def remove_comfort_advertisement(item):
        if item['topic']=='fw/hello':
            item['payload']['control_capabilities'].remove('comfort.target.v1')
        return False
    bus.drop=remove_comfort_advertisement
    await bus.start()
    assert client.ready and client.contacts_supported and not client.comfort_supported
    assert room.comfort is None and (await temperature(comfort,room)).demand
    await contact(comfort,0,'on')
    assert runtime.decisions[room.room_id].reason=='window_open'
    assert not runtime.decisions[room.room_id].demand


async def fire_contact_timers(fixture):
    runtime,_,bus,*_=fixture
    for action,deadline in tuple(bus.contact_timers.items()):
        if deadline<=bus.clock():
            bus.contact_timers.pop(action);action(None)
    await runtime.hass.async_block_till_done();await bus.pump()


@pytest.mark.asyncio
@pytest.mark.parametrize('comfort',[{'contacts':True,'contact_only':True,'close_delay_ms':1000,'contact_timers':True}],indirect=True)
async def test_close_delay_resumes_cpp_without_a_new_temperature_and_cancelled_timers_cannot_resume(comfort):
    runtime,client,bus,room,_=comfort
    await bus.start();await temperature(comfort,room)
    original=runtime.observations[room.room_id]
    assert len(bus.contact_timers)==1 and not runtime.decisions[room.room_id].demand
    # Polling/serialization must not replace or extend the one transition timer.
    pending=dict(bus.contact_timers)
    for _ in range(5):runtime.context_source_status(room.room_id)
    assert bus.contact_timers==pending
    await bus.advance(1000);await fire_contact_timers(comfort)
    assert runtime.observations[room.room_id] is original
    assert runtime.decisions[room.room_id].demand and not bus.contact_timers
    observations=[json.loads(raw) for who,topic,raw in bus.transcript if who=='ha' and topic=='ha/observations']
    assert observations[-1]['source_sample_age_ms']>=1000
    await contact(comfort,0,'on');await contact(comfort,0,'off')
    pending=tuple(bus.contact_timers)
    await contact(comfort,0,'on')
    assert not bus.contact_timers
    await bus.advance(1000)
    for action in pending:action(None) # A late cancelled native callback.
    await runtime.hass.async_block_till_done();await bus.pump()
    assert not runtime.decisions[room.room_id].demand
    assert runtime.decisions[room.room_id].reason=='window_open'
    await contact(comfort,0,'off');pending=tuple(bus.contact_timers)
    assert pending
    await runtime.async_stop()
    assert not bus.contact_timers and not runtime._contact_timers
    before=len(bus.transcript)
    for action in pending:action(None)
    await runtime.hass.async_block_till_done()
    assert len(bus.transcript)==before
