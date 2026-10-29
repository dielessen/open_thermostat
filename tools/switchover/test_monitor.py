"""Tests for tools/switchover/monitor.py against a mocked E32 (no device, no network beyond 127.0.0.1).

    python3 -I -m unittest discover -s tools/switchover -p "test_*.py" -v

The fixtures follow the real payload shapes: /status/heating as in
test/heating-browser.cjs plus the beta.19 `active` block (ActiveHeatGuard::json,
HeatingController::activeHeatJson: confirmation_stored, boiler_limit),
/status/ems/telemetry field names from ClassicBoilerMonitor.h, and /status/logs
from REST.h systemLogs (BlackBox::json, runtimeHealthJson, MQTT counters).
"""
import copy
import http.server
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor as m  # noqa: E402

PASSWORD = 'correct horse battery staple'
COOKIE = 'ot_session=0123456789abcdef'


# --- fixtures -----------------------------------------------------------------------------------

def heating(mode='active', state='active', temp=20.4, setpoint=21.0, flow=45, warnings=(), limit=60,
            heat=True, starts=2, short=False, rooms=None, confirmation=True):
    send_flow = flow if state in m.OWNING and heat else 0
    return {
        'schema': 1, 'revision': 5, 'mode': mode,
        'request': {'heat': heat, 'flow_c': flow if heat else 0, 'reason': 'heating' if heat else 'satisfied'},
        'ha_entities': ['climate.living_room'],
        'rooms': rooms if rooms is not None else [
            {'id': 'living_room', 'name': 'Living room', 'state': 'active', 'inactive_until': 0, 'fallback_centi_c': 1900,
             'minimum_centi_c': 500, 'maximum_centi_c': 3000, 'status': 'ok', 'source': 'climate.living_room',
             'temperature': temp, 'setpoint': setpoint, 'setpoint_source': 'ha', 'demand': heat},
            {'id': 'bathroom', 'name': 'Bathroom', 'state': 'inactive', 'inactive_until': 0, 'fallback_centi_c': 1900,
             'minimum_centi_c': 500, 'maximum_centi_c': 3000, 'status': 'inactive', 'source': 'a4c138a3e8db',
             'temperature': 18.2, 'setpoint': None, 'setpoint_source': 'fallback', 'demand': False}],
        'ble_sensors': [{'id': 'a4c138a3e8db', 'name': 'Bathroom', 'profile': 'pvvx_thermometer', 'temperature': 18.2,
                         'humidity': 60.1, 'battery': 80, 'age_s': 40}],
        'burner': {'starts_last_hour': starts, 'heating_starts_last_hour': starts, 'short_cycling': short},
        'shadow': {'today': {'day': '2026-11-02', 's': 3600}},
        'active': {'state': state, 'awaiting_confirmation': state == 'awaiting_confirmation',
                   'command': {'send': False, 'flow_c': send_flow, 'why': 'heat_request' if send_flow else state},
                   'last_sent': {'age_s': 20, 'flow_c': send_flow} if state in m.OWNING else None,
                   'foreign_controller': None, 'confirmation': {'age_s': 600} if confirmation else None,
                   'warnings': list(warnings), 'enabled': True, 'confirmation_stored': confirmation,
                   'boiler_limit': {'flow_c': limit, 'age_s': 1200, 'reads': 1}},
        'flow': {'source': 'rule', 'rule_flow_c': flow},
        'ha': {'input_age_s': 12, 'broker_connected': True},
    }


def field(value, unit='degC', state='valid'):
    return {'value': value if state == 'valid' else None, 'unit': unit, 'state': state, 'quality': 'reported',
            'source_type': 24, 'source_address': 8, 'age_ms': 900, 'observed_at_ms': 1000}


def telemetry(flow=44.5, modulation=35, heating_active=True, dhw=False, configured=75):
    return {'protocol_profile': 'ems_classic', 'reception': {'state': 'classic_reports_received'},
            'fields': {'measured_flow_temperature': field(flow), 'measured_return_temperature': field(36.0),
                       'reported_selected_flow_temperature': field(45.0),
                       'reported_burner_modulation': field(modulation, '%'),
                       'heating_active': field(1 if heating_active else 0, 'bool'),
                       'dhw_active': field(1 if dhw else 0, 'bool'), 'measured_dhw_temperature': field(52.0),
                       'pressure': field(1.6, 'bar'), 'outdoor_temperature': field(None, state='unknown'),
                       'configured_heating_temperature': field(configured), 'display_code': field('-H', 'text')},
            'burner_cycles': {'known': True, 'short_cycling': False, 'starts_last_hour': 2},
            'transport': {'enabled': True, 'transmitted_frames': 120, 'invalid_telegrams': 0, 'uart_errors': 0,
                          'uart_resets': 0}}


def logs(boot=1234567, disconnects=0, dropped=0, heap_min=31000, stacks=None, previous=None, records=(), latest=10):
    return {'loop_intervals': {}, 'boot': boot, 'latest': latest, 'oldest': 1, 'records': list(records),
            'previous_boot': {'reset_reason': 1 if previous is None else 3, 'wifi_lost_restarts': 0,
                              'bluetooth_silent_restarts': 0, 'network_dead_restarts': 0, 'previous': previous},
            'runtime': {'free_internal_bytes': 41000, 'minimum_free_internal_bytes': heap_min,
                        'largest_internal_block_bytes': 30000, 'free_psram_bytes': 3_900_000,
                        'stack_minimum_bytes': stacks or {'loop': 3100, 'supervisor': 1500, 'ems_uart': 1800,
                                                          'bluetooth_host': 2200},
                        'mqtt_budget_disconnects': disconnects, 'heating_telemetry_dropped': dropped,
                        'heating_telemetry_failed': 0, 'heating_telemetry_large': 0}}


def plan(maximum=60):
    return {'schema': 1, 'revision': 5, 'mode': 'active', 'minimum_flow_c': 30, 'maximum_flow_c': maximum, 'rooms': []}


# --- mock E32 -----------------------------------------------------------------------------------

class FakeE32:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = []      # (method, path, body)
        self.webhook = []
        self.logged_in = False
        self.down = False
        self.data = {'/status': {'uptime': 3600}, '/status/heating': heating(), '/status/ems/telemetry': telemetry(),
                     '/status/logs': logs(), '/config/heating': plan()}
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, body, headers=()):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                for k, v in headers:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                path = urllib.parse.urlsplit(self.path).path
                with fake.lock:
                    fake.requests.append(('GET', self.path, None))
                    if fake.down:
                        self.close_connection = True
                        self.connection.close()
                        return
                    authed = fake.logged_in and COOKIE in (self.headers.get('Cookie') or '')
                    if not authed:
                        return self.reply(401, {'error': 'unauthorized'})
                    if path == '/auth/session':
                        return self.reply(200, {'authenticated': True, 'csrf': 'c' * 64})
                    if path in fake.data:
                        return self.reply(200, copy.deepcopy(fake.data[path]))
                    return self.reply(404, {'error': 'not_found'})

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode()
                with fake.lock:
                    fake.requests.append(('POST', self.path, body))
                    if self.path.startswith('/api/webhook/'):
                        fake.webhook.append(json.loads(body))
                        return self.reply(200, {})
                    if self.path == '/auth/login':
                        form = urllib.parse.parse_qs(body)
                        if form.get('username') == ['admin'] and form.get('password') == [PASSWORD]:
                            fake.logged_in = True
                            return self.reply(200, {'ok': True}, [('Set-Cookie', COOKIE + '; HttpOnly; Path=/')])
                        return self.reply(401, {'error': 'invalid_credentials'})
                    return self.reply(405, {'error': 'method_not_allowed'})

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def set(self, path, value):
        with self.lock:
            self.data[path] = value

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Clock:
    def __init__(self, start=1_793_000_000.0):  # a weekday in November 2026, noon-ish UTC
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# --- tests --------------------------------------------------------------------------------------

class Base(unittest.TestCase):
    def setUp(self):
        self.e32 = FakeE32()
        self.addCleanup(self.e32.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.stream = io.StringIO()
        self.clock = Clock()
        self.make()

    def make(self, notifier=None, thresholds=None, mqtt=None):
        self.client = m.E32Client(self.e32.url, 'admin', PASSWORD, timeout=5, clock=self.clock)
        self.output = m.Output(self.out, notifier, self.stream)
        self.monitor = m.Monitor(self.client, self.output, thresholds or m.Thresholds(), 60, mqtt, self.clock)

    def step(self, n=1, seconds=60):
        sample = None
        for _ in range(n):
            sample = self.monitor.poll()
            self.clock.advance(seconds)
        return sample

    def alarms(self, event='raised'):
        path = self.out / 'alarms.jsonl'
        rows = [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
        return [r for r in rows if event is None or r['event'] == event]

    def keys(self, event='raised'):
        return [r['key'] for r in self.alarms(event)]

    def files_text(self):
        return ''.join(p.read_text(encoding='utf-8') for p in self.out.iterdir()) + self.stream.getvalue()


class SessionAndReadOnly(Base):
    def test_logs_in_once_and_only_reads(self):
        self.step(3)
        posts = [r for r in self.e32.requests if r[0] == 'POST']
        self.assertEqual([p[1] for p in posts], ['/auth/login'])
        self.assertTrue(all(r[0] == 'GET' for r in self.e32.requests if r not in posts))
        paths = {urllib.parse.urlsplit(r[1]).path for r in self.e32.requests}
        self.assertEqual(paths, {'/status/heating', '/auth/login', '/auth/session', '/status', '/status/ems/telemetry',
                                 '/status/logs', '/config/heating'})

    def test_password_never_written(self):
        self.step(2)
        encoded = urllib.parse.quote_plus(PASSWORD)
        self.assertIn(encoded, self.e32.requests[1][2])   # it did go to the E32 ...
        for form in (PASSWORD, encoded):                  # ... and nowhere else
            self.assertNotIn(form, self.files_text())
        self.assertNotIn(COOKIE.split('=')[1], self.files_text())

    def test_client_refuses_writes(self):
        with self.assertRaises(AssertionError):
            self.client._open('POST', '/config/heating/handover', b'{}', 'application/json')
        with self.assertRaises(AssertionError):
            self.client._open('POST', '/config/heating', b'{}', 'application/json')

    def test_relogin_after_session_loss_is_rate_limited(self):
        self.step()
        self.e32.logged_in = False           # E32 restart: sessions are RAM only
        self.clock.advance(200)
        self.assertIsNotNone(self.step())    # one new login
        self.assertEqual(self.client.logins, 2)
        self.e32.logged_in = False
        self.assertIsNone(self.step())       # within 120 s: no new login attempt
        self.assertEqual(self.client.logins, 2)

    def test_wrong_password_is_reported(self):
        client = m.E32Client(self.e32.url, 'admin', 'wrong', timeout=5, clock=self.clock)
        with self.assertRaises(m.AuthError):
            client.login()

    def test_password_not_accepted_on_command_line(self):
        with self.assertRaises(SystemExit), mock.patch('sys.stderr', io.StringIO()):
            m.parse_args(['--host', 'http://e32', '--password', 'x'])

    def test_password_from_env_or_prompt(self):
        with mock.patch.dict(os.environ, {m.PASSWORD_ENV: 'from-env'}):
            self.assertEqual(m.read_password(m.PASSWORD_ENV, 'p: '), 'from-env')
        tty = mock.Mock(isatty=lambda: True)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(m.read_password(m.PASSWORD_ENV, 'p: ', tty, lambda prompt: 'typed'), 'typed')
            with self.assertRaises(SystemExit):
                m.read_password(m.PASSWORD_ENV, 'p: ', mock.Mock(isatty=lambda: False))

    def test_interval_and_host_validation(self):
        with mock.patch('sys.stderr', io.StringIO()):
            for argv in (['--host', 'http://e32', '--interval', '10'], ['--host', 'http://e32', '--interval', '120']):
                with self.assertRaises(SystemExit):
                    m.parse_args(argv)
        self.assertEqual(m.parse_args(['--host', 'http://e32', '--interval', '30']).interval, 30)
        with self.assertRaises(ValueError):
            m.E32Client('http://e32/status', 'admin', 'x')


class SampleContents(Base):
    def test_sample_has_all_fields(self):
        self.e32.set('/status/logs', logs(records=[{'sequence': 9, 'uptime_ms': 5, 'level': 2, 'source': 'esp',
                                                    'feature': 'mqtt', 'message': 'write budget exceeded'},
                                                   {'sequence': 10, 'uptime_ms': 6, 'level': 3, 'source': 'esp',
                                                    'feature': 'x', 'message': 'info only'}]))
        s = self.step()
        self.assertEqual(s['rooms'][0]['temperature'], 20.4)
        self.assertEqual(s['rooms'][0]['setpoint'], 21.0)
        self.assertEqual(s['request'], {'heat': True, 'flow_c': 45, 'reason': 'heating'})
        self.assertEqual(s['guard']['state'], 'active')
        self.assertEqual(s['guard']['command']['flow_c'], 45)
        self.assertTrue(s['guard']['confirmed'])
        self.assertTrue(s['guard']['confirmation_stored'])
        self.assertEqual(s['boiler_limit']['flow_c'], 60)
        self.assertEqual(s['boiler']['flow_c'], 44.5)
        self.assertEqual(s['boiler']['modulation_pct'], 35)
        self.assertTrue(s['boiler']['burner_on'])
        self.assertIs(s['boiler']['heating_active'], True)
        self.assertIs(s['boiler']['dhw_active'], False)
        self.assertIsNone(s['boiler']['outdoor_c'])          # unknown field: no value
        self.assertEqual(s['burner']['heating_starts_last_hour'], 2)
        self.assertEqual(s['e32']['uptime_s'], 3600)
        self.assertEqual(s['e32']['reset_reason_name'], 'power_on')
        self.assertEqual(s['runtime']['minimum_free_internal_bytes'], 31000)
        self.assertEqual(s['runtime']['stack_minimum_bytes']['ems_uart'], 1800)
        self.assertEqual(s['mqtt_health']['mqtt_budget_disconnects'], 0)
        self.assertEqual([r['message'] for r in s['log_records']], ['write budget exceeded'])
        self.assertEqual(self.monitor.log_cursor, 10)
        lines = (self.out / f'samples-{m.local_day(self.clock.now - 60)}.jsonl').read_text(encoding='utf-8').splitlines()
        self.assertEqual(json.loads(lines[0])['guard']['state'], 'active')
        self.assertEqual(self.keys(), [])

    def test_beta18_shape_without_new_fields(self):
        h = heating()
        for key in ('confirmation_stored', 'boiler_limit', 'awaiting_confirmation'):
            h['active'].pop(key)
        self.e32.set('/status/heating', h)
        s = self.step()
        self.assertIsNone(s['boiler_limit']['flow_c'])
        self.assertEqual(s['boiler_limit']['configured_heating_temperature_c'], 75)
        self.assertEqual(m.flow_limit(s), 60)  # plan maximum

    def test_log_cursor_restarts_after_reboot(self):
        self.monitor.log_cursor = 500
        self.e32.set('/status/logs', logs(latest=3))
        self.step()
        self.assertEqual(self.monitor.log_cursor, 0)


class Alarms(Base):
    def test_no_heat_request_after_hold(self):
        self.e32.set('/status/heating', heating(temp=19.8, setpoint=21.0, heat=False))
        self.step(20)
        self.assertNotIn('no_heat_request', self.keys())
        self.step(2)
        self.assertIn('no_heat_request', self.keys())
        self.e32.set('/status/heating', heating(temp=19.8, setpoint=21.0, heat=True))
        self.step()
        self.assertIn('no_heat_request', self.keys('cleared'))

    def test_no_heat_in_shadow_uses_calculated_request(self):
        self.e32.set('/status/heating', heating(mode='shadow', state='shadow', temp=19.8, heat=True))
        self.step(25)
        self.assertNotIn('no_heat_request', self.keys())

    def test_request_above_limit_immediate(self):
        self.e32.set('/status/heating', heating(flow=58, limit=55))
        self.step()
        self.assertIn('request_above_limit', self.keys())

    def test_plan_maximum_is_a_limit(self):
        self.e32.set('/config/heating', plan(maximum=45))
        self.e32.set('/status/heating', heating(flow=50))
        self.step()
        self.assertIn('request_above_limit', self.keys())

    def test_measured_flow_above_limit_needs_two_samples_and_no_dhw(self):
        self.e32.set('/status/ems/telemetry', telemetry(flow=66, dhw=True))
        self.step(3)
        self.assertNotIn('flow_above_limit', self.keys())
        self.e32.set('/status/ems/telemetry', telemetry(flow=66))
        self.step()
        self.assertNotIn('flow_above_limit', self.keys())
        self.step()
        self.assertIn('flow_above_limit', self.keys())

    def test_short_cycling(self):
        self.e32.set('/status/heating', heating(starts=7))
        self.step()
        self.assertIn('short_cycling', self.keys())
        self.e32.set('/status/heating', heating(starts=1, short=True))
        self.step()
        self.assertNotIn('short_cycling', self.keys('cleared'))
        self.e32.set('/status/heating', heating(starts=1))
        self.step()
        self.assertIn('short_cycling', self.keys('cleared'))

    def test_room_too_cold_and_too_warm(self):
        self.e32.set('/status/heating', heating(temp=19.5, setpoint=21.0))
        self.step(29)
        self.assertNotIn('room_cold_living_room', self.keys())
        self.step(2)
        self.assertIn('room_cold_living_room', self.keys())
        self.e32.set('/status/heating', heating(temp=22.8, setpoint=21.0))  # still heating: 5 min
        self.step(7)
        self.assertIn('room_warm_living_room', self.keys())
        self.assertIn('room_cold_living_room', self.keys('cleared'))

    def test_guard_stopping_and_warnings(self):
        self.step(2)
        self.e32.set('/status/heating', heating(state='stopped_measurement_lost', warnings=['measurement_lost']))
        self.step()
        self.assertIn('guard_stopped', self.keys())
        self.assertIn('warning_measurement_lost', self.keys())
        self.e32.set('/status/heating', heating())
        self.step()
        self.assertEqual(sorted(self.keys('cleared')), ['guard_stopped', 'warning_measurement_lost'])

    def test_foreign_controller(self):
        self.step()
        self.e32.set('/status/heating', heating(state='blocked_foreign_controller', warnings=['foreign_controller'],
                                                confirmation=False))
        self.step()
        self.assertIn('guard_stopped', self.keys())
        self.assertIn('warning_foreign_controller', self.keys())

    def test_hand_back_is_info_not_guard_alarm(self):
        self.step()
        self.e32.set('/status/heating', heating(mode='shadow', state='stopping', heat=False, confirmation=False))
        self.step()
        self.assertIn('handed_back', self.keys())
        self.assertNotIn('guard_stopped', self.keys())

    def test_awaiting_confirmation(self):
        self.e32.set('/status/heating', heating(state='awaiting_confirmation', confirmation=False))
        self.step(2)
        self.assertNotIn('awaiting_confirmation', self.keys())
        self.step()
        self.assertIn('awaiting_confirmation', self.keys())

    def test_frost_not_protected(self):
        h = heating(heat=False, temp=21.5, setpoint=21.0)
        h['rooms'][1]['temperature'] = 7.4
        self.e32.set('/status/heating', h)
        self.step(4)
        self.assertIn('frost_not_protected', self.keys())

    def test_unreachable_and_back(self):
        self.step()
        self.e32.down = True
        self.step(3)
        self.assertNotIn('e32_unreachable', self.keys())
        self.step()
        self.assertIn('e32_unreachable', self.keys())
        self.e32.down = False
        self.step()
        self.assertIn('e32_back', self.keys())
        self.assertIn('e32_unreachable', self.keys('cleared'))

    def test_restart_detected_with_reason(self):
        self.step()
        self.e32.set('/status', {'uptime': 40})
        self.e32.set('/status/logs', logs(boot=999, previous={'uptime_s': 7200, 'supervisor_restart': 'none',
                                                              'loop_phase': 'controller'}))
        self.step()
        restart = [a for a in self.alarms() if a['key'] == 'e32_restarted']
        self.assertEqual(len(restart), 1)
        self.assertEqual(restart[0]['reset_reason'], 'software')
        self.assertEqual(restart[0]['previous_boot']['uptime_s'], 7200)

    def test_restart_detected_across_an_outage(self):
        self.step()
        self.e32.down = True
        self.step(4)
        self.e32.down = False
        self.e32.logged_in = False
        self.e32.set('/status', {'uptime': 90})
        self.e32.set('/status/logs', logs(boot=4242))
        self.step()
        self.assertIn('e32_restarted', self.keys())

    def test_heap_minimum_below_20000(self):  # the owner's device: 13280 B
        self.e32.set('/status/logs', logs(heap_min=13280))
        self.step()
        heap = [a for a in self.alarms() if a['key'] == 'heap_low']
        self.assertEqual(len(heap), 1)
        self.assertEqual(heap[0]['severity'], 'warning')
        self.assertIn('13280', heap[0]['message'])

    def test_stack_low(self):
        self.e32.set('/status/logs', logs(stacks={'loop': 300, 'supervisor': 1500, 'ems_uart': 0, 'bluetooth_host': 2000}))
        self.step()
        self.assertIn('stack_low', self.keys())

    def test_mqtt_disconnects(self):  # the owner's device: 4 in 17 minutes
        self.step()
        for total in (1, 2, 3, 4):
            self.e32.set('/status/logs', logs(disconnects=total))
            self.step(seconds=4 * 60)
        events = [a for a in self.alarms(None) if a['key'] == 'mqtt_budget_disconnects']
        self.assertEqual([e['event'] for e in events], ['raised', 'logged', 'logged', 'logged'])
        self.assertEqual([e['total'] for e in events], [1, 2, 3, 4])
        self.clock.advance(3600)
        self.e32.set('/status/logs', logs(disconnects=5))
        self.step()
        self.assertEqual(self.keys().count('mqtt_budget_disconnects'), 2)  # raised again after the repeat window

    def test_mqtt_disconnects_already_at_start(self):
        self.e32.set('/status/logs', logs(disconnects=4, dropped=1))
        self.step()
        self.assertIn('mqtt_budget_disconnects', self.keys())
        self.assertIn('heating_telemetry_dropped', self.keys())

    def test_counters_reset_by_restart_are_not_negative(self):
        self.e32.set('/status/logs', logs(disconnects=4))
        self.step()
        self.e32.set('/status/logs', logs(boot=77, disconnects=0))
        self.step()
        self.assertEqual(self.keys().count('mqtt_budget_disconnects'), 1)

    def test_standing_alarm_repeats_hourly(self):
        self.e32.set('/status/heating', heating(flow=58, limit=55))
        self.step(61)
        self.assertEqual(self.keys().count('request_above_limit'), 1)
        self.assertEqual(self.keys('repeat').count('request_above_limit'), 1)


class Notification(Base):
    def test_webhook_gets_alarms_but_never_logs_its_url(self):
        url = self.e32.url + '/api/webhook/secret-id-123'
        self.make(notifier=m.Notifier(url))
        self.e32.set('/status/heating', heating(flow=58, limit=55))
        self.step()
        self.e32.set('/status/logs', logs(disconnects=2))
        self.step()
        keys = [w['key'] for w in self.e32.webhook]
        self.assertIn('request_above_limit', keys)
        self.assertIn('mqtt_budget_disconnects', keys)
        self.assertTrue(all(w['message'] and w['severity'] for w in self.e32.webhook))
        self.assertNotIn('secret-id-123', self.files_text())

    def test_webhook_failure_does_not_stop_the_monitor(self):
        notifier = m.Notifier('http://127.0.0.1:9/api/webhook/x', timeout=1)
        self.make(notifier=notifier)
        self.e32.set('/status/heating', heating(flow=58, limit=55))
        self.assertIsNotNone(self.step())
        self.assertEqual(notifier.failures, 1)
        self.assertIn('notify failed', self.stream.getvalue())


class Summary(Base):
    def test_daily_summary_written_at_day_change(self):
        self.e32.set('/status/logs', logs(heap_min=25000, disconnects=1))
        self.step(3)
        first_day = m.local_day(self.clock.now)
        self.clock.advance(24 * 3600)
        self.step()
        path = self.out / f'summary-{first_day}.json'
        self.assertTrue(path.exists())
        summary = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(summary['samples'], 3)
        self.assertEqual(summary['guard_states'], {'active': 1.0})
        self.assertEqual(summary['heat_request_share'], 1.0)
        self.assertEqual(summary['minimum_free_internal_bytes'], 25000)
        self.assertEqual(summary['mqtt_budget_disconnects'], {'first': 1, 'last': 1})
        self.assertEqual(summary['rooms']['living_room']['mean_deviation_c'], -0.6)
        self.assertEqual(summary['flow_while_heating_c']['max'], 44.5)
        self.assertEqual(summary['boiler_limits_c'], [60])

    def test_run_writes_summary_on_exit(self):
        sleeps = []

        def sleep(s):
            sleeps.append(s)
            self.clock.advance(s)
        self.monitor.run(duration_s=300, sleep=sleep)
        self.assertEqual(len(sleeps), 5)
        self.assertTrue(all(55 <= s <= 60 for s in sleeps))
        self.assertTrue(list(self.out.glob('summary-*.json')))
        self.assertIn('summary:', self.stream.getvalue())


class Mqtt(Base):
    def test_without_paho_http_only(self):
        feed = m.MqttFeed(self.clock)
        with mock.patch.dict(sys.modules, {'paho': None, 'paho.mqtt': None, 'paho.mqtt.client': None}):
            self.assertFalse(feed.start('broker', 1883, None, None, 'ib-therm'))

    def test_mqtt_heating_used_when_http_is_down(self):
        feed = m.MqttFeed(self.clock)
        feed.connected = True
        self.make(mqtt=feed)
        self.step()
        self.e32.down = True
        compact = heating(temp=20.9)
        feed.on_payload('ib-therm/v1/fw/telemetry/heating', json.dumps(compact).encode())
        s = self.step()
        self.assertEqual(s['heating_source'], 'mqtt')
        self.assertFalse(s['reachable'])
        self.assertEqual(s['rooms'][0]['temperature'], 20.9)
        self.assertEqual(s['mqtt']['heating_age_s'], 0)

    def test_mqtt_silent(self):
        feed = m.MqttFeed(self.clock)
        self.make(mqtt=feed)
        self.step(6)
        self.assertIn('mqtt_silent', self.keys())
        feed.on_payload('ib-therm/v1/fw/telemetry/heating', b'not json')
        feed.on_payload('ib-therm/v1/fw/telemetry/heating', json.dumps(heating()).encode())
        self.step()
        self.assertIn('mqtt_silent', self.keys('cleared'))


if __name__ == '__main__':
    unittest.main()
