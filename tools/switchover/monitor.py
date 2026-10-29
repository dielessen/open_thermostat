#!/usr/bin/env python3
"""Read-only live monitor for the first 48 hours after the attended switch-over.

    OT_E32_PASSWORD=... python3 -I tools/switchover/monitor.py --host http://192.168.1.50
    python3 -I tools/switchover/monitor.py --host http://e32.local --interval 30 --duration-h 48 \\
        --notify-url https://ha.local:8123/api/webhook/<id>          # or OT_NOTIFY_URL
    python3 -I tools/switchover/monitor.py --host http://e32.local --once  # one sample, print it

Polls the E32 every 30-60 s (GET /status, /status/heating, /status/ems/telemetry,
/status/logs and, every 10th sample, /config/heating), optionally listens to
its MQTT telemetry (only when paho-mqtt is installed and --mqtt-host is given),
writes one JSONL line per sample, raises alarms on stdout and to an optional
Home Assistant webhook, and writes a summary per day.

Read-only by construction: the client sends only GET requests, plus POST
/auth/login to open a session. It never changes settings, the room plan, the
handover or the boiler. Passwords come only from environment variables or an
interactive prompt and are never written anywhere. Python 3 standard library only.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import getpass
import http.client
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = 1
NETWORK_ERRORS = (OSError, http.client.HTTPException)  # URLError, timeouts, resets, bad status lines
RESPONSE_LIMIT = 1 << 20
CEILING_C = 80  # ActiveHeatGuard::hardMaximumFlowC (FlowDemand::ceilingC)
FROST_ON_C = 8.0
HEAP_MINIMUM_WARN = 20000  # bytes, minimum free internal heap since boot
STACK_MINIMUM_WARN = 512
STACK_TASKS = ('loop', 'supervisor', 'ems_uart', 'bluetooth_host')
# esp_reset_reason_t
RESET_REASONS = {0: 'unknown', 1: 'power_on', 2: 'external_pin', 3: 'software', 4: 'panic', 5: 'interrupt_watchdog',
                 6: 'task_watchdog', 7: 'other_watchdog', 8: 'deep_sleep', 9: 'brownout', 10: 'sdio'}
OWNING = ('active', 'stopped_measurement_lost')
PATHS = {'status': '/status', 'heating': '/status/heating', 'telemetry': '/status/ems/telemetry'}
PASSWORD_ENV, MQTT_PASSWORD_ENV, NOTIFY_ENV, HOST_ENV = 'OT_E32_PASSWORD', 'OT_MQTT_PASSWORD', 'OT_NOTIFY_URL', 'OT_E32_HOST'


def utc(now):
    return dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec='seconds')


def local_day(now):
    return dt.datetime.fromtimestamp(now).astimezone().date().isoformat()


def num(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def obj(value):
    return value if isinstance(value, dict) else {}


# --- HTTP ---------------------------------------------------------------------------------------

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise urllib.error.URLError('redirect refused')


class AuthError(Exception):
    """The E32 refused the login (wrong password, rate limit) or has no session."""


class E32Client:
    """GET-only client with an in-memory cookie session (never stored on disk)."""
    LOGIN_PATH = '/auth/login'

    def __init__(self, host, user, password, timeout=20, login_min_interval_s=120, clock=time.time):
        parsed = urllib.parse.urlsplit(host)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.path not in ('', '/') or parsed.query:
            raise ValueError('host must look like http://192.168.1.50 (no path)')
        self.host = f'{parsed.scheme}://{parsed.netloc}'
        self._user, self._password = user, password
        self.timeout = timeout
        self.login_min_interval_s = login_min_interval_s
        self.clock = clock
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                                  urllib.request.HTTPCookieProcessor(self.jar))
        self.last_login_at = None
        self.logins = 0

    def _open(self, method, path, data=None, content_type=None):
        assert path.startswith('/') and not path.startswith('//')
        assert method == 'GET' or (method == 'POST' and path == self.LOGIN_PATH), 'read-only client'
        headers = {'Origin': self.host, 'Cache-Control': 'no-store', 'Accept': 'application/json'}
        if content_type:
            headers['Content-Type'] = content_type
        request = urllib.request.Request(self.host + path, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(RESPONSE_LIMIT + 1)
            if len(raw) > RESPONSE_LIMIT:
                raise http.client.HTTPException('response too large')
            return response.code, raw

    def login(self):
        """One POST /auth/login, at most once per login_min_interval_s (the E32 rate-limits failures)."""
        now = self.clock()
        if self.last_login_at is not None and now - self.last_login_at < self.login_min_interval_s:
            raise AuthError('login_backoff')
        self.last_login_at = now
        self.logins += 1
        body = urllib.parse.urlencode({'username': self._user, 'password': self._password}).encode()
        code, _ = self._open('POST', self.LOGIN_PATH, body, 'application/x-www-form-urlencoded')
        if code != 200:
            raise AuthError(f'login_http_{code}')
        code, _ = self._open('GET', '/auth/session')
        if code != 200:
            raise AuthError(f'session_http_{code}')

    def get_json(self, path):
        code, raw = self._open('GET', path)
        if code == 401:
            self.login()
            code, raw = self._open('GET', path)
        if code != 200:
            raise http.client.HTTPException(f'{path}: HTTP {code}')
        return json.loads(raw)


# --- MQTT (optional) ----------------------------------------------------------------------------

class MqttFeed:
    """Latest fw/telemetry/heating and device_status payloads from the broker (read-only subscribe)."""

    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.connected = False
        self.heating = None
        self.heating_at = None
        self.device_status = None
        self.device_status_at = None
        self.messages = 0
        self.client = None

    def on_payload(self, topic, payload):
        try:
            value = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(value, dict):
            return
        with self.lock:
            self.messages += 1
            if topic.endswith('/fw/telemetry/heating'):
                self.heating, self.heating_at = value, self.clock()
            elif topic.endswith('/fw/telemetry/device_status'):
                self.device_status, self.device_status_at = value, self.clock()

    def snapshot(self, now):
        with self.lock:
            age = lambda at: None if at is None else round(now - at)
            return {'connected': self.connected, 'messages': self.messages, 'heating_age_s': age(self.heating_at),
                    'device_status_age_s': age(self.device_status_at), 'heating': self.heating,
                    'device_status': self.device_status}

    def start(self, host, port, user, password, prefix):
        try:
            import paho.mqtt.client as mqtt  # optional dependency
        except ImportError:
            return False
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:  # paho-mqtt 1.x
            client = mqtt.Client()
        if user:
            client.username_pw_set(user, password)

        def on_connect(c, userdata, flags, reason, properties=None):
            self.connected = (reason == 0) if isinstance(reason, int) else not getattr(reason, 'is_failure', False)
            for suffix in ('fw/telemetry/heating', 'fw/telemetry/device_status'):
                c.subscribe(f'{prefix}/+/{suffix}')

        def on_disconnect(c, userdata, *args):
            self.connected = False

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = lambda c, userdata, message: self.on_payload(message.topic, message.payload)
        client.connect_async(host, port, keepalive=60)
        client.loop_start()
        self.client = client
        return True

    def stop(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()


# --- sample extraction --------------------------------------------------------------------------

def boiler_field(telemetry, name):
    """A boiler telemetry field's value while it is fresh ("valid"), else None."""
    field = obj(obj(telemetry).get('fields')).get(name)
    if isinstance(field, dict) and field.get('state') == 'valid':
        value = field.get('value')
        if field.get('unit') == 'bool' and num(value) is not None:
            return bool(value)
        return value
    return None


def extract(now, raw, plan=None, mqtt=None, errors=()):
    """One JSONL sample from the raw replies (any of them may be missing)."""
    status, heating, telemetry, logs = (obj(raw.get(k)) for k in ('status', 'heating', 'telemetry', 'logs'))
    source = 'http' if heating else None
    if not heating and mqtt and isinstance(mqtt.get('heating'), dict) and num(mqtt.get('heating_age_s')) is not None \
            and mqtt['heating_age_s'] < 120:
        heating, source = mqtt['heating'], 'mqtt'  # compact form: rooms, request, active, burner, ha
    active = obj(heating.get('active'))
    limit = obj(active.get('boiler_limit'))
    runtime = obj(logs.get('runtime'))
    black = obj(logs.get('previous_boot'))
    previous = black.get('previous') if isinstance(black.get('previous'), dict) else None
    reset = num(black.get('reset_reason'))
    modulation = num(boiler_field(telemetry, 'reported_burner_modulation'))
    rooms = []
    for room in heating.get('rooms') or []:
        if isinstance(room, dict):
            rooms.append({k: room.get(k) for k in ('id', 'name', 'state', 'status', 'source', 'setpoint_source',
                                                    'temperature', 'setpoint', 'demand')})
    burner = obj(heating.get('burner'))
    transport = obj(telemetry.get('transport'))
    sample = {
        'type': 'sample', 'v': VERSION, 'at_utc': utc(now), 'at': round(now, 1), 'heating_source': source,
        'errors': list(errors),
        'e32': {'uptime_s': num(status.get('uptime')), 'boot_id': logs.get('boot'),
                'reset_reason': reset, 'reset_reason_name': RESET_REASONS.get(reset) if reset is not None else None,
                'previous_boot': None if previous is None else {
                    k: previous.get(k) for k in ('uptime_s', 'supervisor_restart', 'loop_phase', 'minimum_free_heap_bytes',
                                                 'loop_stack_minimum_bytes', 'last_request')},
                'wifi_lost_restarts': black.get('wifi_lost_restarts'),
                'bluetooth_silent_restarts': black.get('bluetooth_silent_restarts'),
                'network_dead_restarts': black.get('network_dead_restarts')},
        'plan': {'mode': heating.get('mode'), 'revision': heating.get('revision'),
                 'minimum_flow_c': obj(plan).get('minimum_flow_c'), 'maximum_flow_c': obj(plan).get('maximum_flow_c')},
        'rooms': rooms,
        'request': {k: obj(heating.get('request')).get(k) for k in ('heat', 'flow_c', 'reason')},
        'flow_source': obj(heating.get('flow')).get('source'),
        'guard': {'state': active.get('state'), 'enabled': active.get('enabled'),
                  'awaiting_confirmation': active.get('awaiting_confirmation'),
                  'confirmed': active.get('confirmation') is not None if 'confirmation' in active else None,
                  'confirmation_stored': active.get('confirmation_stored'),
                  'command': {k: obj(active.get('command')).get(k) for k in ('send', 'flow_c', 'why')},
                  'last_sent': active.get('last_sent'), 'foreign_controller': active.get('foreign_controller'),
                  'warnings': [w for w in active.get('warnings') or [] if isinstance(w, str)]},
        'boiler_limit': {'flow_c': num(limit.get('flow_c')), 'age_s': num(limit.get('age_s')), 'reads': limit.get('reads'),
                         'configured_heating_temperature_c': num(boiler_field(telemetry, 'configured_heating_temperature'))},
        'boiler': {'flow_c': num(boiler_field(telemetry, 'measured_flow_temperature')),
                   'return_c': num(boiler_field(telemetry, 'measured_return_temperature')),
                   'selected_flow_c': num(boiler_field(telemetry, 'reported_selected_flow_temperature')),
                   'modulation_pct': modulation, 'burner_on': None if modulation is None else modulation > 0,
                   'heating_active': boiler_field(telemetry, 'heating_active'),
                   'dhw_active': boiler_field(telemetry, 'dhw_active'),
                   'dhw_c': num(boiler_field(telemetry, 'measured_dhw_temperature')),
                   'pressure_bar': num(boiler_field(telemetry, 'pressure')),
                   'outdoor_c': num(boiler_field(telemetry, 'outdoor_temperature')),
                   'display_code': boiler_field(telemetry, 'display_code'),
                   'reception': obj(telemetry.get('reception')).get('state')},
        'burner': {k: burner.get(k) for k in ('starts_last_hour', 'heating_starts_last_hour', 'short_cycling')},
        'transport': {k: transport.get(k) for k in ('transmitted_frames', 'invalid_telegrams', 'uart_errors', 'uart_resets')},
        'runtime': {'free_internal_bytes': num(runtime.get('free_internal_bytes')),
                    'minimum_free_internal_bytes': num(runtime.get('minimum_free_internal_bytes')),
                    'largest_internal_block_bytes': num(runtime.get('largest_internal_block_bytes')),
                    'stack_minimum_bytes': {t: num(obj(runtime.get('stack_minimum_bytes')).get(t)) for t in STACK_TASKS}},
        'mqtt_health': {'mqtt_budget_disconnects': num(runtime.get('mqtt_budget_disconnects')),
                        'heating_telemetry_dropped': num(runtime.get('heating_telemetry_dropped')),
                        'heating_telemetry_failed': num(runtime.get('heating_telemetry_failed')),
                        'broker_connected': obj(heating.get('ha')).get('broker_connected')},
        'ha': {k: obj(heating.get('ha')).get(k) for k in ('input_age_s', 'broker_connected')},
        'log_records': [{k: r.get(k) for k in ('sequence', 'uptime_ms', 'level', 'feature', 'message')}
                        for r in logs.get('records') or [] if isinstance(r, dict) and num(r.get('level')) is not None
                        and 1 <= r['level'] <= 2],
    }
    if mqtt:
        sample['mqtt'] = {k: mqtt.get(k) for k in ('connected', 'messages', 'heating_age_s', 'device_status_age_s')}
    return sample


def flow_limit(sample):
    """min(plan maximum, 80, boiler 0x16 limit) as far as known."""
    values = [CEILING_C, num(sample['plan'].get('maximum_flow_c')),
              sample['boiler_limit']['flow_c'] or sample['boiler_limit']['configured_heating_temperature_c']]
    return min(v for v in values if v is not None)


def heating_now(sample):
    """The E32 asks heat now: its sent target in active mode, its calculated request otherwise."""
    if sample['plan']['mode'] == 'active':
        return (num(sample['guard']['command'].get('flow_c')) or 0) > 0
    return sample['request'].get('heat') is True


# --- alarms -------------------------------------------------------------------------------------

@dataclasses.dataclass
class Thresholds:
    no_heat_min: float = 20        # rooms below target without a heat request this long
    below_target_c: float = 0.5    # "below target" for the no-heat alarm
    room_cold_c: float = 1.0       # active room this far below its target ...
    room_warm_c: float = 1.5       # ... or above it ...
    room_hold_min: float = 30      # ... this long (5 min when too warm while still heating)
    flow_margin_c: float = 3.0     # measured flow above the limit by more than this (heating, not DHW)
    max_starts_per_hour: int = 6   # heating burner starts in the last hour
    unreachable_min: float = 3     # E32 unreachable this long
    repeat_min: float = 60         # repeat a standing alarm this often
    heap_minimum_bytes: int = HEAP_MINIMUM_WARN


class AlarmTracker:
    """Raises an alarm once a condition held for `hold_s`, repeats it, and reports when it clears."""

    def __init__(self, repeat_s):
        self.repeat_s = repeat_s
        self.since = {}    # key -> first time the condition held
        self.raised = {}   # key -> last time it was reported

    def update(self, key, condition, now, hold_s, message, severity='alarm', **details):
        events = []
        if not condition:
            self.since.pop(key, None)
            if self.raised.pop(key, None) is not None:
                events.append({'type': 'alarm', 'event': 'cleared', 'key': key, 'severity': 'info',
                               'message': f'Resolved: {key}', 'at_utc': utc(now)})
            return events
        since = self.since.setdefault(key, now)
        if now - since < hold_s:
            return events
        last = self.raised.get(key)
        if last is None or now - last >= self.repeat_s:
            events.append({'type': 'alarm', 'event': 'raised' if last is None else 'repeat', 'key': key,
                           'severity': severity, 'message': message, 'at_utc': utc(now),
                           'for_min': round((now - since) / 60, 1), **details})
            self.raised[key] = now
        return events

    def once(self, key, now, message, severity='alarm', **details):
        """A one-off event (restart, recovery): never repeated, never cleared."""
        return [{'type': 'alarm', 'event': 'raised', 'key': key, 'severity': severity, 'message': message,
                 'at_utc': utc(now), **details}]

    def standing(self):
        return sorted(self.raised)


class Evaluator:
    """Turns samples into alarm events. Pure apart from its own memory; the caller passes the time."""
    COUNTERS = (('mqtt_budget_disconnects', 'MQTT disconnects (socket write budget)'),
                ('heating_telemetry_dropped', 'dropped heating telemetry messages'))

    def __init__(self, thresholds, interval_s):
        self.t = thresholds
        self.interval_s = interval_s
        self.alarms = AlarmTracker(thresholds.repeat_min * 60)
        self.previous = None        # the last evaluated sample (HTTP or MQTT)
        self.last_e32 = None        # boot id and uptime of the last HTTP sample that had them
        self.counters = {}          # counter -> last value seen this boot
        self.counter_notified = {}  # counter -> when an increase was last raised (others are only logged)
        self.first_failure = None
        self.flow_over = 0          # consecutive samples with a too-high measured flow
        self.was_active = False     # the guard reached 'active' since the plan went active

    def unreachable(self, now, error):
        if self.first_failure is None:
            self.first_failure = now
        return self.alarms.update('e32_unreachable', True, now, self.t.unreachable_min * 60,
                                  f'E32 unreachable over HTTP for {round((now - self.first_failure) / 60, 1)} min ({error}).')

    def _reachable(self, now):
        events = []
        if self.first_failure is not None:
            down = now - self.first_failure
            self.first_failure = None
            raised = 'e32_unreachable' in self.alarms.raised
            events += self.alarms.update('e32_unreachable', False, now, 0, '')
            if raised:
                events += self.alarms.once('e32_back', now, f'E32 reachable again after {round(down / 60, 1)} min.', 'info')
        return events

    def _restart(self, s, now):
        e32 = s['e32']
        if e32['boot_id'] is None and e32['uptime_s'] is None:
            return [], False
        last, self.last_e32 = self.last_e32, {'boot_id': e32['boot_id'], 'uptime_s': e32['uptime_s']}
        if last is None:
            return [], False
        restarted = (e32['boot_id'] is not None and last['boot_id'] is not None and e32['boot_id'] != last['boot_id']) or \
            (e32['uptime_s'] is not None and last['uptime_s'] is not None and e32['uptime_s'] + 5 < last['uptime_s'])
        if not restarted:
            return [], False
        pb = e32['previous_boot'] or {}
        return self.alarms.once('e32_restarted', now,
                                f"E32 restarted (reset reason {e32['reset_reason_name']}, supervisor restart "
                                f"{pb.get('supervisor_restart')}, previous uptime {pb.get('uptime_s')} s).",
                                reset_reason=e32['reset_reason_name'], previous_boot=pb, uptime_s=e32['uptime_s']), True

    def _counters(self, s, now, restarted):
        """New MQTT disconnects / dropped telemetry: raised at most once per repeat window, otherwise logged."""
        events = []
        if restarted:
            self.counters = {}
        for key, label in self.COUNTERS:
            value = s['mqtt_health'][key]
            if value is None:
                continue
            last = self.counters.get(key)
            if last is None and restarted:
                last = 0
            self.counters[key] = value
            if last is not None and value < last:
                last = 0  # a reset we did not see
            new = value if last is None else value - last
            if new <= 0:
                continue
            text = f'{new} new {label} (total {value} since boot).' if last is not None else f'{value} {label} since boot.'
            event = self.alarms.once(key, now, text, 'warning', new=new, total=value)
            notified = self.counter_notified.get(key)
            if notified is not None and now - notified < self.alarms.repeat_s:
                event[0]['event'] = 'logged'
            else:
                self.counter_notified[key] = now
            events += event
        return events

    def evaluate(self, s, now, reachable=True):
        A, t = self.alarms, self.t
        events = self._reachable(now) if reachable else []
        restart_events, restarted = self._restart(s, now)
        events += restart_events
        mode, guard = s['plan']['mode'], s['guard']
        state = guard['state']
        heating = heating_now(s)
        prev = self.previous
        # Guard: leaving 'active', waiting for the owner, warnings.
        if mode != 'active':
            if prev and prev['plan']['mode'] == 'active':
                events += A.once('handed_back', now, 'The room plan went back to shadow mode (hand-back).', 'info')
            self.was_active = False
        elif state == 'active':
            self.was_active = True
        stopped = mode == 'active' and self.was_active and state not in ('active', 'awaiting_confirmation', None)
        events += A.update('guard_stopped', stopped, now, 3 * 60 if state == 'arming' else 0,
                           f"Active control stopped: now {state} ({guard['command'].get('why')}); "
                           f"warnings {', '.join(guard['warnings']) or 'none'}.", state=state)
        events += A.update('awaiting_confirmation', mode == 'active' and state == 'awaiting_confirmation', now,
                           2 * self.interval_s,
                           'The E32 waits for the takeover confirmation (after a firmware change, a foreign 0x1A or a '
                           'hand-back): no heat and no frost protection until confirmed on the Rooms page.')
        current = set(guard['warnings']) if mode == 'active' else set()
        known = {k[len('warning_'):] for k in list(A.since) + list(A.raised) if k.startswith('warning_')}
        for name in sorted(current | known):
            events += A.update('warning_' + name, name in current, now, 0, f'Active control warning: {name}.')
        # Flow above the limit.
        limit = flow_limit(s)
        sent = [num(guard['command'].get('flow_c')), num(obj(guard['last_sent']).get('flow_c'))]
        over = [v for v in sent if v is not None and v > limit]
        events += A.update('request_above_limit', bool(over), now, 0,
                           f'The E32 requests {max(over) if over else 0} °C, above the limit {limit} °C.', limit_c=limit)
        b = s['boiler']
        flow_high = b['flow_c'] is not None and b['flow_c'] > limit + t.flow_margin_c and b['heating_active'] is True \
            and b['dhw_active'] is not True
        self.flow_over = self.flow_over + 1 if flow_high else 0
        events += A.update('flow_above_limit', self.flow_over >= 2, now, 0,
                           f"Measured flow {b['flow_c']} °C is above the limit {limit} °C while heating.", limit_c=limit)
        # Short cycling.
        burner = s['burner']
        starts = num(burner.get('heating_starts_last_hour'))
        events += A.update('short_cycling', burner.get('short_cycling') is True
                           or (starts is not None and starts >= t.max_starts_per_hour), now, 0,
                           f"Frequent burner starts: {starts} heating starts in the last hour "
                           f"(short cycling {burner.get('short_cycling')}).")
        # Rooms.
        active_rooms = [r for r in s['rooms'] if r.get('state') == 'active']
        below = [r for r in active_rooms if num(r.get('temperature')) is not None and num(r.get('setpoint')) is not None
                 and r['temperature'] < r['setpoint'] - t.below_target_c]
        events += A.update('no_heat_request', bool(below) and not heating, now, t.no_heat_min * 60,
                           'No heat request although ' + ', '.join(f"{r.get('name') or r.get('id')} {r['temperature']} °C "
                                                                    f"< target {r['setpoint']} °C" for r in below)
                           + f" (state {state}, reason {s['request'].get('reason')}).")
        seen = set()
        for r in active_rooms:
            rid = str(r.get('id'))
            seen.add(rid)
            temp, target = num(r.get('temperature')), num(r.get('setpoint'))
            measured = temp is not None and target is not None
            events += A.update(f'room_cold_{rid}', measured and temp < target - t.room_cold_c, now, t.room_hold_min * 60,
                               f"{r.get('name') or rid} too cold: {temp} °C, target {target} °C.")
            events += A.update(f'room_warm_{rid}', measured and temp > target + t.room_warm_c, now,
                               (5 if heating else t.room_hold_min) * 60,
                               f"{r.get('name') or rid} too warm: {temp} °C, target {target} °C"
                               + (' while the E32 still asks heat.' if heating else '.'))
        for key in sorted({k for k in list(A.since) + list(A.raised) if k.startswith(('room_cold_', 'room_warm_'))}):
            if key.split('_', 2)[2] not in seen:
                events += A.update(key, False, now, 0, '')
        temps = [num(r.get('temperature')) for r in s['rooms'] if num(r.get('temperature')) is not None]
        coldest = min(temps) if temps else None
        frost = mode == 'active' and state in OWNING and coldest is not None and coldest < FROST_ON_C and not heating
        events += A.update('frost_not_protected', frost, now, 2 * self.interval_s,
                           f'A room reads {coldest} °C (below {FROST_ON_C} °C) but the E32 asks no heat.')
        # E32 health: heap, stacks, MQTT link.
        rt = s['runtime']
        heap = rt['minimum_free_internal_bytes']
        events += A.update('heap_low', heap is not None and heap < t.heap_minimum_bytes, now, 0,
                           f'Minimum free internal heap since boot is {heap} B (below {t.heap_minimum_bytes} B).', 'warning')
        low = {k: v for k, v in rt['stack_minimum_bytes'].items() if v and v < STACK_MINIMUM_WARN}
        events += A.update('stack_low', bool(low), now, 0, f'Low task stack minimum: {low}.', 'warning')
        if reachable:
            events += self._counters(s, now, restarted)
        if s.get('mqtt'):
            age = s['mqtt'].get('heating_age_s')
            events += A.update('mqtt_silent', age is None or age > 300, now, 300,
                               f'No fw/telemetry/heating on MQTT for {age} s (Home Assistant sees no updates).', 'warning')
        self.previous = s
        return events


# --- daily summary ------------------------------------------------------------------------------

class DaySummary:
    def __init__(self, day):
        self.day = day
        self.samples = self.failed = 0
        self.states = {}
        self.heat = self.burner = self.dhw = 0
        self.flow_heating = []
        self.request_max = None
        self.starts_max = None
        self.heap_min = None
        self.stack_min = {}
        self.rooms = {}
        self.restarts = []
        self.alarms = {}
        self.limits = set()
        self.mqtt_disconnects = {'first': None, 'last': None}

    def add_failure(self):
        self.failed += 1

    def add(self, s):
        self.samples += 1
        state = s['guard']['state'] or 'unknown'
        self.states[state] = self.states.get(state, 0) + 1
        self.heat += heating_now(s)
        b = s['boiler']
        self.burner += b['burner_on'] is True
        self.dhw += b['dhw_active'] is True
        if b['heating_active'] and not b['dhw_active'] and b['flow_c'] is not None:
            self.flow_heating.append(b['flow_c'])
        flow = num(s['guard']['command'].get('flow_c'))
        if flow is not None:
            self.request_max = max(flow, self.request_max or 0)
        starts = num(s['burner'].get('heating_starts_last_hour'))
        if starts is not None:
            self.starts_max = max(starts, self.starts_max or 0)
        heap = s['runtime']['minimum_free_internal_bytes']
        if heap is not None:
            self.heap_min = heap if self.heap_min is None else min(heap, self.heap_min)
        for task, value in s['runtime']['stack_minimum_bytes'].items():
            if value:
                self.stack_min[task] = min(value, self.stack_min.get(task, value))
        if s['boiler_limit']['flow_c'] is not None:
            self.limits.add(s['boiler_limit']['flow_c'])
        d = s['mqtt_health']['mqtt_budget_disconnects']
        if d is not None:
            self.mqtt_disconnects['first'] = d if self.mqtt_disconnects['first'] is None else self.mqtt_disconnects['first']
            self.mqtt_disconnects['last'] = d
        for r in s['rooms']:
            temp, target = num(r.get('temperature')), num(r.get('setpoint'))
            if temp is None:
                continue
            row = self.rooms.setdefault(str(r.get('id')), {'name': r.get('name'), 'n': 0, 'min': temp, 'max': temp,
                                                            'sum': 0.0, 'dev_sum': 0.0, 'dev_n': 0, 'below_05': 0})
            row['n'] += 1
            row['min'], row['max'], row['sum'] = min(row['min'], temp), max(row['max'], temp), row['sum'] + temp
            if target is not None and r.get('state') == 'active':
                row['dev_sum'] += temp - target
                row['dev_n'] += 1
                row['below_05'] += temp < target - 0.5

    def add_events(self, events):
        for e in events:
            if e['event'] == 'raised':
                self.alarms[e['key']] = self.alarms.get(e['key'], 0) + 1
                if e['key'] == 'e32_restarted':
                    self.restarts.append({'at_utc': e['at_utc'], 'reset_reason': e.get('reset_reason'),
                                          'supervisor_restart': (e.get('previous_boot') or {}).get('supervisor_restart')})

    def json(self):
        n = self.samples or 1
        share = lambda c: round(c / n, 3)
        flows = self.flow_heating
        return {'type': 'summary', 'day': self.day, 'samples': self.samples, 'failed_samples': self.failed,
                'guard_states': {k: share(v) for k, v in sorted(self.states.items())},
                'heat_request_share': share(self.heat), 'burner_on_share': share(self.burner), 'dhw_share': share(self.dhw),
                'flow_while_heating_c': {'min': min(flows), 'max': max(flows), 'mean': round(sum(flows) / len(flows), 1)}
                if flows else None,
                'request_max_c': self.request_max, 'heating_starts_per_hour_max': self.starts_max,
                'boiler_limits_c': sorted(self.limits), 'restarts': self.restarts, 'alarms_raised': self.alarms,
                'minimum_free_internal_bytes': self.heap_min, 'stack_minimum_bytes': self.stack_min,
                'mqtt_budget_disconnects': self.mqtt_disconnects,
                'rooms': {k: {'name': r['name'], 'min_c': r['min'], 'max_c': r['max'], 'mean_c': round(r['sum'] / r['n'], 2),
                              'mean_deviation_c': round(r['dev_sum'] / r['dev_n'], 2) if r['dev_n'] else None,
                              'below_target_0_5_share': round(r['below_05'] / r['dev_n'], 3) if r['dev_n'] else None}
                          for k, r in self.rooms.items()}}


# --- output and notification --------------------------------------------------------------------

class Notifier:
    """POSTs alarm events as JSON to a Home Assistant webhook. The URL is never printed or logged."""

    def __init__(self, url, timeout=10, opener=None):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError('notify URL must be http(s)://...')
        self._url = url
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.failures = 0

    def send(self, event):
        body = json.dumps({'title': 'OpenThermostat monitor', 'message': event['message'], 'key': event['key'],
                           'event': event['event'], 'severity': event['severity'], 'at_utc': event['at_utc']}).encode()
        request = urllib.request.Request(self._url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                response.read(4096)
            return True
        except (urllib.error.URLError, *NETWORK_ERRORS):
            self.failures += 1
            return False


class Output:
    def __init__(self, directory, notifier=None, stream=sys.stdout):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.notifier = notifier
        self.stream = stream

    def append(self, name, record):
        with (self.dir / name).open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')

    def sample(self, s, day):
        self.append(f'samples-{day}.jsonl', s)

    NOTIFY_INFO = ('e32_back', 'handed_back')

    def events(self, events):
        """Every event to alarms.jsonl and stdout; raised/repeat/cleared also to the webhook ('logged' is file only)."""
        for e in events:
            self.append('alarms.jsonl', e)
            if e['event'] == 'cleared':
                tag = 'OK'
            elif e['event'] == 'logged':
                tag = 'NOTE'
            else:
                tag = {'alarm': 'ALARM', 'warning': 'WARNING', 'info': 'INFO'}.get(e['severity'], 'ALARM')
                if e['event'] == 'repeat':
                    tag += ' (still)'
            print(f"{e['at_utc']} {tag} [{e['key']}] {e['message']}", file=self.stream, flush=True)
            notify = e['event'] in ('raised', 'repeat') and (e['severity'] != 'info' or e['key'] in self.NOTIFY_INFO)                 or e['event'] == 'cleared'
            if self.notifier and notify and not self.notifier.send(e):
                print(f"{e['at_utc']} notify failed for [{e['key']}]", file=self.stream, flush=True)

    def summary(self, summary):
        path = self.dir / f'summary-{summary.day}.json'
        path.write_text(json.dumps(summary.json(), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        return path


# --- the monitor --------------------------------------------------------------------------------

class Monitor:
    def __init__(self, client, output, thresholds, interval_s, mqtt=None, clock=time.time):
        self.client = client
        self.output = output
        self.interval_s = interval_s
        self.mqtt = mqtt
        self.clock = clock
        self.evaluator = Evaluator(thresholds, interval_s)
        self.plan = None
        self.count = 0
        self.log_cursor = 0
        self.summary = None

    def poll(self):
        """One sample: read, log, alarm. Returns the sample, or None when the E32 did not answer."""
        now = self.clock()
        day = local_day(now)
        if self.summary is None:
            self.summary = DaySummary(day)
        elif self.summary.day != day:
            self.output.summary(self.summary)
            self.summary = DaySummary(day)
        raw, errors = {}, []
        mqtt = self.mqtt.snapshot(now) if self.mqtt else None
        try:
            raw['heating'] = self.client.get_json(PATHS['heating'])
        except AuthError as error:
            errors.append(f'auth: {error}')
        except (*NETWORK_ERRORS, ValueError) as error:
            errors.append(f'heating: {type(error).__name__}: {error}')
        if 'heating' in raw:
            for name, path in (('status', PATHS['status']), ('telemetry', PATHS['telemetry']),
                               ('logs', f'/status/logs?after={self.log_cursor}')):
                try:
                    raw[name] = self.client.get_json(path)
                except (AuthError, *NETWORK_ERRORS, ValueError) as error:
                    errors.append(f'{name}: {type(error).__name__}: {error}')
            if self.count % 10 == 0 or self.plan is None:
                try:
                    self.plan = self.client.get_json('/config/heating')
                except (AuthError, *NETWORK_ERRORS, ValueError) as error:
                    errors.append(f'plan: {type(error).__name__}: {error}')
        self._advance_cursor(obj(raw.get('logs')))
        self.count += 1
        reachable = 'heating' in raw
        events = [] if reachable else self.evaluator.unreachable(now, errors[0] if errors else 'no answer')
        if not reachable and not (mqtt and mqtt.get('heating')):
            self.summary.add_failure()
            self.output.append(f'samples-{day}.jsonl', {
                'type': 'sample', 'v': VERSION, 'at_utc': utc(now), 'at': round(now, 1), 'reachable': False,
                'errors': errors, 'mqtt': None if not mqtt else {k: mqtt.get(k) for k in ('connected', 'heating_age_s')}})
            self.output.events(events)
            self.summary.add_events(events)
            return None
        sample = extract(now, raw, self.plan, mqtt, errors)  # without HTTP: from the MQTT heating payload
        sample['reachable'] = reachable
        events += self.evaluator.evaluate(sample, now, reachable)
        self.output.sample(sample, day)
        self.output.events(events)
        self.summary.add(sample)
        self.summary.add_events(events)
        if self.count % 10 == 0:
            self.output.summary(self.summary)
        return sample

    def _advance_cursor(self, logs):
        """Follow /status/logs by sequence; start again from 0 after a restart (sequences restart)."""
        sequences = [r['sequence'] for r in logs.get('records') or [] if isinstance(r, dict) and num(r.get('sequence')) is not None]
        latest = num(logs.get('latest'))
        if sequences:
            self.log_cursor = max(sequences)
        elif latest is not None and latest < self.log_cursor:
            self.log_cursor = 0

    def run(self, duration_s=None, sleep=time.sleep):
        started = self.clock()
        try:
            while duration_s is None or self.clock() - started < duration_s:
                began = self.clock()
                self.poll()
                sleep(max(1.0, self.interval_s - (self.clock() - began)))
        except KeyboardInterrupt:
            pass
        finally:
            if self.summary:
                path = self.output.summary(self.summary)
                print(f'summary: {path}', file=self.output.stream, flush=True)


def line(s):
    """A short human line per sample for the terminal."""
    rooms = ', '.join(f"{r.get('name') or r.get('id')} {r.get('temperature')}/{r.get('setpoint')}" for r in s['rooms']
                      if r.get('state') == 'active')
    b, g = s['boiler'], s['guard']
    return (f"{s['at_utc']} {g['state']} req {g['command'].get('flow_c')} (calc {s['request'].get('flow_c')}) "
            f"flow {b['flow_c']} mod {b['modulation_pct']} dhw {b['dhw_active']} | {rooms} | "
            f"heap min {s['runtime']['minimum_free_internal_bytes']} mqtt disc {s['mqtt_health']['mqtt_budget_disconnects']}"
            + (f" | warnings {g['warnings']}" if g['warnings'] else ''))


def read_password(env, prompt, stdin=sys.stdin, ask=getpass.getpass):
    value = os.environ.get(env)
    if value:
        return value
    if stdin is not None and stdin.isatty():
        return ask(prompt)
    raise SystemExit(f'Set {env} or run interactively for a password prompt (never on the command line).')


def parse_args(argv=None):
    root = Path(__file__).resolve().parents[2]
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0], allow_abbrev=False)
    p.add_argument('--host', default=os.environ.get(HOST_ENV), help=f'E32 address, e.g. http://192.168.1.50 (or {HOST_ENV})')
    p.add_argument('--user', default='admin', help='E32 web user (default admin); the password comes from '
                                                   f'{PASSWORD_ENV} or a prompt')
    p.add_argument('--interval', type=float, default=60, help='seconds between samples, 30-60 (default 60)')
    p.add_argument('--duration-h', type=float, default=48, help='stop after this many hours (default 48; 0 = until Ctrl+C)')
    p.add_argument('--out', help='output folder (default out/switchover-<UTC date> in the repository)')
    p.add_argument('--once', action='store_true', help='take one sample, print it, write nothing else')
    p.add_argument('--notify-url', default=os.environ.get(NOTIFY_ENV),
                   help=f'Home Assistant webhook URL for alarms (or {NOTIFY_ENV}; prefer the variable, it holds a secret id)')
    p.add_argument('--mqtt-host', help='broker to listen to fw/telemetry (needs paho-mqtt; otherwise HTTP only)')
    p.add_argument('--mqtt-port', type=int, default=1883)
    p.add_argument('--mqtt-user', help=f'broker user; the password comes from {MQTT_PASSWORD_ENV} or a prompt')
    p.add_argument('--mqtt-prefix', default='ib-therm', help='the E32 MQTT prefix (default ib-therm; new installs openthermostat)')
    for field in dataclasses.fields(Thresholds):
        p.add_argument('--' + field.name.replace('_', '-'), type=type(field.default), default=field.default,
                       help=f'alarm threshold (default {field.default})')
    a = p.parse_args(argv)
    if not a.host:
        p.error(f'--host or {HOST_ENV} is required')
    if not 30 <= a.interval <= 60:
        p.error('--interval must be 30-60 s')
    if a.duration_h < 0:
        p.error('--duration-h must be >= 0')
    a.thresholds = Thresholds(**{f.name: getattr(a, f.name) for f in dataclasses.fields(Thresholds)})
    a.out = Path(a.out) if a.out else root / 'out' / f"switchover-{time.strftime('%Y%m%d', time.gmtime())}"
    return a


def main(argv=None):
    a = parse_args(argv)
    client = E32Client(a.host, a.user, read_password(PASSWORD_ENV, f'E32 password for {a.user}: '))
    try:
        client.login()
    except (AuthError, *NETWORK_ERRORS) as error:
        print(f'Login to the E32 failed: {error}', file=sys.stderr)
        return 2
    mqtt = None
    if a.mqtt_host:
        mqtt = MqttFeed()
        password = read_password(MQTT_PASSWORD_ENV, 'MQTT password: ') if a.mqtt_user else None
        if not mqtt.start(a.mqtt_host, a.mqtt_port, a.mqtt_user, password, a.mqtt_prefix):
            print('paho-mqtt is not installed: HTTP only.', flush=True)
            mqtt = None
    if a.once:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            monitor = Monitor(client, Output(tmp, None), a.thresholds, a.interval, mqtt)
            sample = monitor.poll()
        print(json.dumps(sample, ensure_ascii=False, indent=1))
        if mqtt:
            mqtt.stop()
        return 0 if sample else 1
    notifier = Notifier(a.notify_url) if a.notify_url else None
    output = Output(a.out, notifier)
    print(f'Monitoring {client.host} every {a.interval:g} s into {a.out}'
          + (' (alarms also to the webhook)' if notifier else '') + ('; MQTT on' if mqtt else '; HTTP only'), flush=True)

    class Printing(Monitor):
        def poll(self):
            sample = super().poll()
            if sample:
                print(line(sample), flush=True)
            return sample

    monitor = Printing(client, output, a.thresholds, a.interval, mqtt)
    try:
        monitor.run(a.duration_h * 3600 if a.duration_h else None)
    finally:
        if mqtt:
            mqtt.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
