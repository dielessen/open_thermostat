"""Normal comfort edit through real native HA/C++ source and durable readback."""
from copy import deepcopy
import json
import pytest
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.product import configuration_snapshot
from test_native_control_plan import native_plan, native_two
from test_controller_connection import drive
from test_room_contacts_active_plan import install_reload
from test_room_comfort_setup import person, PROFILE

OPTIONS={'week':True,'single':True,'local_source':True,'product':True,'minimum_target_centi_c':500}


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[OPTIONS],indirect=True)
async def test_comfort_presence_save_and_remove_reuse_source_and_real_cpp_targets(native_plan,hass):
    n=native_plan;await n.apply();source=n.source;install_reload(hass,n);selected=person(hass)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings.update(comfort=deepcopy(PROFILE),presence_entity=selected.entity_id)
    before=deepcopy(n.client.journal['accepted']['config'])
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=1600)
    assert saved['settings']==settings and not saved['apply_pending'] and n.source is source
    accepted=n.client.journal['accepted']['config'];profile=accepted['zones'][0]['comfort']
    assert profile['frost_centi_c']==500 and profile['presence'] is True and profile['window'] is False
    assert accepted['mapping']==before['mapping'] and accepted['profile_digest']==before['profile_digest']
    assert json.loads((await n.peer.request('durable_readback'))['stored'])==accepted
    # The existing settle helper advances 121 seconds, past the 120-second
    # presence TTL. Fresh temperatures must not refresh an unchanged person.
    await n.settle(18,22)
    assert n.runtime.decisions[n.rad.room_id].reason=='presence_state_unknown'
    async def presence_report(value):
        attrs=dict(hass.states.get(selected.entity_id).attributes)
        hass.states.async_set(attrs['source'],value,{'source_type':'router'})
        hass.states.async_set(selected.entity_id,value,attrs)
        await hass.async_block_till_done();await n.drain()
    await presence_report('home')
    assert n.runtime.decisions[n.rad.room_id].target_centi_c==2100
    original=n.runtime.observations[n.rad.room_id]
    await presence_report('not_home')
    assert n.runtime.observations[n.rad.room_id] is original
    assert n.runtime.decisions[n.rad.room_id].target_centi_c==1700
    await presence_report('Work')
    assert n.runtime.decisions[n.rad.room_id].target_centi_c is None
    assert n.runtime.decisions[n.rad.room_id].reason=='presence_state_unknown'
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings.update(comfort=None,presence_entity='')
    saved=await drive(n,ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings),steps=1600)
    assert not saved['apply_pending'] and n.source is source
    assert n.runtime.rooms[n.rad.room_id].comfort is None and n.runtime.rooms[n.rad.room_id].presence is None
    assert 'comfort' not in n.client.journal['accepted']['config']['zones'][0]
    await n.settle(18,22);assert n.runtime.decisions[n.rad.room_id].target_centi_c==2100


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan',[OPTIONS],indirect=True)
@pytest.mark.parametrize('fault',['capability','source_frost'])
async def test_unsupported_comfort_cannot_save_before_controller_rejects_it(native_plan,hass,fault):
    n=native_plan;await n.apply();selected=person(hass)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id);settings=deepcopy(model['settings'])
    settings.update(comfort=deepcopy(PROFILE),presence_entity=selected.entity_id)
    if fault=='capability':n.client.comfort_supported=False;reason='comfort_capability_unavailable'
    else:settings['comfort']['frost_centi_c']=1000;reason='native_comfort_frost_profile'
    before=configuration_snapshot(n.parent)
    with pytest.raises(ValueError,match='^'+reason+'$'):
        await ui.save_room(hass,n.parent.entry_id,n.rad.room_id,model['token'],settings)
    assert configuration_snapshot(n.parent)==before and n.runtime.enabled
    assert (await n.peer.request('durable_readback'))['writes']==1
    n.reload.assert_not_awaited()
