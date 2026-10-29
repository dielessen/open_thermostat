"""Normal product presentation over the single existing native configuration owner."""
from copy import deepcopy
from types import MappingProxyType
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import __version__ as HA_VERSION

PRODUCT_CONFIG = "product_configuration"
PRODUCT_VERSION = 1
# The Home Assistant releases this integration version is tested on (CI and the
# release evidence in scripts/package_ha_release.py read this tuple).
SUPPORTED_HA_VERSIONS = ("2026.10.2", "2026.10.3", "2026.10.4")
# The oldest Home Assistant that works: its schema library (probatio 0.13, which
# every form uses) and the config entry save routine below match the tested
# releases from 2026.10.0 on. Newer releases are accepted while that save
# routine keeps the keywords used here (ha_version_supported checks them).
MINIMUM_HA_VERSION = "2026.10.0"
INSTALLATION = "installation_configuration"
_UPDATE_KEYWORDS = frozenset(("data", "options", "subentries", "title", "version"))


def _version_key(value):
    """(year, month, patch) of a Home Assistant version label, or None."""
    import re
    match = re.match(r"(\d{4})\.(\d{1,2})\.(\d+)", value) if type(value) is str else None
    return tuple(int(part) for part in match.groups()) if match else None


def ha_version_supported(hass=None, version=None):
    """True on Home Assistant MINIMUM_HA_VERSION or newer with the expected save routine.

    Configuration saves use Home Assistant's own one-step entry update
    (ConfigEntries._async_update_entry: data, options, subentries and title in
    one save). It is unchanged from 2026.8 to the tested 2026.10 releases; a
    newer release is accepted as long as it still takes the same keywords.
    """
    key = _version_key(HA_VERSION if version is None else version)
    if key is None or key < _version_key(MINIMUM_HA_VERSION):
        return False
    # The class, not a (patched) instance: this checks Home Assistant's own code.
    from homeassistant.config_entries import ConfigEntries
    update = getattr(ConfigEntries, "_async_update_entry", None)
    if not callable(update):
        return False
    import inspect
    try:
        parameters = inspect.signature(update).parameters
    except (TypeError, ValueError):
        return False
    return _UPDATE_KEYWORDS <= {name for name, item in parameters.items()
                                if item.kind is inspect.Parameter.KEYWORD_ONLY}


def is_product(entry):
    value = entry.data.get(PRODUCT_CONFIG)
    return type(value) is int and value == PRODUCT_VERSION


def heating_entries(entry):
    entries = [s for s in entry.subentries.values() if s.subentry_type == "heating"]
    stored = entry.data.get(INSTALLATION) if is_product(entry) else None
    if stored is not None:
        if entries or not isinstance(stored, dict):
            raise ValueError("single_central_owner")
        # Read-only view for existing validators; only entry.data owns these bytes.
        return [ConfigSubentry(data=MappingProxyType(stored), subentry_type="heating",
            subentry_id="installation", title="Installation", unique_id="central_heating")]
    return entries


def configuration_parts(entry):
    return [s for s in entry.subentries.values() if s.subentry_type != "heating"] + heating_entries(entry)


def central_entry(entry):
    entries = heating_entries(entry)
    if len(entries) > 1:
        raise ValueError("single_central_owner")
    return entries[0] if entries else None


def default_document():
    return {"draft_schema": 1, "central": {
        "weather_enabled": False, "outdoor_source": None,
        "outdoor_maximum_age_ms": 600000, "stale_policy": "block_normal_demand",
        "fixed_fallback_centi_c": None,
        "supply_limits": {"minimum_centi_c": 2000, "maximum_centi_c": 4500},
        "curve_centi_c": [2000 + 300 * i for i in range(9)]},
        "groups": [], "actuators": []}


def configuration_snapshot(entry):
    # Room/editor concurrency tokens are public digests of this snapshot. Never
    # turn an E32 access password into an offline password-checking oracle.
    # Device-management operations separately fence full private entry state;
    # ordinary room writes always preserve the current entry's credentials.
    data = dict(entry.data)
    data.pop("controller_password", None)
    return deepcopy((entry.title, data, dict(entry.options),
                     {key: sub.as_dict() for key, sub in entry.subentries.items()}))


def commit_configuration(hass, entry, before, **changes):
    """One pinned HA core Store transaction; never device I/O or activation."""
    if not ha_version_supported(hass):
        raise ValueError("setup_platform_unsupported")
    if (hass.config_entries.async_get_entry(entry.entry_id) is not entry
            or configuration_snapshot(entry) != before):
        raise ValueError("setup_changed")
    # Same guarded native transaction used for paired room/group storage.
    hass.config_entries._async_update_entry(entry, **changes)
