"""One-way authenticated HA helper intent, separate from physical device proof.

Only future native manual state changes are consumed. No helper is written,
polled or read on startup to create an override. Physical climate/number device
events still need their own reviewed original-action adapter.
"""
import asyncio
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import math

MAX_EVENT_AGE_MS = 5000
DEFAULT_DURATION_MS = 3600000


def is_manual_helper(ref):
    return (ref is not None and ref.entity_id.startswith('input_number.')
            and ref.platform == 'input_number' and type(ref.unique_id) is str
            and 1 <= len(ref.unique_id) <= 256)


def target_value(state):
    if state is None or state.attributes.get('restored'):
        return None
    try:
        value = Decimal(state.state)
        if not value.is_finite():
            return None
        unit = state.attributes.get('unit_of_measurement')
        if unit == '°F':
            value = ((value-32)*5/9*100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        elif unit == '°C':
            value *= 100
            if value != value.to_integral_value():
                return None
        else:
            return None
        return int(value) if 500 <= value <= 3500 else None
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None


def select_manual_helper(hass, selection):
    from .v1_heating_graph import selected_reference
    from .v1_model import EntityReference
    raw = selected_reference(hass, selection, ('input_number',))
    ref = EntityReference.from_dict(raw)
    state = hass.states.get(raw['entity_id'])
    if (not is_manual_helper(ref) or state is None
            or state.attributes.get('unit_of_measurement') not in ('°C', '°F')):
        raise ValueError('unsupported_manual_target')
    return ref


def validate_manual_owner(hass, entry, room):
    if not is_manual_helper(room.setpoint):
        return
    from .product import configuration_parts
    from .v1_model import RoomBinding
    for other in hass.config_entries.async_entries('open_thermostat'):
        for sub in configuration_parts(other):
            if sub.subentry_type != 'zone':
                continue
            existing = RoomBinding.from_dict(dict(sub.data))
            if other.entry_id == entry.entry_id and existing.room_id == room.room_id:
                continue
            if existing.setpoint and existing.setpoint.identity() == room.setpoint.identity():
                raise ValueError('manual_target_has_multiple_rooms')


@dataclass(frozen=True, slots=True)
class TargetIntent:
    entity_id: str
    identity: tuple
    context_id: str
    updated_at: object
    target: int
    captured_at: float
    age_ms: int


class ManualTargetOwner:
    def __init__(self, runtime):
        self.runtime = runtime
        self.pending, self.tasks, self.watermarks, self.status = {}, {}, {}, {}
        self.epoch = 0

    def observe(self, room, kind, event):
        from homeassistant.helpers import entity_registry as er
        from homeassistant.util import dt as dt_util
        runtime = self.runtime
        if not is_manual_helper(room.setpoint):
            self.status[room.room_id] = 'device_action_profile_required'
            return
        if kind != 'changed' or event is None or getattr(event,'event_type',None) != 'state_changed' or not runtime.enabled:
            return
        entity_id = runtime.resolved(room.setpoint)
        row = er.async_get(runtime.hass).async_get(entity_id) if entity_id else None
        state = runtime.hass.states.get(entity_id) if row and row.disabled_by is None else None
        before, after = event.data.get('old_state'), event.data.get('new_state')
        context = getattr(event, 'context', None)
        now = runtime._measurement_now()
        target = target_value(state)
        if (state is None or event.data.get('entity_id') != entity_id or after is not state or before is None
                or before.state == after.state or target_value(before) == target
                or context is None or not context.user_id or context.parent_id is not None
                or state.context.id != context.id or type(context.id) is not str or not 1 <= len(context.id) <= 64
                or now is None or target is None
                or not room.minimum_target_centi_c <= target <= room.maximum_target_centi_c):
            self.status[room.room_id] = 'manual_action_required'
            return
        try:
            utc = dt_util.utcnow()
            ages = [(utc-time).total_seconds()*1000 for time in (event.time_fired,state.last_updated)]
            age = math.ceil(max(ages)) if min(ages)>=0 else -1
        except (TypeError, ValueError, OverflowError):
            age = MAX_EVENT_AGE_MS
        old = self.watermarks.get(room.room_id)
        if not 0 <= age < MAX_EVENT_AGE_MS or (old and (old[0] == context.id or state.last_updated <= old[1])):
            self.status[room.room_id] = 'old_or_repeated_action'
            return
        # Consume even while offline. Reconnection never replays a manual action.
        self.watermarks[room.room_id] = (context.id, state.last_updated)
        if not runtime.transport_ready:
            self.status[room.room_id] = 'controller_unavailable'
            return
        proof = TargetIntent(entity_id, room.setpoint.identity(), context.id, state.last_updated, target, now, age)
        self.pending[room.room_id] = (room, runtime._generation, self.epoch, proof)
        self.status[room.room_id] = 'request_pending'
        task = self.tasks.get(room.room_id)
        if task is None or task.done() or task.cancelling():
            self.tasks[room.room_id] = runtime.hass.async_create_task(self._flush(room.room_id))

    async def _flush(self, room_id):
        from homeassistant.helpers import entity_registry as er
        runtime = self.runtime
        try:
            while room_id in self.pending:
                room, generation, epoch, proof = self.pending.pop(room_id)
                now = runtime._measurement_now()
                entity_id = runtime.resolved(room.setpoint)
                row = er.async_get(runtime.hass).async_get(entity_id) if entity_id else None
                state = runtime.hass.states.get(entity_id) if row and row.disabled_by is None else None
                age = proof.age_ms + math.ceil((now-proof.captured_at)*1000) if now is not None else MAX_EVENT_AGE_MS
                if (not runtime.enabled or generation != runtime._generation or epoch != self.epoch
                        or runtime.rooms.get(room_id) is not room or not runtime.transport_ready
                        or entity_id != proof.entity_id or room.setpoint.identity() != proof.identity
                        or state is None or state.context.id != proof.context_id
                        or state.last_updated != proof.updated_at or target_value(state) != proof.target
                        or now is None or now < proof.captured_at or not 0 <= age < MAX_EVENT_AGE_MS):
                    self.status[room_id] = 'request_withdrawn'
                    continue
                transport = runtime._transport
                try:
                    await transport.async_setpoint(room_id, proof.target, duration_ms=room.setpoint_duration_ms)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.status[room_id] = 'request_unconfirmed'
                else:
                    if (room_id not in self.pending and epoch == self.epoch
                            and generation == runtime._generation and runtime._transport is transport):
                        self.status[room_id] = 'request_accepted'
                runtime._notify()
        finally:
            if self.tasks.get(room_id) is asyncio.current_task():
                self.tasks.pop(room_id, None)

    def withdraw(self):
        self.epoch += 1
        for room_id in self.pending.keys() | self.tasks.keys():
            self.status[room_id] = 'request_withdrawn'
        self.pending.clear()
        for task in tuple(self.tasks.values()):
            if not task.done():
                task.cancel()

    async def async_stop(self):
        tasks = tuple(self.tasks.values())
        self.withdraw()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
