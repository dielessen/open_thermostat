"""HA-owned desired heating configuration proposal, NOT a firmware/wire API.

This module deliberately has no listeners, timers, service calls or publishers.
Profiles describe desired hardware semantics, not validated device support.
Existing shadow transport cannot accept this document; transport_document()
always refuses until a separately reviewed firmware contract is implemented.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .v1_model import EntityReference

OUTDOOR_AXIS_CENTI_C = (2000, 1500, 1000, 500, 0, -500, -1000, -1500, -2000)
MAX_GROUPS = 8
MAX_ACTUATORS = 64  # draft bound only; NOT proof of wire/board capacity
_ID = re.compile(r"[a-zA-Z0-9_-]{1,32}")
_ROOM = re.compile(r"[0-9a-f]{8}")
_ENTITY = re.compile(r"[a-z_]+\.[a-z0-9_]+")
class HeatingConfigError(ValueError):
    """Configuration is invalid; callers must leave the old draft intact."""

class HeatingContractUnavailable(HeatingConfigError):
    """No compatible active firmware contract has been implemented."""


def _object(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        raise HeatingConfigError("missing_or_unknown_fields")
    return value


def _integer(value: Any, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise HeatingConfigError("invalid_integer_or_bounds")
    return value


def _choice(value: Any, choices: tuple[str, ...]) -> str:
    if type(value) is not str or value not in choices:
        raise HeatingConfigError("unsupported_choice")
    return value


def _id(value: Any, *, room: bool = False) -> str:
    if type(value) is not str or not (_ROOM if room else _ID).fullmatch(value):
        raise HeatingConfigError("invalid_identifier")
    return value


def _name(value: Any) -> str:
    if type(value) is not str or not value.strip() or len(value) > 80:
        raise HeatingConfigError("invalid_name")
    return value


def _reference(value: Any, domains: tuple[str, ...]) -> EntityReference:
    value = _object(value, {"entity_id"}, {"platform", "unique_id"})
    entity = value["entity_id"]
    if type(entity) is not str or not _ENTITY.fullmatch(entity) or entity.split(".")[0] not in domains:
        raise HeatingConfigError("wrong_entity_domain")
    platform, unique = value.get("platform"), value.get("unique_id")
    if (platform is None) != (unique is None):
        raise HeatingConfigError("incomplete_registry_identity")
    if platform is not None and (type(platform) is not str or not platform or
                                 type(unique) is not str or not unique or
                                 len(platform) > 128 or len(unique) > 256):
        raise HeatingConfigError("invalid_registry_identity")
    if platform == "open_thermostat":
        raise HeatingConfigError("input_output_loop")
    return EntityReference(entity, platform, unique)


def _limits(value: Any, outer_min: int = 500, outer_max: int = 9000) -> tuple[int, int]:
    value = _object(value, {"minimum_centi_c", "maximum_centi_c"})
    low = _integer(value["minimum_centi_c"], outer_min, outer_max)
    high = _integer(value["maximum_centi_c"], outer_min, outer_max)
    if low >= high:
        raise HeatingConfigError("minimum_must_be_below_maximum")
    return low, high


@dataclass(frozen=True)
class HeatingDraft:
    """Immutable JSON snapshots; a desired draft is NEVER applied/readiness proof."""

    _storage_json: str
    _control_json: str
    _bindings_json: str
    required_capabilities: tuple[str, ...]

    def storage_document(self) -> dict:
        return json.loads(self._storage_json)

    def control_proposal(self) -> dict:
        """Entity-free review artifact, explicitly not an active wire document."""
        return json.loads(self._control_json)

    def bindings_document(self) -> dict:
        return json.loads(self._bindings_json)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self._storage_json.encode()).hexdigest()

    @property
    def readiness(self) -> str:
        return "draft_not_applied"

    @property
    def incomplete_group_ids(self) -> tuple[str, ...]:
        control = self.control_proposal()
        assigned = {a["group_id"] for a in control["actuators"]}
        return tuple(sorted(g["group_id"] for g in control["groups"] if g["group_id"] not in assigned))

    def transport_document(self) -> dict:
        raise HeatingContractUnavailable("heating_contract_not_implemented")


def parse_heating_draft(value: Any, *, known_room_ids: set[str]) -> HeatingDraft:
    """Validate a complete HA desired draft atomically, without touching runtime.

    Temperature bounds are structural engineering ranges, NOT a commissioning
    assertion that any selected temperature is safe for a particular installation.
    Source age config never qualifies an HA cache or a physical sample.
    """
    value = deepcopy(_object(value, {"draft_schema", "central", "groups", "actuators"}))
    if type(value["draft_schema"]) is not int or value["draft_schema"] != 1:
        raise HeatingConfigError("unsupported_draft_schema")
    if type(known_room_ids) is not set or len(known_room_ids) > 8:
        raise HeatingConfigError("invalid_room_catalog")
    for room_id in known_room_ids:
        _id(room_id, room=True)
    central = _object(value["central"], {"weather_enabled", "outdoor_source",
        "outdoor_maximum_age_ms", "stale_policy", "fixed_fallback_centi_c",
        "supply_limits", "curve_centi_c"})
    if type(central["weather_enabled"]) is not bool:
        raise HeatingConfigError("weather_enabled_must_be_boolean")
    low, high = _limits(central["supply_limits"])
    age = _integer(central["outdoor_maximum_age_ms"], 1000, 86400000)
    source = central["outdoor_source"]
    bindings: dict[str, dict] = {}
    input_refs: list[EntityReference] = []
    output_refs: list[EntityReference] = []
    # Cross-role collision checks use both current HA ID and registry identity.
    def bind(channel: str, raw: Any, domains: tuple[str, ...], *, output=False):
        ref = _reference(raw, domains)
        channel = "h" + hashlib.sha256(channel.encode()).hexdigest()[:30]
        if channel in bindings:
            raise HeatingConfigError("duplicate_channel")
        if output:
            if any(ref.identity() == r.identity() or ref.entity_id == r.entity_id
                   for r in output_refs):
                raise HeatingConfigError("output_has_multiple_owners")
            output_refs.append(ref)
        else:
            input_refs.append(ref)
        bindings[channel] = ref.as_dict()
        return channel
    if source is not None:
        source_channel = bind("outdoor", source, ("sensor", "weather"))
        source_kind = "weather_temperature_attribute" if source["entity_id"].startswith("weather.") else "temperature_sensor"
    else:
        source_channel, source_kind = None, None
    if central["weather_enabled"] and source_channel is None:
        raise HeatingConfigError("weather_requires_outdoor_source")
    policy = _choice(central["stale_policy"], ("block_normal_demand", "bounded_fixed_flow"))
    fallback = central["fixed_fallback_centi_c"]
    if policy == "bounded_fixed_flow":
        fallback = _integer(fallback, low, high)
    elif fallback is not None:
        raise HeatingConfigError("unused_fallback_must_be_null")
    curve = central["curve_centi_c"]
    if type(curve) is not list or len(curve) != 9:
        raise HeatingConfigError("nine_point_curve_required")
    curve = [_integer(t, low, high) for t in curve]
    if any(warm > cold for warm, cold in zip(curve, curve[1:])):
        raise HeatingConfigError("curve_must_not_fall_towards_cold_outdoors")
    normalized_central = {
        "weather_enabled": central["weather_enabled"], "outdoor_channel": source_channel,
        "outdoor_kind": source_kind, "outdoor_maximum_age_ms": age,
        "stale_policy": policy, "fixed_fallback_centi_c": fallback,
        "supply_limits": deepcopy(central["supply_limits"]),
        "outdoor_axis_centi_c": list(OUTDOOR_AXIS_CENTI_C), "curve_centi_c": curve,
    }
    groups = value["groups"]
    actuators = value["actuators"]
    if type(groups) is not list or not 0 <= len(groups) <= MAX_GROUPS:
        raise HeatingConfigError("group_count")
    if type(actuators) is not list or not 0 <= len(actuators) <= MAX_ACTUATORS:
        raise HeatingConfigError("actuator_count")
    group_ids: set[str] = set()
    normalized_groups = []
    capabilities = {"heating.central_weather.v1", "heating.emitter_groups.v1"}
    for item in groups:
        item = _object(item, {"group_id", "name", "emitter", "supply_limits", "pump",
                             "pump_start_delay_s", "postrun_s", "mixing"})
        gid = _id(item["group_id"])
        if gid in group_ids:
            raise HeatingConfigError("duplicate_group")
        group_ids.add(gid)
        _name(item["name"])
        emitter = _choice(item["emitter"], ("radiator", "floor"))
        _limits(item["supply_limits"], 500, high)
        delay = _integer(item["pump_start_delay_s"], 0, 3600)
        postrun = _integer(item["postrun_s"], 0, 7200)
        pump = bind(gid+"_pump", item["pump"], ("switch",), output=True) if item["pump"] is not None else None
        if pump is None and (delay or postrun):
            raise HeatingConfigError("pump_times_without_pump")
        mixing = item["mixing"]
        if mixing is None:
            if emitter == "floor" and item["supply_limits"]["maximum_centi_c"] < high:
                raise HeatingConfigError("floor_requires_mixing_or_shared_safe_limit")
            normalized_mix = None
        else:
            mixing = _object(mixing, {"kind", "supply_sensor", "outputs", "travel_time_s"})
            kind = _choice(mixing["kind"], ("three_point", "analog_0_10v"))
            travel = _integer(mixing["travel_time_s"], 1, 3600)
            sensor_channel = bind(gid+"_supply", mixing["supply_sensor"], ("sensor",))
            outputs = mixing["outputs"]
            if type(outputs) is not list or len(outputs) != (2 if kind == "three_point" else 1):
                raise HeatingConfigError("mixer_output_count")
            channels = [bind(gid+"_mix_"+str(i), raw,
                             ("switch",) if kind == "three_point" else ("number",), output=True)
                        for i, raw in enumerate(outputs)]
            normalized_mix = {"kind": kind, "supply_channel": sensor_channel,
                              "output_channels": channels, "travel_time_s": travel}
            capabilities.add("heating.mixer."+kind+".v1")
        capabilities.add("heating.emitter."+emitter+".v1")
        normalized_groups.append({"group_id": gid, "name": item["name"], "emitter": emitter,
            "supply_limits": deepcopy(item["supply_limits"]), "pump_channel": pump,
            "pump_start_delay_s": delay, "postrun_s": postrun, "mixing": normalized_mix})
    actuator_ids: set[str] = set()
    per_room: dict[str, int] = {}
    normalized_actuators = []
    used_groups: set[str] = set()
    for item in actuators:
        item = _object(item, {"actuator_id", "room_id", "group_id", "profile", "output", "settings"})
        aid, rid, gid = _id(item["actuator_id"]), _id(item["room_id"], room=True), _id(item["group_id"])
        if aid in actuator_ids or rid not in known_room_ids or gid not in group_ids:
            raise HeatingConfigError("duplicate_actuator_or_missing_reference")
        actuator_ids.add(aid)
        used_groups.add(gid)
        per_room[rid] = per_room.get(rid, 0) + 1
        if per_room[rid] > 8:
            raise HeatingConfigError("room_actuator_limit")
        profile = _choice(item["profile"], ("trv_room_setpoint", "binary_valve", "proportional_valve"))
        settings = item["settings"]
        if profile == "trv_room_setpoint":
            _object(settings, set())
            domains = ("climate",)
        elif profile == "binary_valve":
            settings = _object(settings, {"deenergized_position", "control", "travel_time_s",
                "minimum_on_s", "minimum_off_s", "cycle_s"})
            _choice(settings["deenergized_position"], ("normally_open", "normally_closed"))
            control = _choice(settings["control"], ("hysteresis", "tpi"))
            travel = _integer(settings["travel_time_s"], 1, 3600)
            on = _integer(settings["minimum_on_s"], 1, 7200)
            off = _integer(settings["minimum_off_s"], 1, 7200)
            cycle = settings["cycle_s"]
            if control == "tpi":
                cycle = _integer(cycle, 60, 86400)
                if on < travel or on + off > cycle:
                    raise HeatingConfigError("invalid_tpi_travel_or_minimum_times")
            elif cycle is not None:
                raise HeatingConfigError("hysteresis_has_no_cycle")
            domains = ("switch",)
        else:
            settings = _object(settings, {"minimum_percent", "maximum_percent", "travel_time_s"})
            minimum = _integer(settings["minimum_percent"], 0, 100)
            maximum = _integer(settings["maximum_percent"], 0, 100)
            _integer(settings["travel_time_s"], 1, 3600)
            if minimum >= maximum:
                raise HeatingConfigError("invalid_position_range")
            domains = ("number", "valve")
        channel = bind(aid+"_output", item["output"], domains, output=True)
        capabilities.add("heating.actuator."+profile+".v1")
        normalized_actuators.append({"actuator_id": aid, "room_id": rid, "group_id": gid,
            "profile": profile, "output_channel": channel, "settings": deepcopy(settings)})
    # Unassigned groups are explicit incomplete desired drafts, never readiness.
    if any(a.entity_id == b.entity_id or a.identity() == b.identity()
           for a in input_refs for b in output_refs):
        raise HeatingConfigError("input_output_loop")
    # Sort id collections for stable digest; curve and ordered mixer outputs are semantic order.
    value["groups"].sort(key=lambda x: x["group_id"])
    value["actuators"].sort(key=lambda x: x["actuator_id"])
    canonical = lambda doc: json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    proposal = {"proposal_schema": "ha-heating-draft/1", "central": normalized_central,
                "groups": sorted(normalized_groups, key=lambda x: x["group_id"]),
                "actuators": sorted(normalized_actuators, key=lambda x: x["actuator_id"])}
    return HeatingDraft(canonical(value), canonical(proposal), canonical(bindings),
                        tuple(sorted(capabilities)))
