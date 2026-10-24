"""Prepared M2 receiver admission; NOT selected by the native shadow factory.

The future owner must supply current local scope and separately reviewed authority.
A grant is receiver-clock evidence, never device feedback or boiler permission.
No subscriptions, publishing, timers, storage or automatic actuation wiring.
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, replace
import math
import re
import secrets

from homeassistant.exceptions import HomeAssistantError

from .v1_profile_c import ProfileCActuator, RoomTargetCommand

_ID = re.compile(r'[A-Za-z0-9_-]{1,32}')
_HEX = re.compile(r'[0-9a-f]{64}')
MAX_BYTES = 2048
GRANT_SECONDS = 5.0
MAX_SEQUENCE = 4294967295


@dataclass(frozen=True, slots=True)
class ActuatorScope:
    controller_id: str
    boot_id: str
    epoch: int
    adapter_id: str
    adapter_session_id: str
    config_revision: int
    config_digest: str
    binding_id: str

    def valid(self):
        return (all(type(getattr(self, key)) is str and _ID.fullmatch(getattr(self, key))
                    for key in ('controller_id', 'boot_id', 'adapter_id', 'adapter_session_id', 'binding_id'))
                and all(type(getattr(self, key)) is int and 1 <= getattr(self, key) <= MAX_SEQUENCE
                        for key in ('epoch', 'config_revision'))
                and type(self.config_digest) is str and _HEX.fullmatch(self.config_digest))


class ActuatorReceiver:
    """One immutable, source-admitted owner; at most one pending action/result.

    `scope` arguments are LOCAL current-owner snapshots, never decoded broker
    context. `authorize` must check actual source/registry/profile/exclusive
    ownership. Defaults deny. ProfileCActuator independently retains its guards.
    A new session/config/binding needs a newly reviewed receiver AND adapter.
    """
    def __init__(self, adapter, scope, *, qualified_profile=False, authorize=None):
        if type(adapter) is not ProfileCActuator or type(scope) is not ActuatorScope or not scope.valid():
            raise ValueError('invalid local actuator receiver owner')
        if getattr(adapter, '_openthermostat_receiver_claimed', False):
            raise ValueError('Actuator adapter already belongs to a receiver owner')
        # A new wrapper cannot clear retirement while reusing the old adapter.
        adapter._openthermostat_receiver_claimed = True
        self._adapter, self._scope = adapter, scope
        self._qualified = qualified_profile is True
        self._authorize = authorize or (lambda: False)
        self._clock = adapter.hass.loop.time
        self._clock_watermark = None
        self._retired = False
        self._grant_sequence = 0
        self._grant = None
        self._deadline = None
        self._sequence = 0
        self._key = self._result = None

    def retire(self):
        self._retired = True
        self._grant = None

    def _now(self):
        try:
            now = self._clock()
            valid = (type(now) in (int, float) and math.isfinite(now) and now >= 0
                     and (self._clock_watermark is None or now >= self._clock_watermark))
        except Exception:
            valid = False
        if not valid:
            self.retire()
            raise HomeAssistantError('Actuator receiver clock invalid; requalification required')
        self._clock_watermark = now
        return now

    def _current(self, scope):
        if self._retired:
            raise HomeAssistantError('Actuator receiver retired; requalification required')
        now = self._now()
        if type(scope) is not ActuatorScope or not scope.valid() or scope != self._scope:
            self.retire()
            raise HomeAssistantError('Actuator receiver owner changed; requalification required')
        if not self._qualified:
            raise HomeAssistantError('Actuator receiver profile disabled')
        try:
            authorized = self._authorize()
            now = self._now()  # callback delay/reversal belongs to the original budget
        except BaseException:
            self.retire()
            raise
        if (authorized is not True or self._retired or not self._qualified
                or self._scope != scope):
            self.retire()
            raise HomeAssistantError('Actuator receiver authorization lost; requalification required')
        return now

    def issue(self, *, scope):
        """Return one grant with ORIGINAL deadline; repeated reads never renew it."""
        now = self._current(scope)
        if self._grant is not None and now < self._deadline:
            return dict(self._grant)
        if self._result is not None and not self._result.done():
            raise HomeAssistantError('Actuator receiver action pending; no new grant')
        if self._grant_sequence == MAX_SEQUENCE:
            self.retire()
            raise HomeAssistantError('Actuator receiver grant sequence exhausted')
        self._grant_sequence += 1
        # Sequence prevents local nonce reuse even if RNG repeats; no wrap.
        nonce = f'r{self._grant_sequence:08x}{secrets.token_hex(10)}'
        self._deadline = now + GRANT_SECONDS
        if not math.isfinite(self._deadline) or self._deadline <= now:
            self.retire()
            raise HomeAssistantError('Actuator receiver clock cannot represent grant deadline')
        self._grant = dict(api=1, **asdict(self._scope), command_kind='room_target',
                          grant_id=nonce, grant_sequence=self._grant_sequence, grant_ms=5000)
        return dict(self._grant)

    async def async_receive(self, raw, *, scope, retained=False):
        """Admit one bounded intent; return acceptance only, NEVER a device ACK."""
        if retained:
            raise HomeAssistantError('Retained actuator command refused')
        now = self._current(scope)
        if type(raw) is not str or len(raw) > MAX_BYTES:
            raise HomeAssistantError('Invalid actuator command bytes')
        # Reuse the existing bounded ASCII/no-escapes/duplicate/depth parser.
        from .v1_wire import parse
        try:
            payload = parse(raw)
        except (ValueError, TypeError, OverflowError, RecursionError) as error:
            raise HomeAssistantError('Invalid actuator command bytes') from error
        expected = dict(api=1, **asdict(self._scope), command_kind='room_target')
        fields = set(expected) | {'grant_id', 'grant_sequence', 'sequence', 'target_centi_c'}
        if (payload.keys() != fields or any(type(payload[k]) is not type(v) or payload[k] != v
                                           for k, v in expected.items())
                or type(payload['grant_id']) is not str or not _ID.fullmatch(payload['grant_id'])
                or any(type(payload[k]) is not int or not 1 <= payload[k] <= MAX_SEQUENCE
                       for k in ('grant_sequence', 'sequence'))
                or type(payload['target_centi_c']) is not int or not 500 <= payload['target_centi_c'] <= 3500):
            raise HomeAssistantError('Invalid actuator command scope or payload')
        key = tuple(payload[k] for k in sorted(fields))
        sequence = payload['sequence']
        if sequence < self._sequence:
            raise HomeAssistantError('Actuator command older than receiver high-water mark')
        if sequence == self._sequence:
            if key != self._key:
                raise HomeAssistantError('Actuator duplicate command payload changed')
            receipt = await asyncio.shield(self._result)
            self._current(scope)
            return replace(receipt, duplicate=True)  # historical only; no IO
        if self._result is not None and not self._result.done():
            raise HomeAssistantError('Actuator receiver action pending; no command queued')
        if (self._grant is None or payload['grant_id'] != self._grant['grant_id']
                or payload['grant_sequence'] != self._grant_sequence or now >= self._deadline):
            raise HomeAssistantError('Actuator receiver grant missing or expired')
        deadline = self._deadline
        result = self._adapter.hass.loop.create_future()
        result.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        self._sequence, self._key, self._result = sequence, key, result
        try:
            # Final callback may consume the remaining original window.
            if self._current(scope) >= deadline:
                raise HomeAssistantError('Actuator receiver grant expired before dispatch')
            receipt = await self._adapter.async_apply_command(
                RoomTargetCommand(sequence, payload['target_centi_c'], deadline))
            if self._current(scope) >= deadline:
                raise HomeAssistantError('Actuator receiver completed after original deadline')
        except asyncio.CancelledError:
            self.retire()
            result.set_exception(HomeAssistantError('Actuator command owner cancelled; no retry'))
            raise
        except Exception as error:
            # Even a service acceptance cannot establish the physical outcome.
            # An admitted failed operation is never retried by this owner.
            self.retire()
            result.set_exception(error)
            raise
        result.set_result(receipt)
        return receipt
