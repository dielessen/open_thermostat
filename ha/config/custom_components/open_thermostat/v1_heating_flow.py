"""Native central-settings draft subentry; no control or shadow-wire changes.

One HA desired configuration owner. Only disabled shadow entries may edit this
draft; saving never asserts firmware acceptance, source freshness or actuation.
Group/actuator/mixer execution requires a later negotiated firmware contract.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import math
from typing import Any

import probatio as vol

from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er, selector

from .const import DOMAIN
from .v1_heating_draft import HeatingConfigError, parse_heating_draft
from .v1_model import CONF_ENABLED, MODE_SHADOW, integration_mode

HEATING_SUBENTRY = "heating"
FORM_FIELDS = {"weather_enabled", "outdoor_source", "outdoor_maximum_age_ms",
               "stale_policy", "fixed_fallback_temperature", "minimum_supply_temperature",
               "maximum_supply_temperature"} | {"curve_" + str(i) for i in range(9)}


def centi_c(value: Any) -> int:
    """User selector numbers only, no bool/string/coercion/implicit rounding."""
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise HeatingConfigError("invalid_temperature")
    try:
        scaled = Decimal(str(value)) * 100
        if scaled != scaled.to_integral_value():
            raise HeatingConfigError("temperature_precision")
        return int(scaled)
    except (InvalidOperation, OverflowError):
        raise HeatingConfigError("invalid_temperature") from None


def central_schema(data: dict | None = None) -> vol.Schema:
    """Public HA selectors; only measurement source is selected here."""
    central = (data or {}).get("central", {})
    limits = central.get("supply_limits", {"minimum_centi_c": 2000, "maximum_centi_c": 7000})
    curve = central.get("curve_centi_c", [2000, 2500, 3000, 3500, 4000, 4500, 5000, 5500, 6000])
    number = selector.NumberSelector({"min": 5, "max": 90, "step": 0.1,
                                     "unit_of_measurement": "°C", "mode": "box"})
    # suggested_value (not a default) means clearing an optional source is real.
    reference = central.get("outdoor_source")
    source_marker = (vol.Optional("outdoor_source", description={"suggested_value": reference["entity_id"]})
                     if reference else vol.Optional("outdoor_source"))
    fields = {
        vol.Required("weather_enabled", default=central.get("weather_enabled", False)): bool,
        source_marker: selector.EntitySelector({"filter": [
            {"domain": "sensor", "device_class": "temperature"}, {"domain": "weather"}]}),
        vol.Required("outdoor_maximum_age_ms", default=central.get("outdoor_maximum_age_ms", 600000)):
            vol.All(int, vol.Range(min=1000, max=86400000)),
        vol.Required("stale_policy", default=central.get("stale_policy", "block_normal_demand")):
            selector.SelectSelector({"options": ["block_normal_demand", "bounded_fixed_flow"],
                                     "translation_key": "heating_stale_policy"}),
        vol.Required("minimum_supply_temperature", default=limits["minimum_centi_c"] / 100): number,
        vol.Required("maximum_supply_temperature", default=limits["maximum_centi_c"] / 100): number,
    }
    fallback = central.get("fixed_fallback_centi_c")
    marker = (vol.Optional("fixed_fallback_temperature", description={"suggested_value": fallback / 100})
              if fallback is not None else vol.Optional("fixed_fallback_temperature"))
    fields[marker] = number
    for i, value in enumerate(curve):
        fields[vol.Required("curve_" + str(i), default=value / 100)] = number
    return vol.Schema(fields)


def draft_from_form(hass, user_input: dict, old: dict | None = None):
    if type(user_input) is not dict or user_input.keys() - FORM_FIELDS:
        raise HeatingConfigError("missing_or_unknown_fields")
    source = None
    if selection := user_input.get("outdoor_source"):
        registry = er.async_get(hass)
        entity_id = er.async_validate_entity_id(registry, selection)
        entity = registry.async_get(entity_id)
        if entity is None or entity.disabled_by is not None:
            raise HeatingConfigError("binding_missing")
        if entity.platform == DOMAIN:
            raise HeatingConfigError("loop_binding")
        domain = entity_id.split(".")[0]
        if domain not in ("sensor", "weather"):
            raise HeatingConfigError("wrong_entity_domain")
        state = hass.states.get(entity_id)
        # Offline entities remain configurable, but never become qualified.
        if domain == "sensor" and state is not None and state.state not in ("unknown", "unavailable"):
            if (state.attributes.get("device_class") != "temperature" or
                    state.attributes.get("unit_of_measurement") not in ("°C", "°F")):
                raise HeatingConfigError("not_temperature")
        source = {"entity_id": entity_id, "platform": entity.platform, "unique_id": entity.unique_id}
    central = {
        "weather_enabled": user_input["weather_enabled"],
        "outdoor_source": source,
        "outdoor_maximum_age_ms": user_input["outdoor_maximum_age_ms"],
        "stale_policy": user_input["stale_policy"],
        "fixed_fallback_centi_c": (centi_c(user_input["fixed_fallback_temperature"])
                                  if user_input.get("fixed_fallback_temperature") is not None else None),
        "supply_limits": {"minimum_centi_c": centi_c(user_input["minimum_supply_temperature"]),
                          "maximum_centi_c": centi_c(user_input["maximum_supply_temperature"])},
        "curve_centi_c": [centi_c(user_input["curve_" + str(i)]) for i in range(9)],
    }
    old = old or {}
    # Preserve existing declarations; do not silently overwrite another editor.
    draft = {"draft_schema": 1, "central": central,
             "groups": old.get("groups", []), "actuators": old.get("actuators", [])}
    return draft


class HeatingSubentryFlow(config_entries.ConfigSubentryFlow):
    """Persist desired central draft via the native config-entry manager only."""

    async def async_step_user(self, user_input=None):
        return await self._step(user_input, False)

    async def async_step_reconfigure(self, user_input=None):
        return await self._step(user_input, True)

    async def _step(self, user_input, reconfigure):
        entry = self._get_entry()
        if integration_mode(entry) != MODE_SHADOW:
            return self.async_abort(reason="shadow_mode_required")
        if entry.options.get(CONF_ENABLED, entry.data.get(CONF_ENABLED, False)):
            return self.async_abort(reason="disable_runtime_before_draft")
        old = self._get_reconfigure_subentry() if reconfigure else None
        others = [s for s in entry.subentries.values() if s.subentry_type == HEATING_SUBENTRY
                  and (old is None or s.subentry_id != old.subentry_id)]
        if others:
            return self.async_abort(reason="single_central_owner")
        old_draft = dict(old.data)["draft"] if old else None
        errors = {}
        if user_input is not None:
            try:
                document = draft_from_form(self.hass, user_input, old_draft)
                rooms = {s.data["room_id"] for s in entry.subentries.values() if s.subentry_type == "zone"}
                draft = parse_heating_draft(document, known_room_ids=rooms)
            except (KeyError, ValueError, vol.Invalid) as err:
                key = str(err)
                errors["base"] = key if key in {
                    "binding_missing", "loop_binding", "not_temperature", "weather_requires_outdoor_source",
                    "curve_must_not_fall_towards_cold_outdoors", "unused_fallback_must_be_null",
                    "minimum_must_be_below_maximum", "invalid_integer_or_bounds",
                } else "invalid_heating_draft"
            else:
                data = {"draft": draft.storage_document(), "status": draft.readiness,
                        "draft_digest": draft.digest}
                if old:
                    return self.async_update_and_abort(entry, old, title="Heating settings (draft)",
                                                       data=data, unique_id="central_heating")
                return self.async_create_entry(title="Heating settings (draft)",
                                               data=data, unique_id="central_heating")
        return self.async_show_form(step_id="reconfigure" if reconfigure else "user",
                                    data_schema=central_schema(old_draft), errors=errors)
