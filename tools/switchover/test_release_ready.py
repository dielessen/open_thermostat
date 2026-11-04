"""Tests for tools/switchover/release_ready.py and record_test.py on synthetic data (no network).

    python3 -I -m unittest discover -s tools/switchover -p "test_*.py" -v
"""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_test as rt  # noqa: E402
import release_ready as rr  # noqa: E402

H, D = 3600, 86400
T0 = dt.datetime(2026, 11, 3, 14, tzinfo=dt.timezone.utc).timestamp()  # the attended switch-over


def uptime(start, end, restarts=()):
    """Hourly uptime samples; each restart drops it, with an 'unavailable' sample in between."""
    out, boot = [], start - 600
    for t in range(int(start), int(end), H):
        for r in restarts:
            if t - H < r <= t:
                out.append((r - 30, None))
                boot = r
        out.append((t, float(t - boot)))
    return out


def full_session(result='pass'):
    session = rt.new_session('2026-11-03', 'v0.1.0-e32v2-beta.22', '0.4.0b14')
    at = dt.datetime(2026, 11, 3, 15, tzinfo=dt.timezone.utc)
    for test_id, _, alt in rt.TESTS:
        if test_id == 'T12':
            rt.add_entry(session, test_id, 'alternative', 'not cold enough', evidence='soak frost green', at=at)
        else:
            rt.add_entry(session, test_id, result, 'as expected', at=at)
    return session


def ha_receipt(tag='v0.1.0-e32v2-beta.22'):
    return ('docs/modern-thermostat/update-acceptance/e32-beta22-20261031.json',
            {'schema': 1, 'status': 'PASS', 'tag': tag, 'method': 'home_assistant'})


def install(followed=True, problems=()):
    return {'schema': 1, 'kind': 'install_test', 'date': '2026-11-20', 'followed_to_end': followed,
            'problems': [dict(p) for p in problems]}


class Spans(unittest.TestCase):
    def test_short_unavailability_keeps_the_span_a_long_one_ends_it(self):
        end = T0 + 20 * D
        series = [(T0, True), (T0 + 2 * D, None), (T0 + 2 * D + 30 * 60, True)]
        self.assertEqual(rr.spans(series, end), [(T0, end)])
        series = [(T0, True), (T0 + 2 * D, None), (T0 + 2 * D + 3 * H, True)]
        self.assertEqual(rr.spans(series, end), [(T0, T0 + 2 * D), (T0 + 2 * D + 3 * H, end)])

    def test_a_hand_back_restarts_the_14_days(self):
        end = T0 + 20 * D
        series = [(T0, True), (T0 + 10 * D, False), (T0 + 11 * D, True)]
        r = rr.active_control(series, end)
        self.assertEqual(r['result'], rr.WAIT)
        self.assertEqual(r['interruptions'], 1)
        self.assertAlmostEqual(r['current_hours'], 9 * 24, places=0)
        self.assertEqual(rr.active_control([(T0, True)], T0 + 14 * D)['result'], rr.PASS)
        self.assertEqual(rr.active_control([], T0)['result'], rr.WAIT)


class Criteria(unittest.TestCase):
    def history(self, end, restarts=(), planned=(), trv=None):
        return {'uptime': uptime(T0 - D, end, restarts), 'offline': [], 'planned': list(planned),
                'output': [(T0, True)], 'trv': trv if trv is not None else {'switch.slaapkamer_valve_control': [(T0, True)]}}

    def repo(self, **kw):
        base = {'sessions': [full_session()], 'receipts': [ha_receipt()], 'installs': [install()]}
        base.update(kw)
        return base

    def test_everything_met_after_14_days_passes(self):
        end = T0 + 15 * D
        overall, out = rr.evaluate(self.history(end), end, self.repo())
        self.assertEqual(overall, rr.PASS, {k: v['why'] for k, v in out.items()})

    def test_before_14_days_it_waits(self):
        end = T0 + 5 * D
        overall, out = rr.evaluate(self.history(end), end, self.repo())
        self.assertEqual(overall, rr.WAIT)
        self.assertEqual(out['active_control']['result'], rr.WAIT)

    def test_an_unexpected_restart_resets_stability_a_planned_one_does_not(self):
        end = T0 + 15 * D
        crash = T0 + 8 * D
        _, out = rr.evaluate(self.history(end, restarts=[crash]), end, self.repo())
        self.assertEqual(out['stability']['result'], rr.WAIT)
        _, out = rr.evaluate(self.history(end, restarts=[crash], planned=[crash - 60]), end, self.repo())
        self.assertEqual(out['stability']['result'], rr.PASS)

    def test_no_valve_control_yet_waits(self):
        end = T0 + 15 * D
        overall, out = rr.evaluate(self.history(end, trv={}), end, self.repo())
        self.assertEqual(out['trv_control']['result'], rr.WAIT)
        self.assertEqual(overall, rr.WAIT)

    def test_a_failed_attended_test_fails_and_a_later_pass_counts(self):
        session = full_session()
        rt.add_entry(session, 'T7', 'fail', 'adapter kept burning', at=dt.datetime(2026, 11, 3, 16, tzinfo=dt.timezone.utc))
        r = rr.failure_tests([session])
        self.assertEqual((r['result'], r['tests']['T7']['result']), (rr.FAIL, 'fail'))
        rt.add_entry(session, 'T7', 'pass', 'measured again', at=dt.datetime(2026, 11, 4, 16, tzinfo=dt.timezone.utc))
        self.assertEqual(rr.failure_tests([session])['result'], rr.PASS)

    def test_open_tests_wait_and_an_alternative_needs_permission_and_evidence(self):
        session = rt.new_session('2026-11-03', 'v', 'h')
        self.assertEqual(rr.failure_tests([session])['result'], rr.WAIT)
        with self.assertRaises(ValueError):
            rt.add_entry(session, 'T1', 'alternative', 'x', evidence='y')  # T1 has no alternative proof
        with self.assertRaises(ValueError):
            rt.add_entry(session, 'T12', 'alternative', 'x')  # needs evidence
        forged = full_session()
        forged['tests'][0]['entries'][-1]['result'] = 'alternative'  # edited by hand, no permission
        self.assertEqual(rr.failure_tests([forged])['result'], rr.FAIL)

    def test_updates_need_an_accepted_home_assistant_receipt(self):
        self.assertEqual(rr.updates([ha_receipt()])['result'], rr.PASS)
        native = ('x.json', {'status': 'PASS', 'tag': 'v0.1.0-e32v2-beta.4', 'method': 'native_github'})
        incomplete = ('y.json', {'status': 'INCOMPLETE', 'tag': 'v0.1.0-e32v2-beta.19', 'method': 'home_assistant'})
        self.assertEqual(rr.updates([native, incomplete])['result'], rr.WAIT)

    def test_install_guide(self):
        self.assertEqual(rr.install_guide([])['result'], rr.WAIT)
        self.assertEqual(rr.install_guide([install(followed=False)])['result'], rr.FAIL)
        open_problem = install(problems=[{'text': 'step 4 unclear', 'resolved': False}])
        self.assertEqual(rr.install_guide([open_problem])['result'], rr.WAIT)
        fixed = install(problems=[{'text': 'step 4 unclear', 'resolved': True, 'fixed_in': 'abc'}])
        self.assertEqual(rr.install_guide([fixed])['result'], rr.PASS)


class ReleaseWindow(unittest.TestCase):
    """R5-09: the 14 days are about one release. An install inside the window, or days on an earlier or later
    candidate, make a report about "rc.4" untrue."""
    RELEASE, EARLIER = 'v1.0.0-e32v2-rc.4', 'v1.0.0-e32v2-rc.3'

    def history(self, end, installed, restarts=()):
        return {'uptime': uptime(T0 - D, end, restarts), 'offline': [], 'planned': [], 'output': [(T0, True)],
                'trv': {'switch.slaapkamer_valve_control': [(T0, True)]}, 'installed': installed}

    def repo(self):
        return {'sessions': [full_session()], 'receipts': [ha_receipt()], 'installs': [install()]}

    def test_the_whole_window_on_the_release_passes_in_the_final_stage(self):
        end = T0 + 15 * D
        installed = [(T0 - D, self.RELEASE), (T0 + 5 * D, self.RELEASE)]
        overall, out = rr.evaluate(self.history(end, installed), end, self.repo(), release=self.RELEASE, stage='final')
        self.assertEqual(out[rr.WINDOW]['result'], rr.PASS)
        self.assertEqual(out[rr.WINDOW]['versions'], [self.RELEASE])
        self.assertEqual(overall, rr.PASS, {k: v['why'] for k, v in out.items()})

    def test_days_on_the_earlier_candidate_make_the_final_report_fail(self):
        end = T0 + 15 * D
        installed = [(T0 - D, self.EARLIER), (T0 + 3 * D, self.RELEASE)]  # installed after three days of the window
        overall, out = rr.evaluate(self.history(end, installed, restarts=[T0 + 3 * D]), end, self.repo(),
                                   release=self.RELEASE, stage='final')
        self.assertEqual(out[rr.WINDOW]['result'], rr.FAIL)
        self.assertIn('start it after the install', out[rr.WINDOW]['why'])
        self.assertEqual(overall, rr.FAIL)
        # The same days are fine for the candidate stage: that report is not the 14-day proof.
        overall, out = rr.evaluate(self.history(end, installed, restarts=[T0 + 3 * D]), end, self.repo(),
                                   release=self.RELEASE, stage='candidate')
        self.assertNotEqual(overall, rr.FAIL)

    def test_a_later_candidate_in_the_window_fails_too(self):
        end = T0 + 15 * D
        installed = [(T0 - D, self.RELEASE), (T0 + 10 * D, 'v1.0.0-e32v2-rc.5')]
        _, out = rr.evaluate(self.history(end, installed), end, self.repo(), release=self.RELEASE, stage='final')
        self.assertEqual(out[rr.WINDOW]['result'], rr.FAIL)
        self.assertEqual(out[rr.WINDOW]['versions'], [self.RELEASE, 'v1.0.0-e32v2-rc.5'])

    def test_another_release_only_or_no_history_cannot_be_tied_to_the_release(self):
        end = T0 + 15 * D
        _, out = rr.evaluate(self.history(end, [(T0, self.EARLIER)]), end, self.repo(), release=self.RELEASE, stage='final')
        self.assertEqual(out[rr.WINDOW]['result'], rr.FAIL)
        self.assertIn('never showed', out[rr.WINDOW]['why'])
        overall, out = rr.evaluate(self.history(end, []), end, self.repo(), release=self.RELEASE, stage='final')
        self.assertEqual(out[rr.WINDOW]['result'], rr.WAIT)
        self.assertNotEqual(overall, rr.PASS)

    def test_without_a_release_the_criterion_is_not_added(self):
        end = T0 + 15 * D
        _, out = rr.evaluate(self.history(end, []), end, self.repo())
        self.assertNotIn(rr.WINDOW, out)

    def test_the_report_carries_the_versions_the_gate_checks(self):
        start = dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc)
        end = start + dt.timedelta(days=15)
        criteria = {c: {'result': rr.PASS} for c in rr.CRITERIA}
        criteria[rr.WINDOW] = rr.release_window([(0, self.RELEASE)], self.RELEASE)
        doc = rr.report(self.RELEASE, 'final', start, end, {}, rr.PASS, criteria)
        self.assertEqual(doc['installed_versions'], [self.RELEASE])
        self.assertIsNone(rr.report(self.RELEASE, 'final', start, end, {}, rr.PASS,
                                    {c: {'result': rr.PASS} for c in rr.CRITERIA})['installed_versions'])

    def test_the_history_of_the_update_entity_becomes_the_installed_versions(self):
        class Entity:
            def get(self, path):
                return [{'entity_id': 'sensor.x_device_uptime'}, {'entity_id': 'update.e32_firmware'},
                        {'entity_id': 'climate.x', 'attributes': {'boiler_output_enabled': True}}]

            def history(self, ids, start, end, minimal):
                rows = {'update.e32_firmware': [
                    {'last_changed': '2026-11-01T10:00:00+00:00', 'attributes': {'installed_version': 'v1.0.0-e32v2-rc.3'}},
                    {'last_changed': '2026-11-04T10:00:00+00:00', 'attributes': {'installed_version': self.release}},
                    {'last_changed': '2026-11-05T10:00:00+00:00', 'attributes': {}}]}
                return {i: rows.get(i, []) for i in ids}

        entity = Entity()
        entity.release = self.RELEASE

        class Args:
            uptime = output_entity = update_entity = None
            trv_entity = []
            trv_suffix = '_valve_control'
        start = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
        _, history = rr.load_history(entity, Args(), start, start + dt.timedelta(days=15))
        self.assertEqual([v for _, v in history['installed']], ['v1.0.0-e32v2-rc.3', self.RELEASE])
        self.assertEqual(len(history['planned']), 1)


class Repository(unittest.TestCase):
    def test_record_test_and_read_repo_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(rt.main(['--root', temp, '--date', '2026-11-03', 'init', '--firmware', 'v0.1.0-e32v2-beta.22', '--ha', '0.4.0b14']), 0)
            self.assertEqual(rt.main(['--root', temp, '--date', '2026-11-03', 'T1', 'pass', 'flow up 5 degC in 9 min']), 0)
            with self.assertRaises(SystemExit):
                rt.main(['--root', temp, '--date', '2026-11-03', 'init', '--firmware', 'x', '--ha', 'y'])  # never overwritten
            self.assertEqual(rt.main(['--root', temp, '--date', '2026-11-20', 'install', '--followed', 'yes', '--problem', 'step 4']), 0)
            self.assertEqual(rt.main(['--root', temp, '--date', '2026-11-20', 'install', '--resolve', '1', '--fixed-in', 'abc']), 0)
            receipts = root / rr.DOCS / 'update-acceptance'
            receipts.mkdir(parents=True)
            (receipts / 'e32-beta22-20261031.json').write_text(json.dumps(ha_receipt()[1]))
            (receipts / 'e32-beta19-20261030-postinstall-capture.json').write_text(json.dumps({'kind': 'capture'}))
            repo = rr.read_repo(root)
            self.assertEqual(len(repo['sessions']), 1)
            self.assertEqual([r['tag'] for _, r in repo['receipts']], ['v0.1.0-e32v2-beta.22'])
            self.assertEqual(rr.install_guide(repo['installs'])['result'], rr.PASS)
            r = rr.failure_tests(repo['sessions'])
            self.assertEqual((r['result'], r['tests']['T1']['result'], r['tests']['T2']['result']), (rr.WAIT, 'pass', 'open'))
            raw = (root / rr.DOCS / 'OVERSCHAKELING-RESULTATEN-2026-11-03.json').read_bytes()
            self.assertNotIn(b'\r\n', raw)

    def test_report_shape_for_the_gate(self):
        start = dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc)
        end = start + dt.timedelta(days=15)
        doc = rr.report('v1.0.0-e32v2-rc.1', 'final', start, end, {}, rr.PASS, {c: {'result': rr.PASS} for c in rr.CRITERIA})
        self.assertEqual((doc['kind'], doc['stage'], doc['from'], doc['to']),
                         ('release_readiness', 'final', '2026-11-03T00:00:00Z', '2026-11-18T00:00:00Z'))


if __name__ == '__main__':
    unittest.main()
