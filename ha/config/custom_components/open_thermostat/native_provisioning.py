"""Logical SOURCE export for independent local device-settings review.

NOT source selection, a new worker, physical/report qualification or HA auto-send.
Existing independently reviewed NativePlanSource validates every exported field.
"""
from .graph_shadow_validation import canonical
from .native_plan import NativePlanSource

def local_device_descriptor(source):
    if type(source) is not NativePlanSource:raise ValueError("native_source_type")
    profile,_=source.documents()
    zones=[]
    for z in profile["zones"]:
        c=z["control"]
        zones.append([z["zone_id"],z["sensor_id"],z["actuator_id"],z["group_id"],
            int(z["emitter"]=="floor"),z["sensor_resource"],z["output_resource"],
            z["minimum_target_centi_c"],z["maximum_target_centi_c"],z["maximum_sensor_age_ms"],
            z["minimum_supply_centi_c"],z["maximum_supply_centi_c"],
            int(z["report_evidence"]=="validated_integration_report"),
            [c[k] for k in ("cycle_ms","hysteresis_centi_c","ki_permille_per_c_minute",
                "kp_permille_per_c","minimum_off_ms","minimum_on_ms")]])
    result=["native.source.local.v1",profile["controller_id"],profile["adapter_id"],profile["layout_digest"],
        profile["mapping_revision"],source.policy.legacy_readback_reviewed,zones]
    # Existing total networksettings2048, not an additional/raised quota.
    if len(canonical(result).encode())>=2048:raise ValueError("native_local_settings_budget")
    return result

# Source review is stored in the EXISTING HA entry options, never a second Store
# or a lease/admission journal. The device independently needs the same local
# descriptor; the fresh existing handshake compares its actual immutable SHA.
SOURCE_OPTION="native_logical_source"
def source_from_selection(entry):
    from .native_plan import NativeInstallationPolicy
    from .graph_shadow_validation import raw_document,obj,exact,digest
    value=entry.options.get(SOURCE_OPTION)
    if value is None:return None
    if type(value) is not dict or len(canonical(value).encode())>8192:raise ValueError("native_source_selection_budget")
    obj(value,"schema entry_unique_id profile bindings")
    exact(value["schema"],1)
    exact(value["entry_unique_id"],entry.unique_id,"native_source_entry_owner")
    profile=value["profile"]
    if type(profile) is not dict:raise ValueError("native_source_selection_profile")
    legacy=profile.get("legacy_readback")=="schema1_quarantine_only"
    policy=NativeInstallationPolicy(value["entry_unique_id"],profile.get("controller_id"),profile.get("adapter_id"),
        digest(profile),legacy_readback_reviewed=legacy)
    source=NativePlanSource(policy,canonical(profile),canonical(value["bindings"]));source.validate()
    return source

def source_selection(source):
    profile,bindings=source.documents()
    value=dict(schema=1,entry_unique_id=source.policy.entry_unique_id,profile=profile,bindings=bindings)
    if len(canonical(value).encode())>8192:raise ValueError("native_source_selection_budget")
    return value

def propose_local_shadow_source(hass,entry,controller_id,*,legacy_readback=False):
    """Explicit operator review proposal, NEVER physical/report qualification."""
    from .native_plan import _native_layout,NativeInstallationPolicy
    from .v1_model import EntityReference
    from .graph_shadow_validation import digest,ident
    ident(controller_id)
    if type(legacy_readback) is not bool:raise ValueError("native_legacy_profile")
    rooms,draft,layout=_native_layout(hass,entry)
    rows=[];bindings={}
    for room in rooms:
        actuator=next(a for a in layout["actuators"] if a["room_id"]==room.room_id)
        group=next(g for g in layout["groups"] if g["group_id"]==actuator["group_id"])
        output=draft.bindings_document()[actuator["output_channel"]]
        sensor_id="s_"+room.room_id
        bindings[sensor_id]=room.temperature.as_dict();bindings[actuator["actuator_id"]]=output
        control=dict(mode="local_trv",hysteresis_centi_c=20,kp_permille_per_c=0,ki_permille_per_c_minute=0,
            cycle_ms=0,minimum_on_ms=0,minimum_off_ms=0)
        if group["emitter"]=="floor":
            control.update(mode="slow_binary_pi",kp_permille_per_c=500,ki_permille_per_c_minute=10,
                cycle_ms=actuator["settings"]["cycle_s"]*1000,minimum_on_ms=actuator["settings"]["minimum_on_s"]*1000,
                minimum_off_ms=actuator["settings"]["minimum_off_s"]*1000)
        # Existing supported controller logical defaults only. No summer/frost/
        # readiness/report-provider toggles and no unsupported mixer protection.
        rows.append(dict(zone_id=room.room_id,sensor_id=sensor_id,actuator_id=actuator["actuator_id"],
            group_id=group["group_id"],emitter=group["emitter"],actuator_profile=actuator["profile"],control=control,
            sensor_resource=digest({"native_registry_identity":list(room.temperature.identity())}),
            output_resource=digest({"native_registry_identity":list(EntityReference.from_dict(output).identity())}),
            minimum_target_centi_c=room.minimum_target_centi_c,maximum_target_centi_c=room.maximum_target_centi_c,
            maximum_sensor_age_ms=min(room.maximum_age_ms,120000),report_evidence="physical_report",
            minimum_supply_centi_c=group["supply_limits"]["minimum_centi_c"],
            maximum_supply_centi_c=group["supply_limits"]["maximum_centi_c"]))
    body=dict(schema=1,kind="native_profile.shadow.v1",controller_id=controller_id,
        adapter_id=entry.options.get("adapter_id",entry.data.get("adapter_id")),layout_digest=digest(layout),
        mapping_revision=1,zones=rows)
    if legacy_readback:body.update(schema=2,kind="native_profile.shadow.v2",legacy_readback="schema1_quarantine_only")
    source=NativePlanSource(NativeInstallationPolicy(entry.unique_id,controller_id,body["adapter_id"],digest(body),
        legacy_readback_reviewed=legacy_readback),canonical(body),canonical(bindings))
    source.validate_native(hass,entry)
    local_device_descriptor(source) # Bounds before this proposal reaches review.
    return source
