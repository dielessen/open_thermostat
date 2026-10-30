"""Retained boiler telemetry (E32 beta.19): fw/state/boiler_fields/<g> and fw/state/boiler."""
import json
import pytest
from custom_components.open_thermostat.boiler_fields import FIELDS, QUALITIES, GROUPS_V2
from custom_components.open_thermostat.v1_boiler_fields import async_setup_boiler_fields
from test_boiler_fields import values, by_index, REAL
from test_modern_metrics import system


def group_doc(group=0, **kw):
    return json.dumps({"schema": 1, "group": group, "values": values(group, **kw)})


def state_doc(rows, sampled=20000):
    return json.dumps({"schema": 1, "values": {"schema": 1, "sampled_at_ms": sampled, "profile": "classic_observed", "fields": rows}})


def row(index, raw, observed=19000):
    return [index, raw, observed, QUALITIES[index], FIELDS[index][4]]


@pytest.mark.asyncio
async def test_retained_groups_feed_the_same_entities_without_a_session(hass):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = False                    # the hello no longer announces boiler.fields
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities: added.extend(entities))
    for group in range(7):
        await c.receive(f"fw/state/boiler_fields/{group}", group_doc(group), retained=True)
    r._notify()
    assert sorted(by_index(added)) == REAL                # the same field entities (and unique ids)
    assert by_index(added)[1].native_value == 45
    assert c.boiler_fields.reading(1, now[0])["usable"]
    # A value is not sent again while unchanged: it stays usable far beyond its 30 s source lifetime ...
    for _ in range(10):
        now[0] += 60
        await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 600}))
    assert c.boiler_fields.reading(1, now[0])["usable"]
    # ... until three heartbeats are missed, or the E32 is offline.
    now[0] += 3 * 60 + 16
    assert not c.boiler_fields.reading(1, now[0])["usable"]
    assert c.boiler_fields.reading(1, now[0])["availability_reason"] == "stream_unavailable"
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 900}))
    assert c.boiler_fields.reading(1, now[0])["usable"]
    await c.receive("fw/availability", "offline")
    assert not c.boiler_fields.reading(1, now[0])["usable"]
    await c.receive("fw/availability", "online")
    assert c.boiler_fields.reading(1, now[0])["usable"]
    # A session reset or a hello without boiler capabilities keeps the retained state.
    c.reset_session()
    assert c.boiler_fields.reading(1, now[0])["usable"]
    await r.async_stop()


@pytest.mark.asyncio
async def test_the_boiler_state_updates_its_fields_and_the_e32_decides_staleness(hass):
    e, r, c, now = await system(hass)
    await c.receive("fw/state/boiler_fields/0", group_doc(0, sampled=10000, observed=9000), retained=True)
    await c.receive("fw/state/boiler", state_doc([row(1, 5100), row(2, 4600), row(7, 1), row(12, 0)]))
    assert c.boiler_fields.reading(1, now[0])["raw"] == 5100
    # An older group (sampled before the state) never overwrites the newer value.
    await c.receive("fw/state/boiler_fields/0", group_doc(0, sampled=15000, observed=14000))
    assert c.boiler_fields.reading(1, now[0])["raw"] == 5100
    assert c.boiler_fields.reading(3, now[0])["usable"]   # other fields of that group did update
    # A value past its lifetime comes as null: unavailable at once.
    await c.receive("fw/state/boiler", state_doc([row(1, None), row(2, 4600)], sampled=60000))
    reading = c.boiler_fields.reading(1, now[0])
    assert reading["raw"] is None and not reading["usable"] and reading["measurement_state"] == "invalid"
    # A restarted E32 (uptime below the values' age) starts from scratch.
    await c.receive("fw/state/boiler", state_doc([row(2, 4600, observed=299000)], sampled=300000))
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 5}))
    assert c.boiler_fields.reading(2, now[0]) is None
    await c.receive("fw/state/boiler", state_doc([row(2, 4700, observed=3000)], sampled=4000))
    assert c.boiler_fields.reading(2, now[0])["raw"] == 4700
    await r.async_stop()


@pytest.mark.asyncio
async def test_boiler_state_documents_are_strict(hass):
    e, r, c, now = await system(hass)
    good = json.loads(group_doc(0))
    await c.receive("fw/state/boiler_fields/0", json.dumps(good))
    assert c.boiler_fields.reading(1, now[0])["raw"] == 4500
    for topic, bad in [("fw/state/boiler_fields/0", {**good, "group": 1}),
                       ("fw/state/boiler_fields/0", {**good, "schema": 2}),
                       ("fw/state/boiler_fields/0", {**good, "extra": 1}),
                       ("fw/state/boiler_fields/0", {**good, "values": {**good["values"], "profile": "x"}}),
                       ("fw/state/boiler", {"schema": 1, "values": {**good["values"], "fields": [row(1, 99999)]}}),
                       ("fw/state/boiler", {"schema": 1, "values": {**good["values"], "fields": [row(1, 4500), row(1, 4500)]}}),
                       ("fw/state/boiler", {"schema": 1, "values": {**good["values"], "fields": [[500, 1, 1, 0, 24]]}})]:
        await c.receive(topic, json.dumps(bad))
        assert c.runtime.diagnostics["boiler_fields"] == "invalid_read_only_fields", bad
        assert c.boiler_fields.reading(1, now[0])["raw"] == 4500       # never a half-applied document
    await c.receive("fw/state/boiler_fields/0", "x" * 1600)
    await c.receive(f"fw/state/boiler_fields/{GROUPS_V2}", group_doc(0))  # a newer catalog: ignored
    assert c.boiler_fields.reading(1, now[0])["raw"] == 4500
    await r.async_stop()


@pytest.mark.asyncio
async def test_new_telemetry_topics_never_touch_the_shadow_session(hass):
    e, r, c, now = await system(hass)
    before = (c.session, c.last_rx, c.error)
    for topic, payload in [("fw/state/room/woonkamer", '{"schema":1,"id":"woonkamer","name":"Café \\"x\\""}'),
                           ("fw/state/heating", "{"), ("fw/config/plan", "[]"), ("fw/config/entities/1", "x"),
                           ("fw/telemetry/learned/woonkamer", "{}"), ("fw/telemetry/summary", "{}"),
                           ("fw/telemetry/shadow", "{}"), ("fw/heartbeat", "nope"), ("fw/state/ble/a4c138a3e8db", "")]:
        await c.receive(topic, payload)
        await c.receive(topic, payload, retained=True)
    assert (c.session, c.last_rx, c.error) == before
    await r.async_stop()
