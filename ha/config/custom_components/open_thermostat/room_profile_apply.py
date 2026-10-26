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


def profile_edit_available(entry, source):
    """Saved logical owner and existing private controller connection only."""
    from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD, CONTROLLER_ID
    from .controller_link import controller_address
    try:
        return (source_from_selection(entry) == source
            and entry.data.get(CONTROLLER_ID) == source.policy.controller_id
            and controller_address(entry.data.get(CONTROLLER_ADDRESS)) == entry.data.get(CONTROLLER_ADDRESS)
            and type(entry.data.get(CONTROLLER_PASSWORD)) is str
            and 1 <= len(entry.data[CONTROLLER_PASSWORD]) <= 128)
    except (ValueError, TypeError):
        return False


async def save_active_profile(hass, entry, sub, old, token, settings, *, binding_identities=None):
    from .room_program_apply import active_program_context, _guard
    from .room_editor import prepare_room_edit, read_room
    from .controller_connection import async_refresh_controller_readback
    from .controller_setup_flow import async_connect_installation, CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
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
    document = graph.storage_document()
    proposed = propose_room_source_change(hass, entry, source, room, document)
    if proposed == source:
        raise ValueError('room_profile_change_required')
    if connection.client.journal['staged'] is not None:
        raise ValueError('controller_plan_pending')
    # Validate the complete future wire budget and every room's schedule before
    # stopping the old owner or persisting any part of the user's desired edit.
    await proposed.async_prospective_configuration(hass, entry, room, document)
    _guard(hass, entry, sub, source, before, private_before)
    await async_refresh_controller_readback(hass, entry, source, before, connection,
                                           private_expected=private_before)
    _guard(hass, entry, sub, source, before, private_before)
    client = connection.client
    if (client.journal['staged'] is not None or client.journal['accepted'] is None
            or not client.native_desired_matches(client.journal['accepted']['config'])):
        raise ValueError('controller_plan_pending')
    again, checked, checked_identities = candidate()
    if (room != again or identities != checked_identities or document != checked.storage_document()
            or proposed != propose_room_source_change(hass, entry, source, again, document)):
        raise ValueError('setup_changed')
    # Stop through the current owner. Do not create a parallel worker or publish
    # direct MQTT. Failure after this await must never revive the previous owner.
    await connection.runtime.async_stop()
    if (hass.config_entries.async_get_entry(entry.entry_id) is not entry
            or configuration_snapshot(entry) != before or native_entry_state(entry) != private_before):
        raise ValueError('setup_changed')
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if (state.get('v1_runtime') is not connection.runtime
            or state.get('v1_connection') is not connection or connection.runtime.enabled):
        raise ValueError('setup_changed')
    again, checked, checked_identities = candidate()
    if room != again or identities != checked_identities or document != checked.storage_document():
        raise ValueError('binding_missing')
    proposed.validate_prospective_native(hass, entry, room, document)
    central = central_entry(entry)
    raw = {**deepcopy(dict(sub.data)), **room.as_dict()}
    replacement = replace(sub, data=MappingProxyType(raw), title=room.name)
    heat = {**deepcopy(dict(central.data)), 'draft': document, 'status': graph.readiness,
            'draft_digest': graph.digest, 'incomplete_group_ids': list(graph.incomplete_group_ids)}
    address, password = entry.data[CONTROLLER_ADDRESS], entry.data[CONTROLLER_PASSWORD]
    commit_configuration(hass, entry, before, data={**entry.data, INSTALLATION: heat},
        options={**entry.options, SOURCE_OPTION: source_selection(proposed), CONF_ENABLED: False},
        subentries={**entry.subentries, sub.subentry_id: replacement})
    saved_private = native_entry_state(entry)
    try:
        # Reuse normal authenticated HTTP/ETag provisioning, exact source checks,
        # entry-update reload, existing MQTT worker and verified applied readback.
        if native_entry_state(entry) != saved_private:
            raise ValueError('setup_changed')
        await async_connect_installation(hass, entry, address, password)
    except Exception:
        # Intent is saved; remote outcome may be uncertain. Never roll back the
        # room/profile/journal or retry a write/reboot automatically.
        raise ValueError('save_uncertain') from None
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
