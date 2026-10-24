"""Bounded actuator messages on the EXISTING native worker/connection.

No product source factory is selected. Missing local factory denies all traffic.
A supplied source factory must independently qualify the adapter and receiver;
transport context adds restrictions and never supplies physical authority.
"""
from dataclasses import asdict
import math

from homeassistant.exceptions import HomeAssistantError

from .actuator_receiver import ActuatorReceiver, GRANT_SECONDS, MAX_BYTES, MAX_SEQUENCE
from .v1_wire import canonical, identifier, parse

REQUEST = 'fw/actuator_grant_request/'
COMMAND = 'fw/actuator_command/'


def actuator_topic(topic):
    return topic in (REQUEST[:-1], COMMAND[:-1]) or topic.startswith((REQUEST, COMMAND))


class ActuatorWire:
    """One request/grant record per configured binding, maximum eight owners.

    `factory(scope)` is trusted local SOURCE code, never a broker/GUI flag.
    The native factory currently supplies None. Requalification after disconnect,
    scope loss or uncertain IO requires a new connection owner, not auto-retry.
    """
    def __init__(self, connection, factory=None):
        if factory is not None and not callable(factory):
            raise ValueError('Invalid local actuator source factory')
        self.connection, self._factory = connection, factory
        self._owners = {}
        self._closed = False
        self._watermark = None

    def retire(self):
        self._closed = True
        for state in self._owners.values():
            state['receiver'].retire()

    def transport_lost(self):
        # Initial online/offline status before qualification owns no grant or
        # action. Once any owner exists, reconnect can never revive this route.
        if self._owners:
            self.retire()

    @property
    def accepting(self):
        return self._factory is not None and not self._closed and not self.connection.closed

    def observe(self, topic, raw, *, retained=False):
        """Narrowing-only ingress fence; never apply/renew shadow session data."""
        if self._closed or not self._owners or retained:
            return
        if topic == 'fw/availability':
            if raw in ('online', 'offline'):
                self.transport_lost()
            return
        if (not topic.startswith('fw/') or topic.startswith('fw/telemetry/')
                or actuator_topic(topic)):
            return
        try:
            payload = parse(raw)
            owner = next(iter(self._owners.values()))['receiver'].scope
            expected = dict(api=1, controller_id=owner.controller_id, boot_id=owner.boot_id,
                epoch=owner.epoch, config_revision=owner.config_revision,
                config_digest=owner.config_digest)
            if (type(payload) is not dict
                    or any(type(payload.get(k)) is not type(v) or payload.get(k) != v
                           for k, v in expected.items())
                    or payload.get('storage_fault') is True
                    or payload.get('status') == 'storage_fault'
                    or payload.get('mapping_ready') is False
                    or any(k in payload and payload[k] != v for k, v in
                           [('adapter_id', owner.adapter_id),
                            ('adapter_session_id', owner.adapter_session_id)])):
                self.retire()
                return
            client = self.connection.client
            if ('source_policy' in payload
                    and (client.controller_policy is None or not client.controller_policy.matches(payload))):
                self.retire()
        except Exception:
            self.retire()

    def scope(self, binding):
        client = self.connection.client
        if self._closed or self.connection.closed or client is None:
            return None
        return client.actuator_scope(binding)

    def _now(self):
        try:
            now = self.connection.client.clock()
            valid = (type(now) in (int, float) and math.isfinite(now) and now >= 0
                     and (self._watermark is None or now >= self._watermark))
        except Exception:
            valid = False
        if not valid:
            self.retire()
            raise HomeAssistantError('Actuator wire clock invalid')
        self._watermark = now
        return now

    def check_current(self):
        for binding, state in self._owners.items():
            if self.scope(binding) != state['receiver'].scope:
                self.retire()
                return False
        return not self._closed

    async def receive(self, topic, raw, *, retained=False, received_at=None):
        """Reserved topics never enter the shadow parser or renew last_rx/lease."""
        if not actuator_topic(topic):
            return False
        if self._closed or self._factory is None or retained:
            return True
        binding = topic[len(REQUEST) if topic.startswith(REQUEST) else len(COMMAND):]
        if not identifier(binding) or type(raw) is not str or len(raw) > MAX_BYTES:
            return True
        state = self._owners.get(binding)
        try:
            now = self._now()
            if (type(received_at) not in (int, float) or not math.isfinite(received_at)
                    or not 0 <= received_at <= now < received_at + GRANT_SECONDS):
                return True
            scope = self.scope(binding)
            if scope is None:
                if state is not None:
                    self.retire()
                return True
            if state is not None and state['receiver'].scope != scope:
                self.retire()
                return True
            if topic.startswith(REQUEST):
                payload = parse(raw)
                expected = dict(api=1, **asdict(scope), command_kind='room_target')
                if (payload.keys() != expected.keys() | {'request_sequence'}
                        or any(type(payload[k]) is not type(v) or payload[k] != v
                               for k, v in expected.items())
                        or type(payload['request_sequence']) is not int
                        or not 1 <= payload['request_sequence'] <= MAX_SEQUENCE):
                    return True
                if state is None:
                    if len(self._owners) >= 8:
                        return True
                    receiver = None
                    try:
                        receiver = self._factory(scope)
                        if type(receiver) is not ActuatorReceiver or receiver.scope != scope:
                            raise HomeAssistantError('Invalid local actuator receiver factory result')
                        receiver.bind_context(lambda: self.scope(binding))
                    except BaseException:
                        if type(receiver) is ActuatorReceiver:
                            receiver.retire()
                        self.retire()
                        raise
                    state = dict(receiver=receiver, sequence=0, request=None,
                                 grant=None, deadline=0)
                    self._owners[binding] = state
                sequence = payload['request_sequence']
                if sequence < state['sequence']:
                    return True
                if sequence == state['sequence']:
                    if payload != state['request'] or self._now() >= state['deadline']:
                        return True
                    grant = state['grant']  # original grant/deadline, never reissue
                else:
                    client = self.connection.client
                    deadline = min(received_at + GRANT_SECONDS, client.lease_until, client.grant_until)
                    grant = state['receiver'].issue(scope=scope, not_after=deadline)
                    state.update(sequence=sequence, request=payload, grant=grant,
                                 deadline=min(deadline, state['receiver'].grant_deadline))
                if self.scope(binding) != scope or self._now() >= state['deadline']:
                    self.retire()
                    return True
                await self.connection.publish('ha/actuator_grant/' + binding, canonical(grant))
            elif state is not None:
                receipt = await state['receiver'].async_receive(raw, scope=scope)
                if self.scope(binding) != scope or self._now() >= state['deadline']:
                    self.retire()
                    return True
                await self.connection.publish('ha/actuator_result/' + binding,
                    canonical(dict(api=1, **asdict(scope), **asdict(receipt))))
            self.check_current()
        except (HomeAssistantError, ValueError, TypeError, KeyError, OverflowError):
            # Never replay, manufacture an ACK or reset unrelated shadow data.
            if state is not None:
                state['receiver'].retire()
        except Exception:
            # A local producer/transport failure can have an uncertain outcome.
            # Retire this optional route, without touching the shadow session.
            self.retire()
        return True
