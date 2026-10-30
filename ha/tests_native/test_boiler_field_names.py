"""Every boiler field (Classic and EMS catalog) is named in English and Dutch by translation key field_<id>."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from custom_components.open_thermostat.boiler_fields import CATALOG_FIELDS, FIELDS
from custom_components.open_thermostat.v1_boiler_fields import (
    BoilerFieldEntity, translated_fields, translation_key)

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "ha/config/custom_components/open_thermostat"


def table_ids():
    """Field ids straight from src/EMS/EmsEntityTable.h, also rows not generated into boiler_fields.py yet."""
    spec = importlib.util.spec_from_file_location("generate_ems_fields", ROOT / "scripts/generate_ems_fields.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [row["id"] for row in module.rows()]


def sensors(filename):
    return json.loads((COMPONENT / filename).read_text(encoding="utf-8"))["entity"]["sensor"]


def test_every_field_has_a_short_english_and_dutch_name():
    ids = {field[0] for field in FIELDS} | {field[0] for field in CATALOG_FIELDS} | set(table_ids())
    en, nl = sensors("strings.json"), sensors("translations/nl.json")
    missing = sorted(i for i in ids if translation_key(i) not in en or translation_key(i) not in nl)
    assert missing == [], "add EN and NL names (entity.sensor.field_<id>) for " + ", ".join(missing)
    stale = sorted(k for k in en if k.startswith("field_") and k.removeprefix("field_") not in ids)
    assert stale == []
    for key in (translation_key(i) for i in ids):
        assert en[key]["name"] != nl[key]["name"], key
        assert len(en[key]["name"]) <= 45 and len(nl[key]["name"]) <= 45, key
        assert "{" not in en[key]["name"] + nl[key]["name"], key
    # One device carries all fields: no two fields share a name.
    for names in (en, nl):
        shown = [names[translation_key(i)]["name"] for i in ids]
        assert len(shown) == len(set(shown))
    assert translated_fields() == ids


@pytest.mark.asyncio
@pytest.mark.parametrize("language,name,user_name", [("en", "Flow temperature", None),
                                                     ("nl", "Aanvoertemperatuur", None),
                                                     ("pl", "Temperatura zasilania", None),
                                                     ("nl", "Aanvoer vloer", "Aanvoer vloer")])
async def test_existing_field_entity_keeps_its_entity_id_and_gets_the_translated_name(hass, monkeypatch, language, name,
                                                                                      user_name):
    from homeassistant import loader
    from homeassistant.helpers import device_registry as dr, entity_registry as er, translation
    from test_modern_metrics import system
    from test_room_sensor_restore import platform
    e, runtime, client, now = await system(hass)
    client.boiler_fields_supported = True
    actual = await platform(hass, e)  # also sets up the loader
    integration = loader.Integration(hass, "custom_components.open_thermostat", COMPONENT,
                                     json.loads((COMPONENT / "manifest.json").read_text()),
                                     top_level_files={p.name for p in COMPONENT.iterdir()})
    monkeypatch.setattr(translation, "async_get_integrations", AsyncMock(return_value={"open_thermostat": integration}))
    hass.config.language = language
    device = dr.async_get(hass).async_get_or_create(config_entry_id=e.entry_id, name="E32",
                                                    identifiers={("open_thermostat", "fixture")})
    owner_id = "sensor.woonkamer_e32_regelaar_ketel_en_diagnose_boiler_measured_flow_temperature"
    er.async_get(hass).async_get_or_create("sensor", "open_thermostat", "fixture_boiler_fields_v1_measured_flow_temperature",
                                           config_entry=e, device_id=device.id,
                                           suggested_object_id=owner_id.split(".")[1])
    if user_name:  # a name the user gave the entity wins over the translation
        er.async_get(hass).async_update_entity(owner_id, name=user_name)
    await actual.platform_data.async_load_translations()
    flow = BoilerFieldEntity("fixture", client, 1, translated_fields())
    try:
        await actual.async_add_entities([flow])
        await hass.async_block_till_done()
        assert flow.entity_id == owner_id
        assert hass.states.get(owner_id).attributes["friendly_name"] == (user_name or "E32 " + name)
    finally:
        await actual.async_reset()
        await runtime.async_stop()
