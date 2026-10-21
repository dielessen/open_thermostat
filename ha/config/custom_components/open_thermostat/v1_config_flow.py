"""Native room subentries/selectors; source qualification is never a GUI toggle."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import timedelta, time
import uuid
import re
import probatio as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector
from homeassistant.util import dt as dt_util

from .schedule_compiler import compile_week, WEEKDAYS
from .v1_program import normalize_program, native_week, change_block, clock_second

from .const import CONF_CREATE_DASHBOARD, CONF_TOPIC_PREFIX, DOMAIN
from .v1_model import (
    CONF_ENABLED, CONF_MODE, MODE_LEGACY, MODE_SHADOW, ROOM_LIMIT,
    EntityReference, RoomBinding, integration_mode, target_centi,
    ROOM_CLIMATE_TRV, ROOM_GRAPH_DRAFT, has_graph_rooms,
)
from homeassistant.exceptions import ConfigEntryError
from .v1_wire import identifier
from .v1_heating_flow import HeatingSubentryFlow
from .native_form import retained_input_schema

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
    actuators = tuple(reference(hass, x) for x in user_input.get("actuator_entities", []))
    physical = reference(hass, user_input["setpoint_entity"]) if user_input.get("setpoint_entity") else None
    room = RoomBinding.from_dict({
        "room_id": room_id, "name": user_input["name"], "temperature": sensor.as_dict(),
        "actuators": [x.as_dict() for x in actuators],
        "binding_mode": user_input.get("binding_mode",
            old_subentry.data.get("binding_mode", ROOM_CLIMATE_TRV) if old_subentry else ROOM_CLIMATE_TRV),
        "setpoint": physical.as_dict() if physical else None,
        **({"comfort": {
                "away_centi_c": target_centi(user_input.get("away_temperature", 17)),
                "frost_centi_c": target_centi(user_input.get("frost_temperature", 5)),
                "temporary_ms": user_input.get("override_minutes",60)*60000},
            "window": reference(hass,user_input["window_entity"]).as_dict() if user_input.get("window_entity") else None,
            "presence": reference(hass,user_input["presence_entity"]).as_dict() if user_input.get("presence_entity") else None,
        } if user_input.get("comfort_enabled",False) else {}),
        "maximum_age_ms": user_input.get("maximum_age_ms", 120000),
        "base_centi_c": target_centi(user_input["base_temperature"]) if "base_temperature" in user_input else user_input.get("base_centi_c", 2100),
        "schedule": reference(hass, user_input["schedule_entity"]).as_dict() if user_input.get("schedule_entity") else None,
        "minimum_target_centi_c": target_centi(user_input.get("minimum_target_temperature", 5)),
        "maximum_target_centi_c": target_centi(user_input.get("maximum_target_temperature", 35)),
        **({"week_program": dict(old_subentry.data)["week_program"]}
           if old_subentry and "week_program" in old_subentry.data
           and user_input.get("program_action", "save") != "remove_week" else {}),
    })
    old_mode = old_subentry.data.get("binding_mode", ROOM_CLIMATE_TRV) if old_subentry else ROOM_CLIMATE_TRV
    if room.binding_mode == ROOM_GRAPH_DRAFT or old_mode == ROOM_GRAPH_DRAFT:
        from .v1_heating_graph import actual_runtime_active
        if entry.options.get(CONF_ENABLED, False) or actual_runtime_active(hass, entry):
            raise ValueError("graph_room_runtime_off_required")
    if old_subentry and old_mode != room.binding_mode and user_input.get("confirm_binding_mode_change") is not True:
        raise ValueError("confirm_room_mode_change")
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
    from .v1_heating_graph import validate_room_ownership
    validate_room_ownership(hass, entry, room)
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
        return {"zone": ZoneSubentryFlow, "heating": HeatingSubentryFlow} if integration_mode(config_entry) == MODE_SHADOW else {}

class ShadowOptionsFlow(config_entries.OptionsFlow):
    # Native entry's existing update listener owns options/subentry reload.
    # OptionsFlowWithReload is explicitly incompatible with that listener.
    async def async_step_hot_water(self, user_input=None):
        if user_input is not None:
            return self.async_abort(reason="hot_water_information_complete")
        from .dhw import entry_snapshot, summary
        return self.async_show_form(step_id="hot_water", data_schema=vol.Schema({}),
            description_placeholders={"status": summary(entry_snapshot(self.hass,self.config_entry))})

    def _graph_connection(self):
        data=self.hass.data.get(DOMAIN,{}).get(self.config_entry.entry_id,{})
        connection=data.get("v1_connection")
        from .v1_mqtt import NativeShadowConnection
        from .graph_wire import GraphSourceProfile,GraphShadowClient
        if (isinstance(connection,NativeShadowConnection) and not connection.closed
                and connection.worker is not None and not connection.worker.done()
                and isinstance(connection.graph_profile,GraphSourceProfile)
                and isinstance(connection.client,GraphShadowClient)):
            return connection
        return None

    async def async_step_graph_prepare(self,user_input=None):
        connection=self._graph_connection()
        if connection is None or connection.graph_profile.draft_source is None:
            return self.async_abort(reason="graph_prepare_unavailable")
        try:
            # No raw JSON, manifest, evidence/qualification or profile arguments
            # come from the form. Compile saved native DATA in SAME worker.
            await connection.async_graph_command("prepare")
            return await self.async_step_graph_review()
        except Exception:
            return self.async_abort(reason="graph_prepare_failed")

    async def async_step_graph_review(self,user_input=None):
        from .graph_shadow_validation import GraphValidationError
        connection=self._graph_connection()
        if connection is None:return self.async_abort(reason="graph_review_unavailable")
        try:
            if user_input is not None:
                if user_input.get("confirm_apply") is not True:
                    return self.async_abort(reason="graph_review_cancelled")
                if getattr(self,"_review_connection",None) is not connection:
                    return self.async_abort(reason="graph_review_changed")
                # Existing bounded worker serializes apply with messages/reconnect;
                # journal rechecks reviewed tuple inside the existing Store lock.
                await connection.async_graph_command("apply",self._reviewed_candidate)
                return await self.async_step_graph_status()
            self._reviewed_candidate=connection.client.review_candidate()
            self._review_connection=connection
            state=connection.client.journal.state
            record=state["staged"]
            return self.async_show_form(step_id="graph_review",data_schema=vol.Schema({
                vol.Required("confirm_apply",default=False):bool}),
                description_placeholders={
                    "revision":str(record["config"]["revision"]),
                    "digest":record["config_digest"],
                    "accepted":str(connection.client.graph_status["accepted_revision"]),
                    "status":connection.client.graph_status["journal_status"]})
        except (GraphValidationError,ConfigEntryError):
            if connection.client.journal.status in {"graph_send_unconfirmed","awaiting_graph_readback","graph_interrupted","graph_apply_pending"}:
                return await self.async_step_graph_status()
            return self.async_abort(reason="graph_review_changed")
        except Exception:
            # IO may have reached the peer. No blind retry or optimistic failure
            # claim; expose the existing unconfirmed/readback status instead.
            return await self.async_step_graph_status()

    async def async_step_graph_status(self,user_input=None):
        connection=self._graph_connection()
        if connection is None:return self.async_abort(reason="graph_review_unavailable")
        if user_input is not None and user_input.get("status_action")!="refresh":
            return self.async_abort(reason="graph_review_complete")
        state=connection.client.graph_status
        return self.async_show_form(step_id="graph_status",data_schema=vol.Schema({
            vol.Required("status_action",default="refresh"):selector.SelectSelector({
                "options":["refresh","close"],"translation_key":"graph_status_action"})}),
            description_placeholders={
                "status":state["status"],"journal_status":state["journal_status"],
                "accepted":str(state["accepted_revision"]),"staged":str(state["staged_revision"]),
                "verified":str(state["readback_verified"]),
                "device_result":state["device_result"] or "not_received"})

    @staticmethod
    def _entry_review_snapshot(entry):
        # Read-only native configuration snapshot, never persisted/logged.
        return (deepcopy(dict(entry.data)),deepcopy(dict(entry.options)),
                {key:(item.subentry_type,item.title,deepcopy(dict(item.data)))
                 for key,item in entry.subentries.items()})

    async def _graph_enable_error(self,mode,enabled,owner):
        if not has_graph_rooms(self.config_entry):
            return None
        if mode!=MODE_SHADOW:
            return "graph_room_contract_unavailable"
        if not enabled:
            return None  # OFF must never depend on a valid SOURCE pin.
        from . import (_selected_graph_data_profile,_selected_graph_controller_source,
                       _selected_controller_policy_source_profile)
        try:
            data=_selected_graph_data_profile(self.config_entry)
            source=_selected_graph_controller_source(self.config_entry)
            if data is not None and source is not None:
                return "graph_control_source_review_required"
            if source is None:
                return None if data is not None else "graph_room_contract_unavailable"
            if owner!=source.controller.adapter_id:
                return "graph_control_source_review_required"
            policy=_selected_controller_policy_source_profile(self.config_entry)
            if policy not in (None,source.controller):
                return "graph_control_source_review_required"
            before=self._entry_review_snapshot(self.config_entry)
            # SOURCE selection already exists outside GUI; this is only a
            # read-only preflight of the exact native reviewed DATA/currentdraft.
            await source.async_configuration(self.hass,self.config_entry)
            if (self._entry_review_snapshot(self.config_entry)!=before
                    or _selected_graph_controller_source(self.config_entry)!=source
                    or _selected_graph_data_profile(self.config_entry) is not None
                    or _selected_controller_policy_source_profile(self.config_entry)!=policy):
                return "graph_control_source_review_required"
            return None
        except Exception:
            # No unknown profile/data/adoption/IO error may create authority.
            # Entry setup and fresh device readback independently revalidate.
            return "graph_control_source_review_required"

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None and user_input.get("information")=="hot_water":
            return await self.async_step_hot_water()
        if user_input is not None and user_input.get("graph_action")=="prepare":
            return await self.async_step_graph_prepare()
        if user_input is not None and user_input.get("graph_action")=="review":
            return await self.async_step_graph_review()
        if user_input is not None and user_input.get("graph_action")=="status":
            return await self.async_step_graph_status()
        if user_input is not None:
            mode = user_input[CONF_MODE]
            owner = user_input.get("adapter_id", self.config_entry.options.get(
                "adapter_id", self.config_entry.data.get("adapter_id", "")))
            valid_owner = isinstance(owner, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", owner) is not None
            graph_error=await self._graph_enable_error(mode,user_input.get(CONF_ENABLED,False),owner)
            if graph_error:
                errors["base"]=graph_error
            elif mode == MODE_SHADOW and not valid_owner:
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
            vol.Optional("information",default="settings"): selector.SelectSelector({"options":[{"value":"settings","label":"Settings"},{"value":"hot_water","label":"Domestic hot water (read-only)"}]}),
            **({vol.Optional("graph_action",default="settings"):
                selector.SelectSelector({"options":(["settings","prepare","review","status"]
                    if self._graph_connection().graph_profile.draft_source is not None else ["settings","review","status"]),
                    "translation_key":"graph_action"})}
                if self._graph_connection() is not None else {}),
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
            vol.Required("program_action", default="save"):
                selector.SelectSelector({"options": ["save", "edit_week", "remove_week"],
                                         "translation_key": "program_action"}),
            vol.Required("temperature_entity", default=display(data.get("temperature", {}))):
                selector.EntitySelector({"filter": {"domain": "sensor", "device_class": "temperature"}}),
            vol.Required("binding_mode", default=data.get("binding_mode", ROOM_CLIMATE_TRV)):
                selector.SelectSelector({"options": [ROOM_CLIMATE_TRV, ROOM_GRAPH_DRAFT],
                                         "translation_key": "room_binding_mode"}),
            vol.Optional("actuator_entities", description={"suggested_value": [display(x) for x in data.get("actuators", [])]}):
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
            vol.Required("comfort_enabled", default=data.get("comfort") is not None): bool,
            vol.Required("away_temperature", default=data.get("comfort",{}).get("away_centi_c",1700)/100):
                selector.NumberSelector({"min":5,"max":35,"step":0.1,"unit_of_measurement":"°C","mode":"box"}),
            vol.Required("frost_temperature", default=data.get("comfort",{}).get("frost_centi_c",500)/100):
                selector.NumberSelector({"min":5,"max":35,"step":0.1,"unit_of_measurement":"°C","mode":"box"}),
            vol.Required("override_minutes", default=data.get("comfort",{}).get("temporary_ms",3600000)//60000):
                vol.All(int,vol.Range(min=1,max=720)),
            vol.Optional("window_entity",description={"suggested_value":display(data["window"])} if data.get("window") else {}):
                selector.EntitySelector({"filter":{"domain":"binary_sensor"}}),
            vol.Optional("presence_entity",description={"suggested_value":display(data["presence"])} if data.get("presence") else {}):
                selector.EntitySelector({"filter":{"domain":"person"}}),
            vol.Required("maximum_age_ms", default=data.get("maximum_age_ms", 120000)):
                vol.All(int, vol.Range(min=1000, max=86400000)),
        }
        if reconfigure:
            items[vol.Optional("confirm_binding_mode_change", default=False)] = selector.BooleanSelector()
        if not reconfigure:
            items[vol.Required("room_id", default=uuid.uuid4().hex[:8])] = str
        return vol.Schema(items)

    async def _step(self, user_input, reconfigure):
        entry = self._get_entry()
        old = self._get_reconfigure_subentry() if reconfigure else None
        errors = {}
        if old and not hasattr(self, "_room_original"):
            self._room_original = deepcopy(dict(old.data))
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
                    "program_source_conflict", "room_mode_actuator_conflict", "unsupported_room_binding_mode",
                    "graph_room_runtime_off_required", "confirm_room_mode_change",
                } else "invalid_binding"
            else:
                if user_input.get("program_action") == "edit_week":
                    if room.schedule:
                        errors["base"] = "program_source_conflict"
                    else:
                        self._program_room = room
                        self._program_old = old
                        self._program_original = deepcopy(dict(old.data)) if old else None
                        self._program_week = normalize_program(room.week_program or {})
                        return await self.async_step_program()
                else:
                    return self._commit_room(room, old)
        return self.async_show_form(
            step_id="reconfigure" if reconfigure else "user",
            data_schema=retained_input_schema(self,self._schema(dict(old.data) if old else None, reconfigure=reconfigure),user_input),
            errors=errors)

    async def async_step_user(self, user_input=None):
        return await self._step(user_input, False)

    async def async_step_reconfigure(self, user_input=None):
        return await self._step(user_input, True)


    def _commit_room(self, room, old):
        entry = self._get_entry()
        if old:
            if (entry.subentries.get(old.subentry_id) is not old or
                    dict(old.data) != self._room_original):
                return self.async_abort(reason="room_changed")
            # Same native update listener and persistence path as room bindings.
            return self.async_update_and_abort(
                entry, old, title=room.name, unique_id=room.room_id, data=room.as_dict())
        return self.async_create_entry(
            title=room.name, unique_id=room.room_id, data=room.as_dict())

    async def async_step_program(self, user_input=None):
        if not hasattr(self, "_program_room"):
            return self.async_abort(reason="program_not_started")
        count = sum(len(blocks) for blocks in self._program_week.values())
        return self.async_show_menu(step_id="program",
            menu_options=["add_block", "edit_block", "delete_block", "save_program", "cancel_program"],
            description_placeholders={"blocks": str(count),
                "base": str(self._program_room.base_centi_c / 100)})

    async def async_step_add_block(self, user_input=None):
        self._selected_block = None
        return await self.async_step_block()

    async def _select_program_block(self, user_input, mode):
        options = []
        for day, blocks in self._program_week.items():
            for index, block in enumerate(blocks):
                start = self._display_clock(block["start"])
                end = self._display_clock(block["end"])
                options.append({"value": f"{day}:{index}",
                    "label": f"{day} {start}–{end} · {block['target_centi_c'] / 100:g} °C"})
        if not options:
            return self.async_show_form(step_id="program_empty",
                data_schema=vol.Schema({}), errors={"base": "program_empty"})
        if user_input is not None:
            selected = user_input.get("block")
            if selected not in {option["value"] for option in options}:
                return self.async_abort(reason="program_changed")
            day, index = selected.split(":")
            if mode == "delete":
                self._program_week[day].pop(int(index))
                return await self.async_step_program()
            self._selected_block = (day, int(index))
            return await self.async_step_block()
        return self.async_show_form(step_id=mode + "_block", data_schema=vol.Schema({
            vol.Required("block"): selector.SelectSelector({"options": options})}))

    async def async_step_program_empty(self, user_input=None):
        return await self.async_step_program()

    async def async_step_edit_block(self, user_input=None):
        return await self._select_program_block(user_input, "edit")

    async def async_step_delete_block(self, user_input=None):
        return await self._select_program_block(user_input, "delete")

    @staticmethod
    def _display_clock(second):
        return "24:00:00" if second == 86400 else time(second // 3600, second % 3600 // 60, second % 60).isoformat()

    async def async_step_block(self, user_input=None):
        room = self._program_room
        selected = self._selected_block
        old = self._program_week[selected[0]][selected[1]] if selected else None
        errors = {}
        if user_input is not None:
            try:
                self._program_week = change_block(
                    self._program_week, user_input["days"],
                    clock_second(user_input["start_time"]),
                    86400 if user_input.get("end_at_midnight", False) else clock_second(user_input["end_time"]),
                    target_centi(user_input["temperature"]),
                    room.minimum_target_centi_c, room.maximum_target_centi_c, selected)
            except (KeyError, ValueError) as err:
                code = str(err)
                errors["base"] = code if code in {
                    "program_overlap", "program_limit", "invalid_target_range",
                    "invalid_program_time"} else "invalid_program"
            else:
                return await self.async_step_program()
        default = old or {"start": 7 * 3600, "end": 8 * 3600, "target_centi_c": room.base_centi_c}
        schema=vol.Schema({
            vol.Required("days", default=[selected[0]] if selected else ["monday"]):
                selector.SelectSelector({"options": list(WEEKDAYS), "multiple": True,
                                         "translation_key": "program_days"}),
            vol.Required("start_time", default=self._display_clock(default["start"])):
                selector.TimeSelector(),
            vol.Required("end_time", default=self._display_clock(default["end"] % 86400)):
                selector.TimeSelector(),
            vol.Required("end_at_midnight", default=default["end"] == 86400):
                selector.BooleanSelector(),
            vol.Required("temperature", default=default["target_centi_c"] / 100):
                selector.NumberSelector({"min": room.minimum_target_centi_c / 100,
                    "max": room.maximum_target_centi_c / 100, "step": 0.1,
                    "unit_of_measurement": "°C", "mode": "box"}),
        })
        return self.async_show_form(step_id="block",
            data_schema=retained_input_schema(self,schema,user_input),errors=errors)

    async def async_step_save_program(self, user_input=None):
        old = self._program_old
        entry = self._get_entry()
        if (old and (entry.subentries.get(old.subentry_id) is not old
                     or dict(old.data) != self._program_original)):
            return self.async_abort(reason="program_changed")
        room = replace(self._program_room, week_program=normalize_program(
            self._program_week, self._program_room.minimum_target_centi_c,
            self._program_room.maximum_target_centi_c))
        # Revalidate references, room/actuator uniqueness and bounds at final save,
        # not just when entering a multi-step draft.
        submitted = {
            "room_id": room.room_id, "name": room.name,
            "temperature_entity": room.temperature.entity_id,
            "actuator_entities": [x.entity_id for x in room.actuators],
            "binding_mode": room.binding_mode, "confirm_binding_mode_change": True,
            "base_temperature": room.base_centi_c / 100,
            "minimum_target_temperature": room.minimum_target_centi_c / 100,
            "maximum_target_temperature": room.maximum_target_centi_c / 100,
            "maximum_age_ms": room.maximum_age_ms, "program_action": "remove_week"}
        if room.setpoint:
            submitted["setpoint_entity"] = room.setpoint.entity_id
        if room.comfort is not None:
            submitted.update(comfort_enabled=True,
                away_temperature=room.comfort["away_centi_c"]/100,
                frost_temperature=room.comfort["frost_centi_c"]/100,
                override_minutes=room.comfort["temporary_ms"]//60000)
            if room.window:
                submitted["window_entity"]=room.window.entity_id
            if room.presence:
                submitted["presence_entity"]=room.presence.entity_id
        try:
            checked = validate_room(self.hass, entry, submitted, old)
            room = replace(checked, week_program=room.week_program)
            start = dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            await self.hass.async_add_executor_job(
                compile_week, native_week(room.week_program), room.base_centi_c,
                self.hass.config.time_zone, int(start.timestamp()),
                int((start + timedelta(days=15)).timestamp()))
        except (KeyError, ValueError, vol.Invalid):
            return self.async_show_form(step_id="program_save_error",
                data_schema=vol.Schema({}), errors={"base": "program_export_failed"})
        if old is None and sum(s.subentry_type == "zone" for s in entry.subentries.values()) >= ROOM_LIMIT:
            return self.async_abort(reason="room_limit")
        return self._commit_room(room, old)

    async def async_step_program_save_error(self, user_input=None):
        return await self.async_step_program()

    async def async_step_cancel_program(self, user_input=None):
        return self.async_abort(reason="program_cancelled")
