"""Shared prospective comfort selection; no source selection or device IO."""
from dataclasses import replace
from .v1_model import RoomBinding, EntityReference


def select_comfort(hass, room, profile, presence_entity):
    from .v1_heating_graph import selected_reference
    if (type(presence_entity) is not str or presence_entity.startswith('unresolved:')
            or (profile is None and presence_entity)
            or (profile is not None and (type(profile) is not dict
                or set(profile)!={'away_centi_c','frost_centi_c','temporary_ms'}))):
        raise ValueError('invalid_comfort_selection')
    if profile is None and room.window is not None:
        raise ValueError('comfort_window_requires_contacts')
    if profile is not None and profile!=room.comfort:
        from .native_plan import NATIVE_FROST_TARGET_CENTI_C
        if profile['frost_centi_c']!=NATIVE_FROST_TARGET_CENTI_C:
            raise ValueError('native_comfort_frost_profile')
    presence=(EntityReference.from_dict(selected_reference(hass,presence_entity,('person',)))
              if presence_entity else None)
    candidate=replace(room,comfort=profile,presence=presence,
                      window=room.window if profile is not None else None)
    return RoomBinding.from_dict(candidate.as_dict())


def clear_removed_comfort(raw, room):
    if room.comfort is None:
        for key in ('comfort','presence','window'):
            raw.pop(key,None)
