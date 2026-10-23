
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


async def async_room_schedule(hass,room,start=None):
    start=start or dt_util.utcnow().replace(hour=0,minute=0,second=0,microsecond=0)
    until=start+timedelta(days=15)
    schedule = None
    if room.schedule and room.week_program is not None:
        raise ValueError("program_source_conflict")
    if room.week_program is not None:
        schedule = await hass.async_add_executor_job(
            compile_week, native_week(room.week_program), room.base_centi_c,
            hass.config.time_zone, int(start.timestamp()), int(until.timestamp()))
    elif room.schedule:
        ref=room.schedule
        entity_id=(er.async_get(hass).async_get_entity_id("schedule",ref.platform,ref.unique_id)
                   if ref.platform is not None and ref.unique_id is not None else ref.entity_id)
        if not entity_id or er.async_get(hass).async_get(entity_id) is None:
            raise ValueError("schedule binding missing")
        schedule = await async_compile_schedule(
            hass, entity_id, room.base_centi_c, hass.config.time_zone,
            int(start.timestamp()), int(until.timestamp()))
    if schedule and any(
            not room.minimum_target_centi_c <= target <= room.maximum_target_centi_c
            for _, target in schedule["transitions"]):
        raise ValueError("Schedule temperature is outside room target limits")
    return schedule


async def async_build_configuration(runtime):
    """Read native schedule exports, preserving all future UTC transitions."""
    if getattr(runtime,"graph_controller_source",None) is not None:
        config,mapping=await runtime.graph_controller_source.async_configuration(runtime.hass,runtime.entry)
        return config["zones"],mapping
    if any(not room.shadow_wire_supported for room in runtime.rooms.values()):
        raise ConfigEntryError("graph_room_contract_unavailable")
    hass = runtime.hass
    mapping = {"rooms": [r.as_dict() for r in sorted(runtime.rooms.values(), key=lambda r: r.room_id)],
               "source_policy": "qualified-physical-report/v1", "actuation": "disabled-shadow"}
    start = dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    zones = []
    for room in sorted(runtime.rooms.values(), key=lambda r: r.room_id):
        schedule = await async_room_schedule(hass,room,start)
        zones.append({"zone_id": room.room_id, "sensor_id": f"s_{room.room_id}",
                      "actuator_id": f"a_{room.room_id}", "base_centi_c": room.base_centi_c,
                      "max_age_ms": room.maximum_age_ms, "report_evidence": "physical_report",
                      "schedule": schedule,
                      **({"comfort": {**room.comfort,
                          "minimum_centi_c": room.minimum_target_centi_c,
                          "maximum_centi_c": room.maximum_target_centi_c,
                          "window": room.window is not None,
                          "presence": room.presence is not None}} if room.comfort is not None else {})})
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
        self.original_reports = None
        self.original_pending = False

    async def async_start(self):
        if self.graph_profile is not None and getattr(self.runtime,"controller_policy_source_profile",None) is not None:
            raise ConfigEntryError("controller_policy_graph_conflict")
        if getattr(self.runtime,"graph_data_profile",None) is not None and self.runtime.graph_data_profile!=self.graph_profile:
            raise ConfigEntryError("graph_profile_unsupported")
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
            plan=None
            if self.runtime.native_plan_source is not None:
                plan,mapping=await self.runtime.native_plan_source.async_configuration(self.hass,self.entry)
                zones=plan["zones"]
            else:zones,mapping=await async_build_configuration(self.runtime)
            self.client = ShadowClient(
                self.runtime, adapter, self.publish,
                Store(self.hass, 1, f"open_thermostat.v1.{self.entry.entry_id}"),
                zones, mapping, self.hass.loop.time,control_plan=plan)
        await self.client.async_start()
        if self.runtime.graph_controller_source is not None:
            await self.client.async_stage_graph_source_readback()
            # A native control Store await must not hide graph/config/registry
            # drift. Recheck known SOURCE DATA before any subscribe/publish.
            await self.runtime.graph_controller_source.async_configuration(self.hass,self.entry)
        if self.runtime.native_plan_source is not None and not self.client.native_source_current():
            raise ConfigEntryError("native_plan_source_changed_during_start")
        self.runtime.attach_transport(self.client)
        self.client._close_io = self.async_close
        from .original_temperature import OriginalTemperatureReports
        self.original_reports = OriginalTemperatureReports(self.runtime)
        self.runtime.original_temperature_reports = self.original_reports
        self.worker = self.hass.async_create_background_task(self.run(), "OpenThermostat shadow MQTT")

        @callback
        def received(message):
            if message.topic == self.prefix + "fw/telemetry/boiler_fields":
                self.enqueue(("boiler_message", (message,self.hass.loop.time())))
            else:
                self.enqueue(("message", message))

        @callback
        def connection_status(connected):
            if not connected:
                self.original_reports.invalidate()
                if self.graph_profile is not None or self.runtime.native_plan_source is not None:
                    # Existing Store await can yield inside the same worker.
                    # Fence graph DATA immediately, not behind that in-flight IO.
                    self.client.reset_session()
                self.enqueue(("disconnect", None))

        @callback
        def refresh(_):
            self.enqueue(("refresh", None))

        @callback
        def original_received(message):
            # One pending diagnostic event, with half the existing queue kept
            # free. Original report traffic cannot fill it or reset control.
            if self.closed or self.original_pending or self.queue.qsize() >= 32:
                return
            from .original_temperature import MAX_BYTES
            if (message.topic not in self.original_reports.topics or message.retain
                    or type(message.payload) not in (str, bytes)
                    or len(message.payload) > MAX_BYTES):
                return
            try:
                self.queue.put_nowait(("original_temperature", (message,
                    self.runtime.clock(), int(dt_util.utcnow().timestamp() * 1000),
                    self.original_reports.epoch)))
                self.original_pending = True
            except asyncio.QueueFull:
                return

        try:
            self.unsubs.append(await mqtt.async_subscribe(
                self.hass, self.prefix + "fw/#", received, qos=0, encoding="utf-8"))
            self.unsubs.append(mqtt.async_subscribe_connection_status(self.hass, connection_status))
            for topic in sorted(self.original_reports.topics):
                try:
                    self.unsubs.append(await mqtt.async_subscribe(
                        self.hass, topic, original_received, qos=0, encoding=None))
                except Exception:
                    # Optional reception diagnostics must not break startup of
                    # the existing native connection if this topic is denied.
                    self.original_reports.invalidate("unavailable")
                    break
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
        """Explicit action joins SAME bounded worker; readback only requests DATA."""
        if (self.closed or self.worker is None or (self.graph_profile is None and self.runtime.native_plan_source is None)
                or command not in {"stage", "apply", "prepare", "readback"}
                or command=="readback" and self.runtime.native_plan_source is None):
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
        registry_ids=set(ids)
        source=self.runtime.graph_controller_source or self.runtime.native_plan_source
        if source is not None:
            from .v1_model import EntityReference
            for ref in source.registry_references(self.hass,self.entry):
                if entity_id:=self.runtime.resolved(EntityReference.from_dict(ref)):
                    registry_ids.add(entity_id)
        if not registry_ids or self.closed:
            return

        @callback
        def refresh(_):
            if self.runtime.native_plan_source is not None:
                self.client.reset_session()
            self.enqueue(("refresh", None))

        @callback
        def registry_changed(_):
            if self.runtime.native_plan_source is not None:
                self.client.reset_session()
            self.enqueue(("rebind", None))

        if ids:
            self.schedule_unsubs.extend([
                async_track_state_change_event(self.hass, ids, refresh),
                # Same-value future schedule edits still fence selected pins.
                async_track_state_report_event(self.hass, ids, refresh)])
        self.schedule_unsubs.append(
            async_track_entity_registry_updated_event(self.hass, registry_ids, registry_changed))

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
                if kind == "original_temperature":
                    message, received_at, received_unix_ms, epoch = data
                    self.original_pending = False
                    try:
                        if self.original_reports.receive(message.topic, message.payload,
                                retained=message.retain, received_at=received_at,
                                received_unix_ms=received_unix_ms, epoch=epoch):
                            self.runtime._notify()
                    except Exception:
                        # A diagnostic observer cannot reset a control session,
                        # even if a native registry/listener unexpectedly fails.
                        self.original_reports.invalidate("unavailable")
                elif kind == "boiler_message":
                    message,received_at=data
                    await self.client.receive("fw/telemetry/boiler_fields",message.payload,
                        retained=message.retain,received_at=received_at)
                elif kind == "message":
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
                        if self.runtime.native_plan_source is not None:
                            if command=="stage":raise ConfigEntryError("native_plan_raw_stage_unsupported")
                            if command=="readback":
                                if args:raise ConfigEntryError("native_plan_readback_arguments")
                                result=await self.client.async_request_native_plan_readback()
                            else:
                                result=await (self.client.async_prepare_native_plan() if command=="prepare"
                                              else self.client.async_apply(*args))
                        elif command=="prepare":
                            from .graph_draft_compile import async_compile_saved_graph
                            if args or self.graph_profile.draft_source is None:
                                raise ConfigEntryError("graph_draft_source_unavailable")
                            raw,mapping=await async_compile_saved_graph(self.hass,self.entry,
                                self.client._context(),self.graph_profile.draft_source)
                            result=await self.client.async_stage(raw,mapping)
                        else:
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
                        self.client.error = (self.client.graph_status["journal_status"] if self.runtime.native_plan_source is not None else self.client.journal.status)
                        self.client.changed()
                elif kind in {"refresh", "rebind"}:
                    if self.runtime.native_plan_source is not None:
                        if kind=="refresh" and self.runtime.native_plan_source.policy.week_reviewed:
                            try:
                                await self.client.async_request_native_horizon_refresh()
                                continue
                            except Exception:
                                # Changed/uncertain/helper intent needs explicit review.
                                # Never renew a grant or automatically clear a pending stage.
                                pass
                        self.client.reset_session()
                        self.client.error="native_plan_review_required"
                        if kind=="rebind":self.bind_schedules()
                        self.client.changed()
                        continue
                    if self.runtime.graph_controller_source is not None:
                        self.client.require_graph_source_review()
                        continue
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
        if self.original_reports is not None:
            self.original_reports.invalidate("closed")
            if self.runtime.original_temperature_reports is self.original_reports:
                self.runtime.original_temperature_reports = None
        self.original_pending = False
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
