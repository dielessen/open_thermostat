
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

from .schedule_compiler import async_compile_schedule
from .v1_wire import ShadowClient, identifier


async def async_build_configuration(runtime):
    """Read native schedule exports, preserving all future UTC transitions."""
    hass = runtime.hass
    mapping = {"rooms": [r.as_dict() for r in sorted(runtime.rooms.values(), key=lambda r: r.room_id)],
               "source_policy": "qualified-physical-report/v1", "actuation": "disabled-shadow"}
    start = dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    until = start + timedelta(days=15)
    zones = []
    for room in sorted(runtime.rooms.values(), key=lambda r: r.room_id):
        schedule = None
        if room.schedule:
            entity_id = runtime.resolved(room.schedule)
            if not entity_id or er.async_get(hass).async_get(entity_id) is None:
                raise ValueError("schedule binding missing")
            schedule = await async_compile_schedule(
                hass, entity_id, room.base_centi_c, hass.config.time_zone,
                int(start.timestamp()), int(until.timestamp()))
        zones.append({"zone_id": room.room_id, "sensor_id": f"s_{room.room_id}",
                      "actuator_id": f"a_{room.room_id}", "base_centi_c": room.base_centi_c,
                      "max_age_ms": room.maximum_age_ms, "report_evidence": "physical_report",
                      "schedule": schedule})
    return zones, mapping


class NativeShadowConnection:
    """One bounded worker; native listeners/timers are all owned and removed."""
    def __init__(self, runtime):
        self.runtime, self.hass, self.entry = runtime, runtime.hass, runtime.entry
        self.prefix = self.entry.data["topic_prefix"] + "/v1/"
        self.client = None
        self.queue = asyncio.Queue(maxsize=64)
        self.worker = None
        self.unsubs = []
        self.schedule_unsubs = []
        self.timer = None
        self.closed = False

    async def async_start(self):
        if not identifier(self.entry.data["topic_prefix"]):
            raise ConfigEntryError("Shadow prefix must be1..32 ASCII letters/digits, '-' or '_'; legacy identity was not renamed")
        adapter = self.entry.options.get("adapter_id", self.entry.data.get("adapter_id"))
        if not identifier(adapter):
            raise ConfigEntryError("Missing/invalid shadow adapter owner ID; configure options and provision the same ID on E32")
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
            self.bind_schedules()
            if any(r.schedule for r in self.runtime.rooms.values()):
                self.unsubs.append(async_track_utc_time_change(
                    self.hass, refresh, hour=0, minute=0, second=0))
            self.arm()
        except Exception:
            await self.async_close()
            raise

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
                elif kind == "disconnect":
                    await self.client.async_disconnected()
                elif kind == "poll":
                    await self.client.poll()
                elif kind in {"refresh", "rebind"}:
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

    async def async_close(self):
        if self.closed:
            return
        self.closed = True
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
            self.queue.get_nowait()
            self.queue.task_done()
