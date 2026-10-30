"""Native admin read-only Recorder export. No DB writes, files or extra service."""
from __future__ import annotations
import csv
from datetime import datetime, timezone, timedelta
from functools import partial
import io
import math
import voluptuous as vol
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import state_changes_during_period
from homeassistant.core import SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.service import async_register_admin_service
from .const import DOMAIN

KEY = DOMAIN + "_metrics_reports"
SERVICE = "export_metrics_csv"
MAX_ENTITIES, MAX_ROWS, MAX_BYTES = 64, 5000, 1048576
MAX_INTERVAL_DAYS = 31


def _rows(value):
    if type(value) is not int or not 1 <= value <= MAX_ROWS:
        raise vol.Invalid("limit must be an integer from 1 to 5000")
    return value


SCHEMA = vol.Schema({
    vol.Required("entry_id"): str, vol.Required("start"): str, vol.Required("end"): str,
    vol.Optional("entity_ids"): vol.All([str], vol.Length(min=1, max=MAX_ENTITIES)),
    vol.Optional("limit", default=1000): _rows,
    vol.Optional("include_units", default=False): bool,
})


@callback
def note_legacy_metrics(hass, entry_id):
    """Only actual receipt of old-schema numeric counters creates this issue."""
    ir.async_create_issue(
        hass, DOMAIN, f"legacy_metrics_history_{entry_id}",
        is_fixable=False, is_persistent=True, severity=ir.IssueSeverity.WARNING,
        translation_key="legacy_metrics_history",
    )


@callback
def note_metric_definition_migration(hass, entry_id):
    """An actual existing legacy registry identity needs explicit user remapping."""
    ir.async_create_issue(hass, DOMAIN, f"metrics_definition_v2_{entry_id}",
        is_fixable=False, is_persistent=True, severity=ir.IssueSeverity.WARNING,
        translation_key="metrics_definition_v2")


@callback
def note_room_definition_migration(hass, entry_id):
    """Only an existing legacy room identity triggers review; no DB migration."""
    ir.async_create_issue(hass, DOMAIN, f"room_model_v2_{entry_id}",
        is_fixable=False, is_persistent=True, severity=ir.IssueSeverity.WARNING,
        translation_key="room_model_v2")


@callback
def reconcile_migration_issues(hass, entry, prefix):
    """A native E32 entry: the three information items close once nothing they describe is left.

    - metrics_definition_v2: while an old <prefix>_hub_<metric> record of this
      entry remains (the stale-entity cleanup retires untouched ones; a record
      the user customised keeps it open);
    - room_model_v2: native mode has no legacy room heat estimates at all;
    - legacy_metrics_history: created again only when an old-format counter
      packet actually arrives (note_legacy_metrics).
    """
    from .sensor import VERSIONED_METRICS
    own = {record.unique_id for record in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
           if record.platform == DOMAIN}
    if not any(f"{prefix}_hub_{metric}" in own for metric in VERSIONED_METRICS):
        ir.async_delete_issue(hass, DOMAIN, f"metrics_definition_v2_{entry.entry_id}")
    ir.async_delete_issue(hass, DOMAIN, f"room_model_v2_{entry.entry_id}")
    ir.async_delete_issue(hass, DOMAIN, f"legacy_metrics_history_{entry.entry_id}")


def _utc(value):
    try:
        result = datetime.fromisoformat(value)
        if result.utcoffset() is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError) as err:
        raise HomeAssistantError("Explicit timezone-aware ISO timestamp required") from err


def _cell(value):
    """Keep true negative numeric states; quote spreadsheet-formula text."""
    text = str(value)
    try:
        numeric = math.isfinite(float(text))
    except (ValueError, OverflowError):
        numeric = False
    if not numeric and text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def owned_entities(hass, entry_id):
    return {item.entity_id: item for item in
            er.async_entries_for_config_entry(er.async_get(hass), entry_id)
            if item.platform == DOMAIN and item.disabled_by is None
            and item.domain in {"sensor", "binary_sensor", "climate"}}


def _definition(unique_id):
    if "_room_" in unique_id and "_radiator_" in unique_id:
        return ("bounded_room_model_v2;not_metered_heat_or_flow;no_legacy_backfill"
            if unique_id.endswith("_v2") else "legacy_room_estimate;unbounded_historic_definition_unproven")
    if unique_id.endswith("_v2"):
        return "isolated_observation_definition_v2;no_legacy_backfill;estimate_or_reported_not_meter"
    if "_hub_energy" in unique_id:
        return "nominal_modulation_estimate_not_meter;historic_definition_unproven"
    if unique_id.endswith("_hub_warm_water_usage"):
        return "integrated_reported_volume;historic_definition_unproven"
    if unique_id.endswith("_hub_burner_observed_time"):
        return "observed_reported_flame_time;not_independent_flame_detection"
    if unique_id.endswith("_hub_boiler_selected_flow_temperature"):
        return "boiler_reported_selection;not_controller_command"
    return "recorded_state;not_actuation_or_freshness_proof"


def _unit(unique_id):
    """Advisory native definition unit, NEVER the recorded state unit.

    HA users can configure unit conversions; unique IDs cannot certify the
    actual historical unit. Exported row units come only from recorded metadata.
    """
    if not unique_id.endswith("_v2"):
        return "", "unknown_historic_unit"
    if "_room_" in unique_id:
        for suffix, unit in (("radiator_heating_time_v2", "h"),
                             ("radiator_estimated_power_v2", "W"),
                             ("radiator_estimated_energy_v2", "kWh")):
            if unique_id.endswith("_"+suffix):
                return unit, "definition_v2"
    if "_hub_" in unique_id:
        key = unique_id.rsplit("_hub_", 1)[1][:-3]
        if key in {"energy", "energy_warm_water", "energy_heating", "energy_unattributed"}:
            return "kWh", "definition_v2"
        if key == "warm_water_usage":
            return "L", "definition_v2"
        if key == "warm_water_avg_flow":
            return "L/min", "definition_v2"
        if key == "burner_observed_time":
            return "s", "definition_v2"
    return "", "unknown_historic_unit"


def _recorded_unit(state, enabled):
    if not enabled:
        return "", "not_requested"
    value = state.attributes.get("unit_of_measurement")
    # Only a bounded known unit can leave the read-only history boundary.
    # No arbitrary attributes, formula text or private metadata are exported.
    if isinstance(value, str) and value in {"%", "°C", "°F", "K", "W", "kW", "Wh", "kWh", "MWh",
                 "L", "m³", "L/min", "m³/h", "h", "s", "min", "B", "kB",
                 "MB", "bar", "Pa", "kPa", "psi"}:
        return value, "recorded_unit"
    return "", "unknown_recorded_unit"


async def async_export(hass, data):
    entry_id = data["entry_id"]
    if entry_id not in hass.data.get(KEY, set()):
        raise HomeAssistantError("Entry is not loaded for metrics reporting")
    start, end = _utc(data["start"]), _utc(data["end"])
    if end <= start or end-start > timedelta(days=MAX_INTERVAL_DAYS) or end > datetime.now(timezone.utc)+timedelta(seconds=5):
        raise HomeAssistantError("Use a past nonempty interval of at most 31 days")
    owned = owned_entities(hass, entry_id)
    selected = tuple(data.get("entity_ids", sorted(owned)))
    if not selected or len(selected)>MAX_ENTITIES or len(set(selected))!=len(selected) or not set(selected)<=owned.keys():
        raise HomeAssistantError("Select up to 64 distinct enabled entities owned by this entry")
    try:
        recorder = get_instance(hass)
    except (KeyError, RuntimeError) as err:
        raise HomeAssistantError("Native Recorder is not loaded") from err
    limit = _rows(data.get("limit", 1000))
    # Immutable identities, not mutable request lists or a cached enabled flag.
    identities = {entity: (owned[entity].id, owned[entity].unique_id) for entity in selected}
    def recheck_owner():
        current = owned_entities(hass, entry_id)
        if (entry_id not in hass.data.get(KEY, set())
                or any(entity not in current or
                       (current[entity].id, current[entity].unique_id) != identity
                       for entity, identity in identities.items())):
            raise HomeAssistantError("Entity ownership or availability changed during export")
    rows, queried, truncated = [], [], False
    include_units = data.get("include_units", False)
    if type(include_units) is not bool:
        raise HomeAssistantError("include_units must be a boolean")
    # Native bounded read-only history. The default does not retrieve attributes.
    # Opt-in unit export reads them internally but only emits an allowlisted unit.
    for entity_id in selected:
        remaining = limit-len(rows)
        if not remaining:
            truncated = True
            break
        query = partial(state_changes_during_period, hass, start, end,
                        entity_id=entity_id, no_attributes=not include_units, limit=remaining+1,
                        include_start_time_state=False)
        try:
            history = await recorder.async_add_executor_job(query)
        except Exception:
            # No partial export or private database/SQL exception text in response.
            raise HomeAssistantError("Native Recorder history query failed") from None
        # Executor work yields to registry updates and integration unload.
        # Never return a partial export under replaced/disabled/unloaded owners.
        recheck_owner()
        states = history.get(entity_id, [])
        queried.append(entity_id)
        if len(states)>remaining:
            truncated=True
        for state in states[:remaining]:
            identity = owned[entity_id].unique_id
            rows.append((state.last_updated, entity_id, state.state, _definition(identity), *_recorded_unit(state, include_units)))
    rows.sort(key=lambda row: (row[0], row[1]))
    output=io.StringIO(newline="")
    writer=csv.writer(output)
    writer.writerow(("utc", "entity_id", "state", "definition_quality", "unit", "unit_basis"))
    written=0;byte_count=len(output.getvalue().encode("utf-8"))
    for time, entity, state, definition, unit, basis in rows:
        line=io.StringIO(newline="");csv.writer(line).writerow((time.astimezone(timezone.utc).isoformat(), entity, _cell(state), definition, unit, basis))
        line_bytes=len(line.getvalue().encode("utf-8"))
        if byte_count+line_bytes>MAX_BYTES:
            truncated=True
            break
        output.write(line.getvalue());written+=1;byte_count+=line_bytes
    return {
        "csv": output.getvalue(), "rows": written, "truncated": truncated,
        "queried_entities": queried,
        "unqueried_entities": [entity for entity in selected if entity not in queried],
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "scope": "Recorder state changes only; no inferred continuity, start baseline or detail retention guarantee",
        "history_warning": "Old unversioned counter history is not corrected or certified by this export; no statistics were changed",
        "unit_scope": "Per-row recorded unit only when include_units=true; blank is not a zero/unit inference. Definition units are advisory; no conversion.",
        "definition_units": {entity: _unit(owned[entity].unique_id)[0] for entity in queried},
        "database_writes": False,
    }


@callback
def async_register_entry(hass, entry):
    loaded=hass.data.setdefault(KEY, set());loaded.add(entry.entry_id)
    if hass.services.has_service(DOMAIN,SERVICE):
        return
    async def action(call):
        return await async_export(hass,call.data)
    async_register_admin_service(hass,DOMAIN,SERVICE,action,schema=SCHEMA,supports_response=SupportsResponse.ONLY)


@callback
def async_unregister_entry(hass, entry_id):
    loaded=hass.data.get(KEY,set());loaded.discard(entry_id)
    if not loaded:
        hass.services.async_remove(DOMAIN,SERVICE)
        hass.data.pop(KEY,None)
