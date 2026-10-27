"""Real HA events/registry and owned manual queue; no device or broker IO."""
import asyncio
from dataclasses import replace
from datetime import timedelta
import pytest
import pytest_asyncio
from homeassistant.core import Context,Event
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_config_flow import reference
from test_v1_native import room,entry


class Transport:
    ready=True
    def __init__(self):self.calls=[];self.hold=None;self.failure=False
    async def async_observation(self,*args):pass
    async def async_setpoint(self,room_id,target,*,duration_ms=None):
        self.calls.append((room_id,target,duration_ms))
        if self.failure:raise RuntimeError('unconfirmed fixture response')
        if self.hold is not None:await self.hold
    async def async_close(self):self.ready=False


@pytest_asyncio.fixture
async def manual(hass):
    helper=er.async_get(hass).async_get_or_create('input_number','input_number','room_manual_target')
    hass.states.async_set(helper.entity_id,'21',{'unit_of_measurement':'°C'})
    binding=replace(room(hass),setpoint=reference(hass,helper.entity_id),setpoint_duration_ms=120000)
    parent=entry(hass,enabled=True,room=binding);clock=[1000.0]
    runtime=ShadowRuntime(hass,parent,[binding],clock=lambda:clock[0]);transport=Transport()
    runtime.attach_transport(transport);await runtime.async_start();await hass.async_block_till_done()
    try:yield runtime,transport,binding,helper,clock
    finally:await runtime.async_stop()


async def change(fixture,value,*,context=None,unit='°C',extra=None,wait=True):
    runtime,_,_,helper,_=fixture
    runtime.hass.states.async_set(helper.entity_id,value,{'unit_of_measurement':unit,**(extra or {})},
                                  context=context or Context(user_id='fixture_user'))
    if wait:await runtime.hass.async_block_till_done()
    else:
        for _ in range(5):await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_startup_and_reread_do_not_apply_a_cached_helper_but_one_manual_change_does(manual):
    runtime,transport,binding,helper,_=manual;before=runtime.observations[binding.room_id]
    assert transport.calls==[]
    for _ in range(5):assert runtime.manual_target_status(binding.room_id)['status']=='awaiting_manual_change'
    await change(manual,'22')
    assert transport.calls==[(binding.room_id,2200,120000)]
    assert runtime.observations[binding.room_id] is before
    assert runtime.manual_target_status(binding.room_id)['status']=='request_accepted'
    await change(manual,'22.0')
    assert len(transport.calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['automation','parent_context','restored','nan','unit','outside_room'])
async def test_nonmanual_echo_and_invalid_values_cannot_request_a_target(manual,fault):
    _,transport,_,_,_=manual;args={};value='22'
    if fault=='automation':args['context']=Context()
    if fault=='parent_context':args['context']=Context(user_id='fixture_user',parent_id='automation_parent')
    if fault=='restored':args['extra']={'restored':True}
    if fault=='nan':value='NaN'
    if fault=='unit':args['unit']='%'
    if fault=='outside_room':value='40'
    await change(manual,value,**args)
    assert transport.calls==[]


@pytest.mark.asyncio
async def test_replaying_a_consumed_native_event_never_renews_the_override(manual):
    runtime,transport,_,helper,_=manual;events=[]
    stop=runtime.hass.bus.async_listen('state_changed',lambda event:events.append(event))
    await change(manual,'22');event=next(e for e in events if e.data['entity_id']==helper.entity_id)
    runtime._source_event(helper.entity_id,'changed',event)
    await runtime.hass.async_block_till_done();stop()
    assert len(transport.calls)==1


@pytest.mark.asyncio
async def test_fahrenheit_manual_value_uses_explicit_unit_and_does_not_clip_to_bounds(manual):
    _,transport,binding,_,_=manual
    await change(manual,'73.4',unit='°F')
    assert transport.calls==[(binding.room_id,2300,120000)]


@pytest.mark.asyncio
async def test_only_latest_unsent_human_change_survives_a_busy_command(manual):
    runtime,transport,binding,_,_=manual
    hold=transport.hold=runtime.hass.loop.create_future()
    await change(manual,'22',wait=False)
    assert len(transport.calls)==1
    await change(manual,'23',wait=False);await change(manual,'24',wait=False)
    assert len(runtime.manual_target_owner.pending)==1 and len(transport.calls)==1
    transport.hold=None;hold.set_result(None)
    await runtime.hass.async_block_till_done()
    assert transport.calls==[(binding.room_id,2200,120000),(binding.room_id,2400,120000)]


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['expired','removed','disabled','stopped'])
async def test_final_dispatch_rechecks_age_registry_and_owner(manual,monkeypatch,fault):
    runtime,transport,binding,helper,clock=manual;gate=asyncio.Event()
    original=runtime.manual_target_owner._flush
    async def deferred(room_id):
        await gate.wait();await original(room_id)
    monkeypatch.setattr(runtime.manual_target_owner,'_flush',deferred)
    await change(manual,'22',wait=False)
    assert runtime.manual_target_owner.pending
    if fault=='expired':clock[0]+=6
    if fault=='removed':er.async_get(runtime.hass).async_remove(helper.entity_id)
    if fault=='disabled':er.async_get(runtime.hass).async_update_entity(helper.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    if fault=='stopped':await runtime.async_stop()
    gate.set();await runtime.hass.async_block_till_done()
    assert transport.calls==[]


@pytest.mark.asyncio
async def test_offline_or_uncertain_action_is_never_replayed_by_reconnection_or_status_reads(manual):
    runtime,transport,binding,_,_=manual
    transport.ready=False;await change(manual,'22');transport.ready=True
    runtime.manual_target_status(binding.room_id)
    await runtime.hass.async_block_till_done();assert transport.calls==[]
    transport.failure=True;await change(manual,'23')
    assert len(transport.calls)==1 and runtime.manual_target_status(binding.room_id)['status']=='request_unconfirmed'
    transport.failure=False
    for _ in range(10):runtime.manual_target_status(binding.room_id)
    await runtime.hass.async_block_till_done();assert len(transport.calls)==1


@pytest.mark.asyncio
async def test_deleted_helper_does_not_withdraw_room_temperature_or_adopt_reused_entity_id(manual):
    runtime,transport,binding,helper,_=manual;before=runtime.observations[binding.room_id]
    registry=er.async_get(runtime.hass);registry.async_remove(helper.entity_id)
    registry.async_get_or_create('input_number','input_number','unrelated_helper',suggested_object_id=helper.entity_id.split('.')[1])
    await change(manual,'22')
    assert runtime.observations[binding.room_id] is before and transport.calls==[]
    assert runtime.manual_target_status(binding.room_id)['status']=='binding_unavailable'


@pytest.mark.asyncio
async def test_repeated_helper_renames_follow_identity_and_later_deletion_keeps_temperature(manual):
    runtime,transport,binding,helper,_=manual;before=runtime.observations[binding.room_id]
    registry=er.async_get(runtime.hass);old=helper.entity_id
    for new in ('input_number.renamed_once','input_number.renamed_twice'):
        registry.async_update_entity(old,new_entity_id=new)
        runtime.hass.states.async_set(new,'21',{'unit_of_measurement':'°C'})
        await runtime.hass.async_block_till_done()
        assert runtime.resolved(binding.setpoint)==new
        assert runtime.observations[binding.room_id] is before
        old=new
    registry.async_remove(old);await runtime.hass.async_block_till_done()
    assert runtime.observations[binding.room_id] is before and not transport.calls
    assert runtime.manual_target_status(binding.room_id)['status']=='binding_unavailable'


@pytest.mark.asyncio
async def test_actual_builtin_helper_service_preserves_authenticated_native_user_context(hass):
    from homeassistant import loader
    from homeassistant.setup import async_setup_component
    from homeassistant.helpers.storage import Store
    from homeassistant.auth.const import GROUP_ID_ADMIN
    from homeassistant.auth import auth_manager_from_config
    loader.async_setup(hass)
    hass.auth=await auth_manager_from_config(hass,[],[])
    await Store(hass,1,'input_number').async_save({'items':[{
        'id':'manual_target_fixture','name':'Manual target fixture','min':5,'max':35,'step':0.1,
        'mode':'box','initial':21,'unit_of_measurement':'°C'}]})
    assert await async_setup_component(hass,'input_number',{})
    await hass.async_block_till_done()
    helper=er.async_get(hass).async_get_entity_id('input_number','input_number','manual_target_fixture')
    assert helper is not None
    binding=replace(room(hass),setpoint=reference(hass,helper),setpoint_duration_ms=600000)
    runtime=ShadowRuntime(hass,entry(hass,enabled=True,room=binding),[binding]);transport=Transport()
    runtime.attach_transport(transport);await runtime.async_start()
    user=await hass.auth.async_create_user('Manual target fixture',group_ids=[GROUP_ID_ADMIN])
    try:
        await hass.services.async_call('input_number','set_value',{'entity_id':helper,'value':22},
                                      blocking=True,context=Context(user_id=user.id))
        await hass.async_block_till_done()
        assert transport.calls==[(binding.room_id,2200,600000)]
        # A normal automated service call is not a second human action.
        await hass.services.async_call('input_number','set_value',{'entity_id':helper,'value':23},blocking=True)
        await hass.async_block_till_done()
        assert len(transport.calls)==1
    finally:await runtime.async_stop()
