"""User-facing compatibility errors stay accurate when the reviewed patch set grows."""
import json
from pathlib import Path
import pytest

@pytest.mark.parametrize('filename',['strings.json','translations/en.json','translations/nl.json'])
def test_configuration_version_error_has_translated_recovery_without_a_stale_patch_list(filename):
    root=Path(__file__).resolve().parents[1]/'config/custom_components/open_thermostat'
    document=json.loads((root/filename).read_text());messages=[]
    def walk(value):
        if isinstance(value,dict):
            for key,child in value.items():
                if key=='setup_platform_unsupported':messages.append(child)
                else:walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(document)
    assert messages and len(set(messages))==1
    assert all('Home Assistant' in text and '2026.' not in text for text in messages)
    assert all('update' in text.lower() for text in messages)
    assert all('private' not in text.lower() and 'Store' not in text for text in messages)
    if filename.endswith('/nl.json'):
        assert all('Er is niets aangepast.' in text for text in messages)
    else:
        assert all('Nothing has been changed.' in text for text in messages)
