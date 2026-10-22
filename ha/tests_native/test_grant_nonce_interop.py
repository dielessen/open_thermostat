"""Actual finite C++/native HA nonce proof with synthetic jitter, no network."""
import json
from pathlib import Path
import pytest
from test_modern_metrics_interop import system
from test_v1_wire_interop import integrated

@pytest.mark.asyncio
@pytest.mark.parametrize("steps",[[2000]*180,[1000,3000,2000,4000,2000]*30],ids=["coarse2s360s","jitter360s"])
async def test_actual_cpp_new_nonce_prevents_prior_accumulated_deadline_loss(hass,steps):
    rows=[]
    async with system(hass,metrics_enabled=False) as (runtime,client,bus,sensors):
        assert client.grant_nonce_supported
        initial_session=client.session["adapter_session_id"]
        last_sequence=client.session["grant_sequence"];issued_ms=bus.now
        for step in steps:
            await bus.advance(step)
            assert client.ready and client.session["adapter_session_id"]==initial_session
            if client.session["grant_sequence"]!=last_sequence:
                last_sequence=client.session["grant_sequence"];issued_ms=bus.now
            assert client.grant_until<=bus.clock_base+issued_ms/1000+10+1e-8
            rows.append({"fw_now_ms":bus.now,"grant_remaining_ms":round((client.grant_until-bus.clock())*1000),
                         "lease_remaining_ms":round((client.lease_until-bus.clock())*1000),
                         "grant_sequence":client.session["grant_sequence"]})
            # No physical sample becomes fresh just because heartbeat/grant works.
            assert all(decision.current_centi_c is None and not decision.demand for decision in runtime.decisions.values())
        assert all(topic!="fw/telemetry/ems_metrics" for who,topic,raw in bus.transcript if who=="fw")
        statuses=[json.loads(raw) for who,topic,raw in bus.transcript if who=="fw" and topic=="fw/state/zones"]
        assert statuses and all(p["boiler_output_enabled"] is p["actuator_output_enabled"] is False for p in statuses)
        assert any("grant_request_nonce" in json.loads(raw) for who,topic,raw in bus.transcript if who=="fw" and topic=="fw/session")
        evidence={"scope":"Real finite C++/native HA; synthetic clock steps, no live broker/board/soak or physical outputs",
                  "rows":rows,"metrics_frames":0,"physical_flags_false":True,"runtime_actions":[]}
        # Evidence is an optional explicit verifier request, never a product file.
        import os
        if root:=os.environ.get("OPENTHERMOSTAT_GRANT_EVIDENCE_DIR"):
            name="coarse" if steps[0]==2000 else "jitter"
            (Path(root)/f"GRANT-NONCE-{name.upper()}-INTEROP.json").write_text(json.dumps(evidence,indent=2)+"\n")

@pytest.mark.asyncio
async def test_actual_cpp_lost_grants_and_old_session_replay_do_not_keep_admission(integrated):
    runtime,client,bus,binding=integrated
    await bus.start()
    old=next(raw for who,topic,raw in reversed(bus.transcript) if who=="fw" and topic=="fw/session")
    bus.drop=lambda item:item["topic"]=="fw/session"
    for _ in range(9):await bus.advance(2000)
    assert not client.ready
    await client.receive("fw/session",old)
    assert not client.ready
    assert all(decision.current_centi_c is None and not decision.demand for decision in runtime.decisions.values())

@pytest.mark.asyncio
async def test_optional_cap_absent_retains_old_heartbeat_shape_and_safe_fallback(integrated):
    runtime,client,bus,binding=integrated
    def old_hello(item):
        if item["topic"]=="fw/hello":
            item["payload"].pop("session_capabilities",None)
        return False
    bus.drop=old_hello
    await bus.start();assert client.ready and not client.grant_nonce_supported
    rows=[]
    for _ in range(23):
        await bus.advance(2000);rows.append(client.ready)
    heartbeats=[json.loads(raw) for who,topic,raw in bus.transcript if who=="ha" and topic=="ha/heartbeat"]
    assert heartbeats and all("grant_request_nonce" not in p for p in heartbeats)
    assert not all(rows) # Old conservative availability limit preserved, not weakened.
