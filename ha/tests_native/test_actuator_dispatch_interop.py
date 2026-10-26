"""Actual C++ SOURCE/lease/handoff owner → unchanged guarded native HA receiver."""
import json
import os
from pathlib import Path
import subprocess

import pytest
from test_actuator_receiver import setup


def firmware_dispatch(grant, mode):
    runner = Path(os.environ.get('OPENTHERMOSTAT_ACTUATOR_DISPATCH_RUNNER',
                                 Path(__file__).resolve().parents[2] / 'out/actuator-dispatch-runner'))
    assert runner.is_file(), 'Build exact-source actuator-dispatch-runner before native acceptance'
    result = subprocess.run([str(runner), mode],
                            input=json.dumps(grant, sort_keys=True, separators=(',', ':'))+'\n',
                            text=True, capture_output=True, timeout=5, check=False)
    assert result.returncode == 0, (result.returncode, result.stderr)
    return json.loads(result.stdout)


@pytest.mark.asyncio
async def test_actual_cpp_current_source_handoff_reaches_native_ha_only_once(hass):
    receiver, scope, _, calls = setup(hass)
    result = firmware_dispatch(receiver.issue(scope=scope), 'normal')
    assert result['admitted'] and result['outcome'] == 'transport_accepted'
    assert result['handoffs'] == 1 and result['deadline'] == 6000
    assert result['repeat_refused'] and not result['retired']
    receipt = await receiver.async_receive(result['raw'], scope=scope)
    assert receipt.status == 'ha_action_accepted' and len(calls) == 1
    assert not receipt.device_reported and not receipt.valve_ready and not receipt.control_qualified
    assert (await receiver.async_receive(result['raw'], scope=scope)).duplicate
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,retired', [
    ('lease_lost', True), ('authority_lost', True), ('clock_reversed', True),
    ('grant_expired', False), ('source_delay', False), ('lease_after_encoding', True),
])
async def test_actual_cpp_expiry_or_source_loss_never_hands_off_a_frame(hass, mode, retired):
    receiver, scope, _, calls = setup(hass)
    result = firmware_dispatch(receiver.issue(scope=scope), mode)
    assert result['admitted'] and result['outcome'] == 'refused'
    assert result['handoffs'] == 0 and result['raw'] == ''
    assert result['repeat_refused'] and result['retired'] is retired
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['late_transport', 'transport_false', 'reentrant_transport'])
async def test_actual_cpp_uncertain_handoff_is_retired_and_never_retried(hass, mode):
    receiver, scope, _, calls = setup(hass)
    result = firmware_dispatch(receiver.issue(scope=scope), mode)
    assert result['outcome'] == 'outcome_unknown' and result['retired']
    assert result['handoffs'] == 1 and result['repeat_refused']
    # Raw may have been handed off; an uncertain transport result cannot grant
    # permission to repeat or promote a service/valve acknowledgement.
    assert result['raw'] and calls == []
