"""Shared explicit SOURCE replacement through the existing native owner/link."""
from .const import DOMAIN
from .native_plan import native_entry_state
from .native_provisioning import source_from_selection, source_selection
from .product import configuration_snapshot


def profile_edit_available(entry, source):
    """Observe an existing private connection; never provision or qualify one."""
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


async def apply_profile_edit(hass, entry, source, connection, before, private_before,
                             proposed, room, document, validate_candidate, commit_candidate):
    """Compile/read back before stopping; save once, then use normal provisioning.

    Callbacks are synchronous validation/one atomic HA commit, not workers or IO.
    A saved intent or uncertain remote result is never rolled back or replayed.
    """
    from .room_program_apply import active_program_context
    from .controller_connection import async_refresh_controller_readback
    from .controller_setup_flow import async_connect_installation, CONTROLLER_ADDRESS, CONTROLLER_PASSWORD

    def guard(*, active=True):
        if (hass.config_entries.async_get_entry(entry.entry_id) is not entry
                or configuration_snapshot(entry) != before or native_entry_state(entry) != private_before):
            raise ValueError('setup_changed')
        if active:
            context = active_program_context(hass, entry)
            if context is None or context[0] != source or context[1] is not connection:
                raise ValueError('setup_changed')
        validate_candidate()

    guard()
    # Validate the complete HA SOURCE record too. Its predecessor and registry
    # bindings can exceed the storage budget even when the device descriptor fits.
    source_selection(proposed)
    if connection.client.journal['staged'] is not None:
        raise ValueError('controller_plan_pending')
    # Validate every room's schedule and the complete future wire budget first.
    await proposed.async_prospective_configuration(hass, entry, room, document)
    guard()
    await async_refresh_controller_readback(hass, entry, source, before, connection,
                                           private_expected=private_before)
    guard()
    client = connection.client
    if (client.journal['staged'] is not None or client.journal['accepted'] is None
            or not client.native_desired_matches(client.journal['accepted']['config'])):
        raise ValueError('controller_plan_pending')
    await connection.runtime.async_stop()
    guard(active=False)
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    if (state.get('v1_runtime') is not connection.runtime
            or state.get('v1_connection') is not connection or connection.runtime.enabled):
        raise ValueError('setup_changed')
    proposed.validate_prospective_native(hass, entry, room, document)
    address, password = entry.data[CONTROLLER_ADDRESS], entry.data[CONTROLLER_PASSWORD]
    commit_candidate()
    saved_private = native_entry_state(entry)
    try:
        if native_entry_state(entry) != saved_private:
            raise ValueError('setup_changed')
        await async_connect_installation(hass, entry, address, password)
    except Exception:
        # HA intent is saved; only explicit retry through the normal link may
        # continue. A timeout is not permission to restore the previous owner.
        raise ValueError('save_uncertain') from None
