"""Connect E32 without Home Assistant rooms, and retiring the older HA rooms.

Fresh install: no HA room, only the E32 room plan. Existing install: one older
HA room ("Badkamer", the owner's starter room), a linked E32 with its native
room profile, and an E32 plan with woonkamer and badkamer.
"""
import asyncio
from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr, entity_registry as er, issue_registry as ir

import custom_components.open_thermostat as integration
from custom_components.open_thermostat import controller_connection, controller_link as link
from custom_components.open_thermostat import controller_setup_flow as setup
from custom_components.open_thermostat import e32_link
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.controller_link import ControllerLinkError, ControllerProvisioningError
from custom_components.open_thermostat.native_provisioning import (
    SOURCE_OPTION, local_device_descriptor, propose_local_shadow_source, source_selection)
from custom_components.open_thermostat.product import PRODUCT_CONFIG, configuration_snapshot
from test_room_plan import PLAN
from test_v1_native import entry, room

CONTROLLER = "e32_123456789abc"
TAG = '"' + "a" * 64 + '"'


class PlanE32:
    """The E32 HTTP contract Connect E32 uses (login, reads, one save, one restart)."""

    def __init__(self, *, plan=PLAN, source=None, modern=False, adapter=""):
        self.logout_confirmed = False
        self.calls = []
        self.fail_save = None
        self.reads = {
            "/status/version": {"version": "v0.1.0-e32v2-beta.19", "source": "a" * 40,
                                "sha256": "b" * 64, "web_sha256": "c" * 64},
            "/status": {"controlMode": "shadow" if modern else "legacy"},
            "/updates/status": {"busy": False, "boot_pending": False, "reboot_required": False,
                                "reboot_scheduled": False},
            "/config/rooms": [],
            "/config/heating": deepcopy(plan),
        }
        mqtt_settings = {"enabled": True, "brokerAddress": "192.168.1.10", "brokerPort": 1883,
                         "username": "e32", "password": "", "base": "ib-therm", "clientId": "keep",
                         "modern_shadow": modern, "adapter_id": adapter}
        if source is not None:
            mqtt_settings["native_shadow_source"] = source
        self.settings = {"mqtt": mqtt_settings, "interface_mode": "wifi", "unknown_kept": {"x": [1]}}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.logout_confirmed = True

    async def async_login(self, password):
        self.calls.append(("login",))
        if password != "e32-password":
            raise ControllerLinkError("controller_auth_failed")

    async def async_read(self, path):
        self.calls.append(("read", path))
        if path == "/config/device":
            value = deepcopy(self.settings)
            value["mqtt"].update(native_source_device_id=CONTROLLER, native_source_live_apply=False)
            return value, TAG
        return deepcopy(self.reads[path])

    async def async_save_settings(self, document, etag):
        self.calls.append(("save", deepcopy(document)))
        if self.fail_save:
            raise ControllerLinkError(self.fail_save)
        assert etag == TAG
        self.settings = deepcopy(document)

    async def async_reboot(self):
        self.calls.append(("reboot",))
        self.reads["/status"]["controlMode"] = "shadow"

    # The room plan (/config/heating): a revision per save, 409 for a stale one.
    plan_fail = None
    conflicts = 0
    on_plan_save = None

    async def async_read_heating_plan(self):
        self.calls.append(("read", "/config/heating"))
        return deepcopy(self.reads["/config/heating"])

    async def async_save_heating_plan(self, plan):
        from custom_components.open_thermostat.controller_link import HeatingPlanRejected
        self.calls.append(("plan", deepcopy(plan)))
        if self.on_plan_save is not None:
            self.on_plan_save(plan)
        if self.conflicts:
            self.conflicts -= 1
            self.reads["/config/heating"]["revision"] += 1  # another writer saved in between
            raise HeatingPlanRejected(409, "plan_changed")
        if self.plan_fail:
            raise HeatingPlanRejected(400, self.plan_fail)
        assert plan["revision"] == self.reads["/config/heating"]["revision"]
        stored = {**deepcopy(plan), "revision": plan["revision"] + 1}
        self.reads["/config/heating"] = stored
        return deepcopy(stored)


def product(hass, binding=None):
    parent = entry(hass, room=binding)
    hass.config_entries.async_update_entry(parent, data={**parent.data, PRODUCT_CONFIG: 1})
    return parent


@pytest.fixture
def linked(hass, monkeypatch):
    """Patch the E32 client, the reload and the MQTT confirmation; return the fake E32 holder."""
    holder = {}
    monkeypatch.setattr(setup, "ControllerClient", lambda address: holder["e32"])
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    waits = []

    async def confirmed(h, entry, expected, *, private_expected):
        assert expected == configuration_snapshot(entry) and entry.options["shadow_enabled"] is True
        waits.append(entry.entry_id)
        return {"mqtt_session_verified": True, "room_plan_applied": False, "heating_report_received": True}
    monkeypatch.setattr(setup, "async_wait_room_plan_link", confirmed)
    holder["waits"] = waits
    return holder


def saved_mqtt(e32):
    saves = [c[1] for c in e32.calls if c[0] == "save"]
    assert len(saves) == 1
    return saves[0]["mqtt"]


# --- Fresh install: no Home Assistant room ------------------------------------

@pytest.mark.asyncio
async def test_fresh_install_connects_without_any_home_assistant_room(hass, linked):
    parent = product(hass)
    assert not e32_link.legacy_zones(parent)
    e32 = linked["e32"] = PlanE32()
    result = await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert result["room_ids"] == ["badkamer", "woonkamer"] and result["authorizes_physical_outputs"] is False
    assert result["admin_logout_confirmed"] and linked["waits"] == [parent.entry_id]
    mqtt_settings = saved_mqtt(e32)
    assert mqtt_settings["modern_shadow"] is True and mqtt_settings["adapter_id"] == "ha1"
    assert mqtt_settings["base"] == "fixture" and "native_shadow_source" not in mqtt_settings
    # Everything else on the E32 is written back unchanged.
    assert e32.settings["unknown_kept"] == {"x": [1]} and mqtt_settings["username"] == "e32"
    assert sum(c[0] == "reboot" for c in e32.calls) == 1
    assert parent.data[setup.CONTROLLER_ADDRESS] == "http://192.168.1.206"
    assert parent.data[setup.CONTROLLER_PASSWORD] == "e32-password"
    assert parent.data[setup.CONTROLLER_ID] == CONTROLLER
    assert parent.options["shadow_enabled"] is True and SOURCE_OPTION not in parent.options
    assert not parent.subentries or all(s.subentry_type != "zone" for s in parent.subentries.values())


@pytest.mark.asyncio
async def test_connecting_again_changes_nothing_on_the_e32(hass, linked):
    parent = product(hass)
    linked["e32"] = PlanE32()
    await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    again = linked["e32"] = PlanE32(modern=True, adapter="ha1")
    again.settings["mqtt"]["base"] = "fixture"
    await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert not any(c[0] in ("save", "reboot") for c in again.calls)
    assert parent.options["shadow_enabled"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("change,code", [
    (lambda e: e.settings["mqtt"].update(username=""), "controller_broker_setup_required"),
    (lambda e: e.settings["mqtt"].update(enabled=False), "controller_broker_setup_required"),
    (lambda e: setattr(e, "fail_save", "controller_response_invalid"), "controller_broker_setup_required"),
    (lambda e: e.settings["mqtt"].update(modern_shadow=True, adapter_id="other"), "controller_source_conflict"),
    (lambda e: e.settings["mqtt"].update(native_shadow_source=["native.source.local.week.v1", CONTROLLER,
                                                               "other", "d" * 64, 1, False, []]),
     "controller_source_conflict"),
    (lambda e: e.reads.update({"/config/heating": {"unexpected": True}}), "controller_update_required"),
    (lambda e: e.reads["/updates/status"].update(busy=True), "controller_busy_or_conflict"),
])
async def test_fresh_install_explains_what_the_e32_needs(hass, linked, change, code):
    parent = product(hass)
    e32 = linked["e32"] = PlanE32()
    change(e32)
    before = dict(parent.data)
    with pytest.raises(ControllerProvisioningError) as caught:
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert str(caught.value) == code and caught.value.device_may_have_changed is False
    assert dict(parent.data) == before and not any(c[0] == "reboot" for c in e32.calls)


@pytest.mark.asyncio
async def test_an_unsupported_home_assistant_names_the_minimum_version(hass, linked, monkeypatch):
    from custom_components.open_thermostat import product as product_module
    parent = product(hass)
    linked["e32"] = PlanE32()
    monkeypatch.setattr(product_module, "HA_VERSION", "2026.9.4")
    with pytest.raises(ControllerLinkError, match="controller_ha_version_unsupported"):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert not linked["e32"].calls
    monkeypatch.setattr(product_module, "HA_VERSION", "2026.11.1")
    await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")


@pytest.mark.asyncio
async def test_fresh_install_connect_through_the_options_form(hass, linked, monkeypatch):
    from test_product_flow import option
    from homeassistant import config_entries
    from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
    monkeypatch.setattr(config_entries, "_async_get_flow_handler", AsyncMock(return_value=OpenThermostatConfigFlow))
    parent = product(hass)
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {}
    linked["e32"] = PlanE32()
    manager = hass.config_entries.options
    form = await option(manager, parent, "controller_connection")
    progress = await manager.async_configure(form["flow_id"], {"address": "http://192.168.1.206",
                                                               "password": "e32-password"})
    await hass.async_block_till_done()
    # The fake E32 answers at once, so the flow may already have run through progress.
    if progress["type"] != "abort":
        result = await manager.async_configure(progress["flow_id"])
        assert result["step_id"] == "controller_connected", result
        assert result["description_placeholders"] == {"rooms": "2"}
        progress = await manager.async_configure(progress["flow_id"], {})
    assert progress["reason"] == "controller_connection_complete"
    assert linked["waits"] == [parent.entry_id] and parent.options["shadow_enabled"] is True


# --- Waiting for the E32 over MQTT ---------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("fresh", [True, False])
async def test_link_is_confirmed_by_the_e32_heating_report(hass, monkeypatch, fresh):
    from custom_components.open_thermostat.heating_link import HeatingHub
    parent = product(hass)
    connection = object()
    monkeypatch.setattr(controller_connection, "async_wait_controller_connection",
                        AsyncMock(return_value=connection))
    monkeypatch.setattr(controller_connection, "_connection", lambda h, e, s: connection)
    monkeypatch.setattr(controller_connection, "_guard", lambda *args: None)
    monkeypatch.setattr(controller_connection, "CONNECTION_TIMEOUT", 0.05)
    monkeypatch.setattr(controller_connection, "TELEMETRY_POLL", 0.001)
    hub = HeatingHub("fixture")
    if fresh:
        hub.update({"rooms": []})
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"heating_hub": hub}
    if fresh:
        result = await controller_connection.async_wait_room_plan_link(hass, parent, None)
        assert result["heating_report_received"] is True
    else:
        with pytest.raises(ControllerLinkError, match="controller_mqtt_unconfirmed"):
            await controller_connection.async_wait_room_plan_link(hass, parent, None)


@pytest.mark.asyncio
async def test_a_linked_entry_without_rooms_starts_its_one_connection(hass, monkeypatch):
    """Real setup: zero HA rooms, no native room profile; the session config holds no rooms."""
    parent = product(hass)
    hass.config_entries.async_update_entry(parent, data={**parent.data, setup.CONTROLLER_ADDRESS: "http://e32.local",
        setup.CONTROLLER_PASSWORD: "e32-password", setup.CONTROLLER_ID: CONTROLLER},
        options={**parent.options, "shadow_enabled": True})
    listeners = []

    async def subscribe(hass, topic, callback, **kwargs):
        token = object(); listeners.append(token)
        return lambda: listeners.remove(token)
    published = []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_publish", AsyncMock(side_effect=lambda h, topic, *a, **k: published.append(topic)))
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    try:
        assert await integration.async_setup_entry(hass, parent)
        state = hass.data[DOMAIN][parent.entry_id]
        assert state["v1_runtime"].enabled and state["v1_runtime"].rooms == {}
        assert state["v1_connection"].client.native_plan_source is None
        assert state["v1_connection"].client.desired == []
        assert not [t for t in published if t.endswith("ha/config")]
        assert ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent)) is None
    finally:
        if parent.entry_id in hass.data.get(DOMAIN, {}):
            assert await integration.async_unload_entry(hass, parent)
        await parent._async_process_on_unload(hass)


# --- Existing install with the owner's starter room -----------------------------

@pytest.fixture
def badkamer(hass, monkeypatch):
    from homeassistant import config_entries
    from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
    monkeypatch.setattr(config_entries, "_async_get_flow_handler", AsyncMock(return_value=OpenThermostatConfigFlow))
    return None


async def owner_setup(hass):
    """The owner's entry, made with the real "Add room" flow and linked with a native profile."""
    from test_product_flow import product as flow_product, new_room
    parent = flow_product(hass)
    binding = replace(room(hass, suffix="badkamer"), name="Badkamer")
    manager = hass.config_entries.subentries
    f = await new_room(manager, parent, binding)
    f = await manager.async_configure(f["flow_id"], {"base_temperature": 21, "program_action": "save"})
    await manager.async_configure(f["flow_id"], {})
    sub = next(s for s in parent.subentries.values() if s.subentry_type == "zone")
    assert sub.title == "Badkamer"
    source = propose_local_shadow_source(hass, parent, CONTROLLER, week_reviewed=True)
    hass.config_entries.async_update_entry(parent, data={**parent.data,
        setup.CONTROLLER_ADDRESS: "http://192.168.1.206", setup.CONTROLLER_PASSWORD: "e32-password",
        setup.CONTROLLER_ID: CONTROLLER},
        options={**parent.options, SOURCE_OPTION: source_selection(source), "shadow_enabled": True})
    devices, entities = dr.async_get(hass), er.async_get(hass)
    room_id = sub.data["room_id"]
    legacy = devices.async_get_or_create(config_entry_id=parent.entry_id, config_subentry_id=sub.subentry_id,
        identifiers={(DOMAIN, f"fixture_room_{room_id}")}, name="Badkamer — thermostaat")
    climate = entities.async_get_or_create("climate", DOMAIN, f"fixture_room_{room_id}_climate",
        config_entry=parent, config_subentry_id=sub.subentry_id, device_id=legacy.id)
    # An entity of another integration placed on that device stays (only detached).
    other = ConfigEntry(domain="other_integration", title="other", version=1, minor_version=1, data={},
                        options={}, source="user", unique_id="other", discovery_keys=MappingProxyType({}),
                        subentries_data=[])
    hass.config_entries._entries[other.entry_id] = other
    foreign = entities.async_get_or_create("sensor", "other_integration", "badkamer_extra",
                                           config_entry=other, device_id=legacy.id)
    kept = {}
    for plan_room in ("woonkamer", "badkamer"):
        device = devices.async_get_or_create(config_entry_id=parent.entry_id,
            identifiers={(DOMAIN, f"fixture_e32_room_{plan_room}")}, name=plan_room.title())
        kept[plan_room] = entities.async_get_or_create("sensor", DOMAIN, f"fixture_e32_room_{plan_room}_temperature",
            config_entry=parent, device_id=device.id).entity_id
    return parent, sub, source, climate.entity_id, foreign.entity_id, kept, binding


@pytest.mark.asyncio
async def test_owner_badkamer_is_removed_and_the_e32_stays_linked(hass, linked, badkamer):
    parent, sub, source, climate, foreign, kept, binding = await owner_setup(hass)
    assert e32_link.legacy_rooms_pending(parent)
    e32 = linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    e32.settings["mqtt"]["base"] = "fixture"
    # Connect E32 keeps the native route while the older room exists (unchanged behaviour).
    with pytest.raises(ControllerLinkError, match="controller_room_configuration_invalid"):
        await setup.async_link_room_plan(hass, parent, "http://192.168.1.206", "e32-password")
    result = await setup.async_link_room_plan(hass, parent, parent.data[setup.CONTROLLER_ADDRESS],
                                              parent.data[setup.CONTROLLER_PASSWORD], remove_legacy_rooms=True)
    assert result["room_ids"] == ["badkamer", "woonkamer"]
    assert not e32_link.legacy_zones(parent) and SOURCE_OPTION not in parent.options
    assert parent.options["shadow_enabled"] is True and parent.data[setup.CONTROLLER_ID] == CONTROLLER
    assert parent.data["installation_configuration"]["draft"]["actuators"] == []
    # The E32 drops only its old native room profile (explicit null), restarts once.
    mqtt_settings = saved_mqtt(e32)
    assert mqtt_settings["native_shadow_source"] is None and mqtt_settings["modern_shadow"] is True
    assert sum(c[0] == "reboot" for c in e32.calls) == 1
    assert not any(c[0] == "save" and c[1].get("rooms") for c in e32.calls)  # never a room plan write
    devices, entities = dr.async_get(hass), er.async_get(hass)
    # The old thermostat is gone; its entity ID now belongs to the E32 Badkamer room thermostat.
    assert entities.async_get(climate).unique_id == "fixture_e32_room_badkamer_thermostat"
    assert not any(c[0] == "plan" for c in e32.calls)  # no E32 room used the old room: plan untouched
    assert devices.async_get_device_by_identifier((DOMAIN, f"fixture_room_{sub.data['room_id']}"),
                                                  parent.entry_id) is None
    assert entities.async_get(foreign) is not None and entities.async_get(foreign).device_id is None
    for entity_id in kept.values():
        assert entities.async_get(entity_id) is not None
    # The room's own sensor and valve (another integration) are untouched.
    assert entities.async_get(binding.temperature.entity_id) is not None
    assert entities.async_get(binding.actuators[0].entity_id) is not None
    assert not e32_link.legacy_rooms_pending(parent)
    # Connect E32 again: nothing to change, nothing fails.
    again = linked["e32"] = PlanE32(modern=True, adapter="ha1")
    again.settings["mqtt"].update(base="fixture", native_shadow_source=None)
    await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert not any(c[0] in ("save", "reboot") for c in again.calls)


@pytest.mark.asyncio
async def test_a_room_deleted_on_the_integration_page_never_breaks_start_or_reconnect(hass, linked, badkamer,
                                                                                     monkeypatch):
    parent, sub, source, *_ = await owner_setup(hass)
    hass.config_entries.async_remove_subentry(parent, sub.subentry_id)
    assert e32_link.stale_native_source(parent, integration._selected_native_plan_source(parent))
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())
    monkeypatch.setattr(mqtt, "async_subscribe", AsyncMock(return_value=lambda: None))
    publish = AsyncMock()
    monkeypatch.setattr(mqtt, "async_publish", publish)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    try:
        assert await integration.async_setup_entry(hass, parent)
        state = hass.data[DOMAIN][parent.entry_id]
        # No native room profile without its room, no link, nothing sent to the E32.
        assert not state["v1_runtime"].enabled and "v1_connection" not in state
        publish.assert_not_called()
        issue = ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent))
        assert issue is not None and issue.translation_key == "legacy_rooms_finish" and issue.is_fixable
    finally:
        if parent.entry_id in hass.data.get(DOMAIN, {}):
            assert await integration.async_unload_entry(hass, parent)
        await parent._async_process_on_unload(hass)
    # Connect E32 again finishes it: the E32's own leftover profile is cleared.
    e32 = linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert saved_mqtt(e32)["native_shadow_source"] is None
    assert SOURCE_OPTION not in parent.options and not e32_link.legacy_rooms_pending(parent)


@pytest.mark.asyncio
async def test_existing_install_with_older_rooms_keeps_the_native_route(hass, linked, badkamer, monkeypatch):
    parent, sub, source, climate, *_ = await owner_setup(hass)
    monkeypatch.setattr(setup, "async_link_room_plan", AsyncMock(side_effect=AssertionError("wrong route")))
    monkeypatch.setattr(setup, "async_prepare_controller_link", AsyncMock(side_effect=ControllerLinkError("stop_here")))
    linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    with pytest.raises(ControllerProvisioningError, match="stop_here"):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    # Entry, room and its entity ID are as they were (the route stopped before any change).
    assert e32_link.legacy_zones(parent)[0].subentry_id == sub.subentry_id
    assert er.async_get(hass).async_get(climate) is not None


@pytest.mark.asyncio
async def test_repairs_and_configure_offer_the_removal(hass, linked, badkamer, monkeypatch):
    from custom_components.open_thermostat import repairs
    from custom_components.open_thermostat.e32_link import update_legacy_rooms_issue
    parent, sub, source, *_ = await owner_setup(hass)
    update_legacy_rooms_issue(hass, parent)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent))
    assert issue.translation_key == "legacy_rooms" and issue.translation_placeholders["rooms"] == "Badkamer"
    flow = await repairs.async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass = hass; flow.handler = DOMAIN; flow.flow_id = "fix"
    e32 = linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    form = await flow.async_step_init()  # reads the E32 room plan for the list of what happens
    assert form["step_id"] == "legacy_rooms" and form["description_placeholders"]["rooms"] == "Badkamer"
    e32.fail_save = "controller_unreachable"  # a lost answer first
    progress = await flow.async_step_legacy_rooms({})
    assert progress["type"] in ("progress", "progress_done")
    await asyncio.wait([flow._legacy_task])
    done = await flow.async_step_legacy_rooms_removing()
    assert done["type"] == "progress_done" and done["step_id"] == "legacy_rooms"  # back to the form
    form = await flow.async_step_legacy_rooms()
    # The room is already removed in HA; the form now offers to finish the link.
    assert form["step_id"] == "legacy_rooms_finish" and form["errors"] == {"base": "connection_failed"}
    e32 = linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    await flow.async_step_legacy_rooms_finish({})
    await asyncio.wait([flow._legacy_task])
    await flow.async_step_legacy_rooms_removing()
    finished = await flow.async_step_legacy_rooms_done()
    assert finished["type"] == "create_entry"
    assert ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent)) is None
    assert saved_mqtt(e32)["native_shadow_source"] is None


@pytest.mark.asyncio
async def test_configure_advanced_lists_the_removal_only_while_needed(hass, linked, badkamer):
    from test_product_flow import option
    parent, *_ = await owner_setup(hass)
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {}
    manager = hass.config_entries.options
    menu = await option(manager, parent, "advanced_settings")
    assert "legacy_rooms" in menu["menu_options"]
    form = await manager.async_configure(menu["flow_id"], {"next_step_id": "legacy_rooms"})
    assert form["step_id"] == "legacy_rooms" and form["description_placeholders"]["count"] == "1"
    manager.async_abort(form["flow_id"])
    fresh = product(hass)
    hass.config_entries.async_update_entry(fresh, data={**fresh.data, setup.CONTROLLER_ADDRESS: "http://e32.local",
                                                        setup.CONTROLLER_PASSWORD: "x"})
    hass.data[DOMAIN][fresh.entry_id] = {}
    assert not e32_link.legacy_rooms_pending(fresh)
