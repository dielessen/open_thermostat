"""Exact public receive-only companion payload, no deployment or private pins."""
from pathlib import Path
import hashlib
import json
import subprocess
from prepare_original_report_pins import inspect_template

SOURCES={
    'extensions/original-temperature.cjs':'integrations/zigbee2mqtt/original-temperature.cjs',
    'extensions/original-tv02.cjs':'integrations/zigbee2mqtt/original-tv02.cjs',
    'tools/prepare_original_report_pins.py':'scripts/prepare_original_report_pins.py',
    'README.nl-en.md':'docs/modern-thermostat/Z2M-RELEASE-COMPANION.nl-en.md',
    'LICENSE':'LICENSE',
}


def payload(root,head):
    root=Path(root).resolve()
    tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0'))
    files={};hashes={}
    for member,source in SOURCES.items():
        path=root/source
        if source not in tracked or path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('invalid_companion_source:'+source)
        with path.open('rb') as handle:raw=handle.read(65537)
        if len(raw)>65536:raise ValueError('companion_source_too_large:'+source)
        if source.endswith('.cjs'):
            profile='original_tv02' if 'tv02' in source else 'original_temperature'
            pins,_,_=inspect_template(raw,profile)
            if pins:raise ValueError('private_companion_bindings_not_publishable')
        files[member]=raw;hashes[source]=hashlib.sha256(raw).hexdigest()
    source=dict(schema=1,kind='optional_zigbee2mqtt_receive_only',source_commit=head,
        source_files=hashes,archive_sources=SOURCES,private_bindings_included=False,
        live_HA_data_included=False,installed=False,authorizes_control=False)
    files['SOURCE.json']=(json.dumps(source,indent=2)+'\n').encode()
    files['SHA256SUMS.txt']=''.join(hashlib.sha256(raw).hexdigest()+'  '+name+'\n'
        for name,raw in sorted(files.items())).encode()
    return files,source
