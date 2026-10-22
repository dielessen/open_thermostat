"""Missing pending/empty preview states using the same real native/C++ fixture."""
import pytest
from test_native_control_plan import native_plan,native_two
from test_native_plan_gui import rendered,record

@pytest.mark.asyncio
async def test_empty_and_pending_forms_are_truthful_read_only_and_keep_exact_draft(native_plan,hass):
    n=native_plan;f=n.flow()
    empty=await f.async_step_graph_status();text=await rendered(hass,empty)
    assert empty["description_placeholders"]["verified"]=="False"
    assert "Not applied" in text and "None staged" in text
    record("empty",empty,text)
    assert not n.pending and (await n.peer.request("status"))["writes"]==0
    await f.async_step_init({"graph_action":"prepare"})
    pending=await f.async_step_graph_review({"confirm_apply":True})
    text=await rendered(hass,pending);record("pending",pending,text)
    assert "waiting for exact device readback" in text
    assert pending["description_placeholders"]["accepted"]=="0" and pending["description_placeholders"]["verified"]=="False"
    assert len(n.pending)==1 and (await n.peer.request("status"))["writes"]==0
    original=n.client.journal["staged"]["config_digest"]
    for _ in range(2):await f.async_step_graph_status({"status_action":"refresh"})
    assert len(n.pending)==1 and n.client.journal["staged"]["config_digest"]==original
    await n.drain();await n.handshake()
    assert n.client.ready and (await n.peer.request("status"))["writes"]==1
