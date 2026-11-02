#!/usr/bin/env python3
"""Convert the E32's MQTT log into the replay CSV (tools/replay/README.md).

Input: the read-only MQTT logger's JSON lines (out/switchover-*/mqtt-active.jsonl), one
{"t": <logger wall time>, "topic": ..., "p": <payload>} per message. Used topics:

  .../fw/state/heating            request {heat, flow_c, reason} -> e32_heat, e32_flow_c, e32_reason;
                                  active.state "active" -> mode active, else shadow
  .../fw/state/boiler_fields/<g>  measured flow/return, modulation, burner bit, heating/dhw
                                  active, outdoor and the old thermostat's 0x1A
                                  (ha/.../boiler_fields.py names every field index)
  .../fw/state/room/<id>          temperature, setpoint -> <id>.temp_c, <id>.target_c

A field's time is the logger time minus (sampled_at_ms - the field's own ms): the E32
publishes a group with the age of each value. Every column holds its last value until the
next one (--max-hold bounds it). One row every --step seconds, UTC.

    python3 -I tools/replay/from_mqtt.py mqtt-active.jsonl out.csv [--room-alias woonkamer=room1]
        [--utc-offset +01:00 | --tz Europe/Amsterdam] [--step 10] [--max-hold S]

The logger writes local wall time without an offset: --utc-offset (fixed) or --tz (an IANA
zone, needs the system's tz database) says which; a time with its own offset wins.
"""
import argparse
import bisect
import csv
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIELDS_PY = ROOT / 'ha/config/custom_components/open_thermostat/boiler_fields.py'
# boiler field name -> replay column (boolean columns as 0/1)
FIELD_COLUMNS = {
    'measured_flow_temperature': 'flow_c',
    'measured_return_temperature': 'return_c',
    'reported_burner_modulation': 'modulation_pct',
    'raw_burner_bit': 'burner',
    'heating_active': 'heating_active',
    'dhw_active': 'dhw_active',
    'outdoor_temperature': 'outdoor_c',
    'thermostat_requested_flow_temperature': 'thermostat_flow_c',
}
FIXED = ['flow_c', 'return_c', 'burner', 'heating_active', 'dhw_active', 'modulation_pct', 'e32_heat', 'e32_flow_c',
         'e32_reason', 'thermostat_flow_c', 'outdoor_c', 'mode']


def field_table(path=FIELDS_PY):
    """{index: (name, divisor)} of boiler.fields.v2 from the HA integration's own table."""
    spec = importlib.util.spec_from_file_location('ot_boiler_fields', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    table = {i: (f[0], f[2]) for i, f in enumerate(mod.FIELDS)}
    table.update({mod.CATALOG_BASE + i: (f[0], f[2]) for i, f in enumerate(mod.CATALOG_FIELDS)})
    return table


def parse_time(text, offset, zone):
    t = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    if t.tzinfo is None:
        t = t.replace(tzinfo=offset or zone)
    return t.timestamp()


def number(value, divisor=1):
    if value is None or isinstance(value, bool):
        return None if value is None else int(value)
    try:
        return round(float(value) / divisor, 3)
    except (TypeError, ValueError):
        return None


def read(lines, table, aliases, offset=None, zone=None):
    """{column: {utc: value}} from the log lines."""
    wanted = {i: (FIELD_COLUMNS[name], div) for i, (name, div) in table.items() if name in FIELD_COLUMNS}
    series = {}

    def put(col, t, v):
        series.setdefault(col, {})[t] = v

    for line in lines:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        t = parse_time(d['t'], offset, zone)
        topic, p = d.get('topic', ''), d.get('p') or {}
        if topic.endswith('/fw/state/heating'):
            r = p.get('request') or {}
            if 'heat' in r:
                put('e32_heat', t, int(bool(r.get('heat'))))
                put('e32_flow_c', t, r.get('flow_c') if r.get('heat') else 0)
                put('e32_reason', t, r.get('reason') or '')
            state = (p.get('active') or {}).get('state')
            put('mode', t, 'active' if state == 'active' else 'shadow')
        elif '/fw/state/boiler_fields/' in topic:
            v = p.get('values') or {}
            sampled = v.get('sampled_at_ms')
            for f in v.get('fields') or []:
                if len(f) < 3 or f[0] not in wanted or f[2] is None or sampled is None:
                    continue
                col, div = wanted[f[0]]
                value = number(f[1], div)
                if col in ('burner', 'heating_active', 'dhw_active') and value is not None:
                    value = int(value > 0)
                put(col, round(t - (sampled - f[2]) / 1000.0, 1), value)
        elif '/fw/state/room/' in topic:
            room = topic.rsplit('/', 1)[1]
            room = aliases.get(room, room)
            if 'temperature' in p:
                put(f'{room}.temp_c', t, number(p.get('temperature')))
            if 'setpoint' in p:
                put(f'{room}.target_c', t, number(p.get('setpoint')))
    return series


def columns(series):
    rooms = sorted({c.rsplit('.', 1)[0] for c in series if c.endswith(('.temp_c', '.target_c'))})
    room_cols = [f'{r}.{k}' for r in rooms for k in ('temp_c', 'target_c')]
    return ['utc'] + room_cols + FIXED


def resample(series, step=10, max_hold=None, start=None, end=None):
    """Rows every step seconds (sample and hold), as lists in columns(series) order."""
    cols = columns(series)
    index = {c: sorted(v.items()) for c, v in series.items()}
    keys = {c: [k for k, _ in v] for c, v in index.items()}
    times = [k for v in keys.values() for k in v]
    if not times:
        return cols, []
    t0 = start if start is not None else int(min(times) // step * step + step)
    t1 = end if end is not None else max(times)
    rows = []
    t = t0
    while t <= t1:
        row = [int(t)]
        for c in cols[1:]:
            i = bisect.bisect_right(keys.get(c, []), t) - 1
            ok = i >= 0 and (max_hold is None or t - keys[c][i] <= max_hold)
            v = index[c][i][1] if ok else None
            row.append('' if v is None else v)
        rows.append(row)
        t += step
    return cols, rows


def write(path, cols, rows):
    with open(path, 'w', newline='\n', encoding='utf-8') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(cols)
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('log')
    ap.add_argument('out')
    ap.add_argument('--room-alias', action='append', default=[], metavar='ID=NEW', help='rename a room (e.g. to anonymise)')
    ap.add_argument('--utc-offset', help='the logger time\'s offset, e.g. +01:00')
    ap.add_argument('--tz', default='Europe/Amsterdam', help='IANA zone of the logger time (default Europe/Amsterdam)')
    ap.add_argument('--step', type=int, default=10)
    ap.add_argument('--max-hold', type=float, help='seconds a value holds without a new message (default: until the next)')
    a = ap.parse_args(argv)
    offset = zone = None
    if a.utc_offset:
        sign = -1 if a.utc_offset.startswith('-') else 1
        hh, mm = a.utc_offset.lstrip('+-').split(':')
        offset = dt.timezone(sign * dt.timedelta(hours=int(hh), minutes=int(mm)))
    else:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(a.tz)
    aliases = dict(x.split('=', 1) for x in a.room_alias)
    with open(a.log, encoding='utf-8') as fh:
        series = read(fh, field_table(), aliases, offset, zone)
    cols, rows = resample(series, a.step, a.max_hold)
    write(a.out, cols, rows)
    f = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')
    print(f'{len(rows)} rows' + (f' from {f(rows[0][0])} to {f(rows[-1][0])}' if rows else '') + f' -> {a.out}')
    print('columns seen:', ', '.join(c for c in cols[1:] if c in series))
    return 0


if __name__ == '__main__':
    sys.exit(main())
