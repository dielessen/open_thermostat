"""Helper edits on the real native source without changing its mapping."""
from copy import deepcopy
import json
import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from test_native_control_plan import native_plan, native_two
from test_controller_connection import drive
from test_room_contacts_active_plan import install_reload
from test_manual_target_setup import helper
from test_room_profile_apply import saved_connection
from test_v1_native import room


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_native_helper_add_remove_keeps_same_source_and_durable_mapping(native_plan,hass):
    n=native_plan;await n.apply();source=n.source;install_reload(hass,n);selected=helper(hass)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings.update(setpoint_entity=selected.entity_id,setpoint_duration_ms=600000)
    before=deepcopy(n.client.journal['accepted']['config'])
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=1600)
    assert saved['settings']==settings and not saved['apply_pending'] and n.source is source
    assert n.runtime.rooms[n.rad.room_id].setpoint.unique_id==selected.unique_id
    accepted=n.client.journal['accepted']['config']
    assert accepted['mapping']==before['mapping'] and accepted['profile_digest']==before['profile_digest']
    assert json.loads((await n.peer.request('durable_readback'))['stored'])==accepted
    # A lost optional input must not take the ordinary temperature/control source down.
    await n.settle(16,22);original=n.runtime.observations[n.rad.room_id]
    er.async_get(hass).async_remove(selected.entity_id);await hass.async_block_till_done();await n.drain()
    assert n.runtime.enabled and n.runtime.observations[n.rad.room_id] is original
    assert n.runtime.decisions[n.rad.room_id].demand
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings']);settings['setpoint_entity']=''
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=1600)
    assert not saved['apply_pending'] and n.source is source and n.runtime.rooms[n.rad.room_id].setpoint is None
    assert n.client.journal['accepted']['config']['mapping']==before['mapping']


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_missing_manual_capability_refuses_before_saved_intent_or_reload(native_plan,hass):
    n=native_plan;await n.apply();selected=helper(hass);n.client.manual_target_supported=False
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings['setpoint_entity']=selected.entity_id;before=configuration_snapshot(n.parent)
    with pytest.raises(ValueError,match='^manual_target_capability_unavailable$'):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    assert configuration_snapshot(n.parent)==before and n.runtime.enabled
    n.reload.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[{'week':True,'single':True,'local_source':True,'product':True}],indirect=True)
async def test_combined_sensor_and_helper_edit_also_checks_capability_before_stopping(native_plan,hass,monkeypatch):
    n=native_plan;await saved_connection(hass,monkeypatch,n);await n.apply()
    selected=helper(hass);other=room(hass,'bbcc7788','replacement');n.client.manual_target_supported=False
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings.update(setpoint_entity=selected.entity_id,temperature_entity=other.temperature.entity_id)
    before=configuration_snapshot(n.parent);worker=n.connection
    with pytest.raises(ValueError,match='^manual_target_capability_unavailable$'):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    assert configuration_snapshot(n.parent)==before and n.runtime.enabled and n.connection is worker
    assert (await n.peer.request('durable_readback'))['writes']==1
