"""Tests for tools/switchover/shadow_exit.py on synthetic history (no network).

    python3 -I -m unittest discover -s tools/switchover -p "test_*.py" -v
"""
import datetime as dt
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shadow_exit as se  # noqa: E402

UTC = dt.timezone.utc
H, M = 3600, 60
DAY0 = dt.datetime(2026, 11, 2, tzinfo=UTC).timestamp()  # a Monday, 00:00 UTC


def steps(*points):
    return [(DAY0 + t, v) for t, v in points]


def day_of_heating(day, e32_shift_s=0, e32_flow=38.0, extra_e32_cycles=0):
    """One day: setback at 22:00, warm-up at 06:30, heating 06:35-08:00, 17:00-21:30, quiet nights."""
    base = day * 24 * H
    tado = [(base + 6 * H + 35 * M, 45.0), (base + 8 * H, 0.0), (base + 17 * H, 42.0), (base + 21 * H + 30 * M, 0.0)]
    e32 = [(t + e32_shift_s, e32_flow if v else 0.0) for t, v in tado]
    for k in range(extra_e32_cycles):
        start = base + 12 * H + k * H
        e32 += [(start, e32_flow), (start + 10 * M, 0.0)]
    target = [(base + 6 * H + 30 * M, 21.0), (base + 22 * H, 18.5)]
    return tado, sorted(e32), target


def history(days=6, **kw):
    tado, e32, target = [(0, 0.0)], [(0, 0.0)], [(0, 18.5)]
    for d in range(days):
        a, b, c = day_of_heating(d, **kw)
        tado += a; e32 += b; target += c
    end = days * 24 * H
    uptime = [(t, float(t + 3600)) for t in range(0, end, 3 * H)]  # running since an hour before the window
    return {'tado': steps(*tado), 'e32': steps(*sorted(e32)), 'target': steps(*target),
            'uptime': steps(*uptime), 'boiler': steps((0, 55.0)), 'offline': []}, DAY0 + end


class Criteria(unittest.TestCase):
    def test_six_good_days_pass_everything(self):
        h, end = history(e32_shift_s=2 * M)
        result = se.evaluate(h, end, UTC, plan_max=60)
        for name, r in result.items():
            self.assertEqual(r['result'], se.INFO if name == 'comparison' else se.PASS, (name, r))
        self.assertEqual(result['periods']['thermostat_periods'], 12)
        self.assertEqual(result['timing']['median_min'], 2.0)

    def test_one_day_is_not_enough_yet(self):
        h, end = history(days=1)
        result = se.evaluate(h, end, UTC)
        self.assertEqual(result['stable']['result'], se.WAIT)
        self.assertEqual(result['periods']['result'], se.WAIT)
        self.assertEqual(result['cycling']['result'], se.WAIT)
        self.assertIn('2 of 10 periods', result['periods']['why'])

    def test_a_restart_resets_the_stable_clock(self):
        h, end = history()
        h['uptime'] = [(t, v) for t, v in h['uptime'] if t < end - 10 * H]
        h['uptime'] += [(end - 10 * H, 50.0), (end - 1 * H, 9 * 3600 + 50.0)]
        r = se.stability(h['uptime'], end)
        self.assertEqual(r['result'], se.WAIT)
        self.assertEqual(r['restarts_seen'], 1)
        self.assertAlmostEqual(r['hours_since_restart'], 10.0, places=0)

    def test_an_offline_stretch_fails(self):
        h, end = history()
        h['offline'] = [(end - 20 * H, end - 20 * H + 6 * M)]
        self.assertEqual(se.stability(h['uptime'], end, h['offline'])['result'], se.FAIL)
        h['offline'] = [(end - 20 * H, end - 20 * H + 4 * M)]  # a short blip is fine
        self.assertEqual(se.stability(h['uptime'], end, h['offline'])['result'], se.PASS)

    def test_late_e32_fails_timing(self):
        h, end = history(e32_shift_s=20 * M)
        r = se.evaluate(h, end, UTC)['timing']
        self.assertEqual(r['result'], se.FAIL)
        self.assertGreater(r['median_min'], 5)

    def test_flow_judges_only_the_hard_limit(self):
        # Owner, 30 Oct: keep the hard limit and learn; 48 degC under a 55 degC boiler limit passes.
        h, end = history(e32_flow=48.0)
        self.assertEqual(se.evaluate(h, end, UTC, plan_max=60)['flow']['result'], se.PASS)
        h, end = history(e32_flow=58.0)  # above the boiler's own 55 degC
        r = se.evaluate(h, end, UTC, plan_max=60)['flow']
        self.assertEqual(r['result'], se.FAIL)
        self.assertEqual(r['breaches'][0]['limit_c'], 55.0)
        h, end = history(e32_flow=58.0)
        h['boiler'] = []  # unknown boiler limit: the plan maximum applies
        self.assertEqual(se.evaluate(h, end, UTC, plan_max=60)['flow']['result'], se.PASS)
        self.assertEqual(se.evaluate(h, end, UTC, plan_max=50)['flow']['result'], se.FAIL)
        h, end = history(e32_flow=85.0)
        h['boiler'] = []  # nothing known: the 80 degC ceiling
        self.assertEqual(se.evaluate(h, end, UTC)['flow']['result'], se.FAIL)

    def test_a_lowered_boiler_limit_counts_from_its_report_on(self):
        h, end = history(e32_flow=50.0)
        h['boiler'] = steps((0, 55.0), (5 * 24 * H, 45.0))  # lowered on day 6
        r = se.evaluate(h, end, UTC, plan_max=60)['flow']
        self.assertEqual(r['result'], se.FAIL)
        self.assertTrue(all(b['limit_c'] == 45.0 for b in r['breaches']))

    def test_comparison_with_the_thermostat_is_info_only(self):
        h, end = history(e32_flow=38.0)
        r = se.evaluate(h, end, UTC, plan_max=60)['comparison']
        self.assertEqual(r['result'], se.INFO)
        self.assertLess(r['median_c'], 0)  # the thermostat asked 42-45, the E32 38
        self.assertGreater(r['minutes'], 0)

    def test_extra_e32_cycles_fail(self):
        h, end = history(extra_e32_cycles=2)
        r = se.evaluate(h, end, UTC)['cycling']
        self.assertEqual(r['result'], se.FAIL)
        self.assertGreater(r['e32'], r['thermostat'])

    def test_short_drops_merge_into_one_period(self):
        series = steps((0, 40.0), (10 * M, 0.0), (11 * M, 40.0), (30 * M, 0.0))
        self.assertEqual(len(se.periods(series, DAY0 + H)), 1)
        self.assertEqual(len(se.periods(steps((0, 40.0), (10 * M, None), (20 * M, 40.0)), DAY0 + H)), 2)

    def test_unavailable_values_are_not_heat(self):
        self.assertIsNone(se.number('unavailable'))
        self.assertIsNone(se.number('nan'))
        self.assertEqual(se.number('38'), 38.0)

    def test_setbacks_use_local_time(self):
        amsterdam = dt.timezone(dt.timedelta(hours=1))
        targets = steps((21 * H + 30 * M, 21.0), (22 * H, 18.5))  # 23:00 local
        night, morning = se.setbacks(targets, amsterdam)
        self.assertEqual(len(night), 1); self.assertEqual(morning, [])


class Mqtt(unittest.TestCase):
    HELLO = '{"api":1,"boot_id":"c21db5d9","mode":"shadow"}'

    def lines(self, *beats, boots=('c21db5d9',), availability='online'):
        out = [f'   0.0 R ib-therm/v1/fw/availability 6B {availability}']
        out += [f'   0.1 R ib-therm/v1/fw/hello 40B {{"boot_id":"{b}"}}' for b in boots]
        out += [f'{t:6.1f} - ib-therm/v1/fw/heartbeat 120B {{}}' for t in beats]
        return out

    def test_regular_heartbeats_pass(self):
        self.assertEqual(se.mqtt_health(self.lines(1.0, 61.0, 121.0))['result'], se.PASS)

    def test_a_late_heartbeat_fails(self):
        self.assertEqual(se.mqtt_health(self.lines(1.0, 100.0))['result'], se.FAIL)

    def test_offline_or_a_new_boot_fails(self):
        self.assertEqual(se.mqtt_health(self.lines(1.0, 61.0, availability='offline'))['result'], se.FAIL)
        self.assertEqual(se.mqtt_health(self.lines(1.0, 61.0, boots=('a', 'b')))['result'], se.FAIL)

    def test_too_short_a_listen_waits(self):
        self.assertEqual(se.mqtt_health(self.lines(1.0))['result'], se.WAIT)


if __name__ == '__main__':
    unittest.main()
