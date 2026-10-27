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
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
    _attr_min_temp = 5.0
    _attr_max_temp = 35.0
    _attr_target_temperature_step = 0.1
    _attr_should_poll = False

    def __init__(self, prefix, room, runtime):
        self.room, self.runtime = room, runtime
        if room.comfort is not None:
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = ["none","boost","away","frost","off"]
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
        return self.runtime.room_control_supported(self.room.room_id) and self.runtime.transport_ready and self.room.room_id in self.runtime.decisions

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
        state = self.runtime.decisions.get(self.room.room_id)
        if state is None:
            return None
        return HVACMode.OFF if state.target_source == "off" else HVACMode.HEAT

    async def async_set_hvac_mode(self, hvac_mode):
        await self.runtime.async_hvac_mode(self.room.room_id, hvac_mode)

    @property
    def hvac_action(self):
        state = self.runtime.decisions.get(self.room.room_id)
        return HVACAction.IDLE  # Shadow demand is never real heating.

    @property
    def preset_mode(self):
        state=self.runtime.decisions.get(self.room.room_id)
        return state.comfort_mode if state and state.comfort_mode not in {None,"auto","temporary","vacation"} else "none"

    async def async_set_preset_mode(self,preset_mode):
        await self.runtime.async_comfort(self.room.room_id,"auto" if preset_mode=="none" else preset_mode)

    async def async_set_comfort(self,mode,temperature=None,duration_ms=None,vacation_until_utc=0,
                               duration_minutes=None,vacation_until=None):
        from homeassistant.exceptions import HomeAssistantError
        if duration_minutes is not None:
            if duration_ms is not None or type(duration_minutes) is not int or not 1<=duration_minutes<=720:
                raise HomeAssistantError("Invalid/conflicting override duration")
            duration_ms=duration_minutes*60000
        if vacation_until is not None:
            from homeassistant.util import dt as dt_util
            parsed=dt_util.parse_datetime(vacation_until)
            if vacation_until_utc or parsed is None or parsed.tzinfo is None or parsed.microsecond:
                raise HomeAssistantError("Vacation end needs a date/time with explicit timezone")
            vacation_until_utc=int(parsed.timestamp())
        await self.runtime.async_comfort(self.room.room_id,mode,temperature=temperature,
            duration_ms=duration_ms,vacation_until_utc=vacation_until_utc)

    @property
    def extra_state_attributes(self):
        observation = self.runtime.observations[self.room.room_id]
        state = self.runtime.decisions.get(self.room.room_id)
        return {"integration_mode": "v1_shadow", "actuation_enabled": False,
                'entry_id':self.runtime.entry.entry_id,'room_id':self.room.room_id,
                "control_scope":getattr(self.runtime.native_plan_source or self.runtime.graph_controller_source,"profile_version",
                    "data_only" if self.runtime.graph_data_profile is not None else "native_api1_shadow"),
                "source_config_readback_verified":(self.runtime.native_plan_source is not None or self.runtime.graph_controller_source is not None) and self.runtime.transport_ready,
                "graph_DATA_grants_control":False,
                "boiler_output_enabled": False, "actuator_output_enabled": False,
                "transport_status": self.runtime.diagnostics.get("transport", "not_connected"),
                "controller_policy_status": self.runtime.diagnostics.get("controller_policy",
                    "source_identity_unverified" if self.runtime.controller_policy_source_profile is not None else "default_api1"),
                "simulated_demand": state.demand if state else False,
                "source_quality": observation.quality, "observed_temperature": observation.temperature_c,
                "firmware_reason": state.reason if state else "wire_not_attached",
                "target_source": state.target_source if state else None,
                "comfort_mode": state.comfort_mode if state else None,
                "override_remaining_ms": state.override_remaining_ms if state else None,
                "override_remaining_minutes": (state.override_remaining_ms+59999)//60000 if state else None,
                "vacation_until_utc": state.vacation_until_utc if state else None,
                "comfort_context_sources": self.runtime.context_source_status(self.room.room_id),
                'manual_target_source': self.runtime.manual_target_status(self.room.room_id),
                "local_override_ends_on_presence_change": False,
                "default_override_minutes": self.room.comfort["temporary_ms"]//60000 if self.room.comfort is not None else 60,
                "actuator_profile": "C_unverified" if self.room.shadow_wire_supported else
                    "native_plan_shadow_only" if self.runtime.native_plan_source is not None else
                    "source_graph_shadow_only" if self.runtime.graph_controller_source is not None else "graph_draft_not_applied",
                "diagnostic": self.runtime.diagnostics.get(self.room.room_id)}

    async def async_set_temperature(self, **kwargs):
        if "temperature" in kwargs:
            await self.runtime.async_set_temperature(self.room.room_id, kwargs["temperature"])
