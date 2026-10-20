"""Finite, opt-in Z2M 2.14.2 source bench. No writes or background tasks."""
from __future__ import annotations
import copy
import json
import math
from datetime import datetime

KEY = "^temperature$"
REMOVED = {"friendlyName", "friendly_name", "ID", "type", "devices"}

def clean(value):
    return {k: v for k, v in value.items() if k not in REMOVED}

def effective(config, ieee):
    return {**config.get("device_options", {}), **config["devices"][ieee]}

def zero_buffer(options):
    return all(type(options.get(k, 0)) in (int, float) and options.get(k, 0) == 0
               for k in ("debounce", "throttle"))

def proposal(config, ieee, transaction):
    """Preserve explicit/inherited options; return one request and exact rollback."""
    old = config["devices"][ieee]
    current = effective(config, ieee)
    if not zero_buffer(current):
        raise ValueError("buffered producer: this bench route is not eligible")
    filters = current.get("filtered_cache", [])
    if not isinstance(filters, list) or any(not isinstance(x, str) for x in filters):
        raise ValueError("invalid existing filters")
    if KEY in filters:
        raise ValueError("already filtered: requires separate known cache-drain evidence")
    return ({"id": ieee, "options": {"filtered_cache": [*filters, KEY]}, "transaction": transaction},
            {"id": ieee, "options": {"filtered_cache": copy.deepcopy(old.get("filtered_cache"))},
             "transaction": transaction + "_rollback"})

class BenchSource:
    """All times are injected. Events must be delivered serially in broker order.

    baseline is a scoped native bridge/info config, NOT a user trust flag.
    Current ACK.from + post-request info must agree with it. Exclusive control
    remains a supervised procedure prerequisite; MQTT cannot atomically lock Z2M.
    """
    def __init__(self, baseline, ieee, state_topic, transaction, *, discovery, duration_s=300, max_age_ms=120000):
        if not (1 <= duration_s <= 300 and 1 <= max_age_ms <= 120000):
            raise ValueError("invalid finite bench bounds")
        if not isinstance(transaction, str) or not transaction or len(transaction) > 64:
            raise ValueError("transaction required")
        if not isinstance(state_topic, str) or state_topic.count("/") < 1 or any(x in state_topic for x in ("#", "+")):
            raise ValueError("exact selected source topic required")
        if (discovery.get("device", {}).get("model_id") != "WSDCGQ11LM"
                or discovery.get("origin", {}).get("sw_version") != "2.14.2"
                or discovery.get("state_topic") != state_topic
                or discovery.get("unit_of_measurement") != "°C"
                or discovery.get("value_template") != '{{ value_json["temperature"] }}'):
            raise ValueError("pinned native Discovery binding required")
        options = effective(baseline, ieee)
        if (options.get("retain", False) is not False or type(options.get("qos", 0)) is not int
                or options.get("qos", 0) != 0):
            raise ValueError("bench requires producer QoS0/nonretained state")
        if state_topic.rsplit("/", 1)[1] != baseline["devices"][ieee]["friendly_name"]:
            raise ValueError("friendly name/source topic mismatch")
        self.discovery = copy.deepcopy(discovery)
        self.discovery_seen = False
        self.baseline, self.ieee = copy.deepcopy(baseline), ieee
        self.request, self.rollback = proposal(self.baseline, ieee, transaction)
        self.expected = copy.deepcopy(self.baseline)
        self.expected["devices"][ieee]["filtered_cache"] = self.request["options"]["filtered_cache"]
        self.state_topic = state_topic
        self.duration_s, self.max_age_ms = duration_s, max_age_ms
        self.phase, self.reason = "waiting_request", "disabled_until_observed_cutover"
        self.info_seen = False
        self.baseline_seen = False
        self.deadline = None
        self.cutoff_utc = None
        self.last_seen = None
        self.last_mono = None
        self.last_utc = None

    def stop(self, reason):
        self.phase, self.reason = "closed", reason

    def check_time(self, mono, utc):
        if (type(mono) not in (int, float) or type(utc) not in (int, float)
                or not math.isfinite(mono) or not math.isfinite(utc)
                or (self.last_mono is not None and mono < self.last_mono)
                or (self.last_utc is not None and abs((utc-self.last_utc)-(mono-self.last_mono)) > 1)):
            self.stop("clock_invalid")
            return False
        self.last_mono, self.last_utc = mono, utc
        if self.deadline is not None and mono >= self.deadline:
            self.stop("bench_expired")
        return self.phase != "closed"

    def event(self, kind, payload, *, retained=False, mono, utc):
        if not self.check_time(mono, utc):
            return None
        if kind == "tick":
            return None
        if kind in ("disconnect", "lifecycle"):
            self.stop("lifecycle_changed")
            return None
        if kind == "discovery":
            def pin(document):
                return {"source": [document.get(k) for k in ("state_topic", "unique_id", "unit_of_measurement", "value_template")],
                        "device": [document.get("device", {}).get(k) for k in ("model_id", "sw_version", "identifiers")],
                        "origin": [document.get("origin", {}).get(k) for k in ("name", "sw_version")]}
            if self.phase != "waiting_request" or pin(payload) != pin(self.discovery):
                self.stop("discovery_changed")
            else:
                self.discovery_seen = True
            return None
        if retained and not (kind == "info" and self.phase == "waiting_request"):
            return None
        if kind == "request":
            if self.phase != "waiting_request" or not self.baseline_seen or not self.discovery_seen or payload != self.request:
                self.stop("unexpected_control_request")
            else:
                self.phase, self.reason = "waiting_readback", "awaiting_native_ack_and_info"
                self.cutoff_utc, self.deadline = utc, mono + self.duration_s
            return None
        if kind == "info":
            try:
                config = payload["config"]
                scoped = {"device_options": config.get("device_options", {}),
                          "devices": {self.ieee: config["devices"][self.ieee]}}
                reference = self.baseline if self.phase == "waiting_request" else self.expected
                expected = {"device_options": reference.get("device_options", {}),
                            "devices": {self.ieee: reference["devices"][self.ieee]}}
                ok = (payload["version"] == "2.14.2"
                      and payload["zigbee_herdsman_converters"]["version"] == "26.115.1"
                      and payload["restart_required"] is False
                      and config["advanced"]["cache_state"] is True
                      and config["advanced"]["last_seen"] == "ISO_8601"
                      and scoped == expected)
            except (KeyError, TypeError):
                ok = False
            if self.phase == "waiting_request":
                if ok:
                    self.baseline_seen = True
                    self.reason = "baseline_config_readback_observed"
                else:
                    self.stop("baseline_readback_mismatch")
                return None
            if not ok:
                self.stop("option_or_version_readback_changed")
            else:
                self.info_seen = True
            return None
        if kind == "ack":
            expected = {"from": clean(effective(self.baseline, self.ieee)),
                        "to": clean(effective(self.expected, self.ieee)),
                        "id": self.ieee, "restart_required": False}
            if (self.phase != "waiting_readback" or not self.info_seen
                    or payload != {"status": "ok", "data": expected,
                                   "transaction": self.request["transaction"]}):
                self.stop("ack_mismatch_or_lost_barrier")
            else:
                self.phase, self.reason = "draining", "drop_first_nonretained_temperature_frame"
            return None
        if kind != "source" or self.phase not in ("draining", "active"):
            return None
        try:
            value = payload["temperature"]
            if type(value) not in (int, float) or not math.isfinite(value) or not -20 <= value <= 60:
                return None
            timestamp = datetime.fromisoformat(payload["last_seen"].replace("Z", "+00:00"))
            if timestamp.utcoffset() is None:
                raise ValueError("naive time")
            seen = timestamp.timestamp()
            age = (utc-seen)*1000
            if seen < self.cutoff_utc or age < 0 or age >= self.max_age_ms:
                return None
            if self.last_seen is not None and seen <= self.last_seen:
                return None
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
            return None
        self.last_seen = seen
        if self.phase == "draining":
            self.phase, self.reason = "active", "first_cache_carryover_discarded"
            return None
        return {"temperature_c": value, "source_sample_age_ms": math.ceil(age),
                "evidence": "validated_integration_report",
                "sample_key": str(seen), "received_monotonic": mono,
                "bench_deadline_monotonic": self.deadline}

def replay(lines):
    """Executable JSONL protocol harness; configuration first, then observed events."""
    gate = None
    for line in lines:
        event = json.loads(line)
        if gate is None:
            gate = BenchSource(**event)
            yield {"request_proposal": gate.request, "rollback_proposal": gate.rollback}
            continue
        result = gate.event(**event)
        yield {"phase": gate.phase, "reason": gate.reason, "observation": result}

if __name__ == "__main__":
    import sys
    for record in replay(sys.stdin):
        print(json.dumps(record, sort_keys=True, separators=(",", ":")))
