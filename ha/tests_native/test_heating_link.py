"""The one heating route: E32 status in, plan entities forwarded out."""
import json
from datetime import datetime, timezone
from pathlib import Path
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


def test_fahrenheit_inputs_are_forwarded_in_celsius():
    # A °F Home Assistant: climate attributes follow the unit system.
    climate = state("climate.living_room", "heat", current_temperature=68, temperature=68)
    assert json.loads(input_payload(climate, "°F")) == {
        "entity": "climate.living_room", "temperature": 20.0, "target": 20.0}
    # A °C Home Assistant with a °F sensor or setpoint: the entity's own unit counts.
    assert json.loads(input_payload(state("sensor.attic", "68", unit_of_measurement="°F")))["temperature"] == 20.0
    assert json.loads(input_payload(state("input_number.target", "70.7", unit_of_measurement="°F")))["target"] == 21.5
    assert json.loads(input_payload(state("sensor.k", "293.15", unit_of_measurement="K")))["temperature"] == 20.0
    # °C stays as it is, also in a °F Home Assistant for an entity that says °C.
    assert json.loads(input_payload(state("sensor.room", "19.5", unit_of_measurement="°C"), "°F"))["temperature"] == 19.5
    assert json.loads(input_payload(climate, "°C"))["target"] is None  # 68 °C is no room target
    # Out of range after conversion, or not a temperature at all: nothing is sent.
    assert input_payload(state("input_number.target", "100", unit_of_measurement="°F")) is None
    assert input_payload(state("sensor.humidity", "55", unit_of_measurement="%")) is None
    assert input_payload(state("sensor.attic", "nan", unit_of_measurement="°F")) is None


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


@pytest.mark.asyncio
async def test_a_fahrenheit_home_assistant_forwards_celsius(hass, monkeypatch):
    from homeassistant.components import mqtt
    from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
    from custom_components.open_thermostat import heating_link as module
    from custom_components.open_thermostat.const import DOMAIN
    callbacks, published = {}, []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

    async def subscribe(hass, topic, callback):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)

    async def publish(hass, topic, payload, qos, retain):
        published.append(json.loads(payload))
    monkeypatch.setattr(mqtt, "async_publish", publish)
    monkeypatch.setattr(module, "async_track_state_change_event", lambda hass, ids, cb: lambda: None)
    monkeypatch.setattr(module, "async_track_time_interval", lambda hass, cb, interval: lambda: None)
    hass.config.units = US_CUSTOMARY_SYSTEM
    hass.data[DOMAIN] = {"e": {"v1_connection": SimpleNamespace(client=object(), prefix="fixture/v1/")}}
    entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture"}, async_on_unload=lambda _: None)
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 68, "temperature": 70.7})
    await module.async_setup_heating_link(hass, entry, lambda *_a, **_k: None)
    callbacks["fixture/v1/fw/telemetry/heating"](SimpleNamespace(payload=json.dumps(STATUS), retain=False))
    await hass.async_block_till_done()
    assert {"entity": "climate.woonkamer", "temperature": 20.0, "target": 21.5} in published


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
    # The room is its own device: the entity name has no room placeholder.
    assert room_temp.translation_key == "room_temperature" and not room_temp.translation_placeholders
    assert by_id["fixture_e32_room_woonkamer_setpoint"].native_value == 21.0
    status = by_id["fixture_e32_room_woonkamer_status"]
    assert status.native_value == "fallback" and status.extra_state_attributes["source"] == "a4c138a3e8db"
    battery = by_id["fixture_e32_ble_a4c138a3e8db_battery"]
    assert battery.native_value == 87 and battery.native_unit_of_measurement == PERCENTAGE
    assert battery.device_class == "battery" and battery.extra_state_attributes["age_s"] == 12
    assert by_id["fixture_e32_ble_a4c138a3e8db_humidity"].device_class == "humidity"
    assert by_id["fixture_e32_ble_a4c138a3e8db_temperature"].native_unit_of_measurement == "°C"
    devices = {e.unique_id: e.device_info for e in added}
    assert devices["fixture_hub_heat_request"]["identifiers"] == {("open_thermostat", "fixture")}
    for key in ("temperature", "setpoint", "status"):
        assert devices[f"fixture_e32_room_woonkamer_{key}"] == {
            "identifiers": {("open_thermostat", "fixture_e32_room_woonkamer")}, "name": "Woonkamer",
            "manufacturer": "intuibase"}
    assert devices["fixture_e32_ble_a4c138a3e8db_battery"]["identifiers"] == {
        ("open_thermostat", "fixture_e32_ble_a4c138a3e8db")}
    assert devices["fixture_e32_ble_a4c138a3e8db_battery"]["name"] == "Woonkamer BLE"
    assert devices["fixture_e32_ble_112233445566_temperature"]["name"] == "Kelder"
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
    # The "Heating problem" sensor is there from the start, on the product device.
    assert [e.unique_id for e in demand] == ["fixture_hub_heating_problem"]
    send(FULL)
    assert [e.unique_id for e in demand][1:] == ["fixture_e32_room_woonkamer_demand"]
    assert demand[1].is_on is True and demand[1].device_class == "heat"
    off = json.loads(json.dumps(FULL)); off["rooms"][0]["demand"] = False
    send(off)
    assert demand[1].is_on is False


COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
# The glossary names (EN, NL); the room or sensor name comes from its own device.
NAMES = {
    "sensor": {"room_temperature": ("Temperature", "Temperatuur"),
               "room_setpoint": ("Target temperature", "Gewenste temperatuur"),
               "room_status": ("Control status", "Regelstatus"),
               "ble_temperature": ("Temperature", "Temperatuur"), "ble_humidity": ("Humidity", "Luchtvochtigheid"),
               "ble_battery": ("Battery", "Batterij"),
               "heat_request": ("Boiler request (E32)", "Ketelvraag (E32)"),
               "burner_starts_last_hour": ("Burner starts last hour", "Branderstarts afgelopen uur"),
               "room_learning": ("Learning status", "Leerstatus"),
               "room_flow_advice": ("Recommended flow", "Geadviseerde aanvoer"),
               "room_heating_start": ("Predicted heating start", "Verwachte start verwarmen"),
               "dhw_taps_today": ("Hot water taps today", "Warmwatertappen vandaag"),
               "dhw_keep_warm_today": ("Keeping warm today", "Warmhouden vandaag"),
               "dhw_burner_time_today": ("Hot water burner time today", "Brandertijd warm water vandaag")},
    "binary_sensor": {"room_demand": ("Heat demand", "Warmtevraag"),
                      "burner_short_cycling": ("Burner short cycling", "Brander pendelt"),
                      "heating_problem": ("Heating problem", "Verwarmingsprobleem")},
    "select": {"room_state": ("Heating", "Verwarmen")},
    "datetime": {"room_inactive_until": ("Off until", "Uit tot")},
    "number": {"room_fallback_setpoint": ("Temperature without Home Assistant", "Temperatuur zonder Home Assistant")},
}


def test_entity_names_are_plain_glossary_names_in_both_languages():
    for name, column in (("strings.json", 0), ("translations/en.json", 0), ("translations/nl.json", 1)):
        entity = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["entity"]
        for platform, items in NAMES.items():
            for key, names in items.items():
                assert entity[platform][key]["name"] == names[column], (name, key)
                assert "{" not in entity[platform][key]["name"], (name, key)
        assert set(entity["sensor"]["room_status"]["state"]) == {"ok", "fallback", "stale", "lost", "inactive"}
        assert set(entity["select"]["room_state"]["state"]) == {"active", "inactive"}
    nl = json.loads((COMPONENT / "translations/nl.json").read_text(encoding="utf-8"))["entity"]
    assert nl["sensor"]["room_status"]["state"] == {"ok": "In orde", "fallback": "Terugvalstand",
                                                    "stale": "Meting verouderd", "lost": "Sensor kwijt",
                                                    "inactive": "Uit"}
    assert nl["select"]["room_state"]["state"] == {"active": "Aan", "inactive": "Uit"}


def test_icons_cover_the_entities_and_services():
    import re
    icons = json.loads((COMPONENT / "icons.json").read_text(encoding="utf-8"))
    strings = json.loads((COMPONENT / "strings.json").read_text(encoding="utf-8"))
    for platform, items in icons["entity"].items():
        for key, icon in items.items():
            assert key in strings["entity"][platform], (platform, key)  # only real translation keys
            assert re.fullmatch(r"mdi:[a-z0-9-]+", icon["default"]), key
            for state, value in icon.get("state", {}).items():
                assert re.fullmatch(r"mdi:[a-z0-9-]+", value), (key, state)
    for platform, items in NAMES.items():
        for key in items:
            if key not in ("room_temperature", "ble_temperature", "ble_humidity", "ble_battery"):
                assert key in icons["entity"][platform], key  # device-class icons for the plain measurements
    assert set(icons["entity"]["sensor"]["room_status"]["state"]) == set(strings["entity"]["sensor"]["room_status"]["state"])
    services = set(re.findall(r"^([a-z_]+):", (COMPONENT / "services.yaml").read_text(encoding="utf-8"), re.M))
    assert set(icons["services"]) == services


TODAY = {"day": "2026-10-28", "s": 36000, "tado_unknown_s": 600,
         "e32": {"heat_s": 5400, "starts": 4, "flow_min_c": 31, "flow_max_c": 44, "flow_mean_c": 37.5},
         "tado": {"heat_s": 6000, "starts": 5, "flow_min_c": 30, "flow_max_c": 46, "flow_mean_c": 38.2},
         "both_s": 4800, "agree_s": 33630, "e32_only_s": 600, "tado_only_s": 1200, "flow_diff_mean_c": 1.4,
         "starts_paired": 4, "starts_within_5min": 3, "start_offset_mean_s": -40, "start_offset_max_s": 420}


@pytest.mark.asyncio
async def test_todays_shadow_comparison_becomes_compact_hub_sensors(hass, monkeypatch):
    from homeassistant.components.sensor import SensorStateClass
    from custom_components.open_thermostat import heating_link as module
    entry, hub, added, send = await _setup(hass, monkeypatch)
    send(FULL)
    assert not any(e.unique_id.startswith("fixture_hub_shadow_") for e in added)  # older firmware: none
    send({**FULL, "shadow": {"today": TODAY}})
    by_id = {e.unique_id.removeprefix("fixture_hub_shadow_"): e for e in added
             if e.unique_id.startswith("fixture_hub_shadow_")}
    assert sorted(by_id) == sorted(module.SHADOW_SENSORS)
    e32, tado = by_id["e32_heating_time_today"], by_id["tado_heating_time_today"]
    assert (e32.native_value, tado.native_value) == (90.0, 100.0)
    assert e32.native_unit_of_measurement == "min" and e32.device_class == "duration"
    assert e32.state_class == SensorStateClass.TOTAL_INCREASING  # restarts at 0 every day
    assert e32.extra_state_attributes == {"day": "2026-10-28", "flow_min_c": 31, "flow_mean_c": 37.5, "flow_max_c": 44}
    starts = by_id["e32_starts_today"]
    assert (starts.native_value, by_id["tado_starts_today"].native_value) == (4, 5)
    assert starts.extra_state_attributes["start_offset_max_s"] == 420
    assert starts.extra_state_attributes["starts_within_5min"] == 3
    agreement = by_id["agreement_today"]
    assert agreement.native_value == 95.0  # 33630 / (36000 - 600)
    assert agreement.native_unit_of_measurement == "%" and agreement.state_class == SensorStateClass.MEASUREMENT
    assert agreement.extra_state_attributes["flow_diff_mean_c"] == 1.4
    assert all(e.translation_key == "shadow_" + key for key, e in by_id.items())
    assert all(e.device_info["identifiers"] == {("open_thermostat", "fixture")} for e in by_id.values())
    # Nulls (no data yet today) are unknown, not zero; the thermostat side unknown all day has no agreement.
    empty = {**TODAY, "tado_unknown_s": 36000, "e32": {"heat_s": 0, "starts": 0, "flow_min_c": None,
             "flow_max_c": None, "flow_mean_c": None}, "start_offset_mean_s": None, "start_offset_max_s": None}
    send({**FULL, "shadow": {"today": empty}})
    assert e32.native_value == 0 and e32.extra_state_attributes["flow_mean_c"] is None
    assert agreement.native_value is None and agreement.available
    # Stale telemetry, or a status without the comparison: unavailable.
    send(FULL)
    assert not any(e.available for e in by_id.values())
    send({**FULL, "shadow": {"today": TODAY}})
    now = [hub.received + module.STALE_SECONDS + 1]
    hub.clock = lambda: now[0]
    hub.check_stale()
    assert not any(e.available for e in by_id.values())


@pytest.mark.asyncio
async def test_a_home_without_a_bus_thermostat_gets_no_comparison_entities(hass, monkeypatch):
    from custom_components.open_thermostat.heating_link import shadow_has_thermostat
    entry, hub, added, send = await _setup(hass, monkeypatch)
    alone = {**TODAY, "tado_unknown_s": TODAY["s"], "tado": {"heat_s": 0, "starts": 0, "flow_min_c": None,
             "flow_max_c": None, "flow_mean_c": None}, "both_s": 0, "agree_s": 0, "tado_only_s": 0,
             "flow_diff_mean_c": None, "starts_paired": 0, "starts_within_5min": 0,
             "start_offset_mean_s": None, "start_offset_max_s": None}
    assert not shadow_has_thermostat({"shadow": {"today": alone}})
    send({**FULL, "shadow": {"today": alone}})
    send({**FULL, "shadow": {"today": {**alone, "s": 0, "tado_unknown_s": 0}}})
    assert not any(e.unique_id.startswith("fixture_hub_shadow_") for e in added)
    # The thermostat's request seen for a moment (even without heat) is enough.
    seen = {**alone, "tado_unknown_s": TODAY["s"] - 10}
    assert shadow_has_thermostat({"shadow": {"today": seen}})
    assert shadow_has_thermostat({"shadow": {"today": {**alone, "tado": {**alone["tado"], "heat_s": 60}}}})
    send({**FULL, "shadow": {"today": seen}})
    assert sum(e.unique_id.startswith("fixture_hub_shadow_") for e in added) == len(TODAY_KEYS)


TODAY_KEYS = ("e32_heating_time_today", "tado_heating_time_today", "e32_starts_today", "tado_starts_today",
              "agreement_today")


def test_shadow_sensor_names_are_translated():
    from custom_components.open_thermostat.heating_link import SHADOW_SENSORS
    names = {}
    for name in ("strings.json", "translations/nl.json"):
        sensor = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["entity"]["sensor"]
        names[name] = [sensor["shadow_" + key]["name"] for key in SHADOW_SENSORS]
    assert names["strings.json"] == ["Heating time today (E32)", "Heating time today (thermostat)",
                                     "Burner starts today (E32)", "Burner starts today (thermostat)",
                                     "Agreement with thermostat today"]
    assert names["translations/nl.json"] == ["Stooktijd vandaag (E32)", "Stooktijd vandaag (thermostaat)",
                                             "Branderstarts vandaag (E32)", "Branderstarts vandaag (thermostaat)",
                                             "Overeenstemming met thermostaat vandaag"]


@pytest.mark.asyncio
async def test_burner_cycling_entities_only_with_the_burner_telemetry(hass, monkeypatch):
    from homeassistant.components.sensor import SensorStateClass
    from custom_components.open_thermostat import heating_link as module
    entry, hub, added, send = await _setup(hass, monkeypatch)
    binary = []
    await module.async_setup_demand(hass, entry, binary.extend)
    send(FULL)
    assert not any("burner" in e.unique_id for e in added + binary)  # older firmware: none
    send({**FULL, "burner": {"short_cycling": None}})  # counted, not known yet
    starts = next(e for e in added if e.unique_id == "fixture_hub_burner_starts_last_hour")
    cycling = next(e for e in binary if e.unique_id == "fixture_hub_burner_short_cycling")
    assert not starts.available and not cycling.available and cycling.is_on is None
    assert starts.state_class == SensorStateClass.MEASUREMENT and cycling.device_class == "problem"
    assert starts.translation_key == "burner_starts_last_hour" and cycling.translation_key == "burner_short_cycling"
    assert starts.device_info["identifiers"] == cycling.device_info["identifiers"] == {("open_thermostat", "fixture")}
    send({**FULL, "burner": {"starts_last_hour": 7, "heating_starts_last_hour": 6, "short_cycling": True}})
    assert starts.available and starts.native_value == 7 and cycling.available and cycling.is_on is True
    assert cycling.extra_state_attributes == {"starts_last_hour": 7, "heating_starts_last_hour": 6}
    assert starts.extra_state_attributes["heating_starts_last_hour"] == 6
    send({**FULL, "burner": {"starts_last_hour": 1, "heating_starts_last_hour": 1, "short_cycling": False}})
    assert cycling.is_on is False and cycling.available
    send({**FULL, "burner": {"starts_last_hour": -1, "short_cycling": "yes"}})  # nonsense is unknown
    assert not starts.available and not cycling.available
    send({**FULL, "burner": {"starts_last_hour": 2, "short_cycling": False}})
    now = [hub.received + module.STALE_SECONDS + 1]
    hub.clock = lambda: now[0]
    hub.check_stale()
    assert not starts.available and not cycling.available
    assert len([e for e in added + binary if "burner" in e.unique_id]) == 2  # created once


@pytest.mark.asyncio
async def test_existing_room_entities_keep_their_entity_ids_and_move_to_a_room_device(hass, monkeypatch):
    """The owner's registry: same unique IDs, so entity IDs and history stay; the device is new."""
    import logging
    from datetime import timedelta
    from homeassistant import loader
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from homeassistant.helpers.entity_platform import EntityPlatform
    from custom_components.open_thermostat import heating_link as module
    from test_v1_native import entry as make_entry
    from homeassistant.helpers import translation
    loader.async_setup(hass)
    integration = loader.Integration(hass, "custom_components.open_thermostat", COMPONENT,
                                     json.loads((COMPONENT / "manifest.json").read_text()),
                                     top_level_files={p.name for p in COMPONENT.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={"open_thermostat": integration}))
    hass.config.language = "en"
    config_entry = make_entry(hass)
    devices, entities = dr.async_get(hass), er.async_get(hass)
    product = devices.async_get_or_create(config_entry_id=config_entry.entry_id,
                                          identifiers={("open_thermostat", "fixture")}, name="OpenThermostat")
    old_id = "sensor.woonkamer_e32_regelaar_ketel_en_diagnose_woonkamer_temperature"
    old = entities.async_get_or_create("sensor", "open_thermostat", "fixture_e32_room_woonkamer_temperature",
                                       config_entry=config_entry, device_id=product.id,
                                       suggested_object_id=old_id.split(".")[1])
    assert old.entity_id == old_id
    _, hub, _, send = await _setup(hass, monkeypatch)
    send({**FULL, "learned": {**LEARNED, "plans": PLANS}})
    platform = EntityPlatform(hass=hass, logger=logging.getLogger(__name__), domain="sensor",
                              platform_name="open_thermostat", platform=None,
                              scan_interval=timedelta(seconds=30), entity_namespace=None)
    platform.config_entry = config_entry
    await platform.platform_data.async_load_translations()
    room = hub.rooms["woonkamer"]
    sensor = hub.ble["a4c138a3e8db"]
    moved, new, ble = (module.RoomTemperatureSensor(hub, room), module.RoomStatusSensor(hub, room),
                       module.BleSensor(hub, sensor, "temperature"))
    learned = [module.RoomLearningSensor(hub, room), module.RoomFlowAdviceSensor(hub, room),
               module.RoomHeatingStartSensor(hub, room)]
    try:
        await platform.async_add_entities([moved, new, ble, *learned])
        await hass.async_block_till_done()
        room_device = devices.async_get_device_by_identifier(
            ("open_thermostat", "fixture_e32_room_woonkamer"), config_entry.entry_id)
        assert moved.entity_id == old_id and entities.async_get(old_id).device_id == room_device.id
        assert new.entity_id == "sensor.woonkamer_control_status"
        # The learned values read like the room's other entities, on the same room device.
        assert [e.entity_id for e in learned] == ["sensor.woonkamer_learning_status",
                                                  "sensor.woonkamer_recommended_flow",
                                                  "sensor.woonkamer_predicted_heating_start"]
        assert hass.states.get("sensor.woonkamer_learning_status").state == "ready"
        assert hass.states.get("sensor.woonkamer_predicted_heating_start").state == "2026-10-30T03:35:00+00:00"
        assert hass.states.get("sensor.woonkamer_recommended_flow").state == "34"
        assert {entities.async_get(e.entity_id).device_id for e in learned} == {
            devices.async_get_device_by_identifier(("open_thermostat", "fixture_e32_room_woonkamer"),
                                                   config_entry.entry_id).id}
        assert hass.states.get(old_id).attributes["friendly_name"] == "Woonkamer Temperature"
        assert room_device.via_device_id == product.id and room_device.name == "Woonkamer"
        ble_device = devices.async_get_device_by_identifier(
            ("open_thermostat", "fixture_e32_ble_a4c138a3e8db"), config_entry.entry_id)
        assert ble.entity_id == "sensor.woonkamer_ble_temperature" and ble_device.via_device_id == product.id
        # A room renamed on the E32 renames its device; a name the user gave it stays shown.
        renamed = json.loads(json.dumps(FULL))
        renamed["rooms"][0]["name"] = "Living room"
        send(renamed)
        await hass.async_block_till_done()
        assert devices.async_get(room_device.id).name == "Living room" and moved.entity_id == old_id
        devices.async_update_device(room_device.id, name_by_user="Zitkamer")
        send(FULL)
        await hass.async_block_till_done()
        assert devices.async_get(room_device.id).name_by_user == "Zitkamer"
        # Only a room the E32 no longer reports may be deleted by the user, and only while it reports.
        assert not module.removable_device(hass, config_entry, room_device)
        assert not module.removable_device(hass, config_entry, product)
        hass.data["open_thermostat"][config_entry.entry_id] = {"heating_hub": hub}
        send({**FULL, "rooms": []})
        assert module.removable_device(hass, config_entry, devices.async_get(room_device.id))
        assert not module.removable_device(hass, config_entry, product)
        assert not module.removable_device(hass, config_entry, ble_device)  # still reported
        hub.update(None)
        assert not module.removable_device(hass, config_entry, devices.async_get(room_device.id))
    finally:
        await platform.async_reset()


SWITCH_UTC = int(datetime(2026, 10, 30, 5, 30, tzinfo=timezone.utc).timestamp())


def _advice(shortfall, required, flow, warmup, rule_flow, rule_warmup, rule, reason="learned"):
    return {"shortfall_c": shortfall, "required_c_per_h": required, "flow_c": flow, "warmup_h": warmup,
            "reason": reason, "rule_flow_c": rule_flow, "rule_warmup_h": rule_warmup, "rule": rule}


# FlowLearner::json() as the E32 publishes it over MQTT (rooms[].curve trimmed).
LEARNED = {
    "schema": 1, "applied": False, "status": "learning", "heating_periods": 5, "outdoor_c": 8.5,
    "gas_calibration": 1, "gas_intervals": 0,
    "rooms": [
        {"id": "woonkamer", "emitter": "floor", "readiness": "ready", "segments": 9, "periods": 4, "rejected": 2,
         "last": "segment_learned", "segment_open": False, "accept_base_min": 60, "accept_per_degree_min": 60,
         "outdoor_slope_c_per_h_per_k": None, "loss_per_h": 0.0312, "capacity_kwh_per_k": 1.85,
         "cool_segments": 3, "power_segments": 4,
         "advice": [_advice(0, 0, 30, 0, 30, 0, "similar", "lowest_learned"),
                    _advice(0.5, 0.33, 32, 1.4, 35, 1.1, "higher_wasteful"),
                    _advice(1, 0.5, 34, 1.9, 40, 1.2, "higher_wasteful"),
                    _advice(2, 0.67, 38, 2.9, 50, 1.8, "higher_wasteful")],
         "now": _advice(0.4, 0.3, 32, 1.2, 34, 1.0, "similar")},
        # A room the E32 learns but does not report in its rooms: no entities.
        {"id": "zolder", "emitter": "radiator", "readiness": "collecting", "segments": 0, "periods": 0,
         "advice": [], "now": None}],
}
NIGHT = {"reason": "estimated", "confidence": "low",
         "strategies": [{"name": "program", "night_c": 17, "kwh": 6.1, "m3": 0.66, "eur": None, "end_c": 20.5,
                         "on_time": True},
                        {"name": "hold_0_5", "night_c": 17.5, "kwh": 5.0, "m3": 0.54, "eur": None, "end_c": 20.5,
                         "on_time": True},
                        {"name": "hold_1_0", "night_c": 18, "kwh": 5.4, "m3": 0.58, "eur": None, "end_c": 20.5,
                         "on_time": True},
                        {"name": "tado_like", "night_c": 17, "kwh": 5.2, "m3": 0.56, "eur": None, "end_c": 19.6,
                         "on_time": False}],
         "recommended": "hold_0_5", "recommended_night_c": 17.5, "saving_m3": 0.12, "saving_eur": None}
START = {"reason": "planned",
         "next_switch": {"time": "fri 06:30", "utc": SWITCH_UTC, "from_c": 17, "target_c": 20.5},
         "predicted_start": "fri 04:35", "predicted_start_utc": SWITCH_UTC - 115 * 60, "lead_minutes": 115,
         "start_temperature_c": 17.6, "flow_c": 36, "confidence": "learned", "reachable": True, "start_now": False}
PLANS = {"rooms": [{"id": "woonkamer", "optimum_start": START, "night": NIGHT}]}


def _learned_ids(added):
    return sorted(e.unique_id for e in added if e.unique_id.rsplit("_", 1)[-1] in ("learning", "advice", "start"))


@pytest.mark.asyncio
async def test_learned_advice_becomes_room_entities_once_the_e32_reports_it(hass, monkeypatch):
    from homeassistant.components.sensor import SensorStateClass
    from custom_components.open_thermostat import heating_link as module
    entry, hub, added, send = await _setup(hass, monkeypatch)
    send(FULL)
    assert _learned_ids(added) == []  # older firmware: none
    send({**FULL, "learned": LEARNED})  # no trusted clock yet: no plans
    assert _learned_ids(added) == ["fixture_e32_room_woonkamer_flow_advice", "fixture_e32_room_woonkamer_learning"]
    by_id = {e.unique_id: e for e in added}
    learning, advice = by_id["fixture_e32_room_woonkamer_learning"], by_id["fixture_e32_room_woonkamer_flow_advice"]
    assert learning.native_value == "ready" and learning.options == ["collecting", "learning", "ready"]
    assert learning.device_class == "enum" and learning.translation_key == "room_learning"
    assert learning.extra_state_attributes == {
        "room_id": "woonkamer", "emitter": "floor", "segments": 9, "periods": 4, "heating_periods": 5,
        "learner": "learning", "loss_per_h": 0.0312, "capacity_kwh_per_k": 1.85, "applied": False}
    assert learning.device_info["identifiers"] == {("open_thermostat", "fixture_e32_room_woonkamer")}
    assert advice.native_value == 34 and advice.native_unit_of_measurement == "°C"
    assert advice.device_class == "temperature" and advice.state_class == SensorStateClass.MEASUREMENT
    attributes = advice.extra_state_attributes
    keys = ("shortfall_c", "warmup_h", "reason", "rule_flow_c", "rule_warmup_h", "rule", "applied")
    assert {k: attributes[k] for k in keys} == {
        "shortfall_c": 1, "warmup_h": 1.9, "reason": "learned", "rule_flow_c": 40, "rule_warmup_h": 1.2, "rule": "higher_wasteful",
        "applied": False}
    assert [a["shortfall_c"] for a in attributes["other_shortfalls"]] == [0, 0.5, 2]
    assert attributes["other_shortfalls"][2] == _advice(2, 0.67, 38, 2.9, 50, 1.8, "higher_wasteful")
    assert attributes["now"]["shortfall_c"] == 0.4

    # With a trusted clock: the predicted heating start, and tonight's options.
    send({**FULL, "learned": {**LEARNED, "plans": PLANS}})
    start = next(e for e in added if e.unique_id == "fixture_e32_room_woonkamer_heating_start")
    assert start.device_class == "timestamp" and start.translation_key == "room_heating_start"
    assert start.native_value == datetime(2026, 10, 30, 3, 35, tzinfo=timezone.utc)
    attributes = start.extra_state_attributes
    assert attributes["switch_at"] == "2026-10-30T05:30:00+00:00" and attributes["target_c"] == 20.5
    assert (attributes["lead_minutes"], attributes["flow_c"], attributes["confidence"]) == (115, 36, "learned")
    assert (attributes["night_recommended"], attributes["night_recommended_c"]) == ("hold_0_5", 17.5)
    assert attributes["night_saving_m3"] == 0.12 and attributes["night_saving_eur"] is None
    assert [s["name"] for s in attributes["night_strategies"]] == ["program", "hold_0_5", "hold_1_0", "tado_like"]
    assert attributes["night_strategies"][3] == NIGHT["strategies"][3]
    # Without the exact time: the switch time minus the lead.
    rounded = {**START, "predicted_start_utc": None, "lead_minutes": 120}
    send({**FULL, "learned": {**LEARNED, "plans": {"rooms": [{"id": "woonkamer", "optimum_start": rounded,
                                                                "night": {"reason": "not_learned"}}]}}})
    assert start.native_value == datetime(2026, 10, 30, 3, 30, tzinfo=timezone.utc)
    assert "night_strategies" not in start.extra_state_attributes
    # The compact MQTT form: no next_switch, no strategies; recommended_c for the night setpoint.
    compact = {"id": "woonkamer",
               "optimum_start": {k: START[k] for k in ("reason", "predicted_start_utc", "lead_minutes", "flow_c",
                                                       "confidence", "reachable", "start_now")},
               "night": {"reason": "estimated", "recommended": "hold_0_5", "recommended_c": 17.5,
                         "saving_m3": 0.12, "saving_eur": 0.17}}
    send({**FULL, "learned": {**LEARNED, "plans": {"rooms": [compact]}}})
    assert start.available and start.native_value == datetime(2026, 10, 30, 3, 35, tzinfo=timezone.utc)
    assert start.extra_state_attributes == {
        "room_id": "woonkamer", "reason": "planned", "lead_minutes": 115, "flow_c": 36, "confidence": "learned",
        "reachable": True, "start_now": False, "night_reason": "estimated", "night_recommended": "hold_0_5",
        "night_recommended_c": 17.5, "night_saving_m3": 0.12, "night_saving_eur": 0.17}
    # Compact, without the exact time: unknown (there is no switch time to count back from).
    send({**FULL, "learned": {**LEARNED, "plans": {"rooms": [{**compact, "optimum_start": {
        **compact["optimum_start"], "predicted_start_utc": None}}]}}})
    assert start.available and start.native_value is None
    # Nothing to plan: known to be unknown, not unavailable.
    send({**FULL, "learned": {**LEARNED, "plans": {"rooms": [{"id": "woonkamer", "optimum_start": {
        "reason": "no_rise_within_24h"}, "night": {"reason": "no_rise_within_24h"}}]}}})
    assert start.available and start.native_value is None
    assert start.extra_state_attributes["reason"] == "no_rise_within_24h"
    # Plans dropped from a message (size): only the start is unavailable.
    send({**FULL, "learned": LEARNED})
    assert not start.available and learning.available and advice.available

    # Still learning: the advice is unknown, not a number; nonsense is unknown too.
    collecting = json.loads(json.dumps(LEARNED))
    collecting["rooms"][0].update(readiness="collecting", segments=0,
                                  advice=[_advice(1, 0.5, None, None, 40, None, "unknown", "not_ready")])
    send({**FULL, "learned": collecting})
    assert learning.native_value == "collecting" and advice.native_value is None and advice.available
    assert advice.extra_state_attributes["rule_flow_c"] == 40
    collecting["rooms"][0].update(readiness="bogus", advice=[_advice(1, 0.5, 500, -3, 40, None, 7)])
    send({**FULL, "learned": collecting})
    assert learning.native_value is None and advice.native_value is None
    assert advice.extra_state_attributes["warmup_h"] is None and advice.extra_state_attributes["rule"] is None

    # Another schema, a status without it, or stale telemetry: unavailable.
    send({**FULL, "learned": {**LEARNED, "schema": 2}})
    assert not learning.available and not advice.available
    send({**FULL, "learned": {**LEARNED, "plans": PLANS}})
    assert learning.available and advice.available and start.available
    now = [hub.received + module.STALE_SECONDS + 1]
    hub.clock = lambda: now[0]
    hub.check_stale()
    assert not any(e.available for e in (learning, advice, start))
    assert len(_learned_ids(added)) == 3  # created once


DHW = {"method": "flow", "clock_known": True, "active_s": None,
       "today": {"tapping": {"count": 6, "s": 540}, "keep_warm": {"count": 2, "s": 300},
                 "unknown": {"count": 1, "s": 20}, "burner_s": 750, "peak_flow_l_min": 7.5},
       "last_7_days": {"tapping": {"count": 40, "s": 3600}, "keep_warm": {"count": 15, "s": 2000},
                       "unknown": {"count": 1, "s": 20}, "burner_s": 5100, "peak_flow_l_min": 8.1}}


@pytest.mark.asyncio
async def test_todays_hot_water_becomes_product_sensors_once_reported(hass, monkeypatch):
    from homeassistant.components.sensor import SensorStateClass
    from custom_components.open_thermostat import heating_link as module
    entry, hub, added, send = await _setup(hass, monkeypatch)
    send(FULL)
    assert not any("_hub_dhw_" in e.unique_id for e in added)  # older firmware: none
    send({**FULL, "dhw": DHW})
    by_key = {e.unique_id.removeprefix("fixture_hub_"): e for e in added if "_hub_dhw_" in e.unique_id}
    assert sorted(by_key) == sorted(module.DHW_SENSORS)
    taps, warm, burner = (by_key[k] for k in module.DHW_SENSORS)
    assert (taps.native_value, warm.native_value, burner.native_value) == (6, 2, 12.5)
    assert all(e.state_class == SensorStateClass.TOTAL_INCREASING for e in by_key.values())  # daily counters
    assert burner.device_class == "duration" and burner.native_unit_of_measurement == "min"
    assert taps.native_unit_of_measurement is None and taps.translation_key == "dhw_taps_today"
    assert all(e.device_info["identifiers"] == {("open_thermostat", "fixture")} for e in by_key.values())
    assert taps.extra_state_attributes == {"method": "flow", "clock_known": True, "minutes": 9.0, "last_7_days": 40,
                                           "peak_flow_l_min": 7.5, "unknown_count": 1}
    assert warm.extra_state_attributes == {"method": "flow", "clock_known": True, "minutes": 5.0, "last_7_days": 15}
    assert burner.extra_state_attributes == {"method": "flow", "clock_known": True, "tapping_minutes": 9.0,
                                             "keep_warm_minutes": 5.0, "last_7_days_minutes": 85.0}
    # A new day starts at zero; no flow meter: no peak flow; nonsense is unknown.
    fallen = {"method": "dhw_temperature_fall", "clock_known": True,
              "today": {"tapping": {"count": 0, "s": 0}, "keep_warm": {"count": -1, "s": 0},
                        "unknown": {"count": 0, "s": 0}, "burner_s": 0, "peak_flow_l_min": None}}
    send({**FULL, "dhw": fallen})
    assert (taps.native_value, warm.native_value, burner.native_value) == (0, None, 0)
    assert taps.extra_state_attributes["peak_flow_l_min"] is None and taps.extra_state_attributes["last_7_days"] is None
    # Without the summary, or stale: unavailable.
    send({**FULL, "dhw": {"method": "flow"}})
    assert not any(e.available for e in by_key.values())
    send({**FULL, "dhw": DHW})
    assert all(e.available for e in by_key.values())
    now = [hub.received + module.STALE_SECONDS + 1]
    hub.clock = lambda: now[0]
    hub.check_stale()
    assert not any(e.available for e in by_key.values())
    assert len([e for e in added if "_hub_dhw_" in e.unique_id]) == 3  # created once


def test_learning_states_and_icons_in_both_languages():
    icons = json.loads((COMPONENT / "icons.json").read_text(encoding="utf-8"))["entity"]["sensor"]
    states = {}
    for name in ("strings.json", "translations/en.json", "translations/nl.json"):
        sensor = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["entity"]["sensor"]
        states[name] = sensor["room_learning"]["state"]
        assert list(states[name]) == ["collecting", "learning", "ready"], name
    assert states["strings.json"] == states["translations/en.json"] == {
        "collecting": "Collecting data", "learning": "Learning", "ready": "Ready"}
    assert states["translations/nl.json"] == {"collecting": "Gegevens verzamelen", "learning": "Aan het leren",
                                              "ready": "Klaar"}
    assert set(icons["room_learning"]["state"]) == set(states["strings.json"])
    from custom_components.open_thermostat.heating_link import LEARNING_STATES
    assert LEARNING_STATES == list(states["strings.json"])

# -- learned rooms on their own topic (MQTT size limit) --


def test_learned_room_messages_are_strict():
    from custom_components.open_thermostat.heating_link import decode_learned
    room = {"id": "woonkamer", "emitter": "floor", "readiness": "ready", "advice": []}
    message = {"schema": 1, "id": "woonkamer", "learned": room, "plan": None}
    assert decode_learned("woonkamer", json.dumps(message)) == (room, None)
    assert decode_learned("woonkamer", json.dumps({**message, "plan": PLANS["rooms"][0]}))[1]["id"] == "woonkamer"
    for bad in ({**message, "schema": 2}, {**message, "id": "zolder"}, {**message, "learned": []},
                {**message, "plan": "x"}, "not json"):
        assert decode_learned("woonkamer", bad if type(bad) is str else json.dumps(bad)) is None
    assert decode_learned("BAD id", json.dumps(message)) is None
    assert decode_learned("woonkamer", "x" * 9000) is None


async def _setup_topics(hass, monkeypatch):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat import heating_link as module
    from custom_components.open_thermostat.const import DOMAIN
    callbacks, added = {}, []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

    async def subscribe(hass, topic, callback):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_publish", AsyncMock())
    monkeypatch.setattr(module, "async_track_state_change_event", lambda hass, ids, cb: lambda: None)
    monkeypatch.setattr(module, "async_track_time_interval", lambda hass, cb, interval: lambda: None)
    hass.data[DOMAIN] = {"e": {"v1_connection": SimpleNamespace(client=object(), prefix="fixture/v1/")}}
    entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture"}, async_on_unload=lambda f: None)
    await module.async_setup_heating_link(hass, entry, added.extend)
    hub = hass.data[DOMAIN]["e"]["heating_hub"]
    now = [1000.0]
    hub.clock = lambda: now[0]

    def status(value):
        callbacks["fixture/v1/fw/telemetry/heating"](SimpleNamespace(payload=json.dumps(value), retain=False))

    def learned(room_id, value, retain=False):
        callbacks["fixture/v1/fw/telemetry/heating_learned/+"](SimpleNamespace(
            topic=f"fixture/v1/fw/telemetry/heating_learned/{room_id}", payload=json.dumps(value), retain=retain))
    return hub, added, now, status, learned


@pytest.mark.asyncio
async def test_learned_rooms_arrive_per_room_and_expire_on_their_own(hass, monkeypatch):
    hub, added, now, status, learned = await _setup_topics(hass, monkeypatch)
    # The newer status keeps only the learned header (and no room details the plan holds).
    header = {"schema": 1, "applied": False, "status": "learning", "heating_periods": 5}
    room = {k: v for k, v in FULL["rooms"][0].items() if k not in ("inactive_until",)}
    status({**FULL, "rooms": [room], "learned": header})
    assert _learned_ids(added) == []
    woonkamer = LEARNED["rooms"][0]
    message = {"schema": 1, "id": "woonkamer", "plan": {"optimum_start": START, "night": NIGHT},
               "learned": {**{k: woonkamer[k] for k in ("id", "emitter", "readiness", "segments", "periods",
                                                       "loss_per_h", "capacity_kwh_per_k", "now")},
                           "advice": [woonkamer["advice"][2]]}}
    learned("woonkamer", message, retain=True)  # retained: ignored
    assert hub.learned == {}
    learned("woonkamer", message)
    assert _learned_ids(added) == ["fixture_e32_room_woonkamer_flow_advice", "fixture_e32_room_woonkamer_heating_start",
                                   "fixture_e32_room_woonkamer_learning"]
    by_id = {e.unique_id: e for e in added}
    advice, learning = by_id["fixture_e32_room_woonkamer_flow_advice"], by_id["fixture_e32_room_woonkamer_learning"]
    start = by_id["fixture_e32_room_woonkamer_heating_start"]
    assert advice.native_value == 34 and advice.extra_state_attributes["rule"] == "higher_wasteful"
    assert learning.native_value == "ready" and learning.extra_state_attributes["applied"] is False
    assert start.available and start.extra_state_attributes["night_recommended_c"] == 17.5
    # A message without a plan (no trusted clock) removes the room's plan only.
    learned("woonkamer", {**message, "plan": None})
    assert not start.available and advice.available
    # A message for another room or with a wrong id changes nothing.
    learned("zolder", {**message, "id": "woonkamer"})
    assert set(hub.learned) == {"woonkamer"}
    # The main status every 15 s keeps the learned room; its own message expires after 180 s.
    now[0] += 170
    status({**FULL, "rooms": [room], "learned": header})
    hub.check_stale()
    assert advice.available
    now[0] += 20
    hub.check_stale()
    assert hub.learned == {} and not advice.available and not learning.available
    # Older firmware (learned rooms inside the status) still works.
    status({**FULL, "rooms": [room], "learned": LEARNED})
    assert advice.available and advice.native_value == 34


@pytest.mark.asyncio
async def test_room_details_left_out_of_the_mqtt_rooms_come_from_the_plan(hass, monkeypatch):
    from custom_components.open_thermostat.heating_link import RoomStatusSensor
    from custom_components.open_thermostat.room_plan import RoomPlanLink, until_datetime
    hub, added, now, status, learned = await _setup_topics(hass, monkeypatch)
    room = {k: v for k, v in FULL["rooms"][0].items() if k != "inactive_until"}
    status({**FULL, "rooms": [{**room, "state": "inactive"}]})
    link = RoomPlanLink.__new__(RoomPlanLink)
    link.hub = hub
    link.plan = {"revision": 7, "rooms": [{"id": "woonkamer", "state": "inactive", "inactive_until": 1893456000,
                                           "fallback_centi_c": 1900, "minimum_centi_c": 1500,
                                           "maximum_centi_c": 2400}]}
    hub.plan = link
    operation = link.operation("woonkamer")
    assert operation["inactive_until"] == 1893456000 and until_datetime(operation) is not None
    assert RoomStatusSensor(hub, hub.rooms["woonkamer"]).extra_state_attributes["inactive_until"] == 1893456000
    # A status that still carries it keeps the live value.
    status({**FULL, "rooms": [{**room, "state": "inactive", "inactive_until": 0}]})
    assert link.operation("woonkamer")["inactive_until"] == 0
    hub.plan = None
