"""Boiler values without a session, and only the values this boiler has (HA 0.4.0b12).

Live on 30 Oct 2026 the E32's hello carried storage_fault: the shadow session
was reset and every boiler value stayed unavailable, although beta.19 publishes
them retained. Now the retained values show whenever the E32 is alive, and the
boiler profile (fw/config/boiler_profile) decides which entities exist: values
the boiler lacks leave no "unavailable" rows, values that become supported come
back, and anything the user customised is never touched. Universal: only the
profile counts, never a list of one house's boiler.
"""
import json

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.boiler_fields import INDEX_BY_NAME, concept
from custom_components.open_thermostat.v1_boiler_fields import (
    PLACEHOLDER, PROFILE_HIDDEN, REPORTED, apply_boiler_profile, async_setup_boiler_fields, field_unique_id)
from test_boiler_state import group_doc
from test_modern_metrics import system

INTEGRATION = er.RegistryEntryDisabler.INTEGRATION
HIDDEN = er.RegistryEntryHider.INTEGRATION
USER = er.RegistryEntryDisabler.USER


def at(name):
    return INDEX_BY_NAME[name]


def uid(name):
    return field_unique_id("fixture", at(name))


def profile(supported=(), not_fitted=(), not_reported=(), settled=True):
    return json.dumps({"schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": None, "version": None},
                       "supported": sorted(at(n) for n in supported), "not_fitted": sorted(at(n) for n in not_fitted),
                       "not_reported": sorted(at(n) for n in not_reported), "settled": settled})


def hello(storage_fault):
    return json.dumps({"api": 1, "mode": "shadow", "controller_id": "e32_lab", "boot_id": "boot2",
                       "challenge_id": "c1", "epoch": 1, "config_revision": 0, "config_digest": "",
                       "lease_ms": 30000, "grant_ms": 30000, "storage_fault": storage_fault,
                       "read_only_capabilities": ["boiler.fields.v1"]})


@pytest.mark.asyncio
async def test_a_storage_fault_hello_still_shows_the_retained_boiler_values(hass):
    e, r, c, now = await system(hass)
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 600}))
    for group in range(7):
        await c.receive(f"fw/state/boiler_fields/{group}", group_doc(group), retained=True)
    await c.receive("fw/hello", hello(True), retained=True)
    assert c.error == "firmware_storage_fault" and c.session is None and not c.ready
    flow = {entity.index: entity for entity in added}[1]
    assert flow.available and flow.native_value == 45
    assert flow.extra_state_attributes["availability_reason"] == "ready"
    # Freshness follows the E32 itself: silent for three heartbeats, or offline -> unavailable.
    now[0] += 3 * 60 + 16
    assert not flow.available and flow.native_value is None
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 900}))
    assert flow.available and flow.native_value == 45
    await c.receive("fw/availability", "offline")
    assert not flow.available
    await r.async_stop()


@pytest.mark.asyncio
async def test_older_session_telemetry_keeps_the_session_rule(hass):
    e, r, c, now = await system(hass)
    from test_boiler_fields import packet
    from custom_components.open_thermostat.v1_wire import canonical
    c.boiler_fields_supported = True
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/telemetry/boiler_fields", canonical(packet(c)))
    r._notify()
    flow = {entity.index: entity for entity in added}[1]
    assert flow.available
    c.reset_session()  # no retained state on that firmware: the session ends, the values go
    assert not flow.available
    await r.async_stop()


@pytest.mark.asyncio
async def test_the_profile_hides_what_this_boiler_lacks_and_brings_it_back(hass):
    e, r, c, now = await system(hass)
    reg = er.async_get(hass)

    def record(name, reported=False, **kw):
        entity_id = reg.async_get_or_create("sensor", "open_thermostat", uid(name), config_entry=e, **kw).entity_id
        if reported:
            reg.async_update_entity_options(entity_id, "open_thermostat", {REPORTED: True})
        return entity_id

    # Records an older release made: a not-fitted value that once reported, one that never
    # did, an old disabled placeholder of a value that is not reported, and the user's own.
    reported_pressure = record("pressure", reported=True)
    never_storage = record("storage_temperature_1")
    placeholder = record("outdoor_temperature", disabled_by=INTEGRATION)
    reg.async_update_entity_options(placeholder, "open_thermostat", {PLACEHOLDER: True})
    renamed = record("storage_temperature_2")
    reg.async_update_entity(renamed, name="My storage")
    user_disabled = record("exhaust_temperature", disabled_by=USER)
    flow = record("measured_flow_temperature")
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 600}))
    await c.receive("fw/state/boiler_fields/6", group_doc(6), retained=True)  # retained state (beta.19)
    plus = [name for name in INDEX_BY_NAME if name.startswith("plus_")]
    await c.receive("fw/config/boiler_profile", profile(
        ["measured_flow_temperature"], ["pressure", "storage_temperature_1", "storage_temperature_2",
                                        "exhaust_temperature"], ["outdoor_temperature", *plus]), retained=True)
    r._notify()
    # Never reported: gone. Reported once: disabled and hidden (history kept). The user's: untouched.
    assert reg.async_get(never_storage) is None and reg.async_get(placeholder) is None
    pressure = reg.async_get(reported_pressure)
    assert pressure.disabled_by is INTEGRATION and pressure.hidden_by is HIDDEN
    assert pressure.options["open_thermostat"][PROFILE_HIDDEN] is True
    assert reg.async_get(renamed).name == "My storage" and reg.async_get(renamed).disabled_by is None
    assert reg.async_get(user_disabled).disabled_by is USER and reg.async_get(user_disabled).hidden_by is None
    assert reg.async_get(flow).disabled_by is None
    made = {entity.index for entity in added}
    assert at("measured_flow_temperature") in made  # supported: made at once
    # The user's own records keep their entity (HA leaves the user-disabled one out); nothing else lacking.
    assert {at("storage_temperature_2"), at("exhaust_temperature")} <= made
    made -= {at("storage_temperature_2"), at("exhaust_temperature")}
    assert not made & {*concept(at("pressure")), at("storage_temperature_1"), at("outdoor_temperature")}
    assert all(c.boiler_fields.concept_state(concept(index)) not in ("not_fitted", "not_reported")
               for index in made), made
    # A pressure sensor fitted later (or "Show anyway" on the E32): its own hidden record comes back.
    await c.receive("fw/config/boiler_profile", profile(
        ["measured_flow_temperature", "pressure"], ["storage_temperature_1", "storage_temperature_2",
                                                    "exhaust_temperature"], ["outdoor_temperature", *plus]),
        retained=True)
    r._notify()
    pressure = reg.async_get(reported_pressure)
    assert pressure.disabled_by is None and pressure.hidden_by is None
    assert PROFILE_HIDDEN not in pressure.options["open_thermostat"]
    assert at("pressure") in {entity.index for entity in added}
    # A user's own disable is never undone, even when the value is supported.
    await c.receive("fw/config/boiler_profile", profile(
        ["measured_flow_temperature", "pressure", "exhaust_temperature"], [], ["outdoor_temperature", *plus]),
        retained=True)
    r._notify()
    assert reg.async_get(user_disabled).disabled_by is USER
    await r.async_stop()


@pytest.mark.asyncio
async def test_unknown_values_wait_for_the_profile_or_a_real_value(hass):
    e, r, c, now = await system(hass)
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 600}))
    await c.receive("fw/state/boiler_fields/6", group_doc(6), retained=True)  # retained state, no flow value
    # Not settled yet: a not-reported value is neither made nor removed.
    reg = er.async_get(hass)
    kept = reg.async_get_or_create("sensor", "open_thermostat", uid("boiler_uptime"), config_entry=e).entity_id
    await c.receive("fw/config/boiler_profile", profile(["measured_flow_temperature"], [], ["boiler_uptime"],
                                                        settled=False), retained=True)
    r._notify()
    assert reg.async_get(kept) is not None
    made = {entity.index: entity for entity in added}
    assert at("measured_flow_temperature") in made and at("boiler_uptime") not in made
    assert all(i in range(60, 69) or i == at("measured_flow_temperature") for i in made)  # values seen, or supported
    # A supported value without a value yet reads unknown while the E32 is online, not unavailable.
    flow = made[at("measured_flow_temperature")]
    assert flow.available and flow.native_value is None
    await r.async_stop()


@pytest.mark.asyncio
async def test_a_complete_profile_leaves_no_unavailable_boiler_entity(hass):
    """Every value supported (and reporting) or lacking: nothing reads unavailable while the E32 is online."""
    from custom_components.open_thermostat.boiler_fields import INDEXES
    e, r, c, now = await system(hass)
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 600}))
    for group in range(7):
        await c.receive(f"fw/state/boiler_fields/{group}", group_doc(group), retained=True)
    reporting = {index for index in INDEXES if c.boiler_fields.reading(index, now[0])
                 and c.boiler_fields.reading(index, now[0])["usable"]}
    names = {index: name for name, index in INDEX_BY_NAME.items()}
    supported = [names[i] for i in sorted(reporting)]
    lacking = [names[i] for i in INDEXES if i not in reporting]
    await c.receive("fw/config/boiler_profile", json.dumps({
        "schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": None, "version": None},
        "supported": sorted(at(n) for n in supported), "not_fitted": [],
        "not_reported": sorted(at(n) for n in lacking), "settled": True}), retained=True)
    r._notify()
    assert added and all(entity.available for entity in added)
    assert all(entity.native_value is not None for entity in added if entity.enabled)
    assert apply_boiler_profile(hass, e, "fixture", c.boiler_fields) == frozenset()
    await r.async_stop()
