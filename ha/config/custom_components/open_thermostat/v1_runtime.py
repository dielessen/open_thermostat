"""Native HA shadow lifecycle. No MQTT topics or device calls are defined here."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from dataclasses import replace
import math
from typing import Any, Protocol

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later, async_track_entity_registry_updated_event, async_track_device_registry_updated_event,
    async_track_state_change_event, async_track_state_report_event,
)
from homeassistant.util import dt as dt_util

from .native_binding import native_binding_identity

from .comfort_sources import ContextReport, ContextSourceProfile, CONTEXT_MAX_AGE_MS

from .v1_model import (
    CONF_ENABLED, EntityReference, Observation, QualifiedReport,
    RoomBinding, RoomDecision, target_centi, temperature_c,
)

class ShadowTransport(Protocol):
    """Internal injection seam, NOT a negotiated wire/JSON schema."""
    @property
    def ready(self) -> bool: ...
    async def async_observation(self, room_id: str, observation: Observation) -> None: ...
    async def async_setpoint(self, room_id: str, centi_c: int) -> None: ...
    async def async_hvac_mode(self, room_id: str, mode: str) -> None: ...
    async def async_close(self) -> None: ...

ReportProfile = Callable[[Any, str], QualifiedReport | None]

class ShadowRuntime:
    def __init__(self, hass: HomeAssistant, entry: Any, rooms: list[RoomBinding], *, graph_data_profile=None, context_source_profiles=(), controller_policy_source_profile=None, graph_controller_source=None,native_plan_source=None, clock: Callable[[], float] | None = None):
        self.clock = clock if clock is not None else hass.loop.time
        self._measurement_clock_watermark = None
        self._measurement_clock_failed = False
        if graph_data_profile is not None:
            from .graph_wire import GraphSourceProfile
            if not isinstance(graph_data_profile,GraphSourceProfile):
                raise ValueError("graph_profile_unsupported")
            graph_data_profile.validate()
        if controller_policy_source_profile is not None:
            from .comfort_sources import ControllerPolicySourceProfile
            from .native_plan import NativeInstallationPolicy
            profile=controller_policy_source_profile
            if not isinstance(profile,(ControllerPolicySourceProfile,NativeInstallationPolicy)):
                raise ValueError("controller_policy_profile_invalid")
            profile.validate()
            if (graph_data_profile is not None or profile.entry_unique_id!=entry.unique_id
                    or profile.adapter_id!=entry.options.get("adapter_id",entry.data.get("adapter_id"))):
                raise ValueError("controller_policy_profile_binding")
        if graph_controller_source is not None:
            from .graph_control_source import GraphControllerEntrySource
            from .topology_control_source import TopologyControllerEntrySource
            if not isinstance(graph_controller_source,(GraphControllerEntrySource,TopologyControllerEntrySource)):
                raise ValueError("graph_control_source_invalid")
            graph_controller_source.validate()
            if (graph_data_profile is not None or controller_policy_source_profile!=graph_controller_source.controller
                    or graph_controller_source.controller.entry_unique_id!=entry.unique_id
                    or len(rooms)!=graph_controller_source.room_count or not all(graph_controller_source.supports_room(room) for room in rooms)):
                raise ValueError("graph_control_source_binding")
        from .native_plan import NativePlanSource
        if native_plan_source is not None:
            if (type(native_plan_source) is not NativePlanSource or graph_data_profile is not None
                or graph_controller_source is not None or controller_policy_source_profile!=native_plan_source.policy
                or len(rooms)!=native_plan_source.room_count or not all(native_plan_source.supports_room(room) for room in rooms)):
                raise ValueError("native_plan_source_binding")
            native_plan_source.validate_native(hass,entry)
        self.native_plan_source=native_plan_source
        self.graph_controller_source=graph_controller_source
        self.controller_policy_source_profile=controller_policy_source_profile
        self.graph_data_profile=graph_data_profile
        self.hass, self.entry = hass, entry
        self.original_temperature_reports = None
        self.original_tv02_reports = None
        self.rooms = {room.room_id: room for room in rooms}
        if len(self.rooms) != len(rooms) or len(rooms) > 8:
            raise ValueError("duplicate/excess rooms")
        seen: set[tuple] = set()
        for room in rooms:
            for actuator in room.actuators:
                if actuator.identity() in seen:
                    raise ValueError("actuator assigned to multiple rooms")
                seen.add(actuator.identity())
        self.observations = {room.room_id: Observation(None, "disabled") for room in rooms}
        self.decisions: dict[str, RoomDecision] = {}
        self._comfort_context_cache = {}
        # At most two SOURCE pins per room. Never loaded from entry/options/Store.
        if type(context_source_profiles) is not tuple or len(context_source_profiles)>16:
            raise ValueError("context_profile_invalid")
        self._context_source_profiles = {}
        self._context_source_values = {}
        self._context_source_watermarks = {}
        for profile in context_source_profiles:
            if not isinstance(profile,ContextSourceProfile):
                raise ValueError("context_profile_invalid")
            profile.validate()
            room=self.rooms.get(profile.room_id)
            ref=getattr(room,profile.kind,None)
            key=(profile.room_id,profile.kind)
            if (graph_data_profile is not None or profile.entry_unique_id!=entry.unique_id
                    or room is None or room.comfort is None or ref is None
                    or ref.identity()!=profile.identity or key in self._context_source_profiles):
                raise ValueError("context_profile_binding")
            self._context_source_profiles[key]=profile
        self.diagnostics: dict[str, str] = {}
        self._profiles: dict[str, ReportProfile] = {}
        self._profile_owners: dict[str, object] = {}
        self._profile_bindings: dict[str, tuple] = {}
        self._sample_keys: dict[str, str] = {}
        self._sample_times: dict[str, datetime] = {}
        self._subscriptions: list[Callable] = []
        self._expiries: dict[str, Callable] = {}
        self._listeners: set[Callable] = set()
        self._pending: dict[str, Observation] = {}
        self._task: asyncio.Task | None = None
        self._transport: ShadowTransport | None = None
        self._active = False
        self._generation = 0
        self._bench_owner = None
        self._bench_fault = None

    @property
    def enabled(self) -> bool:
        return self._active

    @property
    def transport_ready(self) -> bool:
        return self.graph_data_profile is None and self._active and self._transport is not None and self._transport.ready

    def room_control_supported(self,room_id):
        room=self.rooms.get(room_id)
        return room is not None and (room.shadow_wire_supported or
            (self.graph_controller_source is not None and self.graph_controller_source.supports_room(room))
            or (self.native_plan_source is not None and self.native_plan_source.supports_room(room)))

    def add_listener(self, listener: Callable) -> Callable:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _measurement_now(self):
        """One clock read per boundary; failure retires this runtime's evidence.

        Registering a new report callback cannot repair a broken clock owner.
        Milliseconds stay within the exact integer range of the wire/UI domain.
        """
        if self._measurement_clock_failed:
            return None
        try:
            now = self.clock()
            valid = (type(now) in (int, float) and 0 <= now <= (2**53-1)/1000
                     and math.isfinite(now))
        except Exception:
            valid = False
        if (not valid or self._measurement_clock_watermark is not None
                and now < self._measurement_clock_watermark):
            self._measurement_clock_failed = True
            for room_id in self.rooms:
                current = self.observations.get(room_id)
                if (current is not None and current.quality == "qualified"
                        and room_id != self._bench_owner):
                    self._withdraw(room_id, "invalid")
            return None
        self._measurement_clock_watermark = now
        return now

    def measurement_status(self, room_id: str) -> dict:
        """Current measurement evidence only; no grants, identities or sample keys.

        Reading this view never renews a report or its original expiry.
        """
        room = self.rooms.get(room_id)
        observation = self.observations.get(room_id)
        configured = room_id in self._profiles
        quality = observation.quality if observation is not None else "disabled"
        age = None
        if (observation is not None and quality == "qualified"
                and observation.observed_monotonic is not None
                and observation.source_age_ms is not None):
            now = self._measurement_now()
            if now is None or now < observation.observed_monotonic:
                quality = "invalid"
            else:
                age = observation.source_age_ms + math.ceil(
                    (now - observation.observed_monotonic) * 1000)
                if room is None or age >= room.maximum_age_ms:
                    quality = "stale"
        if configured and not self._report_binding_matches(room):
            quality, age = "binding_changed", None
        allowed = {"disabled", "unverified", "qualified", "stale", "unavailable",
                   "invalid", "profile_error", "out_of_order", "binding_changed"}
        if quality not in allowed:
            quality = "unverified"
        if not self._active:
            status = "inactive"
        elif not configured:
            status = "profile_missing"
        elif quality == "qualified" and age is not None:
            status = "qualified"
        else:
            status = quality if quality != "qualified" else "unverified"
        result = {"status": status, "report_profile_configured": configured,
                  "sample_age_ms": age, "usable": status == "qualified"}
        if self.original_temperature_reports is not None:
            original = self.original_temperature_reports.status(room_id)
            if original is not None:
                result["original_report"] = original
        return result

    def actuator_report_status(self, room_id: str) -> dict:
        """Original receive diagnostics only, separate from control readiness."""
        if self.original_tv02_reports is None:
            return {}
        return self.original_tv02_reports.status(room_id)

    def set_report_profile(self, room_id: str, profile: ReportProfile) -> Callable[[], bool]:
        """Attach a trusted observer; dispose with the returned scoped revoker.

        Replacement/removal withdraws the previous qualification immediately.
        Replay watermarks survive owner changes. Neither registration nor its
        cleanup supplies a sample, renews age or qualifies a physical source.
        """
        if room_id not in self.rooms:
            raise ValueError("unknown room")
        if not callable(profile):
            raise ValueError("report profile must be callable")
        binding = native_binding_identity(self.hass, self._resolve(self.rooms[room_id].temperature))
        if binding is None:
            raise ValueError("native report binding unavailable")
        owner = object()
        self._profile_bindings[room_id] = binding
        self._profiles[room_id] = profile
        self._profile_owners[room_id] = owner
        self._withdraw(room_id, "unverified")

        @callback
        def revoke() -> bool:
            # An old unsubscribe/close must not detach a replacement, including
            # a new registration of the SAME callable or a post-restart owner.
            if self._profile_owners.get(room_id) is not owner:
                return False
            self._profiles.pop(room_id, None)
            self._profile_owners.pop(room_id, None)
            self._profile_bindings.pop(room_id, None)
            self._withdraw(room_id, "unverified")
            return True

        return revoke

    def _report_binding_matches(self, room: RoomBinding | None) -> bool:
        if room is None:
            return False
        captured = self._profile_bindings.get(room.room_id)
        return captured is not None and captured == native_binding_identity(
            self.hass, self._resolve(room.temperature))

    def _drop_report_binding(self, room_id: str) -> None:
        self._profiles.pop(room_id, None)
        self._profile_owners.pop(room_id, None)
        self._profile_bindings.pop(room_id, None)
        self._withdraw(room_id, "binding_changed")

    def attach_transport(self, transport: ShadowTransport) -> None:
        if self.controller_policy_source_profile is not None:
            from .v1_wire import ShadowClient
            if (not isinstance(transport,ShadowClient) or transport.runtime is not self
                    or transport.controller_policy!=self.controller_policy_source_profile):
                raise HomeAssistantError("controller_policy_transport_mismatch")
        if self.graph_data_profile is not None:
            from .graph_wire import GraphShadowClient
            if not isinstance(transport,GraphShadowClient) or transport.profile!=self.graph_data_profile or transport.runtime is not self:
                raise HomeAssistantError("graph_profile_unsupported")
        if any(not self.room_control_supported(room.room_id) for room in self.rooms.values()) and self.graph_data_profile is None:
            raise HomeAssistantError("graph_room_contract_unavailable")
        if self._transport is not None:
            raise ValueError("one transport owner only")
        self._transport = transport

    def _resolve(self, ref: EntityReference) -> str | None:
        if ref.platform is not None and ref.unique_id is not None:
            return er.async_get(self.hass).async_get_entity_id(
                ref.entity_id.split(".", 1)[0], ref.platform, ref.unique_id)
        return ref.entity_id

    def resolved(self, ref: EntityReference) -> str | None:
        return self._resolve(ref)

    async def async_start(self) -> None:
        if self._active:
            raise ValueError("runtime already started")
        if not self.entry.options.get(CONF_ENABLED, False):
            return
        if any(not self.room_control_supported(room.room_id) for room in self.rooms.values()) and self.graph_data_profile is None:
            raise HomeAssistantError("graph_room_contract_unavailable")
        self.invalidate_context_sources()
        self._active = True
        self._generation += 1
        if self.graph_data_profile is not None:
            # DATA-only: no source listeners, source timers, temperature reports,
            # room decision or active transport capability is established.
            return
        self._bind_listeners()
        # Restored/state-cache reads are never promoted to qualified samples.
        for room in self.rooms.values():
            entity_id = self._resolve(room.temperature)
            state = self.hass.states.get(entity_id) if entity_id else None
            self._record(room.room_id, Observation(temperature_c(state), "unverified"))

    def _bind_listeners(self) -> None:
        for unsub in self._subscriptions:
            unsub()
        self._subscriptions.clear()
        ids: set[str] = set()
        device_ids: set[str] = set()
        for room in self.rooms.values():
            for ref in (room.temperature, *room.actuators, room.setpoint, room.window, room.presence):
                if ref and (entity_id := self._resolve(ref)):
                    ids.add(entity_id)
            for ref in (room.temperature, *room.actuators):
                source_id = self._resolve(ref)
                source = er.async_get(self.hass).async_get(source_id) if source_id else None
                if source and source.device_id:
                    device_ids.add(source.device_id)
        if not ids or not self._active:
            return
        generation = self._generation

        @callback
        def changed(event):
            if self._active and self._generation == generation:
                self._source_event(event.data["entity_id"], "changed")

        @callback
        def reported(event):
            if self._active and self._generation == generation:
                self._source_event(event.data["entity_id"], "reported")

        @callback
        def registry_changed(event):
            if not self._active or self._generation != generation:
                return
            self._recheck_original_reports()
            if self._bench_fault:
                self._bench_fault("binding_changed")
            self.invalidate_context_sources()
            for room_id, room in self.rooms.items():
                if room_id in self._profiles and not self._report_binding_matches(room):
                    self._drop_report_binding(room_id)
                else:
                    self._withdraw(room_id, "binding_changed")
            self._bind_listeners()

        @callback
        def device_changed(event):
            if not self._active or self._generation != generation:
                return
            self._recheck_original_reports()
            for room_id, room in self.rooms.items():
                if room_id in self._profiles and not self._report_binding_matches(room):
                    self._drop_report_binding(room_id)
            self._bind_listeners()

        if device_ids:
            self._subscriptions.append(async_track_device_registry_updated_event(
                self.hass, device_ids, device_changed))
        self._subscriptions.extend([
            async_track_state_change_event(self.hass, ids, changed),
            async_track_state_report_event(self.hass, ids, reported),
            async_track_entity_registry_updated_event(self.hass, ids, registry_changed),
        ])

    @callback
    def _source_event(self, entity_id: str, event_kind: str) -> None:
        for room in self.rooms.values():
            if self._bench_owner == room.room_id:
                continue
            if self._resolve(room.temperature) == entity_id:
                self._observe(room, event_kind)
            elif any(ref and self._resolve(ref)==entity_id for ref in (room.window,room.presence)):
                # NEW logical proof only on the existing native event path.
                # Reuse ORIGINAL temperature observation/deadline, never renew it.
                for kind in ("window","presence"):
                    ref=getattr(room,kind)
                    if ref and self._resolve(ref)==entity_id:
                        self._observe_context_source(room,kind,event_kind)
                self._record(room.room_id,self.observations[room.room_id])
            elif room.setpoint and self._resolve(room.setpoint) == entity_id:
                # Knob origin/echo qualification awaits a concrete profile.
                self.diagnostics[room.room_id] = "physical_setpoint_unqualified"
                self._notify()
            elif any(self._resolve(ref) == entity_id for ref in room.actuators):
                self.diagnostics[room.room_id] = "profile_C_unverified"
                self._notify()

    @callback
    def _observe(self, room: RoomBinding, event_kind: str) -> None:
        if self._measurement_now() is None:
            self._withdraw(room.room_id, "invalid")
            return
        source_id = self._resolve(room.temperature)
        state = self.hass.states.get(source_id) if source_id else None
        value = temperature_c(state)
        if value is None:
            self._withdraw(room.room_id, "unavailable" if state is None or state.state == "unavailable" else "invalid")
            return
        profile = self._profiles.get(room.room_id)
        profile_owner = self._profile_owners.get(room.room_id)
        if profile is not None and not self._report_binding_matches(room):
            self._drop_report_binding(room.room_id)
            return
        try:
            report = profile(state, event_kind) if profile else None
        except Exception:
            if self._profile_owners.get(room.room_id) is profile_owner:
                if not self._report_binding_matches(room):
                    self._drop_report_binding(room.room_id)
                else:
                    self._withdraw(room.room_id, "profile_error", value)
            return
        if self._profile_owners.get(room.room_id) is not profile_owner:
            return  # callback disposed/replaced itself; old result has no owner
        if profile is not None and not self._report_binding_matches(room):
            self._drop_report_binding(room.room_id)
            return
        if report is None:
            self._withdraw(room.room_id, "unverified", value)
            return
        if not isinstance(report, QualifiedReport) or not isinstance(report.sample_key, str) or not report.sample_key or not isinstance(report.sampled_at, datetime) or report.sampled_at.tzinfo is None:
            self._withdraw(room.room_id, "unverified", value)
            return
        observed_at = self._measurement_now()
        if observed_at is None:
            self._withdraw(room.room_id, "invalid")
            return
        now = dt_util.utcnow()
        age_ms = (now - report.sampled_at).total_seconds() * 1000
        if age_ms < 0 or age_ms >= room.maximum_age_ms:
            self._withdraw(room.room_id, "stale", value)
            return
        if self._sample_keys.get(room.room_id) == report.sample_key:
            # A repeat/cache rewrite cannot restart the original expiry.
            return
        if report.sampled_at <= self._sample_times.get(room.room_id, datetime.min.replace(tzinfo=now.tzinfo)):
            self._withdraw(room.room_id, "out_of_order", value)
            return
        self._sample_keys[room.room_id] = report.sample_key
        self._sample_times[room.room_id] = report.sampled_at
        if old := self._expiries.pop(room.room_id, None):
            old()
        generation = self._generation

        @callback
        def expired(_):
            current = self.observations.get(room.room_id)
            if (self._active and self._generation == generation
                    and self._profile_owners.get(room.room_id) is profile_owner
                    and current is not None and current.quality == "qualified"
                    and current.source_key == report.sample_key):
                self._withdraw(room.room_id, "stale")

        self._expiries[room.room_id] = async_call_later(
            self.hass, (room.maximum_age_ms - age_ms) / 1000, expired)
        self._record(room.room_id, Observation(value, "qualified", math.ceil(age_ms), report.sample_key, observed_at))

    @callback
    def _withdraw(self, room_id: str, quality: str, value: float | None = None) -> None:
        if old := self._expiries.pop(room_id, None):
            old()
        self._record(room_id, Observation(value, quality))

    @callback
    def _record(self, room_id: str, observation: Observation) -> None:
        if self._bench_owner == room_id:
            return
        self.observations[room_id] = observation
        self._notify()
        if self.transport_ready:
            self._pending[room_id] = observation
            if self._task is None or self._task.done():
                self._task = self.hass.async_create_task(self._flush(self._generation))

    async def _flush(self, generation: int) -> None:
        try:
            while self._pending and self._active and self._generation == generation and self.transport_ready:
                room_id = next(iter(self._pending))
                observation = self._pending.pop(room_id)
                if self._bench_owner == room_id:
                    continue
                if observation.quality == "qualified":
                    if not self._report_binding_matches(self.rooms.get(room_id)):
                        self._drop_report_binding(room_id)
                        continue
                    now = self._measurement_now()
                    if now is None or now < observation.observed_monotonic:
                        observation = Observation(None, "invalid")
                    else:
                        age = observation.source_age_ms + math.ceil(
                            (now - observation.observed_monotonic) * 1000)
                        if age >= self.rooms[room_id].maximum_age_ms:
                            observation = Observation(None, "stale")
                        else:
                            observation = replace(observation, source_age_ms=age,
                                                  observed_monotonic=now)
                await self._transport.async_observation(room_id, observation)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.diagnostics["transport"] = "observation_failed"
            self._notify()

    def _recheck_original_reports(self) -> None:
        """Registry changes fence both optional observers, never the controller."""
        changed = False
        for owner in (self.original_temperature_reports, self.original_tv02_reports):
            if owner is None:
                continue
            try:
                changed = owner.recheck() or changed
            except Exception:
                owner.invalidate("unavailable")
                changed = True
        if changed:
            self._notify()

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def async_set_temperature(self, room_id: str, celsius: float) -> None:
        if room_id not in self.rooms or not self.transport_ready:
            raise HomeAssistantError("Shadow transport is disabled or not ready")
        try:
            target = target_centi(celsius)
            room = self.rooms[room_id]
            if not room.minimum_target_centi_c <= target <= room.maximum_target_centi_c:
                raise ValueError("Target temperature is outside room target limits")
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self._transport.async_setpoint(room_id, target)
        # Only admitted firmware state, never this request/ack, changes the target.

    async def async_hvac_mode(self, room_id: str, mode: str) -> None:
        if mode not in ("heat", "off"):
            raise HomeAssistantError("Unsupported shadow HVAC mode")
        if not self.room_control_supported(room_id) or not self.transport_ready:
            raise HomeAssistantError("Shadow transport is disabled or not ready")
        command = getattr(self._transport, "async_hvac_mode", None)
        if command is None:
            raise HomeAssistantError("Shadow HVAC mode transport unavailable")
        await command(room_id, mode)
        # Only admitted firmware state confirms the choice. No local latch/retry.

    async def async_comfort(self,room_id,mode,*,temperature=None,duration_ms=None,vacation_until_utc=0):
        if room_id not in self.rooms or not self.transport_ready or self.rooms[room_id].comfort is None:
            raise HomeAssistantError("Comfort transport unavailable")
        await self._transport.async_comfort(room_id,mode,temperature=temperature,
            duration_ms=duration_ms,vacation_until_utc=vacation_until_utc)

    def invalidate_context_sources(self):
        """Owner/rebind/stop drops usable proofs; bounded replay watermarks survive."""
        self._context_source_values.clear()
        for key,prior in self._context_source_watermarks.items():
            self._context_source_watermarks[key]=(*prior[:3],None)

    def _observe_context_source(self,room,kind,event_kind):
        key=(room.room_id,kind)
        profile=self._context_source_profiles.get(key)
        if profile is None:
            return
        state_id=self._resolve(getattr(room,kind))
        state=self.hass.states.get(state_id) if state_id else None
        old=self._context_source_values.pop(key,None)
        prior=self._context_source_watermarks.get(key)
        if prior:
            self._context_source_watermarks[key]=(*prior[:3],None)
        allowed=("on","off") if kind=="window" else ("not_home","home")
        if (not self._active or state is None or state.attributes.get("restored")
                or state.state not in allowed or event_kind not in ("changed","reported")):
            return
        # Registry rename can preserve stable identity; removal/replacement cannot.
        row=er.async_get(self.hass).async_get(state_id)
        if row is None or (row.domain,row.platform,row.unique_id)!=profile.identity:
            return
        try:
            report=profile.report(state,event_kind)
            if (not isinstance(report,ContextReport) or type(report.sample_key) is not str
                    or not 1<=len(report.sample_key)<=128
                    or not isinstance(report.sampled_at,datetime)
                    or report.sampled_at.utcoffset() is None):
                return
            age=(dt_util.utcnow()-report.sampled_at).total_seconds()*1000
            if not math.isfinite(age) or not 0<=age<CONTEXT_MAX_AGE_MS:
                return
        except Exception:
            # Never expose exception text, report IDs, payloads or private source labels.
            self.diagnostics[room.room_id]="context_profile_error"
            return
        value=state.state==allowed[0]
        if prior is not None:
            if report.sample_key==prior[0]:
                # Identical report cannot refresh original age; changed replay loses proof.
                if report.sampled_at==prior[1] and value==prior[2]:
                    if old is not None and old is prior[3]:
                        self._context_source_values[key]=old
                        self._context_source_watermarks[key]=prior
                return
            if report.sampled_at<=prior[1]:
                return
        proof=(math.ceil(age),self.hass.loop.time(),value)
        self._context_source_values[key]=proof
        self._context_source_watermarks[key]=(report.sample_key,report.sampled_at,value,proof)

    def _context_source_value(self,key):
        proof=self._context_source_values.get(key)
        if not self._active or proof is None:
            return None,86400000
        elapsed=self.hass.loop.time()-proof[1]
        age=proof[0]+math.ceil(elapsed*1000)
        if not 0<=elapsed or not 0<=age<CONTEXT_MAX_AGE_MS:
            self._context_source_values.pop(key,None)
            # Invalidated proof cannot be revived by a replay or clock recovery.
            prior=self._context_source_watermarks.get(key)
            if prior:
                self._context_source_watermarks[key]=(*prior[:3],None)
            return None,86400000
        return proof[2],age

    def context_source_status(self,room_id):
        """Whitelisted native UI/diagnostics; no identities/tokens/report payloads."""
        room=self.rooms[room_id]
        result={}
        for kind in ("window","presence"):
            key=(room_id,kind)
            if key in self._context_source_profiles:
                value,_=self._context_source_value(key)
                result[kind]="qualified_logical_report" if value is not None else "source_report_unknown"
            else:
                result[kind]="conservative_state_age" if getattr(room,kind) else "not_configured"
        return result

    def comfort_context(self,room):
        """Native HA logical observations, NOT physical readiness or source evidence.

        Source-selected proof is updated ONLY by native source events, never here.
        Unselected fallback keeps conservative last_changed120s unchanged.
        Unknown, future, stale or restored state cannot become known by re-reading.
        """
        result={}
        for ref,key,on,off in ((room.window,"window", "on","off"),
                              (room.presence,"presence","not_home","home")):
            cache_key=(room.room_id,key)
            if cache_key in self._context_source_profiles:
                value,age=self._context_source_value(cache_key)
                result["window_open" if key=="window" else "presence_away"]=value
                result[key+"_age_ms"]=age
                continue
            entity_id=self._resolve(ref) if ref else None
            state=self.hass.states.get(entity_id) if entity_id else None
            token=(entity_id,state.last_changed) if state else None
            cache_key=(room.room_id,key)
            prior=self._comfort_context_cache.get(cache_key)
            if prior is None or prior[0]!=token:
                age=math.ceil((dt_util.utcnow()-state.last_changed).total_seconds()*1000) if state else 86400000
                value=None
                if state and not state.attributes.get("restored") and 0<=age<120000:
                    if state.state==on:value=True
                    elif state.state==off:value=False
                    # Other named zones, unknown/unavailable and future/restored are unknown.
                # Older timestamps cannot renew a context after out-of-order input.
                if prior and token and prior[0] and token[1]<=prior[0][1]:
                    value=None;age=86400000
                prior=(token,age,self.hass.loop.time(),value)
                self._comfort_context_cache[cache_key]=prior
            elapsed=self.hass.loop.time()-prior[2]
            age=prior[1]+math.ceil(elapsed*1000)
            value=prior[3] if 0<=elapsed and 0<=age<120000 else None
            result["window_open" if key=="window" else "presence_away"]=value
            result[key+"_age_ms"]=age if 0<=age<=86400000 else 86400000
        return result

    @callback
    def apply_confirmed_state(self, room_id: str, decision: RoomDecision) -> None:
        """Trusted future wire adapter calls only after complete admission."""
        if room_id not in self.rooms or not self.transport_ready:
            raise ValueError("no active admitted shadow transport")
        self.decisions[room_id] = decision
        self._notify()
        # Shadow mode NEVER executes an actuator action.

    async def async_stop(self) -> None:
        self.invalidate_context_sources()
        self._active = False
        self._generation += 1
        for unsub in self._subscriptions:
            unsub()
        self._subscriptions.clear()
        for cancel in self._expiries.values():
            cancel()
        self._expiries.clear()
        self._pending.clear()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._transport:
            await self._transport.async_close()
        self._transport = None
        self.decisions.clear()
        self._profiles.clear()
        self._profile_owners.clear()
        self._profile_bindings.clear()
        self._listeners.clear()
