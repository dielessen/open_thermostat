"""Actual HA registry move events must preserve controller/room identities."""
from copy import deepcopy
from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
from custom_components.open_thermostat.product import PRODUCT_CONFIG, INSTALLATION, configuration_snapshot
from custom_components.open_thermostat.product_flow import ProductRoomFlow
from custom_components.open_thermostat.installation_group import ensure_installation_group, GROUP_TYPE, GROUP_UNIQUE_ID, GROUP_TITLE
from test_v1_native import entry, room


def existing(hass):
    parent = entry(hass, room=room(hass))
    hass.config_entries.async_update_entry(parent, data={**parent.data, PRODUCT_CONFIG: 1, INSTALLATION: {"unchanged": "central owner"}})
    devices, entities = dr.async_get(hass), er.async_get(hass)
    hub = devices.async_get_or_create(config_entry_id=parent.entry_id, identifiers={(DOMAIN,"fixture")}, name="Controller")
    devices.async_update_device(hub.id, name_by_user="E32-regelaar — ketel en diagnose")
    zone = next(s for s in parent.subentries.values() if s.subentry_type=="zone")
    room_device=devices.async_get_or_create(config_entry_id=parent.entry_id, config_subentry_id=zone.subentry_id,
        identifiers={(DOMAIN,"fixture_room_"+zone.unique_id)}, name="Badkamer", via_device_id=hub.id)
    records=[entities.async_get_or_create(domain,DOMAIN,"fixture_hub_"+key,config_entry=parent,device_id=hub.id,suggested_object_id=key)
             for domain,key in [("sensor","flow"),("sensor","energy_v2"),("binary_sensor","connected")]]
    room_record=entities.async_get_or_create("climate",DOMAIN,"fixture_room_climate",config_entry=parent,
        config_subentry_id=zone.subentry_id,device_id=room_device.id)
    return parent,hub,room_device,records,room_record


@pytest.mark.asyncio
async def test_upgrade_groups_the_same_entities_before_queued_device_move_event(hass):
    parent,hub,room_device,records,room_record=existing(hass)
    data,options,zone_data=deepcopy(dict(parent.data)),dict(parent.options),deepcopy(dict(next(iter(parent.subentries.values())).data))
    group_id=ensure_installation_group(hass,parent)
    await hass.async_block_till_done() # Real Core listener removes incorrectly ordered moves.
    assert parent.subentries[group_id].title==GROUP_TITLE
    assert parent.subentries[group_id].subentry_type==GROUP_TYPE and dict(parent.subentries[group_id].data)=={}
    assert dict(parent.data)==data and dict(parent.options)==options
    assert dict(next(s for s in parent.subentries.values() if s.subentry_type=="zone").data)==zone_data
    for old in records:
        current=er.async_get(hass).async_get(old.entity_id)
        assert current is not None and current.id==old.id and current.unique_id==old.unique_id
        assert current.device_id==hub.id and current.config_subentry_id==group_id
    assert dr.async_get(hass).async_get(hub.id).config_subentry_id==group_id
    assert dr.async_get(hass).async_get(hub.id).name_by_user=="E32-regelaar — ketel en diagnose"
    assert dr.async_get(hass).async_get(room_device.id).config_subentry_id==room_record.config_subentry_id
    assert er.async_get(hass).async_get(room_record.entity_id)==room_record


@pytest.mark.asyncio
async def test_group_repeated_setup_keeps_identity_custom_title_and_only_room_add_choice(hass):
    parent,*_=existing(hass);gid=ensure_installation_group(hass,parent)
    hass.config_entries.async_update_subentry(parent,parent.subentries[gid],title="My boiler")
    before=configuration_snapshot(parent)
    assert ensure_installation_group(hass,parent)==gid
    await hass.async_block_till_done()
    assert configuration_snapshot(parent)==before
    assert OpenThermostatConfigFlow.async_get_supported_subentry_types(parent)=={"zone":ProductRoomFlow}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_data",[{}, {"draft":"not a second central owner"}])
async def test_conflicting_system_group_refuses_without_mutation(hass,bad_data):
    parent,*_=existing(hass)
    sub=ConfigSubentry(data=MappingProxyType(bad_data),subentry_type=GROUP_TYPE,title="Foreign",unique_id="foreign")
    hass.config_entries.async_add_subentry(parent,sub);before=configuration_snapshot(parent)
    with pytest.raises(ValueError,match="installation_group_conflict"):ensure_installation_group(hass,parent)
    assert configuration_snapshot(parent)==before


@pytest.mark.asyncio
async def test_device_move_failure_restores_entities_and_removes_only_new_empty_group(hass,monkeypatch):
    parent,hub,room_device,records,room_record=existing(hass);before=configuration_snapshot(parent)
    registry=dr.async_get(hass);original=type(registry).async_update_device
    def fail(self,device_id,**kwargs):
        if device_id==hub.id and "new_config_subentry_id" in kwargs:raise RuntimeError("injected move refusal")
        return original(self,device_id,**kwargs)
    monkeypatch.setattr(type(registry),"async_update_device",fail)
    with pytest.raises(RuntimeError,match="injected move refusal"):ensure_installation_group(hass,parent)
    await hass.async_block_till_done()
    assert configuration_snapshot(parent)==before
    assert registry.async_get(hub.id).config_subentry_id is None
    assert all(er.async_get(hass).async_get(e.entity_id).config_subentry_id is None for e in records)
    assert er.async_get(hass).async_get(room_record.entity_id)==room_record

@pytest.mark.asyncio
@pytest.mark.parametrize('core_version',['2026.10.4','2026.11.0'])
async def test_presentation_group_does_not_block_startup_on_a_different_core_version(hass,monkeypatch,core_version):
    """Public registry grouping must not inherit the private Store write pin."""
    from custom_components.open_thermostat import installation_group,product
    parent,hub,room_device,records,room_record=existing(hass)
    before_data=deepcopy(dict(parent.data));before_options=dict(parent.options)
    monkeypatch.setattr(product,'HA_VERSION',core_version)
    monkeypatch.setattr(installation_group,'HA_VERSION',core_version,raising=False)
    gid=ensure_installation_group(hass,parent)
    await hass.async_block_till_done()
    assert ensure_installation_group(hass,parent)==gid
    assert dict(parent.data)==before_data and dict(parent.options)==before_options
    assert all(er.async_get(hass).async_get(e.entity_id).id==e.id for e in records)
    assert dr.async_get(hass).async_get(hub.id).config_subentry_id==gid
    assert er.async_get(hass).async_get(room_record.entity_id)==room_record

@pytest.mark.asyncio
async def test_presentation_compatibility_does_not_enable_unreviewed_private_configuration_writes(hass,monkeypatch):
    from custom_components.open_thermostat import installation_group,product
    parent,*_=existing(hass);before=configuration_snapshot(parent)
    # Older than MINIMUM_HA_VERSION: the private one-step save is refused.
    monkeypatch.setattr(product,'HA_VERSION','2026.9.4')
    monkeypatch.setattr(installation_group,'HA_VERSION','2026.9.4',raising=False)
    with pytest.raises(ValueError,match='setup_platform_unsupported'):
        product.commit_configuration(hass,parent,before,title='must not be saved')
    assert configuration_snapshot(parent)==before
    # Newer than tested, but with Home Assistant's same save routine: accepted.
    monkeypatch.setattr(product,'HA_VERSION','2026.11.0')
    product.commit_configuration(hass,parent,before,title='saved on a newer core')
    assert parent.title=='saved on a newer core'
