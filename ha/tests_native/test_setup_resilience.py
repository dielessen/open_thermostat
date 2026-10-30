"""One failing part never leaves the E32 rooms and the forwarding dead (HA 0.4.0b12).

- The sensor platform sets up the E32 rooms and ha/heating_input first; every
  other step (cleanup, boiler values, telemetry, metrics, flow sensors, advice,
  gas use) is optional and only logs its failure.
- A failing hub listener never stops the others, and the forwarding runs first.
- An MQTT client that is not available yet makes Home Assistant retry the entry.
"""
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt
from homeassistant.exceptions import ConfigEntryNotReady

import custom_components.open_thermostat as integration
from custom_components.open_thermostat import sensor as sensor_platform
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.v1_boiler_fields import RetainedBoilerSource
from test_e32_room_plan_link import product


@pytest.mark.asyncio
async def test_a_failing_optional_sensor_step_never_stops_the_rooms(hass, monkeypatch, caplog):
    from custom_components.open_thermostat import (e32_flow, heating_link, native_entity_cleanup, product_telemetry,
                                                   v1_boiler_fields, v1_metrics)
    parent = product(hass)
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"v1_runtime": SimpleNamespace(enabled=False)}
    ran = []

    def step(name, fail=False):
        async def run(*args, **kwargs):
            ran.append(name)
            if fail:
                raise RuntimeError(name)
        return run

    def cleanup(*args):
        ran.append("cleanup")
        raise RuntimeError("cleanup")
    monkeypatch.setattr(native_entity_cleanup, "cleanup_stale_entities", cleanup)
    monkeypatch.setattr(heating_link, "async_setup_heating_link", step("rooms"))
    monkeypatch.setattr(v1_boiler_fields, "async_setup_boiler_fields", step("boiler", fail=True))
    monkeypatch.setattr(product_telemetry, "async_setup_sensors", step("telemetry", fail=True))
    monkeypatch.setattr(v1_metrics, "async_setup_shadow_metrics", step("metrics"))
    monkeypatch.setattr(e32_flow, "async_setup_sensors", step("flow", fail=True))
    with caplog.at_level(logging.ERROR):
        await sensor_platform.async_setup_entry(hass, parent, lambda *a, **k: None)
    assert ran == ["cleanup", "rooms", "boiler", "telemetry", "metrics", "flow"]
    assert "setting up the boiler values failed" in caplog.text


def test_a_failing_hub_listener_never_stops_the_forwarding(caplog):
    hub = HeatingHub("fixture")
    calls = []
    hub.add_listener(lambda: (_ for _ in ()).throw(RuntimeError("entity")))
    hub.add_listener(lambda: calls.append("other"))
    hub.add_listener(lambda: calls.append("forward"), first=True)
    with caplog.at_level(logging.ERROR):
        hub.update({"rooms": []})
    assert calls == ["forward", "other"]
    assert "listener failed" in caplog.text


def test_a_failing_boiler_listener_never_stops_the_others():
    source = RetainedBoilerSource(lambda: 100.0)
    calls = []
    source.add_listener(lambda: 1 / 0)
    source.add_listener(lambda: calls.append(1))
    source.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 5}))
    assert calls == [1]


@pytest.mark.asyncio
async def test_an_unavailable_mqtt_client_makes_home_assistant_retry(hass, monkeypatch):
    from homeassistant.components.mqtt import util
    parent = product(hass)
    monkeypatch.setattr(util, "mqtt_config_entry_enabled", lambda hass: True)
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock(return_value=False))
    with pytest.raises(ConfigEntryNotReady):
        await integration.async_setup_entry(hass, parent)
    assert parent.entry_id not in hass.data.get(DOMAIN, {})
