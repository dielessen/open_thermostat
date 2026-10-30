"""Actual finite C++ controller -> existing HA shadow client -> field entities."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import pytest
from homeassistant.helpers.storage import Store
from custom_components.open_thermostat.v1_wire import ShadowClient,canonical
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_mqtt import async_build_configuration
from custom_components.open_thermostat.v1_boiler_fields import async_setup_boiler_fields
from test_v1_native import room,entry
from test_v1_wire_interop import FirmwareBus,RUNNER
from test_boiler_fields import values
from custom_components.open_thermostat.boiler_fields import CATALOG_FIELDS

@asynccontextmanager
async def system(hass):
    binding=room(hass,age=10000);e=entry(hass,enabled=True,room=binding)
    runtime=ShadowRuntime(hass,e,[binding]);zones,mapping=await async_build_configuration(runtime)
    process=await asyncio.create_subprocess_exec(str(RUNNER),'ha1','boiler',
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    bus=FirmwareBus(process,hass.loop.time)
    client=ShadowClient(runtime,'ha1',bus.send,Store(hass,1,'boiler_interop'),zones,mapping,bus.clock)
    bus.client=client;runtime.attach_transport(client);await client.async_start();await runtime.async_start()
    hass.data.setdefault('open_thermostat',{})[e.entry_id]={'v1_runtime':runtime,'v1_connection':SimpleNamespace(client=client)}
    added=[];await async_setup_boiler_fields(hass,e,lambda entities:added.extend(entities))
    try:
        for group in range(7):
            await bus.event('boiler_payload',group=group,raw=canonical(values(group,sampled=1000,observed=0)))
        await bus.start();await bus.advance(1)
        assert client.ready and client.boiler_fields_supported
        yield e,runtime,client,bus,added
    finally:
        await e._async_process_on_unload(hass);await runtime.async_stop()
        process.stdin.close();await asyncio.wait_for(process.wait(),5)
        assert process.returncode==0,await process.stderr.read()

@pytest.mark.asyncio
async def test_real_cpp_publishes_bounded_groups_to_native_entities_without_commands(hass):
    async with system(hass) as (e,r,c,bus,entities):
        # The real firmware announces boiler.fields.v2; only fields with a real value get an
        # entity: no catalog row, no invalid display code, no unreliable zero filler.
        from test_boiler_fields import REAL, by_index
        r._notify()  # Entities are created on the runtime tick after their first value.
        assert c.boiler_fields_v2 and len(CATALOG_FIELDS) and set(by_index(entities))<=set(REAL)
        assert by_index(entities)[1].native_value==45
        deadline=c.boiler_fields.records[1][1]
        # HA announces boiler.fields.v2 with its next heartbeat (every 10 s since beta.19).
        for second in range(1,31):
            bus.now+=1000;bus.utc+=1
            await bus.event('tick');await bus.pump()
            if second%2==0:
                await c.poll();await bus.pump()
        assert len(c.boiler_fields.records)==69
        r._notify();assert sorted(by_index(entities))==REAL and len(entities)==len(REAL)
        assert c.boiler_fields.records[1][1]==deadline
        import json
        frames=[json.loads(raw) for direction,topic,raw in bus.transcript if direction=='fw' and topic=='fw/telemetry/boiler_fields']
        assert {p['group'] for p in frames}==set(range(7))
        assert all(len(canonical(p))<=2048 for p in frames)
        assert all(p['boiler_output_enabled'] is p['actuator_output_enabled'] is False for p in frames)
        assert not any(topic.startswith('ha/actuator') for direction,topic,raw in bus.transcript if direction=='ha')
