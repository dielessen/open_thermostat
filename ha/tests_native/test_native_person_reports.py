"""Original HA person events, immutable timestamps and bounded logical proof."""
from dataclasses import replace
from datetime import timedelta
import pytest
import pytest_asyncio
from homeassistant.core import Event
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from custom_components.open_thermostat.v1_config_flow import reference
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from test_v1_native import room, entry
from test_manual_target_runtime import Transport
from test_room_comfort_setup import person, PROFILE


@pytest_asyncio.fixture
async def presence(hass):
    selected=person(hass)
    binding=replace(room(hass),comfort=dict(PROFILE),presence=reference(hass,selected.entity_id))
    clock=[1000.0];runtime=ShadowRuntime(hass,entry(hass,enabled=True,room=binding),[binding],clock=lambda:clock[0])
    runtime.attach_transport(Transport());await runtime.async_start();await hass.async_block_till_done()
    try:yield runtime,binding,selected,clock
    finally:await runtime.async_stop()


async def report(fixture,value='home',attrs=None,*,source_report=True):
    runtime,_,selected,_=fixture
    old=runtime.hass.states.get(selected.entity_id)
    attributes={**(dict(old.attributes) if old else {}),**(attrs or {})}
    if source_report and attributes.get('source'):
        runtime.hass.states.async_set(attributes['source'],value,{'source_type':'router'})
    runtime.hass.states.async_set(selected.entity_id,value,attributes)
    await runtime.hass.async_block_till_done()


@pytest.mark.asyncio
async def test_only_new_native_reports_renew_presence_not_cache_reads_or_temperature(presence):
    runtime,binding,selected,clock=presence;original=runtime.observations[binding.room_id]
    assert runtime.comfort_context(binding)['presence_away'] is None
    await report(presence) # Unchanged State: original state_reported event.
    assert runtime.comfort_context(binding)['presence_away'] is False
    assert runtime.context_source_status(binding.room_id)['presence']=='native_person_report'
    clock[0]+=60;before=runtime.comfort_context(binding)['presence_age_ms']
    for _ in range(10):runtime.context_source_status(binding.room_id)
    assert runtime.comfort_context(binding)['presence_age_ms']==before>=60000
    assert runtime.observations[binding.room_id] is original
    await report(presence);assert runtime.comfort_context(binding)['presence_age_ms']<100
    clock[0]+=120
    assert runtime.comfort_context(binding)['presence_away'] is None
    assert runtime.context_source_status(binding.room_id)['presence']=='native_person_report_unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize('state',['unknown','unavailable','Work','School'])
async def test_unknown_named_and_restored_states_cannot_become_away(presence,state):
    runtime,binding,*_=presence;await report(presence,'not_home')
    assert runtime.comfort_context(binding)['presence_away'] is True
    await report(presence,state);assert runtime.comfort_context(binding)['presence_away'] is None
    await report(presence,'home',{'restored':True})
    assert runtime.comfort_context(binding)['presence_away'] is None


@pytest.mark.asyncio
async def test_retirement_preserves_replay_watermark_and_requires_a_new_report(presence):
    runtime,binding,selected,clock=presence;events=[]
    stop=runtime.hass.bus.async_listen('state_changed',lambda event:events.append(event))
    await report(presence,'not_home');stop()
    event=next(e for e in events if e.data['entity_id']==selected.entity_id)
    clock[0]+=5;age=runtime.comfort_context(binding)['presence_age_ms']
    runtime._source_event(selected.entity_id,'changed',event)
    assert runtime.comfort_context(binding)['presence_age_ms']==age
    runtime.invalidate_context_sources()
    runtime._source_event(selected.entity_id,'changed',event)
    assert runtime.comfort_context(binding)['presence_away'] is None
    await report(presence,'not_home',source_report=False)
    assert runtime.comfort_context(binding)['presence_away'] is None
    await report(presence,'not_home')
    assert runtime.comfort_context(binding)['presence_away'] is True


@pytest.mark.asyncio
async def test_person_reemission_cannot_refresh_same_cached_tracker_or_a_retired_origin(presence):
    runtime,binding,_,clock=presence;await report(presence)
    clock[0]+=90;await report(presence,source_report=False)
    assert runtime.comfort_context(binding)['presence_age_ms']>=90000
    clock[0]+=30;await report(presence,source_report=False)
    assert runtime.comfort_context(binding)['presence_away'] is None
    await report(presence);assert runtime.comfort_context(binding)['presence_away'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['source_unavailable','source_restored','source_removed','source_replaced'])
async def test_source_tracker_must_still_match_original_identity_and_be_available(presence,fault):
    runtime,binding,selected,_=presence;await report(presence)
    source_id=runtime.hass.states.get(selected.entity_id).attributes['source'];registry=er.async_get(runtime.hass)
    if fault=='source_unavailable':runtime.hass.states.async_set(source_id,'unavailable')
    if fault=='source_restored':runtime.hass.states.async_set(source_id,'home',{'restored':True})
    if fault in ('source_removed','source_replaced'):
        registry.async_remove(source_id)
        if fault=='source_replaced':registry.async_get_or_create('device_tracker','other','reused_source',suggested_object_id=source_id.split('.')[1])
    await runtime.hass.async_block_till_done()
    assert runtime.comfort_context(binding)['presence_away'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['future','old','naive','wrong_entity','wrong_state'])
async def test_invalid_original_event_cannot_create_presence_proof(presence,fault):
    runtime,binding,selected,_=presence;state=runtime.hass.states.get(selected.entity_id)
    stamp=dt_util.utcnow()
    if fault=='future':stamp+=timedelta(seconds=1)
    if fault=='old':stamp-=timedelta(seconds=121)
    if fault=='naive':stamp=stamp.replace(tzinfo=None)
    event=Event('state_reported',{'entity_id':'person.other' if fault=='wrong_entity' else selected.entity_id,
        'new_state':None if fault=='wrong_state' else state,'last_reported':stamp})
    runtime._source_event(selected.entity_id,'reported',event)
    assert runtime.comfort_context(binding)['presence_away'] is None


@pytest.mark.asyncio
async def test_removed_disabled_or_reused_presence_identity_cannot_supply_cached_proof(presence):
    runtime,binding,selected,_=presence;await report(presence)
    registry=er.async_get(runtime.hass)
    registry.async_update_entity(selected.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    await runtime.hass.async_block_till_done()
    assert runtime.comfort_context(binding)['presence_away'] is None
    registry.async_remove(selected.entity_id)
    registry.async_get_or_create('person','person','new_identity',suggested_object_id=selected.entity_id.split('.')[1])
    await report(presence)
    assert runtime.comfort_context(binding)['presence_away'] is None


@pytest.mark.asyncio
async def test_actual_person_integration_emits_new_report_for_unchanged_home_on_tracker_update(hass):
    from homeassistant import loader
    from homeassistant.auth import auth_manager_from_config
    from homeassistant.setup import async_setup_component
    loader.async_setup(hass);hass.auth=await auth_manager_from_config(hass,[],[])
    tracker=er.async_get(hass).async_get_or_create('device_tracker','router','presence_tracker')
    hass.states.async_set(tracker.entity_id,'home',{'source_type':'router','fixture_report':0})
    assert await async_setup_component(hass,'person',{'person':[{
        'id':'native_person_fixture','name':'Native presence fixture','device_trackers':[tracker.entity_id]}]})
    # Exercise native startup listeners on this isolated fixture. No tracker
    # integration or external network source is installed or contacted.
    from homeassistant.const import EVENT_HOMEASSISTANT_START
    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()
    eid=er.async_get(hass).async_get_entity_id('person','person','native_person_fixture')
    assert eid and hass.states.get(eid).state=='home'
    binding=replace(room(hass),comfort=dict(PROFILE),presence=reference(hass,eid))
    clock=[1000.0];runtime=ShadowRuntime(hass,entry(hass,enabled=True,room=binding),[binding],clock=lambda:clock[0])
    runtime.attach_transport(Transport());await runtime.async_start();await hass.async_block_till_done()
    try:
        assert runtime.comfort_context(binding)['presence_away'] is None
        original_state=hass.states.get(eid)
        hass.states.async_set(tracker.entity_id,'home',{'source_type':'router','fixture_report':1})
        await hass.async_block_till_done()
        assert hass.states.get(eid) is original_state # Person value/attributes unchanged.
        assert runtime.comfort_context(binding)['presence_away'] is False
        clock[0]+=60
        assert runtime.comfort_context(binding)['presence_age_ms']>=60000
        hass.states.async_set(tracker.entity_id,'home',{'source_type':'router','fixture_report':2})
        await hass.async_block_till_done()
        assert runtime.comfort_context(binding)['presence_age_ms']<100
        assert runtime.context_source_status(binding.room_id)['presence']=='native_person_report'
    finally:await runtime.async_stop()
