"""boiler.output.v1 (E32 beta.22, HA 0.4.0b14): the real C++ ShadowController against the real HA client.

HA asks for the capability once per session; the E32 then reports the real
boiler_output_enabled (True while it sends the boiler request itself). Without
the request, as from HA 0.4.0b13, the E32 keeps sending False, and HA accepts
True only in a session in which it asked for it.
"""
import json
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat.v1_wire import BOILER_OUTPUT_CAPABILITY, ShadowClient, canonical
from test_modern_metrics import data
from test_session_recovery import system


async def run(bus, seconds):
    for second in range(seconds):
        bus.now += 1000
        bus.utc += 1
        await bus.event("tick")
        if second % 2:
            await bus.client.poll()
        await bus.pump()


def zone_states(bus, after=0):
    return [json.loads(raw) for direction, topic, raw in bus.transcript[after:]
            if direction == "fw" and topic == "fw/state/zones"]


def requests(bus):
    return [json.loads(raw) for direction, topic, raw in bus.transcript
            if direction == "ha" and topic == "ha/capabilities"]


@pytest.mark.asyncio
async def test_asked_for_the_flag_follows_the_e32_and_is_shown(hass, monkeypatch):
    monkeypatch.setenv("OPENTHERMOSTAT_RUNNER_BOILER_OUTPUT", "1")
    async with system(hass, metrics=True) as (runtime, bus):
        await bus.event("metrics_payload", raw=canonical(data()))
        await run(bus, 10)
        assert bus.client.boiler_output_supported
        assert any(BOILER_OUTPUT_CAPABILITY in r["read_only"] for r in requests(bus))
        assert all(s["boiler_output_enabled"] is False for s in zone_states(bus))
        mark = len(bus.transcript)
        await bus.event("boiler_output", on=True)     # the guard owns the boiler and sends
        await run(bus, 8)
        states = zone_states(bus, mark)
        assert states and states[-1]["boiler_output_enabled"] is True
        assert all(s["actuator_output_enabled"] is False for s in states)
        assert bus.client.ready and bus.client.error == "shadow_ready"  # accepted, not a session error
        assert runtime.diagnostics["boiler_output_enabled"] is True
        mark = len(bus.transcript)
        await bus.event("boiler_output", on=False)    # hand-back, a foreign 0x1A, lost readings
        await run(bus, 8)
        assert zone_states(bus, mark)[-1]["boiler_output_enabled"] is False
        assert runtime.diagnostics["boiler_output_enabled"] is False and bus.client.ready


@pytest.mark.asyncio
async def test_firmware_without_the_capability_keeps_the_old_contract(hass):
    async with system(hass, metrics=True) as (runtime, bus):
        await bus.event("metrics_payload", raw=canonical(data()))
        await run(bus, 10)
        assert not bus.client.boiler_output_supported
        assert not any(BOILER_OUTPUT_CAPABILITY in r["read_only"] for r in requests(bus))
        assert all(s["boiler_output_enabled"] is False for s in zone_states(bus))
        assert bus.client.ready


def test_true_is_accepted_only_in_the_session_that_asked_for_it():
    valid = ShadowClient.boiler_output_valid
    asked = SimpleNamespace(boiler_output_supported=True, _capabilities_sent="s1", session={"adapter_session_id": "s1"})
    assert valid(asked, False) and valid(asked, True)
    for other in (SimpleNamespace(boiler_output_supported=False, _capabilities_sent="s1", session={"adapter_session_id": "s1"}),
                  SimpleNamespace(boiler_output_supported=True, _capabilities_sent=None, session={"adapter_session_id": "s1"}),
                  SimpleNamespace(boiler_output_supported=True, _capabilities_sent="s0", session={"adapter_session_id": "s1"}),
                  SimpleNamespace(boiler_output_supported=True, _capabilities_sent="s1", session=None)):
        assert valid(other, False) and not valid(other, True)
    assert not valid(asked, 1) and not valid(asked, None) and not valid(asked, "true")
