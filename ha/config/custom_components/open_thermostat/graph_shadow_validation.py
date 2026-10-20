"""Pure REVIEW/test graph-shadow validator. Not imported by runtime or transport.

A valid candidate is NOT accepted/applied or physically qualified. Trust anchors
are caller-owned reviewed manifest hashes; an incoming checkbox cannot grant them.
The initial test layout supports ONE unmixed binary-floor topology only.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

CAPS = frozenset(("heating.graph_shadow.v1", "heating.central_weather.v1",
    "heating.emitter_groups.v1", "heating.emitter.floor.v1",
    "heating.actuator.binary_valve.v1", "schedule.utc.v1"))
MAX_U32 = 4294967295
# Isolated test layout only, NEVER advertised or inferred from HA draft limits.
MAX_ROOMS = MAX_GROUPS = MAX_ACTUATORS = 1
MAX_TRANSITIONS = MAX_TOTAL_TRANSITIONS = 8
MAX_STREAMS = 7
_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
_HEX = re.compile(r"[0-9a-f]{64}")
_ZONE = re.compile(r"[0-9a-f]{8}")

class GraphValidationError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def fail(code):
    raise GraphValidationError(code)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()

def raw_document(raw):
    if not isinstance(raw,str) or not raw or not raw.isascii() or "\\" in raw:
        fail("json_format")
    if len(raw)>8192:
        fail("budget_exceeded")
    depth=nodes=0
    quoted=False
    length=0
    i=0
    while i<len(raw):
        c=raw[i]
        if quoted:
            if c=='"':
                quoted=False;nodes+=1
            else:
                length+=1
                if ord(c)<32:fail("json_format")
                if length>64:fail("budget_exceeded")
        elif c=='"':
            quoted=True;length=0
        elif c in "{[":
            depth+=1;nodes+=1
            if depth>8:fail("budget_exceeded")
        elif c in "}]":
            depth-=1
        elif c=='-' or c.isdigit():
            end=i+1
            while end<len(raw) and raw[end] not in ",]} \t\r\n":end+=1
            token=raw[i:end]
            if any(x not in "-0123456789" for x in token):fail("json_integer")
            digits=token[1:] if token.startswith("-") else token
            if not digits or not digits.isdigit() or (digits.startswith("0") and len(digits)>1):
                fail("json_format")
            if len(digits)>10 or int(digits)>MAX_U32:fail("json_integer")
            nodes+=1;i=end-1
        elif c in "tfn":
            # Count the literal once; JSON parser verifies the actual spelling.
            end=i
            while end<len(raw) and raw[end] not in ",]} \t\r\n":end+=1
            nodes+=1;i=end-1
        if nodes>512:fail("budget_exceeded")
        i+=1
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:fail("json_duplicate")
            result[k]=v
        return result
    def invalid(_):fail("json_integer")
    try:
        value=json.loads(raw,object_pairs_hook=pairs,parse_float=invalid,parse_constant=invalid)
    except (ValueError,RecursionError) as err:
        if isinstance(err,GraphValidationError):raise
        fail("json_format")
    def ints(x):
        if type(x) is int and abs(x)>MAX_U32:fail("json_integer")
        if type(x) is dict:
            for v in x.values():ints(v)
        if type(x) is list:
            for v in x:ints(v)
    ints(value)
    if not isinstance(value,dict):fail("json_format")
    if canonical(value)!=raw:fail("json_canonical")
    return value

def obj(x,keys):
    if type(x) is not dict or set(x)!=set(keys.split()):
        fail("schema")
    return x

def integer(x,low,high):
    if type(x) is not int or not low<=x<=high:fail("bounds")
    return x

def ident(x):
    if type(x) is not str or not _ID.fullmatch(x):fail("reference")
    return x

def exact(x,value,code="schema"):
    if type(x) is not type(value) or canonical(x)!=canonical(value):fail(code)

def bound_pair(x):
    obj(x,"minimum_centi_c maximum_centi_c")
    low=integer(x["minimum_centi_c"],500,9000)
    high=integer(x["maximum_centi_c"],low+1,9000)
    return low,high

@dataclass(frozen=True)
class GraphValidationContext:
    controller_id: str
    boot_id: str
    epoch: int
    adapter_id: str
    adapter_session_id: str
    grant_id: str
    grant_sequence: int
    current_revision: int
    mapping_revision: int
    mapping_digest: str
    qualification_digest: str

@dataclass(frozen=True)
class ValidatedGraphCandidate:
    revision: int
    mapping_revision: int
    config_digest: str
    total_transitions: int
    stream_count: int
    boiler_output_enabled: bool = False
    actuator_output_enabled: bool = False

def validate_graph_shadow(raw, mapping_raw, context):
    """No IO, Store, session admission or device action. Caller keeps ownership."""
    if (type(context.mapping_revision) is not int or not 0<=context.mapping_revision<=MAX_U32
        or (context.mapping_revision==0 and context.mapping_digest!="")
        or (context.mapping_revision>0 and (type(context.mapping_digest) is not str or not _HEX.fullmatch(context.mapping_digest)))):
        fail("mapping_conflict")
    envelope=raw_document(raw)
    mapping=raw_document(mapping_raw)
    obj(envelope,"api controller_id boot_id epoch adapter_id adapter_session_id grant_id grant_sequence config_revision binding_id sequence expected_revision config_digest config")
    exact(envelope["api"],2,"unsupported_schema")
    for k in ("controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id","grant_sequence"):
        exact(envelope[k],getattr(context,k),"identity")
    for k in ("controller_id","boot_id","adapter_id","adapter_session_id","grant_id"):
        ident(envelope[k])
    integer(envelope["epoch"],1,MAX_U32);integer(envelope["grant_sequence"],1,MAX_U32)
    integer(envelope["sequence"],1,MAX_U32);exact(envelope["binding_id"],"config","identity")
    c=obj(envelope["config"],"schema mode revision mapping_revision mapping_digest required_capabilities central groups actuators rooms qualification")
    exact(c["schema"],2,"unsupported_schema");exact(c["mode"],"shadow_graph","unsupported_schema")
    if context.current_revision>=MAX_U32:fail("revision_exhausted")
    if (envelope["expected_revision"]!=context.current_revision or
        envelope["config_revision"]!=context.current_revision or
        type(envelope["expected_revision"]) is not int or type(envelope["config_revision"]) is not int):
        fail("revision_conflict")
    exact(c["revision"],context.current_revision+1,"revision_conflict")
    if len(canonical(c))>4096:fail("budget_exceeded")
    if envelope["config_digest"]!=digest(c):fail("config_digest")
    caps=c["required_capabilities"]
    if type(caps) is not list or any(type(x) is not str for x in caps):fail("unsupported_capability")
    if len(set(caps))!=len(caps) or set(caps)!=CAPS or caps!=sorted(caps):fail("unsupported_capability")
    obj(mapping,"mapping_schema mapping_revision channels")
    exact(mapping["mapping_schema"],2,"mapping_conflict")
    revision=integer(mapping["mapping_revision"],1,MAX_U32)
    if c["mapping_revision"]!=revision or type(c["mapping_revision"]) is not int or c["mapping_digest"]!=digest(mapping):
        fail("mapping_conflict")
    if c["mapping_digest"]==context.mapping_digest:
        if revision!=context.mapping_revision:fail("mapping_conflict")
    elif context.mapping_revision==MAX_U32 or revision!=context.mapping_revision+1:
        fail("mapping_conflict")
    channels=mapping["channels"]
    if type(channels) is not list or len(channels)!=3:fail("reference")
    roles={}
    resources=set()
    for ch in channels:
        obj(ch,"channel_id direction owner_id resource_id")
        key=ident(ch["channel_id"]);ident(ch["owner_id"])
        if key in ("adapter","config","snapshot") or key in roles or type(ch["resource_id"]) is not str or not _HEX.fullmatch(ch["resource_id"]):fail("reference")
        if ch["resource_id"] in resources:fail("output_owner_conflict")
        if ch["direction"] not in ("input","output"):fail("reference")
        resources.add(ch["resource_id"]);roles[key]=(ch["direction"],ch["owner_id"])
    def role(channel,direction,owner):
        ident(channel)  # Reject wrong types/invalid IDs before dictionary lookup.
        if roles.get(channel)!=(direction,owner):fail("reference")
    rooms=c["rooms"];groups=c["groups"];actuators=c["actuators"]
    if any(type(x) is not list or len(x)!=1 for x in (rooms,groups,actuators)):fail("test_layout_limit")
    r=obj(rooms[0],"zone_id sensor_id base_centi_c minimum_target_centi_c maximum_target_centi_c max_age_ms report_profile_id report_evidence schedule")
    rid=r["zone_id"]
    if type(rid) is not str or not _ZONE.fullmatch(rid):fail("reference")
    role(r["sensor_id"],"input",rid)
    minimum=integer(r["minimum_target_centi_c"],500,3499)
    maximum=integer(r["maximum_target_centi_c"],minimum+1,3500)
    integer(r["base_centi_c"],minimum,maximum);integer(r["max_age_ms"],1000,86400000)
    g=obj(groups[0],"group_id emitter supply_limits pump_channel pump_start_delay_s postrun_s mixing")
    gid=ident(g["group_id"]);exact(g["emitter"],"floor","unsupported_capability")
    gl,gh=bound_pair(g["supply_limits"])
    for key in ("mixing","pump_channel"):exact(g[key],None,"unsupported_capability")
    exact(g["pump_start_delay_s"],0,"unsupported_capability");exact(g["postrun_s"],0,"unsupported_capability")
    central=obj(c["central"],"weather_enabled outdoor_channel outdoor_kind outdoor_maximum_age_ms stale_policy fixed_fallback_centi_c supply_limits outdoor_axis_centi_c curve_centi_c")
    exact(central["weather_enabled"],False,"unsupported_capability")
    exact(central["outdoor_channel"],None,"unsupported_capability");exact(central["outdoor_kind"],None,"unsupported_capability")
    integer(central["outdoor_maximum_age_ms"],1000,86400000)
    exact(central["stale_policy"],"block_normal_demand","unsupported_capability")
    exact(central["fixed_fallback_centi_c"],None,"unsupported_capability")
    cl,ch=bound_pair(central["supply_limits"])
    if gh!=ch or gl<cl:fail("bounds") # unmixed floor: shared maximum only
    exact(central["outdoor_axis_centi_c"],[2000,1500,1000,500,0,-500,-1000,-1500,-2000])
    curve=central["curve_centi_c"]
    if type(curve) is not list or len(curve)!=9:fail("schema")
    for value in curve:integer(value,cl,ch)
    if curve!=sorted(curve):fail("bounds")
    a=obj(actuators[0],"actuator_id room_id group_id profile output_channel settings")
    aid=ident(a["actuator_id"])
    if len({rid,gid,aid,*roles})!=6 or {rid,gid,aid}&{"adapter","config","snapshot"}:fail("reference")
    exact(a["room_id"],rid,"reference");exact(a["group_id"],gid,"reference")
    exact(a["profile"],"binary_valve","unsupported_capability")
    role(a["output_channel"],"output",aid)
    settings=obj(a["settings"],"deenergized_position control travel_time_s minimum_on_s minimum_off_s cycle_s")
    if settings["deenergized_position"] not in ("normally_closed","normally_open"):fail("qualification")
    exact(settings["control"],"tpi","unsupported_capability")
    travel=integer(settings["travel_time_s"],1,3600)
    on=integer(settings["minimum_on_s"],travel,7200);off=integer(settings["minimum_off_s"],1,7200)
    integer(settings["cycle_s"],max(60,on+off),86400)
    q=obj(c["qualification"],"record_digest outputs_ready boiler_ready sources devices installation")
    exact(q["outputs_ready"],False,"qualification");exact(q["boiler_ready"],False,"qualification")
    manifest={k:q[k] for k in ("sources","devices","installation")}
    if (type(context.qualification_digest) is not str or not _HEX.fullmatch(context.qualification_digest)
        or q["record_digest"]!=digest(manifest) or q["record_digest"]!=context.qualification_digest):
        fail("qualification")
    if type(q["sources"]) is not list or len(q["sources"])!=1:fail("qualification")
    source=obj(q["sources"][0],"channel_id profile_id evidence maximum_report_interval_ms maximum_transport_delay_ms restore_policy evidence_record_id producer_path_record_id")
    exact(source["channel_id"],r["sensor_id"],"qualification")
    ident(source["profile_id"]);ident(source["evidence_record_id"]);ident(source["producer_path_record_id"])
    exact(r["report_profile_id"],source["profile_id"],"qualification")
    if source["evidence"] not in ("physical_report","validated_integration_report"):fail("qualification")
    exact(r["report_evidence"],source["evidence"],"qualification")
    cadence=integer(source["maximum_report_interval_ms"],1,86400000)
    delay=integer(source["maximum_transport_delay_ms"],1,15000)
    if cadence+delay>=r["max_age_ms"]:fail("qualification")
    exact(source["restore_policy"],"reject","qualification")
    if type(q["devices"]) is not list or len(q["devices"])!=1:fail("qualification")
    device=obj(q["devices"][0],"output_channel profile_id deenergized_position energized_position command_polarity feedback_channel feedback_profile_id feedback_maximum_age_ms readiness opening_deadline_ms failure_policy_id reference_policy evidence_record_id power_loss_position safe_position failure_action stale_feedback_policy safe_position_record_id")
    exact(device["output_channel"],a["output_channel"],"qualification")
    for k in ("profile_id","feedback_profile_id","failure_policy_id","evidence_record_id","safe_position_record_id"):ident(device[k])
    exact(device["deenergized_position"],settings["deenergized_position"],"qualification")
    exact(device["energized_position"],"open" if settings["deenergized_position"]=="normally_closed" else "closed","qualification")
    power_loss="closed" if settings["deenergized_position"]=="normally_closed" else "open"
    exact(device["power_loss_position"],power_loss,"qualification")
    exact(device["safe_position"],power_loss,"qualification")
    exact(device["failure_action"],"withdraw_heat_deenergize","qualification")
    exact(device["stale_feedback_policy"],"withdraw_heat","qualification")
    exact(device["command_polarity"],"on_energizes","qualification")
    role(device["feedback_channel"],"input",aid)
    integer(device["feedback_maximum_age_ms"],1,15000)
    exact(device["readiness"],"end_switch_open","qualification")
    integer(device["opening_deadline_ms"],travel*1000,3600000)
    exact(device["reference_policy"],"binary_endstops","qualification")
    inst=obj(q["installation"],"group_id minimum_flow_record_id postrun_record_id high_limit_record_id maximum_supply_centi_c high_limit_kind floor_limit_kind maximum_floor_centi_c floor_limit_record_id")
    exact(inst["group_id"],gid,"qualification")
    for k in ("minimum_flow_record_id","postrun_record_id","high_limit_record_id","floor_limit_record_id"):ident(inst[k])
    exact(inst["maximum_supply_centi_c"],gh,"qualification")
    exact(inst["high_limit_kind"],"independent_water_cutout","qualification")
    exact(inst["floor_limit_kind"],"independent_floor_cutout","qualification")
    integer(inst["maximum_floor_centi_c"],500,3500)
    total=0
    if (schedule:=r["schedule"]) is not None:
        obj(schedule,"timezone policy valid_from_utc valid_until_utc base_centi_c transitions")
        if schedule["timezone"] not in ("UTC","Europe/Amsterdam"):fail("schedule")
        exact(schedule["policy"],"wall-clock-membership/v1","schedule")
        start=integer(schedule["valid_from_utc"],946684800,4102444799)
        end=integer(schedule["valid_until_utc"],start+1,min(start+16*86400,4102444800))
        exact(schedule["base_centi_c"],r["base_centi_c"],"schedule")
        transitions=schedule["transitions"]
        if type(transitions) is not list or not 1<=len(transitions)<=MAX_TRANSITIONS:fail("schedule_budget")
        last=start-1
        for index,item in enumerate(transitions):
            if type(item) is not list or len(item)!=2:fail("schedule")
            at=integer(item[0],start,end-1);integer(item[1],minimum,maximum)
            if at<=last or (index==0 and at!=start):fail("schedule")
            last=at
        total=len(transitions)
    if total>MAX_TOTAL_TRANSITIONS:fail("schedule_budget")
    streams=3+2*len(rooms)+2*len(actuators)
    if streams>MAX_STREAMS:fail("stream_budget")
    return ValidatedGraphCandidate(c["revision"],revision,digest(c),total,streams)
