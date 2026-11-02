"""E32 settings backups in Home Assistant (1.0): schedule, retention, Repairs, entities and restore.

A fake E32 answers POST /config/backup like ConfigBackupRoute.cpp: export seals
the secrets with the passphrase it is given, validate summarises and returns a
fingerprint, apply needs that fingerprint and refuses while the E32 controls
the boiler. No network, no real E32.
"""
from copy import deepcopy
from datetime import timedelta
import json
import logging
from types import MappingProxyType

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from custom_components.open_thermostat import e32_backup as module
from custom_components.open_thermostat import controller_link as link
from custom_components.open_thermostat.controller_link import BackupRejected, ControllerLinkError
from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_ID
from custom_components.open_thermostat.e32_backup import (E32Backups, PASSPHRASE, ensure_passphrase,
                                                          passphrase_only_update, retained, summary_text)
from custom_components.open_thermostat.e32_backup_entities import E32BackupButton, E32LastBackupSensor
from custom_components.open_thermostat.e32_backup_flow import restore_error
from custom_components.open_thermostat.product import configuration_snapshot
from custom_components.open_thermostat.support_diagnostics import scrub
from test_controller_link import BASE, CSRF, Response, login_responses, setup
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import FakeE32

ADDRESS, PASSWORD = "http://192.168.1.206", "secret"
IDENTITY = "e32_0123456789ab"
FIRMWARE = "v0.1.0-e32v2-beta.24"


class FakeBackupE32:
    """POST /config/backup of one E32: its host name stands for all its settings."""

    def __init__(self, hostname="openthermostat", identity=IDENTITY, address=ADDRESS, password=PASSWORD):
        self.hostname, self.identity, self.address, self.password = hostname, identity, address, password
        self.sealed_with = None  # the passphrase of the last export (the E32 never stores it)
        self.calls, self.logins = [], 0
        self.refuse = {}  # action -> (status, error)
        self.unreachable = False
        self.controls_boiler = False
        self.restarts = 0
        # The apply's answer never arrives: "after" it applied (a reset connection), "offline" and then
        # no answer at all for a while, "before" it applied anything (the request was lost on the way).
        self.lose_answer = None

    def client(self, address):
        e32 = self

        class Client:
            default_password = False

            async def __aenter__(self):
                if e32.unreachable or address != e32.address:
                    raise ControllerLinkError("controller_unreachable")
                return self

            async def __aexit__(self, *_):
                return None

            async def async_login(self, password):
                if password != e32.password:
                    raise link.ControllerLoginRejected()
                e32.logins += 1

            async def async_read(self, path):
                if path == "/config/device":
                    return {"hostname": e32.hostname, "mqtt": {"native_source_device_id": e32.identity}}, '"' + "a" * 64 + '"'
                assert path == "/status/version"
                return {"version": FIRMWARE}

            async def async_config_backup(self, request):
                e32.calls.append(deepcopy(request))
                action = request["action"]
                if action in e32.refuse:
                    raise BackupRejected(*e32.refuse[action])
                if action == "export":
                    e32.sealed_with = request.get("passphrase")
                    secrets = None if not request.get("passphrase") else {
                        "cipher": "aes-128-ccm", "kdf": "pbkdf2-sha256", "iterations": 16384,
                        "box": "5e" * 60}
                    return {"format": "openthermostat-e32-backup", "schema": 1, "firmware": FIRMWARE,
                            "board": "e32v2", "created": None, "secrets": secrets,
                            "not_included": ["wifi_password", "web_password"],
                            "network": {"hostname": e32.hostname, "mqtt": {"base": "fixture"}},
                            "heating": {"schema": 1, "mode": "active", "rooms": []}}, 200
                backup = request["backup"]
                if backup["secrets"] is not None and request.get("passphrase") != SEALED[0]:
                    raise BackupRejected(400, "wrong_passphrase")
                if e32.controls_boiler:
                    raise BackupRejected(409, "boiler_owned")
                wanted = backup["network"]["hostname"]
                fingerprint = (e32.hostname + ">" + wanted).encode().hex().ljust(64, "0")[:64]
                if action == "validate":
                    changes = [] if wanted == e32.hostname else [
                        {"section": "network", "field": "hostname", "from": e32.hostname, "to": wanted},
                        {"section": "network", "field": "mqtt.password", "hidden": True}]
                    return {"valid": True, "fingerprint": fingerprint, "restart": bool(changes),
                            "secrets_sealed": True, "secrets_restored": True, "language": None,
                            "changes": changes, "warnings": ["plan_mode_shadow", "unknown_key:network.future"],
                            "reenter": ["bluetooth_key:Zolder"]}, 200
                if request.get("fingerprint") != fingerprint:
                    raise BackupRejected(409, "settings_changed")
                if e32.lose_answer == "before":
                    raise ControllerLinkError("controller_unreachable")
                e32.hostname = wanted
                e32.restarts += 1
                if e32.lose_answer:
                    e32.unreachable = e32.lose_answer == "offline"
                    raise ControllerLinkError("controller_unreachable")
                return {"applied": True, "restart": True, "restart_scheduled": True, "restart_in_s": 0,
                        "language": None, "reenter": ["bluetooth_key:Zolder"]}, 201
        return Client()


SEALED = [None]  # the installation's passphrase, as the fake E32 checks it


async def backups(hass, parent, e32, monkeypatch=None):
    manager = E32Backups(hass, parent)
    manager._client = e32.client
    await manager.async_load()
    hass.data.setdefault("open_thermostat", {}).setdefault(parent.entry_id, {})[module.STATE_KEY] = manager
    SEALED[0] = ensure_passphrase(hass, parent)
    return manager


def at(days=0, hours=0):
    return dt_util.parse_datetime("2026-11-01T03:00:00+00:00") + timedelta(days=days, hours=hours)


def clock(monkeypatch, moment):
    monkeypatch.setattr(module, "_now", lambda: moment[0])


# -- the E32 client -------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_client_posts_a_backup_request_and_names_a_refusal(monkeypatch):
    big = {"format": "openthermostat-e32-backup", "pad": "x" * 20000}
    refusal = Response({"error": "boiler_owned", "warnings": ["w" * 40] * 30}, status=409)
    session, _ = setup(monkeypatch, *login_responses(), Response(big), refusal, Response({"authenticated": False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("password")
        value, status = await client.async_config_backup({"action": "export", "passphrase": "p" * 43})
        assert status == 200 and value == big  # larger than the 8 KB of the other routes
        with pytest.raises(BackupRejected) as refused:
            await client.async_config_backup({"action": "validate", "backup": big, "passphrase": "p" * 43})
    assert refused.value.error == "boiler_owned" and refused.value.status == 409
    assert "p" * 43 not in str(refused.value)
    post = session.calls[2]
    assert post[0] == "POST" and post[1] == BASE + "/config/backup"
    assert post[2]["headers"]["X-OpenThermostat-CSRF"] == CSRF
    assert json.loads(post[2]["data"]) == {"action": "export", "passphrase": "p" * 43}
    assert restore_error(refused.value) == "e32_restore_boiler_owned"


@pytest.mark.asyncio
async def test_a_request_larger_than_a_backup_never_leaves_home_assistant(monkeypatch):
    session, _ = setup(monkeypatch, *login_responses(), Response({"authenticated": False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("password")
        with pytest.raises(BackupRejected, match="backup_too_large"):
            await client.async_config_backup({"action": "validate", "backup": {"pad": "x" * 26000}})
        with pytest.raises(ControllerLinkError, match="controller_request_invalid"):
            await client.async_config_backup({"action": "anything"})
    assert not any(call[1].endswith("/config/backup") for call in session.calls)


@pytest.mark.asyncio
async def test_a_valid_backup_with_non_ascii_names_is_sent_as_utf8_and_never_too_large(monkeypatch):
    """valid_document measures UTF-8, so the request goes as UTF-8 too (no \\uXXXX escapes)."""
    doc = {"format": "openthermostat-e32-backup", "schema": 1, "board": "e32v2", "secrets": None,
           "heating": {"rooms": [{"name": "Łazienka ąęść żółw"} for _ in range(60)]}}
    doc["pad"] = "x" * (24576 - module._size(doc) - 20)
    assert module.valid_document(doc)
    assert len(json.dumps(doc, ensure_ascii=True, separators=(",", ":"))) > link.CONFIG_BACKUP_REQUEST_BYTES
    answer = {"valid": True, "fingerprint": "a" * 64, "restart": False}
    session, _ = setup(monkeypatch, *login_responses(), Response(answer), Response({"authenticated": False}))
    async with link.ControllerClient(BASE) as client:
        await client.async_login("password")
        value, status = await client.async_config_backup({"action": "validate", "backup": doc, "passphrase": "p" * 43})
    assert status == 200 and value == answer
    sent = session.calls[2][2]["data"]
    assert type(sent) is bytes and "Łazienka".encode() in sent and b"\\u" not in sent
    assert json.loads(sent)["backup"] == doc and len(sent) <= link.CONFIG_BACKUP_REQUEST_BYTES


# -- the passphrase ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_passphrase_is_made_once_kept_in_the_entry_and_needs_no_reload(hass):
    parent, _ = product(hass, FakeE32())
    before = configuration_snapshot(parent)
    first = ensure_passphrase(hass, parent)
    assert 8 <= len(first) <= 64 and parent.data[PASSPHRASE] == first
    state = hass.data["open_thermostat"][parent.entry_id]
    assert passphrase_only_update(state, parent) and not passphrase_only_update(state, parent)
    assert ensure_passphrase(hass, parent) == first  # never replaced: older backups stay readable
    # Never part of the public editor digest, and redacted from the diagnostics download.
    assert configuration_snapshot(parent) == before and first not in repr(configuration_snapshot(parent))
    assert first not in json.dumps(scrub({"data": dict(parent.data)}))


# -- scheduling ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_backup_is_made_at_start_when_due_and_then_once_a_day(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    moment = [at()]
    clock(monkeypatch, moment)
    scheduled = {}
    monkeypatch.setattr(module, "async_call_later", lambda h, delay, job: scheduled.setdefault("start", delay) and (lambda: None))
    monkeypatch.setattr(module, "async_track_time_interval",
                        lambda h, job, interval: scheduled.setdefault("interval", interval) and (lambda: None))
    manager = await backups(hass, parent, e32)
    manager.start()
    assert scheduled == {"start": module.START_DELAY, "interval": module.CHECK_INTERVAL}
    assert manager.due()  # no backup yet
    await manager.async_scheduled()
    assert [c["action"] for c in e32.calls] == ["export"] and e32.sealed_with == parent.data[PASSPHRASE]
    assert manager.records()[0]["kind"] == "daily" and manager.records()[0]["secrets"] is True
    moment[0] = at(hours=23)
    await manager.async_scheduled()
    assert len(e32.calls) == 1  # not yet due
    moment[0] = at(hours=24)
    await manager.async_scheduled()
    assert len(e32.calls) == 2
    # A restarted Home Assistant reads the stored backups: no new one within 24 hours.
    again = await backups(hass, parent, e32)
    assert again.records() == manager.records() and not again.due()
    manager.stop()


@pytest.mark.asyncio
async def test_a_failed_backup_is_recorded_and_retried_at_the_next_hourly_look(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    moment = [at()]
    clock(monkeypatch, moment)
    manager = await backups(hass, parent, e32)
    e32.unreachable = True
    await manager.async_scheduled()
    assert manager.last_error == "controller_unreachable" and manager.last_success is None
    e32.unreachable = False
    moment[0] = at(hours=1)
    await manager.async_scheduled()
    assert manager.last_error is None and manager.last_success == at(hours=1)


@pytest.mark.asyncio
async def test_a_refused_password_asks_for_the_new_one_and_is_not_tried_again(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32(password="changed")
    started = []
    monkeypatch.setattr(parent, "async_start_reauth", lambda h: started.append(True))
    manager = await backups(hass, parent, e32)
    for _ in range(2):
        with pytest.raises(link.ControllerLoginRejected):
            await manager.async_backup("manual")
    assert started == [True] and e32.logins == 0 and manager.last_error == "controller_auth_failed"


# -- retention ---------------------------------------------------------------------


def record(created, kind="daily"):
    return {"id": f"{abs(hash((created, kind))):016x}"[-16:], "kind": kind, "created": created.isoformat(),
            "size": 10, "document": {}}


def test_the_newest_backup_of_each_of_the_last_7_days_and_the_last_pre_restore_one_are_kept():
    records = [record(at(days=-d)) for d in range(10)]
    records += [record(at(days=-1, hours=5), "manual"), record(at(days=-3, hours=1), "manual")]
    records += [record(at(days=-2), "pre_restore"), record(at(days=-8), "pre_restore")]
    kept = retained(records)
    regular = [r for r in kept if r["kind"] != "pre_restore"]
    assert len(regular) == 7 and len({dt_util.as_local(module._created(r)).date() for r in regular}) == 7
    assert regular[1]["created"] == at(days=-1, hours=5).isoformat()  # the newest of that day wins
    assert regular[3]["created"] == at(days=-3, hours=1).isoformat()
    assert [r["created"] for r in kept if r["kind"] == "pre_restore"] == [at(days=-2).isoformat()]
    assert [r["created"] for r in kept] == sorted((r["created"] for r in kept), reverse=True)


@pytest.mark.asyncio
async def test_stored_backups_follow_the_retention_after_every_new_one(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    moment = [at()]
    clock(monkeypatch, moment)
    manager = await backups(hass, parent, e32)
    for day in range(9):
        moment[0] = at(days=day)
        await manager.async_backup("daily")
        await manager.async_backup("manual")  # the same day: replaces the earlier one
    assert len(manager.records()) == 7 and manager.records()[0]["kind"] == "manual"
    assert manager.records()[-1]["created"] == at(days=2).isoformat()


# -- Repairs -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repairs_warns_after_3_days_without_a_backup_and_clears_on_the_next_success(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    moment = [at()]
    clock(monkeypatch, moment)
    manager = await backups(hass, parent, e32)
    await manager.async_backup("daily")
    e32.unreachable = True
    issue = ("open_thermostat", module.issue_id(parent))
    for hours in (24, 48, 71):
        moment[0] = at(hours=hours)
        await manager.async_scheduled()
        assert ir.async_get(hass).async_get_issue(*issue) is None
    moment[0] = at(hours=72)
    await manager.async_scheduled()
    raised = ir.async_get(hass).async_get_issue(*issue)
    assert raised is not None and raised.translation_key == "e32_backup_failing"
    assert raised.severity == ir.IssueSeverity.WARNING and raised.translation_placeholders["name"] == parent.title
    e32.unreachable = False
    moment[0] = at(hours=73)
    await manager.async_scheduled()
    assert ir.async_get(hass).async_get_issue(*issue) is None


@pytest.mark.asyncio
async def test_repairs_also_warns_when_a_new_installation_never_got_a_backup(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    e32.unreachable = True
    moment = [at()]
    clock(monkeypatch, moment)
    manager = await backups(hass, parent, e32)
    moment[0] = at(days=3)
    await manager.async_scheduled()
    assert ir.async_get(hass).async_get_issue("open_thermostat", module.issue_id(parent)) is not None


# -- the button and the sensor ---------------------------------------------------------


@pytest.mark.asyncio
async def test_the_button_backs_up_now_and_the_sensor_shows_the_last_backup(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    moment = [at()]
    clock(monkeypatch, moment)
    manager = await backups(hass, parent, e32)
    button, sensor = E32BackupButton(parent, manager), E32LastBackupSensor(parent, manager)
    assert button.unique_id == "fixture_e32_backup_now" and sensor.unique_id == "fixture_e32_last_backup"
    assert button.entity_category == "config" and sensor.entity_category == "diagnostic"
    assert button.translation_key == "e32_backup_now" and sensor.device_class == "timestamp"
    assert sensor.native_value is None and sensor.extra_state_attributes == {"count": 0, "size": None}
    written = []
    manager.add_listener(lambda: written.append(True))
    await button.async_press()
    newest = manager.records()[0]
    assert newest["kind"] == "manual" and written
    assert sensor.native_value == at() and sensor.extra_state_attributes == {"count": 1, "size": newest["size"]}
    e32.unreachable = True
    with pytest.raises(HomeAssistantError) as failed:
        await button.async_press()
    assert failed.value.translation_key == "e32_backup_unreachable"
    e32.unreachable, e32.refuse = False, {"export": (409, "busy")}
    with pytest.raises(HomeAssistantError) as failed:
        await button.async_press()
    assert failed.value.translation_key == "e32_backup_busy"
    assert sensor.native_value == at() and sensor.extra_state_attributes["count"] == 1


# -- secrets -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_passphrase_password_or_secret_reaches_a_log_or_an_attribute(hass, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    manager = await backups(hass, parent, e32)
    passphrase = parent.data[PASSPHRASE]
    await manager.async_backup("manual")
    e32.unreachable = True
    with pytest.raises(ControllerLinkError):
        await manager.async_backup("manual")
    e32.unreachable = False
    e32.refuse = {"validate": (400, "wrong_passphrase")}
    with pytest.raises(BackupRejected) as refused:
        await manager.async_check(ADDRESS, PASSWORD, manager.records()[0]["id"])
    e32.refuse = {}
    check = await manager.async_check(ADDRESS, PASSWORD, manager.records()[0]["id"])
    texts = caplog.text + str(refused.value) + repr(check) + json.dumps(E32LastBackupSensor(parent, manager)
                                                                       .extra_state_attributes)
    for secret in (passphrase, PASSWORD, "5e" * 60):
        assert secret not in texts
    assert manager.last_error == "controller_unreachable"


# -- restore --------------------------------------------------------------------------


async def open_restore(manager_flow, parent):
    flow = await manager_flow.async_init(parent.entry_id)
    advanced = await manager_flow.async_configure(flow["flow_id"], {"next_step_id": "advanced_settings"})
    assert "e32_restore" in advanced["menu_options"]
    return await manager_flow.async_configure(flow["flow_id"], {"next_step_id": "e32_restore"})


async def finish(hass, manager_flow, result):
    """The step after a check or restore: its progress is always shown first, also for a quick answer."""
    assert result["type"] == FlowResultType.SHOW_PROGRESS, result
    await hass.async_block_till_done()
    return await manager_flow.async_configure(result["flow_id"])


@pytest.mark.asyncio
async def test_restore_checks_shows_the_summary_and_restores_only_after_the_tick(hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32(hostname="kelder")
    monkeypatch.setattr(module, "RESTART_POLL", 0)
    backup = await backups(hass, parent, e32)
    await backup.async_backup("daily")
    e32.hostname = "zolder"  # the settings changed (or a reset E32) after that backup
    form = await open_restore(manager, parent)
    assert form["step_id"] == "e32_restore" and form["description_placeholders"]["count"] == "1"
    chosen = backup.records()[0]["id"]
    confirm = await finish(hass, manager, await manager.async_configure(form["flow_id"], {
        "backup": chosen, "address": ADDRESS}))
    assert confirm["step_id"] == "e32_restore_confirm", confirm
    summary = confirm["description_placeholders"]["summary"]
    assert "Network · Device name: zolder → kelder" in summary and "MQTT password: will change" in summary
    assert "trial run" in summary and "future" in summary and "Bluetooth key for Zolder" in summary
    assert [c["action"] for c in e32.calls] == ["export", "validate"] and e32.hostname == "zolder"
    refused = await manager.async_configure(confirm["flow_id"], {"confirm": False})
    assert refused["errors"] == {"base": "e32_restore_confirm_required"} and e32.hostname == "zolder"
    done = await finish(hass, manager, await manager.async_configure(confirm["flow_id"], {"confirm": True}))
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "e32_restore_done_online", done
    assert "Bluetooth key for Zolder" in done["description_placeholders"]["reenter"]
    assert e32.hostname == "kelder" and e32.restarts == 1
    assert [c["action"] for c in e32.calls] == ["export", "validate", "export", "apply"]
    apply = e32.calls[-1]
    assert apply["passphrase"] == parent.data[PASSPHRASE] and apply["backup"] == backup.record(chosen)["document"]
    # The E32 as it was right before the restore is kept, next to the daily one.
    kinds = [r["kind"] for r in backup.records()]
    assert sorted(kinds) == ["daily", "pre_restore"]
    assert next(r for r in backup.records() if r["kind"] == "pre_restore")["document"]["network"]["hostname"] == "zolder"
    assert parent.data[CONTROLLER_ID] == IDENTITY


@pytest.mark.asyncio
async def test_a_restore_is_refused_while_the_e32_controls_the_boiler(hass, manager):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, e32)
    await backup.async_backup("daily")
    e32.hostname, e32.controls_boiler = "zolder", True
    form = await open_restore(manager, parent)
    again = await finish(hass, manager, await manager.async_configure(form["flow_id"], {
        "backup": backup.records()[0]["id"], "address": ADDRESS}))
    assert again["step_id"] == "e32_restore" and again["errors"] == {"base": "e32_restore_boiler_owned"}
    assert e32.hostname == "zolder" and "apply" not in [c["action"] for c in e32.calls]


@pytest.mark.asyncio
async def test_settings_changed_after_the_check_need_a_new_check(hass, manager):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, e32)
    await backup.async_backup("daily")
    e32.hostname = "zolder"
    form = await open_restore(manager, parent)
    confirm = await finish(hass, manager, await manager.async_configure(form["flow_id"], {
        "backup": backup.records()[0]["id"], "address": ADDRESS}))
    e32.hostname = "zolder2"  # someone saved on the E32 page meanwhile
    again = await finish(hass, manager, await manager.async_configure(confirm["flow_id"], {"confirm": True}))
    assert again["step_id"] == "e32_restore" and again["errors"] == {"base": "e32_restore_settings_changed"}
    assert e32.hostname == "zolder2"


@pytest.mark.asyncio
async def test_undoing_a_restore_never_loses_the_undo_point_when_the_apply_fails(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    monkeypatch.setattr(module, "RESTART_POLL", 0)
    e32 = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, e32)
    await backup.async_backup("daily")
    e32.hostname = "zolder"  # changed during the day: in no daily backup
    await backup.async_restore(await backup.async_check(ADDRESS, PASSWORD, backup.records()[0]["id"]))
    undo = next(r for r in backup.records() if r["kind"] == "pre_restore")
    assert undo["document"]["network"]["hostname"] == "zolder" and e32.hostname == "kelder"
    # Undo that restore; the E32 refuses the apply (busy): it is unchanged, and so are the backups.
    check = await backup.async_check(ADDRESS, PASSWORD, undo["id"])
    e32.refuse["apply"] = (503, "out_of_memory")
    with pytest.raises(BackupRejected):
        await backup.async_restore(check)
    assert backup.record(undo["id"]) == undo and e32.hostname == "kelder"
    assert [r["kind"] for r in backup.records()].count("pre_restore") == 1
    stored = await module.Store(hass, 1, module.store_key(parent.entry_id), private=True).async_load()
    assert any(r["id"] == undo["id"] for r in stored["backups"])
    # The retry works: "zolder" is back, and "kelder" is the new undo point.
    e32.refuse = {}
    await backup.async_restore(await backup.async_check(ADDRESS, PASSWORD, undo["id"]))
    assert e32.hostname == "zolder"
    after = [r for r in backup.records() if r["kind"] == "pre_restore"]
    assert [r["document"]["network"]["hostname"] for r in after] == ["kelder"]


def test_the_backup_being_restored_is_kept_next_to_the_new_undo_point():
    older, newer = record(at(days=-1), "pre_restore"), record(at(), "pre_restore")
    assert retained([older, newer]) == [newer]
    assert retained([older, newer], keep=(older["id"],)) == [newer, older]


@pytest.mark.asyncio
async def test_nothing_to_restore_and_no_backup_yet_are_said_plainly(hass, manager):
    parent, _ = product(hass, FakeE32())
    e32 = FakeBackupE32()
    backup = await backups(hass, parent, e32)
    flow = await manager.async_init(parent.entry_id)
    advanced = await manager.async_configure(flow["flow_id"], {"next_step_id": "advanced_settings"})
    empty = await manager.async_configure(advanced["flow_id"], {"next_step_id": "e32_restore"})
    assert empty["type"] == FlowResultType.ABORT and empty["reason"] == "e32_restore_no_backups"
    await backup.async_backup("daily")
    form = await open_restore(manager, parent)
    same = await finish(hass, manager, await manager.async_configure(form["flow_id"], {
        "backup": backup.records()[0]["id"], "address": ADDRESS}))
    assert same["type"] == FlowResultType.ABORT and same["reason"] == "e32_restore_nothing"


@pytest.mark.asyncio
async def test_a_replacement_e32_at_another_address_gets_the_settings_and_becomes_this_installations(
        hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32())
    old = FakeBackupE32(hostname="kelder")
    monkeypatch.setattr(module, "RESTART_POLL", 0)
    backup = await backups(hass, parent, old)
    await backup.async_backup("daily")
    hass.config_entries.async_update_entry(parent, data={**parent.data, CONTROLLER_ID: IDENTITY})
    new = FakeBackupE32(hostname="openthermostat", identity="e32_ba9876543210",
                        address="http://192.168.1.77", password="admin")
    backup._client = new.client
    form = await open_restore(manager, parent)
    chosen = backup.records()[0]["id"]
    # The stored password never goes to another address.
    missing = await manager.async_configure(form["flow_id"], {"backup": chosen, "address": "http://192.168.1.77"})
    assert missing["errors"] == {"base": "controller_password_required"} and new.calls == []
    confirm = await finish(hass, manager, await manager.async_configure(form["flow_id"], {
        "backup": chosen, "address": "http://192.168.1.77", "password": "admin"}))
    done = await finish(hass, manager, await manager.async_configure(confirm["flow_id"], {"confirm": True}))
    assert done["reason"] == "e32_restore_done_online" and new.hostname == "kelder"
    assert parent.data[CONTROLLER_ADDRESS] == "http://192.168.1.77" and parent.data[CONTROLLER_ID] == "e32_ba9876543210"
    assert parent.data["controller_password"] == "admin"


@pytest.mark.asyncio
async def test_a_replacement_that_already_holds_the_settings_is_used_after_a_tick(hass, manager):
    """Restored on its own page (or an earlier lost answer): nothing to restore, but use this E32 from now on."""
    parent, _ = product(hass, FakeE32())
    old = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, old)
    await backup.async_backup("daily")
    hass.config_entries.async_update_entry(parent, data={**parent.data, CONTROLLER_ID: IDENTITY})
    new = FakeBackupE32(hostname="kelder", identity="e32_ba9876543210",
                        address="http://192.168.1.77", password="admin")
    backup._client = new.client
    form = await open_restore(manager, parent)
    adopt = await finish(hass, manager, await manager.async_configure(form["flow_id"], {
        "backup": backup.records()[0]["id"], "address": "http://192.168.1.77", "password": "admin"}))
    assert adopt["step_id"] == "e32_restore_adopt", adopt
    assert adopt["description_placeholders"]["address"] == "http://192.168.1.77"
    # Never without the tick: showing the step or an unticked box changes nothing.
    assert parent.data[CONTROLLER_ADDRESS] == ADDRESS and parent.data[CONTROLLER_ID] == IDENTITY
    refused = await manager.async_configure(adopt["flow_id"], {"confirm": False})
    assert refused["errors"] == {"base": "e32_restore_adopt_confirm_required"}
    assert parent.data[CONTROLLER_ADDRESS] == ADDRESS and parent.data[CONTROLLER_ID] == IDENTITY
    done = await manager.async_configure(adopt["flow_id"], {"confirm": True})
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "e32_restore_adopted"
    assert parent.data[CONTROLLER_ADDRESS] == "http://192.168.1.77" and parent.data[CONTROLLER_ID] == "e32_ba9876543210"
    assert parent.data["controller_password"] == "admin"
    assert "apply" not in [c["action"] for c in new.calls] and new.hostname == "kelder"


@pytest.mark.asyncio
async def test_a_lost_restore_answer_is_checked_again_and_the_replacement_used(hass, manager, monkeypatch):
    """The E32 applied, but its answer never arrived: its check again finds nothing left, so it arrived."""
    parent, _ = product(hass, FakeE32())
    monkeypatch.setattr(module, "RESTART_POLL", 0)
    monkeypatch.setattr(module, "RESTART_DELAY", 0)
    old = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, old)
    await backup.async_backup("daily")
    hass.config_entries.async_update_entry(parent, data={**parent.data, CONTROLLER_ID: IDENTITY})
    new = FakeBackupE32(hostname="openthermostat", identity="e32_ba9876543210",
                        address="http://192.168.1.77", password="admin")
    new.lose_answer = "after"
    backup._client = new.client
    form = await open_restore(manager, parent)
    confirm = await finish(hass, manager, await manager.async_configure(form["flow_id"], {
        "backup": backup.records()[0]["id"], "address": "http://192.168.1.77", "password": "admin"}))
    done = await finish(hass, manager, await manager.async_configure(confirm["flow_id"], {"confirm": True}))
    assert done["reason"] == "e32_restore_done_online", done
    assert "Bluetooth key for Zolder" in done["description_placeholders"]["reenter"]
    assert [c["action"] for c in new.calls] == ["validate", "export", "apply", "validate"]
    assert new.hostname == "kelder" and parent.data[CONTROLLER_ADDRESS] == "http://192.168.1.77"
    assert parent.data[CONTROLLER_ID] == "e32_ba9876543210"
    assert sorted(r["kind"] for r in backup.records()) == ["daily", "pre_restore"]


@pytest.mark.asyncio
async def test_a_lost_restore_answer_never_counts_as_restored_unless_the_e32_check_says_so(
        hass, manager, monkeypatch):
    parent, _ = product(hass, FakeE32())
    monkeypatch.setattr(module, "RESTART_POLL", 0.01)
    monkeypatch.setattr(module, "RESTART_WAIT", 0.2)
    old = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, old)
    await backup.async_backup("daily")
    hass.config_entries.async_update_entry(parent, data={**parent.data, CONTROLLER_ID: IDENTITY})
    new = FakeBackupE32(hostname="openthermostat", identity="e32_ba9876543210",
                        address="http://192.168.1.77", password="admin")
    backup._client = new.client
    choice = {"backup": backup.records()[0]["id"], "address": "http://192.168.1.77", "password": "admin"}
    # The request was lost on its way: the check again still finds the changes.
    new.lose_answer = "before"
    form = await open_restore(manager, parent)
    confirm = await finish(hass, manager, await manager.async_configure(form["flow_id"], choice))
    again = await finish(hass, manager, await manager.async_configure(confirm["flow_id"], {"confirm": True}))
    assert again["step_id"] == "e32_restore" and again["errors"] == {"base": "e32_restore_not_applied"}
    assert new.hostname == "openthermostat" and parent.data[CONTROLLER_ADDRESS] == ADDRESS
    # Applied, and then no answer at all: not known; nothing is adopted.
    new.lose_answer = "offline"
    confirm = await finish(hass, manager, await manager.async_configure(again["flow_id"], choice))
    again = await finish(hass, manager, await manager.async_configure(confirm["flow_id"], {"confirm": True}))
    assert again["errors"] == {"base": "e32_restore_unconfirmed"} and new.hostname == "kelder"
    assert parent.data[CONTROLLER_ADDRESS] == ADDRESS and parent.data[CONTROLLER_ID] == IDENTITY
    # It answers again: choosing the backup once more offers to use it (it holds the settings now).
    new.unreachable, new.lose_answer = False, None
    adopt = await finish(hass, manager, await manager.async_configure(again["flow_id"], choice))
    assert adopt["step_id"] == "e32_restore_adopt"
    done = await manager.async_configure(adopt["flow_id"], {"confirm": True})
    assert done["reason"] == "e32_restore_adopted" and parent.data[CONTROLLER_ID] == "e32_ba9876543210"


@pytest.mark.asyncio
async def test_a_lost_answer_to_an_undo_keeps_both_undo_points(hass, monkeypatch):
    parent, _ = product(hass, FakeE32())
    monkeypatch.setattr(module, "RESTART_POLL", 0)
    monkeypatch.setattr(module, "RESTART_DELAY", 0)
    e32 = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, e32)
    await backup.async_backup("daily")
    e32.hostname = "zolder"
    await backup.async_restore(await backup.async_check(ADDRESS, PASSWORD, backup.records()[0]["id"]))
    undo = next(r for r in backup.records() if r["kind"] == "pre_restore")
    e32.lose_answer = "after"
    result = await backup.async_restore(await backup.async_check(ADDRESS, PASSWORD, undo["id"]))
    assert result["online"] is True and e32.hostname == "zolder"
    kept = sorted(r["document"]["network"]["hostname"] for r in backup.records() if r["kind"] == "pre_restore")
    assert kept == ["kelder", "zolder"]


def other_installation_entry(hass, **data):
    """A second OpenThermostat installation in the same Home Assistant, with its own E32."""
    item = ConfigEntry(domain="open_thermostat", title="other", version=2, minor_version=1,
                       data={"topic_prefix": "other", "adapter_id": "ha_other", **data}, options={},
                       source="user", unique_id="other", discovery_keys=MappingProxyType({}), subentries_data=[])
    hass.config_entries._entries[item.entry_id] = item
    return item


@pytest.mark.asyncio
@pytest.mark.parametrize("other_data,adapter_change", [
    ({CONTROLLER_ID: "e32_ba9876543210"}, False),            # the same E32 identity
    ({CONTROLLER_ADDRESS: "http://192.168.1.77/"}, False),   # the same address (normalised)
    ({}, True),                                              # the E32 is linked to the other installation
])
async def test_a_restore_never_takes_the_e32_of_another_installation(hass, manager, monkeypatch,
                                                                    other_data, adapter_change):
    parent, _ = product(hass, FakeE32())
    monkeypatch.setattr(module, "RESTART_POLL", 0)
    old = FakeBackupE32(hostname="kelder")
    backup = await backups(hass, parent, old)
    await backup.async_backup("daily")
    hass.config_entries.async_update_entry(parent, data={**parent.data, CONTROLLER_ID: IDENTITY})
    other = other_installation_entry(hass, **other_data)
    new = FakeBackupE32(hostname="openthermostat", identity="e32_ba9876543210",
                        address="http://192.168.1.77", password="admin")
    if adapter_change:
        validate = new.client

        def client(address):
            inner = validate(address)
            answer = inner.async_config_backup

            async def async_config_backup(request):
                value, status = await answer(request)
                if request["action"] == "validate":  # this restore moves the E32's link to this installation
                    value["changes"].append({"section": "network", "field": "mqtt.adapter_id",
                                             "from": "ha_other", "to": "ha1"})
                return value, status
            inner.async_config_backup = async_config_backup
            return inner
        backup._client = client
    else:
        backup._client = new.client
    choice = {"backup": backup.records()[0]["id"], "address": "http://192.168.1.77", "password": "admin"}
    form = await open_restore(manager, parent)
    refused = await finish(hass, manager, await manager.async_configure(form["flow_id"], choice))
    assert refused["step_id"] == "e32_restore" and refused["errors"] == {"base": "e32_restore_other_installation"}
    assert "apply" not in [c["action"] for c in new.calls] and new.hostname == "openthermostat"
    assert parent.data[CONTROLLER_ADDRESS] == ADDRESS and parent.data[CONTROLLER_ID] == IDENTITY
    # Holding the settings already (nothing to restore) is no way around it either.
    new.hostname = "kelder"
    refused = await finish(hass, manager, await manager.async_configure(refused["flow_id"], choice))
    assert refused["errors"] == {"base": "e32_restore_other_installation"}
    check = await backup.async_check("http://192.168.1.77", "admin", choice["backup"])
    assert backup.adopt(check) is False and parent.data[CONTROLLER_ID] == IDENTITY
    assert dict(other.data).get(CONTROLLER_ID) == other_data.get(CONTROLLER_ID)
    # Without the other installation the same E32 is this installation's replacement.
    hass.config_entries._entries.pop(other.entry_id)
    assert backup.adopt(check) is True and parent.data[CONTROLLER_ID] == "e32_ba9876543210"


def test_the_summary_is_plain_and_in_the_users_language():
    summary = {"changes": [{"section": "heating", "field": "rooms", "from": ["Hal"], "to": ["Hal", "Zolder"]},
                           {"section": "flow", "field": "weather_curve", "from": False, "to": True}],
               "warnings": ["plan_mode_shadow"], "reenter": ["mqtt_password"], "restart": False}
    english = summary_text(summary, "en")
    assert "Rooms: Hal → Hal, Zolder" in english and "Water temperature · Follow outdoor temperature (heating curve): Off → On" in english
    assert "The rooms are restored in the trial run." in english and "- MQTT password" in english
    dutch = summary_text(summary, "nl")
    assert "Stooklijn" not in dutch and "Buitentemperatuur volgen (stooklijn): Uit → Aan" in dutch
    assert "proefperiode" in dutch and "MQTT-wachtwoord" in dutch
    assert "Hasło MQTT" in summary_text(summary, "pl")


def test_the_summary_names_the_tuning_and_what_the_thermostat_learned():
    summary = {"changes": [{"section": "flow", "field": "tuning", "from": None, "to": None, "hidden": True},
                           {"section": "learned", "field": "learned", "from": None, "to": None, "hidden": True}],
               "warnings": ["learned_skipped"], "reenter": [], "restart": False}
    for language, words in (("en", ("Comfort and boiler care", "What the thermostat has learned", "keeps learning")),
                            ("nl", ("Comfort en zorg voor de ketel", "Wat de thermostaat heeft geleerd", "leert verder")),
                            ("pl", ("Komfort i dbałość o kocioł", "Czego nauczył się termostat", "uczy się dalej"))):
        text = summary_text(summary, language)
        assert all(word in text for word in words), (language, text)
        assert "- learned:" not in text and "tuning:" not in text and "learned_skipped" not in text
