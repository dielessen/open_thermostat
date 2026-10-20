"""Actual native graph menus, atomic Store and ownership/cascade acceptance."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntries, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.v1_heating_draft import HeatingContractUnavailable, parse_heating_draft
from custom_components.open_thermostat.v1_heating_graph import reconcile_removed_rooms, validated_graph
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_config_flow import ZoneSubentryFlow
from custom_components.open_thermostat import _async_options_updated
from test_v1_native import entry, room
from test_v1_heating_draft import form_values


@pytest.fixture
def manager(hass,monkeypatch):
    monkeypatch.setattr(config_entries,"_async_get_flow_handler",AsyncMock(return_value=OpenThermostatConfigFlow))
    return hass.config_entries.subentries


def heating(parent):
    return next(s for s in parent.subentries.values() if s.subentry_type=="heating")


def registry_entity(hass,domain,name):
    entity=er.async_get(hass).async_get_or_create(domain,"graph_fixture",name)
    if domain=="sensor":
        hass.states.async_set(entity.entity_id,"20",{"device_class":"temperature","unit_of_measurement":"°C"})
    return entity.entity_id


async def create_central(manager,parent):
    r=await manager.async_init((parent.entry_id,"heating"),context={"source":"user"})
    r=await manager.async_configure(r["flow_id"],form_values())
    assert r["type"]=="create_entry"
    return heating(parent)


async def open_graph(manager,parent):
    old=heating(parent)
    r=await manager.async_init((parent.entry_id,"heating"),
        context={"source":"reconfigure","subentry_id":old.subentry_id})
    r=await manager.async_configure(r["flow_id"],form_values(draft_action="edit_graph"))
    assert r["type"]=="menu" and r["step_id"]=="graph"
    return r


async def menu(manager,r,step):
    return await manager.async_configure(r["flow_id"],{"next_step_id":step})


def selector_options(form,key):
    schema={str(k):v for k,v in form["data_schema"].schema.items()}
    return schema[key].config["options"]


async def add_group(manager,r,**changes):
    r=await menu(manager,r,"add_group")
    values={"name":"Radiators","emitter":"radiator","minimum_supply_temperature":20,
            "maximum_supply_temperature":70,"pump_start_delay_s":0,"postrun_s":0,"mixing_kind":"none"}
    return await manager.async_configure(r["flow_id"],{**values,**changes})


async def add_actuator(manager,r,rid,output,profile="trv_room_setpoint",group_id=None,**settings):
    r=await menu(manager,r,"add_actuator")
    gid=group_id or selector_options(r,"group_id")[0]["value"]
    r=await manager.async_configure(r["flow_id"],{"room_id":rid,"group_id":gid,"profile":profile})
    assert r["step_id"]=="actuator_details"
    return await manager.async_configure(r["flow_id"],{"output":output,**settings})


async def seed_graph(hass,manager,*,profile="trv_room_setpoint",output=None):
    binding=room(hass);parent=entry(hass,room=binding)
    old=await create_central(manager,parent)
    r=await open_graph(manager,parent);r=await add_group(manager,r)
    settings={}
    if profile=="binary_valve":
        output=output or registry_entity(hass,"switch","floor")
        settings={"deenergized_position":"normally_closed","control":"tpi","travel_time_s":180,
                  "minimum_on_s":180,"minimum_off_s":120,"cycle_s":900}
    elif profile=="proportional_valve":
        output=output or registry_entity(hass,"number","position")
        settings={"minimum_percent":0,"maximum_percent":100,"travel_time_s":60}
    else:
        output=output or binding.actuators[0].entity_id
    r=await add_actuator(manager,r,binding.room_id,output,profile,**settings)
    assert r["type"]=="menu"
    r=await menu(manager,r,"save_graph")
    assert r["type"]=="abort" and r["reason"]=="reconfigure_successful"
    return parent,binding,old


@pytest.mark.asyncio
@pytest.mark.parametrize("profile",["trv_room_setpoint","binary_valve","proportional_valve"])
async def test_native_create_read_update_delete_profile_and_store(hass,manager,profile):
    parent,binding,old=await seed_graph(hass,manager,profile=profile)
    original_id=old.subentry_id
    before_room=deepcopy(dict(next(s for s in parent.subentries.values() if s.subentry_type=="zone").data))
    d=deepcopy(dict(old.data)["draft"]);a=d["actuators"][0];central=deepcopy(d["central"])
    assert a["profile"]==profile and d["groups"][0]["group_id"]==a["group_id"]
    assert old.data["status"]=="draft_not_applied" and old.data["incomplete_group_ids"]==[]
    r=await open_graph(manager,parent);r=await menu(manager,r,"edit_actuator")
    r=await manager.async_configure(r["flow_id"],{"actuator_id":a["actuator_id"]})
    r=await manager.async_configure(r["flow_id"],{"room_id":binding.room_id,"group_id":a["group_id"],"profile":profile})
    if profile=="binary_valve":
        values={**a["settings"],"output":a["output"]["entity_id"],"minimum_on_s":240}
    elif profile=="proportional_valve":
        values={**a["settings"],"output":a["output"]["entity_id"],"minimum_percent":10}
    else:
        values={"output":a["output"]["entity_id"]}
    r=await manager.async_configure(r["flow_id"],values)
    r=await menu(manager,r,"save_graph")
    assert r["type"]=="abort" and old.subentry_id==original_id
    assert old.data["draft"]["central"]==central
    assert next(s for s in parent.subentries.values() if s.subentry_type=="zone").data==before_room
    saved=deepcopy(dict(old.data))
    await hass.async_stop(force=True)
    second=HomeAssistant(hass.config.config_dir);second.config_entries=ConfigEntries(second,{})
    try:
        await second.config_entries.async_initialize()
        restored=second.config_entries.async_get_entry(parent.entry_id).subentries[original_id]
        assert dict(restored.data)==saved
    finally:
        await second.async_stop(force=True)


@pytest.mark.asyncio
async def test_group_delete_requires_explicit_cascade_and_preserves_rooms_central(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    before=deepcopy(dict(old.data));gid=before["draft"]["groups"][0]["group_id"]
    r=await open_graph(manager,parent);r=await menu(manager,r,"delete_group")
    bad=await manager.async_configure(r["flow_id"],{"group_id":gid,"cascade_actuators":False})
    assert bad["errors"]["base"]=="confirm_group_cascade"
    assert dict(old.data)==before
    r=await manager.async_configure(r["flow_id"],{"group_id":gid,"cascade_actuators":True})
    assert dict(old.data)==before  # deletion only staged
    r=await menu(manager,r,"save_graph")
    assert old.data["draft"]["groups"]==[] and old.data["draft"]["actuators"]==[]
    assert old.data["draft"]["central"]==before["draft"]["central"]
    assert any(s.data.get("room_id")==binding.room_id for s in parent.subentries.values())


@pytest.mark.asyncio
async def test_actuator_delete_confirmation_cancel_and_incomplete_group(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    before=deepcopy(dict(old.data));aid=before["draft"]["actuators"][0]["actuator_id"]
    r=await open_graph(manager,parent);r=await menu(manager,r,"delete_actuator")
    r=await manager.async_configure(r["flow_id"],{"actuator_id":aid,"confirm":False})
    assert r["errors"]["base"]=="confirm_delete"
    r=await manager.async_configure(r["flow_id"],{"actuator_id":aid,"confirm":True})
    assert dict(old.data)==before
    r=await menu(manager,r,"cancel_graph")
    assert r["reason"]=="graph_cancelled" and dict(old.data)==before
    r=await open_graph(manager,parent);r=await menu(manager,r,"delete_actuator")
    r=await manager.async_configure(r["flow_id"],{"actuator_id":aid,"confirm":True})
    await menu(manager,r,"save_graph")
    assert old.data["draft"]["actuators"]==[]
    assert old.data["incomplete_group_ids"]==[before["draft"]["groups"][0]["group_id"]]
    with pytest.raises(HeatingContractUnavailable):
        parse_heating_draft(dict(old.data)["draft"],known_room_ids={binding.room_id}).transport_document()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["three_point","analog_0_10v"])
async def test_native_floor_mixer_fields_and_output_ownership(hass,manager,kind):
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    before=deepcopy(dict(old.data))
    r=await open_graph(manager,parent)
    r=await add_group(manager,r,emitter="floor",maximum_supply_temperature=40,mixing_kind=kind)
    assert r["step_id"]=="mixing"
    supply=registry_entity(hass,"sensor","mixed_supply")
    payload={"supply_sensor":supply,"travel_time_s":120}
    if kind=="three_point":
        output=registry_entity(hass,"switch","open")
        payload.update(open_output=output,close_output=output)
        bad=await manager.async_configure(r["flow_id"],payload)
        assert bad["errors"]["base"]=="output_has_multiple_owners" and dict(old.data)==before
        payload["close_output"]=registry_entity(hass,"switch","close")
    else:
        payload["analog_output"]=registry_entity(hass,"number","mix_position")
    r=await manager.async_configure(r["flow_id"],payload)
    assert r["type"]=="menu" and dict(old.data)==before
    await menu(manager,r,"save_graph")
    assert old.data["draft"]["groups"][0]["mixing"]["kind"]==kind
    assert old.data["draft"]["groups"][0]["supply_limits"]["maximum_centi_c"]==4000


@pytest.mark.asyncio
@pytest.mark.parametrize("keep",[True,False])
async def test_group_pump_optional_keep_clear_and_edit_identity(hass,manager,keep):
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    pump=registry_entity(hass,"switch","pump")
    r=await open_graph(manager,parent);r=await add_group(manager,r,pump=pump,pump_start_delay_s=5,postrun_s=60)
    await menu(manager,r,"save_graph");gid=old.data["draft"]["groups"][0]["group_id"]
    r=await open_graph(manager,parent);r=await menu(manager,r,"edit_group")
    r=await manager.async_configure(r["flow_id"],{"group_id":gid})
    vals={"name":"Edited group","emitter":"radiator","minimum_supply_temperature":20,
          "maximum_supply_temperature":70,"mixing_kind":"none","pump_start_delay_s":5 if keep else 0,"postrun_s":60 if keep else 0}
    if keep: vals["pump"]=pump
    r=await manager.async_configure(r["flow_id"],vals);await menu(manager,r,"save_graph")
    actual=old.data["draft"]["groups"][0]
    assert actual["group_id"]==gid and actual["name"]=="Edited group"
    assert (actual["pump"] is not None) is keep


@pytest.mark.asyncio
async def test_invalid_tpi_and_cross_room_existing_output_never_change_saved_graph(hass,manager):
    a=room(hass);b=room(hass,room_id="b1b2b3b4",suffix="second");parent=entry(hass,room=a)
    hass.config_entries.async_add_subentry(parent,ConfigSubentry(data=b.as_dict(),subentry_type="zone",title=b.name,unique_id=b.room_id))
    old=await create_central(manager,parent);before=deepcopy(dict(old.data))
    r=await open_graph(manager,parent);r=await add_group(manager,r)
    bad=await add_actuator(manager,r,a.room_id,b.actuators[0].entity_id)
    assert bad["errors"]["base"]=="output_has_multiple_owners" and dict(old.data)==before
    # Abandon staged flow rather than force an invalid output.
    manager.async_abort(bad["flow_id"])


@pytest.mark.asyncio
async def test_duplicate_graph_and_pump_outputs_blocked(hass,manager):
    parent,binding,old=await seed_graph(hass,manager,profile="binary_valve")
    before=deepcopy(dict(old.data));output=before["draft"]["actuators"][0]["output"]["entity_id"]
    r=await open_graph(manager,parent)
    bad=await add_group(manager,r,name="Conflicting pump",pump=output)
    assert bad["errors"]["base"]=="output_has_multiple_owners"
    assert dict(old.data)==before


@pytest.mark.asyncio
async def test_native_room_delete_cascades_only_its_draft_and_reloads_once(hass,manager,monkeypatch):
    parent,binding,old=await seed_graph(hass,manager)
    before=deepcopy(dict(old.data));zone=next(s for s in parent.subentries.values() if s.subentry_type=="zone")
    reload=AsyncMock(return_value=True);monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    unsub=parent.add_update_listener(_async_options_updated)
    try:
        assert hass.config_entries.async_remove_subentry(parent,zone.subentry_id)
        await hass.async_block_till_done()
        assert old.data["draft"]["actuators"]==[]
        assert old.data["draft"]["groups"]==before["draft"]["groups"]
        assert old.data["draft"]["central"]==before["draft"]["central"]
        assert old.data["last_room_cascade"]==before["draft"]["actuators"]
        reload.assert_awaited_once_with(parent.entry_id)
    finally:
        unsub()


@pytest.mark.asyncio
async def test_graph_stale_after_room_delete_or_parallel_edit_cannot_resurrect(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    r=await open_graph(manager,parent)
    zone=next(s for s in parent.subentries.values() if s.subentry_type=="zone")
    hass.config_entries.async_remove_subentry(parent,zone.subentry_id)
    assert reconcile_removed_rooms(hass,parent)
    blocked=await menu(manager,r,"save_graph")
    assert blocked["type"]=="abort" and blocked["reason"]=="graph_changed"
    assert old.data["draft"]["actuators"]==[]


@pytest.mark.asyncio
async def test_missing_entity_at_final_save_is_fail_closed_and_cancelable(hass,manager):
    parent,binding,old=await seed_graph(hass,manager,profile="binary_valve")
    before=deepcopy(dict(old.data));r=await open_graph(manager,parent)
    er.async_get(hass).async_remove(before["draft"]["actuators"][0]["output"]["entity_id"])
    bad=await menu(manager,r,"save_graph")
    assert bad["step_id"]=="graph_error" and bad["errors"]["base"]=="binding_missing"
    assert dict(old.data)==before


@pytest.mark.asyncio
async def test_registry_rename_resolves_stable_identity_without_new_owner(hass,manager):
    parent,binding,old=await seed_graph(hass,manager,profile="binary_valve")
    output=old.data["draft"]["actuators"][0]["output"]
    er.async_get(hass).async_update_entity(output["entity_id"],new_entity_id="switch.renamed_graph")
    r=await open_graph(manager,parent);await menu(manager,r,"save_graph")
    assert old.data["draft"]["actuators"][0]["output"]["entity_id"]=="switch.renamed_graph"
    assert old.data["draft"]["actuators"][0]["output"]["unique_id"]==output["unique_id"]


@pytest.mark.asyncio
async def test_full_heating_native_delete_keeps_room_and_existing_wire_exact(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    runtime=ShadowRuntime(hass,parent,[binding]);before=await async_build_configuration(runtime)
    assert hass.config_entries.async_remove_subentry(parent,old.subentry_id)
    assert len(parent.subentries)==1
    assert await async_build_configuration(runtime)==before
    assert runtime.enabled is False and runtime.transport_ready is False


@pytest.mark.asyncio
async def test_output_cannot_be_stolen_by_prospective_room_binding(hass,manager):
    free=registry_entity(hass,"climate","free_graph_trv")
    parent,a,old=await seed_graph(hass,manager,output=free)
    b=room(hass,room_id="b1b2b3b4",suffix="prospective")
    before=deepcopy(dict(old.data))
    flow=ZoneSubentryFlow();flow.hass=hass;flow.handler=(parent.entry_id,"zone");flow.context={"source":"user"}
    form=await flow.async_step_user()
    result=await flow.async_step_user(form["data_schema"]({"room_id":b.room_id,"name":"Prospective",
        "temperature_entity":b.temperature.entity_id,"actuator_entities":[free],"base_temperature":21,
        "minimum_target_temperature":5,"maximum_target_temperature":35,"maximum_age_ms":120000}))
    assert result["type"]=="form" and result["errors"]["base"]=="duplicate_actuator"
    assert dict(old.data)==before


@pytest.mark.asyncio
async def test_active_guard_rechecked_on_graph_save(hass,manager):
    parent,binding,old=await seed_graph(hass,manager);before=deepcopy(dict(old.data))
    r=await open_graph(manager,parent)
    hass.config_entries.async_update_entry(parent,options={**parent.options,"shadow_enabled":True})
    blocked=await menu(manager,r,"save_graph")
    assert blocked["reason"]=="disable_runtime_before_draft" and dict(old.data)==before

@pytest.mark.asyncio
async def test_invalid_tpi_cycle_is_native_error_atomic(hass,manager):
    parent,binding,old=await seed_graph(hass,manager,profile="binary_valve")
    before=deepcopy(dict(old.data));a=before["draft"]["actuators"][0]
    r=await open_graph(manager,parent);r=await menu(manager,r,"edit_actuator")
    r=await manager.async_configure(r["flow_id"],{"actuator_id":a["actuator_id"]})
    r=await manager.async_configure(r["flow_id"],{"room_id":binding.room_id,"group_id":a["group_id"],"profile":"binary_valve"})
    bad=await manager.async_configure(r["flow_id"],{"output":a["output"]["entity_id"],
        **a["settings"],"minimum_on_s":60})
    assert bad["errors"]["base"]=="invalid_tpi_travel_or_minimum_times"
    assert dict(old.data)==before


@pytest.mark.asyncio
async def test_parallel_central_edit_invalidates_open_graph_save(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    graph=await open_graph(manager,parent)
    other=await manager.async_init((parent.entry_id,"heating"),
        context={"source":"reconfigure","subentry_id":old.subentry_id})
    await manager.async_configure(other["flow_id"],form_values(maximum_supply_temperature=80))
    after=deepcopy(dict(old.data))
    blocked=await menu(manager,graph,"save_graph")
    assert blocked["reason"]=="graph_changed" and dict(old.data)==after


@pytest.mark.asyncio
async def test_cross_controller_graph_outputs_are_not_reclaimed(hass,manager):
    free=registry_entity(hass,"climate","claimed_by_other_graph")
    parent,binding,old=await seed_graph(hass,manager,output=free)
    other_binding=room(hass,room_id="b1b2b3b4",suffix="other_controller")
    other=entry(hass,room=other_binding)
    duplicate=deepcopy(dict(old.data))
    duplicate["draft"]["actuators"][0]["room_id"]=other_binding.room_id
    hass.config_entries.async_add_subentry(other,ConfigSubentry(data=duplicate,
        subentry_type="heating",title="Other desired graph",unique_id="central_heating"))
    before=deepcopy(dict(old.data))
    r=await open_graph(manager,parent)
    bad=await menu(manager,r,"save_graph")
    assert bad["errors"]["base"]=="output_has_multiple_owners" and dict(old.data)==before


@pytest.mark.asyncio
async def test_actuator_moves_groups_without_changing_its_identity(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    aid=old.data["draft"]["actuators"][0]["actuator_id"]
    r=await open_graph(manager,parent);r=await add_group(manager,r,name="Second")
    await menu(manager,r,"save_graph")
    second=next(g for g in old.data["draft"]["groups"] if g["name"]=="Second")
    actuator=old.data["draft"]["actuators"][0]
    r=await open_graph(manager,parent);r=await menu(manager,r,"edit_actuator")
    r=await manager.async_configure(r["flow_id"],{"actuator_id":aid})
    r=await manager.async_configure(r["flow_id"],{"room_id":binding.room_id,
        "group_id":second["group_id"],"profile":"trv_room_setpoint"})
    r=await manager.async_configure(r["flow_id"],{"output":actuator["output"]["entity_id"]})
    await menu(manager,r,"save_graph")
    actual=old.data["draft"]["actuators"][0]
    assert actual["actuator_id"]==aid and actual["group_id"]==second["group_id"]


@pytest.mark.asyncio
async def test_deleted_room_without_loaded_listener_is_reconciled_on_next_setup_boundary(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    zone=next(s for s in parent.subentries.values() if s.subentry_type=="zone")
    hass.config_entries.async_remove_subentry(parent,zone.subentry_id)
    # Same synchronous native helper used by actual setup, not an always-on watcher.
    assert reconcile_removed_rooms(hass,parent)
    assert reconcile_removed_rooms(hass,parent) is False
    assert old.data["draft"]["actuators"]==[]
    await hass.async_stop(force=True)
    second=HomeAssistant(hass.config.config_dir);second.config_entries=ConfigEntries(second,{})
    try:
        await second.config_entries.async_initialize()
        restored=second.config_entries.async_get_entry(parent.entry_id).subentries[old.subentry_id]
        assert restored.data["draft"]["actuators"]==[] and len(restored.data["last_room_cascade"])==1
    finally:
        await second.async_stop(force=True)


@pytest.mark.asyncio
async def test_offline_selected_output_can_remain_draft_but_disabled_registry_is_rejected(hass,manager):
    parent,binding,old=await seed_graph(hass,manager,profile="binary_valve")
    output=old.data["draft"]["actuators"][0]["output"]["entity_id"]
    hass.states.async_set(output,"unavailable")
    r=await open_graph(manager,parent);await menu(manager,r,"save_graph")
    assert old.data["status"]=="draft_not_applied"
    before=deepcopy(dict(old.data))
    er.async_get(hass).async_update_entity(output,disabled_by=er.RegistryEntryDisabler.USER)
    r=await open_graph(manager,parent);bad=await menu(manager,r,"save_graph")
    assert bad["errors"]["base"]=="binding_missing" and dict(old.data)==before


@pytest.mark.asyncio
async def test_source_temperature_role_is_revalidated_not_just_entity_domain(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    source=registry_entity(hass,"sensor","actually_battery")
    hass.states.async_set(source,"50",{"device_class":"battery","unit_of_measurement":"%"})
    before=deepcopy(dict(old.data))
    r=await open_graph(manager,parent)
    r=await add_group(manager,r,emitter="floor",maximum_supply_temperature=40,mixing_kind="analog_0_10v")
    bad=await manager.async_configure(r["flow_id"],{"supply_sensor":source,"travel_time_s":120,
        "analog_output":registry_entity(hass,"number","mix")})
    assert bad["errors"]["base"]=="not_temperature" and dict(old.data)==before


@pytest.mark.asyncio
async def test_no_room_graph_does_not_offer_or_create_dangling_actuator(hass,manager):
    parent=entry(hass);old=await create_central(manager,parent)
    r=await open_graph(manager,parent);r=await add_group(manager,r)
    assert "add_actuator" not in r["menu_options"]
    await menu(manager,r,"save_graph")
    assert len(old.data["draft"]["groups"])==1 and old.data["draft"]["actuators"]==[]


@pytest.mark.asyncio
async def test_native_graph_english_resources_make_unimplemented_profiles_explicit(hass,monkeypatch):
    from pathlib import Path
    from homeassistant import loader
    from homeassistant.helpers import translation
    component=Path(__file__).resolve().parents[1]/"config/custom_components/open_thermostat"
    import json
    loader.async_setup(hass)
    integration=loader.Integration(hass,"custom_components.open_thermostat",component,
        json.loads((component/"manifest.json").read_text()),top_level_files={p.name for p in component.iterdir()})
    monkeypatch.setattr(translation,"async_get_integrations",AsyncMock(return_value={"open_thermostat":integration}))
    resources=await translation.async_get_translations(hass,"en","config_subentries",{"open_thermostat"})
    pre="component.open_thermostat.config_subentries.heating.step."
    assert resources[pre+"graph.menu_options.save_graph"]=="Save desired graph (not applied)"
    assert "homing" in resources[pre+"group.data_description.mixing_kind"]
    assert "NOT implemented" in resources[pre+"group.data_description.mixing_kind"]
    assert "same desired output owner" in resources[pre+"actuator_details.data_description.output"].lower()

@pytest.mark.asyncio
async def test_stale_central_form_cannot_overwrite_new_graph(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    central=await manager.async_init((parent.entry_id,"heating"),
        context={"source":"reconfigure","subentry_id":old.subentry_id})
    r=await open_graph(manager,parent);r=await add_group(manager,r,name="Concurrent new group")
    await menu(manager,r,"save_graph")
    before=deepcopy(dict(old.data))
    blocked=await manager.async_configure(central["flow_id"],form_values())
    assert blocked["reason"]=="graph_changed" and dict(old.data)==before


@pytest.mark.asyncio
async def test_renamed_optional_pump_is_shown_and_preserved_by_identity(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    pump=registry_entity(hass,"switch","old_pump")
    r=await open_graph(manager,parent);r=await add_group(manager,r,pump=pump)
    await menu(manager,r,"save_graph")
    group=old.data["draft"]["groups"][0]
    er.async_get(hass).async_update_entity(pump,new_entity_id="switch.renamed_pump")
    r=await open_graph(manager,parent);r=await menu(manager,r,"edit_group")
    r=await manager.async_configure(r["flow_id"],{"group_id":group["group_id"]})
    marker=next(k for k in r["data_schema"].schema if str(k)=="pump")
    assert marker.description["suggested_value"]=="switch.renamed_pump"
    values={"name":group["name"],"emitter":"radiator","minimum_supply_temperature":20,
        "maximum_supply_temperature":70,"pump":"switch.renamed_pump",
        "pump_start_delay_s":0,"postrun_s":0,"mixing_kind":"none"}
    r=await manager.async_configure(r["flow_id"],values);await menu(manager,r,"save_graph")
    assert old.data["draft"]["groups"][0]["pump"]["unique_id"]==group["pump"]["unique_id"]


@pytest.mark.asyncio
async def test_native_group_invalid_unmixed_floor_preserves_draft(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    before=deepcopy(dict(old.data))
    r=await open_graph(manager,parent)
    bad=await add_group(manager,r,emitter="floor",maximum_supply_temperature=40)
    assert bad["errors"]["base"]=="floor_requires_mixing_or_shared_safe_limit"
    assert dict(old.data)==before


@pytest.mark.asyncio
async def test_native_mixer_edit_interface_and_explicit_clear(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    source=registry_entity(hass,"sensor","edit_supply")
    r=await open_graph(manager,parent);r=await add_group(manager,r,mixing_kind="three_point")
    r=await manager.async_configure(r["flow_id"],{"supply_sensor":source,"travel_time_s":120,
        "open_output":registry_entity(hass,"switch","edit_open"),
        "close_output":registry_entity(hass,"switch","edit_close")})
    await menu(manager,r,"save_graph")
    gid=old.data["draft"]["groups"][0]["group_id"]
    central=deepcopy(old.data["draft"]["central"])
    for kind in ["analog_0_10v","none"]:
        r=await open_graph(manager,parent);r=await menu(manager,r,"edit_group")
        r=await manager.async_configure(r["flow_id"],{"group_id":gid})
        r=await manager.async_configure(r["flow_id"],{"name":"Edited mixer","emitter":"radiator",
            "minimum_supply_temperature":20,"maximum_supply_temperature":70,
            "pump_start_delay_s":0,"postrun_s":0,"mixing_kind":kind})
        if kind!="none":
            r=await manager.async_configure(r["flow_id"],{"supply_sensor":source,"travel_time_s":120,
                "analog_output":registry_entity(hass,"number","edit_analog")})
        await menu(manager,r,"save_graph")
        mix=old.data["draft"]["groups"][0]["mixing"]
        assert (mix is None) is (kind=="none")
        if mix: assert mix["kind"]==kind and len(mix["outputs"])==1
        assert old.data["draft"]["central"]==central


@pytest.mark.asyncio
async def test_native_profile_switch_does_not_keep_incompatible_output_or_settings(hass,manager):
    parent,binding,old=await seed_graph(hass,manager)
    a=deepcopy(old.data["draft"]["actuators"][0])
    r=await open_graph(manager,parent);r=await menu(manager,r,"edit_actuator")
    r=await manager.async_configure(r["flow_id"],{"actuator_id":a["actuator_id"]})
    r=await manager.async_configure(r["flow_id"],{"room_id":binding.room_id,"group_id":a["group_id"],"profile":"binary_valve"})
    marker=next(k for k in r["data_schema"].schema if str(k)=="output")
    assert getattr(marker,"default",None) != a["output"]["entity_id"]
    r=await manager.async_configure(r["flow_id"],{"output":registry_entity(hass,"switch","new_binary"),
        "deenergized_position":"normally_open","control":"hysteresis","travel_time_s":10,
        "minimum_on_s":30,"minimum_off_s":30})
    await menu(manager,r,"save_graph")
    actual=old.data["draft"]["actuators"][0]
    assert actual["actuator_id"]==a["actuator_id"] and actual["profile"]=="binary_valve"
    assert actual["settings"]["cycle_s"] is None and actual["output"]["entity_id"].startswith("switch.")

@pytest.mark.asyncio
async def test_actual_runtime_still_running_blocks_editor_even_if_saved_option_is_off(hass,manager):
    from types import SimpleNamespace
    from custom_components.open_thermostat.const import DOMAIN
    parent=entry(hass)
    hass.data.setdefault(DOMAIN,{})[parent.entry_id]={"v1_runtime":SimpleNamespace(enabled=True)}
    result=await manager.async_init((parent.entry_id,"heating"),context={"source":"user"})
    assert result["reason"]=="disable_runtime_before_draft"
    assert not parent.subentries

@pytest.mark.asyncio
async def test_trv_position_alias_on_same_device_cannot_get_second_owner(hass,manager):
    from homeassistant.helpers import device_registry as dr
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    position=registry_entity(hass,"number","same_trv_position")
    device=dr.async_get(hass).async_get_or_create(config_entry_id=parent.entry_id,
        identifiers={("graph_fixture","one_trv")})
    registry=er.async_get(hass)
    registry.async_update_entity(binding.actuators[0].entity_id,device_id=device.id)
    registry.async_update_entity(position,device_id=device.id)
    before=deepcopy(dict(old.data))
    r=await open_graph(manager,parent);r=await add_group(manager,r)
    bad=await add_actuator(manager,r,binding.room_id,position,"proportional_valve",
        minimum_percent=0,maximum_percent=100,travel_time_s=60)
    assert bad["errors"]["base"]=="output_has_multiple_owners" and dict(old.data)==before


@pytest.mark.asyncio
async def test_distinct_relay_controller_channels_can_share_device_not_output(hass,manager):
    from homeassistant.helpers import device_registry as dr
    binding=room(hass);parent=entry(hass,room=binding);old=await create_central(manager,parent)
    outputs=[registry_entity(hass,"switch","relay_open"),registry_entity(hass,"switch","relay_close")]
    device=dr.async_get(hass).async_get_or_create(config_entry_id=parent.entry_id,
        identifiers={("graph_fixture","two_relay_controller")})
    for eid in outputs:
        er.async_get(hass).async_update_entity(eid,device_id=device.id)
    r=await open_graph(manager,parent);r=await add_group(manager,r,mixing_kind="three_point")
    r=await manager.async_configure(r["flow_id"],{"supply_sensor":registry_entity(hass,"sensor","relay_supply"),
        "travel_time_s":120,"open_output":outputs[0],"close_output":outputs[1]})
    await menu(manager,r,"save_graph")
    assert len(old.data["draft"]["groups"][0]["mixing"]["outputs"])==2
    assert old.data["status"]=="draft_not_applied"
