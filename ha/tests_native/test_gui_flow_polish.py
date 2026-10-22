"""Actual native HA forms and config persistence, not a replacement frontend."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat.v1_config_flow import reference
from test_v1_native import entry,room
from test_v1_heating_graph_gui import manager,create_central,open_graph,menu
from test_v1_heating_draft import form_values
from test_graph_review_flow import native_graph

def suggested(result,key):
    marker=next(k for k in result["data_schema"].schema if str(k)==key)
    return (marker.description or {}).get("suggested_value")

@pytest.mark.asyncio
async def test_group_error_retains_all_submitted_values_without_saving(hass,manager):
    parent=entry(hass,room=room(hass));old=await create_central(manager,parent)
    original=deepcopy(dict(old.data));r=await open_graph(manager,parent)
    r=await menu(manager,r,"add_group")
    values=dict(name="Upstairs trial",emitter="radiator",minimum_supply_temperature=60,
                maximum_supply_temperature=55,pump_start_delay_s=0,postrun_s=0,mixing_kind="none")
    r=await manager.async_configure(r["flow_id"],values)
    assert r["errors"]["base"]=="minimum_must_be_below_maximum"
    assert {k:suggested(r,k) for k in values}==values
    assert dict(old.data)==original

@pytest.mark.asyncio
async def test_central_error_retains_user_draft_and_cancel_does_not_save(hass,manager):
    parent=entry(hass,room=room(hass));old=await create_central(manager,parent)
    original=deepcopy(dict(old.data))
    r=await manager.async_init((parent.entry_id,"heating"),context={"source":"reconfigure","subentry_id":old.subentry_id})
    values=form_values(minimum_supply_temperature=80,maximum_supply_temperature=70,curve_0=22)
    r=await manager.async_configure(r["flow_id"],values)
    assert r["errors"]
    assert {k:suggested(r,k) for k in values}==values
    manager.async_abort(r["flow_id"])
    assert dict(old.data)==original

@pytest.mark.asyncio
async def test_room_invalid_bounds_retain_name_entities_and_option_clear(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);old=next(iter(parent.subentries.values()))
    original=deepcopy(dict(old.data))
    r=await manager.async_init((parent.entry_id,"zone"),context={"source":"reconfigure","subentry_id":old.subentry_id})
    values=r["data_schema"]({"name":"Room being edited","temperature_entity":binding.temperature.entity_id,
        "actuator_entities":[binding.actuators[0].entity_id],"minimum_target_temperature":24,
        "maximum_target_temperature":22,"base_temperature":21})
    r=await manager.async_configure(r["flow_id"],values)
    assert r["errors"]["base"]=="invalid_target_range"
    assert {k:suggested(r,k) for k in values}==values
    assert dict(old.data)==original

@pytest.mark.asyncio
@pytest.mark.parametrize("action",["save_program","cancel_program"])
async def test_week_editor_preserves_comfort_and_context_bindings(hass,manager,action):
    registry=er.async_get(hass)
    window=registry.async_get_or_create("binary_sensor","gui_fixture","window")
    presence=registry.async_get_or_create("person","gui_fixture","presence")
    binding=replace(room(hass),comfort=dict(away_centi_c=1600,frost_centi_c=500,temporary_ms=420000),
                    window=reference(hass,window.entity_id),presence=reference(hass,presence.entity_id))
    parent=entry(hass,room=binding);old=next(iter(parent.subentries.values()));original=deepcopy(dict(old.data))
    r=await manager.async_init((parent.entry_id,"zone"),context={"source":"reconfigure","subentry_id":old.subentry_id})
    data=r["data_schema"]({"name":binding.name,"temperature_entity":binding.temperature.entity_id,
                          "actuator_entities":[binding.actuators[0].entity_id],"program_action":"edit_week",
                          "window_entity":window.entity_id,"presence_entity":presence.entity_id})
    r=await manager.async_configure(r["flow_id"],data)
    assert r["step_id"]=="program"
    r=await menu(manager,r,"add_block")
    r=await manager.async_configure(r["flow_id"],dict(days=["monday"],start_time="07:00:00",
        end_time="09:00:00",end_at_midnight=False,temperature=22))
    assert r["step_id"]=="program" and dict(old.data)==original
    r=await menu(manager,r,action)
    if action=="cancel_program":
        assert r["reason"]=="program_cancelled" and dict(old.data)==original
    else:
        assert r["reason"]=="reconfigure_successful"
        for key in ("comfort","window","presence"):
            assert old.data.get(key)==original[key],key
        assert old.data["week_program"]["monday"][0]["target_centi_c"]==2200

@pytest.mark.asyncio
async def test_native_status_refresh_only_reads_pending_and_verified_tuple(native_graph):
    n=native_graph;await n.stage();f=n.flow();await f.async_step_graph_review()
    result=await f.async_step_graph_review({"confirm_apply":True})
    assert result["description_placeholders"]["verified"]=="False"
    before=len(n.publications)
    refreshed=await f.async_step_graph_status({"status_action":"refresh"})
    assert refreshed["type"]=="form" and refreshed["description_placeholders"]["verified"]=="False"
    assert len(n.publications)==before
    await n.drain()
    writes=(await n.peer.request("status"))["writes"]
    refreshed=await f.async_step_graph_status({"status_action":"refresh"})
    assert refreshed["description_placeholders"]["verified"]=="True"
    assert (await n.peer.request("status"))["writes"]==writes==1
    assert not n.publications
    closed=await f.async_step_graph_status({"status_action":"close"})
    assert closed["reason"]=="graph_review_complete"
    assert n.runtime.transport_ready is False

def test_english_status_actions_have_visible_labels_and_no_refresh_write_claim():
    root=Path(__file__).parents[1]/"config/custom_components/open_thermostat"
    for name in ("strings.json","translations/en.json"):
        doc=json.loads((root/name).read_text())
        assert doc["options"]["step"]["graph_status"]["data"]["status_action"]
        options=doc["selector"]["graph_status_action"]["options"]
        assert options["refresh"]=="Refresh status" and options["close"]=="Close status"

@pytest.mark.asyncio
async def test_cleared_optional_context_is_not_reinserted_after_validation_error(hass,manager):
    registry=er.async_get(hass)
    w=registry.async_get_or_create("binary_sensor","gui_fixture","clear_window")
    binding=replace(room(hass),comfort=dict(away_centi_c=1600,frost_centi_c=500,temporary_ms=420000),
                    window=reference(hass,w.entity_id))
    parent=entry(hass,room=binding);old=next(iter(parent.subentries.values()))
    original=deepcopy(dict(old.data))
    r=await manager.async_init((parent.entry_id,"zone"),context={"source":"reconfigure","subentry_id":old.subentry_id})
    assert suggested(r,"window_entity")==w.entity_id
    data=r["data_schema"]({"name":"Keep entered name","temperature_entity":binding.temperature.entity_id,
        "actuator_entities":[binding.actuators[0].entity_id],"minimum_target_temperature":24,
        "maximum_target_temperature":22})
    assert "window_entity" not in data
    r=await manager.async_configure(r["flow_id"],data)
    assert r["errors"] and suggested(r,"window_entity") is None
    assert suggested(r,"name")=="Keep entered name"
    assert dict(old.data)==original

@pytest.mark.asyncio
async def test_week_save_revalidates_missing_context_instead_of_silently_dropping_it(hass,manager):
    registry=er.async_get(hass)
    w=registry.async_get_or_create("binary_sensor","gui_fixture","lost_window")
    binding=replace(room(hass),comfort=dict(away_centi_c=1600,frost_centi_c=500,temporary_ms=420000),
                    window=reference(hass,w.entity_id))
    parent=entry(hass,room=binding);old=next(iter(parent.subentries.values()));original=deepcopy(dict(old.data))
    r=await manager.async_init((parent.entry_id,"zone"),context={"source":"reconfigure","subentry_id":old.subentry_id})
    data=r["data_schema"]({"name":binding.name,"temperature_entity":binding.temperature.entity_id,
        "actuator_entities":[binding.actuators[0].entity_id],"program_action":"edit_week","window_entity":w.entity_id})
    r=await manager.async_configure(r["flow_id"],data)
    registry.async_remove(w.entity_id)
    r=await menu(manager,r,"save_program")
    assert r["step_id"]=="program_save_error" and dict(old.data)==original

@pytest.mark.asyncio
async def test_overlapping_block_error_preserves_days_time_and_target(hass,manager):
    binding=room(hass);parent=entry(hass,room=binding);old=next(iter(parent.subentries.values()))
    original=deepcopy(dict(old.data))
    r=await manager.async_init((parent.entry_id,"zone"),context={"source":"reconfigure","subentry_id":old.subentry_id})
    r=await manager.async_configure(r["flow_id"],r["data_schema"]({"name":binding.name,
        "temperature_entity":binding.temperature.entity_id,"actuator_entities":[binding.actuators[0].entity_id],
        "program_action":"edit_week"}))
    r=await menu(manager,r,"add_block")
    await manager.async_configure(r["flow_id"],dict(days=["monday"],start_time="07:00:00",
        end_time="09:00:00",end_at_midnight=False,temperature=22))
    r=await menu(manager,r,"add_block")
    values=dict(days=["monday","tuesday"],start_time="08:00:00",end_time="10:00:00",
        end_at_midnight=False,temperature=23)
    r=await manager.async_configure(r["flow_id"],values)
    assert r["errors"]["base"]=="program_overlap"
    assert {k:suggested(r,k) for k in values}==values
    assert dict(old.data)==original
