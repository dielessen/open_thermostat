"""Pinned HA core schema contract; no project shim, no unsupported old-core claim."""
import ast,importlib,importlib.metadata as metadata
from pathlib import Path
import pytest

@pytest.mark.parametrize("module",["v1_config_flow","v1_heating_flow","v1_heating_graph_flow","native_form"])
def test_current_form_schema_provider_is_declared_native_HA_core_dependency(module):
    import homeassistant
    import probatio
    from homeassistant import data_entry_flow
    from packaging.requirements import Requirement
    dependency=next(Requirement(r) for r in metadata.requires("homeassistant") if Requirement(r).name=="probatio")
    assert metadata.version("homeassistant") in ("2026.10.2", "2026.10.3")
    assert metadata.version("probatio")=="0.13.0" and metadata.version("probatio") in dependency.specifier
    current=importlib.import_module("custom_components.open_thermostat."+module)
    assert current.vol.Schema is data_entry_flow.probatio.Schema is probatio.Schema
    assert current.vol.Marker is data_entry_flow.probatio.Marker
    source=Path(current.__file__).read_text()
    tree=ast.parse(source)
    # Production modules import the dependency normally. They do not change
    # Python's module table, install a compatibility mapping or inject a shim.
    assert any(isinstance(n,ast.Import) and any(a.name=="probatio" for a in n.names) for n in tree.body)
    assert "sys.modules" not in source and "install_as_voluptuous" not in source

def test_native_core_suggestion_uses_same_optional_marker_and_preserves_error_input():
    import probatio as vol
    from homeassistant.data_entry_flow import FlowHandler
    from custom_components.open_thermostat.native_form import retained_input_schema
    flow=FlowHandler();schema=vol.Schema({vol.Required("name"):str,vol.Optional("window"):str})
    changed=retained_input_schema(flow,schema,{"name":"Unstored room"})
    markers={m.schema:m for m in changed.schema}
    assert markers["name"].description["suggested_value"]=="Unstored room"
    assert markers["window"].description["suggested_value"] is None
    assert changed({"name":"Room"})=={"name":"Room"}
    with pytest.raises(vol.Invalid):changed({"name":42})
    assert all(not (m.description or {}).get("suggested_value") for m in schema.schema)
