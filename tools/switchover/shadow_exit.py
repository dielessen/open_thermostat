#!/usr/bin/env python3
"""Shadow exit criteria: is the E32 ready to take over from the old thermostat?

Read-only. It reads Home Assistant history (GET only) and, optionally, the E32's
MQTT topics, and prints PASS / FAIL / WAIT per criterion of the switch-over
plan (docs/SWITCHOVER.md, OVERSCHAKELING.nl.md section 3):

  1. stable          72 h without a restart or an offline E32
  2. periods         at least 10 heating periods of the thermostat, among them
                     a night setback, a morning warm-up and a no-demand period
  3. timing          the E32 starts and stops heat within minutes of the thermostat
  4. flow            the E32's flow request never exceeds the hard limit: the lowest
                     of the plan maximum (--plan-max), the boiler's own heating limit
                     and 80 degC (owner, 30 Oct 2026: keep the hard limit and learn;
                     the flow level itself is not judged, the E32 learns it)
  5. cycling         the E32 would not start the burner more often than the thermostat

WAIT means there is not enough data yet; it is not a failure. The difference
between the E32's and the thermostat's requested flow is reported as INFO
(median and spread), never as PASS or FAIL.

    export OT_HA_TOKEN='<long-lived token>'
    python3 -I tools/switchover/shadow_exit.py --ha-url https://homeassistant.local:8123 \\
        --climate climate.living_room --plan-max 60 [--days 3 | --since 2026-10-30T17:10Z] \\
        [--mqtt-log listener.txt] [--json out.json]

The E32 entities are found by their suffix (_heat_request,
_thermostat_requested_flow_temperature, _device_uptime and the optional
_boiler_configured_heating_temperature) unless given.
--insecure skips the TLS check for a Home Assistant with a self-signed
certificate on your own network. Exit status 0 only when every criterion passes.
"""
import argparse
import datetime as dt
import json
import os
import re
import ssl
import statistics
import sys
import urllib.parse
import urllib.request

HARD_CEILING_C = 80.0  # the firmware's absolute ceiling (ActiveHeatGuard / ActiveHeatEnvelope)
STABLE_HOURS = 72
MIN_PERIODS = 10
OFFLINE_MINUTES = 5
MERGE_GAP_S = 120          # a heat request that drops for less than this is one period
MATCH_WINDOW_S = 30 * 60   # a start or stop further apart than this is not the same event
TIMING_MEDIAN_S, TIMING_P90_S, TIMING_MATCHED = 5 * 60, 15 * 60, 0.8
SETBACK_C = 0.5
NO_DEMAND_S = 60 * 60

PASS, FAIL, WAIT, INFO = 'PASS', 'FAIL', 'WAIT', 'INFO'


def number(state):
    try:
        value = float(state)
    except (TypeError, ValueError):
        return None
    return value if value == value else None  # NaN is no value


def parse_time(text):
    return dt.datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp()


def periods(series, end, merge_gap_s=MERGE_GAP_S):
    """[(start, stop)] where the value is above zero; series: [(t, value or None)], sorted."""
    out = []
    on_since = None
    for i, (t, value) in enumerate(series):
        on = value is not None and value > 0
        if on and on_since is None:
            on_since = t
        elif not on and on_since is not None:
            out.append([on_since, t])
            on_since = None
    if on_since is not None:
        out.append([on_since, end])
    merged = []
    for start, stop in out:
        if merged and start - merged[-1][1] < merge_gap_s:
            merged[-1][1] = stop
        else:
            merged.append([start, stop])
    return [tuple(p) for p in merged]


PLANNED_WINDOW_S = (-120, 900)  # a restart from 2 min before to 15 min after a firmware install is planned


def stability(uptime, end, offline=(), planned=()):
    """uptime: [(t, seconds or None)]. Restarts are drops of the uptime; offline:
    [(start, stop)] where the E32 was unavailable; planned: times of firmware installs.

    A restart within PLANNED_WINDOW_S of an install is planned (owner, 31 Oct 2026:
    "je kan alle testdata wel bij elkaar optellen, ook de data voor de reboot") and
    does not reset the stable time; every other restart does."""
    known = [(t, v) for t, v in uptime if v is not None]  # an 'unavailable' sample sits between the two sides of a reboot
    restarts = [t for (t0, a), (t, b) in zip(known, known[1:]) if b < a]
    lo, hi = PLANNED_WINDOW_S
    unplanned = [t for t in restarts if not any(p + lo <= t <= p + hi for p in planned)]
    last = max(restarts) if restarts else None
    values = [(t, v) for t, v in uptime if v is not None]
    if not values:
        return {'result': WAIT, 'why': 'no uptime samples'}
    t_first, up_first = values[0]
    t_last, up_last = values[-1]
    if unplanned:
        since = end - max(unplanned)
    elif restarts:  # only planned restarts: all observed time counts, plus the uptime before the first sample
        since = up_first + (end - t_first)
    else:
        since = up_last + (end - t_last)  # the uptime keeps counting between samples
    long_offline = [(a, b) for a, b in offline if b - a >= OFFLINE_MINUTES * 60 and b > end - STABLE_HOURS * 3600]
    hours = since / 3600
    detail = {'hours_since_restart': round(hours, 1), 'restarts_seen': len(restarts),
              'planned_restarts': len(restarts) - len(unplanned), 'offline_stretches': len(long_offline)}
    if last is not None:
        detail['last_restart'] = dt.datetime.fromtimestamp(last, dt.timezone.utc).isoformat(timespec='minutes')
    if long_offline:
        return {'result': FAIL, 'why': f'E32 offline for {OFFLINE_MINUTES} min or more in the last {STABLE_HOURS} h', **detail}
    if hours < STABLE_HOURS:
        return {'result': WAIT, 'why': f'{hours:.1f} h of the {STABLE_HOURS} h without a restart so far', **detail}
    return {'result': PASS, 'why': f'{hours:.1f} h without a restart', **detail}


def setbacks(targets, tz):
    """Night setbacks and morning rises of the target: [(t, delta)] by local hour."""
    night, morning = [], []
    for (t0, a), (t, b) in zip(targets, targets[1:]):
        if a is None or b is None or abs(b - a) < SETBACK_C:
            continue
        hour = dt.datetime.fromtimestamp(t, tz).hour
        if b < a and (hour >= 18 or hour < 3):
            night.append((t, b - a))
        elif b > a and 4 <= hour < 10:
            morning.append((t, b - a))
    return night, morning


def heating_periods(tado, e32, targets, tz, end):
    night, morning = setbacks(targets, tz)
    warmups = [t for t, _ in morning if any(0 <= start - t <= 3600 for start, _ in tado)]
    quiet = []
    previous_stop = None
    for start, stop in tado:
        if previous_stop is not None and start - previous_stop >= NO_DEMAND_S:
            quiet.append((previous_stop, start))
        previous_stop = stop
    agreed_quiet = [q for q in quiet if overlap(e32, *q) <= 0.1 * (q[1] - q[0])]
    detail = {'thermostat_periods': len(tado), 'night_setbacks': len(night), 'morning_warmups': len(warmups),
              'no_demand_periods': len(agreed_quiet)}
    missing = [name for name, n in (('night setback', len(night)), ('morning warm-up', len(warmups)),
                                    ('no-demand period', len(agreed_quiet))) if not n]
    if len(tado) >= MIN_PERIODS and not missing:
        return {'result': PASS, 'why': f'{len(tado)} periods with a night setback, a morning warm-up and a quiet period', **detail}
    need = []
    if len(tado) < MIN_PERIODS:
        need.append(f'{len(tado)} of {MIN_PERIODS} periods')
    need += [f'no {m} yet' for m in missing]
    return {'result': WAIT, 'why': '; '.join(need), **detail}


def overlap(intervals, start, stop):
    return sum(max(0.0, min(b, stop) - max(a, start)) for a, b in intervals)


def timing(tado, e32):
    deltas, unmatched = [], 0
    for index in (0, 1):  # starts, then stops
        theirs = [p[index] for p in tado]
        ours = [p[index] for p in e32]
        for t in theirs:
            nearest = min((abs(o - t) for o in ours), default=None)
            if nearest is None or nearest > MATCH_WINDOW_S:
                unmatched += 1
            else:
                deltas.append(nearest)
    events = len(deltas) + unmatched
    if events < 2 * MIN_PERIODS:
        return {'result': WAIT, 'why': f'{events} start/stop events, need {2 * MIN_PERIODS}', 'events': events}
    matched = len(deltas) / events
    median = statistics.median(deltas) if deltas else None
    p90 = sorted(deltas)[max(0, int(round(0.9 * len(deltas))) - 1)] if deltas else None
    detail = {'events': events, 'matched_share': round(matched, 2),
              'median_min': None if median is None else round(median / 60, 1),
              'p90_min': None if p90 is None else round(p90 / 60, 1)}
    ok = matched >= TIMING_MATCHED and median is not None and median <= TIMING_MEDIAN_S and p90 <= TIMING_P90_S
    why = (f"{detail['matched_share']:.0%} matched, median {detail['median_min']} min, 90% within {detail['p90_min']} min"
           if deltas else 'the E32 never started or stopped near the thermostat')
    return {'result': PASS if ok else FAIL, 'why': why, **detail}


def value_at(series, t):
    """The step series' value at t (the latest sample at or before t), else None."""
    value = None
    for at, v in series:
        if at > t:
            break
        value = v
    return value


def flow(e32_series, end, plan_max=None, boiler=()):
    """The E32's positive requests against the hard limit: min(plan maximum, the
    boiler's own heating limit at that moment, 80 degC). Any request above it fails."""
    total, breaches, values = 0.0, [], []
    for (t, v), nxt in zip(e32_series, e32_series[1:] + [(end, None)]):
        if v is None or v <= 0:
            continue
        limits = [HARD_CEILING_C] + ([plan_max] if plan_max else [])
        reported = value_at(boiler, t)
        if reported is not None and reported > 0:
            limits.append(reported)
        limit = min(limits)
        total += max(0.0, nxt[0] - t)
        values.append(v)
        if v > limit:
            breaches.append({'at': dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(timespec='minutes'),
                             'flow_c': v, 'limit_c': limit})
    known = 'plan maximum ' + (f'{plan_max:.0f}' if plan_max else 'not given') + ', boiler limit ' + (
        'reported' if boiler else 'unknown') + f', ceiling {HARD_CEILING_C:.0f} degC'
    detail = {'requests_min': round(total / 60), 'breaches': breaches[:20], 'breach_count': len(breaches),
              'plan_max_c': plan_max, 'max_c': max(values) if values else None, 'limits': known}
    if breaches:
        worst = max(breaches, key=lambda b: b['flow_c'] - b['limit_c'])
        return {'result': FAIL, 'why': f"{len(breaches)} request(s) above the hard limit, worst {worst['flow_c']:.0f} > "
                                        f"{worst['limit_c']:.0f} degC at {worst['at']}", **detail}
    if total < 3600:
        return {'result': WAIT, 'why': f'{total / 60:.0f} min of E32 heat requests so far, none above the hard limit ({known})',
                **detail}
    return {'result': PASS, 'why': f"never above the hard limit (max {detail['max_c']:.0f} degC; {known})", **detail}


def comparison(e32_series, tado_series, start, end, step_s=60):
    """INFO only: E32 minus thermostat requested flow while both ask heat, sampled every minute."""
    diffs = []
    t = start
    while t < end:
        a, b = value_at(e32_series, t), value_at(tado_series, t)
        if a and b and a > 0 and b > 0:
            diffs.append(a - b)
        t += step_s
    if not diffs:
        return {'result': INFO, 'why': 'no minute in which both asked heat yet', 'minutes': 0}
    ordered = sorted(diffs)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]
    detail = {'minutes': len(diffs), 'median_c': statistics.median(diffs), 'p10_c': pick(0.1), 'p90_c': pick(0.9)}
    return {'result': INFO, 'why': f"E32 minus thermostat while both heat: median {detail['median_c']:+.0f} degC, "
                                   f"10-90% {detail['p10_c']:+.0f} to {detail['p90_c']:+.0f} degC over {len(diffs)} min",
            **detail}


def cycling(tado, e32):
    if len(tado) < MIN_PERIODS:
        return {'result': WAIT, 'why': f'{len(tado)} thermostat periods so far', 'thermostat': len(tado), 'e32': len(e32)}
    ok = len(e32) <= len(tado)
    return {'result': PASS if ok else FAIL, 'why': f'E32 {len(e32)} heat periods, thermostat {len(tado)}',
            'thermostat': len(tado), 'e32': len(e32)}


def mqtt_health(lines):
    """Lines of the read-only listener: '<secs> <R|-> <topic> <n>B <payload>'."""
    beats, boot_ids, availability = [], set(), None
    for line in lines:
        m = re.match(r'\s*([\d.]+) [R-] (\S+) \d+B ?(.*)', line)
        if not m:
            continue
        secs, topic, payload = float(m.group(1)), m.group(2), m.group(3)
        if topic.endswith('/fw/heartbeat'):
            beats.append(secs)
        elif topic.endswith('/fw/availability'):
            availability = payload.strip()
        elif topic.endswith('/fw/hello'):
            boot = re.search(r'"boot_id":"([0-9a-f]+)"', payload)
            if boot:
                boot_ids.add(boot.group(1))
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    detail = {'availability': availability, 'heartbeats': len(beats), 'max_gap_s': max(gaps) if gaps else None,
              'boot_ids': len(boot_ids)}
    if availability != 'online':
        return {'result': FAIL, 'why': f'availability is {availability!r}', **detail}
    if len(boot_ids) > 1:
        return {'result': FAIL, 'why': 'the E32 restarted while listening', **detail}
    if len(beats) < 2:
        return {'result': WAIT, 'why': 'fewer than two heartbeats heard (listen 130 s or longer)', **detail}
    ok = max(gaps) <= 75
    return {'result': PASS if ok else FAIL, 'why': f'{len(beats)} heartbeats, largest gap {max(gaps):.0f} s', **detail}


def evaluate(history, end, tz, mqtt_lines=None, plan_max=None):
    """history: {'uptime', 'e32', 'tado', 'target', optional 'boiler': [(t, value)], 'offline': [(start, stop)]}."""
    tado = periods(history['tado'], end)
    e32 = periods(history['e32'], end)
    out = {
        'stable': stability(history['uptime'], end, history.get('offline', ()), history.get('planned', ())),
        'periods': heating_periods(tado, e32, history['target'], tz, end),
        'timing': timing(tado, e32),
        'flow': flow(history['e32'], end, plan_max, history.get('boiler', ())),
        'cycling': cycling(tado, e32),
    }
    first = min((t for key in ('e32', 'tado') for t, _ in history[key][:1]), default=end)
    out['comparison'] = comparison(history['e32'], history['tado'], first, end)
    if mqtt_lines is not None:
        out['mqtt'] = mqtt_health(mqtt_lines)
    return out


class HomeAssistant:
    def __init__(self, url, token, insecure=False):
        self.url, self.token = url.rstrip('/'), token
        self.context = ssl._create_unverified_context() if insecure else ssl.create_default_context()

    def get(self, path):
        request = urllib.request.Request(self.url + path, headers={'Authorization': 'Bearer ' + self.token,
                                                                    'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=120, context=self.context) as response:
            return json.load(response)

    def history(self, entity_ids, start, end, minimal):
        query = {'filter_entity_id': ','.join(entity_ids), 'end_time': end.isoformat(),
                 'significant_changes_only': '0'}
        if minimal:
            query['minimal_response'] = ''
        rows = self.get('/api/history/period/' + urllib.parse.quote(start.isoformat()) + '?' + urllib.parse.urlencode(query))
        by_id = {}
        for series in rows:
            if series:
                entity = series[0]['entity_id']
                by_id[entity] = series
        return by_id


def parse_since(text):
    value = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


def find(states, suffix, optional=False):
    ids = sorted(s['entity_id'] for s in states if s['entity_id'].startswith('sensor.') and s['entity_id'].endswith(suffix))
    if optional and not ids:
        return None
    if len(ids) != 1:
        raise SystemExit(f'expected one sensor ending in {suffix}, found {ids or "none"}: pass it explicitly')
    return ids[0]


def load(ha, args, start, end):
    states = ha.get('/api/states')
    ids = {'uptime': args.uptime or find(states, '_device_uptime'),
           'e32': args.e32_request or find(states, '_heat_request'),
           'tado': args.thermostat_request or find(states, '_thermostat_requested_flow_temperature')}
    boiler = args.boiler_limit or find(states, '_boiler_configured_heating_temperature', optional=True)
    if boiler:
        ids['boiler'] = boiler
    sensors = ha.history(list(ids.values()), start, end, minimal=True)
    climate = ha.history([args.climate], start, end, minimal=False).get(args.climate, [])
    history = {}
    for key, entity in ids.items():
        rows = sensors.get(entity, [])
        history[key] = [(parse_time(r.get('last_changed') or r.get('last_updated')), number(r.get('state'))) for r in rows]
    history['target'] = [(parse_time(r['last_changed']), number((r.get('attributes') or {}).get('temperature')))
                         for r in climate]
    offline, since = [], None
    for t, state in [(parse_time(r.get('last_changed') or r.get('last_updated')), r.get('state')) for r in sensors.get(ids['uptime'], [])]:
        if state in ('unavailable', 'unknown') and since is None:
            since = t
        elif state not in ('unavailable', 'unknown') and since is not None:
            offline.append((since, t)); since = None
    if since is not None:
        offline.append((since, end.timestamp()))
    history['offline'] = offline
    # Planned restarts: every change of the installed version on the E32's Firmware entity.
    update = args.update_entity or next((e['entity_id'] for e in states if e['entity_id'].startswith('update.')
                                         and e['entity_id'].endswith('_firmware') and 'e32' in e['entity_id']), None)
    planned, seen = [], None
    if update:
        ids['update'] = update
        for r in ha.history([update], start, end, minimal=False).get(update, []):
            version = (r.get('attributes') or {}).get('installed_version')
            if version and seen and version != seen:
                planned.append(parse_time(r.get('last_changed') or r.get('last_updated')))
            seen = version or seen
    planned += [parse_since(t).timestamp() for t in args.planned_restart]
    history['planned'] = planned
    return ids, history


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--ha-url', required=True)
    parser.add_argument('--climate', required=True, help='the old thermostat (its target temperature)')
    parser.add_argument('--days', type=float, default=3.0)
    parser.add_argument('--since', help='start here instead (ISO time, e.g. the install of the current firmware)')
    parser.add_argument('--plan-max', type=float, help="the room plan's maximum flow in degC (this house: 60)")
    parser.add_argument('--uptime'); parser.add_argument('--e32-request'); parser.add_argument('--thermostat-request')
    parser.add_argument('--boiler-limit', help="the boiler's reported heating limit sensor (found by its suffix)")
    parser.add_argument('--update-entity', help="the E32's Firmware update entity (found by its suffix)")
    parser.add_argument('--planned-restart', action='append', default=[],
                        help='an extra planned restart (ISO time), e.g. an install the history does not show')
    parser.add_argument('--mqtt-log', help='output of the read-only MQTT listener (optional)')
    parser.add_argument('--json', help='also write the result here')
    parser.add_argument('--insecure', action='store_true', help='self-signed certificate on your own network')
    args = parser.parse_args(argv)
    token = os.environ.get('OT_HA_TOKEN', '').strip()
    if not token:
        raise SystemExit('set OT_HA_TOKEN to a Home Assistant long-lived access token')
    ha = HomeAssistant(args.ha_url, token, args.insecure)
    tz_name = ha.get('/api/config').get('time_zone') or 'UTC'
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:  # no tz database (Windows without the tzdata package): this computer's zone
        tz = dt.datetime.now().astimezone().tzinfo
        tz_name = f'{tz_name} not found, using this computer\'s zone {tz}'
    end = dt.datetime.now(dt.timezone.utc)
    start = parse_since(args.since) if args.since else end - dt.timedelta(days=args.days)
    ids, history = load(ha, args, start, end)
    lines = open(args.mqtt_log, encoding='utf-8').read().splitlines() if args.mqtt_log else None
    result = evaluate(history, end.timestamp(), tz, lines, args.plan_max)
    print(f'Shadow exit criteria, {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC ({tz_name})')
    for name, r in result.items():
        print(f'  {r["result"]:<4}  {name:<10} {r["why"]}')
    judged = [r for r in result.values() if r['result'] != INFO]
    overall = PASS if all(r['result'] == PASS for r in judged) else (
        FAIL if any(r['result'] == FAIL for r in judged) else WAIT)
    print(f'Overall: {overall}')
    if args.json:
        with open(args.json, 'w', encoding='utf-8', newline='\n') as f:
            json.dump({'from': start.isoformat(), 'to': end.isoformat(), 'entities': ids, 'overall': overall,
                       'criteria': result}, f, indent=1)
    return 0 if overall == PASS else 1


if __name__ == '__main__':
    sys.exit(main())
