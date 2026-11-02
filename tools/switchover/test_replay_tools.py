"""Tests for replay_export.py, active_review.py and the learning replay harness (no network).

    python3 -I -m unittest discover -s tools/switchover -p "test_*.py" -v

The harness test builds test/learning_replay/replay.cpp with g++ and cJSON when both are
present (after `pio pkg install -e native`, or OT_CJSON_DIR=<dir with cJSON.c>), else it is skipped.
"""
import csv
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import active_review as ar  # noqa: E402
import replay_export as rx  # noqa: E402

UTC = dt.timezone.utc


def house(hours=30, step=10, store=False):
    """A floor-heated room: the thermostat asks 40 degC while below target; target 19 at night,
    21 from 06:30. Optional keep-warm store: 3 min hot water every 11 min."""
    rows, room = [], 19.0
    for k in range(int(hours * 3600 / step)):
        t = k * step
        hour = (t / 3600) % 24
        target = 21.0 if 6.5 <= hour < 22 else 19.0
        heat = room < target - 0.05
        dhw = store and (t // 60) % 11 < 3
        mod = 100.0 if dhw else (40.0 if heat else 0.0)
        room += (0.6 if heat else -0.1) * step / 3600
        rows.append({'t_s': t, 'room_c': round(room, 2), 'setpoint_c': target, 'flow_c': 70.0 if dhw else (40.0 if heat else 30.0),
                     'return_c': 35.0, 'modulation_pct': mod, 'burner': int(mod > 0), 'dhw': int(dhw),
                     'thermostat_flow_c': 40.0 if heat else 0.0, 'e32_flow_c': 37.0 if heat else 0.0, 'outdoor_c': 5.0})
    return rows


class Export(unittest.TestCase):
    def test_resample_holds_until_the_next_record_and_marks_unknown(self):
        series = {'room_c': [(0, 20.0), (30, None), (50, 21.0)], 'modulation_pct': [(0, 0.0), (20, 50.0)]}
        rows = rx.resample(series, 0, 60, 10)
        self.assertEqual([r['room_c'] for r in rows], [20.0, 20.0, 20.0, None, None, 21.0, 21.0])
        self.assertEqual([r['burner'] for r in rows], [0, 0, 1, 1, 1, 1, 1])
        bounded = rx.resample(series, 0, 60, 10, max_hold_s=15)
        self.assertIsNone(bounded[2]['room_c'])  # 20 s old > 15 s

    def test_flags(self):
        self.assertEqual([rx.flag(x) for x in ('on', 'off', '1.0', '0.0', 'unavailable')], [1, 0, 1, 0, None])


class Review(unittest.TestCase):
    def setUp(self):
        self.rows = house()
        self.start = dt.datetime(2026, 11, 3, tzinfo=UTC).timestamp()

    def test_comfort_reports_the_morning_rise(self):
        rises = ar.comfort(self.rows)
        morning = [c for c in rises if c['to_c'] == 21.0]
        self.assertTrue(morning)
        self.assertIsNotNone(morning[0]['minutes'])
        self.assertAlmostEqual(morning[0]['rate_c_per_h'], 0.5, delta=0.15)

    def test_compare_and_flow(self):
        c = ar.compare(self.rows, 10)
        self.assertEqual(c['median_c'], -3.0)
        f = ar.flow(self.rows)
        self.assertEqual(f['requested_median_c'], 37.0)  # the E32's request wins over the thermostat's

    def test_cycling_and_gas(self):
        cyc = ar.cycling(self.rows)
        self.assertGreaterEqual(cyc['starts'], 1)
        g = ar.gas(self.rows, 10, 22.0)
        self.assertGreater(g['heating_m3'], 0)
        self.assertEqual(g['hot_water_m3'], 0)

    def test_keep_warm_store_counts_as_hot_water_not_cycling_heat(self):
        rows = house(store=True)
        g = ar.gas(rows, 10, 22.0)
        self.assertGreater(g['hot_water_m3'], 0)
        result = ar.review(rows, self.start, UTC, 10, 22.0)
        self.assertTrue(result)

    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'r.csv')
            rx.write_csv(self.rows[:5], path)
            back = ar.read_csv(path)
            self.assertEqual(back[3]['room_c'], self.rows[3]['room_c'])
            with open(path, encoding='utf-8') as fh:
                self.assertEqual(next(csv.reader(fh)), list(rx.COLUMNS))


class Harness(unittest.TestCase):
    def test_replay_harness_runs_and_reproduces_the_engine(self):
        dirs = [Path(os.environ['OT_CJSON_DIR'])] if os.environ.get('OT_CJSON_DIR') else []
        cjson = next((p for p in dirs + [ROOT / '.pio/libdeps/native/cJSON'] if (p / 'cJSON.c').exists()), None)
        gpp = shutil.which('g++')
        if not (cjson and gpp):
            self.skipTest('needs g++ and .pio/libdeps/native/cJSON (pio pkg install -e native)')
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, 'replay')
            subprocess.run([gpp, '-std=c++17', '-O1', f'-I{ROOT / "src"}', f'-I{cjson}',
                            str(ROOT / 'test/learning_replay/replay.cpp'), str(cjson / 'cJSON.c'), '-o', exe], check=True)
            path = os.path.join(d, 'r.csv')
            rx.write_csv(house(hours=60, store=True), path)
            out = json.loads(subprocess.run([exe, path], check=True, capture_output=True, text=True).stdout)
        self.assertEqual({l['variant'] for l in out['learner']} >= {'firmware', 'bridge_hot_water'}, True)
        self.assertTrue(any(v['variant'] == 'firmware' for v in out['flow_demand']))
        self.assertIn('heat_agreement', out['room_engine'])
        firmware = next(l for l in out['learner'] if l['variant'] == 'firmware')
        bridge = next(l for l in out['learner'] if l['variant'] == 'bridge_hot_water')
        # The keep-warm store splits the firmware's periods; the bridge keeps them whole.
        self.assertGreater(firmware['heating_periods'], bridge['heating_periods'])


if __name__ == '__main__':
    unittest.main()
