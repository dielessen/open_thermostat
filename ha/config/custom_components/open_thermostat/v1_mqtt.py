
"""Native HA MQTT/Store lifecycle for explicitly enabled shadow mode only."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later, async_track_state_change_event, async_track_state_report_event,
    async_track_entity_registry_updated_event, async_track_utc_time_change,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .schedule_compiler import async_compile_schedule, compile_week
from .v1_program import native_week
from .v1_wire import ShadowClient, identifier


async def async_build_configuration(runtime):
    """Read native schedule exports, preserving all future UTC transitions."""
    if any(not room.shadow_wire_supported for room in runtime.rooms.values()):
        raise ConfigEntryError("graph_room_contract_unavailable")
    hass = runtime.hass
    mapping = {"rooms": [r.as_dict() for r in sorted(runtime.rooms.values(), key=lambda r: r.room_id)],
               "source_policy": "qualified-physical-report/v1", "actuation": "disabled-shadow"}
    start = dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    until = start + timedelta(days=15)
    zones = []
    for room in sorted(runtime.rooms.values(), key=lambda r: r.room_id):
        schedule = None
        if room.schedule and room.week_program is not None:
            raise ValueError("program_source_conflict")
        if room.week_program is not None:
            schedule = await hass.async_add_executor_job(
                compile_week, native_week(room.week_program), room.base_centi_c,
                hass.config.time_zone, int(start.timestamp()), int(until.timestamp()))
        elif room.schedule:
            entity_id = runtime.resolved(room.schedule)
            if not entity_id or er.async_get(hass).async_get(entity_id) is None:
                raise ValueError("schedule binding missing")
            schedule = await async_compile_schedule(
                hass, entity_id, room.base_centi_c, hass.config.time_zone,
                int(start.timestamp()), int(until.timestamp()))
        if schedule and any(
                not room.minimum_target_centi_c <= target <= room.maximum_target_centi_c
                for _, target in schedule["transitions"]):
            raise ValueError("Schedule temperature is outside room target limits")
        zones.append({"zone_id": room.room_id, "sensor_id": f"s_{room.room_id}",
                      "actuator_id": f"a_{room.room_id}", "base_centi_c": room.base_centi_c,
                      "max_age_ms": room.maximum_age_ms, "report_evidence": "physical_report",
                      "schedule": schedule})
    return zones, mapping


class NativeShadowConnection:
    """One bounded worker; native listeners/timers are all owned and removed."""
    def __init__(self, runtime, graph_profile=None):
        self.runtime, self.hass, self.entry = runtime, runtime.hass, runtime.entry
        self.graph_profile = graph_profile
        self.prefix = self.entry.data["topic_prefix"] + ("/v2/" if graph_profile is not None else "/v1/")
        self.client = None
        self.queue = asyncio.Queue(maxsize=64)
        self.worker = None
        self.unsubs = []
        self.schedule_unsubs = []
        self.timer = None
        self.closed = False
        self.bench = None

    async def async_start(self):
        if not identifier(self.entry.data["topic_prefix"]):
            raise ConfigEntryError("Shadow prefix must be1..32 ASCII letters/digits, '-' or '_'; legacy identity was not renamed")
        adapter = self.entry.options.get("adapter_id", self.entry.data.get("adapter_id"))
        if not identifier(adapter):
            raise ConfigEntryError("Missing/invalid shadow adapter owner ID; configure options and provision the same ID on E32")
        if self.graph_profile is not None:
            # Explicit source-owned pin only. No current product options/default
            # call supplies it, and selected2 NEVER silently falls back to1.
            from .graph_wire import GraphSourceProfile, GraphShadowClient
            from .graph_shadow_storage import native_graph_journal
            if not isinstance(self.graph_profile, GraphSourceProfile):
                raise ConfigEntryError("graph_profile_unsupported")
            self.graph_profile.validate()
            journal = native_graph_journal(
                self.hass, self.entry, self.graph_profile.qualification_digest)
            self.client = GraphShadowClient(self.runtime, adapter, self.publish,
                journal, self.graph_profile, self.hass.loop.time)
        else:
            zones, mapping = await async_build_configuration(self.runtime)
            self.client = ShadowClient(
                self.runtime, adapter, self.publish,
                Store(self.hass, 1, f"open_thermostat.v1.{self.entry.entry_id}"),
                zones, mapping, self.hass.loop.time)
        await self.client.async_start()
        self.runtime.attach_transport(self.client)
        self.client._close_io = self.async_close
        self.worker = self.hass.async_create_background_task(self.run(), "OpenThermostat shadow MQTT")

        @callback
        def received(message):
            self.enqueue(("message", message))

        @callback
        def connection_status(connected):
            if not connected:
                self.enqueue(("disconnect", None))

        @callback
        def refresh(_):
            self.enqueue(("refresh", None))

        try:
            self.unsubs.append(await mqtt.async_subscribe(
                self.hass, self.prefix + "fw/#", received, qos=0, encoding="utf-8"))
            self.unsubs.append(mqtt.async_subscribe_connection_status(self.hass, connection_status))
            if self.graph_profile is None:
                self.bind_schedules()
            if self.graph_profile is None and any(r.schedule or r.week_program is not None for r in self.runtime.rooms.values()):
                self.unsubs.append(async_track_utc_time_change(
                    self.hass, refresh, hour=0, minute=0, second=0))
            self.arm()
        except Exception:
            await self.async_close()
            raise

    async def async_graph_command(self, command, *args):
        """Explicit stage/apply joins SAME bounded worker, never a parallel writer."""
        if self.closed or self.worker is None or self.graph_profile is None or command not in {"stage", "apply"}:
            raise ConfigEntryError("graph_profile_unavailable")
        future = self.hass.loop.create_future()
        try:
            self.queue.put_nowait(("graph_command", (future, command, args)))
        except asyncio.QueueFull as error:
            self.client.reset_session()
            self.client.error = "receive_queue_overflow"
            self.client.changed()
            raise ConfigEntryError("graph_queue_full") from error
        return await future

    @callback
    def bind_schedules(self):
        for unsub in self.schedule_unsubs:
            unsub()
        self.schedule_unsubs.clear()
        ids = {self.runtime.resolved(r.schedule) for r in self.runtime.rooms.values() if r.schedule}
        ids.discard(None)
        if not ids or self.closed:
            return

        @callback
        def refresh(_):
            self.enqueue(("refresh", None))

        @callback
        def registry_changed(_):
            self.enqueue(("rebind", None))

        self.schedule_unsubs.extend([
            async_track_state_change_event(self.hass, ids, refresh),
            # Schedule.async_update_config->_update always writes state in
            # HA2026.10.2, even on a future-only edit with identical attributes.
            async_track_state_report_event(self.hass, ids, refresh),
            async_track_entity_registry_updated_event(self.hass, ids, registry_changed),
        ])

    async def publish(self, suffix, raw):
        if self.closed:
            return
        await mqtt.async_publish(self.hass, self.prefix + suffix, raw, qos=0, retain=False)

    @callback
    def enqueue(self, item):
        if self.closed:
            return
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            # Invalidate immediately; don't queue stop behind 64 stale messages.
            self.client.reset_session()
            self.client.error = "receive_queue_overflow"
            self.client.changed()

    @callback
    def arm(self):
        @callback
        def tick(_):
            self.timer = None
            self.enqueue(("poll", None))
            if not self.closed:
                self.arm()
        self.timer = async_call_later(self.hass, 2, tick)

    async def run(self):
        while True:
            kind, data = await self.queue.get()
            try:
                if kind == "message":
                    if data.topic.startswith(self.prefix):
                        await self.client.receive(data.topic[len(self.prefix):], data.payload, retained=data.retain)
                        self.check_bench_admission()
                elif kind == "disconnect":
                    if self.bench:
                        self.bench.request_stop("firmware_transport_disconnected")
                    await self.client.async_disconnected()
                elif kind == "poll":
                    await self.client.poll()
                    self.check_bench_admission()
                elif kind == "graph_command":
                    future, command, args = data
                    if future.cancelled():
                        continue
                    try:
                        result = await (self.client.async_stage(*args) if command == "stage"
                                        else self.client.async_apply(*args))
                        if not future.done():
                            future.set_result(result)
                    except asyncio.CancelledError:
                        future.cancel()
                        raise
                    except Exception as error:
                        if not future.done():
                            future.set_exception(error)
                        # Validation fails the journal closed but need not force
                        # another session. Uncertain IO/dependency failures do.
                        from .graph_shadow_validation import GraphValidationError
                        if not isinstance(error, GraphValidationError):
                            self.client.reset_session()
                        self.client.error = self.client.journal.status
                        self.client.changed()
                elif kind in {"refresh", "rebind"}:
                    if self.graph_profile is not None:
                        self.client.configuration_changed()
                        continue
                    if self.bench:
                        self.bench.request_stop("configuration_or_schedule_changed")
                        continue
                    if kind == "rebind":
                        self.bind_schedules()
                    # Attribute changes on adjacent on-blocks also trigger this.
                    zones, mapping = await async_build_configuration(self.runtime)
                    self.client.desired, self.client.mapping = zones, mapping
                    if self.client.session and self.hass.loop.time() < self.client.grant_until:
                        self.client.verified = False
                        await self.client.message("ha/snapshot_request", "snapshot", {})
            except asyncio.CancelledError:
                raise
            except Exception:
                self.client.reset_session()
                self.client.error = "shadow_io_or_configuration_failed"
                self.client.changed()
            finally:
                self.queue.task_done()

    @callback
    def check_bench_admission(self):
        bench = self.bench
        if bench and bench.phase in {"listening", "observing"}:
            identity = (self.client.identity, self.client.session.get("adapter_session_id") if self.client.session else None)
            if not self.client.ready or identity != bench.fw_identity:
                bench.request_stop("firmware_availability_or_session_lost")

    async def async_close(self):
        if self.closed:
            return
        self.closed = True
        if self.client is not None:
            self.client.reset_session()
        if self.timer:
            self.timer()
            self.timer = None
        for unsub in (*self.unsubs, *self.schedule_unsubs):
            unsub()
        self.unsubs.clear()
        self.schedule_unsubs.clear()
        if self.worker and self.worker is not asyncio.current_task():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        while not self.queue.empty():
            kind, data = self.queue.get_nowait()
            if kind == "graph_command":
                data[0].cancel()
            self.queue.task_done()
