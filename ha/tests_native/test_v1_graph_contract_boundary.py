"""Proposal is not negotiated wire: use actual native backend and actual C++ core."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from homeassistant import loader
from homeassistant.helpers import translation

from custom_components.open_thermostat.v1_wire import canonical, digest
from test_v1_wire_interop import integrated

COMPONENT=Path(__file__).resolve().parents[1]/"config/custom_components/open_thermostat"
FIXTURE=Path(__file__).parent/"fixtures/graph-contract-proposal.json"

@pytest.mark.asyncio
async def test_actual_current_fw_rejects_graph_schema_without_replacing_old_config(integrated):
    runtime,client,bus,binding=integrated
    await bus.start()
    before=deepcopy(client.journal)
    proposed=json.loads(FIXTURE.read_text())["config"]
    proposed["revision"]=2
    # Deliberately bypass ONLY HA exporter to probe the real v1 FW parser.
    # No implementation of api2 exists; sending to v1 must NOT apply.
    p=client.envelope("config")
    p.update(expected_revision=1,config_digest=digest(proposed),config=proposed)
    emitted=await bus.event("receive",topic="ha/config",raw=canonical(p))
    assert not any(x["topic"]=="fw/config_result" and x["payload"]["status"]=="applied" for x in emitted)
    await bus.event("tick")
    await bus.pump()
    assert client.journal==before
    await client.message("ha/snapshot_request","snapshot",{})
    await bus.pump()
    snapshots=[json.loads(raw) for who,topic,raw in bus.transcript if who=="fw" and topic=="fw/config_snapshot"]
    assert snapshots[-1]["config"]==before["accepted"]["config"]
    assert snapshots[-1]["config_revision"]==1
    assert client.ready

@pytest.mark.asyncio
async def test_native_english_room_mode_help_and_choices_loaded_by_real_ha(hass,monkeypatch):
    loader.async_setup(hass)
    component=loader.Integration(hass,"custom_components.open_thermostat",COMPONENT,
        json.loads((COMPONENT/"manifest.json").read_text()),
        top_level_files={p.name for p in COMPONENT.iterdir()})
    monkeypatch.setattr(translation,"async_get_integrations",AsyncMock(return_value={"open_thermostat":component}))
    values=await translation.async_get_translations(hass,"en","config_subentries",{"open_thermostat"})
    for step in ("user","reconfigure"):
        prefix="component.open_thermostat.config_subentries.zone.step."+step+"."
        assert values[prefix+"data.binding_mode"]=="Room output configuration"
        assert "runtime and transport are blocked" in values[prefix+"data_description.binding_mode"]
    values=await translation.async_get_translations(hass,"en","selector",{"open_thermostat"})
    assert "Graph-only / floor room (unapplied draft)" in values.values()

def test_proposal_has_no_ha_routing_or_implicit_hardware_qualification():
    d=json.loads(FIXTURE.read_text());c=d["config"]
    assert d["status"]=="PROPOSAL_ONLY_REJECT_BY_CURRENT_V1"
    assert c["qualification"]=={"record_digest":None,"outputs_ready":False,"boiler_ready":False}
    assert c["rooms"][0]["report_profile_id"] is None
    assert c["rooms"][0]["report_evidence"] is None
    encoded=canonical(c)
    assert "entity_id" not in encoded and "switch.floor" not in encoded and '"name":' not in encoded
    assert c["mapping_digest"]==digest(d["mapping"])
    assert len(c["required_capabilities"])==len(set(c["required_capabilities"]))
