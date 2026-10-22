import copy
from types import SimpleNamespace
import pytest
from test_v1_bench_gate import gate, baseline, info, event, ready, report, config, discovery, IEEE, UTC
from custom_components.open_thermostat.v1_bench_source import BenchSource
from custom_components.open_thermostat.v1_bench_mqtt import NativeBenchListener

def test_request_without_baseline_rejected():
    g = gate(); event(g, "request", g.request)
    assert g.phase == "closed"

def test_retained_info_not_post_write_ack_barrier():
    g = baseline(gate()); event(g, "request", g.request)
    event(g, "info", info(g), retained=True)
    assert not g.info_seen

def test_running_option_change_closes():
    g = ready(); i = info(g)
    i["config"]["device_options"]["temperature_calibration"] = 0.1
    event(g, "info", i, t=1)
    assert g.phase == "closed"

@pytest.mark.parametrize("field,value", [("retain", True), ("qos", 1), ("qos", True)])
def test_qos_retention_fence(field, value):
    c = config(); c["devices"][IEEE][field] = value
    with pytest.raises(ValueError):
        BenchSource(c, IEEE, "zigbee2mqtt/selected", "tx", discovery=discovery())

def test_unknown_model():
    d = discovery(); d["device"]["model_id"] = "other"
    with pytest.raises(ValueError):
        BenchSource(config(), IEEE, "zigbee2mqtt/selected", "tx", discovery=d)

def test_stale_missing_values_do_not_extend_deadline():
    g = ready(); event(g, "source", report(1), t=1)
    event(g, "source", {}, t=299)
    event(g, "tick", t=300)
    assert g.phase == "closed"

@pytest.mark.asyncio
async def test_setup_failure_unloads(monkeypatch):
    from homeassistant.core import HomeAssistant
    from homeassistant.components import mqtt
    hass = HomeAssistant("/tmp/ot-bench-failure")
    calls, removed, closed = [], [], []
    async def subscribe(hass, topic, callback, **kw):
        calls.append(topic)
        if len(calls) == 3: raise RuntimeError("offline")
        return lambda: removed.append(topic)
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    listener = NativeBenchListener(hass, gate(), "zigbee2mqtt", "homeassistant/status",
                                   "discovery/selected", lambda _: None, closed.append)
    with pytest.raises(RuntimeError): await listener.async_start(True)
    assert len(removed) == 2 and len(closed) == 1
    await hass.async_stop(force=True)

@pytest.mark.asyncio
async def test_native_expiry_unsubscribes(monkeypatch):
    from homeassistant.core import HomeAssistant
    from homeassistant.components import mqtt
    import custom_components.open_thermostat.v1_bench_mqtt as bench_mqtt
    hass = HomeAssistant("/tmp/ot-bench-expiry")
    removed, closed, timers = [], [], []
    async def subscribe(hass, topic, callback, **kw):
        return lambda: removed.append(topic)
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_subscribe_connection_status",
                        lambda hass, cb: lambda: removed.append("connection"))
    def later(hass, delay, cb):
        timers.append(cb)
        return lambda: None
    monkeypatch.setattr(bench_mqtt, "async_call_later", later)
    listener = NativeBenchListener(hass, gate(), "zigbee2mqtt", "homeassistant/status",
                                   "discovery/selected", lambda _: None, closed.append)
    await listener.async_start(True)
    timers[0](None)
    assert len(removed) == 8 and listener.gate.phase == "closed" and len(closed) == 1
    await hass.async_stop(force=True)
