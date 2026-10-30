"""Connect E32 without Home Assistant rooms: the E32 room plan link.

Rooms live in the E32 room plan (/config/heating, edited under Configure ->
Rooms). Connecting therefore needs no room in Home Assistant: this link only
switches the E32's MQTT connection to the Home Assistant protocol (modern_shadow,
this installation's adapter_id and MQTT prefix), restarts the E32 once when that
changed, and stores the E32 address and password in the entry.

The older route (controller_link.initial_controller_link) also sends the older
Home Assistant rooms (zone subentries) as a native room profile. Installations
that still have such rooms keep that route unchanged; remove_legacy_rooms below
retires them once the E32 room plan has replaced them.

The E32 is never sent a native room profile without rooms. A profile this
installation saved earlier on the E32 is cleared explicitly (null); the E32
then runs the plain Home Assistant session, whose configuration holds no rooms
and switches nothing (no outputs; the E32 room plan is not touched).
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import json
import re

from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import controller_link as link
from .const import CONF_TOPIC_PREFIX, DOMAIN
from .controller_link import ControllerLinkError, ControllerProvisioningError

FIRMWARE_VERSION = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+-e32v2(?:-(?:alpha|beta|rc)\.[0-9]+)?")
CONTROLLER = re.compile(r"e32_[0-9a-f]{12}")
EVOLUTION = "native.source.evolution.v1"


# The first firmware that publishes the retained room-plan topics (fw/state/heating,
# fw/config/plan) Home Assistant confirms this link with: E32 beta.19.
ROOM_PLAN_TOPICS_FIRMWARE = (0, 1, 0, 1, 19)


def room_plan_topics_firmware(version):
    """True for an E32 firmware version (``v0.1.0-e32v2-beta.19``) with the room-plan topics."""
    from .firmware_update import parse_tag
    key = parse_tag(version)
    return key is not None and key >= ROOM_PLAN_TOPICS_FIRMWARE


async def async_check_room_plan_firmware(hass, entry, client):
    """Stop before any change when the E32 cannot confirm the room plan link.

    The link is confirmed by the E32's retained heating report over MQTT, which
    firmware before beta.19 does not send: linking it would wait in vain and
    leave a half-finished change. Telemetry already arriving (the heating hub is
    fresh) proves the firmware too; otherwise /status/version is read.
    """
    hub = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub")
    if hub is not None and hub.fresh:
        return
    version = await client.async_read("/status/version")
    if not room_plan_topics_firmware(version.get("version") if type(version) is dict else None):
        raise ControllerLinkError("controller_room_plan_update_required")


async def async_room_plan_firmware_problem(hass, entry):
    """controller_room_plan_update_required when the stored E32 runs firmware before beta.19.

    For a form shown before the user confirms: None when the firmware is new
    enough and also when it cannot be checked now (the action itself checks
    again before it changes anything).
    """
    hub = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("heating_hub")
    if hub is not None and hub.fresh:
        return None
    from . import controller_setup_flow as setup
    try:
        async with setup.ControllerClient(entry.data[setup.CONTROLLER_ADDRESS]) as client:
            await client.async_login(entry.data[setup.CONTROLLER_PASSWORD])
            await async_check_room_plan_firmware(hass, entry, client)
    except ControllerLinkError as err:
        return str(err) if str(err) == "controller_room_plan_update_required" else None
    except KeyError:
        return None
    return None


def legacy_zones(entry):
    """The older Home Assistant rooms (zone subentries) of an entry."""
    return [s for s in entry.subentries.values() if s.subentry_type == "zone"]


def _adapter(entry):
    return entry.options.get("adapter_id", entry.data.get("adapter_id"))


def own_native_source(descriptor, adapter_id):
    """True when a native room profile saved on the E32 belongs to this installation.

    Its descriptor names the installation's random adapter id (index 2), also
    inside both halves of an evolution descriptor.
    """
    if type(descriptor) is not list or not descriptor:
        return False
    if descriptor[0] == EVOLUTION:
        return len(descriptor) == 3 and all(own_native_source(part, adapter_id) for part in descriptor[1:])
    return (len(descriptor) >= 3 and type(descriptor[0]) is str
            and descriptor[0].startswith("native.source.local") and descriptor[2] == adapter_id)


@dataclass(frozen=True, slots=True)
class RoomPlanLink:
    before: tuple = field(repr=False)
    private_entry_state: str = field(repr=False)
    controller_id: str
    observed_settings: dict = field(repr=False)
    settings: dict = field(repr=False)
    etag: str
    firmware_identity: dict
    settings_unchanged: bool
    needs_reboot: bool
    room_ids: tuple
    clears_native_source: bool


def room_plan_link(entry, *, version, status, updates, settings, etag, rooms, heating):
    """Check the authenticated E32 reads and derive the settings to save; no I/O."""
    from .v1_wire import canonical
    from .room_plan import decode_plan
    from .v1_wire import identifier
    if (type(version) is not dict or type(status) is not dict or type(updates) is not dict
            or type(settings) is not dict or type(rooms) is not list):
        raise ControllerLinkError("controller_response_invalid")
    if status.get("controlMode") not in ("legacy", "shadow"):
        raise ControllerLinkError("controller_response_invalid")
    if type(etag) is not str or re.fullmatch(r'"[0-9a-f]{64}"', etag) is None:
        raise ControllerLinkError("controller_update_required")
    if (type(version.get("version")) is not str or FIRMWARE_VERSION.fullmatch(version["version"]) is None
            or type(version.get("source")) is not str or re.fullmatch(r"[0-9a-f]{40}", version["source"]) is None
            or any(type(version.get(k)) is not str or re.fullmatch(r"[0-9a-f]{64}", version[k]) is None
                   for k in ("sha256", "web_sha256"))):
        raise ControllerLinkError("controller_update_required")
    plan = decode_plan(heating)
    if plan is None:  # firmware without the E32 room plan
        raise ControllerLinkError("controller_update_required")
    if (updates.get("busy") is not False or updates.get("boot_pending") is not False
            or updates.get("reboot_required") is not False or updates.get("reboot_scheduled") is not False):
        raise ControllerLinkError("controller_busy_or_conflict")
    if rooms:
        raise ControllerLinkError("controller_legacy_rooms_present")
    mqtt = settings.get("mqtt")
    # The E32 only connects to a broker with its own login (user name and
    # password); it never sends the password back, so "" here means "stored".
    if (type(mqtt) is not dict or mqtt.get("enabled") is not True
            or type(mqtt.get("brokerAddress")) is not str or not mqtt["brokerAddress"]
            or type(mqtt.get("brokerPort")) is not int or not 1 <= mqtt["brokerPort"] <= 65535
            or type(mqtt.get("username")) is not str or not mqtt["username"]
            or mqtt.get("password") != ""):
        raise ControllerLinkError("controller_broker_setup_required")
    controller = mqtt.get("native_source_device_id")
    adapter, prefix = _adapter(entry), entry.data.get(CONF_TOPIC_PREFIX)
    if (type(controller) is not str or CONTROLLER.fullmatch(controller) is None
            or type(mqtt.get("native_source_live_apply")) is not bool):
        raise ControllerLinkError("controller_update_required")
    if not identifier(adapter) or not identifier(prefix):
        raise ControllerLinkError("controller_room_configuration_invalid")
    current = deepcopy(settings)
    current["mqtt"].pop("native_source_device_id")
    current["mqtt"].pop("native_source_live_apply")
    mqtt = current["mqtt"]
    if mqtt.get("modern_shadow") is True and mqtt.get("adapter_id") != adapter:
        raise ControllerLinkError("controller_source_conflict")  # linked to another installation
    source = mqtt.get("native_shadow_source")
    if source is not None and not own_native_source(source, adapter):
        raise ControllerLinkError("controller_source_conflict")
    candidate = deepcopy(current)
    candidate["mqtt"].update(modern_shadow=True, adapter_id=adapter, base=prefix)
    if source is not None:
        candidate["mqtt"]["native_shadow_source"] = None  # explicit clear, never an empty profile
    if len(json.dumps(candidate, ensure_ascii=True, separators=(",", ":")).encode()) >= 2048:
        raise ControllerLinkError("controller_settings_too_large")
    unchanged = canonical(current) == canonical(candidate)
    from .native_plan import native_entry_state
    from .product import configuration_snapshot
    return RoomPlanLink(configuration_snapshot(entry), native_entry_state(entry), controller, current,
                        candidate, etag, {k: version[k] for k in ("version", "source", "sha256", "web_sha256")},
                        unchanged, not (unchanged and status.get("controlMode") == "shadow"),
                        tuple(sorted(room["id"] for room in plan["rooms"])), source is not None)


async def async_prepare_room_plan_link(hass, entry, client):
    """Bounded authenticated reads and the checks above; no writes."""
    from .native_plan import native_entry_state
    from .product import configuration_snapshot
    before, private_before = configuration_snapshot(entry), native_entry_state(entry)
    link._link_guard(hass, entry, before, private_entry_state=private_before)
    observed = {}
    for key, path in (("version", "/status/version"), ("status", "/status"),
                      ("updates", "/updates/status"), ("settings", "/config/device"),
                      ("rooms", "/config/rooms"), ("heating", link.HEATING_PLAN)):
        try:
            value = await client.async_read(path)
        except ControllerLinkError as err:
            # Firmware without the room plan has no /config/heating route.
            if key == "heating" and str(err) == "controller_response_invalid":
                raise ControllerLinkError("controller_update_required") from None
            raise
        link._link_guard(hass, entry, before, private_entry_state=private_before)
        if key == "settings":
            observed[key], observed["etag"] = value
        else:
            observed[key] = value
    return room_plan_link(entry, **observed)


async def async_provision_room_plan(hass, entry, client, plan, password):
    """Save the link settings once, restart once when needed and read them back."""
    from .v1_wire import canonical
    if type(plan) is not RoomPlanLink:
        raise ControllerLinkError("controller_readback_invalid")
    changed = wrote = rebooted = False

    def guard():
        link._link_guard(hass, entry, plan.before, private_entry_state=plan.private_entry_state)

    try:
        guard()
        fresh = await async_prepare_room_plan_link(hass, entry, client)
        guard()
        if (fresh.etag != plan.etag or fresh.firmware_identity != plan.firmware_identity
                or fresh.controller_id != plan.controller_id
                or canonical(fresh.observed_settings) != canonical(plan.observed_settings)
                or canonical(fresh.settings) != canonical(plan.settings)):
            raise ControllerLinkError("controller_settings_changed")
        if not fresh.settings_unchanged:
            changed = True  # set before the await: a lost answer may still have saved
            try:
                await client.async_save_settings(fresh.settings, fresh.etag)
            except ControllerLinkError as err:
                if str(err) == "controller_response_invalid":
                    # 400: the E32 refuses the Home Assistant connection without a
                    # complete broker login (user name and password).
                    changed = False
                    raise ControllerLinkError("controller_broker_setup_required") from None
                if str(err) in ("controller_auth_failed", "controller_settings_changed",
                                "controller_busy_or_conflict", "controller_settings_too_large",
                                "controller_readback_invalid", "controller_request_invalid"):
                    changed = False
                raise
            wrote = True
            guard()
            saved, _ = await client.async_read("/config/device")
            guard()
            actual, _ = link._saved_link_settings(saved, plan.controller_id)
            if canonical(actual) != canonical(plan.settings):
                raise ControllerLinkError("controller_settings_changed")
        if fresh.needs_reboot:
            changed = True
            guard()
            try:
                await client.async_reboot()
                rebooted = True
            except ControllerLinkError as err:
                if str(err) != "controller_unreachable":
                    raise
                # A lost answer may mean the restart began; never send a second one.
        reauthenticated = False
        try:
            async with asyncio.timeout(link.LINK_BOOT_TIMEOUT):
                while True:
                    guard()
                    try:
                        version = await client.async_read("/status/version")
                        updates = await client.async_read("/updates/status")
                        status = await client.async_read("/status")
                        saved, _ = await client.async_read("/config/device")
                    except ControllerLinkError as err:
                        guard()
                        if fresh.needs_reboot and str(err) == "controller_auth_failed" and not reauthenticated:
                            await client.async_login(password)
                            reauthenticated = True
                        elif str(err) != "controller_unreachable":
                            raise
                        await asyncio.sleep(link.LINK_POLL_INTERVAL)
                        continue
                    guard()
                    if any(type(value) is not dict for value in (version, updates, status)):
                        raise ControllerLinkError("controller_response_invalid")
                    if {k: version.get(k) for k in plan.firmware_identity} != plan.firmware_identity:
                        raise ControllerLinkError("controller_changed")
                    actual, _ = link._saved_link_settings(saved, plan.controller_id)
                    if canonical(actual) != canonical(plan.settings):
                        raise ControllerLinkError("controller_settings_changed")
                    if (status.get("controlMode") == "shadow" and updates.get("busy") is False
                            and updates.get("boot_pending") is False and updates.get("reboot_required") is False
                            and updates.get("reboot_scheduled") is False):
                        break
                    await asyncio.sleep(link.LINK_POLL_INTERVAL)
        except TimeoutError:
            raise ControllerLinkError("controller_boot_unconfirmed") from None
        guard()
        return {"controller_id": plan.controller_id, "device_settings_verified": True,
                "settings_written": wrote, "reboot_acknowledged": rebooted,
                "native_source_cleared": plan.clears_native_source}
    except ControllerLinkError as err:
        raise ControllerProvisioningError(str(err), device_may_have_changed=changed) from None


# --- Older Home Assistant rooms ---------------------------------------------

def legacy_room_devices(hass, entry, room_ids):
    """This entry's own devices of the older HA rooms (identifier <prefix>_room_<room id>)."""
    registry = dr.async_get(hass)
    prefix = entry.data[CONF_TOPIC_PREFIX]
    found = []
    for room_id in room_ids:
        device = registry.async_get_device_by_identifier((DOMAIN, f"{prefix}_room_{room_id}"), entry.entry_id)
        if device is not None:
            found.append(device)
    return found


def _own(item, entry):
    return item.config_entry_id == entry.entry_id and item.platform == DOMAIN


def remove_legacy_room_devices(hass, entry, removed):
    """Remove this entry's entities and devices of removed older rooms.

    removed: (subentry id, room id) pairs. An entity of another integration
    that sits on such a device is only detached from it and stays; the room's
    temperature sensor and valve (other integrations) are never touched.
    """
    devices, entities = dr.async_get(hass), er.async_get(hass)
    found = legacy_room_devices(hass, entry, [room_id for _, room_id in removed])
    for device in found:
        for item in er.async_entries_for_device(entities, device.id, include_disabled_entities=True):
            if not _own(item, entry):
                entities.async_update_entity(item.entity_id, device_id=None)
    # Like Home Assistant's own subentry delete: this entry's entities of the subentry.
    for subentry_id, _ in removed:
        devices.async_clear_config_subentry(entry.entry_id, subentry_id, entry.domain)
        entities.async_clear_config_subentry(entry.entry_id, subentry_id)
    for device in legacy_room_devices(hass, entry, [room_id for _, room_id in removed]):
        for item in er.async_entries_for_device(entities, device.id, include_disabled_entities=True):
            if _own(item, entry):
                entities.async_remove(item.entity_id)
        devices.async_remove_device(device.id)


def without_legacy_rooms(entry):
    """The entry's subentries and draft without its older HA rooms."""
    from .product import INSTALLATION, central_entry
    from .v1_heating_draft import parse_heating_draft
    zones = legacy_zones(entry)
    room_ids = {s.data["room_id"] for s in zones}
    removed = sorted((s.subentry_id, s.data["room_id"]) for s in zones)
    # The saved native room profile (SOURCE_OPTION) stays until the E32 link is
    # confirmed without it: an interrupted removal stays visible (Repairs) and
    # the entry starts without that profile (stale_native_source).
    changes = {"subentries": {k: s for k, s in entry.subentries.items() if s.subentry_type != "zone"}}
    current = central_entry(entry)
    if current is not None:
        data = deepcopy(dict(current.data))
        document = data["draft"]
        own_groups = {a["group_id"] for a in document["actuators"] if a["room_id"] in room_ids}
        document["actuators"] = [a for a in document["actuators"] if a["room_id"] not in room_ids]
        used = {a["group_id"] for a in document["actuators"]}
        document["groups"] = [g for g in document["groups"] if g["group_id"] not in own_groups or g["group_id"] in used]
        parsed = parse_heating_draft(document, known_room_ids=set())
        data.update(draft=parsed.storage_document(), status=parsed.readiness, draft_digest=parsed.digest,
                    incomplete_group_ids=list(parsed.incomplete_group_ids))
        changes["data"] = {**entry.data, INSTALLATION: data}
    return changes, removed


LEGACY_ROOMS_ISSUE = "legacy_rooms"


def stale_native_source(entry, source):
    """True when a linked entry's saved native room profile no longer fits its HA rooms.

    That happens when an older Home Assistant room was deleted (for example on
    the integration page) after Connect E32. Starting that profile would fail;
    the entry then starts without the native link until "Remove old Home
    Assistant rooms" (or Connect E32) finishes the change.
    """
    from .native_provisioning import SOURCE_OPTION
    from .product import is_product
    from .room_plan import has_room_plan
    from .v1_model import RoomBinding
    if source is None or SOURCE_OPTION not in entry.options or not is_product(entry) or not has_room_plan(entry):
        return False
    try:
        rooms = [RoomBinding.from_dict(dict(s.data)) for s in legacy_zones(entry)]
        return len(rooms) != source.room_count or not all(source.supports_room(room) for room in rooms)
    except (ValueError, TypeError, KeyError):
        return True


def legacy_rooms_pending(entry):
    """Older HA rooms (or an unfinished removal) on an entry whose rooms are the E32 plan."""
    from .native_provisioning import SOURCE_OPTION
    from .product import is_product
    from .room_plan import has_room_plan
    from .v1_model import MODE_SHADOW, integration_mode
    return bool(is_product(entry) and integration_mode(entry) == MODE_SHADOW and has_room_plan(entry)
                and (legacy_zones(entry) or SOURCE_OPTION in entry.options))


def issue_id(entry):
    return f"{LEGACY_ROOMS_ISSUE}_{entry.entry_id}"


def update_legacy_rooms_issue(hass, entry):
    """Show a Repairs item while older HA rooms remain; remove it once they are gone."""
    from homeassistant.helpers import issue_registry as ir
    if not legacy_rooms_pending(entry):
        ir.async_delete_issue(hass, DOMAIN, issue_id(entry))
        return
    names = ", ".join(sorted(s.title for s in legacy_zones(entry)))
    # Without rooms left only the E32 link is unfinished (a room deleted elsewhere).
    ir.async_create_issue(hass, DOMAIN, issue_id(entry), is_fixable=True, is_persistent=False,
                          severity=ir.IssueSeverity.WARNING,
                          translation_key=LEGACY_ROOMS_ISSUE if names else LEGACY_ROOMS_ISSUE + "_finish",
                          translation_placeholders={"rooms": names, "installation": entry.title},
                          data={"entry_id": entry.entry_id})
