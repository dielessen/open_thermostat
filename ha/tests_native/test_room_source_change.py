"""Prospective native profile over actual saved ownership; no live device I/O."""
from copy import deepcopy
import pytest
from custom_components.open_thermostat import room_editor as ui
from custom_components.open_thermostat.native_plan import native_entry_state
from custom_components.open_thermostat.native_provisioning import (
    propose_room_source_change, current_profile_only, local_device_descriptor, source_selection, SOURCE_OPTION,
)
from test_native_control_plan import native_plan, native_two
from test_v1_native import room
from test_graph_owner_interop import pair
from custom_components.open_thermostat.graph_shadow_validation import canonical


def select_saved_source(hass,monkeypatch,n):
    from custom_components import open_thermostat as integration
    # Exercise the normal persisted selection; this operation must not replace
    # a source owned by an independently configured integration profile.
    monkeypatch.setattr(integration,'_NATIVE_PLAN_SOURCE_PROFILES',())
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,SOURCE_OPTION:source_selection(n.source)})


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
@pytest.mark.parametrize('change', ['sensor', 'output', 'bounds', 'name'])
async def test_pending_room_profile_preserves_real_entry_and_previous_source(native_plan,hass,monkeypatch,change):
    n=native_plan
    select_saved_source(hass,monkeypatch,n)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    settings=deepcopy(model['settings'])
    other=room(hass,room_id='bbbb2222',suffix='prospective')
    if change=='sensor':settings['temperature_entity']=other.temperature.entity_id
    if change=='output':settings['radiator_entities']=[other.actuators[0].entity_id]
    if change=='bounds':settings['maximum_centi_c']-=100
    if change=='name':settings['name']='Pending name'
    entry,sub,old=ui._target(hass,n.parent.entry_id,n.rad.room_id)
    candidate=ui.prepare_room_edit(hass,entry,sub,old,settings)
    pending,graph,_=candidate()
    before=native_entry_state(entry)
    source=propose_room_source_change(hass,entry,n.source,pending,graph.storage_document())
    assert native_entry_state(entry)==before
    assert n.connection.client.journal['staged'] is None
    if change=='name':
        assert source is n.source
    else:
        assert source.predecessor==current_profile_only(n.source)
        assert source.policy.controller_id==n.source.policy.controller_id
        assert source.policy.adapter_id==n.source.policy.adapter_id
        assert source.documents()[0]['mapping_revision']==n.source.documents()[0]['mapping_revision']+1
        assert source.policy.profile_digest!=n.source.policy.profile_digest
        assert local_device_descriptor(source)[0]=='native.source.evolution.v1'
        source.validate_prospective_native(hass,entry,pending,graph.storage_document())
        async with pair(hass) as pending_peer:
            loaded=await pending_peer.request('initialize_native_local_source',
                controller=source.policy.controller_id,boot='pending_boot',owner=source.policy.adapter_id,
                stored='',local_source=canonical(local_device_descriptor(source)))
            assert not loaded['fault'] and loaded['writes']==0 and loaded['revision']==0
        # Runtime must still reject using this profile against the OLD saved
        # intent. A prepared future profile is not current admission authority.
        with pytest.raises(ValueError):source.validate_native(hass,entry)
    assert (await n.peer.request('durable_readback'))['writes']==0


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_native_room_profile_rejects_two_trvs_without_touching_intent(native_plan,hass,monkeypatch):
    n=native_plan
    select_saved_source(hass,monkeypatch,n)
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    settings=deepcopy(model['settings']);other=room(hass,room_id='cccc3333',suffix='second')
    settings['radiator_entities'].append(other.actuators[0].entity_id)
    entry,sub,old=ui._target(hass,n.parent.entry_id,n.rad.room_id)
    pending,graph,_=ui.prepare_room_edit(hass,entry,sub,old,settings)()
    before=native_entry_state(entry)
    with pytest.raises(ValueError,match='native_group_limit'):
        propose_room_source_change(hass,entry,n.source,pending,graph.storage_document())
    assert native_entry_state(entry)==before
    assert (await n.peer.request('durable_readback'))['writes']==0


@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'week': True, 'single': True, 'local_source': True, 'product': True}], indirect=True)
async def test_pending_profile_cannot_replace_an_independent_source_owner(native_plan,hass):
    n=native_plan
    model=ui.read_room(hass,n.parent.entry_id,n.rad.room_id)
    entry,sub,old=ui._target(hass,n.parent.entry_id,n.rad.room_id)
    settings=deepcopy(model['settings']);settings['maximum_centi_c']-=100
    pending,graph,_=ui.prepare_room_edit(hass,entry,sub,old,settings)()
    before=native_entry_state(entry)
    with pytest.raises(ValueError,match='native_source_owner_changed'):
        propose_room_source_change(hass,entry,n.source,pending,graph.storage_document())
    assert native_entry_state(entry)==before
    assert (await n.peer.request('durable_readback'))['writes']==0
