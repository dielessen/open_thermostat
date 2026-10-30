"""One integration-page group per E32 room; the installation group holds the rest.

Presentation only. Each E32 room gets an empty config subentry, type
``e32_room``. The room's own device (``{prefix}_e32_room_{id}``) and every
entity on it live in that group: its thermostat, temperature, target, demand,
status, plan controls and learned values. A Bluetooth sensor
(``{prefix}_e32_ble_{id}``) that exactly one room of the E32 room plan uses
lives with that room. A sensor that several rooms use, that no room uses, or
whose use is unknown (the plan has not been read) goes in the installation
group, with the E32 controller device (installation_group.py).

The E32 room plan is the single source of truth. A room added there gets its
group when its device appears. A room removed there loses its device
(native_entity_cleanup) and then its group. Home Assistant offers no way to
add these groups (the type is not in async_get_supported_subentry_types). If
the user deletes one on the integration page, Core has already removed the
room's device and entities. While the room is still in the E32 plan, it keeps
heating, so a Repairs message explains that and one reload brings the group
back. The room's device and entities come back from Home Assistant's deleted
registry with the same entity IDs, names, areas and history.

Only this entry's E32 room and Bluetooth devices move, and only their
``config_subentry_id`` changes. Device and entity IDs, unique IDs, names and
the user's areas stay. The older Home Assistant rooms (``zone`` subentries and
their ``{prefix}_room_*`` devices) are never touched; legacy_rooms_flow removes
them. An area is suggested at most once per device: only when the device is
first created or first gets its group, only while it has no area, and only if
an area with the room's name (case-insensitive) already exists. No area is ever
created.
"""
from __future__ import annotations

from copy import deepcopy
import logging
from types import MappingProxyType

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .const import CONF_TOPIC_PREFIX, DOMAIN
from .product import configuration_subentries

_LOGGER = logging.getLogger(__name__)

GROUP_TYPE = "e32_room"
GROUP_PREFIX = "e32_room_"
STATE_KEY = "room_groups"
RESTORED_ISSUE = "room_group_restored"


def group_unique_id(room_id):
    return f"{GROUP_PREFIX}{room_id}"


def room_group_ids(entry):
    """{room id: subentry id} of the entry's E32 room groups."""
    return {sub.unique_id.removeprefix(GROUP_PREFIX): sub.subentry_id for sub in entry.subentries.values()
            if sub.subentry_type == GROUP_TYPE and type(sub.unique_id) is str
            and sub.unique_id.startswith(GROUP_PREFIX)}


def restored_issue_id(entry, room_id):
    return f"{RESTORED_ISSUE}_{entry.entry_id}_{room_id}"


def _snapshot(entry):
    """Everything an entry change could mean except the presentation groups (memory only)."""
    return deepcopy((entry.title, dict(entry.data), dict(entry.options),
                     {key: sub.as_dict() for key, sub in configuration_subentries(entry).items()}))


def _state(hass, entry):
    return hass.data.get(DOMAIN, {}).get(entry.entry_id)


def room_groups(hass, entry):
    """The entry's RoomGroups while it is set up (product entries only), else None."""
    state = _state(hass, entry)
    return state.get(STATE_KEY) if state is not None else None


@callback
def remember_configuration(hass, entry):
    """The entry's configuration as it is now applied (setup, or a change applied without a reload)."""
    if (groups := room_groups(hass, entry)) is not None:
        groups.baseline = _snapshot(entry)


@callback
def presentation_only_update(hass, entry):
    """True when the entry change was only to the presentation groups: no reload.

    A room group the user deleted is handled here (see RoomGroups.reconcile).
    """
    groups = room_groups(hass, entry)
    if groups is None or groups.baseline is None or _snapshot(entry) != groups.baseline:
        return False
    groups.reconcile(force=True)
    return True


def _area_named(hass, name):
    """An existing area with this name, ignoring case and surrounding spaces; never a new one."""
    if type(name) is not str or not name.strip():
        return None
    areas = ar.async_get(hass)
    if (area := areas.async_get_area_by_name(name)) is not None:
        return area
    wanted = name.strip().casefold()
    return next((area for area in areas.async_list_areas() if area.name.strip().casefold() == wanted), None)


class RoomGroups:
    """Keeps the room groups of one set-up product entry in line with the E32 room plan."""

    def __init__(self, hass, entry, installation_id):
        self.hass, self.entry = hass, entry
        self.prefix = entry.data[CONF_TOPIC_PREFIX]
        self.installation_id = installation_id
        self.hub = None
        self.baseline = None
        self._known = dict(room_group_ids(entry))  # groups this setup saw or made
        self._titles = {}  # room id: the group title this setup gave it
        self._signature = None
        self._restoring = False
        self._unsubscribe = []

    # -- identifiers ---------------------------------------------------------

    def _room_head(self):
        return f"{self.prefix}_e32_room_"

    def _ble_head(self):
        return f"{self.prefix}_e32_ble_"

    def _own(self, identifiers, head):
        from .heating_link import BLE_ID, ROOM_ID
        pattern = ROOM_ID if head == self._room_head() else BLE_ID
        for domain, identifier in identifiers or ():
            if domain == DOMAIN and type(identifier) is str and identifier.startswith(head):
                item = identifier.removeprefix(head)
                if pattern.fullmatch(item):
                    return item
        return None

    def _devices(self, head):
        """{room or sensor id: device} of this entry's devices of that kind."""
        found = {}
        for device in dr.async_entries_for_config_entry(dr.async_get(self.hass), self.entry.entry_id):
            if device.config_entry_id == self.entry.entry_id and (item := self._own(device.identifiers, head)):
                found[item] = device
        return found

    def _device(self, head, item):
        device = dr.async_get(self.hass).async_get_device_by_identifier((DOMAIN, head + item), self.entry.entry_id)
        return device if device is not None and device.config_entry_id == self.entry.entry_id else None

    # -- the plan ------------------------------------------------------------

    def _plan(self):
        link = getattr(self.hub, "plan", None)
        plan = getattr(link, "plan", None)
        return plan if type(plan) is dict and type(plan.get("rooms")) is list else None

    def _rooms(self):
        """{room id: name} of the rooms that exist: the plan once read, else what the E32 and HA know."""
        from .heating_link import ROOM_ID, label
        plan = self._plan()
        if plan is not None:
            return {room["id"]: label(room) for room in plan["rooms"]
                    if type(room) is dict and type(room.get("id")) is str and ROOM_ID.fullmatch(room["id"])}
        rooms = {room_id: device.name or room_id for room_id, device in self._devices(self._room_head()).items()}
        for room_id, room in (getattr(self.hub, "rooms", None) or {}).items():
            rooms[room_id] = label(room)
        return rooms

    def _ble_owner(self, sensor_id):
        """(plan known, the one room that uses the sensor or None)."""
        plan = self._plan()
        if plan is None:
            return False, None
        users = [room for room in plan["rooms"] if type(room) is dict and any(
            type(source) is dict and source.get("type") == "ble"
            and str(source.get("id", "")).lower() == sensor_id.lower()
            for source in (room.get("sources") if type(room.get("sources")) is list else []))]
        return True, (users[0]["id"] if len(users) == 1 and type(users[0].get("id")) is str else None)

    # -- groups --------------------------------------------------------------

    @callback
    def ensure_room(self, room_id, name):
        """The room's group, made when missing; the room's device (and its entities) moved into it."""
        entries = self.hass.config_entries
        name = (name or room_id).strip()[:64] or room_id
        group_id = room_group_ids(self.entry).get(room_id)
        device = self._device(self._room_head(), room_id)
        created = group_id is None
        if created:
            group = ConfigSubentry(data=MappingProxyType({}), subentry_type=GROUP_TYPE,
                                   title=name, unique_id=group_unique_id(room_id))
            entries.async_add_subentry(self.entry, group)
            group_id = group.subentry_id
            self._titles[room_id] = name
        else:
            title = self.entry.subentries[group_id].title
            # The group follows the E32 room name; a title the user gave it on the integration page stays.
            if title != name and title in {room_id, self._titles.get(room_id), getattr(device, "name", None)}:
                entries.async_update_subentry(self.entry, self.entry.subentries[group_id], title=name)
                self._titles[room_id] = name
        self._known[room_id] = group_id
        if device is not None:
            self._move(device, group_id)
            if created:
                self.suggest_area(device)
        return group_id

    @callback
    def _ble_group(self, sensor_id):
        known, owner = self._ble_owner(sensor_id)
        if owner is not None:
            rooms = self._rooms()
            if owner in rooms:
                return self.ensure_room(owner, rooms[owner])
        if not known:
            device = self._device(self._ble_head(), sensor_id)
            if device is not None and device.config_subentry_id in self.entry.subentries:
                return device.config_subentry_id  # where it is until the plan says otherwise
        return self.installation_id

    @callback
    def subentry_for(self, entity, default):
        """The group an entity is added to: its room's, its sensor's room's, else the default."""
        info = getattr(entity, "_attr_device_info", None) or {}
        identifiers = info.get("identifiers") if isinstance(info, dict) else None
        if room_id := self._own(identifiers, self._room_head()):
            return self.ensure_room(room_id, info.get("name"))
        if sensor_id := self._own(identifiers, self._ble_head()):
            return self._ble_group(sensor_id)
        return default

    @callback
    def _move(self, device, group_id):
        """Entities first, then the device, without yielding (Core drops entities left behind)."""
        if device.config_subentry_id == group_id:
            return
        entities = er.async_get(self.hass)
        members = [record for record in er.async_entries_for_device(entities, device.id, include_disabled_entities=True)
                   if record.config_entry_id == self.entry.entry_id and record.platform == DOMAIN]
        previous = {record.entity_id: record.config_subentry_id for record in members}
        try:
            for record in members:
                if record.config_subentry_id != group_id:
                    entities.async_update_entity(record.entity_id, config_subentry_id=group_id)
            dr.async_get(self.hass).async_update_device(device.id, new_config_subentry_id=group_id)
        except Exception:
            for entity_id, subentry_id in previous.items():
                if entities.async_get(entity_id) is not None and (
                        subentry_id is None or subentry_id in self.entry.subentries):
                    entities.async_update_entity(entity_id, config_subentry_id=subentry_id)
            raise

    @callback
    def suggest_area(self, device):
        """Once, for a device without an area: the existing area named like the room."""
        room_id = self._own(device.identifiers, self._room_head())
        if device.area_id is not None or room_id is None:
            return
        try:
            area = _area_named(self.hass, self._rooms().get(room_id) or device.name)
            if area is not None:
                dr.async_get(self.hass).async_update_device(device.id, area_id=area.id)
        except Exception:  # a suggestion only: never stop the room from being added
            _LOGGER.debug("No area suggested for E32 room %s", room_id, exc_info=True)

    # -- lifecycle -----------------------------------------------------------

    @callback
    def prepare(self):
        """At setup, before the platforms: move the existing room devices into their own groups."""
        for room_id, name in self._rooms().items():
            if self._device(self._room_head(), room_id) is not None or room_id in room_group_ids(self.entry):
                self.ensure_room(room_id, name)
        self._unsubscribe.append(self.hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._device_event))

    @callback
    def attach(self, hub):
        """The entry's heating hub: follow its plan and rooms."""
        self.hub = hub
        hub.room_groups = self
        self._unsubscribe.append(hub.add_listener(self.reconcile))

    @callback
    def stop(self):
        while self._unsubscribe:
            self._unsubscribe.pop()()
        if self.hub is not None and getattr(self.hub, "room_groups", None) is self:
            self.hub.room_groups = None

    @callback
    def _device_event(self, event):
        if event.data.get("action") != "create":
            return
        device = dr.async_get(self.hass).async_get(event.data["device_id"])
        if device is not None and device.config_entry_id == self.entry.entry_id:
            self.suggest_area(device)

    @callback
    def reconcile(self, force=False):
        """Follow the plan: titles, moved Bluetooth sensors, removed rooms, a group the user deleted."""
        if self._restoring or self.hass.config_entries.async_get_entry(self.entry.entry_id) is not self.entry:
            return
        if self._current_signature() == self._signature and not force:
            return  # every telemetry message notifies the hub; nothing that matters here changed
        try:
            self._reconcile()
        except Exception:  # presentation only: never break the telemetry path
            _LOGGER.exception("Could not arrange the OpenThermostat room groups")
        self._signature = self._current_signature()

    def _current_signature(self):
        plan = self._plan()
        rooms = getattr(self.hub, "rooms", None) or {}
        return (id(plan), plan.get("revision") if plan else None,
                tuple(sorted((room_id, str(room.get("name"))) for room_id, room in rooms.items())),
                tuple(sorted(getattr(self.hub, "ble", None) or {})),
                tuple((key, sub.title) for key, sub in self.entry.subentries.items()))

    @callback
    def _reconcile(self):
        groups = room_group_ids(self.entry)
        rooms = self._rooms()
        room_devices = self._devices(self._room_head())
        # A group that disappeared without us: deleted on the integration page (Core then
        # removes its devices too), or dropped by a configuration save (devices stay).
        vanished = [room_id for room_id, group_id in self._known.items() if group_id not in self.entry.subentries]
        for room_id in vanished:
            self._known.pop(room_id)
        deleted = sorted(room_id for room_id in vanished if room_id in rooms and room_id not in room_devices)
        if deleted:
            self._restore(deleted, rooms)
            return
        for room_id, name in rooms.items():
            if room_id in groups or room_id in room_devices:
                self.ensure_room(room_id, name)
        for sensor_id, device in self._devices(self._ble_head()).items():
            target = self._ble_group(sensor_id)
            if device.config_subentry_id != target:
                self._move(device, target)
        plan_known = self._plan() is not None
        for room_id, group_id in room_group_ids(self.entry).items():
            if room_id in rooms and (plan_known or room_id in room_devices):
                continue
            # The room left the plan (its device is gone already), or nothing of it is left.
            for device in dr.async_entries_for_config_entry(dr.async_get(self.hass), self.entry.entry_id):
                if device.config_subentry_id == group_id and self._own(device.identifiers, self._room_head()) is None:
                    self._move(device, self.installation_id)
            self._known.pop(room_id, None)
            self.hass.config_entries.async_remove_subentry(self.entry, group_id)
            ir.async_delete_issue(self.hass, DOMAIN, restored_issue_id(self.entry, room_id))

    @callback
    def _restore(self, room_ids, rooms):
        """A room group deleted while the room is still on the E32: say so, and reload once to restore it."""
        for room_id in room_ids:
            name = rooms.get(room_id, room_id)
            _LOGGER.warning("The group of E32 room %s was deleted in Home Assistant, but the room is still in "
                            "the E32 room plan; restoring it", name)
            ir.async_create_issue(self.hass, DOMAIN, restored_issue_id(self.entry, room_id), is_fixable=False,
                                  is_persistent=False, severity=ir.IssueSeverity.WARNING,
                                  translation_key=RESTORED_ISSUE,
                                  translation_placeholders={"room": name, "installation": self.entry.title},
                                  data={"entry_id": self.entry.entry_id, "room_id": room_id})
        self._restoring = True
        self.hass.config_entries.async_schedule_reload(self.entry.entry_id)


@callback
def async_setup_room_groups(hass, entry, installation_id):
    """Product entries: the room groups for this setup (call before the platforms start)."""
    state = hass.data[DOMAIN][entry.entry_id]
    groups = state[STATE_KEY] = RoomGroups(hass, entry, installation_id)
    entry.async_on_unload(groups.stop)
    try:
        groups.prepare()
    except Exception:  # presentation only: never block the start
        _LOGGER.exception("Could not move the OpenThermostat room devices into their room groups")
    return groups


@callback
def attach_hub(hass, entry, hub):
    if (groups := room_groups(hass, entry)) is not None:
        groups.attach(hub)


@callback
def add_grouped(hub, async_add_entities, entities, options):
    """async_add_entities per group: each room's entities to its room group (product entries)."""
    groups = getattr(hub, "room_groups", None)
    if groups is None or "config_subentry_id" not in options:
        async_add_entities(entities, **options)
        return
    by_group = {}
    for entity in entities:
        by_group.setdefault(groups.subentry_for(entity, options["config_subentry_id"]), []).append(entity)
    for group_id, members in by_group.items():
        async_add_entities(members, **{**options, "config_subentry_id": group_id})
