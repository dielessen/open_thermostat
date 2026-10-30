"""Boiler value entities write only real changes, and never once removed or disabled.

Every runtime notification (session messages, heartbeats, telemetry) used to
write all ~70 boiler entities, each re-evaluating the session (~1 ms per
client.ready): the "Updating state took 0.6 s" warnings and recorder churn. A
disabled entity (Home Assistant removed it, but it keeps its hass) was still
written: "is incorrectly being triggered for updates while it is disabled".
"""
import json

import pytest

from custom_components.open_thermostat.v1_boiler_fields import BoilerFieldEntity, async_setup_boiler_fields
from custom_components.open_thermostat.v1_wire import ShadowClient, canonical
from test_boiler_fields import packet
from test_boiler_state import group_doc
from test_modern_metrics import system


def counted(monkeypatch, entities):
    writes = []
    for entity in entities:
        entity.hass, entity.entity_id, entity.added = object(), f"sensor.field_{entity.index}", True
        monkeypatch.setattr(entity, "async_write_ha_state", lambda entity=entity: writes.append(entity.index))
    return writes


@pytest.mark.asyncio
async def test_only_changed_entities_are_written_and_never_a_removed_one(hass, monkeypatch):
    e, r, c, now = await system(hass)
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 600}))
    for group in range(7):
        await c.receive(f"fw/state/boiler_fields/{group}", group_doc(group), retained=True)
    writes = counted(monkeypatch, added)
    r._notify()
    first = len(writes)
    assert first == len(added)  # first pass after adding: each once
    for _ in range(5):
        r._notify()  # nothing changed: nothing written
    assert len(writes) == first
    await c.receive("fw/state/boiler_fields/0", group_doc(0, sampled=20000, observed=19000), retained=True)
    flow = {entity.index: entity for entity in added}[1]
    assert len(writes) == first  # same values, newer sample time only: no state change
    # The E32 goes offline: every entity once more (unavailable), then quiet again.
    await c.receive("fw/availability", "offline")
    assert len(writes) == 2 * first and not flow.available
    r._notify()
    assert len(writes) == 2 * first
    # Removed or disabled (Home Assistant removed it; hass stays set): never written again.
    flow.added = False
    await c.receive("fw/availability", "online")
    assert 1 not in writes[2 * first:] and len(writes) == 3 * first - 1
    await r.async_stop()


@pytest.mark.asyncio
async def test_the_session_is_evaluated_once_per_pass(hass, monkeypatch):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = True
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/telemetry/boiler_fields", canonical(packet(c)))
    r._notify()
    assert len(added) > 3
    counted(monkeypatch, added)
    calls = []
    original = ShadowClient.ready.fget
    monkeypatch.setattr(ShadowClient, "ready", property(lambda self: calls.append(1) or original(self)))
    r._notify()
    assert len(calls) <= 2  # not once per entity (and per property)
    await r.async_stop()


def test_per_sample_diagnostics_are_not_recorded():
    assert {"source_observed_at_ms", "age_basis", "raw_divisor", "source_ttl_ms", "protocol_profile",
            "source_fields"} <= BoilerFieldEntity._unrecorded_attributes


@pytest.mark.asyncio
async def test_a_removed_gas_sensor_is_not_written(hass):
    from types import SimpleNamespace
    from custom_components.open_thermostat.energy_use import GasUseSensor
    writes = []
    use = SimpleNamespace(hub=SimpleNamespace(prefix="fixture"), sensors=[])
    sensor = GasUseSensor(use, "heating")
    sensor.hass, sensor.entity_id = hass, "sensor.heating_gas"
    sensor.async_write_ha_state = lambda: writes.append(1)
    use.sensors = [sensor]
    from custom_components.open_thermostat.energy_use import EnergyUse
    EnergyUse._write(SimpleNamespace(sensors=[sensor], _written=None), 0)
    assert writes == []  # never added (or removed / disabled): no write
    sensor.added = True
    EnergyUse._write(SimpleNamespace(sensors=[sensor], _written=None), 0)
    assert writes == [1]
