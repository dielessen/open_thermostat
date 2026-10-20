"""Actual native manager/Store acceptance; graph-only is not a wire profile."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ConfigEntryError

import custom_components.open_thermostat as integration
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow
from custom_components.open_thermostat.v1_model import (
    RoomBinding, ROOM_GRAPH_DRAFT, ROOM_CLIMATE_TRV, CONF_ENABLED, CONF_MODE, MODE_LEGACY)
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration, NativeShadowConnection
from custom_components.open_thermostat.v1_climate import ShadowRoom
from custom_components.open_thermostat.v1_heating_graph import reconcile_removed_rooms
from test_v1_native import entry, room, LocalTransport
from test_v1_heating_graph_gui import (create_central, open_graph, add_group, add_actuator,
                                      menu, registry_entity, heating)

@pytest.fixture
def manager(hass, monkeypatch):
    monkeypatch.setattr(config_entries, "_async_get_flow_handler",
                        AsyncMock(return_value=OpenThermostatConfigFlow))
    return hass.config_entries.subentries

def values(binding, **kw):
    return {"name":binding.name,
        "temperature_entity":binding.temperature.entity_id,
        "actuator_entities":[a.entity_id for a in binding.actuators],
        "base_temperature":binding.base_centi_c/100,
        "minimum_target_temperature":binding.minimum_target_centi_c/100,
        "maximum_target_temperature":binding.maximum_target_centi_c/100,
        "maximum_age_ms":binding.maximum_age_ms, **kw}

async def edit(manager, parent, sub):
    return await manager.async_init((parent.entry_id,"zone"),
        context={"source":"reconfigure","subentry_id":sub.subentry_id})

def graph(binding):
    return replace(binding,actuators=(),binding_mode=ROOM_GRAPH_DRAFT)

@pytest.mark.asyncio
async def test_legacy_record_roundtrip_exact_no_migration_or_new_wire_keys(hass):
    binding=room(hass)
    original=binding.as_dict()
    assert "binding_mode" not in original
    assert RoomBinding.from_dict(original).as_dict()==original
    old=entry(hass,room=binding)
    runtime=ShadowRuntime(hass,old,[binding])
    zones,mapping=await async_build_configuration(runtime)
    assert mapping["rooms"]==[original]
    assert zones==[{"zone_id":binding.room_id,"sensor_id":"s_"+binding.room_id,
        "actuator_id":"a_"+binding.room_id,"base_centi_c":2100,"max_age_ms":120000,
        "report_evidence":"physical_report","schedule":None}]

@pytest.mark.asyncio
async def test_native_graph_room_without_any_trv_selection_create_edit_store(hass,manager):
    binding=room(hass)
    parent=entry(hass)
    r=await manager.async_init((parent.entry_id,"zone"),context={"source":"user"})
    v=values(binding,room_id=binding.room_id,binding_mode=ROOM_GRAPH_DRAFT)
    del v["actuator_entities"]
    r=await manager.async_configure(r["flow_id"],v)
    assert r["type"]=="create_entry"
    sub=next(iter(parent.subentries.values()));sid=sub.subentry_id
    assert sub.data["binding_mode"]==ROOM_GRAPH_DRAFT and sub.data["actuators"]==[]
    assert sub.data["actuator_profile"]=="graph_draft_not_applied"
    r=await edit(manager,parent,sub)
    r=await manager.async_configure(r["flow_id"],values(graph(binding),name="Floor room",
        binding_mode=ROOM_GRAPH_DRAFT,minimum_target_temperature=16,maximum_target_temperature=25))
    assert r["reason"]=="reconfigure_successful"
    assert sub.subentry_id==sid and sub.unique_id==binding.room_id
    saved=deepcopy(dict(sub.data))
    await hass.async_stop(force=True)
    second=HomeAssistant(hass.config.config_dir);second.config_entries=ConfigEntries(second,{})
    try:
        await second.config_entries.async_initialize()
        assert dict(second.config_entries.async_get_entry(parent.entry_id).subentries[sid].data)==saved
    finally:
        await second.async_stop(force=True)

@pytest.mark.asyncio
async def test_explicit_mode_migration_preserves_room_week_bounds_and_graph(hass,manager):
    binding=replace(room(hass),minimum_target_centi_c=1600,maximum_target_centi_c=2400,
        week_program={"monday":[{"start":3600,"end":7200,"target_centi_c":2050}]})
    parent=entry(hass,room=binding);sub=next(iter(parent.subentries.values()))
    await create_central(manager,parent)
    r=await open_graph(manager,parent);r=await add_group(manager,r)
    r=await add_actuator(manager,r,binding.room_id,binding.actuators[0].entity_id)
    await menu(manager,r,"save_graph")
    saved_graph=deepcopy(dict(heating(parent).data));before=deepcopy(dict(sub.data))
    r=await edit(manager,parent,sub)
    v=values(binding,binding_mode=ROOM_GRAPH_DRAFT,actuator_entities=[])
    bad=await manager.async_configure(r["flow_id"],v)
    assert bad["errors"]["base"]=="confirm_room_mode_change" and sub.data==before
    r=await manager.async_configure(r["flow_id"],{**v,"confirm_binding_mode_change":True})
    assert r["reason"]=="reconfigure_successful"
    after=dict(sub.data)
    for k in ("room_id","week_program","minimum_target_centi_c","maximum_target_centi_c",
              "temperature","setpoint","schedule","base_centi_c","maximum_age_ms"):
        assert after[k]==before[k]
    assert heating(parent).data==saved_graph
    # Explicit reverse migration reselects the same TRV, no new room identity.
    r=await edit(manager,parent,sub)
    r=await manager.async_configure(r["flow_id"],values(binding,
        binding_mode=ROOM_CLIMATE_TRV,confirm_binding_mode_change=True))
    assert r["reason"]=="reconfigure_successful"
    assert dict(sub.data)==before and heating(parent).data==saved_graph

@pytest.mark.asyncio
@pytest.mark.parametrize("mode,actors,err",[
    (ROOM_GRAPH_DRAFT,True,"room_mode_actuator_conflict"),
    (ROOM_CLIMATE_TRV,False,"room_mode_actuator_conflict"),
    ("unsupported",False,"unsupported_room_binding_mode"),
])
async def test_native_bad_mode_combinations_atomic(hass,manager,mode,actors,err):
    binding=room(hass);parent=entry(hass,room=binding);sub=next(iter(parent.subentries.values()))
    before=deepcopy(dict(sub.data))
    r=await edit(manager,parent,sub)
    if mode=="unsupported":
        with pytest.raises(ValueError,match=err):
            RoomBinding.from_dict({**before,"binding_mode":mode,"actuators":[]})
        manager.async_abort(r["flow_id"]);return
    r=await manager.async_configure(r["flow_id"],values(binding,binding_mode=mode,
        actuator_entities=[binding.actuators[0].entity_id] if actors else [],
        confirm_binding_mode_change=True))
    assert r["errors"]["base"]==err and sub.data==before

@pytest.mark.asyncio
async def test_graph_room_week_editor_remains_graph_only(hass,manager):
    binding=graph(room(hass));parent=entry(hass,room=binding)
    sub=next(iter(parent.subentries.values()))
    r=await edit(manager,parent,sub)
    r=await manager.async_configure(r["flow_id"],values(binding,binding_mode=ROOM_GRAPH_DRAFT,program_action="edit_week"))
    r=await menu(manager,r,"add_block")
    r=await manager.async_configure(r["flow_id"],{
        "days":["monday"],"start_time":"07:00:00","end_time":"08:00:00","temperature":21})
    r=await menu(manager,r,"save_program")
    assert r["reason"]=="reconfigure_successful"
    assert sub.data["binding_mode"]==ROOM_GRAPH_DRAFT and sub.data["actuators"]==[]
    assert sub.data["week_program"]["monday"][0]["target_centi_c"]==2100

@pytest.mark.asyncio
async def test_graph_only_floor_switch_owner_and_native_room_delete_cascade(hass,manager):
    binding=graph(room(hass));parent=entry(hass,room=binding)
    sub=next(iter(parent.subentries.values()))
    await create_central(manager,parent)
    output=registry_entity(hass,"switch","floor")
    r=await open_graph(manager,parent);r=await add_group(manager,r,emitter="floor",maximum_supply_temperature=70)
    # Unmixed floor upper matches central; no claim 70C physically safe.
    r=await add_actuator(manager,r,binding.room_id,output,"binary_valve",
        deenergized_position="normally_closed",control="tpi",travel_time_s=180,
        minimum_on_s=180,minimum_off_s=120,cycle_s=900)
    await menu(manager,r,"save_graph")
    old=heating(parent);before=deepcopy(dict(old.data))
    hass.config_entries.async_remove_subentry(parent,sub.subentry_id)
    assert reconcile_removed_rooms(hass,parent)
    assert old.data["draft"]["actuators"]==[]
    assert old.data["draft"]["central"]==before["draft"]["central"]
    assert old.data["draft"]["groups"]==before["draft"]["groups"]
    assert old.data["last_room_cascade"]==before["draft"]["actuators"]
    from homeassistant.helpers import entity_registry as er
    assert er.async_get(hass).async_get(output)

@pytest.mark.asyncio
async def test_stale_room_form_cannot_overwrite_native_external_update(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);sub=next(iter(parent.subentries.values()))
    r=await edit(manager,parent,sub)
    changed={**dict(sub.data),"name":"Concurrent"}
    hass.config_entries.async_update_subentry(parent,sub,data=changed)
    r=await manager.async_configure(r["flow_id"],values(binding,name="Stale"))
    assert r["reason"]=="room_changed" and dict(sub.data)==changed

@pytest.mark.asyncio
@pytest.mark.parametrize("enabled",[False,True])
async def test_graph_export_runtime_attach_all_fail_closed_without_io(hass,enabled):
    binding=graph(room(hass));parent=entry(hass,room=binding,enabled=enabled)
    runtime=ShadowRuntime(hass,parent,[binding])
    with pytest.raises(ConfigEntryError,match="graph_room_contract_unavailable"):
        await async_build_configuration(runtime)
    connection=NativeShadowConnection(runtime)
    with pytest.raises(ConfigEntryError):
        await connection.async_start()
    assert connection.client is None and connection.worker is None and connection.unsubs==[]
    with pytest.raises(HomeAssistantError,match="graph_room_contract_unavailable"):
        runtime.attach_transport(LocalTransport())
    if enabled:
        with pytest.raises(HomeAssistantError,match="graph_room_contract_unavailable"):
            await runtime.async_start()
    else:
        await runtime.async_start()
    assert runtime.enabled is False and runtime._subscriptions==[]
    entity=ShadowRoom("fixture",binding,runtime)
    assert not entity.available and entity.extra_state_attributes["actuator_profile"]=="graph_draft_not_applied"

@pytest.mark.asyncio
@pytest.mark.parametrize("mode,enabled",[("v1_shadow",True),(MODE_LEGACY,False)])
async def test_options_and_setup_reject_unsupported_graph_activation_before_io(hass,mode,enabled):
    binding=graph(room(hass));parent=entry(hass,room=binding)
    flow=ShadowOptionsFlow();flow.hass=hass;flow.handler=parent.entry_id
    r=await flow.async_step_init({CONF_MODE:mode,CONF_ENABLED:enabled,"adapter_id":"ha1"})
    assert r["errors"]["base"]=="graph_room_contract_unavailable"
    hass.config_entries.async_update_entry(parent,options={CONF_MODE:mode,CONF_ENABLED:enabled})
    with pytest.raises(ConfigEntryError,match="graph_room_contract_unavailable"):
        await integration.async_setup_entry(hass,parent)
    assert "open_thermostat" not in hass.data

@pytest.mark.asyncio
async def test_live_runtime_blocks_graph_migration_even_when_saved_option_off(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);sub=next(iter(parent.subentries.values()))
    class Running:
        enabled=True
    hass.data["open_thermostat"]={parent.entry_id:{"v1_runtime":Running()}}
    r=await edit(manager,parent,sub)
    r=await manager.async_configure(r["flow_id"],values(binding,
        binding_mode=ROOM_GRAPH_DRAFT,actuator_entities=[],confirm_binding_mode_change=True))
    assert r["errors"]["base"]=="graph_room_runtime_off_required"
    assert "binding_mode" not in sub.data

@pytest.mark.asyncio
async def test_disabled_graph_room_sensor_unavailable_is_not_physical_evidence(hass,manager):
    binding=room(hass);hass.states.async_set(binding.temperature.entity_id,"unavailable")
    parent=entry(hass)
    r=await manager.async_init((parent.entry_id,"zone"),context={"source":"user"})
    r=await manager.async_configure(r["flow_id"],values(graph(binding),room_id=binding.room_id,binding_mode=ROOM_GRAPH_DRAFT))
    assert r["type"]=="create_entry"
    runtime=ShadowRuntime(hass,parent,[RoomBinding.from_dict(r["data"])])
    await runtime.async_start()
    assert runtime.observations[binding.room_id].quality=="disabled"
    assert runtime.decisions=={}

@pytest.mark.asyncio
async def test_native_migration_store_keeps_other_room_and_native_entities(hass,manager):
    from homeassistant.config_entries import ConfigSubentry
    from homeassistant.helpers import entity_registry as er
    binding=room(hass);other=replace(room(hass,"b1b2c3d4","other"),
        minimum_target_centi_c=1700,maximum_target_centi_c=2300)
    parent=entry(hass,room=binding);sub=next(iter(parent.subentries.values()))
    second_sub=ConfigSubentry(data=other.as_dict(),subentry_type="zone",title=other.name,unique_id=other.room_id)
    hass.config_entries.async_add_subentry(parent,second_sub)
    original_other=deepcopy(dict(second_sub.data))
    source_ids={r.entity_id for r in er.async_get(hass).entities.values()}
    r=await edit(manager,parent,sub)
    r=await manager.async_configure(r["flow_id"],values(binding,binding_mode=ROOM_GRAPH_DRAFT,
        actuator_entities=[],confirm_binding_mode_change=True))
    assert r["reason"]=="reconfigure_successful"
    expected=deepcopy(dict(sub.data));parent_id=parent.entry_id
    assert dict(second_sub.data)==original_other
    assert {r.entity_id for r in er.async_get(hass).entities.values()}==source_ids
    await hass.async_stop(force=True)
    restored=HomeAssistant(hass.config.config_dir);restored.config_entries=ConfigEntries(restored,{})
    try:
        await restored.config_entries.async_initialize()
        stored=restored.config_entries.async_get_entry(parent_id)
        assert dict(stored.subentries[sub.subentry_id].data)==expected
        assert dict(stored.subentries[second_sub.subentry_id].data)==original_other
        assert stored.options[CONF_ENABLED] is False
    finally:
        await restored.async_stop(force=True)

@pytest.mark.asyncio
async def test_mixed_rooms_export_is_all_or_nothing(hass):
    one=room(hass);two=graph(room(hass,"b1b2c3d4","floor"))
    parent=entry(hass)
    runtime=ShadowRuntime(hass,parent,[one,two])
    with pytest.raises(ConfigEntryError,match="graph_room_contract_unavailable"):
        await async_build_configuration(runtime)
    assert runtime.decisions=={} and runtime._transport is None and not runtime.enabled

@pytest.mark.asyncio
async def test_graph_only_invalid_bounds_do_not_replace_saved_room(hass,manager):
    binding=graph(room(hass));parent=entry(hass,room=binding)
    sub=next(iter(parent.subentries.values()));before=deepcopy(dict(sub.data))
    r=await edit(manager,parent,sub)
    r=await manager.async_configure(r["flow_id"],values(binding,binding_mode=ROOM_GRAPH_DRAFT,
        minimum_target_temperature=24,maximum_target_temperature=16))
    assert r["errors"]["base"]=="invalid_target_range"
    assert dict(sub.data)==before
