"""The devices on the E32's EMS bus as Home Assistant devices, and the E32's own firmware version (beta.23)."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import device_registry as dr

from custom_components.open_thermostat import ems_devices
from custom_components.open_thermostat.firmware_update import E32FirmwareUpdate

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "ha/config/custom_components/open_thermostat"


def payload(*devices):
    return json.dumps({"schema": 1, "devices": [dict(zip(("address", "product_id", "version", "brand_id"), d))
                                                 for d in devices]})


def test_the_product_table_matches_the_e32_pages_reference():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/generate_ems_products.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_invalid_payloads_are_ignored():
    assert ems_devices.parse("{") is None
    assert ems_devices.parse(json.dumps({"schema": 2, "devices": []})) is None
    assert ems_devices.parse(payload((0, None, None, None))) is None  # address 0
    assert ems_devices.parse(payload((8, None, None, None), (8, None, None, None))) is None  # duplicate
    assert ems_devices.parse(payload((8, 300, None, None))) is None
    assert ems_devices.parse(payload((8, None, None, None))) == [
        {"address": 8, "product_id": None, "version": None, "brand_id": None}]


def test_names_follow_the_e32_page():
    # The owner's adapter once its identity is read (EMS-ESP product 211, brand Bosch).
    assert ems_devices.describe({"address": 8, "product_id": 211, "version": "1.3", "brand_id": 1}) == {
        "name": "Bosch EasyControl Adapter (0x08)", "manufacturer": "Bosch", "model": "EasyControl Adapter"}
    assert ems_devices.describe({"address": 8, "product_id": 211, "version": None, "brand_id": None})["name"] == \
        "EasyControl Adapter (0x08)"
    assert ems_devices.describe({"address": 8, "product_id": None, "version": None, "brand_id": None}) is None
    unknown = ems_devices.describe({"address": 23, "product_id": 2, "version": "2.0", "brand_id": 4})
    assert "name" not in unknown and unknown["translation_key"] == "ems_thermostat"
    assert unknown["translation_placeholders"] == {"address": "0x17", "product": "2"}


def test_generic_names_are_translated_in_english_dutch_and_polish():
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        device = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["device"]
        for key in ("ems_boiler", "ems_thermostat", "ems_device"):
            assert "{address}" in device[key]["name"] and "{product}" in device[key]["name"], (name, key)


@pytest.mark.asyncio
async def test_known_identities_become_devices_via_the_e32_and_unknown_ones_wait(hass, monkeypatch):
    from test_product_flow import product
    entry = product(hass)
    registry = dr.async_get(hass)
    hub = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("open_thermostat", "fixture")},
                                       name="OpenThermostat E32")
    callbacks = {}

    async def subscribe(_hass, topic, callback, *args, **kwargs):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    await ems_devices.async_setup_ems_devices(hass, entry)
    receive = callbacks["fixture/v1/fw/config/ems_devices"]
    receive(SimpleNamespace(payload=payload((8, None, None, None), (23, None, None, None))))
    assert registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id) is None
    assert ems_devices.diagnostics(hass, entry)[0]["address"] == 8
    receive(SimpleNamespace(payload=payload((8, 211, "1.3", 1), (23, None, None, None))))
    adapter = registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id)
    assert (adapter.name, adapter.manufacturer, adapter.model, adapter.model_id, adapter.sw_version) == (
        "Bosch EasyControl Adapter (0x08)", "Bosch", "EasyControl Adapter", "211", "1.3")
    assert adapter.via_device_id == hub.id
    # A name the user gives stays; a newer version updates the device.
    registry.async_update_device(adapter.id, name_by_user="Ketel")
    receive(SimpleNamespace(payload=payload((8, 211, "1.4", 1))))
    adapter = registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id)
    assert (adapter.name_by_user, adapter.sw_version) == ("Ketel", "1.4")
    receive(SimpleNamespace(payload="{not json"))
    assert registry.async_get_device_by_identifier(("open_thermostat", "fixture_ems_08"), entry.entry_id) is not None


@pytest.mark.asyncio
async def test_the_e32_device_shows_its_firmware_version(hass):
    from test_product_flow import product
    entry = product(hass)
    registry = dr.async_get(hass)
    hub = registry.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("open_thermostat", "fixture")},
                                       name="OpenThermostat E32")
    assert hub.sw_version is None
    fake = SimpleNamespace(hass=hass, registry_entry=SimpleNamespace(device_id=hub.id),
                           _attr_installed_version="v0.1.0-e32v2-beta.22")
    E32FirmwareUpdate._sync_device_version(fake)
    assert registry.async_get(hub.id).sw_version == "v0.1.0-e32v2-beta.22"
    fake._attr_installed_version = None  # unknown: nothing is overwritten
    E32FirmwareUpdate._sync_device_version(fake)
    assert registry.async_get(hub.id).sw_version == "v0.1.0-e32v2-beta.22"
