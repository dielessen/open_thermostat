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
    async_call_later, async_track_entity_registry_updated_event,
    async_track_state_change_event, async_track_state_report_event,
)
from homeassistant.util import dt as dt_util

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
    async def async_close(self) -> None: ...

ReportProfile = Callable[[Any, str], QualifiedReport | None]

class ShadowRuntime:
    def __init__(self, hass: HomeAssistant, entry: Any, rooms: list[RoomBinding], *, graph_data_profile=None):
        if graph_data_profile is not None:
            from .graph_wire import GraphSourceProfile
            if not isinstance(graph_data_profile,GraphSourceProfile):
                raise ValueError("graph_profile_unsupported")
            graph_data_profile.validate()
        self.graph_data_profile=graph_data_profile
        self.hass, self.entry = hass, entry
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
        self.diagnostics: dict[str, str] = {}
        self._profiles: dict[str, ReportProfile] = {}
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

    def add_listener(self, listener: Callable) -> Callable:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def set_report_profile(self, room_id: str, profile: ReportProfile) -> None:
        """Trusted model-specific code only; no GUI freshness override."""
        if room_id not in self.rooms:
            raise ValueError("unknown room")
        self._profiles[room_id] = profile

    def attach_transport(self, transport: ShadowTransport) -> None:
        if self.graph_data_profile is not None:
            from .graph_wire import GraphShadowClient
            if not isinstance(transport,GraphShadowClient) or transport.profile!=self.graph_data_profile or transport.runtime is not self:
                raise HomeAssistantError("graph_profile_unsupported")
        if any(not room.shadow_wire_supported for room in self.rooms.values()) and self.graph_data_profile is None:
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
        if any(not room.shadow_wire_supported for room in self.rooms.values()) and self.graph_data_profile is None:
            raise HomeAssistantError("graph_room_contract_unavailable")
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
        for room in self.rooms.values():
            for ref in (room.temperature, *room.actuators, room.setpoint, room.window, room.presence):
                if ref and (entity_id := self._resolve(ref)):
                    ids.add(entity_id)
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
            if self._bench_fault:
                self._bench_fault("binding_changed")
            for room_id in self.rooms:
                self._withdraw(room_id, "binding_changed")
            self._bind_listeners()

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
                # Reuse the ORIGINAL temperature observation/deadline. A contact
                # update never creates a new physical temperature report.
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
        source_id = self._resolve(room.temperature)
        state = self.hass.states.get(source_id) if source_id else None
        value = temperature_c(state)
        if value is None:
            self._withdraw(room.room_id, "unavailable" if state is None or state.state == "unavailable" else "invalid")
            return
        profile = self._profiles.get(room.room_id)
        try:
            report = profile(state, event_kind) if profile else None
        except Exception:
            self._withdraw(room.room_id, "profile_error", value)
            return
        if report is None:
            self._withdraw(room.room_id, "unverified", value)
            return
        if not isinstance(report, QualifiedReport) or not isinstance(report.sample_key, str) or not report.sample_key or not isinstance(report.sampled_at, datetime) or report.sampled_at.tzinfo is None:
            self._withdraw(room.room_id, "unverified", value)
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
            if self._active and self._generation == generation:
                self._withdraw(room.room_id, "stale")

        self._expiries[room.room_id] = async_call_later(
            self.hass, (room.maximum_age_ms - age_ms) / 1000, expired)
        self._record(room.room_id, Observation(value, "qualified", math.ceil(age_ms), report.sample_key, self.hass.loop.time()))

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
                    elapsed = max(0, self.hass.loop.time() - observation.observed_monotonic)
                    age = observation.source_age_ms + math.ceil(elapsed * 1000)
                    if age >= self.rooms[room_id].maximum_age_ms:
                        observation = Observation(None, "stale")
                    else:
                        observation = replace(observation, source_age_ms=age,
                                              observed_monotonic=self.hass.loop.time())
                await self._transport.async_observation(room_id, observation)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.diagnostics["transport"] = "observation_failed"
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

    async def async_comfort(self,room_id,mode,*,temperature=None,duration_ms=None,vacation_until_utc=0):
        if room_id not in self.rooms or not self.transport_ready or self.rooms[room_id].comfort is None:
            raise HomeAssistantError("Comfort transport unavailable")
        await self._transport.async_comfort(room_id,mode,temperature=temperature,
            duration_ms=duration_ms,vacation_until_utc=vacation_until_utc)

    def comfort_context(self,room):
        """Native HA logical observations, NOT physical readiness or source evidence.

        State age uses last_changed (not a cache report/poll). Unknown, future,
        stale or restored state cannot become known by being re-read.
        """
        result={}
        for ref,key,on,off in ((room.window,"window", "on","off"),
                              (room.presence,"presence","not_home","home")):
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
        self._listeners.clear()
