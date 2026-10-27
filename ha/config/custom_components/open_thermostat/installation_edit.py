"""Supported central edits through the normal active native plan transaction."""
from copy import deepcopy

import probatio as vol
from homeassistant.data_entry_flow import section

from .const import CONF_CREATE_DASHBOARD
from .native_form import retained_input_schema
from .native_plan import native_entry_state
from .native_profile_apply import apply_profile_edit, profile_edit_available
from .native_provisioning import SOURCE_OPTION, propose_room_source_change, source_selection
from .product import central_entry, commit_configuration, configuration_snapshot, is_product, INSTALLATION
from .room_program_apply import active_program_context
from .v1_heating_flow import central_schema, centi_c
from .v1_heating_graph import validated_graph
from .v1_model import CONF_ENABLED, RoomBinding


def installation_context(hass, entry):
    if not is_product(entry):
        return None
    context = active_program_context(hass, entry)
    return context if context is not None and profile_edit_available(entry, context[0]) else None


def prepare_installation_edit(hass, entry, user_input):
    """Change central limits and inherited radiator limits; keep all bindings.

    Weather/curve execution needs a different native contract. Existing curves
    are clipped to their new bounds, preserving order, rather than leaving an
    invalid stored curve after narrowing limits. Custom circuits stay exact.
    """
    if (type(user_input) is not dict or set(user_input)-{'name', CONF_CREATE_DASHBOARD, 'advanced'}
            or type(user_input.get(CONF_CREATE_DASHBOARD, False)) is not bool):
        raise ValueError('setup_invalid')
    if (type(user_input.get('name')) is not str or not user_input['name'].strip()
            or len(user_input['name'].strip()) > 80):
        raise ValueError('invalid_name')
    advanced = user_input.get('advanced', {})
    if type(advanced) is not dict or set(advanced)-{'minimum_supply_temperature', 'maximum_supply_temperature'}:
        raise ValueError('installation_native_settings_only')
    central = central_entry(entry)
    if central is None:
        raise ValueError('setup_changed')
    old = deepcopy(dict(central.data)['draft'])
    document = deepcopy(old)
    previous = old['central']['supply_limits']
    limits = {
        'minimum_centi_c': centi_c(advanced.get('minimum_supply_temperature', previous['minimum_centi_c']/100)),
        'maximum_centi_c': centi_c(advanced.get('maximum_supply_temperature', previous['maximum_centi_c']/100)),
    }
    if not 500 <= limits['minimum_centi_c'] < limits['maximum_centi_c'] <= 9000:
        raise ValueError('minimum_must_be_below_maximum')
    def bound_curve(owner):
        owner['curve_centi_c'] = [min(limits['maximum_centi_c'], max(limits['minimum_centi_c'], value))
                                 for value in owner['curve_centi_c']]
    document['central']['supply_limits'] = limits
    bound_curve(document['central'])
    for group in document['groups']:
        if group['emitter'] == 'radiator' and group['supply_limits'] == previous:
            group['supply_limits'] = deepcopy(limits)
    graph = validated_graph(hass, entry, document)
    # The current prospective API uses one explicit room replacement. Reuse an
    # unchanged real room as its anchor; every actual saved room is still checked.
    anchor = next((RoomBinding.from_dict(dict(sub.data)) for sub in entry.subentries.values()
                   if sub.subentry_type == 'zone'), None)
    if anchor is None:
        raise ValueError('setup_changed')
    return graph, anchor


async def save_active_installation(hass, entry, before, private_before, user_input):
    context = installation_context(hass, entry)
    if context is None:
        raise ValueError('setup_changed')
    source, connection = context
    if (configuration_snapshot(entry) != before or native_entry_state(entry) != private_before):
        raise ValueError('setup_changed')
    graph, anchor = prepare_installation_edit(hass, entry, user_input)
    document = graph.storage_document()
    proposed = propose_room_source_change(hass, entry, source, anchor, document)
    title = user_input['name'].strip()
    dashboard = user_input.get(CONF_CREATE_DASHBOARD, entry.options.get(CONF_CREATE_DASHBOARD, False))

    def validate_candidate():
        again, checked_anchor = prepare_installation_edit(hass, entry, user_input)
        if (again.storage_document() != document or anchor != checked_anchor
                or propose_room_source_change(hass, entry, source, checked_anchor, document) != proposed):
            raise ValueError('setup_changed')

    def commit_candidate():
        central = central_entry(entry)
        data = {**deepcopy(dict(central.data)), 'draft': document, 'status': graph.readiness,
                'draft_digest': graph.digest, 'incomplete_group_ids': list(graph.incomplete_group_ids)}
        options = {**entry.options, CONF_CREATE_DASHBOARD: dashboard}
        if proposed != source:
            options.update({SOURCE_OPTION: source_selection(proposed), CONF_ENABLED: False})
        commit_configuration(hass, entry, before, title=title,
            data={**entry.data, INSTALLATION: data}, options=options,
            subentries={key: sub for key, sub in entry.subentries.items() if sub.subentry_type != 'heating'})

    if proposed != source:
        await apply_profile_edit(hass, entry, source, connection, before, private_before,
            proposed, anchor, document, validate_candidate, commit_candidate)
        return 'installation_applied'
    # Name/dashboard changes need no device-settings write or new SOURCE. Use
    # the existing update listener and a fresh readback from its replacement worker.
    if title == entry.title and dashboard == entry.options.get(CONF_CREATE_DASHBOARD, False):
        return 'installation_saved'
    validate_candidate()
    commit_candidate()
    expected, private_expected = configuration_snapshot(entry), native_entry_state(entry)
    from .controller_connection import async_synchronise_controller_plan
    try:
        await async_synchronise_controller_plan(hass, entry, source, expected,
            private_expected=private_expected, previous_connection=connection)
    except Exception:
        raise ValueError('save_uncertain') from None
    return 'installation_applied'


async def active_installation_step(flow, user_input):
    entry = flow.config_entry
    if not hasattr(flow, '_central_active_before'):
        flow._central_active_before = configuration_snapshot(entry)
        flow._central_active_private = native_entry_state(entry)
    if (configuration_snapshot(entry) != flow._central_active_before
            or native_entry_state(entry) != flow._central_active_private
            or installation_context(flow.hass, entry) is None):
        return flow.async_abort(reason='setup_changed')
    errors = {}
    if user_input is not None:
        try:
            result = await save_active_installation(flow.hass, entry,
                flow._central_active_before, flow._central_active_private, user_input)
        except ValueError as error:
            code = str(error)
            if code == 'save_uncertain':
                return flow.async_abort(reason='setup_save_uncertain')
            if installation_context(flow.hass, entry) is None:
                return flow.async_abort(reason='setup_changed')
            errors['base'] = code if code in {'setup_changed', 'binding_missing', 'controller_plan_pending',
                'minimum_must_be_below_maximum', 'installation_native_settings_only', 'invalid_name'} else 'installation_limits_conflict'
        except Exception:
            return flow.async_abort(reason='setup_save_uncertain')
        else:
            return flow.async_abort(reason=result)
    document = dict(central_entry(entry).data)['draft']
    fields = central_schema(document, flow.hass)
    limits = {key: value for key, value in fields.schema.items()
              if str(key) in {'minimum_supply_temperature', 'maximum_supply_temperature'}}
    schema = vol.Schema({
        vol.Required('name', default=entry.title): str,
        vol.Optional(CONF_CREATE_DASHBOARD, default=entry.options.get(CONF_CREATE_DASHBOARD, False)): bool,
        vol.Optional('advanced'): section(vol.Schema(limits), {'collapsed': True}),
    })
    return flow.async_show_form(step_id='installation_connected',
        data_schema=retained_input_schema(flow, schema, user_input), errors=errors)
