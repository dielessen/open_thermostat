"""Actual native EntityPlatform + RestoreSensor + registry unit preferences."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import logging
import math
import json
import os
from pathlib import Path
from copy import copy
import pytest
from homeassistant import loader
from homeassistant.components.sensor import RestoreSensor, SensorExtraStoredData
from homeassistant.core import State
from homeassistant.helpers import entity_registry as er, restore_state
from homeassistant.helpers.entity_platform import EntityPlatform
from custom_components.open_thermostat import sensor
from custom_components.open_thermostat.heating import HeatingTracker
from test_room_model_v2 import Model,KEY

async def platform(hass,entry):
    loader.async_setup(hass)
    await restore_state.async_load(hass,load_empty=True)
    p=EntityPlatform(hass=hass,logger=logging.getLogger(__name__),domain="sensor",
        platform_name="open_thermostat",platform=None,scan_interval=timedelta(seconds=30),entity_namespace=None)
    p.config_entry=entry;p.async_prepare()
    return p

def stored(hass,entity_id,value,unit,extra_value=None,extra_unit=None,has_extra=True):
    # Only persisted cache boundary is supplied; getters/lifecycle/conversion are
    # actual HA implementations. Extra data is native, not displayed State.
    data=SensorExtraStoredData(extra_value,extra_unit) if has_extra else None
    restore_state.async_get(hass).last_states[entity_id]=restore_state.StoredState(
        State(entity_id,str(value),{"unit_of_measurement":unit}),data,datetime.now(timezone.utc))

def entity(m,kind,legacy=False):
    cls=sensor.RoomEstimatedEnergy if kind=="energy" else sensor.RoomHeatingTime
    return cls("fixture",0,KEY,"Room",None,m.tracker,legacy=legacy)

def total(m,kind):
    room=m.tracker.rooms[KEY]
    return room.estimated_energy_kwh if kind=="energy" else room.heating_seconds

async def registered(hass,m,p,kind,display_unit,display_value,native_value,native_unit,*,has_extra=True,legacy=False):
    e=entity(m,kind,legacy)
    registry=er.async_get(hass)
    ref=registry.async_get_or_create("sensor","open_thermostat",e.unique_id,config_entry=m.tracker.entry)
    registry.async_update_entity_options(ref.entity_id,"sensor",{"unit_of_measurement":display_unit})
    stored(hass,ref.entity_id,display_value,display_unit,native_value,native_unit,has_extra)
    await p.async_add_entities([e])
    await hass.async_block_till_done()
    assert e.entity_id==ref.entity_id and ref.entity_id in p.entities
    assert isinstance(e,RestoreSensor)
    return e

@pytest.mark.asyncio
@pytest.mark.parametrize("kind,display_unit,display_value,native_value,native_unit,expected",[
    ("energy","Wh",1000,1,"kWh",1),
    ("energy","kWh",1,1000,"Wh",1),
    ("energy","Wh",1234.5,Decimal("1.2345"),"kWh",1.2345),
    ("duration","s",600,600,"s",600),
    ("duration","min",10,10,"min",600),
    ("duration","h",1/6,1/6,"h",600),
    ("duration","s",600,1/6,"h",600),
])
async def test_real_native_lifecycle_restores_native_data_and_honors_display_unit(hass,kind,display_unit,display_value,native_value,native_unit,expected):
    m=Model(hass);m.ready();p=await platform(hass,m.tracker.entry)
    try:
        e=await registered(hass,m,p,kind,display_unit,display_value,native_value,native_unit)
        assert total(m,kind)==pytest.approx(expected)
        state=hass.states.get(e.entity_id)
        assert state.attributes["unit_of_measurement"]==display_unit
        assert float(state.state)==pytest.approx(float(display_value))
        assert e.extra_restore_state_data.native_unit_of_measurement==("kWh" if kind=="energy" else "h")
        if evidence := os.environ.get("ROOM_RESTORE_EVIDENCE"):
            with Path(evidence).open("a") as f:
                f.write(json.dumps(dict(kind=kind,previous_display_value=display_value,previous_display_unit=display_unit,
                    persisted_native_value=str(native_value),persisted_native_unit=native_unit,
                    actual_canonical_total=total(m,kind),expected_canonical_total=expected,
                    actual_HA_display_state=state.state,actual_HA_display_unit=state.attributes["unit_of_measurement"],
                    actual_native_sensor_value=e.native_value,actual_native_sensor_unit=e.native_unit_of_measurement,
                    lifecycle="actual EntityPlatform / RestoreSensor / native registry options, no mocked getters"))+"\n")
    finally:await p.async_destroy()

@pytest.mark.asyncio
@pytest.mark.parametrize("kind,display_unit",[
    ("energy","Wh"),("energy","kWh"),("duration","s"),("duration","min"),("duration","h")])
async def test_native_remove_readd_roundtrip_never_restores_converted_or_rounded_state(hass,kind,display_unit):
    m=Model(hass);m.ready();entry=m.tracker.entry;p=await platform(hass,entry)
    expected=1.2345678901234 if kind=="energy" else 600.123456789
    native=expected if kind=="energy" else expected/3600
    native_unit="kWh" if kind=="energy" else "h"
    try:
        e=await registered(hass,m,p,kind,display_unit,"999999",native,native_unit)
        assert total(m,kind)==pytest.approx(expected,rel=1e-12)
        original_id=e.entity_id
        # Actual internal RestoreSensor removal writes native extra data; no
        # supplied second persisted snapshot or mocked restore getter.
        await p.async_remove_entity(original_id)
        previous=restore_state.async_get(hass).last_states[original_id]
        assert previous.extra_data.as_dict()["native_unit_of_measurement"]==native_unit
        assert previous.extra_data.as_dict()["native_value"]==pytest.approx(native,rel=1e-12)
        again=copy(m);again.tracker=HeatingTracker(hass,entry,clock=lambda:again.time);again.status("on");again.ready()
        fresh=entity(again,kind)
        await p.async_add_entities([fresh]);await hass.async_block_till_done()
        assert fresh.entity_id==original_id
        assert total(again,kind)==pytest.approx(expected,rel=1e-12)
        assert hass.states.get(original_id).attributes["unit_of_measurement"]==display_unit
    finally:await p.async_destroy()

@pytest.mark.asyncio
@pytest.mark.parametrize("kind,unit",[("energy","Wh"),("duration","s")])
async def test_display_only_parent_failure_probe_is_failclosed_not_guessed(hass,kind,unit):
    m=Model(hass);m.ready();p=await platform(hass,m.tracker.entry)
    try:
        await registered(hass,m,p,kind,unit,1000,None,None,has_extra=False)
        assert total(m,kind)==0
    finally:await p.async_destroy()

@pytest.mark.asyncio
@pytest.mark.parametrize("kind,value,unit",[
    ("energy",1,None),("energy",1,"W"),("energy",1,""),("energy",float("nan"),"kWh"),
    ("energy",float("inf"),"kWh"),("energy",-1,"kWh"),("energy",True,"kWh"),("energy","1","kWh"),
    ("energy",1e10,"kWh"),("energy",Decimal("1e9999"),"kWh"),("energy",1,{}),
    ("duration",1,None),("duration",1,"kWh"),("duration",float("nan"),"s"),
    ("duration",float("inf"),"h"),("duration",-1,"s"),("duration",True,"s"),
    ("duration",1e13,"s"),("duration",1,[]),
])
async def test_invalid_explicit_native_units_or_totals_failclosed_despite_plausible_display(hass,kind,value,unit):
    m=Model(hass);m.ready();p=await platform(hass,m.tracker.entry)
    try:
        await registered(hass,m,p,kind,"kWh" if kind=="energy" else "h",10,value,unit)
        assert total(m,kind)==0
    finally:await p.async_destroy()

@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["energy","duration"])
async def test_legacy_real_lifecycle_never_backfills_even_with_good_native_data(hass,kind):
    m=Model(hass);m.ready();p=await platform(hass,m.tracker.entry)
    try:
        e=await registered(hass,m,p,kind,"kWh" if kind=="energy" else "h",10,10,
            "kWh" if kind=="energy" else "h",legacy=True)
        assert total(m,kind)==0 and e.native_value is None and not e.available and e.state_class is None
        assert hass.states.get(e.entity_id).state=="unavailable"
    finally:await p.async_destroy()
