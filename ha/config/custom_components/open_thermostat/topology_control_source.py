"""Explicit two-room-targets.v1 SOURCE prerequisite, not graph DATA apply."""
from dataclasses import dataclass
from copy import deepcopy
from .comfort_sources import ControllerPolicySourceProfile
from .graph_topology_review import TopologyReviewContext,validate_topology_review,native_topology_plan
from .graph_shadow_validation import canonical,digest,GraphValidationError
from .v1_model import ROOM_GRAPH_DRAFT

def require(ok,code):
    if not ok:raise GraphValidationError(code)

@dataclass(frozen=True,slots=True)
class TopologyControllerEntrySource:
    controller: ControllerPolicySourceProfile
    context: TopologyReviewContext
    review_json: str
    evidence: tuple[str,str]
    profile_version: str = "two-room-targets.v1"
    schema: int = 1

    room_count=2

    def review(self):
        require(type(self.context) is TopologyReviewContext,"topology_control_context")
        for key in ("epoch","registry_revision","source_revision","config_revision"):
            value=getattr(self.context,key)
            require(type(value) is int and (0 if key=="config_revision" else 1)<=value
                    <=(4294967294 if key=="config_revision" else 4294967295),
                    "topology_control_context")
        return validate_topology_review(self.review_json,self.context)

    def record(self):
        review=self.review();rooms=review["plan"]["rooms"]
        channels=[]
        for r in rooms:
            for cid,direction,owner,resource in (
                ("s_"+r["zone_id"],"input",r["zone_id"],r["sensor_resource"]),
                (r["actuator_id"],"output",r["actuator_id"],r["output_resource"])):
                channels.append(dict(channel_id=cid,direction=direction,owner_id=owner,resource_id=resource))
        require(len({c["channel_id"] for c in channels})==4,"topology_control_channel_conflict")
        mapping=dict(channels=sorted(channels,key=lambda c:c["channel_id"]),
                     mapping_schema=2,mapping_revision=self.context.registry_revision)
        cfg=dict(schema=1,mode="shadow",revision=self.context.config_revision+1,mapping_digest=digest(mapping),
            zones=[dict(zone_id=r["zone_id"],sensor_id="s_"+r["zone_id"],actuator_id=r["actuator_id"],
                base_centi_c=r["base_centi_c"],max_age_ms=r["max_age_ms"],report_evidence=self.evidence[i],
                schedule=None) for i,r in enumerate(rooms)])
        return dict(config=cfg,config_digest=digest(cfg),mapping=mapping)

    def projection(self):return deepcopy(self.record()["config"])

    def validate(self):
        require(type(self.schema) is int and self.schema==1 and self.profile_version=="two-room-targets.v1",
                "topology_control_profile_version")
        require(isinstance(self.controller,ControllerPolicySourceProfile),"topology_control_source_invalid")
        self.controller.validate()
        review=self.review()
        require(canonical(review)==self.review_json and self.context.controller_id==self.controller.controller_id,
                "topology_control_source_binding")
        require(type(self.evidence) is tuple and len(self.evidence)==2
            and all(x in ("physical_report","validated_integration_report") for x in self.evidence),
            "topology_control_report_policy")
        require(all(r["max_age_ms"]<=120000 for r in review["plan"]["rooms"]),
                "topology_control_sensor_budget")
        require(digest(self.projection())==self.controller.config_digest,"topology_control_config_pin")
        require(len(canonical(self.record()).encode())<=4096,"topology_control_record_budget")

    def supports_room(self,room):
        return room.binding_mode==ROOM_GRAPH_DRAFT and room.room_id in {
            r["zone_id"] for r in self.review()["plan"]["rooms"]}

    async def async_configuration(self,hass,entry):
        self.validate()
        require(entry.unique_id==self.controller.entry_unique_id
                and entry.options.get("adapter_id",entry.data.get("adapter_id"))==self.controller.adapter_id,
                "topology_control_source_binding")
        require(native_topology_plan(hass,entry)==self.review()["plan"],"topology_control_native_drift")
        record=self.record()
        return deepcopy(record["config"]),deepcopy(record["mapping"])

    def registry_references(self,hass,entry):
        from .v1_model import RoomBinding
        from .v1_heating_graph import validated_graph
        refs=[RoomBinding.from_dict(dict(s.data)).temperature.as_dict()
              for s in entry.subentries.values() if s.subentry_type=="zone"]
        central=next(s for s in entry.subentries.values() if s.subentry_type=="heating")
        refs.extend(validated_graph(hass,entry,dict(central.data)["draft"]).bindings_document().values())
        return tuple(refs)
