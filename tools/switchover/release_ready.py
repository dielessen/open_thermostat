#!/usr/bin/env python3
"""Release readiness for 1.0: are the 1.0 criteria met? (NEXT-RELEASE.nl.md, "1.0")

Read-only. It reads Home Assistant history (GET only), the attended switch-over results,
the update receipts and the install-test record in the repository, and prints PASS / WAIT /
FAIL per criterion:

  1. stability       14 days without an unexpected restart or a long offline E32; a restart
                     around a firmware install is planned and does not count (shadow_exit.py)
  2. active_control  the E32 has run the boiler itself (boiler_output_enabled, HA 0.4.0b14+)
                     for the last 14 days without a hand-back
  3. trv_control     every room with radiator valves has had valve control on for 14 days;
                     an installation without valves (no valve-control switches) passes as not applicable
                     (WAIT until the 1.0 valve control exists and is switched on)
  4. failure_tests   every attended switch-over test (OVERSCHAKELING.nl.md section 6) passed,
                     recorded with record_test.py in OVERSCHAKELING-RESULTATEN-<date>.json
  5. updates         at least one update was accepted on the official Home Assistant route
  6. install_guide   someone other than the author followed the install guide to the end and
                     every problem found is resolved (INSTALLATIETEST-<date>.json)

  7. release_window  the 14 days are the days of --release: the update entity showed that release
                     as installed for the whole window and no install happened inside it. An
                     install, or a later candidate, starts a new window; a report of "rc.4"
                     cannot include days on rc.3 (R5-09). It counts toward the overall result in
                     --stage final, and the gate requires it PASS for v1.0.0.

WAIT means not yet; FAIL blocks until it is fixed and measured again. --stage final writes
the report the release gate requires for v1.0.0 (scripts/verify_e32_update_gate.py);
--stage candidate is the same report for a 1.0 candidate, which may be published before
the 14 days. Start the window (--since) after the install of --release ended; the gate also
requires that.

    export OT_HA_TOKEN='<long-lived token>'
    python3 -I tools/switchover/release_ready.py --ha-url https://homeassistant.local:8123 \\
        --release v1.0.0-e32v2-rc.1 [--since 2026-11-03T14:00Z] [--stage final] \\
        [--json docs/modern-thermostat/RELEASE-READINESS-1.0.json] [--insecure]

Entities are found by their suffix unless given: _device_uptime, the climate entity that carries
boiler_output_enabled, the E32's _firmware update entity, and valve-control switches ending in
--trv-suffix. Exit status 0 only when every criterion passes.

Saved evidence instead of a live Home Assistant (nothing is requested):

    python3 -I tools/switchover/release_ready.py --history-file <saved /api/history/period answer> [...]
        [--states-file <saved /api/states answer>] --release v1.0.0-e32v2-rc.5 --stage final
        --since 2026-11-05T05:55:13Z --until 2026-11-05T09:00:00Z [--json <report>]

The window ends at --until (required). A row before --since stands for the state at --since, as Home
Assistant's history does. Without --states-file (or --trv-entity) the valve switches cannot be listed, so
trv_control is WAIT ("not measured"), never "not applicable". The report lists the files and their SHA-256.

The owner's stable declaration (docs/modern-thermostat/STABLE-RELEASE-TAGS.en.md, "Owner-declared stable
release"): --declaration <file in --root> quotes the owner's words and names the criteria he declares;
--declare <criterion>=<reason> declares one (default: the declaration's declared_criteria). A declared
criterion becomes DECLARED with its measured result kept under "measured"; a measured FAIL is never
declared and updates is always measured. With every criterion PASS or DECLARED the overall result is
PASS_DECLARED, which the gate accepts only with that declaration (bound by digest) and only for the stable
tag it names. A declaration whose statement is still the placeholder "<OWNER STATEMENT>" is refused.
"""
import argparse
import datetime as dt
import glob
import hashlib
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
WINDOW = 'release_window'  # the seventh criterion: the window is about --release only (R5-09)
DECLARED = 'DECLARED'
PLACEHOLDER = '<OWNER STATEMENT>'  # scripts/verify_e32_update_gate.DECLARATION_PLACEHOLDER
UPTIME_UNITS = {'s': 1, 'min': 60, 'h': 3600, 'd': 86400}  # Home Assistant reports the uptime in its display unit


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
    # rc.5: the valve-control switches exist only for rooms with radiator valves (HA 1.0.0rc6), so an
    # installation without them has nothing to measure: not applicable, which PASSES the criterion (the
    # gate requires PASS on every criterion; a house without valves must not be held back by them).
    # None: the entity list is unknown (saved evidence without a state list), so absence proves nothing.
    if by_entity is None:
        return {'result': WAIT, 'why': 'not measured: the saved evidence has no entity list (--states-file) to tell '
                                       'whether the installation has valve-control switches', 'rooms': {}}
    if not by_entity:
        return {'result': PASS, 'not_applicable': True,
                'why': 'not applicable: no radiator valves in this installation (no valve-control switches)', 'rooms': {}}
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
    # A receipt with checks the owner declared (from the saved history) is listed, but never counts as measured.
    accepted = [(p, r) for p, r in receipts
                if r.get('status') == 'PASS' and r.get('method') == 'home_assistant' and not r.get('declared_checks')]
    declared = [str(p) for p, r in receipts
                if r.get('status') == 'PASS' and r.get('method') == 'home_assistant' and r.get('declared_checks')]
    tags = [r.get('tag') for _, r in accepted]
    extra = {'receipts_with_declared_checks': declared} if declared else {}
    if accepted:
        return {'result': PASS, 'why': f'{len(accepted)} updates accepted on the Home Assistant route', 'tags': tags,
                'receipts': [str(p) for p, _ in accepted], **extra}
    return {'result': WAIT, 'why': 'no update accepted on the Home Assistant route yet', 'tags': [], **extra}


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


def release_window(installed, release):
    """installed: [(t, installed_version)] from the update entity's history over the window, oldest first.
    PASS only when that history shows `release` and nothing else: no other version, so no install inside it."""
    versions = []
    for _, version in installed:
        if version and (not versions or versions[-1] != version):
            versions.append(version)
    if not versions:
        return {'result': WAIT, 'why': 'no history of the update entity: the window cannot be tied to the release',
                'versions': []}
    if versions == [release]:
        return {'result': PASS, 'why': f'{release} was installed for the whole window, no install inside it',
                'versions': versions}
    if release not in versions:
        return {'result': FAIL, 'why': f'the update entity never showed {release} in this window (it showed '
                                       f'{", ".join(versions)})', 'versions': versions}
    return {'result': FAIL, 'why': f'the window contains more than {release}: {", ".join(versions)}; start it after '
                                   'the install of the release ended', 'versions': versions}


def evaluate(history, end, repo, release=None, stage='candidate'):
    """history: {'uptime', 'offline', 'planned', 'output': [(t, bool|None)], 'trv': {entity: series},
    'installed': [(t, version)]}; repo: {'sessions', 'receipts', 'installs'}. With `release`, the release_window
    criterion is added; in --stage final it takes part in the overall result."""
    out = {
        'stability': se.stability(history['uptime'], end, history.get('offline', ()), history.get('planned', ()),
                                  hours_needed=HOURS_NEEDED),
        'active_control': active_control(history.get('output', []), end),
        'trv_control': trv_control(history.get('trv', {}), end),
        'failure_tests': failure_tests(repo.get('sessions', [])),
        'updates': updates(repo.get('receipts', [])),
        'install_guide': install_guide(repo.get('installs', [])),
    }
    if release is not None:
        out[WINDOW] = release_window(history.get('installed', []), release)
    results = [out[c]['result'] for c in CRITERIA + ((WINDOW,) if release is not None and stage == 'final' else ())]
    overall = PASS if all(r == PASS for r in results) else FAIL if FAIL in results else WAIT
    return overall, out


def declare(overall, criteria, declared, stage):
    """The owner's declaration over the measured criteria: each declared one becomes DECLARED with its measured
    result kept. Refused for updates (always measured) and over a measured FAIL. Returns (overall, criteria)."""
    for name, reason in declared.items():
        if name not in criteria or name == 'updates':
            raise SystemExit(f'{name} cannot be declared (declarable: '
                             f'{", ".join(c for c in CRITERIA + (WINDOW,) if c != "updates")})')
        if criteria[name]['result'] == FAIL:
            raise SystemExit(f'{name} measured FAIL ({criteria[name]["why"]}): a declaration never overrides a FAIL')
        if not isinstance(reason, str) or not reason.strip():
            raise SystemExit(f'{name}: a declared criterion needs its reason')
    out = {name: ({'result': DECLARED, 'why': 'declared by the owner: ' + declared[name], 'declared': declared[name],
                   'measured': value} if name in declared else value) for name, value in criteria.items()}
    counted = CRITERIA + ((WINDOW,) if stage == 'final' and WINDOW in out else ())
    results = [out[c]['result'] for c in counted]
    if all(r in (PASS, DECLARED) for r in results):
        overall = 'PASS_DECLARED' if DECLARED in results else PASS
    else:
        overall = FAIL if FAIL in results else WAIT
    return overall, out


def read_declaration(root, name, given):
    """The owner's stable declaration (a file in the repository): his statements, and the criteria to declare
    (--declare wins over the file's declared_criteria). A placeholder statement is refused."""
    path = (Path(root) / name).resolve()
    if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
        raise SystemExit(f'{name}: the declaration must be a file in {root}')
    document = json.loads(path.read_text(encoding='utf-8'))
    statements = [item.get('text') for item in ((document.get('owner') or {}).get('statements') or [])
                  if isinstance(item, dict)]
    if not statements or any(not isinstance(t, str) or not t.strip() or PLACEHOLDER in t for t in statements):
        raise SystemExit(f'{name}: the owner statement is still a placeholder or missing; nothing can be declared '
                         'until his own words are in it')
    declared = dict(given) if given else dict(document.get('declared_criteria') or {})
    if not declared:
        raise SystemExit(f'{name} declares no criterion and no --declare was given')
    block = {'file': Path(name).as_posix(), 'statements': statements, 'declared_criteria': sorted(declared)}
    return block, declared


class SavedHistory:
    """Saved Home Assistant answers instead of a live one: /api/history/period exports (lists of series) and,
    optionally, /api/states. history() answers as Home Assistant does: the last row before the start stands for
    the state at the start."""

    def __init__(self, exports, states=None):
        self.series, self.states = {}, states
        for export in exports:
            for rows in export:
                if not rows or not isinstance(rows[0], dict) or 'entity_id' not in rows[0]:
                    raise SystemExit('a history export is a list of series, each starting with a row that has entity_id')
                known = self.series.setdefault(rows[0]['entity_id'], [])
                known += [row for row in rows if row not in known]
        for rows in self.series.values():
            rows.sort(key=lambda r: se.parse_time(r.get('last_changed') or r.get('last_updated')))

    def get(self, path):
        if path != '/api/states':
            raise SystemExit(f'saved evidence cannot answer {path}')
        if self.states is not None:
            return self.states
        return [{'entity_id': entity, 'state': rows[-1].get('state'),
                 'attributes': next((r['attributes'] for r in reversed(rows) if r.get('attributes')), {})}
                for entity, rows in sorted(self.series.items())]

    def history(self, entity_ids, start, end, minimal):
        out = {}
        for entity in entity_ids:
            rows = self.series.get(entity) or []
            before = [r for r in rows if se.parse_time(r.get('last_changed') or r.get('last_updated')) <= start.timestamp()]
            inside = [r for r in rows
                      if start.timestamp() < se.parse_time(r.get('last_changed') or r.get('last_updated')) <= end.timestamp()]
            # Home Assistant's first row is the full state at the start (minimal rows lack the attributes).
            known = next((r['attributes'] for r in reversed(before) if r.get('attributes')), None)
            first = [dict(before[-1], entity_id=entity, last_changed=start.isoformat(), last_updated=start.isoformat(),
                          **({'attributes': known} if known is not None else {}))] if before else []
            if first or inside:
                out[entity] = first + inside
        return out


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
    listed = not isinstance(ha, SavedHistory) or ha.states is not None  # saved history alone does not list entities
    trv = args.trv_entity or (sorted(s['entity_id'] for s in states if s['entity_id'].endswith(args.trv_suffix))
                              if listed else None)
    ids = {'uptime': uptime, 'output': output, 'update': update, 'trv': trv}
    rows = ha.history([uptime], start, end, minimal=True).get(uptime, [])
    unit = next(((r.get('attributes') or {}).get('unit_of_measurement') for r in rows
                 if (r.get('attributes') or {}).get('unit_of_measurement')), 's')
    scale = UPTIME_UNITS.get(unit)
    if scale is None:
        raise SystemExit(f'{uptime}: unknown uptime unit {unit!r}')

    def seconds(state):
        value = se.number(state)
        return None if value is None else value * scale
    history = {'uptime': [(se.parse_time(r.get('last_changed') or r.get('last_updated')), seconds(r.get('state'))) for r in rows]}
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
    planned, seen, installed = [], None, []
    if update:
        for r in ha.history([update], start, end, minimal=False).get(update, []):
            version = (r.get('attributes') or {}).get('installed_version')
            if version and seen and version != seen:
                planned.append(se.parse_time(r.get('last_changed') or r.get('last_updated')))
            if version:
                installed.append((se.parse_time(r.get('last_changed') or r.get('last_updated')), version))
            seen = version or seen
    history['planned'] = planned
    history['installed'] = installed
    history['output'] = []
    if output:
        for r in ha.history([output], start, end, minimal=False).get(output, []):
            value = None if r.get('state') in ('unavailable', 'unknown') else boolean((r.get('attributes') or {}).get('boiler_output_enabled'))
            history['output'].append((se.parse_time(r.get('last_changed') or r.get('last_updated')), value))
    history['trv'] = None if trv is None else {}
    if trv:
        for entity, rows in ha.history(trv, start, end, minimal=True).items():
            history['trv'][entity] = [(se.parse_time(r.get('last_changed') or r.get('last_updated')),
                                       None if r.get('state') in ('unavailable', 'unknown') else boolean(r.get('state')))
                                      for r in rows]
    return ids, history


def report(release, stage, start, end, ids, overall, criteria, declaration=None, evidence=None):
    """The report the gate reads. The window's installed versions are the measured ones, also when the window
    criterion is declared."""
    window = criteria.get(WINDOW) or {}
    document = {'schema': 1, 'kind': 'release_readiness', 'release': release, 'stage': stage,
                'from': start.strftime('%Y-%m-%dT%H:%M:%SZ'), 'to': end.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'days_needed': DAYS_NEEDED, 'entities': ids, 'overall': overall, 'criteria': criteria,
                'installed_versions': (window.get('measured') or window).get('versions'),
                'generated_by': 'tools/switchover/release_ready.py'}
    if evidence is not None:
        document['source'] = 'saved_history'
        document['evidence_files'] = evidence
    if declaration is not None:
        document['declaration'] = declaration
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--ha-url')
    source.add_argument('--history-file', action='append', help='a saved /api/history/period answer (repeatable)')
    parser.add_argument('--states-file', help='a saved /api/states answer (with --history-file)')
    parser.add_argument('--until', help='end of the window (ISO; required with --history-file)')
    parser.add_argument('--declaration', help="the owner's stable declaration, a path in --root")
    parser.add_argument('--declare', action='append', default=[], metavar='CRITERION=REASON',
                        help='declare one criterion (with --declaration); default: the declaration\'s declared_criteria')
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
    given = {}
    for item in args.declare:
        name, _, reason = item.partition('=')
        if not reason.strip():
            parser.error(f'--declare {item!r}: give CRITERION=REASON')
        given[name.strip()] = reason.strip()
    if given and not args.declaration:
        parser.error("--declare needs --declaration (the owner's stable declaration with his own words)")
    if (args.history_file is None) != (args.until is None) or (args.states_file and not args.history_file):
        parser.error('--until and --states-file go with --history-file (saved evidence), and --history-file needs --until')
    evidence = None
    if args.history_file:
        root = Path(args.root).resolve()
        exports, evidence = [], []
        for name in args.history_file:
            raw = Path(name).read_bytes()
            exports.append(json.loads(raw))
            path = Path(name).resolve()
            evidence.append({'path': path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
                             'sha256': hashlib.sha256(raw).hexdigest(), 'kind': 'ha_history'})
        states = None
        if args.states_file:
            raw = Path(args.states_file).read_bytes()
            states = json.loads(raw)
            path = Path(args.states_file).resolve()
            evidence.append({'path': path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix(),
                             'sha256': hashlib.sha256(raw).hexdigest(), 'kind': 'ha_states'})
        ha = SavedHistory(exports, states)
        end = se.parse_since(args.until).astimezone(dt.timezone.utc).replace(microsecond=0)
    else:
        token = os.environ.get('OT_HA_TOKEN', '').strip()
        if not token:
            raise SystemExit('set OT_HA_TOKEN to a Home Assistant long-lived access token')
        ha = se.HomeAssistant(args.ha_url, token, args.insecure)
        end = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    start = se.parse_since(args.since) if args.since else end - dt.timedelta(days=DAYS_NEEDED + 1)
    declaration, declared = (read_declaration(args.root, args.declaration, given) if args.declaration else (None, {}))
    ids, history = load_history(ha, args, start, end)
    overall, criteria = evaluate(history, end.timestamp(), read_repo(args.root), release=args.release, stage=args.stage)
    if declaration is not None:
        overall, criteria = declare(overall, criteria, declared, args.stage)
    print(f'1.0 readiness of {args.release} ({args.stage}), {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC'
          + (' (saved evidence)' if evidence is not None else ''))
    for name in CRITERIA + (WINDOW,):
        line = f'  {criteria[name]["result"]:<8}  {name:<15} {criteria[name]["why"]}'
        if criteria[name]['result'] == DECLARED:
            line += f' [measured: {criteria[name]["measured"]["result"]}, {criteria[name]["measured"]["why"]}]'
        print(line)
    print(f'Overall: {overall}')
    if declaration is not None:
        print('Owner declaration:', declaration['file'], '|', ' | '.join(declaration['statements']))
    if args.json:
        Path(args.json).write_bytes((json.dumps(report(args.release, args.stage, start, end, ids, overall, criteria,
                                                       declaration, evidence),
                                                indent=1, ensure_ascii=False) + '\n').encode())
    return 0 if overall in (PASS, 'PASS_DECLARED') else 1


if __name__ == '__main__':
    sys.exit(main())
