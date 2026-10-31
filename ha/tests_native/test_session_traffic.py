"""Session traffic per topic: the real C++ ShadowController against the real HA client.

The measurement behind TELEMETRIEBUDGET.nl.md ("Sessieprotocol"): one room, the
ems_metrics session telemetry on, 600 s after the session is ready, the E32 loop
every second and HA's poll every 2 s, one new room temperature a minute. The
runner uses identifiers as long as on an E32 (OPENTHERMOSTAT_RUNNER_DEVICE_IDS).

Set OPENTHERMOSTAT_TRAFFIC_REPORT=<file> to keep the numbers as JSON, and run
pytest with -s to see the table.
"""
import json
import os
from collections import defaultdict

import pytest

from custom_components.open_thermostat.v1_model import Observation
from custom_components.open_thermostat.v1_wire import canonical
from test_modern_metrics import data
from test_session_recovery import system

SECONDS = 600
PREFIX = "open_thermostat/v1/"   # the topic as it travels; MQTT adds a few header bytes


def classify(topic):
    if topic == "fw/hello":
        return "hello"
    if topic == "fw/session":
        return "grant"
    if topic == "fw/heartbeat_result":
        return "heartbeat_result"
    if topic.endswith("_result"):
        return "other_results"
    if topic == "fw/state/zones":
        return "zone_state"
    if topic.startswith("fw/telemetry/"):
        return "session_telemetry"
    if topic.startswith("ha/"):
        return "ha_to_e32"
    return "other"


async def measure(hass, monkeypatch, seconds=SECONDS):
    monkeypatch.setenv("OPENTHERMOSTAT_RUNNER_DEVICE_IDS", "1")
    async with system(hass, metrics=True) as (runtime, bus):
        await bus.event("metrics_payload", raw=canonical(data()))
        client, room_id = bus.client, bus.binding.room_id
        start = len(bus.transcript)
        ready = 0
        for second in range(seconds):
            bus.now += 1000
            bus.utc += 1
            await bus.event("tick")
            if second % 60 == 30:
                temperature = 19.5 + (second // 60) % 3 / 10
                await client.async_observation(room_id, Observation(temperature, "qualified", 10, "physical-1", bus.clock()))
            if second % 2:
                await client.poll()
            await bus.pump()
            ready += client.ready
        frames = defaultdict(lambda: [0, 0, ""])
        for who, topic, raw in bus.transcript[start:]:
            row = frames[topic]
            row[0] += 1
            row[1] += len(raw.encode()) + len(PREFIX) + len(topic)
            row[2] = raw
        compact = bool(getattr(client, "session_compact", False))
        return dict(frames), ready / seconds, compact


def summary(frames, seconds=SECONDS):
    classes = defaultdict(float)
    for topic, (_count, size, _raw) in frames.items():
        classes[classify(topic)] += size / seconds
    e32 = sum(v for k, v in classes.items() if k != "ha_to_e32")
    return {k: round(v, 1) for k, v in sorted(classes.items())}, round(e32, 1)


@pytest.mark.asyncio
async def test_session_traffic_per_topic_class(hass, monkeypatch):
    frames, ready, compact = await measure(hass, monkeypatch)
    classes, e32 = summary(frames)
    report = dict(seconds=SECONDS, compact=compact, ready_fraction=ready, e32_to_ha_bytes_per_s=e32,
                  classes_bytes_per_s=classes,
                  topics={t: dict(frames=c, bytes=b, bytes_per_s=round(b / SECONDS, 1), sample=raw) for t, (c, b, raw) in sorted(frames.items())})
    print("\n" + json.dumps(report, indent=1))
    if os.environ.get("OPENTHERMOSTAT_TRAFFIC_REPORT"):
        with open(os.environ["OPENTHERMOSTAT_TRAFFIC_REPORT"], "w", encoding="utf-8") as out:
            json.dump(report, out, indent=1)
    assert ready == 1.0                               # the session never dropped
    assert frames["ha/heartbeat"][0] >= SECONDS // 10 - 2
    assert compact                                    # beta.21 firmware and HA 0.4.0b13 agree on it
    # session.compact.v1: compact grant rotations and results; the hello and zone state stay full.
    assert frames["fw/hello"][0] >= SECONDS // 15 - 2
    assert e32 < 130, classes


@pytest.mark.asyncio
async def test_compact_session_carries_less_than_the_full_form(hass, monkeypatch):
    import custom_components.open_thermostat.v1_wire as wire
    compact_frames, ready, compact = await measure(hass, monkeypatch, seconds=120)
    assert compact and ready == 1.0
    _, compact_e32 = summary(compact_frames, 120)
    # An HA without the capability (0.4.0b12) never asks for it and keeps the full form.
    monkeypatch.setattr(wire, "COMPACT_CAPABILITY", "session.compact.v0-unknown")
    full_frames, ready, compact = await measure(hass, monkeypatch, seconds=120)
    assert not compact and ready == 1.0
    _, full_e32 = summary(full_frames, 120)
    print(f"E32 to HA: compact {compact_e32} B/s, full {full_e32} B/s")
    assert compact_e32 < 0.8 * full_e32
