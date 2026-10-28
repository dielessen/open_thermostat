"""The one heating route: E32 status in, plan entities forwarded out."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.open_thermostat.heating_link import decode_status, input_payload

STATUS = {"schema": 1, "mode": "shadow", "request": {"heat": True, "flow_c": 36, "reason": "heating"},
          "ha_entities": ["climate.woonkamer"],
          "rooms": [{"id": "woonkamer", "status": "ok", "source": "climate.woonkamer",
                     "temperature": 20.4, "setpoint": 21.0, "demand": True}]}


def state(entity_id, value, **attributes):
    return SimpleNamespace(entity_id=entity_id, domain=entity_id.split(".")[0], state=value, attributes=attributes)


def test_status_is_strict():
    assert decode_status(json.dumps(STATUS)) == STATUS
    for key, bad in [("schema", 2), ("mode", "manual"), ("ha_entities", ["no_domain"]),
                     ("request", {"heat": True, "flow_c": 75, "reason": "heating"})]:
        assert decode_status(json.dumps({**STATUS, key: bad})) is None
    assert decode_status("x" * 8193) is None


def test_climate_forwards_measurement_and_target():
    payload = json.loads(input_payload(state("climate.woonkamer", "heat", current_temperature=20.4, temperature=21)))
    assert payload == {"entity": "climate.woonkamer", "temperature": 20.4, "target": 21.0}
    assert json.loads(input_payload(state("sensor.room", "19.5")))["temperature"] == 19.5
    assert input_payload(state("climate.woonkamer", "unavailable", current_temperature=20)) is None
    assert input_payload(state("climate.woonkamer", "heat", current_temperature="nan", temperature=99)) is None


@pytest.mark.asyncio
async def test_forwards_exactly_the_plan_entities(hass, monkeypatch):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat import heating_link as module
    from custom_components.open_thermostat.const import DOMAIN
    callbacks, published, tracked, added, unload = {}, [], [], [], []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

    async def subscribe(hass, topic, callback):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)

    async def publish(hass, topic, payload, qos, retain):
        published.append((topic, json.loads(payload), retain))
    monkeypatch.setattr(mqtt, "async_publish", publish)
    monkeypatch.setattr(module, "async_track_state_change_event", lambda hass, ids, cb: tracked.append(list(ids)) or (lambda: None))
    monkeypatch.setattr(module, "async_track_time_interval", lambda hass, cb, interval: lambda: None)
    hass.data[DOMAIN] = {"e": {"v1_connection": SimpleNamespace(client=object(), prefix="fixture/v1/")}}
    entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture"}, async_on_unload=unload.append)
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.4, "temperature": 21})
    await module.async_setup_heating_link(hass, entry, added.extend)
    sensor = added[0]
    callbacks["fixture/v1/fw/telemetry/heating"](SimpleNamespace(payload=json.dumps(STATUS), retain=False))
    await hass.async_block_till_done()
    assert tracked == [["climate.woonkamer"]]
    assert published == [("fixture/v1/ha/heating_input", {"entity": "climate.woonkamer", "temperature": 20.4, "target": 21.0}, False)]
    assert sensor.native_value == 36 and sensor.available
    # A retained or invalid status changes nothing; an unchanged plan is not re-tracked.
    callbacks["fixture/v1/fw/telemetry/heating"](SimpleNamespace(payload=json.dumps(STATUS), retain=True))
    callbacks["fixture/v1/fw/telemetry/heating"](SimpleNamespace(payload=json.dumps(STATUS), retain=False))
    assert tracked == [["climate.woonkamer"]]


FULL = {**STATUS, "revision": 7,
        "rooms": [{"id": "woonkamer", "name": "Woonkamer", "state": "active", "inactive_until": 0, "status": "fallback",
                   "source": "a4c138a3e8db", "temperature": 20.4, "setpoint": 21.0, "demand": True},
                  {"id": "BAD id"}, "not a room"],
        "ble_sensors": [{"id": "a4c138a3e8db", "name": "Woonkamer BLE", "profile": "pvvx_thermometer",
                         "temperature": 20.4, "humidity": 55.0, "battery": 87, "age_s": 12},
                        {"id": "112233445566", "name": "Kelder", "profile": "x", "temperature": 12.5,
                         "humidity": None, "battery": None, "age_s": None},
                        {"id": "NOT-HEX"}],
        "comparison": {"future": "keys are ignored"}}


async def _setup(hass, monkeypatch, entry_data=None):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat import heating_link as module
    from custom_components.open_thermostat.const import DOMAIN
    callbacks, added, unload = {}, [], []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

    async def subscribe(hass, topic, callback):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_publish", AsyncMock())
    monkeypatch.setattr(module, "async_track_state_change_event", lambda hass, ids, cb: lambda: None)
    monkeypatch.setattr(module, "async_track_time_interval", lambda hass, cb, interval: lambda: None)
    hass.data[DOMAIN] = {"e": {"v1_connection": SimpleNamespace(client=object(), prefix="fixture/v1/")}}
    entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture", **(entry_data or {})},
                            async_on_unload=unload.append)
    await module.async_setup_heating_link(hass, entry, added.extend)
    hub = hass.data[DOMAIN]["e"]["heating_hub"]
    return entry, hub, added, lambda status: callbacks["fixture/v1/fw/telemetry/heating"](
        SimpleNamespace(payload=json.dumps(status), retain=False))


@pytest.mark.asyncio
async def test_rooms_and_bluetooth_sensors_become_entities_for_the_ids_seen(hass, monkeypatch):
    from homeassistant.const import PERCENTAGE
    entry, hub, added, send = await _setup(hass, monkeypatch)
    assert [e.unique_id for e in added] == ["fixture_hub_heat_request"]
    send(FULL)
    by_id = {e.unique_id: e for e in added}
    assert sorted(by_id) == sorted([
        "fixture_hub_heat_request",
        "fixture_e32_room_woonkamer_temperature", "fixture_e32_room_woonkamer_setpoint",
        "fixture_e32_room_woonkamer_status",
        "fixture_e32_ble_a4c138a3e8db_temperature", "fixture_e32_ble_a4c138a3e8db_humidity",
        "fixture_e32_ble_a4c138a3e8db_battery",
        # The cellar sensor reports no humidity or battery: no entities that would stay unknown.
        "fixture_e32_ble_112233445566_temperature"])
    room_temp = by_id["fixture_e32_room_woonkamer_temperature"]
    assert room_temp.native_value == 20.4 and room_temp.available
    assert room_temp.translation_key == "room_temperature" and room_temp.translation_placeholders == {"room": "Woonkamer"}
    assert by_id["fixture_e32_room_woonkamer_setpoint"].native_value == 21.0
    status = by_id["fixture_e32_room_woonkamer_status"]
    assert status.native_value == "fallback" and status.extra_state_attributes["source"] == "a4c138a3e8db"
    battery = by_id["fixture_e32_ble_a4c138a3e8db_battery"]
    assert battery.native_value == 87 and battery.native_unit_of_measurement == PERCENTAGE
    assert battery.device_class == "battery" and battery.extra_state_attributes["age_s"] == 12
    assert by_id["fixture_e32_ble_a4c138a3e8db_humidity"].device_class == "humidity"
    assert by_id["fixture_e32_ble_a4c138a3e8db_temperature"].native_unit_of_measurement == "°C"
    assert all(e.device_info["identifiers"] == {("open_thermostat", "fixture")} for e in added)
    # The same status again adds nothing; a reading that appears later adds its entity once.
    send(FULL)
    assert len(added) == 8
    later = json.loads(json.dumps(FULL))
    later["ble_sensors"][1]["battery"] = 64
    later["rooms"][0]["status"] = "future_status"
    send(later)
    assert len(added) == 9 and added[-1].unique_id == "fixture_e32_ble_112233445566_battery"
    assert status.native_value is None  # An unknown status is not passed to the enum.
    # A room the E32 no longer reports is unavailable, not removed.
    send({**FULL, "rooms": [], "ble_sensors": []})
    assert not room_temp.available and not battery.available and by_id["fixture_hub_heat_request"].available


@pytest.mark.asyncio
async def test_stale_or_invalid_telemetry_makes_every_entity_unavailable(hass, monkeypatch):
    from custom_components.open_thermostat import heating_link as module
    entry, hub, added, send = await _setup(hass, monkeypatch)
    now = [1000.0]
    hub.clock = lambda: now[0]
    send(FULL)
    assert all(e.available for e in added)
    now[0] += module.STALE_SECONDS - 1
    hub.check_stale()
    assert all(e.available for e in added)
    now[0] += 2
    hub.check_stale()
    assert not any(e.available for e in added) and added[0].native_value is None
    send(FULL)
    assert all(e.available for e in added)
    send({"schema": 2})
    assert not any(e.available for e in added)


@pytest.mark.asyncio
async def test_room_demand_is_a_binary_sensor_on_the_same_hub(hass, monkeypatch):
    from custom_components.open_thermostat import heating_link as module
    entry, hub, added, send = await _setup(hass, monkeypatch)
    demand = []
    await module.async_setup_demand(hass, entry, demand.extend)
    assert demand == []
    send(FULL)
    assert [e.unique_id for e in demand] == ["fixture_e32_room_woonkamer_demand"]
    assert demand[0].is_on is True and demand[0].device_class == "heat"
    off = json.loads(json.dumps(FULL)); off["rooms"][0]["demand"] = False
    send(off)
    assert demand[0].is_on is False


def test_entity_names_are_translated_with_their_placeholders():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
    keys = {"sensor": {"room_temperature": "{room}", "room_setpoint": "{room}", "room_status": "{room}",
                       "ble_temperature": "{sensor}", "ble_humidity": "{sensor}", "ble_battery": "{sensor}"},
            "binary_sensor": {"room_demand": "{room}"}, "select": {"room_state": "{room}"},
            "datetime": {"room_inactive_until": "{room}"}, "number": {"room_fallback_setpoint": "{room}"}}
    for name in ("strings.json", "translations/en.json", "translations/nl.json"):
        entity = json.loads((root / name).read_text(encoding="utf-8"))["entity"]
        for platform, items in keys.items():
            for key, placeholder in items.items():
                assert placeholder in entity[platform][key]["name"], (name, key)
        assert set(entity["sensor"]["room_status"]["state"]) == {"ok", "fallback", "stale", "lost", "inactive"}
        assert set(entity["select"]["room_state"]["state"]) == {"active", "inactive"}
