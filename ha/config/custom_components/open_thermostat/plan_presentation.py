"""Read-only labels for the EXISTING configuration flow; no policy or IO."""
from datetime import UTC,datetime
from html import escape

# Only known local plan-budget failures receive actionable prose. Never expose
# arbitrary exception strings, remote payloads or private profile information.
def validation_error(error):
    from .graph_shadow_validation import GraphValidationError
    if not isinstance(error,GraphValidationError):return None
    return {"native_transition_limit":"native_plan_schedule_limit",
            "native_config_budget":"native_plan_config_limit"}.get(error.code)

STATUS={
    "native_plan_horizon_readback_required":"Refreshing the unchanged local week; waiting for exact device readback",
    "native_plan_horizon_review_required":"The schedule horizon could not be safely renewed; review the saved plan",
    "native_plan_profile_review_required":"Previous profile configuration read back in quarantine; explicitly review and apply the new profile plan",
    "native_profile_evolution_capability_required":"Device does not support the reviewed profile migration; control blocked",
    "native_plan_legacy_review_required":"Old configuration read back in quarantine; explicitly review the new plan",
    "shadow_ready":"Exact current plan readback verified",
    "native_plan_unconfigured_review_required":"Not applied: review the saved rooms",
    "native_plan_staged_not_applied":"Draft staged locally; not sent to the device",
    "native_plan_awaiting_readback":"Sent; waiting for exact device readback",
    "native_plan_send_unconfirmed":"Send outcome unknown; do not assume rollback",
    "native_plan_apply_unconfirmed":"Apply outcome unknown; fresh readback required",
    "native_plan_recovery_review_required":"Recovery needs a new explicit review",
    "native_plan_remote_conflict":"Conflict: device configuration is not this reviewed draft",
    "native_plan_draft_changes_not_applied":"Saved room changes are not applied",
    "native_plan_source_or_entry_changed":"Owner, source or bindings changed; control blocked",
    "native_plan_review_required":"Source or schedule changed; review required",
    "native_plan_already_applied":"No changes: the matching plan is already applied",
    "native_plan_capability_unavailable":"Device does not support the selected plan contract",
    "firmware_storage_fault":"Device storage fault; control blocked",
    "storage_fault":"Device storage fault; control blocked",
    "conflict":"Conflict; the device has not accepted this revision",
    "mapping_conflict":"Mapping conflict; control blocked",
    "rejected":"Device rejected the request",
    "firmware_offline":"Offline; current device state is not verified",
    "disconnected":"Disconnected; current device state is not verified",
    "not_connected":"Not connected; no current device proof",
    "awaiting_firmware_handshake":"Connecting; no current configuration proof",
    "ack_timeout_effect_unknown":"Acknowledgement timeout; effect unknown",
    "graph_staged_not_applied":"DATA draft staged locally; not sent",
    "awaiting_graph_readback":"DATA sent; waiting for exact readback",
    "graph_remote_conflict":"DATA conflict; no configuration was adopted",
    "graph_readback_verified_no_admission":"DATA readback verified; no control authority",
}
RESULT={
    "acknowledged_unverified":"Acknowledged, but not verified by readback",
    "conflict":"Device reported a revision or mapping conflict",
    "rejected":"Device rejected the reviewed request",
    "storage_fault":"Device reported a storage fault",
}
def labels(status,result,verified,*,native,room_count=2):
    """Unknown/private wire strings are never interpolated into prose."""
    control=(("Verified one-room shadow control; physical outputs disabled" if room_count==1 else
        "Verified two-room shadow control; physical outputs disabled") if verified else
        "No verified native-plan control; physical outputs disabled") if native else (
        "DATA verification never grants control; a separate SOURCE review is required")
    result_label=RESULT.get(result)
    if result_label is None:
        result_label=("No current-session acknowledgement retained; exact readback is authoritative" if native else
            "No current-session acknowledgement recorded")
    status_label=STATUS.get(status,"No current verified status; review the configuration and connection")
    if not verified and status in ("shadow_ready","graph_readback_verified_no_admission"):
        status_label="Previous verification is no longer current; connection or source changed"
    return dict(status_label=status_label,
        result_label=result_label,control_status=control)

def scope(native,room_count=2):
    return ("One complete shadow room plan, including mapping" if room_count==1 else
        "Two complete shadow room plans, including mapping") if native else "Heating graph DATA only; not control admission"

def review_summary(config,rooms,*,native):
    if not native:return "DATA-only configuration. Check room and heating-group mappings before applying."
    lines=[]
    for zone in config["zones"]:
        room=rooms[zone["zone_id"]]
        lines.append(escape(room.name)+" ("+zone["zone_id"]+"): base "+format(zone["base_centi_c"]/100,".2f")+" °C")
        schedule=zone["schedule"]
        if schedule is not None and schedule.get("policy")=="wall-clock-packed/v1":
            from .compact_schedule import expand_schedule
            schedule=expand_schedule(schedule)
        if schedule is None:lines.append("No weekly schedule; the base target applies.")
        else:
            lines.append("UTC schedule; expires "+datetime.fromtimestamp(schedule["valid_until_utc"],UTC).isoformat())
            for at,target in schedule["transitions"]:
                lines.append(datetime.fromtimestamp(at,UTC).isoformat()+" → "+format(target/100,".2f")+" °C")
    if config.get("plan_contract")=="control.plan.week.v1":
        lines.append("Complete UTC schedules: at most 128 transitions per room within the device configuration budget. Unchanged local weeks renew through fresh device readback; changed programs, helper exports, pending plans and expired horizons require explicit review.")
    else:lines.append("This version permits at most eight UTC transitions across both rooms; larger programs are rejected, not truncated.")
    return "\n\n".join(lines)
