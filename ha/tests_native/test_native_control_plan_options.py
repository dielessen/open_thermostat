"""Actual native OptionsManager, no frontend/browser/device claim."""
import pytest
from homeassistant import loader
from custom_components.open_thermostat.v1_model import CONF_MODE,CONF_ENABLED,MODE_SHADOW
from test_native_control_plan import native_plan,native_two

@pytest.mark.asyncio
@pytest.mark.parametrize("confirm",[False,True])
async def test_native_OptionsManager_prepare_review_cancel_or_apply_current_readback(native_plan,hass,confirm):
    n=native_plan;ids=tuple(n.parent.subentries)
    loader.async_setup(hass)
    component=await loader.async_get_integration(hass,"open_thermostat")
    await component.async_get_platform("config_flow")
    manager=hass.config_entries.options
    result=await manager.async_init(n.parent.entry_id)
    assert result["step_id"]=="init"
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({
        "graph_action":"prepare",CONF_MODE:MODE_SHADOW,CONF_ENABLED:True,"adapter_id":"test_owner"}))
    assert result["step_id"]=="graph_review" and result["type"]=="form"
    assert not n.client.ready and (await n.peer.request("status"))["writes"]==0
    result=await manager.async_configure(result["flow_id"],result["data_schema"]({"confirm_apply":confirm}))
    if not confirm:
        assert result["type"]=="abort" and result["reason"]=="graph_review_cancelled"
        assert not n.pending and (await n.peer.request("status"))["writes"]==0
    else:
        assert result["step_id"]=="graph_status" and not n.client.ready
        await n.drain();await n.handshake()
        result=await manager.async_configure(result["flow_id"],result["data_schema"]({"status_action":"refresh"}))
        assert result["step_id"]=="graph_status"
        assert result["description_placeholders"]["verified"]=="True"
        assert "Two complete" in result["description_placeholders"]["data_scope"]
        assert n.client.ready and (await n.peer.request("status"))["writes"]==1
        await manager.async_configure(result["flow_id"],result["data_schema"]({"status_action":"close"}))
    assert tuple(n.parent.subentries)==ids and n.source is n.runtime.native_plan_source
