"""Actual native HA options selection of independently matched logical profile."""
from copy import deepcopy
from dataclasses import replace
import json
import pytest
from homeassistant import loader
from custom_components.open_thermostat.native_provisioning import (
    SOURCE_OPTION,propose_local_shadow_source,source_from_selection,local_device_descriptor)
from custom_components.open_thermostat.graph_shadow_validation import canonical
from custom_components.open_thermostat.v1_model import CONF_MODE,CONF_ENABLED,MODE_SHADOW
from test_native_control_plan import native_plan,native_two

async def source_flow(hass,parent,legacy=False):
    loader.async_setup(hass)
    component=await loader.async_get_integration(hass,"open_thermostat")
    await component.async_get_platform("config_flow")
    manager=hass.config_entries.options
    result=await manager.async_init(parent.entry_id)
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({
        "information":"installation_source",CONF_MODE:MODE_SHADOW,CONF_ENABLED:False,"adapter_id":"test_owner"}))
    assert result["step_id"]=="installation_source"
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({
        "controller_id":"e32_test","legacy_readback":legacy}))
    assert result["step_id"]=="installation_source_review"
    return manager,result

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True},{"local_source":True,"legacy":True}],indirect=True)
async def test_real_options_review_persists_independent_profile_then_normal_apply_uses_actual_factory(native_plan,hass,monkeypatch):
    import custom_components.open_thermostat as integration
    n=native_plan;old=n.source;await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    manager,result=await source_flow(hass,n.parent,old.policy.legacy_readback_reviewed)
    assert SOURCE_OPTION not in n.parent.options
    shown=result["description_placeholders"]
    from test_native_plan_gui import rendered,record
    translated=await rendered(hass,result)
    record("independent_source_review",result,translated)
    assert "Measurement/safety producers UNKNOWN" in translated
    assert "report TTL 120.0 s" in translated and "P=500 permille/°C" in translated
    assert "radiator: target" in translated and "floor: target" in translated
    assert old.policy.profile_digest in translated
    assert shown["fingerprint"]==old.policy.profile_digest and shown["descriptor"]==canonical(local_device_descriptor(old))
    # This does not connect/write/claim the E32 was provisioned. Actual firmware
    # descriptor was independently provisioned at fixture startup.
    writes=(await n.peer.request("status"))["writes"]
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({"confirm_source":True}))
    assert result["type"]=="create_entry" and not n.pending
    assert integration._selected_native_plan_source(n.parent)==old
    assert (await n.peer.request("status"))["writes"]==writes==0
    # Normal Settings save must preserve profile across the ordinary enable.
    result=await manager.async_init(n.parent.entry_id)
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({
        CONF_MODE:MODE_SHADOW,CONF_ENABLED:True,"adapter_id":"test_owner"}))
    assert result["type"]=="create_entry" and SOURCE_OPTION in n.parent.options
    await n.start();await n.handshake()
    assert not n.client.ready # Only source matched, no config apply.
    actual=await n.apply()
    assert n.client.ready and actual["config"]["profile_digest"]==old.policy.profile_digest
    assert (await n.peer.request("durable_readback"))["stored"]==canonical(actual["config"])
    selection=deepcopy(n.parent.options[SOURCE_OPTION])
    floor=next(v for v in n.parent.subentries.values() if v.subentry_type=="zone" and v.data["room_id"]==n.floor.room_id)
    hass.config_entries.async_update_subentry(n.parent,floor,data={**floor.data,"base_centi_c":2000})
    await hass.async_block_till_done()
    assert not n.client.ready
    await n.stop();await n.start();await n.handshake()
    assert not n.client.ready # Old exact config is not the new desired plan.
    changed=await n.apply()
    assert changed["config"]["revision"]==actual["config"]["revision"]+1
    assert changed["config"]["zones"][1]["base_centi_c"]==2000
    assert n.parent.options[SOURCE_OPTION]==selection and n.source.policy.profile_digest==old.policy.profile_digest
    saved=await n.peer.request("durable_readback")
    assert saved["writes"]==2 and saved["stored"]==canonical(changed["config"])
    assert sum(op=="initialize_native_local_source" for op,_,_ in n.peer.trace)==1
    # Exact durable plan survives an actual core boot; old ephemeral ownership
    # and UNKNOWN safety/sample state do not become restored physical authority.
    await n.stop();await n.peer.request("reboot",boot="local_source_reboot")
    await n.start();await n.event("connect");await n.handshake()
    assert n.client.ready and n.client.journal["accepted"]==changed
    assert (await n.peer.request("status"))["writes"]==2

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("change",["cancel","owner","registration","room_goal","registry","enabled"])
async def test_profile_review_cancel_or_native_drift_cannot_persist_or_send(native_plan,hass,monkeypatch,change):
    import custom_components.open_thermostat as integration
    n=native_plan;await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    manager,result=await source_flow(hass,n.parent)
    if change=="owner":hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"another"})
    elif change=="registration":monkeypatch.setattr(hass.config_entries,"async_get_entry",lambda _:None)
    elif change=="room_goal":
        sub=next(v for v in n.parent.subentries.values() if v.subentry_type=="zone")
        hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2200})
    elif change=="registry":
        from homeassistant.helpers import entity_registry as er
        er.async_get(hass).async_remove(n.rad.temperature.entity_id)
    elif change=="enabled":hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:True})
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({"confirm_source":change!="cancel"}))
    assert result["type"]=="abort"
    assert SOURCE_OPTION not in n.parent.options and not n.pending and (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_active_runtime_cannot_be_silently_rebound_by_source_form(native_plan,hass):
    n=native_plan
    loader.async_setup(hass);component=await loader.async_get_integration(hass,"open_thermostat")
    await component.async_get_platform("config_flow")
    manager=hass.config_entries.options;result=await manager.async_init(n.parent.entry_id)
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({
        "information":"installation_source",CONF_MODE:MODE_SHADOW,CONF_ENABLED:False,"adapter_id":"test_owner"}))
    assert result["type"]=="abort" and result["reason"]=="native_source_runtime_off_required"
    assert SOURCE_OPTION not in n.parent.options and not n.pending

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_local_profile_still_cannot_bypass_actual_device_source_digest(native_plan,hass,monkeypatch):
    import custom_components.open_thermostat as integration
    n=native_plan;await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False})
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    manager,result=await source_flow(hass,n.parent,legacy=True) # Actual E32 fixture v1, not v2.
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({"confirm_source":True}))
    assert result["type"]=="create_entry"
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:True})
    await n.start()
    for _ in range(5):await n.event("tick");await n.drain()
    assert n.client.session is None and not n.client.ready and not n.pending
    assert (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("wrong",["unknown_schema","malformed","overlap","foreign_entry"])
async def test_invalid_or_overlapping_local_source_selection_never_falls_back(native_plan,hass,monkeypatch,wrong):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat.native_provisioning import source_selection
    from homeassistant.exceptions import ConfigEntryError
    n=native_plan;await n.stop()
    value=source_selection(n.source)
    if wrong=="unknown_schema":value["schema"]=99
    elif wrong=="malformed":value["profile"]={}
    elif wrong=="foreign_entry":hass.config_entries.async_update_entry(n.parent,unique_id="foreign_prefix")
    else:monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",(n.source,))
    if wrong!="overlap":monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,SOURCE_OPTION:value})
    with pytest.raises(ConfigEntryError):integration._selected_native_plan_source(n.parent)
    assert (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_source_profile_replacement_cannot_orphan_current_durable_plan(native_plan,hass,monkeypatch):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat.native_provisioning import source_selection
    n=native_plan;await n.apply();before=await n.peer.request("durable_readback");await n.stop()
    original=source_selection(n.source)
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,CONF_ENABLED:False,SOURCE_OPTION:original})
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    manager,result=await source_flow(hass,n.parent,legacy=True)
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({"confirm_source":True}))
    assert result["type"]=="abort" and result["reason"]=="native_source_replacement_unsupported"
    assert n.parent.options[SOURCE_OPTION]==original
    after=await n.peer.request("durable_readback")
    assert before["stored"]==after["stored"] and before["writes"]==after["writes"]==1
