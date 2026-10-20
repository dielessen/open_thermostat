"""Native room subentries/selectors; source qualification is never a GUI toggle."""
from __future__ import annotations

import uuid
import re
import probatio as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .const import CONF_CREATE_DASHBOARD, CONF_TOPIC_PREFIX, DOMAIN
from .v1_model import (
    CONF_ENABLED, CONF_MODE, MODE_LEGACY, MODE_SHADOW, ROOM_LIMIT,
    EntityReference, RoomBinding, integration_mode, target_centi,
)
from .v1_wire import identifier

def reference(hass, selection: str) -> EntityReference:
    registry = er.async_get(hass)
    entity_id = er.async_validate_entity_id(registry, selection)
    registered = registry.async_get(entity_id)
    if registered is None or registered.disabled_by is not None:
        raise ValueError("binding_missing")
    if registered.platform == DOMAIN:
        raise ValueError("loop_binding")
    return EntityReference(entity_id, registered.platform, registered.unique_id)

def validate_room(hass, entry, user_input: dict, old_subentry=None) -> RoomBinding:
    room_id = old_subentry.data["room_id"] if old_subentry else user_input["room_id"]
    sensor = reference(hass, user_input["temperature_entity"])
    actuators = tuple(reference(hass, x) for x in user_input["actuator_entities"])
    physical = reference(hass, user_input["setpoint_entity"]) if user_input.get("setpoint_entity") else None
    room = RoomBinding.from_dict({
        "room_id": room_id, "name": user_input["name"], "temperature": sensor.as_dict(),
        "actuators": [x.as_dict() for x in actuators],
        "setpoint": physical.as_dict() if physical else None,
        "maximum_age_ms": user_input.get("maximum_age_ms", 120000),
        "base_centi_c": target_centi(user_input["base_temperature"]) if "base_temperature" in user_input else user_input.get("base_centi_c", 2100),
        "schedule": reference(hass, user_input["schedule_entity"]).as_dict() if user_input.get("schedule_entity") else None,
        "minimum_target_centi_c": target_centi(user_input.get("minimum_target_temperature", 5)),
        "maximum_target_centi_c": target_centi(user_input.get("maximum_target_temperature", 35)),
    })
    sensor_state = hass.states.get(sensor.entity_id)
    if sensor_state and sensor_state.state not in ("unknown", "unavailable"):
        if sensor_state.attributes.get("device_class") != "temperature":
            raise ValueError("not_temperature")
        if sensor_state.attributes.get("unit_of_measurement") not in ("°C", "°F"):
            raise ValueError("unsupported_unit")
    for subentry in entry.subentries.values():
        if subentry.subentry_type != "zone" or (old_subentry and subentry.subentry_id == old_subentry.subentry_id):
            continue
        other = RoomBinding.from_dict(dict(subentry.data))
        if room.room_id == other.room_id:
            raise ValueError("duplicate_room")
        if {x.identity() for x in room.actuators} & {x.identity() for x in other.actuators}:
            raise ValueError("duplicate_actuator")
    return room

class V1FlowMixin:
    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["legacy", "shadow"])

    async def async_step_shadow(self, user_input=None):
        # Generated once per flow, not a shared owner identity or a redraw nonce.
        if not hasattr(self, "_shadow_adapter_id"):
            self._shadow_adapter_id = uuid.uuid4().hex
        errors = {}
        if user_input is not None:
            prefix = user_input[CONF_TOPIC_PREFIX]
            owner = user_input.get("adapter_id", self._shadow_adapter_id)
            if not isinstance(owner, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,32}", owner) is None:
                errors["base"] = "invalid_adapter_id"
            elif not identifier(prefix):
                errors["base"] = "invalid_topic"
            else:
                # Same unique identity as legacy: no parallel writers for a prefix.
                await self.async_set_unique_id(prefix)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"OpenThermostat shadow ({prefix})",
                    data={CONF_TOPIC_PREFIX: prefix, CONF_MODE: MODE_SHADOW,
                          "adapter_id": owner},
                    options={CONF_MODE: MODE_SHADOW, CONF_ENABLED: False,
                             CONF_CREATE_DASHBOARD: False},
                )
        return self.async_show_form(step_id="shadow", data_schema=vol.Schema({
            vol.Required(CONF_TOPIC_PREFIX, default="ib-therm"): str,
            vol.Required("adapter_id", default=self._shadow_adapter_id): vol.Match(r"^[A-Za-z0-9_-]{1,32}$"),
        }), errors=errors)

    @classmethod
    @callback
    def async_get_supported_subentry_types(cls, config_entry):
        return {"zone": ZoneSubentryFlow} if integration_mode(config_entry) == MODE_SHADOW else {}

class ShadowOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            mode = user_input[CONF_MODE]
            owner = user_input.get("adapter_id", self.config_entry.options.get(
                "adapter_id", self.config_entry.data.get("adapter_id", "")))
            valid_owner = isinstance(owner, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", owner) is not None
            if mode == MODE_SHADOW and not valid_owner:
                errors["base"] = "invalid_adapter_id"
            elif mode == MODE_SHADOW and not identifier(self.config_entry.data[CONF_TOPIC_PREFIX]):
                # Match the first E32 wire profile without renaming legacy IDs.
                errors["base"] = "invalid_topic"
            else:
                data = {
                    CONF_MODE: mode,
                    CONF_ENABLED: mode == MODE_SHADOW and user_input.get(CONF_ENABLED, False),
                    CONF_CREATE_DASHBOARD: user_input.get(CONF_CREATE_DASHBOARD, False),
                }
                if valid_owner:
                    data["adapter_id"] = owner
                return self.async_create_entry(data=data)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_MODE, default=integration_mode(self.config_entry)):
                selector.SelectSelector({"options": [MODE_LEGACY, MODE_SHADOW]}),
            vol.Optional(CONF_ENABLED, default=self.config_entry.options.get(CONF_ENABLED, False)): bool,
            vol.Optional(CONF_CREATE_DASHBOARD, default=self.config_entry.options.get(CONF_CREATE_DASHBOARD, False)): bool,
            vol.Optional("adapter_id", default=self.config_entry.options.get("adapter_id", self.config_entry.data.get("adapter_id", ""))): str,
        }), errors=errors)

class ZoneSubentryFlow(config_entries.ConfigSubentryFlow):
    def _schema(self, data=None, *, reconfigure=False):
        data = data or {}
        registry = er.async_get(self.hass)
        def display(ref):
            if ref.get("platform") is not None and ref.get("unique_id") is not None:
                return registry.async_get_entity_id(ref["entity_id"].split(".", 1)[0], ref["platform"], ref["unique_id"]) or ref["entity_id"]
            return ref.get("entity_id", "")
        physical = data.get("setpoint")
        # Suggested values keep the current selection visible without reinserting
        # it when the user clears an optional selector in the native form.
        physical_marker = vol.Optional("setpoint_entity", description={"suggested_value": display(physical)}) if physical else vol.Optional("setpoint_entity")
        schedule_marker = vol.Optional("schedule_entity", description={"suggested_value": display(data["schedule"])}) if data.get("schedule") else vol.Optional("schedule_entity")
        items = {
            vol.Required("name", default=data.get("name", "")): str,
            vol.Required("temperature_entity", default=display(data.get("temperature", {}))):
                selector.EntitySelector({"filter": {"domain": "sensor", "device_class": "temperature"}}),
            vol.Required("actuator_entities", default=[display(x) for x in data.get("actuators", [])]):
                selector.EntitySelector({"filter": {"domain": "climate"}, "multiple": True}),
            schedule_marker: selector.EntitySelector({"filter": {"domain": "schedule"}}),
            vol.Required("base_temperature", default=data.get("base_centi_c", 2100) / 100):
                selector.NumberSelector({"min": 5, "max": 35, "step": 0.1,
                                         "unit_of_measurement": "°C", "mode": "box"}),
            vol.Required("minimum_target_temperature", default=data.get("minimum_target_centi_c", 500) / 100):
                selector.NumberSelector({"min": 5, "max": 35, "step": 0.1,
                                         "unit_of_measurement": "°C", "mode": "box"}),
            vol.Required("maximum_target_temperature", default=data.get("maximum_target_centi_c", 3500) / 100):
                selector.NumberSelector({"min": 5, "max": 35, "step": 0.1,
                                         "unit_of_measurement": "°C", "mode": "box"}),
            physical_marker:
                selector.EntitySelector({"filter": [{"domain": "climate"}, {"domain": "number"}]}),
            vol.Required("maximum_age_ms", default=data.get("maximum_age_ms", 120000)):
                vol.All(int, vol.Range(min=1000, max=86400000)),
        }
        if not reconfigure:
            items[vol.Required("room_id", default=uuid.uuid4().hex[:8])] = str
        return vol.Schema(items)

    async def _step(self, user_input, reconfigure):
        entry = self._get_entry()
        old = self._get_reconfigure_subentry() if reconfigure else None
        errors = {}
        if integration_mode(entry) != MODE_SHADOW:
            return self.async_abort(reason="shadow_mode_required")
        zones = [s for s in entry.subentries.values() if s.subentry_type == "zone"]
        if not old and len(zones) >= ROOM_LIMIT:
            return self.async_abort(reason="room_limit")
        if user_input is not None:
            try:
                room = validate_room(self.hass, entry, user_input, old)
            except (KeyError, ValueError, vol.Invalid) as err:
                message = str(err)
                errors["base"] = message if message in {
                    "binding_missing", "loop_binding", "not_temperature", "unsupported_unit",
                    "duplicate_room", "duplicate_actuator", "invalid_target_range",
                } else "invalid_binding"
            else:
                if old:
                    # Parent runtime uses an update listener. Do not combine with
                    # ConfigSubentryFlow.async_update_reload_and_abort.
                    return self.async_update_and_abort(
                        entry, old, title=room.name, unique_id=room.room_id, data=room.as_dict())
                return self.async_create_entry(
                    title=room.name, unique_id=room.room_id, data=room.as_dict())
        return self.async_show_form(
            step_id="reconfigure" if reconfigure else "user",
            data_schema=self._schema(dict(old.data) if old else None, reconfigure=reconfigure),
            errors=errors)

    async def async_step_user(self, user_input=None):
        return await self._step(user_input, False)

    async def async_step_reconfigure(self, user_input=None):
        return await self._step(user_input, True)
