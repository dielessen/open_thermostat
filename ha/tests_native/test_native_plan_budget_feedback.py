"""Real saved week -> native enable preflight; no device or broker actions."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers.translation import async_get_translations

from custom_components.open_thermostat.graph_shadow_validation import GraphValidationError
from custom_components.open_thermostat.v1_model import CONF_ENABLED, CONF_MODE, MODE_SHADOW
from custom_components.open_thermostat.v1_program import normalize_program
from test_native_control_plan import native_plan, native_two


async def options_text(hass, category, reason):
    from homeassistant import loader
    if loader.DATA_INTEGRATIONS not in hass.data:
        loader.async_setup(hass)
    text = await async_get_translations(hass, "en", "options", {"open_thermostat"})
    return text[f"component.open_thermostat.options.{category}.{reason}"]


def enable():
    return {CONF_MODE: MODE_SHADOW, CONF_ENABLED: True, "adapter_id": "test_owner"}


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["empty", "accepted", "staged"])
async def test_saved_week_over_contract_limit_explains_failure_and_retains_all_data(native_plan, hass, history):
    n = native_plan
    if history == "accepted":
        await n.apply()
    elif history == "staged":
        await n.flow().async_step_init({"graph_action": "prepare"})
    await n.stop()
    hass.config_entries.async_update_entry(n.parent, options={**n.parent.options, CONF_ENABLED: False})
    # A valid ordinary week, but it needs at least nine UTC transitions in the
    # 15-day window. Do not trim it to make the current two-room contract fit.
    program = normalize_program({day: [{"start": 7*3600, "end": 9*3600, "target_centi_c": 2200}]
                                 for day in ("monday", "tuesday")}, 1600, 2400)
    sub = next(s for s in n.parent.subentries.values() if s.data.get("room_id") == n.rad.room_id)
    hass.config_entries.async_update_subentry(n.parent, sub, data={**sub.data, "week_program": program})
    await hass.async_block_till_done()
    before = await n.peer.request("durable_readback")
    journal = deepcopy(n.client.journal)
    options = dict(n.parent.options)
    saved_rooms = {key: dict(s.data) for key, s in n.parent.subentries.items()}

    result = await n.flow().async_step_init(enable())

    assert result["type"] == "form" and result["step_id"] == "init"
    assert result["errors"] == {"base": "native_plan_schedule_limit"}
    text = await options_text(hass, "error", result["errors"]["base"])
    assert "eight UTC transitions across both rooms" in text and "15-day" in text
    assert "nothing was sent" in text and "Full-week support remains pending" in text
    assert n.parent.options == options and n.parent.options[CONF_ENABLED] is False
    assert {key: dict(s.data) for key, s in n.parent.subentries.items()} == saved_rooms
    assert n.client.journal == journal
    after = await n.peer.request("durable_readback")
    assert (after["stored"], after["writes"]) == (before["stored"], before["writes"])
    assert not n.pending and not n.client.ready


@pytest.mark.asyncio
async def test_valid_native_plan_still_passes_enable_preflight(native_plan, hass):
    n = native_plan
    await n.stop()
    hass.config_entries.async_update_entry(n.parent, options={**n.parent.options, CONF_ENABLED: False})
    result = await n.flow().async_step_init(enable())
    assert result["type"] == "create_entry" and result["data"][CONF_ENABLED] is True
    assert not n.pending and (await n.peer.request("durable_readback"))["writes"] == 0


@pytest.mark.asyncio
async def test_off_never_requires_valid_schedule_or_compilation(native_plan, monkeypatch):
    n = native_plan
    before = await n.peer.request("durable_readback")
    compile_plan = AsyncMock(side_effect=GraphValidationError("native_transition_limit"))
    monkeypatch.setattr(type(n.source), "async_configuration", compile_plan)
    result = await n.flow().async_step_init({**enable(), CONF_ENABLED: False})
    assert result["type"] == "create_entry" and result["data"][CONF_ENABLED] is False
    compile_plan.assert_not_awaited()
    assert not n.pending
    after = await n.peer.request("durable_readback")
    assert (after["stored"], after["writes"]) == (before["stored"], before["writes"])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,reason", [
    (GraphValidationError("native_config_budget"), "native_plan_config_limit"),
    (ValueError("native_transition_limit"), "graph_control_source_review_required"),
    (GraphValidationError("private_profile_value"), "graph_control_source_review_required"),
])
async def test_preflight_budget_or_unknown_dependency_failure_never_enables_or_leaks(
        native_plan, hass, monkeypatch, failure, reason):
    n = native_plan
    await n.stop()
    hass.config_entries.async_update_entry(n.parent, options={**n.parent.options, CONF_ENABLED: False})
    monkeypatch.setattr(type(n.source), "async_configuration", AsyncMock(side_effect=failure))
    options = dict(n.parent.options)
    result = await n.flow().async_step_init(enable())
    assert result["errors"] == {"base": reason} and result["type"] == "form"
    text = await options_text(hass, "error", reason)
    assert "private_profile_value" not in text and "native_transition_limit" not in text
    if reason == "native_plan_config_limit":
        assert "4096-byte" in text and "nothing was sent" in text
    assert n.parent.options == options and not n.pending
    assert (await n.peer.request("durable_readback"))["writes"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,reason", [
    (GraphValidationError("native_transition_limit"), "native_plan_schedule_limit"),
    (GraphValidationError("native_config_budget"), "native_plan_config_limit"),
    (ValueError("private_profile_value"), "native_plan_prepare_failed"),
])
async def test_existing_prepare_worker_failure_keeps_plan_and_uses_native_wording(
        native_plan, hass, monkeypatch, failure, reason):
    n = native_plan
    await n.apply()
    before = await n.peer.request("durable_readback")
    journal = deepcopy(n.client.journal)
    # Real bounded command worker still owns the command; replace only the
    # failing schedule/dependency boundary, not the options flow or transport.
    monkeypatch.setattr(type(n.source), "async_configuration", AsyncMock(side_effect=failure))
    result = await n.flow().async_step_init({"graph_action": "prepare"})
    assert result["type"] == "abort" and result["reason"] == reason
    text = await options_text(hass, "abort", reason)
    assert "DATA" not in text and "private_profile_value" not in text
    assert n.client.journal == journal and not n.pending
    after = await n.peer.request("durable_readback")
    assert (after["stored"], after["writes"]) == (before["stored"], before["writes"])
