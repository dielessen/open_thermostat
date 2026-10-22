"""Native radiator-room setup; stages room and heating changes until Save.

Uses the existing room, week editor, graph validators and HA subentry store.
No transport, source selection, service calls or activation belong in this flow.
"""
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
import uuid
import logging

import probatio as vol
from homeassistant import config_entries
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .v1_config_flow import ZoneSubentryFlow, validate_room
from .v1_heating_graph import (
    actual_runtime_active, normalize_bindings, resolved_reference,
    selected_reference, validate_ownership,
)
from .v1_heating_draft import parse_heating_draft
from .v1_model import CONF_ENABLED, MODE_SHADOW, ROOM_GRAPH_DRAFT, ROOM_LIMIT, integration_mode
from .native_form import retained_input_schema


_LOGGER = logging.getLogger(__name__)


def snapshot(entry):
    return deepcopy((dict(entry.data), dict(entry.options),
                     {k: s.as_dict() for k, s in entry.subentries.items()}))


def prepare_radiator_graph(hass, entry, room, heating, radiators, group_id, actuator_ids, *, replace_room=False):
    """Shared prospective graph validation for wizard and single-screen editing."""
    if heating:
        document = deepcopy(dict(heating.data)["draft"])
    else:
        document = {"draft_schema": 1, "central": {
            "weather_enabled": False, "outdoor_source": None,
            "outdoor_maximum_age_ms": 600000, "stale_policy": "block_normal_demand",
            "fixed_fallback_centi_c": None,
            "supply_limits": {"minimum_centi_c": 2000, "maximum_centi_c": 4500},
            "curve_centi_c": [2000 + 300*i for i in range(9)]},
            "groups": [], "actuators": []}
    own = [a for a in document["actuators"] if a["room_id"] == room.room_id]
    gid = own[0]["group_id"] if own else group_id
    if not own:
        document["groups"].append({"group_id": gid, "name": room.name[:71] + " radiator",
            "emitter": "radiator", "supply_limits": deepcopy(document["central"]["supply_limits"]),
            "pump": None, "pump_start_delay_s": 0, "postrun_s": 0, "mixing": None})
    document["actuators"] = [a for a in document["actuators"] if a["room_id"] != room.room_id]
    for raw in radiators:
        output = resolved_reference(hass, raw, ("climate",))
        identity = (output["platform"], output["unique_id"])
        old = next((a for a in own if (a["output"].get("platform"), a["output"].get("unique_id")) == identity), None)
        aid = old["actuator_id"] if old else actuator_ids.setdefault(identity, uuid.uuid4().hex[:8])
        document["actuators"].append({"actuator_id": aid, "room_id": room.room_id,
            "group_id": gid, "profile": "trv_room_setpoint", "output": output, "settings": {}})
    document = normalize_bindings(hass, document)
    ids = {s.data["room_id"] for s in entry.subentries.values() if s.subentry_type == "zone"} | {room.room_id}
    parsed = parse_heating_draft(document, known_room_ids=ids)
    validate_ownership(hass, entry, document, room_replacement=room if replace_room else None)
    # Prospective room inputs are not in entry.subentries until final Save.
    inputs = [room.temperature, room.setpoint, room.schedule]
    if any(r and r.identity() == (output["entity_id"].split('.')[0], output["platform"], output["unique_id"])
           for r in inputs for output in (a["output"] for a in document["actuators"])):
        raise ValueError("input_output_loop")
    return parsed


class RadiatorRoomSetupFlow(ZoneSubentryFlow):
    """Create or edit an ordinary radiator room through one native entrypoint."""

    def _guard(self):
        try:
            entry = self._get_entry()
        except config_entries.UnknownEntry:
            return self.async_abort(reason="setup_changed")
        # The single subentry-map transaction below is pinned to the actual
        # reviewed HA core implementation. Fail closed on an untested core.
        if HA_VERSION != "2026.10.2":
            return self.async_abort(reason="setup_platform_unsupported")
        if integration_mode(entry) != MODE_SHADOW:
            return self.async_abort(reason="shadow_mode_required")
        if entry.options.get(CONF_ENABLED, entry.data.get(CONF_ENABLED, False)) or actual_runtime_active(self.hass, entry):
            return self.async_abort(reason="setup_runtime_off")
        if hasattr(self, "_before") and snapshot(entry) != self._before:
            return self.async_abort(reason="setup_changed")
        return None

    async def async_step_user(self, user_input=None):
        if guard := self._guard():
            return guard
        entry = self._get_entry()
        if not hasattr(self, "_before"):
            self._before = snapshot(entry)
        rooms = [s for s in entry.subentries.values() if s.subentry_type == "zone"]
        options = [{"value": "new", "label": "New room"}]
        options += [{"value": s.subentry_id, "label": s.title} for s in rooms]
        if user_input is not None:
            selected = user_input["room"]
            if selected not in {"new", *(s.subentry_id for s in rooms)}:
                return self.async_abort(reason="setup_changed")
            self._old = entry.subentries.get(selected)
            if self._old is None and len(rooms) >= ROOM_LIMIT:
                return self.async_abort(reason="room_limit")
            self._room_id = self._old.data["room_id"] if self._old else uuid.uuid4().hex[:8]
            self._room_original = deepcopy(dict(self._old.data)) if self._old else None
            self._group_id = uuid.uuid4().hex[:8]
            self._actuator_ids = {}
            from .product import central_entry
            self._heating = central_entry(entry)
            data = dict(self._old.data) if self._old else {}
            # Never silently remove advanced controls or convert a floor room.
            if data.get("comfort") is not None or data.get("setpoint") is not None:
                return self.async_abort(reason="advanced_room_required")
            if self._heating:
                draft = self._heating.data["draft"]
                groups = {g["group_id"]: g for g in draft["groups"]}
                own = [a for a in draft["actuators"] if a["room_id"] == self._room_id]
                if any(a["profile"] != "trv_room_setpoint" or
                       groups[a["group_id"]]["emitter"] != "radiator" for a in own):
                    return self.async_abort(reason="advanced_room_required")
                if len({a["group_id"] for a in own}) > 1:
                    return self.async_abort(reason="advanced_room_required")
            return await self.async_step_radiator()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required("room", default=rooms[0].subentry_id if len(rooms) == 1 else "new"):
                selector.SelectSelector({"options": options, "translation_key": "setup_room_choice"})}))

    def _display(self, ref, domains):
        try:
            return resolved_reference(self.hass, ref, domains)["entity_id"]
        except ValueError:
            return ref.get("entity_id", "")

    def _radiator_schema(self):
        data = dict(self._old.data) if self._old else {}
        outputs = [self._display(r, ("climate",)) for r in data.get("actuators", [])]
        if self._heating:
            outputs = [self._display(a["output"], ("climate",))
                       for a in self._heating.data["draft"]["actuators"]
                       if a["room_id"] == self._room_id] or outputs
        number = selector.NumberSelector({"min": 5, "max": 35, "step": 0.1,
                                          "unit_of_measurement": "°C", "mode": "box"})
        advanced = {
            vol.Required("minimum_target_temperature", default=data.get("minimum_target_centi_c", 500)/100): number,
            vol.Required("maximum_target_temperature", default=data.get("maximum_target_centi_c", 3500)/100): number,
            vol.Required("maximum_age_ms", default=data.get("maximum_age_ms", 120000)):
                vol.All(int, vol.Range(min=1000, max=86400000)),
        }
        helper = data.get("schedule")
        marker = vol.Optional("schedule_entity", description={"suggested_value": self._display(helper, ("schedule",))}) if helper else vol.Optional("schedule_entity")
        advanced[marker] = selector.EntitySelector({"filter": {"domain": "schedule"}})
        return vol.Schema({
            vol.Required("name", default=data.get("name", "")): str,
            vol.Required("temperature_entity", default=self._display(data.get("temperature", {}), ("sensor",))):
                selector.EntitySelector({"filter": {"domain": "sensor", "device_class": "temperature"}}),
            vol.Required("radiator_entities", default=outputs):
                selector.EntitySelector({"filter": {"domain": "climate"}, "multiple": True}),
            vol.Required("base_temperature", default=data.get("base_centi_c", 2100)/100): number,
            vol.Required("program_action", default="save"):
                selector.SelectSelector({"options": ["save", "edit_week", "remove_week"], "translation_key": "room_setup_program_action"}),
            vol.Optional("advanced"): section(vol.Schema(advanced), {"collapsed": True}),
        })

    def _submitted(self, values):
        data = dict(self._old.data) if self._old else {}
        advanced = dict(values.get("advanced", {}))
        # An omitted section retains existing advanced settings. An expanded
        # section is authoritative: clearing its optional helper is explicit.
        if "advanced" not in values and data.get("schedule"):
            advanced["schedule_entity"] = self._display(data["schedule"], ("schedule",))
        return {
            "room_id": self._room_id, "name": values["name"],
            "temperature_entity": values["temperature_entity"],
            "base_temperature": values["base_temperature"],
            "program_action": values.get("program_action", "save"),
            "minimum_target_temperature": advanced.get("minimum_target_temperature", data.get("minimum_target_centi_c", 500)/100),
            "maximum_target_temperature": advanced.get("maximum_target_temperature", data.get("maximum_target_centi_c", 3500)/100),
            "maximum_age_ms": advanced.get("maximum_age_ms", data.get("maximum_age_ms", 120000)),
            **({"schedule_entity": advanced["schedule_entity"]} if advanced.get("schedule_entity") else {}),
            "binding_mode": ROOM_GRAPH_DRAFT, "actuator_entities": [], "confirm_binding_mode_change": True,
        }

    async def async_step_radiator(self, user_input=None):
        if guard := self._guard():
            return guard
        errors = {}
        if user_input is not None:
            try:
                if not user_input["name"].strip() or len(user_input["name"]) > 80:
                    raise ValueError("invalid_name")
                outputs = user_input["radiator_entities"]
                if not 1 <= len(outputs) <= 8:
                    raise ValueError("select_radiators")
                self._radiators = [selected_reference(self.hass, x, ("climate",)) for x in outputs]
                identities = [(r["platform"], r["unique_id"]) for r in self._radiators]
                if len(identities) != len(set(identities)):
                    raise ValueError("output_has_multiple_owners")
                room = validate_room(self.hass, self._get_entry(), self._submitted(user_input), self._old)
                self._prepare_graph(room)  # Catch conflicts before opening the week editor.
                if user_input.get("program_action") == "edit_week":
                    if room.schedule:
                        raise ValueError("program_source_conflict")
                    from .v1_program import normalize_program
                    self._program_room = room
                    self._program_old = self._old
                    self._program_original = self._room_original
                    self._program_week = normalize_program(room.week_program or {})
                    return await self.async_step_program()
                return self._commit_room(room, self._old)
            except (KeyError, ValueError, vol.Invalid) as err:
                known = {"binding_missing", "loop_binding", "not_temperature", "unsupported_unit",
                         "invalid_target_range", "program_source_conflict", "duplicate_room",
                         "output_has_multiple_owners", "input_output_loop", "select_radiators", "invalid_name"}
                errors["base"] = str(err) if str(err) in known else "setup_invalid"
        return self.async_show_form(step_id="radiator", data_schema=retained_input_schema(
            self, self._radiator_schema(), user_input), errors=errors)

    def _prepare_graph(self, room):
        return prepare_radiator_graph(self.hass, self._get_entry(), room,
            self._heating, self._radiators, self._group_id, self._actuator_ids)

    def _commit_room(self, room, old):
        if guard := self._guard():
            return guard
        self._review_room = room
        self._prepare_graph(room)
        return self._review_form()

    def _label(self, entity_id):
        state = self.hass.states.get(entity_id)
        return state.name if state is not None else entity_id

    def _review_form(self, errors=None):
        room = self._review_room
        return self.async_show_form(step_id="room_review", data_schema=vol.Schema({}),
            description_placeholders={"name": room.name, "sensor": self._label(room.temperature.entity_id),
                "radiators": ", ".join(self._label(r["entity_id"]) for r in self._radiators),
                "target": f"{room.base_centi_c/100:g}"}, errors=errors or {})

    async def async_step_room_review(self, user_input=None):
        if guard := self._guard():
            return guard
        if user_input is None:
            return self._review_form()
        try:
            room = self._review_room
            # Resolve renamed or disabled registry identities again at final Save.
            from .v1_model import EntityReference
            room = replace(room, temperature=EntityReference.from_dict(resolved_reference(
                self.hass, room.temperature.as_dict(), ("sensor",), temperature=True)))
            if room.schedule:
                room = replace(room, schedule=EntityReference.from_dict(resolved_reference(
                    self.hass, room.schedule.as_dict(), ("schedule",))))
            parsed = self._prepare_graph(room)
            data = {**(dict(self._heating.data) if self._heating else {}),
                    "draft": parsed.storage_document(), "status": parsed.readiness,
                    "draft_digest": parsed.digest, "incomplete_group_ids": list(parsed.incomplete_group_ids)}
        except (KeyError, ValueError, vol.Invalid):
            return self._review_form({"base": "setup_invalid"})
        manager = self.hass.config_entries
        entry = self._get_entry()
        room_data = {**(dict(self._old.data) if self._old else {}), **room.as_dict()}
        if room.week_program is None:
            room_data.pop("week_program", None)
        room_sub = (replace(self._old, data=MappingProxyType(room_data), title=room.name)
                    if self._old else config_entries.ConfigSubentry(data=MappingProxyType(room_data),
                        subentry_type="zone", title=room.name, unique_id=room.room_id))
        heat_sub = (replace(self._heating, data=MappingProxyType(data)) if self._heating else
                    config_entries.ConfigSubentry(data=MappingProxyType(data), subentry_type="heating",
                        title="Heating settings (draft)", unique_id="central_heating"))
        from .product import is_product, INSTALLATION
        if is_product(entry):
            heat_sub = replace(heat_sub, title="Installation")
        subentries = {**entry.subentries, room_sub.subentry_id: room_sub, heat_sub.subentry_id: heat_sub}
        unique_ids = [s.unique_id for s in subentries.values() if s.unique_id is not None]
        if len(unique_ids) != len(set(unique_ids)):
            return self.async_abort(reason="setup_changed")
        try:
            # HA2026.10.2's public add/update_subentry callbacks each notify eager
            # listeners immediately; two callbacks expose an incomplete pair.
            # Use their SAME pinned core transaction with the complete map once.
            # This is a private core API: _guard explicitly refuses other cores.
            # No direct .storage writes, second owner or deferred reconciliation.
            if is_product(entry):
                manager._async_update_entry(entry,
                    data={**entry.data, INSTALLATION: data},
                    subentries={k: s for k, s in subentries.items() if s.subentry_type != "heating"})
            else:
                manager._async_update_entry(entry, subentries=subentries)
        except Exception:
            # The pinned core validates before replacing the map. Do not mask an
            # unexpected post-commit notifier failure by claiming a rollback.
            _LOGGER.exception("Room setup save could not be confirmed")
            return self.async_abort(reason="setup_save_uncertain")
        return self.async_abort(reason="room_saved")
