"""Generate the Home Assistant catalog fields from the one C++ entity table.

src/EMS/EmsEntityTable.h is the single source: the boiler fields route
(boiler.fields.v2) carries one field per entity id from index 70, in table
order. This writes the matching tuple into boiler_fields.py; --check fails
when the two differ.
"""
from pathlib import Path
import argparse
import re

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / 'src/EMS/EmsEntityTable.h'
TARGET = ROOT / 'ha/config/custom_components/open_thermostat/boiler_fields.py'
START = '# BEGIN GENERATED CATALOG FIELDS (scripts/generate_ems_fields.py)\n'
END = '# END GENERATED CATALOG FIELDS\n'
ROW = re.compile(r'\{(0x[0-9A-Fa-f]+),(\d+),EntityKind::(\w+),(\d+),(\d+),(-?\d+),(-?\d+),EntitySource::(\w+),"(\w+)","([^"]+)",(\w+)(,verified)?\}')


def rows():
    text = TABLE.read_text(encoding='utf-8')
    ttl = {name: int(value) for name, value in re.findall(r'(\w+Ttl)=(\d+)', text)}
    found = [m.groups() for m in ROW.finditer(text)]
    size = re.search(r'std::array<EntitySpec,(\d+)> entityCatalog', text)
    assert found and size and len(found) == int(size.group(1)), 'catalog rows the generator cannot parse'
    return [{'type': int(t, 16), 'kind': k, 'divisor': int(d), 'minimum': int(lo), 'maximum': int(hi),
             'id': i, 'unit': u, 'ttl': ttl[x], 'verified': bool(v)} for t, _o, k, _b, d, lo, hi, _s, i, u, x, v in found]


def fields():
    out = {}
    for row in rows():
        field = out.setdefault(row['id'], {**row, 'types': []})
        assert (field['divisor'], field['unit'], field['kind']) == (row['divisor'], row['unit'], row['kind']), row['id']
        if row['type'] not in field['types']:
            field['types'].append(row['type'])
    return list(out.values())


def block():
    lines = [START, '# name, unit, raw divisor, source TTL ms, telegram types, raw minimum, raw maximum\n',
             'CATALOG_FIELDS = (\n']
    for f in fields():
        types = '(' + ', '.join(str(t) for t in f['types']) + (',)' if len(f['types']) == 1 else ')')
        lines.append(f"    ({f['id']!r}, {f['unit']!r}, {f['divisor']}, {f['ttl']}, {types}, {f['minimum']}, {f['maximum']}),\n")
    counters = ', '.join(repr(f['id']) for f in fields() if f['kind'] == 'u24')
    verified = ', '.join(f"({r['id']!r}, {r['type']})" for r in rows() if r['verified'])
    lines += [')\n', '# EMS 3-byte lifetime counters (EntityKind::u24): Home Assistant total_increasing\n',
              f'CATALOG_COUNTERS = frozenset({{{counters}}})\n',
              '# (name, telegram type) rows decoded from real frames with plausible values\n',
              f'CATALOG_VERIFIED = frozenset({{{verified}}})\n', END]
    return ''.join(lines)


def generate(check=False):
    text = TARGET.read_text(encoding='utf-8')
    start, end = text.index(START), text.index(END) + len(END)
    updated = text[:start] + block() + text[end:]
    if check:
        assert updated == text, 'boiler_fields.py catalog fields differ from EmsEntityTable.h; run scripts/generate_ems_fields.py'
    elif updated != text:
        TARGET.write_bytes(updated.encode('utf-8'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    generate(parser.parse_args().check)
