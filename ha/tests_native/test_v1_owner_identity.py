
"""Per-entry owner identity, deliberately no shared production fallback."""
import re
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import ConfigEntryError
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from test_v1_native import entry, room


def flow(hass):
    result = OpenThermostatConfigFlow()
    result.hass = hass
    result.context = {"source": "user"}
    result.handler = "open_thermostat"
    return result


def default_owner(form):
    return next(marker.default() for marker in form["data_schema"].schema
                if str(marker) == "adapter_id")


@pytest.mark.asyncio
async def test_random_owner_generated_once_per_flow_and_persisted(hass):
    first = flow(hass)
    owner = default_owner(await first.async_step_shadow())
    assert re.fullmatch("[0-9a-f]{32}", owner)
    assert default_owner(await first.async_step_shadow()) == owner
    second = flow(hass)
    assert default_owner(await second.async_step_shadow()) != owner
    created = await first.async_step_shadow({"topic_prefix": "new_owner_fixture"})
    assert created["data"]["adapter_id"] == owner
    assert created["options"]["shadow_enabled"] is False


@pytest.mark.asyncio
async def test_explicit_provisioned_owner_allowed_but_invalid_owner_not(hass):
    first = flow(hass)
    bad = await first.async_step_shadow({"topic_prefix": "new_owner_fixture", "adapter_id": "a/b"})
    assert bad["type"] == "form"
    assert bad["errors"]["base"] == "invalid_adapter_id"
    created = await first.async_step_shadow({"topic_prefix": "new_owner_fixture", "adapter_id": "explicit_owner_32"})
    assert created["data"]["adapter_id"] == "explicit_owner_32"


@pytest.mark.asyncio
async def test_missing_runtime_owner_fails_before_mqtt_subscription(hass, monkeypatch):
    binding = room(hass)
    parent = entry(hass, enabled=True)
    hass.config_entries.async_update_entry(parent, data={
        k:v for k,v in parent.data.items() if k != "adapter_id"})
    runtime = ShadowRuntime(hass, parent, [binding])
    from homeassistant.components import mqtt
    subscribe = AsyncMock()
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    connection = NativeShadowConnection(runtime)
    with pytest.raises(ConfigEntryError, match="owner ID"):
        await connection.async_start()
    assert not subscribe.called


@pytest.mark.asyncio
async def test_options_missing_owner_requires_deliberate_shadow_provision(hass):
    parent = entry(hass)
    hass.config_entries.async_update_entry(parent, data={
        k:v for k,v in parent.data.items() if k != "adapter_id"})
    options = ShadowOptionsFlow()
    options.hass = hass
    options.handler = parent.entry_id
    # Native OptionsFlow resolves its config entry from handler.
    result = await options.async_step_init({"integration_mode": "v1_shadow", "shadow_enabled": True})
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_adapter_id"
    legacy = await options.async_step_init({"integration_mode": "legacy", "shadow_enabled": True})
    assert legacy["type"] == "create_entry"
    assert legacy["data"]["shadow_enabled"] is False
    assert "adapter_id" not in legacy["data"]
