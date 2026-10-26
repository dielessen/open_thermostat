"""Existing actual finite C++ controller + native HA, no device/source qualification."""
import asyncio
import json
import os
from pathlib import Path
import pytest
import pytest_asyncio
from homeassistant.helpers.storage import Store
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_wire import ShadowClient,canonical,digest
from custom_components.open_thermostat.v1_model import Observation
from custom_components.open_thermostat.v1_climate import ShadowRoom
from test_v1_native import room,entry
from test_v1_wire_interop import FirmwareBus,RUNNER

@pytest_asyncio.fixture
async def seasonal(hass,tmp_path):
    binding=room(hass,age=120000);parent=entry(hass,enabled=True,room=binding)
    runtime=ShadowRuntime(hass,parent,[binding])
    zones,mapping=await async_build_configuration(runtime)
    # Exact independent expected SOURCE test pin, NOT an incoming qualification.
    expected={"schema":1,"mode":"shadow","revision":1,"mapping_digest":digest(mapping),"zones":zones}
    source=tmp_path/"source-reviewed-fixture-config.json";source.write_text(canonical(expected))
    process=await asyncio.create_subprocess_exec(str(RUNNER),"ha1","seasonal",str(source),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    bus=FirmwareBus(process,hass.loop.time)
    client=ShadowClient(runtime,"ha1",bus.send,Store(hass,1,"test.seasonal."+parent.entry_id),zones,mapping,bus.clock)
    bus.client=client;runtime.attach_transport(client);await client.async_start();await runtime.async_start()
    try:
        await bus.start()
        assert client.ready and client.journal["accepted"]["config"]==expected
        yield runtime,client,bus,binding
    finally:
        await runtime.async_stop();process.stdin.close();await asyncio.wait_for(process.wait(),5)
        assert process.returncode==0

async def fresh(runtime,client,bus,binding):
    await client.async_observation(binding.room_id,Observation(19,"qualified",0,"fixture-report",bus.clock()))
    await bus.pump()
    return runtime.decisions[binding.room_id]

def evidence(row):
    if path:=os.environ.get("OPENTHERMOSTAT_CONTEXT_EVIDENCE"):
        with Path(path).open("a") as f:f.write(json.dumps(row,sort_keys=True)+"\n")

@pytest.mark.asyncio
@pytest.mark.parametrize("fault",["dhw","source_expired"])
async def test_actual_selected_cpp_profile_reaches_native_ha_and_safe_observer_limits_win(seasonal,fault):
    runtime,client,bus,binding=seasonal
    first=await fresh(*seasonal)
    if first.reason=="seasonal_owner_changed":
        assert not first.demand
        first=await fresh(*seasonal)
    assert first.demand and first.reason=="shadow_seasonal_demand"
    entity=ShadowRoom("fixture",binding,runtime)
    assert entity.extra_state_attributes["simulated_demand"] is True
    if fault=="dhw":
        bus.now+=1  # A changed producer fact has a new acquisition time.
        await bus.event("safety_snapshot",limits_known_safe=True,dhw_state_known=True,dhw_active=True)
        stopped=await fresh(*seasonal)
        assert stopped.reason=="seasonal_dhw_priority"
    else:
        await bus.advance(3000) # Mere state/hello/getter cannot re-date boot0 safety report.
        stopped=runtime.decisions[binding.room_id]
        assert stopped.current_centi_c==1900 and stopped.reason=="seasonal_limits_unavailable"
    assert stopped.target_centi_c==2100 and not stopped.demand
    assert entity.extra_state_attributes["simulated_demand"] is False
    assert entity.extra_state_attributes["boiler_output_enabled"] is False
    assert entity.extra_state_attributes["actuator_output_enabled"] is False
    for who,topic,raw in bus.transcript:
        if topic=="fw/state/zones":
            packet=json.loads(raw)
            assert packet["boiler_output_enabled"] is packet["actuator_output_enabled"] is False
            assert packet["supervisor"]["physical_outputs_enabled"] is False
            if packet["config_revision"]==0:
                assert packet["zones"]==[]  # Legitimate pre-config hello/state, never a source row.
                continue
            assert len(packet["zones"])==1
            assert packet["zones"][0]["seasonal_policy"] is True
    evidence(dict(scenario="actual_selected_cpp_native_ha_"+fault,selected_controller_profile=True,
                  accepted_exact_source_config=True,source_report_not_redated_by_get=True,
                  stopped_reason=stopped.reason,physical_outputs_enabled=False))
