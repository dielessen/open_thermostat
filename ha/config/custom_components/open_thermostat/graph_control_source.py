"""Explicit reviewed SOURCE caller contract, not graph_ready authority."""
from dataclasses import dataclass
from copy import deepcopy
from .comfort_sources import ControllerPolicySourceProfile
from .graph_wire import GraphSourceProfile
from .graph_shadow_storage import GraphShadowJournal,native_graph_journal
from .graph_shadow_validation import (GraphValidationContext,GraphValidationError,
    canonical,digest,raw_document,validate_graph_shadow)

def require(value,code):
    if not value:raise GraphValidationError(code)

@dataclass(frozen=True,slots=True)
class GraphControllerEntrySource:
    graph: GraphSourceProfile
    controller: ControllerPolicySourceProfile
    accepted_record_json: str
    schema: int = 1

    def record(self):
        require(type(self.schema) is int and self.schema==1,"graph_control_source_schema")
        require(type(self.accepted_record_json) is str
                and len(self.accepted_record_json.encode())<=4096,"graph_control_source_budget")
        record=raw_document(self.accepted_record_json)
        GraphShadowJournal._record(record)
        require(canonical(record)==self.accepted_record_json,"graph_control_source_canonical")
        return record

    def context(self,record):
        return GraphValidationContext(controller_id=self.controller.controller_id,boot_id="source_data",
            epoch=1,adapter_id=self.controller.adapter_id,adapter_session_id="source_data",
            grant_id="not_admission",grant_sequence=1,current_revision=record["config"]["revision"]-1,
            mapping_revision=record["mapping"]["mapping_revision"],mapping_digest=digest(record["mapping"]),
            qualification_digest=self.graph.qualification_digest)

    def projection(self):
        record=self.record();cfg=record["config"]
        require(len(cfg["rooms"])==len(cfg["actuators"])==1,"graph_control_topology")
        room,actuator=cfg["rooms"][0],cfg["actuators"][0]
        return dict(schema=1,mode="shadow",revision=cfg["revision"],mapping_digest=cfg["mapping_digest"],
            zones=[dict(zone_id=room["zone_id"],sensor_id=room["sensor_id"],actuator_id=actuator["actuator_id"],
                base_centi_c=room["base_centi_c"],max_age_ms=room["max_age_ms"],
                report_evidence=room["report_evidence"],schedule=deepcopy(room["schedule"]))])

    def validate(self):
        require(isinstance(self.graph,GraphSourceProfile) and self.graph.draft_source is not None
                and isinstance(self.controller,ControllerPolicySourceProfile),"graph_control_source_invalid")
        self.graph.validate();self.controller.validate()
        require(self.graph.entry_unique_id==self.controller.entry_unique_id
                and self.graph.controller_id==self.controller.controller_id,"graph_control_source_binding")
        record=self.record();context=self.context(record)
        envelope=GraphShadowJournal._envelope(record,context,1)
        validate_graph_shadow(canonical(envelope),canonical(record["mapping"]),context)
        require(digest(self.projection())==self.controller.config_digest,"graph_control_source_config_pin")

    async def async_configuration(self,hass,entry):
        """Known reviewed DATA may only seed STAGED readback, never admission."""
        from .graph_draft_compile import async_compile_saved_graph
        self.validate()
        require(entry.unique_id==self.controller.entry_unique_id and
                entry.options.get("adapter_id",entry.data.get("adapter_id"))==self.controller.adapter_id,
                "graph_control_source_binding")
        record=self.record()
        journal=native_graph_journal(hass,entry,self.graph.qualification_digest)
        state=await journal.async_initialize()
        require(state["staged"] is None and state["accepted"]==record,"graph_control_graph_readback_required")
        raw,mapping=await async_compile_saved_graph(hass,entry,self.context(record),self.graph.draft_source)
        envelope=raw_document(raw)
        require(envelope["config"]==record["config"] and raw_document(mapping)==record["mapping"],
                "graph_control_draft_changed")
        require(await journal.store.async_load()==state and journal.state==state,
                "graph_control_store_changed")
        return self.projection(),deepcopy(record["mapping"])

    def supports_room(self,room):
        record=self.record();r=record["config"]["rooms"][0]
        return room.binding_mode=="graph_only_draft" and room.room_id==r["zone_id"]
