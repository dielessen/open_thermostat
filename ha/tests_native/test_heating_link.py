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
