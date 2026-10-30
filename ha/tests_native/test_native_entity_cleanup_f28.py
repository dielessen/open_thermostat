"""F28: of an EMS+ field and its Classic twin only the record the user has stays."""
import logging

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat.native_entity_cleanup import cleanup_stale_entities
from custom_components.open_thermostat.v1_boiler_fields import REPORTED
from test_modern_metrics import system  # noqa: F401  (fixture)
from test_product_flow import product
from test_v1_native import room

INTEGRATION = er.RegistryEntryDisabler.INTEGRATION


@pytest.mark.asyncio
async def test_cleanup_removes_the_untouched_duplicate_only(hass, caplog):
    p = product(hass, room(hass))
    reg = er.async_get(hass)

    def record(name, reported=False, **kw):
        entity_id = reg.async_get_or_create("sensor", "open_thermostat", f"fixture_boiler_fields_v1_{name}",
                                            config_entry=p, **kw).entity_id
        if reported:
            reg.async_update_entity_options(entity_id, "open_thermostat", {REPORTED: True})
        return entity_id

    owner_flow = record("measured_flow_temperature", reported=True)
    plus_flow = record("plus_flow_temperature", reported=True)  # an enabled leftover with history
    renamed = record("plus_return_temperature", reported=True)
    reg.async_update_entity(renamed, name="My return")
    classic_return = record("measured_return_temperature", reported=True)
    hidden_classic = record("pressure", disabled_by=INTEGRATION, reported=True)
    plus_pressure = record("plus_pressure", reported=True)
    other_integration = reg.async_get_or_create("sensor", "other", "fixture_boiler_fields_v1_plus_dhw_flow",
                                                config_entry=p).entity_id
    with caplog.at_level(logging.INFO):
        removed = cleanup_stale_entities(hass, p, "fixture")
    assert sorted(item.split(" ")[0] for item in removed) == sorted([plus_flow, hidden_classic])
    assert "boiler_field_duplicate" in caplog.text
    for kept in (owner_flow, renamed, classic_return, plus_pressure, other_integration):
        assert reg.async_get(kept) is not None
    assert cleanup_stale_entities(hass, p, "fixture") == []
