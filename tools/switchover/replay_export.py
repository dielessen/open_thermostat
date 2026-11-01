#!/usr/bin/env python3
"""Export Home Assistant history as a replay input for the E32's learning code.

Read-only (GET only). It reads the history of the E32's boiler fields, the room
temperature and target, the old thermostat's requested flow and the outdoor
temperature, and writes one CSV row every --step seconds (sample and hold):

    t_s, room_c, setpoint_c, flow_c, return_c, modulation_pct, burner, dhw,
    thermostat_flow_c, e32_flow_c, outdoor_c

test/learning_replay/replay.cpp reads this file and runs the firmware's
FlowLearner, RoomEngine and FlowDemand on it (docs/modern-thermostat/LEREN-ANALYSE.nl.md).

    export OT_HA_TOKEN='<long-lived token>'
    python3 -I tools/switchover/replay_export.py --ha-url https://homeassistant.local:8123 \\
        --room-climate climate.living_room --since 2026-10-30T17:10Z --out replay.csv \\
        [--outdoor weather.home] [--until ...] [--step 10] [--insecure]

The E32 entities are found by their suffix (as shadow_exit.py) unless given:
--room-temperature (_<room>_temperature), --room-setpoint (_<room>_setpoint) or,
without them, the climate's current_temperature and temperature attributes.
"""
import argparse
import bisect
import csv
import datetime as dt
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shadow_exit import HomeAssistant, find, number, parse_since, parse_time  # noqa: E402

COLUMNS = ('t_s', 'room_c', 'setpoint_c', 'flow_c', 'return_c', 'modulation_pct', 'burner', 'dhw',
           'thermostat_flow_c', 'e32_flow_c', 'outdoor_c')
SUFFIXES = {
    'flow_c': '_boiler_measured_flow_temperature',
    'return_c': '_boiler_measured_return_temperature',
    'modulation_pct': '_boiler_reported_burner_modulation',
    'dhw': '_boiler_dhw_active',
    'thermostat_flow_c': '_thermostat_requested_flow_temperature',
    'e32_flow_c': '_heat_request',
}
# Home Assistant records a state only when it changes, so a value holds until the next record;
# 'unavailable'/'unknown' records are the gaps. --max-hold can still bound it (seconds).
MAX_HOLD_S = None


def flag(state):
    """on/off sensors (or 1.0/0.0) as 1/0; None when unknown."""
    if state in ('on', 'true', 'True'):
        return 1
    if state in ('off', 'false', 'False'):
        return 0
    value = number(state)
    return None if value is None else int(value > 0)


def resample(series, start, end, step_s=10, max_hold_s=MAX_HOLD_S):
    """series: {column: [(t, value or None)] sorted by t}. Rows every step_s from start to end;
    each column holds its last value (up to max_hold_s when given), else None (unknown)."""
    index = {k: ([t for t, _ in v], [x for _, x in v]) for k, v in series.items()}
    rows = []
    t = start
    while t <= end:
        row = {'t_s': int(t - start)}
        for col in COLUMNS[1:]:
            times, values = index.get(col, ([], []))
            i = bisect.bisect_right(times, t) - 1
            row[col] = values[i] if i >= 0 and (max_hold_s is None or t - times[i] <= max_hold_s) else None
        mod = row.get('modulation_pct')
        row['burner'] = None if mod is None else int(mod > 0)
        rows.append(row)
        t += step_s
    return rows


def write_csv(rows, path):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow(['' if r.get(c) is None else r[c] for c in COLUMNS])


def load(ha, args, start, end):
    states = ha.get('/api/states')
    ids = {col: find(states, suffix) for col, suffix in SUFFIXES.items()}
    sensors = ha.history(list(ids.values()), start, end, minimal=True)
    series = {}
    for col, entity in ids.items():
        convert = flag if col == 'dhw' else number
        series[col] = [(parse_time(r.get('last_changed') or r.get('last_updated')), convert(r.get('state')))
                       for r in sensors.get(entity, [])]
    climate = ha.history([args.room_climate], start, end, minimal=False).get(args.room_climate, [])
    attrs = [(parse_time(r['last_changed']), r.get('attributes') or {}) for r in climate]
    series['room_c'] = [(t, number(a.get('current_temperature'))) for t, a in attrs]
    series['setpoint_c'] = [(t, number(a.get('temperature'))) for t, a in attrs]
    for col, entity in (('room_c', args.room_temperature), ('setpoint_c', args.room_setpoint)):
        if entity:
            rows = ha.history([entity], start, end, minimal=True).get(entity, [])
            series[col] = [(parse_time(r.get('last_changed') or r.get('last_updated')), number(r.get('state'))) for r in rows]
    if args.outdoor:
        rows = ha.history([args.outdoor], start, end, minimal=False).get(args.outdoor, [])
        key = 'temperature' if args.outdoor.startswith('weather.') else None
        series['outdoor_c'] = [(parse_time(r['last_changed']),
                                number((r.get('attributes') or {}).get(key) if key else r.get('state'))) for r in rows]
    ids.update({'room_climate': args.room_climate, 'outdoor': args.outdoor})
    return ids, series


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--ha-url', required=True)
    p.add_argument('--room-climate', required=True)
    p.add_argument('--room-temperature'); p.add_argument('--room-setpoint')
    p.add_argument('--outdoor', help='weather.* (its temperature attribute) or a sensor')
    p.add_argument('--since', required=True); p.add_argument('--until')
    p.add_argument('--step', type=int, default=10)
    p.add_argument('--max-hold', type=int, help='seconds a value holds without a new record (default: until the next record)')
    p.add_argument('--out', required=True)
    p.add_argument('--insecure', action='store_true')
    args = p.parse_args(argv)
    token = os.environ.get('OT_HA_TOKEN', '').strip()
    if not token:
        raise SystemExit('set OT_HA_TOKEN to a Home Assistant long-lived access token')
    ha = HomeAssistant(args.ha_url, token, args.insecure)
    start = parse_since(args.since)
    end = parse_since(args.until) if args.until else dt.datetime.now(dt.timezone.utc)
    ids, series = load(ha, args, start, end)
    rows = resample(series, start.timestamp(), end.timestamp(), args.step, args.max_hold)
    write_csv(rows, args.out)
    print(f'{len(rows)} rows from {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC -> {args.out}')
    print('entities:', ids)
    return 0


if __name__ == '__main__':
    sys.exit(main())
