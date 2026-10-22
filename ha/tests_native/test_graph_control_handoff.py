"""Native graph options/Store + fresh real C++ owner/projection/controller probe.
SOURCE/safety fixture selection is explicit SYNTHETIC test code, not HA activation.
"""
import asyncio,json,os
from pathlib import Path
from copy import deepcopy
import pytest
from custom_components.open_thermostat.graph_shadow_storage import GraphShadowJournal
from custom_components.open_thermostat.graph_shadow_validation import canonical,digest,GraphValidationError
from test_graph_draft_apply import saved_graph

PROBE=Path(os.environ.get("OPENTHERMOSTAT_GRAPH_CONTROL_PROBE","out/graph-control-projection-runner"))
def emit(row):
    if path:=os.environ.get("OPENTHERMOSTAT_HANDOFF_EVIDENCE"):
        with Path(path).open("a") as f:f.write(json.dumps(row,sort_keys=True)+"\n")

async def accepted(n):
    f=n.flow()
    review=await f.async_step_init({"graph_action":"prepare"})
    assert review["step_id"]=="graph_review"
    await f.async_step_graph_review({"confirm_apply":True});await n.drain()
    assert n.client.graph_ready and not n.client.ready and not n.runtime.transport_ready
    record=n.client.journal.state["accepted"]
    ctx=n.client._context()
    return record,GraphShadowJournal.review_key(record,ctx)

def fixture_source(record,anchor):
    # Separate declared reviewed SOURCE fixture; production never infers policy
    # or physical qualification from this tuple, a checkbox or graph_ready.
    cfg=record["config"];r=cfg["rooms"][0];a=cfg["actuators"][0]
    projected=dict(mapping_digest=cfg["mapping_digest"],mode="shadow",revision=cfg["revision"],schema=1,
        zones=[dict(actuator_id=a["actuator_id"],base_centi_c=r["base_centi_c"],max_age_ms=r["max_age_ms"],
            report_evidence=r["report_evidence"],schedule=r["schedule"],sensor_id=r["sensor_id"],zone_id=r["zone_id"])])
    source=dict(controller_id="e32_test",adapter_id="test_owner",qualification_digest=anchor,
        config_digest=record["config_digest"],mapping_digest=cfg["mapping_digest"],
        revision=cfg["revision"],mapping_revision=cfg["mapping_revision"],
        profile_digest="f"*64,expected_profile_digest="f"*64,control_digest=digest(projected),
        zone_id=r["zone_id"],sensor_id=r["sensor_id"],actuator_id=a["actuator_id"],
        minimum=r["minimum_target_centi_c"],maximum=r["maximum_target_centi_c"])
    return source,projected

async def probe(stored,source):
    process=await asyncio.create_subprocess_exec(str(PROBE),stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    async with asyncio.timeout(8):
        stdout,stderr=await process.communicate((canonical(dict(stored=stored,source=source))+"\n").encode())
    assert process.returncode==0,stderr.decode()
    value=json.loads(stdout)
    assert value["writes"]==0 and value["durable_unchanged"] and value["physical_outputs_enabled"] is False
    return value

@pytest.mark.asyncio
@pytest.mark.parametrize("saved_graph",[True],indirect=True)
async def test_native_options_store_cpp_owner_to_explicit_readonly_controller_prerequisite(saved_graph):
    n=saved_graph;record,key=await accepted(n)
    disk=await n.client.journal.store.async_load()
    exported=await n.client.async_reviewed_handoff_data(key)
    assert exported==record==disk["accepted"]
    assert await n.client.journal.store.async_load()==disk
    actual=await n.peer.request("durable_readback")
    stored=json.loads(actual["stored"])
    assert stored["config"]==record["config"] and stored["mapping"]==record["mapping"]
    source,projected=fixture_source(exported,n.profile.qualification_digest)
    result=await probe(actual["stored"],source)
    assert not result["fault"] and result["revision"]==record["config"]["revision"]
    assert result["digest"]==digest(projected) and result["reads"]==1
    state=result["controller_state"]
    assert not any(row["demand"] for row in state["zones"])
    assert state["boiler_output_enabled"] is state["actuator_output_enabled"] is False
    assert n.client.ready is False and n.runtime.decisions=={} # DATA never control.
    assert (await n.peer.request("status"))["writes"]==1
    emit(dict(scenario="native_options_store_actual_cpp_tuple_explicit_source_readonly_constructor",
        revision=result["revision"],control_digest=result["digest"],store_bytes=len(actual["stored"]),
        projected_config_bytes=len(canonical(projected)),view_object_bytes=result["view_object_bytes"],
        actual_controller_no_admission=True,full_ha_control_activation=False,physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("mutation",["boot","session","owner","revision","digest","mapping","extra"])
async def test_old_or_mismatched_review_cannot_export_even_if_graph_data_was_ready(saved_graph,mutation):
    n=saved_graph;_,key=await accepted(n);before=await n.client.journal.store.async_load()
    key=deepcopy(key)
    field={"boot":"boot_id","session":"adapter_session_id","owner":"adapter_id",
        "revision":"revision","digest":"config_digest","mapping":"mapping_digest"}.get(mutation)
    if field:key[field]=2 if field=="revision" else "mismatch"
    else:key["authority"]=True
    with pytest.raises(GraphValidationError,match="handoff_review_changed"):
        await n.client.async_reviewed_handoff_data(key)
    assert await n.client.journal.store.async_load()==before
    assert n.client.ready is False and not n.client.journal.verified
    emit(dict(scenario="reject_review_"+mutation,durable_unchanged=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("mode",["staged","expired","disconnect","store_drift","await_disconnect","await_expiry"])
async def test_stage_ack_only_expiry_disconnect_and_storeawait_cannot_export(saved_graph,monkeypatch,mode):
    n=saved_graph
    if mode=="staged":
        await n.connection.async_graph_command("prepare")
        ctx=n.client._context();key=GraphShadowJournal.review_key(n.client.journal.state["staged"],ctx)
    else:_,key=await accepted(n)
    j=n.client.journal;before=await j.store.async_load()
    if mode=="expired":n.peer.clock[0]+=10
    elif mode=="disconnect":await n.client.async_disconnected()
    elif mode=="store_drift":
        corrupt=deepcopy(before);corrupt["accepted"]=None
        await j.store.async_save(corrupt);before=corrupt
    elif mode=="await_expiry":
        real=j.store.async_load
        n.client.grant_until=n.peer.clock[0]+1
        async def expired():
            result=await real();n.peer.clock[0]+=2;return result
        monkeypatch.setattr(j.store,"async_load",expired)
    elif mode=="await_disconnect":
        real=j.store.async_load
        async def invalidated():
            result=await real();j.invalidate();return result
        monkeypatch.setattr(j.store,"async_load",invalidated)
    with pytest.raises(GraphValidationError):
        await n.client.async_reviewed_handoff_data(key)
    assert await j.store.async_load()==before
    assert n.client.ready is False
    assert (await n.peer.request("status"))["writes"]==(0 if mode=="staged" else 1)
    emit(dict(scenario="no_export_"+mode,physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("field",["config_digest","mapping_digest","qualification_digest","controller_id","adapter_id",
    "revision","mapping_revision","profile_digest","control_digest","sensor_id","actuator_id","minimum","maximum"])
async def test_separate_source_tuple_profile_and_binding_mismatches_preserve_cpp_durable(saved_graph,field):
    n=saved_graph;record,key=await accepted(n)
    exported=await n.client.async_reviewed_handoff_data(key)
    actual=await n.peer.request("durable_readback")
    source,_=fixture_source(exported,n.profile.qualification_digest)
    source[field]=(source[field]+1 if field in ("revision","mapping_revision","minimum","maximum")
                   else "0"*64 if field.endswith("digest") else "foreign")
    result=await probe(actual["stored"],source)
    assert result["fault"]
    assert (await n.peer.request("status"))["writes"]==1
    assert n.client.ready is False and record==exported
    emit(dict(scenario="source_constructor_reject_"+field,durable_unchanged=True,physical_outputs_enabled=False))
