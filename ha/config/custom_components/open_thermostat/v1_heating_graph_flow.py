"""Native multi-step desired graph editor; stages everything until final Save."""
from __future__ import annotations

from copy import deepcopy
import uuid
import probatio as vol
from homeassistant.helpers import selector

from .native_form import retained_input_schema
from .v1_heating_draft import HeatingConfigError
from .v1_heating_graph import selected_reference, validated_graph, resolved_reference, actual_runtime_active
from .v1_model import CONF_ENABLED, MODE_SHADOW, integration_mode


def number(low, high):
    return selector.NumberSelector({"min": low, "max": high, "step": 1, "mode": "box"})


def choice(values, key=None):
    options = {"options": values}
    if key:
        options["translation_key"] = key
    return selector.SelectSelector(options)


def entity(domains):
    return selector.EntitySelector({"filter": [{"domain": domain} for domain in domains]})


def optional(key, ref):
    return (vol.Optional(key, description={"suggested_value": ref["entity_id"]})
            if ref else vol.Optional(key))


def error_key(error):
    key = str(error)
    return key if key in {
        "binding_missing", "loop_binding", "wrong_entity_domain", "input_output_loop", "not_temperature",
        "output_has_multiple_owners", "floor_requires_mixing_or_shared_safe_limit",
        "minimum_must_be_below_maximum", "invalid_integer_or_bounds",
        "invalid_tpi_travel_or_minimum_times", "pump_times_without_pump",
        "unused_fallback_must_be_null", "invalid_position_range", "group_count",
        "actuator_count", "room_actuator_limit", "duplicate_actuator_or_missing_reference",
    } else "invalid_heating_graph"


class HeatingGraphFlowMixin:
    """Mixed into the single native heating-subentry owner, not another writer."""

    def _graph_guard(self):
        entry = self._get_entry()
        if integration_mode(entry) != MODE_SHADOW:
            return self.async_abort(reason="shadow_mode_required")
        if (entry.options.get(CONF_ENABLED, entry.data.get(CONF_ENABLED, False))
                or actual_runtime_active(self.hass, entry)):
            return self.async_abort(reason="disable_runtime_before_draft")
        if not hasattr(self, "_graph_document"):
            return self.async_abort(reason="graph_not_started")
        return None

    def _start_graph(self, document, old):
        self._graph_document = deepcopy(document)
        self._graph_old_id = old.subentry_id if old else None
        self._graph_original = deepcopy(dict(old.data)) if old else None

    async def async_step_graph(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        document = self._graph_document
        options = ["add_group"]
        if document["groups"]:
            options += ["edit_group", "delete_group"]
            if any(s.subentry_type == "zone" for s in self._get_entry().subentries.values()):
                options += ["add_actuator"]
        if document["actuators"]:
            options += ["edit_actuator", "delete_actuator"]
        options += ["save_graph", "cancel_graph"]
        return self.async_show_menu(
            step_id="graph", menu_options=options,
            description_placeholders={"groups": str(len(document["groups"])),
                                      "actuators": str(len(document["actuators"]))})

    def _display_ref(self, ref):
        if not ref:
            return None
        try:
            return resolved_reference(self.hass, ref, (ref["entity_id"].split(".")[0],))
        except HeatingConfigError:
            return ref  # Missing binding stays visible; final validation blocks it.

    def _group_schema(self, old=None):
        old = old or {}
        central = self._graph_document["central"]
        limits = old.get("supply_limits", central["supply_limits"])
        return vol.Schema({
            vol.Required("name", default=old.get("name", "")): str,
            vol.Required("emitter", default=old.get("emitter", "radiator")):
                choice(["radiator", "floor"], "heating_emitter"),
            vol.Required("minimum_supply_temperature", default=limits["minimum_centi_c"]/100):
                selector.NumberSelector({"min":5,"max":90,"step":0.1,"mode":"box","unit_of_measurement":"°C"}),
            vol.Required("maximum_supply_temperature", default=limits["maximum_centi_c"]/100):
                selector.NumberSelector({"min":5,"max":90,"step":0.1,"mode":"box","unit_of_measurement":"°C"}),
            optional("pump", self._display_ref(old.get("pump"))): entity(("switch",)),
            vol.Required("pump_start_delay_s", default=old.get("pump_start_delay_s",0)): number(0,3600),
            vol.Required("postrun_s", default=old.get("postrun_s",0)): number(0,7200),
            vol.Required("mixing_kind", default=(old.get("mixing") or {}).get("kind","none")):
                choice(["none","three_point","analog_0_10v"],"heating_mixing"),
        })

    def _group_options(self):
        return [{"value":g["group_id"],"label":g["name"]+" ("+g["group_id"]+")"}
                for g in self._graph_document["groups"]]

    def _actuator_options(self):
        labels = {"trv_room_setpoint":"TRV room target", "binary_valve":"Binary zone/floor valve",
                  "proportional_valve":"Position valve"}
        rooms = {s.data["room_id"]:s.title for s in self._get_entry().subentries.values()
                 if s.subentry_type == "zone"}
        return [{"value":a["actuator_id"],"label":labels[a["profile"]]+" / "+
                 rooms.get(a["room_id"],a["room_id"])+" / "+
                 self._display_ref(a["output"])["entity_id"]+" ("+a["actuator_id"]+")"}
                for a in self._graph_document["actuators"]]

    def _stage(self, document):
        parsed = validated_graph(self.hass, self._get_entry(), document)
        self._graph_document = parsed.storage_document()

    async def async_step_add_group(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        self._editing_group = None
        self._new_group_id = uuid.uuid4().hex[:8]
        return await self.async_step_group()

    async def async_step_edit_group(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        if user_input is not None:
            self._editing_group = next(g for g in self._graph_document["groups"]
                                       if g["group_id"] == user_input["group_id"])
            return await self.async_step_group()
        return self.async_show_form(step_id="edit_group", data_schema=vol.Schema({
            vol.Required("group_id"): choice(self._group_options())}))

    async def async_step_group(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        old = getattr(self, "_editing_group", None)
        errors = {}
        if user_input is not None:
            try:
                group = {
                    "group_id": old["group_id"] if old else self._new_group_id,
                    "name": user_input["name"], "emitter": user_input["emitter"],
                    "supply_limits": {
                        "minimum_centi_c": self._temperature(user_input["minimum_supply_temperature"]),
                        "maximum_centi_c": self._temperature(user_input["maximum_supply_temperature"])},
                    "pump": selected_reference(self.hass,user_input["pump"],("switch",))
                            if user_input.get("pump") else None,
                    "pump_start_delay_s": self._seconds(user_input["pump_start_delay_s"]),
                    "postrun_s": self._seconds(user_input["postrun_s"]), "mixing": None,
                }
                kind = user_input["mixing_kind"]
                if kind != "none":
                    self._pending_group, self._mixing_kind = group, kind
                    return await self.async_step_mixing()
                self._accept_group(group)
            except (ValueError, KeyError, OverflowError) as err:
                errors["base"] = error_key(err)
            else:
                return await self.async_step_graph()
        return self.async_show_form(step_id="group", data_schema=retained_input_schema(self,self._group_schema(old),user_input), errors=errors)

    @staticmethod
    def _seconds(value):
        if type(value) not in (int,float) or int(value) != value:
            raise HeatingConfigError("invalid_integer_or_bounds")
        return int(value)

    def _accept_group(self, group):
        document = deepcopy(self._graph_document)
        document["groups"] = [g for g in document["groups"] if g["group_id"] != group["group_id"]] + [group]
        self._stage(document)

    def _mix_schema(self):
        old = (self._editing_group or {}).get("mixing") or {}
        if old.get("kind") != self._mixing_kind:
            old = {}
        fields = {
            vol.Required("supply_sensor", **({"default":self._display_ref(old["supply_sensor"])["entity_id"]} if old else {})):
                selector.EntitySelector({"filter":[{"domain":"sensor","device_class":"temperature"}]}),
            vol.Required("travel_time_s",default=old.get("travel_time_s",120)): number(1,3600)}
        if self._mixing_kind == "three_point":
            for i,key in enumerate(("open_output","close_output")):
                fields[vol.Required(key, **({"default":self._display_ref(old["outputs"][i])["entity_id"]} if old else {}))] = entity(("switch",))
        else:
            fields[vol.Required("analog_output", **({"default":self._display_ref(old["outputs"][0])["entity_id"]} if old else {}))] = entity(("number",))
        return vol.Schema(fields)

    async def async_step_mixing(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        errors = {}
        if user_input is not None:
            try:
                kind = self._mixing_kind
                group = deepcopy(self._pending_group)
                outputs = ([selected_reference(self.hass,user_input[key],("switch",))
                            for key in ("open_output","close_output")] if kind=="three_point" else
                           [selected_reference(self.hass,user_input["analog_output"],("number",))])
                group["mixing"] = {"kind":kind,
                    "supply_sensor":selected_reference(self.hass,user_input["supply_sensor"],("sensor",)),
                    "outputs":outputs,"travel_time_s":self._seconds(user_input["travel_time_s"])}
                self._accept_group(group)
            except (ValueError, KeyError, OverflowError) as err:
                errors["base"] = error_key(err)
            else:
                return await self.async_step_graph()
        return self.async_show_form(step_id="mixing", data_schema=retained_input_schema(self,self._mix_schema(),user_input), errors=errors)

    async def async_step_delete_group(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        errors = {}
        if user_input is not None:
            gid = user_input["group_id"]
            children = [a for a in self._graph_document["actuators"] if a["group_id"]==gid]
            if children and not user_input.get("cascade_actuators",False):
                errors["base"] = "confirm_group_cascade"
            else:
                try:
                    document = deepcopy(self._graph_document)
                    document["groups"] = [g for g in document["groups"] if g["group_id"]!=gid]
                    document["actuators"] = [a for a in document["actuators"] if a["group_id"]!=gid]
                    self._stage(document)
                except (ValueError, KeyError, OverflowError) as err:
                    errors["base"] = error_key(err)
                else:
                    return await self.async_step_graph()
        return self.async_show_form(step_id="delete_group",data_schema=vol.Schema({
            vol.Required("group_id"):choice(self._group_options()),
            vol.Required("cascade_actuators",default=False):bool}),errors=errors)

    async def async_step_add_actuator(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        if not any(s.subentry_type == "zone" for s in self._get_entry().subentries.values()):
            return self.async_show_form(step_id="graph_error", data_schema=vol.Schema({}),
                                        errors={"base":"room_required"})
        self._editing_actuator = None
        self._new_actuator_id = uuid.uuid4().hex[:8]
        return await self.async_step_actuator()

    async def async_step_edit_actuator(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        if user_input is not None:
            self._editing_actuator = next(a for a in self._graph_document["actuators"]
                                          if a["actuator_id"]==user_input["actuator_id"])
            return await self.async_step_actuator()
        return self.async_show_form(step_id="edit_actuator",data_schema=vol.Schema({
            vol.Required("actuator_id"):choice(self._actuator_options())}))

    def _actuator_schema(self):
        old = self._editing_actuator or {}
        rooms = [{"value":s.data["room_id"],"label":s.title+" ("+s.data["room_id"]+")"}
                 for s in self._get_entry().subentries.values() if s.subentry_type=="zone"]
        return vol.Schema({
            vol.Required("room_id",**({"default":old["room_id"]} if old else {})):choice(rooms),
            vol.Required("group_id",**({"default":old["group_id"]} if old else {})):choice(self._group_options()),
            vol.Required("profile",default=old.get("profile","trv_room_setpoint")):
                choice(["trv_room_setpoint","binary_valve","proportional_valve"],"heating_actuator")})

    async def async_step_actuator(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        if user_input is not None:
            self._pending_actuator = {
                "actuator_id": self._editing_actuator["actuator_id"] if self._editing_actuator else self._new_actuator_id,
                "room_id":user_input["room_id"],"group_id":user_input["group_id"],"profile":user_input["profile"]}
            return await self.async_step_actuator_details()
        return self.async_show_form(step_id="actuator",data_schema=self._actuator_schema())

    def _actuator_detail_schema(self):
        profile = self._pending_actuator["profile"]
        old = self._editing_actuator or {}
        if old.get("profile") != profile:
            old = {}
        domains = {"trv_room_setpoint":("climate",),"binary_valve":("switch",),
                   "proportional_valve":("number","valve")}[profile]
        fields = {vol.Required("output",**({"default":self._display_ref(old["output"])["entity_id"]} if old else {})):entity(domains)}
        settings = old.get("settings",{})
        if profile=="binary_valve":
            fields.update({
                vol.Required("deenergized_position",**({"default":settings["deenergized_position"]} if "deenergized_position" in settings else {})):
                    choice(["normally_open","normally_closed"],"heating_deenergized"),
                vol.Required("control",default=settings.get("control","hysteresis")):
                    choice(["hysteresis","tpi"],"heating_binary_control"),
                vol.Required("travel_time_s",default=settings.get("travel_time_s",180)):number(1,3600),
                vol.Required("minimum_on_s",default=settings.get("minimum_on_s",180)):number(1,7200),
                vol.Required("minimum_off_s",default=settings.get("minimum_off_s",120)):number(1,7200)})
            cycle = settings.get("cycle_s")
            fields[vol.Optional("cycle_s",**({"description":{"suggested_value":cycle}} if cycle is not None else {}))]=number(60,86400)
        elif profile=="proportional_valve":
            fields.update({
                vol.Required("minimum_percent",default=settings.get("minimum_percent",0)):number(0,100),
                vol.Required("maximum_percent",default=settings.get("maximum_percent",100)):number(0,100),
                vol.Required("travel_time_s",default=settings.get("travel_time_s",60)):number(1,3600)})
        return vol.Schema(fields)

    async def async_step_actuator_details(self, user_input=None):
        if guard := self._graph_guard():
            return guard
        errors = {}
        if user_input is not None:
            try:
                item = deepcopy(self._pending_actuator)
                profile = item["profile"]
                domains = {"trv_room_setpoint":("climate",),"binary_valve":("switch",),
                           "proportional_valve":("number","valve")}[profile]
                item["output"] = selected_reference(self.hass,user_input["output"],domains)
                if profile=="trv_room_setpoint":
                    settings={}
                elif profile=="binary_valve":
                    settings={key:user_input[key] for key in ("deenergized_position","control")}
                    settings.update({key:self._seconds(user_input[key])
                                     for key in ("travel_time_s","minimum_on_s","minimum_off_s")})
                    settings["cycle_s"] = self._seconds(user_input["cycle_s"]) if user_input.get("cycle_s") is not None else None
                else:
                    settings={key:self._seconds(user_input[key])
                              for key in ("minimum_percent","maximum_percent","travel_time_s")}
                item["settings"]=settings
                document=deepcopy(self._graph_document)
                document["actuators"]=[a for a in document["actuators"] if a["actuator_id"]!=item["actuator_id"]]+[item]
                self._stage(document)
            except (ValueError, KeyError, OverflowError) as err:
                errors["base"]=error_key(err)
            else:
                return await self.async_step_graph()
        return self.async_show_form(step_id="actuator_details",data_schema=retained_input_schema(self,self._actuator_detail_schema(),user_input),errors=errors)

    async def async_step_delete_actuator(self,user_input=None):
        if guard := self._graph_guard():
            return guard
        errors={}
        if user_input is not None:
            if not user_input.get("confirm",False):
                errors["base"]="confirm_delete"
            else:
                try:
                    document=deepcopy(self._graph_document)
                    document["actuators"]=[a for a in document["actuators"] if a["actuator_id"]!=user_input["actuator_id"]]
                    self._stage(document)
                except (ValueError,KeyError) as err:
                    errors["base"]=error_key(err)
                else:
                    return await self.async_step_graph()
        return self.async_show_form(step_id="delete_actuator",data_schema=vol.Schema({
            vol.Required("actuator_id"):choice(self._actuator_options()),
            vol.Required("confirm",default=False):bool}),errors=errors)

    async def async_step_save_graph(self,user_input=None):
        if guard := self._graph_guard():
            return guard
        entry=self._get_entry()
        old=entry.subentries.get(self._graph_old_id) if self._graph_old_id else None
        if ((self._graph_old_id and (old is None or dict(old.data)!=self._graph_original))
            or (old is None and any(s.subentry_type=="heating" for s in entry.subentries.values()))):
            return self.async_abort(reason="graph_changed")
        try:
            parsed=validated_graph(self.hass,entry,self._graph_document)
        except (ValueError,KeyError) as err:
            return self.async_show_form(step_id="graph_error",data_schema=vol.Schema({}),
                                        errors={"base":error_key(err)})
        data={**(dict(old.data) if old else {}),
              "draft":parsed.storage_document(),"draft_digest":parsed.digest,"status":parsed.readiness,
              "incomplete_group_ids":list(parsed.incomplete_group_ids)}
        if old:
            return self.async_update_and_abort(entry,old,title="Heating settings (draft)",data=data,unique_id="central_heating")
        return self.async_create_entry(title="Heating settings (draft)",data=data,unique_id="central_heating")

    async def async_step_graph_error(self,user_input=None):
        return await self.async_step_graph()

    async def async_step_cancel_graph(self,user_input=None):
        return self.async_abort(reason="graph_cancelled")
