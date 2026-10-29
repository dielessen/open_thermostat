"""Versioned current/Recorder identities: actual HA registries and SQLite history."""
import json
from datetime import datetime,timedelta,timezone
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from homeassistant.components import mqtt,recorder
from homeassistant.components.sensor import SensorStateClass
from homeassistant.helpers import entity_registry as er,issue_registry as ir
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.setup import async_setup_component
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat import sensor as module
from custom_components.open_thermostat.heating import HeatingTracker
from custom_components.open_thermostat.dashboard import RoomDashboard
from test_v1_native import entry

def payload(value=0):
    return {"metricsSchema":2,"counterDefinition":"observation-total-v2","counterScope":"boot","protocolScope":"plus",
            "totalEnergyUsedKwh":None,"totalEnergyUsedKwhV2":value,"warmWaterUsage":None,"warmWaterUsageV2":0}

def registry(hass,e,unique,object_id):
    return er.async_get(hass).async_get_or_create("sensor",DOMAIN,unique,config_entry=e,suggested_object_id=object_id)

def test_new_definitions_never_reuse_legacy_unique_ids_or_accept_legacy_numeric_fields():
    fresh=module.HubMetric("fixture","ems_metrics","energy")
    old=module.HubMetric("fixture","ems_metrics","energy",definition_version=1)
    assert fresh.unique_id=="fixture_hub_energy_v2" and old.unique_id=="fixture_hub_energy"
    assert fresh.state_class==SensorStateClass.TOTAL_INCREASING and old.state_class is None
    fresh.update_payload({"metricsSchema":2,"totalEnergyUsedKwh":999},True)
    assert fresh.native_value is None
    fresh.update_payload(payload(0),True);old.update_payload(payload(0),True)
    assert fresh.native_value==0 and old.native_value is None and not old.available
    old.set_online(True);old.update_value(999,True)
    assert not old.available and old.native_value is None

@pytest.mark.parametrize("version,definition",[(1,"observation-total-v2"),(2,None),(2,"old-delta"),(True,"observation-total-v2"),(2.0,"observation-total-v2")])
def test_unnegotiated_or_unknown_definition_is_not_new_statistics(version,definition):
    sensor=module.HubMetric("fixture","ems_metrics","energy")
    sensor.update_payload({**payload(1),"metricsSchema":version,"counterDefinition":definition},True)
    assert sensor.native_value is None

@pytest.mark.asyncio
@pytest.mark.parametrize("existing",[False,True,"foreign"])
async def test_real_platform_handler_fresh_setup_no_legacy_alias_existing_identity_preserved(hass,monkeypatch,existing):
    e=entry(hass);old=None;old_owner=e if existing!="foreign" else entry(hass)
    if existing:
        old=registry(hass,old_owner,"fixture_hub_energy","legacy_energy")
    tracker=HeatingTracker(hass,e)
    hass.data.setdefault(DOMAIN,{})[e.entry_id]={"heating_tracker":tracker}
    callbacks={};added=[]
    monkeypatch.setattr(mqtt,"async_wait_for_mqtt_client",AsyncMock())
    async def subscribe(_hass,topic,callback,**kwargs):
        callbacks[topic]=callback
        def unsubscribe():
            callbacks.pop(topic,None)
        return unsubscribe
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    await module.async_setup_entry(hass,e,lambda values:added.extend(values))
    callbacks["fixture/status"](SimpleNamespace(payload="on"))
    callbacks["fixture/ems_metrics"](SimpleNamespace(topic="fixture/ems_metrics",payload=json.dumps(payload(0))))
    energies=[value for value in added if value._metric=="energy"]
    assert len(energies)==(2 if existing is True else 1)
    current=next(value for value in energies if value.unique_id.endswith("_v2"))
    assert current.native_value==0 and current.available
    if existing is True:
        compat=next(value for value in energies if value.unique_id=="fixture_hub_energy")
        assert not compat.available and compat.state_class is None
        assert er.async_get(hass).async_get(old.entity_id).unique_id=="fixture_hub_energy"
        compat.hass=hass;await compat.async_added_to_hass()
        assert ir.async_get(hass).async_get_issue(DOMAIN,f"metrics_definition_v2_{e.entry_id}")
    if existing=="foreign":
        assert er.async_get(hass).async_get(old.entity_id).config_entry_id==old_owner.entry_id
    await e._async_process_on_unload(hass)
    assert callbacks=={}

@pytest.mark.asyncio
async def test_retained_maintained_discovery_template_null_is_native_mqtt_unknown_not_zero(hass):
    from homeassistant.helpers.template import Template
    from homeassistant.components.mqtt.sensor import MqttSensor
    # Exact maintained esp32_utilities9186b65 sensor val_tpl expression;
    # test boundary only, not an actual broker subscription claim.
    legacy=Template("{{(value_json.totalEnergyUsedKwh) if value_json.totalEnergyUsedKwh is defined else '0'}}",hass)
    current=Template("{{(value_json.totalEnergyUsedKwhV2) if value_json.totalEnergyUsedKwhV2 is defined else '0'}}",hass)
    body=json.dumps(payload(0))
    assert legacy.async_render_with_possible_json_value(body)=="None"
    assert current.async_render_with_possible_json_value(body)=="0"
    entity=MqttSensor.__new__(MqttSensor) # Real native method; no fake HA sensor module.
    entity._expire_after=None;entity._template=legacy.async_render_with_possible_json_value
    entity._attr_native_value=999
    entity._update_state(SimpleNamespace(payload=body,topic="fixture/ems_metrics"))
    assert entity.native_value is None

@pytest.mark.asyncio
async def test_native_dashboard_counter_aggregates_only_new_v2_statistic_entities(hass):
    e=entry(hass)
    old=registry(hass,e,"fixture_hub_energy","legacy_energy")
    new=registry(hass,e,"fixture_hub_energy_v2","energy_definition_v2")
    volume=registry(hass,e,"fixture_hub_warm_water_usage_v2","volume_definition_v2")
    config=RoomDashboard(hass,"fixture",e.entry_id)._dashboard_config()
    from custom_components.open_thermostat.dashboard import view_cards
    charts=[card for view in config["views"] for card in view_cards(view) if card["type"]=="statistics-graph"]
    assert len(charts)==2
    assert {eid for card in charts for eid in card["entities"]}=={new.entity_id,volume.entity_id}
    assert all(card["stat_types"]==["change"] for card in charts)
    assert old.entity_id not in str(charts)

@pytest.mark.asyncio
async def test_real_sqlite_old_history_retained_no_new_numeric_definition_under_old_id(hass):
    from homeassistant import loader
    loader.async_setup(hass);async_initialize_recorder(hass)
    assert await async_setup_component(hass,"recorder",{"recorder":{"db_url":"sqlite:///"+hass.config.path("definition-isolation.db"),
        "auto_purge":False,"auto_repack":False,"commit_interval":0}})
    await hass.async_start()
    e=entry(hass);old=registry(hass,e,"fixture_hub_energy","legacy_energy")
    start=datetime.now(timezone.utc)-timedelta(minutes=1);instance=recorder.get_instance(hass)
    hass.states.async_set(old.entity_id,"8",{"state_class":"total","unit_of_measurement":"kWh"})
    await hass.async_block_till_done();await instance.async_block_till_done()
    old_sensor=module.HubMetric("fixture","ems_metrics","energy",definition_version=1)
    new_sensor=module.HubMetric("fixture","ems_metrics","energy")
    new=registry(hass,e,new_sensor.unique_id,"energy_definition_v2")
    old_sensor.update_payload(payload(0),True)
    assert old_sensor.state_class is None and old_sensor.native_value is None and not old_sensor.available
    hass.states.async_set(old.entity_id,"unavailable") # Native SensorEntity will expose this, never 0 or a new total.
    for value in (0,.5):
        new_sensor.update_payload(payload(value),True)
        hass.states.async_set(new.entity_id,str(new_sensor.native_value),{"state_class":new_sensor.state_class,
            "unit_of_measurement":new_sensor.native_unit_of_measurement,"device_class":"energy"})
        await hass.async_block_till_done();await instance.async_block_till_done()
    # Always enqueue a commit barrier: async_block_till_done may observe an
    # empty queue while the recorder thread is still processing its last event.
    from homeassistant.components.recorder.tasks import SynchronizeTask
    committed=hass.loop.create_future()
    instance.queue_task(SynchronizeTask(committed))
    await committed
    end=datetime.now(timezone.utc)
    from homeassistant.components.recorder.history import state_changes_during_period
    async def history(entity_id):
        result=await instance.async_add_executor_job(partial(state_changes_during_period,hass,start,end,
            entity_id=entity_id,no_attributes=True,limit=10,include_start_time_state=False))
        return [state.state for state in result.get(entity_id,[])]
    assert await history(old.entity_id)==["8","unavailable"]
    assert await history(new.entity_id)==["0.0","0.5"]
    assert er.async_get(hass).async_get(old.entity_id).unique_id=="fixture_hub_energy"
