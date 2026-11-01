"""actuator.output.v1 (E32 beta.24 radiator valves): the real C++ ShadowController against the real HA client.

The E32 cannot name the capability in its hello (the lists are full), so HA asks for
it beside boiler.output.v1. The E32 then reports the real actuator_output_enabled
(True while a room's valve control is on and the output enabled); HA accepts True
only in a session in which it asked. Firmware without valves ignores the name.
"""
import json
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat.v1_wire import ACTUATOR_OUTPUT_CAPABILITY, BOILER_OUTPUT_CAPABILITY, ShadowClient, canonical
from test_boiler_output_interop import requests, run, zone_states
from test_modern_metrics import data
from test_session_recovery import system


@pytest.mark.asyncio
async def test_asked_for_beside_boiler_output_the_flag_follows_the_valves(hass, monkeypatch):
    monkeypatch.setenv("OPENTHERMOSTAT_RUNNER_BOILER_OUTPUT", "1")
    monkeypatch.setenv("OPENTHERMOSTAT_RUNNER_ACTUATOR_OUTPUT", "1")
    async with system(hass, metrics=True) as (runtime, bus):
        await bus.event("metrics_payload", raw=canonical(data()))
        await run(bus, 10)
        asked = [r["read_only"] for r in requests(bus)]
        assert asked and all(BOILER_OUTPUT_CAPABILITY in r and ACTUATOR_OUTPUT_CAPABILITY in r and len(r) <= 8 for r in asked)
        assert all(s["actuator_output_enabled"] is False for s in zone_states(bus))
        mark = len(bus.transcript)
        await bus.event("actuator_output", on=True)   # a room's valve control on, the E32 drives the boiler
        await run(bus, 8)
        states = zone_states(bus, mark)
        assert states and states[-1]["actuator_output_enabled"] is True
        assert bus.client.ready and bus.client.error == "shadow_ready"
        assert runtime.diagnostics["actuator_output_enabled"] is True
        mark = len(bus.transcript)
        await bus.event("actuator_output", on=False)
        await run(bus, 8)
        assert zone_states(bus, mark)[-1]["actuator_output_enabled"] is False
        assert runtime.diagnostics["actuator_output_enabled"] is False and bus.client.ready


@pytest.mark.asyncio
async def test_firmware_without_valves_keeps_false_although_asked(hass, monkeypatch):
    monkeypatch.setenv("OPENTHERMOSTAT_RUNNER_BOILER_OUTPUT", "1")   # beta.22/23: boiler output, no valves
    async with system(hass, metrics=True) as (runtime, bus):
        await bus.event("metrics_payload", raw=canonical(data()))
        await bus.event("actuator_output", on=True)
        await run(bus, 18)
        assert any(ACTUATOR_OUTPUT_CAPABILITY in r["read_only"] for r in requests(bus))
        assert all(s["actuator_output_enabled"] is False for s in zone_states(bus))
        assert bus.client.ready


def test_true_is_accepted_only_in_the_session_that_asked_for_it():
    valid = ShadowClient.actuator_output_valid
    asked = SimpleNamespace(boiler_output_supported=True, _capabilities_sent="s1", session={"adapter_session_id": "s1"})
    assert valid(asked, False) and valid(asked, True)
    for other in (SimpleNamespace(boiler_output_supported=False, _capabilities_sent="s1", session={"adapter_session_id": "s1"}),
                  SimpleNamespace(boiler_output_supported=True, _capabilities_sent=None, session={"adapter_session_id": "s1"}),
                  SimpleNamespace(boiler_output_supported=True, _capabilities_sent="s0", session={"adapter_session_id": "s1"}),
                  SimpleNamespace(boiler_output_supported=True, _capabilities_sent="s1", session=None)):
        assert valid(other, False) and not valid(other, True)
    assert not valid(asked, 1) and not valid(asked, None) and not valid(asked, "true")
