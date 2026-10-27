"""Explicit complete room/profile replacement over the existing controller link."""
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

from .const import DOMAIN
from .native_plan import native_entry_state
from .native_provisioning import SOURCE_OPTION, source_from_selection, source_selection, propose_room_source_change
from .product import configuration_snapshot, commit_configuration, central_entry, INSTALLATION
from .v1_model import CONF_ENABLED
from .v1_wire import digest


# Re-export for existing callers; one transaction implementation owns both flows.
from .native_profile_apply import profile_edit_available, apply_profile_edit


async def save_active_profile(hass, entry, sub, old, token, settings, *, binding_identities=None):
    from .room_program_apply import active_program_context
    from .room_editor import prepare_room_edit, read_room
    context = active_program_context(hass, entry)
    if context is None or not profile_edit_available(entry, context[0]):
        raise ValueError('room_profile_change_required')
    source, connection = context
    before, private_before = configuration_snapshot(entry), native_entry_state(entry)
    if digest(before) != token:
        raise ValueError('setup_changed')
    # Existing SOURCE contract supports local programs only in this room editor.
    if old.schedule is not None or settings.get('program_source') != 'local' or settings.get('schedule_entity'):
        raise ValueError('program_source_conflict')
    candidate = prepare_room_edit(hass, entry, sub, old, settings, binding_identities=binding_identities)
    room, graph, identities = candidate()
    if room.comfort is not None and not connection.client.comfort_supported:
        raise ValueError('comfort_capability_unavailable')
    from .manual_target import is_manual_helper
    if room.contacts and not connection.client.contacts_supported:
        raise ValueError('contact_capability_unavailable')
    if is_manual_helper(room.setpoint) and not connection.client.manual_target_supported:
        raise ValueError('manual_target_capability_unavailable')
    document = graph.storage_document()
    proposed = propose_room_source_change(hass, entry, source, room, document)
    if proposed == source:
        raise ValueError('room_profile_change_required')

    def validate_candidate():
        if entry.subentries.get(sub.subentry_id) is not sub:
            raise ValueError('setup_changed')
        again, checked, checked_identities = candidate()
        if (room != again or identities != checked_identities or document != checked.storage_document()
                or proposed != propose_room_source_change(hass, entry, source, again, document)):
            raise ValueError('setup_changed')

    def commit_candidate():
        central = central_entry(entry)
        raw = {**deepcopy(dict(sub.data)), **room.as_dict()}
        from .room_comfort import clear_removed_comfort
        clear_removed_comfort(raw,room)
        if not is_manual_helper(room.setpoint):raw.pop('setpoint_duration_ms',None)
        if not room.contacts:
            raw.pop('contacts',None);raw.pop('contact_policy',None)
        replacement = replace(sub, data=MappingProxyType(raw), title=room.name)
        heat = {**deepcopy(dict(central.data)), 'draft': document, 'status': graph.readiness,
                'draft_digest': graph.digest, 'incomplete_group_ids': list(graph.incomplete_group_ids)}
        commit_configuration(hass, entry, before, data={**entry.data, INSTALLATION: heat},
            options={**entry.options, SOURCE_OPTION: source_selection(proposed), CONF_ENABLED: False},
            subentries={**entry.subentries, sub.subentry_id: replacement})
    await apply_profile_edit(hass, entry, source, connection, before, private_before,
        proposed, room, document, validate_candidate, commit_candidate)
    return read_room(hass, entry.entry_id, old.room_id)


def pending_profile_source(hass, entry):
    """Display/retry saved intent only; this is never admission or apply proof."""
    if entry.options.get(CONF_ENABLED, False):
        return None
    try:
        source = source_from_selection(entry)
        if source is None or source.predecessor is None or not profile_edit_available(entry, source):
            return None
        source.validate_native(hass, entry)
    except ValueError:
        return None
    connection = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get('v1_connection')
    client = getattr(connection, 'client', None)
    journal = getattr(client, 'journal', {})
    accepted = journal.get('accepted')
    if (accepted is not None and journal.get('staged') is None
            and accepted['config'].get('profile_digest') == source.policy.profile_digest):
        return None
    return source


async def retry_saved_profile(hass, entry, sub, old, token, settings, *, binding_identities=None):
    from .room_editor import read_room, prepare_room_edit
    from .controller_setup_flow import async_connect_installation, CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
    from .v1_heating_graph import actual_runtime_active
    source = pending_profile_source(hass, entry)
    if source is None or actual_runtime_active(hass, entry):
        raise ValueError('runtime_active')
    before = configuration_snapshot(entry)
    model = read_room(hass, entry.entry_id, old.room_id)
    if digest(before) != token or settings != model['settings']:
        raise ValueError('setup_changed')
    # Retry only the exact saved intent. A changed draft requires a separate edit
    # after the uncertain operation has been resolved by the normal link route.
    prepare_room_edit(hass, entry, sub, old, settings, binding_identities=binding_identities)()
    source.validate_native(hass, entry)
    try:
        await async_connect_installation(hass, entry,
            entry.data[CONTROLLER_ADDRESS], entry.data[CONTROLLER_PASSWORD])
    except Exception:
        raise ValueError('save_uncertain') from None
    return read_room(hass, entry.entry_id, old.room_id)
