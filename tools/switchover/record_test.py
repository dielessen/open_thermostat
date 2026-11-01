#!/usr/bin/env python3
"""Record the attended switch-over tests (OVERSCHAKELING.nl.md section 6) as they are done.

One small JSON file per session, docs/modern-thermostat/OVERSCHAKELING-RESULTATEN-<date>.json,
read by release_ready.py (criterion "failure_tests"). Every call appends an entry; the
latest entry of a test counts. Nothing here talks to the E32 or Home Assistant.

    python3 tools/switchover/record_test.py init --firmware v0.1.0-e32v2-beta.22 --ha 0.4.0b14
    python3 tools/switchover/record_test.py T1 pass "request 40 degC in 10 s, flow +5 degC in 9 min"
    python3 tools/switchover/record_test.py T7 fail "adapter kept burning 30 min" --evidence "photo 14:32"
    python3 tools/switchover/record_test.py T12 alternative "not cold enough" --evidence "soak frost green, CI run 123"
    python3 tools/switchover/record_test.py status

The install-guide test (1.0 criterion) is recorded the same way:

    python3 tools/switchover/record_test.py install --followed yes --problem "step 4 unclear"
    python3 tools/switchover/record_test.py install --resolve 1 --fixed-in "commit abc1234"

--date picks the session file (default: today, local time); --root the repository.
"""
import argparse
import datetime as dt
import json
import pathlib
import sys

# Section 6 of OVERSCHAKELING.nl.md, in its order. allow_alternative: the checklist itself names an
# alternative proof when the situation cannot be made on the day (T12: not cold enough).
TESTS = (
    ('T1', 'Start', False), ('T2', 'Modulatie', False), ('T3', 'Stop en minimale pauze', False),
    ('T4', 'Tapwater tijdens verwarmen', False), ('T5', 'Teruggeefknop', False),
    ('T6', 'E32-herstart (bewaarde bevestiging) en gedrag van de adapter', False),
    ('T7', 'E32 stroomloos (adaptergedrag)', False), ('T8', 'Wifi weg (20 min)', False),
    ('T9', 'Home Assistant weg', False), ('T10', 'Meting weg', False),
    ('T11', 'Vreemde regelaar (0x1A)', False), ('T12', 'Vorstbeveiliging (simulatie)', True),
)
RESULTS = ('pass', 'fail', 'alternative', 'skipped')
DOCS = 'docs/modern-thermostat'


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def results_path(root, day):
    return pathlib.Path(root) / DOCS / f'OVERSCHAKELING-RESULTATEN-{day}.json'


def install_path(root, day):
    return pathlib.Path(root) / DOCS / f'INSTALLATIETEST-{day}.json'


def new_session(day, firmware, ha):
    return {'schema': 1, 'kind': 'switchover_results', 'date': day, 'firmware': firmware, 'ha': ha,
            'checklist': f'{DOCS}/OVERSCHAKELING.nl.md#6-bijgewoonde-tests',
            'tests': [{'id': i, 'title': t, 'allow_alternative': alt, 'entries': []} for i, t, alt in TESTS]}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode())


def add_entry(session, test_id, result, observed, evidence=None, at=None):
    """Append one entry; returns the test. An alternative needs evidence and must be allowed."""
    if result not in RESULTS:
        raise ValueError(f'result must be one of {RESULTS}')
    test = next((t for t in session['tests'] if t['id'] == test_id.upper()), None)
    if test is None:
        raise ValueError(f'unknown test {test_id}; known: {", ".join(t["id"] for t in session["tests"])}')
    if result == 'alternative' and not (test['allow_alternative'] and evidence):
        raise ValueError(f'{test["id"]}: an alternative proof is only allowed where the checklist names one, with --evidence')
    if not observed.strip():
        raise ValueError('describe what you observed')
    at = at or now_utc()
    entry = {'at_utc': at.strftime('%Y-%m-%dT%H:%M:%SZ'), 'at_local': at.astimezone().strftime('%Y-%m-%d %H:%M'),
             'result': result, 'observed': observed.strip()}
    if evidence:
        entry['evidence'] = evidence.strip()
    test['entries'].append(entry)
    return test


def latest(test):
    return test['entries'][-1] if test['entries'] else None


def status_lines(session):
    lines = []
    for test in session['tests']:
        entry = latest(test)
        state = entry['result'] if entry else 'open'
        lines.append(f"{test['id']:<4} {state:<11} {test['title']}" + (f" - {entry['observed']}" if entry else ''))
    return lines


def new_install_record(day):
    return {'schema': 1, 'kind': 'install_test', 'date': day, 'guide': 'docs/INSTALL.md', 'guide_commit': None,
            'tester': 'someone other than the author', 'followed_to_end': None, 'problems': []}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', default=str(pathlib.Path(__file__).resolve().parents[2]))
    parser.add_argument('--date', default=dt.date.today().isoformat())
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='start the session file')
    init.add_argument('--firmware', required=True)
    init.add_argument('--ha', required=True)
    sub.add_parser('status', help='show every test and its latest result')
    install = sub.add_parser('install', help='record the install-guide test')
    install.add_argument('--followed', choices=('yes', 'no'))
    install.add_argument('--guide-commit')
    install.add_argument('--problem', action='append', default=[])
    install.add_argument('--resolve', type=int, action='append', default=[], help='1-based problem number')
    install.add_argument('--fixed-in')
    for test_id, _, _ in TESTS:
        one = sub.add_parser(test_id, help=f'record {test_id}')
        one.add_argument('result', choices=RESULTS)
        one.add_argument('observed')
        one.add_argument('--evidence')
    args = parser.parse_args(argv)
    path = results_path(args.root, args.date)
    if args.command == 'init':
        if path.exists():
            raise SystemExit(f'{path} exists already')
        save(path, new_session(args.date, args.firmware, args.ha))
        print(f'started {path}')
        return 0
    if args.command == 'install':
        ipath = install_path(args.root, args.date)
        record = load(ipath) if ipath.exists() else new_install_record(args.date)
        if args.followed:
            record['followed_to_end'] = args.followed == 'yes'
        if args.guide_commit:
            record['guide_commit'] = args.guide_commit
        record['problems'] += [{'text': p, 'resolved': False, 'fixed_in': None} for p in args.problem]
        for number in args.resolve:
            if not 1 <= number <= len(record['problems']):
                raise SystemExit(f'no problem {number}')
            record['problems'][number - 1].update(resolved=True, fixed_in=args.fixed_in)
        save(ipath, record)
        print(json.dumps(record, indent=1, ensure_ascii=False))
        return 0
    if not path.exists():
        raise SystemExit(f'{path} does not exist: run "init" first')
    session = load(path)
    if args.command != 'status':
        try:
            add_entry(session, args.command, args.result, args.observed, args.evidence)
        except ValueError as error:
            raise SystemExit(str(error))
        save(path, session)
    print('\n'.join(status_lines(session)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
