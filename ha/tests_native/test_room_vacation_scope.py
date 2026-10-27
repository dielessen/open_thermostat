"""Actual HA climate service + C++ vacation admission under expected room scope."""
import asyncio
from datetime import datetime,timezone,timedelta
import logging
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import pytest_asyncio
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError,Unauthorized
from homeassistant.helpers import entity_platform,entity_registry as er
from custom_components.open_thermostat.climate import async_setup_entry
from custom_components.open_thermostat.room_vacation import preview_vacation,ws_vacation_preview
from custom_components.open_thermostat.product import configuration_snapshot
from custom_components.open_thermostat.v1_wire import digest
from test_comfort_interop import comfort,command,observe


@pytest_asyncio.fixture
async def vacation(comfort,hass):
    runtime,client,bus,binding,_=comfort
    from custom_components.open_thermostat import async_migrate_entry
    assert await async_migrate_entry(hass,runtime.entry)
    runtime.entry._async_set_state(hass,ConfigEntryState.LOADED,None)
    previous_zone=hass.config.time_zone
    await hass.config.async_set_time_zone('Europe/Amsterdam')
    hass.data['open_thermostat']={runtime.entry.entry_id:{'v1_runtime':runtime}}
    platform=entity_platform.EntityPlatform(hass=hass,logger=logging.getLogger(__name__),domain='climate',
        platform_name='open_thermostat',platform=None,scan_interval=timedelta(seconds=30),entity_namespace=None)
    platform.config_entry=runtime.entry;token=entity_platform.current_platform.set(platform);tasks=[]
    def add(entities,*,config_subentry_id=None):
        tasks.append(hass.async_create_task(platform.async_add_entities(entities,config_subentry_id=config_subentry_id)))
    try:
        await async_setup_entry(hass,runtime.entry,add);await asyncio.gather(*tasks)
        await bus.start();await observe(runtime,client,bus,binding);await hass.async_block_till_done()
        entity=next(iter(platform.entities.values()))
        scope={'expected_entry_id':runtime.entry.entry_id,'expected_room_id':binding.room_id,
               'expected_token':digest(configuration_snapshot(runtime.entry)),'expected_time_zone':hass.config.time_zone}
        yield SimpleNamespace(runtime=runtime,client=client,bus=bus,binding=binding,entity=entity,scope=scope)
    finally:
        await platform.async_reset();entity_platform.current_platform.reset(token)
        runtime.entry._async_set_state(hass,ConfigEntryState.NOT_LOADED,None)
        await hass.config.async_set_time_zone(previous_zone)


def frames(n):return [x for x in n.bus.transcript if x[0]=='ha' and x[1]=='ha/user_command']


@pytest.mark.asyncio
async def test_preview_is_read_only_then_existing_service_sets_and_cancels_finite_vacation(vacation,hass):
    n=vacation;before=configuration_snapshot(n.runtime.entry);scope=n.scope
    local=(datetime.now(timezone.utc)+timedelta(days=2)).strftime('%Y-%m-%dT18:00')
    preview=preview_vacation(hass,scope['expected_entry_id'],scope['expected_room_id'],scope['expected_token'],local,scope['expected_time_zone'])
    assert preview['entity_id']==n.entity.entity_id and len(preview['candidates'])==1
    assert configuration_snapshot(n.runtime.entry)==before and not frames(n)
    end=preview['candidates'][0]
    await command(n.bus,hass.services.async_call('open_thermostat','set_comfort',{
        'entity_id':n.entity.entity_id,'mode':'vacation','vacation_until':end['iso'],**scope},blocking=True))
    await hass.async_block_till_done()
    state=n.runtime.decisions[n.binding.room_id]
    assert state.comfort_mode=='vacation' and state.vacation_until_utc==end['until_utc']
    attrs=hass.states.get(n.entity.entity_id).attributes
    assert attrs['vacation_ends_at']==end['iso'] and attrs['vacation_time_zone']=='Europe/Amsterdam'
    await command(n.bus,hass.services.async_call('open_thermostat','set_comfort',{
        'entity_id':n.entity.entity_id,'mode':'auto',**scope},blocking=True))
    assert n.runtime.decisions[n.binding.room_id].vacation_until_utc==0
    assert len(frames(n))==2 and configuration_snapshot(n.runtime.entry)==before
    assert n.entity.extra_state_attributes['boiler_output_enabled'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('fault',['other_entry','other_room','partial_scope','stale_token','timezone','foreign_state','disabled_entity','replaced_runtime'])
async def test_expected_scope_rejects_before_any_command(vacation,hass,fault):
    n=vacation;scope=dict(n.scope)
    if fault=='other_entry':scope['expected_entry_id']='another_entry'
    if fault=='other_room':scope['expected_room_id']='ffffffff'
    if fault=='partial_scope':scope.pop('expected_token')
    if fault=='stale_token':scope['expected_token']='f'*64
    if fault=='timezone':scope['expected_time_zone']='UTC'
    if fault=='foreign_state':
        attrs=dict(hass.states.get(n.entity.entity_id).attributes);attrs['room_id']='ffffffff'
        hass.states.async_set(n.entity.entity_id,'heat',attrs)
    if fault=='disabled_entity':er.async_get(hass).async_update_entity(n.entity.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    if fault=='replaced_runtime':hass.data['open_thermostat'][n.runtime.entry.entry_id]['v1_runtime']=None
    with pytest.raises(HomeAssistantError):await n.entity.async_set_comfort('away',**scope)
    assert not frames(n)


@pytest.mark.asyncio
async def test_changed_scope_after_dispatch_is_uncertain_and_never_replayed(vacation,hass,monkeypatch):
    n=vacation;original=n.runtime.async_comfort
    async def changed(*args,**kwargs):
        await original(*args,**kwargs)
        hass.config_entries.async_update_entry(n.runtime.entry,title='Changed after original dispatch')
    monkeypatch.setattr(n.runtime,'async_comfort',changed)
    with pytest.raises(HomeAssistantError):await command(n.bus,n.entity.async_set_comfort('away',**n.scope))
    assert len(frames(n))==1
    assert n.runtime.decisions[n.binding.room_id].comfort_mode=='away'


@pytest.mark.asyncio
async def test_preview_endpoint_requires_admin_before_access(hass):
    for user in (None,SimpleNamespace(is_admin=False)):
        connection=SimpleNamespace(user=user,send_result=Mock(),send_error=Mock())
        with pytest.raises(Unauthorized):ws_vacation_preview(hass,connection,{'id':1})
        connection.send_result.assert_not_called();connection.send_error.assert_not_called()
