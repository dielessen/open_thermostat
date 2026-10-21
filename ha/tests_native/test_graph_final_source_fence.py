"""Real final native DATA load cannot hide SOURCE/owner/native drift before stage."""
import inspect
from dataclasses import replace
import pytest
from homeassistant.helpers.storage import Store
from homeassistant.helpers import entity_registry as er
from homeassistant.exceptions import ConfigEntryError
import custom_components.open_thermostat as integration
from custom_components.open_thermostat.graph_shadow_storage import native_graph_journal
from test_graph_two_bridge import bridge,native_two

@pytest.mark.asyncio
@pytest.mark.parametrize("cause",["adapter","unique_id","topic","disabled","selected_none",
    "data_conflict","policy_conflict","room","registry","registry_feedback","native_journal"])
async def test_final_DATA_load_all_current_source_fences_precede_first_mirror_stage(bridge,hass,monkeypatch,cause):
    n=bridge;record=await n.apply();profile=n.source(record)
    await n.stop();await n.peer.request("disconnect")
    mirror=Store(hass,1,"open_thermostat.v1."+n.parent.entry_id)
    empty={"accepted":None,"staged":None};await mirror.async_save(empty)
    monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",None)
    monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",(profile,))
    real=Store.async_load;fired=False
    async def load(store):
        nonlocal fired
        result=await real(store)
        if (not fired and store.key=="open_thermostat.graph_shadow."+n.parent.entry_id
                and any(frame.function=="async_stage_graph_source_readback" for frame in inspect.stack())):
            fired=True
            if cause=="adapter":
                hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"another_owner"})
            elif cause=="unique_id":
                hass.config_entries.async_update_entry(n.parent,unique_id="another_entry")
            elif cause=="topic":
                hass.config_entries.async_update_entry(n.parent,data={**n.parent.data,"topic_prefix":"other_prefix"})
            elif cause=="disabled":
                hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"shadow_enabled":False})
            elif cause=="selected_none":
                monkeypatch.setattr(integration,"_GRAPH_CONTROLLER_ENTRY_SOURCES",())
            elif cause=="data_conflict":
                monkeypatch.setattr(integration,"_GRAPH_DATA_SOURCE_PROFILE",n.data_profile)
            elif cause=="policy_conflict":
                monkeypatch.setattr(integration,"_CONTROLLER_POLICY_SOURCE_PROFILES",
                    (replace(profile.controller,profile_digest="c"*64),))
            elif cause=="room":
                sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone" and s.data["room_id"]==n.rad.room_id)
                hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"base_centi_c":2200})
            elif cause=="registry":
                er.async_get(hass).async_remove(n.rad.temperature.entity_id)
            elif cause=="registry_feedback":
                er.async_get(hass).async_remove(n.feedback.entity_id)
            else:
                journal=native_graph_journal(hass,n.parent,n.data_profile.qualification_digest)
                journal._state={"accepted":None,"staged":record} # explicit cache fault, never a durable write
        return result
    monkeypatch.setattr(Store,"async_load",load)
    rejected=False
    try:
        await n.start("v1")
    except (ValueError,ConfigEntryError):
        rejected=True
    assert fired
    assert await mirror.async_load()==empty,"final source drift reached STAGED mirror"
    assert rejected and not n.pending
    assert (await n.peer.request("status"))["writes"]==1
