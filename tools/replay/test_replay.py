#!/usr/bin/env python3
"""Known behaviour of the learning and self-tuning on the anonymised real-data fixture.

Builds tools/replay/replay.cpp against this tree's src/ (tools/replay/run.sh --build-only),
replays test/fixtures/replay/house-shadow.csv in shadow and active mode and checks:

  - AutoTuner proposes nothing on the shadow fixture (it does evaluate a day change);
  - WarmupPlanner never plans more than its default lead without a cooling model;
  - FlowLearner learns at least ACTIVE_MIN_SEGMENTS segments in active mode, with the
    E32's own request as its heating reference (FlowLearner::heatingReference).

Plus the converters on small inline inputs. Skipped without g++ or without the fixture.

rc.5 (P4): synth.py on a small synthetic house made here (no recorded data): the boiler holds
its target up to +5 K, stops there, rests its anti-cycle and keeps the rows; score.py on
hand-made replay JSONs (the table, the change column, malformed input); and, with g++, a replay
of the synthetic CSV scored by score.py (held events counted once the firmware has BoilerResponse).

    python3 tools/replay/test_replay.py [-v]
Environment: as run.sh (REPLAY_BUILD, REPLAY_LIBDEPS, REPLAY_REV, CXX).
"""
import contextlib
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURE = ROOT / 'test/fixtures/replay/house-shadow.csv'
PLAN = ROOT / 'test/fixtures/replay/plan.json'
ACTIVE_MIN_SEGMENTS = 2  # the fixture in active mode at rc.2: 2 (0 without FlowLearner::heatingReference)

# Checks of behaviour that is still being built, with the branch that brings it. A listed check
# that fails is an expected failure; one that passes is an "unexpected success" and fails the
# run, so the entry is removed when (or right after) the branch is merged.
EXPECTED_FAIL = {}

sys.path.insert(0, str(HERE))
import from_ha  # noqa: E402
import from_mqtt  # noqa: E402
import score  # noqa: E402
import synth  # noqa: E402

SYNTH_COLUMNS = ['utc', 'room1.temp_c', 'room1.target_c', 'flow_c', 'return_c', 'burner', 'heating_active', 'dhw_active', 'modulation_pct',
                 'e32_heat', 'e32_flow_c', 'e32_reason', 'thermostat_flow_c', 'outdoor_c', 'mode']


def synthetic_house(path, hours=8, step=10):
    """A small made-up recording (no recorded data): one room warming while heat is asked, the E32
    asking 32 C (a load the boiler's minimum is too much for), 50 C (it modulates) and nothing in
    turns, the old thermostat asking 38 C in the first half (shadow), then active, and one 3-minute
    hot-water run. The target rises 18.5 -> 21.0 after 2 h with the room less than 1 K below it (no
    warm-up). Returns the rows written."""
    rows, temp, t0 = [], 20.2, 1794283200  # 2026-11-10 04:00 UTC
    for k in range(hours * 3600 // step):
        t = t0 + k * step
        minute = k * step // 60
        phase = minute % 90
        flow = 32 if phase < 40 else 50 if phase < 70 else 0
        temp += (0.15 if flow else -0.2) * step / 3600
        active = minute >= hours * 30
        rows.append({'utc': t, 'room1.temp_c': f'{temp:.2f}', 'room1.target_c': '18.5' if minute < 120 else '21.0',
                     'flow_c': '45.0', 'return_c': '40.0', 'burner': '0', 'heating_active': '0',
                     'dhw_active': '1' if 150 <= minute < 153 else '0', 'modulation_pct': '0',
                     'e32_heat': '1' if flow else '0', 'e32_flow_c': str(flow), 'e32_reason': 'heating' if flow else 'idle',
                     'thermostat_flow_c': '' if active else ('38' if phase < 60 else '0'), 'outdoor_c': '6.0',
                     'mode': 'active' if active else 'shadow'})
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(f'# made up for tools/replay/test_replay.py: one room, {hours} h, no recorded data\n')
        w = csv.DictWriter(fh, SYNTH_COLUMNS, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    return rows


def read_synth(path):
    with open(path, encoding='utf-8') as fh:
        lines = fh.read().splitlines()
    comments = [line for line in lines if line.startswith('#')]
    return comments, list(csv.DictReader(line for line in lines if not line.startswith('#')))


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
        code = fn(*args)
    return code, out.getvalue(), err.getvalue()


def expected_fail(fn):
    return unittest.expectedFailure(fn) if fn.__name__ in EXPECTED_FAIL else fn


def build():
    env = dict(os.environ)
    subprocess.run(['bash', str(HERE / 'run.sh'), '--build-only'], check=True, env=env)
    b = Path(env.get('REPLAY_BUILD', '/tmp/openthermostat-replay'))
    if env.get('REPLAY_REV'):
        rev = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--short=12', env['REPLAY_REV']],
                             check=True, capture_output=True, text=True).stdout.strip()
        return b / f'replay-{rev}'
    return b / 'replay'


def replay(binary, *args):
    with tempfile.TemporaryDirectory() as tmp:
        out, text = Path(tmp) / 'out.json', Path(tmp) / 'out.txt'
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1', UBSAN_OPTIONS='halt_on_error=1')
        subprocess.run([str(binary), '--json', str(out), '--text', str(text), *args], check=True, env=env)
        return json.loads(out.read_text(encoding='utf-8')), text.read_text(encoding='utf-8')


@unittest.skipUnless(shutil.which('g++') and FIXTURE.exists(), 'needs g++ and test/fixtures/replay')
class FixtureReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = build()
        # --no-grace: the fixture's one day change is evaluated (a boot 24 h before the first row).
        cls.out, cls.text = replay(binary, '--plan', str(PLAN), '--mode', 'shadow,active', '--no-grace', str(FIXTURE))
        cls.runs = {r['mode']: r for r in cls.out['runs']}
        if os.environ.get('REPLAY_VERBOSE'):
            print(cls.text)

    def test_replays_the_whole_fixture(self):
        self.assertEqual(self.out['inputs']['rooms'], ['room1'])
        self.assertGreater(self.out['inputs']['rows'], 1000)
        self.assertEqual(set(self.runs), {'shadow', 'active'})
        self.assertGreater(sum(d['observed_h'] for d in self.out['days']), 10)
        self.assertTrue(self.out['warmups'], 'the fixture holds a recorded target rise')
        for run in self.runs.values():
            self.assertEqual(len(run['learner']['rooms']), 1)
            self.assertGreaterEqual(run['learner']['heating_periods'], 1)

    def test_shadow_autotuner_proposes_nothing(self):
        tuner = self.runs['shadow']['autotuner']
        self.assertGreaterEqual(len(tuner['evaluations']), 1, 'no day change was evaluated')
        self.assertEqual(tuner['proposals'], [])
        self.assertEqual(tuner['final']['tuning']['log'], [])

    def test_planner_stays_within_the_default_lead_without_a_cooling_model(self):
        for mode, run in self.runs.items():
            checks = run['planner']['checks']
            with self.subTest(mode=mode):
                self.assertGreater(checks['without_cooling_model'], 0, 'the planner was not consulted without a cooling model')
                self.assertEqual(checks['over_default_lead'], 0, f'{checks["max_over_default_min"]} min over the default lead')
                for plan in run['planner']['schedule']:
                    if plan['reason'] == 'planned':
                        self.assertLessEqual(plan['lead_min'], 6 * 60)  # the floor default's maximum

    @expected_fail
    def test_active_learner_learns_from_e32_request(self):
        run = self.runs['active']
        self.assertEqual(run['learner_reference'], 'e32_request', 'the firmware has no FlowLearner::heatingReference')
        self.assertGreaterEqual(run['learner']['rooms'][0]['segments'], ACTIVE_MIN_SEGMENTS)


class Converters(unittest.TestCase):
    def test_from_mqtt(self):
        table = from_mqtt.field_table()
        index = {name: i for i, (name, _) in table.items()}
        group = [[index['measured_flow_temperature'], 4512, 9000, 0, 24], [index['reported_burner_modulation'], 37, 9000, 0, 24],
                 [index['dhw_active'], 1, 9500, 0, 24], [index['thermostat_requested_flow_temperature'], None, None, 0, 0]]
        lines = [
            json.dumps({'t': '2026-11-01T21:00:00+01:00', 'topic': 'ib-therm/v1/fw/state/boiler_fields/0',
                        'p': {'values': {'sampled_at_ms': 10000, 'fields': group}}}),
            json.dumps({'t': '2026-11-01T21:00:05+01:00', 'topic': 'ib-therm/v1/fw/state/heating',
                        'p': {'request': {'heat': True, 'flow_c': 41, 'reason': 'heating'}, 'active': {'state': 'active'}}}),
            json.dumps({'t': '2026-11-01T21:00:10+01:00', 'topic': 'ib-therm/v1/fw/state/room/woonkamer',
                        'p': {'schema': 1, 'temperature': 20.34, 'setpoint': 21}}),
        ]
        cols, rows = from_mqtt.resample(from_mqtt.read(lines, table, {'woonkamer': 'room1'}), step=10)
        self.assertEqual(cols[:3], ['utc', 'room1.temp_c', 'room1.target_c'])
        last = dict(zip(cols, rows[-1]))
        self.assertEqual(last['flow_c'], 45.12)  # field time 20:59:59: logger time - (10000 - 9000) ms
        self.assertEqual((last['modulation_pct'], last['dhw_active'], last['thermostat_flow_c']), (37, 1, ''))
        self.assertEqual((last['e32_heat'], last['e32_flow_c'], last['e32_reason'], last['mode']), (1, 41, 'heating', 'active'))
        self.assertEqual((last['room1.temp_c'], last['room1.target_c']), (20.34, 21))

    def test_from_ha(self):
        e = 'sensor.e32_heating_'
        export = [
            [{'entity_id': e + 'boiler_measured_flow_temperature', 'state': '40.5', 'last_changed': '2026-10-30T10:00:00+00:00'},
             {'state': 'unavailable', 'last_changed': '2026-10-30T10:00:30+00:00'}],
            [{'entity_id': 'binary_sensor.e32_heating_boiler_dhw_active', 'state': 'on', 'last_changed': '2026-10-30T10:00:00+00:00'}],
            [{'entity_id': e + 'heat_request', 'state': '35', 'last_changed': '2026-10-30T09:00:00+00:00'}],
            [{'entity_id': 'climate.living', 'state': 'heat', 'last_changed': '2026-10-30T08:00:00+00:00',
              'last_updated': '2026-10-30T10:00:10+00:00', 'attributes': {'current_temperature': 20.1, 'temperature': 21}}],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / 'h.json', Path(tmp) / 'h.csv'
            src.write_text(json.dumps(export), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                from_ha.main([str(src), '--room', 'room1=climate.living', '--mode', 'shadow', '--since', '2026-10-30T10:00:00Z',
                              '--until', '2026-10-30T10:00:40Z', '--out', str(out)])
            with out.open(encoding='utf-8') as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 5)
        self.assertEqual((rows[0]['flow_c'], rows[0]['dhw_active'], rows[0]['room1.temp_c']), ('40.5', '1', ''))
        self.assertEqual((rows[1]['room1.temp_c'], rows[1]['room1.target_c']), ('20.1', '21.0'))  # attributes at last_updated
        self.assertEqual((rows[3]['flow_c'], rows[3]['e32_flow_c'], rows[3]['e32_heat'], rows[3]['mode']), ('', '35.0', '1', 'shadow'))


class Synth(unittest.TestCase):
    """synth.py: a holding boiler under the made-up house's requests."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.house = cls.dir / 'house-made-up.csv'
        cls.rows = synthetic_house(cls.house)
        cls.out = cls.dir / 'synth.csv'
        cls.code, cls.text, _ = quiet(synth.main, [str(cls.house), str(cls.out)])
        cls.comments, cls.synth = read_synth(cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_keeps_the_rows_and_says_what_it_is(self):
        self.assertEqual(self.code, 0)
        self.assertEqual([r['utc'] for r in self.synth], [str(r['utc']) for r in self.rows])
        self.assertTrue(self.comments[0].startswith('# synthetic (tools/replay/synth.py) from house-made-up.csv: a holding boiler'))
        self.assertTrue(any(c.startswith('# input: made up for tools/replay/test_replay.py') for c in self.comments))
        for a, b in zip(self.rows, self.synth):  # driver e32: active, no thermostat; rooms and requests are the input's
            self.assertEqual((b['mode'], b['thermostat_flow_c'], b['dhw_active']), ('active', '', '0'))
            self.assertEqual((b['room1.temp_c'], b['room1.target_c'], b['e32_heat'], b['e32_flow_c']),
                             (a['room1.temp_c'], a['room1.target_c'], a['e32_heat'], a['e32_flow_c']))

    def test_holds_its_target_and_rests_its_anti_cycle(self):
        held, stopped = 0, None
        for prev, row in zip(self.synth, self.synth[1:]):
            req = float(row['e32_flow_c']) if row['e32_heat'] == '1' else 0
            flow, at = float(row['flow_c']), int(row['utc'])
            if prev['burner'] == '1' and row['burner'] == '0' and req >= 20:
                self.assertGreaterEqual(flow, req + 5 - 0.5, f'stopped below its held target at {at}')
                held, stopped = held + 1, at
            if prev['burner'] == '0' and row['burner'] == '1' and stopped is not None:
                self.assertGreaterEqual(at - stopped, 600 - 10, f'fired again inside its anti-cycle at {at}')
                stopped = None
            if row['burner'] == '1' and req >= 20:
                self.assertLessEqual(flow, req + 5 + 1, f'ran past its held target at {at}')
                self.assertGreaterEqual(float(row['modulation_pct']), 25, f'modulated below its minimum at {at}')
            self.assertEqual(row['heating_active'], '1' if req >= 20 else '0')
        self.assertGreaterEqual(held, 6, 'the 32 C requests are less than the boiler minimum: it must hold')
        self.assertIn('held targets', self.text)

    def test_recorded_driver_follows_the_controller_of_each_row(self):
        out = self.dir / 'recorded.csv'
        self.assertEqual(quiet(synth.main, [str(self.house), str(out), '--driver', 'recorded', '--hot-water', 'recorded'])[0], 0)
        _, rows = read_synth(out)
        self.assertEqual([(r['mode'], r['thermostat_flow_c']) for r in rows], [(r['mode'], r['thermostat_flow_c']) for r in self.rows])
        self.assertEqual(sum(r['dhw_active'] == '1' for r in rows), 18)  # the 3-minute hot-water run
        for r in rows:
            if r['mode'] == 'shadow' and r['dhw_active'] == '0':  # the old thermostat's 38 C drives the shadow rows
                self.assertEqual(r['heating_active'], '1' if r['thermostat_flow_c'] == '38' else '0')

    def test_is_deterministic(self):
        again = self.dir / 'again.csv'
        quiet(synth.main, [str(self.house), str(again)])
        self.assertEqual(again.read_bytes(), self.out.read_bytes())

    def test_refuses_a_file_without_utc(self):
        bad = self.dir / 'bad.csv'
        bad.write_text('flow_c\n40\n41\n', encoding='utf-8')
        with self.assertRaises(SystemExit):
            quiet(synth.main, [str(bad), str(self.dir / 'never.csv')])


def replay_json(**runs):
    """A minimal replay JSON (replay.cpp's shape) with one score per mode."""
    base = {'heating_h': 10.0, 'burner_starts': 30, 'heating_starts': 25, 'starts_per_heating_h': 2.5, 'request_mean_c': 44.0,
            'flow_mean_c': 46.0, 'return_mean_c': 40.0, 'heating_kwh': 50.0, 'optimum_start_h': 1.0, 'arrivals': []}
    return {'tool': 'openthermostat-replay', 'schema': 1, 'inputs': {'rows': 10, 'first_local': 'a', 'last_local': 'b'},
            'firmware': {}, 'runs': [{'mode': m, 'score': {**base, **s}} for m, s in runs.items()]}


class Score(unittest.TestCase):
    """score.py on hand-made replay JSONs."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, doc):
        path = Path(self.tmp.name) / name
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding='utf-8')
        return str(path)

    @staticmethod
    def cells(out, label):
        return next(line for line in out.splitlines() if line.strip().startswith(label))[40:].split()

    def test_before_after_table(self):
        before = self.write('before.json', replay_json(active={}))
        after = self.write('after.json', replay_json(active={
            'request_mean_c': 41.5, 'heating_starts': 20, 'starts_per_heating_h': 2.0, 'return_mean_c': None,
            'arrivals': [{'room': 'room1', 'rise_local': '2026-11-10 07:00', 'error_min': 12}, {'room': 'room1', 'rise_local': '2026-11-11 07:00', 'error_min': -4}],
            'boiler': {'held': 7, 'state': 'learned', 'rest_s': 610, 'ceiling_c': [None, None, 44, 42, None, None]}}))
        code, out, err = quiet(score.main, [after, before])
        self.assertEqual((code, err), (0, ''))
        self.assertIn('[active]', out)
        self.assertEqual(self.cells(out, 'mean request while heating (C)'), ['44.0', '41.5', '-2.5'])
        self.assertEqual(self.cells(out, 'heating starts'), ['25', '20', '-5'])
        self.assertEqual(self.cells(out, 'starts per heating hour'), ['2.50', '2.00', '-0.50'])
        self.assertEqual(self.cells(out, 'mean return while heating (C)'), ['40.0', '-'])  # unknown: no change
        self.assertEqual(self.cells(out, 'arrival room1: mean error (min)'), ['-', '4'])
        self.assertEqual(self.cells(out, 'arrival room1: mean |error| (min)'), ['-', '8'])
        self.assertEqual(self.cells(out, 'arrival room1: judged mornings'), ['-', '2'])
        self.assertEqual(self.cells(out, 'held events'), ['-', '7'])
        self.assertEqual(self.cells(out, 'ceiling, outdoor 5..10 C'), ['-', '42'])
        self.assertIn('room1 2026-11-10 07:00 +12 min, room1 2026-11-11 07:00 -4 min', out)

    def test_one_file_has_one_column(self):
        code, out, _ = quiet(score.main, [self.write('one.json', replay_json(shadow={}, active={'heating_h': 3.25}))])
        self.assertEqual(code, 0)
        self.assertIn('[shadow]', out)
        self.assertEqual(self.cells(out.split('[active]')[1], 'heating hours'), ['3.25'])

    def test_malformed_input_exits_2(self):
        good = replay_json(active={})
        score_of = good['runs'][0]['score']
        cases = {
            'missing.json': None,
            'text.json': 'not json',
            'other.json': {'tool': 'something else', 'runs': []},
            'no-runs.json': {**good, 'runs': []},
            'no-score.json': {**good, 'runs': [{'mode': 'active'}]},
            'bad-number.json': {**good, 'runs': [{'mode': 'active', 'score': {**score_of, 'heating_h': 'ten'}}]},
            'bad-arrivals.json': {**good, 'runs': [{'mode': 'active', 'score': {**score_of, 'arrivals': [{'room': 1}]}}]},
            'bad-boiler.json': {**good, 'runs': [{'mode': 'active', 'score': {**score_of, 'boiler': {'held': 1, 'ceiling_c': [40] * 5}}}]},
            'twice.json': {**good, 'runs': good['runs'] * 2},
        }
        for name, doc in cases.items():
            path = str(Path(self.tmp.name) / name) if doc is None else self.write(name, doc)
            with self.subTest(name):
                code, out, err = quiet(score.main, [path])
                self.assertEqual((code, out), (2, ''))
                self.assertIn('score.py:', err)
        self.assertEqual(quiet(score.main, [])[0], 2)
        self.assertEqual(quiet(score.main, ['-v'])[0], 2)


@unittest.skipUnless(shutil.which('g++'), 'needs g++')
class SyntheticReplay(unittest.TestCase):
    """synth.py -> replay (active, the recorded request, the default plan: the CSV's target) -> score.py,
    on the made-up house."""
    @classmethod
    def setUpClass(cls):
        binary = build()
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        synthetic_house(d / 'house.csv')
        quiet(synth.main, [str(d / 'house.csv'), str(d / 'synth.csv')])
        cls.out, cls.text = replay(binary, '--mode', 'active', '--recorded-request', '--apply-learned', '--weather-curve', '--no-grace',
                                   str(d / 'synth.csv'))
        (d / 'replay.json').write_text(json.dumps(cls.out), encoding='utf-8')
        cls.scored = quiet(score.main, [str(d / 'replay.json')])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_replay_scores_the_synthetic_boiler(self):
        s = self.out['runs'][0]['score']
        self.assertGreater(s['heating_h'], 3)
        self.assertGreater(s['heating_starts'], 3)
        self.assertGreater(s['request_mean_c'], 32)   # the recorded 32 and 50 C
        self.assertLess(s['request_mean_c'], 50)
        code, out, _ = self.scored
        self.assertEqual(code, 0)
        self.assertIn('[active]', out)

    def test_boiler_response_hears_the_held_targets(self):
        if not self.out['firmware'].get('boiler_response'):
            self.skipTest('the firmware has no BoilerResponse yet (rc.5 P1)')
        boiler = self.out['runs'][0]['score']['boiler']
        self.assertGreaterEqual(boiler['held'], 1, 'a boiler that holds the E32 target again and again is not heard')
        if boiler['rest_s'] is not None:  # reported once a few rests were seen
            self.assertGreaterEqual(boiler['rest_s'], 540)  # its own 10-minute anti-cycle


if __name__ == '__main__':
    unittest.main()
