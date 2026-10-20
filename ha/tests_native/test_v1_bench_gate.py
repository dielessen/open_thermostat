import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from custom_components.open_thermostat.v1_bench_source import BenchSource, proposal, clean, effective, replay
from custom_components.open_thermostat.v1_bench_mqtt import NativeBenchListener, async_forward_shadow, decode

IEEE = "0xtest"
UTC = 1792368000
def config():
    return {"device_options": {}, "devices": {IEEE: {"friendly_name": "selected"}},
            "advanced": {"cache_state": True, "last_seen": "ISO_8601"}}
def discovery():
    return {"device": {"model_id": "WSDCGQ11LM"}, "origin": {"sw_version": "2.14.2"},
            "state_topic": "zigbee2mqtt/selected", "unit_of_measurement": "°C",
            "value_template": '{{ value_json["temperature"] }}'}
def gate(**kw):
    return BenchSource(config(), IEEE, "zigbee2mqtt/selected", "unique_tx", discovery=discovery(), **kw)
def info(g):
    return {"version": "2.14.2", "zigbee_herdsman_converters": {"version": "26.115.1"},
            "restart_required": False, "config": copy.deepcopy(g.expected)}
def ack(g):
    return {"status": "ok", "transaction": "unique_tx", "data": {
        "from": clean(effective(g.baseline, IEEE)), "to": clean(effective(g.expected, IEEE)),
        "id": IEEE, "restart_required": False}}
def event(g, kind, payload=None, t=0, **kw):
    return g.event(kind, payload, mono=t, utc=UTC+t, **kw)
def baseline(g):
    event(g, "discovery", discovery(), retained=True)
    i = info(g); i["config"] = copy.deepcopy(g.baseline)
    event(g, "info", i, retained=True)
    return g
def ready():
    g = baseline(gate())
    event(g, "request", g.request)
    event(g, "info", info(g))
    event(g, "ack", ack(g))
    assert g.phase == "draining"
    return g
def report(t, value=20):
    return {"temperature": value, "last_seen": datetime.fromtimestamp(UTC+t, timezone.utc).isoformat()}

def test_cutover_drain_equal_new_reports():
    g = ready()
    assert event(g, "source", report(1), t=1) is None
    sample = event(g, "source", report(2), t=2)
    assert sample["evidence"] == "validated_integration_report"
    assert sample["temperature_c"] == 20
    assert event(g, "source", report(2), t=3) is None

@pytest.mark.parametrize("field,value", [("debounce", 1), ("throttle", 1), ("throttle", True)])
def test_buffered_source_rejected(field, value):
    c = config(); c["device_options"][field] = value
    with pytest.raises(ValueError):
        BenchSource(c, IEEE, "z/selected", "tx", discovery=discovery())

def test_explicit_zero_and_preserved_filter_rollback():
    c = config(); c["device_options"] = {"debounce": 0, "filtered_cache": ["battery"]}
    request, rollback = proposal(c, IEEE, "tx")
    assert request["options"] == {"filtered_cache": ["battery", "^temperature$"]}
    assert rollback["options"] == {"filtered_cache": None}
    c["devices"][IEEE]["filtered_cache"] = ["humidity"]
    assert proposal(c, IEEE, "tx")[1]["options"] == {"filtered_cache": ["humidity"]}

@pytest.mark.parametrize("change", ["transaction", "from", "restart", "version", "calibration", "info_order"])
def test_ack_barrier_fail_closed(change):
    g = baseline(gate()); event(g, "request", g.request)
    i, a = info(g), ack(g)
    if change == "transaction": a["transaction"] = "other"
    if change == "from": a["data"]["from"]["debounce"] = 1
    if change == "restart": a["data"]["restart_required"] = True
    if change == "version": i["version"] = "other"
    if change == "calibration": i["config"]["devices"][IEEE]["temperature_calibration"] = 1
    if change != "info_order": event(g, "info", i)
    event(g, "ack", a)
    assert g.phase == "closed"

def test_retained_frame_not_drain():
    g = ready()
    event(g, "source", report(1), t=1, retained=True)
    assert g.phase == "draining"
    assert event(g, "source", report(2), t=2) is None
    assert event(g, "source", report(3), t=3)

@pytest.mark.parametrize("payload", [
    {"last_seen": "bad", "temperature": 20},
    {"temperature": 20}, {"temperature": None}, {"temperature": True},
    {"temperature": "20"}, {"temperature": float("nan")},
    {"humidity": 50, "last_seen": "2026-10-19T00:00:00Z"},
])
def test_missing_invalid_data_never_renews(payload):
    g = ready()
    assert event(g, "source", payload, t=1) is None
    assert g.phase == "draining"

@pytest.mark.parametrize("kind", ["lifecycle", "disconnect", "request"])
def test_invalidation(kind):
    g = ready(); event(g, kind, {}, t=1)
    assert g.phase == "closed"
    assert event(g, "source", report(2), t=2) is None

def test_expiry_no_source_needed():
    g = ready(); event(g, "tick", t=300)
    assert g.phase == "closed"

def test_old_future_and_clock_jump():
    g = ready()
    assert event(g, "source", report(-1), t=1) is None
    assert event(g, "source", report(3), t=2) is None
    g.event("tick", None, mono=3, utc=UTC+30)
    assert g.reason == "clock_invalid"

def test_shared_jsonl():
    path = Path(__file__).parent / "fixtures/source_bench_cutover.jsonl"
    results = list(replay(path.read_text().splitlines()))
    assert results[-2]["observation"]["evidence"] == "validated_integration_report"
    assert results[-1]["phase"] == "closed"

def test_parser():
    for bad in ('{"a":1,"a":2}', '{"x":NaN}'):
        with pytest.raises(ValueError): decode(bad)

@pytest.mark.asyncio
async def test_real_ha_native_api_lifecycle(monkeypatch):
    # Real pinned HA APIs imported; only MQTT broker boundary replaced.
    from homeassistant.core import HomeAssistant
    from homeassistant.components import mqtt
    hass = HomeAssistant("/tmp/ot-bench-offline")
    calls, removed, observations, closed = {}, [], [], []
    async def subscribe(hass, topic, cb, **kw):
        calls[topic] = cb
        return lambda: removed.append(topic)
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_subscribe_connection_status",
                        lambda hass, cb: lambda: removed.append("connection"))
    listener = NativeBenchListener(hass, gate(), "zigbee2mqtt", "homeassistant/status", "homeassistant/sensor/selected/config",
                                   observations.append, closed.append)
    with pytest.raises(ValueError): await listener.async_start()
    assert not calls
    await listener.async_start(True)
    assert len(calls) == 7
    g = listener.gate
    calls["homeassistant/sensor/selected/config"](SimpleNamespace(topic="homeassistant/sensor/selected/config", payload=json.dumps(discovery()), retain=True))
    initial = info(g); initial["config"] = copy.deepcopy(g.baseline)
    calls["zigbee2mqtt/bridge/info"](SimpleNamespace(topic="zigbee2mqtt/bridge/info", payload=json.dumps(initial), retain=True))
    for topic, payload in [
        ("zigbee2mqtt/bridge/request/device/options", g.request),
        ("zigbee2mqtt/bridge/info", info(g)),
        ("zigbee2mqtt/bridge/response/device/options", ack(g)),
    ]:
        calls.get(topic, calls["zigbee2mqtt/bridge/request/#"])(SimpleNamespace(topic=topic, payload=json.dumps(payload), retain=False))
    assert g.phase == "draining"
    calls["homeassistant/status"](SimpleNamespace(topic="homeassistant/status", payload="online", retain=False))
    assert g.phase == "closed" and len(closed) == 1 and len(removed) == 8
    await listener.async_close()
    assert len(closed) == 1
    await hass.async_stop(force=True)

@pytest.mark.asyncio
async def test_forward_only_accepted_validated_shadow():
    config_ = {"mode": "shadow", "mapping_digest": "known", "zones": [
        {"zone_id": "r1", "sensor_id": "s_r1", "max_age_ms": 120000,
         "report_evidence": "validated_integration_report"}]}
    client = SimpleNamespace(ready=True, journal={"accepted": {"config": config_}},
                             clock=lambda: 10, message=AsyncMock())
    sample = {"temperature_c": 20, "source_sample_age_ms": 100,
              "received_monotonic": 9, "bench_deadline_monotonic": 100}
    await async_forward_shadow(client, "r1", sample, "known")
    body = client.message.call_args.args[2]
    assert body["evidence"] == "validated_integration_report"
    assert body["source_sample_age_ms"] == 1100
    config_["zones"][0]["report_evidence"] = "physical_report"
    with pytest.raises(ValueError): await async_forward_shadow(client, "r1", sample, "known")
    config_["zones"][0]["report_evidence"] = "validated_integration_report"
    await async_forward_shadow(client, "r1", None, "known")
    assert client.message.call_args.args[2]["source_available"] is False
