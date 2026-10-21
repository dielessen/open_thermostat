"""Production local profile decoder/factory; offline finite source/safety seams."""
from copy import deepcopy
import json,os
from pathlib import Path
import pytest
from custom_components.open_thermostat.native_provisioning import local_device_descriptor
from custom_components.open_thermostat.graph_shadow_validation import canonical
from test_native_control_plan import native_plan,native_two

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True},{"local_source":True,"legacy":True}],indirect=True)
async def test_native_local_factory_has_exact_independent_profile_and_normal_apply_readback(native_plan):
    n=native_plan;descriptor=local_device_descriptor(n.source)
    decoded=await n.peer.request("decode_local_source",raw=canonical(descriptor),controller="e32_test",owner="test_owner")
    assert decoded["accepted"] and decoded["profile_digest"]==n.policy.profile_digest and decoded["writes"]==0
    # Same normal options review/apply chain, no desired plan/profile preloaded.
    record=await n.apply()
    actual=await n.peer.request("durable_readback")
    assert actual["stored"]==canonical(record["config"]) and actual["writes"]==1
    # Absence of a genuine safety producer must inhibit even with fresh reports.
    await n.samples(16,16);await n.event("tick");await n.drain()
    assert not any(d.demand for d in n.runtime.decisions.values())
    assert actual["boiler_output_enabled"] is False and actual["actuator_output_enabled"] is False
    # Illustrative native saved networksettings; no real credentials or IO.
    settings=dict(mqtt=dict(enabled=True,modern_shadow=True,adapter_id="test_owner",
        brokerAddress="fixture-broker",brokerPort=1883,username="fixture-user",password="fixture-password",
        native_shadow_source=descriptor))
    size=len(canonical(settings).encode())+1
    assert size<=2048
    if path:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(path).open("a") as f:f.write(canonical(dict(scenario="local_logical_source_factory",
            descriptor_bytes=len(canonical(descriptor)),network_fixture_bytes=size,
            expanded_profile_bytes=len(n.source.profile_json),profile_digest=decoded["profile_digest"],
            config_bytes=actual["store_bytes"],safety_producer="UNKNOWN_NO_DEMAND",physical_outputs=False))+"\n")

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("bad",["version","owner","controller","layout","mapping_bool","legacy_integer","one_room","third_room",
 "zone_order","unknown_emitter","duplicate_resource","radiator_pi","too_young_cycle","unknown_field","huge"])
async def test_local_profile_rejects_unknown_shape_binding_budget_and_policy_without_writes(native_plan,bad):
    n=native_plan;v=deepcopy(local_device_descriptor(n.source))
    if bad=="version":v[0]="native.source.local.v9"
    elif bad=="owner":v[2]="someone_else"
    elif bad=="controller":v[1]="other_device"
    elif bad=="layout":v[3]="unverified"
    elif bad=="mapping_bool":v[4]=True
    elif bad=="legacy_integer":v[5]=1
    elif bad=="one_room":v[6].pop()
    elif bad=="third_room":v[6].append(deepcopy(v[6][0]))
    elif bad=="zone_order":v[6].reverse()
    elif bad=="unknown_emitter":v[6][0][4]=2
    elif bad=="duplicate_resource":v[6][1][5]=v[6][0][5]
    elif bad=="radiator_pi":next(z for z in v[6] if z[4]==0)[13][3]=1
    elif bad=="too_young_cycle":next(z for z in v[6] if z[4]==1)[13][0]=10
    elif bad=="unknown_field":v.append("physical_all_safe")
    else:v[0]="x"*2050
    before=await n.peer.request("durable_readback")
    result=await n.peer.request("decode_local_source",raw=canonical(v),controller="e32_test",owner="test_owner")
    after=await n.peer.request("durable_readback")
    assert not result["accepted"] and not result["profile_digest"]
    assert before["writes"]==after["writes"]==0 and before["stored"]==after["stored"]

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
async def test_long_broker_credentials_cannot_be_hidden_by_descriptor_only_budget(native_plan):
    # Existing device endpoint enforces final2048 incl preserved broker secrets.
    n=native_plan
    descriptor=local_device_descriptor(n.source)
    record=dict(mqtt=dict(native_shadow_source=descriptor,password="x"*512,adapter_id="test_owner",modern_shadow=True),
        hostname="h"*255,ntpHost="n"*255,loggerHost="l"*255,openweather=dict(appid="a"*255))
    assert len(canonical(record).encode())+1>2048
    reply=await n.peer.request("check_native_settings",raw=canonical(record),previous="{}",controller="e32_test")
    assert not reply["accepted"] and not reply["within_budget"] and reply["source_valid"]
    assert reply["writes"]==0

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True}],indirect=True)
@pytest.mark.parametrize("change",["omitted","clear","missing_mqtt","wrong_owner","disabled_mode","replacement"])
async def test_existing_settings_form_preserves_SOURCE_on_omission_and_never_silently_downgrades(native_plan,change):
    n=native_plan;descriptor=local_device_descriptor(n.source)
    previous=dict(mqtt=dict(native_shadow_source=descriptor,adapter_id="test_owner",modern_shadow=True))
    candidate=deepcopy(previous);candidate["mqtt"].pop("native_shadow_source")
    if change=="clear":candidate["mqtt"]["native_shadow_source"]=None
    elif change=="missing_mqtt":candidate.pop("mqtt")
    elif change=="wrong_owner":candidate["mqtt"]["adapter_id"]="other_owner"
    elif change=="disabled_mode":candidate["mqtt"]["modern_shadow"]=False
    elif change=="replacement":
        candidate["mqtt"]["native_shadow_source"]=deepcopy(descriptor)
        candidate["mqtt"]["native_shadow_source"][5]=True
    reply=await n.peer.request("check_native_settings",raw=canonical(candidate),previous=canonical(previous),controller="e32_test")
    assert reply["accepted"]==(change in ("omitted","clear")) and reply["writes"]==0
    if change=="omitted":assert json.loads(reply["encoded"])==previous
    elif change=="clear":assert json.loads(reply["encoded"])==candidate

@pytest.mark.asyncio
@pytest.mark.parametrize("native_plan",[{"local_source":True},{"local_source":True,"legacy":True}],indirect=True)
async def test_every_actual_codec_cjson_allocation_failure_rejects_without_leak_IO_or_retry(native_plan):
    n=native_plan
    result=await n.peer.request("probe_local_source_allocations",raw=canonical(local_device_descriptor(n.source)),
        controller="e32_test",owner="test_owner")
    assert result["accepted"] and not result["leaks"]
    assert result["allocation_faults"]==result["rejected_faults"] and 0<result["allocation_faults"]<=512
    assert result["writes"]==0
    # Only host cJSON requested bytes, NOT target heap/high-water, C++strings or NVS.
    assert result["host_cjson_peak_requested_bytes"]>0
    if path:=os.environ.get("OPENTHERMOSTAT_GRAPH_BRIDGE_EVIDENCE"):
        with Path(path).open("a") as f:f.write(canonical(dict(scenario="local_codec_allocation_faults",**result))+"\n")
