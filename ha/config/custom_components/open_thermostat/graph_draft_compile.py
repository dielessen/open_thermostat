"""Native saved draft -> existing bounded api2 DATA contract, source-owned pins.

No profile construction, scheduling loop, qualification discovery or physical IO.
Only the existing source-selected worker calls this compiler before journal stage.
"""
from __future__ import annotations

from .product import heating_entries

from dataclasses import dataclass
import json

from .graph_shadow_validation import GraphValidationError,canonical,digest,raw_document,CAPS,validate_graph_shadow,qualification_record_digest
from .v1_model import EntityReference,RoomBinding,ROOM_GRAPH_DRAFT,integration_mode,MODE_SHADOW,CONF_ENABLED


def require(condition,code):
    if not condition:raise GraphValidationError(code)


@dataclass(frozen=True)
class GraphDraftSource:
    """Immutable SOURCE-owned qualification and registry bindings, never GUI data.

    Complete qualification is supplied by reviewed source, NOT derived from a
    contact state, actuator setting, draft checkbox, name or incoming manifest.
    Native references remain private; only identity hashes go onto graph wire.
    """
    qualification_json:str
    bindings_json:str

    def documents(self):
        require(type(self.qualification_json) is str and type(self.bindings_json) is str
                and len(self.bindings_json.encode())<=4096,"qualification")
        record=raw_document(self.qualification_json)
        def pairs(items):
            result={}
            for key,value in items:
                require(key not in result,"qualification")
                result[key]=value
            return result
        try:
            bindings=json.loads(self.bindings_json,object_pairs_hook=pairs,
                parse_constant=lambda _:require(False,"qualification"))
        except (ValueError,TypeError,RecursionError) as error:
            raise GraphValidationError("qualification") from error
        require(type(bindings) is dict and len(bindings)==3,"qualification")
        for key,ref in bindings.items():
            require(type(key) is str and 1<=len(key)<=32 and type(ref) is dict
                    and set(ref)=={"entity_id","platform","unique_id"},"qualification")
            require(type(ref["entity_id"]) is str and 1<=len(ref["entity_id"])<=255
                    and type(ref["platform"]) is str and 1<=len(ref["platform"])<=128
                    and type(ref["unique_id"]) is str and 1<=len(ref["unique_id"])<=256,"qualification")
        return record,bindings

    def validate(self,anchor):
        record,_=self.documents()
        require(set(record)=={"record_digest","outputs_ready","boiler_ready","sources","devices","installation"}
                and record["outputs_ready"] is False and record["boiler_ready"] is False
                and record["record_digest"]==anchor
                and qualification_record_digest(record)==anchor,"qualification")


def _saved(entry,source=None,hass=None):
    from .graph_floor_bridge import GraphFloorTopologyDraftSource
    if isinstance(source,GraphFloorTopologyDraftSource):return source.select_native(hass,entry)
    require(integration_mode(entry)==MODE_SHADOW,"unsupported_owner")
    room_data=[dict(s.data) for s in entry.subentries.values() if s.subentry_type=="zone"]
    known={"room_id","name","temperature","actuators","setpoint","maximum_age_ms","base_centi_c",
           "schedule","minimum_target_centi_c","maximum_target_centi_c","week_program","binding_mode","actuator_profile"}
    require(all(not (set(data)-known) for data in room_data),"unsupported_room_feature")
    rooms=[RoomBinding.from_dict(data) for data in room_data]
    heating=[dict(s.data)["draft"] for s in heating_entries(entry)]
    require(len(rooms)==1 and len(heating)==1 and rooms[0].binding_mode==ROOM_GRAPH_DRAFT
            and rooms[0].comfort is None and rooms[0].setpoint is None,"unsupported_topology")
    return rooms[0],heating[0]


def _resource(ref):
    return digest({"native_registry_identity":list(EntityReference.from_dict(ref).identity())})


async def async_compile_saved_graph(hass,entry,context,source):
    """Existing active DATA caller; enable fence stays before AND after awaits."""
    require(entry.options.get(CONF_ENABLED) is True,"unsupported_owner")
    result=await async_compile_graph_data(hass,entry,context,source)
    require(entry.options.get(CONF_ENABLED) is True,"unsupported_owner")
    return result

async def async_compile_graph_data(hass,entry,context,source):
    """Compile only supported desired DATA; caller stages via existing journal.

    Pure representation check, including while disabled: it cannot activate,
    persist, create a transport or publish. Callers still independently select
    SOURCE, require exact native Store review and fresh firmware readback.
    Calendar compilation uses the SAME native HA/UTC schedule compiler as api1.
    """
    from .v1_heating_graph import validated_graph,resolved_reference
    from .v1_mqtt import async_room_schedule
    require(entry.options.get("adapter_id",entry.data.get("adapter_id"))==context.adapter_id,"unsupported_owner")
    require(isinstance(source,GraphDraftSource),"qualification")
    source.validate(context.qualification_digest)
    qualification,source_bindings=source.documents()
    room,stored=_saved(entry,source,hass)
    draft=validated_graph(hass,entry,stored)
    snapshot=(room.as_dict(),draft.storage_document())
    proposal=draft.control_proposal()
    require(set(draft.required_capabilities)|{"heating.graph_shadow.v1","schedule.utc.v1"}==CAPS
            and len(proposal["groups"])==len(proposal["actuators"])==1,"unsupported_topology")
    actuator=proposal["actuators"][0];group=proposal["groups"][0]
    require(group["emitter"]=="floor" and group["mixing"] is None and group["pump_channel"] is None
            and actuator["profile"]=="binary_valve" and actuator["room_id"]==room.room_id,
            "unsupported_topology")
    require(len(qualification.get("sources",[]))==len(qualification.get("devices",[]))==1,"qualification")
    observed=qualification["sources"][0];device=qualification["devices"][0]
    sensor="s_"+room.room_id;output=actuator["output_channel"];feedback=device.get("feedback_channel")
    require(set(source_bindings)=={sensor,output,feedback}
            and observed.get("channel_id")==sensor and device.get("output_channel")==output,"qualification")
    actual={}
    for channel,ref in source_bindings.items():
        domains=("switch",) if channel==output else ("sensor",) if channel==sensor else ("binary_sensor",)
        actual[channel]=resolved_reference(hass,ref,domains,temperature=channel==sensor)
    require(EntityReference.from_dict(resolved_reference(hass,room.temperature.as_dict(),("sensor",),temperature=True)).identity()
            ==EntityReference.from_dict(actual[sensor]).identity(),"source_binding_mismatch")
    native_outputs=draft.bindings_document()
    require(set(native_outputs)=={output}
            and EntityReference.from_dict(native_outputs[output]).identity()
            ==EntityReference.from_dict(actual[output]).identity(),"source_binding_mismatch")
    schedule=await async_room_schedule(hass,room)
    # No state/report/cache here grants physical source freshness.
    require(entry.options.get("adapter_id",entry.data.get("adapter_id"))==context.adapter_id,"unsupported_owner")
    current_room,current_stored=_saved(entry,source,hass)
    current_draft=validated_graph(hass,entry,current_stored)
    require(snapshot==(current_room.as_dict(),current_draft.storage_document()),"draft_changed")
    for channel,ref in source_bindings.items():
        domains=("switch",) if channel==output else ("sensor",) if channel==sensor else ("binary_sensor",)
        again=resolved_reference(hass,ref,domains,temperature=channel==sensor)
        require(EntityReference.from_dict(again).identity()==EntityReference.from_dict(actual[channel]).identity(),
                "source_binding_mismatch")
    channels=[
        dict(channel_id=sensor,direction="input",owner_id=room.room_id,resource_id=_resource(actual[sensor])),
        dict(channel_id=output,direction="output",owner_id=actuator["actuator_id"],resource_id=_resource(actual[output])),
        dict(channel_id=feedback,direction="input",owner_id=actuator["actuator_id"],resource_id=_resource(actual[feedback]))]
    mapping=dict(mapping_schema=2,mapping_revision=context.mapping_revision or 1,
                 channels=sorted(channels,key=lambda c:c["channel_id"]))
    if context.mapping_revision and digest(mapping)!=context.mapping_digest:
        mapping["mapping_revision"]=context.mapping_revision+1
    config=dict(schema=2,mode="shadow_graph",revision=context.current_revision+1,
        mapping_revision=mapping["mapping_revision"],mapping_digest=digest(mapping),
        required_capabilities=sorted(CAPS),central=proposal["central"],
        groups=[{key:value for key,value in group.items() if key!="name"}],
        actuators=proposal["actuators"],qualification=qualification,
        rooms=[dict(zone_id=room.room_id,sensor_id=sensor,base_centi_c=room.base_centi_c,
            minimum_target_centi_c=room.minimum_target_centi_c,maximum_target_centi_c=room.maximum_target_centi_c,
            max_age_ms=room.maximum_age_ms,report_evidence=observed["evidence"],
            report_profile_id=observed["profile_id"],schedule=schedule)])
    envelope={key:getattr(context,key) for key in ("controller_id","boot_id","epoch","adapter_id",
        "adapter_session_id","grant_id","grant_sequence")}
    envelope.update(api=2,config_revision=context.current_revision,binding_id="config",sequence=1,
        expected_revision=context.current_revision,config_digest=digest(config),config=config)
    raw,mapping_raw=canonical(envelope),canonical(mapping)
    validate_graph_shadow(raw,mapping_raw,context) # Existing sole bounded policy.
    return raw,mapping_raw
