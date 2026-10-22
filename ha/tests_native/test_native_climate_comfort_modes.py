"""New native HVAC presentation must reuse, not bypass, existing comfort."""
import pytest
from homeassistant.components.climate.const import HVACMode
from homeassistant.exceptions import HomeAssistantError
from custom_components.open_thermostat.v1_climate import ShadowRoom
from test_comfort_interop import comfort,command,observe

@pytest.mark.asyncio
async def test_hvac_off_auto_reuses_negotiated_comfort_and_clears_old_boost(comfort):
    runtime,client,bus,room,other=comfort
    await bus.start();await observe(runtime,client,bus,room);await observe(runtime,client,bus,other)
    entity=ShadowRoom("fixture",room,runtime)
    await command(bus,runtime.async_comfort(room.room_id,"boost",temperature=23,duration_ms=60000))
    assert entity.target_temperature==23 and entity.hvac_mode==HVACMode.HEAT
    await command(bus,entity.async_set_hvac_mode(HVACMode.OFF))
    assert entity.hvac_mode==HVACMode.OFF and entity.target_temperature is None
    assert runtime.decisions[other.room_id].target_centi_c==2100
    await command(bus,entity.async_set_hvac_mode(HVACMode.HEAT))
    assert entity.hvac_mode==HVACMode.HEAT and entity.target_temperature==21
    assert runtime.decisions[room.room_id].comfort_mode=="auto"
    assert runtime.decisions[room.room_id].override_remaining_ms==0

@pytest.mark.asyncio
async def test_hvac_heat_cannot_override_an_open_zone_window(comfort,hass):
    runtime,client,bus,room,other=comfort
    await bus.start();await observe(runtime,client,bus,room);await observe(runtime,client,bus,other)
    entity=ShadowRoom("fixture",room,runtime)
    hass.states.async_set(room.window.entity_id,"on")
    await hass.async_block_till_done()
    await observe(runtime,client,bus,room)
    await command(bus,entity.async_set_hvac_mode(HVACMode.HEAT))
    state=runtime.decisions[room.room_id]
    assert state.target_source=="window" and state.target_centi_c is None and not state.demand
    # Selected heating mode is not falsely displayed as actual heating.
    assert entity.hvac_mode==HVACMode.HEAT and entity.hvac_action=="idle"
    assert runtime.decisions[other.room_id].target_centi_c==2100

@pytest.mark.asyncio
async def test_comfort_capability_loss_never_falls_back_to_legacy_command(comfort):
    runtime,client,bus,room,_=comfort
    await bus.start();await observe(runtime,client,bus,room)
    entity=ShadowRoom("fixture",room,runtime)
    client.comfort_supported=False
    before=list(bus.transcript)
    with pytest.raises(HomeAssistantError):
        await entity.async_set_hvac_mode(HVACMode.OFF)
    assert bus.transcript==before
    assert not client.pending
