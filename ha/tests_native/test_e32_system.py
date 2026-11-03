"""E32 system settings from Home Assistant (rc.3): the system log, the time zone and a restart.

Each request is the one the E32 page sends (``/config/logging`` with all fields, the device
settings with the read's ETag and nothing else changed, ``/updates/reboot``), each in one
sign-in that is closed again, values the E32 would refuse never leave Home Assistant, older
firmware is told to update, and every text exists in English, Dutch and Polish.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from custom_components.open_thermostat import controller_link as link_module
from custom_components.open_thermostat import e32_system as module
from custom_components.open_thermostat.controller_link import ControllerLinkError
from test_controller_link import BASE, Response, login_responses, setup
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import FakeE32 as PlanE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
TAG = '"' + "e" * 64 + '"'
LOGGING = {"syslog_enabled": False, "server": "", "port": 514, "syslog_level": 3, "web_level": 3,
           "mark_interval_s": 0, "syslog_esp": True, "syslog_ems": False}
DEVICE = {"hostname": "", "listenPort": 80, "ntpEnabled": True, "ntpHost": "pool.ntp.org", "timeZone": "UTC0",
          "ntpUtcOffset": 0, "ntpDaylightUtcOffset": 0, "openweather": {"enabled": False, "appid": ""},
          "mqtt": {"enabled": True, "brokerAddress": "192.168.1.2", "brokerPort": 1883, "username": "ot",
                   "password": "", "base": "fixture", "modern_shadow": True, "adapter_id": "ha_1",
                   "native_source_device_id": "e32_aabbccddeeff", "native_source_live_apply": False},
          "bt": {"scanTime": 30}, "unknown_later_field": [1, 2]}


class FakeE32(PlanE32):
    """The room plan plus /config/logging, /config/device (ETag per read) and /updates/reboot."""

    def __init__(self, logging=LOGGING):
        super().__init__()
        self.logging = deepcopy(logging)
        self.device = deepcopy(DEVICE)
        self.requests, self.closed = [], 0
        self.logging_missing = False
        self.fail = None
        self.reboot_fail = None
        self.tags = 0

    def client(self, address):
        client = super().client(address)
        e32 = self
        exit_ = client.__class__.__aexit__

        async def logging(document=None):
            e32.requests.append(("logging", deepcopy(document), e32.logins))
            if e32.logging_missing:
                raise ControllerLinkError("controller_update_required")
            if document is not None:
                if e32.fail:
                    raise e32.fail
                if set(document) not in (set(LOGGING), set(LOGGING) - {"syslog_esp", "syslog_ems"}):
                    raise ControllerLinkError("controller_settings_invalid")
                e32.logging.update(document)
            return deepcopy(e32.logging)

        async def read(path):
            assert path == "/config/device"
            e32.tags += 1
            e32.requests.append(("read_device", None, e32.logins))
            return deepcopy(e32.device), f'"{e32.tags:064d}"'

        async def save(document, etag):
            e32.requests.append(("save_device", deepcopy(document), etag))
            if etag != f'"{e32.tags:064d}"':
                raise ControllerLinkError("controller_settings_changed")
            e32.device = {**deepcopy(document), "mqtt": {**document["mqtt"],
                          "native_source_device_id": "e32_aabbccddeeff", "native_source_live_apply": False}}

        async def reboot():
            e32.requests.append(("reboot", None, e32.logins))
            if e32.reboot_fail:
                raise e32.reboot_fail

        class Client(client.__class__):
            async def __aexit__(self, *args):
                e32.closed += 1
                return await exit_(self, *args)
        client.__class__ = Client
        client.async_logging, client.async_read = logging, read
        client.async_save_settings, client.async_reboot = save, reboot
        return client


async def advanced(manager, parent, step):
    await manager.hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    menu = await manager.async_configure(flow["flow_id"], {"next_step_id": "advanced_settings"})
    assert step in menu["menu_options"]
    return await manager.async_configure(menu["flow_id"], {"next_step_id": step})


def defaults(form):
    out = {}
    for key in form["data_schema"].schema:
        suggested = (key.description or {}).get("suggested_value")
        out[str(key)] = suggested if suggested is not None else (key.default() if callable(key.default) else None)
    return out


# -- the system log ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_system_log_settings_are_read_and_saved_whole_in_one_sign_in(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await advanced(manager, parent, "e32_logging")
    assert form["step_id"] == "e32_logging"
    assert defaults(form) == {"syslog_enabled": False, "server": None, "port": 514, "syslog_level": "3",
                              "syslog_esp": True, "syslog_ems": False, "web_level": "3", "mark_interval_s": 0}
    assert e32.requests[-1][:2] == ("logging", None)
    closed = e32.closed
    done = await manager.async_configure(form["flow_id"], {
        "syslog_enabled": True, "server": " 192.168.1.10 ", "port": 5140, "syslog_level": "4",
        "syslog_esp": True, "syslog_ems": True, "web_level": "2", "mark_interval_s": 600})
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "e32_logging_saved"
    assert e32.requests[-1][1] == {"syslog_enabled": True, "server": "192.168.1.10", "port": 5140, "syslog_level": 4,
                                   "web_level": 2, "mark_interval_s": 600, "syslog_esp": True, "syslog_ems": True}
    assert e32.closed == closed + 1  # one sign-in for the change, closed again


@pytest.mark.asyncio
@pytest.mark.parametrize("change,field,error", [
    ({"syslog_enabled": True, "server": ""}, "server", "e32_log_server_invalid"),
    ({"server": "192.168.1.010"}, "server", "e32_log_server_invalid"),
    ({"server": "224.0.0.1"}, "server", "e32_log_server_invalid"),
    ({"server": "syslog.local"}, "server", "e32_log_server_invalid"),
    ({"port": 514.5}, "port", "e32_log_number_invalid"),
])
async def test_log_settings_the_e32_would_refuse_never_leave_home_assistant(hass, manager, change, field, error):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await advanced(manager, parent, "e32_logging")
    values = {**{k: v for k, v in defaults(form).items() if v is not None}, **change}
    again = await manager.async_configure(form["flow_id"], values)
    assert again["errors"] == {field: error}
    assert [r for r in e32.requests if r[1] is not None] == []


@pytest.mark.asyncio
async def test_unchanged_log_settings_and_older_firmware(hass, manager):
    e32 = FakeE32(logging={k: v for k, v in LOGGING.items() if k not in ("syslog_esp", "syslog_ems")})
    parent, _ = product(hass, e32)
    form = await advanced(manager, parent, "e32_logging")
    # Firmware without the message choice: neither shown nor sent.
    assert "syslog_esp" not in defaults(form)
    done = await manager.async_configure(form["flow_id"], {k: v for k, v in defaults(form).items() if v is not None})
    assert done["reason"] == "e32_settings_unchanged" and all(r[1] is None for r in e32.requests)
    form = await advanced(manager, parent, "e32_logging")
    done = await manager.async_configure(form["flow_id"], {**{k: v for k, v in defaults(form).items() if v is not None},
                                                           "web_level": "4"})
    assert done["reason"] == "e32_logging_saved" and set(e32.requests[-1][1]) == set(LOGGING) - {"syslog_esp", "syslog_ems"}
    e32.logging_missing = True
    done = await advanced(manager, parent, "e32_logging")
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "e32_settings_update_required"


@pytest.mark.asyncio
async def test_a_refused_log_setting_is_a_form_error_without_a_retry(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await advanced(manager, parent, "e32_logging")
    e32.fail = ControllerLinkError("controller_settings_unconfirmed")
    values = {**{k: v for k, v in defaults(form).items() if v is not None}, "web_level": "1"}
    again = await manager.async_configure(form["flow_id"], values)
    assert again["errors"] == {"base": "e32_settings_unconfirmed"}
    assert len([r for r in e32.requests if r[1] is not None]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(400, "controller_settings_invalid"), (404, "controller_update_required"),
                                         (503, "controller_settings_unconfirmed")])
async def test_the_client_names_the_e32_logging_refusals(monkeypatch, status, code):
    session, _ = setup(monkeypatch, *login_responses(), Response(raw=b"Invalid logging settings", status=status),
                       Response({"authenticated": False}))
    async with link_module.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        with pytest.raises(ControllerLinkError, match="^" + code + "$"):
            await client.async_logging(dict(LOGGING))
    assert [c[1].removeprefix(BASE) for c in session.calls] == ["/auth/login", "/auth/session", "/config/logging",
                                                                "/auth/logout"]
    sent = session.calls[2]
    assert sent[0] == "POST" and json.loads(sent[2]["data"]) == LOGGING


# -- the time zone -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_time_zone_follows_home_assistant_and_only_it_changes(hass, manager):
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    form = await advanced(manager, parent, "e32_time_zone")
    assert form["step_id"] == "e32_time_zone"
    assert form["description_placeholders"]["e32"] == "UTC" and form["description_placeholders"]["home"] == "Europe/Amsterdam"
    assert defaults(form) == {"time_zone": "Europe/Amsterdam"}  # Home Assistant's own zone first
    e32.requests.clear()
    done = await manager.async_configure(form["flow_id"], {"time_zone": "Europe/Amsterdam"})
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "e32_time_zone_saved"
    assert [r[0] for r in e32.requests] == ["read_device", "save_device", "read_device", "reboot"]
    saved = e32.requests[1]
    expected = deepcopy(DEVICE)
    expected["timeZone"] = "CET-1CEST,M3.5.0,M10.5.0/3"
    for shown_only in ("native_source_device_id", "native_source_live_apply"):
        expected["mqtt"].pop(shown_only)
    assert saved[1] == expected  # everything else back unchanged, the secrets stay on the E32
    assert saved[2] == f'"{2:064d}"'  # the ETag of this sign-in's own read
    assert len({r[2] for r in e32.requests if r[0] != "save_device"}) == 1  # one sign-in for all of it


@pytest.mark.asyncio
async def test_a_time_zone_changed_meanwhile_or_the_same_zone_writes_nothing(hass, manager):
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    e32 = FakeE32()
    e32.device["timeZone"] = "CET-1CEST-2,M3.5.0/02:00:00,M10.5.0/03:00:00"  # the beta.17 text for the same rules
    parent, _ = product(hass, e32)
    form = await advanced(manager, parent, "e32_time_zone")
    assert form["description_placeholders"]["e32"] == "Europe/Amsterdam"
    done = await manager.async_configure(form["flow_id"], {"time_zone": "Europe/Berlin"})
    assert done["reason"] == "e32_settings_unchanged" and "save_device" not in [r[0] for r in e32.requests]
    form = await advanced(manager, parent, "e32_time_zone")
    e32.device["timeZone"] = "GMT0BST,M3.5.0/1,M10.5.0"  # changed on the E32 page meanwhile
    again = await manager.async_configure(form["flow_id"], {"time_zone": "Europe/Lisbon"})
    assert again["errors"] == {"base": "e32_settings_changed"}
    assert "save_device" not in [r[0] for r in e32.requests] and "reboot" not in [r[0] for r in e32.requests]


def test_time_zones_match_the_e32_list():
    page = (Path(__file__).resolve().parents[2] / "data/html/network.html").read_text(encoding="utf-8")
    for posix, zones in module.TIME_ZONES.items():
        assert f"['{posix}','{' '.join(zones)}']" in page, posix
    assert module.zone_of("CET-1CEST,M3.5.0,M10.5.0/3", "Europe/Paris") == "Europe/Paris"
    assert module.zone_of("CET-1CEST,M3.5.0,M10.5.0/3") == "Europe/Amsterdam" and module.zone_of("xyz") is None


# -- Repairs: another time zone on the E32 -----------------------------------------------


def zone_issue(hass, parent):
    return ir.async_get(hass).async_get_issue("open_thermostat", module.time_zone_issue_id(parent))


class Backups:
    """The settings backups as the check sees them: the newest record's network section."""

    def __init__(self, zone):
        self.zone, self.listeners = zone, []

    def records(self):
        return [{"document": {"network": {"timeZone": self.zone}}}] if self.zone else []

    def add_listener(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)


@pytest.mark.asyncio
async def test_another_time_zone_on_the_e32_is_a_repair_that_clears_itself(hass):
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    parent, _ = product(hass, FakeE32())
    backups = Backups("UTC0")
    remove = module.setup_time_zone_check(hass, parent, backups)
    issue = zone_issue(hass, parent)
    assert issue is not None and issue.is_fixable and issue.translation_key == "e32_time_zone"
    assert issue.translation_placeholders["e32"] == "UTC" and issue.translation_placeholders["home"] == "Europe/Amsterdam"
    # The next backup has the same rules (also in the beta.17 text): the issue goes.
    backups.zone = "CET-1CEST-2,M3.5.0/02:00:00,M10.5.0/03:00:00"
    backups.listeners[0]()
    assert zone_issue(hass, parent) is None
    # Home Assistant moves to London: the last seen E32 zone is checked again.
    await hass.config.async_update(time_zone="Europe/London")
    await hass.async_block_till_done()
    assert zone_issue(hass, parent) is not None
    # A Home Assistant zone the E32 does not list: nothing to fix from here.
    await hass.config.async_update(time_zone="Asia/Kathmandu")
    await hass.async_block_till_done()
    assert zone_issue(hass, parent) is None
    remove()
    assert backups.listeners == []


@pytest.mark.asyncio
async def test_the_repair_sets_home_assistant_s_zone_in_one_sign_in(hass):
    await hass.config.async_set_time_zone("Europe/Amsterdam")
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    await hass.async_block_till_done()
    module.check_time_zone(hass, parent, "UTC0")
    from custom_components.open_thermostat.repairs import async_create_fix_flow
    flow = await async_create_fix_flow(hass, module.time_zone_issue_id(parent), {"entry_id": parent.entry_id})
    assert isinstance(flow, module.TimeZoneRepairFlow)
    flow.hass = hass
    form = await flow.async_step_init()
    assert form["step_id"] == "confirm_time_zone" and form["description_placeholders"]["home"] == "Europe/Amsterdam"
    e32.requests.clear()
    done = await flow.async_step_confirm_time_zone({})
    assert done["type"] == FlowResultType.CREATE_ENTRY
    assert [r[0] for r in e32.requests] == ["read_device", "save_device", "read_device", "reboot"]
    assert e32.requests[1][1]["timeZone"] == "CET-1CEST,M3.5.0,M10.5.0/3"
    assert zone_issue(hass, parent) is None
    # Refused: the form says why and the issue stays.
    module.check_time_zone(hass, parent, "UTC0")
    e32.reboot_fail = ControllerLinkError("controller_busy_or_conflict")
    again = await flow.async_step_confirm_time_zone({})
    assert again["errors"] == {"base": "e32_settings_busy"} and zone_issue(hass, parent) is not None


def test_the_time_zone_repair_texts_exist_in_every_language():
    for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json"):
        issue = json.loads((COMPONENT / name).read_text(encoding="utf-8"))["issues"]["e32_time_zone"]
        step = issue["fix_flow"]["step"]["confirm_time_zone"]
        assert issue["title"] and "{home}" in step["description"] and "{e32}" in step["description"], name
        assert {"e32_settings_busy", "e32_settings_unreachable"} <= set(issue["fix_flow"]["error"])
        assert {"e32_rooms_unavailable", "e32_time_zone_unknown"} <= set(issue["fix_flow"]["abort"])


# -- the restart button ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_restart_button_restarts_the_e32_in_one_sign_in(hass):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    button = module.E32RestartButton(hass, parent)
    button.hass = hass
    await hass.async_block_till_done()  # the hub's own plan read after its first status
    e32.requests.clear()
    closed = e32.closed
    assert button.unique_id == parent.data["topic_prefix"] + "_e32_restart"
    assert button.device_info["identifiers"] == {("open_thermostat", parent.data["topic_prefix"])}  # the product device
    assert button.entity_category is EntityCategory.CONFIG and button.device_class is ButtonDeviceClass.RESTART
    assert button.translation_key == "e32_restart"
    await button.async_press()
    assert [r[0] for r in e32.requests] == ["reboot"] and e32.closed == closed + 1  # signed out again
    e32.reboot_fail = ControllerLinkError("controller_busy_or_conflict")
    with pytest.raises(HomeAssistantError) as error:
        await button.async_press()
    assert error.value.translation_key == "e32_restart_busy"
    e32.reboot_fail = ControllerLinkError("controller_unreachable")
    with pytest.raises(HomeAssistantError) as error:
        await button.async_press()
    assert error.value.translation_key == "e32_restart_failed"
    assert error.value.translation_placeholders == {"error": "controller_unreachable"}


@pytest.mark.asyncio
async def test_the_restart_button_exists_only_with_a_stored_e32_connection(hass):
    added = []
    parent, _ = product(hass, FakeE32())
    await module.async_setup_buttons(hass, parent, lambda entities, **kwargs: added.extend(entities))
    assert [type(e) for e in added] == [module.E32RestartButton]
    added.clear()
    other, _ = product(hass, FakeE32(), credentials=False)
    await module.async_setup_buttons(hass, other, lambda entities, **kwargs: added.extend(entities))
    assert added == []


def test_every_system_text_exists_in_every_language():
    files = {name: json.loads((COMPONENT / name).read_text(encoding="utf-8"))
             for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json")}
    assert files["strings.json"] == files["translations/en.json"]
    for name, data in files.items():
        options = data["options"]
        menu = options["step"]["advanced_settings"]["menu_options"]
        assert menu["e32_logging"] and menu["e32_time_zone"], name
        assert set(options["step"]["e32_logging"]["data"]) == {
            "syslog_enabled", "server", "port", "syslog_level", "syslog_esp", "syslog_ems", "web_level", "mark_interval_s"}
        assert set(options["step"]["e32_time_zone"]["data"]) == {"time_zone"}
        assert "{e32}" in options["step"]["e32_time_zone"]["description"]
        for key in ("e32_log_server_invalid", "e32_log_number_invalid", "e32_settings_invalid", "e32_settings_unconfirmed",
                    "e32_settings_changed", "e32_settings_busy", "e32_settings_unreachable",
                    "e32_settings_no_free_session", "e32_time_zone_invalid"):
            assert options["error"][key], (name, key)
        for key in ("e32_settings_unreachable", "e32_settings_update_required", "e32_settings_password_default",
                    "e32_settings_unchanged", "e32_settings_unconfirmed", "e32_logging_saved", "e32_time_zone_saved"):
            assert options["abort"][key], (name, key)
        assert set(data["selector"]["e32_log_level"]["options"]) == set(module.LOG_LEVELS)
        assert data["entity"]["button"]["e32_restart"]["name"]
        for key in ("e32_restart_busy", "e32_restart_failed", "e32_no_free_session", "room_plan_password",
                    "e32_password_change_required"):
            assert data["exceptions"][key]["message"], (name, key)
