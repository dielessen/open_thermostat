"""Actual native temporary SQLite; sample size is NOT production/72h evidence."""
import csv
from datetime import datetime,timedelta,timezone
import io
import json
import os
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant import loader
from homeassistant.components import recorder
from homeassistant.components.recorder.tasks import SynchronizeTask
from homeassistant.components.sensor import recorder as sensor_statistics
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.setup import async_setup_component
from custom_components.open_thermostat import metrics_reports as reports
from test_v1_native import entry

def registered(hass,e,unique):
    return er.async_get(hass).async_get_or_create("sensor","open_thermostat",unique,config_entry=e)

def args(e,ids,start=None,end=None):
    now=datetime.now(timezone.utc)
    return {"entry_id":e.entry_id,"entity_ids":ids,"limit":1000,
        "start":(start or now-timedelta(hours=1)).isoformat(),"end":(end or now).isoformat()}

@pytest.mark.asyncio
async def test_csv_units_are_definition_scoped_timezone_explicit_and_unknown_preserved(hass,monkeypatch):
    e=entry(hass);reports.async_register_entry(hass,e)
    energy=registered(hass,e,"fixture_room_a1b2c3d4_radiator_estimated_energy_v2")
    old=registered(hass,e,"fixture_room_a1b2c3d4_radiator_estimated_energy")
    values={energy.entity_id:[State(energy.entity_id,"1000",{"unit_of_measurement":"Wh","password":"NO_EXPORT"}),State(energy.entity_id,"unknown",{"unit_of_measurement":"Wh"})],
            old.entity_id:[State(old.entity_id,"99",{"unit_of_measurement":"NOT_CERTIFIED","password":"NO_EXPORT"})]}
    monkeypatch.setattr(reports,"get_instance",lambda _:SimpleNamespace(
        async_add_executor_job=AsyncMock(side_effect=lambda call:{call.keywords["entity_id"]:values[call.keywords["entity_id"]]})))
    start=datetime(2026,1,1,1,tzinfo=timezone(timedelta(hours=1)))
    result=await reports.async_export(hass,{**args(e,[energy.entity_id,old.entity_id],start,start+timedelta(hours=1)),"include_units":True})
    rows=list(csv.DictReader(io.StringIO(result["csv"])))
    assert result["start_utc"]=="2026-01-01T00:00:00+00:00"
    current=[r for r in rows if r["entity_id"]==energy.entity_id]
    assert [r["state"] for r in current]==["1000","unknown"]
    assert all(r["unit"]=="Wh" and r["unit_basis"]=="recorded_unit" for r in current)
    legacy=next(r for r in rows if r["entity_id"]==old.entity_id)
    assert legacy["unit"]=="" and legacy["unit_basis"]=="unknown_recorded_unit"
    assert "unbounded_historic_definition_unproven" in legacy["definition_quality"]
    assert "NO_EXPORT" not in result["csv"] and "NOT_CERTIFIED" not in result["csv"]
    reports.async_unregister_entry(hass,e.entry_id)

@pytest.mark.parametrize("unique,unit",[
    ("fixture_room_a1b2c3d4_radiator_heating_time_v2","h"),
    ("fixture_room_a1b2c3d4_radiator_estimated_power_v2","W"),
    ("fixture_hub_energy_v2","kWh"),("fixture_hub_warm_water_usage_v2","L"),
    ("fixture_hub_warm_water_avg_flow_v2","L/min"),("fixture_hub_burner_observed_time_v2","s"),
    ("fixture_hub_boiler_burner_power",""),("arbitrary_v2","")])
def test_fixed_definitions_only_no_percent_to_kw_or_flow_to_volume_conversion(unique,unit):
    assert reports._unit(unique)[0]==unit

@pytest.mark.asyncio
async def test_csv_database_failure_is_controlled_not_partial_private_sql(hass,monkeypatch):
    e=entry(hass);item=registered(hass,e,"fixture_hub_energy_v2");reports.async_register_entry(hass,e)
    monkeypatch.setattr(reports,"get_instance",lambda _:SimpleNamespace(
        async_add_executor_job=AsyncMock(side_effect=RuntimeError("PRIVATE_SQL_DATABASE_PATH"))))
    with pytest.raises(HomeAssistantError,match="Native Recorder history query failed") as caught:
        await reports.async_export(hass,args(e,[item.entity_id]))
    assert "PRIVATE" not in str(caught.value)
    reports.async_unregister_entry(hass,e.entry_id)

async def barrier(hass,instance):
    await hass.async_block_till_done()
    committed=hass.loop.create_future()
    instance.queue_task(SynchronizeTask(committed))
    await committed

def volume(path):
    # Read-only inspection of the actual native Recorder-created schema/file.
    with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as connection:
        counts={table:connection.execute("select count(*) from "+table).fetchone()[0]
                for table in ("states","states_meta","state_attributes")}
        page_count=connection.execute("pragma page_count").fetchone()[0]
        page_size=connection.execute("pragma page_size").fetchone()[0]
        journal=connection.execute("pragma journal_mode").fetchone()[0]
    files={suffix:Path(str(path)+suffix).stat().st_size if Path(str(path)+suffix).exists() else 0
        for suffix in ("","-wal","-shm")}
    return {"rows":counts,"page_count":page_count,"page_size":page_size,
        "logical_allocated_bytes":page_count*page_size,"journal_mode":journal,"file_bytes":files}

@pytest.mark.asyncio
async def test_real_recorder_volume_metadata_reset_duplicates_gaps_and_no_legacy_rewrite(hass):
    loader.async_setup(hass);async_initialize_recorder(hass)
    path=Path(hass.config.path("room-model-sample.db"))
    assert await async_setup_component(hass,"recorder",{"recorder":{"db_url":"sqlite:///"+str(path),
        "auto_purge":False,"auto_repack":False,"commit_interval":0}})
    await hass.async_start()
    e=entry(hass);reports.async_register_entry(hass,e)
    specifications=[
        ("fixture_room_a1b2c3d4_radiator_estimated_energy_v2","kWh","energy","total_increasing"),
        ("fixture_room_a1b2c3d4_radiator_heating_time_v2","h","duration","total_increasing"),
        ("fixture_room_a1b2c3d4_radiator_estimated_power_v2","W","power","measurement"),
        ("fixture_hub_energy_v2","kWh","energy","total_increasing"),
        ("fixture_hub_warm_water_usage_v2","L","water","total_increasing"),
    ]
    items=[registered(hass,e,unique) for unique,*_ in specifications]
    old=registered(hass,e,"fixture_room_a1b2c3d4_radiator_estimated_energy")
    hass.states.async_set(old.entity_id,"999",{"unit_of_measurement":"kWh","state_class":"total"})
    instance=recorder.get_instance(hass);await barrier(hass,instance)
    baseline=await instance.async_add_executor_job(volume,path)
    started=time.monotonic();start=datetime.now(timezone.utc)-timedelta(milliseconds=1)
    attempts=0
    for tick in range(60):
        # Logical 30s source cadence, compressed into a finite event fixture.
        # Not wall-clock cadence or production I/O/retention measurement.
        for item,(_,unit,device,state_class) in zip(items,specifications,strict=True):
            if unit=="W":
                value=str(500+tick%3*100)
            else:
                value=str(round((tick if item is not items[3] else tick%30)*.01,5))
            if tick==20:value="unknown"       # missing observation, never coerced to zero
            if tick==40:value="unavailable"   # explicit offline
            attributes={"unit_of_measurement":unit,"device_class":device,"state_class":state_class}
            for _ in range(3):
                hass.states.async_set(item.entity_id,value,attributes)
                attempts+=1
        await hass.async_block_till_done()
    hass.states.async_set(old.entity_id,"unavailable") # old identity has no numeric new-definition state
    await barrier(hass,instance)
    end=datetime.now(timezone.utc);seconds=time.monotonic()-started
    after=await instance.async_add_executor_job(volume,path)
    metadata=await instance.async_add_executor_job(sensor_statistics.list_statistic_ids,hass,[i.entity_id for i in items])
    assert set(metadata)=={i.entity_id for i in items}
    assert metadata[items[0].entity_id]["has_sum"] and not metadata[items[2].entity_id]["has_sum"]
    assert metadata[items[0].entity_id]["unit_of_measurement"]=="kWh"
    assert metadata[items[2].entity_id]["unit_of_measurement"]=="W"
    # Native compile over actual temporary SQLite history; no fake SQL/result.
    def compile_native():
        with instance.get_session() as session:
            return sensor_statistics.compile_statistics(hass,session,start,end,{})
    compiled=await instance.async_add_executor_job(compile_native)
    stats={row["meta"]["statistic_id"]:row for row in compiled.platform_stats}
    assert set(stats)=={i.entity_id for i in items}
    assert stats[items[3].entity_id]["stat"]["sum"]==pytest.approx(.58)
    # Existing old history is neither rewritten nor made a source of v2 totals.
    exported=await reports.async_export(hass,{**args(e,[i.entity_id for i in items],start,end),"include_units":True})
    rows=list(csv.DictReader(io.StringIO(exported["csv"])))
    assert len(rows)==300 and not exported["truncated"]
    assert {r["unit"] for r in rows}=={"kWh","h","W","L"}
    assert all(r["unit_basis"]=="recorded_unit" for r in rows)
    assert sum(r["state"]=="unknown" for r in rows)==5
    assert sum(r["state"]=="unavailable" for r in rows)==5
    previous=await reports.async_export(hass,args(e,[old.entity_id],start-timedelta(minutes=1),end))
    assert [r["state"] for r in csv.DictReader(io.StringIO(previous["csv"]))]==["999","unavailable"]
    assert after["rows"]["states"]-baseline["rows"]["states"]==301
    record={
        "pass":True,"scope":"Actual HA2026.10.2 temporary disk SQLite Recorder; 5 entities, 60 logical source ticks, 3 exact duplicate state reports/tick. Wall-clock event fixture, not physical 30min/72h, production write-rate/retention or E32 performance.",
        "logical_source_cadence_seconds":30,"logical_ticks":60,"state_set_attempts":attempts,
        "new_definition_history_rows":len(rows),"baseline":baseline,"after":after,
        "wall_fixture_seconds":seconds,"native_metadata":metadata,
        "compiled_boiler_boot_reset_sum_kwh":stats[items[3].entity_id]["stat"]["sum"],
        "production_history_modified":False,"live_device_actions":[],
    }
    evidence=Path(os.environ.get("ROOM_METRICS_EVIDENCE_DIR",hass.config.path()))
    evidence.mkdir(parents=True,exist_ok=True)
    (evidence/"ROOM-RECORDER-SAMPLE.json").write_text(json.dumps(record,indent=2,default=str)+"\n")
    reports.async_unregister_entry(hass,e.entry_id)
    assert not hass.services.has_service("open_thermostat",reports.SERVICE)


@pytest.mark.parametrize("bad",[None,{},[],["kWh"],"=PRIVATE","UNBOUNDED_PRIVATE_UNIT"])
def test_historical_unit_output_is_bounded_and_does_not_expose_other_attributes(bad):
    state=State("sensor.fixture","0",{"unit_of_measurement":bad,"password":"PRIVATE"})
    assert reports._recorded_unit(state,True)==("","unknown_recorded_unit")
    assert reports._recorded_unit(state,False)==("","not_requested")

@pytest.mark.asyncio
async def test_invalid_include_units_never_queries_recorder(hass,monkeypatch):
    e=entry(hass);item=registered(hass,e,"fixture_hub_energy_v2");reports.async_register_entry(hass,e)
    executor=AsyncMock()
    monkeypatch.setattr(reports,"get_instance",lambda _:SimpleNamespace(async_add_executor_job=executor))
    with pytest.raises(HomeAssistantError,match="include_units must be a boolean"):
        await reports.async_export(hass,{**args(e,[item.entity_id]),"include_units":"true"})
    executor.assert_not_awaited()
    reports.async_unregister_entry(hass,e.entry_id)
