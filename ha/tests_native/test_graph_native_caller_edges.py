"""Native caller rejections use actual Store/config lifecycle, no dependency stubs."""
from copy import deepcopy
from dataclasses import replace
import pytest
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.storage import Store
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.graph_draft_compile import GraphDraftSource
from custom_components.open_thermostat.graph_control_source import GraphControllerEntrySource
from custom_components.open_thermostat.v1_wire import canonical,digest
from test_graph_native_caller import native_caller,emit,saved_graph

@pytest.mark.asyncio
@pytest.mark.parametrize("native_caller",["drop_snapshot"],indirect=True)
async def test_source_staging_and_ack_never_replace_fresh_actual_snapshot(native_caller):
    n=native_caller
    assert not n.client.ready and n.client.journal["accepted"] is None
    assert n.client.journal["staged"]["config"]==n.projected
    n.drop_snapshot=False
    await n.client.message("ha/snapshot_request","snapshot",{})
    await n.drain()
    assert n.client.ready and n.client.journal["accepted"]["config"]==n.projected
    emit(dict(scenario="staged_and_ack_wait_for_actual_fresh_cpp_snapshot",physical_outputs_enabled=False))

@pytest.mark.asyncio
@pytest.mark.parametrize("failure",["control_pin","tuple","source_binding","draft","graph_store","future",
    "data_owner","owner","existing_control_journal"])
async def test_source_or_native_tuple_draft_owner_conflict_fails_before_publish_and_preserves_journal(native_caller,hass,monkeypatch,failure):
    n=native_caller
    await n.stop()
    source=n.profile
    journal=n.client.store;before=await journal.async_load()
    if failure=="control_pin":source=replace(source,controller=replace(source.controller,config_digest="0"*64))
    elif failure=="tuple":
        record=source.record();record["config"]["rooms"][0]["base_centi_c"]+=50
        record["config_digest"]=digest(record["config"])
        candidate=replace(source,accepted_record_json=canonical(record))
        source=replace(candidate,controller=replace(source.controller,config_digest=digest(candidate.projection())))
    elif failure=="source_binding":
        record,bindings=source.graph.draft_source.documents()
        sensor="s_"+n.graph.binding.room_id
        bindings[sensor]["unique_id"]="foreign"
        graph=replace(source.graph,draft_source=GraphDraftSource(canonical(record),canonical(bindings)))
        source=replace(source,graph=graph)
    elif failure=="draft":
        sub=next(s for s in n.graph.parent.subentries.values() if s.subentry_type=="zone")
        data=dict(sub.data);data["base_centi_c"]+=50
        hass.config_entries.async_update_subentry(n.graph.parent,sub,data=data)
    elif failure=="graph_store":
        graph_store=Store(hass,1,"open_thermostat.graph_shadow."+n.graph.parent.entry_id)
        state=await graph_store.async_load();state["accepted"]=None;await graph_store.async_save(state)
    elif failure=="future":source=replace(source,schema=2)
    elif failure=="data_owner":monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",source.graph)
    elif failure=="owner":source=replace(source,controller=replace(source.controller,adapter_id="another_owner"))
    elif failure=="existing_control_journal":
        other=deepcopy(before);other["accepted"]["config"]["revision"]+=1
        other["accepted"]["config_digest"]=digest(other["accepted"]["config"])
        await journal.async_save(other);before=other
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(source,))
    publishes=[]
    from homeassistant.components import mqtt
    async def no_publish(*args,**kwargs):publishes.append(args)
    monkeypatch.setattr(mqtt,"async_publish",no_publish)
    with pytest.raises((ConfigEntryError,ValueError)):
        await integration.async_setup_entry(hass,n.graph.parent)
    assert not publishes and await journal.async_load()==before
    assert not hass.data.get("open_thermostat",{}).get(n.graph.parent.entry_id,{}).get("v1_connection")
    emit(dict(scenario="native_setup_reject_"+failure,existing_journal_preserved=True,physical_outputs_enabled=False))

@pytest.mark.asyncio
async def test_graph_store_drift_during_native_control_store_await_cannot_attach_owner(native_caller,hass,monkeypatch):
    n=native_caller;await n.stop()
    control_store=n.client.store;control_before=await control_store.async_load()
    graph_store=Store(hass,1,"open_thermostat.graph_shadow."+n.graph.parent.entry_id)
    graph_before=await graph_store.async_load()
    real=control_store.async_load;loads=0
    async def changed():
        nonlocal loads
        value=await real();loads+=1
        if loads==2:
            corrupt=deepcopy(graph_before);corrupt["accepted"]=None
            await graph_store.async_save(corrupt)
        return value
    monkeypatch.setattr(control_store,"async_load",changed)
    import custom_components.open_thermostat.v1_mqtt as connection_module
    monkeypatch.setattr(connection_module,"Store",lambda *args,**kwargs:control_store)
    with pytest.raises(ValueError,match="graph_control_store_changed"):
        await integration.async_setup_entry(hass,n.graph.parent)
    assert await real()==control_before
    assert not hass.data.get("open_thermostat",{}).get(n.graph.parent.entry_id,{}).get("v1_connection")
    emit(dict(scenario="graph_storeawait_drift_no_control_owner",existing_control_journal_preserved=True,physical_outputs_enabled=False))
