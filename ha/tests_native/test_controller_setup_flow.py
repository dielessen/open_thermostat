"""Normal HA options-manager lifecycle and guarded existing entry ownership."""
import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType

from custom_components.open_thermostat import controller_setup_flow as setup
from custom_components.open_thermostat.controller_link import ControllerLinkError, ControllerProvisioningError
from custom_components.open_thermostat.native_provisioning import source_from_selection
from custom_components.open_thermostat.native_plan import native_entry_state
from custom_components.open_thermostat.product import configuration_snapshot
from test_product_flow import option
from test_controller_link import NativeReceiver
from test_room_editor import configured


@pytest.mark.asyncio
async def test_normal_connection_form_never_returns_or_suggests_saved_password(hass, configured):
    parent, _, _ = configured
    hass.config_entries.async_update_entry(parent, data={**parent.data,
        setup.CONTROLLER_ADDRESS: 'http://e32.local', setup.CONTROLLER_PASSWORD: 'private-fixture-only'})
    before = native_entry_state(parent)
    form = await option(hass.config_entries.options, parent, 'controller_connection')
    assert form['step_id'] == 'controller_connection'
    assert 'private-fixture-only' not in str(form)
    assert set(str(k) for k in form['data_schema'].schema) == {'address', 'password'}
    hass.config_entries.options.async_abort(form['flow_id'])
    assert native_entry_state(parent) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('address,password', [('http://different.local', ''),
    ('http://e32.local', False), ('http://e32.local', 'x' * 129)])
async def test_invalid_access_never_starts_a_connection(hass, configured, monkeypatch, address, password):
    parent, _, _ = configured
    hass.config_entries.async_update_entry(parent, data={**parent.data,
        setup.CONTROLLER_ADDRESS: 'http://e32.local', setup.CONTROLLER_PASSWORD: 'private-fixture-only'})
    connect = AsyncMock(); monkeypatch.setattr(setup, 'async_connect_installation', connect)
    manager = hass.config_entries.options
    form = await option(manager, parent, 'controller_connection')
    if type(password) is not str:
        from homeassistant.data_entry_flow import InvalidData
        with pytest.raises(InvalidData):
            await manager.async_configure(form['flow_id'], {'address': address, 'password': password})
    else:
        form = await manager.async_configure(form['flow_id'], {'address': address, 'password': password})
        assert form['errors'] == {'base': 'controller_password_required'}
    connect.assert_not_called()
    assert 'private-fixture-only' not in str(form)
    manager.async_abort(form['flow_id'])


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'partial', 'unexpected', 'cancel'])
async def test_native_progress_completion_errors_and_abort_cancel_only_own_task(
        hass, configured, monkeypatch, outcome):
    parent, _, _ = configured
    hass.config_entries.async_update_entry(parent, data={**parent.data,
        setup.CONTROLLER_ADDRESS: 'http://e32.local', setup.CONTROLLER_PASSWORD: 'private-fixture-only'})
    started, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def connect(h, entry, address, password):
        assert h is hass and entry is parent and address == 'http://e32.local'
        assert password == 'private-fixture-only'
        started.set()
        try: await release.wait()
        except asyncio.CancelledError:
            cancelled.set(); raise
        if outcome == 'partial':
            raise ControllerProvisioningError('controller_plan_unconfirmed', device_may_have_changed=True)
        if outcome == 'unexpected': raise RuntimeError('private remote response')
        return {'room_ids': ['a1b2c3d4']}
    monkeypatch.setattr(setup, 'async_connect_installation', connect)
    manager = hass.config_entries.options
    form = await option(manager, parent, 'controller_connection')
    progress = await manager.async_configure(form['flow_id'], {'address': 'http://e32.local'})
    assert progress['type'] is FlowResultType.SHOW_PROGRESS
    await started.wait()
    if outcome == 'cancel':
        manager.async_abort(form['flow_id'])
        await asyncio.wait_for(cancelled.wait(), 1)
        assert not manager.async_progress()
        return
    release.set()
    await hass.async_block_till_done()
    assert manager._progress[form['flow_id']].cur_step['type'] is FlowResultType.SHOW_PROGRESS_DONE
    result = await manager.async_configure(form['flow_id'])
    if outcome == 'success':
        assert result['step_id'] == 'controller_connected'
        assert result['description_placeholders'] == {'rooms': '1'}
        result = await manager.async_configure(form['flow_id'], {})
        assert result['reason'] == 'controller_connection_complete'
    else:
        assert result['step_id'] == 'controller_connection'
        assert result['errors']['base'] == ('controller_partial_connection' if outcome == 'partial'
                                          else 'controller_connection_failed')
        assert 'private remote response' not in str(result)
        manager.async_abort(form['flow_id'])


class ScopedReceiver(NativeReceiver):
    logout_confirmed = False
    async def __aenter__(self): return self
    async def __aexit__(self, *args): self.logout_confirmed = True


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'ack_only', 'cancel', 'private_change', 'bad_login'])
async def test_scoped_operation_uses_actual_candidate_store_and_preserves_partial_intent(
        hass, configured, monkeypatch, outcome):
    parent, _, _ = configured
    peer = ScopedReceiver(); before = deepcopy(dict(parent.data))
    monkeypatch.setattr(setup, 'ControllerClient', lambda address: peer)
    # Bootstrapped test entry has no actual integration reload listener.
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, 'async_reload', reload)
    async def synchronise(h, entry, source, expected, *, private_expected):
        assert h is hass and entry is parent and expected == configuration_snapshot(parent)
        assert private_expected == native_entry_state(parent)
        assert peer.logout_confirmed and peer.saved and peer.rebooted
        assert source_from_selection(parent) == source
        assert parent.options['shadow_enabled'] is True
        assert parent.data[setup.CONTROLLER_PASSWORD] == 'http-fixture-only'
        assert 'http-fixture-only' not in str(expected)
        if outcome == 'ack_only': raise ControllerLinkError('controller_plan_unconfirmed')
        if outcome == 'cancel': raise asyncio.CancelledError
        if outcome == 'private_change':
            hass.config_entries.async_update_entry(parent,
                data={**parent.data, setup.CONTROLLER_PASSWORD: 'concurrent-fixture-only'})
        return {'room_ids': ['a1b2c3d4'], 'room_plan_applied': True, 'authorizes_physical_outputs': False}
    monkeypatch.setattr(setup, 'async_synchronise_controller_plan', synchronise)
    if outcome == 'bad_login':
        peer.async_login = AsyncMock(side_effect=ControllerLinkError('controller_auth_failed'))
    if outcome == 'success':
        result = await setup.async_connect_installation(hass, parent, 'http://e32.local', 'http-fixture-only')
        assert result['room_plan_applied'] and result['admin_logout_confirmed']
        assert result['authorizes_physical_outputs'] is False
    else:
        error = asyncio.CancelledError if outcome == 'cancel' else ControllerProvisioningError
        with pytest.raises(error) as captured:
            await setup.async_connect_installation(hass, parent, 'http://e32.local', 'http-fixture-only')
        if outcome != 'cancel': assert captured.value.device_may_have_changed == (outcome != 'bad_login')
    if outcome == 'bad_login':
        assert dict(parent.data) == before and not peer.saved
        reload.assert_not_called()
    else:
        assert all(parent.data[k] == v for k,v in before.items())
        assert parent.options['shadow_enabled'] == (outcome in ('success', 'private_change'))
        assert source_from_selection(parent) is not None
        reload.assert_awaited_once()
    assert peer.logout_confirmed


@pytest.mark.asyncio
async def test_diagnostics_never_exports_controller_credentials_or_session_state(hass, configured):
    from custom_components.open_thermostat.diagnostics import async_get_config_entry_diagnostics
    parent, _, _ = configured
    hass.config_entries.async_update_entry(parent, data={**parent.data,
        setup.CONTROLLER_ADDRESS: 'http://e32.local', setup.CONTROLLER_PASSWORD: 'never-export-fixture'})
    result = json.dumps(await async_get_config_entry_diagnostics(hass, parent))
    assert 'never-export-fixture' not in result and 'controller_password' not in result
    assert 'http://e32.local' not in result
