"""Native HA Store paired with real C++ firmware config core; finite pipes, no MQTT."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
import pytest
from custom_components.open_thermostat.graph_shadow_validation import canonical,digest
from test_graph_shadow_storage import documents,capability,journal,FIXTURE
ROOT=Path(__file__).resolve().parents[2]
RUNNER=Path(os.environ.get("OPENTHERMOSTAT_GRAPH_STORE_RUNNER",str(ROOT/"out/graph-configuration-runner")))

@asynccontextmanager
async def firmware():
    process=await asyncio.create_subprocess_exec(str(RUNNER),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    async def request(**data):
        process.stdin.write((json.dumps(data)+"\n").encode());await process.stdin.drain()
        async with asyncio.timeout(5):
            line=await process.stdout.readline()
        assert line,await process.stderr.read()
        value=json.loads(line)
        assert value["boiler_output_enabled"] is value["actuator_output_enabled"] is False
        return value
    try:
        result=await request(op="initialize",controller="e32_test",boot="test_boot",owner="test_owner",anchor=FIXTURE["context"]["qualification_digest"])
        assert result["accepted"]
        yield request
    finally:
        if process.returncode is None:
            process.stdin.close()
            async with asyncio.timeout(5):
                await process.wait()
        assert process.returncode==0,await process.stderr.read()

async def admit(request,context,now=100):
    result=await request(op="admit",session=context.adapter_session_id,epoch=context.epoch,
        grant=context.grant_id,grant_sequence=context.grant_sequence,now=now)
    assert result["accepted"]
    return result

def current(context,state):
    return replace(context,current_revision=state["revision"],mapping_revision=state["mapping_revision"],
                   mapping_digest=digest(state["mapping"]))

@pytest.mark.asyncio
async def test_real_ha_durable_stage_single_send_firmware_commit_and_exact_readback(hass):
    raw,mapping,context=documents();j=journal(hass,"real_firmware_graph")
    await j.async_stage(canonical(raw),canonical(mapping),context,capability(context),100,retained=False)
    async with firmware() as request:
        await admit(request,context);replies=[]
        async def send(topic,body):
            assert topic=="ha/config";state=await request(op="apply",raw=body,mapping=canonical(mapping),now=101)
            assert state["accepted"];replies.append(state)
        await j.async_apply(send,context,capability(context),100,3,retained=False)
        assert len(replies)==1 and replies[0]["writes"]==1
        assert replies[0]["config"]==raw["config"] and replies[0]["mapping"]==mapping
        assert replies[0]["store_bytes"]<=4096
        assert not j.verified # Commit/ACK is not the HA readback gate.
        state=replies[0];ctx=current(context,state)
        assert await j.async_reconcile(state["config"],ctx,capability(ctx,state["config_digest"]),100,retained=False)
        assert j.verified and not j.outputs_enabled

@pytest.mark.asyncio
async def test_actual_ambiguous_commit_reboot_and_native_ha_restart_require_new_admission_readback(hass):
    raw,mapping,context=documents();j=journal(hass,"ambiguous_native_graph")
    await j.async_stage(canonical(raw),canonical(mapping),context,capability(context),100,retained=False)
    async with firmware() as request:
        await admit(request,context);await request(op="ambiguous")
        state=await request(op="apply",raw=canonical(raw),mapping=canonical(mapping),now=101)
        assert not state["accepted"] and state["fault"] and state["revision"]==0 and state["writes"]==1
        restored=journal(hass,"ambiguous_native_graph");assert not restored.verified
        state=await request(op="reboot",boot="new_boot")
        assert state["accepted"] and state["revision"]==1 and state["status"]=="graph_loaded_no_admission"
        ctx=replace(current(context,state),boot_id="new_boot",epoch=2,adapter_session_id="new_session",grant_id="new_grant",grant_sequence=2)
        await admit(request,ctx,102)
        assert await restored.async_reconcile(state["config"],ctx,capability(ctx,state["config_digest"]),100,retained=False)
        assert restored.verified and restored.state["staged"] is None

@pytest.mark.asyncio
async def test_firmware_disconnect_old_packet_cannot_commit_or_replace_ha_staged_state(hass):
    raw,mapping,context=documents();j=journal(hass,"disconnect_native_graph")
    await j.async_stage(canonical(raw),canonical(mapping),context,capability(context),100,retained=False)
    async with firmware() as request:
        await admit(request,context);await request(op="disconnect")
        state=await request(op="apply",raw=canonical(raw),mapping=canonical(mapping),now=101)
        assert not state["accepted"] and state["writes"]==0 and state["revision"]==0
        assert j.state["staged"] and j.state["accepted"] is None and not j.verified
