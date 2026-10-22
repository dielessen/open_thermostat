"""Unregistered native HA BENCH listener. Default disabled; never publishes."""
from __future__ import annotations
import json
import math
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.helpers.event import async_call_later

def decode(raw):
    if len(raw.encode("utf-8")) > 262144:
        raise ValueError("bounded bench readback")
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("duplicate JSON key")
            obj[key] = value
        return obj
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

class NativeBenchListener:
    """Caller supplies source gate and synchronous shadow-only observation sink.

    Not registered in config flow/runtime. No automatic production profile.
    Dedicated controlled bench owner must explicitly invoke async_start(True).
    """
    def __init__(self, hass, gate, prefix, ha_status_topic, discovery_topic, observation, closed):
        self.hass, self.gate = hass, gate
        self.prefix, self.ha_status = prefix, ha_status_topic
        self.discovery_topic = discovery_topic
        self.observation, self.closed_callback = observation, closed
        self.unsubs, self.timer = [], None
        self.closed_notified = False

    @callback
    def notify_closed(self):
        if not self.closed_notified:
            self.closed_notified = True
            if self.timer:
                self.timer()
                self.timer = None
            for unsub in reversed(self.unsubs):
                unsub()
            self.unsubs.clear()
            self.closed_callback(self.gate.reason)

    @callback
    def received(self, message):
        topic = message.topic
        if message.retain and not (topic in (self.prefix + "/bridge/info", self.discovery_topic) and self.gate.phase == "waiting_request"):
            return
        if topic == self.discovery_topic:
            kind = "discovery"
        elif topic == self.gate.state_topic:
            kind = "source"
        elif topic == self.prefix + "/bridge/info":
            kind = "info"
        elif topic == self.prefix + "/bridge/response/device/options":
            kind = "ack"
        elif topic.startswith(self.prefix + "/bridge/request/"):
            kind = "request"
        else:
            kind = "lifecycle"
        try:
            payload = decode(message.payload) if kind != "lifecycle" else None
            if kind == "request" and topic != self.prefix + "/bridge/request/device/options":
                self.gate.stop("unexpected_control_request")
            else:
                import time
                result = self.gate.event(kind, payload, retained=message.retain, mono=self.hass.loop.time(), utc=time.time())
                if result is not None:
                    self.observation(result)
        except (ValueError, TypeError, RecursionError):
            self.gate.stop("malformed_bench_message")
        if self.gate.phase == "closed":
            self.notify_closed()

    async def async_start(self, enabled=False):
        if enabled is not True:
            raise ValueError("explicit supervised shadow bench enable required")
        if self.unsubs or self.closed_notified:
            raise ValueError("bench cannot resume/restart")
        try:
            for topic in (self.gate.state_topic, self.prefix + "/bridge/info",
                          self.prefix + "/bridge/request/#",
                          self.prefix + "/bridge/response/device/options",
                          self.prefix + "/bridge/state", self.ha_status, self.discovery_topic):
                self.unsubs.append(await mqtt.async_subscribe(
                    self.hass, topic, self.received, qos=0, encoding="utf-8"))
            @callback
            def status(connected):
                if not connected:
                    self.gate.stop("broker_disconnected")
                    self.notify_closed()
            self.unsubs.append(mqtt.async_subscribe_connection_status(self.hass, status))
            @callback
            def expire(_):
                self.gate.stop("finite_listener_expired")
                self.notify_closed()
            from homeassistant.const import EVENT_HOMEASSISTANT_STOP
            @callback
            def shutdown(_):
                self.gate.stop("ha_stopping")
                self.notify_closed()
            self.unsubs.append(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown))
            self.timer = async_call_later(self.hass, self.gate.duration_s, expire)
        except Exception:
            await self.async_close()
            raise

    async def async_close(self):
        if self.timer:
            self.timer()
            self.timer = None
        for unsub in reversed(self.unsubs):
            unsub()
        self.unsubs.clear()
        self.gate.stop("listener_unloaded")
        self.notify_closed()

async def async_forward_shadow(client, room_id, sample, expected_mapping_digest):
    """Explicit alternative wire path; never mislabels a report physical_report.

    Generic HA-state observation writer for this sensor must be excluded by the
    enclosing bench binding. No automatic reconfiguration or profile promotion.
    """
    accepted = client.journal.get("accepted")
    if not client.ready or not accepted:
        raise ValueError("accepted shadow session required")
    config = accepted["config"]
    zones = [z for z in config["zones"] if z["zone_id"] == room_id]
    if (config["mode"] != "shadow" or config["mapping_digest"] != expected_mapping_digest
            or len(zones) != 1 or zones[0]["report_evidence"] != "validated_integration_report"):
        raise ValueError("bench evidence/mapping not admitted")
    age = (sample["source_sample_age_ms"] + math.ceil(max(0, client.clock() - sample["received_monotonic"]) * 1000)) if sample else 0
    available = sample is not None and client.clock() < sample["bench_deadline_monotonic"]
    available = available and age < zones[0]["max_age_ms"]
    await client.message("ha/observations", zones[0]["sensor_id"], {
        "zone_id": room_id, "source_available": available,
        "temperature_c": sample["temperature_c"] if available else 0,
        "source_sample_age_ms": age if available else 0,
        "evidence": "validated_integration_report" if available else "unverified"})
