"""Real HA manager/schema + official config Store + existing finite compiler."""
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.v1_config_flow import ZoneSubentryFlow
from custom_components.open_thermostat.v1_model import RoomBinding
from custom_components.open_thermostat.v1_mqtt import async_build_configuration, NativeShadowConnection
from custom_components.open_thermostat.v1_program import normalize_program, change_block, native_week
from custom_components.open_thermostat.schedule_compiler import compile_week, WEEKDAYS
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_wire import canonical

from test_v1_native import room, entry, reference
from test_v1_room_target_bounds import inputs, flow

def program(day="monday", start=7*3600, end=8*3600, target=2200):
    return normalize_program({day: [{"start": start, "end": end, "target_centi_c": target}]})

def reinputs(binding, **updates):
    data = inputs(binding, **updates)
    data.pop("room_id")
    return data

async def editor(hass, binding=None):
    binding = binding or room(hass)
    parent = entry(hass, room=binding)
    old = next(iter(parent.subentries.values()))
    item = flow(hass, parent, old)
    form = await item.async_step_reconfigure()
    result = await item.async_step_reconfigure(form["data_schema"](reinputs(
        binding, program_action="edit_week")))
    assert result["type"] == "menu" and result["step_id"] == "program"
    return item, parent, old

async def add(item, **updates):
    form = await item.async_step_add_block()
    data = {"days": ["monday"], "start_time": "07:00:00", "end_time": "08:00:00",
            "end_at_midnight": False, "temperature": 22, **updates}
    return await item.async_step_block(form["data_schema"](data))

@pytest.mark.asyncio
async def test_editor_add_edit_delete_atomic_draft_and_store_roundtrip(hass):
    item,parent,old = await editor(hass)
    before = deepcopy(dict(old.data))
    assert (await add(item, days=["monday","tuesday"]))["type"] == "menu"
    assert dict(old.data) == before  # No partial persistence while editing.
    choose = await item.async_step_edit_block()
    validated = choose["data_schema"]({"block": "monday:0"})
    form = await item.async_step_edit_block(validated)
    assert form["data_schema"]({"days":["monday"],"start_time":"09:00:00",
           "end_time":"10:00:00","temperature":21})["end_at_midnight"] is False
    await item.async_step_block(form["data_schema"]({"days":["monday"],"start_time":"09:00:00",
               "end_time":"10:00:00","temperature":21}))
    select = await item.async_step_delete_block()
    await item.async_step_delete_block(select["data_schema"]({"block":"tuesday:0"}))
    assert dict(old.data) == before
    result = await item.async_step_save_program()
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    saved = RoomBinding.from_dict(dict(old.data))
    assert saved.week_program["monday"] == [{"start":32400,"end":36000,"target_centi_c":2100}]
    assert saved.week_program["tuesday"] == []
    assert saved.minimum_target_centi_c == 1600 and saved.maximum_target_centi_c == 2300
    # Official HA config Store flush/reload; no private file edits.
    await hass.async_stop(force=True)
    second = HomeAssistant(hass.config.config_dir)
    second.config_entries = ConfigEntries(second,{})
    try:
        await second.config_entries.async_initialize()
        restored = second.config_entries.async_get_entry(parent.entry_id).subentries[old.subentry_id]
        assert dict(restored.data) == dict(old.data)
    finally:
        await second.async_stop(force=True)

@pytest.mark.asyncio
async def test_real_subentry_manager_performs_menu_schema_and_persistence(hass, monkeypatch):
    binding=room(hass);parent=entry(hass)
    # Resolve only the already loaded integration handler at its import boundary.
    # Actual ConfigSubentryFlowManager validates forms and finishes persistence.
    monkeypatch.setattr(config_entries,"_async_get_flow_handler",AsyncMock(return_value=OpenThermostatConfigFlow))
    manager=hass.config_entries.subentries
    result=await manager.async_init((parent.entry_id,"zone"),context={"source":"user"})
    result=await manager.async_configure(result["flow_id"],inputs(binding,program_action="edit_week"))
    assert result["type"]=="menu"
    result=await manager.async_configure(result["flow_id"],{"next_step_id":"add_block"})
    assert result["step_id"]=="block"
    result=await manager.async_configure(result["flow_id"],{
        "days":["friday"],"start_time":"22:00:00","end_time":"00:00:00",
        "end_at_midnight":True,"temperature":22})
    result=await manager.async_configure(result["flow_id"],{"next_step_id":"save_program"})
    assert result["type"]=="create_entry"
    assert len(parent.subentries)==1
    saved=next(iter(parent.subentries.values()))
    assert saved.data["week_program"]["friday"]==[{"start":79200,"end":86400,"target_centi_c":2200}]
    assert saved.data["minimum_target_centi_c"]==1600

@pytest.mark.asyncio
async def test_program_reconfigure_manager_cancel_leaves_original(hass,monkeypatch):
    binding=replace(room(hass),week_program=program())
    parent=entry(hass,room=binding);old=next(iter(parent.subentries.values()));before=deepcopy(dict(old.data))
    monkeypatch.setattr(config_entries,"_async_get_flow_handler",AsyncMock(return_value=OpenThermostatConfigFlow))
    manager=hass.config_entries.subentries
    result=await manager.async_init((parent.entry_id,"zone"),context={"source":"reconfigure","subentry_id":old.subentry_id})
    result=await manager.async_configure(result["flow_id"],reinputs(binding,program_action="edit_week"))
    result=await manager.async_configure(result["flow_id"],{"next_step_id":"cancel_program"})
    assert result["type"]=="abort" and result["reason"]=="program_cancelled"
    assert dict(old.data)==before

@pytest.mark.asyncio
async def test_invalid_overlap_and_room_target_leave_draft_and_persistence(hass):
    item,parent,old=await editor(hass);await add(item)
    before=deepcopy(item._program_week);stored=dict(old.data)
    for updates,error in [({"start_time":"07:30:00"},"program_overlap"),
                          ({"start_time":"23:00:00","end_time":"01:00:00"},"invalid_program_time"),
                          ({"temperature":24},"invalid_target_range")]:
        # Direct callback additionally defends against non-schema callers.
        await item.async_step_add_block()
        result=await item.async_step_block({"days":["monday"],"start_time":"07:00:00",
                     "end_time":"08:00:00","temperature":22,**updates})
        assert result["errors"]["base"]==error
        assert item._program_week==before and dict(old.data)==stored

@pytest.mark.asyncio
async def test_optional_helper_conflict_and_explicit_source_switch(hass):
    binding=replace(room(hass),week_program=program())
    parent=entry(hass,room=binding);old=next(iter(parent.subentries.values()))
    reg=er.async_get(hass).async_get_or_create("schedule","schedule","external_week")
    item=flow(hass,parent,old)
    result=await item.async_step_reconfigure(inputs(binding,schedule_entity=reg.entity_id))
    assert result["errors"]["base"]=="program_source_conflict"
    assert old.data["week_program"]==binding.week_program
    result=await item.async_step_reconfigure(inputs(binding,schedule_entity=reg.entity_id,program_action="remove_week"))
    assert result["type"]=="abort" and "week_program" not in old.data
    assert old.data["schedule"]["entity_id"]==reg.entity_id
    conflict=flow(hass,parent,old)
    result=await conflict.async_step_reconfigure(inputs(binding,schedule_entity=reg.entity_id,program_action="edit_week"))
    assert result["errors"]["base"]=="program_source_conflict"
    # Explicitly clear helper in the actual schema, then select local editing.
    form=await conflict.async_step_reconfigure()
    result=await conflict.async_step_reconfigure(form["data_schema"](reinputs(binding,program_action="edit_week")))
    assert result["type"]=="menu" and conflict._program_room.schedule is None

@pytest.mark.asyncio
async def test_draft_conflicting_room_change_or_removal_aborts(hass):
    item,parent,old=await editor(hass)
    hass.config_entries.async_update_subentry(parent,old,title="Concurrent edit",data={**old.data,"name":"Concurrent edit"})
    result=await item.async_step_save_program()
    assert result["reason"]=="program_changed"
    assert old.data["name"]=="Concurrent edit"

@pytest.mark.asyncio
async def test_room_limit_rechecked_at_finish(hass):
    binding=room(hass)
    parent=entry(hass)
    item=flow(hass,parent)
    await item.async_step_user(inputs(binding,program_action="edit_week"))
    from homeassistant.config_entries import ConfigSubentry
    from types import MappingProxyType
    for i in range(8):
        other=room(hass,f"{i:08x}",f"room{i}")
        hass.config_entries.async_add_subentry(parent,ConfigSubentry(
            data=MappingProxyType(other.as_dict()),subentry_type="zone",title=other.name,unique_id=other.room_id))
    result=await item.async_step_save_program()
    assert result["reason"]=="room_limit" and len(parent.subentries)==8

@pytest.mark.parametrize("raw", [
    {"monday":[{"start":True,"end":3600,"target_centi_c":2100}]},
    {"monday":[{"start":0,"end":3600,"target_centi_c":float("nan")}]},
    {"monday":[{"start":0,"end":3600,"target_centi_c":True}]},
    {"monday":[{"start":0,"end":3600,"target_centi_c":"2100"}]},
    {"monday":[{"start":0,"end":3600,"target_centi_c":2100,"extra":1}]},
    {"wrongday":[]},
])
def test_program_rejects_noncanonical_or_unsafe_storage(raw):
    with pytest.raises(ValueError):normalize_program(raw)

def test_28_day_block_limit_and_adjacent_valid():
    week=normalize_program({})
    for i in range(4):
        week=change_block(week,list(WEEKDAYS),i*3600,(i+1)*3600,2100,500,3500)
    assert sum(map(len,week.values()))==28
    with pytest.raises(ValueError,match="program_limit"):
        change_block(week,["monday"],5*3600,6*3600,2200,500,3500)
    # Frozen caller mapping was not mutated on failed multi-day edit.
    assert len(week["monday"])==4

@pytest.mark.asyncio
@pytest.mark.parametrize("when,start,end,expected",[
    ("2026-03-29T00:00:00+00:00",9000,9900,[[0,2100]]),
    ("2026-03-29T00:00:00+00:00",9000,12600,[[0,2100],[3600,2200],[5400,2100]]),
    ("2026-10-25T00:00:00+00:00",9000,10800,[[0,2100],[1800,2200],[3600,2100],[5400,2200],[7200,2100]]),
])
async def test_local_editor_storage_uses_existing_real_dst_policy(hass,when,start,end,expected):
    epoch=int(datetime.fromisoformat(when).timestamp())
    week=program("sunday",start,end)
    output=compile_week(native_week(week),2100,"Europe/Amsterdam",epoch,epoch+10800)
    assert output["transitions"]==[[epoch+delta,target] for delta,target in expected]
    assert output["valid_until_utc"]==epoch+10800

@pytest.mark.asyncio
async def test_export_15days_integer_wire_and_mapping_no_new_wire_keys(hass):
    binding=replace(room(hass),week_program=program())
    runtime=ShadowRuntime(hass,entry(hass),[binding])
    zones,mapping=await async_build_configuration(runtime)
    schedule=zones[0]["schedule"]
    assert schedule["valid_until_utc"]-schedule["valid_from_utc"]==15*86400
    assert schedule["policy"]=="wall-clock-membership/v1"
    assert set(zones[0])=={"zone_id","sensor_id","actuator_id","base_centi_c","max_age_ms","report_evidence","schedule"}
    assert mapping["rooms"][0]["week_program"]==binding.week_program
    assert all(type(t) is int and type(v) is int for t,v in schedule["transitions"])
    # Existing integer-only local mapping canonicalization stays deterministic.
    assert canonical(mapping)==canonical(deepcopy(mapping))

@pytest.mark.asyncio
async def test_local_schedule_refresh_uses_existing_native_timer_and_unloads(hass,monkeypatch):
    from custom_components.open_thermostat import v1_mqtt
    from homeassistant.components import mqtt
    binding=replace(room(hass),week_program=program())
    runtime=ShadowRuntime(hass,entry(hass,enabled=True),[binding])
    tracked=[];removed=[]
    monkeypatch.setattr(mqtt,"async_subscribe",AsyncMock(return_value=lambda:removed.append("mqtt")))
    monkeypatch.setattr(mqtt,"async_subscribe_connection_status",lambda *a:lambda:removed.append("status"))
    def track(hass,callback,**kwargs):
        tracked.append((callback,kwargs));return lambda:removed.append("daily")
    monkeypatch.setattr(v1_mqtt,"async_track_utc_time_change",track)
    conn=NativeShadowConnection(runtime)
    await conn.async_start()
    assert len(tracked)==1 and tracked[0][1]=={"hour":0,"minute":0,"second":0}
    await conn.async_close()
    assert "daily" in removed and conn.worker.done() and conn.timer is None


@pytest.mark.asyncio
async def test_128_transition_horizon_limit_preserves_unsaved_room(hass,monkeypatch):
    from custom_components.open_thermostat import v1_config_flow
    monkeypatch.setattr(v1_config_flow.dt_util,"utcnow",lambda:datetime(2026,10,19,tzinfo=UTC))
    item,parent,old=await editor(hass)
    before=dict(old.data)
    item._program_week=normalize_program({"monday":[
        {"start":i*120,"end":i*120+60,"target_centi_c":2200} for i in range(28)]})
    result=await item.async_step_save_program()
    assert result["step_id"]=="program_save_error"
    assert result["errors"]["base"]=="program_export_failed"
    assert dict(old.data)==before
    assert (await item.async_step_program_save_error({}))["type"]=="menu"

@pytest.mark.asyncio
async def test_program_empty_edit_delete_and_base_only_save(hass):
    item,parent,old=await editor(hass)
    result=await item.async_step_edit_block()
    assert result["step_id"]=="program_empty"
    assert (await item.async_step_program_empty({}))["type"]=="menu"
    assert (await item.async_step_delete_block())["step_id"]=="program_empty"
    assert (await item.async_step_save_program())["type"]=="abort"
    saved=RoomBinding.from_dict(dict(old.data))
    assert saved.week_program is not None and all(not b for b in saved.week_program.values())
    zones,_=await async_build_configuration(ShadowRuntime(hass,parent,[saved]))
    assert zones[0]["schedule"]["transitions"]==[[zones[0]["schedule"]["valid_from_utc"],2100]]

@pytest.mark.asyncio
async def test_final_save_revalidates_deleted_source(hass):
    item,parent,old=await editor(hass)
    before=dict(old.data)
    er.async_get(hass).async_remove(item._program_room.temperature.entity_id)
    result=await item.async_step_save_program()
    assert result["step_id"]=="program_save_error" and dict(old.data)==before


@pytest.mark.asyncio
async def test_export_defends_single_source_even_for_direct_domain_objects(hass):
    binding=room(hass)
    registered=er.async_get(hass).async_get_or_create("schedule","schedule","conflict")
    conflicting=replace(binding,week_program=program(),schedule=reference(hass,registered.entity_id))
    with pytest.raises(ValueError,match="program_source_conflict"):
        RoomBinding.from_dict(conflicting.as_dict())
    with pytest.raises(ValueError,match="program_source_conflict"):
        await async_build_configuration(ShadowRuntime(hass,entry(hass),[conflicting]))
