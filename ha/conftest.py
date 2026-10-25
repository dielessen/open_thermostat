"""Whole-suite source evidence for release packaging; no production access."""
from pathlib import Path
import pytest
from homeassistant.const import __version__ as ACTUAL_HA_CORE
from scripts.ha_test_evidence import snapshot


@pytest.fixture(scope="session", autouse=True)
def release_source_evidence(record_testsuite_property):
    root=Path(__file__).resolve().parents[1]
    before=snapshot(root)
    yield
    after=snapshot(root)
    for name,value in before.items():
        record_testsuite_property('opth.'+name,str(value).lower() if isinstance(value,bool) else value)
    record_testsuite_property('opth.unchanged_source',str(before==after).lower())
    record_testsuite_property('opth.ha_core',ACTUAL_HA_CORE)
