"""Actual finite C++ controller -> existing HA client -> native metric entities."""
import asyncio
from contextlib import asynccontextmanager
import json
import pytest
from types import SimpleNamespace
from homeassistant.helpers.storage import Store
from custom_components.open_thermostat.v1_wire import ShadowClient,canonical
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_metrics import async_setup_shadow_metrics
from test_v1_native import room,entry
from test_v1_wire_interop import FirmwareBus,RUNNER
from test_modern_metrics import data

@asynccontextmanager
async def system(hass,metrics_enabled=True):
    binding=room(hass,age=10000);e=entry(hass,enabled=True,room=binding)
    runtime=ShadowRuntime(hass,e,[binding]);zones,mapping=await async_build_configuration(runtime)
    args=[str(RUNNER),"ha1"]+(["metrics"] if metrics_enabled else [])
    process=await asyncio.create_subprocess_exec(*args,
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    bus=FirmwareBus(process,hass.loop.time)
    client=ShadowClient(runtime,"ha1",bus.send,Store(hass,1,"modern_metrics_interop"),zones,mapping,bus.clock)
    bus.client=client;runtime.attach_transport(client)
    await client.async_start();await runtime.async_start()
    hass.data.setdefault("open_thermostat",{})[e.entry_id]={"v1_runtime":runtime,"v1_connection":SimpleNamespace(client=client)}
    added=[];await async_setup_shadow_metrics(hass,e,lambda entities:added.extend(entities))
    try:
        await bus.event("metrics_payload",raw=canonical(data()))
        await bus.start();await bus.advance(1)
        assert client.ready and client.metrics_supported is metrics_enabled
        yield runtime,client,bus,added
    finally:
        await e._async_process_on_unload(hass);await runtime.async_stop()
        process.stdin.close();await asyncio.wait_for(process.wait(),5)
        assert process.returncode==0,await process.stderr.read()

async def ordinary_cadence(bus,milliseconds):
    # Model separate FW loop and HA2s timer; a coupled2s step makes FW grants
    # rotate every6s, exposing a separate pre-existing conservative-deadline drift.
    for second in range(milliseconds//1000):
        bus.now+=1000;bus.utc+=1
        await bus.event("tick");await bus.pump()
        if second%2==1:
            await bus.client.poll();await bus.pump()

@pytest.mark.asyncio
async def test_real_cpp_session_scoped_metrics_create_native_v2_sensor_without_control_effect(hass):
    async with system(hass) as (runtime,client,bus,sensors):
        assert client.metrics_payload["totalEnergyUsedKwhV2"]==0
        energy=next(sensor for sensor in sensors if sensor.unique_id.endswith("_energy_v2"))
        assert energy.available and energy.native_value==0 and not energy.extra_state_attributes["control_qualified"]
        frame=next(json.loads(raw) for direction,topic,raw in bus.transcript if direction=="fw" and topic=="fw/telemetry/ems_metrics")
        assert frame["boiler_output_enabled"] is frame["actuator_output_enabled"] is False
        assert frame["adapter_session_id"]==client.session["adapter_session_id"]
        before=(client.last_rx,client.lease_until,client.grant_until)
        bus.now+=1000
        await client.receive("fw/telemetry/ems_metrics",canonical(frame))
        assert before==(client.last_rx,client.lease_until,client.grant_until)
        assert not any(topic.startswith("ha/actuator") for direction,topic,raw in bus.transcript if direction=="ha")

@pytest.mark.asyncio
async def test_real_cpp_bad_getter_expires_metrics_not_control_then_new_snapshot_recovers(hass):
    async with system(hass) as (runtime,client,bus,sensors):
        frame=next(json.loads(raw) for direction,topic,raw in bus.transcript if direction=="fw" and topic=="fw/telemetry/ems_metrics")
        await bus.event("metrics_payload",raw="{invalid")
        await ordinary_cadence(bus,46000)
        assert client.ready and client.metrics_payload is None and all(not sensor.available for sensor in sensors)
        await client.receive("fw/telemetry/ems_metrics",canonical(frame))
        assert client.metrics_payload is None
        payload=data();payload["totalEnergyUsedKwhV2"]=.5
        await bus.event("metrics_payload",raw=canonical(payload))
        await ordinary_cadence(bus,16000)
        assert client.ready and client.metrics_payload["totalEnergyUsedKwhV2"]==.5
        energy=next(sensor for sensor in sensors if sensor.unique_id.endswith("_energy_v2"))
        assert energy.native_value==.5 and energy.available
