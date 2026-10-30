"""The boiler profile (E32 beta.19): only the boiler values this boiler actually has.

The E32 learns per field whether the boiler reports a valid value (supported),
always reports its "no sensor" sentinel (not_fitted) or never sent the telegram
(not_reported), and publishes the retained fw/config/boiler_profile. Home
Assistant creates entities for supported values, never new ones for not-fitted
values (and removes their untouched records), and none for values that are not
reported once the profile settled (0.4.0b12: no disabled placeholders; see
test_boiler_profile_visibility.py).
"""
import json

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.boiler_fields import (
    INDEX_BY_NAME, BoilerFieldCache, combined_state, concept, validate_profile)
from custom_components.open_thermostat.native_entity_cleanup import cleanup_not_fitted, cleanup_stale_entities
from custom_components.open_thermostat.v1_boiler_fields import (
    PLACEHOLDER, REPORTED, async_setup_boiler_fields, boiler_field_shown, field_unique_id)
from test_boiler_state import group_doc
from test_modern_metrics import system

INTEGRATION = er.RegistryEntryDisabler.INTEGRATION
USER = er.RegistryEntryDisabler.USER


def at(name):
    return INDEX_BY_NAME[name]


def profile(supported=(), not_fitted=(), not_reported=(), settled=True):
    return json.dumps({"schema": 1, "boiler": {"address": 8, "family": "classic", "product_id": None, "version": None},
                       "supported": sorted(at(n) for n in supported), "not_fitted": sorted(at(n) for n in not_fitted),
                       "not_reported": sorted(at(n) for n in not_reported), "settled": settled})


# The owner's boiler: no digital pressure sensor and no storage sensors (0xFF / 0x8000).
OWNER_NOT_FITTED = ("pressure", "storage_temperature_1", "storage_temperature_2")
CLASSIC_PLUS = [name for name in INDEX_BY_NAME if name.startswith("plus_")]


def test_the_profile_wire_is_validated_and_newer_indexes_are_ignored():
    cache = BoilerFieldCache()
    assert cache.field_state(at("pressure")) is None and cache.concept_state(concept(at("pressure"))) is None
    assert cache.accept_profile(profile(["measured_flow_temperature"], OWNER_NOT_FITTED, ["outdoor_temperature"]))
    assert cache.field_state(at("pressure")) == "not_fitted"
    assert cache.field_state(at("measured_flow_temperature")) == "supported"
    assert cache.field_state(at("outdoor_temperature")) == "not_reported"
    assert cache.field_state(at("display_code")) == "unknown"  # in no list
    sequence = cache.profile_sequence
    assert cache.accept_profile(profile(["measured_flow_temperature"], OWNER_NOT_FITTED, ["outdoor_temperature"]))
    assert cache.profile_sequence == sequence  # unchanged: no new pass
    for bad in ("{", json.dumps({"schema": 2}), json.dumps({"schema": 1, "boiler": {}, "supported": [1, 1],
                                                            "not_fitted": [], "not_reported": []}),
                json.dumps({"schema": 1, "boiler": {}, "supported": [1], "not_fitted": [1], "not_reported": []}),
                json.dumps({"schema": 1, "boiler": {}, "supported": ["1"], "not_fitted": [], "not_reported": []}),
                "x" * 2000):
        assert not cache.accept_profile(bad)
        assert cache.field_state(at("pressure")) == "not_fitted"  # an invalid one keeps the last
    assert validate_profile({"schema": 1, "boiler": {}, "supported": [200], "not_fitted": [], "not_reported": []}) == {}
    assert cache.accept_profile("") and cache.field_profile is None
    # One physical value (F28): EMS+ twin not reported, Classic not fitted -> not fitted.
    assert combined_state({"not_fitted", "not_reported"}) == "not_fitted"
    assert combined_state({"not_fitted", "supported"}) == "supported"
    assert combined_state({"not_fitted", "unknown"}) == "unknown"
    assert combined_state({"not_reported"}) == "not_reported"


@pytest.mark.asyncio
async def test_retained_profile_reaches_the_cache_and_survives_a_session_reset(hass):
    e, r, c, now = await system(hass)
    await c.receive("fw/config/boiler_profile", profile(["measured_flow_temperature"], OWNER_NOT_FITTED), retained=True)
    assert c.boiler_fields.field_state(at("pressure")) == "not_fitted"
    c.reset_session()
    await c.receive("fw/state/boiler_fields/0", group_doc(0), retained=True)
    assert c.boiler_fields.field_state(at("pressure")) == "not_fitted"
    await c.receive("fw/config/boiler_profile", "", retained=True)  # cleared
    assert c.boiler_fields.field_profile is None
    await r.async_stop()


@pytest.mark.asyncio
async def test_entities_follow_the_profile_per_state(hass):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = True
    reg = er.async_get(hass)
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    # Classic owner: flow and return supported (no value received yet in HA), the sensors it
    # lacks not fitted, the EMS+ twins and the outdoor sensor never reported.
    supported = ["measured_flow_temperature", "measured_return_temperature"]
    not_reported = ["outdoor_temperature", "boiler_uptime", *CLASSIC_PLUS]
    await c.receive("fw/config/boiler_profile", profile(supported, OWNER_NOT_FITTED, not_reported, settled=False),
                    retained=True)
    r._notify()
    names = {entity.index: entity for entity in added}
    # Supported values get their entity at once, before HA saw a value (no gap after a restart).
    assert {at(n) for n in supported} <= set(names)
    assert not any(member in names for name in OWNER_NOT_FITTED for member in concept(at(name)))
    # Not reported: nothing while the profile has not settled ...
    assert at("outdoor_temperature") not in names and at("boiler_uptime") not in names
    flow = names[at("measured_flow_temperature")]
    assert flow.entity_registry_enabled_default
    assert flow.extra_state_attributes["boiler_profile"] == "supported"
    # ... and none once it settled either: no disabled placeholder rows (the EMS+ pressure twin
    # is part of the not-fitted value).
    await c.receive("fw/config/boiler_profile", profile(supported, OWNER_NOT_FITTED, not_reported), retained=True)
    r._notify()
    names = {entity.index: entity for entity in added}
    for name in ("outdoor_temperature", "boiler_uptime"):
        assert not any(member in names for member in concept(at(name))), name
    assert at("plus_pressure") not in names and at("pressure") not in names
    assert len({member for entity in added for member in entity.members}) == sum(len(entity.members) for entity in added)
    # The boiler reports a pressure after all (a sensor fitted later): created automatically.
    await c.receive("fw/config/boiler_profile",
                    profile([*supported, "pressure"], OWNER_NOT_FITTED[1:], not_reported), retained=True)
    r._notify()
    assert at("pressure") in {entity.index for entity in added}
    # Nothing twice on repeated passes.
    before = len(added)
    r._notify()
    r._notify()
    assert len(added) == before
    await r.async_stop()


@pytest.mark.asyncio
async def test_not_fitted_records_go_unless_the_user_customised_them(hass, caplog):
    e, r, c, now = await system(hass)
    c.boiler_fields_supported = True
    reg = er.async_get(hass)

    def record(name, reported=False, **kw):
        entity_id = reg.async_get_or_create("sensor", "open_thermostat", field_unique_id("fixture", at(name)),
                                            config_entry=e, **kw).entity_id
        if reported:
            reg.async_update_entity_options(entity_id, "open_thermostat", {REPORTED: True})
        return entity_id

    # Older releases created every field at once: an enabled, untouched pressure record
    # that never had a value; a renamed storage sensor; a user-disabled one; one that reported.
    pressure = record("pressure")
    plus_pressure = record("plus_pressure", disabled_by=INTEGRATION)
    renamed = record("storage_temperature_1")
    reg.async_update_entity(renamed, name="My storage")
    user_disabled = record("storage_temperature_2", disabled_by=USER)
    reported = record("exhaust_temperature", reported=True)
    flow = record("measured_flow_temperature")
    other = reg.async_get_or_create("sensor", "other", "fixture_boiler_fields_v1_pressure", config_entry=e).entity_id
    added = []
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: added.extend(entities))
    import logging
    with caplog.at_level(logging.INFO):
        await c.receive("fw/config/boiler_profile",
                        profile(["measured_flow_temperature"], [*OWNER_NOT_FITTED, "exhaust_temperature"],
                                CLASSIC_PLUS), retained=True)
        r._notify()
    assert reg.async_get(pressure) is None and reg.async_get(plus_pressure) is None
    assert "no sensor for" in caplog.text
    for kept in (renamed, user_disabled, reported, flow, other):
        assert reg.async_get(kept) is not None, kept
    # A kept not-fitted record says why it has no value; it never becomes a new entity elsewhere.
    by_index = {entity.index: entity for entity in added}
    storage = by_index[at("storage_temperature_1")]
    assert not storage.available
    assert storage.extra_state_attributes["availability_reason"] == "not_fitted"
    # One that reported before is ours: disabled and hidden instead of an unavailable row.
    assert at("exhaust_temperature") not in by_index
    assert reg.async_get(reported).disabled_by is INTEGRATION and reg.async_get(reported).hidden_by is not None
    assert at("pressure") not in by_index
    assert by_index[at("measured_flow_temperature")].unique_id == reg.async_get(flow).unique_id  # same identity
    # Not fitted only when the EMS+ twin is not reported either: a twin that may still turn out keeps it.
    cache = BoilerFieldCache()
    cache.accept_profile(profile([], ["pressure"]))
    assert cache.concept_state(concept(at("pressure"))) == "unknown"
    # The setup cleanup leaves the same set alone; a second pass removes nothing more.
    assert cleanup_not_fitted(hass, e, "fixture", c.boiler_fields) == frozenset()
    assert cleanup_stale_entities(hass, e, "fixture") == []
    await r.async_stop()


@pytest.mark.asyncio
async def test_placeholders_survive_the_setup_cleanup_and_go_once_not_fitted(hass):
    e, r, c, now = await system(hass)
    reg = er.async_get(hass)
    uptime = reg.async_get_or_create("sensor", "open_thermostat", field_unique_id("fixture", at("boiler_uptime")),
                                     config_entry=e, disabled_by=INTEGRATION).entity_id
    never = reg.async_get_or_create("sensor", "open_thermostat", field_unique_id("fixture", at("boiler_temperature")),
                                    config_entry=e, disabled_by=INTEGRATION).entity_id
    from custom_components.open_thermostat.v1_boiler_fields import mark_placeholders
    assert mark_placeholders(hass, "fixture", {at("boiler_uptime"), at("solar_dhw_temperature")}) == {
        at("solar_dhw_temperature")}  # its record does not exist yet: retried
    assert reg.async_get(uptime).options["open_thermostat"][PLACEHOLDER] is True
    # The F28 setup cleanup removes a never-reported disabled record, but not a placeholder.
    removed = cleanup_stale_entities(hass, e, "fixture")
    assert [item.split(" ")[0] for item in removed] == [never]
    assert reg.async_get(uptime) is not None
    # Once the profile says not fitted, it goes.
    c.boiler_fields.accept_profile(profile([], ["boiler_uptime"]))
    assert cleanup_not_fitted(hass, e, "fixture", c.boiler_fields) == {field_unique_id("fixture", at("boiler_uptime"))}
    assert reg.async_get(uptime) is None
    # A real value later turns the placeholder mark into REPORTED.
    from custom_components.open_thermostat.v1_boiler_fields import confirm_reported
    solar = reg.async_get_or_create("sensor", "open_thermostat", field_unique_id("fixture", at("solar_dhw_temperature")),
                                    config_entry=e, disabled_by=INTEGRATION).entity_id
    mark_placeholders(hass, "fixture", {at("solar_dhw_temperature")})
    confirm_reported(hass, "fixture", {at("solar_dhw_temperature")})
    options = reg.async_get(solar).options["open_thermostat"]
    assert options[REPORTED] is True and PLACEHOLDER not in options
    await r.async_stop()


@pytest.mark.asyncio
async def test_dashboard_helper_hides_tiles_of_values_the_boiler_lacks(hass):
    e, r, c, now = await system(hass)
    assert boiler_field_shown(hass, e.entry_id, "pressure")           # no profile: every tile as before
    assert boiler_field_shown(hass, "no-such-entry", "pressure")
    await c.receive("fw/config/boiler_profile",
                    profile(["measured_flow_temperature"], OWNER_NOT_FITTED, ["outdoor_temperature", *CLASSIC_PLUS]),
                    retained=True)
    assert not boiler_field_shown(hass, e.entry_id, "pressure")
    assert not boiler_field_shown(hass, e.entry_id, "plus_pressure")  # the same value
    assert boiler_field_shown(hass, e.entry_id, "measured_flow_temperature")
    assert boiler_field_shown(hass, e.entry_id, "plus_flow_temperature")
    assert not boiler_field_shown(hass, e.entry_id, "outdoor_temperature")
    assert not boiler_field_shown(hass, e.entry_id, "display_code")   # unknown yet
    assert boiler_field_shown(hass, e.entry_id, "not_a_field")
    await r.async_stop()


def test_the_firmware_profile_indexes_match_home_assistant():
    """The E32 lists wire indexes: Classic 0..68 and the catalog from 70, as boiler_fields.py."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    header = (root / "src/EMS/BoilerProfile.h").read_text(encoding="utf-8")
    assert "classicBoilerFieldCount = 69" in header and "catalogWireBase = 70" in header
    from custom_components.open_thermostat.boiler_fields import CATALOG_BASE, FIELDS
    assert len(FIELDS) == 69 and CATALOG_BASE == 70
