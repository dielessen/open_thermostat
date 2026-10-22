"""Compose existing native OptionsManager with the actual bounded two-target bridge."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import AsyncMock
import pytest
from homeassistant import loader
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.v1_model import CONF_MODE,CONF_ENABLED,MODE_SHADOW
from custom_components.open_thermostat.graph_floor_bridge import GraphFloorControllerEntrySource
from test_graph_two_bridge import bridge,native_two

async def select_reviewed_source(n,hass,monkeypatch,profile=None):
    record=await n.apply()
    profile=profile or n.source(record)
    wire=n.ctor_for(profile)
    old_worker=n.connection.worker
    await n.stop()
    await n.peer.request("disconnect")
    assert old_worker.done() and not n.pending
    selected=await n.peer.request("select_graph_floor_source",source=wire)
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(profile,))
    return profile,selected

async def manager(hass,parent):
    loader.async_setup(hass)
    component=await loader.async_get_integration(hass,"open_thermostat")
    await component.async_get_platform("config_flow")
    return hass.config_entries.options

def enable(parent):
    return {CONF_MODE:MODE_SHADOW,CONF_ENABLED:True,"adapter_id":parent.options["adapter_id"]}

@pytest.mark.asyncio
async def test_normal_options_phase_change_same_graph_store_two_room_targets_and_stop(bridge,hass,monkeypatch):
    n=bridge
    ids=tuple(n.parent.subentries)
    profile,selected=await select_reviewed_source(n,hass,monkeypatch)
    original=await n.peer.request("durable_readback")
    reload=AsyncMock()
    monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    assert await integration.async_setup_entry(hass,n.parent)
    state=hass.data["open_thermostat"][n.parent.entry_id]
    assert state["v1_runtime"].enabled is False and "v1_connection" not in state
    assert not n.pending
    manager_=await manager(hass,n.parent)
    result=await manager_.async_init(n.parent.entry_id)
    result=await manager_.async_configure(result["flow_id"],result["data_schema"](enable(n.parent)))
    assert result["type"]=="create_entry",result.get("errors")
    await hass.async_block_till_done()
    reload.assert_awaited_once_with(n.parent.entry_id)
    assert not n.pending
    # Fixture boundary is normal public reload I/O, not a second worker/owner.
    assert await integration.async_unload_entry(hass,n.parent)
    await n.parent._async_process_on_unload(hass)
    await n.start("v1")
    assert n.client.journal["accepted"] is None
    assert n.client.journal["staged"]["config"]==profile.projection()
    assert not n.client.ready and not n.runtime.transport_ready
    assert tuple(n.parent.subentries)==ids
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
    await n.event("connect");await n.event("tick");await n.drain()
    assert n.client.ready and n.runtime.transport_ready
    assert n.runtime.graph_controller_source==profile
    await n.settle(16,22)
    assert tuple(n.runtime.decisions[r.room_id].target_centi_c for r in (n.rad,n.floor))==(2100,1900)
    assert tuple(n.runtime.decisions[r.room_id].demand for r in (n.rad,n.floor))==(True,False), n.runtime.decisions
    await n.command(n.runtime.async_hvac_mode(n.rad.room_id,"off"))
    await n.samples(16,22)
    assert not any(x.demand for x in n.runtime.decisions.values())
    durable=await n.peer.request("durable_readback")
    assert durable["stored"]==original["stored"] and durable["writes"]==original["writes"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("cause",["wrong_pin","store_await_edit"])
async def test_native_options_phase_preflight_never_qualifies_wrong_or_changed_source(bridge,hass,monkeypatch,cause):
    n=bridge
    record=await n.apply()
    profile=n.source(record)
    if cause=="wrong_pin":
        profile=replace(profile,controller=replace(profile.controller,config_digest="0"*64))
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(profile,))
    if cause=="store_await_edit":
        original=GraphFloorControllerEntrySource.async_configuration
        async def after_store(self,hass_,entry_):
            value=await original(self,hass_,entry_)
            sub=next(s for s in entry_.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
            hass_.config_entries.async_update_subentry(entry_,sub,data={**sub.data,"base_centi_c":2200})
            return value
        monkeypatch.setattr(GraphFloorControllerEntrySource,"async_configuration",after_store)
    options=deepcopy(dict(n.parent.options))
    durable=await n.peer.request("durable_readback")
    before=n.connection.worker
    manager_=await manager(hass,n.parent)
    result=await manager_.async_init(n.parent.entry_id)
    result=await manager_.async_configure(result["flow_id"],result["data_schema"](enable(n.parent)))
    assert result["type"]=="form" and result["errors"]
    assert dict(n.parent.options)==options
    assert n.connection.worker is before and not before.done()
    assert not n.pending
    after=await n.peer.request("durable_readback")
    assert after["stored"]==durable["stored"] and after["writes"]==durable["writes"]==1
