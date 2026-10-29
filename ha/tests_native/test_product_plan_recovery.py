"""Product menu recovery traverses the real Core menu schema and C++ readback."""
from copy import deepcopy
import pytest
from homeassistant import loader
from test_native_control_plan import native_plan, native_two

@pytest.mark.asyncio
@pytest.mark.parametrize('native_plan', [{'product':True}], indirect=True)
@pytest.mark.parametrize('confirm', [False, True])
@pytest.mark.parametrize('interrupted', [False, True])
async def test_product_native_recovery_menu_separates_prepare_review_and_actual_readback(native_plan,hass,confirm,interrupted):
    n=native_plan
    if interrupted:
        await n.connection.async_graph_command('prepare')
        stage=deepcopy(n.client.journal['staged'])
        await n.stop();await n.start();await n.event('connect');await n.handshake()
        assert n.client.error=='native_plan_recovery_review_required'
        assert n.client.journal['staged']==stage and not n.pending
    loader.async_setup(hass)
    component=await loader.async_get_integration(hass,'open_thermostat')
    await component.async_get_platform('config_flow')
    manager=hass.config_entries.options
    entry_before=deepcopy((dict(n.parent.data),dict(n.parent.options),tuple(n.parent.subentries)))
    form=await manager.async_init(n.parent.entry_id)
    assert 'graph_prepare' not in form['menu_options']  # recovery lives under Advanced
    form=await manager.async_configure(form['flow_id'],form['data_schema']({'next_step_id':'advanced_settings'}))
    assert 'graph_prepare' in form['menu_options']
    # Real menu schema rejected this route before the product menu fix.
    review=await manager.async_configure(form['flow_id'],form['data_schema']({'next_step_id':'graph_prepare'}))
    assert review.get('step_id')=='graph_review', review
    assert not n.pending and (await n.peer.request('status'))['writes']==0
    result=await manager.async_configure(review['flow_id'],review['data_schema']({'confirm_apply':confirm}))
    if confirm:
        assert result['step_id']=='graph_status' and not n.client.ready
        await n.drain();await n.handshake()
        result=await manager.async_configure(result['flow_id'],result['data_schema']({'status_action':'refresh'}))
        assert result['description_placeholders']['verified']=='True'
        assert n.client.ready and (await n.peer.request('status'))['writes']==1
    else:
        assert result['reason']=='graph_review_cancelled'
        assert not n.pending and (await n.peer.request('status'))['writes']==0
    assert entry_before==(dict(n.parent.data),dict(n.parent.options),tuple(n.parent.subentries))
    diagnostics=await manager.async_init(n.parent.entry_id)
    diagnostics=await manager.async_configure(diagnostics['flow_id'],diagnostics['data_schema']({'next_step_id':'advanced_settings'}))
    assert 'graph_status' in diagnostics['menu_options']
    before=await n.peer.request('durable_readback')
    status=await manager.async_configure(diagnostics['flow_id'],diagnostics['data_schema']({'next_step_id':'graph_status'}))
    assert status['step_id']=='graph_status'
    after=await n.peer.request('durable_readback')
    assert before['stored']==after['stored'] and before['writes']==after['writes']

@pytest.mark.asyncio
async def test_inactive_product_has_no_plan_actions(hass,monkeypatch):
    from unittest.mock import AsyncMock
    from homeassistant import config_entries
    from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
    from test_product_flow import product
    p=product(hass)
    monkeypatch.setattr(config_entries,'_async_get_flow_handler',AsyncMock(return_value=OpenThermostatConfigFlow))
    manager=hass.config_entries.options
    form=await manager.async_init(p.entry_id)
    assert 'graph_prepare' not in form['menu_options']
    form=await manager.async_configure(form['flow_id'],form['data_schema']({'next_step_id':'advanced_settings'}))
    assert 'graph_status' not in form['menu_options'] and 'graph_prepare' not in form['menu_options']
