"""Normal native options manager reaches existing SOURCE caller, offline only."""
from copy import deepcopy
from dataclasses import replace
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from homeassistant import loader
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow
from custom_components.open_thermostat.v1_model import CONF_MODE,CONF_ENABLED,MODE_SHADOW
import custom_components.open_thermostat as integration
from test_graph_native_caller import native_caller
from test_graph_draft_apply import saved_graph

@pytest_asyncio.fixture
async def options_caller(native_caller,hass,monkeypatch):
    reload=AsyncMock()
    monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    native_caller.options_reload=reload
    yield native_caller
    assert all(call.args==(native_caller.graph.parent.entry_id,) for call in reload.await_args_list)
    if native_caller.connection.closed:
        state=hass.data.get("open_thermostat",{}).get(native_caller.graph.parent.entry_id,{})
        assert set(state)<= {"graph_journal"}
        hass.data.get("open_thermostat",{}).pop(native_caller.graph.parent.entry_id,None)

def flow(hass,parent):
    f=ShadowOptionsFlow();f.hass=hass;f.handler=parent.entry_id;return f

def enable(parent,**kw):
    return {CONF_MODE:MODE_SHADOW,CONF_ENABLED:True,"adapter_id":parent.options.get("adapter_id"),**kw}

@pytest.mark.asyncio
async def test_actual_native_options_enable_existing_source_then_normal_entry_fresh_cpp_readback(options_caller,hass):
    n=options_caller
    await n.stop()
    hass.config_entries.async_update_entry(n.graph.parent,options={**n.graph.parent.options,CONF_ENABLED:False})
    before=(await n.graph.peer.request("durable_readback"))["stored"]
    # A normally loaded but disabled SOURCE entry still owns its existing
    # update listener. No transport/second controller is started while OFF.
    assert await integration.async_setup_entry(hass,n.graph.parent)
    state=hass.data["open_thermostat"][n.graph.parent.entry_id]
    assert state["v1_runtime"].enabled is False and "v1_connection" not in state
    loader.async_setup(hass)
    component=await loader.async_get_integration(hass,"open_thermostat")
    await component.async_get_platform("config_flow")
    assert integration._selected_graph_controller_source(n.graph.parent)==n.profile
    await n.profile.async_configuration(hass,n.graph.parent)
    assert await flow(hass,n.graph.parent)._graph_enable_error(MODE_SHADOW,True,"test_owner") is None
    manager=hass.config_entries.options
    r=await manager.async_init(n.graph.parent.entry_id)
    r=await manager.async_configure(r["flow_id"],r["data_schema"](enable(n.graph.parent)))
    assert r["type"]=="create_entry",r.get("errors")
    assert n.graph.parent.options[CONF_ENABLED] is True
    assert not n.publications
    await hass.async_block_till_done()
    n.options_reload.assert_awaited_once_with(n.graph.parent.entry_id)
    # Existing public reload I/O is the fixture boundary, not another worker.
    assert await integration.async_unload_entry(hass,n.graph.parent)
    await n.graph.parent._async_process_on_unload(hass)
    await n.start();assert not n.client.ready
    await n.event("disconnect");await n.event("connect");await n.event("tick");await n.drain()
    assert n.client.ready and n.runtime.transport_ready
    assert n.runtime.graph_controller_source==n.profile
    state=await n.graph.peer.request("durable_readback")
    assert state["stored"]==before and state["writes"]==1
    assert all(not d.demand for d in n.runtime.decisions.values())
    await n.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True)
    await n.observe();await n.observe()
    assert n.runtime.decisions[n.graph.binding.room_id].demand

@pytest.mark.asyncio
@pytest.mark.parametrize("bad",["default_none","invalid_pin","owner","data_conflict","draft_changed"])
async def test_options_cannot_create_source_authority_or_enable_mismatched_tuple(options_caller,hass,monkeypatch,bad):
    n=options_caller
    if bad=="default_none":monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",())
    elif bad=="invalid_pin":
        wrong=replace(n.profile.controller,config_digest="0"*64)
        monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(replace(n.profile,controller=wrong),))
    elif bad=="data_conflict":monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",n.graph.profile)
    elif bad=="draft_changed":
        room=next(s for s in n.graph.parent.subentries.values() if s.subentry_type=="zone")
        hass.config_entries.async_update_subentry(n.graph.parent,room,data={**room.data,"base_centi_c":2200})
    old=deepcopy(dict(n.graph.parent.options))
    request=enable(n.graph.parent,**({"adapter_id":"another_owner"} if bad=="owner" else {}))
    r=await flow(hass,n.graph.parent).async_step_init(request)
    assert r["type"]=="form" and r["errors"]
    assert dict(n.graph.parent.options)==old and not n.publications
    # A failed enable check does not silently disable or mutate a running owner.
    assert n.client is n.connection.client

@pytest.mark.asyncio
async def test_disable_still_available_when_selected_source_pin_is_invalid(options_caller,hass,monkeypatch):
    n=options_caller
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",("unqualified",))
    r=await flow(hass,n.graph.parent).async_step_init(enable(n.graph.parent,**{CONF_ENABLED:False}))
    assert r["type"]=="create_entry" and r["data"][CONF_ENABLED] is False
    assert not n.publications

@pytest.mark.asyncio
async def test_options_source_preflight_entry_changes_across_store_await_cannot_save(options_caller,hass,monkeypatch):
    n=options_caller
    from custom_components.open_thermostat.graph_control_source import GraphControllerEntrySource
    original=GraphControllerEntrySource.async_configuration
    async def changed(self,hass_,entry_):
        result=await original(self,hass_,entry_)
        hass.config_entries.async_update_entry(entry_,options={**entry_.options,"adapter_id":"changed_owner"})
        return result
    monkeypatch.setattr(GraphControllerEntrySource,"async_configuration",changed)
    r=await flow(hass,n.graph.parent).async_step_init(enable(n.graph.parent))
    assert r["type"]=="form" and r["errors"]
    assert n.graph.parent.options["adapter_id"]=="changed_owner"
    assert not n.publications

@pytest.mark.asyncio
async def test_normal_native_options_has_only_existing_listener_reload_owner(options_caller,hass):
    n=options_caller
    from homeassistant import config_entries
    assert issubclass(ShadowOptionsFlow,config_entries.OptionsFlow)
    assert not issubclass(ShadowOptionsFlow,config_entries.OptionsFlowWithReload)
    loader.async_setup(hass)
    component=await loader.async_get_integration(hass,"open_thermostat")
    await component.async_get_platform("config_flow")
    manager=hass.config_entries.options
    r=await manager.async_init(n.graph.parent.entry_id)
    r=await manager.async_configure(r["flow_id"],r["data_schema"](enable(n.graph.parent,**{CONF_ENABLED:False})))
    assert r["type"]=="create_entry" and n.graph.parent.options[CONF_ENABLED] is False
    await hass.async_block_till_done()
    n.options_reload.assert_awaited_once_with(n.graph.parent.entry_id)
    assert not n.publications

@pytest.mark.asyncio
async def test_active_graph_data_compiler_keeps_enable_fence_when_source_preflight_is_readonly(options_caller,hass):
    from custom_components.open_thermostat.graph_draft_compile import async_compile_saved_graph,async_compile_graph_data
    from custom_components.open_thermostat.graph_shadow_validation import GraphValidationError
    n=options_caller;await n.stop()
    hass.config_entries.async_update_entry(n.graph.parent,options={**n.graph.parent.options,CONF_ENABLED:False})
    context=n.profile.context(n.profile.record())
    with pytest.raises(GraphValidationError,match="unsupported_owner"):
        await async_compile_saved_graph(hass,n.graph.parent,context,n.profile.graph.draft_source)
    await async_compile_graph_data(hass,n.graph.parent,context,n.profile.graph.draft_source)
    assert not n.publications and (await n.graph.peer.request("status"))["writes"]==1
