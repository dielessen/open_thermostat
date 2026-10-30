"""The beta.19 telemetry budget on the HA side: small retained topics, heartbeat liveness."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.open_thermostat import heating_link as module
from e32_telemetry import FakeE32, split_status

STATUS = {"schema": 1, "revision": 7, "mode": "shadow", "request": {"heat": True, "flow_c": 36, "reason": "heating"},
          "ha_entities": ["climate.woonkamer", "sensor.keuken"],
          "rooms": [{"id": "woonkamer", "name": "Woonkamer", "state": "active", "status": "ok", "source": "climate.woonkamer",
                     "temperature": 20.4, "setpoint": 21.0, "setpoint_source": "ha", "demand": True},
                    {"id": "keuken", "name": "Keuken", "state": "active", "status": "fallback", "source": None,
                     "temperature": None, "setpoint": 19.0, "setpoint_source": "fallback", "demand": False}],
          "ble_sensors": [{"id": "a4c138a3e8db", "name": "Woonkamer BLE", "profile": "pvvx_thermometer",
                           "temperature": 20.4, "humidity": 55.0, "battery": 87, "age_s": 12}],
          "burner": {"starts_last_hour": 3, "heating_starts_last_hour": 2, "short_cycling": False},
          "active": {"state": "awaiting_confirmation", "awaiting_confirmation": True, "restored": True, "listened_s": 30,
                     "warnings": []},
          "shadow": {"today": {"day": "2026-10-29", "s": 600, "tado_unknown_s": 600}},
          "ha": {"input_age_s": 12, "broker_connected": True}}
UNIQUE_IDS = sorted([
    "fixture_hub_heat_request", "fixture_hub_burner_starts_last_hour",
    "fixture_e32_room_woonkamer_temperature", "fixture_e32_room_woonkamer_setpoint", "fixture_e32_room_woonkamer_status",
    "fixture_e32_room_keuken_temperature", "fixture_e32_room_keuken_setpoint", "fixture_e32_room_keuken_status",
    "fixture_e32_ble_a4c138a3e8db_temperature", "fixture_e32_ble_a4c138a3e8db_humidity",
    "fixture_e32_ble_a4c138a3e8db_battery"])


async def _setup(hass, monkeypatch):
    from homeassistant.components import mqtt
    from custom_components.open_thermostat.const import DOMAIN
    callbacks, added, published = {}, [], []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

    async def subscribe(hass, topic, callback):
        callbacks[topic] = callback
        return lambda: None
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)

    async def publish(hass, topic, payload, qos, retain):
        published.append((topic, payload))
    monkeypatch.setattr(mqtt, "async_publish", publish)
    tracked = []
    monkeypatch.setattr(module, "async_track_state_change_event", lambda hass, ids, cb: tracked.append(list(ids)) or (lambda: None))
    monkeypatch.setattr(module, "async_track_time_interval", lambda hass, cb, interval: lambda: None)
    hass.data[DOMAIN] = {"e": {"v1_connection": SimpleNamespace(client=object(), prefix="fixture/v1/")}}
    entry = SimpleNamespace(entry_id="e", data={"topic_prefix": "fixture"}, async_on_unload=lambda f: None)
    await module.async_setup_heating_link(hass, entry, added.extend)
    hub = hass.data[DOMAIN]["e"]["heating_hub"]
    now = [5000.0]
    hub.clock = lambda: now[0]
    hub.started = now[0]
    return hub, added, FakeE32(callbacks), now, callbacks, tracked


def test_it_subscribes_to_exactly_the_new_topics_and_no_old_one():
    import inspect
    source = inspect.getsource(module)
    for old in ("fw/telemetry/heating\"", "heating_learned", "heating_summary"):
        assert old not in source, old


@pytest.mark.asyncio
async def test_every_topic_is_subscribed(hass, monkeypatch):
    _, _, _, _, callbacks, _ = await _setup(hass, monkeypatch)
    assert sorted(t.removeprefix("fixture/v1/") for t in callbacks) == sorted([
        "fw/availability", "fw/heartbeat", "fw/state/heating", "fw/state/room/+", "fw/state/ble/+", "fw/config/plan",
        "fw/config/entities", "fw/config/entities/+", "fw/telemetry/learned/+", "fw/telemetry/summary",
        "fw/telemetry/flow", "fw/telemetry/shadow"])


def test_topic_documents_are_strict():
    plan = {"schema": 1, "revision": 7, "mode": "shadow", "rooms": ["woonkamer"], "ble": ["a4c138a3e8db"], "entity_parts": 1}
    assert module.decode_plan(json.dumps(plan)) == plan
    for key, bad in [("schema", 2), ("mode", "manual"), ("rooms", ["BAD id"]), ("rooms", ["a", "a"]),
                     ("rooms", [f"r{i}" for i in range(9)]), ("ble", ["NOT-HEX"]), ("entity_parts", 0),
                     ("entity_parts", 9), ("revision", "7")]:
        assert module.decode_plan(json.dumps({**plan, key: bad})) is None, key
    part = {"schema": 1, "revision": 7, "part": 1, "parts": 2, "entities": ["climate.a"]}
    assert module.decode_entities(json.dumps(part), 1) == part
    assert module.decode_entities(json.dumps(part), 0) is None          # the topic's part number
    for key, bad in [("parts", 1), ("parts", 9), ("entities", ["no_domain"]), ("entities", ["x." + "y" * 80]),
                     ("entities", ["a.b"] * 41)]:
        assert module.decode_entities(json.dumps({**part, key: bad}), 1) is None, key
    room = {"schema": 1, "id": "woonkamer", "temperature": 20.4}
    assert module.decode_item(json.dumps(room), "woonkamer", module.ROOM_ID) == {"id": "woonkamer", "temperature": 20.4}
    assert module.decode_item(json.dumps(room), "keuken", module.ROOM_ID) is None
    assert module.decode_item(json.dumps({**room, "id": "BAD id"}), "BAD id", module.ROOM_ID) is None
    assert module.decode_item(json.dumps({**room, "schema": 2}), "woonkamer", module.ROOM_ID) is None
    assert module.decode_heartbeat(json.dumps({"schema": 1, "uptime_s": 61})) == {"schema": 1, "uptime_s": 61}
    for bad in ({"schema": 1}, {"schema": 1, "uptime_s": -1}, {"schema": 1, "uptime_s": "1"}, {"schema": 2, "uptime_s": 1}):
        assert module.decode_heartbeat(json.dumps(bad)) is None
    # Every message is at most 1.5 KB (the E32's hard limit).
    assert module.decode_document(json.dumps({"schema": 1, "x": "y" * 1600})) is None
    assert module.decode_document("not json") is None and module.decode_document(None) is None


@pytest.mark.asyncio
async def test_the_assembled_status_is_the_same_status_and_keeps_the_entity_ids(hass, monkeypatch):
    hub, added, e32, now, _, tracked = await _setup(hass, monkeypatch)
    e32.status(STATUS)
    assert hub.fresh
    assert {k: v for k, v in hub.status.items()} == {k: v for k, v in STATUS.items()}
    assert sorted(e.unique_id for e in added if e.unique_id in UNIQUE_IDS) == UNIQUE_IDS
    assert tracked == [["climate.woonkamer", "sensor.keuken"]]
    # The guard's block for the awaiting-confirmation alert (heating_problem reads hub.active).
    assert hub.active == STATUS["active"]
    from custom_components.open_thermostat.heating_problem import awaiting_confirmation
    assert awaiting_confirmation(hub)


@pytest.mark.asyncio
async def test_a_restarted_home_assistant_is_complete_at_once_from_the_retained_topics(hass, monkeypatch):
    hub, added, e32, now, _, tracked = await _setup(hass, monkeypatch)
    e32.message("fw/availability", "online", retain=True)
    e32.status(STATUS, retain=True, heartbeat=False)               # no heartbeat yet: the retained state counts
    assert hub.fresh and hub.rooms["woonkamer"]["temperature"] == 20.4
    assert sorted(e.unique_id for e in added if e.unique_id in UNIQUE_IDS) == UNIQUE_IDS
    assert all(e.available for e in added if e.unique_id in UNIQUE_IDS)
    # Without a heartbeat for three heartbeat periods: unavailable.
    now[0] += module.STALE_SECONDS + 1
    hub.check_stale()
    assert not hub.fresh and not any(e.available for e in added)
    e32.heartbeat()
    assert hub.fresh and all(e.available for e in added if e.unique_id in UNIQUE_IDS)
    # A retained "offline" (the E32's will) at HA start: unavailable until it is back.
    hub2, _, e32b, _, _, _ = await _setup(hass, monkeypatch)
    e32b.message("fw/availability", "offline", retain=True)
    e32b.status(STATUS, retain=True, heartbeat=False)
    assert not hub2.fresh
    e32b.message("fw/availability", "online")
    assert hub2.fresh


@pytest.mark.asyncio
async def test_values_stay_until_three_heartbeats_are_missed_or_the_e32_is_offline(hass, monkeypatch):
    hub, added, e32, now, _, _ = await _setup(hass, monkeypatch)
    e32.status(STATUS)
    room = next(e for e in added if e.unique_id == "fixture_e32_room_woonkamer_temperature")
    # Unchanged rooms are not sent again for minutes: the heartbeat keeps them.
    for _ in range(30):
        now[0] += 60
        e32.heartbeat()
        hub.check_stale()
        assert room.available and room.native_value == 20.4
    # Two missed heartbeats: still there; three: unavailable.
    now[0] += 2 * 60
    hub.check_stale()
    assert room.available
    now[0] += 60 + 16
    hub.check_stale()
    assert not room.available and not hub.fresh
    last = hub.last_seen
    e32.heartbeat()
    assert room.available and hub.last_seen > last
    # The E32's will (offline): unavailable at once.
    e32.message("fw/availability", "offline")
    assert not room.available
    e32.message("fw/availability", "online")
    e32.heartbeat()
    assert room.available


@pytest.mark.asyncio
async def test_each_topic_updates_its_own_part(hass, monkeypatch):
    hub, added, e32, now, _, tracked = await _setup(hass, monkeypatch)
    e32.status(STATUS)
    room = next(e for e in added if e.unique_id == "fixture_e32_room_woonkamer_temperature")
    sensor = next(e for e in added if e.unique_id == "fixture_e32_ble_a4c138a3e8db_battery")
    request = next(e for e in added if e.unique_id == "fixture_hub_heat_request")
    e32.message("fw/state/room/woonkamer", json.dumps({"schema": 1, **STATUS["rooms"][0], "temperature": 20.6}))
    assert room.native_value == 20.6
    e32.message("fw/state/ble/a4c138a3e8db", json.dumps({"schema": 1, **STATUS["ble_sensors"][0], "battery": 80}))
    assert sensor.native_value == 80
    heating = dict(split_status(STATUS))["fw/state/heating"]
    e32.message("fw/state/heating", json.dumps({**heating, "request": {"heat": True, "flow_c": 44, "reason": "heating"}}))
    assert request.native_value == 44
    # An invalid room document drops that room only; an invalid heating document every value.
    e32.message("fw/state/room/woonkamer", json.dumps({"schema": 1, "id": "keuken"}))
    assert not room.available and request.available
    e32.message("fw/state/heating", json.dumps({**heating, "request": {"heat": True, "flow_c": 81, "reason": "heating"}}))
    assert not request.available
    e32.message("fw/state/heating", json.dumps(heating))
    assert request.available
    # The entity list in parts: a new revision counts once all its parts and the plan agree.
    plan = dict(split_status(STATUS))["fw/config/plan"]
    e32.message("fw/config/entities/1", json.dumps({"schema": 1, "revision": 8, "part": 1, "parts": 2, "entities": ["sensor.zolder"]}))
    e32.message("fw/config/entities", json.dumps({"schema": 1, "revision": 8, "part": 0, "parts": 2, "entities": ["climate.woonkamer"]}))
    assert hub.status["ha_entities"] == STATUS["ha_entities"]      # the plan still names revision 7
    e32.message("fw/config/plan", json.dumps({**plan, "revision": 8, "entity_parts": 2}))
    assert hub.status["ha_entities"] == ["climate.woonkamer", "sensor.zolder"]
    assert tracked[-1] == ["climate.woonkamer", "sensor.zolder"]
    # A room that left the plan is gone, its learned values too.
    e32.learned("keuken", {"schema": 1, "id": "keuken", "learned": {"readiness": "ready"}, "plan": None})
    assert "keuken" in hub.learned
    e32.message("fw/config/plan", json.dumps({**plan, "revision": 8, "entity_parts": 2, "rooms": ["woonkamer"]}))
    assert "keuken" not in hub.rooms and "keuken" not in hub.learned
    # The summary and the shadow comparison.
    e32.summary({"schema": 1, "dhw": {"method": "flow", "clock_known": True, "today": {"burner_s": 60}},
                 "learned": {"schema": 1, "gas": {"status": "calibrated"}}})
    assert hub.dhw["today"]["burner_s"] == 60 and hub.learned_header["gas"] == {"status": "calibrated"}
    # The flow policy's part (weather curve, learned flow, night gas) on its own topic, merged into the summary.
    flow = {"source": "curve", "rule_flow_c": 40, "applied_flow_c": 38, "curve": {"state": "active", "flow_c": 38}}
    e32.message("fw/telemetry/flow", json.dumps({"schema": 1, "flow": flow, "night_gas": {"m3": 0.4}, "junk": 1}))
    assert hub.summary["flow"] == flow and hub.summary["night_gas"] == {"m3": 0.4} and "junk" not in hub.summary
    e32.summary({"schema": 1, "dhw": {"method": "flow", "clock_known": True, "today": {"burner_s": 90}}})
    assert hub.summary["flow"] == flow and hub.dhw["today"]["burner_s"] == 90
    e32.message("fw/telemetry/flow", json.dumps({"schema": 2, "flow": flow}))
    assert "flow" not in hub.summary
    heating = dict(split_status(STATUS))["fw/state/heating"]
    e32.message("fw/state/heating", json.dumps({**heating, "request": {"heat": True, "flow_c": 38, "reason": "optimum_start"}}))
    assert hub.status["request"]["reason"] == "optimum_start" and request.native_value == 38
    e32.message("fw/telemetry/shadow", json.dumps({"schema": 1, "today": {"day": "2026-10-30", "s": 5}}))
    assert hub.status["shadow"] == {"today": {"day": "2026-10-30", "s": 5}}
    # Unknown topics and malformed heartbeats change nothing.
    before = dict(hub.status)
    e32.message("fw/heartbeat", "nope")
    hub.receive("fw/unknown", "{}")
    assert hub.status == before
