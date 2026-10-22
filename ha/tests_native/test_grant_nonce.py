"""Original-send-time grant freshness proofs, native HA, no network."""
import json
from copy import deepcopy
import pytest
import pytest_asyncio
from custom_components.open_thermostat.v1_wire import canonical,MAX_GRANT_PROOFS
from test_modern_metrics import system

@pytest_asyncio.fixture
async def client(hass):
    e,r,c,now=await system(hass)
    c.open_request={"client_nonce":"client1"};c.open_sent=100
    c.grant_nonce_supported=True;c._nonce=lambda:"fixed_nonce"
    try:
        yield c,now
    finally:
        await r.async_stop()

def status(c,sequence=2,nonce=None,**change):
    p={"api":1,"controller_id":c.identity[0],"boot_id":c.identity[1],"epoch":c.identity[2],
       "config_revision":1,"config_digest":"a"*64,"client_nonce":"client1","adapter_id":"ha1",
       "adapter_session_id":c.session["adapter_session_id"],"grant_id":f"grant{sequence}",
       "grant_sequence":sequence,"grant_ms":10000,"mapping_ready":True}
    if nonce is not None:p["grant_request_nonce"]=nonce
    p.update(change);return p

async def heartbeat(c):
    await c.message("ha/heartbeat","adapter",{})
    return json.loads(c.send.await_args.args[1])["grant_request_nonce"]

@pytest.mark.asyncio
async def test_fresh_echo_anchors_original_send_not_receipt_and_never_renews_lease(client):
    c,now=client;nonce=await heartbeat(c);c.grant_until=101
    now[0]=106;old_lease=c.lease_until;old_source=deepcopy(c.runtime.observations)
    await c.receive("fw/session",canonical(status(c,nonce=nonce)))
    assert c.grant_until==110<now[0]+10 and c.lease_until==old_lease
    assert c.runtime.observations==old_source and c.ready
    assert nonce not in c._grant_proofs

@pytest.mark.asyncio
async def test_exact_heartbeat_retry_keeps_nonce_and_first_send_timestamp(client):
    c,now=client;nonce=await heartbeat(c);original=c.send.await_args.args[1]
    now[0]=102;await c.poll()
    assert c.send.await_args.args[1]==original and c._grant_proofs[nonce]==100
    pending=next(iter(c.pending.values()));assert pending["sent"]==100 and pending["last"]==102
    c.grant_until=101;now[0]=106
    await c.receive("fw/session",canonical(status(c,nonce=nonce)));assert c.grant_until==110

@pytest.mark.asyncio
@pytest.mark.parametrize("proof",["missing","unknown","expired","future","malformed","unsupported","evicted"])
async def test_unproven_echo_uses_safe_old_bound_never_receipt_renewal(client,proof):
    c,now=client;nonce=await heartbeat(c)
    if proof=="missing":nonce=None
    if proof=="unknown":nonce="unknown"
    if proof=="expired":c._grant_proofs[nonce]=95
    if proof=="future":c._grant_proofs[nonce]=108
    if proof=="malformed":nonce="bad/slash"
    if proof=="unsupported":c.grant_nonce_supported=False
    if proof=="evicted":
        for _ in range(MAX_GRANT_PROOFS):await heartbeat(c)
        assert nonce not in c._grant_proofs
    c.grant_until=105;now[0]=106
    await c.receive("fw/session",canonical(status(c,nonce=nonce)))
    assert c.grant_until==110<now[0]+10

@pytest.mark.asyncio
async def test_repeated_or_reordered_session_never_consumes_or_renews_proof(client):
    c,now=client;nonce=await heartbeat(c);c.grant_until=101;now[0]=106
    p=status(c,nonce=nonce);await c.receive("fw/session",canonical(p));assert c.grant_until==110
    proofs=deepcopy(c._grant_proofs);now[0]=108
    await c.receive("fw/session",canonical(p))
    assert c.grant_until==110 and c._grant_proofs==proofs
    # Consumed nonce can't reanchor a genuinely newer grant; safe fallback only.
    await c.receive("fw/session",canonical(status(c,3,nonce)))
    assert c.grant_until==115<now[0]+10

@pytest.mark.asyncio
@pytest.mark.parametrize("change",[{"boot_id":"oldBoot"},{"epoch":2},{"adapter_id":"other"},
                                  {"adapter_session_id":"oldSession"}])
async def test_foreign_session_cannot_use_local_proof(client,change):
    c,now=client;nonce=await heartbeat(c);old=c.grant_until;now[0]=106
    await c.receive("fw/session",canonical(status(c,nonce=nonce,**change)))
    assert c.grant_until in (old,0) # Existing owner mismatch resets fail-closed.
    assert not c.ready or nonce in c._grant_proofs

@pytest.mark.asyncio
async def test_bounded_proof_map_unique_sequence_even_if_test_rng_repeats(client):
    c,now=client;nonces=[await heartbeat(c) for _ in range(12)]
    assert len(set(nonces))==12 and len(c._grant_proofs)==MAX_GRANT_PROOFS
    assert len(nonces[0])<=32 and nonces[0] not in c._grant_proofs
    c.reset_session();assert not c._grant_proofs and not c.grant_nonce_supported

@pytest.mark.asyncio
async def test_old_peer_heartbeat_shape_and_readonly_cap_do_not_enable_grant_proof(client):
    c,now=client;c.grant_nonce_supported=False
    await c.message("ha/heartbeat","adapter",{})
    assert "grant_request_nonce" not in json.loads(c.send.await_args.args[1]) and not c._grant_proofs

@pytest.mark.asyncio
async def test_expired_unproven_grant_fails_closed_instead_of_receipt_extension(client):
    c,now=client;await heartbeat(c);c.grant_until=100;now[0]=106
    await c.receive("fw/session",canonical(status(c,nonce="unknown")))
    assert c.session is None and not c.ready and c.error=="invalid_firmware_message"

@pytest.mark.asyncio
@pytest.mark.parametrize("caps",[None,"session.grant_nonce.v1",{},["session.grant_nonce.v1"]*9,[False]])
async def test_absent_or_malformed_control_capability_cannot_enable_receipt_reanchor(client,caps):
    c,now=client;await heartbeat(c)
    hello={"api":1,"mode":"shadow","controller_id":"e32_lab","boot_id":"boot1","epoch":1,
           "challenge_id":"challenge1","config_revision":1,"config_digest":"a"*64,
           "lease_ms":15000,"grant_ms":10000,
           "read_only_capabilities":["session.grant_nonce.v1"]}
    if caps is not None:hello["session_capabilities"]=caps
    await c.receive("fw/hello",canonical(hello))
    assert not c.grant_nonce_supported and not c._grant_proofs
    await c.message("ha/heartbeat","adapter",{})
    assert "grant_request_nonce" not in json.loads(c.send.await_args.args[1])

@pytest.mark.asyncio
async def test_initial_grant_still_uses_open_request_roundtrip_not_an_echo(client):
    c,now=client;nonce=await heartbeat(c);c.session=None;now[0]=108
    p={"api":1,"controller_id":"e32_lab","boot_id":"boot1","epoch":1,
       "config_revision":1,"config_digest":"a"*64,"client_nonce":"client1","adapter_id":"ha1",
       "adapter_session_id":"newSession","grant_id":"newGrant","grant_sequence":1,
       "grant_ms":10000,"mapping_ready":True,"grant_request_nonce":nonce}
    await c.receive("fw/session",canonical(p))
    assert c.grant_until==110
