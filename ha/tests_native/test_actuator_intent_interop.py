"""Actual C++ sender → native HA receiver: service acceptance never device ACK."""
import json
import os
from pathlib import Path
import subprocess

import pytest
from homeassistant.exceptions import HomeAssistantError

from test_actuator_receiver import setup


def firmware_command(grant):
    runner = Path(os.environ.get('OPENTHERMOSTAT_ACTUATOR_INTENT_RUNNER',
                                 Path(__file__).resolve().parents[2] / 'out/actuator-intent-runner'))
    assert runner.is_file(), 'Build the exact-source actuator-intent-runner before native acceptance'
    result = subprocess.run([str(runner)], input=json.dumps(grant, sort_keys=True, separators=(',', ':'))+'\n',
                            text=True, capture_output=True, timeout=5, check=False)
    assert result.returncode == 0, (result.returncode, result.stderr)
    return result.stdout.strip()


@pytest.mark.asyncio
async def test_actual_cpp_command_reaches_existing_guarded_native_adapter_once(hass):
    receiver, scope, _, calls = setup(hass)
    raw = firmware_command(receiver.issue(scope=scope))
    result = await receiver.async_receive(raw, scope=scope)
    assert result.sequence == 1 and result.requested_centi_c == 2100
    assert result.status == 'ha_action_accepted'
    assert result.scope == 'service_acceptance_only'
    assert not result.device_reported and not result.valve_ready and not result.control_qualified
    assert len(calls) == 1 and calls[0]['temperature'] == 21.0
    assert (await receiver.async_receive(raw, scope=scope)).duplicate
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['expired', 'retained', 'retired', 'authorization_lost', 'changed_target'])
async def test_cpp_preparation_never_overrides_current_ha_admission(hass, failure):
    allowed = [True]
    receiver, scope, clock, calls = setup(hass, authorize=lambda: allowed[0])
    raw = firmware_command(receiver.issue(scope=scope))
    if failure == 'expired':
        clock[0] += 5
    elif failure == 'retired':
        receiver.retire()
    elif failure == 'authorization_lost':
        allowed[0] = False
    elif failure == 'changed_target':
        await receiver.async_receive(raw, scope=scope)
        payload = json.loads(raw)
        payload['target_centi_c'] = 2200
        raw = json.dumps(payload)
    with pytest.raises(HomeAssistantError):
        await receiver.async_receive(raw, scope=scope, retained=failure == 'retained')
    assert len(calls) == (1 if failure == 'changed_target' else 0)
