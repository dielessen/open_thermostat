"""Pinned native HA registry/cards/services/Repairs and actual SQLite Recorder."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import csv
import io
import pytest
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.components import recorder
from homeassistant.setup import async_setup_component
from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.sensor import HubMetric
from custom_components.open_thermostat import metrics_reports as reports
from test_v1_native import entry

def entity(hass,e,key,platform="sensor",prefix="fixture"):
    return er.async_get(hass).async_get_or_create(platform,"open_thermostat",f"{prefix}_hub_{key}",config_entry=e)

def arguments(e,entities=None,limit=1000):
    now=datetime.now(timezone.utc)
    data={"entry_id":e.entry_id,"start":(now-timedelta(hours=1)).isoformat(),"end":now.isoformat(),"limit":limit}
    if entities is not None:
        data["entity_ids"]=entities
    return data

@pytest.mark.asyncio
async def test_native_dashboard_five_views_reported_vs_estimated_no_legacy_counter_statistics(hass):
    e=entry(hass)
    for key in ("boiler_selected_flow_temperature","boiler_current_flow_temperature","boiler_burner_power","energy","warm_water_usage"):
        entity(hass,e,key)
    for key in ("boiler_heating_active","boiler_hot_water_active","boiler_burner_active","boiler_pump_active"):
        entity(hass,e,key,"binary_sensor")
    dashboard=RoomDashboard(hass,"fixture",e.entry_id)
    config=dashboard._dashboard_config()
    assert [v["path"] for v in config["views"]]==["rooms","heating","boiler","analysis","diagnostics"]
    boiler=config["views"][2]["cards"]
    assert len(boiler)==4
    assert [x["name"] for x in boiler[1]["entities"]]==["Reported selected flow","Reported current flow"]
    assert boiler[2]["title"]=="Reported burner modulation (%) — not kW"
    assert len(boiler[3]["entities"])==4
    raw=str(config)
    assert "statistics-graph" not in raw and "not gas/heat meters" in raw and "not a proven E32 command" in raw

@pytest.mark.asyncio
async def test_dashboard_tracks_renamed_registry_and_excludes_disabled_hub(hass):
    e=entry(hass);old=entity(hass,e,"boiler_burner_power")
    reg=er.async_get(hass);reg.async_update_entity(old.entity_id,new_entity_id="sensor.renamed_modulation")
    disabled=entity(hass,e,"boiler_current_flow_temperature")
    reg.async_update_entity(disabled.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    config=RoomDashboard(hass,"fixture",e.entry_id)._dashboard_config()
    assert "sensor.renamed_modulation" in str(config)
    assert disabled.entity_id not in str(config)

def test_modulation_not_electrical_power_factor_and_numeric_strings_unknown():
    modulation=HubMetric("fixture","ems_status","boiler_burner_power")
    assert modulation.device_class is None and modulation.native_unit_of_measurement=="%"
    modulation.update_payload({"currentBurnerPower":"25"},True)
    assert modulation.native_value is None
    modulation.update_payload({"currentBurnerPower":0},True)
    assert modulation.native_value==0

@pytest.mark.parametrize("key",["energy_unattributed","burner_observed_time"])
def test_new_counter_entities_need_v2_and_preserve_real_zero(key):
    sensor=HubMetric("fixture","ems_metrics",key)
    field="unattributedEnergyUsedKwhV2" if key=="energy_unattributed" else "observedBurnerSecondsV2"
    sensor.update_payload({field:1},True);assert sensor.native_value is None
    sensor.update_payload({"metricsSchema":2,"counterDefinition":"observation-total-v2",field:0},True);assert sensor.native_value==0

@pytest.mark.parametrize("key,field", [("energy","totalEnergyUsedKwhV2"),("warm_water_usage","warmWaterUsageV2"),("burner_observed_time","observedBurnerSecondsV2")])
def test_negative_cumulative_counters_never_enter_recorder(key,field):
    sensor=HubMetric("fixture","ems_metrics",key)
    sensor.update_payload({"metricsSchema":2,"counterDefinition":"observation-total-v2",field:-1},True)
    assert sensor.native_value is None

@pytest.mark.asyncio
async def test_actual_old_numeric_receipt_creates_persistent_native_repair_no_clear_on_v2(hass):
    e=entry(hass);sensor=HubMetric("fixture","ems_metrics","energy",e.entry_id);sensor.hass=hass
    sensor.update_payload({"totalEnergyUsedKwh":.01},True)
    issue=ir.async_get(hass).async_get_issue("open_thermostat",f"legacy_metrics_history_{e.entry_id}")
    assert issue and issue.is_persistent and not issue.is_fixable
    sensor.update_payload({"metricsSchema":2,"counterDefinition":"observation-total-v2","totalEnergyUsedKwhV2":0},True)
    assert ir.async_get(hass).async_get_issue("open_thermostat",f"legacy_metrics_history_{e.entry_id}") is issue

@pytest.mark.asyncio
async def test_empty_or_corrected_payload_does_not_fabricate_old_history_repair(hass):
    e=entry(hass);sensor=HubMetric("fixture","ems_metrics","energy",e.entry_id);sensor.hass=hass
    sensor.update_payload({},True);sensor.update_payload({"metricsSchema":2,"counterDefinition":"observation-total-v2","totalEnergyUsedKwhV2":0},True)
    assert not ir.async_get(hass).async_get_issue("open_thermostat",f"legacy_metrics_history_{e.entry_id}")

@pytest.mark.asyncio
async def test_export_exact_ownership_no_attributes_formula_and_truncation_bound(hass,monkeypatch):
    e=entry(hass);owned=entity(hass,e,"energy")
    foreign=er.async_get(hass).async_get_or_create("sensor","other","private")
    reports.async_register_entry(hass,e)
    async def query(call):
        assert call.keywords==dict(entity_id=owned.entity_id,no_attributes=True,limit=3,include_start_time_state=False)
        return {owned.entity_id:[State(owned.entity_id,"0",{"password":"NEVER_EXPORT"}),
                                 State(owned.entity_id,"=HYPERLINK(\"private\")"),
                                 State(owned.entity_id,"3")]}
    executor=AsyncMock(side_effect=query);monkeypatch.setattr(reports,"get_instance",lambda _:SimpleNamespace(async_add_executor_job=executor))
    with pytest.raises(HomeAssistantError):
        await reports.async_export(hass,arguments(e,[foreign.entity_id]))
    result=await reports.async_export(hass,arguments(e,[owned.entity_id],2))
    assert result["rows"]==2 and result["truncated"] and not result["database_writes"]
    assert "password" not in result["csv"] and "NEVER_EXPORT" not in result["csv"]
    rows=list(csv.reader(io.StringIO(result["csv"])))
    assert rows[1][2]=="0" and rows[2][2].startswith("'=")
    assert "historic_definition_unproven" in rows[1][3]
    reports.async_unregister_entry(hass,e.entry_id)

@pytest.mark.asyncio
async def test_multibyte_csv_limit_is_bytes_and_current_unloaded_owner_cannot_query(hass,monkeypatch):
    e=entry(hass);owned=entity(hass,e,"boiler_display_code");reports.async_register_entry(hass,e)
    states=[State(owned.entity_id,"é"*50),State(owned.entity_id,"é"*50)]
    monkeypatch.setattr(reports,"get_instance",lambda _:SimpleNamespace(async_add_executor_job=AsyncMock(return_value={owned.entity_id:states})))
    monkeypatch.setattr(reports,"MAX_BYTES",300)
    result=await reports.async_export(hass,arguments(e,[owned.entity_id]))
    assert len(result["csv"].encode("utf-8"))<=300 and result["truncated"]
    reports.async_unregister_entry(hass,e.entry_id)
    with pytest.raises(HomeAssistantError):
        await reports.async_export(hass,arguments(e,[owned.entity_id]))

@pytest.mark.asyncio
async def test_response_only_native_service_two_entries_and_final_unload(hass,monkeypatch):
    a=entry(hass);b=entry(hass)
    entity(hass,a,"energy");reports.async_register_entry(hass,a);reports.async_register_entry(hass,b)
    monkeypatch.setattr(reports,"get_instance",lambda _:SimpleNamespace(async_add_executor_job=AsyncMock(return_value={})))
    result=await hass.services.async_call("open_thermostat",reports.SERVICE,arguments(a),blocking=True,return_response=True)
    assert result["rows"]==0 and result["unqueried_entities"]==[]
    reports.async_unregister_entry(hass,a.entry_id);assert hass.services.has_service("open_thermostat",reports.SERVICE)
    with pytest.raises(HomeAssistantError):
        await reports.async_export(hass,arguments(a))
    reports.async_unregister_entry(hass,b.entry_id);assert not hass.services.has_service("open_thermostat",reports.SERVICE)

@pytest.mark.asyncio
async def test_service_rejects_non_admin_native_context(hass):
    from homeassistant.auth.const import GROUP_ID_USER
    from homeassistant.core import Context
    e=entry(hass);entity(hass,e,"energy");reports.async_register_entry(hass,e)
    from homeassistant.auth import auth_manager_from_config
    hass.auth=await auth_manager_from_config(hass,[],[])
    await hass.auth.async_create_user("fixture_owner")
    user=await hass.auth.async_create_user("fixture_non_admin",group_ids=[GROUP_ID_USER])
    assert not user.is_admin
    with pytest.raises(Unauthorized):
        await hass.services.async_call("open_thermostat",reports.SERVICE,arguments(e),blocking=True,return_response=True,context=Context(user_id=user.id))
    reports.async_unregister_entry(hass,e.entry_id)

@pytest.mark.asyncio
async def test_timezones_ranges_and_disabled_or_duplicate_entities_rejected_without_query(hass,monkeypatch):
    e=entry(hass);item=entity(hass,e,"energy");reports.async_register_entry(hass,e)
    executor=AsyncMock();monkeypatch.setattr(reports,"get_instance",lambda _:SimpleNamespace(async_add_executor_job=executor))
    for data in ({"start":"2026-01-01T00:00:00","end":"2026-01-01T01:00:00Z"},
                 {"start":"2026-01-01T00:00:00Z","end":"2026-01-03T01:00:00Z"},
                 {"entity_ids":[item.entity_id,item.entity_id]}):
        with pytest.raises(HomeAssistantError):
            await reports.async_export(hass,{**arguments(e),**data})
    er.async_get(hass).async_update_entity(item.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    with pytest.raises(HomeAssistantError):
        await reports.async_export(hass,arguments(e,[item.entity_id]))
    executor.assert_not_awaited();reports.async_unregister_entry(hass,e.entry_id)

@pytest.mark.asyncio
async def test_integration_registers_and_native_unload_hook_removes_export_service(hass,monkeypatch):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat.v1_model import MODE_LEGACY
    e=entry(hass,mode=MODE_LEGACY)
    monkeypatch.setattr(integration,"_legacy_setup_entry",AsyncMock(return_value=True))
    assert await integration.async_setup_entry(hass,e)
    assert hass.services.has_service("open_thermostat",reports.SERVICE)
    await e._async_process_on_unload(hass) # Native ConfigEntry hook, test boundary only.
    assert not hass.services.has_service("open_thermostat",reports.SERVICE)

@pytest.mark.asyncio
async def test_diagnostics_export_only_history_review_flag_not_entry_credentials(hass):
    from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
    e=entry(hass);hass.config_entries.async_update_entry(e,data={**e.data,"password":"NEVER_EXPORT"})
    reports.note_legacy_metrics(hass,e.entry_id)
    data=await async_get_config_entry_diagnostics(hass,e)
    assert data["metrics_history"]["review_required"] and not data["metrics_history"]["automatic_statistics_migration"]
    assert "NEVER_EXPORT" not in str(data)

@pytest.mark.asyncio
async def test_actual_native_sqlite_recorder_roundtrip_preserves_zero_unknown_without_attributes(hass):
    # Real HA Recorder, real SQLite, real public bounded history query; no patched SQL.
    from homeassistant import loader
    loader.async_setup(hass)
    from homeassistant.helpers.recorder import async_initialize_recorder
    async_initialize_recorder(hass)
    assert await async_setup_component(hass,"recorder",{"recorder":{"db_url":"sqlite:///"+hass.config.path("test-recorder.db"),"auto_purge":False,"auto_repack":False,"commit_interval":0}})
    await hass.async_start()
    e=entry(hass);item=entity(hass,e,"energy");reports.async_register_entry(hass,e)
    instance=recorder.get_instance(hass)
    start=datetime.now(timezone.utc)-timedelta(minutes=1)
    for value in ("1","0","unknown"):
        hass.states.async_set(item.entity_id,value,{"password":"NEVER_EXPORT","unit_of_measurement":"kWh"})
        await hass.async_block_till_done();await instance.async_block_till_done()
    # Always enqueue a commit barrier: async_block_till_done may observe an
    # empty queue while the recorder thread is still processing its last event.
    from homeassistant.components.recorder.tasks import SynchronizeTask
    committed=hass.loop.create_future()
    instance.queue_task(SynchronizeTask(committed))
    await committed
    end=datetime.now(timezone.utc)
    result=await reports.async_export(hass,{"entry_id":e.entry_id,"start":start.isoformat(),"end":end.isoformat(),"entity_ids":[item.entity_id],"limit":10})
    rows=list(csv.reader(io.StringIO(result["csv"])))
    assert [row[2] for row in rows[1:]]==["1","0","unknown"]
    assert not result["truncated"] and "NEVER_EXPORT" not in result["csv"]
    again=await reports.async_export(hass,{"entry_id":e.entry_id,"start":start.isoformat(),"end":end.isoformat(),"entity_ids":[item.entity_id],"limit":1})
    assert again["rows"]==1 and again["truncated"]
    reports.async_unregister_entry(hass,e.entry_id)


@pytest.mark.asyncio
async def test_native_boiler_view_uses_owned_enabled_renamed_fields_and_quality_groups(hass):
    e=entry(hass);reg=er.async_get(hass)
    def field(name, **kwargs):
        return reg.async_get_or_create("sensor","open_thermostat",
            f"fixture_boiler_fields_v1_{name}",config_entry=e,**kwargs)
    flow=field("measured_flow_temperature")
    reg.async_update_entity(flow.entity_id,new_entity_id="sensor.renamed_native_flow")
    returned=field("measured_return_temperature")
    inferred=field("heating_active")
    raw=field("raw_burner_bit",disabled_by=er.RegistryEntryDisabler.INTEGRATION)
    disabled=field("reported_burner_modulation",disabled_by=er.RegistryEntryDisabler.USER)
    legacy=entity(hass,e,"boiler_current_flow_temperature")
    other=entry(hass);foreign=reg.async_get_or_create("sensor","open_thermostat",
        "fixture_boiler_fields_v1_selected_dhw_temperature",config_entry=other)
    dashboard=RoomDashboard(hass,"fixture",e.entry_id)
    config=dashboard._dashboard_config();boiler=next(v for v in config["views"] if v["path"]=="boiler")
    text=str(boiler)
    assert "sensor.renamed_native_flow" in text and returned.entity_id in text
    assert inferred.entity_id in text and "Inferred activity" in text
    reported=next(c for c in boiler["cards"] if c.get("title")=="Reported boiler fields")
    assert inferred.entity_id not in str(reported)
    for missing in [raw.entity_id,disabled.entity_id,foreign.entity_id,legacy.entity_id]:
        assert missing not in text
    graphs=[c for c in boiler["cards"] if c["type"]=="history-graph"]
    assert graphs and all(inferred.entity_id not in str(c) for c in graphs)
    assert "statistics-graph" not in text and "call-service" not in text
    reg.async_update_entity(raw.entity_id,disabled_by=None)
    config=dashboard._dashboard_config()
    diagnostics=next(v for v in config["views"] if v["path"]=="diagnostics")
    assert raw.entity_id in str(diagnostics) and "Unreliable raw boiler diagnostics" in str(diagnostics)
    assert raw.entity_id not in str(next(v for v in config["views"] if v["path"]=="boiler"))
