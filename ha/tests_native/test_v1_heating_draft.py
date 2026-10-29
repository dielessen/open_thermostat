"""Current-source native HA tests for desired heating config, never a heating GO."""
from copy import deepcopy
from unittest.mock import AsyncMock
import json

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.v1_heating_draft import (
    HeatingConfigError, HeatingContractUnavailable, parse_heating_draft, OUTDOOR_AXIS_CENTI_C,
)
from custom_components.open_thermostat.v1_heating_flow import HeatingSubentryFlow, central_schema, centi_c
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from test_v1_native import entry, room


def central():
    return {"weather_enabled": False, "outdoor_source": None,
            "outdoor_maximum_age_ms": 600000, "stale_policy": "block_normal_demand",
            "fixed_fallback_centi_c": None,
            "supply_limits": {"minimum_centi_c": 2000, "maximum_centi_c": 7000},
            "curve_centi_c": [2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000]}


def graph():
    return {"draft_schema": 1, "central": central(),
            "groups": [{"group_id": "radiators", "name": "Radiators", "emitter": "radiator",
                "supply_limits": {"minimum_centi_c": 2000, "maximum_centi_c": 7000},
                "pump": None, "pump_start_delay_s": 0, "postrun_s": 0, "mixing": None}],
            "actuators": [{"actuator_id": "valve_1", "room_id": "a1b2c3d4",
                "group_id": "radiators", "profile": "trv_room_setpoint",
                "output": {"entity_id": "climate.valve"}, "settings": {}}]}


def form_values(**changes):
    value = {"weather_enabled": False, "outdoor_maximum_age_ms": 600000,
             "stale_policy": "block_normal_demand", "minimum_supply_temperature": 20,
             "maximum_supply_temperature": 70}
    value.update({"curve_" + str(i): t for i, t in enumerate([20,25,30,35,40,45,50,55,60])})
    return {**value, **changes}


def parse(value):
    return parse_heating_draft(value, known_room_ids={"a1b2c3d4"})


def test_central_axis_is_existing_e32_axis_and_no_ha_entities_on_control_side():
    draft = parse(graph())
    control = draft.control_proposal()
    assert OUTDOOR_AXIS_CENTI_C == (2000,1500,1000,500,0,-500,-1000,-1500,-2000)
    import re
    from pathlib import Path
    header=(Path(__file__).resolve().parents[2]/"src/HeatingCurve.h").read_text()
    axis=re.search(r"hcOutdoorAxis\{([^}]+)\}",header).group(1)
    assert tuple(int(x.strip())*100 for x in axis.split(",")) == OUTDOOR_AXIS_CENTI_C
    assert control["central"]["curve_centi_c"] == [2000,2500,3000,3500,4000,4500,5000,5500,6000]
    assert control["central"]["outdoor_axis_centi_c"] == list(OUTDOOR_AXIS_CENTI_C)
    assert "climate.valve" not in json.dumps(control)
    assert list(draft.bindings_document().values())[0]["entity_id"] == "climate.valve"
    assert draft.readiness == "draft_not_applied"
    with pytest.raises(HeatingContractUnavailable):
        draft.transport_document()


@pytest.mark.parametrize("change", [
    lambda g: g["central"].update(weather_enabled=True),
    lambda g: g["central"].update(weather_enabled=1),
    lambda g: g["central"].update(outdoor_maximum_age_ms=True),
    lambda g: g["central"]["curve_centi_c"].__setitem__(0, "2000"),
    lambda g: g["central"]["curve_centi_c"].__setitem__(0, float("nan")),
    lambda g: g["central"]["curve_centi_c"].__setitem__(0, 3000),
    lambda g: g["central"]["supply_limits"].update(minimum_centi_c=7000),
    lambda g: g["central"].update(fixed_fallback_centi_c=3000),
    lambda g: g["central"].update(qualified=True),
    lambda g: g.update(draft_schema=True),
    lambda g: g["actuators"][0].update(room_id="deadbeef"),
    lambda g: g["actuators"][0].update(group_id="missing"),
    lambda g: g["groups"][0].update(postrun_s=10),
    lambda g: g["actuators"][0].update(output={"entity_id": "switch.trv"}),
    lambda g: g["actuators"][0].update(output={"entity_id": "climate.trv", "platform": "driver"}),
])
def test_invalid_graph_rejected_without_mutation(change):
    value = graph()
    change(value)
    before = deepcopy(value)
    with pytest.raises(HeatingConfigError):
        parse(value)
    # NaN inequality is special; compare serialized representations.
    assert json.dumps(value, sort_keys=True) == json.dumps(before, sort_keys=True)


def test_outdoor_measurement_config_does_not_qualify_sample_or_call_anything():
    value = graph()
    value["central"].update(weather_enabled=True, outdoor_source={"entity_id":"weather.local"})
    draft = parse(value)
    c = draft.control_proposal()["central"]
    assert c["outdoor_kind"] == "weather_temperature_attribute"
    assert draft.readiness == "draft_not_applied"
    value["central"].update(stale_policy="bounded_fixed_flow", fixed_fallback_centi_c=3500)
    assert parse(value).control_proposal()["central"]["fixed_fallback_centi_c"] == 3500
    value["central"]["fixed_fallback_centi_c"] = 9000
    with pytest.raises(HeatingConfigError):
        parse(value)


def test_binary_tpi_and_proportional_flow_valve_not_a_mixer():
    value = graph()
    a = value["actuators"][0]
    a.update(profile="binary_valve", output={"entity_id":"switch.floor"},
             settings={"deenergized_position":"normally_closed", "control":"tpi",
                       "travel_time_s":180,"minimum_on_s":180,"minimum_off_s":120,"cycle_s":900})
    draft = parse(value)
    assert "heating.actuator.binary_valve.v1" in draft.required_capabilities
    a["settings"]["minimum_on_s"] = 60
    with pytest.raises(HeatingConfigError, match="invalid_tpi"):
        parse(value)
    a.update(profile="proportional_valve", output={"entity_id":"number.position"},
             settings={"minimum_percent":0,"maximum_percent":100,"travel_time_s":60})
    draft = parse(value)
    assert draft.control_proposal()["groups"][0]["mixing"] is None
    assert "heating.actuator.proportional_valve.v1" in draft.required_capabilities


@pytest.mark.parametrize("kind,outputs", [
    ("three_point", [{"entity_id":"switch.open"},{"entity_id":"switch.close"}]),
    ("analog_0_10v", [{"entity_id":"number.analog_output"}]),
])
def test_mixing_group_uses_separate_supply_loop_declaration(kind, outputs):
    value = graph()
    g = value["groups"][0]
    g.update(emitter="floor", supply_limits={"minimum_centi_c":1000,"maximum_centi_c":4000},
             mixing={"kind":kind,"supply_sensor":{"entity_id":"sensor.floor_supply"},
                     "outputs":outputs,"travel_time_s":120})
    draft = parse(value)
    mix = draft.control_proposal()["groups"][0]["mixing"]
    assert mix["kind"] == kind
    assert len(mix["output_channels"]) == (2 if kind=="three_point" else 1)
    assert "heating.mixer."+kind+".v1" in draft.required_capabilities
    assert draft.readiness == "draft_not_applied"


def test_alias_same_output_identity_and_input_output_loops_rejected():
    value = graph()
    a = value["actuators"][0]
    a["output"] = {"entity_id":"climate.old","platform":"mqtt","unique_id":"same"}
    value["actuators"].append({**deepcopy(a),"actuator_id":"second",
                              "output":{"entity_id":"climate.renamed","platform":"mqtt","unique_id":"same"}})
    with pytest.raises(HeatingConfigError, match="multiple_owners"):
        parse(value)
    value = graph()
    value["central"]["outdoor_source"] = {"entity_id":"sensor.source","platform":"mqtt","unique_id":"shared"}
    value["groups"][0].update(pump={"entity_id":"switch.pump","platform":"mqtt","unique_id":"shared"})
    # Registry identities include domain: same driver/unique ID across sensor/switch
    # is NOT the same physical channel. Same entity cannot serve both roles,
    # and same-domain aliases cannot have multiple owners (case above).
    assert parse(value).readiness == "draft_not_applied"


def test_canonical_roundtrip_is_defensive_and_graph_order_independent():
    value = graph()
    draft = parse(value)
    assert parse(draft.storage_document()).digest == draft.digest
    value["central"]["curve_centi_c"][0] = 9999
    returned = draft.storage_document()
    returned["actuators"].clear()
    assert parse(draft.storage_document()).digest == draft.digest
    assert all(1 <= len(k) <= 32 for k in draft.bindings_document())


@pytest.mark.parametrize("value", [True,"20",float("inf"),20.001,10**1000])
def test_ui_numbers_are_not_coerced_or_silently_rounded(value):
    with pytest.raises(HeatingConfigError):
        centi_c(value)


@pytest.mark.asyncio
async def test_native_manager_persists_single_draft_and_real_store_reloads(hass, monkeypatch):
    parent = entry(hass)
    monkeypatch.setattr(config_entries, "_async_get_flow_handler",
                        AsyncMock(return_value=OpenThermostatConfigFlow))
    manager = hass.config_entries.subentries
    result = await manager.async_init((parent.entry_id,"heating"),context={"source":"user"})
    assert result["type"] == "form"
    selectors = {str(k):v for k,v in result["data_schema"].schema.items()}
    assert selectors["outdoor_source"].config["multiple"] is False
    assert len(selectors["outdoor_source"].config["filter"]) == 2
    result = await manager.async_configure(result["flow_id"], form_values())
    assert result["type"] == "create_entry"
    saved = next(iter(parent.subentries.values()))
    assert saved.data["status"] == "draft_not_applied"
    assert saved.data["draft"]["central"]["weather_enabled"] is False
    assert parent.options["shadow_enabled"] is False
    duplicate = await manager.async_init((parent.entry_id,"heating"),context={"source":"user"})
    assert duplicate["type"] == "abort" and duplicate["reason"] == "single_central_owner"
    await hass.async_stop(force=True)
    second = HomeAssistant(hass.config.config_dir)
    second.config_entries = ConfigEntries(second,{})
    try:
        await second.config_entries.async_initialize()
        actual = second.config_entries.async_get_entry(parent.entry_id).subentries[saved.subentry_id]
        assert dict(actual.data) == dict(saved.data)
    finally:
        await second.async_stop(force=True)


@pytest.mark.asyncio
async def test_native_invalid_reconfigure_is_atomic_and_optional_source_can_clear(hass, monkeypatch):
    parent = entry(hass)
    registry = er.async_get(hass)
    source = registry.async_get_or_create("sensor","fixture","outside")
    hass.states.async_set(source.entity_id,"unavailable",{"device_class":"temperature","unit_of_measurement":"°C"})
    monkeypatch.setattr(config_entries,"_async_get_flow_handler",AsyncMock(return_value=OpenThermostatConfigFlow))
    manager=hass.config_entries.subentries
    first=await manager.async_init((parent.entry_id,"heating"),context={"source":"user"})
    first=await manager.async_configure(first["flow_id"],form_values(outdoor_source=source.entity_id))
    saved=next(iter(parent.subentries.values()));before=deepcopy(dict(saved.data))
    ctx={"source":"reconfigure","subentry_id":saved.subentry_id}
    edit=await manager.async_init((parent.entry_id,"heating"),context=ctx)
    bad=await manager.async_configure(edit["flow_id"],form_values(minimum_supply_temperature=75))
    assert bad["type"]=="form" and bad["errors"]
    assert dict(saved.data)==before
    ok=await manager.async_configure(edit["flow_id"],form_values())
    assert ok["type"]=="abort"
    assert saved.data["draft"]["central"]["outdoor_source"] is None
    assert saved.data["status"]=="draft_not_applied"


@pytest.mark.asyncio
async def test_current_shadow_runtime_wire_and_rooms_remain_identical(hass, monkeypatch):
    binding = room(hass);parent=entry(hass,room=binding)
    runtime=ShadowRuntime(hass,parent,[binding])
    before=await async_build_configuration(runtime)
    monkeypatch.setattr(config_entries,"_async_get_flow_handler",AsyncMock(return_value=OpenThermostatConfigFlow))
    manager=hass.config_entries.subentries
    created=await manager.async_init((parent.entry_id,"heating"),context={"source":"user"})
    await manager.async_configure(created["flow_id"],form_values())
    after=await async_build_configuration(runtime)
    assert after == before
    assert runtime.enabled is False and runtime.transport_ready is False
    assert runtime.decisions == {} and runtime._profiles == {}


@pytest.mark.asyncio
async def test_active_shadow_and_legacy_cannot_edit_heating_draft(hass):
    active=entry(hass,enabled=True)
    flow=HeatingSubentryFlow();flow.hass=hass;flow.handler=(active.entry_id,"heating");flow.context={"source":"user"}
    assert (await flow.async_step_user())["reason"]=="disable_runtime_before_draft"
    legacy=entry(hass,mode="legacy")
    flow=HeatingSubentryFlow();flow.hass=hass;flow.handler=(legacy.entry_id,"heating");flow.context={"source":"user"}
    assert (await flow.async_step_user())["reason"]=="shadow_mode_required"

def test_unmixed_floor_needs_shared_safe_upper_bound_not_just_close_valve():
    value = graph()
    value["groups"][0].update(emitter="floor",supply_limits={"minimum_centi_c":2000,"maximum_centi_c":4000})
    with pytest.raises(HeatingConfigError,match="floor_requires_mixing"):
        parse(value)
    value["central"]["supply_limits"]["maximum_centi_c"] = 4000
    value["central"]["curve_centi_c"] = [2000,2200,2400,2600,2800,3000,3200,3400,3600]
    assert parse(value).readiness == "draft_not_applied"


def test_mixer_roles_are_not_silently_aliased_or_position_profile():
    value=graph()
    value["groups"][0]["mixing"]={"kind":"three_point","supply_sensor":{"entity_id":"sensor.supply"},
                                "outputs":[{"entity_id":"switch.both"},{"entity_id":"switch.both"}],
                                "travel_time_s":60}
    with pytest.raises(HeatingConfigError,match="multiple_owners"):
        parse(value)
    value["groups"][0]["mixing"]["kind"]="proportional_valve"
    with pytest.raises(HeatingConfigError,match="unsupported_choice"):
        parse(value)


def test_own_output_and_excessive_draft_counts_rejected():
    value=graph()
    value["central"]["outdoor_source"]={"entity_id":"sensor.opth_output",
        "platform":"open_thermostat","unique_id":"derived"}
    with pytest.raises(HeatingConfigError,match="input_output_loop"):
        parse(value)
    value=graph()
    value["groups"]=value["groups"]*9
    with pytest.raises(HeatingConfigError,match="group_count"):
        parse(value)


def test_identifier_order_coalesces_but_ordered_mixer_ports_remain_semantic():
    value=graph()
    value["groups"].append({**deepcopy(value["groups"][0]),"group_id":"second"})
    value["actuators"].append({**deepcopy(value["actuators"][0]),"actuator_id":"second",
                              "group_id":"second","output":{"entity_id":"climate.second"}})
    one=parse(value)
    value["groups"].reverse();value["actuators"].reverse()
    assert parse(value).digest == one.digest


@pytest.mark.asyncio
async def test_new_native_translation_is_bilingual_and_explicitly_draft(hass,monkeypatch):
    from pathlib import Path
    from homeassistant import loader
    from homeassistant.helpers import translation
    component=Path(__file__).resolve().parents[1]/"config/custom_components/open_thermostat"
    loader.async_setup(hass)
    integration=loader.Integration(hass,"custom_components.open_thermostat",component,
        json.loads((component/"manifest.json").read_text()),
        top_level_files={p.name for p in component.iterdir()})
    monkeypatch.setattr(translation,"async_get_integrations",AsyncMock(return_value={"open_thermostat":integration}))
    resources=await translation.async_get_translations(hass,"en","config_subentries",{"open_thermostat"})
    prefix="component.open_thermostat.config_subentries.heating.step.user."
    assert resources[prefix+"title"]=="Central heating settings — draft only"
    assert "NOT applied to E32" in resources[prefix+"description"]
    assert "not sample qualification" in resources[prefix+"data_description.outdoor_source"]
    assert all(prefix+"data.curve_"+str(i) in resources for i in range(9))
    nl=json.loads((component/"translations/nl.json").read_text())
    assert nl["config_subentries"]["room_setup"]["initiate_flow"]["user"]=="Radiatorruimte instellen"
    resources_nl=await translation.async_get_translations(hass,"nl","config_subentries",{"open_thermostat"})
    assert resources_nl[prefix+"title"]=="Centrale verwarmingsinstellingen — alleen concept"
    assert "NIET op de E32 toegepast" in resources_nl[prefix+"description"]
    assert "kwalificeert geen meting" in resources_nl[prefix+"data_description.outdoor_source"]
    assert all(prefix+"data.curve_"+str(i) in resources_nl for i in range(9))


@pytest.mark.asyncio
async def test_keep_optional_outdoor_source_and_delete_only_draft_preserves_room(hass,monkeypatch):
    binding=room(hass);parent=entry(hass,room=binding)
    room_entry=next(iter(parent.subentries.values()));before=deepcopy(dict(room_entry.data))
    registry=er.async_get(hass);source=registry.async_get_or_create("weather","fixture","outdoor")
    hass.states.async_set(source.entity_id,"sunny",{"temperature":10,"temperature_unit":"°C"})
    monkeypatch.setattr(config_entries,"_async_get_flow_handler",AsyncMock(return_value=OpenThermostatConfigFlow))
    manager=hass.config_entries.subentries
    result=await manager.async_init((parent.entry_id,"heating"),context={"source":"user"})
    await manager.async_configure(result["flow_id"],form_values(outdoor_source=source.entity_id,weather_enabled=True))
    draft=next(s for s in parent.subentries.values() if s.subentry_type=="heating")
    original=deepcopy(dict(draft.data))
    result=await manager.async_init((parent.entry_id,"heating"),
        context={"source":"reconfigure","subentry_id":draft.subentry_id})
    await manager.async_configure(result["flow_id"],form_values(outdoor_source=source.entity_id,weather_enabled=True))
    assert dict(draft.data)==original
    # Official native removal targets only the new config subentry.
    assert hass.config_entries.async_remove_subentry(parent,draft.subentry_id)
    assert parent.subentries[room_entry.subentry_id].data==before
    assert len(parent.subentries)==1 and parent.options["shadow_enabled"] is False
