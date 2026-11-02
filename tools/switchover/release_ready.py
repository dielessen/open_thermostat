#!/usr/bin/env python3
"""Release readiness for 1.0: are the four 1.0 criteria met? (NEXT-RELEASE.nl.md, "1.0")

Read-only. It reads Home Assistant history (GET only), the attended switch-over results,
the update receipts and the install-test record in the repository, and prints PASS / WAIT /
FAIL per criterion:

  1. stability       14 days without an unexpected restart or a long offline E32; a restart
                     around a firmware install is planned and does not count (shadow_exit.py)
  2. active_control  the E32 has run the boiler itself (boiler_output_enabled, HA 0.4.0b14+)
                     for the last 14 days without a hand-back
  3. trv_control     every room with radiator valves has had valve control on for 14 days
                     (WAIT until the 1.0 valve control exists and is switched on)
  4. failure_tests   every attended switch-over test (OVERSCHAKELING.nl.md section 6) passed,
                     recorded with record_test.py in OVERSCHAKELING-RESULTATEN-<date>.json
  5. updates         at least one update was accepted on the official Home Assistant route
  6. install_guide   someone other than the author followed the install guide to the end and
                     every problem found is resolved (INSTALLATIETEST-<date>.json)

WAIT means not yet; FAIL blocks until it is fixed and measured again. --stage final writes
the report the release gate requires for v1.0.0 (scripts/verify_e32_update_gate.py);
--stage candidate is the same report for a 1.0 candidate, which may be published before
the 14 days.

    export OT_HA_TOKEN='<long-lived token>'
    python3 -I tools/switchover/release_ready.py --ha-url https://homeassistant.local:8123 \\
        --release v1.0.0-e32v2-rc.1 [--since 2026-11-03T14:00Z] [--stage final] \\
        [--json docs/modern-thermostat/RELEASE-READINESS-1.0.json] [--insecure]

Entities are found by their suffix unless given: _device_uptime, the climate entity that carries
boiler_output_enabled, the E32's _firmware update entity, and valve-control switches ending in
--trv-suffix. Exit status 0 only when every criterion passes.
"""
import argparse
import datetime as dt
import glob
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shadow_exit as se  # noqa: E402

PASS, FAIL, WAIT = se.PASS, se.FAIL, se.WAIT
DAYS_NEEDED = 14
HOURS_NEEDED = DAYS_NEEDED * 24
GAP_TOLERANCE_S = 3600   # Home Assistant unavailable for less than this does not end a span
DOCS = 'docs/modern-thermostat'
CRITERIA = ('stability', 'active_control', 'trv_control', 'failure_tests', 'updates', 'install_guide')


def spans(series, end, gap_tolerance_s=GAP_TOLERANCE_S):
    """series: [(t, True|False|None)] -> [(start, stop)] while True. None (unavailable) shorter
    than the tolerance keeps the state before it; a longer one ends the span where it began."""
    out, start, gap_from = [], None, None
    for t, value in series:
        if value is None:
            if start is not None and gap_from is None:
                gap_from = t
            continue
        if gap_from is not None:
            if t - gap_from > gap_tolerance_s and start is not None:
                out.append((start, gap_from))
                start = None
            gap_from = None
        if value and start is None:
            start = t
        elif not value and start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        stop = gap_from if gap_from is not None and end - gap_from > gap_tolerance_s else end
        out.append((start, stop))
    return out


def span_criterion(series, end, what):
    found = spans(series, end)
    current = found[-1][1] - found[-1][0] if found and found[-1][1] == end else 0
    longest = max((b - a for a, b in found), default=0)
    detail = {'current_hours': round(current / 3600, 1), 'longest_hours': round(longest / 3600, 1),
              'interruptions': max(len(found) - 1, 0), 'active_hours': round(sum(b - a for a, b in found) / 3600, 1)}
    if current >= HOURS_NEEDED * 3600:
        return {'result': PASS, 'why': f'{what} for {current / 3600:.0f} h without interruption', **detail}
    if not found:
        return {'result': WAIT, 'why': f'{what}: not yet', **detail}
    return {'result': WAIT, 'why': f'{what}: {current / 3600:.1f} of {HOURS_NEEDED} h so far', **detail}


def active_control(series, end):
    return span_criterion(series, end, 'the E32 ran the boiler')


def trv_control(by_entity, end):
    if not by_entity:
        return {'result': WAIT, 'why': 'no radiator-valve control entities yet (1.0 valve control)', 'rooms': {}}
    rooms = {entity: span_criterion(series, end, 'valve control') for entity, series in sorted(by_entity.items())}
    ok = all(r['result'] == PASS for r in rooms.values())
    short = [e for e, r in rooms.items() if r['result'] != PASS]
    return {'result': PASS if ok else WAIT,
            'why': f'{len(rooms)} rooms with valve control, all 14 days' if ok else f'waiting for {", ".join(short)}',
            'rooms': {e: {k: v for k, v in r.items() if k != 'why'} for e, r in rooms.items()}}


def failure_tests(sessions):
    """sessions: the OVERSCHAKELING-RESULTATEN documents. The latest entry of a test counts."""
    tests = {}
    for session in sessions:
        for test in session.get('tests', []):
            known = tests.setdefault(test['id'], {'title': test.get('title'), 'allow_alternative': test.get('allow_alternative', False), 'entries': []})
            known['entries'] += test.get('entries', [])
    if not tests:
        return {'result': WAIT, 'why': 'no attended switch-over results recorded yet', 'tests': {}}
    summary, failed, open_ = {}, [], []
    for test_id, test in sorted(tests.items(), key=lambda kv: int(kv[0][1:])):
        entry = max(test['entries'], key=lambda e: e['at_utc']) if test['entries'] else None
        result = entry['result'] if entry else 'open'
        if result == 'alternative' and not (test['allow_alternative'] and entry.get('evidence')):
            result = 'fail'
        summary[test_id] = {'result': result, 'at_utc': entry and entry['at_utc'], 'observed': entry and entry['observed']}
        if result == 'fail':
            failed.append(test_id)
        elif result not in ('pass', 'alternative'):
            open_.append(test_id)
    if failed:
        return {'result': FAIL, 'why': f'failed: {", ".join(failed)}', 'tests': summary}
    if open_:
        return {'result': WAIT, 'why': f'not done yet: {", ".join(open_)}', 'tests': summary}
    return {'result': PASS, 'why': f'all {len(summary)} tests passed', 'tests': summary}


def updates(receipts):
    """receipts: [(path, record)]. One accepted update on the official route is enough."""
    accepted = [(p, r) for p, r in receipts
                if r.get('status') == 'PASS' and r.get('method') == 'home_assistant']
    tags = [r.get('tag') for _, r in accepted]
    if accepted:
        return {'result': PASS, 'why': f'{len(accepted)} updates accepted on the Home Assistant route', 'tags': tags,
                'receipts': [str(p) for p, _ in accepted]}
    return {'result': WAIT, 'why': 'no update accepted on the Home Assistant route yet', 'tags': []}


def install_guide(records):
    if not records:
        return {'result': WAIT, 'why': 'nobody has followed the install guide yet (INSTALLATIETEST-<date>.json)'}
    done = [r for r in records if r.get('followed_to_end') is True]
    if not done:
        stuck = [r for r in records if r.get('followed_to_end') is False]
        if stuck:
            return {'result': FAIL, 'why': 'the tester could not finish the install guide', 'date': stuck[-1].get('date')}
        return {'result': WAIT, 'why': 'install test started, not finished'}
    last = max(done, key=lambda r: r.get('date', ''))
    open_ = [p['text'] for p in last.get('problems', []) if not p.get('resolved')]
    if open_:
        return {'result': WAIT, 'why': f'{len(open_)} problems from the install test still open', 'open': open_}
    return {'result': PASS, 'why': f'followed to the end on {last.get("date")}, {len(last.get("problems", []))} problems resolved',
            'guide_commit': last.get('guide_commit')}


def evaluate(history, end, repo):
    """history: {'uptime', 'offline', 'planned', 'output': [(t, bool|None)], 'trv': {entity: series}};
    repo: {'sessions', 'receipts', 'installs'}."""
    out = {
        'stability': se.stability(history['uptime'], end, history.get('offline', ()), history.get('planned', ()),
                                  hours_needed=HOURS_NEEDED),
        'active_control': active_control(history.get('output', []), end),
        'trv_control': trv_control(history.get('trv', {}), end),
        'failure_tests': failure_tests(repo.get('sessions', [])),
        'updates': updates(repo.get('receipts', [])),
        'install_guide': install_guide(repo.get('installs', [])),
    }
    results = [out[c]['result'] for c in CRITERIA]
    overall = PASS if all(r == PASS for r in results) else FAIL if FAIL in results else WAIT
    return overall, out


def read_repo(root):
    root = Path(root)
    docs = root / DOCS
    def load(path):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
    sessions = [d for d in map(load, sorted(glob.glob(str(docs / 'OVERSCHAKELING-RESULTATEN-*.json'))))
                if isinstance(d, dict) and d.get('kind') == 'switchover_results']
    receipts = []
    for path in sorted(glob.glob(str(docs / 'update-acceptance' / 'e32-*.json'))):
        record = load(path)
        if isinstance(record, dict) and 'status' in record and 'tag' in record:
            receipts.append((Path(path).relative_to(root).as_posix(), record))
    installs = [d for d in map(load, sorted(glob.glob(str(docs / 'INSTALLATIETEST-*.json'))))
                if isinstance(d, dict) and d.get('kind') == 'install_test']
    return {'sessions': sessions, 'receipts': receipts, 'installs': installs}


def boolean(value):
    return {True: True, False: False, 'on': True, 'off': False, 'true': True, 'false': False}.get(value)


def load_history(ha, args, start, end):
    states = ha.get('/api/states')
    uptime = args.uptime or se.find(states, '_device_uptime')
    output = args.output_entity or next((s['entity_id'] for s in sorted(states, key=lambda s: s['entity_id'])
                                         if s['entity_id'].startswith('climate.')
                                         and 'boiler_output_enabled' in (s.get('attributes') or {})), None)
    update = args.update_entity or next((s['entity_id'] for s in states if s['entity_id'].startswith('update.')
                                         and s['entity_id'].endswith('_firmware') and 'e32' in s['entity_id']), None)
    trv = args.trv_entity or sorted(s['entity_id'] for s in states if s['entity_id'].endswith(args.trv_suffix))
    ids = {'uptime': uptime, 'output': output, 'update': update, 'trv': trv}
    rows = ha.history([uptime], start, end, minimal=True).get(uptime, [])
    history = {'uptime': [(se.parse_time(r.get('last_changed') or r.get('last_updated')), se.number(r.get('state'))) for r in rows]}
    offline, since = [], None
    for r in rows:
        t = se.parse_time(r.get('last_changed') or r.get('last_updated'))
        if r.get('state') in ('unavailable', 'unknown') and since is None:
            since = t
        elif r.get('state') not in ('unavailable', 'unknown') and since is not None:
            offline.append((since, t)); since = None
    if since is not None:
        offline.append((since, end.timestamp()))
    history['offline'] = offline
    planned, seen = [], None
    if update:
        for r in ha.history([update], start, end, minimal=False).get(update, []):
            version = (r.get('attributes') or {}).get('installed_version')
            if version and seen and version != seen:
                planned.append(se.parse_time(r.get('last_changed') or r.get('last_updated')))
            seen = version or seen
    history['planned'] = planned
    history['output'] = []
    if output:
        for r in ha.history([output], start, end, minimal=False).get(output, []):
            value = None if r.get('state') in ('unavailable', 'unknown') else boolean((r.get('attributes') or {}).get('boiler_output_enabled'))
            history['output'].append((se.parse_time(r.get('last_changed') or r.get('last_updated')), value))
    history['trv'] = {}
    if trv:
        for entity, rows in ha.history(trv, start, end, minimal=True).items():
            history['trv'][entity] = [(se.parse_time(r.get('last_changed') or r.get('last_updated')),
                                       None if r.get('state') in ('unavailable', 'unknown') else boolean(r.get('state')))
                                      for r in rows]
    return ids, history


def report(release, stage, start, end, ids, overall, criteria):
    return {'schema': 1, 'kind': 'release_readiness', 'release': release, 'stage': stage,
            'from': start.strftime('%Y-%m-%dT%H:%M:%SZ'), 'to': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'days_needed': DAYS_NEEDED, 'entities': ids, 'overall': overall, 'criteria': criteria,
            'generated_by': 'tools/switchover/release_ready.py'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--ha-url', required=True)
    parser.add_argument('--release', required=True, help='the release that was measured, e.g. v1.0.0-e32v2-rc.1')
    parser.add_argument('--stage', choices=('candidate', 'final'), default='candidate')
    parser.add_argument('--since', help='start of the window (ISO); default 15 days back')
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--uptime'); parser.add_argument('--output-entity'); parser.add_argument('--update-entity')
    parser.add_argument('--trv-entity', action='append', default=[])
    parser.add_argument('--trv-suffix', default='_valve_control')
    parser.add_argument('--json', help='also write the report here')
    parser.add_argument('--insecure', action='store_true', help='self-signed certificate on your own network')
    args = parser.parse_args(argv)
    token = os.environ.get('OT_HA_TOKEN', '').strip()
    if not token:
        raise SystemExit('set OT_HA_TOKEN to a Home Assistant long-lived access token')
    ha = se.HomeAssistant(args.ha_url, token, args.insecure)
    end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = se.parse_since(args.since) if args.since else end - dt.timedelta(days=DAYS_NEEDED + 1)
    ids, history = load_history(ha, args, start, end)
    overall, criteria = evaluate(history, end.timestamp(), read_repo(args.root))
    print(f'1.0 readiness of {args.release} ({args.stage}), {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC')
    for name in CRITERIA:
        print(f'  {criteria[name]["result"]:<4}  {name:<15} {criteria[name]["why"]}')
    print(f'Overall: {overall}')
    if args.json:
        Path(args.json).write_bytes((json.dumps(report(args.release, args.stage, start, end, ids, overall, criteria),
                                                indent=1, ensure_ascii=False) + '\n').encode())
    return 0 if overall == PASS else 1


if __name__ == '__main__':
    sys.exit(main())
