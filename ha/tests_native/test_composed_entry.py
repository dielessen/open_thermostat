"""Native HA entry/GUI boundaries; no replacement modules, services or network."""
import importlib.metadata
import pytest
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow

@pytest.mark.asyncio
async def test_actual_native_ha_declares_probatio_and_no_unknown_module_shim(hass):
    import probatio
    requires=importlib.metadata.requires("homeassistant")
    assert "probatio==0.13.0" in requires
    assert importlib.metadata.version("probatio")=="0.13.0"
    assert importlib.metadata.metadata("probatio")["License-Expression"]=="MIT"
    assert probatio.__file__ and "site-packages/probatio/" in probatio.__file__
    from homeassistant.helpers import config_validation
    assert config_validation.probatio is probatio

@pytest.mark.asyncio
@pytest.mark.parametrize("mode",["legacy","shadow"])
async def test_actual_native_gui_view_serializes_real_entry_forms(hass,mode):
    flow=OpenThermostatConfigFlow();flow.hass=hass;flow.handler="open_thermostat";flow.context={"source":"user"}
    form=await getattr(flow,"async_step_"+mode)()
    rendered=FlowManagerIndexView(hass.config_entries.flow)._prepare_result_json(form)
    assert rendered["step_id"]==mode
    assert isinstance(rendered["data_schema"],list) and rendered["data_schema"]
    assert any(field["name"]=="topic_prefix" for field in rendered["data_schema"])
