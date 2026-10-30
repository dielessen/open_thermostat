"""Negotiated complete room plan; configuration is NOT installation authority.

Only an independently selected logical installation profile may select this path.
Local review is never physical readiness, a new worker/store or per-config pin.
"""

from .room_contacts import context_record
from .product import configuration_subentries,heating_entries
from copy import deepcopy
from dataclasses import dataclass
import json,re

from .graph_shadow_validation import canonical,digest,raw_document,obj,integer,ident,exact,GraphValidationError,time_zone_name
from .v1_model import RoomBinding,EntityReference,ROOM_GRAPH_DRAFT,integration_mode,MODE_SHADOW
from .v1_heating_graph import validated_graph,resolved_reference

CONTRACT="control.plan.v1"
WEEK_CONTRACT="control.plan.week.v1"
KIND="installation.shadow.v1"
LEGACY_CAPABILITY="control.plan.legacy_readback.v1"
EVOLUTION_CAPABILITY="control.plan.profile_evolution.v1"
LIMITS=dict(zones=2,groups=2,channels=4,config_bytes=4096,wire_bytes=8192,total_transitions=8)
WEEK_LIMITS={**LIMITS,"total_transitions":256}
# Existing native SOURCE contracts use the independent default 5 C frost target.
# A wire/GUI comfort profile cannot replace that source policy.
NATIVE_FROST_TARGET_CENTI_C=500
HEX=re.compile(r"[0-9a-f]{64}")

def require(ok,code):
    if not ok:raise GraphValidationError(code)

@dataclass(frozen=True,slots=True)
class NativeInstallationPolicy:
    entry_unique_id:str
    controller_id:str
    adapter_id:str
    profile_digest:str
    legacy_readback_reviewed:bool=False
    predecessor_profile_digest:str=""
    week_reviewed:bool=False

    @property
    def plan_contract(self):
        return WEEK_CONTRACT if self.week_reviewed else CONTRACT

    def validate(self):
        require(isinstance(self.entry_unique_id,str) and 1<=len(self.entry_unique_id)<=128,"native_entry")
        ident(self.controller_id);ident(self.adapter_id)
        require(type(self.legacy_readback_reviewed) is bool,"native_legacy_profile")
        require(type(self.week_reviewed) is bool and not (self.week_reviewed and self.legacy_readback_reviewed),"native_week_profile")
        require(type(self.predecessor_profile_digest) is str and (not self.predecessor_profile_digest
            or (HEX.fullmatch(self.predecessor_profile_digest) and not self.legacy_readback_reviewed)),"native_predecessor_profile")
        require(isinstance(self.profile_digest,str) and HEX.fullmatch(self.profile_digest),"native_profile")

    def matches(self,p):
        self.validate()
        expected=dict(schema=2,kind=KIND,adapter_id=self.adapter_id,profile_digest=self.profile_digest,
            plan_contract=self.plan_contract,physical_outputs_enabled=False,frost_protection_available=False,
            limits=WEEK_LIMITS if self.week_reviewed else LIMITS)
        if self.legacy_readback_reviewed:
            expected.update(schema=3,kind="installation.shadow.v2",legacy_readback="schema1_quarantine_only")
        if self.predecessor_profile_digest:
            expected.update(schema=4,kind="installation.shadow.v3",predecessor_profile_digest=self.predecessor_profile_digest)
        return (p.get("controller_id")==self.controller_id and type(p.get("source_policy")) is dict
            and canonical(p["source_policy"])==canonical(expected))

def _native_layout(hass,entry,*,allow_single=False,room_replacement=None,draft_replacement=None):
    """Pure desired native layout, not qualification or source-report evidence."""
    require(integration_mode(entry)==MODE_SHADOW,"native_mode")
    rooms=[RoomBinding.from_dict(dict(s.data)) for s in entry.subentries.values() if s.subentry_type=="zone"]
    require((room_replacement is None)==(draft_replacement is None),"native_prospective_layout")
    if room_replacement is not None:
        require(type(room_replacement) is RoomBinding and sum(r.room_id==room_replacement.room_id for r in rooms)==1,
            "native_room_binding")
        rooms=[room_replacement if r.room_id==room_replacement.room_id else r for r in rooms]
    groups=heating_entries(entry)
    require((1<=len(rooms)<=2 if allow_single else len(rooms)==2) and len(groups)==1
        and len({r.room_id for r in rooms})==len(rooms),"native_two_room_limit")
    from .manual_target import is_manual_helper
    require(all(r.binding_mode==ROOM_GRAPH_DRAFT and not r.actuators
        and (r.setpoint is None or is_manual_helper(r.setpoint)) for r in rooms),"native_room_mode")
    document=dict(groups[0].data)["draft"] if draft_replacement is None else draft_replacement
    draft=validated_graph(hass,entry,document,room_replacement=room_replacement)
    proposal=deepcopy(draft.control_proposal())
    require(len(proposal["groups"])==len(proposal["actuators"])==len(rooms),"native_group_limit")
    require(proposal["central"]["weather_enabled"] is False and proposal["central"]["outdoor_channel"] is None
        and all(g["mixing"] is None and g["pump_channel"] is None and g["pump_start_delay_s"]==g["postrun_s"]==0 for g in proposal["groups"]),
        "native_unsupported_hydraulic_policy")
    for g in proposal["groups"]:g.pop("name",None)
    return sorted(rooms,key=lambda r:r.room_id),draft,proposal

def native_entry_state(entry):
    return canonical(dict(entry_id=entry.entry_id,unique_id=entry.unique_id,data=dict(entry.data),options=dict(entry.options),
        # The presentation groups (one per E32 room) come and go with the telemetry; never a guard.
        subentries={key:dict(kind=s.subentry_type,data=dict(s.data)) for key,s in configuration_subentries(entry).items()}))

@dataclass(frozen=True,slots=True)
class NativePlanSource:
    """Independent immutable logical SHADOW profile; config/DATA never qualify it."""
    policy:NativeInstallationPolicy
    profile_json:str
    bindings_json:str
    predecessor:object=None

    @property
    def room_count(self):return len(self.documents()[0]["zones"])
    @property
    def profile_version(self):return self.policy.plan_contract

    def documents(self):
        require(type(self.policy) is NativeInstallationPolicy,"native_policy_type");self.policy.validate()
        require(type(self.profile_json) is str and len(self.profile_json.encode())<=4096,"native_profile_budget")
        profile=raw_document(self.profile_json)
        legacy=self.policy.legacy_readback_reviewed
        obj(profile,"adapter_id controller_id kind layout_digest mapping_revision schema zones"+(" legacy_readback" if legacy else ""))
        exact(profile["schema"],3 if self.policy.week_reviewed else 2 if legacy else 1)
        exact(profile["kind"],"native_profile.week.v1" if self.policy.week_reviewed else "native_profile.shadow.v2" if legacy else "native_profile.shadow.v1")
        if legacy:exact(profile["legacy_readback"],"schema1_quarantine_only")
        exact(profile["controller_id"],self.policy.controller_id);exact(profile["adapter_id"],self.policy.adapter_id)
        require(digest(profile)==self.policy.profile_digest and HEX.fullmatch(profile["layout_digest"]),"native_profile_digest")
        integer(profile["mapping_revision"],1,4294967295)
        rows=profile["zones"];require(type(rows) is list and
            (1<=len(rows)<=2 if self.policy.week_reviewed else len(rows)==2),"native_profile_limit")
        keys="actuator_id actuator_profile control emitter group_id maximum_sensor_age_ms maximum_supply_centi_c maximum_target_centi_c minimum_supply_centi_c minimum_target_centi_c output_resource report_evidence sensor_id sensor_resource zone_id"
        ids={"adapter","config","snapshot"};resources=set();previous="";emitters=set()
        for z in rows:
            obj(z,keys)
            require(isinstance(z["zone_id"],str) and re.fullmatch(r"[0-9a-f]{8}",z["zone_id"]) and z["zone_id"]>previous,"native_zone_identity")
            previous=z["zone_id"]
            for k in ("zone_id","sensor_id","actuator_id","group_id"):
                ident(z[k]);require(z[k] not in ids,"native_owner_overlap");ids.add(z[k])
            require((z["emitter"],z["actuator_profile"]) in (("floor","binary_valve"),("radiator","trv_room_setpoint"))
                and (self.policy.week_reviewed or z["emitter"] not in emitters),"native_emitter_profile");emitters.add(z["emitter"])
            for k in ("sensor_resource","output_resource"):
                require(isinstance(z[k],str) and HEX.fullmatch(z[k]) and z[k] not in resources,"native_resource_overlap");resources.add(z[k])
            lo=integer(z["minimum_target_centi_c"],500,3500);integer(z["maximum_target_centi_c"],lo,3500)
            lo=integer(z["minimum_supply_centi_c"],500,8999);integer(z["maximum_supply_centi_c"],lo+1,9000)
            integer(z["maximum_sensor_age_ms"],1000,120000)
            require(z["report_evidence"] in ("physical_report","validated_integration_report"),"native_evidence")
            c=obj(z["control"],"cycle_ms hysteresis_centi_c ki_permille_per_c_minute kp_permille_per_c minimum_off_ms minimum_on_ms mode")
            integer(c["hysteresis_centi_c"],1,200)
            if z["emitter"]=="floor":
                exact(c["mode"],"slow_binary_pi")
                integer(c["kp_permille_per_c"],1,1000);integer(c["ki_permille_per_c_minute"],0,1000)
                cycle=integer(c["cycle_ms"],600000,3600000)
                integer(c["minimum_on_ms"],120000,cycle//2);integer(c["minimum_off_ms"],120000,cycle//2)
            else:
                exact(c["mode"],"local_trv")
                for key in ("cycle_ms","minimum_off_ms","minimum_on_ms","kp_permille_per_c","ki_permille_per_c_minute"):integer(c[key],0,0)
        require(type(self.bindings_json) is str and len(self.bindings_json.encode())<=4096,"native_binding_budget")
        try:bindings=json.loads(self.bindings_json)
        except (ValueError,TypeError):raise GraphValidationError("native_bindings") from None
        require(type(bindings) is dict and canonical(bindings)==self.bindings_json
            and set(bindings)=={z[k] for z in rows for k in ("sensor_id","actuator_id")},"native_bindings")
        for ref in bindings.values():
            obj(ref,"entity_id platform unique_id")
            require(all(isinstance(ref[k],str) and 1<=len(ref[k])<=255 for k in ref),"native_bindings")
        return profile,bindings

    def validate(self):
        profile,_=self.documents()
        previous=self.predecessor
        require((previous is None)==(not self.policy.predecessor_profile_digest),"native_predecessor_required")
        if previous is not None:
            require(type(previous) is NativePlanSource and previous is not self and previous.predecessor is None,
                "native_predecessor_depth")
            previous.validate();old,_=previous.documents()
            require(not previous.policy.legacy_readback_reviewed and not self.policy.legacy_readback_reviewed
                and previous.policy.entry_unique_id==self.policy.entry_unique_id
                and previous.policy.controller_id==self.policy.controller_id
                and previous.policy.adapter_id==self.policy.adapter_id
                and previous.policy.profile_digest==self.policy.predecessor_profile_digest
                and previous.policy.profile_digest!=self.policy.profile_digest
                and old["mapping_revision"]<4294967295 and profile["mapping_revision"]==old["mapping_revision"]+1,
                "native_predecessor_binding")

    def is_predecessor_config(self,config):
        return self.predecessor is not None and config.get("schema")==2 and config.get("profile_digest")==self.policy.predecessor_profile_digest

    def validate_predecessor_config(self,config):
        self.validate()
        require(self.is_predecessor_config(config),"native_predecessor_config")
        return self.predecessor.validate_plan(config)

    def supports_room(self,room):
        profile,_=self.documents()
        return room.binding_mode==ROOM_GRAPH_DRAFT and room.room_id in {z["zone_id"] for z in profile["zones"]}

    def registry_references(self,hass,entry):
        return tuple(self.documents()[1].values())

    def validate_native(self,hass,entry):
        return self._validate_native_layout(hass,entry)

    def validate_prospective_native(self,hass,entry,room,draft):
        """Validate explicit pending intent against the real registry and owner.

        This does not select a source, alter the entry or authorize a worker.
        Normal runtime validation always reads the actual saved layout.
        """
        return self._validate_native_layout(hass,entry,room_replacement=room,draft_replacement=draft)

    def _validate_native_layout(self,hass,entry,*,room_replacement=None,draft_replacement=None):
        self.validate()
        profile,bindings=self.documents()
        require(entry.unique_id==self.policy.entry_unique_id
            and entry.options.get("adapter_id",entry.data.get("adapter_id"))==self.policy.adapter_id,"native_owner")
        rooms,draft,proposal=_native_layout(hass,entry,allow_single=self.policy.week_reviewed,
            room_replacement=room_replacement,draft_replacement=draft_replacement)
        require(len(rooms)==len(profile["zones"]),"native_room_binding")
        require(digest(proposal)==profile["layout_digest"],"native_layout_review_required")
        rows={z["zone_id"]:z for z in profile["zones"]}
        groups={g["group_id"]:g for g in proposal["groups"]}
        for room in rooms:
            z=rows.get(room.room_id);require(z is not None,"native_room_binding")
            require(z["minimum_target_centi_c"]<=room.minimum_target_centi_c<=room.base_centi_c
                <=room.maximum_target_centi_c<=z["maximum_target_centi_c"]
                and 1000<=room.maximum_age_ms<=z["maximum_sensor_age_ms"],"native_target_limits")
            sensor=resolved_reference(hass,room.temperature.as_dict(),("sensor",),temperature=True)
            require(digest({"native_registry_identity":list(EntityReference.from_dict(sensor).identity())})==z["sensor_resource"],"native_sensor_binding")
            for key,resource,domains in (
                (z["sensor_id"],z["sensor_resource"],("sensor",)),
                (z["actuator_id"],z["output_resource"],("switch",) if z["emitter"]=="floor" else ("climate",))):
                ref=resolved_reference(hass,bindings[key],domains,temperature=key==z["sensor_id"])
                require(digest({"native_registry_identity":list(EntityReference.from_dict(ref).identity())})==resource,"native_resource_binding")
            g=groups.get(z["group_id"]);require(g is not None and g["emitter"]==z["emitter"]
                and g["supply_limits"]==dict(minimum_centi_c=z["minimum_supply_centi_c"],maximum_centi_c=z["maximum_supply_centi_c"]),"native_supply_profile")
            a=next((a for a in proposal["actuators"] if a["room_id"]==room.room_id),None)
            require(a is not None and a["actuator_id"]==z["actuator_id"] and a["group_id"]==z["group_id"]
                and a["profile"]==z["actuator_profile"],"native_actuator_binding")
            if z["emitter"]=="floor":
                c=z["control"];settings=a["settings"]
                require(settings["cycle_s"]*1000==c["cycle_ms"] and settings["minimum_on_s"]*1000==c["minimum_on_ms"]
                    and settings["minimum_off_s"]*1000==c["minimum_off_ms"],"native_control_profile")
        return rooms,profile

    async def async_configuration(self,hass,entry,*,start=None):
        return await self._async_configuration(hass,entry,start=start)

    async def async_prospective_configuration(self,hass,entry,room,draft,*,start=None):
        """Compile pending intent; never persist it or authorize its execution."""
        return await self._async_configuration(hass,entry,start=start,
            room_replacement=room,draft_replacement=draft)

    async def _async_configuration(self,hass,entry,*,start=None,room_replacement=None,draft_replacement=None):
        from .v1_mqtt import async_room_schedule
        before=native_entry_state(entry)
        rooms,profile=self._validate_native_layout(hass,entry,
            room_replacement=room_replacement,draft_replacement=draft_replacement)
        rows={z["zone_id"]:z for z in profile["zones"]};zones=[];channels=[];groups=[]
        for room in rooms:
            z=rows[room.room_id];schedule=await async_room_schedule(hass,room,start)
            if schedule is not None and self.policy.week_reviewed:
                from .compact_schedule import compact_schedule
                schedule=compact_schedule(schedule)
            zone=dict(zone_id=room.room_id,sensor_id=z["sensor_id"],actuator_id=z["actuator_id"],
                actuator_profile=z["actuator_profile"],group_id=z["group_id"],base_centi_c=room.base_centi_c,
                max_age_ms=room.maximum_age_ms,report_evidence=z["report_evidence"],schedule=schedule)
            zone.update(context_record(room))
            zones.append(zone)
            for cid,direction,owner,res in ((z["sensor_id"],"input",room.room_id,z["sensor_resource"]),
                (z["actuator_id"],"output",z["actuator_id"],z["output_resource"])):
                channels.append(dict(channel_id=cid,direction=direction,owner_id=owner,resource_id=res))
            groups.append({k:z[k] for k in ("emitter","group_id","maximum_supply_centi_c","minimum_supply_centi_c")})
        require(before==native_entry_state(entry),"native_entry_changed_during_compile")
        self._validate_native_layout(hass,entry,room_replacement=room_replacement,
            draft_replacement=draft_replacement) # Registry/owner/layout after LAST schedule await.
        mapping=dict(channels=sorted(channels,key=lambda c:c["channel_id"]),mapping_revision=profile["mapping_revision"],mapping_schema=2)
        config=dict(schema=2,mode="shadow_plan",revision=1,profile_digest=self.policy.profile_digest,
            mapping=mapping,mapping_digest=digest(mapping),groups=sorted(groups,key=lambda g:g["group_id"]),zones=zones)
        if self.policy.week_reviewed:config["plan_contract"]=WEEK_CONTRACT
        self.validate_plan(config)
        return config,deepcopy(mapping)

    def validate_plan(self,config):
        """Same bounded product schema as real C++decoder; no session admission."""
        profile,_=self.documents();value=raw_document(canonical(config))
        require(len(canonical(value))<=4096,"native_config_budget")
        obj(value,"groups mapping mapping_digest mode profile_digest revision schema zones"+(" plan_contract" if self.policy.week_reviewed else ""))
        if self.policy.week_reviewed:exact(value["plan_contract"],WEEK_CONTRACT)
        exact(value["schema"],2);exact(value["mode"],"shadow_plan");exact(value["profile_digest"],self.policy.profile_digest,"native_profile_digest")
        integer(value["revision"],1,4294967295)
        m=obj(value["mapping"],"channels mapping_revision mapping_schema")
        exact(m["mapping_schema"],2);exact(m["mapping_revision"],profile["mapping_revision"],"native_mapping_revision")
        exact(value["mapping_digest"],digest(m),"native_mapping_digest")
        expected=[]
        for z in profile["zones"]:
            for cid,direction,owner,res in ((z["sensor_id"],"input",z["zone_id"],z["sensor_resource"]),
                (z["actuator_id"],"output",z["actuator_id"],z["output_resource"])):
                expected.append(dict(channel_id=cid,direction=direction,owner_id=owner,resource_id=res))
        require(m["channels"]==sorted(expected,key=lambda c:c["channel_id"]),"native_mapping_conflict")
        require(value["groups"]==sorted([{k:z[k] for k in ("emitter","group_id","maximum_supply_centi_c","minimum_supply_centi_c")} for z in profile["zones"]],key=lambda g:g["group_id"]),"native_group_conflict")
        require(type(value["zones"]) is list and len(value["zones"])==len(profile["zones"]),"native_two_room_limit")
        previous="";transitions=0
        for zone in value["zones"]:
            keys="actuator_id actuator_profile base_centi_c group_id max_age_ms report_evidence schedule sensor_id zone_id"
            obj(zone,keys+(" comfort" if "comfort" in zone else "")+(" contacts" if "contacts" in zone else ""))
            if 'contacts' in zone:
                require('comfort' not in zone, 'native_contact_policy')
                c = obj(zone['contacts'], 'maximum_age_ms')
                integer(c['maximum_age_ms'], 1000, 86400000)
            rid=zone["zone_id"];require(type(rid) is str and rid>previous,"native_zone_order");previous=rid
            z=next((x for x in profile["zones"] if x["zone_id"]==rid),None);require(z is not None,"native_zone_binding")
            for k in ("actuator_id","actuator_profile","group_id","report_evidence","sensor_id"):exact(zone[k],z[k],"native_zone_binding")
            integer(zone["base_centi_c"],z["minimum_target_centi_c"],z["maximum_target_centi_c"])
            integer(zone["max_age_ms"],1000,z["maximum_sensor_age_ms"])
            if "comfort" in zone:
                c=obj(zone["comfort"],"away_centi_c frost_centi_c maximum_centi_c minimum_centi_c presence temporary_ms window"
                    +(" window_max_age_ms" if "window_max_age_ms" in zone["comfort"] else ""))
                if "window_max_age_ms" in c:
                    require(c["window"] is True,"native_contact_policy")
                    integer(c["window_max_age_ms"],1000,86400000)
                lo=integer(c["minimum_centi_c"],z["minimum_target_centi_c"],z["maximum_target_centi_c"])
                hi=integer(c["maximum_centi_c"],lo,z["maximum_target_centi_c"])
                for k in ("away_centi_c","frost_centi_c"):integer(c[k],lo,hi)
                require(c['frost_centi_c']==NATIVE_FROST_TARGET_CENTI_C,'native_comfort_frost_profile')
                integer(c["temporary_ms"],60000,43200000)
                require(type(c["window"]) is type(c["presence"]) is bool,"native_comfort")
                integer(zone["base_centi_c"],lo,hi)
            if zone["schedule"] is not None:
                schedule=zone["schedule"]
                if self.policy.week_reviewed:
                    from .compact_schedule import expand_schedule
                    schedule=expand_schedule(schedule)
                c=obj(schedule,"base_centi_c policy timezone transitions valid_from_utc valid_until_utc")
                require(time_zone_name(c["timezone"]) and c["policy"]=="wall-clock-membership/v1","native_schedule")
                begin=integer(c["valid_from_utc"],946684800,4102444799)
                end=integer(c["valid_until_utc"],begin+1,min(begin+16*86400,4102444800))
                integer(c["base_centi_c"],z["minimum_target_centi_c"],z["maximum_target_centi_c"])
                ts=c["transitions"];require(type(ts) is list and len(ts)>=1,"native_schedule")
                transitions+=len(ts)
                require(len(ts)<=128 and transitions<=(256 if self.policy.week_reviewed else 8),"native_transition_limit")
                at=begin-1
                for point in ts:
                    require(type(point) is list and len(point)==2,"native_schedule")
                    at=integer(point[0],at+1,end-1);integer(point[1],z["minimum_target_centi_c"],z["maximum_target_centi_c"])
                require(ts[0][0]==begin,"native_schedule")
        return value

    def validate_legacy_config(self,config):
        """Reviewed READBACK ONLY. This method cannot qualify an active plan."""
        require(self.policy.legacy_readback_reviewed,"native_legacy_profile_required")
        profile,_=self.documents();v=raw_document(canonical(config))
        require(len(canonical(v))<=4096,"native_legacy_budget")
        obj(v,"mapping_digest mode revision schema zones")
        exact(v["schema"],1);exact(v["mode"],"shadow");integer(v["revision"],1,4294967295)
        require(type(v["mapping_digest"]) is str and HEX.fullmatch(v["mapping_digest"]),"native_legacy_mapping")
        require(type(v["zones"]) is list and 1<=len(v["zones"])<=2,"native_legacy_room_limit")
        ids={"adapter","config","snapshot"};transitions=0
        for zone in v["zones"]:
            obj(zone,"actuator_id base_centi_c max_age_ms report_evidence schedule sensor_id zone_id")
            z=next((x for x in profile["zones"] if x["zone_id"]==zone["zone_id"]),None)
            require(z is not None,"native_legacy_room_loss")
            for k in ("zone_id","sensor_id"):
                ident(zone[k]);require(zone[k] not in ids,"native_legacy_identity");ids.add(zone[k])
            require(type(zone["actuator_id"]) is str,"native_legacy_identity")
            if zone["actuator_id"]:
                ident(zone["actuator_id"]);require(zone["actuator_id"] not in ids,"native_legacy_identity");ids.add(zone["actuator_id"])
            integer(zone["base_centi_c"],z["minimum_target_centi_c"],z["maximum_target_centi_c"])
            integer(zone["max_age_ms"],1000,z["maximum_sensor_age_ms"])
            exact(zone["report_evidence"],z["report_evidence"])
            schedule=zone["schedule"]
            if schedule is None:continue
            obj(schedule,"base_centi_c policy timezone transitions valid_from_utc valid_until_utc")
            exact(schedule["policy"],"wall-clock-membership/v1")
            require(time_zone_name(schedule["timezone"]),"native_legacy_schedule")
            begin=integer(schedule["valid_from_utc"],946684800,4102444799)
            end=integer(schedule["valid_until_utc"],begin+1,min(begin+16*86400,4102444800))
            integer(schedule["base_centi_c"],z["minimum_target_centi_c"],z["maximum_target_centi_c"])
            points=schedule["transitions"];require(type(points) is list and points,"native_legacy_schedule")
            transitions+=len(points);require(transitions<=8,"native_legacy_transition_limit")
            at=begin-1
            for point in points:
                require(type(point) is list and len(point)==2,"native_legacy_schedule")
                at=integer(point[0],at+1,end-1);integer(point[1],z["minimum_target_centi_c"],z["maximum_target_centi_c"])
            require(points[0][0]==begin,"native_legacy_schedule")
        return v
