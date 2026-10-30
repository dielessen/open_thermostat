"""A failed or refused E32 room-plan link never leaves the integration dead (HA 0.4.0b12).

Live on 30 Oct 2026: HA b11 with an E32 still on beta.18. "Remove the old
Home Assistant room" (Repairs) switched the link off, linked the E32 and then
waited for the beta.19 heating report that beta.18 never sends; the timeout
left the link off, so no runtime, no E32 room entities, no boiler values and no
ha/heating_input. These tests pin the fixes:

- the room-plan link stops before any change on firmware before beta.19, with
  a clear message (Repairs and Connect E32);
- a failure before the save switches the previous link on again, a failure
  after it keeps the saved link running (it authorizes no outputs); the native
  route only resumes when nothing reached the E32 (fail closed after that);
- the E32 telemetry, the forwarding and the boiler values need no link at all.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.components import mqtt
from homeassistant.helpers import entity_registry as er

from custom_components.open_thermostat import controller_setup_flow as setup
from custom_components.open_thermostat import e32_link
from custom_components.open_thermostat.const import DOMAIN
from custom_components.open_thermostat.controller_link import ControllerLinkError, ControllerProvisioningError
from custom_components.open_thermostat.heating_link import HeatingHub
from custom_components.open_thermostat.native_provisioning import SOURCE_OPTION, local_device_descriptor
from test_e32_room_plan_link import CONTROLLER, PlanE32, badkamer, linked, owner_setup, product  # noqa: F401
from test_heating_link import STATUS
from e32_telemetry import split_status

BETA18 = "v0.1.0-e32v2-beta.18"


def beta18(e32):
    e32.reads["/status/version"]["version"] = BETA18
    return e32


def changes(e32):
    return [call for call in e32.calls if call[0] in ("save", "reboot", "plan")]


@pytest.mark.parametrize("version,ok", [
    ("v0.1.0-e32v2-beta.19", True), ("v0.1.0-e32v2-beta.20", True), ("v0.1.0-e32v2-rc.1", True),
    ("v0.1.0-e32v2", True), ("v0.2.0-e32v2-alpha.1", True), ("v1.0.0-e32v2", True),
    (BETA18, False), ("v0.1.0-e32v2-alpha.30", False), ("v0.0.9-e32v2", False), (None, False), ("garbage", False)])
def test_room_plan_topics_need_beta_19_or_newer(version, ok):
    assert e32_link.room_plan_topics_firmware(version) is ok


# --- The owner's path, end to end ------------------------------------------------

@pytest.mark.asyncio
async def test_owner_path_beta18_remove_old_room_is_refused_and_nothing_is_switched_off(hass, linked, badkamer):
    """b11-era entry (older room Badkamer, native profile, link on) and an E32 on beta.18 (no beta.19 topics)."""
    from homeassistant.helpers import issue_registry as ir
    from custom_components.open_thermostat import repairs
    parent, sub, source, climate, *_ = await owner_setup(hass)
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"heating_hub": HeatingHub("fixture")}  # no heating report
    e32_link.update_legacy_rooms_issue(hass, parent)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent))
    before_options, before_data = dict(parent.options), dict(parent.data)
    e32 = linked["e32"] = beta18(PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1"))
    flow = await repairs.async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass, flow.handler, flow.flow_id = hass, DOMAIN, "fix"
    # The form already says what to do, before the user confirms anything.
    form = await flow.async_step_init()
    assert form["step_id"] == "legacy_rooms" and form["errors"] == {"base": "e32_update_required"}
    # Confirming anyway: refused before any change, with the same message.
    progress = await flow.async_step_legacy_rooms({})
    assert progress["type"] in ("progress", "progress_done")
    await asyncio.wait([flow._legacy_task])
    done = await flow.async_step_legacy_rooms_removing()
    assert done["type"] == "progress_done" and done["step_id"] == "legacy_rooms"
    form = await flow.async_step_legacy_rooms()
    assert form["errors"] == {"base": "e32_update_required"}
    # Nothing is left switched off or half changed: same entry, same room, nothing written to the E32.
    assert parent.options["shadow_enabled"] is True and dict(parent.options) == before_options
    assert dict(parent.data) == before_data and SOURCE_OPTION in parent.options
    assert e32_link.legacy_zones(parent)[0].subentry_id == sub.subentry_id
    assert er.async_get(hass).async_get(climate) is not None
    assert changes(e32) == [] and linked["waits"] == []
    assert e32.logout_confirmed  # every sign-in ends with a logout
    # The text tells the owner exactly what to do, in English and Dutch.
    from test_polish_translation import COMPONENT
    for name, words in (("strings.json", "beta.19"), ("translations/nl.json", "Werk de E32 eerst bij")):
        strings = json.loads((COMPONENT / name).read_text(encoding="utf-8"))
        assert words in strings["issues"]["legacy_rooms"]["fix_flow"]["error"]["e32_update_required"]


@pytest.mark.asyncio
async def test_connect_e32_on_old_firmware_is_refused_before_any_change(hass, linked):
    parent = product(hass)
    e32 = linked["e32"] = beta18(PlanE32())
    with pytest.raises(ControllerProvisioningError, match="controller_room_plan_update_required") as caught:
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert caught.value.device_may_have_changed is False
    assert changes(e32) == [] and setup.CONTROLLER_ID not in parent.data


@pytest.mark.asyncio
async def test_a_fresh_heating_report_proves_the_firmware(hass, linked):
    """Telemetry already arriving (beta.19 topics) is proof enough; the version string is not judged."""
    parent = product(hass)
    hub = HeatingHub("fixture")
    hub.update({"rooms": []})
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"heating_hub": hub}
    linked["e32"] = beta18(PlanE32())
    result = await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert result["room_ids"] == ["badkamer", "woonkamer"] and parent.options["shadow_enabled"] is True


# --- Failures after the E32 checks -------------------------------------------------

@pytest.mark.asyncio
async def test_a_link_that_is_not_confirmed_over_mqtt_keeps_running(hass, linked, monkeypatch):
    parent = product(hass)
    linked["e32"] = PlanE32()

    async def unconfirmed(*args, **kwargs):
        raise ControllerLinkError("controller_mqtt_unconfirmed")
    monkeypatch.setattr(setup, "async_wait_room_plan_link", unconfirmed)
    with pytest.raises(ControllerProvisioningError, match="controller_mqtt_unconfirmed"):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    # Saved and linked; the link stays on (it authorizes nothing) instead of a dead integration.
    assert parent.options["shadow_enabled"] is True and parent.data[setup.CONTROLLER_ID] == CONTROLLER


@pytest.mark.asyncio
async def test_a_cancelled_wait_keeps_the_saved_link_running(hass, linked, monkeypatch):
    parent = product(hass)
    linked["e32"] = PlanE32()

    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError
    monkeypatch.setattr(setup, "async_wait_room_plan_link", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert parent.options["shadow_enabled"] is True


@pytest.mark.asyncio
async def test_a_failure_before_the_save_switches_the_previous_link_on_again(hass, linked):
    parent = product(hass)
    linked["e32"] = PlanE32()
    await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert parent.options["shadow_enabled"] is True
    e32 = linked["e32"] = PlanE32()  # the E32 lost its link settings; this time the save is refused
    e32.fail_save = "controller_busy_or_conflict"
    with pytest.raises(ControllerProvisioningError, match="controller_busy_or_conflict"):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert parent.options["shadow_enabled"] is True


@pytest.mark.asyncio
async def test_a_room_plan_link_an_older_release_left_off_is_switched_on_again(hass, linked):
    """The owner's state after the b11 failure: linked, no native profile, link off."""
    parent = product(hass)
    hass.config_entries.async_update_entry(parent, data={**parent.data, setup.CONTROLLER_ADDRESS: "http://192.168.1.206",
        setup.CONTROLLER_PASSWORD: "e32-password", setup.CONTROLLER_ID: CONTROLLER},
        options={**parent.options, "shadow_enabled": False})
    e32 = linked["e32"] = beta18(PlanE32())
    with pytest.raises(ControllerProvisioningError, match="controller_room_plan_update_required"):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert changes(e32) == [] and parent.options["shadow_enabled"] is True


@pytest.mark.asyncio
async def test_a_failed_removal_after_the_e32_checks_leaves_the_link_on(hass, linked, badkamer):
    """Lost answer to the settings save after the older room was removed: the link is not left off."""
    from custom_components.open_thermostat.native_provisioning import local_device_descriptor as descriptor
    parent, sub, source, *_ = await owner_setup(hass)
    e32 = linked["e32"] = PlanE32(source=descriptor(source), modern=True, adapter="ha1")
    e32.fail_save = "controller_unreachable"
    with pytest.raises(ControllerProvisioningError):
        await setup.async_link_room_plan(hass, parent, "http://192.168.1.206", "e32-password",
                                         remove_legacy_rooms=True)
    assert not e32_link.legacy_zones(parent) and parent.options["shadow_enabled"] is True
    assert e32_link.legacy_rooms_pending(parent)  # Repairs still offers to finish it


@pytest.mark.asyncio
async def test_the_native_route_resumes_only_when_nothing_reached_the_e32(hass, linked, badkamer, monkeypatch):
    parent, sub, source, *_ = await owner_setup(hass)
    linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    monkeypatch.setattr(setup, "async_prepare_controller_link", AsyncMock(side_effect=ControllerLinkError("stop_here")))
    with pytest.raises(ControllerProvisioningError, match="stop_here"):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert parent.options["shadow_enabled"] is True  # reads only: the previous link runs again
    plan = SimpleNamespace(private_entry_state=None, settings_unchanged=True, needs_reboot=False)
    monkeypatch.setattr(setup, "async_prepare_controller_link", AsyncMock(return_value=plan))
    monkeypatch.setattr(setup, "async_provision_controller", AsyncMock(
        side_effect=ControllerProvisioningError("controller_unreachable", device_may_have_changed=True)))
    with pytest.raises(ControllerProvisioningError, match="controller_unreachable"):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert parent.options["shadow_enabled"] is False  # the E32 may have changed: fail closed (native route)


# --- No link needed for the E32 telemetry, the forwarding and the boiler values ----------------

def broker(monkeypatch):
    callbacks, published = {}, []
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock())

    async def subscribe(hass, topic, callback, **kwargs):
        callbacks.setdefault(topic, []).append(callback)
        return lambda: callbacks[topic].remove(callback)

    async def publish(hass, topic, payload, qos=0, retain=False):
        published.append((topic, payload))
    monkeypatch.setattr(mqtt, "async_subscribe", subscribe)
    monkeypatch.setattr(mqtt, "async_publish", publish)

    def send(suffix, payload, retain=False):
        topic = "fixture/v1/" + suffix
        for pattern, items in list(callbacks.items()):
            if pattern == topic or pattern.endswith("/+") and topic.startswith(pattern[:-1]) \
                    and "/" not in topic[len(pattern) - 1:]:
                for callback in list(items):
                    callback(SimpleNamespace(topic=topic, payload=payload, retain=retain))
    return callbacks, published, send


@pytest.mark.asyncio
async def test_e32_telemetry_forwarding_and_boiler_values_work_with_the_link_off(hass, monkeypatch):
    from custom_components.open_thermostat.heating_link import async_setup_heating_link
    from custom_components.open_thermostat.v1_boiler_fields import (SOURCE_KEY, async_setup_boiler_fields,
                                                                    field_unique_id)
    from test_boiler_state import group_doc
    parent = product(hass)
    assert parent.options.get("shadow_enabled", False) is False
    # Before Connect E32 nothing is set up without the link (no rows that can only stay unavailable).
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"v1_runtime": SimpleNamespace(enabled=False)}
    added = []
    await async_setup_boiler_fields(hass, parent, added.extend)
    await async_setup_heating_link(hass, parent, added.extend)
    assert added == []
    hass.config_entries.async_update_entry(parent, data={**parent.data, setup.CONTROLLER_ADDRESS: "http://e32.local",
        setup.CONTROLLER_PASSWORD: "e32-password", setup.CONTROLLER_ID: CONTROLLER})
    runtime = SimpleNamespace(enabled=False)
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"v1_runtime": runtime}  # no v1_connection
    callbacks, published, send = broker(monkeypatch)
    added = []
    await async_setup_boiler_fields(hass, parent, lambda entities, **kw: added.extend(entities))
    await async_setup_heating_link(hass, parent, lambda entities, **kw: added.extend(entities))
    await hass.async_block_till_done()
    assert "fixture/v1/fw/state/heating" in callbacks and "fixture/v1/fw/state/boiler_fields/+" in callbacks
    hass.states.async_set("climate.woonkamer", "heat", {"current_temperature": 20.4, "temperature": 21})
    send("fw/heartbeat", json.dumps({"schema": 1, "uptime_s": 100}))
    for suffix, document in split_status(STATUS):
        send(suffix, json.dumps(document), retain=True)
    for group in range(7):
        send(f"fw/state/boiler_fields/{group}", group_doc(group), retain=True)
    await hass.async_block_till_done()
    state = hass.data[DOMAIN][parent.entry_id]
    assert state["heating_hub"].fresh and SOURCE_KEY in state
    ids = {getattr(entity, "unique_id", None): entity for entity in added}
    assert "fixture_e32_room_woonkamer_temperature" in ids
    assert ("fixture/v1/ha/heating_input", json.dumps({"entity": "climate.woonkamer", "temperature": 20.4,
                                                       "target": 21.0}, separators=(",", ":"))) in published \
        or any(topic == "fixture/v1/ha/heating_input" for topic, _ in published)
    flow = ids["fixture_boiler_fields_v1_measured_flow_temperature"]
    assert flow.available and flow.native_value == 45


# --- Cancellation (the progress dialog closed) at every point ------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["migration", "handover", "prepare", "provision", "wait"])
async def test_a_cancelled_room_removal_never_leaves_the_link_off(hass, linked, badkamer, monkeypatch, where):
    from custom_components.open_thermostat import legacy_room_migration as migrate
    parent, sub, source, *_ = await owner_setup(hass)
    linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError
    if where == "migration":
        monkeypatch.setattr(migrate, "async_write_migration", cancel)
    elif where == "handover":
        monkeypatch.setattr(migrate, "async_apply_handover", cancel)
    elif where == "prepare":
        monkeypatch.setattr(setup, "async_prepare_room_plan_link", cancel)
    elif where == "provision":
        monkeypatch.setattr(setup, "async_provision_room_plan", cancel)
    else:
        monkeypatch.setattr(setup, "async_wait_room_plan_link", cancel)
    with pytest.raises(asyncio.CancelledError):
        await setup.async_link_room_plan(hass, parent, "http://192.168.1.206", "e32-password",
                                         remove_legacy_rooms=True)
    assert parent.options["shadow_enabled"] is True, where


@pytest.mark.asyncio
async def test_a_cancelled_native_connect_fails_closed_once_the_e32_may_change(hass, linked, badkamer, monkeypatch):
    parent, sub, source, *_ = await owner_setup(hass)
    linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError
    # Cancelled during the reads: nothing reached the E32, the previous link runs again.
    monkeypatch.setattr(setup, "async_prepare_controller_link", cancel)
    with pytest.raises(asyncio.CancelledError):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert parent.options["shadow_enabled"] is True
    # Cancelled while provisioning: the E32 may have changed, so the link stays off.
    plan = SimpleNamespace(private_entry_state=None, settings_unchanged=True, needs_reboot=False)
    monkeypatch.setattr(setup, "async_prepare_controller_link", AsyncMock(return_value=plan))
    monkeypatch.setattr(setup, "async_provision_controller", cancel)
    with pytest.raises(asyncio.CancelledError):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert parent.options["shadow_enabled"] is False


@pytest.mark.asyncio
async def test_an_unusable_saved_native_profile_starts_without_it_and_offers_the_fix(hass, linked, badkamer,
                                                                                     monkeypatch):
    import custom_components.open_thermostat as integration
    from homeassistant.exceptions import ConfigEntryError
    from homeassistant.helpers import issue_registry as ir
    parent, sub, source, *_ = await owner_setup(hass)

    def unusable(entry):
        raise ConfigEntryError("native_plan_profile_unsupported")
    monkeypatch.setattr(integration, "_selected_native_plan_source", unusable)
    monkeypatch.setattr(mqtt, "async_wait_for_mqtt_client", AsyncMock(return_value=True))
    monkeypatch.setattr(mqtt, "async_subscribe", AsyncMock(return_value=lambda: None))
    publish = AsyncMock()
    monkeypatch.setattr(mqtt, "async_publish", publish)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True))
    try:
        assert await integration.async_setup_entry(hass, parent)
        state = hass.data[DOMAIN][parent.entry_id]
        assert not state["v1_runtime"].enabled and "v1_connection" not in state
        publish.assert_not_called()
        assert ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent)) is not None
    finally:
        if parent.entry_id in hass.data.get(DOMAIN, {}):
            assert await integration.async_unload_entry(hass, parent)
        await parent._async_process_on_unload(hass)


@pytest.mark.asyncio
async def test_repairs_shows_the_real_error_when_the_link_fails_after_the_room_is_gone(hass, linked, badkamer,
                                                                                       monkeypatch):
    """Not "nothing to remove": the old room is gone, the link is not confirmed; say so and offer a retry."""
    from homeassistant.helpers import issue_registry as ir
    from custom_components.open_thermostat import repairs
    parent, sub, source, *_ = await owner_setup(hass)
    e32_link.update_legacy_rooms_issue(hass, parent)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, e32_link.issue_id(parent))
    linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    confirmed = setup.async_wait_room_plan_link

    async def unconfirmed(*args, **kwargs):
        raise ControllerLinkError("controller_mqtt_unconfirmed")
    monkeypatch.setattr(setup, "async_wait_room_plan_link", unconfirmed)
    flow = await repairs.async_create_fix_flow(hass, issue.issue_id, issue.data)
    flow.hass, flow.handler, flow.flow_id = hass, DOMAIN, "fix"
    form = await flow.async_step_init()
    await flow.async_step_legacy_rooms({})
    await asyncio.wait([flow._legacy_task])
    done = await flow.async_step_legacy_rooms_removing()
    assert done["type"] == "progress_done"
    form = await flow.async_step_legacy_rooms()
    assert not e32_link.legacy_zones(parent) and not e32_link.legacy_rooms_pending(parent)
    assert form["type"] == "form" and form["step_id"] == "legacy_rooms_finish", form
    assert form["errors"] == {"base": "mqtt_unconfirmed"}
    assert parent.options["shadow_enabled"] is True
    # The E32 reaches Home Assistant now: submitting finishes the link.
    monkeypatch.setattr(setup, "async_wait_room_plan_link", confirmed)
    linked["e32"] = PlanE32(modern=True, adapter="ha1")
    linked["e32"].settings["mqtt"].update(base="fixture", native_shadow_source=None)
    await flow.async_step_legacy_rooms_finish({})
    await asyncio.wait([flow._legacy_task])
    await flow.async_step_legacy_rooms_removing()
    assert (await flow.async_step_legacy_rooms_done())["type"] == "create_entry"


@pytest.mark.asyncio
async def test_unload_callbacks_return_nothing(hass, monkeypatch):
    """Home Assistant awaits a truthy unload callback result as a coroutine; one TypeError skips the rest."""
    from custom_components.open_thermostat.v1_boiler_fields import SOURCE_KEY, _async_retained_source
    parent = product(hass)
    state = hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {}
    callbacks, published, send = broker(monkeypatch)
    callbacks_before = len(parent._on_unload or [])
    await _async_retained_source(hass, parent, state)
    added = (parent._on_unload or [])[callbacks_before:]
    assert SOURCE_KEY in state and added
    for callback in added:
        assert callback() is None
    assert SOURCE_KEY not in state


# --- Review follow-ups ------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["room_plan", "native"])
async def test_a_cancel_while_the_link_stops_never_leaves_it_stopped_but_on(hass, linked, badkamer, route):
    """The saved switch goes off before the running link stops, so the resume always sees it."""
    if route == "room_plan":
        parent = product(hass)
        hass.config_entries.async_update_entry(parent, options={**parent.options, "shadow_enabled": True})
        linked["e32"] = PlanE32()
    else:
        parent, sub, source, *_ = await owner_setup(hass)
        linked["e32"] = PlanE32(source=local_device_descriptor(source), modern=True, adapter="ha1")
    stopped = []

    async def stop():
        stopped.append(parent.options["shadow_enabled"])
        raise asyncio.CancelledError
    runtime = SimpleNamespace(enabled=True, async_stop=stop, native_plan_source=None)
    hass.data.setdefault(DOMAIN, {})[parent.entry_id] = {"v1_runtime": runtime}
    with pytest.raises(asyncio.CancelledError):
        await setup.async_connect_installation(hass, parent, "http://192.168.1.206", "e32-password")
    assert stopped == [False]  # the switch was already off when the link stopped
    assert parent.options["shadow_enabled"] is True  # and the cancel switched it on again (a reload restarts it)


def test_a_user_cannot_switch_the_link_off_for_a_linked_product_entry():
    """Why a room-plan entry found "off" may be switched on again by Connect E32 (_room_plan_linked)."""
    import re
    from test_polish_translation import COMPONENT
    writers = {}
    for path in COMPONENT.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"CONF_ENABLED\s*:\s*(False|mode ==)", text):
            writers[path.name] = text
    # Only Connect E32 itself, the non-product options form and the native-profile edits
    # (which always save a native profile, so the entry is not a room-plan link) set it.
    assert set(writers) == {"controller_setup_flow.py", "v1_config_flow.py", "installation_edit.py",
                            "room_profile_apply.py"}, sorted(writers)
    for name in ("installation_edit.py", "room_profile_apply.py"):
        assert "SOURCE_OPTION" in writers[name]
    from custom_components.open_thermostat.config_flow import OpenThermostatConfigFlow
    from custom_components.open_thermostat.product_flow import ProductOptionsFlow
    from custom_components.open_thermostat.product import PRODUCT_CONFIG
    entry = SimpleNamespace(data={PRODUCT_CONFIG: 1}, options={})
    assert isinstance(OpenThermostatConfigFlow.async_get_options_flow(entry), ProductOptionsFlow)


@pytest.mark.asyncio
async def test_the_repairs_precheck_never_holds_the_form_up(hass, monkeypatch):
    import time
    parent = product(hass)
    hass.config_entries.async_update_entry(parent, data={**parent.data, setup.CONTROLLER_ADDRESS: "http://e32.local",
                                                         setup.CONTROLLER_PASSWORD: "e32-password"})

    class Hanging:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def async_login(self, password):
            await asyncio.sleep(60)
    monkeypatch.setattr(setup, "ControllerClient", lambda address: Hanging())
    monkeypatch.setattr(e32_link, "PRECHECK_SECONDS", 0.05)
    started = time.monotonic()
    assert await e32_link.async_room_plan_firmware_problem(hass, parent) is None
    assert time.monotonic() - started < 2
    assert e32_link.PRECHECK_SECONDS == 0.05
