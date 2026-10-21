"""SOURCE-only two-room contract preparation, not a transport/Store/admission.

Projects the existing native saved draft and registry; standalone review never
grants control. A separately explicit two-room-targets.v1 SOURCE caller may now
consume this validator with independent policy/config pins. Default selection
stays empty; no qualification is fabricated or existing graph limits raised.
The SOURCE caller must pin the exact plan digest and native lifecycle revisions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re

from .graph_shadow_validation import (
    canonical, digest, raw_document, obj, exact, integer, ident, fail, MAX_U32,
)

MAX_REVIEW_BYTES = 4096  # separate review document; NOT a larger runtime budget
MAX_REVIEW_ROOMS = 2
_HEX = re.compile(r"[0-9a-f]{64}")
_ZONE = re.compile(r"[0-9a-f]{8}")


@dataclass(frozen=True)
class TopologyReviewContext:
    controller_id: str
    boot_id: str
    adapter_session_id: str
    epoch: int
    config_revision: int
    registry_revision: int
    source_revision: int
    plan_digest: str


def validate_topology_review(raw, context):
    """Exact SOURCE review readback only. Never persisted/applied/admitted."""
    if type(raw) is not str or len(raw) > MAX_REVIEW_BYTES:
        fail("budget_exceeded")
    value = raw_document(raw)
    obj(value, "schema mode controller_id boot_id adapter_session_id epoch config_revision registry_revision source_revision plan_digest plan boiler_output_enabled actuator_output_enabled admission applied")
    exact(value["schema"], 1, "unsupported_schema")
    exact(value["mode"], "source_topology_review", "unsupported_schema")
    for key, expected in asdict(context).items():
        exact(value[key], expected, "context_conflict")
    for key in ("controller_id", "boot_id", "adapter_session_id"):
        ident(value[key])
    for key in ("epoch", "registry_revision", "source_revision"):
        integer(value[key], 1, MAX_U32)
    integer(value["config_revision"], 0, MAX_U32 - 1)
    for key in ("boiler_output_enabled", "actuator_output_enabled", "admission", "applied"):
        exact(value[key], False, "review_only")
    plan = obj(value["plan"], "draft_digest rooms")
    for d in (plan["draft_digest"], context.plan_digest):
        if type(d) is not str or not _HEX.fullmatch(d):
            fail("source_conflict")
    if digest(plan) != context.plan_digest:
        fail("source_conflict")
    rooms = plan["rooms"]
    if type(rooms) is not list or len(rooms) != MAX_REVIEW_ROOMS:
        fail("review_layout_limit")
    ids, resources, emitters = set(), set(), set()
    previous = ""
    for r in rooms:
        obj(r, "zone_id group_id actuator_id emitter actuator_profile sensor_resource output_resource base_centi_c minimum_target_centi_c maximum_target_centi_c max_age_ms minimum_supply_centi_c maximum_supply_centi_c")
        rid = r["zone_id"]
        if type(rid) is not str or not _ZONE.fullmatch(rid) or rid <= previous:
            fail("reference")
        previous = rid
        for key in ("zone_id", "group_id", "actuator_id"):
            val = ident(r[key])
            if val in ids or val in ("adapter", "config", "snapshot"):
                fail("owner_conflict")
            ids.add(val)
        pair = (r["emitter"], r["actuator_profile"])
        if pair not in (("radiator", "trv_room_setpoint"), ("floor", "binary_valve")):
            fail("unsupported_topology")
        if r["emitter"] in emitters:
            fail("unsupported_topology")
        emitters.add(r["emitter"])
        for key in ("sensor_resource", "output_resource"):
            resource = r[key]
            if type(resource) is not str or not _HEX.fullmatch(resource):
                fail("reference")
            if resource in resources:
                fail("owner_conflict")
            resources.add(resource)
        lo = integer(r["minimum_target_centi_c"], 500, 3499)
        hi = integer(r["maximum_target_centi_c"], lo + 1, 3500)
        integer(r["base_centi_c"], lo, hi)
        integer(r["max_age_ms"], 1000, 86400000)
        low = integer(r["minimum_supply_centi_c"], 500, 8999)
        integer(r["maximum_supply_centi_c"], low + 1, 9000)
    return value  # exact parsed review, NOT ValidatedGraphCandidate


def native_topology_plan(hass, entry):
    """Atomic native snapshot for SOURCE review tooling, never GUI apply.

    Entire existing desired draft digest remains pinned, including settings and
    central limits. This projection does NOT implement those hardware semantics.
    No source-report freshness/actuator support is inferred from registry state.
    """
    from .v1_heating_graph import validated_graph, resolved_reference
    from .v1_model import RoomBinding, EntityReference, ROOM_GRAPH_DRAFT, integration_mode, MODE_SHADOW
    if integration_mode(entry) != MODE_SHADOW:
        fail("unsupported_owner")
    subs = [s for s in entry.subentries.values() if s.subentry_type == "zone"]
    heating = [s for s in entry.subentries.values() if s.subentry_type == "heating"]
    if len(subs) != 2 or len(heating) != 1:
        fail("review_layout_limit")
    # Do not silently drop future/unsupported room features.
    known = {"room_id", "name", "temperature", "actuators", "setpoint", "maximum_age_ms",
             "base_centi_c", "schedule", "minimum_target_centi_c", "maximum_target_centi_c",
             "week_program", "binding_mode", "actuator_profile"}
    if any(set(s.data) - known for s in subs):
        fail("unsupported_room_feature")
    rooms = [RoomBinding.from_dict(dict(s.data)) for s in subs]
    if any(r.binding_mode != ROOM_GRAPH_DRAFT or r.actuators or r.setpoint or r.schedule
           or r.week_program is not None or r.comfort is not None for r in rooms):
        fail("unsupported_room_feature")
    draft = validated_graph(hass, entry, dict(heating[0].data)["draft"])
    proposal = draft.control_proposal()
    if len(proposal["groups"]) != 2 or len(proposal["actuators"]) != 2:
        fail("unsupported_topology")
    if (proposal["central"]["weather_enabled"] or proposal["central"]["outdoor_channel"] is not None
            or any(g["mixing"] is not None or g["pump_channel"] is not None
                   for g in proposal["groups"])):
        fail("unsupported_topology")
    rows = []
    groups = {g["group_id"]: g for g in proposal["groups"]}
    bindings = draft.bindings_document()
    for room in sorted(rooms, key=lambda r: r.room_id):
        actuators = [a for a in proposal["actuators"] if a["room_id"] == room.room_id]
        if len(actuators) != 1:
            fail("owner_conflict")
        a = actuators[0]; g = groups[a["group_id"]]
        ref = resolved_reference(hass, room.temperature.as_dict(), ("sensor",), temperature=True)
        resource = digest({"native_registry_identity": list(EntityReference.from_dict(ref).identity())})
        row = dict(zone_id=room.room_id, group_id=g["group_id"], actuator_id=a["actuator_id"],
            emitter=g["emitter"], actuator_profile=a["profile"], sensor_resource=resource,
            output_resource=digest({"native_registry_identity": list(EntityReference.from_dict(bindings[a["output_channel"]]).identity())}),
            base_centi_c=room.base_centi_c, minimum_target_centi_c=room.minimum_target_centi_c,
            maximum_target_centi_c=room.maximum_target_centi_c, max_age_ms=room.maximum_age_ms,
            minimum_supply_centi_c=g["supply_limits"]["minimum_centi_c"],
            maximum_supply_centi_c=g["supply_limits"]["maximum_centi_c"])
        rows.append(row)
    return dict(draft_digest=draft.digest, rooms=rows)


def prepare_saved_topology_review(hass, entry, context):
    """Explicit SOURCE tooling call only; no queue/publish/Store/new service."""
    plan = native_topology_plan(hass, entry)
    value = dict(schema=1, mode="source_topology_review", **asdict(context), plan=plan,
                 boiler_output_enabled=False, actuator_output_enabled=False,
                 admission=False, applied=False)
    raw = canonical(value)
    validate_topology_review(raw, context)
    return raw
