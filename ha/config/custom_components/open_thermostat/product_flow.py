"""Ordinary installation/room flows; configuration is not actuator authority.

Uses the existing HA subentry map, validators and versioned runtime. Historic
internal protocol names do not create a second user-facing test installation.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import logging

import probatio as vol
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import CONF_CREATE_DASHBOARD
from .product import (central_entry, commit_configuration, configuration_snapshot,
                      default_document)
from .product import INSTALLATION
from .room_setup_flow import RadiatorRoomSetupFlow
from .v1_config_flow import ShadowOptionsFlow, validate_room
from .v1_heating_flow import central_schema, draft_from_form
from .v1_heating_graph import actual_runtime_active, selected_reference, validated_graph
from .v1_model import CONF_ENABLED, MODE_SHADOW, integration_mode
from .native_form import retained_input_schema
from .schedule_compiler import WEEKDAYS
from .v1_program import normalize_program
from .controller_setup_flow import ControllerSetupFlow
from .e32_room_flow import E32RoomFlow

_LOGGER = logging.getLogger(__name__)


def milliseconds(seconds):
    if type(seconds) not in (int, float):
        raise ValueError("invalid_integer_or_bounds")
    try:
        value = Decimal(str(seconds)) * 1000
        if not value.is_finite() or value != value.to_integral_value() or not 1000 <= value <= 86400000:
            raise ValueError("invalid_integer_or_bounds")
        return int(value)
    except InvalidOperation:
        raise ValueError("invalid_integer_or_bounds") from None


def _error(err):
    key = str(err)
    known = {"binding_missing", "loop_binding", "not_temperature", "unsupported_unit",
             "invalid_target_range", "program_source_conflict", "duplicate_room",
             "duplicate_actuator", "output_has_multiple_owners", "input_output_loop",
             "select_radiators", "invalid_name", "weather_requires_outdoor_source",
             "curve_must_not_fall_towards_cold_outdoors", "unused_fallback_must_be_null",
             "minimum_must_be_below_maximum", "invalid_integer_or_bounds",
             "single_central_owner", "setup_changed", "setup_platform_unsupported", "runtime_active",
             "advanced_room_required", "confirm_program_source_change", "emitter_not_available",
             "invalid_program", "program_overlap", "program_limit"}
    return key if key in known else "setup_invalid"


class ProductRoomFlow(RadiatorRoomSetupFlow):
    """One guided native flow for adding and editing ordinary radiator rooms."""

    async def async_step_user(self, user_input=None):
        return await RadiatorRoomSetupFlow.async_step_user(self, {"room": "new"})

    async def async_step_reconfigure(self, user_input=None):
        return await self.async_step_edit_room(user_input)

    async def async_step_edit_room(self, user_input=None):
        """Existing rooms have one settings form; creation alone uses the wizard."""
        from .room_editor import read_room, save_room
        from .dashboard import RoomDashboard
        entry = self._get_entry()
        old = self._get_reconfigure_subentry()
        if not hasattr(self, '_edit_model'):
            try:
                self._edit_model = read_room(self.hass, entry.entry_id, old.data['room_id'])
            except (ValueError, KeyError):
                return self.async_abort(reason='setup_changed')
        model = self._edit_model
        values = model['settings']
        errors = {}
        if user_input is not None:
            settings = deepcopy(values)
            try:
                settings.update(name=user_input['name'], emitter=user_input['emitter'],
                    temperature_entity=user_input['temperature_entity'], radiator_entities=user_input['radiator_entities'])
                settings['base_centi_c'] = round(user_input['base_temperature'] * 100)
                advanced = user_input.get('advanced', {})
                for native, key in [('minimum_target_temperature', 'minimum_centi_c'), ('maximum_target_temperature', 'maximum_centi_c')]:
                    if native in advanced:
                        settings[key] = round(advanced[native] * 100)
                if 'maximum_age_seconds' in advanced:
                    settings['maximum_age_ms'] = milliseconds(advanced['maximum_age_seconds'])
                await save_room(self.hass, entry.entry_id, old.data['room_id'], model['token'], settings)
            except (KeyError, ValueError, vol.Invalid) as err:
                errors['base'] = _error(err)
            except Exception:
                _LOGGER.exception('Room edit save could not be confirmed')
                return self.async_abort(reason='setup_save_uncertain')
            else:
                return self.async_abort(reason='room_saved')
        number = selector.NumberSelector({'min': 5, 'max': 35, 'step': .1, 'mode': 'box', 'unit_of_measurement': '°C'})
        fields = {
            vol.Required('name', default=values['name']): str,
            vol.Required('emitter', default='radiator'): selector.SelectSelector({'options': ['radiator', 'floor', 'combined'], 'translation_key': 'product_emitter'}),
            vol.Required('temperature_entity', default=values['temperature_entity']): selector.EntitySelector({'filter': {'domain': 'sensor', 'device_class': 'temperature'}}),
            vol.Required('radiator_entities', default=values['radiator_entities']): selector.EntitySelector({'filter': {'domain': 'climate'}, 'multiple': True}),
            vol.Required('base_temperature', default=values['base_centi_c']/100): number,
            vol.Optional('advanced'): section(vol.Schema({
                vol.Required('minimum_target_temperature', default=values['minimum_centi_c']/100): number,
                vol.Required('maximum_target_temperature', default=values['maximum_centi_c']/100): number,
                vol.Required('maximum_age_seconds', default=values['maximum_age_ms']/1000): selector.NumberSelector({'min': 1, 'max': 86400, 'step': .001, 'mode': 'box', 'unit_of_measurement': 's'}),
            }), {'collapsed': True}),
        }
        dashboard = RoomDashboard(self.hass, entry.data.get('topic_prefix', entry.unique_id), entry.entry_id)
        return self.async_show_form(step_id='edit_room', data_schema=retained_input_schema(self, vol.Schema(fields), user_input),
            errors=errors, description_placeholders={'editor_url': '/' + dashboard.path + '/room-' + old.data['room_id']})

    async def async_step_radiator(self, user_input=None):
        # The parent starts here only after taking its snapshot and preparing IDs.
        if not hasattr(self, "_wizard_values"):
            data = dict(self._old.data) if self._old else {}
            schema = RadiatorRoomSetupFlow._radiator_schema(self)
            defaults = {str(k): k.default() for k in schema.schema
                        if k.default is not vol.UNDEFINED and str(k) != "advanced"}
            defaults.update(name=data.get("name", ""), program_action="save")
            self._wizard_values = defaults
        return await self.async_step_room(user_input)

    async def async_step_room(self, user_input=None):
        if guard := self._guard():
            return guard
        errors = {}
        if user_input is not None:
            if not user_input.get("name", "").strip() or len(user_input["name"]) > 80:
                errors["name"] = "invalid_name"
            elif user_input.get("emitter", "radiator") != "radiator":
                errors["emitter"] = "emitter_not_available"
            else:
                self._wizard_values["name"] = user_input["name"].strip()
                return await self.async_step_devices()
        schema = vol.Schema({
            vol.Required("name", default=self._wizard_values.get("name", "")): str,
            vol.Required("emitter", default="radiator"): selector.SelectSelector({
                "options": ["radiator", "floor", "combined"],
                "translation_key": "product_emitter"}),
        })
        return self.async_show_form(step_id="room", data_schema=retained_input_schema(
            self, schema, user_input), errors=errors)

    async def async_step_devices(self, user_input=None):
        if guard := self._guard():
            return guard
        values = self._wizard_values
        errors = {}
        if user_input is not None:
            values.update(user_input)
            try:
                outputs = values["radiator_entities"]
                if not 1 <= len(outputs) <= 8:
                    raise ValueError("select_radiators")
                self._radiators = [selected_reference(self.hass, x, ("climate",)) for x in outputs]
                self._prepare_graph(validate_room(self.hass, self._get_entry(),
                                                  self._submitted(values), self._old))
            except (KeyError, ValueError, vol.Invalid) as err:
                errors["base"] = _error(err)
            else:
                return await self.async_step_room_temperature()
        schema = vol.Schema({
            vol.Required("temperature_entity", default=values.get("temperature_entity", "")):
                selector.EntitySelector({"filter": {"domain": "sensor", "device_class": "temperature"}}),
            vol.Required("radiator_entities", default=values.get("radiator_entities", [])):
                selector.EntitySelector({"filter": {"domain": "climate"}, "multiple": True}),
        })
        return self.async_show_form(step_id="devices", data_schema=retained_input_schema(
            self, schema, user_input), errors=errors)

    async def async_step_room_temperature(self, user_input=None):
        if guard := self._guard():
            return guard
        values = self._wizard_values
        errors = {}
        if user_input is not None:
            submitted = deepcopy(user_input)
            advanced = submitted.get("advanced")
            try:
                if advanced is not None and "maximum_age_seconds" in advanced:
                    advanced["maximum_age_ms"] = milliseconds(advanced.pop("maximum_age_seconds"))
                values.update(submitted)
                result = await RadiatorRoomSetupFlow.async_step_radiator(self, values)
            except ValueError as err:
                errors["base"] = _error(err)
            else:
                if result.get("step_id") != "radiator":
                    return result
                errors = result.get("errors", {})
        base = RadiatorRoomSetupFlow._radiator_schema(self)
        kept = {key: val for key, val in base.schema.items()
                if str(key) in {"base_temperature", "program_action"}}
        # Retain the native collapsed section, but express report age in seconds.
        advanced_fields = {
            vol.Required("minimum_target_temperature", default=(dict(self._old.data) if self._old else {}).get("minimum_target_centi_c", 500)/100):
                selector.NumberSelector({"min": 5, "max": 35, "step": .1, "unit_of_measurement": "°C", "mode": "box"}),
            vol.Required("maximum_target_temperature", default=(dict(self._old.data) if self._old else {}).get("maximum_target_centi_c", 3500)/100):
                selector.NumberSelector({"min": 5, "max": 35, "step": .1, "unit_of_measurement": "°C", "mode": "box"}),
            vol.Required("maximum_age_seconds", default=(dict(self._old.data) if self._old else {}).get("maximum_age_ms", 120000)/1000):
                selector.NumberSelector({"min": 1, "max": 86400, "step": .001, "unit_of_measurement": "s", "mode": "box"}),
        }
        kept[vol.Optional("advanced")] = section(vol.Schema(advanced_fields), {"collapsed": True})
        defaults = {k: values[k] for k in ("base_temperature", "program_action") if k in values}
        if user_input is None:
            user_input = defaults
        return self.async_show_form(step_id="room_temperature", data_schema=retained_input_schema(
            self, vol.Schema(kept), user_input), errors=errors)

    async def async_step_program(self, user_input=None):
        result = await super().async_step_program(user_input)
        if result.get("type") == "menu":
            result["menu_options"].insert(3, "copy_day")
        return result

    async def async_step_copy_day(self, user_input=None):
        if guard := self._guard():
            return guard
        errors = {}
        if user_input is not None:
            try:
                source, targets = user_input["source_day"], user_input["target_days"]
                if source not in WEEKDAYS or not targets or any(t not in WEEKDAYS or t == source for t in targets):
                    raise ValueError("invalid_program")
                candidate = deepcopy(self._program_week)
                for day in targets:
                    candidate[day] = deepcopy(candidate[source])
                self._program_week = normalize_program(candidate,
                    self._program_room.minimum_target_centi_c, self._program_room.maximum_target_centi_c)
            except (KeyError, ValueError, vol.Invalid):
                errors["base"] = "invalid_program"
            else:
                return await self.async_step_program()
        return self.async_show_form(step_id="copy_day", data_schema=vol.Schema({
            vol.Required("source_day"): selector.SelectSelector({"options": list(WEEKDAYS), "translation_key": "program_days"}),
            vol.Required("target_days"): selector.SelectSelector({"options": list(WEEKDAYS), "multiple": True, "translation_key": "program_days"}),
        }), errors=errors)


class ProductOptionsFlow(E32RoomFlow, ControllerSetupFlow, ShadowOptionsFlow, ProductRoomFlow):
    """One central options entrypoint, using the same room editor and native Store.

    With a stored E32 connection the rooms are the E32 room plan: "E32 rooms"
    replaces the older HA room settings in this menu.
    """

    def _get_entry(self):
        return self.config_entry

    def _get_reconfigure_subentry(self):
        return self.config_entry.subentries[self._managed_room]

    def _native_plan_review_available(self):
        connection = self._graph_connection()
        return connection is not None and connection.runtime.native_plan_source is not None

    async def async_step_init(self, user_input=None):
        from .room_plan import has_room_plan
        rooms = "e32_rooms" if has_room_plan(self.config_entry) else "room_settings"
        options = ["installation", "controller_connection", rooms, "configuration_status"]
        if self._native_plan_review_available():
            options.append("graph_prepare")
        options += ["energy", "advanced_settings"]
        return self.async_show_menu(step_id="init", menu_options=options)

    async def async_step_energy(self, user_input=None):
        """Optional gas meter, gas price, outdoor temperature and boiler power (nothing is required)."""
        from .energy_input import EnergyError, energy_schema, save_energy, validate_energy
        errors = {}
        if user_input is not None:
            try:
                values = validate_energy(self.hass, user_input)
            except EnergyError as err:
                errors[err.field] = err.code
            else:
                save_energy(self.hass, self.config_entry, values)
                return self.async_abort(reason="energy_saved")
        schema = energy_schema(vol, self.config_entry.options)
        return self.async_show_form(step_id="energy", data_schema=retained_input_schema(self, schema, user_input),
                                    errors=errors)

    async def async_step_installation(self, user_input=None):
        entry = self.config_entry
        if integration_mode(entry) != MODE_SHADOW:
            return self.async_abort(reason="product_upgrade_required")
        from .installation_edit import installation_context, active_installation_step
        if hasattr(self, '_central_active_before') or installation_context(self.hass, entry) is not None:
            if hasattr(self, '_central_before'):
                return self.async_abort(reason='setup_changed')
            return await active_installation_step(self, user_input)
        if entry.options.get(CONF_ENABLED, False) or actual_runtime_active(self.hass, entry):
            return self.async_abort(reason="setup_runtime_off")
        from .room_profile_apply import pending_profile_source
        if pending_profile_source(self.hass, entry) is not None:
            return self.async_abort(reason='installation_apply_pending')
        errors = {}
        try:
            current = central_entry(entry)
        except ValueError as err:
            return self.async_abort(reason=_error(err))
        document = deepcopy(dict(current.data)["draft"]) if current else default_document()
        if not hasattr(self, "_central_before"):
            self._central_before = configuration_snapshot(entry)
        if user_input is not None:
            try:
                name = user_input["name"].strip()
                if not name or len(name) > 80:
                    raise ValueError("invalid_name")
                defaults = central_schema(document, self.hass)
                flattened = {str(key): key.default() for key in defaults.schema
                             if key.default is not vol.UNDEFINED and str(key) != "draft_action"}
                if document["central"].get("outdoor_source"):
                    flattened["outdoor_source"] = self._display(document["central"]["outdoor_source"], ("sensor", "weather"))
                if document["central"].get("fixed_fallback_centi_c") is not None:
                    flattened["fixed_fallback_temperature"] = document["central"]["fixed_fallback_centi_c"] / 100
                advanced = dict(user_input.get("advanced", {}))
                if "advanced" in user_input and "fixed_fallback_temperature" not in advanced:
                    flattened.pop("fixed_fallback_temperature", None)
                if "outdoor_maximum_age_seconds" in advanced:
                    advanced["outdoor_maximum_age_ms"] = milliseconds(advanced.pop("outdoor_maximum_age_seconds"))
                flattened.update(advanced)
                flattened["weather_enabled"] = user_input["weather_enabled"]
                if user_input.get("outdoor_source"):
                    flattened["outdoor_source"] = user_input["outdoor_source"]
                else:
                    flattened.pop("outdoor_source", None)
                # Central changes never silently replace room/group declarations.
                candidate = draft_from_form(self.hass, flattened, document)
                for group in candidate["groups"]:
                    if (group["emitter"] == "radiator" and group["supply_limits"] == document["central"]["supply_limits"]):
                        group["supply_limits"] = deepcopy(candidate["central"]["supply_limits"])
                parsed = validated_graph(self.hass, entry, candidate)
                data = {**(dict(current.data) if current else {}),
                    "draft": parsed.storage_document(), "status": parsed.readiness,
                    "draft_digest": parsed.digest, "incomplete_group_ids": list(parsed.incomplete_group_ids)}
                commit_configuration(self.hass, entry, self._central_before,
                    title=name, options={**entry.options, CONF_CREATE_DASHBOARD: user_input.get(CONF_CREATE_DASHBOARD, False)},
                    data={**entry.data, INSTALLATION: data},
                    subentries={k: s for k, s in entry.subentries.items() if s.subentry_type != "heating"})
            except (KeyError, ValueError, vol.Invalid) as err:
                errors["base"] = _error(err)
            except Exception:
                _LOGGER.exception("Installation save could not be confirmed")
                return self.async_abort(reason="setup_save_uncertain")
            else:
                return self.async_abort(reason="installation_saved")
        fields = central_schema(document, self.hass)
        advanced = {}
        for key, value in fields.schema.items():
            if str(key) in {"draft_action", "weather_enabled", "outdoor_source"}:
                continue
            if str(key) == "outdoor_maximum_age_ms":
                key = vol.Required("outdoor_maximum_age_seconds", default=document["central"]["outdoor_maximum_age_ms"]/1000)
                value = selector.NumberSelector({"min": 1, "max": 86400, "step": .001, "mode": "box", "unit_of_measurement": "s"})
            advanced[key] = value
        source = document["central"].get("outdoor_source")
        marker = vol.Optional("outdoor_source", description={"suggested_value": self._display(source, ("sensor", "weather"))}) if source else vol.Optional("outdoor_source")
        schema = vol.Schema({
            vol.Required("name", default=entry.title): str,
            vol.Required("weather_enabled", default=document["central"]["weather_enabled"]): bool,
            marker: selector.EntitySelector({"filter": [
                {"domain": "sensor", "device_class": "temperature"}, {"domain": "weather"}]}),
            vol.Optional(CONF_CREATE_DASHBOARD, default=entry.options.get(CONF_CREATE_DASHBOARD, False)): bool,
            vol.Optional("advanced"): section(vol.Schema(advanced), {"collapsed": True}),
        })
        return self.async_show_form(step_id="installation", data_schema=retained_input_schema(
            self, schema, user_input), errors=errors)

    async def async_step_installation_connected(self, user_input=None):
        from .installation_edit import active_installation_step
        return await active_installation_step(self, user_input)

    async def async_step_room_settings(self, user_input=None):
        rooms = [s for s in self.config_entry.subentries.values() if s.subentry_type == "zone"]
        if not rooms:
            return self.async_abort(reason="no_rooms")
        if user_input is not None:
            if user_input.get("room") not in {s.subentry_id for s in rooms}:
                return self.async_abort(reason="setup_changed")
            self._managed_room = user_input["room"]
            if user_input.get("action") == "remove":
                return await self.async_step_remove_room()
            if user_input.get("action") != "edit":
                return self.async_abort(reason="setup_changed")
            return await ProductRoomFlow.async_step_reconfigure(self)
        return self.async_show_form(step_id="room_settings", data_schema=vol.Schema({
            vol.Required("room", default=rooms[0].subentry_id): selector.SelectSelector({"options": [
                {"value": s.subentry_id, "label": s.title} for s in rooms]}),
            vol.Required("action", default="edit"): selector.SelectSelector({
                "options": ["edit", "remove"], "translation_key": "product_room_action"}),
        }))

    async def async_step_remove_room(self, user_input=None):
        entry = self.config_entry
        if entry.options.get(CONF_ENABLED, False) or actual_runtime_active(self.hass, entry):
            return self.async_abort(reason="setup_runtime_off")
        old = entry.subentries.get(self._managed_room)
        if old is None:
            return self.async_abort(reason="setup_changed")
        if not hasattr(self, "_remove_before"):
            self._remove_before = configuration_snapshot(entry)
        if user_input is not None:
            if not user_input.get("confirm_remove", False):
                return self.async_abort(reason="cancelled")
            try:
                subentries = {k: s for k, s in entry.subentries.items() if k != old.subentry_id}
                current = central_entry(entry)
                if current:
                    document = deepcopy(dict(current.data)["draft"])
                    own_groups = {a["group_id"] for a in document["actuators"] if a["room_id"] == old.data["room_id"]}
                    document["actuators"] = [a for a in document["actuators"] if a["room_id"] != old.data["room_id"]]
                    used = {a["group_id"] for a in document["actuators"]}
                    document["groups"] = [g for g in document["groups"] if g["group_id"] not in own_groups or g["group_id"] in used]
                    # Parse prospective ownership without creating an intermediate entry.
                    from .v1_heating_draft import parse_heating_draft
                    parsed = parse_heating_draft(document, known_room_ids={s.data["room_id"] for s in subentries.values() if s.subentry_type == "zone"})
                    data = {**dict(current.data), "draft": parsed.storage_document(), "status": parsed.readiness,
                            "draft_digest": parsed.digest, "incomplete_group_ids": list(parsed.incomplete_group_ids)}
                # A removed layout invalidates the selected logical device profile.
                from .native_provisioning import SOURCE_OPTION
                options = {k: v for k, v in entry.options.items() if k != SOURCE_OPTION}
                changed = {"options": options, "subentries": subentries}
                if current:
                    changed["data"] = {**entry.data, INSTALLATION: data}
                commit_configuration(self.hass, entry, self._remove_before, **changed)
            except (ValueError, KeyError) as err:
                return self.async_abort(reason=_error(err))
            except Exception:
                _LOGGER.exception("Room removal could not be confirmed")
                return self.async_abort(reason="setup_save_uncertain")
            return self.async_abort(reason="room_removed")
        return self.async_show_form(step_id="remove_room", data_schema=vol.Schema({
            vol.Required("confirm_remove", default=False): bool,
        }), description_placeholders={"name": old.title})

    async def async_step_configuration_status(self, user_input=None):
        if user_input is not None:
            return self.async_abort(reason="configuration_status_closed")
        entry = self.config_entry
        state = self.hass.data.get("open_thermostat", {}).get(entry.entry_id, {})
        connection = state.get("v1_connection")
        client = getattr(connection, "client", None)
        verified = bool(getattr(client, "graph_status", {}).get("readback_verified", False))
        dutch = self.hass.config.language == "nl"
        connection_text = ("Toepassing bevestigd" if verified else "Toepassing nog niet bevestigd") if dutch else (
            "Application confirmed" if verified else "Application not yet confirmed")
        enabled = actual_runtime_active(self.hass, entry)
        runtime_text = (("Alleen uitlezen en berekenen (schaduwmodus)" if enabled else "Berekeningen uit; geen aansturing")
                        if dutch else ("Read and calculate only (shadow mode)" if enabled else "Calculations off; no device control"))
        # Inspect saved targets without altering settings or granting physical readiness.
        from .room_editor import read_room
        from .v1_profile_c import MODE_MESSAGES
        checks = []
        for sub in entry.subentries.values():
            if sub.subentry_type != "zone":
                continue
            try:
                review = read_room(self.hass, entry.entry_id, sub.data["room_id"])["actuator_target_review"]
            except (KeyError, ValueError):
                continue
            for actuator in review["actuators"]:
                cap = actuator.get("capability")
                text = actuator["entity_id"] + ": "
                if cap and actuator["status"] != "unknown":
                    text += f"{cap['minimum']:g}–{cap['maximum']:g} {cap['unit']}; "
                    text += ("stap " if dutch else "step ") + f"{cap['step']:g} {cap['unit']}"
                    if any(reason in actuator["issues"] for reason in (
                            "room_limits_exceed_actuator", "saved_targets_need_review")):
                        text += (". Controleer kamergrenzen en programmadoelen." if dutch
                                 else ". Review room limits and program targets.")
                else:
                    text += ("Eigenschappen niet beschikbaar; controleer de kraanverbinding." if dutch
                             else "Capabilities unavailable; check the valve connection.")
                for reason in actuator.get("operating_mode", {}).get("issues", []):
                    if reason in MODE_MESSAGES:
                        text += " " + MODE_MESSAGES[reason][0 if dutch else 1]
                if review["external_program_present"]:
                    text += (" Het bestaande externe programma is niet gecontroleerd." if dutch
                             else " The existing external program has not been checked.")
                checks.append(text)
        actuator_text = "\n\n".join(checks) or ("Nog geen radiatorkranen gekoppeld." if dutch else "No radiator valves linked yet.")
        return self.async_show_form(step_id="configuration_status", data_schema=vol.Schema({}),
            description_placeholders={"rooms": str(sum(s.subentry_type == "zone" for s in entry.subentries.values())),
                "connection": connection_text, "runtime": runtime_text, "actuator_checks": actuator_text})

    async def async_step_advanced_settings(self, user_input=None):
        options = ["configuration_status", "hot_water"]
        if self._native_plan_review_available():
            options.append("graph_status")
        return self.async_show_menu(step_id="advanced_settings", menu_options=options)
