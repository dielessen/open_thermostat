"""What removing the older Home Assistant rooms means for the E32 room plan.

An E32 room may use an entity of an older Home Assistant room (a zone
subentry of this integration) as a temperature source or as its setpoint
entity. Removing the older room deletes that entity, so before anything is
removed the E32 plan is changed:

- a reference moves to the entity the older room itself was built on (its
  temperature sensor, else one of its thermostats/valves; for the setpoint its
  setpoint entity), never to an entity of this integration;
- without such an entity the reference is dropped (the setpoint then follows
  the room's own week program). A room whose only source it was keeps that
  reference, because the E32 refuses a room without sources; it gets a Repairs
  note "Choose a temperature source for <room>". The room itself always stays,
  in the same state.

The older room's own thermostat (climate entity) is handed over to the
matching E32 room's thermostat: the user's name, icon and area move along
(only fields the room thermostat has not set itself) and the room thermostat
takes over the freed entity ID when its own one is still the generated one, so
dashboards, automations and voice assistants keep working.

Order (controller_setup_flow.async_link_room_plan): plan write (revision
checked, one re-read on 409) -> remove the older rooms -> hand over.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
import re

from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir
from homeassistant.util import slugify

from .const import CONF_TOPIC_PREFIX, DOMAIN
from .controller_link import ControllerLinkError, HeatingPlanRejected

SOURCE_DOMAINS = ("climate", "sensor")
SETPOINT_DOMAINS = ("climate", "input_number", "number")
CHOOSE_SOURCE_ISSUE = "e32_room_choose_source"
HANDOVER_WAIT = 5.0  # seconds for a removed entity's state to leave
_GENERATED = re.compile(r"(?P<base>.+?)(?:_(?P<n>[2-9]|[1-9][0-9]+))?")


@dataclass(frozen=True, slots=True)
class Change:
    """One reference of an E32 room to an entity of an older HA room."""

    room_id: str
    room_name: str
    field: str        # "source" or "setpoint"
    old: str
    new: str | None   # the replacement; None: dropped (or kept, see below)
    kept: bool = False  # the room's only source: the reference stays until the user chooses one


@dataclass(frozen=True, slots=True)
class Handover:
    """The older room's thermostat replaced by an E32 room's thermostat."""

    room_id: str
    room_name: str
    legacy_entity_id: str
    room_unique_id: str
    room_entity_id: str | None  # None: the room thermostat is not registered yet
    rename: bool


@dataclass(frozen=True, slots=True)
class Migration:
    changes: tuple
    handovers: tuple
    rooms: tuple  # (room_id, name) of every E32 room: they all stay

    def signature(self):
        """What the user confirmed; the apply step refuses a different outcome."""
        return (tuple((c.room_id, c.field, c.old, c.new, c.kept) for c in self.changes),
                tuple((h.room_id, h.legacy_entity_id, h.rename) for h in self.handovers))


def _own(item, entry):
    return item.config_entry_id == entry.entry_id and item.platform == DOMAIN


def zone_entities(hass, entry, zones):
    """entity_id -> zone subentry for this entry's own entities of the older rooms being removed."""
    from .e32_link import legacy_room_devices
    entities = er.async_get(hass)
    found = {}
    for zone in zones:
        devices = legacy_room_devices(hass, entry, [zone.data["room_id"]])
        items = [i for i in entities.entities.values() if i.config_subentry_id == zone.subentry_id]
        for device in devices:
            items += er.async_entries_for_device(entities, device.id, include_disabled_entities=True)
        for item in items:
            if _own(item, entry):
                found[item.entity_id] = zone
    return found


def _exists(hass, entity_id):
    return hass.states.get(entity_id) is not None or er.async_get(hass).async_get(entity_id) is not None


def _usable(hass, entry, entity_id, domains):
    """A replacement: exists, fits the field, and is not an entity of this integration."""
    if type(entity_id) is not str or entity_id.split(".", 1)[0] not in domains or not _exists(hass, entity_id):
        return False
    item = er.async_get(hass).async_get(entity_id)
    return item is None or not _own(item, entry)


def _candidates(zone, field):
    data = zone.data
    if field == "setpoint":
        return [data["setpoint"]["entity_id"]] if data.get("setpoint") else []
    found = [data["temperature"]["entity_id"]] if data.get("temperature") else []
    return found + [a["entity_id"] for a in data.get("actuators", [])]


def room_thermostat_unique_id(prefix, room_id):
    return f"{prefix}_e32_room_{room_id}_thermostat"


def _match_rooms(plan, zones, owned):
    """zone subentry id -> E32 room: the room that uses its entities, else the same id, else the same name."""
    matches, taken = {}, set()

    def unique(found):
        return found[0] if len(found) == 1 and found[0]["id"] not in taken else None
    for zone in sorted(zones, key=lambda z: z.subentry_id):
        def uses(room, zone=zone):
            ids = [s.get("id") for s in room.get("sources", []) if s.get("type") == "ha"]
            ids.append(room.get("setpoint_entity"))
            return any(owned.get(i) is zone for i in ids)
        rooms = plan["rooms"]
        room = (unique([r for r in rooms if uses(r)])
                or unique([r for r in rooms if r["id"] == zone.data.get("room_id")])
                or unique([r for r in rooms if str(r.get("name", "")).casefold() == zone.title.casefold()]))
        if room is not None:
            matches[zone.subentry_id] = room
            taken.add(room["id"])
    return matches


def generated_entity_id(hass, item):
    """True when a registry entry's entity ID is still the one Home Assistant generated."""
    device = dr.async_get(hass).async_get(item.device_id) if item.device_id else None
    names = []
    if item.has_entity_name and device is not None and device.name:
        names.append(device.name if not item.original_name else f"{device.name} {item.original_name}")
    if item.original_name:
        names.append(item.original_name)
    domain, object_id = item.entity_id.split(".", 1)
    match = _GENERATED.fullmatch(object_id)
    return match is not None and any(slugify(name) in (object_id, match["base"]) for name in names)


def plan_migration(hass, entry, plan, zones):
    """(the plan to write, or None when nothing changes; what happens) for removing these zones; no I/O."""
    owned = zone_entities(hass, entry, zones)
    candidate = deepcopy(plan)
    changes = []
    for room in candidate["rooms"]:
        name = room.get("name") or room["id"]
        sources, dropped = [], []
        for source in room.get("sources", []):
            zone = owned.get(source.get("id")) if source.get("type") == "ha" else None
            if zone is None:
                if source not in sources:
                    sources.append(source)
                continue
            new = next((e for e in _candidates(zone, "source") if _usable(hass, entry, e, SOURCE_DOMAINS)), None)
            if new is not None:
                replacement = {"type": "ha", "id": new}
                if replacement not in sources and replacement not in room["sources"]:
                    sources.append(replacement)
                changes.append(Change(room["id"], name, "source", source["id"], new))
            else:
                dropped.append(source)
        if not sources and dropped:
            # The E32 needs at least one source: keep it until the user chooses one.
            sources = dropped[:1]
            changes.append(Change(room["id"], name, "source", dropped[0]["id"], None, kept=True))
            dropped = dropped[1:]
        changes += [Change(room["id"], name, "source", s["id"], None) for s in dropped]
        if sources != room.get("sources", []):
            room["sources"] = sources
        setpoint = room.get("setpoint_entity")
        if setpoint and (zone := owned.get(setpoint)) is not None:
            new = next((e for e in _candidates(zone, "setpoint") if _usable(hass, entry, e, SETPOINT_DOMAINS)), None)
            room["setpoint_entity"] = new or ""
            changes.append(Change(room["id"], name, "setpoint", setpoint, new))
    entities = er.async_get(hass)
    prefix = entry.data[CONF_TOPIC_PREFIX]
    still_used = {s.get("id") for r in candidate["rooms"] for s in r.get("sources", [])} | {
        r.get("setpoint_entity") for r in candidate["rooms"]}
    handovers = []
    for zone_id, room in sorted(_match_rooms(plan, zones, owned).items()):
        legacy = next((i for e, z in owned.items() if z.subentry_id == zone_id
                       and (i := entities.async_get(e)) is not None and i.domain == "climate"), None)
        if legacy is None:
            continue
        unique_id = room_thermostat_unique_id(prefix, room["id"])
        room_entity = entities.async_get_entity_id("climate", DOMAIN, unique_id)
        rename = legacy.entity_id not in still_used and (
            room_entity is None or generated_entity_id(hass, entities.async_get(room_entity)))
        handovers.append(Handover(room["id"], room.get("name") or room["id"], legacy.entity_id, unique_id,
                                  room_entity, rename))
    migration = Migration(tuple(changes), tuple(handovers),
                          tuple((r["id"], r.get("name") or r["id"]) for r in plan["rooms"]))
    return (candidate if candidate != plan else None), migration


async def async_write_migration(hass, entry, client, zones, confirmed=None):
    """Write the migrated plan through an open, logged-in E32 client; nothing is removed here.

    The plan is read, changed and saved with the revision it was read at; on
    409 plan_changed it is read and changed once more. When the user confirmed
    an outcome (confirmed: Migration.signature()), a different outcome stops
    before writing (legacy_rooms_plan_changed).
    """
    from .room_plan import decode_plan
    for attempt in (1, 2):
        plan = decode_plan(await client.async_read_heating_plan())
        if plan is None:
            raise ControllerLinkError("controller_update_required")
        candidate, migration = plan_migration(hass, entry, plan, zones)
        if confirmed is not None and migration.signature() != confirmed:
            raise ControllerLinkError("legacy_rooms_plan_changed")
        if candidate is None:
            return migration, None
        try:
            stored = await client.async_save_heating_plan(candidate)
        except HeatingPlanRejected as err:
            if err.error == "plan_changed" and attempt == 1:
                continue
            raise ControllerLinkError("legacy_rooms_plan_changed" if err.error == "plan_changed"
                                      else "legacy_rooms_plan_failed") from None
        stored = decode_plan(stored)
        expected = {r["id"]: (r.get("sources"), r.get("setpoint_entity")) for r in candidate["rooms"]}
        if stored is None or {r["id"]: (r.get("sources"), r.get("setpoint_entity"))
                              for r in stored["rooms"]} != expected:
            raise ControllerLinkError("legacy_rooms_plan_failed")
        return migration, stored
    raise ControllerLinkError("legacy_rooms_plan_changed")


def capture_handover(hass, entry, migration):
    """What the user set on the older thermostats, read before they are removed."""
    entities, devices = er.async_get(hass), dr.async_get(hass)
    captured = []
    for handover in migration.handovers:
        item = entities.async_get(handover.legacy_entity_id)
        if item is None:
            continue
        device = devices.async_get(item.device_id) if item.device_id else None
        captured.append((handover, {"name": item.name, "icon": item.icon, "area_id": item.area_id,
                                    "device_area_id": device.area_id if device else None}))
    return captured


async def async_apply_handover(hass, entry, captured, wait=HANDOVER_WAIT):
    """After the older rooms are gone: carry the user's settings over and take over the entity ID.

    A removed entity leaves Home Assistant's state machine a moment after its
    registry entry; the freed ID is taken once its state is gone too.
    """
    from .heating_link import room_device_identifier
    entities, devices = er.async_get(hass), dr.async_get(hass)
    prefix = entry.data[CONF_TOPIC_PREFIX]
    for handover, before in captured:
        legacy_id = handover.legacy_entity_id
        room_entity = entities.async_get_entity_id("climate", DOMAIN, handover.room_unique_id)
        if handover.rename and entities.async_get(legacy_id) is None:
            for _ in range(int(wait / 0.05)):
                if hass.states.get(legacy_id) is None:
                    break
                await asyncio.sleep(0.05)
        free = entities.async_get(legacy_id) is None and hass.states.async_available(legacy_id)
        if room_entity is None:
            if not (handover.rename and free):
                continue
            # Not created yet: register it under the freed ID; the platform adopts this entry.
            room_entity = entities.async_get_or_create(
                "climate", DOMAIN, handover.room_unique_id, config_entry=entry,
                suggested_object_id=legacy_id.split(".", 1)[1]).entity_id
        item = entities.async_get(room_entity)
        changes = {}
        for field in ("name", "icon", "area_id"):
            if before[field] is not None and getattr(item, field) is None:
                changes[field] = before[field]
        if handover.rename and free and item.entity_id != legacy_id and generated_entity_id(hass, item):
            changes["new_entity_id"] = legacy_id
        if changes:
            try:
                entities.async_update_entity(item.entity_id, **changes)
            except ValueError:  # the ID was taken in between: keep the room thermostat's own one
                changes.pop("new_entity_id", None)
                if changes:
                    entities.async_update_entity(item.entity_id, **changes)
        device = devices.async_get_device_by_identifier(room_device_identifier(prefix, handover.room_id),
                                                       entry.entry_id)
        if before["device_area_id"] and device is not None and device.area_id is None:
            devices.async_update_device(device.id, area_id=before["device_area_id"])


# --- "Choose a temperature source for <room>" ----------------------------------

def choose_source_issue_id(entry, room_id):
    return f"{CHOOSE_SOURCE_ISSUE}_{entry.entry_id}_{room_id}"


def note_rooms_without_source(hass, entry, migration):
    """A Repairs note for each room whose only source went with the older room."""
    for change in migration.changes:
        if change.kept:
            ir.async_create_issue(
                hass, DOMAIN, choose_source_issue_id(entry, change.room_id), is_fixable=True,
                is_persistent=True, severity=ir.IssueSeverity.WARNING, translation_key=CHOOSE_SOURCE_ISSUE,
                translation_placeholders={"room": change.room_name, "installation": entry.title},
                data={"entry_id": entry.entry_id, "room_id": change.room_id, "entities": [change.old]})


def update_choose_source_issues(hass, entry, plan):
    """A plan read from the E32: notes of rooms that no longer use the removed entity go."""
    from .room_plan import plan_room
    registry = ir.async_get(hass)
    start = f"{CHOOSE_SOURCE_ISSUE}_{entry.entry_id}_"
    for (domain, issue_id), issue in list(registry.issues.items()):
        if domain != DOMAIN or not issue_id.startswith(start):
            continue
        data = issue.data or {}
        room = plan_room(plan, data.get("room_id"))
        dead = set(data.get("entities") or ())
        if room is None or not any(s.get("id") in dead for s in room.get("sources", [])):
            ir.async_delete_issue(hass, DOMAIN, issue_id)


# --- The confirmation text -------------------------------------------------------

def _label(hass, entity_id):
    state = hass.states.get(entity_id)
    name = state.attributes.get("friendly_name") if state is not None else None
    if not name and (item := er.async_get(hass).async_get(entity_id)) is not None:
        name = item.name or item.original_name
    return f"'{name}' ({entity_id})" if name and name != entity_id else f"'{entity_id}'"


TEXT = {
    "en": {
        "source": "{room} on the E32 used {old} as its temperature source; it will use {new} instead.",
        "source_dropped": "{room} on the E32 used {old} as one of its temperature sources; that source goes with "
                          "the old room, and {room} keeps its other sources.",
        "source_kept": "{room} on the E32 used {old} as its temperature source, and the old room has nothing to "
                       "replace it with: {room} will have no temperature source until you choose one "
                       "(Configure → Rooms, or the Repairs message \"Choose a temperature source for {room}\").",
        "setpoint": "{room} on the E32 took its desired temperature from {old}; it will take it from {new} instead.",
        "setpoint_dropped": "{room} on the E32 took its desired temperature from {old}; it will follow its own week "
                            "program instead.",
        "handover": "Your thermostat {old} is replaced by the {room} room thermostat; it keeps the entity ID "
                    "{entity_id}, so dashboards, automations and voice assistants keep working.",
        "handover_other": "Your thermostat {old} is replaced by the {room} room thermostat ({new}). Dashboards and "
                          "automations that use {entity_id} need to use {new} instead.",
        "nothing": "None of the rooms on the E32 uses the old rooms, so nothing changes in them.",
        "rooms": "The rooms on the E32 themselves stay, with their settings and week programs: {rooms}.",
        "unreadable": "The E32 room plan could not be read just now, so this list is not complete. Submit to try "
                      "again; nothing is removed before the E32 room plan has been checked.",
    },
    "nl": {
        "source": "{room} op de E32 gebruikte {old} als temperatuurbron; dat wordt {new}.",
        "source_dropped": "{room} op de E32 gebruikte {old} als een van zijn temperatuurbronnen; die bron verdwijnt "
                          "met de oude ruimte en {room} houdt zijn andere bronnen.",
        "source_kept": "{room} op de E32 gebruikte {old} als temperatuurbron en de oude ruimte heeft niets om die "
                       "te vervangen: {room} heeft geen temperatuurbron tot je er een kiest (Configureren → "
                       "Ruimtes, of de melding \"Kies een temperatuurbron voor {room}\" onder Reparaties).",
        "setpoint": "{room} op de E32 nam de gewenste temperatuur van {old}; dat wordt {new}.",
        "setpoint_dropped": "{room} op de E32 nam de gewenste temperatuur van {old}; voortaan volgt {room} zijn "
                            "eigen weekprogramma.",
        "handover": "Je thermostaat {old} wordt vervangen door de ruimtethermostaat van {room}; die houdt de "
                    "entiteit-ID {entity_id}, dus dashboards, automatiseringen en spraakassistenten blijven werken.",
        "handover_other": "Je thermostaat {old} wordt vervangen door de ruimtethermostaat van {room} ({new}). "
                          "Dashboards en automatiseringen met {entity_id} moeten voortaan {new} gebruiken.",
        "nothing": "Geen van de ruimtes op de E32 gebruikt de oude ruimtes, dus daarin verandert niets.",
        "rooms": "De ruimtes op de E32 zelf blijven, met hun instellingen en weekprogramma's: {rooms}.",
        "unreadable": "Het E32-ruimteplan kon nu niet gelezen worden, dus dit overzicht is niet compleet. Verstuur "
                      "om het opnieuw te proberen; er wordt niets verwijderd voordat het ruimteplan gecontroleerd is.",
    },
}


def describe(hass, migration):
    """The plain-language list for the confirmation step (Dutch or English)."""
    text = TEXT["nl" if getattr(hass.config, "language", "en") == "nl" else "en"]
    if migration is None:
        return text["unreadable"]
    lines = []
    for c in migration.changes:
        key = c.field + ("_kept" if c.kept else "" if c.new else "_dropped")
        lines.append(text[key].format(room=c.room_name, old=_label(hass, c.old),
                                      new=_label(hass, c.new) if c.new else ""))
    for h in migration.handovers:
        new = h.legacy_entity_id if h.rename else (h.room_entity_id or h.room_name)
        lines.append(text["handover" if h.rename else "handover_other"].format(
            room=h.room_name, old=_label(hass, h.legacy_entity_id), entity_id=h.legacy_entity_id, new=new))
    if not lines:
        lines.append(text["nothing"])
    lines = [f"- {line}" for line in lines]
    if migration.rooms:
        lines.append(text["rooms"].format(rooms=", ".join(name for _, name in migration.rooms)))
    return "\n".join(lines)


async def async_read_plan(hass, entry):
    """The E32 plan for the confirmation step, or None when it cannot be read now."""
    from homeassistant.exceptions import HomeAssistantError
    from .room_plan import decode_plan
    hub = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub")
    link = getattr(hub, "plan", None)
    try:
        if link is not None:
            return await link.async_read()
        from . import controller_setup_flow as setup
        async with setup.ControllerClient(entry.data[setup.CONTROLLER_ADDRESS]) as client:
            await client.async_login(entry.data[setup.CONTROLLER_PASSWORD])
            return decode_plan(await client.async_read_heating_plan())
    except (HomeAssistantError, ControllerLinkError, KeyError):
        return None
