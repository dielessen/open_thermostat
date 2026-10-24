"""ESP diagnostic recovery, independent of boiler telemetry/control."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.open_thermostat.device_diagnostics import decode, async_setup_device_diagnostics

PACKET = dict(mem_free=95000, mem_min_free=65000, mem_max_alloc=81000,
              temperature=None, cpu_temperature=48.5, uptime=5000000)


def test_strict_diagnostics():
    assert decode(json.dumps(PACKET)) == PACKET
    for key, bad in [("cpu_temperature", float('nan')), ("mem_free", True),
                     ("uptime", -1), ("mem_free", 2**32), ("cpu_temperature", 151)]:
        assert decode(json.dumps({**PACKET, key: bad})) is None
    assert decode(json.dumps({**PACKET, 'target': 21})) is None
    assert decode('{}') is None
    assert decode('x' * 513) is None


@pytest.mark.asyncio
async def test_native_values_identity_expiry_and_disconnect(hass, monkeypatch):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat import device_diagnostics as module
    from custom_components.open_thermostat.const import DOMAIN
    callbacks = {}; listeners = []; added = []; cleanup = []
    clock = [100.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(mqtt, 'async_wait_for_mqtt_client', AsyncMock())
    async def subscribe(hass, topic, callback):
        callbacks[topic] = callback
        return lambda: cleanup.append(topic)
    monkeypatch.setattr(mqtt, 'async_subscribe', subscribe)
    publish = AsyncMock(); monkeypatch.setattr(mqtt, 'async_publish', publish)
    unload = []
    entry = SimpleNamespace(entry_id='diagnostics', data={'topic_prefix': 'fixture'}, async_on_unload=unload.append)
    def listener(callback):
        listeners.append(callback)
        return lambda: cleanup.append('listener')
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        'v1_runtime': SimpleNamespace(enabled=True, add_listener=listener),
        'v1_connection': SimpleNamespace(client=object(), prefix='fixture/v1/')}
    await async_setup_device_diagnostics(hass, entry, lambda values, **kwargs: added.extend(values))
    assert len(added) == 6
    assert all(not e.available for e in added)
    online = callbacks['fixture/v1/fw/availability']
    receive = callbacks['fixture/v1/fw/telemetry/device_status']
    # HA can restart while firmware stays connected: no online event replay.
    receive(SimpleNamespace(payload=json.dumps(PACKET), retain=True))
    assert all(not e.available for e in added)
    receive(SimpleNamespace(payload=json.dumps(PACKET), retain=False))
    by_id = {e.unique_id: e for e in added}
    assert by_id['fixture_hub_memory_free'].native_value == 95000
    assert by_id['fixture_hub_cpu_temperature'].native_value == 48.5
    assert by_id['fixture_hub_rtc_temperature'].native_value is None
    assert all(e.available for e in added)
    clock[0] += 45
    listeners[0]()
    assert all(not e.available for e in added)
    receive(SimpleNamespace(payload=json.dumps(PACKET), retain=False))
    assert all(e.available for e in added)
    online(SimpleNamespace(payload='offline'))
    online(SimpleNamespace(payload='online'))
    assert all(not e.available for e in added)
    receive(SimpleNamespace(payload=json.dumps(PACKET), retain=False))
    clock[0] -= 1
    listeners[0]()
    assert all(not e.available for e in added)
    clock[0] += 2
    listeners[0]()
    assert all(not e.available for e in added)
    publish.assert_not_called()
    for cancel in unload: cancel()
    assert len(cleanup) == 3


def test_actual_firmware_serializer_matches_ha_decoder(tmp_path):
    import subprocess
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / 'diagnostics.cpp'
    source.write_text('#include <iostream>\n#include "control/DeviceDiagnostics.h"\n'
                      'int main(){std::cout << heating::control::deviceDiagnosticsJson(95000,65000,81000,48.5,5000000);}\n')
    binary = tmp_path / 'diagnostics'
    subprocess.run(['g++', '-std=c++17', '-I', str(root/'src'), str(source), '-o', str(binary)], check=True, capture_output=True)
    wire = subprocess.check_output([str(binary)])
    assert decode(wire) == PACKET
