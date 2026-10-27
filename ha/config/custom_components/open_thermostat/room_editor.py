"""Single room editor over native room + installation configuration ownership."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from types import MappingProxyType
import logging
import math

import probatio as vol
from homeassistant.components import websocket_api
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import DOMAIN, CONF_TOPIC_PREFIX
from .product import central_entry, configuration_snapshot, commit_configuration, INSTALLATION
from .room_setup_flow import prepare_radiator_graph
from .schedule_compiler import compile_week
from .v1_config_flow import _room_candidate
from .v1_heating_graph import actual_runtime_active, selected_reference
from .v1_model import CONF_ENABLED, ROOM_GRAPH_DRAFT
from .v1_program import native_week, normalize_program
from .v1_wire import digest
from .week_planner import _target
from .v1_profile_c import review_room_targets
from .device_metadata import selected_device, MetadataUnavailable
from .room_contacts import ContactPolicy, select_contacts
from .manual_target import is_manual_helper, select_manual_helper, validate_manual_owner
from .room_comfort import select_comfort, clear_removed_comfort

_LOGGER = logging.getLogger(__name__)


def _choice(hass, item):
    """UI observation of HA state, never measurement age or physical readiness."""
    state = hass.states.get(item.entity_id)
    status = ('disabled' if item.disabled_by is not None else 'no_state' if state is None
              else state.state if state.state in ('unknown', 'unavailable') else 'available')
    if status == 'available' and item.entity_id.startswith('sensor.'):
        try:
            valid = (state.attributes.get('device_class') == 'temperature'
                     and state.attributes.get('unit_of_measurement') in ('°C', '°F')
                     and math.isfinite(float(state.state)))
        except (TypeError, ValueError, OverflowError):
            valid = False
        if not valid:
            status = 'invalid_temperature'
    result = {'value': item.entity_id,
            'label': state.name if state else item.name or item.original_name or item.entity_id,
            'status': status, 'identity': {'platform': item.platform, 'unique_id': item.unique_id}}
    if item.entity_id.startswith('sensor.'):
        result['temperature_role'] = ('diagnostic' if item.entity_category == EntityCategory.DIAGNOSTIC
                                      else 'unreviewed')
    return result


def _temperature_source_review(hass, reference, selection):
    # Native metadata only: no broker request, state sample, pin or admission.
    reason, status = 'original_report_required', 'unreviewed'
    item = er.async_get(hass).async_get(selection)
    if selection.startswith('unresolved:') or item is None or item.disabled_by is not None:
        reason, status = 'binding_unavailable', 'unavailable'
    else:
        if item.entity_category == EntityCategory.DIAGNOSTIC:
            reason, status = 'diagnostic_entity', 'review_required'
        try:
            metadata = selected_device(hass, reference.as_dict())
        except (MetadataUnavailable, TypeError, AttributeError, KeyError):
            pass  # Missing/malformed native metadata cannot break the room editor.
        else:
            if metadata.sensor_property == 'device_temperature':
                reason, status = 'internal_device_temperature', 'review_required'
    return {'status': status, 'reason': reason, 'scope': 'native_entity_metadata_only',
            'authorizes_control': False}


def _guard(hass, entry, sub, token):
    current, current_sub, room = _target(hass, entry.entry_id, sub.data['room_id'])
    if current is not entry or current_sub is not sub or digest(configuration_snapshot(entry)) != token:
        raise ValueError('setup_changed')
    if entry.options.get(CONF_ENABLED, False) or actual_runtime_active(hass, entry):
        raise ValueError('runtime_active')
    if room.binding_mode != ROOM_GRAPH_DRAFT or (room.setpoint is not None and not is_manual_helper(room.setpoint)):
        raise ValueError('advanced_room_required')
    return room


def read_room(hass, entry_id, room_id):
    entry, sub, room = _target(hass, entry_id, room_id)
    central = central_entry(entry)
    graph = central.data['draft'] if central else {'actuators': [], 'groups': []}
    own = [a for a in graph['actuators'] if a['room_id'] == room_id]
    groups = {g['group_id']: g for g in graph['groups']}
    supported = (room.binding_mode == ROOM_GRAPH_DRAFT and (room.setpoint is None or is_manual_helper(room.setpoint))
        and bool(own) and len({a['group_id'] for a in own}) == 1
        and all(a['profile'] == 'trv_room_setpoint' and groups[a['group_id']]['emitter'] == 'radiator' for a in own))
    registry = er.async_get(hass)
    choices = {d: [] for d in ('sensor', 'climate', 'schedule', 'binary_sensor', 'input_number', 'person')}
    def entity(ref):
        domain = ref['entity_id'].split('.')[0]
        resolved = registry.async_get_entity_id(domain, ref['platform'], ref['unique_id'])
        item = registry.async_get(resolved) if resolved else None
        if item is not None and item.disabled_by is None and item.platform != DOMAIN:
            choice = _choice(hass, item)
        else:
            # A UI-only marker is deliberately not a real entity ID. Retain the
            # broken selection until the user replaces/removes it; never let an
            # unrelated entity reusing its old ID silently inherit the binding.
            choice = {'value': 'unresolved:' + digest(ref), 'label': ref['entity_id'],
                      'status': 'disabled' if item else 'identity_changed' if registry.async_get(ref['entity_id']) else 'missing'}
        if domain in choices and not any(x['value'] == choice['value'] for x in choices[domain]):
            choices[domain].append(choice)
        return choice['value']
    for item in registry.entities.values():
        domain = item.entity_id.split('.')[0]
        if domain not in choices or item.disabled_by is not None or item.platform == DOMAIN:
            continue
        state = hass.states.get(item.entity_id)
        device_class = state.attributes.get('device_class') if state else None
        device_class = device_class or item.device_class or item.original_device_class
        if domain == 'sensor' and device_class != 'temperature':
            continue
        if domain == 'binary_sensor' and device_class not in ('window','door','opening','garage_door'):
            continue
        if domain == 'input_number' and (item.platform != 'input_number' or state is None
                or state.attributes.get('unit_of_measurement') not in ('°C','°F')):
            continue
        choices[domain].append(_choice(hass, item))
    temperature = entity(room.temperature.as_dict())
    radiators = [entity(a['output']) for a in own]
    schedule = entity(room.schedule.as_dict()) if room.schedule else ''
    manual_target = entity(room.setpoint.as_dict()) if room.setpoint else ''
    presence_entity = entity(room.presence.as_dict()) if room.presence else ''
    contact_entities = [entity(c.entity.as_dict()) for c in room.contacts]
    if room.window is not None:
        contact_entities.append(entity(room.window.as_dict()))
    for values in choices.values():
        values.sort(key=lambda x: (x['label'].casefold(), x['value']))
    from .room_program_apply import active_program_context
    program_context = active_program_context(hass, entry) if supported else None
    active = entry.options.get(CONF_ENABLED, False) or actual_runtime_active(hass, entry)
    program_only = active and program_context is not None and room.schedule is None
    from .room_profile_apply import profile_edit_available, pending_profile_source
    profile_editable = bool(program_only and profile_edit_available(entry, program_context[0]))
    profile_pending = pending_profile_source(hass, entry) is not None
    apply_pending = profile_pending
    if program_only:
        client = program_context[1].client
        accepted = client.journal['accepted']
        apply_pending = (not client.current_native_room_state_verified or accepted is None
                         or client.journal['staged'] is not None
                         or not client.native_desired_matches(accepted['config']))
    runtime = hass.data.get(DOMAIN, {}).get(entry_id, {}).get('v1_runtime')
    measurement = (runtime.measurement_status(room_id) if callable(getattr(runtime, 'measurement_status', None))
                   else {'status': 'inactive', 'report_profile_configured': False,
                         'sample_age_ms': None, 'usable': False})
    actuator_review = review_room_targets(hass, room, radiators)
    originals = (runtime.actuator_report_status(room_id)
                 if callable(getattr(runtime, 'actuator_report_status', None)) else {})
    for actuator in actuator_review['actuators']:
        if actuator['entity_id'] in originals:
            actuator['original_report'] = originals[actuator['entity_id']]
    return {'entry_id': entry_id, 'room_id': room_id, 'token': digest(configuration_snapshot(entry)),
        'status_identity':{'entry_id':entry_id,'room_id':room_id},
        'measurement': measurement,
        'manual_target_status': (runtime.manual_target_status(room_id)
            if callable(getattr(runtime,'manual_target_status',None)) else None),
        'contact_status_entity': registry.async_get_entity_id('climate',DOMAIN,
            f"{entry.data.get(CONF_TOPIC_PREFIX,'')}_room_{room_id}_climate"),
        'contact_status': (runtime.context_source_status(room_id).get('contacts')
            if room.contacts and callable(getattr(runtime,'context_source_status',None)) else None),
        'temperature_source_review': _temperature_source_review(hass, room.temperature, temperature),
        'rooms': [{'room_id': s.data['room_id'], 'name': s.title} for s in entry.subentries.values() if s.subentry_type == 'zone'],
        'choices': choices, 'time_zone': hass.config.time_zone, 'maximum_blocks': 28,
        'actuator_target_review': actuator_review,
        'supported': supported, 'editable': supported and not profile_pending and (not active or program_only),
        'program_only': program_only, 'apply_pending': apply_pending,
        'profile_editable': profile_editable, 'profile_apply_pending': profile_pending,
        'settings': {'name': room.name, 'emitter': 'radiator' if supported else 'unsupported',
            'temperature_entity': temperature, 'radiator_entities': radiators,
            'contact_entities': contact_entities,
            'contact_policy': (room.contact_policy or ContactPolicy()).as_dict(),
            'setpoint_entity': manual_target, 'setpoint_duration_ms': room.setpoint_duration_ms,
            'comfort': dict(room.comfort) if room.comfort is not None else None, 'presence_entity':presence_entity,
            'base_centi_c': room.base_centi_c, 'minimum_centi_c': room.minimum_target_centi_c,
            'maximum_centi_c': room.maximum_target_centi_c, 'maximum_age_ms': room.maximum_age_ms,
            'program_source': 'helper' if room.schedule else 'local',
            'schedule_entity': schedule,
            'week': normalize_program(room.week_program or {})}}


def prepare_room_edit(hass, entry, sub, old, settings, *, confirm_source_change=False, binding_identities=None):
    """Validate a prospective whole-room edit without mutating the HA entry.

    Return a revalidation callable sharing the proposed actuator IDs. Callers
    must fence their entry/owner and invoke it again after their final await.
    This prepares intent only; it never stops a runtime or selects a source.
    """
    entry_id, room_id = entry.entry_id, old.room_id
    required = {'name', 'emitter', 'temperature_entity', 'radiator_entities', 'base_centi_c',
        'minimum_centi_c', 'maximum_centi_c', 'maximum_age_ms', 'program_source', 'schedule_entity', 'week'}
    contact_keys={'contact_entities','contact_policy'}
    target_keys={'setpoint_entity','setpoint_duration_ms'}
    comfort_keys={'comfort','presence_entity'}
    optional=(contact_keys,target_keys,comfort_keys)
    if (type(settings) is not dict or not required<=settings.keys()
            or not settings.keys()<=required|contact_keys|target_keys|comfort_keys
            or any(group&settings.keys() and not group<=settings.keys() for group in optional)):
        raise ValueError('setup_invalid')
    edit_target=target_keys<=settings.keys()
    edit_comfort=comfort_keys<=settings.keys()
    if edit_target and (type(settings['setpoint_entity']) is not str
            or settings['setpoint_entity'].startswith('unresolved:')
            or type(settings['setpoint_duration_ms']) is not int or not 60000<=settings['setpoint_duration_ms']<=43200000):
        raise ValueError('invalid_manual_target')
    contacts=settings.get('contact_entities')
    edit_contacts=contact_keys<=settings.keys()
    policy=ContactPolicy.from_dict(settings['contact_policy']) if edit_contacts else old.contact_policy
    if settings['emitter'] != 'radiator':
        raise ValueError('emitter_not_available')
    if settings['program_source'] not in ('local', 'helper'):
        raise ValueError('program_source_conflict')
    changed_source = bool(old.schedule) != (settings['program_source'] == 'helper')
    if changed_source and confirm_source_change is not True:
        raise ValueError('confirm_program_source_change')
    ids = settings['radiator_entities']
    if type(ids) is not list or not 1 <= len(ids) <= 8 or not all(type(x) is str for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('select_radiators')
    for k in ('base_centi_c', 'minimum_centi_c', 'maximum_centi_c', 'maximum_age_ms'):
        if type(settings[k]) is not int:
            raise ValueError('invalid_integer_or_bounds')
    if not 1000 <= settings['maximum_age_ms'] <= 86400000:
        raise ValueError('invalid_integer_or_bounds')
    if not isinstance(settings['name'], str) or not settings['name'].strip() or len(settings['name']) > 80:
        raise ValueError('invalid_name')
    if type(settings['temperature_entity']) is not str or type(settings['schedule_entity']) is not str:
        raise ValueError('binding_missing')
    if any(x.startswith('unresolved:') for x in [settings['temperature_entity'], *ids, settings['schedule_entity']]):
        raise ValueError('binding_missing')
    central = central_entry(entry)
    own = [a for a in central.data['draft']['actuators'] if a['room_id'] == room_id] if central else []
    old_refs = [old.temperature.as_dict(), *[a['output'] for a in own]]
    if old.schedule:
        old_refs.append(old.schedule.as_dict())
    old_refs.extend(c.entity.as_dict() for c in old.contacts)
    if old.window:
        old_refs.append(old.window.as_dict())
    if old.setpoint:
        old_refs.append(old.setpoint.as_dict())
    if old.presence:
        old_refs.append(old.presence.as_dict())
    if not read_room(hass, entry_id, room_id)['supported']:
        raise ValueError('advanced_room_required')
    group_id, actuator_ids = own[0]['group_id'], {}
    def candidate():
        radiators = [selected_reference(hass, x, ('climate',)) for x in ids]
        helper = settings['schedule_entity'] if settings['program_source'] == 'helper' else None
        if settings['program_source'] == 'helper' and not helper:
            raise ValueError('binding_missing')
        room = _room_candidate(hass, entry, {'name': settings['name'].strip(), 'temperature_entity': settings['temperature_entity'],
            'binding_mode': ROOM_GRAPH_DRAFT, 'base_centi_c': settings['base_centi_c'],
            'minimum_target_temperature': settings['minimum_centi_c'] / 100,
            'maximum_target_temperature': settings['maximum_centi_c'] / 100,
            'maximum_age_ms': settings['maximum_age_ms'], 'schedule_entity': helper, 'program_action': 'remove_week'}, sub,
            check_ownership=False)
        week = normalize_program(settings['week'], room.minimum_target_centi_c, room.maximum_target_centi_c)
        if helper and any(week.values()):
            raise ValueError('program_source_conflict')
        room = replace(room, week_program=None if helper else week)
        # Existing clients cannot silently erase context they cannot edit.
        selected_contacts=old.contacts
        legacy_window=old.window
        if edit_contacts:
            selected_contacts=select_contacts(hass,contacts);legacy_window=None
        comfort=old.comfort
        room=replace(room,contacts=selected_contacts,contact_policy=policy if selected_contacts else None,
                     comfort=comfort,window=legacy_window,presence=old.presence)
        selected_target = (select_manual_helper(hass,settings['setpoint_entity']) if settings['setpoint_entity'] else None) if edit_target else old.setpoint
        duration = settings['setpoint_duration_ms'] if edit_target else old.setpoint_duration_ms
        room=replace(room,setpoint=selected_target,setpoint_duration_ms=duration)
        if edit_comfort:
            room=select_comfort(hass,room,settings['comfort'],settings['presence_entity'])
        validate_manual_owner(hass,entry,room)
        room=type(room).from_dict(room.as_dict())
        # Validate ownership against this complete prospective room/graph, so
        # replacing this room's deleted old device does not require resolving it.
        # No configured entry is mutated; every other room/output is still checked.
        parsed = prepare_radiator_graph(hass, entry, room, central, radiators, group_id, actuator_ids, replace_room=True)
        refs = [room.temperature, room.schedule, room.setpoint, room.window, room.presence,*(c.entity for c in room.contacts)]
        identities = [r.as_dict() for r in refs if r] + radiators
        if binding_identities is not None:
            expected = {r['entity_id']: {'platform': r['platform'], 'unique_id': r['unique_id']} for r in identities}
            if binding_identities != expected:
                raise ValueError('binding_missing')
        else:
            # Backward compatible clients have no explicit selection identity.
            # An unchanged ID must keep its original identity, even if registry
            # deletion/recreation happened before this save began.
            for ref in identities:
                for previous in old_refs:
                    if (ref['entity_id'] == previous['entity_id']
                            and (ref['platform'], ref['unique_id']) != (previous['platform'], previous['unique_id'])):
                        raise ValueError('binding_missing')
        return room, parsed, identities
    return candidate


async def save_room(hass, entry_id, room_id, token, settings, *, confirm_source_change=False, binding_identities=None):
    entry, sub, current_room = _target(hass, entry_id, room_id)
    from .room_profile_apply import pending_profile_source, retry_saved_profile
    if pending_profile_source(hass, entry) is not None:
        return await retry_saved_profile(hass, entry, sub, current_room, token, settings,
            binding_identities=binding_identities)
    if entry.options.get(CONF_ENABLED, False) or actual_runtime_active(hass, entry):
        from .room_program_apply import save_active_program
        return await save_active_program(hass, entry, sub, current_room, token, settings,
                                         binding_identities=binding_identities)
    old = _guard(hass, entry, sub, token)
    before = configuration_snapshot(entry)
    candidate = prepare_room_edit(hass, entry, sub, old, settings,
        confirm_source_change=confirm_source_change, binding_identities=binding_identities)
    room, parsed, identities = candidate()
    start = dt_util.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    await hass.async_add_executor_job(compile_week, native_week(room.week_program or {}), room.base_centi_c,
        hass.config.time_zone, int(start.timestamp()), int((start + timedelta(days=15)).timestamp()))
    _guard(hass, entry, sub, token)
    again, checked, current_identities = candidate()
    if identities != current_identities or room != again or parsed.storage_document() != checked.storage_document():
        raise ValueError('binding_missing')
    raw = {**deepcopy(dict(sub.data)), **room.as_dict()}
    clear_removed_comfort(raw,room)
    if not is_manual_helper(room.setpoint):raw.pop('setpoint_duration_ms',None)
    if not room.contacts:
        raw.pop('contacts',None);raw.pop('contact_policy',None)
    if room.week_program is None:
        raw.pop('week_program', None)
    replacement = replace(sub, data=MappingProxyType(raw), title=room.name)
    central = central_entry(entry)
    heat = {**deepcopy(dict(central.data)), 'draft': parsed.storage_document(), 'status': parsed.readiness,
        'draft_digest': parsed.digest, 'incomplete_group_ids': list(parsed.incomplete_group_ids)}
    commit_configuration(hass, entry, before, data={**entry.data, INSTALLATION: heat},
        subentries={**entry.subentries, sub.subentry_id: replacement})
    return read_room(hass, entry_id, room_id)


@websocket_api.websocket_command({vol.Required('type'): 'open_thermostat/room/get', vol.Required('entry_id'): str, vol.Required('room_id'): str})
@websocket_api.require_admin
@callback
def ws_room_get(hass, connection, msg):
    try:
        result = read_room(hass, msg['entry_id'], msg['room_id'])
    except (KeyError, ValueError):
        connection.send_error(msg['id'], 'room_changed', 'Room settings are unavailable')
    else:
        connection.send_result(msg['id'], result)


@websocket_api.websocket_command({vol.Required('type'): 'open_thermostat/room/save', vol.Required('entry_id'): str,
    vol.Required('room_id'): str, vol.Required('token'): vol.Match(r'^[a-f0-9]{64}$'),
    vol.Required('settings'): dict, vol.Optional('confirm_source_change', default=False): bool,
    vol.Optional('binding_identities'): dict})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_room_save(hass, connection, msg):
    try:
        result = await save_room(hass, msg['entry_id'], msg['room_id'], msg['token'], msg['settings'],
            confirm_source_change=msg['confirm_source_change'], binding_identities=msg.get('binding_identities'))
    except (KeyError, ValueError) as err:
        code = str(err) if isinstance(err, ValueError) else 'setup_invalid'
        connection.send_error(msg['id'], code,
            'Room application was not confirmed; reload before retrying' if code == 'save_uncertain' else 'Room was not saved')
    except Exception:
        _LOGGER.exception('Room save could not be confirmed')
        connection.send_error(msg['id'], 'save_uncertain', 'Reload saved room before retrying')
    else:
        connection.send_result(msg['id'], result)


@websocket_api.websocket_command({vol.Required('type'): 'open_thermostat/room/device_metadata',
    vol.Required('entry_id'): str, vol.Required('room_id'): str,
    vol.Required('token'): vol.Match(r'^[a-f0-9]{64}$')})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_room_device_metadata(hass, connection, msg):
    """Observe only saved room bindings; never accepts topics or arbitrary IDs."""
    from .device_metadata import async_read_selected_metadata, MetadataUnavailable
    try:
        entry, sub, room = _target(hass, msg['entry_id'], msg['room_id'])
        if digest(configuration_snapshot(entry)) != msg['token']:
            raise MetadataUnavailable('setup_changed')
        central = central_entry(entry)
        own = [a for a in central.data['draft']['actuators'] if a['room_id'] == room.room_id] if central else []
        if not 1 <= len(own) <= 8 or any(a['profile'] != 'trv_room_setpoint' for a in own):
            raise MetadataUnavailable('device_metadata_unavailable')
        result = await async_read_selected_metadata(hass, entry,
            [room.temperature.as_dict(), *[a['output'] for a in own]])
    except MetadataUnavailable as err:
        connection.send_error(msg['id'], str(err), 'Device information could not be verified')
    except Exception:
        connection.send_error(msg['id'], 'device_metadata_unavailable', 'Device information is unavailable')
    else:
        connection.send_result(msg['id'], result)
