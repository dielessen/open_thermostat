"""Retire legacy hub identities that a modern-mode E32 never feeds.

Modern firmware publishes native v1 topics only, so these entities would stay
unavailable or frozen forever. Disable (never delete) their registry records:
Recorder history survives and user choices are left alone.
"""
from homeassistant.helpers import entity_registry as er


def legacy_unique_ids(prefix):
    from .binary_sensor import BOILER_STATES
    from .sensor import HUB_METRICS
    ids = {f"{prefix}_hub_connected", f"{prefix}_hub_dhw_capabilities",
           f"{prefix}_hub_rtc_temperature"}  # E32 has no RTC temperature sensor.
    ids.update(f"{prefix}_hub_{metric}" for metric in HUB_METRICS["ems_status"])
    ids.update(f"{prefix}_hub_{state}" for state in BOILER_STATES)
    return ids


def retire_legacy_entities(hass, entry, prefix):
    registry = er.async_get(hass)
    retired = legacy_unique_ids(prefix)
    for record in er.async_entries_for_config_entry(registry, entry.entry_id):
        if record.unique_id in retired and record.disabled_by is None:
            registry.async_update_entity(record.entity_id,
                                         disabled_by=er.RegistryEntryDisabler.INTEGRATION)
