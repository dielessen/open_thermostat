"""Reproduce writable boiler metadata; no device support or TX permission implied."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'public/ems/entities.csv'
TARGET = ROOT / 'docs/modern-thermostat/BOILER-WRITE-INVENTORY.json'


def inventory():
    raw = SOURCE.read_bytes()
    pinned = json.loads((SOURCE.parent / 'SOURCES.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == pinned['sources']['entities.csv']['sha256']
    rows = [r for r in csv.DictReader(io.StringIO(raw.decode()))
            if r['device type'] == 'boiler' and r['writeable'] == 'true']
    fields = {}
    for row in rows:
        name = row['shortname']
        field = fields.setdefault(name, {
            'name': name, 'device_support': 'unverified',
            'general_write_implementation': 'not_implemented', 'variants': []})
        if name in {'heatingactivated', 'heatingtemp', 'burnminperiod', 'pumpdelay'}:
            field['general_write_implementation'] = 'classic_editor_connected_writes_disabled'
            field['encoder_source'] = 'src/EMS/ClassicBoilerSettingsEncoder.h'
            field['transaction_source'] = 'src/EMS/ClassicBoilerSettingTransaction.h'
            field['service_source'] = 'src/EMS/ClassicBoilerSettingsService.h'
            field['uart_boundary_source'] = 'src/EMS/ClassicSettingUartWrite.h'
            field['editor_source'] = 'data/html/ems-devices.js'
        field['variants'].append({
            'product_id': int(row['product id']), 'device_name': row['device name'],
            'description': row['fullname'],
            'type_options_bounds': next(value for key, value in row.items()
                                        if key.startswith('type [options...]')),
            'unit': row['uom'].strip()})
    return {
        'schema': 1, 'source': 'public/ems/entities.csv',
        'source_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'all pinned boiler groups; not a Classic capability list',
        'writable_rows': len(rows), 'unique_names': len(fields),
        'product_groups': len({r['product id'] for r in rows}),
        'existing_exception': {
            'entity': 'selflowtemp', 'telegram': '0x1A',
            'implementation': 'bounded_manual_trial_only',
            'source': 'src/EMS/ClassicBoilerTestEncoder.h',
            'general_setting_control': False},
        'fields': [fields[name] for name in sorted(fields)]}


if __name__ == '__main__':
    content = json.dumps(inventory(), ensure_ascii=False, indent=2) + '\n'
    if '--check' in sys.argv:
        assert TARGET.read_text() == content, 'Regenerate boiler write inventory'
    else:
        TARGET.write_text(content)
    print('PASS boiler write inventory: 1907 rows, 117 names, 31 product groups')
