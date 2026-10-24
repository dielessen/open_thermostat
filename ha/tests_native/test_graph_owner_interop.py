"""Actual API2 C++ handshake, real HA Store; finite pipes, no grant/admit shortcuts."""
import asyncio
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

from custom_components.open_thermostat.graph_shadow_validation import canonical,digest,GraphValidationError
from custom_components.open_thermostat.graph_wire import GraphSourceProfile,GraphShadowClient
from test_graph_shadow_storage import documents,journal,FIXTURE

ROOT=Path(__file__).resolve().parents[2]
RUNNER=Path(os.environ.get("OPENTHERMOSTAT_GRAPH_SESSION_RUNNER",str(ROOT/"out/graph-session-runner")))

@asynccontextmanager
async def pair(hass,*,stored="",anchor=None):
    anchor=anchor or FIXTURE["context"]["qualification_digest"]
    process=await asyncio.create_subprocess_exec(str(RUNNER),stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    # Drain sanitizer diagnostics concurrently: a full stderr pipe must not
    # deadlock startup or mask the original error behind teardown timeout.
    stderr_task=asyncio.create_task(process.stderr.read())
    clock=[100.0];out=deque();trace=[];nonces=[0]
    runtime=SimpleNamespace(diagnostics={},_notify=lambda:None)
    async def send(topic,raw):out.append((topic,raw))
    from custom_components.open_thermostat.graph_shadow_storage import GraphShadowJournal
    native_store=journal(hass,"native_graph_protocol").store
    j=GraphShadowJournal(native_store,anchor,lambda:clock[0])
    client=GraphShadowClient(runtime,"test_owner",send,j,
        GraphSourceProfile("e32_test",anchor),lambda:clock[0])
    def nonce():
        nonces[0]+=1
        return "ha_nonce_"+str(nonces[0])
    client._nonce=nonce
    await client.async_start()
    async def request(op,**kwargs):
        process.stdin.write((json.dumps(dict(op=op,now=int(clock[0]*1000),**kwargs))+"\n").encode())
        await process.stdin.drain()
        try:
            async with asyncio.timeout(5):line=await process.stdout.readline()
        except TimeoutError as error:
            if process.returncode is None:process.kill()
            await process.wait()
            raise AssertionError(dict(error="runner_timeout",returncode=process.returncode,
                                      stderr=(await stderr_task).decode(errors="replace"))) from error
        if not line:
            await process.wait()
            raise AssertionError(dict(error="runner_eof",returncode=process.returncode,
                                      stderr=(await stderr_task).decode(errors="replace")))
        value=json.loads(line)
        assert value["boiler_output_enabled"] is value["actuator_output_enabled"] is False
        trace.append((op,{"now":int(clock[0]*1000),**kwargs},value))
        return value
    async def deliver(frames):
        for frame in frames:await client.receive(frame["topic"],frame["raw"])
    async def drain():
        loops=0;last=None
        while out:
            loops+=1;assert loops<30
            topic,raw=out.popleft()
            last=await request("receive",topic=topic,raw=raw)
            await deliver(last["frames"])
        return last
    try:
        value=await request("initialize",controller="e32_test",boot="test_boot",
                            owner="test_owner",anchor=anchor,stored=stored)
        yield SimpleNamespace(client=client,journal=j,clock=clock,out=out,
            request=request,deliver=deliver,drain=drain,trace=trace,initial=value)
    finally:
        if process.returncode is None:
            process.stdin.close()
            try:
                async with asyncio.timeout(5):await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
        stderr=await stderr_task
        assert process.returncode==0,stderr.decode(errors="replace")

async def connect(p):
    result=await p.request("connect")
    await p.deliver(result["frames"]);await p.drain()
    return result

def staged_raw(client):
    raw,mapping,_=documents()
    ctx=client._context()
    raw.update({key:getattr(ctx,key) for key in (
        "controller_id","boot_id","epoch","adapter_id","adapter_session_id",
        "grant_id","grant_sequence")})
    return canonical(raw),canonical(mapping)

@pytest.mark.asyncio
async def test_actual_hello_open_heartbeat_cap_snapshot_stage_commit_new_session_readback(hass):
    async with pair(hass) as p:
        assert not p.initial["fault"]
        await connect(p)
        assert p.client.error=="graph_empty" and p.client._fresh()
        assert p.journal.state["accepted"] is None
        assert p.client.ready is False and p.client.graph_ready is False
        raw,mapping=staged_raw(p.client)
        await p.client.async_stage(raw,mapping)
        assert p.journal.status=="graph_staged_not_applied" and not p.journal.verified
        sent=await p.client.async_apply()
        assert json.loads(sent)["mapping"]==json.loads(mapping)
        assert p.journal.status=="awaiting_graph_readback"
        await p.drain()
        state=await p.request("status")
        assert state["revision"]==1 and state["writes"]==1 and not state["fault"]
        assert p.client.graph_ready and p.journal.verified
        assert p.journal.state["staged"] is None
        assert p.journal.state["accepted"]["config"]==json.loads(raw)["config"]
        assert p.client.ready is False and not p.journal.outputs_enabled
        assert {args["topic"] for op,args,_ in p.trace if op=="receive"}>={
            "ha/open_session","ha/heartbeat","ha/config","ha/snapshot_request"}
        assert not any(op=="admit" for op,_,_ in p.trace)

@pytest.mark.asyncio
async def test_nonce_rotation_duplicate_status_does_not_extend_deadline_and_replay_no_second_write(hass):
    async with pair(hass) as p:
        await connect(p)
        initial=p.client.grant_until
        p.clock[0]+=2;await p.client.poll();await p.drain()
        p.clock[0]+=4
        result=await p.request("tick")
        await p.deliver(result["frames"]);await p.drain()
        assert p.client.grant_until>=initial+5
        assert p.client.grant_until<=p.clock[0]+10
        session=next(f for f in result["frames"] if f["topic"]=="fw/session")
        before=p.client.grant_until
        p.clock[0]+=.1
        await p.client.receive(session["topic"],session["raw"])
        assert p.client.grant_until==before
        raw,mapping=staged_raw(p.client);await p.client.async_stage(raw,mapping)
        sent=await p.client.async_apply();await p.drain()
        old=await p.request("receive",topic="ha/config",raw=sent)
        assert old["writes"]==1 and old["revision"]==1

@pytest.mark.asyncio
@pytest.mark.parametrize("reason",["retained","changed_mapping","foreign_owner","expired"])
async def test_wire_cannot_skip_current_admission_or_digest(reason,hass):
    async with pair(hass) as p:
        result=await p.request("connect")
        if reason=="retained":
            for f in result["frames"]:await p.client.receive(f["topic"],f["raw"],retained=True)
            assert not p.out and p.client.session is None
            state=await p.request("status");assert state["writes"]==0
            return
        await p.deliver(result["frames"]);await p.drain()
        raw,mapping=staged_raw(p.client);await p.client.async_stage(raw,mapping)
        sent=await p.client.async_apply();p.out.clear()
        wire=json.loads(sent)
        if reason=="changed_mapping":wire["mapping"]["channels"][0]["resource_id"]="f"*64
        elif reason=="foreign_owner":wire["adapter_id"]="foreign"
        else:p.clock[0]+=16
        state=await p.request("receive",topic="ha/config",raw=canonical(wire))
        assert state["writes"]==0 and state["revision"]==0
        assert not p.journal.verified

@pytest.mark.asyncio
async def test_ambiguous_committed_reboot_requires_actual_new_handshake_exact_readback(hass):
    async with pair(hass) as p:
        await connect(p)
        raw,mapping=staged_raw(p.client);await p.client.async_stage(raw,mapping)
        await p.request("ambiguous");await p.client.async_apply();await p.drain()
        state=await p.request("status")
        assert state["fault"] and state["writes"]==1 and state["revision"]==0
        assert not p.journal.verified
        await p.client.async_disconnected()
        state=await p.request("reboot",boot="new_boot")
        assert not state["fault"] and state["revision"]==1
        await connect(p)
        assert p.client.graph_ready and p.journal.verified
        assert p.client.session["boot_id"]=="new_boot"
        assert p.client.ready is False

@pytest.mark.asyncio
async def test_preexisting_api1_blob_preserved_no_graph_migration_or_handshake(hass):
    legacy='{"mapping_digest":"old","mode":"shadow","revision":1,"schema":1,"zones":[]}'
    async with pair(hass,stored=legacy) as p:
        assert p.initial["fault"] and p.initial["writes"]==0
        await connect(p)
        assert not p.out and p.client.session is None
        state=await p.request("status")
        assert state["writes"]==0 and state["store_bytes"]==len(legacy)

@pytest.mark.asyncio
async def test_lost_config_result_still_requires_new_hello_not_ack_promotion(hass):
    async with pair(hass) as p:
        await connect(p)
        raw,mapping=staged_raw(p.client);await p.client.async_stage(raw,mapping)
        await p.client.async_apply()
        topic,sent=p.out.popleft()
        committed=await p.request("receive",topic=topic,raw=sent)
        assert committed["writes"]==1 and committed["revision"]==1
        # Drop config result entirely. Only actual new hello/session/snapshot.
        assert not p.journal.verified
        await p.deliver([f for f in committed["frames"] if f["topic"]=="fw/hello"])
        await p.drain()
        assert p.journal.verified and p.client.graph_ready

@pytest.mark.asyncio
async def test_old_capability_snapshot_replays_never_restore_expired_or_disconnected_readiness(hass):
    async with pair(hass) as p:
        await connect(p)
        raw,mapping=staged_raw(p.client);await p.client.async_stage(raw,mapping)
        await p.client.async_apply();await p.drain()
        assert p.client.graph_ready
        frames=[f for _,_,v in p.trace for f in v["frames"]
                if f["topic"] in ("fw/config_snapshot","fw/graph_capability")]
        await p.client.async_disconnected()
        for f in frames:await p.client.receive(f["topic"],f["raw"])
        assert not p.client.graph_ready and not p.journal.verified
        await connect(p);assert p.client.graph_ready
        p.clock[0]+=16
        await p.client.poll()
        for f in frames:await p.client.receive(f["topic"],f["raw"])
        assert not p.client.graph_ready and not p.journal.verified

@pytest.mark.asyncio
async def test_six_minute_real_protocol_jitter_preserves_send_bound_grants_without_snapshot_poll_spam(hass):
    async with pair(hass) as p:
        await connect(p)
        for _ in range(180):
            p.clock[0]+=2
            state=await p.request("tick")
            await p.deliver(state["frames"])
            await p.client.poll();state=await p.drain() or state
            assert p.client._fresh()
            # Exact pure-core expiry, not merely receipt-time+10. Test clocks
            # have known mapping; production code never compares FW clock.
            assert p.client.grant_until*1000<=state["grant_deadline_ms"]
            assert p.client.grant_until<=p.clock[0]+10
            assert p.client.lease_until<=p.clock[0]+15
        requests=[args for op,args,_ in p.trace if op=="receive"]
        snapshots=[a for a in requests if a["topic"]=="ha/snapshot_request"]
        report=dict(duration_seconds=360,synthetic_tick_seconds=2,
            ha_wire_requests=len(requests),snapshot_requests=len(snapshots),
            ha_wire_bytes=sum(len(a["raw"].encode("ascii")) for a in requests),
            firmware_frames=sum(len(v["frames"]) for _,_,v in p.trace),
            firmware_wire_bytes=sum(len(f["raw"].encode("ascii")) for _,_,v in p.trace for f in v["frames"]),
            scope="Actual C++/HA protocol, synthetic six-minute2s timing, empty readback DATA only. NOT actual-time/broker/device/GUI speed or physical/source/model readiness.")
        if output:=os.environ.get("OPENTHERMOSTAT_GRAPH_POLL_EVIDENCE"):
            Path(output).write_text(json.dumps(report,indent=2)+"\n")
        assert len(snapshots)==1,report
        assert not p.client.ready and not p.journal.outputs_enabled

@pytest.mark.asyncio
async def test_actual_transport_online_after_hello_is_not_a_session_reset_or_proof(hass):
    async with pair(hass) as p:
        hello=await p.request("connect")
        await p.deliver(hello["frames"])
        opening=p.client.open_request
        assert opening is not None
        await p.client.receive("fw/availability","online")
        assert p.client.open_request==opening and p.client.session is None
        assert p.client.grant_until==p.client.lease_until==0
        await p.drain()
        raw,mapping=staged_raw(p.client);await p.client.async_stage(raw,mapping)
        await p.client.async_apply();await p.drain()
        assert p.client.graph_ready
        deadline=p.client.grant_until
        await p.client.receive("fw/availability","online")
        assert p.client.graph_ready and p.client.grant_until==deadline
        await p.client.receive("fw/availability","offline",retained=True)
        assert p.client.graph_ready
        await p.client.receive("fw/availability","offline")
        assert not p.client.graph_ready and not p.journal.verified
        assert p.client.session is None and p.client.ready is False
