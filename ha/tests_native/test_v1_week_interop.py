"""Editor model -> actual existing bounded wire -> actual supplied C++ FW runner."""
from dataclasses import replace

import pytest

from custom_components.open_thermostat.v1_model import Observation
from custom_components.open_thermostat.v1_program import normalize_program
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_wire import canonical, digest
from custom_components.open_thermostat.schedule_compiler import WEEKDAYS
from test_v1_wire_interop import integrated

@pytest.mark.asyncio
async def test_local_program_actual_fw_ack_target_and_expiry(integrated):
    runtime,client,bus,binding=integrated
    program=normalize_program({day:[{"start":0,"end":86400,"target_centi_c":2200}] for day in WEEKDAYS})
    runtime.rooms[binding.room_id]=replace(binding,week_program=program)
    zones,mapping=await async_build_configuration(runtime)
    client.desired,client.mapping=zones,mapping
    schedule=zones[0]["schedule"]
    bus.utc=schedule["valid_from_utc"]+3600
    await bus.start()
    assert client.ready and client.journal["staged"] is None
    accepted=client.journal["accepted"]
    assert accepted["mapping"]["rooms"][0]["week_program"]==program
    assert accepted["config"]["mapping_digest"]==digest(mapping)
    assert accepted["config"]["zones"]==zones
    assert len(canonical(accepted["config"]).encode("ascii"))<=4096
    await client.async_observation(binding.room_id,Observation(19,"qualified",0,"test-real-report",bus.clock()))
    await bus.pump()
    decision=runtime.decisions[binding.room_id]
    assert decision.target_centi_c==2200 and decision.demand is True
    # Wall clock at exclusive finite expiry, transport/monotonic clock still valid.
    # Actual firmware must withdraw normal schedule demand, not hold target forever.
    bus.utc=schedule["valid_until_utc"]
    bus.now += 3000  # ShadowController::tick publishes periodic state every 3000 ms.
    await bus.event("tick")
    await bus.pump()
    decision=runtime.decisions[binding.room_id]
    assert decision.target_centi_c is None and decision.demand is False
    assert decision.reason=="schedule_time_invalid_or_expired"
    assert client.ready  # Explicit expiry, not confused with transport failure.
