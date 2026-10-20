"""Actual English HA backend translation resources + actual room selectors; no live writes."""
import json,os
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from homeassistant import loader
from homeassistant.helpers import translation
from custom_components.open_thermostat.v1_config_flow import ZoneSubentryFlow
from test_v1_native import entry

COMPONENT=Path(__file__).resolve().parents[1]/"config/custom_components/open_thermostat"
EXPECTED={
 "en":{"temperature_entity":"Room temperature sensor","actuator_entities":"Radiator valves (TRVs)","schedule_entity":"Weekly schedule (Home Assistant, optional)","setpoint_entity":"External temperature setting (optional)"}}

@pytest.mark.asyncio
@pytest.mark.parametrize("language",["en","nl"])
async def test_actual_backend_resources_match_native_form_and_help(hass,monkeypatch,language):
    loader.async_setup(hass)
    integration=loader.Integration(hass,"custom_components.open_thermostat",COMPONENT,
                                  json.loads((COMPONENT/"manifest.json").read_text()),
                                  top_level_files={p.name for p in COMPONENT.iterdir()})
    # Only native integration discovery is supplied; resource loading/fallback,
    # flattening and public backend API are real HA2026.10.2.
    monkeypatch.setattr(translation,"async_get_integrations",AsyncMock(return_value={"open_thermostat":integration}))
    resources=await translation.async_get_translations(hass,language,"config_subentries",{"open_thermostat"})
    parent=entry(hass);flow=ZoneSubentryFlow()
    flow.hass=hass;flow.handler=(parent.entry_id,"zone");flow.context={"source":"user"}
    form=await flow.async_step_user()
    schema={str(k):v for k,v in form["data_schema"].schema.items()}
    projection={"requested_ha_language":language,"product_label_language":"en","native_step":form["step_id"],"fields":{}}
    for step in ["user","reconfigure"]:
        prefix=f"component.open_thermostat.config_subentries.zone.step.{step}."
        for field,label in EXPECTED["en"].items():
            assert resources[prefix+"data."+field]==label
            help_text=resources[prefix+"data_description."+field]
            assert len(help_text)>60
            assert "profile C" not in label
            projection["fields"].setdefault(step,{})[field]={"label":label,"help":help_text}
        for field in ["minimum_target_temperature","maximum_target_temperature","maximum_age_ms","base_temperature","program_action"]:
            assert resources[prefix+"data."+field]
            assert resources[prefix+"data_description."+field]
    assert "sensor" in str(schema["temperature_entity"].config)
    assert "temperature" in str(schema["temperature_entity"].config)
    assert "climate" in str(schema["actuator_entities"].config)
    assert schema["actuator_entities"].config["multiple"] is True
    assert "schedule" in str(schema["schedule_entity"].config)
    assert "number" in str(schema["setpoint_entity"].config) and "climate" in str(schema["setpoint_entity"].config)
    # Technical entity IDs/values remain in native selectors; labels do not
    # convert climate to valve entities, add a report profile or touch services.
    projection["selector_configs"]={f:dict(schema[f].config) for f in EXPECTED["en"]}
    if output:=os.environ.get("OPTH_UI_RESOURCE_EVIDENCE"):
        directory=Path(output);directory.mkdir(parents=True,exist_ok=True)
        (directory/("native-form-en.json" if language=="en" else "native-form-english-fallback-nl.json")).write_text(json.dumps(projection,ensure_ascii=False,indent=2)+"\n")

def test_new_labels_have_no_schema_or_technical_field_rename():
    en=json.loads((COMPONENT/"translations/en.json").read_text())
    strings=json.loads((COMPONENT/"strings.json").read_text())
    assert en==strings
    for language in ("en","pl"):
        data=json.loads((COMPONENT/f"translations/{language}.json").read_text())
        for step in ("user","reconfigure"):
            form=data["config_subentries"]["zone"]["step"][step]
            assert set(EXPECTED["en"]).issubset(form["data"])
            assert set(EXPECTED["en"]).issubset(form["data_description"])
            assert "profile C" not in form["data"]["actuator_entities"]
        assert "{blocks}" in data["config_subentries"]["zone"]["step"]["program"]["description"]
        assert "{base}" in data["config_subentries"]["zone"]["step"]["program"]["description"]
    assert not (COMPONENT/"translations/nl.json").exists()
    assert en["config_subentries"]["zone"]["step"]["block"]["data"]["days"]=="Days"
    assert en["config_subentries"]["zone"]["step"]["block"]["data"]["temperature"]=="Target temperature"
