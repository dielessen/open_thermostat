
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

_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")
_HEX = re.compile(r"[0-9a-f]{64}")
MAX_BYTES = 8192


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

    @property
    def ready(self):
        now = self.clock()
        return (not self.closed and self.verified and self.session is not None
                and self.session.get("mapping_ready") is True
                and now < self.grant_until and now < self.lease_until
                and now - self.last_rx < 15)

    def changed(self):
        self.runtime.diagnostics["transport"] = self.error
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
        for item in self.pending.values():
            if item["future"] is not None and not item["future"].done():
                item["future"].cancel()
        self.session = None
        self.sequence.clear()
        self.pending.clear()
        self.open_request = None
        self.verified = False
        self.grant_until = self.lease_until = 0
        self.runtime.decisions.clear()

    async def async_disconnected(self):
        self.reset_session()
        self.identity = None
        self.error = "disconnected"
        self.changed()

    async def receive(self, topic, raw, *, retained=False):
        if self.closed or retained:
            return
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

    def same_identity(self, p):
        return (self.identity and type(p.get("api")) is int and p.get("api") == 1
                and p.get("controller_id") == self.identity[0]
                and p.get("boot_id") == self.identity[1]
                and integer(p.get("epoch"), 1) and p.get("epoch") == self.identity[2])

    def same_config(self, p):
        return (self.session is not None and
                integer(p.get("config_revision")) and p.get("config_revision") == self.session["config_revision"] and
                p.get("config_digest") == self.session["config_digest"])

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
                # FW rotates at most once per >=5s. Conservative issuance lower
                # bound propagates from the original nonce round trip, not from
                # unrelated/replayed state receipts. Never compare clock origins.
                grant_deadline = min(self.clock() + 10, self.grant_until +
                                     5 * (p["grant_sequence"] - self.session["grant_sequence"]))
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
                    or row.get("target_source") not in {"base", "schedule", "temporary", "off"}
                    or (row.get("sample_age_ms") is not None and not integer(row["sample_age_ms"], 0, 9007199254740991))
                    or (row.get("temperature_centi_c") is not None and
                        (row.get("sample_state") != 1 or row.get("sample_age_ms") is None
                         or row["sample_age_ms"] >= self.runtime.rooms[row["zone_id"]].maximum_age_ms))
                    or (row.get("demand") is True and (row.get("temperature_centi_c") is None or row.get("target_centi_c") is None))):
                    raise ValueError("state quality/duplicate")
                decisions[row["zone_id"]] = RoomDecision(
                    row["target_centi_c"], row["temperature_centi_c"], row["demand"], row["reason"])
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
        if current_revision >= 4294967295:
            raise ValueError("revision exhausted")
        config = {"schema": 1, "mode": "shadow", "revision": current_revision + 1,
                  "mapping_digest": digest(self.mapping), "zones": json.loads(canonical(self.desired))}
        if len(canonical(config).encode("ascii")) > 4096:
            raise ValueError("configuration budget exceeded")
        record = {"config": config, "config_digest": digest(config), "mapping": json.loads(canonical(self.mapping))}
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
        raw = canonical(p)
        parse(raw)
        self.sequence[binding] += 1
        result_topic = {"ha/heartbeat": "fw/heartbeat_result", "ha/config": "fw/config_result",
                        "ha/observations": "fw/observation_result", "ha/user_command": "fw/user_command_result",
                        "ha/snapshot_request": "fw/snapshot_result"}[topic]
        key = (result_topic, binding, p["sequence"])
        self.pending[key] = {"topic": topic, "raw": raw, "sent": self.clock(), "last": self.clock(),
                             "tries": 1, "future": future, "deadline": self.grant_until}
        if len(self.pending) > 48:
            self.pending.pop(key)
            raise HomeAssistantError("Bounded shadow command queue full")
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
            "evidence": "physical_report" if usable else "unverified"})

    async def async_setpoint(self, room_id, centi_c):
        if not self.ready or room_id not in self.runtime.rooms or not integer(centi_c, 500, 3500):
            raise HomeAssistantError("Shadow mapping not ready")
        future = self.runtime.hass.loop.create_future()
        await self.message("ha/user_command", room_id, {
            "mode": "temporary", "temperature_centi_c": centi_c, "duration_ms": 3600000}, future)
        await future  # Bounded by poll(); teardown cancels unresolved futures.

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
