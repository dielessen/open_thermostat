"""Native Store transaction policy for the bounded graph-shadow profile.

No worker/listener/service, no automatic publish, no active-runtime import.
The existing transport owner supplies fresh admitted context/capability and send.
Current api1 firmware cannot pass this gate and is never silently migrated.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from contextlib import asynccontextmanager
import math

from .graph_shadow_validation import (
    CAPS, MAX_ROOMS, MAX_GROUPS, MAX_ACTUATORS, MAX_TRANSITIONS,
    MAX_TOTAL_TRANSITIONS, MAX_STREAMS, GraphValidationContext,
    GraphValidationError, canonical, digest, integer, obj, raw_document,
    validate_graph_shadow,
)

LIMITS = dict(rooms=MAX_ROOMS, groups=MAX_GROUPS, actuators=MAX_ACTUATORS,
              transitions=MAX_TRANSITIONS, total_transitions=MAX_TOTAL_TRANSITIONS,
              streams=MAX_STREAMS, config_bytes=4096, wire_bytes=8192)
IDENTITY = ("controller_id", "boot_id", "epoch", "adapter_id",
            "adapter_session_id", "grant_id", "grant_sequence")


def require(condition, code):
    if not condition:
        raise GraphValidationError(code)


class GraphShadowJournal:
    """One existing native Store + awaited atomic transaction; no coordinator IO."""
    def __init__(self, store, qualification_digest, clock):
        require(isinstance(qualification_digest, str)
                and len(qualification_digest) == 64
                and all(c in "0123456789abcdef" for c in qualification_digest), "qualification")
        self.store, self.qualification_digest, self.clock = store, qualification_digest, clock
        self._lock = asyncio.Lock()
        self._state = None
        self.status = "not_loaded"
        self.verified = False
        self._generation = 0

    @asynccontextmanager
    async def _transaction(self):
        async with self._lock:
            self.verified = False
            try:
                yield
            except GraphValidationError as error:
                self.status = error.code
                raise
            except asyncio.CancelledError:
                self.status = 'graph_interrupted'
                raise
            except Exception:
                if self.status != 'graph_send_unconfirmed':
                    self.status = 'storage_fault'
                raise

    def invalidate(self):
        # Reconnect never resurrects admission from a persisted accepted record.
        self._generation += 1
        self.verified = False
        self.status = "awaiting_graph_readback"

    @staticmethod
    def _record(record):
        obj(record, "config config_digest mapping")
        config, mapping = record["config"], record["mapping"]
        require(isinstance(config, dict) and isinstance(mapping, dict), "journal_schema")
        require(type(config.get("schema")) is int and config["schema"] == 2
                and config.get("mode") == "shadow_graph", "unsupported_schema")
        require(type(mapping.get("mapping_schema")) is int
                and mapping["mapping_schema"] == 2, "unsupported_schema")
        integer(config.get("revision"), 1, 4294967295)
        integer(mapping.get("mapping_revision"), 1, 4294967295)
        require(record["config_digest"] == digest(config)
                and config.get("mapping_revision") == mapping["mapping_revision"]
                and config.get("mapping_digest") == digest(mapping), "mapping_conflict")
        return deepcopy(record)

    async def _load(self):
        if self._state is not None:
            return
        try:
            value = await self.store.async_load()
            if value is None:
                value = dict(schema=1, accepted=None, staged=None)
            obj(value, "schema accepted staged")
            require(type(value["schema"]) is int and value["schema"] == 1, "journal_schema")
            for key in ("accepted", "staged"):
                if value[key] is not None:
                    self._record(value[key])
            if value["accepted"] and value["staged"]:
                require(value["staged"]["config"]["revision"]
                        == value["accepted"]["config"]["revision"] + 1, "revision_conflict")
            self._state = deepcopy(value)
            self.status = "awaiting_graph_readback"
        except Exception:
            self.invalidate()
            self.status = "storage_fault"
            raise

    async def _save(self, value):
        snapshot = deepcopy(value)
        try:
            await self.store.async_save(snapshot)
            require(await self.store.async_load() == snapshot, "storage_fault")
        except asyncio.CancelledError:
            self.invalidate()
            self._state = None
            raise
        except Exception as error:
            self.invalidate()
            self.status = "storage_fault"
            self._state = None
            # Save may have committed: never silently roll back or publish old state.
            raise GraphValidationError("storage_fault") from error
        self._state = snapshot

    def _capability(self, context, capability, received_at, retained):
        require(retained is False, 'retained_capability')
        require(isinstance(context, GraphValidationContext), "identity")
        require(context.qualification_digest == self.qualification_digest, "qualification")
        require(type(received_at) in (int, float) and math.isfinite(received_at), "stale_capability")
        now = self.clock()
        require(type(now) in (int, float) and math.isfinite(now)
                and 0 <= now - received_at < 10, "stale_capability")
        obj(capability, "api mode capabilities limits controller_id boot_id epoch adapter_id adapter_session_id grant_id grant_sequence config_revision config_digest mapping_revision mapping_digest boiler_output_enabled actuator_output_enabled")
        require(type(capability["api"]) is int and capability["api"] == 2
                and capability["mode"] == "shadow_graph", "unsupported_schema")
        require(capability["capabilities"] == sorted(CAPS), "unsupported_capability")
        require(type(capability["limits"]) is dict and capability["limits"] == LIMITS
                and all(type(v) is int for v in capability["limits"].values()), "test_layout_limit")
        for key in IDENTITY:
            require(type(capability[key]) is type(getattr(context, key))
                    and capability[key] == getattr(context, key), "identity")
        require(type(capability["config_revision"]) is int
                and capability["config_revision"] == context.current_revision, "revision_conflict")
        require(type(capability["mapping_revision"]) is int
                and capability["mapping_revision"] == context.mapping_revision
                and capability["mapping_digest"] == context.mapping_digest, "mapping_conflict")
        require(capability["boiler_output_enabled"] is False
                and capability["actuator_output_enabled"] is False, "outputs_not_locked")
        return deepcopy(capability)

    @staticmethod
    def _envelope(record, context, sequence):
        integer(sequence, 1, 4294967295)
        return dict(api=2, **{key: getattr(context, key) for key in IDENTITY},
                    config_revision=context.current_revision, binding_id="config",
                    sequence=sequence, expected_revision=context.current_revision,
                    config_digest=record["config_digest"], config=deepcopy(record["config"]))

    def _validate_record(self, record, context, sequence=1, *, restored=False):
        if restored:
            # Revalidate durable DATA, not a persisted grant/lease/session.
            context = replace(context, current_revision=record["config"]["revision"] - 1,
                              mapping_revision=record["mapping"]["mapping_revision"],
                              mapping_digest=digest(record["mapping"]))
        return validate_graph_shadow(canonical(self._envelope(record, context, sequence)),
                                     canonical(record["mapping"]), context)

    def _known_baseline(self, context, capability):
        accepted = self._state["accepted"]
        require(context.current_revision == (accepted["config"]["revision"] if accepted else 0)
                and capability["config_digest"] == (accepted["config_digest"] if accepted else "")
                and context.mapping_revision == (accepted["mapping"]["mapping_revision"] if accepted else 0)
                and context.mapping_digest == (digest(accepted["mapping"]) if accepted else ""),
                "readback_required")

    async def async_stage(self, raw, mapping_raw, context, capability, received_at, *, retained):
        """Validate whole candidate, persist mapping+config BEFORE possible send."""
        async with self._transaction():
            capability = self._capability(context, capability, received_at, retained)
            candidate = validate_graph_shadow(raw, mapping_raw, context)
            envelope, mapping = raw_document(raw), raw_document(mapping_raw)
            record = self._record(dict(config=envelope["config"],
                                       config_digest=candidate.config_digest, mapping=mapping))
            await self._load()
            self._known_baseline(context, capability)
            require(self._state["staged"] in (None, record), "pending_conflict")
            await self._save({**self._state, "staged": record})
            self.status = "graph_staged_not_applied"
            return candidate

    async def async_apply(self, send, context, capability, received_at, sequence, *, retained):
        """Explicit caller-triggered single send; an ACK alone is never applied."""
        async with self._transaction():
            generation = self._generation
            capability = self._capability(context, capability, received_at, retained)
            await self._load()
            record = self._state["staged"]
            require(record is not None, "nothing_staged")
            self._known_baseline(context, capability)
            self._validate_record(record, context, sequence)
            # Native Store readback must still match staged bytes before publish.
            require(await self.store.async_load() == self._state, "storage_fault")
            require(generation == self._generation, "session_changed")
            self._capability(context, capability, received_at, retained)
            raw = canonical(self._envelope(record, context, sequence))
            try:
                await send("ha/config", raw)
            except Exception:
                self.status = "graph_send_unconfirmed"
                raise
            require(generation == self._generation, "session_changed")
            self.status = "awaiting_graph_readback"
            return raw

    async def async_reconcile(self, config, context, capability, received_at, *, retained):
        """Fresh reconnect/readback matches a known immutable tuple or fails closed."""
        async with self._transaction():
            self.invalidate()
            generation = self._generation
            capability = self._capability(context, capability, received_at, retained)
            config = deepcopy(config)
            await self._load()
            require(isinstance(config, dict), "unsupported_schema")
            require(type(config.get("schema")) is int and config["schema"] == 2,
                    "unsupported_schema")
            require(config.get("revision") == context.current_revision
                    and digest(config) == capability["config_digest"], "revision_conflict")
            record = next((record for record in (self._state["accepted"], self._state["staged"])
                           if record is not None and record["config"] == config
                           and record["config_digest"] == capability["config_digest"]
                           and record["mapping"]["mapping_revision"] == context.mapping_revision
                           and digest(record["mapping"]) == context.mapping_digest), None)
            require(record is not None, "mapping_conflict")
            self._validate_record(record, context, restored=True)
            if record == self._state["staged"]:
                await self._save(dict(schema=1, accepted=record, staged=None))
            require(await self.store.async_load() == self._state, "storage_fault")
            require(generation == self._generation, "session_changed")
            self._capability(context, capability, received_at, retained)
            self.verified = self._state["staged"] is None
            self.status = "graph_shadow_readback_verified" if self.verified else "graph_staged_not_applied"
            return self.verified

    @property
    def state(self):
        return deepcopy(self._state)

    @property
    def outputs_enabled(self):
        # This is graph-shadow persistence only, never physical readiness.
        return False


def native_graph_journal(hass, entry, qualification_digest):
    """Explicit source-stage entry point; never starts transport or advertises api2.

    One native HA Store/lock per entry. No migration from the legacy api1 journal.
    Owner must supply a reviewed anchor, fresh capability/context and explicit send.
    """
    from time import monotonic
    from homeassistant.helpers.storage import Store
    from .const import DOMAIN

    data = hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})
    journal = data.get("graph_shadow_journal")
    if journal is not None:
        require(journal.qualification_digest == qualification_digest, "qualification")
        return journal
    journal = GraphShadowJournal(
        Store(hass, 1, f"open_thermostat.graph_shadow.{entry.entry_id}"),
        qualification_digest, monotonic)
    data["graph_shadow_journal"] = journal
    return journal
