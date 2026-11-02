#!/usr/bin/env python3
"""Daily review of heating with the E32: comfort on time, flow vs need, cycling, gas, learning.

Read-only. Meant to run daily during the 14-day 1.0 window after the switch-over,
and on the shadow period before it. It works on the CSV of replay_export.py
(--csv) or reads Home Assistant itself (--ha-url, GET only):

    export OT_HA_TOKEN='<long-lived token>'
    python3 -I tools/switchover/active_review.py --ha-url https://homeassistant.local:8123 \\
        --room-climate climate.living_room --since 2026-11-03T12:00Z [--outdoor weather.home] [--insecure]
    python3 -I tools/switchover/active_review.py --csv replay.csv --start 2026-10-30T17:10Z

Per day (local time) it reports:
  comfort     each rise of the target (program step, >= 0.5 degC): minutes until the room
              reached it (within 0.2 degC), the warm-up rate, and whether it took longer than
              the firmware's default lead for this emitter (floor 2 h per degC, max 6 h)
  flow        when the heating burner runs: the flow requested (E32, else the old thermostat)
              against the measured flow and the room's shortfall
  cycling     heating burner starts and runs shorter than 10 minutes (short cycles)
  gas         an estimate from burner modulation x --boiler-kw (heating and hot water apart)
  cooling     with the heating off for 2 h or more: the room's cooling rate per K to outdoor
With --ha-url it also prints the E32's learning state (readiness, segments, learned flow).
"""
import argparse
import csv
import datetime as dt
import json
import os
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

FLOOR_LEAD_S_PER_C, FLOOR_LEAD_MAX_S = 7200, 21600  # WarmupPlanner::defaultLeadS for a floor
REACHED_C = 0.2
RISE_MIN_C = 0.5
SHORT_RUN_S = 600
KWH_PER_M3 = 9.77
COAST_S = 2 * 3600  # floor heating: the emitter still gives heat this long after the burner stops


def f(x):
    return None if x in (None, '') else float(x)


def read_csv(path):
    with open(path, encoding='utf-8') as fh:
        return [{k: f(v) for k, v in r.items()} for r in csv.DictReader(fh)]


def day_key(start_ts, t_s, tz):
    return dt.datetime.fromtimestamp(start_ts + t_s, tz).date().isoformat()


def runs(rows, test):
    """[(t_start, t_end)] while test(row) holds (rows every few seconds, sorted)."""
    out, begin = [], None
    for r in rows:
        if test(r):
            if begin is None:
                begin = r['t_s']
        elif begin is not None:
            out.append((begin, r['t_s'])); begin = None
    if begin is not None and rows:
        out.append((begin, rows[-1]['t_s']))
    return out


def heating_burner(r):
    return (r.get('modulation_pct') or 0) > 0 and not r.get('dhw')


def comfort(rows):
    """Each target rise: when it reached, the rate, and whether it beat the default floor lead."""
    out = []
    for i in range(1, len(rows)):
        a, b = rows[i - 1].get('setpoint_c'), rows[i].get('setpoint_c')
        if a is None or b is None or b - a < RISE_MIN_C:
            continue
        t0, room0 = rows[i]['t_s'], rows[i].get('room_c')
        hit = next((r for r in rows[i:] if r.get('room_c') is not None and r['room_c'] >= b - REACHED_C
                    and r.get('setpoint_c') == b), None)
        reached = hit['t_s'] if hit else None
        changed = next((r['t_s'] for r in rows[i:] if r.get('setpoint_c') not in (None, b)), None)
        item = {'t_s': t0, 'from_c': a, 'to_c': b, 'room_c': room0,
                'shortfall_c': None if room0 is None else round(b - room0, 2)}
        if reached is not None and (changed is None or reached <= changed):
            minutes = (reached - t0) / 60
            item['minutes'] = round(minutes)
            gap = (b - room0) if room0 is not None else None
            if gap and gap > 0 and minutes > 0:
                item['rate_c_per_h'] = round((hit['room_c'] - room0) / (minutes / 60), 2)  # the rise it really made
                lead = min(gap * FLOOR_LEAD_S_PER_C, FLOOR_LEAD_MAX_S) / 60
                item['default_lead_min'] = round(lead)
                item['slower_than_default'] = minutes > lead
        else:
            item['minutes'] = None  # not reached before the target changed or the data ended
        out.append(item)
    return out


def cycling(rows):
    burns = runs(rows, heating_burner)
    durations = [(e - s) for s, e in burns]
    return {'starts': len(burns), 'short_runs': sum(1 for d in durations if d < SHORT_RUN_S),
            'median_run_min': round(statistics.median(durations) / 60, 1) if durations else None}


def flow(rows):
    """When the heating burner runs: requested vs measured flow, and per shortfall band."""
    req, meas, diffs, bands = [], [], [], {}
    for r in rows:
        if not heating_burner(r):
            continue
        want = r.get('e32_flow_c') if (r.get('e32_flow_c') or 0) >= 20 else r.get('thermostat_flow_c')
        if want is None or r.get('flow_c') is None:
            continue
        req.append(want); meas.append(r['flow_c']); diffs.append(r['flow_c'] - want)
        if r.get('room_c') is not None and r.get('setpoint_c') is not None:
            short = r['setpoint_c'] - r['room_c']
            band = '<=0' if short <= 0 else '0-0.5' if short <= 0.5 else '0.5-1' if short <= 1 else '>1'
            bands.setdefault(band, []).append(want)
    med = lambda xs: round(statistics.median(xs), 1) if xs else None
    return {'requested_median_c': med(req), 'measured_median_c': med(meas), 'measured_minus_requested_c': med(diffs),
            'requested_by_shortfall': {k: med(v) for k, v in sorted(bands.items())}}


def compare(rows, step_s):
    """Both the E32 and the old thermostat ask for heat: median and spread of the difference."""
    d = [r['e32_flow_c'] - r['thermostat_flow_c'] for r in rows
         if (r.get('e32_flow_c') or 0) >= 20 and (r.get('thermostat_flow_c') or 0) >= 20]
    e_only = sum(1 for r in rows if (r.get('e32_flow_c') or 0) >= 20 and (r.get('thermostat_flow_c') or 0) < 20)
    t_only = sum(1 for r in rows if (r.get('thermostat_flow_c') or 0) >= 20 and (r.get('e32_flow_c') or 0) < 20)
    q = statistics.quantiles(d, n=10) if len(d) >= 10 else None
    return {'both_heat_min': round(len(d) * step_s / 60), 'median_c': round(statistics.median(d), 1) if d else None,
            'p10_c': round(q[0], 1) if q else None, 'p90_c': round(q[-1], 1) if q else None,
            'e32_only_min': round(e_only * step_s / 60), 'thermostat_only_min': round(t_only * step_s / 60)}


def gas(rows, step_s, boiler_kw):
    heat = sum((r.get('modulation_pct') or 0) / 100 for r in rows if heating_burner(r)) * step_s / 3600 * boiler_kw
    dhw = sum((r.get('modulation_pct') or 0) / 100 for r in rows
              if (r.get('modulation_pct') or 0) > 0 and r.get('dhw')) * step_s / 3600 * boiler_kw
    return {'heating_m3': round(heat / KWH_PER_M3, 2), 'hot_water_m3': round(dhw / KWH_PER_M3, 2)}


def cooling(rows):
    """Heating off >= COAST_S: room slope (degC/h) per K room - outdoor, from the part after the coast."""
    quiet = runs(rows, lambda r: not heating_burner(r))
    k = []
    for s, e in quiet:
        if e - s < COAST_S + 3600:
            continue
        seg = [r for r in rows if s + COAST_S <= r['t_s'] <= e and r.get('room_c') is not None and r.get('outdoor_c') is not None]
        if len(seg) < 2:
            continue
        hours = (seg[-1]['t_s'] - seg[0]['t_s']) / 3600
        drop = seg[0]['room_c'] - seg[-1]['room_c']
        dT = statistics.mean(r['room_c'] - r['outdoor_c'] for r in seg)
        if hours > 0 and dT > 1:
            k.append({'hours': round(hours, 1), 'drop_c': round(drop, 2), 'per_h_per_k': round(drop / hours / dT, 4)})
    return k


def by_day(rows, start_ts, tz):
    days = {}
    for r in rows:
        days.setdefault(day_key(start_ts, r['t_s'], tz), []).append(r)
    return days


def review(rows, start_ts, tz, step_s=10, boiler_kw=22.0):
    out = {}
    for day, rs in by_day(rows, start_ts, tz).items():
        out[day] = {'comfort': comfort(rs), 'cycling': cycling(rs), 'flow': flow(rs), 'compare': compare(rs, step_s),
                    'gas': gas(rs, step_s, boiler_kw), 'cooling': cooling(rs),
                    'outdoor_c': (round(min(r['outdoor_c'] for r in rs if r.get('outdoor_c') is not None), 1),
                                  round(max(r['outdoor_c'] for r in rs if r.get('outdoor_c') is not None), 1))
                    if any(r.get('outdoor_c') is not None for r in rs) else None}
    return out


def learning_state(ha):
    """The E32's learning entities (heating_learned_* / learned_flow) as Home Assistant shows them."""
    out = {}
    for e in ha.get('/api/states'):
        i = e['entity_id']
        if ('learn' in i or 'curve' in i) and (i.startswith('sensor.') or i.startswith('switch.')):
            a = e.get('attributes') or {}
            out[i] = {'state': e['state'], **{k: a[k] for k in ('readiness', 'segments', 'periods', 'status', 'reason') if k in a}}
    return out


def print_report(result, learning=None):
    for day, d in result.items():
        print(f'== {day}  outdoor {d["outdoor_c"]}')
        for c in d['comfort']:
            when = '' if c['minutes'] is None else f'{c["minutes"]} min'
            slow = ' (slower than the default lead)' if c.get('slower_than_default') else ''
            print(f'  comfort  {c["from_c"]}->{c["to_c"]} degC from {c["room_c"]}: {when or "not reached"}'
                  f'{" at " + str(c["rate_c_per_h"]) + " degC/h" if c.get("rate_c_per_h") else ""}{slow}')
        print(f'  cycling  {d["cycling"]}')
        print(f'  flow     {d["flow"]}')
        print(f'  compare  {d["compare"]}')
        print(f'  gas      {d["gas"]}')
        if d['cooling']:
            print(f'  cooling  {d["cooling"]}')
    if learning:
        print('== learning')
        for k, v in learning.items():
            print(f'  {k}: {v}')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('--csv'); p.add_argument('--start', help='the CSV start time (ISO, UTC) for day boundaries')
    p.add_argument('--ha-url'); p.add_argument('--room-climate'); p.add_argument('--room-temperature'); p.add_argument('--room-setpoint')
    p.add_argument('--outdoor'); p.add_argument('--since'); p.add_argument('--until'); p.add_argument('--insecure', action='store_true')
    p.add_argument('--boiler-kw', type=float, default=22.0)
    p.add_argument('--tz-offset-hours', type=float, default=1.0, help='local time for day boundaries (NL winter: 1)')
    p.add_argument('--json')
    args = p.parse_args(argv)
    tz = dt.timezone(dt.timedelta(hours=args.tz_offset_hours))
    learning = None
    if args.csv:
        if not args.start:
            raise SystemExit('--start is needed with --csv')
        from shadow_exit import parse_since
        start_ts = parse_since(args.start).timestamp()
        rows = read_csv(args.csv)
    else:
        if not (args.ha_url and args.room_climate and args.since):
            raise SystemExit('give --csv, or --ha-url with --room-climate and --since')
        import replay_export as rx
        from shadow_exit import HomeAssistant, parse_since
        token = os.environ.get('OT_HA_TOKEN', '').strip()
        if not token:
            raise SystemExit('set OT_HA_TOKEN to a Home Assistant long-lived access token')
        ha = HomeAssistant(args.ha_url, token, args.insecure)
        start = parse_since(args.since)
        end = parse_since(args.until) if args.until else dt.datetime.now(dt.timezone.utc)
        _, series = rx.load(ha, args, start, end)
        start_ts = start.timestamp()
        rows = [{k: (None if v is None else float(v)) for k, v in r.items()}
                for r in rx.resample(series, start_ts, end.timestamp(), 10)]
        learning = learning_state(ha)
    step = rows[1]['t_s'] - rows[0]['t_s'] if len(rows) > 1 else 10
    result = review(rows, start_ts, tz, step, args.boiler_kw)
    print_report(result, learning)
    if args.json:
        with open(args.json, 'w', encoding='utf-8', newline='\n') as fh:
            json.dump({'days': result, 'learning': learning}, fh, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
