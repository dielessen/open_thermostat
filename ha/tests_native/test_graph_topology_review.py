"""Actual native HA saved draft/registry -> SOURCE-only C++ review, no MQTT."""
from copy import deepcopy
from dataclasses import replace,asdict
import json,os,subprocess
from pathlib import Path
from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import entity_registry as er
from custom_components.open_thermostat.graph_topology_review import (
    TopologyReviewContext,native_topology_plan,prepare_saved_topology_review,validate_topology_review,
)
from custom_components.open_thermostat.graph_shadow_validation import (
    canonical,digest,GraphValidationError,GraphValidationContext,validate_graph_shadow,
)
from custom_components.open_thermostat.v1_model import ROOM_GRAPH_DRAFT
from custom_components.open_thermostat.v1_config_flow import reference
from custom_components.open_thermostat.v1_heating_draft import HeatingConfigError
from test_v1_native import room,entry

ROOT=Path(__file__).resolve().parents[2]
FIXTURES=[json.loads(line) for line in (ROOT/"test/fixtures/topology-review.jsonl").read_text().splitlines()]

def cpp(row):
    peer=os.environ.get("OPENTHERMOSTAT_TOPOLOGY_REVIEW_RUNNER",str(ROOT/"out/topology-review-runner"))
    run=subprocess.run([peer],input=canonical(row)+"\n",capture_output=True,text=True,timeout=15,check=True)
    assert not run.stderr
    return json.loads(run.stdout)


@pytest.mark.parametrize("fixture",FIXTURES,ids=lambda f:f["name"])
def test_shared_python_cpp_review_and_exact_readback(fixture):
    try:
        value=validate_topology_review(fixture["raw"],TopologyReviewContext(**fixture["context"]))
        py="source_topology_review_only"
    except GraphValidationError as err:
        py=err.code
    native=cpp(fixture)
    assert py==native["code"]==fixture["expected"]
    assert native["admission"] is native["applied"] is False
    assert native["boiler_output_enabled"] is native["actuator_output_enabled"] is False
    if py=="source_topology_review_only":
        assert native["readback"]==fixture["raw"]==canonical(value)
        assert [r["zone_id"] for r in native["rooms"]]==[r["zone_id"] for r in value["plan"]["rooms"]]
        assert [r["emitter"] for r in native["rooms"]]==["radiator","floor"]
    else:
        assert native["readback"]=="" and native["rooms"]==[]


@pytest.fixture
def native_two(hass):
    rad=room(hass);floor=room(hass,room_id="b1b2c3d4",suffix="floor")
    rad_output=rad.actuators[0].as_dict()
    rad=replace(rad,actuators=(),binding_mode=ROOM_GRAPH_DRAFT,
                minimum_target_centi_c=1600,maximum_target_centi_c=2400)
    floor=replace(floor,actuators=(),binding_mode=ROOM_GRAPH_DRAFT,
                  minimum_target_centi_c=1600,maximum_target_centi_c=2400)
    parent=entry(hass,enabled=False,room=rad)
    hass.config_entries.async_add_subentry(parent,ConfigSubentry(data=MappingProxyType(floor.as_dict()),
        subentry_type="zone",title="Floor",unique_id=floor.room_id))
    output=er.async_get(hass).async_get_or_create("switch","review_fixture","floor_output")
    raw=json.loads((ROOT/"test/fixtures/graph-shadow-validation.jsonl").read_text().splitlines()[0])
    old=json.loads(raw["raw"])["config"]
    central=deepcopy(old["central"])
    for k in ("outdoor_channel","outdoor_kind","outdoor_axis_centi_c"):central.pop(k)
    central["outdoor_source"]=None
    groups=[]
    for gid,emitter in (("radiators","radiator"),("floor","floor")):
        group=deepcopy(old["groups"][0]);group.pop("pump_channel")
        group.update(group_id=gid,emitter=emitter,name=gid,pump=None);groups.append(group)
    a=deepcopy(old["actuators"][0]);a.pop("output_channel")
    a.update(room_id=floor.room_id,group_id="floor",output=reference(hass,output.entity_id).as_dict())
    stored=dict(draft_schema=1,central=central,groups=groups,actuators=[
        dict(actuator_id="radiator_1",room_id=rad.room_id,group_id="radiators",
             profile="trv_room_setpoint",output=rad_output,settings={}),a])
    sub=ConfigSubentry(data=MappingProxyType({"draft":stored}),subentry_type="heating",
                      title="Synthetic two-room desired draft",unique_id="review_heating")
    hass.config_entries.async_add_subentry(parent,sub)
    return parent,rad,floor,sub,output

def context(plan):
    return TopologyReviewContext("fixture_controller","fixture_boot","fixture_session",1,0,1,1,digest(plan))


@pytest.mark.asyncio
async def test_actual_saved_two_room_registry_projection_is_exact_private_and_read_only(hass,native_two):
    parent,rad,floor,sub,output=native_two
    before={k:dict(v.data) for k,v in parent.subentries.items()}
    plan=native_topology_plan(hass,parent);cx=context(plan)
    raw=prepare_saved_topology_review(hass,parent,cx)
    result=cpp(dict(raw=raw,context=asdict(cx)))
    assert result["code"]=="source_topology_review_only" and result["readback"]==raw
    assert [r["emitter"] for r in plan["rooms"]]==["radiator","floor"]
    assert len({r[k] for r in plan["rooms"] for k in ("sensor_resource","output_resource")})==4
    for private in (rad.temperature.entity_id,floor.temperature.entity_id,output.entity_id,
                    rad.temperature.unique_id):
        assert private not in raw
    assert before=={k:dict(v.data) for k,v in parent.subentries.items()}
    assert not hass.data.get("open_thermostat")  # no transport, runtime or listener installed
    assert not result["applied"] and not result["admission"]
    assert len(raw.encode())<=4096
    # A review document is not a legacy apply envelope, even with a known source.
    old=json.loads((ROOT/"test/fixtures/graph-shadow-validation.jsonl").read_text().splitlines()[0])
    with pytest.raises(GraphValidationError):
        validate_graph_shadow(raw,old["mapping_raw"],GraphValidationContext(**old["context"]))


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation",["missing","disabled","new_identity","draft_changed","duplicate_output",
                                    "shared_sensor","reconnect","source_revision","registry_revision"])
async def test_native_changes_conflict_without_implicit_adoption(hass,native_two,mutation):
    parent,rad,floor,sub,output=native_two
    plan=native_topology_plan(hass,parent);cx=context(plan);raw=prepare_saved_topology_review(hass,parent,cx)
    registry=er.async_get(hass)
    if mutation=="missing":registry.async_remove(output.entity_id)
    elif mutation=="disabled":registry.async_update_entity(output.entity_id,disabled_by=er.RegistryEntryDisabler.USER)
    elif mutation=="new_identity":
        registry.async_remove(output.entity_id)
        registry.async_get_or_create("switch","review_fixture","replacement",suggested_object_id=output.entity_id.split(".")[1])
    elif mutation in ("draft_changed","duplicate_output"):
        stored=deepcopy(dict(sub.data))
        if mutation=="draft_changed":stored["draft"]["actuators"][1]["settings"]["cycle_s"]=1200
        else:stored["draft"]["actuators"][1]["output"]=stored["draft"]["actuators"][0]["output"]
        hass.config_entries.async_update_subentry(parent,sub,data=stored)
    elif mutation=="shared_sensor":
        z=next(s for s in parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==floor.room_id)
        data=dict(z.data);data["temperature"]=rad.temperature.as_dict()
        hass.config_entries.async_update_subentry(parent,z,data=data)
    else:
        key={"reconnect":"adapter_session_id","source_revision":"source_revision","registry_revision":"registry_revision"}[mutation]
        newer=replace(cx,**{key:"new_session" if mutation=="reconnect" else getattr(cx,key)+1})
        with pytest.raises(GraphValidationError):
            validate_topology_review(raw,newer)
        assert cpp(dict(raw=raw,context=asdict(newer)))["code"]=="context_conflict"
        return
    with pytest.raises((GraphValidationError,HeatingConfigError)):
        prepare_saved_topology_review(hass,parent,cx)
    # The source pin is not recomputed/auto-adopted after a registry or draft change.
    assert cx.plan_digest==digest(plan)


@pytest.mark.asyncio
async def test_cross_entry_output_owner_is_rejected_by_existing_native_validator(hass,native_two):
    parent,rad,floor,sub,output=native_two
    other=entry(hass,room=replace(room(hass,room_id="c1b2c3d4",suffix="other"),
                                actuators=(reference(hass,sub.data["draft"]["actuators"][0]["output"]["entity_id"]),)))
    with pytest.raises(HeatingConfigError,match="output_has_multiple_owners"):
        native_topology_plan(hass,parent)
    assert other is not parent


@pytest.mark.asyncio
async def test_native_config_store_restart_requires_registry_then_new_source_context(hass,native_two):
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.helpers import device_registry as dr,frame
    parent,*_=native_two
    before=native_topology_plan(hass,parent);cx=context(before)
    saved_subs={k:dict(v.data) for k,v in parent.subentries.items()}
    identities=[(e.entity_id,e.platform,e.unique_id) for e in er.async_get(hass).entities.values()]
    raw=prepare_saved_topology_review(hass,parent,cx)
    await hass.async_stop(force=True)
    second=HomeAssistant(hass.config.config_dir);second.config_entries=ConfigEntries(second,{})
    try:
        frame.async_setup(second)
        dr.async_setup(second)
        await dr.async_load(second)
        await er.async_load(second)
        await second.config_entries.async_initialize()
        restored=second.config_entries.async_get_entry(parent.entry_id)
        assert {k:dict(v.data) for k,v in restored.subentries.items()}==saved_subs
        # Registry producer is not running in this fresh native HA instance.
        # Saved config alone must not invent a missing registry binding.
        with pytest.raises(HeatingConfigError,match="binding_missing"):
            native_topology_plan(second,restored)
        for entity_id,platform,unique_id in identities:
            domain,object_id=entity_id.split(".",1)
            er.async_get(second).async_get_or_create(domain,platform,unique_id,suggested_object_id=object_id)
        assert native_topology_plan(second,restored)==before
        # Draft restoration does not restore a boot/session or an accepted review.
        new=replace(cx,boot_id="new_boot",adapter_session_id="new_session")
        with pytest.raises(GraphValidationError,match="context_conflict"):
            validate_topology_review(raw,new)
        result=cpp(dict(raw=raw,context=asdict(new)))
        assert result["code"]=="context_conflict" and not result["admission"]
        assert not second.data.get("open_thermostat")
    finally:
        await second.async_stop(force=True)


@pytest.mark.asyncio
async def test_actual_two_room_serialization_budget_evidence(hass,native_two):
    parent,*_=native_two
    from custom_components.open_thermostat.v1_heating_graph import validated_graph
    sub=next(s for s in parent.subentries.values() if s.subentry_type=="heating")
    draft=validated_graph(hass,parent,sub.data["draft"])
    plan=native_topology_plan(hass,parent);cx=context(plan)
    raw=prepare_saved_topology_review(hass,parent,cx)
    row=dict(scope="Actual saved native two-room desired draft; SOURCE-only projection, NOT qualified runtime configuration.",
        native_storage_bytes=len(canonical(draft.storage_document()).encode()),
        control_proposal_bytes=len(canonical(draft.control_proposal()).encode()),
        private_registry_bindings_bytes=len(canonical(draft.bindings_document()).encode()),
        plan_bytes=len(canonical(plan).encode()),review_envelope_bytes=len(raw.encode()),
        unchanged_existing_config_limit=4096,unchanged_existing_payload_limit=8192,
        unchanged_existing_runtime_rooms=1,review_rooms=2,target_requirement_rooms=8,
        hardware_qualified=False,applied=False,admission=False)
    if out:=os.environ.get("OPENTHERMOSTAT_TOPOLOGY_MEASUREMENT"):
        Path(out).write_text(json.dumps(row,indent=2)+"\n")
    assert row["review_envelope_bytes"]<=4096
