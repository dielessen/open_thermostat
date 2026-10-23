"""Native developer actions for ONE finite shadow source bench. No device writes."""
from __future__ import annotations
import asyncio
import copy
import math
import secrets
import time
import voluptuous as vol
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.event import async_call_later
from .const import DOMAIN
from .v1_model import MODE_SHADOW, integration_mode
from .v1_wire import canonical, digest
from .v1_bench_source import BenchSource
from .v1_bench_mqtt import NativeBenchListener, async_forward_shadow

KEY = DOMAIN + "_finite_source_benches"
ACTIONS = ("source_bench_start", "source_bench_stop", "source_bench_status")
START = vol.Schema({
    vol.Required("entry_id"): str, vol.Required("baseline"): dict,
    vol.Required("discovery"): dict, vol.Required("ieee"): str,
    vol.Required("discovery_topic"): str, vol.Required("ha_status_topic"): str,
    vol.Required("transaction"): str,
    vol.Optional("duration_s", default=300): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
})
ENTRY = vol.Schema({vol.Required("entry_id"): str})

def exact_topic(value):
    return (isinstance(value, str) and 0 < len(value) <= 256
            and not any(c in value for c in ("+", "#", "\0")))

class Bench:
    def __init__(self, hass, entry_id):
        self.hass, self.entry_id = hass, entry_id
        self.lock = asyncio.Lock()
        self.phase, self.reason = "inactive", "not_started"
        self.listener = self.runtime = self.connection = self.client = None
        self.original = self.timer = self.sample_timer = None
        self.worker = self.stop_task = None
        self.latest = None
        self.wake = asyncio.Event()
        self.generation = 0
        self.samples = 0
        self.mapping_digest = None
        self.closed = True
        self.restored = None
        self.unlisten = None

    def status(self):
        return {"entry_id": self.entry_id, "phase": self.phase, "reason": self.reason,
                "gate_phase": self.listener.gate.phase if self.listener else None,
                "gate_reason": self.listener.gate.reason if self.listener else None,
                "observations_forwarded": self.samples, "mapping_digest": self.mapping_digest,
                "normal_mapping_restored": self.restored,
                "boiler_output_enabled": False, "actuator_output_enabled": False,
                "expires_monotonic": self.deadline if hasattr(self, "deadline") else None}

    @callback
    def request_stop(self, reason):
        if self.closed:
            return
        self.reason = reason
        if self.listener:
            self.listener.gate.stop(reason)
        # This callback schedules native lifecycle work, never a device action.
        if self.stop_task is None or self.stop_task.done():
            self.stop_task = self.hass.async_create_task(self.stop(reason))

    async def reconfigure(self, desired, mapping):
        self.client.desired = copy.deepcopy(desired)
        self.client.mapping = copy.deepcopy(mapping)
        self.client.verified = False
        if self.client.session and self.client.clock() < self.client.grant_until:
            await self.client.message("ha/snapshot_request", "snapshot", {})
        async with asyncio.timeout(30):
            while True:
                record = self.client.journal.get("accepted")
                if (self.client.ready and record and self.client.journal["staged"] is None
                        and record["mapping"] == mapping
                        and record["config"]["zones"] == desired):
                    return
                if self.client.closed:
                    raise HomeAssistantError("Shadow transport closed during config admission")
                await asyncio.sleep(0.02)

    async def start(self, data):
        async with self.lock:
            if self.phase == "blocked":
                raise HomeAssistantError("Previous restore unconfirmed; reload entry before another bench")
            if not self.closed or self.phase == "stopping":
                raise HomeAssistantError("Bench already active")
            state = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})
            runtime, connection = state.get("v1_runtime"), state.get("v1_connection")
            if (runtime is None or connection is None or not runtime.enabled
                    or len(runtime.rooms) != 1 or not connection.client.ready):
                raise HomeAssistantError("Enabled, admitted one-zone shadow entry required")
            # This developer bench replaces a schema1 mapping. It cannot
            # migrate an admitted SOURCE-owned plan/profile or its journal.
            # Refuse before taking ownership, changing desired DATA or timers.
            if any(getattr(runtime, name, None) is not None for name in (
                    "native_plan_source", "graph_controller_source", "graph_data_profile",
                    "controller_policy_source_profile")):
                raise HomeAssistantError("Finite source bench does not support source-owned control plans")
            if runtime._bench_owner is not None or connection.bench is not None:
                raise HomeAssistantError("Exclusive source owner already held")
            if len(canonical(data)) > 32768:
                raise HomeAssistantError("Bench metadata exceeds bounded input")
            room = next(iter(runtime.rooms.values()))
            if (len(connection.client.desired) != 1 or connection.client.desired[0]["zone_id"] != room.room_id):
                raise HomeAssistantError("Exactly one matching firmware zone required")
            if any(other is not self and not other.closed
                   for other in self.hass.data.get(KEY, {}).values()):
                raise HomeAssistantError("Only one finite source bench may own this HA instance")
            discovery = data["discovery"]
            source = discovery.get("state_topic")
            prefix = source.rsplit("/", 1)[0] if exact_topic(source) else ""
            topic = data["discovery_topic"]
            if (not prefix or not exact_topic(topic) or not exact_topic(data["ha_status_topic"])
                    or topic == source or not topic.endswith("/config")):
                raise HomeAssistantError("Exact source/Discovery/status topics required")
            registry = er.async_get(self.hass).async_get(runtime.resolved(room.temperature))
            if (registry is None or registry.platform != "mqtt"
                    or registry.unique_id != discovery.get("unique_id")
                    or not discovery["unique_id"].startswith(data["ieee"] + "_")):
                raise HomeAssistantError("Discovery does not match selected native MQTT temperature binding")
            baseline = data["baseline"]
            if (set(baseline) != {"device_options", "devices", "advanced"}
                    or set(baseline["devices"]) != {data["ieee"]}
                    or not set(baseline["advanced"]) <= {"cache_state", "last_seen", "cache_state_send_on_startup"}):
                raise HomeAssistantError("Only scoped selected-device baseline metadata is accepted")
            gate = BenchSource(data["baseline"], data["ieee"], source, data["transaction"],
                               discovery=discovery, duration_s=data["duration_s"],
                               max_age_ms=min(room.maximum_age_ms, 120000))
            self.runtime, self.connection, self.client = runtime, connection, connection.client
            self.room_id = room.room_id
            self.original = (copy.deepcopy(self.client.desired), copy.deepcopy(self.client.mapping))
            self.closed, self.phase, self.reason = False, "preparing", "durable_mapping_admission"
            self.restored, self.samples, self.latest = None, 0, None
            self.generation += 1
            generation = self.generation
            self.deadline = self.hass.loop.time() + data["duration_s"]
            runtime._bench_owner, runtime._bench_fault = self.room_id, self.request_stop
            connection.bench = self
            runtime._pending.pop(self.room_id, None)
            if runtime._task and not runtime._task.done():
                runtime._task.cancel()
                await asyncio.gather(runtime._task, return_exceptions=True)
            # Remove outstanding generic sample retries before reusing this channel.
            for key in list(self.client.pending):
                if key[1] == "s_" + self.room_id:
                    self.client.pending.pop(key)
            desired = copy.deepcopy(self.original[0])
            desired[0]["report_evidence"] = "validated_integration_report"
            mapping = {"rooms": [room.as_dict()], "source_policy": "finite-native-source-bench/v1",
                       "actuation": "disabled-shadow", "bench_id": secrets.token_hex(12),
                       "source_metadata_digest": digest(data)}
            self.mapping_digest = digest(mapping)
            @callback
            def expire(_):
                self.timer = None
                self.request_stop("finite_bench_expired")
            self.timer = async_call_later(self.hass, data["duration_s"], expire)
            try:
                await self.reconfigure(desired, mapping)
                if self.hass.loop.time() >= self.deadline:
                    raise HomeAssistantError("Bench expired during config admission")
                self.fw_identity = (self.client.identity, self.client.session["adapter_session_id"])
                self.worker = self.hass.async_create_background_task(
                    self.forward(generation), "OpenThermostat finite bench observations")
                self.listener = NativeBenchListener(
                    self.hass, gate, prefix, data["ha_status_topic"], topic,
                    self.sample, self.request_stop)
                await self.listener.async_start(True)
                self.phase, self.reason = "listening", "awaiting_native_cutover_evidence"
                @callback
                def transport_changed():
                    if not self.closed and self.phase in ("listening", "observing") and not self.client.ready:
                        self.request_stop("firmware_admission_lost")
                self.unlisten = runtime.add_listener(transport_changed)
                return {**self.status(), "options_request_proposal": gate.request,
                        "options_rollback_proposal": gate.rollback}
            except BaseException:
                # lock is held: use internal cleanup, not recursive stop().
                await self._stop("start_failed")
                raise

    @callback
    def sample(self, sample):
        if self.closed or self.hass.loop.time() >= self.deadline:
            return
        self.latest = sample
        self.wake.set()  # at most one coalesced sample, not an unbounded task queue

    async def forward(self, generation):
        try:
            while not self.closed and self.generation == generation:
                await self.wake.wait()
                self.wake.clear()
                sample, self.latest = self.latest, None
                await async_forward_shadow(self.client, self.room_id, sample, self.mapping_digest)
                self.samples += 1
                if self.sample_timer:
                    self.sample_timer()
                if sample:
                    age = sample["source_sample_age_ms"] + math.ceil(
                        max(0, self.hass.loop.time()-sample["received_monotonic"])*1000)
                    maximum = min(self.runtime.rooms[self.room_id].maximum_age_ms, 120000)
                    @callback
                    def stale(_):
                        self.sample_timer = None
                        if not self.closed:
                            self.latest = None
                            self.wake.set()
                    self.sample_timer = async_call_later(self.hass, max(0, maximum-age)/1000, stale)
                self.phase, self.reason = "observing", "validated_shadow_report_only"
        except asyncio.CancelledError:
            raise
        except Exception:
            self.request_stop("source_forward_failed")

    async def stop(self, reason="developer_stop"):
        async with self.lock:
            await self._stop(reason)
            return self.status()

    async def _stop(self, reason):
        if self.closed:
            return
        self.closed, self.phase, self.reason = True, "stopping", reason
        self.generation += 1
        if self.unlisten:
            self.unlisten()
            self.unlisten = None
        for name in ("timer", "sample_timer"):
            if cancel := getattr(self, name):
                cancel()
                setattr(self, name, None)
        if self.worker and self.worker is not asyncio.current_task():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        if self.listener:
            await self.listener.async_close()
        self.latest = None
        self.wake.clear()
        try:
            if self.client.ready:
                await async_forward_shadow(self.client, self.room_id, None, self.mapping_digest)
            await self.reconfigure(*self.original)
            self.restored = True
        except Exception:
            self.restored = False
            # Do not release the generic writer into an unproven mapping.
        self.connection.bench = None
        if self.restored:
            self.runtime._bench_owner = self.runtime._bench_fault = None
        self.phase = "stopped" if self.restored else "blocked"
        if not self.restored:
            self.reason += ":normal_mapping_restore_unconfirmed_reload_required"

def async_register_entry(hass, entry):
    """Only invoked by explicit shadow-mode entry setup; actions never auto-start."""
    if integration_mode(entry) != MODE_SHADOW:
        return
    managers = hass.data.setdefault(KEY, {})
    managers.setdefault(entry.entry_id, Bench(hass, entry.entry_id))
    if hass.services.has_service(DOMAIN, ACTIONS[0]):
        return
    async def action(call):
        manager = hass.data.get(KEY, {}).get(call.data["entry_id"])
        if manager is None:
            raise HomeAssistantError("Unknown explicit shadow entry")
        if call.service == ACTIONS[0]:
            return await manager.start(dict(call.data))
        if call.service == ACTIONS[1]:
            return await manager.stop()
        return manager.status()
    for name in ACTIONS:
        async_register_admin_service(hass, DOMAIN, name, action,
            schema=START if name == ACTIONS[0] else ENTRY,
            supports_response=SupportsResponse.ONLY)

async def async_unregister_entry(hass, entry_id):
    managers = hass.data.get(KEY, {})
    manager = managers.get(entry_id)
    if manager:
        await manager.stop("entry_unload")
        managers.pop(entry_id, None)
    if not managers:
        for name in ACTIONS:
            hass.services.async_remove(DOMAIN, name)
        hass.data.pop(KEY, None)
