#!/usr/bin/env python3
"""Known behaviour of the learning and self-tuning on the anonymised real-data fixture.

Builds tools/replay/replay.cpp against this tree's src/ (tools/replay/run.sh --build-only),
replays test/fixtures/replay/house-shadow.csv in shadow and active mode and checks:

  - AutoTuner proposes nothing on the shadow fixture (it does evaluate a day change);
  - WarmupPlanner never plans more than its default lead without a cooling model;
  - FlowLearner learns at least ACTIVE_MIN_SEGMENTS segments in active mode, with the
    E32's own request as its heating reference (FlowLearner::heatingReference).

Plus the converters on small inline inputs. Skipped without g++ or without the fixture.

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


if __name__ == '__main__':
    unittest.main()
