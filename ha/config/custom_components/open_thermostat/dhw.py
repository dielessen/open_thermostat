"""Bounded DHW *presentation*, never capability admission or a boiler writer."""
import math
from copy import deepcopy

from .const import DOMAIN

PACKET_TTL = 30.0
PROFILES = {"classic_observed", "plus_observed", "unknown", "conflicting_families"}
FIELDS = ("selected_temperature", "current_temperature", "enabled", "activity", "flow", "comfort", "schedule", "runtime")


def _reading(value, low, high, divisor=1):
    return value / divisor if type(value) in (int, float) and low <= value <= high and math.isfinite(value) else None


class DhwPresentation:
    """Receipt-bounded status cache on the EXISTING tracker; not a collector."""
    def __init__(self, clock):
        self._clock = clock
        self._profile = "unknown"
        self._data = {}
        self.deadline = 0.0
        self._reason = "no_observation"
        self._last = None

    def invalidate(self, reason="offline"):
        self._data = {}
        self.deadline = 0.0
        self._reason = reason

    def receive(self, payload, online, retained=False):
        now = self._clock()
        reversed_time = self._last is not None and now < self._last
        self._last = now
        if type(payload) is not dict:
            self._profile = "unknown"
            self.invalidate("malformed")
            return
        profile = payload.get("protocolProfile")
        self._profile = profile if type(profile) is str and profile in PROFILES else "unknown"
        self.invalidate("unknown_profile")
        if reversed_time:
            self._reason = "clock_reversed"
            return
        if not online or retained:
            self._reason = "retained" if retained else "offline"
            return
        if self._profile not in {"classic_observed", "plus_observed"}:
            self._reason = "conflicting_profiles" if self._profile == "conflicting_families" else "unknown_profile"
            return
        # Fixed allowlist: never keep whole payload, identity, settings or secrets.
        self._data = {
            "selected_temperature": _reading(payload.get("selectedWarmWaterTemperature"), 0, 100),
            "current_temperature": _reading(payload.get("currentWarmWaterTemperature"), 0, 1300, 10),
            "enabled": payload.get("warmWaterEnabled") if type(payload.get("warmWaterEnabled")) is bool else None,
            "activity": payload.get("warmWaterActive") if type(payload.get("warmWaterActive")) is bool else None,
            "flow": _reading(payload.get("warmWaterFlow"), 0, 254, 10),
        }
        self.deadline = now + PACKET_TTL
        self._reason = "last_reported_not_source_qualified"

    def snapshot(self, online, qualified_activity=None):
        now = self._clock()
        fresh = online and self.deadline > now and self._last is not None and now >= self._last
        status = self._profile if fresh else "offline" if not online else self._reason if not self.deadline else "stale"
        if self._last is not None and now < self._last:
            status = "clock_reversed"
        known = self._profile in {"classic_observed", "plus_observed"}
        fields = {}
        for name in FIELDS:
            profile_field = known and name in {"selected_temperature", "current_temperature", "enabled", "activity", "flow"}
            supported = profile_field and self._data.get(name) is not None
            quality = "unsupported_contract" if not profile_field else "reported_unqualified_source_age"
            value = self._data.get(name) if fresh and supported else None
            if name == "activity" and self._profile == "classic_observed":
                quality = "inferred_unqualified"
            if name == "activity" and self._profile == "plus_observed" and fresh:
                # The existing tracker alone validates observation ages/boot/sequence.
                value = qualified_activity if type(qualified_activity) is bool else None
                supported = supported or value is not None
                quality = "reported_source_bounded_not_physical" if value is not None else "unknown_source_quality"
            if name == "flow" and self._profile == "classic_observed":
                quality, value = "unreliable_classic", None
            if fresh and profile_field and value is None and quality == "reported_unqualified_source_age":
                quality = "invalid_or_missing"
            fields[name] = {"supported_read": supported, "value": value, "quality": quality,
                            "unit": "°C" if name.endswith("temperature") else "L/min" if name == "flow" else None}
        return {"profile": self._profile, "status": status, "transport": "legacy_status",
                "packet_fresh": fresh, "source_age_qualified": False, "physical_validation": False,
                "write_supported": False, "automatic_reset": False, "boiler_priority_unchanged": True,
                "fields": fields}


def entry_snapshot(hass, entry):
    """Fixed non-secret shape from existing lifecycle owners; no IO or writes."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    tracker = state.get("heating_tracker")
    if tracker is not None:
        return deepcopy(tracker.dhw_snapshot())
    result = DhwPresentation(lambda: 0).snapshot(False)
    result["status"] = "unknown"
    result["transport"] = "not_running"
    runtime = state.get("v1_runtime")
    client = getattr(state.get("v1_connection"), "client", None)
    if runtime is not None:
        result["transport"] = "shadow_metrics_only"
        result["status"] = "metrics_only" if getattr(client, "metrics_payload", None) is not None else "unknown"
        # metrics protocolScope=plus is NOT a DHW capability/field grant.
    return result


def summary(snapshot):
    """Fixed labels only, safe for translated options and Markdown."""
    return (f"Profile: {snapshot['profile']}. Status: {snapshot['status']}. "
            "Read-only last-reported values; source ages are not verified. "
            "Classic flow is unreliable; comfort, schedule and runtime are unsupported. "
            "No DHW controls or resets. Boiler priority remains unchanged.")
