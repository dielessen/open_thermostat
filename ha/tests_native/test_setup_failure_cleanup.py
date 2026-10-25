"""Actual HA/runtime lifecycle; only subscription/start-failure boundaries injected."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt

import custom_components.open_thermostat as integration
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.product import PRODUCT_CONFIG
from custom_components.open_thermostat.v1_mqtt import NativeShadowConnection
from test_v1_native import entry, room
from custom_components.open_thermostat.v1_model import MODE_LEGACY, MODE_SHADOW


@pytest.fixture(autouse=True)
def unloaded_platform_boundary(hass,monkeypatch):
    monkeypatch.setattr(hass.config_entries,'async_unload_platforms',AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_group_setup_failure_does_not_leave_a_published_runtime(hass, monkeypatch):
    parent=entry(hass,room=room(hass),enabled=False)
    hass.config_entries.async_update_entry(parent,data={**parent.data,PRODUCT_CONFIG:1})
    from custom_components.open_thermostat import installation_group
    def fail(*args):raise ValueError('injected_group_conflict')
    monkeypatch.setattr(installation_group,'ensure_installation_group',fail)
    with pytest.raises(ValueError,match='injected_group_conflict'):
        await integration.async_setup_entry(hass,parent)
    assert parent.entry_id not in hass.data.get(DOMAIN,{})


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',[MODE_LEGACY,MODE_SHADOW])
@pytest.mark.parametrize('phase',['tracker_wait','platform_forward'])
async def test_cancelled_setup_unsubscribes_started_tracker_and_removes_bench(hass,monkeypatch,mode,phase):
    parent=entry(hass,room=room(hass),enabled=False,mode=mode)
    hass.config_entries.async_update_entry(parent,data={**parent.data,PRODUCT_CONFIG:1})
    listeners=[]
    async def subscribe(hass,topic,callback,**kwargs):
        token=object();listeners.append(token)
        return lambda:listeners.remove(token)
    monkeypatch.setattr(mqtt,'async_wait_for_mqtt_client',AsyncMock(side_effect=asyncio.CancelledError() if phase=='tracker_wait' else None))
    monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    async def cancelled(*args):raise asyncio.CancelledError()
    monkeypatch.setattr(hass.config_entries,'async_forward_entry_setups',cancelled)
    try:
        with pytest.raises(asyncio.CancelledError):await integration.async_setup_entry(hass,parent)
        assert not listeners
        assert parent.entry_id not in hass.data.get(DOMAIN,{})
        from custom_components.open_thermostat.v1_bench_actions import KEY
        assert parent.entry_id not in hass.data.get(KEY,{})
    finally:
        # Old-source reproduction must not leak its deliberately failed setup.
        state=hass.data.get(DOMAIN,{}).pop(parent.entry_id,{})
        if tracker:=state.get('heating_tracker'):await tracker.async_stop()
        if runtime:=state.get('v1_runtime'):await runtime.async_stop()
        from custom_components.open_thermostat.v1_bench_actions import async_unregister_entry
        await async_unregister_entry(hass,parent.entry_id)


@pytest.mark.asyncio
async def test_connection_failure_before_attach_still_closes_connection(hass,monkeypatch):
    parent=entry(hass,room=room(hass),enabled=True);opened=[]
    async def failed(self):opened.append(self);raise RuntimeError('injected_start_failure')
    monkeypatch.setattr(NativeShadowConnection,'async_start',failed)
    with pytest.raises(RuntimeError,match='injected_start_failure'):
        await integration.async_setup_entry(hass,parent)
    assert len(opened)==1 and opened[0].closed
    assert not opened[0].runtime._active and not opened[0].runtime._subscriptions
    assert parent.entry_id not in hass.data.get(DOMAIN,{})


@pytest.mark.asyncio
async def test_failed_old_setup_cannot_remove_a_replacement_owner(hass,monkeypatch):
    parent=entry(hass,room=room(hass),enabled=False);replacement={'replacement_owner':True}
    async def fail(*args):
        hass.data[DOMAIN][parent.entry_id]=replacement
        raise RuntimeError('injected_owner_replacement')
    monkeypatch.setattr(hass.config_entries,'async_forward_entry_setups',fail)
    with pytest.raises(RuntimeError,match='injected_owner_replacement'):
        await integration.async_setup_entry(hass,parent)
    assert hass.data[DOMAIN].get(parent.entry_id) is replacement
    hass.data[DOMAIN].pop(parent.entry_id,None)


@pytest.mark.asyncio
async def test_cleanup_exception_still_removes_only_its_own_state(hass,monkeypatch):
    from custom_components.open_thermostat import installation_group
    from custom_components.open_thermostat.v1_runtime import ShadowRuntime
    parent=entry(hass,room=room(hass),enabled=False)
    hass.config_entries.async_update_entry(parent,data={**parent.data,PRODUCT_CONFIG:1})
    stopped=[];original=ShadowRuntime.async_stop
    async def stop(self):
        await original(self);stopped.append(self)
        raise RuntimeError('injected_cleanup_error')
    def fail(*args):raise ValueError('injected_setup_error')
    monkeypatch.setattr(ShadowRuntime,'async_stop',stop)
    monkeypatch.setattr(installation_group,'ensure_installation_group',fail)
    with pytest.raises(RuntimeError,match='injected_cleanup_error'):
        await integration.async_setup_entry(hass,parent)
    assert len(stopped)==1 and not stopped[0]._active
    assert parent.entry_id not in hass.data.get(DOMAIN,{})

@pytest.mark.asyncio
@pytest.mark.parametrize('version_label',['2026.10.4','2026.11.0'])
async def test_existing_product_starts_without_a_presentation_version_gate_and_unloads_cleanly(hass,monkeypatch,version_label):
    """Real current Core lifecycle; other labels test guard independence, not future-Core qualification."""
    from custom_components.open_thermostat import product,installation_group
    from homeassistant.helpers import device_registry as dr
    parent=entry(hass,room=room(hass),enabled=False)
    hass.config_entries.async_update_entry(parent,data={**parent.data,PRODUCT_CONFIG:1})
    before=dict(parent.data);listeners=[]
    async def subscribe(hass,topic,callback,**kwargs):
        token=object();listeners.append(token)
        return lambda:listeners.remove(token)
    monkeypatch.setattr(mqtt,'async_wait_for_mqtt_client',AsyncMock())
    monkeypatch.setattr(mqtt,'async_subscribe',subscribe)
    publish=AsyncMock();monkeypatch.setattr(mqtt,'async_publish',publish)
    forward=AsyncMock();monkeypatch.setattr(hass.config_entries,'async_forward_entry_setups',forward)
    monkeypatch.setattr(product,'HA_VERSION',version_label)
    monkeypatch.setattr(installation_group,'HA_VERSION',version_label,raising=False)
    try:
        assert await integration.async_setup_entry(hass,parent)
        state=hass.data[DOMAIN][parent.entry_id]
        assert 'heating_tracker' in state and not state['v1_runtime'].enabled
        assert 'v1_connection' not in state and listeners
        assert dr.async_get(hass).async_get_device_by_identifier((DOMAIN,parent.data['topic_prefix']),parent.entry_id)
        assert dict(parent.data)==before
        forward.assert_awaited_once();publish.assert_not_called()
    finally:
        if parent.entry_id in hass.data.get(DOMAIN,{}):
            assert await integration.async_unload_entry(hass,parent)
        await parent._async_process_on_unload(hass)
    assert not listeners and parent.entry_id not in hass.data.get(DOMAIN,{})
    publish.assert_not_called()
