"""Explicit room-program edit over the existing native owner and reload lifecycle.

Hardware/profile migration is a separate operation. This module can change only
name, base and local week, inside the selected source's unchanged room bounds.
"""
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

from homeassistant.exceptions import ConfigEntryError
from homeassistant.util import dt as dt_util

from .product import configuration_snapshot, commit_configuration
from .native_plan import NativePlanSource, native_entry_state
from .v1_model import CONF_ENABLED, MODE_SHADOW, integration_mode
from .v1_program import normalize_program


def active_program_context(hass, entry):
    """Observe an already selected/validated native worker, never activate one."""
    from . import _selected_native_plan_source
    from .controller_connection import _connection
    if integration_mode(entry) != MODE_SHADOW or entry.options.get(CONF_ENABLED) is not True:
        return None
    try:
        source = _selected_native_plan_source(entry)
        if not isinstance(source, NativePlanSource) or not source.policy.week_reviewed:
            return None
        source.validate_native(hass, entry)
    except (ValueError, ConfigEntryError):
        return None
    connection = _connection(hass, entry, source)
    return (source, connection) if connection is not None else None


def _guard(hass, entry, sub, source, public_before, private_before):
    from .week_planner import _target
    current, current_sub, _ = _target(hass, entry.entry_id, sub.data['room_id'])
    context = active_program_context(hass, entry)
    if (current is not entry or current_sub is not sub
            or configuration_snapshot(entry) != public_before
            or native_entry_state(entry) != private_before
            or context is None or context[0] != source):
        raise ValueError('setup_changed')
    return context[1]


async def save_active_program(hass, entry, sub, old, token, settings, *, binding_identities=None):
    from .room_editor import read_room
    from .v1_wire import digest
    from .v1_mqtt import async_room_schedule
    from .compact_schedule import compact_schedule
    from .controller_connection import async_synchronise_controller_plan
    context = active_program_context(hass, entry)
    if context is None:
        raise ValueError('runtime_active')
    source, connection = context
    before, private_before = configuration_snapshot(entry), native_entry_state(entry)
    if digest(before) != token:
        raise ValueError('setup_changed')
    model = read_room(hass, entry.entry_id, old.room_id)
    saved = model['settings']
    if not model['supported'] or old.schedule is not None or saved['program_source'] != 'local':
        raise ValueError('advanced_room_required')
    if type(settings) is not dict or set(settings) != set(saved):
        raise ValueError('setup_invalid')
    for field in set(saved) - {'name', 'base_centi_c', 'week'}:
        if settings[field] != saved[field]:
            raise ValueError('room_profile_change_required')
    if binding_identities is not None:
        ids = [saved['temperature_entity'], *saved['radiator_entities']]
        choices = {row['value']: row.get('identity') for rows in model['choices'].values() for row in rows}
        if binding_identities != {entity_id: choices.get(entity_id) for entity_id in ids}:
            raise ValueError('binding_missing')
    name, base = settings['name'], settings['base_centi_c']
    if type(name) is not str or not name.strip() or len(name) > 80:
        raise ValueError('invalid_name')
    if type(base) is not int or not old.minimum_target_centi_c <= base <= old.maximum_target_centi_c:
        raise ValueError('invalid_integer_or_bounds')
    week = normalize_program(settings['week'], old.minimum_target_centi_c, old.maximum_target_centi_c)
    candidate = replace(old, name=name.strip(), base_centi_c=base, week_program=week)
    if (not connection.client.native_plan_readback_ready
            or connection.client.journal['staged'] is not None):
        raise ValueError('controller_plan_pending')
    start = dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    # Compile the COMPLETE installation, then replace only this candidate's
    # program fields. No forged ConfigEntry, registry binding or source flags.
    try:
        config, _ = await source.async_configuration(hass, entry, start=start)
    except ValueError:
        _guard(hass, entry, sub, source, before, private_before)
        raise
    _guard(hass, entry, sub, source, before, private_before)
    schedule = await async_room_schedule(hass, candidate, start)
    _guard(hass, entry, sub, source, before, private_before)
    row = next(z for z in config['zones'] if z['zone_id'] == old.room_id)
    row.update(base_centi_c=base, schedule=compact_schedule(schedule) if schedule is not None else None)
    source.validate_plan(config)
    raw = {**deepcopy(dict(sub.data)), **candidate.as_dict()}
    replacement = replace(sub, data=MappingProxyType(raw), title=candidate.name)
    changed = replacement != sub
    _guard(hass, entry, sub, source, before, private_before)
    if changed:
        commit_configuration(hass, entry, before,
            subentries={**entry.subentries, sub.subentry_id: replacement})
    expected, private_expected = configuration_snapshot(entry), native_entry_state(entry)
    try:
        # The same entry listener owns the reload. An old ready worker must not
        # satisfy this save, even in the gap before the listener starts unloading.
        await async_synchronise_controller_plan(hass, entry, source, expected,
            private_expected=private_expected, previous_connection=connection if changed else None)
    except Exception:
        # HA may be saved and the remote commit may be uncertain. Do not blindly
        # roll either side back or turn ACK-only into an applied result.
        raise ValueError('save_uncertain') from None
    return read_room(hass, entry.entry_id, old.room_id)
