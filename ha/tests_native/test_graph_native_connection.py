"""One actual native HA worker; public MQTT IO intercepted, real C++ peer.

No real broker/physical/GUI apply claim. Runtime has no rooms; config tuple uses
the explicitly synthetic shared1room/floor/binary qualification fixture.
"""
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from homeassistant.components import mqtt
from homeassistant.exceptions import ConfigEntryError
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.graph_wire import GraphSourceProfile
from custom_components.open_thermostat.graph_shadow_validation import GraphValidationError
from test_v1_native import entry
from test_graph_owner_interop import pair,staged_raw
from test_graph_shadow_storage import FIXTURE


@pytest.mark.asyncio
async def test_explicit_graph_pin_uses_same_native_worker_stage_apply_cleanup(hass,monkeypatch):
    parent=entry(hass,enabled=True)
    hass.config_entries.async_update_entry(parent,options={**parent.options,"adapter_id":"test_owner"})
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
    profile=GraphSourceProfile("e32_test",FIXTURE["context"]["qualification_digest"])
    connection=NativeShadowConnection(runtime,profile);await connection.async_start()
    client=connection.client;initial_worker=connection.worker
    try:
        async with pair(hass) as p:
            client.clock=client.journal.clock=lambda:p.clock[0]
            async def deliver(frames):
                for f in frames:
                    callbacks["message"](SimpleNamespace(topic="fixture/v2/"+f["topic"],payload=f["raw"],retain=False))
                    await connection.queue.join()
            async def drain():
                for _ in range(40):
                    await connection.queue.join()
                    if not publications:return
                    topic,raw=publications.popleft()
                    reply=await p.request("receive",topic=topic,raw=raw)
                    await deliver(reply["frames"])
                raise AssertionError("protocol loop")
            result=await p.request("connect");await deliver(result["frames"]);await drain()
            assert client.error=="graph_empty"
            raw,mapping=staged_raw(client)
            await connection.async_graph_command("stage",raw,mapping)
            assert client.journal.status=="graph_staged_not_applied"
            await connection.async_graph_command("apply");assert not client.graph_ready
            await drain();state=await p.request("status")
            assert state["writes"]==1 and state["revision"]==1
            assert client.graph_ready and client.journal.verified
            assert not runtime.transport_ready and client.ready is False
            assert connection.worker is initial_worker
            from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
            data=hass.data["open_thermostat"][parent.entry_id]
            data["v1_runtime"]=runtime
            result=await async_get_config_entry_diagnostics(hass,parent)
            assert result["graph"]["readback_verified"] is True
            assert result["graph"]["control_contract_supported"] is False
            assert result["graph"]["accepted_revision"]==1
            import json
            diagnostic=json.dumps(result)
            for secret in (profile.qualification_digest,client.session["grant_id"],client.session["adapter_session_id"]):
                assert secret not in diagnostic
            callbacks["status"](False);await connection.queue.join()
            assert not client.graph_ready and not client.journal.verified
    finally:
        await runtime.async_stop()
    assert connection.worker.done() and connection.timer is None
    assert removed==["mqtt","status"] and not connection.unsubs
    assert connection.queue.empty()
    with pytest.raises(ConfigEntryError,match="graph_profile_unavailable"):
        await connection.async_graph_command("apply")


@pytest.mark.asyncio
@pytest.mark.parametrize("profile",[object(),GraphSourceProfile("bad.id","0"*64),GraphSourceProfile("e32_test","bad")])
async def test_invalid_selected_profile_no_api1_fallback_or_subscription(hass,monkeypatch,profile):
    runtime=ShadowRuntime(hass,entry(hass,enabled=True),[])
    subscribe=AsyncMock();monkeypatch.setattr(mqtt,"async_subscribe",subscribe)
    connection=NativeShadowConnection(runtime,profile)
    assert connection.prefix=="fixture/v2/"
    with pytest.raises((ConfigEntryError,GraphValidationError)):
        await connection.async_start()
    subscribe.assert_not_awaited()
    assert connection.worker is None and connection.timer is None
    await connection.async_close()


@pytest.mark.asyncio
async def test_graph_command_unavailable_in_default_profile_cannot_start_extra_worker(hass):
    connection=NativeShadowConnection(ShadowRuntime(hass,entry(hass),[]))
    assert connection.prefix=="fixture/v1/"
    with pytest.raises(ConfigEntryError,match="graph_profile_unavailable"):
        await connection.async_graph_command("apply")
    assert connection.worker is None and connection.queue.empty()
