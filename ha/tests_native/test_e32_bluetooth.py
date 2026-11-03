"""Configure → Advanced and diagnostics → Bluetooth sensors (rc.3): rename and forget, saved together.

Several changes are one save and so one E32 restart; the save reads the list again in the same
sign-in and posts it with that ETag, each row keeping its key on the E32 (no bindkey ever leaves
or enters Home Assistant), a change made on the E32 meanwhile writes nothing.
"""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.open_thermostat import controller_link as link_module
from custom_components.open_thermostat import e32_bluetooth as module
from custom_components.open_thermostat.controller_link import BluetoothRejected, ControllerLinkError
from test_controller_link import BASE, Response, login_responses, setup
from test_e32_room_flow import manager, product  # noqa: F401  (the manager fixture)
from test_room_plan import FakeE32 as PlanE32

COMPONENT = Path(__file__).resolve().parents[1] / "config/custom_components/open_thermostat"
SENSORS = [
    {"address": "a4c138a3e8db", "profile": "pvvx_thermometer", "encryption": "none", "name": "Slaapkamer",
     "key_stored": False, "control_qualified": False, "status": "ok", "frames_received": 12},
    {"address": "112233445566", "profile": "xiaomi_monitor_3", "encryption": "mibeacon_v4_v5", "name": "Zolder",
     "key_stored": True, "control_qualified": False, "status": "ok", "frames_received": 3},
]


class FakeE32(PlanE32):
    """The room plan plus /config/bluetooth: an ETag per read, If-Match on the save."""

    def __init__(self, sensors=SENSORS):
        super().__init__()
        self.sensors = deepcopy(sensors)
        self.tags, self.posts, self.bt_reads = 0, [], []
        self.fail = None

    def client(self, address):
        client = super().client(address)
        e32 = self

        async def bluetooth(document=None, etag=None):
            if document is None:
                e32.tags += 1
                e32.bt_reads.append(e32.logins)
                return ({"schema": 1, "pending_restart": False, "restart_scheduled": False, "config_error": "none",
                         "devices": deepcopy(e32.sensors), "discovery": {"devices": []}}, f'"{e32.tags:064d}"')
            e32.posts.append((deepcopy(document), etag, e32.logins))
            if e32.fail:
                raise e32.fail
            if etag != f'"{e32.tags:064d}"':
                raise ControllerLinkError("controller_settings_changed")
            e32.sensors = [{**next(s for s in e32.sensors if s["address"] == row["address"]), "name": row["name"]}
                           for row in document["devices"]]
            return {"changed": True, "pending_restart": True, "restart_scheduled": True, "restart_in_s": 30}
        client.async_bluetooth = bluetooth
        return client


async def ble_menu(manager, parent):
    await manager.hass.async_block_till_done()
    flow = await manager.async_init(parent.entry_id)
    menu = await manager.async_configure(flow["flow_id"], {"next_step_id": "advanced_settings"})
    assert "ble_sensors" in menu["menu_options"]
    return await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_sensors"})


@pytest.mark.asyncio
async def test_renames_and_a_forget_are_one_save_one_restart_and_keys_stay_on_the_e32(hass, manager):
    hass.config.language = "en"
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    menu = await ble_menu(manager, parent)
    assert menu["type"] == FlowResultType.MENU and menu["menu_options"] == ["ble_rename", "ble_forget"]
    assert "- Slaapkamer (a4c138a3e8db)" in menu["description_placeholders"]["sensors"]
    rename = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_rename"})
    menu = await manager.async_configure(rename["flow_id"], {"sensor": "a4c138a3e8db", "name": " Woonkamer "})
    assert menu["step_id"] == "ble_sensors" and menu["menu_options"] == ["ble_rename", "ble_forget", "ble_save"]
    assert "a4c138a3e8db) → new name: Woonkamer" in menu["description_placeholders"]["sensors"]
    forget = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_forget"})
    assert "Badkamer" in forget["description_placeholders"]["used"]  # the rooms that measure with it
    menu = await manager.async_configure(forget["flow_id"], {"sensors": ["112233445566"]})
    assert "Zolder (112233445566): will be forgotten" in menu["description_placeholders"]["sensors"]
    assert e32.posts == []  # nothing written while collecting
    save = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_save"})
    again = await manager.async_configure(save["flow_id"], {"confirm": False})
    assert again["errors"] == {"base": "care_confirm"} and e32.posts == []
    done = await manager.async_configure(save["flow_id"], {"confirm": True})
    assert done["type"] == FlowResultType.ABORT and done["reason"] == "ble_saved"
    assert len(e32.posts) == 1
    document, etag, login = e32.posts[0]
    assert document == {"devices": [{"address": "a4c138a3e8db", "profile": "pvvx_thermometer", "encryption": "none",
                                     "name": "Woonkamer", "key_action": "keep"}]}
    assert "bindkey" not in json.dumps(document)
    assert etag == f'"{e32.tags:064d}"' and e32.bt_reads[-1] == login  # read again in the same sign-in


@pytest.mark.asyncio
async def test_a_list_changed_on_the_e32_meanwhile_writes_nothing(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    menu = await ble_menu(manager, parent)
    rename = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_rename"})
    menu = await manager.async_configure(rename["flow_id"], {"sensor": "112233445566", "name": "Vliering"})
    e32.sensors[0]["name"] = "Renamed on the E32 page"
    save = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_save"})
    done = await manager.async_configure(save["flow_id"], {"confirm": True})
    assert done["reason"] == "ble_changed" and e32.posts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "   ", "x" * 41, "é" * 21, "two\nlines"])
async def test_a_name_the_e32_would_refuse_never_leaves_home_assistant(hass, manager, name):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    menu = await ble_menu(manager, parent)
    rename = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_rename"})
    again = await manager.async_configure(rename["flow_id"], {"sensor": "a4c138a3e8db", "name": name})
    assert again["errors"] == {"name": "ble_name_invalid"}
    assert module.valid_name("é" * 20) and module.valid_name("x" * 40)


@pytest.mark.asyncio
async def test_a_refusal_is_a_clear_message_and_no_sensors_means_pair_on_the_e32_first(hass, manager):
    e32 = FakeE32()
    parent, _ = product(hass, e32)
    menu = await ble_menu(manager, parent)
    rename = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_rename"})
    menu = await manager.async_configure(rename["flow_id"], {"sensor": "a4c138a3e8db", "name": "Hal"})
    save = await manager.async_configure(menu["flow_id"], {"next_step_id": "ble_save"})
    e32.fail = BluetoothRejected(507, "bluetooth_storage_full")
    again = await manager.async_configure(save["flow_id"], {"confirm": True})
    assert again["errors"] == {"base": "ble_storage_full"} and len(e32.posts) == 1
    empty = FakeE32(sensors=[])
    other, _ = product(hass, empty)
    result = await ble_menu(manager, other)
    assert result["type"] == FlowResultType.ABORT and result["reason"] == "ble_none"


def test_sensors_are_checked_before_they_are_shown():
    value = {"schema": 1, "devices": deepcopy(SENSORS)}
    assert [s["name"] for s in module.decode_sensors(value)] == ["Slaapkamer", "Zolder"]
    for bad in ({**SENSORS[0], "address": "A4C138A3E8DB"}, {**SENSORS[0], "profile": "unknown"},
                {**SENSORS[0], "encryption": "aes"}, {**SENSORS[0], "name": None}):
        assert module.decode_sensors({"schema": 1, "devices": [bad]}) is None
    assert module.decode_sensors({"schema": 2, "devices": []}) is None


@pytest.mark.asyncio
async def test_the_client_reads_with_an_etag_and_saves_with_if_match(monkeypatch):
    tag = '"' + "f" * 64 + '"'
    session, _ = setup(monkeypatch, *login_responses(), Response({"schema": 1, "devices": []}, tag=tag),
                       Response({"changed": True, "restart_scheduled": True}, status=201),
                       Response(raw=b'{"error":"invalid_device_name"}', status=400), Response({"authenticated": False}))
    async with link_module.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        value, etag = await client.async_bluetooth()
        assert etag == tag
        assert (await client.async_bluetooth({"devices": []}, etag))["changed"] is True
        with pytest.raises(BluetoothRejected) as error:
            await client.async_bluetooth({"devices": []}, etag)
        assert error.value.error == "invalid_device_name"
    assert session.calls[3][2]["headers"]["If-Match"] == tag and session.calls[3][1] == BASE + "/config/bluetooth"
    session, _ = setup(monkeypatch, *login_responses(), Response({"schema": 1, "devices": []}),
                       Response({"authenticated": False}))
    async with link_module.ControllerClient(BASE) as client:
        await client.async_login("temporary")
        with pytest.raises(ControllerLinkError, match="^controller_update_required$"):
            await client.async_bluetooth()  # no ETag: firmware that cannot take a save


def test_every_bluetooth_text_exists_in_every_language():
    files = {name: json.loads((COMPONENT / name).read_text(encoding="utf-8"))
             for name in ("strings.json", "translations/en.json", "translations/nl.json", "translations/pl.json")}
    assert files["strings.json"] == files["translations/en.json"]
    for name, data in files.items():
        options = data["options"]
        assert options["step"]["advanced_settings"]["menu_options"]["ble_sensors"], name
        assert set(options["step"]["ble_sensors"]["menu_options"]) == {"ble_rename", "ble_forget", "ble_save"}
        assert "30" in options["step"]["ble_sensors"]["description"] and "30" in options["step"]["ble_save"]["description"]
        for key in ("ble_sensor_invalid", "ble_name_invalid", "ble_storage_full", "ble_rejected"):
            assert options["error"][key], (name, key)
        for key in ("ble_none", "ble_changed", "ble_saved", "ble_saved_restart_later"):
            assert options["abort"][key], (name, key)
