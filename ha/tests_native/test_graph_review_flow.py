"""Native HA options + same worker + actual C++ api2 peer; no LAN/broker IO.
Source-selected qualification is the declared synthetic fixture, not a UI grant.
"""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from collections import deque
import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from homeassistant.components import mqtt
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_config_flow import ShadowOptionsFlow
from custom_components.open_thermostat.graph_wire import GraphSourceProfile
from custom_components.open_thermostat.graph_shadow_validation import GraphValidationError,canonical,digest
from custom_components.open_thermostat.graph_wire_codec import TRANSPORT
from test_v1_native import entry
from test_graph_owner_interop import pair
from test_graph_shadow_storage import FIXTURE,documents,journal,stage,capability

@pytest_asyncio.fixture
async def native_graph(hass,monkeypatch):
    parent=entry(hass,enabled=True)
    hass.config_entries.async_update_entry(parent,options={**parent.options,"adapter_id":"test_owner"})
    original=deepcopy(dict(parent.options))
    runtime=ShadowRuntime(hass,parent,[]);await runtime.async_start()
    callbacks={};publications=deque();removed=[]
    async def subscribe(_hass,topic,callback,qos=0,encoding=None):
        assert topic=="fixture/v2/fw/#" and qos==0
        callbacks["message"]=callback
        return lambda:removed.append("mqtt")
    def status(_hass,callback):
        callbacks["status"]=callback
        return lambda:removed.append("status")
    async def publish(_hass,topic,raw,qos=0,retain=False):
        assert topic.startswith("fixture/v2/") and qos==0 and retain is False
        publications.append((topic.removeprefix("fixture/v2/"),raw))
    monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    monkeypatch.setattr(mqtt,"async_subscribe_connection_status",status)
    monkeypatch.setattr(mqtt,"async_publish",publish)
    reload=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_reload",reload)
    profile=GraphSourceProfile("e32_test",FIXTURE["context"]["qualification_digest"])
    connection=NativeShadowConnection(runtime,profile);await connection.async_start()
    data=hass.data.setdefault("open_thermostat",{}).setdefault(parent.entry_id,{})
    data.update(v1_connection=connection,v1_runtime=runtime)
    initial_worker=connection.worker
    async with pair(hass) as peer:
        client=connection.client
        client.clock=client.journal.clock=lambda:peer.clock[0]
        async def deliver(frames):
            for frame in frames:
                callbacks["message"](SimpleNamespace(topic="fixture/v2/"+frame["topic"],payload=frame["raw"],retain=False))
                await connection.queue.join()
        async def drain():
            for _ in range(50):
                await connection.queue.join()
                if not publications:return
                topic,raw=publications.popleft()
                result=await peer.request("receive",topic=topic,raw=raw)
                await deliver(result["frames"])
            raise AssertionError("finite protocol bound")
        async def connect():
            result=await peer.request("connect");await deliver(result["frames"]);await drain()
        async def stage_next():
            context=client._context()
            raw,mapping,_=documents(context.current_revision+1)
            raw.update({key:getattr(context,key) for key in (
                "controller_id","boot_id","epoch","adapter_id","adapter_session_id","grant_id","grant_sequence")})
            await connection.async_graph_command("stage",canonical(raw),canonical(mapping))
        def flow():
            f=ShadowOptionsFlow();f.hass=hass;f.handler=parent.entry_id
            return f
        await connect()
        try:
            yield SimpleNamespace(parent=parent,runtime=runtime,connection=connection,
                client=client,peer=peer,callbacks=callbacks,publications=publications,
                drain=drain,deliver=deliver,connect=connect,stage=stage_next,flow=flow)
        finally:
            await runtime.async_stop()
            assert connection.worker is initial_worker and connection.worker.done()
            assert connection.queue.empty() and connection.timer is None
            assert removed==["mqtt","status"] and not connection.unsubs
            assert dict(parent.options)==original
            reload.assert_not_awaited()

@pytest.mark.asyncio
async def test_native_options_consent_exact_apply_pending_vs_actual_readback_and_no_reload(native_graph):
    n=native_graph
    await n.stage()
    options=n.flow()
    init=await options.async_step_init()
    assert "graph_action" in {str(k) for k in init["data_schema"].schema}
    form=await options.async_step_init({"graph_action":"review"})
    assert form["type"]=="form" and form["step_id"]=="graph_review"
    assert form["description_placeholders"]["revision"]=="1"
    public=json.dumps(form["description_placeholders"])
    for secret in (n.client.session["adapter_session_id"],n.client.session["grant_id"],n.client.profile.qualification_digest):
        assert secret not in public
    before=await n.peer.request("status")
    assert before["writes"]==0 and not n.publications
    response=await options.async_step_graph_review({"confirm_apply":True})
    assert response["step_id"]=="graph_status"
    assert response["description_placeholders"]["verified"]=="False"
    assert response["description_placeholders"]["accepted"]=="0"
    assert n.client.ready is False
    await n.drain()
    state=await n.peer.request("status")
    assert state["writes"]==1 and state["revision"]==1
    status=await options.async_step_graph_status()
    assert status["description_placeholders"]["verified"]=="True"
    assert status["description_placeholders"]["accepted"]=="1"
    assert status["description_placeholders"]["staged"]=="None"
    assert n.client.graph_ready and n.runtime.transport_ready is False
    done=await options.async_step_graph_status({})
    assert done["type"]=="abort" and done["reason"]=="graph_review_complete"

@pytest.mark.asyncio
async def test_native_no_confirmation_and_submitted_without_review_cannot_send(native_graph):
    n=native_graph;await n.stage()
    f=n.flow();form=await f.async_step_graph_review()
    data=form["data_schema"]({})
    assert data["confirm_apply"] is False
    aborted=await f.async_step_graph_review(data)
    assert aborted["reason"]=="graph_review_cancelled"
    direct=await n.flow().async_step_graph_review({"confirm_apply":True})
    assert direct["reason"]=="graph_review_changed"
    assert not n.publications and (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
async def test_other_flow_commits_then_stages_new_tuple_old_review_cannot_apply(native_graph):
    n=native_graph;await n.stage()
    old=n.flow();await old.async_step_graph_review()
    other=n.flow();await other.async_step_graph_review()
    await other.async_step_graph_review({"confirm_apply":True});await n.drain()
    assert (await n.peer.request("status"))["writes"]==1
    await n.stage()
    result=await old.async_step_graph_review({"confirm_apply":True})
    assert result["type"]=="abort" and result["reason"]=="graph_review_changed"
    assert not n.publications and (await n.peer.request("status"))["writes"]==1
    assert n.client.journal.state["staged"]["config"]["revision"]==2

@pytest.mark.asyncio
async def test_reconnect_invalidates_old_review_but_keeps_staged_DATA_and_needs_new_consent(native_graph):
    n=native_graph;await n.stage()
    old=n.flow();await old.async_step_graph_review()
    n.callbacks["status"](False);await n.connection.queue.join()
    await n.connect()
    assert n.client.error=="graph_staged_not_applied"
    result=await old.async_step_graph_review({"confirm_apply":True})
    assert result["reason"]=="graph_review_changed"
    assert not n.publications and (await n.peer.request("status"))["writes"]==0
    new=n.flow();await new.async_step_graph_review()
    await new.async_step_graph_review({"confirm_apply":True});await n.drain()
    assert n.client.graph_ready and (await n.peer.request("status"))["writes"]==1

@pytest.mark.asyncio
async def test_disconnect_while_existing_worker_awaits_native_store_readback_fences_before_send(native_graph,monkeypatch):
    n=native_graph;await n.stage()
    flow=n.flow();await flow.async_step_graph_review()
    store=n.client.journal.store
    real_load=store.async_load
    entered=asyncio.Event();release=asyncio.Event()
    async def blocked_load():
        result=await real_load()
        entered.set();await release.wait()
        return result
    monkeypatch.setattr(store,"async_load",blocked_load)
    apply=asyncio.create_task(flow.async_step_graph_review({"confirm_apply":True}))
    await asyncio.wait_for(entered.wait(),2)
    # Native MQTT callback, NOT direct grant/admission manipulation.
    n.callbacks["status"](False)
    release.set()
    result=await asyncio.wait_for(apply,2)
    await n.connection.queue.join()
    assert not n.publications and (await n.peer.request("status"))["writes"]==0
    # The queued native disconnect has already invalidated the journal: show
    # pending/unverified status, not an optimistic applied or settings result.
    assert result["type"]=="form" and result["step_id"]=="graph_status"
    assert result["description_placeholders"]["verified"]=="False"
    assert result["description_placeholders"]["accepted"]=="0"
    assert result["description_placeholders"]["staged"]=="1"
    assert not n.client.graph_ready and n.client.journal.state["staged"] is not None

@pytest.mark.asyncio
async def test_live_disk_drift_while_review_waits_never_sends(native_graph):
    n=native_graph;await n.stage()
    f=n.flow();await f.async_step_graph_review()
    changed=n.client.journal.state
    changed["staged"]["config"]["rooms"][0]["base_centi_c"]+=1
    changed["staged"]["config_digest"]=digest(changed["staged"]["config"])
    await n.client.journal.store.async_save(changed) # private temporary test Store only
    result=await f.async_step_graph_review({"confirm_apply":True})
    assert result["reason"]=="graph_review_changed"
    assert not n.publications and (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
async def test_lost_config_ack_has_no_blind_repeat_and_reconnect_readback_promotes_DATA(native_graph):
    n=native_graph;await n.stage()
    f=n.flow();await f.async_step_graph_review()
    result=await f.async_step_graph_review({"confirm_apply":True})
    assert result["description_placeholders"]["verified"]=="False"
    topic,raw=n.publications.popleft()
    assert topic=="ha/config"
    committed=await n.peer.request("receive",topic=topic,raw=raw)
    # Lost publications after actual C++ durable commit; no synthetic acceptance.
    assert committed["writes"]==1
    n.callbacks["status"](False);await n.connection.queue.join()
    await n.connect()
    assert n.client.graph_ready and n.client.journal.state["staged"] is None
    assert (await n.peer.request("status"))["writes"]==1
    assert not any(topic=="ha/config" for topic,_ in n.publications)

@pytest.mark.asyncio
@pytest.mark.parametrize("field",["controller_id","boot_id","epoch","adapter_id","adapter_session_id","revision","config_digest","mapping_digest"])
async def test_journal_review_key_exact_fields_checked_under_actual_store_transaction(hass,field):
    j=journal(hass,"review_"+field)
    raw,mapping,context,_=await stage(j)
    key=j.review_key(j.state["staged"],context)
    key[field]=key[field]+1 if type(key[field]) is int else "changed"
    sent=[]
    async def send(topic,body):sent.append((topic,body))
    with pytest.raises(GraphValidationError,match="review_changed"):
        await j.async_apply_tuple(send,context,capability(context),100,1,
            retained=False,transport=TRANSPORT,reviewed=key)
    assert not sent and not j.verified and j.status=="review_changed"

@pytest.mark.asyncio
async def test_default_or_missing_source_connection_cannot_enable_graph_from_options(hass):
    parent=entry(hass)
    f=ShadowOptionsFlow();f.hass=hass;f.handler=parent.entry_id
    init=await f.async_step_init()
    assert "graph_action" not in {str(k) for k in init["data_schema"].schema}
    result=await f.async_step_init({"graph_action":"review"})
    assert result["type"]=="abort" and result["reason"]=="graph_review_unavailable"
    assert parent.options["shadow_enabled"] is False

@pytest.mark.asyncio
async def test_reviewed_token_is_copied_before_waiting_for_store_lock(hass):
    j=journal(hass,"copied_review")
    _,_,context,_=await stage(j)
    original=j.review_key(j.state["staged"],context)
    reviewed=dict(original);sent=[]
    async def send(topic,body):sent.append((topic,body))
    await j._lock.acquire()
    task=asyncio.create_task(j.async_apply_tuple(send,context,capability(context),100,1,
        retained=False,transport=TRANSPORT,reviewed=reviewed))
    await asyncio.sleep(0)
    reviewed["config_digest"]="tampered-after-call"
    j._lock.release()
    await task
    assert len(sent)==1 # captured actual token, not subsequently mutable caller object


@pytest.mark.asyncio
async def test_expired_capability_after_visible_review_cannot_publish(native_graph):
    n=native_graph;await n.stage()
    f=n.flow();await f.async_step_graph_review()
    n.peer.clock[0]+=11
    result=await f.async_step_graph_review({"confirm_apply":True})
    assert result["reason"]=="graph_review_changed"
    assert not n.publications and (await n.peer.request("status"))["writes"]==0

@pytest.mark.asyncio
async def test_uncertain_publish_never_claims_accepted_or_retries_then_real_readback_reconciles(native_graph,monkeypatch):
    n=native_graph;await n.stage()
    f=n.flow();await f.async_step_graph_review()
    real_publish=mqtt.async_publish
    async def uncertain(*args,**kwargs):
        await real_publish(*args,**kwargs)
        if args[1].endswith("/ha/config"):raise RuntimeError("finite fixture lost send completion")
    monkeypatch.setattr(mqtt,"async_publish",uncertain)
    result=await f.async_step_graph_review({"confirm_apply":True})
    assert result["type"]=="form" and result["step_id"]=="graph_status"
    assert result["description_placeholders"]["verified"]=="False"
    assert result["description_placeholders"]["accepted"]=="0"
    assert len([topic for topic,_ in n.publications if topic=="ha/config"])==1
    # Actual peer may receive the message despite lost local completion.
    monkeypatch.setattr(mqtt,"async_publish",real_publish)
    await n.drain()
    state=await n.peer.request("status")
    assert state["writes"]==1 and n.client.graph_ready
    assert n.client.journal.state["staged"] is None and n.client.ready is False
    assert not n.publications
