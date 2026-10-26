"""Native desired-graph integrity only. No services, listeners or transport."""
from __future__ import annotations

from .product import configuration_parts, heating_entries, is_product, INSTALLATION

from copy import deepcopy

from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .v1_heating_draft import HeatingConfigError, parse_heating_draft
from .v1_model import EntityReference, RoomBinding


def actual_runtime_active(hass, entry) -> bool:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("v1_runtime")
    return runtime is not None and runtime.enabled is not False


def resolved_reference(hass, raw: dict, domains: tuple[str, ...], *, temperature=False) -> dict:
    """Resolve registry identity across rename; never substitute by display name."""
    if not isinstance(raw, dict) or not isinstance(raw.get("entity_id"), str):
        raise HeatingConfigError("binding_missing")
    domain = raw["entity_id"].split(".")[0]
    registry = er.async_get(hass)
    platform, unique = raw.get("platform"), raw.get("unique_id")
    if platform is not None and unique is not None:
        entity_id = registry.async_get_entity_id(domain, platform, unique)
    else:
        entity_id = er.async_validate_entity_id(registry, raw["entity_id"])
    entity = registry.async_get(entity_id) if entity_id else None
    if entity is None or entity.disabled_by is not None:
        raise HeatingConfigError("binding_missing")
    if entity.platform == DOMAIN:
        raise HeatingConfigError("loop_binding")
    if entity.entity_id.split(".")[0] not in domains:
        raise HeatingConfigError("wrong_entity_domain")
    state = hass.states.get(entity.entity_id)
    if (temperature and entity.entity_id.startswith("sensor.") and state is not None
            and state.state not in ("unknown", "unavailable")
            and (state.attributes.get("device_class") != "temperature"
                 or state.attributes.get("unit_of_measurement") not in ("°C", "°F"))):
        raise HeatingConfigError("not_temperature")
    return EntityReference(entity.entity_id, entity.platform, entity.unique_id).as_dict()


def selected_reference(hass, selection: str, domains: tuple[str, ...]) -> dict:
    return resolved_reference(hass, {"entity_id": selection}, domains)


def normalize_bindings(hass, document: dict) -> dict:
    """Revalidate every selected role at final save, not just the edited field."""
    value = deepcopy(document)
    central = value["central"]
    if central["outdoor_source"] is not None:
        central["outdoor_source"] = resolved_reference(hass, central["outdoor_source"], ("sensor", "weather"), temperature=True)
    for g in value["groups"]:
        if g["pump"] is not None:
            g["pump"] = resolved_reference(hass, g["pump"], ("switch",))
        if m := g["mixing"]:
            m["supply_sensor"] = resolved_reference(hass, m["supply_sensor"], ("sensor",), temperature=True)
            domains = ("switch",) if m["kind"] == "three_point" else ("number",)
            m["outputs"] = [resolved_reference(hass, r, domains) for r in m["outputs"]]
    for a in value["actuators"]:
        domains = {"trv_room_setpoint": ("climate",), "binary_valve": ("switch",),
                   "proportional_valve": ("number", "valve")}[a["profile"]]
        a["output"] = resolved_reference(hass, a["output"], domains)
    return value


def _key(hass, raw):
    registry = er.async_get(hass)
    ref = EntityReference.from_dict(raw)
    if ref.platform is not None and ref.unique_id is not None:
        eid = registry.async_get_entity_id(ref.entity_id.split(".")[0], ref.platform, ref.unique_id)
        if not eid:
            raise HeatingConfigError("binding_missing")
        return ref.identity()
    actual = resolved_reference(hass, raw, (ref.entity_id.split(".")[0],))
    return EntityReference.from_dict(actual).identity()


def _device_id(hass, raw):
    ref = EntityReference.from_dict(raw)
    registry = er.async_get(hass)
    eid = (registry.async_get_entity_id(ref.entity_id.split(".")[0], ref.platform, ref.unique_id)
           if ref.platform is not None and ref.unique_id is not None else ref.entity_id)
    item = registry.async_get(eid) if eid else None
    return item.device_id if item else None


def _same_output_resource(hass, left, right):
    if _key(hass, left) == _key(hass, right):
        return True
    # Conservative TRV/valve-device reservation: a climate setpoint and a
    # separate position entity on that same device must not acquire two owners.
    # Independent switch/number channels of a relay/mixer controller may share
    # a device, but physical independence still needs a qualified device profile.
    domains = {left["entity_id"].split(".")[0], right["entity_id"].split(".")[0]}
    if domains & {"climate", "valve"}:
        device = _device_id(hass, left)
        return bool(device and device == _device_id(hass, right))
    return False


def _graph_outputs(document):
    for a in document["actuators"]:
        yield a["output"], ("room", a["room_id"], a["profile"])
    for g in document["groups"]:
        if g["pump"] is not None:
            yield g["pump"], ("pump", g["group_id"])
        if m := g["mixing"]:
            for i, output in enumerate(m["outputs"]):
                yield output, ("mixer", g["group_id"], i)


def validate_ownership(hass, entry, document, *, room_replacement=None):
    """One output owner across configured entries; exact same-room C is adoption.

    Existing zone actuator and graph TRV declaration may identify the same
    room/output; this is a single desired owner, never independent executions.
    Pump/mixer/position reuse, cross-room and cross-controller reuse is rejected.
    """
    claimed = {}
    outputs = list(_graph_outputs(document))
    for i, (ref, _) in enumerate(outputs):
        if any(_same_output_resource(hass, ref, other) for other, _ in outputs[:i]):
            raise HeatingConfigError("output_has_multiple_owners")
    for ref, role in outputs:
        key = _key(hass, ref)
        if key in claimed:
            raise HeatingConfigError("output_has_multiple_owners")
        claimed[key] = role
    if not claimed:
        return
    for other in hass.config_entries.async_entries(DOMAIN):
        for sub in configuration_parts(other):
            if sub.subentry_type == "zone":
                room = RoomBinding.from_dict(dict(sub.data))
                if (room_replacement is not None and other.entry_id == entry.entry_id
                        and room.room_id == room_replacement.room_id):
                    room = room_replacement
                for ref in (room.temperature, room.setpoint, room.schedule):
                    if ref and _key(hass, ref.as_dict()) in claimed:
                        raise HeatingConfigError("input_output_loop")
                for ref in room.actuators:
                    role = claimed.get(_key(hass, ref.as_dict()))
                    shared = any(_same_output_resource(hass, ref.as_dict(), output) for output, _ in outputs)
                    if shared and not (
                        other.entry_id == entry.entry_id and role == ("room", room.room_id, "trv_room_setpoint")
                    ):
                        raise HeatingConfigError("output_has_multiple_owners")
            elif sub.subentry_type == "heating" and other.entry_id != entry.entry_id:
                try:
                    other_outputs = list(_graph_outputs(dict(sub.data)["draft"]))
                except (KeyError, TypeError):
                    raise HeatingConfigError("other_graph_invalid") from None
                for ref, _ in other_outputs:
                    if any(_same_output_resource(hass, ref, output) for output, _ in outputs):
                        raise HeatingConfigError("output_has_multiple_owners")


def validated_graph(hass, entry, document, *, room_replacement=None):
    value = normalize_bindings(hass, document)
    rooms = {s.data["room_id"] for s in entry.subentries.values() if s.subentry_type == "zone"}
    parsed = parse_heating_draft(value, known_room_ids=rooms)
    validate_ownership(hass, entry, value, room_replacement=room_replacement)
    return parsed


def validate_room_ownership(hass, entry, room):
    """Prospective room binding must not steal another graph output."""
    for other in hass.config_entries.async_entries(DOMAIN):
        for sub in configuration_parts(other):
            if sub.subentry_type != "heating":
                continue
            document = dict(sub.data)["draft"]
            graph_outputs = list(_graph_outputs(document))
            outputs = {_key(hass, ref): role for ref, role in graph_outputs}
            if not outputs:
                continue
            for ref in (room.temperature, room.setpoint, room.schedule):
                if ref and _key(hass, ref.as_dict()) in outputs:
                    raise ValueError("loop_binding")
            for ref in room.actuators:
                role = outputs.get(_key(hass, ref.as_dict()))
                shared = any(_same_output_resource(hass, ref.as_dict(), output) for output, _ in graph_outputs)
                if shared and not (other.entry_id == entry.entry_id
                                 and role == ("room", room.room_id, "trv_room_setpoint")):
                    raise ValueError("duplicate_actuator")


@callback
def reconcile_removed_rooms(hass, entry) -> bool:
    """Native room delete prunes ONLY its desired graph actuators, with audit.

    Called by the existing update/reload lifecycle; not a background watcher.
    No room, group, source, output entity or central setting is removed.
    The next update callback performs the single reload after this atomic save.
    """
    rooms = {s.data["room_id"] for s in entry.subentries.values() if s.subentry_type == "zone"}
    changed = False
    for sub in tuple(heating_entries(entry)):
        if sub.subentry_type != "heating":
            continue
        data = deepcopy(dict(sub.data))
        document = data["draft"]
        removed = [a for a in document["actuators"] if a["room_id"] not in rooms]
        if not removed:
            continue
        document["actuators"] = [a for a in document["actuators"] if a["room_id"] in rooms]
        parsed = parse_heating_draft(document, known_room_ids=rooms)
        data.update(draft=parsed.storage_document(), draft_digest=parsed.digest,
                    status=parsed.readiness, last_room_cascade=removed,
                    incomplete_group_ids=list(parsed.incomplete_group_ids))
        if is_product(entry):
            changed |= hass.config_entries.async_update_entry(entry, data={**entry.data, INSTALLATION: data})
        else:
            changed |= hass.config_entries.async_update_subentry(entry, sub, data=data)
    return changed
