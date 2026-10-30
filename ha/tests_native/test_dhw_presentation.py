"""Real native HA read-only DHW profile/registry/options/dashboard lifecycle."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.template import Template
from custom_components.open_thermostat import sensor, diagnostics
from custom_components.open_thermostat.dhw import DhwPresentation, entry_snapshot
from custom_components.open_thermostat.heating import HeatingTracker
from custom_components.open_thermostat.dashboard import RoomDashboard
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow
from custom_components.open_thermostat.v1_model import MODE_LEGACY,MODE_SHADOW
from test_v1_native import entry
from test_room_model_v2 import Model
from test_room_sensor_restore import platform


def raw(profile="classic_observed", **more):
    return {"protocolProfile":profile,"selectedWarmWaterTemperature":60,
        "currentWarmWaterTemperature":583,"warmWaterEnabled":True,"warmWaterActive":True,"warmWaterFlow":25,**more}


def send(tracker,payload,retain=False):
    tracker._handle_ems(SimpleNamespace(payload=json.dumps(payload),retain=retain))


@pytest.mark.asyncio
@pytest.mark.parametrize("profile",["classic_observed","plus_observed"])
async def test_supported_temperatures_are_last_reported_only_never_a_write_grant(hass,profile):
    m=Model(hass);send(m.tracker,raw(profile,comfort="SECRET",schedule="SECRET",runtime=42,write_supported=True))
    s=m.tracker.dhw_snapshot();assert s["profile"]==profile and s["packet_fresh"]
    assert s["fields"]["selected_temperature"]["value"]==60
    assert s["fields"]["current_temperature"]["value"]==58.3
    assert s["fields"]["current_temperature"]["quality"]=="reported_unqualified_source_age"
    assert not s["source_age_qualified"] and not s["physical_validation"] and not s["write_supported"]
    for key in ("comfort","schedule","runtime"):
        assert s["fields"][key]["supported_read"] is False and s["fields"][key]["value"] is None
    assert "SECRET" not in json.dumps(s) and not m.tracker.ems_available()
    if profile=="classic_observed":
        assert s["fields"]["activity"]["quality"]=="inferred_unqualified"
        assert s["fields"]["flow"]["quality"]=="unreliable_classic" and s["fields"]["flow"]["value"] is None
    else:assert s["fields"]["activity"]["value"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("profile",[None,"unknown","conflicting_families","Classic","Plus",17,{},["plus_observed"]])
async def test_unknown_conflicting_or_malformed_profile_cannot_be_promoted_by_numeric_fields(hass,profile):
    m=Model(hass);send(m.tracker,raw(profile,protocolVersion="Plus",model="Classic HRC"))
    s=m.tracker.dhw_snapshot();assert not s["packet_fresh"]
    assert all(not f["supported_read"] and f["value"] is None for f in s["fields"].values())
    assert s["profile"] in {"unknown","conflicting_families"}


@pytest.mark.asyncio
@pytest.mark.parametrize("value",[True,"58",None,float("inf"),float("nan"),-1,1301,{"password":"PRIVATE"}])
async def test_invalid_temperature_types_and_ranges_remain_unknown_not_zero(hass,value):
    m=Model(hass);send(m.tracker,raw(currentWarmWaterTemperature=value))
    f=m.tracker.dhw_snapshot()["fields"]["current_temperature"]
    assert f["value"] is None and f["quality"]=="invalid_or_missing"
    assert "PRIVATE" not in json.dumps(m.tracker.dhw_snapshot())


@pytest.mark.asyncio
async def test_zero_valid_temperature_enabled_false_and_profile_switch_clear_old_fields(hass):
    m=Model(hass);send(m.tracker,raw(selectedWarmWaterTemperature=0,currentWarmWaterTemperature=0,warmWaterEnabled=False))
    s=m.tracker.dhw_snapshot();assert s["fields"]["current_temperature"]["value"]==0
    assert s["fields"]["enabled"]["value"] is False
    send(m.tracker,{"protocolProfile":"plus_observed"})
    assert m.tracker.dhw_snapshot()["fields"]["current_temperature"]["value"] is None


@pytest.mark.asyncio
async def test_receipt_ttl_getters_offline_retained_and_backwards_clock_never_certify_source_age(hass):
    m=Model(hass);send(m.tracker,raw());m.time=29
    for _ in range(100):assert m.tracker.dhw_snapshot()["packet_fresh"]
    m.time=30;m.tracker._tick();assert m.tracker.dhw_snapshot()["status"]=="stale"
    assert all(f["value"] is None for f in m.tracker.dhw_snapshot()["fields"].values())
    send(m.tracker,raw(),retain=True);assert not m.tracker.dhw_snapshot()["packet_fresh"]
    send(m.tracker,raw());m.status("off");m.status("on")
    assert not m.tracker.dhw_snapshot()["packet_fresh"]
    send(m.tracker,raw());m.time=1;assert m.tracker.dhw_snapshot()["status"]=="clock_reversed"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload",["bad json","[]",'{"protocolProfile":',"x"*65537])
async def test_malformed_frame_invalidates_dhw_only_without_exporting_private_payload(hass,payload):
    m=Model(hass);send(m.tracker,raw())
    m.tracker._handle_ems(SimpleNamespace(payload=payload,retain=False))
    s=m.tracker.dhw_snapshot();assert not s["packet_fresh"] and s["status"]=="malformed"
    assert all(f["value"] is None for f in s["fields"].values())


@pytest.mark.asyncio
async def test_activity_uses_existing_qualified_plus_observation_and_dhw_priority_is_unchanged(hass):
    m=Model(hass);m.ready();before=m.tracker._ems_deadline
    # This is the SAME real tracker observation validator, not a raw DHW flag.
    observation={"schema":2,"boot_id":"a"*32,"source_ms":1000000,"observed_ms":1000000,
        "sequence":2,"ttl_ms":30000,"quality":"reported_plus_not_delivery_proof","valid":True,
        "ch":True,"dhw":True,"flame":True,"pump":True,"supply_c":60,"selected_flow_c":60,"modulation_pct":50}
    send(m.tracker,raw("plus_observed",roomEstimateObservation=observation))
    s=m.tracker.dhw_snapshot();assert s["fields"]["activity"]["value"] is True
    assert s["fields"]["activity"]["quality"]=="reported_source_bounded_not_physical"
    assert not m.tracker._heating(next(iter(m.tracker.rooms.values())),m.time)
    for _ in range(100):m.tracker.dhw_snapshot()
    assert m.tracker._ems_deadline==before
    m.time=30;m.tracker._tick();assert m.tracker.boiler_reading("dhw") is None
    assert m.tracker.dhw_snapshot()["fields"]["activity"]["value"] is None


@pytest.mark.asyncio
async def test_native_sensor_platform_registry_no_unit_statistics_or_write_features_and_no_repeated_state_writes(hass):
    e=entry(hass,mode="legacy");clock=[0.0];t=HeatingTracker(hass,e,clock=lambda:clock[0]);t.online=True
    p=await platform(hass,e);entity=sensor.DhwStatus("fixture",t)
    try:
        await p.async_add_entities([entity]);remove=t.async_add_listener(entity.update_from_tracker)
        send(t,raw());await hass.async_block_till_done()
        original=hass.states.get(entity.entity_id)
        assert original.state=="classic_observed" and original.attributes["write_supported"] is False
        assert entity.state_class is None and entity.native_unit_of_measurement is None and entity.supported_features==0
        for _ in range(10):entity.update_from_tracker()
        assert hass.states.get(entity.entity_id) is original
        clock[0]=30;t._tick();await hass.async_block_till_done()
        assert hass.states.get(entity.entity_id).state=="stale"
        assert er.async_get(hass).async_get(entity.entity_id).unique_id=="fixture_hub_dhw_capabilities"
        remove();await t.async_stop();assert not t._listeners and t._timer_cancel is None
    finally:await p.async_destroy()


@pytest.mark.asyncio
async def test_real_tracker_has_only_existing_subscriptions_and_one_expiry_timer(hass,monkeypatch):
    e=entry(hass,mode="legacy");t=HeatingTracker(hass,e);callbacks={};removed=[]
    monkeypatch.setattr(mqtt,"async_wait_for_mqtt_client",AsyncMock())
    async def subscribe(_,topic,cb):
        callbacks[topic]=cb
        return lambda:removed.append(topic)
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    await t.async_start()
    assert set(callbacks)=={"fixture/status","fixture/room_data","fixture/ems_status"}
    callbacks["fixture/status"](SimpleNamespace(payload="on",retain=False))
    send(t,raw());assert t._timer_cancel is not None
    await t.async_stop();assert set(removed)==set(callbacks) and t._timer_cancel is None and not t._listeners
    assert not t.dhw_snapshot()["packet_fresh"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode",[MODE_LEGACY,MODE_SHADOW])
async def test_real_native_options_information_step_never_saves_or_reloads(hass,monkeypatch,mode):
    e=entry(hass,mode=mode);clock=[0.0];t=HeatingTracker(hass,e,clock=lambda:clock[0]);t.online=True;send(t,raw())
    hass.data.setdefault("open_thermostat",{})[e.entry_id]={"heating_tracker":t}
    before=(deepcopy(dict(e.data)),deepcopy(dict(e.options)));reload=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    f=ShadowOptionsFlow();f.hass=hass;f.handler=e.entry_id
    info=await f.async_step_init({"information":"hot_water","warmWaterTemperature":99,"password":"PRIVATE"})
    assert info["type"]=="form" and info["step_id"]=="hot_water" and not info["data_schema"].schema
    assert "classic_observed" in info["description_placeholders"]["status"] and "PRIVATE" not in str(info)
    end=await f.async_step_hot_water({});assert end["type"]=="abort"
    assert (dict(e.data),dict(e.options))==before;reload.assert_not_awaited()


@pytest.mark.asyncio
async def test_diagnostics_and_dashboard_render_only_owned_renamed_capability_entity_without_secrets(hass):
    e=entry(hass,mode="legacy");t=HeatingTracker(hass,e);t.online=True;send(t,raw(password="NEVER_EXPORT",adapter_session_id="NEVER_EXPORT"))
    hass.data.setdefault("open_thermostat",{})[e.entry_id]={"heating_tracker":t}
    d=await diagnostics.async_get_config_entry_diagnostics(hass,e)
    assert d["dhw"]["profile"]=="classic_observed" and "NEVER_EXPORT" not in json.dumps(d)
    ref=er.async_get(hass).async_get_or_create("sensor","open_thermostat","fixture_hub_dhw_capabilities",config_entry=e)
    er.async_get(hass).async_update_entity(ref.entity_id,new_entity_id="sensor.renamed_dhw_status")
    hass.states.async_set("sensor.renamed_dhw_status","classic_observed",t.dhw_snapshot())
    config=RoomDashboard(hass,"fixture",e.entry_id)._dashboard_config()
    from custom_components.open_thermostat.dashboard import view_cards
    diagnostics_view=next(v for v in config["views"] if v["path"]=="diagnostics")
    card=next(c for c in view_cards(diagnostics_view) if c["type"]=="markdown" and "Domestic hot water" in c["content"])
    rendered=Template(card["content"],hass).async_render()
    assert "58.3" in rendered and "unreliable_classic" in rendered and "source age" in rendered
    assert "NEVER_EXPORT" not in rendered and "call-service" not in str(config)
    er.async_get(hass).async_update_entity("sensor.renamed_dhw_status",disabled_by=er.RegistryEntryDisabler.USER)
    assert "sensor.renamed_dhw_status" not in str(RoomDashboard(hass,"fixture",e.entry_id)._dashboard_config())


@pytest.mark.asyncio
async def test_no_migration_or_fictitious_dhw_contract_from_shadow_counter_capability(hass):
    e=entry(hass,version=1);old=er.async_get(hass).async_get_or_create("sensor","open_thermostat","fixture_hub_boiler_selected_hot_water_temperature",config_entry=e)
    hass.states.async_set(old.entity_id,"60",{"unit_of_measurement":"°C"})
    original=hass.states.get(old.entity_id)
    hass.data.setdefault("open_thermostat",{})[e.entry_id]={"v1_runtime":SimpleNamespace(enabled=True),"v1_connection":SimpleNamespace(client=SimpleNamespace(metrics_payload={"protocolScope":"plus"}))}
    d=entry_snapshot(hass,e);assert d["transport"]=="shadow_metrics_only" and d["status"]=="metrics_only"
    assert all(not f["supported_read"] and f["value"] is None for f in d["fields"].values())
    assert hass.states.get(old.entity_id) is original and er.async_get(hass).async_get(old.entity_id).unique_id.endswith("selected_hot_water_temperature")


@pytest.mark.asyncio
async def test_new_dhw_reading_with_duplicate_room_sequence_updates_presentation_not_source_lease(hass):
    m=Model(hass);m.ready()
    observation={"schema":2,"boot_id":"a"*32,"source_ms":1000000,"observed_ms":1000000,
        "sequence":2,"ttl_ms":30000,"quality":"reported_plus_not_delivery_proof","valid":True,
        "ch":True,"dhw":False,"flame":True,"pump":True,"supply_c":60,"selected_flow_c":60,"modulation_pct":50}
    send(m.tracker,raw("plus_observed",roomEstimateObservation=observation));deadline=m.tracker._ems_deadline
    seen=[];remove=m.tracker.async_add_listener(lambda:seen.append(m.tracker.dhw_snapshot()))
    try:
        m.time=10;observation["source_ms"]=1010000
        send(m.tracker,raw("plus_observed",roomEstimateObservation=observation,currentWarmWaterTemperature=584))
        assert seen[-1]["fields"]["current_temperature"]["value"]==58.4
        assert m.tracker._ems_deadline==deadline==30
        m.time=30;m.tracker._tick();assert m.tracker.boiler_reading("dhw") is None
    finally:remove()


@pytest.mark.asyncio
@pytest.mark.parametrize("profile",["classic_observed","plus_observed"])
async def test_observed_family_alone_never_advertises_unreceived_optional_dhw_fields(hass,profile):
    m=Model(hass);send(m.tracker,{"protocolProfile":profile})
    s=m.tracker.dhw_snapshot();assert s["profile"]==profile
    assert all(not f["supported_read"] and f["value"] is None for f in s["fields"].values())
    send(m.tracker,{"protocolProfile":profile,"currentWarmWaterTemperature":"60"})
    assert not m.tracker.dhw_snapshot()["fields"]["current_temperature"]["supported_read"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field,name",[
    ("selectedWarmWaterTemperature","selected_temperature"),
    ("currentWarmWaterTemperature","current_temperature"),
    ("warmWaterFlow","flow"),
])
@pytest.mark.parametrize("value",[10**400,-10**400])
async def test_parent_oversize_json_integer_is_unknown_and_next_packet_recovers(hass,field,name,value):
    # These 401-digit integers are valid JSON far below the existing packet cap.
    # The actual MQTT callback must reach its unchanged source-validation path.
    m=Model(hass);m.ready()
    send(m.tracker,raw("plus_observed",**{field:value}))
    f=m.tracker.dhw_snapshot()["fields"][name]
    assert f["value"] is None and not f["supported_read"]
    assert f["quality"]=="invalid_or_missing"
    assert not m.tracker.ems_available()
    assert not m.tracker.dhw_snapshot()["write_supported"]
    send(m.tracker,raw("plus_observed"))
    f=m.tracker.dhw_snapshot()["fields"][name]
    assert f["value"] is not None and f["supported_read"]
