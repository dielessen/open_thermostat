"""Versioned complete week through actual local SOURCE decoder and C++ store."""
from copy import deepcopy
import json
import os
import subprocess
from pathlib import Path

import pytest

from custom_components.open_thermostat.compact_schedule import compact_schedule, expand_schedule
from custom_components.open_thermostat.graph_shadow_validation import GraphValidationError, canonical, digest
from custom_components.open_thermostat.native_plan import WEEK_CONTRACT
from custom_components.open_thermostat.schedule_compiler import WEEKDAYS, compile_week
from custom_components.open_thermostat.v1_program import normalize_program
from test_native_control_plan import native_plan, native_two


def program(target):
    return normalize_program({day: [
        {"start": hour*3600, "end": (hour+1)*3600, "target_centi_c": target}
        for hour in (6, 9, 14, 19)] for day in WEEKDAYS}, 1600, 2400)


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "single": True, "local_source": True}], indirect=True)
async def test_one_bathroom_week_native_source_review_apply_reload_and_off(native_plan, hass, monkeypatch):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat.native_provisioning import (
        propose_local_shadow_source, local_device_descriptor, source_selection, source_from_selection, SOURCE_OPTION)
    n=native_plan
    await n.stop()
    sub=next(s for s in n.parent.subentries.values() if s.subentry_type=="zone")
    hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"name":"Bathroom","week_program":program(2200)})
    proposal=propose_local_shadow_source(hass,n.parent,"e32_test",week_reviewed=True)
    assert proposal.room_count==1 and len(local_device_descriptor(proposal)[-1])==1
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,SOURCE_OPTION:source_selection(proposal)})
    assert source_from_selection(n.parent)==proposal
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    with pytest.raises(GraphValidationError):
        propose_local_shadow_source(hass,n.parent,"e32_test")
    await hass.async_block_till_done()
    await n.start();await n.handshake()
    record=await n.apply()
    assert len(record["config"]["zones"])==len(record["config"]["groups"])==1
    assert len(record["config"]["mapping"]["channels"])==2
    assert len(expand_schedule(record["config"]["zones"][0]["schedule"])["transitions"])>100
    actual=await n.peer.request("durable_readback")
    assert json.loads(actual["stored"])==record["config"] and actual["writes"]==1
    view=(await n.flow().async_step_graph_status())["description_placeholders"]
    assert view["data_scope"]=="One complete shadow room plan, including mapping"
    assert view["control_status"]=="Verified one-room shadow control; physical outputs disabled"
    assert actual["actuator_output_enabled"] is actual["boiler_output_enabled"] is False
    await n.stop();await n.start();await n.handshake()
    assert n.client.ready and len(n.runtime.rooms)==1
    assert (await n.peer.request("durable_readback"))["writes"]==1
    await n.command(n.runtime.async_hvac_mode(n.rad.room_id,"off"))
    assert (await n.peer.request("durable_readback"))["stored"]==actual["stored"]


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "local_source": True}], indirect=True)
async def test_explicit_two_to_one_room_profile_keeps_old_plan_in_quarantine(native_plan,hass,monkeypatch):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat.native_provisioning import (
        propose_local_shadow_source, reviewed_profile_evolution, local_device_descriptor, source_selection, SOURCE_OPTION)
    n=native_plan
    first=await n.apply();before=await n.peer.request("durable_readback")
    await n.stop()
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"shadow_enabled":False,
        SOURCE_OPTION:source_selection(n.source)})
    sub=next(s for s in n.parent.subentries.values() if s.data.get("room_id")==n.floor.room_id)
    assert hass.config_entries.async_remove_subentry(n.parent,sub.subentry_id)
    draft=deepcopy(n.heating.data["draft"])
    draft["groups"]=[g for g in draft["groups"] if g["group_id"]=="radiators"]
    draft["actuators"]=[a for a in draft["actuators"] if a["room_id"]==n.rad.room_id]
    hass.config_entries.async_update_subentry(n.parent,n.heating,data={"draft":draft})
    new=reviewed_profile_evolution(n.source,propose_local_shadow_source(hass,n.parent,"e32_test",week_reviewed=True))
    assert new.room_count==1 and new.predecessor.room_count==2
    monkeypatch.setattr(integration,"_NATIVE_PLAN_SOURCE_PROFILES",())
    initialized=await n.peer.request("initialize_native_local_source",controller="e32_test",owner="test_owner",
        boot="one_room_evolution",stored=before["stored"],local_source=canonical(local_device_descriptor(new)))
    assert not initialized["fault"] and initialized["revision"]==first["config"]["revision"]
    hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"shadow_enabled":True,
        SOURCE_OPTION:source_selection(new)})
    await hass.async_block_till_done()
    await n.start();await n.event("connect");await n.handshake()
    assert not n.client.ready and n.client.error=="native_plan_profile_review_required"
    assert (await n.peer.request("durable_readback"))["stored"]==before["stored"]
    second=await n.apply()
    after=await n.peer.request("durable_readback")
    assert len(second["config"]["zones"])==1 and after["writes"]==2
    assert json.loads(after["stored"])==second["config"]


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "local_source": True}], indirect=True)
async def test_both_complete_28_block_weeks_apply_and_exact_readback_within_existing_limits(native_plan, hass):
    n = native_plan
    await n.stop()
    for room, target in ((n.rad, 2200), (n.floor, 2300)):
        sub = next(s for s in n.parent.subentries.values() if s.data.get("room_id") == room.room_id)
        hass.config_entries.async_update_subentry(n.parent, sub, data={**sub.data, "week_program": program(target)})
    await hass.async_block_till_done()
    await n.start()
    await n.handshake()
    record = await n.apply()
    config = record["config"]
    assert config["plan_contract"] == WEEK_CONTRACT and n.client.ready
    counts = [len(expand_schedule(z["schedule"])["transitions"]) for z in config["zones"]]
    assert all(100 < count <= 128 for count in counts)
    actual = await n.peer.request("durable_readback")
    assert json.loads(actual["stored"]) == config and actual["writes"] == 1
    assert actual["store_bytes"] <= 4096
    form = await n.flow().async_step_graph_status()
    assert form["description_placeholders"]["data_scope"] == "Two complete shadow room plans, including mapping"
    assert all(len(chunk) <= 60 for zone in config["zones"] for chunk in zone["schedule"]["transitions"])
    if path := os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(path).open("a") as f:
            f.write(canonical(dict(scenario="complete_28_block_weeks",transitions=counts,
                store_bytes=actual["store_bytes"],config=config,physical_outputs=False))+"\n")


@pytest.mark.parametrize("start", [1774051200, 1792195200, 2147483647, 4101148800])
def test_complete_week_codec_preserves_dst_and_epoch_bounds(start):
    end = min(start+15*86400, 4102444800)
    week = {day: [{"from": "02:15", "to": "03:15", "data": {"temperature": 22}}] for day in WEEKDAYS}
    original = compile_week(week, 1700, "Europe/Amsterdam", start, end)
    saved = deepcopy(original)
    packed = compact_schedule(original)
    assert expand_schedule(packed) == original == saved
    assert len(canonical(packed)) < len(canonical(original))


@pytest.mark.parametrize("mutation", ["empty", "bad_digit", "missing_digit", "split", "too_many", "first_offset", "wrong_policy", "extra", "reorder"])
def test_packed_schedule_refuses_ambiguous_or_invalid_encoding(mutation):
    original = compile_week({}, 1700, "UTC", 1790000000, 1790001000)
    packed = compact_schedule(original)
    if mutation == "empty": packed["transitions"] = []
    elif mutation == "bad_digit": packed["transitions"][0] = "!"+packed["transitions"][0][1:]
    elif mutation == "missing_digit": packed["transitions"][0] = packed["transitions"][0][1:]
    elif mutation == "split": packed["transitions"] *= 2
    elif mutation == "too_many": packed["transitions"] = [packed["transitions"][0]*10]*13
    elif mutation == "first_offset": packed["transitions"][0] = "AAB"+packed["transitions"][0][3:]
    elif mutation == "wrong_policy": packed["policy"] = "wall-clock-membership/v1"
    elif mutation == "extra": packed["qualification"] = True
    elif mutation == "reorder":
        packed["transitions"][0] *= 2
    with pytest.raises(GraphValidationError): expand_schedule(packed)


@pytest.mark.parametrize("case", ["spring_wholly_gap", "fall_both_folds"])
def test_packed_cpp_evaluator_matches_independent_DST_membership_every_second(case):
    root = Path(__file__).resolve().parents[2]
    row = next(r for r in json.loads((root/"test/fixtures/compiled-schedule-cases.json").read_text()) if r["case"] == case)
    schedule = compact_schedule(row["output"])
    runner = os.environ.get("OPENTHERMOSTAT_PACKED_SCHEDULE_RUNNER",str(root/"out/packed-schedule-runner"))
    start,end = schedule["valid_from_utc"],schedule["valid_until_utc"]
    # Keep each probe under the existing JSON budgets; bounded batches exercise
    # the production evaluator every second, not another decoder-as-oracle.
    for begin in range(start,end,100):
        times = list(range(begin,min(begin+100,end)))
        raw = canonical(dict(schedule=schedule,allow_packed=True,clock_valid=True,times=times))
        result = subprocess.run([runner],input=raw+"\n",capture_output=True,text=True,check=True,timeout=5)
        decoded = json.loads(result.stdout)
        assert decoded["accepted"]
        for at,target in zip(times,decoded["targets"],strict=True):
            elapsed = at-start
            expected = 2100 if case == "fall_both_folds" and (1800 <= elapsed < 3600 or 5400 <= elapsed < 7200) else 1700
            assert target["target"] == expected
    for valid,at in ((False,start),(True,end),(True,start-1)):
        raw=canonical(dict(schedule=schedule,allow_packed=True,clock_valid=valid,times=[at]))
        decoded=json.loads(subprocess.run([runner],input=raw+"\n",capture_output=True,text=True,check=True,timeout=5).stdout)
        assert decoded["accepted"] and decoded["targets"][0]["target"] is None
    raw=canonical(dict(schedule=schedule,allow_packed=False,clock_valid=True,times=[start]))
    decoded=json.loads(subprocess.run([runner],input=raw+"\n",capture_output=True,text=True,check=True,timeout=5).stdout)
    assert not decoded["accepted"] # Old decoder paths cannot silently accept the new policy.


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "local_source": True}], indirect=True)
@pytest.mark.parametrize("mutation", ["policy", "chunk", "duplicate", "out_of_range", "contract", "missing_contract", "extra"])
async def test_real_cpp_refuses_bad_week_without_replacing_durable_plan(native_plan, mutation):
    n = native_plan
    first = await n.apply()
    cfg = deepcopy(first["config"])
    original = compile_week({}, 2100, "UTC", 1790000000, 1790001000)
    cfg["zones"][0]["schedule"] = compact_schedule(original)
    schedule = cfg["zones"][0]["schedule"]
    if mutation == "policy": schedule["policy"] = "wall-clock-membership/v1"
    elif mutation == "chunk": schedule["transitions"][0] = "?"+schedule["transitions"][0][1:]
    elif mutation == "duplicate": schedule["transitions"][0] *= 2
    elif mutation == "out_of_range":
        schedule.update(compact_schedule(compile_week({}, 3500, "UTC", 1790000000, 1790001000)))
    elif mutation == "contract": cfg["plan_contract"] = "control.plan.v1"
    elif mutation == "missing_contract": cfg.pop("plan_contract")
    elif mutation == "extra": schedule["physical_safe"] = True
    cfg["revision"] += 1
    with pytest.raises(ValueError): n.source.validate_plan(cfg)
    before = await n.peer.request("durable_readback")
    await n.client.message("ha/config", "config", dict(expected_revision=1, config_digest=digest(cfg), config=cfg))
    await n.drain()
    after = await n.peer.request("durable_readback")
    assert (after["stored"], after["writes"]) == (before["stored"], before["writes"])
    assert not after["fault"]


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "local_source": True}], indirect=True)
@pytest.mark.parametrize("days", [0, 1, 15, -1])
async def test_existing_daily_refresh_only_renews_unchanged_local_week_with_exact_readback(
        native_plan, hass, monkeypatch, days):
    from datetime import timedelta
    from homeassistant.util import dt
    n = native_plan
    await n.stop()
    sub = next(s for s in n.parent.subentries.values() if s.data.get("room_id") == n.rad.room_id)
    hass.config_entries.async_update_subentry(n.parent, sub, data={**sub.data, "week_program": program(2200)})
    await hass.async_block_till_done()
    await n.start(); await n.handshake()
    first = await n.apply()
    old = await n.peer.request("durable_readback")
    now = dt.utcnow()
    monkeypatch.setattr(dt, "utcnow", lambda: now+timedelta(days=days))
    n.connection.enqueue(("refresh", None))
    await n.connection.queue.join()
    # No optimistic stage/commit before fresh current-session snapshot arrives.
    middle = await n.peer.request("durable_readback")
    assert middle["stored"] == old["stored"] and middle["writes"] == old["writes"]
    await n.drain(); await n.handshake()
    result = await n.peer.request("durable_readback")
    if days == 1:
        assert result["writes"] == old["writes"]+1
        config = json.loads(result["stored"])
        assert config["revision"] == first["config"]["revision"]+1
        assert config["zones"][0]["schedule"]["valid_from_utc"] == first["config"]["zones"][0]["schedule"]["valid_from_utc"]+86400
        assert n.client.journal["accepted"]["config"] == config and n.client.journal["staged"] is None
        assert n.client.ready
    else:
        assert (result["stored"], result["writes"]) == (old["stored"], old["writes"])
        if days == 15:
            assert not n.client.ready and n.client.error == "native_plan_horizon_review_required"
            # A later matching snapshot must not lift the inhibit. Only a new
            # explicit prepare/review/apply can install a fresh planning window.
            await n.client.poll(); await n.drain(); await n.handshake()
            assert not n.client.ready and (await n.peer.request("durable_readback"))["writes"] == old["writes"]
            renewed = await n.apply()
            assert renewed["config"]["revision"] == first["config"]["revision"]+1 and n.client.ready


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "local_source": True}], indirect=True)
async def test_pending_draft_is_never_automatically_sent_by_daily_refresh(native_plan):
    n = native_plan
    await n.flow().async_step_init({"graph_action": "prepare"})
    journal = deepcopy(n.client.journal)
    n.connection.enqueue(("refresh", None)); await n.connection.queue.join()
    assert not n.pending and n.client.journal == journal
    assert (await n.peer.request("durable_readback"))["writes"] == 0
    assert not n.client.ready


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "local_source": True}], indirect=True)
@pytest.mark.parametrize("count", [128, 129])
async def test_actual_256_point_wire_and_store_boundary_without_unknown_plan_adoption(native_plan, count):
    n = native_plan
    cfg, _ = await n.source.async_configuration(n.runtime.hass, n.parent)
    start = 1790000000
    for zone in cfg["zones"]:
        ordinary = dict(timezone="UTC", policy="wall-clock-membership/v1", base_centi_c=1700,
            valid_from_utc=start, valid_until_utc=start+15*86400,
            transitions=[[start+i*1000,1700 if i%2 else 2300] for i in range(128)])
        packed = compact_schedule(ordinary)
        if count == 129:
            extra = compact_schedule({**ordinary, "transitions": [[start,2300],[start+128000,1700]]})
            packed["transitions"][-1] += extra["transitions"][0][-6:]
        zone["schedule"] = packed
    if count == 128: n.source.validate_plan(cfg)
    else:
        with pytest.raises(GraphValidationError): n.source.validate_plan(cfg)
    await n.client.message("ha/config", "config", dict(expected_revision=0, config_digest=digest(cfg), config=cfg))
    wire = len(n.pending[-1][1].encode())
    assert wire <= 8192
    await n.drain()
    actual = await n.peer.request("durable_readback")
    assert not actual["fault"] and not n.client.ready and n.client.journal == {"accepted": None, "staged": None}
    if count == 128:
        assert json.loads(actual["stored"]) == cfg and actual["writes"] == 1 and actual["store_bytes"] <= 4096
        if path := os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
            with Path(path).open("a") as f:
                f.write(canonical(dict(scenario="actual_256_point_boundary",store_bytes=actual["store_bytes"],
                    wire_bytes=wire,unknown_remote_not_adopted=True,physical_outputs=False))+"\n")
    else:
        assert actual["stored"] == "" and actual["writes"] == 0


@pytest.mark.asyncio
async def test_existing_v1_source_refuses_the_new_plan_contract(native_plan):
    n = native_plan
    cfg, _ = await n.source.async_configuration(n.runtime.hass,n.parent)
    cfg["plan_contract"] = WEEK_CONTRACT
    cfg["zones"][0]["schedule"] = compact_schedule(compile_week({},2100,"UTC",1790000000,1790001000))
    with pytest.raises(ValueError): n.source.validate_plan(cfg)
    await n.client.message("ha/config", "config", dict(expected_revision=0,config_digest=digest(cfg),config=cfg))
    await n.drain()
    result = await n.peer.request("durable_readback")
    assert result["stored"] == "" and result["writes"] == 0 and not n.client.ready


@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan", [{"week": True, "local_source": True}], indirect=True)
async def test_auto_horizon_cannot_send_after_owner_changes_during_final_store_await(native_plan, hass, monkeypatch):
    from datetime import timedelta
    from homeassistant.util import dt
    n = native_plan
    await n.stop()
    sub = next(s for s in n.parent.subentries.values() if s.data.get("room_id") == n.rad.room_id)
    hass.config_entries.async_update_subentry(n.parent,sub,data={**sub.data,"week_program":program(2200)})
    await hass.async_block_till_done();await n.start();await n.handshake();await n.apply()
    before = await n.peer.request("durable_readback")
    journal = deepcopy(n.client.journal)
    now = dt.utcnow();monkeypatch.setattr(dt,"utcnow",lambda:now+timedelta(days=1))
    original = n.client.store.async_load
    async def changed():
        result = await original()
        hass.config_entries.async_update_entry(n.parent,options={**n.parent.options,"adapter_id":"changed_owner"})
        return result
    monkeypatch.setattr(n.client.store,"async_load",changed)
    n.connection.enqueue(("refresh",None));await n.connection.queue.join();await n.drain()
    after = await n.peer.request("durable_readback")
    assert (after["stored"],after["writes"]) == (before["stored"],before["writes"])
    assert n.client.journal == journal and not n.client.ready and not n.pending
