"""Consume exact actual-C++ serialized observation/context, no hand-built EMS."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from custom_components.open_thermostat.heating import HeatingTracker
from test_v1_native import entry

@pytest.mark.asyncio
async def test_actual_cpp_parser_producer_to_native_ha_expiry_and_reboot(hass):
    path=Path(os.environ.get("ROOM_METRICS_CPP_WIRE",Path(__file__).resolve().parents[2]/"out/room-observation-wire.json"))
    if not path.exists():
        pytest.skip("Compile finite native room observation peer first")
    rows=json.loads(Path(path).read_text())
    assert len(rows)==6
    clock=[0];tracker=HeatingTracker(hass,entry(hass),clock=lambda:clock[0])
    tracker._handle_status(SimpleNamespace(payload="on",retain=False))
    states=[]
    for row in rows:
        clock[0]=row["at"]
        for method,body in (("_handle_rooms",row["room"]),("_handle_ems",row["ems"])):
            getattr(tracker,method)(SimpleNamespace(topic="fixture",payload=json.dumps(body),retain=False))
        tracker.set_rated_power("a1b2c3d4",1000)
        states.append((tracker.estimate_available("a1b2c3d4"),tracker.is_heating("a1b2c3d4"),
                       tracker.estimated_power("a1b2c3d4"),tracker.rooms["a1b2c3d4"].heating_seconds))
    assert [s[0] for s in states]==[True,True,True,False,True,True]
    assert [s[1] for s in states]==[True,True,True,False,False,True]
    assert states[3][2] is None and states[4][2]==0
    assert [s[3] for s in states]==[0,10,29,30,30,30]
    assert rows[1]["ems"]["roomEstimateObservation"]["sequence"]==1
    assert rows[-1]["ems"]["roomEstimateObservation"]["boot_id"]=="b"*32
