"""Real HA objects, deterministic source clocks, MQTT messages at boundary only."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorStateClass
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from custom_components.open_thermostat.heating import HeatingTracker
from custom_components.open_thermostat import sensor, binary_sensor
from custom_components.open_thermostat.dashboard import RoomDashboard
from test_v1_native import entry

BOOT="a"*32
KEY="a1b2c3d4"
class Model:
    def __init__(self,hass):
        self.time=0.0
        self.tracker=HeatingTracker(hass,entry(hass),clock=lambda:self.time)
        self.status("on")
    def raw(self,method,payload,retain=False):
        getattr(self.tracker,method)(SimpleNamespace(topic="fixture",payload=json.dumps(payload),retain=retain))
    def status(self,status,retain=False):
        self.tracker._handle_status(SimpleNamespace(payload=status,retain=retain))
    def rooms(self,*,boot=BOOT,age=0,source=None,retain=False,**changes):
        stamp=int(1000000+self.time*1000) if source is None else source
        self.raw("_handle_rooms",{"roomObservation":{"schema":2,"boot_id":boot,"source_ms":stamp},
            "rooms":[{"id":KEY,"name":"Room","currentTemp":2000,"currentTempAgeMs":age,
                      "isBeingHeatedState":"on",**changes}]},retain)
    def ems(self,*,boot=BOOT,sequence=1,age=0,source=None,retain=False,**changes):
        stamp=int(1000000+self.time*1000) if source is None else source
        self.raw("_handle_ems",{"roomEstimateObservation":{"schema":2,"boot_id":boot,"source_ms":stamp,
            "observed_ms":stamp-age,"sequence":sequence,"ttl_ms":30000,
            "quality":"reported_plus_not_delivery_proof","valid":True,"ch":True,"dhw":False,
            "flame":True,"pump":True,"supply_c":60,"selected_flow_c":60,"modulation_pct":50,**changes}},retain)
    def ready(self):
        self.rooms();self.ems();self.tracker.set_rated_power(KEY,1000)

@pytest.mark.asyncio
async def test_source_windows_clip_long_gap_and_reads_never_integrate(hass):
    m=Model(hass);m.ready();t=m.tracker
    power=t.estimated_power(KEY)
    for _ in range(20):
        assert t.estimated_power(KEY)==power
    assert t.rooms[KEY].heating_seconds==0
    m.time=3600;t._tick()
    assert t.rooms[KEY].heating_seconds==30
    assert t.rooms[KEY].estimated_energy_kwh==pytest.approx(power*30/3600000)
    assert not t.estimate_available(KEY) and t.estimated_power(KEY) is None
    # A fresh report cannot fill the unobserved gap.
    m.rooms();m.ems(sequence=2);m.time+=1;t._tick()
    assert t.rooms[KEY].heating_seconds==31

@pytest.mark.asyncio
async def test_duplicate_and_get_source_timestamp_do_not_extend_observation(hass):
    m=Model(hass);m.ready();t=m.tracker
    m.time=29;m.ems(sequence=1,age=29000);m.rooms(source=1000000)
    m.time=31;t._tick()
    assert not t.estimate_available(KEY)
    assert t.rooms[KEY].heating_seconds==30

@pytest.mark.asyncio
async def test_room_snapshot_and_temperature_age_have_separate_deadlines(hass):
    m=Model(hass);m.rooms(age=299000);m.ems();m.tracker.set_rated_power(KEY,1000)
    m.time=5;m.tracker._tick()
    assert m.tracker.rooms[KEY].heating_seconds==1
    assert m.tracker.estimated_power(KEY) is None
    # Live EMS alone never renews the room snapshot.
    m=Model(hass);m.ready();m.time=25;m.ems(sequence=2);m.time=46;m.tracker._tick()
    assert m.tracker.rooms[KEY].heating_seconds==45

@pytest.mark.asyncio
async def test_offline_and_boot_mismatch_require_new_matching_observations(hass):
    m=Model(hass);m.ready();m.time=3;m.status("off")
    m.time=10;m.status("on")
    assert not m.tracker.estimate_available(KEY)
    m.rooms();m.ems(sequence=2,boot="b"*32)
    assert not m.tracker.estimate_available(KEY)
    m.rooms(boot="b"*32,source=110001)
    assert m.tracker.estimate_available(KEY)
    assert m.tracker.rooms[KEY].heating_seconds==3

@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["room","ems","status"])
async def test_retained_messages_are_not_fresh_evidence(hass,kind):
    m=Model(hass);m.ready()
    if kind=="room":m.rooms(retain=True)
    elif kind=="ems":m.ems(sequence=2,retain=True)
    else:m.status("on",retain=True)
    assert not m.tracker.estimate_available(KEY)

@pytest.mark.asyncio
async def test_old_schema_remains_room_compatible_but_never_estimated_heat(hass):
    m=Model(hass)
    m.raw("_handle_rooms",{"rooms":[{"id":KEY,"currentTemp":2000,"isBeingHeatedState":"on"}]})
    m.raw("_handle_ems",{"heatingActive":True,"warmWaterActive":False,"currentFlowTemperature":600})
    m.tracker.set_rated_power(KEY,1000);m.time=600;m.tracker._tick()
    assert m.tracker.room_available(KEY)
    assert not m.tracker.is_heating(KEY) and m.tracker.estimated_power(KEY) is None
    assert m.tracker.rooms[KEY].estimated_energy_kwh==0

@pytest.mark.asyncio
@pytest.mark.parametrize("change",[{"ch":False},{"dhw":True},{"ch":False,"dhw":False,"flame":False}])
async def test_reported_inactive_is_real_zero_not_missing_data(hass,change):
    m=Model(hass);m.ready();m.time=1;m.ems(sequence=2,**change)
    assert m.tracker.estimate_available(KEY) and not m.tracker.is_heating(KEY)
    assert m.tracker.estimated_power(KEY)==0

@pytest.mark.asyncio
@pytest.mark.parametrize("bad",[float("nan"),float("inf"),-1,True,20001])
async def test_config_and_restore_reject_nonfinite_or_unbounded_totals(hass,bad):
    m=Model(hass);m.ready()
    with pytest.raises(HomeAssistantError):m.tracker.set_rated_power(KEY,bad)
    m.tracker.restore_totals(KEY,seconds=float("inf"),energy=float("nan"))
    assert m.tracker.rooms[KEY].heating_seconds==0 and m.tracker.rooms[KEY].estimated_energy_kwh==0

@pytest.mark.asyncio
@pytest.mark.parametrize("change",[{"supply_c":float("nan")},{"modulation_pct":101},{"ttl_ms":60000},{"sequence":True}])
async def test_invalid_ems_envelope_fails_closed(hass,change):
    m=Model(hass);m.ready();m.ems(sequence=2,**{k:v for k,v in change.items() if k!="sequence"}) if "sequence" not in change else m.ems(**change)
    assert not m.tracker.estimate_available(KEY)

@pytest.mark.asyncio
async def test_missing_rated_power_is_unknown_not_zero_and_definition_isolated(hass):
    m=Model(hass);m.rooms();m.ems()
    current=sensor.RoomEstimatedEnergy("fixture",0,KEY,"Room",None,m.tracker)
    old=sensor.RoomEstimatedEnergy("fixture",0,KEY,"Room",None,m.tracker,legacy=True)
    power=sensor.RoomEstimatedPower("fixture",0,KEY,"Room",None,m.tracker)
    for e in (current,old,power):e.update_from_tracker()
    assert current.unique_id.endswith("_v2") and not old.unique_id.endswith("_v2")
    assert current.state_class==SensorStateClass.TOTAL_INCREASING and old.state_class is None
    assert current.extra_state_attributes["not_a_heat_meter"]
    assert not current.available and not old.available and not power.available
    assert power.native_value is None and old.native_value is None

@pytest.mark.asyncio
async def test_mqtt_timer_expiry_and_unload_cancel_exact_native_resources(hass,monkeypatch):
    callbacks={};removed=[]
    async def subscribe(_hass,topic,fn):
        callbacks[topic]=fn
        return lambda:removed.append(topic)
    monkeypatch.setattr(mqtt,"async_wait_for_mqtt_client",AsyncMock())
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    m=Model(hass);await m.tracker.async_start();m.ready()
    assert m.tracker._timer_cancel is not None
    m.time=30;m.tracker._tick()
    assert not m.tracker.estimate_available(KEY)
    await m.tracker.async_stop()
    assert len(removed)==3 and m.tracker._timer_cancel is None

@pytest.mark.asyncio
async def test_room_dashboard_uses_registry_v2_not_old_history_and_english_quality(hass):
    e=entry(hass);registry=er.async_get(hass)
    old=registry.async_get_or_create("sensor","open_thermostat",f"fixture_room_{KEY}_radiator_estimated_energy",config_entry=e)
    new=registry.async_get_or_create("sensor","open_thermostat",f"fixture_room_{KEY}_radiator_estimated_energy_v2",config_entry=e)
    dashboard=RoomDashboard(hass,"fixture",e.entry_id);dashboard._rooms={KEY}
    config=dashboard._dashboard_config();raw=str(config)
    entities=[item for view in config["views"] for card in view["cards"] if card["type"]=="entities" for item in card["entities"]]
    assert new.entity_id in entities and old.entity_id not in entities
    assert "Unknown/stale inputs create gaps" in raw and "not measured heat" in raw
    import os
    from pathlib import Path
    if directory := os.environ.get("ROOM_METRICS_EVIDENCE_DIR"):
        Path(directory,"ROOM-MODEL-DASHBOARD.json").write_text(json.dumps(config,indent=2)+"\n")


@pytest.mark.asyncio
@pytest.mark.parametrize("existing",[False,True,"foreign"])
async def test_actual_sensor_platform_legacy_identity_preserved_no_total_backfill_unload(hass,monkeypatch,existing):
    from homeassistant.core import State
    from custom_components.open_thermostat.const import DOMAIN
    e=entry(hass);other=entry(hass) if existing=="foreign" else e
    old_record=None
    if existing:
        old_record=er.async_get(hass).async_get_or_create("sensor",DOMAIN,
            f"fixture_room_{KEY}_radiator_estimated_energy",config_entry=other)
    tracker=HeatingTracker(hass,e)
    hass.data.setdefault(DOMAIN,{})[e.entry_id]={"heating_tracker":tracker}
    added=[];callbacks={}
    async def subscribe(_hass,topic,fn):
        callbacks[topic]=fn
        def unsubscribe():
            callbacks.pop(topic,None)
        return unsubscribe
    monkeypatch.setattr(mqtt,"async_wait_for_mqtt_client",AsyncMock())
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    await sensor.async_setup_entry(hass,e,lambda values:added.extend(values))
    tracker._handle_status(SimpleNamespace(payload="on",retain=False))
    tracker._handle_rooms(SimpleNamespace(topic="room_data",retain=False,payload=json.dumps({
        "rooms":[{"id":KEY,"currentTemp":2000,"isBeingHeatedState":"on"}]})))
    models=[x for x in added if isinstance(x,sensor.RoomEstimatedEnergy)]
    assert len(models)==(2 if existing is True else 1)
    current=next(x for x in models if x.unique_id.endswith("_v2"))
    assert current.native_value==0 and not current.available
    assert tracker.rooms[KEY].estimated_energy_kwh==0
    if existing is True:
        old=next(x for x in models if not x.unique_id.endswith("_v2"))
        old.hass=hass
        old.async_get_last_state=AsyncMock(return_value=State(old_record.entity_id,"999"))
        await old.async_added_to_hass()
        old.async_get_last_state.assert_not_awaited()
        assert old.native_value is None and old.state_class is None and not old.available
        assert ir.async_get(hass).async_get_issue(DOMAIN,f"room_model_v2_{e.entry_id}")
        assert er.async_get(hass).async_get(old_record.entity_id).unique_id==old_record.unique_id
    if existing=="foreign":
        assert old_record.config_entry_id==other.entry_id
    await e._async_process_on_unload(hass)
    assert callbacks=={}


@pytest.mark.asyncio
async def test_native_boiler_cards_share_source_deadline_not_room_membership_or_raw_cache(hass):
    m=Model(hass)
    target=sensor.HubMetric("fixture","ems_status","boiler_selected_flow_temperature",tracker=m.tracker)
    measured=sensor.HubMetric("fixture","ems_status","boiler_current_flow_temperature",tracker=m.tracker)
    modulation=sensor.HubMetric("fixture","ems_status","boiler_burner_power",tracker=m.tracker)
    states=[binary_sensor.BoilerState("fixture",key,tracker=m.tracker) for key in
        ("boiler_heating_active","boiler_hot_water_active","boiler_burner_active","boiler_pump_active")]
    # Old cached values must NOT feed native configured entities.
    target.update_payload({"selectedFlowTemperature":99},True)
    assert not target.available and target.native_value is None
    m.ems()
    for e in (target,measured,modulation,*states):e.update_from_tracker()
    assert [e.native_value for e in (target,measured,modulation)]==[60,60,50]
    assert [e.is_on for e in states]==[True,False,True,True]
    assert all(e.available for e in (target,measured,modulation,*states))
    assert not m.tracker.rooms
    m.time=30
    for e in (target,measured,modulation,*states):e.update_from_tracker()
    assert all(not e.available for e in (target,measured,modulation,*states))
    assert all(e.native_value is None for e in (target,measured,modulation))
    assert all(e.is_on is None for e in states)


@pytest.mark.asyncio
async def test_retained_online_hint_allows_late_subscription_but_not_cached_evidence(hass):
    m=Model(hass);m.ready();m.status("on",retain=True)
    assert m.tracker.online and not m.tracker.ems_available()
    assert not m.tracker.estimate_available(KEY)
    m.time=1;m.ems(sequence=2)
    assert m.tracker.ems_available() and not m.tracker.estimate_available(KEY)
    m.rooms()
    assert m.tracker.estimate_available(KEY)

@pytest.mark.asyncio
async def test_partial_native_subscription_failure_cleans_up_without_listener_leak(hass,monkeypatch):
    m=Model(hass);removed=[]
    async def subscribe(_hass,topic,fn):
        if topic.endswith("/room_data"):
            raise RuntimeError("fixture subscription failure")
        return lambda:removed.append(topic)
    monkeypatch.setattr(mqtt,"async_wait_for_mqtt_client",AsyncMock())
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    with pytest.raises(RuntimeError,match="subscription failure"):
        await m.tracker.async_start()
    assert removed==["fixture/status"]
    assert not m.tracker._unsubscribers and not m.tracker._started and m.tracker._timer_cancel is None
