"""Device names: "OpenThermostat E32" and "Thermometer <room>" for a sensor on its broadcast name.

Real HA registries and entity platform; synthetic E32 status only, no device.
"""
import json
import logging
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.open_thermostat import heating_link as module
from custom_components.open_thermostat.const import E32_DEVICE_NAME
from custom_components.open_thermostat.heating_link import ble_broadcast_name, ble_device_name

from test_heating_link import FULL, _setup
from test_v1_native import entry as make_entry

ID = "a4c138a3e8db"


def sensor(name):
    return {"id": ID, "name": name}


def rooms(*rows):
    return {row["id"]: row for row in rows}


WOONKAMER = {"id": "woonkamer", "name": "Woonkamer", "source": ID}


@pytest.mark.parametrize("name,broadcast", [
    ("BTE_A3E8DB", True), ("ATC_E8DB", True), ("pvvx_a3e8db", True), ("", True), (None, True), (ID, True),
    ("  BTE_A3E8DB ", True), ("BTE_112233", False), ("Woonkamer BLE", False), ("Kast", False),
    ("Thermometer bank", False), ("A3E8DB", True), ("Keuken 2", False)])
def test_only_the_broadcast_name_counts_as_no_own_name(name, broadcast):
    assert ble_broadcast_name(sensor(name)) is broadcast


def test_the_name_follows_exactly_one_room_and_never_flips_while_the_source_is_away():
    assert ble_device_name(sensor("BTE_A3E8DB"), rooms(WOONKAMER)) == "Thermometer Woonkamer"
    # A name given on the E32 always wins.
    assert ble_device_name(sensor("Kast"), rooms(WOONKAMER)) == "Kast"
    # Two rooms measure with it: no single room name.
    both = rooms(WOONKAMER, {"id": "keuken", "name": "Keuken", "source": ID})
    assert ble_device_name(sensor("BTE_A3E8DB"), both, "Thermometer Woonkamer") == "BTE_A3E8DB"
    # Source lost or on fallback for a moment: the current room name stays (None = keep).
    away = rooms({**WOONKAMER, "source": "other"})
    assert ble_device_name(sensor("BTE_A3E8DB"), away, "Thermometer Woonkamer") is None
    assert ble_device_name(sensor("BTE_A3E8DB"), rooms({"id": "woonkamer", "name": "Woonkamer"}),
                           "Thermometer Woonkamer") is None
    # ... but not for a room that no longer exists, and not for a name of the sensor's own.
    assert ble_device_name(sensor("BTE_A3E8DB"), rooms(), "Thermometer Woonkamer") == "BTE_A3E8DB"
    assert ble_device_name(sensor("BTE_A3E8DB"), away, "BTE_A3E8DB") == "BTE_A3E8DB"
    assert ble_device_name(sensor("BTE_A3E8DB"), away) == "BTE_A3E8DB"
    # A room renamed on the E32 renames the thermometer too.
    assert ble_device_name(sensor("BTE_A3E8DB"), rooms({**WOONKAMER, "name": "Living room"}),
                           "Thermometer Woonkamer") == "Thermometer Living room"


def status(name="BTE_A3E8DB", room=WOONKAMER, *more):
    value = json.loads(json.dumps(FULL))
    value["rooms"] = [{**value["rooms"][0], **room}, *more]
    value["ble_sensors"][0]["name"] = name
    return value


@pytest.mark.asyncio
async def test_a_broadcast_named_sensor_device_reads_thermometer_room_on_the_real_registry(hass, monkeypatch):
    config_entry = make_entry(hass)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    product = devices.async_get_or_create(config_entry_id=config_entry.entry_id,
                                          identifiers={("open_thermostat", "fixture")}, name=E32_DEVICE_NAME)
    _, hub, _, send = await _setup(hass, monkeypatch)
    send(status())

    def platform():
        p = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain="sensor",
                           platform_name="open_thermostat", platform=None,
                           scan_interval=timedelta(seconds=30), entity_namespace=None)
        p.config_entry = config_entry
        return p
    first = platform()
    try:
        ble = module.BleSensor(hub, hub.ble[ID], "temperature")
        await first.async_add_entities([ble])
        await hass.async_block_till_done()
        device = devices.async_get_device_by_identifier(("open_thermostat", f"fixture_e32_ble_{ID}"),
                                                        config_entry.entry_id)
        assert device.name == "Thermometer Woonkamer" and device.via_device_id == product.id
        entity_id = ble.entity_id

        def name():
            return devices.async_get(device.id).name
        # The room loses its sensor or switches to its fallback: no flip back.
        send(status(room={**WOONKAMER, "source": None, "status": "lost"}))
        await hass.async_block_till_done()
        assert name() == "Thermometer Woonkamer"
        send(status(room={**WOONKAMER, "source": "ha_entity"}))
        await hass.async_block_till_done()
        assert name() == "Thermometer Woonkamer"
        # A restart while the source is away adds the entity again: the name stays too.
        await first.async_reset()
        second = platform()
        await second.async_add_entities([module.BleSensor(hub, hub.ble[ID], "temperature")])
        await hass.async_block_till_done()
        assert name() == "Thermometer Woonkamer"
        await second.async_reset()
        first = platform()
        ble = module.BleSensor(hub, hub.ble[ID], "temperature")
        await first.async_add_entities([ble])
        await hass.async_block_till_done()
        # Room renamed on the E32, and the sensor named on the E32.
        send(status(room={**WOONKAMER, "name": "Living room"}))
        await hass.async_block_till_done()
        assert name() == "Thermometer Living room"
        send(status(name="Kast", room={**WOONKAMER, "name": "Living room"}))
        await hass.async_block_till_done()
        assert name() == "Kast"
        # Back to the broadcast name, now used by two rooms: no single room.
        send(status("BTE_A3E8DB", WOONKAMER, {"id": "keuken", "name": "Keuken", "source": ID}))
        await hass.async_block_till_done()
        assert name() == "BTE_A3E8DB"
        # The user's own name in Home Assistant always wins; the entity ID never changes.
        devices.async_update_device(device.id, name_by_user="Mijn thermometer")
        send(status())
        await hass.async_block_till_done()
        assert devices.async_get(device.id).name_by_user == "Mijn thermometer"
        assert ble.entity_id == entity_id and entities.async_get(entity_id).device_id == device.id
        assert len(dr.async_entries_for_config_entry(devices, config_entry.entry_id)) == 2
    finally:
        await first.async_reset()


@pytest.mark.asyncio
async def test_the_product_device_is_named_openthermostat_e32_and_a_user_name_stays(hass, monkeypatch):
    import custom_components.open_thermostat as integration
    from homeassistant.components import mqtt
    assert E32_DEVICE_NAME == "OpenThermostat E32"
    for user_name in (None, "E32-regelaar — ketel en diagnose"):
        parent = make_entry(hass)
        devices = dr.async_get(hass)
        hub = devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={("open_thermostat", "fixture")},
                                          name="OpenThermostat", manufacturer="OpenThermostat")
        devices.async_update_device(hub.id, name_by_user=user_name)
        monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock(return_value=True))
        monkeypatch.setattr(mqtt, "async_subscribe", AsyncMock(return_value=lambda: None))
        monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock(return_value=None))
        monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
        try:
            assert await integration.async_setup_entry(hass, parent)
            current = devices.async_get(hub.id)
            assert current.name == "OpenThermostat E32" and current.name_by_user == user_name
            assert dr.async_entries_for_config_entry(devices, parent.entry_id) == [current]
        finally:
            await integration.async_unload_entry(hass, parent)
            state = hass.data.get("open_thermostat", {}).pop(parent.entry_id, {})
            for key in ("heating_tracker", "v1_runtime"):
                if state.get(key) is not None:
                    await state[key].async_stop()
            hass.config_entries._entries.pop(parent.entry_id)
            devices.async_remove_device(hub.id)
