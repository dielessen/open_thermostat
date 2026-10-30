"""Bounded read-only shadow intents, never a physical qualification source."""
from __future__ import annotations

PHASES = frozenset({"inhibited", "idle", "opening", "pump_wait", "heating", "postrun", "fault"})
REASONS = frozenset({
    "actuator_failure", "adapter_unavailable", "boiler_fault", "clock_reversed",
    "command_exhausted", "dhw_priority", "dhw_state_unknown", "fault_state_unknown",
    "flow_lost", "flow_or_pump_wait_timeout", "flow_unconfirmed",
    "hydraulic_profile_unqualified", "latched_fault", "limit_trip", "limits_unknown",
    "no_demand", "opening", "opening_timeout", "postrun", "pump_delay_or_minimum_off",
    "readiness_lost", "seasonal_clock_discontinuity", "shadow_heat_intent",
    "source_unavailable", "stop", "water_target_invalid",
})
FEEDBACK = frozenset({"hydraulic_feedback_unavailable", "hydraulic_feedback_owner_mismatch",
                     "hydraulic_feedback_future", "hydraulic_feedback_reordered", "hydraulic_feedback_clock_invalid", "hydraulic_feedback_received"})
INTENT_KEYS = frozenset({"feedback_status", "heat_intent", "pump_intent", "path_intent",
                         "opening_command", "water_target_centi_c"})
# The zone state carrying it comes on a change and at least every 30 s (beta.19): three missed refreshes.
MAX_AGE_SECONDS = 100


def supervisor_status(value):
    """Project a flat allowlist; unknown wire fields are never exported."""
    if (type(value) is not dict or type(value.get("phase")) is not str or value["phase"] not in PHASES
            or type(value.get("reason")) is not str or len(value["reason"]) > 64
            or type(value.get("requested_heat")) is not bool
            or value.get("physical_outputs_enabled") is not False):
        raise ValueError("invalid_shadow_supervisor")
    result = {"phase": value["phase"],
              "reason": value["reason"] if value["reason"] in REASONS else "unknown_reason",
              "requested_heat": value["requested_heat"], "physical_outputs_enabled": False,
              "control_qualified": False, "scope": "reported_shadow_intent_only"}
    if INTENT_KEYS.intersection(value):
        if (not INTENT_KEYS.issubset(value) or type(value["feedback_status"]) is not str or value["feedback_status"] not in FEEDBACK
                or type(value["heat_intent"]) is not bool or type(value["pump_intent"]) is not bool
                or type(value["path_intent"]) is not str or value["path_intent"] not in {"none", "request_qualified_path", "retain_existing_path"}
                or type(value["opening_command"]) is not int or not 0 <= value["opening_command"] <= 4294967295
                or (value["water_target_centi_c"] is not None and
                    (type(value["water_target_centi_c"]) is not int or not 500 <= value["water_target_centi_c"] <= 9000))
                or (value["heat_intent"] and value["phase"] != "heating")):
            raise ValueError("invalid_shadow_supervisor_intents")
        result.update({key: value[key] for key in INTENT_KEYS})
    return result
