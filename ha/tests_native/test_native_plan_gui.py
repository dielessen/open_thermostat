"""Native translated forms and actual C++ACKs; not frontend/browser/device proof."""
import json,os
from pathlib import Path
from copy import deepcopy
import pytest
from homeassistant.helpers.translation import async_get_translations
from test_native_control_plan import native_plan,native_two

async def rendered(hass,form):
    from homeassistant import loader
    if loader.DATA_INTEGRATIONS not in hass.data:loader.async_setup(hass)
    text=await async_get_translations(hass,"en","options",{"open_thermostat"})
    prefix="component.open_thermostat.options.step."+form["step_id"]
    return text[prefix+".title"]+"\n"+text[prefix+".description"].format(**form["description_placeholders"])

def record(name,form,description):
    if p:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        path=Path(p).parent/"NATIVE-FORMS.jsonl"
        with path.open("a") as f:f.write(json.dumps(dict(scenario=name,form={k:v for k,v in form.items() if k in ("type","step_id","description_placeholders")},english=description),sort_keys=True)+"\n")

async def applied_reply(n):
    f=n.flow();await f.async_step_init({"graph_action":"prepare"})
    await f.async_step_graph_review({"confirm_apply":True})
    topic,raw=n.pending.popleft();assert topic=="ha/config"
    actual=await n.peer.request("receive",topic=topic,raw=raw)
    ack=next(frame for frame in actual["frames"] if frame["topic"]=="fw/config_result")
    return f,actual,ack

@pytest.mark.asyncio
async def test_native_review_identifies_complete_plan_not_DATA_only(native_plan,hass):
    n=native_plan;f=n.flow();review=await f.async_step_init({"graph_action":"prepare"})
    text=await rendered(hass,review)
    record("staged_review",review,text)
    assert "Two complete shadow room plans" in text
    assert "stores this exact reviewed DATA tuple only" not in text
    before=await n.peer.request("durable_readback")
    cancelled=await f.async_step_graph_review({"confirm_apply":False})
    assert cancelled["reason"]=="graph_review_cancelled"
    after=await n.peer.request("durable_readback")
    assert before["stored"]==after["stored"]=="" and after["writes"]==0

@pytest.mark.asyncio
async def test_current_verified_readback_is_not_presented_as_still_waiting(native_plan,hass):
    n=native_plan;await n.apply()
    f=n.flow();state=await f.async_step_graph_status();text=await rendered(hass,state)
    record("verified",state,text)
    assert "Verified two-room shadow control" in text
    assert "Fresh plan readback required" not in text
    assert state["description_placeholders"]["verified"]=="True"
    before=await n.peer.request("durable_readback")
    for _ in range(3):await f.async_step_graph_status({"status_action":"refresh"})
    assert not n.pending
    after=await n.peer.request("durable_readback")
    assert after["stored"]==before["stored"] and after["writes"]==before["writes"]==1

@pytest.mark.asyncio
async def test_real_cpp_ACK_visible_without_any_readback_or_authority_change(native_plan,hass):
    n=native_plan;f,result,ack=await applied_reply(n)
    before=(n.client.grant_until,n.client.lease_until,n.client.last_rx,deepcopy(n.client.journal))
    await n.deliver([ack])
    state=await f.async_step_graph_status();text=await rendered(hass,state)
    record("actual_ACK_only",state,text)
    assert state["description_placeholders"]["device_result"]=="acknowledged_unverified"
    assert "Acknowledged, but not verified by readback" in text
    assert state["description_placeholders"]["verified"]=="False" and state["description_placeholders"]["accepted"]=="0"
    assert before==(n.client.grant_until,n.client.lease_until,n.client.last_rx,n.client.journal)
    assert not n.client.ready
    await n.deliver([frame for frame in result["frames"] if frame is not ack]);await n.drain();await n.handshake()
    assert n.client.ready
    assert n.client.graph_status["device_result"] is None # new configuration/session, never restore ACK

@pytest.mark.asyncio
@pytest.mark.parametrize("wrong",["sequence","sequence_bool","session","boot","digest","revision","revision_float","status","private_extra","retained","expired","clock_reversal"])
async def test_unmatched_or_stale_cpp_ACK_cannot_change_public_state_or_deadlines(native_plan,wrong):
    n=native_plan;_,_,ack=await applied_reply(n)
    value=json.loads(ack["raw"])
    if wrong=="sequence":value["sequence"]+=1
    elif wrong=="sequence_bool":value["sequence"]=True
    elif wrong=="session":value["adapter_session_id"]="other_session"
    elif wrong=="boot":value["boot_id"]="old_boot"
    elif wrong=="digest":value["config_digest"]="a"*64
    elif wrong=="revision":value["config_revision"]+=1
    elif wrong=="revision_float":value["config_revision"]=float(value["config_revision"])
    elif wrong=="status":value["status"]="synthetic-secret-status"
    elif wrong=="private_extra":value["password"]="synthetic-secret"
    elif wrong=="expired":n.peer.clock[0]+=11
    elif wrong=="clock_reversal":n.peer.clock[0]-=1
    before=(n.client.last_rx,n.client.grant_until,n.client.lease_until,deepcopy(n.client.journal))
    await n.client.receive("fw/config_result",json.dumps(value),retained=wrong=="retained")
    assert n.client.graph_status["device_result"] is None
    assert (n.client.last_rx,n.client.grant_until,n.client.lease_until,n.client.journal)==before
    assert not n.client.ready

@pytest.mark.asyncio
async def test_disconnected_or_closed_connection_shows_offline_not_cached_verified(native_plan,hass):
    n=native_plan;await n.apply();f=n.flow()
    await n.client.async_disconnected()
    offline=await f.async_step_graph_status();text=await rendered(hass,offline)
    record("offline",offline,text)
    assert "Disconnected" in text and offline["description_placeholders"]["verified"]=="False"
    before=await n.peer.request("durable_readback")
    # A finished existing worker/client may remain briefly in entry data during
    # public lifecycle teardown. Read-only status must not revive cached proof.
    await n.client.async_close()
    closed=await f.async_step_graph_status({"status_action":"refresh"})
    assert closed["step_id"]=="graph_status" and closed["description_placeholders"]["verified"]=="False"
    assert "Disconnected" in await rendered(hass,closed)
    assert not n.pending
    after=await n.peer.request("durable_readback")
    assert before["stored"]==after["stored"] and before["writes"]==after["writes"]==1

@pytest.mark.asyncio
async def test_actual_revision_conflict_is_human_readable_and_never_adopted(native_plan,hass):
    n=native_plan;f=n.flow();await f.async_step_init({"graph_action":"prepare"})
    await f.async_step_graph_review({"confirm_apply":True})
    topic,raw=n.pending.popleft();value=json.loads(raw);value["expected_revision"]=7
    actual=await n.peer.request("receive",topic=topic,raw=json.dumps(value,sort_keys=True,separators=(",",":")))
    await n.deliver(actual["frames"])
    state=await f.async_step_graph_status();text=await rendered(hass,state)
    record("conflict",state,text)
    assert "Conflict" in text and state["description_placeholders"]["verified"]=="False"
    assert n.client.journal["accepted"] is None and n.client.journal["staged"] is not None
    assert actual["writes"]==0 and not n.pending

@pytest.mark.asyncio
async def test_native_GUI_exposes_two_room_values_but_no_session_or_SOURCEsecrets(native_plan,hass):
    n=native_plan;f=n.flow();state=await f.async_step_init({"graph_action":"prepare"})
    text=await rendered(hass,state)
    assert n.rad.room_id in text and n.floor.room_id in text
    assert "21.00 °C" in text and "19.00 °C" in text
    for secret in (n.client.session["adapter_session_id"],n.client.session["grant_id"],n.source.policy.profile_digest):
        assert secret not in text
    assert (await n.peer.request("status"))["writes"]==0

def test_unknown_status_or_result_is_not_reflected_into_user_prose():
    from custom_components.open_thermostat.plan_presentation import labels
    view=labels("synthetic-secret-url","synthetic-secret-token",False,native=True)
    assert "synthetic" not in json.dumps(view)

@pytest.mark.asyncio
async def test_SOURCE_drift_cannot_leave_cached_success_prose(native_plan,hass,monkeypatch):
    import custom_components.open_thermostat as integration
    n=native_plan;await n.apply()
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    state=await n.flow().async_step_graph_status();text=await rendered(hass,state)
    assert state["description_placeholders"]["verified"]=="False"
    assert "Exact current plan readback verified" not in text
    assert "no longer current" in text and "physical outputs disabled" in text
    assert not n.pending and (await n.peer.request("status"))["writes"]==1
