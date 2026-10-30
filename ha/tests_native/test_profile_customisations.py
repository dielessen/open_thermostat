"""The boiler profile undoes only what it did itself and never hides what the user made their own (review 5)."""
import json

import pytest
from homeassistant.helpers import area_registry as ar, entity_registry as er

from custom_components.open_thermostat.boiler_fields import INDEX_BY_NAME

from custom_components.open_thermostat.v1_boiler_fields import (
    PROFILE_HIDDEN, REPORTED, async_setup_boiler_fields, renamed_id)
from test_boiler_profile_visibility import at, profile, uid
from test_boiler_state import group_doc
from test_modern_metrics import system

INTEGRATION = er.RegistryEntryDisabler.INTEGRATION
HIDDEN = er.RegistryEntryHider.INTEGRATION


@pytest.mark.asyncio
async def test_a_hidden_record_the_user_placed_meanwhile_comes_back_and_an_own_entity_id_is_never_hidden(hass):
    await ar.async_load(hass, load_empty=True)
    kitchen = ar.async_get(hass).async_create("Keuken")
    e, r, c, now = await system(hass)
    reg = er.async_get(hass)

    def record(name, reported=False, **kw):
        entity_id = reg.async_get_or_create("sensor", "open_thermostat", uid(name), config_entry=e, **kw).entity_id
        if reported:
            reg.async_update_entity_options(entity_id, "open_thermostat", {REPORTED: True})
        return entity_id

    pressure = record("pressure", reported=True)
    own = record("storage_temperature_1", original_name="Storage temperature 1")
    reg.async_update_entity(own, new_entity_id="sensor.boiler_tank_top")
    own = "sensor.boiler_tank_top"
    plain = record("storage_temperature_2", original_name="Storage temperature 2")
    assert renamed_id(reg.async_get(own)) and not renamed_id(reg.async_get(plain))
    await async_setup_boiler_fields(hass, e, lambda entities, **kw: None)
    await c.receive("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 600}))
    await c.receive("fw/state/boiler_fields/6", group_doc(6), retained=True)
    lacking = ["pressure", "storage_temperature_1", "storage_temperature_2"]
    plus = [name for name in INDEX_BY_NAME if name.startswith("plus_")]  # the EMS+ twins: not reported
    await c.receive("fw/config/boiler_profile", profile(["measured_flow_temperature"], lacking, plus), retained=True)
    r._notify()
    # Hidden by the profile; the never-reported plain record goes; the user's own entity_id stays as it is.
    hidden = reg.async_get(pressure)
    assert hidden.disabled_by is INTEGRATION and hidden.hidden_by is HIDDEN
    assert reg.async_get(plain) is None
    assert reg.async_get(own) is not None and reg.async_get(own).disabled_by is None
    # The user puts the hidden pressure sensor in the kitchen; later the boiler reports pressure.
    reg.async_update_entity(pressure, area_id=kitchen.id)
    await c.receive("fw/config/boiler_profile", profile(["measured_flow_temperature", "pressure"],
                                                        ["storage_temperature_1"], plus), retained=True)
    r._notify()
    back = reg.async_get(pressure)
    assert back.disabled_by is None and back.hidden_by is None and back.area_id == kitchen.id
    assert PROFILE_HIDDEN not in back.options["open_thermostat"]
    await r.async_stop()
