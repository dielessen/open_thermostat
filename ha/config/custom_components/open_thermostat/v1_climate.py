"""Confirmed firmware shadow state, preserving legacy climate unique IDs."""
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode, HVACAction
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, CONF_TOPIC_PREFIX
from .v1_model import RoomBinding

async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]["v1_runtime"]
    for subentry in entry.subentries.values():
        if subentry.subentry_type == "zone":
            room = RoomBinding.from_dict(dict(subentry.data))
            async_add_entities([ShadowRoom(entry.data[CONF_TOPIC_PREFIX], room, runtime)],
                               config_subentry_id=subentry.subentry_id)

class ShadowRoom(ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0
    _attr_target_temperature_step = 0.1
    _attr_should_poll = False

    def __init__(self, prefix, room, runtime):
        self.room, self.runtime = room, runtime
        self._attr_min_temp = room.minimum_target_centi_c / 100
        self._attr_max_temp = room.maximum_target_centi_c / 100
        self._attr_unique_id = f"{prefix}_room_{room.room_id}_climate"
        hub = dr.async_get(runtime.hass).async_get_device_by_identifier((DOMAIN, prefix), runtime.entry.entry_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{prefix}_room_{room.room_id}")},
            name=f"OpenThermostat — {room.name}", manufacturer="intuibase",
            model="OpenThermostat room", **({"via_device_id": hub.id} if hub else {}))

    async def async_added_to_hass(self):
        self.async_on_remove(self.runtime.add_listener(self.async_write_ha_state))

    @property
    def available(self):
        return self.room.shadow_wire_supported and self.runtime.transport_ready and self.room.room_id in self.runtime.decisions

    @property
    def target_temperature(self):
        state = self.runtime.decisions.get(self.room.room_id)
        return state.target_centi_c / 100 if state and state.target_centi_c is not None else None

    @property
    def current_temperature(self):
        state = self.runtime.decisions.get(self.room.room_id)
        return state.current_centi_c / 100 if state and state.current_centi_c is not None else None

    @property
    def hvac_mode(self):
        return HVACMode.HEAT

    @property
    def hvac_action(self):
        state = self.runtime.decisions.get(self.room.room_id)
        return HVACAction.IDLE  # Shadow demand is never real heating.

    @property
    def extra_state_attributes(self):
        observation = self.runtime.observations[self.room.room_id]
        state = self.runtime.decisions.get(self.room.room_id)
        return {"integration_mode": "v1_shadow", "actuation_enabled": False,
                "boiler_output_enabled": False, "actuator_output_enabled": False,
                "simulated_demand": state.demand if state else False,
                "source_quality": observation.quality, "observed_temperature": observation.temperature_c,
                "firmware_reason": state.reason if state else "wire_not_attached",
                "actuator_profile": "C_unverified" if self.room.shadow_wire_supported else "graph_draft_not_applied",
                "diagnostic": self.runtime.diagnostics.get(self.room.room_id)}

    async def async_set_temperature(self, **kwargs):
        if "temperature" in kwargs:
            await self.runtime.async_set_temperature(self.room.room_id, kwargs["temperature"])
