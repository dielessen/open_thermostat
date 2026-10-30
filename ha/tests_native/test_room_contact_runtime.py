"""Actual HA registries/states plus bounded context owner; no device/broker IO."""
from dataclasses import replace
from datetime import timedelta
import pytest
from homeassistant.core import StateMachine
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from custom_components.open_thermostat.comfort_sources import ContextSourceProfile,ContextReport
from custom_components.open_thermostat.room_contacts import ContactBinding,ContactPolicy,comfort_record
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_config_flow import reference
from test_v1_native import room,entry


def setup(hass,monkeypatch,*,age=3600000,close=0,profiles=False):
    utc=dt_util.utcnow();clock=[1000.0];real=clock[0]
    monkeypatch.setattr(dt_util,'utcnow',lambda:utc+timedelta(seconds=clock[0]-real))
    # States carry the same fake time: HA stamps them with time.time(), so a busy
    # machine could otherwise make a contact's age negative and the test flaky.
    set_state=StateMachine.async_set
    monkeypatch.setattr(StateMachine,'async_set',lambda self,*a,**k:set_state(self,*a,**{'timestamp':dt_util.utcnow().timestamp(),**k}))
    registry=er.async_get(hass);refs=[]
    for name,kind in (('window','window'),('door','door')):
        row=registry.async_get_or_create('binary_sensor','context_fixture','contact_'+name)
        hass.states.async_set(row.entity_id,'off',{'device_class':kind})
        refs.append(ContactBinding(reference(hass,row.entity_id),kind))
    binding=replace(room(hass),comfort={'away_centi_c':1700,'frost_centi_c':500,'temporary_ms':60000},
                    contacts=tuple(refs),contact_policy=ContactPolicy(age,0,close))
    parent=entry(hass,enabled=True,room=binding)
    def report(state,event):return ContextReport(state.attributes.get('proof_key'),state.attributes.get('proof_at'))
    pins=tuple(ContextSourceProfile(parent.unique_id,binding.room_id,'contact',c.entity.platform,
                   c.entity.unique_id,'synthetic_original_contact',report) for c in refs) if profiles else ()
    runtime=ShadowRuntime(hass,parent,[binding],clock=lambda:clock[0],context_source_profiles=pins)
    runtime._active=True # Explicit fixture owner; no transport/output authority.
    return runtime,binding,clock,utc


@pytest.mark.asyncio
async def test_native_closed_contacts_age_without_refresh_and_expire_independently(hass,monkeypatch):
    runtime,binding,clock,_=setup(hass,monkeypatch,age=3600000)
    assert runtime.comfort_context(binding)['window_open'] is False
    clock[0]+=1800
    state=runtime.comfort_context(binding)
    assert state['window_open'] is False and state['window_age_ms']>=1800000
    clock[0]+=1800
    assert runtime.comfort_context(binding)['window_open'] is None
    assert runtime.context_source_status(binding.room_id)['contacts']['reason']=='contact_state_unknown'


@pytest.mark.asyncio
async def test_contact_unavailability_and_close_delay_do_not_renew_temperature(hass,monkeypatch):
    runtime,binding,clock,_=setup(hass,monkeypatch,close=1000)
    before=runtime.observations[binding.room_id]
    assert runtime.comfort_context(binding)['window_open'] is None
    clock[0]+=1
    assert runtime.comfort_context(binding)['window_open'] is False
    first=binding.contacts[0].entity.entity_id
    hass.states.async_set(first,'on',{'device_class':'window'});runtime._source_event(first,'changed')
    assert runtime.comfort_context(binding)['window_open'] is True
    assert runtime.observations[binding.room_id] is before
    second=binding.contacts[1].entity.entity_id
    clock[0]+=0.1;hass.states.async_set(second,'unavailable')
    assert runtime.comfort_context(binding)['window_open'] is True
    clock[0]+=0.1;hass.states.async_set(first,'off',{'device_class':'window'})
    assert runtime.comfort_context(binding)['window_open'] is None
    clock[0]+=0.1;hass.states.async_set(second,'off',{'device_class':'door'})
    assert runtime.comfort_context(binding)['window_open'] is None
    clock[0]+=1
    assert runtime.comfort_context(binding)['window_open'] is False


@pytest.mark.asyncio
async def test_contact_registry_loss_or_restored_state_cannot_inherit_closed_context(hass,monkeypatch):
    runtime,binding,clock,_=setup(hass,monkeypatch)
    assert runtime.comfort_context(binding)['window_open'] is False
    row=binding.contacts[0].entity
    hass.states.async_set(row.entity_id,'off',{'restored':True,'device_class':'window'})
    assert runtime.comfort_context(binding)['window_open'] is None
    er.async_get(hass).async_remove(row.entity_id)
    er.async_get(hass).async_get_or_create('binary_sensor','context_fixture','unrelated',suggested_object_id=row.entity_id.split('.')[1])
    hass.states.async_set(row.entity_id,'off',{'device_class':'window'})
    assert runtime.comfort_context(binding)['window_open'] is None


@pytest.mark.asyncio
async def test_selected_original_contact_reports_advance_only_on_new_events_and_replays_do_not_renew(hass,monkeypatch):
    runtime,binding,clock,utc=setup(hass,monkeypatch,profiles=True)
    assert runtime.comfort_context(binding)['window_open'] is None
    for c in binding.contacts:
        eid=c.entity.entity_id
        hass.states.async_set(eid,'off',{'proof_key':'first','proof_at':utc})
        runtime._source_event(eid,'reported')
    assert runtime.comfort_context(binding)['window_open'] is False
    clock[0]+=120
    assert runtime.comfort_context(binding)['window_open'] is None
    for c in binding.contacts:runtime._source_event(c.entity.entity_id,'reported')
    assert runtime.comfort_context(binding)['window_open'] is None
    clock[0]+=1
    for c in binding.contacts:
        eid=c.entity.entity_id
        hass.states.async_set(eid,'off',{'proof_key':'new','proof_at':utc+timedelta(seconds=121)})
        runtime._source_event(eid,'reported')
    assert runtime.comfort_context(binding)['window_open'] is False


@pytest.mark.asyncio
async def test_wire_projection_contains_one_aggregate_with_explicit_age_and_no_native_contact_ids(hass,monkeypatch):
    runtime,binding,_,_=setup(hass,monkeypatch)
    record=comfort_record(binding)
    assert record['window'] is True and record['window_max_age_ms']==3600000
    assert 'entity' not in repr(record) and 'contact_' not in repr(record)
    assert runtime.context_source_status(binding.room_id)['contacts']['count']==2
