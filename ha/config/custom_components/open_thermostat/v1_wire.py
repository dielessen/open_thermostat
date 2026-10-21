
"""Bounded TEST-WIRE v1 shadow client; no actuator execution.

All timeouts use the receiver's local monotone clock, never FW milliseconds.
Native MQTT and Store are supplied by v1_mqtt; injected IO enables actual FW tests.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
import re
import secrets

from homeassistant.exceptions import HomeAssistantError

from .v1_model import Observation, RoomDecision
from .session_grant import register_grant_proof, consume_grant_proof, MAX_GRANT_PROOFS
from .metric_snapshot import CAPABILITY,MAX_BYTES as MAX_METRIC_BYTES,EXPIRY_SECONDS,valid_snapshot

_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
_HEX = re.compile(r"[0-9a-f]{64}")
MAX_BYTES = 8192
GRANT_NONCE_CAPABILITY = "session.grant_nonce.v1"
COMFORT_CAPABILITY = "comfort.target.v1"
COMFORT_MODES = {"auto","off","temporary","boost","away","vacation","frost"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("ascii")).hexdigest()


def integer(value, low=0, high=4294967295):
    return type(value) is int and low <= value <= high


def identifier(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def parse(raw):
    """Wire is ASCII without escapes; reject duplicates, deep/oversize trees."""
    if not isinstance(raw, str) or len(raw) > MAX_BYTES or not raw.isascii() or "\\" in raw:
        raise ValueError("invalid wire bytes")
    # Bound nesting before JSON allocation. Strings on this profile contain no escapes.
    depth = 0
    quoted = False
    for char in raw:
        if char == '"':
            quoted = not quoted
        elif not quoted:
            if char in "[{":
                depth += 1
                if depth > 12:
                    raise ValueError("wire depth")
            elif char in "]}":
                depth -= 1
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate member")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("non-finite number")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    def nodes(item):
        if isinstance(item, dict):
            return 1 + sum(1 + nodes(x) for x in item.values())
        if isinstance(item, list):
            return 1 + sum(nodes(x) for x in item)
        return 1
    if not isinstance(value, dict) or nodes(value) > 512:
        raise ValueError("wire shape/budget")
    return value


class ShadowClient:
    def __init__(self, runtime, adapter_id, send, store, desired, mapping, clock):
        if not identifier(adapter_id):
            raise ValueError("invalid local adapter owner")
        self.runtime, self.adapter_id = runtime, adapter_id
        self.controller_policy=getattr(runtime,"controller_policy_source_profile",None)
        if self.controller_policy is not None:
            self.controller_policy.validate()
            if self.controller_policy.adapter_id!=adapter_id:raise ValueError("controller_policy_owner_mismatch")
        self.source_policy_matched=False
        self.graph_source_review_required=False
        self.send, self.store, self.clock = send, store, clock
        self.desired, self.mapping = json.loads(canonical(desired)), json.loads(canonical(mapping))
        self.journal = {"accepted": None, "staged": None}
        self.identity = None
        self.session = None
        self.open_request = None
        self.open_sent = 0.0
        self.grant_until = 0.0
        self.lease_until = 0.0
        self.last_rx = 0.0
        self.sequence = defaultdict(int)
        self.pending = {}
        self.verified = False
        self.closed = False
        self.error = "not_connected"
        self._nonce = lambda: secrets.token_hex(12)
        self._close_io = None
        self.grant_nonce_supported=False
        self._grant_proofs={}
        self.metrics_supported=False
        self.comfort_supported=False
        self._metrics=None
        self._metrics_received=0.0
        self._metrics_highwater=0

    @property
    def metrics_payload(self):
        if (not self.ready or not self.metrics_supported or self._metrics is None
                or not 0<=self.clock()-self._metrics_received<EXPIRY_SECONDS):
            return None
        return dict(self._metrics) # Flat schema, no caller can mutate cached data.

    @property
    def metrics_key(self):
        return (self.session.get("adapter_session_id") if self.session else None,
                self._metrics_highwater,self.metrics_payload is not None)

    @property
    def ready(self):
        now = self.clock()
        return (not self.closed and not self.graph_source_review_required and self.verified and (self.controller_policy is None or self.source_policy_matched) and self.session is not None
                and self.session.get("mapping_ready") is True
                and now < self.grant_until and now < self.lease_until
                and now - self.last_rx < 15)

    def changed(self):
        self.runtime.diagnostics["transport"] = self.error
        self.runtime.diagnostics["controller_policy"]=("default_api1" if self.controller_policy is None else
            "source_identity_verified_shadow_only" if self.source_policy_matched else "source_identity_unverified")
        self.runtime._notify()

    async def async_start(self):
        stored = await self.store.async_load()
        if stored is not None:
            if not isinstance(stored, dict) or set(stored) != {"accepted", "staged"}:
                raise ValueError("invalid durable mapping journal")
            for record in stored.values():
                if record is not None and not self.valid_record(record):
                    raise ValueError("invalid durable mapping record")
            self.journal = stored

    async def async_stage_graph_source_readback(self):
        source=getattr(self.runtime,"graph_controller_source",None)
        if source is None or self.controller_policy!=source.controller:
            raise ValueError("graph_control_source_invalid")
        source.validate()
        config=source.projection()
        record={"config":config,"config_digest":digest(config),"mapping":source.record()["mapping"]}
        current=await self.store.async_load()
        # Same never-configured representation already used by async_start.
        if current is None:current={"accepted":None,"staged":None}
        if current!=self.journal:
            raise ValueError("graph_control_existing_journal_drift")
        if self.journal["accepted"]==record and self.journal["staged"] is None:return
        if self.journal["accepted"] is not None or self.journal["staged"] not in (None,record):
            raise ValueError("graph_control_existing_journal_conflict")
        # Explicit known SOURCE tuple is only STAGED. A fresh matching device
        # snapshot, not this Store save/ACK/graph_ready, performs reconciliation.
        await self.save({"accepted":None,"staged":record})
        if await self.store.async_load()!=self.journal:
            raise ValueError("graph_control_stage_readback_failed")

    @staticmethod
    def valid_record(record):
        try:
            return (set(record) == {"config", "config_digest", "mapping"}
                    and digest(record["config"]) == record["config_digest"]
                    and digest(record["mapping"]) == record["config"]["mapping_digest"]
                    and integer(record["config"]["revision"], 1))
        except (KeyError, TypeError, ValueError):
            return False

    def known(self, revision, config_digest):
        return next((record for record in self.journal.values()
                     if record and record["config"]["revision"] == revision
                     and record["config_digest"] == config_digest), None)

    async def save(self, journal):
        # Native Store's awaited atomic save completes BEFORE any config publish.
        snapshot = json.loads(canonical(journal))
        await self.store.async_save(snapshot)
        self.journal = snapshot

    def reset_session(self):
        self.source_policy_matched=False
        for item in self.pending.values():
            if item["future"] is not None and not item["future"].done():
                item["future"].cancel()
        self.session = None
        self.sequence.clear()
        self.pending.clear()
        self.open_request = None
        self.grant_nonce_supported = False
        self.comfort_supported = False
        self._grant_proofs.clear()
        self.verified = False
        self.grant_until = self.lease_until = 0
        self.runtime.decisions.clear()
        self.runtime.invalidate_context_sources()
        self._metrics=None
        self._metrics_received=0.0
        self._metrics_highwater=0

    def require_graph_source_review(self):
        if getattr(self.runtime,"graph_controller_source",None) is None:
            raise ValueError("graph_control_source_not_selected")
        self.graph_source_review_required=True
        self.reset_session()
        self.error="graph_control_source_review_required"
        self.changed()

    async def async_disconnected(self):
        self.reset_session()
        self.identity = None
        self.error = "disconnected"
        self.changed()

    async def receive(self, topic, raw, *, retained=False):
        if self.closed or retained or self.graph_source_review_required:
            return
        if topic == "fw/telemetry/ems_metrics":
            self.receive_metrics(raw)
            return # No last_rx/lease/sample/control update, even for valid telemetry.
        if topic == "fw/availability" and raw in ("online", "offline"):
            # The actual PubSubClient transport uses plain LWT tokens. Neither
            # token establishes a session, source sample or fresh heat request.
            await self.async_disconnected()
            self.error = "firmware_offline" if raw == "offline" else "awaiting_firmware_handshake"
            self.changed()
            return
        try:
            payload = parse(raw)
            await self._receive(topic, payload)
        except (ValueError, KeyError, TypeError, OverflowError):
            self.reset_session()
            self.error = "invalid_firmware_message"
            self.changed()

    def receive_metrics(self,raw):
        if not self.ready or not self.metrics_supported:
            return
        try:
            if not isinstance(raw,str) or len(raw)>MAX_METRIC_BYTES:
                raise ValueError("metric budget")
            p=parse(raw)
            # Foreign/stale scope cannot disturb a legitimate current display.
            if (not self.same_identity(p) or not self.same_config(p)
                    or p.get("adapter_id")!=self.adapter_id
                    or p.get("adapter_session_id")!=self.session["adapter_session_id"]
                    or p.get("grant_id")!=self.session["grant_id"]
                    or p.get("grant_sequence")!=self.session["grant_sequence"]):
                return
            expected={"api","controller_id","boot_id","epoch","config_revision","config_digest","mode",
                      "adapter_id","adapter_session_id","grant_id","grant_sequence","sequence",
                      "boiler_output_enabled","actuator_output_enabled","metrics"}
            if (set(p)!=expected or p["mode"]!="shadow" or p["boiler_output_enabled"] is not False
                    or p["actuator_output_enabled"] is not False or not integer(p["sequence"],1)
                    or type(p["grant_sequence"]) is not int or not valid_snapshot(p["metrics"])):
                raise ValueError("metric shape")
            if p["sequence"]<=self._metrics_highwater:
                return # Duplicate/reorder can never refresh age or revive expired data.
            self._metrics=dict(p["metrics"]);self._metrics_highwater=p["sequence"]
            self._metrics_received=self.clock()
            self.runtime.diagnostics["metrics"]="read_only_snapshot_not_control_qualified"
        except (ValueError,TypeError,KeyError,OverflowError):
            self._metrics=None # Preserve high-water and valid CONTROL session.
            self.runtime.diagnostics["metrics"]="invalid_read_only_snapshot"
        self.runtime._notify()

    def same_identity(self, p):
        return (self.identity and type(p.get("api")) is int and p.get("api") == 1
                and p.get("controller_id") == self.identity[0]
                and p.get("boot_id") == self.identity[1]
                and integer(p.get("epoch"), 1) and p.get("epoch") == self.identity[2])

    def same_config(self, p):
        return (self.session is not None and
                integer(p.get("config_revision")) and p.get("config_revision") == self.session["config_revision"] and
                p.get("config_digest") == self.session["config_digest"])

    def source_policy_matches(self,p):
        if self.controller_policy is None:
            if "source_policy" not in p:return True
            self.reset_session();self.error="controller_policy_not_selected";self.changed();return False
        if not self.controller_policy.matches(p):
            self.reset_session();self.error="controller_policy_mismatch";self.changed();return False
        self.source_policy_matched=True
        return True

    async def _receive(self, topic, p):
        if topic == "fw/hello":
            if (not integer(p.get("api"), 1, 1) or p.get("mode") != "shadow"
                or not all(identifier(p.get(k)) for k in ("controller_id", "boot_id", "challenge_id"))
                or not integer(p.get("epoch"), 1)
                or not integer(p.get("config_revision"))
                or not isinstance(p.get("config_digest"), str)
                or (p["config_revision"] == 0 and p["config_digest"] != "")
                or (p["config_revision"] != 0 and not _HEX.fullmatch(p["config_digest"]))
                or p.get("lease_ms") != 15000 or p.get("grant_ms") != 10000
                or type(p.get("storage_fault", False)) is not bool):
                raise ValueError("hello")
            new_identity = (p["controller_id"], p["boot_id"], p["epoch"])
            if self.identity and new_identity[:2] == self.identity[:2] and new_identity[2] < self.identity[2]:
                return
            if p.get("storage_fault"):
                self.reset_session()
                self.error = "firmware_storage_fault"
                self.changed()
                return
            if new_identity != self.identity or (self.session and not self.same_config(p)):
                self.reset_session()
                self.identity = new_identity
            if not self.source_policy_matches(p):return
            session_caps=p.get("session_capabilities",[])
            self.grant_nonce_supported=(type(session_caps) is list and len(session_caps)<=8
                and all(isinstance(cap,str) and len(cap)<=64 for cap in session_caps)
                and GRANT_NONCE_CAPABILITY in session_caps)
            if not self.grant_nonce_supported:
                self._grant_proofs.clear()
            comfort_caps=p.get("control_capabilities",[])
            self.comfort_supported=(type(comfort_caps) is list and len(comfort_caps)<=8
                and all(isinstance(cap,str) and len(cap)<=64 for cap in comfort_caps)
                and COMFORT_CAPABILITY in comfort_caps)
            if any("comfort" in z for z in self.desired) and not self.comfort_supported:
                self.reset_session();self.error="comfort_capability_unavailable";self.changed();return
            caps=p.get("read_only_capabilities",[])
            self.metrics_supported=(type(caps) is list and len(caps)<=8
                and all(isinstance(cap,str) and len(cap)<=64 for cap in caps) and CAPABILITY in caps)
            if not self.metrics_supported:
                self._metrics=None
            self.last_rx = self.clock()
            if self.session:
                return
            known = self.known(p["config_revision"], p["config_digest"])
            # Unknown remote revision is diagnostic-only: never silently adopt.
            revision, known_digest = ((p["config_revision"], p["config_digest"])
                                      if known else (0, ""))
            if self.open_request is None:
                self.open_request = dict(
                    api=1, controller_id=p["controller_id"], boot_id=p["boot_id"],
                    epoch=p["epoch"], challenge_id=p["challenge_id"],
                    adapter_id=self.adapter_id, client_nonce=self._nonce(),
                    known_revision=revision, known_digest=known_digest)
                if self.controller_policy is not None:
                    self.open_request.update(source_profile_digest=self.controller_policy.profile_digest,
                                             source_config_pin=self.controller_policy.config_digest)
                self.open_sent = self.clock()
            elif self.clock() - self.open_sent >= 10:
                self.open_request = None
                return  # Next fresh hello; no cached-challenge admission.
            await self.send("ha/open_session", canonical(self.open_request))
            return

        if not self.same_identity(p):
            return
        if topic == "fw/session":
            if (not self.open_request or p.get("client_nonce") != self.open_request["client_nonce"]
                or p.get("adapter_id") != self.adapter_id
                or not all(identifier(p.get(k)) for k in ("adapter_session_id", "grant_id"))
                or not integer(p.get("grant_sequence"), 1)
                or p.get("grant_ms") != 10000 or type(p.get("mapping_ready")) is not bool
                or not integer(p.get("config_revision"))):
                raise ValueError("session")
            if self.session:
                if p["adapter_session_id"] != self.session["adapter_session_id"]:
                    return
                if p["grant_sequence"] <= self.session["grant_sequence"]:
                    return  # Repeated status may NOT extend a grant.
                if not self.same_config(p):
                    raise ValueError("session config changed")
                # Safe old-peer fallback: minimum5s per rotation, NOT receipt+10.
                grant_deadline = min(self.clock() + 10, self.grant_until +
                                     5 * (p["grant_sequence"] - self.session["grant_sequence"]))
                proof=p.get("grant_request_nonce")
                if self.grant_nonce_supported and identifier(proof):
                    deadline=consume_grant_proof(self._grant_proofs,proof,self.clock())
                    if deadline is not None:
                        # SAME original-send proof used by explicit graph owner.
                        grant_deadline=max(grant_deadline,deadline)
                delay_bound = self.clock() + 10 - grant_deadline
            else:
                delay_bound = self.clock() - self.open_sent
            if delay_bound < 0 or delay_bound >= 10:
                raise ValueError("late grant")
            self.session = p
            self.grant_until = self.clock() + 10 - delay_bound
            self.last_rx = self.clock()
            await self.message("ha/heartbeat", "adapter", {})
            self.changed()
            return

        if self.session is None or not self.same_config(p):
            return
        if topic=="fw/state/zones" and not self.source_policy_matches(p):return
        self.last_rx = self.clock()
        if topic.endswith("_result"):
            if p.get("adapter_session_id") != self.session["adapter_session_id"]:
                return
            key = (topic, p.get("binding_id"), p.get("sequence"))
            pending = self.pending.get(key)
            if pending is None:
                return
            if p.get("status") not in {"accepted", "duplicate", "applied", "conflict", "rejected", "storage_fault", "mapping_conflict"}:
                raise ValueError("result")
            self.pending.pop(key)
            status = p["status"]
            if status in {"rejected", "conflict", "storage_fault", "mapping_conflict"}:
                self.error = status
                if topic == "fw/user_command_result" and not pending["future"].done():
                    pending["future"].set_exception(HomeAssistantError("Firmware rejected shadow command"))
                if status == "storage_fault":
                    self.reset_session()
                self.changed()
                return
            if topic == "fw/heartbeat_result":
                # Use original publish timestamp, not receipt, as conservative start.
                self.lease_until = pending["sent"] + 15
                if not self.verified:
                    await self.message("ha/snapshot_request", "snapshot", {})
            if topic == "fw/user_command_result" and not pending["future"].done():
                pending["future"].set_result(None)
            return

        if topic == "fw/config_snapshot":
            await self.snapshot(p)
            return
        if topic == "fw/state/zones":
            if (p.get("mode") != "shadow" or p.get("boiler_output_enabled") is not False
                or p.get("actuator_output_enabled") is not False
                or type(p.get("adapter_alive")) is not bool or not isinstance(p.get("zones"), list)):
                raise ValueError("not shadow state")
            if not self.ready or not p["adapter_alive"]:
                self.runtime.decisions.clear()
                self.changed()
                return
            rows = p["zones"]
            if len(rows) != len(self.runtime.rooms) or {r.get("zone_id") for r in rows} != set(self.runtime.rooms):
                raise ValueError("state room mismatch")
            decisions = {}
            for row in rows:
                if (row["zone_id"] in decisions or not isinstance(row.get("reason"), str)
                    or len(row["reason"]) > 64 or not integer(row.get("sample_state"), 0, 6)
                    or row.get("target_source") not in ({"base","schedule","temporary","off","boost","away","vacation","frost","window","presence","limit"} if self.comfort_supported else {"base","schedule","temporary","off"})
                    or (row.get("sample_age_ms") is not None and not integer(row["sample_age_ms"], 0, 9007199254740991))
                    or (row.get("temperature_centi_c") is not None and
                        (row.get("sample_state") != 1 or row.get("sample_age_ms") is None
                         or row["sample_age_ms"] >= self.runtime.rooms[row["zone_id"]].maximum_age_ms))
                    or (row.get("demand") is True and (row.get("temperature_centi_c") is None or row.get("target_centi_c") is None))):
                    raise ValueError("state quality/duplicate")
                room=self.runtime.rooms[row["zone_id"]]
                if room.comfort is not None and (not self.comfort_supported or row.get("comfort_mode") not in COMFORT_MODES
                    or not integer(row.get("override_remaining_ms"),0,43200000)
                    or not integer(row.get("vacation_until_utc"),0,4102444800)
                    or type(row.get("learning_allowed")) is not bool
                    or (row.get("target_centi_c") is not None and
                        not room.minimum_target_centi_c<=row["target_centi_c"]<=room.maximum_target_centi_c)):
                    raise ValueError("comfort state")
                decisions[row["zone_id"]] = RoomDecision(
                    row["target_centi_c"], row["temperature_centi_c"], row["demand"], row["reason"],
                    row["target_source"],row.get("comfort_mode"),row.get("override_remaining_ms",0),row.get("vacation_until_utc",0))
            self.runtime.decisions = decisions
            self.error = "shadow_ready"
            self.changed()

    async def snapshot(self, p):
        config = p.get("config")
        if config is None:
            if p["config_revision"] != 0 or p["config_digest"] != "":
                raise ValueError("empty snapshot")
            await self.propose(0)
            return
        if digest(config) != p["config_digest"] or config.get("revision") != p["config_revision"]:
            raise ValueError("snapshot digest")
        if self.controller_policy is not None and p["config_digest"]!=self.controller_policy.config_digest:
            self.reset_session();self.error="controller_policy_config_mismatch";self.changed();return
        record = self.known(p["config_revision"], p["config_digest"])
        if record is None or record["config"] != config:
            self.error = "mapping_conflict"
            self.verified = False
            self.changed()
            return
        if self.journal["accepted"] != record or self.journal["staged"] is not None:
            await self.save({"accepted": record, "staged": None})
        if config["mapping_digest"] != digest(self.mapping) or config["zones"] != self.desired:
            await self.propose(config["revision"])
            return
        self.verified = self.session["mapping_ready"]
        self.error = "shadow_ready" if self.verified else "mapping_not_admitted"
        self.changed()

    async def propose(self, current_revision):
        if getattr(self.runtime,"graph_controller_source",None) is not None:
            # This route consumes a reviewed graph projection readback only.
            # Unknown/empty remote config must never become an API1 write path.
            self.require_graph_source_review()
            return
        if current_revision >= 4294967295:
            raise ValueError("revision exhausted")
        config = {"schema": 1, "mode": "shadow", "revision": current_revision + 1,
                  "mapping_digest": digest(self.mapping), "zones": json.loads(canonical(self.desired))}
        if len(canonical(config).encode("ascii")) > 4096:
            raise ValueError("configuration budget exceeded")
        record = {"config": config, "config_digest": digest(config), "mapping": json.loads(canonical(self.mapping))}
        if self.controller_policy is not None and record["config_digest"]!=self.controller_policy.config_digest:
            self.reset_session();self.error="controller_policy_config_mismatch";self.changed();return
        # Also validate full wire budget BEFORE staging.
        probe = self.envelope("config")
        probe.update(expected_revision=current_revision, config_digest=record["config_digest"], config=config)
        parse(canonical(probe))
        await self.save({**self.journal, "staged": record})
        await self.message("ha/config", "config", {
            "expected_revision": current_revision, "config_digest": record["config_digest"], "config": config})
        self.verified = False
        self.error = "awaiting_config_readback"
        self.changed()

    def envelope(self, binding):
        if self.session is None or self.clock() >= self.grant_until:
            raise HomeAssistantError("No fresh firmware grant")
        return dict(api=1, controller_id=self.identity[0], boot_id=self.identity[1],
                    epoch=self.identity[2], adapter_id=self.adapter_id,
                    adapter_session_id=self.session["adapter_session_id"],
                    grant_id=self.session["grant_id"], grant_sequence=self.session["grant_sequence"],
                    config_revision=self.session["config_revision"], binding_id=binding,
                    sequence=self.sequence[binding] + 1)

    async def message(self, topic, binding, body, future=None):
        p = self.envelope(binding)
        p.update(body)
        if topic=="ha/heartbeat" and self.grant_nonce_supported:
            # Session-local HB sequence prevents reuse even if a test RNG repeats.
            p["grant_request_nonce"]=f"g{p['sequence']:08x}{self._nonce()[:20]}"
            if not identifier(p["grant_request_nonce"]):
                raise HomeAssistantError("Invalid grant request nonce")
        raw = canonical(p)
        parse(raw)
        self.sequence[binding] += 1
        result_topic = {"ha/heartbeat": "fw/heartbeat_result", "ha/config": "fw/config_result",
                        "ha/observations": "fw/observation_result", "ha/user_command": "fw/user_command_result",
                        "ha/snapshot_request": "fw/snapshot_result"}[topic]
        key = (result_topic, binding, p["sequence"])
        sent=self.clock()
        self.pending[key] = {"topic": topic, "raw": raw, "sent": sent, "last": sent,
                             "tries": 1, "future": future, "deadline": self.grant_until}
        if len(self.pending) > 48:
            self.pending.pop(key)
            raise HomeAssistantError("Bounded shadow command queue full")
        if topic=="ha/heartbeat" and self.grant_nonce_supported:
            register_grant_proof(self._grant_proofs,p["grant_request_nonce"],sent)
        await self.send(topic, raw)

    async def async_observation(self, room_id, observation: Observation):
        if not self.ready:
            return
        room = self.runtime.rooms[room_id]
        age = observation.source_age_ms or 0
        if observation.observed_monotonic is not None:
            age += math.ceil(max(0, self.clock() - observation.observed_monotonic) * 1000)
        usable = (observation.quality == "qualified" and observation.temperature_c is not None
                  and age < room.maximum_age_ms)
        await self.message("ha/observations", f"s_{room_id}", {
            "zone_id": room_id, "source_available": usable,
            "temperature_c": observation.temperature_c if usable else 0,
            "source_sample_age_ms": age if usable else 0,
            "evidence": "physical_report" if usable else "unverified",
            **(self.runtime.comfort_context(room) if room.comfort is not None else {})})

    async def async_setpoint(self, room_id, centi_c):
        if not self.ready or room_id not in self.runtime.rooms or not integer(centi_c, 500, 3500):
            raise HomeAssistantError("Shadow mapping not ready")
        if self.runtime.rooms[room_id].comfort is not None:
            await self.async_comfort(room_id,"temporary",temperature=centi_c/100)
            return
        future = self.runtime.hass.loop.create_future()
        await self.message("ha/user_command", room_id, {
            "mode": "temporary", "temperature_centi_c": centi_c, "duration_ms": 3600000}, future)
        await future  # Bounded by poll(); teardown cancels unresolved futures.

    async def async_comfort(self,room_id,mode,*,temperature=None,duration_ms=None,vacation_until_utc=0):
        from .v1_model import target_centi
        room=self.runtime.rooms.get(room_id)
        if not self.ready or not self.comfort_supported or room is None or room.comfort is None or mode not in COMFORT_MODES:
            raise HomeAssistantError("Comfort capability/mapping unavailable")
        target=None
        duration=0
        if mode in {"temporary","boost"}:
            try:
                target=target_centi(temperature if temperature is not None else (room.maximum_target_centi_c if mode=="boost" else room.base_centi_c)/100)
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err;
            if not room.minimum_target_centi_c<=target<=room.maximum_target_centi_c:
                raise HomeAssistantError("Comfort target outside room limits")
            duration=duration_ms if duration_ms is not None else min(room.comfort["temporary_ms"],14400000 if mode=="boost" else 43200000)
            if not integer(duration,1000,14400000 if mode=="boost" else 43200000):
                raise HomeAssistantError("Comfort duration invalid")
        elif temperature is not None or duration_ms is not None:
            raise HomeAssistantError("Unexpected comfort target/duration")
        if not integer(vacation_until_utc,0,4102444800) or (mode!="vacation" and vacation_until_utc):
            raise HomeAssistantError("Vacation expiry invalid")
        if mode=="vacation":
            from homeassistant.util import dt as dt_util
            now=int(dt_util.utcnow().timestamp())
            if not now<vacation_until_utc<=now+366*86400:
                raise HomeAssistantError("Vacation needs a bounded future UTC expiry")
        future=self.runtime.hass.loop.create_future()
        await self.message("ha/user_command",room_id,{"mode":mode,"temperature_centi_c":target,
            "duration_ms":duration,"vacation_until_utc":vacation_until_utc},future)
        await future # Only admitted fw/state confirms a target. Never store/replay commands.

    async def poll(self):
        if self.closed:
            return
        now = self.clock()
        for key, item in list(self.pending.items()):
            if now >= item["deadline"] or now - item["sent"] >= 8 or item["tries"] >= 3:
                self.pending.pop(key, None)
                if item["future"] is not None and not item["future"].done():
                    item["future"].set_exception(HomeAssistantError("Shadow acknowledgement timed out; effect unknown"))
                self.error = "ack_timeout_effect_unknown"
            elif now - item["last"] >= 2:
                # Critical: exact original complete bytes, including original grant.
                item["tries"] += 1
                item["last"] = now
                await self.send(item["topic"], item["raw"])
        if self.session and now < self.grant_until:
            if not any(k[0] == "fw/heartbeat_result" for k in self.pending):
                await self.message("ha/heartbeat", "adapter", {})
        if self.session and (now - self.last_rx >= 15 or (self.lease_until and now >= self.lease_until)):
            await self.async_disconnected()
        self.changed()

    async def async_close(self):
        self.closed = True
        for item in self.pending.values():
            if item["future"] is not None and not item["future"].done():
                item["future"].cancel()
        self.reset_session()
        if self._close_io:
            await self._close_io()
