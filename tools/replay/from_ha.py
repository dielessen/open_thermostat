#!/usr/bin/env python3
"""Convert Home Assistant history exports into the replay CSV (tools/replay/README.md).

Input: one or more JSON files saved from GET /api/history/period/<start> (a list with one
list of states per entity; with minimal_response only the first state of each list names
its entity). Nothing is fetched here: the README shows the read-only curl command.

Columns come from the E32's own entities, found by their suffix when exactly one entity in
the export ends with it, or from --map COLUMN=ENTITY[@ATTRIBUTE]; rooms from
--room ID=climate.x (its current_temperature and temperature attributes) or --map
ID.temp_c=... / ID.target_c=.... HA records a state only when it changes, so every column
holds its last value until the next record (--max-hold bounds it); "unavailable" and
"unknown" are gaps. e32_heat is e32_flow_c > 0 unless mapped.

    python3 -I tools/replay/from_ha.py history-*.json --room room1=climate.living_room \\
        [--map outdoor_c=weather.home@temperature] [--mode shadow] [--since 2026-10-30T17:10Z]
        [--until ...] [--step 10] [--max-hold S] --out house.csv
"""
import argparse
import bisect
import csv
import datetime as dt
import json
import sys

# column -> suffix of the E32 integration's entity (as tools/switchover/replay_export.py)
SUFFIXES = {
    'flow_c': '_boiler_measured_flow_temperature',
    'return_c': '_boiler_measured_return_temperature',
    'modulation_pct': '_boiler_reported_burner_modulation',
    'heating_active': '_boiler_heating_active',
    'dhw_active': '_boiler_dhw_active',
    'thermostat_flow_c': '_thermostat_requested_flow_temperature',
    'e32_flow_c': '_heat_request',
    'outdoor_c': '_boiler_outdoor_temperature',
}
FLAGS = {'burner', 'heating_active', 'dhw_active', 'e32_heat'}
TEXT = {'e32_reason', 'mode'}
FIXED = ['flow_c', 'return_c', 'burner', 'heating_active', 'dhw_active', 'modulation_pct', 'e32_heat', 'e32_flow_c',
         'e32_reason', 'thermostat_flow_c', 'outdoor_c', 'mode']


def parse_time(text):
    t = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    return (t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)).timestamp()


def convert(column, value):
    if value is None or value in ('unavailable', 'unknown', ''):
        return None
    if column in TEXT:
        return str(value)
    if column in FLAGS:
        if value in ('on', 'true', 'True', True):
            return 1
        if value in ('off', 'false', 'False', False):
            return 0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return int(v > 0) if column in FLAGS else v


def load(paths):
    """{entity_id: [(utc, state, attributes)]} over every file, sorted, duplicates dropped."""
    out = {}
    for path in paths:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        for states in data:
            entity, attrs = None, {}
            for s in states:
                entity = s.get('entity_id') or entity
                if 'attributes' in s:
                    attrs = s.get('attributes') or {}
                when = s.get('last_updated') or s.get('last_changed')
                if entity and when:
                    out.setdefault(entity, []).append((parse_time(when), s.get('state'), attrs))
    for entity, rows in out.items():
        rows.sort(key=lambda r: r[0])
        unique = []
        for r in rows:
            if unique and unique[-1][0] == r[0]:
                unique[-1] = r
            else:
                unique.append(r)
        out[entity] = unique
    return out


def mapping(history, maps, rooms):
    """{column: (entity, attribute or None)}: suffixes first, then --room, then --map."""
    m = {}
    for col, suffix in SUFFIXES.items():
        ids = sorted(e for e in history if e.startswith(('sensor.', 'binary_sensor.')) and e.endswith(suffix))
        if len(ids) == 1:
            m[col] = (ids[0], None)
    for spec in rooms:
        room, entity = spec.split('=', 1)
        m[f'{room}.temp_c'] = (entity, 'current_temperature')
        m[f'{room}.target_c'] = (entity, 'temperature')
    for spec in maps:
        col, target = spec.split('=', 1)
        entity, _, attr = target.partition('@')
        m[col] = (entity, attr or None)
    return m


def series_of(history, m):
    series = {}
    for col, (entity, attr) in m.items():
        if entity not in history:
            raise SystemExit(f'{entity} (for {col}) is not in the export')
        series[col] = [(t, convert(col, attrs.get(attr) if attr else state)) for t, state, attrs in history[entity]]
    return series


def resample(series, start, end, step=10, max_hold=None, mode=None):
    rooms = sorted({c.rsplit('.', 1)[0] for c in series if c.endswith(('.temp_c', '.target_c'))})
    cols = ['utc'] + [f'{r}.{k}' for r in rooms for k in ('temp_c', 'target_c')] + FIXED
    index = {c: ([t for t, _ in v], [x for _, x in v]) for c, v in series.items()}
    rows = []
    t = int(start)
    while t <= end:
        row = {'utc': t}
        for c in cols[1:]:
            times, values = index.get(c, ([], []))
            i = bisect.bisect_right(times, t) - 1
            row[c] = values[i] if i >= 0 and (max_hold is None or t - times[i] <= max_hold) else None
        if 'e32_heat' not in series and row.get('e32_flow_c') is not None:
            row['e32_heat'] = int(row['e32_flow_c'] > 0)
        if mode and row.get('mode') is None:
            row['mode'] = mode
        rows.append(['' if row.get(c) is None else row[c] for c in cols])
        t += step
    return cols, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('history', nargs='+', help='JSON files from /api/history/period')
    ap.add_argument('--out', required=True)
    ap.add_argument('--room', action='append', default=[], metavar='ID=climate.x')
    ap.add_argument('--map', action='append', default=[], metavar='COLUMN=ENTITY[@ATTRIBUTE]')
    ap.add_argument('--mode', choices=('shadow', 'active'), help='the mode column where no entity gives it')
    ap.add_argument('--since')
    ap.add_argument('--until')
    ap.add_argument('--step', type=int, default=10)
    ap.add_argument('--max-hold', type=float, help='seconds a value holds without a new record (default: until the next)')
    a = ap.parse_args(argv)
    history = load(a.history)
    m = mapping(history, a.map, a.room)
    if not m:
        raise SystemExit('no column found: pass --room/--map')
    series = series_of(history, m)
    times = [t for v in series.values() for t, _ in v]
    start = parse_time(a.since) if a.since else min(times) // a.step * a.step
    end = parse_time(a.until) if a.until else max(times)
    cols, rows = resample(series, start, end, a.step, a.max_hold, a.mode)
    with open(a.out, 'w', newline='\n', encoding='utf-8') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(cols)
        w.writerows(rows)
    print(f'{len(rows)} rows -> {a.out}')
    for col, (entity, attr) in sorted(m.items()):
        print(f'  {col:20} {entity}' + (f'@{attr}' if attr else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
