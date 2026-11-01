"""Optional tidy of the long entity IDs (Configure -> Advanced -> "Tidy entity IDs").

Early installations got entity IDs from a long device name of the project's test setup
("…_e32_regelaar_ketel_en_diagnose_…") or an older device name. The new IDs are the ones
Home Assistant itself would give these entities today (``async_regenerate_entity_id``: the
area, device and entity names and the user's own entity-ID settings), so there is no scheme of
our own to keep up.

Never automatic: the user sees every old -> new pair and where each entity is used, and
confirms. A rename goes through the entity registry (``async_update_entity(new_entity_id=)``),
which makes the recorder move the entity's history and long-term statistics to the new ID.
References in the user's automations, scripts, scenes, groups and dashboards are listed, never
edited; OpenThermostat's own dashboard follows the registry by itself. Skipped: entities the
user named (``name``), IDs the user chose (no known device prefix) and IDs whose target is taken.
The mapping is kept for 30 days, so the rename can be undone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import json
import re

from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify

from .const import DOMAIN, TEST_SETUP_DEVICE_NAMES

UNDO_DAYS = 30
STORE_VERSION = 1
PREVIEW_LINES = 40
_SUFFIX = re.compile(r"_\d+$")


@dataclass
class Rename:
    old: str
    new: str
    name: str
    used_in: list[str] = field(default_factory=list)


@dataclass
class Plan:
    renames: list[Rename]
    skipped: dict[str, str]  # entity_id -> why: "user_named" | "user_entity_id" | "target_taken"

    @property
    def unused(self) -> list[Rename]:
        return [r for r in self.renames if not r.used_in]


def _store(hass, entry_id):
    return Store(hass, STORE_VERSION, f"{DOMAIN}.entity_id_tidy.{entry_id}")


def _known_prefixes(hass, config_entry, entities) -> set[str]:
    """The object-ID starts an automatically given ID of this integration's entities can have:
    [area_]device name, old or new, for every device and area of the entry. Room entities of early
    installations carry the hub's area and long name, so all of them count for each entity."""
    devices, areas = dr.async_get(hass), ar.async_get(hass)
    names = {"openthermostat", *(slugify(n) for n in TEST_SETUP_DEVICE_NAMES)}
    area_ids = {e.area_id for e in entities}
    for device in dr.async_entries_for_config_entry(devices, config_entry.entry_id):
        names |= {slugify(n) for n in (device.name, device.name_by_user, getattr(device, "default_name", None)) if n}
        area_ids.add(device.area_id)
    area_slugs = {""} | {slugify(a.name) for i in area_ids if i and (a := areas.async_get_area(i)) is not None}
    return {f"{a}_{n}" if a else n for a in area_slugs for n in names if n}


def _generated(entity, prefixes) -> bool:
    object_id = entity.entity_id.split(".", 1)[1]
    return any(object_id == p or object_id.startswith(p + "_") for p in prefixes)


def _display_name(hass, entity) -> str:
    state = hass.states.get(entity.entity_id)
    return (state.attributes.get("friendly_name") if state else None) or entity.original_name or entity.entity_id


def references(hass, entity_id: str, dashboards=(), energy: str = "") -> list[str]:
    """Where an entity is used, read only: automations, scripts, scenes, groups (by their entity IDs)
    the user's dashboards (by title; ``dashboards`` from ``async_dashboard_texts``) and the Energy
    dashboard (``energy``: its preferences as text). The Energy dashboard does not follow a rename."""
    found = []
    for module, kind in (("automation", "automations_with_entity"), ("script", "scripts_with_entity"),
                         ("scene", "scenes_with_entity"), ("group", "groups_with_entity")):
        try:
            component = __import__(f"homeassistant.components.{module}", fromlist=[kind])
            found += getattr(component, kind)(hass, entity_id)
        except (ImportError, AttributeError, KeyError):
            continue
    pattern = re.compile(r"(?<![\w.])" + re.escape(entity_id) + r"(?!\w)")
    found += [f"dashboard: {title}" for title, text in dashboards if pattern.search(text)]
    if energy and pattern.search(energy):
        found.append("energy")
    return sorted(set(found))


async def async_energy_text(hass) -> str:
    """The Energy dashboard's preferences as text, read only ("" without the energy integration)."""
    try:
        from homeassistant.components.energy.data import async_get_manager
        manager = await async_get_manager(hass)
    except Exception:  # no energy integration in this installation
        return ""
    return json.dumps(manager.data or {})


async def async_dashboard_texts(hass) -> list[tuple[str, str]]:
    """(title, config as JSON text) of each of the user's dashboards, read only. OpenThermostat's own
    dashboard is left out: it is rebuilt from the registry after a rename."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:
        return []
    data = hass.data.get(LOVELACE_DATA)
    if data is None:
        return []
    texts = []
    for url_path, dashboard in data.dashboards.items():
        if url_path and url_path.startswith("open-thermostat"):
            continue
        try:
            config = await dashboard.async_load(False)
        except Exception:  # an empty or broken dashboard: nothing to scan
            continue
        meta = getattr(dashboard, "config", None) or {}
        texts.append((meta.get("title") or url_path or "Overview", json.dumps(config)))
    return texts


def _collapse_double(hass, registry, entity, new: str, reserved: set[str]) -> str:
    """A room device sits in an area of the same name ("Badkamer" in "Badkamer"): Home Assistant's own
    ID then repeats it (binary_sensor.badkamer_badkamer_heat_demand). Say it once."""
    devices, areas = dr.async_get(hass), ar.async_get(hass)
    device = devices.async_get(entity.device_id) if entity.device_id else None
    area_id = entity.area_id or (device.area_id if device else None)
    area = areas.async_get_area(area_id) if area_id else None
    if device is None or area is None:
        return new
    domain, object_id = new.split(".", 1)
    twice = slugify(area.name)
    if twice != slugify(device.name_by_user or device.name or "") or not (
            object_id == f"{twice}_{twice}" or object_id.startswith(f"{twice}_{twice}_")):
        return new
    return registry.async_get_available_entity_id(domain, object_id[len(twice) + 1:],
                                                  current_entity_id=entity.entity_id, reserved_entity_ids=reserved)


async def async_plan(hass, config_entry) -> Plan:
    """Every OpenThermostat entity whose ID Home Assistant would now give a different, free name."""
    dashboards = await async_dashboard_texts(hass)
    energy = await async_energy_text(hass)
    registry = er.async_get(hass)
    renames, skipped, reserved = [], {}, set()
    entries = sorted(er.async_entries_for_config_entry(registry, config_entry.entry_id), key=lambda e: e.entity_id)
    prefixes = _known_prefixes(hass, config_entry, entries)
    for entity in entries:
        if entity.name is not None:
            skipped[entity.entity_id] = "user_named"
            continue
        if not _generated(entity, prefixes):
            skipped[entity.entity_id] = "user_entity_id"
            continue
        new = _collapse_double(hass, registry, entity, registry.async_regenerate_entity_id(entity, reserved_entity_ids=reserved),
                               reserved)
        if new == entity.entity_id:
            continue
        if _SUFFIX.search(new) and not _SUFFIX.search(entity.entity_id):
            base = _SUFFIX.sub("", new)
            if base != entity.entity_id and (registry.async_get(base) or hass.states.get(base)):
                skipped[entity.entity_id] = "target_taken"
                continue
        reserved.add(new)
        renames.append(Rename(entity.entity_id, new, _display_name(hass, entity),
                              references(hass, entity.entity_id, dashboards, energy)))
    return Plan(renames, skipped)


def preview_text(plan: Plan, only_unused: bool) -> str:
    rows = plan.unused if only_unused else plan.renames
    lines = [f"- {r.old} → {r.new}" + (f"  (gebruikt in: {', '.join(r.used_in)})" if r.used_in else "")
             for r in rows[:PREVIEW_LINES]]
    if len(rows) > PREVIEW_LINES:
        lines.append(f"- … +{len(rows) - PREVIEW_LINES}")
    return "\n".join(lines) or "-"


async def async_apply(hass, config_entry, renames: list[Rename]) -> dict[str, str]:
    """Rename through the registry (history follows) and keep the mapping for undo. Returns new -> old."""
    registry = er.async_get(hass)
    done = {}
    for rename in renames:
        entity = registry.async_get(rename.old)
        if entity is None or entity.name is not None or registry.async_get(rename.new) is not None:
            continue  # changed since the preview: leave it
        try:
            registry.async_update_entity(rename.old, new_entity_id=rename.new)
        except ValueError:  # taken since the preview
            continue
        done[rename.new] = rename.old
    if done:
        store = _store(hass, config_entry.entry_id)
        previous = await store.async_load() or {}
        mapping = {**previous.get("mapping", {}), **done} if _fresh(previous) else done
        await store.async_save({"at": dt_util.utcnow().isoformat(), "mapping": mapping})
    return done


def _fresh(saved) -> bool:
    at = dt_util.parse_datetime(saved.get("at", "")) if saved else None
    return at is not None and dt_util.utcnow() - at <= timedelta(days=UNDO_DAYS)


async def async_undo_available(hass, config_entry) -> dict[str, str]:
    """new -> old for the last tidy, while it is at most UNDO_DAYS old and the new IDs still exist."""
    saved = await _store(hass, config_entry.entry_id).async_load()
    if not _fresh(saved):
        return {}
    registry = er.async_get(hass)
    return {new: old for new, old in saved.get("mapping", {}).items() if registry.async_get(new) is not None}


async def async_undo(hass, config_entry) -> dict[str, str]:
    """Rename back where the old ID is still free. Returns old -> new of what was undone."""
    registry = er.async_get(hass)
    undone = {}
    for new, old in (await async_undo_available(hass, config_entry)).items():
        if registry.async_get(old) is not None:
            continue
        try:
            registry.async_update_entity(new, new_entity_id=old)
        except ValueError:  # Home Assistant holds the old ID for something else now
            continue
        undone[old] = new
    await _store(hass, config_entry.entry_id).async_remove()
    return undone
