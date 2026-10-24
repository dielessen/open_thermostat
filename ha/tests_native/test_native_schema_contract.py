"""Real selected HA production API provenance, not optional import availability."""
import base64,hashlib,importlib,importlib.metadata as md
from pathlib import Path
import pytest
import probatio
from homeassistant.helpers import config_validation
from homeassistant import data_entry_flow

def record_verified(distribution,relative):
    item=next(f for f in distribution.files if str(f)==relative)
    data=Path(distribution.locate_file(item)).read_bytes()
    assert item.hash and item.hash.mode=="sha256"
    assert base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")==item.hash.value
    return data.decode()

def test_chosen_schema_is_declared_and_used_by_actual_supported_native_HA_API():
    ha=md.distribution("homeassistant");provider=md.distribution("probatio")
    assert ha.version in ("2026.10.2", "2026.10.3") and provider.version=="0.13.0"
    assert "probatio==0.13.0" in ha.requires
    assert provider.metadata["License-Expression"]=="MIT"
    assert config_validation.probatio is probatio and data_entry_flow.probatio is probatio
    for relative in ("homeassistant/data_entry_flow.py","homeassistant/config_entries.py",
                     "homeassistant/helpers/selector.py"):
        text=record_verified(ha,relative)
        assert "import probatio" in text and "probatio.Schema" in text
    # Read exact actual upstream bootstrap, never install any project alias.
    bootstrap=record_verified(ha,"homeassistant/__init__.py")
    assert "from probatio.compat import install_as_voluptuous" in bootstrap
    assert "install_as_voluptuous()" in bootstrap
    package=record_verified(provider,"probatio/__init__.py")
    assert "Probatio" in package

@pytest.mark.parametrize("name",["v1_config_flow","v1_heating_flow","v1_heating_graph_flow"])
def test_each_real_flow_uses_native_schema_provider_without_own_module_alias(name):
    module=importlib.import_module("custom_components.open_thermostat."+name)
    assert module.vol is probatio and module.vol.Schema is data_entry_flow.probatio.Schema
    source=Path(module.__file__).read_text()
    assert "import probatio as vol" in source
    assert "sys.modules" not in source and "install_as_voluptuous" not in source
