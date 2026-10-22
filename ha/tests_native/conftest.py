"""Real HA 2026.10.2 core/registries; no broker, devices, network or production config."""
import sys
from pathlib import Path
import socket

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntries
from homeassistant.helpers import entity_registry as er, device_registry as dr, frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "config"))

@pytest_asyncio.fixture
async def hass(tmp_path, monkeypatch):
    def forbidden_network(*args, **kwargs):
        raise AssertionError("offline test attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    instance = HomeAssistant(str(tmp_path))
    frame.async_setup(instance)
    dr.async_setup(instance)
    await dr.async_load(instance, load_empty=True)
    await er.async_load(instance, load_empty=True)
    instance.config_entries = ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    yield instance
    await instance.async_stop(force=True)
