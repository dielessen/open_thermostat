#!/usr/bin/env python3
"""Score a replay (tools/replay/README.md "Scoring"): a before/after table of two replay JSONs.

    python3 -I tools/replay/score.py <replay.json> [<base.json>]

Reads the "score" object of every run (replay.cpp, rc.5) and prints, per mode, the base (before)
and the replay (after) side by side with the change:

  - heating hours, heating burner starts and starts per heating hour (while the run's request
    asked heat; a start is an off->on edge of the burner that is not hot water),
  - the mean request, measured flow and return while heating (no hot water),
  - the learner's heating energy estimate (kWh, before a gas meter's calibration),
  - the optimum-start hours and the arrival errors per room (every judged morning),
  - with BoilerResponse (rc.5): held events, the boiler's rest and the ceiling per outdoor band.

One file: a single column. Exit status 0, or 2 for a missing, unreadable or malformed file.
"""
import json
import sys

BANDS = ['<-5', '-5..0', '0..5', '5..10', '10..15', '>=15']


class Malformed(Exception):
    pass


def load(path):
    """The replay JSON's runs by mode, after checking every field the table reads."""
    try:
        with open(path, encoding='utf-8') as fh:
            doc = json.load(fh)
    except OSError as e:
        raise Malformed(f'cannot read: {e.strerror or e}') from None
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise Malformed(f'not JSON: {e}') from None
    if not isinstance(doc, dict) or doc.get('tool') != 'openthermostat-replay':
        raise Malformed('not an openthermostat-replay JSON (no "tool": "openthermostat-replay")')
    runs = doc.get('runs')
    if not isinstance(runs, list) or not runs:
        raise Malformed('no "runs"')
    out = {}
    for i, run in enumerate(runs):
        if not isinstance(run, dict) or not isinstance(run.get('mode'), str):
            raise Malformed(f'run {i} has no "mode"')
        score = run.get('score')
        if not isinstance(score, dict):
            raise Malformed(f'run {run["mode"]} has no "score" (a replay from before rc.5? rebuild with tools/replay/run.sh)')
        for key in ('heating_h', 'burner_starts', 'heating_starts', 'heating_kwh', 'optimum_start_h'):
            if not number(score.get(key)):
                raise Malformed(f'run {run["mode"]}: score.{key} is not a number')
        for key in ('starts_per_heating_h', 'request_mean_c', 'flow_mean_c', 'return_mean_c'):
            if score.get(key) is not None and not number(score.get(key)):
                raise Malformed(f'run {run["mode"]}: score.{key} is neither a number nor null')
        arrivals = score.get('arrivals')
        if not isinstance(arrivals, list) or not all(isinstance(a, dict) and isinstance(a.get('room'), str) and number(a.get('error_min'))
                                                     for a in arrivals):
            raise Malformed(f'run {run["mode"]}: score.arrivals is not a list of {{room, error_min}}')
        boiler = score.get('boiler')
        if boiler is not None:
            ceiling = boiler.get('ceiling_c') if isinstance(boiler, dict) else None
            if not isinstance(ceiling, list) or len(ceiling) != len(BANDS) or not all(c is None or number(c) for c in ceiling) \
                    or not number(boiler.get('held')):
                raise Malformed(f'run {run["mode"]}: score.boiler needs "held" and six "ceiling_c" values')
        if run['mode'] in out:
            raise Malformed(f'two runs of mode {run["mode"]}')
        out[run['mode']] = score
    return doc, out


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt(v, digits):
    if v is None:
        return '-'
    if isinstance(v, str):
        return v
    return f'{v:.{digits}f}' if digits else f'{v:.0f}'


def change(before, after, digits):
    if not number(before) or not number(after):
        return ''
    d = after - before
    return f'{d:+.{digits}f}' if digits else f'{d:+.0f}'


def arrivals(score):
    """{room: (mean error, mean |error|, n)} of the judged mornings."""
    rooms = {}
    for a in score['arrivals']:
        rooms.setdefault(a['room'], []).append(a['error_min'])
    return {r: (sum(e) / len(e), sum(abs(x) for x in e) / len(e), len(e)) for r, e in rooms.items()}


def rows(score):
    """(label, value, digits) for one run's score."""
    out = [
        ('heating hours', score['heating_h'], 2),
        ('heating starts', score['heating_starts'], 0),
        ('starts per heating hour', score.get('starts_per_heating_h'), 2),
        ('mean request while heating (C)', score.get('request_mean_c'), 1),
        ('mean flow while heating (C)', score.get('flow_mean_c'), 1),
        ('mean return while heating (C)', score.get('return_mean_c'), 1),
        ('heating kWh (learner estimate)', score['heating_kwh'], 1),
        ('optimum start hours', score['optimum_start_h'], 2),
    ]
    for room, (mean, absolute, n) in sorted(arrivals(score).items()):
        out.append((f'arrival {room}: mean error (min)', mean, 0))
        out.append((f'arrival {room}: mean |error| (min)', absolute, 0))
        out.append((f'arrival {room}: judged mornings', n, 0))
    boiler = score.get('boiler')
    if boiler is not None:
        out.append(('held events', boiler['held'], 0))
        out.append(('boiler rest (s)', boiler.get('rest_s'), 0))
        out.append(('boiler state', boiler.get('state') or '-', 0))
        for band, c in zip(BANDS, boiler['ceiling_c']):
            out.append((f'ceiling, outdoor {band} C', c, 0))
    return out


def header(label, path, doc):
    i = doc.get('inputs') if isinstance(doc.get('inputs'), dict) else {}
    fw = doc.get('firmware') if isinstance(doc.get('firmware'), dict) else {}
    modules = [m for m in ('boiler_response', 'house_model', 'free_heat') if fw.get(m) is True]
    return (f'{label}: {path} ({i.get("first_local", "?")} .. {i.get("last_local", "?")}, {i.get("rows", "?")} rows; '
            f'rc.5 modules: {", ".join(modules) if modules else "none"})')


def table(after, before=None):
    """The text: per mode the rows of both files (labels of either), the change when both have a number."""
    lines = []
    modes = list(after) + [m for m in (before or {}) if m not in after]
    for mode in modes:
        a, b = after.get(mode), (before or {}).get(mode)
        ra = {label: (v, d) for label, v, d in rows(a)} if a else {}
        rb = {label: (v, d) for label, v, d in rows(b)} if b else {}
        labels = [label for label, _, _ in (rows(a) if a else [])] + [label for label, _, _ in (rows(b) if b else []) if label not in ra]
        lines.append('')
        if before is None:
            lines.append(f'[{mode}]'.ljust(40) + 'value'.rjust(12))
        else:
            lines.append(f'[{mode}]'.ljust(40) + 'before'.rjust(12) + 'after'.rjust(12) + 'change'.rjust(10))
        for label in labels:
            va, da = ra.get(label, (None, 0))
            vb, db = rb.get(label, (None, 0))
            digits = da if label in ra else db
            if before is None:
                lines.append(f'  {label}'.ljust(40) + fmt(va, digits).rjust(12))
            else:
                lines.append(f'  {label}'.ljust(40) + fmt(vb, digits).rjust(12) + fmt(va, digits).rjust(12) + change(vb, va, digits).rjust(10))
    return lines


def details(label, runs):
    lines = []
    for mode, score in runs.items():
        judged = score['arrivals']
        if judged and len(judged) <= 30:
            lines.append(f'{label} [{mode}] judged mornings: ' + ', '.join(
                f'{a["room"]} {a.get("rise_local", "?")} {a["error_min"]:+.0f} min' for a in judged))
    return lines


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) not in (1, 2) or any(a.startswith('-') for a in argv):
        print(__doc__.strip().split('\n\n')[1], file=sys.stderr)
        return 2
    loaded = []
    for path in argv:
        try:
            loaded.append((path, *load(path)))
        except Malformed as e:
            print(f'score.py: {path}: {e}', file=sys.stderr)
            return 2
    (path_a, doc_a, after), base = loaded[0], loaded[1] if len(loaded) > 1 else None
    out = ['OpenThermostat replay score', header('after ' if base else 'replay', path_a, doc_a)]
    if base:
        out.append(header('before', base[0], base[1]))
    out += table(after, base[2] if base else None)
    extra = details('after' if base else 'replay', after) + (details('before', base[2]) if base else [])
    if extra:
        out += [''] + extra
    print('\n'.join(out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
