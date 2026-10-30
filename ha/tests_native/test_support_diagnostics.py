"""The diagnostics download for an E32: useful for help, and no secret, address or key in it."""
import json
from types import SimpleNamespace

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat import diagnostics
from custom_components.open_thermostat import support_diagnostics as module
from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
from custom_components.open_thermostat.energy_input import CONF_BOILER_KW, CONF_GAS_METER
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.product import PRODUCT_CONFIG
from test_v1_native import entry

BLE_ID = "a4c138a3e8db"
SECRETS = ("never-export-password", "192.168.1.206", BLE_ID, "A4:C1:38:A3:E8:DB", "a4:c1:38:a3:e8:db",
           "MyHomeWiFi", "00112233445566778899aabbccddeeff", "10.0.0.2", "mqtt://", "broker-user", "broker-pass",
           "fe80::1ff:fe23:4567:890a", "tok3n-value", "bssid-value", "http://e32.local")


INSTALL = {"tag": "v0.1.0-e32v2-beta.19", "from_version": "v0.1.0-e32v2-beta.18", "sha256": "ab" * 32,
           "size": 1_843_200, "started_at": "2026-10-29T18:00:00Z", "finished_at": "2026-10-29T18:01:12Z",
           "duration_s": 72.4, "result": "installed", "uploads": 1,
           "reported": {"version": "v0.1.0-e32v2-beta.19", "source_commit": "0123456789abcdef0123456789abcdef01234567",
                        "web_sha256": "cd" * 32, "elf_sha256": "ef" * 32}}


def product_entry(hass):
    parent = entry(hass)
    hass.config_entries.async_update_entry(parent, data={
        **parent.data, PRODUCT_CONFIG: 1, CONTROLLER_ADDRESS: "http://192.168.1.206",
        CONTROLLER_PASSWORD: "never-export-password"},
        options={**parent.options, CONF_GAS_METER: "sensor.gas", CONF_BOILER_KW: 24})
    hub = HeatingHub("fixture")
    hub.update({"schema": 1, "revision": 4, "mode": "shadow",
                "request": {"heat": True, "flow_c": 38, "reason": "heating"}, "ha_entities": ["climate.woonkamer"],
                "rooms": [{"id": "woonkamer", "name": "Woonkamer", "source": f"ble:{BLE_ID}", "temperature": 20.1}],
                "ble_sensors": [{"id": BLE_ID, "name": "Slaapkamer", "temperature": 19.4,
                                 "bind_key": "00112233445566778899aabbccddeeff", "mac": "A4:C1:38:A3:E8:DB"}],
                "wifi": {"ssid": "MyHomeWiFi", "bssid": "bssid-value", "ip": "192.168.1.206", "rssi": -61,
                         "note": "gateway 10.0.0.2, link fe80::1ff:fe23:4567:890a, mac a4:c1:38:a3:e8:db"},
                "mqtt": {"broker": "mqtt://broker-user:broker-pass@10.0.0.2:1883", "username": "broker-user",
                         "password": "broker-pass", "token": "tok3n-value"}})
    hub.summary = {"schema": 1, "learned": {"schema": 1, "applied": False, "status": "learning",
                                            "inputs": {"gas_meter": True, "boiler_kw": 24, "boiler_kw_source": "ha"}},
                   "dhw": {"method": "flow", "today": {"tapping": {"count": 3, "s": 120}}}}
    hub.summary_received = hub.clock()
    hub.plan = SimpleNamespace(login_rejected=False, plan={
        "schema": 1, "revision": 4, "mode": "shadow", "maximum_flow_c": 60,
        "rooms": [{"id": "woonkamer", "name": "Woonkamer", "emitter": "floor", "sources": [f"ble:{BLE_ID}", "x"],
                   "schedule": [{"day": 0}], "bind_key": "00112233445566778899aabbccddeeff"}]})
    hass.data.setdefault("open_thermostat", {})[parent.entry_id] = {"heating_hub": hub}
    hass.states.async_set("sensor.gas", "1234.5", {"unit_of_measurement": "m³", "device_class": "gas",
                                                   "state_class": "total_increasing"})
    return parent, hub


@pytest.mark.asyncio
async def test_the_e32_diagnostics_help_and_contain_no_secret(hass):
    parent, hub = product_entry(hass)
    registry = er.async_get(hass)
    update = registry.async_get_or_create("update", "open_thermostat", "fixture_firmware", config_entry=parent)
    hass.states.async_set(update.entity_id, "on", {
        "installed_version": "v0.1.0-e32v2-beta.18", "latest_version": "v0.1.0-e32v2-beta.19",
        "last_install": {**INSTALL, "reported": {**INSTALL["reported"], "address": "192.168.1.206"}}})
    stale = registry.async_get_or_create("sensor", "open_thermostat", "fixture_hub_old", config_entry=parent)
    registry.async_get_or_create("sensor", "open_thermostat", "fixture_hub_off", config_entry=parent,
                                 disabled_by=er.RegistryEntryDisabler.USER)
    result = await diagnostics.async_get_config_entry_diagnostics(hass, parent)
    text = json.dumps(result)
    for secret in SECRETS:
        assert secret not in text, secret
    assert "controller_password" not in text
    e32 = result["e32"]
    assert e32["firmware"]["installed_version"] == "v0.1.0-e32v2-beta.18"
    assert e32["firmware"]["last_install"]["result"] == "installed"
    # Not as the update entity writes it (an extra field): shown, redacted and marked invalid.
    assert e32["firmware"]["last_install"]["reported"]["address"] == module.REDACTED
    assert e32["firmware"]["last_install_valid"] is False
    assert e32["plan"]["rooms"] == [{"id": "woonkamer", "name": "Woonkamer", "emitter": "floor", "sources": 2,
                                      "schedule": 1, "bind_key": module.REDACTED}]
    assert e32["plan"]["maximum_flow_c"] == 60 and e32["plan"]["read"] is True
    status = e32["telemetry"]["status"]
    assert status["request"]["flow_c"] == 38 and status["ble_sensors"][0]["id"] == "ble_1"
    assert status["rooms"][0]["source"] == "ble:ble_1" and status["wifi"]["rssi"] == -61
    assert e32["telemetry"]["summary"]["learned"]["inputs"]["boiler_kw"] == 24
    assert e32["inputs"]["options"] == {CONF_GAS_METER: "sensor.gas", CONF_BOILER_KW: 24}
    assert e32["inputs"]["entities"][CONF_GAS_METER]["unit_of_measurement"] == "m³"
    assert e32["inputs"]["on_e32"]["boiler_kw_source"] == "ha"
    counts = e32["entities"]
    assert counts["per_domain"] == {"sensor": 2, "update": 1} and counts["total"] == 3
    assert counts["unavailable"] == [stale.entity_id] and len(counts["disabled"]) == 1
    assert e32["energy"] is None and e32["advice"] is None
    # The native part is still there.
    assert "integration_mode" in result and "dhw" in result


@pytest.mark.asyncio
async def test_device_diagnostics_name_the_device_without_its_address(hass):
    parent, hub = product_entry(hass)
    devices = dr.async_get(hass)
    product = devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={("open_thermostat", "fixture")},
                                          name="OpenThermostat", model="E32", sw_version="v0.1.0-e32v2-beta.18")
    sensor = devices.async_get_or_create(config_entry_id=parent.entry_id, name="Slaapkamer",
                                         identifiers={("open_thermostat", f"fixture_e32_ble_{BLE_ID}")})
    result = await diagnostics.async_get_device_diagnostics(hass, parent, sensor)
    text = json.dumps(result)
    for secret in SECRETS:
        assert secret not in text, secret
    assert result["device"]["kind"] == "bluetooth_sensor" and result["device"]["identifiers"] == ["fixture_e32_ble_ble_1"]
    assert result["e32"]["firmware"]["device_sw_version"] == "v0.1.0-e32v2-beta.18"
    result = await diagnostics.async_get_device_diagnostics(hass, parent, product)
    assert result["device"]["kind"] == "e32" and result["device"]["name"] == "OpenThermostat"
    # A sensor the E32 no longer reports keeps no readable address either.
    hub.ble = {}
    result = await diagnostics.async_get_device_diagnostics(hass, parent, sensor)
    assert BLE_ID not in json.dumps(result)


def test_scrub_removes_addresses_and_keys_but_keeps_ordinary_values():
    value = {"time": "2026-10-29T12:30:45+00:00", "version": "v0.1.0-e32v2-beta.18", "ha": "2026.10.4",
             "sha256": "ab" * 32, "page": "https://github.com/dielessen/open_thermostat/releases/tag/v1",
             "url_in_text": "see http://192.168.1.2/status", "nested": [{"Password": "x", "password": "y"}],
             "ble_" + BLE_ID: 1, "flow": 38.5, "aes": "00112233445566778899aabbccddeeff"}
    result = module.scrub(value, {BLE_ID: "ble_1"})
    assert result["time"] == value["time"] and result["version"] == value["version"] and result["ha"] == "2026.10.4"
    assert result["sha256"] == value["sha256"] and result["page"] == value["page"] and result["flow"] == 38.5
    assert result["url_in_text"] == "see " + module.REDACTED and result["nested"][0]["password"] == module.REDACTED
    assert "ble_ble_1" in result and result["aes"] == module.REDACTED


@pytest.mark.asyncio
async def test_the_last_install_record_of_the_update_entity_is_in_the_download_complete(hass, monkeypatch):
    from custom_components.open_thermostat.firmware_update import INSTALL_RECORD, valid_install_record
    assert valid_install_record(INSTALL) and set(INSTALL) == set(INSTALL_RECORD)
    assert module._update_entity(hass, "update.none") is None  # no update platform loaded
    parent, _ = product_entry(hass)
    update = er.async_get(hass).async_get_or_create("update", "open_thermostat", "fixture_firmware", config_entry=parent)
    # From the state attribute (as recorded and restored) ...
    hass.states.async_set(update.entity_id, "off", {"installed_version": INSTALL["tag"], "last_install": INSTALL})
    result = await diagnostics.async_get_config_entry_diagnostics(hass, parent)
    firmware = result["e32"]["firmware"]
    assert firmware["last_install"] == INSTALL and firmware["last_install_valid"] is True
    for secret in SECRETS:
        assert secret not in json.dumps(result), secret
    # ... and from the live entity's property, which wins (also before its state is written).
    failed = {**INSTALL, "result": "not_confirmed", "reported": None}
    hass.states.async_set(update.entity_id, "off", {"installed_version": INSTALL["tag"]})
    monkeypatch.setattr(module, "_update_entity",
                        lambda hass, entity_id: SimpleNamespace(last_install=failed)
                        if entity_id == update.entity_id else None)
    firmware = (await diagnostics.async_get_device_diagnostics(
        hass, parent, dr.async_get(hass).async_get_or_create(
            config_entry_id=parent.entry_id, identifiers={("open_thermostat", "fixture")})))["e32"]["firmware"]
    assert firmware["last_install"] == failed and firmware["last_install_valid"] is True
    # No install through Home Assistant yet: nothing, not an error.
    monkeypatch.setattr(module, "_update_entity", lambda hass, entity_id: None)
    firmware = (await diagnostics.async_get_config_entry_diagnostics(hass, parent))["e32"]["firmware"]
    assert firmware["last_install"] is None and firmware["last_install_valid"] is None
