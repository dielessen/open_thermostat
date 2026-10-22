"""Session-scoped read-only metric snapshots; native runtime/platform lifecycle."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from homeassistant.helpers.storage import Store
from custom_components.open_thermostat.v1_runtime import ShadowRuntime
from custom_components.open_thermostat.v1_wire import ShadowClient,canonical
from custom_components.open_thermostat.metric_snapshot import CAPABILITY,LEGACY,VERSIONED,valid_snapshot
from custom_components.open_thermostat.v1_metrics import async_setup_shadow_metrics
from test_v1_native import entry,room

def data():
    return {"metricsSchema":2,"counterDefinition":"observation-total-v2","counterScope":"boot",
            "energyQuality":"estimated_nominal_modulation","protocolScope":"plus","flowQuality":"reported_integrated",
            **{key:None for key in LEGACY},**{key:0 for key in VERSIONED},
            "powerFresh":False,"outdoorTemperature":-5.7}

def packet(client,sequence=1):
    return {"api":1,"controller_id":"e32_lab","boot_id":"boot1","epoch":1,"mode":"shadow",
            "config_revision":1,"config_digest":"a"*64,"adapter_id":"ha1",
            "adapter_session_id":client.session["adapter_session_id"],"grant_id":client.session["grant_id"],
            "grant_sequence":client.session["grant_sequence"],"sequence":sequence,
            "boiler_output_enabled":False,"actuator_output_enabled":False,"metrics":data()}

async def system(hass,enabled=True):
    binding=room(hass);e=entry(hass,enabled=enabled,room=binding)
    runtime=ShadowRuntime(hass,e,[binding]);await runtime.async_start()
    now=[100.0]
    client=ShadowClient(runtime,"ha1",AsyncMock(),Store(hass,1,"metric_fixture"),[],{},lambda:now[0])
    client.identity=("e32_lab","boot1",1)
    client.session={"adapter_session_id":"session1","grant_id":"grant1","grant_sequence":1,
                    "config_revision":1,"config_digest":"a"*64,"mapping_ready":True}
    client.verified=True;client.grant_until=110;client.lease_until=115;client.last_rx=100;client.metrics_supported=True
    runtime.attach_transport(client)
    hass.data.setdefault("open_thermostat",{})[e.entry_id]={"v1_runtime":runtime,"v1_connection":SimpleNamespace(client=client)}
    return e,runtime,client,now

@pytest.mark.asyncio
async def test_snapshot_changes_neither_control_deadline_nor_room_admission_or_models(hass):
    e,r,c,now=await system(hass)
    before=(c.last_rx,c.grant_until,c.lease_until,deepcopy(r.observations),deepcopy(r.decisions))
    now[0]=102
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    assert c.metrics_payload["totalEnergyUsedKwhV2"]==0
    assert before==(c.last_rx,c.grant_until,c.lease_until,r.observations,r.decisions)
    copy=c.metrics_payload;copy["totalEnergyUsedKwhV2"]=999
    assert c.metrics_payload["totalEnergyUsedKwhV2"]==0
    c.send.assert_not_awaited()
    await r.async_stop()

@pytest.mark.asyncio
async def test_retained_duplicate_reorder_and_rotated_grant_replay_never_refresh_metrics(hass):
    e,r,c,now=await system(hass)
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)),retained=True)
    assert c.metrics_payload is None
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c,2)))
    assert c._metrics_received==100
    now[0]=105
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c,2)))
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c,1)))
    assert c._metrics_received==100 and c._metrics_highwater==2
    now[0]=145;c.grant_until=155;c.lease_until=160;c.last_rx=145
    c.session["grant_id"]="grant10";c.session["grant_sequence"]=10
    assert c.metrics_payload is None
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c,2)))
    assert c.metrics_payload is None and c._metrics_received==100
    await r.async_stop()

@pytest.mark.asyncio
@pytest.mark.parametrize("change",[
    lambda p:p.update(boot_id="other_boot"),lambda p:p.update(epoch=2),lambda p:p.update(adapter_id="foreign"),
    lambda p:p.update(adapter_session_id="old_session"),lambda p:p.update(grant_id="old_grant"),
    lambda p:p.update(config_revision=2),lambda p:p.update(config_digest="b"*64),
])
async def test_foreign_or_stale_scope_cannot_replace_current_snapshot(hass,change):
    e,r,c,now=await system(hass)
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    now[0]=102;p=packet(c,2);change(p)
    await c.receive("fw/telemetry/ems_metrics",canonical(p))
    assert c._metrics_received==100 and c._metrics_highwater==1 and c.metrics_payload
    await r.async_stop()

@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["invalid_json","oversize","legacy_numeric","bool_counter","extra","flags","schema","definition","grant_bool"])
async def test_malformed_metrics_only_fail_readonly_not_control_session(hass,kind):
    e,r,c,now=await system(hass);p=packet(c)
    if kind=="legacy_numeric":p["metrics"]["totalEnergyUsedKwh"]=0
    if kind=="bool_counter":p["metrics"]["totalEnergyUsedKwhV2"]=False
    if kind=="extra":p["metrics"]["password"]="NEVER_RELAY"
    if kind=="flags":p["boiler_output_enabled"]=True
    if kind=="schema":p["metrics"]["metricsSchema"]=2.0
    if kind=="definition":p["metrics"]["counterDefinition"]="old-delta"
    if kind=="grant_bool":p["grant_sequence"]=True
    raw="{invalid" if kind=="invalid_json" else "x"*2049 if kind=="oversize" else canonical(p)
    session=c.session;await c.receive("fw/telemetry/ems_metrics",raw)
    assert c.metrics_payload is None and c.session is session and c.ready
    assert c.last_rx==100 and c.lease_until==115 and c.grant_until==110
    c.send.assert_not_awaited();await r.async_stop()

@pytest.mark.asyncio
async def test_expired_or_missing_control_admission_or_capability_never_makes_metrics_available(hass):
    e,r,c,now=await system(hass)
    c.metrics_supported=False;await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    assert c.metrics_payload is None
    c.metrics_supported=True;now[0]=110
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    assert c.metrics_payload is None
    c.grant_until=120;c.lease_until=110
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    assert c.metrics_payload is None
    c.lease_until=125;c.verified=False
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    assert c.metrics_payload is None
    await r.async_stop()

@pytest.mark.asyncio
async def test_existing_listener_platform_no_new_io_disabled_no_entities_and_unload_cleans(hass):
    e,r,c,now=await system(hass,False);added=[]
    await async_setup_shadow_metrics(hass,e,lambda entities:added.extend(entities))
    assert not added and not r._listeners
    await r.async_stop()

@pytest.mark.asyncio
async def test_platform_capability_gate_only_writes_on_snapshot_or_availability_change(hass):
    e,r,c,now=await system(hass);c.metrics_supported=False;added=[]
    await async_setup_shadow_metrics(hass,e,lambda entities:added.extend(entities))
    assert not added and len(r._listeners)==1
    c.metrics_supported=True;r._notify()
    assert len(added)==8 and all(not sensor.available for sensor in added)
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    energy=next(sensor for sensor in added if sensor.unique_id.endswith("_energy_v2"))
    assert energy.native_value==0 and energy.available and energy.extra_state_attributes["control_qualified"] is False
    calls=[]
    for sensor in added:
        original=sensor.update_payload
        def update(payload,online,fn=original):
            calls.append(1);fn(payload,online)
        sensor.update_payload=update
    for _ in range(5):r._notify()
    assert calls==[] # No metric rewrites from ordinary2s control poll.
    c.reset_session();r._notify()
    assert len(calls)==8 and all(not sensor.available for sensor in added)
    await e._async_process_on_unload(hass);assert not r._listeners
    await r.async_stop()

@pytest.mark.asyncio
async def test_diagnostics_reports_readonly_availability_without_grants_or_payload(hass):
    from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
    e,r,c,now=await system(hass)
    await c.receive("fw/telemetry/ems_metrics",canonical(packet(c)))
    result=await async_get_config_entry_diagnostics(hass,e)
    assert result["read_only_metrics"]["supported"] and result["read_only_metrics"]["available"]
    assert not result["read_only_metrics"]["control_qualified"]
    assert "grant1" not in str(result) and "session1" not in str(result) and "totalEnergyUsedKwhV2" not in str(result)
    await r.async_stop()

@pytest.mark.asyncio
@pytest.mark.parametrize("stop_fails",[False,True])
async def test_shadow_dispatch_forwards_native_sensor_and_cleans_optional_dashboard_failure(hass,monkeypatch,stop_fails):
    import custom_components.open_thermostat as integration
    from custom_components.open_thermostat.const import CONF_CREATE_DASHBOARD
    from homeassistant.const import Platform
    e=entry(hass,enabled=False,room=room(hass))
    hass.config_entries.async_update_entry(e,options={**e.options,CONF_CREATE_DASHBOARD:True})
    forward=AsyncMock();monkeypatch.setattr(hass.config_entries,"async_forward_entry_setups",forward)
    stopped=[]
    class Dashboard:
        def __init__(self,*args):pass
        async def async_start(self):raise RuntimeError("synthetic dashboard storage failure")
        async def async_stop(self):
            stopped.append(True)
            if stop_fails:raise RuntimeError("synthetic dashboard stop failure")
    monkeypatch.setattr(integration,"RoomDashboard",Dashboard)
    with pytest.raises(RuntimeError,match="dashboard (stop|storage)"):
        await integration.async_setup_entry(hass,e)
    forward.assert_awaited_once_with(e,[Platform.CLIMATE,Platform.SENSOR])
    assert stopped==[True] and e.entry_id not in hass.data["open_thermostat"]
    await e._async_process_on_unload(hass)

def test_fixed_metric_schema_is_finite_and_not_an_arbitrary_secret_relay():
    assert valid_snapshot(data())
    for key,value in (("extra",{}),("totalEnergyUsedKwhV2",float("inf")),("totalEnergyUsedKwhV2",-1),
                      ("totalEnergyUsedKwhV2",True),("outdoorTemperature",-101)):
        p=data();p[key]=value;assert not valid_snapshot(p)
