"""Versioned one-floor DATA + independently SOURCE-reviewed native TRV target.
No new protocol/worker/owner; no claim of two-room API2 DATA support.
"""

from .product import heating_entries
from copy import deepcopy
from dataclasses import dataclass
from .graph_draft_compile import GraphDraftSource
from .graph_topology_review import TopologyReviewContext,validate_topology_review,native_topology_plan
from .graph_shadow_validation import (canonical,digest,raw_document,validate_graph_shadow,
    GraphValidationContext,GraphValidationError)
from .graph_shadow_storage import GraphShadowJournal,native_graph_journal
from .graph_wire import GraphSourceProfile
from .topology_control_source import TopologyControllerEntrySource

VERSION="graph-floor-native-trv.v1"

def require(ok,code):
    if not ok:raise GraphValidationError(code)

@dataclass(frozen=True)
class GraphFloorTopologyDraftSource(GraphDraftSource):
    context: TopologyReviewContext
    review_json: str
    scope=VERSION

    def review(self):
        require(type(self.context) is TopologyReviewContext,"bridge_context")
        review=validate_topology_review(self.review_json,self.context)
        require(canonical(review)==self.review_json,"bridge_review_canonical")
        return review

    def validate(self,anchor):
        super().validate(anchor)
        self.review()

    def select_native(self,hass,entry):
        """Pure representation scope; native full plan pinned BEFORE/AFTER awaits."""
        from .v1_model import RoomBinding
        from .v1_heating_graph import validated_graph
        review=self.review()
        require(native_topology_plan(hass,entry)==review["plan"],"bridge_native_review_changed")
        floor=next(r for r in review["plan"]["rooms"] if r["emitter"]=="floor")
        rooms=[RoomBinding.from_dict(dict(s.data)) for s in entry.subentries.values() if s.subentry_type=="zone"]
        room=next(r for r in rooms if r.room_id==floor["zone_id"])
        heating=next(iter(heating_entries(entry)))
        whole=validated_graph(hass,entry,dict(heating.data)["draft"]).storage_document()
        # Full plan/digest above remains pinned. These are only the supported
        # floor DATA fields, not silent removal of the native radiator owner.
        value=deepcopy(whole)
        value["groups"]=[g for g in value["groups"] if g["group_id"]==floor["group_id"]]
        value["actuators"]=[a for a in value["actuators"] if a["actuator_id"]==floor["actuator_id"]]
        require(len(value["groups"])==len(value["actuators"])==1,"bridge_floor_scope")
        validated_graph(hass,entry,value)
        from .graph_draft_compile import _resource
        _,refs=self.documents()
        claims={r[k] for r in review["plan"]["rooms"] for k in ("sensor_resource","output_resource")}
        # Only the floor's two existing DATA resources may overlap its SOURCE
        # resources; feedback must never reserve the radiator's source/output.
        for ref in refs.values():
            resource=_resource(ref)
            require(resource not in claims or resource in (floor["sensor_resource"],floor["output_resource"]),
                    "bridge_resource_overlap")
        return room,value

def validate_floor_link(record,source):
    """DATA translation check only. Cannot create a profile or runtime grant."""
    GraphShadowJournal._record(record)
    graph=source.graph
    require(isinstance(graph,GraphSourceProfile) and isinstance(graph.draft_source,GraphFloorTopologyDraftSource),
            "bridge_graph_profile")
    graph.validate()
    require(graph.entry_unique_id==source.controller.entry_unique_id
            and graph.controller_id==source.controller.controller_id
            and graph.draft_source.context==source.context
            and graph.draft_source.review_json==source.review_json,"bridge_source_scope")
    cfg=record["config"];mapping=record["mapping"]
    require(cfg["revision"]==source.context.config_revision+1,"bridge_revision")
    require(mapping["mapping_revision"]==source.context.registry_revision,"bridge_registry_revision")
    context=GraphValidationContext(controller_id=source.controller.controller_id,boot_id="source_data",
        epoch=1,adapter_id=source.controller.adapter_id,adapter_session_id="source_data",
        grant_id="not_admission",grant_sequence=1,current_revision=cfg["revision"]-1,
        mapping_revision=mapping["mapping_revision"],mapping_digest=digest(mapping),
        qualification_digest=graph.qualification_digest)
    validate_graph_shadow(canonical(GraphShadowJournal._envelope(record,context,1)),canonical(mapping),context)
    rooms=source.review()["plan"]["rooms"];i=next(i for i,r in enumerate(rooms) if r["emitter"]=="floor")
    floor=rooms[i];r=cfg["rooms"][0];a=cfg["actuators"][0];g=cfg["groups"][0]
    require(r["schedule"] is None and a["profile"]=="binary_valve" and g["emitter"]=="floor",
            "bridge_unsupported_floor")
    pairs={"zone_id":"zone_id","base_centi_c":"base_centi_c","max_age_ms":"max_age_ms",
           "minimum_target_centi_c":"minimum_target_centi_c","maximum_target_centi_c":"maximum_target_centi_c"}
    require(all(r[k]==floor[v] for k,v in pairs.items())
            and r["sensor_id"]=="s_"+floor["zone_id"] and r["report_evidence"]==source.evidence[i]
            and a["actuator_id"]==floor["actuator_id"] and a["group_id"]==floor["group_id"]
            and g["supply_limits"]==dict(minimum_centi_c=floor["minimum_supply_centi_c"],
                                        maximum_centi_c=floor["maximum_supply_centi_c"]),
            "bridge_floor_conflict")
    channels={c["channel_id"]:c for c in mapping["channels"]}
    require(channels[r["sensor_id"]]["resource_id"]==floor["sensor_resource"]
            and channels[a["output_channel"]]["resource_id"]==floor["output_resource"],
            "bridge_mapping_conflict")
    reserved={r[k] for r in rooms for k in ("sensor_resource","output_resource")}
    require(all(c["resource_id"] not in reserved for c in mapping["channels"]
                if c["channel_id"] not in (r["sensor_id"],a["output_channel"])),
            "bridge_resource_overlap")
    return context

@dataclass(frozen=True,slots=True)
class GraphFloorControllerEntrySource(TopologyControllerEntrySource):
    profile_version: str = VERSION
    graph: GraphSourceProfile|None = None
    accepted_record_json: str = ""

    def data_record(self):
        require(type(self.accepted_record_json) is str and len(self.accepted_record_json.encode())<=4096,
                "bridge_record_budget")
        record=raw_document(self.accepted_record_json)
        require(canonical(record)==self.accepted_record_json,"bridge_record_canonical")
        return record

    def validate(self):
        require(self.profile_version==VERSION,"bridge_profile_version")
        # Existing independent SOURCE/policy/config/review bounds remain exact.
        TopologyControllerEntrySource(self.controller,self.context,self.review_json,self.evidence,
                                      schema=self.schema).validate()
        validate_floor_link(self.data_record(),self)

    async def async_configuration(self,hass,entry):
        from .graph_draft_compile import async_compile_graph_data
        self.validate()
        require(entry.unique_id==self.controller.entry_unique_id and
            entry.options.get("adapter_id",entry.data.get("adapter_id"))==self.controller.adapter_id,
            "bridge_owner")
        # Keep entry/owner identity separate from the topological digest:
        # the final Store await may change adapter/options without changing
        # native_topology_plan at all.
        entry_state=(entry.entry_id,entry.unique_id,deepcopy(dict(entry.data)),deepcopy(dict(entry.options)))
        record=self.data_record();context=validate_floor_link(record,self)
        journal=native_graph_journal(hass,entry,self.graph.qualification_digest)
        state=await journal.async_initialize()
        require(state["accepted"]==record and state["staged"] is None,"bridge_exact_readback_required")
        raw,mapping=await async_compile_graph_data(hass,entry,context,self.graph.draft_source)
        require(raw_document(raw)["config"]==record["config"] and raw_document(mapping)==record["mapping"],
                "bridge_native_changed")
        require(await journal.store.async_load()==state and journal.state==state,"bridge_store_changed")
        require((entry.entry_id,entry.unique_id,dict(entry.data),dict(entry.options))==entry_state
                and entry.unique_id==self.controller.entry_unique_id
                and entry.options.get("adapter_id",entry.data.get("adapter_id"))==self.controller.adapter_id,
                "bridge_owner_changed_after_store")
        # The topological review covers room sensor/output identities, not
        # the floor DATA feedback channel. Resolve all THREE existing private
        # DATA bindings again after the final Store await; registry existence
        # is still not physical availability/readiness qualification.
        from .v1_heating_graph import resolved_reference
        qualification,bindings=self.graph.draft_source.documents()
        sensor=qualification["sources"][0]["channel_id"]
        output=qualification["devices"][0]["output_channel"]
        for channel,ref in bindings.items():
            domains=("sensor",) if channel==sensor else ("switch",) if channel==output else ("binary_sensor",)
            resolved_reference(hass,ref,domains,temperature=channel==sensor)
        require(native_topology_plan(hass,entry)==self.review()["plan"],"bridge_native_review_changed")
        return self.projection(),deepcopy(self.record()["mapping"])

    def registry_references(self,hass,entry):
        return (*TopologyControllerEntrySource.registry_references(self,hass,entry),*self.graph.draft_source.documents()[1].values())
