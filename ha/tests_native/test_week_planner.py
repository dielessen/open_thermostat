"""Actual native config transactions, stale editor/registry fences and WS auth."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

import pytest
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat import week_planner as editor
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.product import configuration_snapshot, PRODUCT_CONFIG
from custom_components.open_thermostat.schedule_compiler import WEEKDAYS
from custom_components.open_thermostat.v1_config_flow import reference
from test_v1_native import entry, room


def setup(hass, binding=None):
    binding = binding or room(hass)
    parent = entry(hass, room=binding)
    hass.config_entries.async_update_entry(parent, data={**parent.data, PRODUCT_CONFIG: 1})
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {}
    return parent, binding, editor.read_program(hass, parent.entry_id, binding.room_id)


def week():
    return {day: ([{"start": 25200, "end": 28800, "target_centi_c": 2250}]
                  if day == "monday" else []) for day in WEEKDAYS}


@pytest.mark.asyncio
async def test_one_native_save_preserves_all_other_room_and_installation_bytes(hass):
    p, binding, model = setup(hass)
    before = configuration_snapshot(p)
    original = next(iter(p.subentries.values()))
    result = await editor.save_program(hass, p.entry_id, binding.room_id, model["token"], week())
    assert result["week"] == week() and result["token"] != model["token"]
    assert dict(p.data) == before[1] and dict(p.options) == before[2]
    sub = p.subentries[original.subentry_id]
    assert sub.unique_id == original.unique_id and sub.title == original.title
    assert dict(sub.data) == {**dict(original.data), "week_program": week()}
    assert model["week"]["monday"] == []  # No in-place mutation of caller state.
    assert not p.options["shadow_enabled"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["overlap", "range", "boolean", "too_many", "bad_time"])
async def test_invalid_weeks_never_partially_save(hass, change):
    p, b, model = setup(hass); before = configuration_snapshot(p); submitted = week()
    block = submitted["monday"][0]
    if change == "overlap": submitted["monday"].append(deepcopy(block))
    if change == "range": block["target_centi_c"] = 3600
    if change == "boolean": block["start"] = True
    if change == "too_many": submitted = {d: [{"start":i*3600,"end":i*3600+1800,"target_centi_c":2100} for i in range(5)] for d in WEEKDAYS}
    if change == "bad_time": block["end"] = 0
    with pytest.raises(ValueError): await editor.save_program(hass, p.entry_id, b.room_id, model["token"], submitted)
    assert configuration_snapshot(p) == before


@pytest.mark.asyncio
async def test_adjacent_blocks_midnight_and_per_room_limits_round_trip(hass):
    p,b,model=setup(hass, replace(room(hass), minimum_target_centi_c=1500, maximum_target_centi_c=2300))
    submitted=week();submitted['monday'].append({'start':28800,'end':86400,'target_centi_c':1500})
    assert (await editor.save_program(hass,p.entry_id,b.room_id,model['token'],submitted))['week']==submitted
    current=editor.read_program(hass,p.entry_id,b.room_id);submitted['monday'][0]['target_centi_c']=1400
    before=configuration_snapshot(p)
    with pytest.raises(ValueError,match='invalid_target_range'):await editor.save_program(hass,p.entry_id,b.room_id,current['token'],submitted)
    assert configuration_snapshot(p)==before


@pytest.mark.asyncio
async def test_stale_second_editor_cannot_overwrite_first_save(hass):
    p,b,model=setup(hass)
    await editor.save_program(hass,p.entry_id,b.room_id,model['token'],week());before=configuration_snapshot(p)
    with pytest.raises(ValueError,match='setup_changed'):await editor.save_program(hass,p.entry_id,b.room_id,model['token'],{d:[] for d in WEEKDAYS})
    assert configuration_snapshot(p)==before


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['options','unload','replacement','registry','runtime'])
async def test_final_executor_await_rechecks_owner_config_registry_and_runtime(hass,monkeypatch,change):
    p,b,model=setup(hass);original_data=configuration_snapshot(p)
    executor=hass.async_add_executor_job
    async def mutate(*args):
        result=await executor(*args)
        if change=='options':hass.config_entries.async_update_entry(p,options={**p.options,'other':True})
        if change=='unload':hass.data[DOMAIN].pop(p.entry_id)
        if change=='replacement':hass.config_entries._entries.pop(p.entry_id)
        if change=='registry':er.async_get(hass).async_remove(b.temperature.entity_id)
        if change=='runtime':hass.config_entries.async_update_entry(p,options={**p.options,'shadow_enabled':True})
        return result
    monkeypatch.setattr(hass,'async_add_executor_job',mutate)
    with pytest.raises(ValueError):await editor.save_program(hass,p.entry_id,b.room_id,model['token'],week())
    assert configuration_snapshot(p)[3]==original_data[3]


@pytest.mark.asyncio
async def test_helper_source_is_readable_but_cannot_be_overwritten(hass):
    reg=er.async_get(hass).async_get_or_create('schedule','schedule','existing_helper')
    p,b,model=setup(hass,replace(room(hass),schedule=reference(hass,reg.entity_id)))
    assert model['external_schedule'] and not model['editable'];before=configuration_snapshot(p)
    with pytest.raises(ValueError,match='program_source_conflict'):await editor.save_program(hass,p.entry_id,b.room_id,model['token'],week())
    assert configuration_snapshot(p)==before


@pytest.mark.asyncio
async def test_ws_read_and_write_require_authenticated_admin_before_target_access(hass):
    p,b,model=setup(hass);before=configuration_snapshot(p)
    for user in (None,SimpleNamespace(is_admin=False)):
        connection=SimpleNamespace(user=user,send_result=Mock(),send_error=Mock())
        for handler in (editor.ws_get,editor.ws_save):
            with pytest.raises(Unauthorized):handler(hass,connection,{'id':1,'entry_id':p.entry_id,'room_id':b.room_id,'token':model['token'],'week':week()})
        connection.send_result.assert_not_called();connection.send_error.assert_not_called()
    assert configuration_snapshot(p)==before


@pytest.mark.asyncio
async def test_wrong_product_or_room_is_not_exposed(hass):
    p,b,_=setup(hass)
    with pytest.raises(ValueError,match='room_changed'):editor.read_program(hass,p.entry_id,'not-a-room')
    hass.config_entries.async_update_entry(p,data={k:v for k,v in p.data.items() if k!=PRODUCT_CONFIG})
    with pytest.raises(ValueError,match='installation_unavailable'):editor.read_program(hass,p.entry_id,b.room_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',['adopted','refused','exception'])
async def test_native_reload_preserves_one_panel_and_cleans_failed_handover(hass,monkeypatch,outcome):
    import custom_components.open_thermostat as integration
    p,_,_=setup(hass)
    hass.config_entries.async_update_entry(p,options={**p.options,'create_dashboard':True})
    panel=SimpleNamespace(async_stop=AsyncMock())
    hass.data[DOMAIN][p.entry_id]['dashboard']=panel
    async def reload(entry_id):
        assert 'dashboard' not in hass.data[DOMAIN][entry_id]
        assert hass.data[integration._RELOAD_DASHBOARDS][entry_id] is panel
        if outcome=='adopted':
            taken=hass.data[integration._RELOAD_DASHBOARDS].pop(entry_id)
            hass.data[DOMAIN][entry_id]={'dashboard':taken}
        if outcome=='exception':raise RuntimeError('injected reload failure')
        return outcome=='adopted'
    monkeypatch.setattr(hass.config_entries,'async_reload',reload)
    if outcome=='exception':
        with pytest.raises(RuntimeError):await integration._async_options_updated(hass,p)
    else:await integration._async_options_updated(hass,p)
    assert p.entry_id not in hass.data[integration._RELOAD_DASHBOARDS]
    assert panel.async_stop.await_count==(0 if outcome=='adopted' else 1)
