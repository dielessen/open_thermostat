"""E32 firmware through Home Assistant: only the exact verified release is uploaded."""
import hashlib
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat import firmware_update as module
from custom_components.open_thermostat.firmware_update import (
    E32FirmwareUpdate, is_stable, parse_tag, select_release, valid_install_record, verify_image)

TAG = "v0.1.0-e32v2-beta.16"
IMAGE = bytearray(1200000)
IMAGE[4096:4096 + 64] = f"OT_E32V2_OTA_V1:{TAG}:".encode().ljust(64, b"0")
IMAGE = bytes(IMAGE)
DIGEST = hashlib.sha256(IMAGE).hexdigest()


def release(tag=TAG, digest=DIGEST, size=len(IMAGE), draft=False):
    return {"tag_name": tag, "draft": draft, "html_url": "https://github.com/r/" + tag, "body": "notes",
            "assets": [{"name": "firmware.bin", "size": size, "digest": "sha256:" + digest,
                        "browser_download_url": "https://github.com/x/" + tag + "/firmware.bin"}]}


def test_newest_e32_release_is_chosen_and_foreign_tags_ignored():
    picked = select_release([release("ha-v0.4.0b8"), release("v0.1.0-e32v2-beta.15"), release(TAG),
                             release("v0.1.0-e32v2-beta.17", draft=True)])
    assert picked["tag"] == TAG and picked["sha256"] == DIGEST
    assert select_release([release(TAG, digest="xyz")]) is None
    assert select_release("not a list") is None


def test_version_order_is_numeric_and_channel_aware():
    assert parse_tag("v0.1.0-e32v2-beta.16") > parse_tag("v0.1.0-e32v2-beta.9")
    assert parse_tag("v0.1.0-e32v2-rc.1") > parse_tag("v0.1.0-e32v2-beta.99")
    assert parse_tag("ha-v0.4.0b8") is None
    entity = E32FirmwareUpdate.__new__(E32FirmwareUpdate)
    assert entity.version_is_newer(TAG, "v0.1.0-e32v2-beta.15")
    assert not entity.version_is_newer("v0.1.0-e32v2-beta.15", TAG)


def test_only_the_exact_release_image_verifies():
    r = select_release([release()])
    assert verify_image(IMAGE, r)
    changed = bytearray(IMAGE); changed[100] ^= 1
    assert not verify_image(bytes(changed), r)
    other = select_release([release("v0.1.0-e32v2-beta.17", digest=DIGEST)])
    assert not verify_image(IMAGE, other)  # right bytes, but another version marker


class FakeClient:
    uploads = []
    running = "v0.1.0-e32v2-beta.15"

    def __init__(self, address):
        self.address = address

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def async_login(self, password):
        assert password == "secret"

    async def async_read(self, path):
        assert path == "/status/version"
        return {"version": FakeClient.running}

    async def async_upload_firmware(self, image):
        FakeClient.uploads.append(image)
        FakeClient.running = TAG


class FakeResponse:
    def __init__(self, status, payload=None, data=b""):
        self.status, self._payload, self._data = status, payload, data
        self.content = SimpleNamespace(iter_chunked=self._chunks)

    async def _chunks(self, size):
        for start in range(0, len(self._data), size):
            yield self._data[start:start + size]

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None


@pytest.mark.asyncio
async def test_install_uploads_the_verified_image_and_confirms_the_new_version(hass, monkeypatch):
    from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD

    def get(url, **_):
        return FakeResponse(200, [release()]) if "api.github.com" in url else FakeResponse(200, data=IMAGE)

    monkeypatch.setattr(module, "ControllerClient", FakeClient)
    monkeypatch.setattr(module, "async_get_clientsession", lambda hass: SimpleNamespace(get=get))
    sleeps = []

    async def fast_sleep(seconds):
        sleeps.append(seconds)
    monkeypatch.setattr(module.asyncio, "sleep", fast_sleep)
    entry = SimpleNamespace(data={"topic_prefix": "fixture", CONTROLLER_ADDRESS: "http://192.168.1.206",
                                  CONTROLLER_PASSWORD: "secret"})
    entity = E32FirmwareUpdate(hass, entry)
    entity.async_write_ha_state = lambda: None
    await entity.async_refresh()
    assert entity.installed_version == "v0.1.0-e32v2-beta.15" and entity.latest_version == TAG
    await entity.async_install(TAG, False)
    assert FakeClient.uploads == [IMAGE]
    assert entity.installed_version == TAG and not entity.in_progress


@pytest.mark.asyncio
async def test_a_tampered_download_is_never_uploaded(hass, monkeypatch):
    from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
    tampered = bytearray(IMAGE); tampered[5] ^= 1

    def get(url, **_):
        return FakeResponse(200, [release()]) if "api.github.com" in url else FakeResponse(200, data=bytes(tampered))

    FakeClient.uploads = []; FakeClient.running = "v0.1.0-e32v2-beta.15"
    monkeypatch.setattr(module, "ControllerClient", FakeClient)
    monkeypatch.setattr(module, "async_get_clientsession", lambda hass: SimpleNamespace(get=get))
    entry = SimpleNamespace(data={"topic_prefix": "fixture", CONTROLLER_ADDRESS: "http://192.168.1.206",
                                  CONTROLLER_PASSWORD: "secret"})
    entity = E32FirmwareUpdate(hass, entry)
    entity.async_write_ha_state = lambda: None
    await entity.async_refresh()
    with pytest.raises(ValueError, match="SHA-256"):
        await entity.async_install(TAG, False)
    assert FakeClient.uploads == [] and not entity.in_progress


@pytest.mark.asyncio
async def test_upload_is_the_device_form_with_a_fixed_length_and_csrf():
    from aiohttp import web
    from aiohttp.test_utils import TestServer
    from custom_components.open_thermostat.controller_link import ControllerClient
    seen = {}

    async def ota(request):
        seen["chunked"] = request.headers.get("Transfer-Encoding")
        seen["length"] = int(request.headers["Content-Length"])
        seen["csrf"] = request.headers.get("X-OpenThermostat-CSRF")
        form = await request.post()
        seen["fields"] = (form["type"], form["size"], form["file"].filename, form["file"].file.read())
        return web.Response(text="OK")

    app = web.Application(client_max_size=8 * 1024 * 1024)
    app.router.add_post("/ota", ota)
    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    try:
        client = ControllerClient("http://192.168.1.206")  # loopback is refused by design
        client.address = f"http://127.0.0.1:{server.port}"
        async with client:
            client._csrf = "c" * 64
            await client.async_upload_firmware(IMAGE)
    finally:
        await server.close()
    assert seen["chunked"] is None and seen["csrf"] == "c" * 64
    assert seen["fields"] == ("firmware", str(len(IMAGE)), "firmware.bin", IMAGE)
    assert seen["length"] > len(IMAGE)


def test_stable_tags_parse_and_order_after_their_release_candidates():
    order = ["v0.1.0-e32v2-alpha.36", "v0.1.0-e32v2-beta.9", "v0.1.0-e32v2-beta.19", "v1.0.0-e32v2-beta.1",
             "v1.0.0-e32v2-rc.1", "v1.0.0-e32v2-rc.2", "v1.0.0-e32v2", "v1.0.1-e32v2-beta.1", "v1.0.1-e32v2",
             "v1.1.0-e32v2"]
    assert sorted(reversed(order), key=parse_tag) == order
    assert parse_tag("v1.0.0-e32v2") == (1, 0, 0, 3, 0) and is_stable("v1.0.0-e32v2")
    assert not is_stable("v1.0.0-e32v2-rc.1") and not is_stable("ha-v1.0.0")
    for bad in ("v1.0.0", "v1.0.0-e32v2-", "v1.0.0-e32v2-stable.1", "v1.0.0-e32v2-gamma.1", "v01.0.0-e32v2",
                "v1.0.0-e32v2-beta.01", "ha-v1.0.0", "v1.0.0-e32v2\n", None, 1):
        assert parse_tag(bad) is None, bad
    entity = E32FirmwareUpdate.__new__(E32FirmwareUpdate)
    assert entity.version_is_newer("v1.0.0-e32v2", "v0.1.0-e32v2-beta.19")
    assert entity.version_is_newer("v1.0.0-e32v2", "v1.0.0-e32v2-rc.3")
    assert not entity.version_is_newer("v1.0.0-e32v2-rc.3", "v1.0.0-e32v2")


def test_a_stable_installation_is_not_offered_a_pre_release():
    releases = [release("v0.1.0-e32v2-beta.19"), release("v1.0.0-e32v2"), release("v1.1.0-e32v2-beta.1")]
    assert select_release(releases)["tag"] == "v1.1.0-e32v2-beta.1"  # a beta installation follows the betas
    assert select_release(releases, minimum_channel=3)["tag"] == "v1.0.0-e32v2"
    assert select_release([release("v1.1.0-e32v2-rc.1")], minimum_channel=3) is None


def test_beta_and_rc_installations_are_offered_version_one():
    # As GitHub lists them: newest first, a stable release is not a GitHub pre-release.
    catalog = [{**release("v1.0.0-e32v2"), "prerelease": False}, {**release("v1.0.0-e32v2-rc.2"), "prerelease": True},
               {**release("v1.0.0-e32v2-rc.1"), "prerelease": True}, {**release("v0.1.0-e32v2-beta.20"), "prerelease": True},
               {**release("v0.1.0-e32v2-beta.19"), "prerelease": True}, release("ha-v1.0.0")]
    entity = E32FirmwareUpdate.__new__(E32FirmwareUpdate)
    for installed in ("v0.1.0-e32v2-beta.19", "v0.1.0-e32v2-beta.20", "v1.0.0-e32v2-rc.1", "v1.0.0-e32v2-rc.2"):
        offered = select_release(catalog, parse_tag(installed)[3])
        assert offered["tag"] == "v1.0.0-e32v2", installed
        assert entity.version_is_newer(offered["tag"], installed), installed
    # Before 1.0 is published, a beta installation is offered the release candidate.
    assert select_release(catalog[1:], parse_tag("v0.1.0-e32v2-beta.20")[3])["tag"] == "v1.0.0-e32v2-rc.2"
    # An rc installation never falls back to a beta, and 1.0.0 is not offered to itself.
    assert select_release(catalog[3:], parse_tag("v1.0.0-e32v2-rc.1")[3]) is None
    assert not entity.version_is_newer("v1.0.0-e32v2", "v1.0.0-e32v2")


def identity(tag):
    return {"version": tag, "source": "a" * 40, "web_sha256": "b" * 64, "sha256": "c" * 64,
            "project": "open_thermostat", "idf": "v4.4.7", "date": "Oct 29 2026"}


class IdentityClient(FakeClient):
    async def async_read(self, path):
        assert path == "/status/version"
        return identity(FakeClient.running)


def _entity(hass, monkeypatch, image, releases=None, client=IdentityClient):
    from custom_components.open_thermostat.controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD

    def get(url, **_):
        return FakeResponse(200, releases or [release()]) if "api.github.com" in url else FakeResponse(200, data=image)

    async def fast_sleep(seconds):
        return None
    monkeypatch.setattr(module, "ControllerClient", client)
    monkeypatch.setattr(module, "async_get_clientsession", lambda hass: SimpleNamespace(get=get))
    monkeypatch.setattr(module.asyncio, "sleep", fast_sleep)
    entry = SimpleNamespace(data={"topic_prefix": "fixture", CONTROLLER_ADDRESS: "http://192.168.1.206",
                                  CONTROLLER_PASSWORD: "secret"})
    entity = E32FirmwareUpdate(hass, entry)
    entity.async_write_ha_state = lambda: None
    return entity


@pytest.mark.asyncio
async def test_a_stable_installation_keeps_the_stable_channel(hass, monkeypatch):
    FakeClient.uploads = []; FakeClient.running = "v1.0.0-e32v2"
    entity = _entity(hass, monkeypatch, IMAGE, [release("v1.0.0-e32v2"), release("v1.1.0-e32v2-beta.1")])
    await entity.async_refresh()
    assert entity.installed_version == entity.latest_version == "v1.0.0-e32v2"

    class Offline(IdentityClient):
        async def async_login(self, password):
            raise module.ControllerLinkError("controller_unreachable")
    monkeypatch.setattr(module, "ControllerClient", Offline)
    await entity.async_refresh()  # the E32 unreachable: still no beta offered to a stable installation
    # (0.4.0b12: an unreachable E32 keeps its last known version instead of blanking it)
    assert entity.installed_version == "v1.0.0-e32v2" and entity.latest_version == "v1.0.0-e32v2"
    monkeypatch.setattr(module, "ControllerClient", IdentityClient)
    FakeClient.running = "v0.1.0-e32v2-beta.19"
    await entity.async_refresh()
    assert entity.latest_version == "v1.1.0-e32v2-beta.1"


@pytest.mark.asyncio
async def test_a_beta_installation_installs_version_one_through_home_assistant(hass, monkeypatch):
    one = "v1.0.0-e32v2"
    image = bytearray(1200000)
    image[4096:4096 + 64] = f"OT_E32V2_OTA_V1:{one}:".encode().ljust(64, b"0")
    image = bytes(image)
    stable = {**release(one, digest=hashlib.sha256(image).hexdigest(), size=len(image)), "prerelease": False}

    class Updating(IdentityClient):
        async def async_upload_firmware(self, upload):
            FakeClient.uploads.append(upload)
            FakeClient.running = one
    FakeClient.uploads = []; FakeClient.running = "v0.1.0-e32v2-beta.19"
    entity = _entity(hass, monkeypatch, image, [stable, {**release("v0.1.0-e32v2-beta.19"), "prerelease": True}],
                     client=Updating)
    await entity.async_refresh()
    assert (entity.installed_version, entity.latest_version) == ("v0.1.0-e32v2-beta.19", one)
    assert entity.version_is_newer(entity.latest_version, entity.installed_version)
    await entity.async_install(one, False)
    assert FakeClient.uploads == [image] and entity.installed_version == one
    record = entity.last_install
    assert valid_install_record(record) and record["result"] == "installed"
    assert (record["tag"], record["from_version"], record["reported"]["version"]) == (
        one, "v0.1.0-e32v2-beta.19", one)
    await entity.async_refresh()  # now on the stable channel: nothing newer offered
    assert entity.latest_version == entity.installed_version == one


@pytest.mark.asyncio
async def test_the_last_install_is_recorded_for_the_acceptance_without_secrets(hass, monkeypatch):
    FakeClient.uploads = []; FakeClient.running = "v0.1.0-e32v2-beta.15"
    entity = _entity(hass, monkeypatch, IMAGE)
    await entity.async_refresh()
    assert entity.extra_state_attributes is None
    await entity.async_install(TAG, False)
    record = entity.extra_state_attributes["last_install"]
    assert record == entity.last_install and valid_install_record(record)
    assert {k: record[k] for k in ("tag", "from_version", "sha256", "size", "result", "uploads")} == {
        "tag": TAG, "from_version": "v0.1.0-e32v2-beta.15", "sha256": DIGEST, "size": len(IMAGE),
        "result": "installed", "uploads": 1}
    # Only the identity the E32 reports after its restart, nothing else it sends.
    assert record["reported"] == {"version": TAG, "source_commit": "a" * 40, "web_sha256": "b" * 64,
                                  "elf_sha256": "c" * 64}
    assert record["started_at"] <= record["finished_at"] and record["duration_s"] >= 0
    assert record["started_at"].endswith("Z") and len(record["started_at"]) == 20
    text = repr(entity.extra_state_attributes)
    assert "secret" not in text and "192.168" not in text and "project" not in text


@pytest.mark.asyncio
async def test_a_failed_install_records_where_it_stopped(hass, monkeypatch):
    tampered = bytearray(IMAGE); tampered[5] ^= 1
    FakeClient.uploads = []; FakeClient.running = "v0.1.0-e32v2-beta.15"
    entity = _entity(hass, monkeypatch, bytes(tampered))
    await entity.async_refresh()
    with pytest.raises(ValueError, match="SHA-256"):
        await entity.async_install(TAG, False)
    record = entity.last_install
    assert record["result"] == "verification_failed" and record["uploads"] == 0 and record["reported"] is None

    class Stuck(IdentityClient):  # accepts the upload, but keeps running the old version
        async def async_upload_firmware(self, image):
            FakeClient.uploads.append(image)
    FakeClient.running = "v0.1.0-e32v2-beta.15"
    entity = _entity(hass, monkeypatch, IMAGE, client=Stuck)
    await entity.async_refresh()
    with pytest.raises(ValueError, match="did not report the new version"):
        await entity.async_install(TAG, False)
    record = entity.last_install
    assert record["result"] == "not_confirmed" and record["uploads"] == 1
    assert record["reported"]["version"] == "v0.1.0-e32v2-beta.15"  # the old firmware stayed (or rolled back)

    class Refused(IdentityClient):
        async def async_upload_firmware(self, image):
            raise module.ControllerLinkError("controller_busy_or_conflict")
    entity = _entity(hass, monkeypatch, IMAGE, client=Refused)
    await entity.async_refresh()
    with pytest.raises(ValueError, match="upload failed"):
        await entity.async_install(TAG, False)
    assert entity.last_install["result"] == "upload_failed" and entity.last_install["uploads"] == 0


@pytest.mark.asyncio
async def test_the_last_install_survives_a_restart_only_when_well_formed(hass, monkeypatch):
    from homeassistant.core import State
    FakeClient.uploads = []; FakeClient.running = "v0.1.0-e32v2-beta.15"
    entity = _entity(hass, monkeypatch, IMAGE)
    await entity.async_refresh()
    await entity.async_install(TAG, False)
    good = entity.last_install
    for record, restored in [(good, good), ({**good, "address": "http://192.168.1.206"}, None),
                             ({**good, "result": "maybe"}, None), ({**good, "sha256": "x"}, None),
                             ({**good, "reported": {**good["reported"], "extra": 1}}, None), ("text", None)]:
        fresh = _entity(hass, monkeypatch, IMAGE)

        async def last_state(record=record):
            return State("update.fixture_firmware", "off", {"last_install": record})
        fresh.async_get_last_state = last_state
        await fresh.async_added_to_hass()
        assert fresh.last_install == restored
        assert valid_install_record(record) is (restored is not None)


# --- 0.4.0b12: a failed read never blanks a known version -------------------------------


class Refusing(IdentityClient):
    error = "controller_session_capacity"

    async def async_login(self, password):
        raise module.ControllerLinkError(Refusing.error)


async def _restored(hass, monkeypatch, attributes, client=Refusing):
    from homeassistant.core import State
    entity = _entity(hass, monkeypatch, IMAGE, client=client)
    scheduled = []
    monkeypatch.setattr(module, "async_call_later",
                        lambda hass, delay, action: scheduled.append((delay, action)) or (lambda: None))

    async def last_state():
        return State("update.fixture_firmware", "off", attributes)
    entity.async_get_last_state = last_state
    await entity.async_added_to_hass()
    return entity, scheduled


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["controller_session_capacity", "controller_unreachable", "controller_try_again_later"])
async def test_a_failed_startup_read_keeps_the_restored_version_and_retries_within_minutes(hass, monkeypatch, error):
    Refusing.error = error
    FakeClient.running = "v0.1.0-e32v2-beta.19"
    entity, scheduled = await _restored(hass, monkeypatch, {"installed_version": "v0.1.0-e32v2-beta.19",
                                                            "latest_version": "v0.1.0-e32v2-beta.19"})
    assert entity.installed_version == "v0.1.0-e32v2-beta.19" and entity.available
    await entity.async_refresh()  # the start-up read fails (E32 busy or still restarting)
    assert entity.installed_version == "v0.1.0-e32v2-beta.19" and entity.available
    assert entity.state is not None  # never "unknown"
    assert [delay for delay, _ in scheduled] == [60]
    await scheduled[-1][1](None)  # 1 minute later: still failing, next try after 5 minutes
    assert [delay for delay, _ in scheduled] == [60, 300]
    monkeypatch.setattr(module, "ControllerClient", IdentityClient)
    FakeClient.running = "v0.1.0-e32v2-beta.20"
    await scheduled[-1][1](None)  # the retry succeeds: the read version replaces the restored one
    assert entity.installed_version == "v0.1.0-e32v2-beta.20"
    assert len(scheduled) == 2  # no more retries after a success


@pytest.mark.asyncio
async def test_retries_stop_after_15_minutes_until_the_normal_interval(hass, monkeypatch):
    entity, scheduled = await _restored(hass, monkeypatch, {})
    assert entity.installed_version is None and not entity.available  # never known: unavailable
    for _ in range(5):
        await entity.async_refresh()
    assert [delay for delay, _ in scheduled] == [60, 300, 900]


@pytest.mark.asyncio
async def test_the_last_install_restores_the_version_when_the_state_did_not(hass, monkeypatch):
    FakeClient.uploads = []; FakeClient.running = "v0.1.0-e32v2-beta.15"
    done = _entity(hass, monkeypatch, IMAGE)
    await done.async_refresh()
    await done.async_install(TAG, False)
    entity, _ = await _restored(hass, monkeypatch, {"last_install": done.last_install})
    assert entity.installed_version == TAG and entity.available


@pytest.mark.asyncio
async def test_a_wrong_password_raises_the_repair_but_keeps_the_version(hass, monkeypatch):
    calls = []

    class Rejected(IdentityClient):
        async def async_login(self, password):
            raise module.ControllerLoginRejected()
    from custom_components.open_thermostat import e32_access
    monkeypatch.setattr(e32_access, "login_rejected", lambda hass, entry: calls.append("reauth"))
    entity, scheduled = await _restored(hass, monkeypatch, {"installed_version": "v0.1.0-e32v2-beta.19"},
                                        client=Rejected)
    await entity.async_refresh()
    await entity.async_refresh()  # the same refused password is not tried again
    assert calls == ["reauth"] and entity.installed_version == "v0.1.0-e32v2-beta.19" and entity.available
    assert scheduled == []  # no retries for a refused password: Repairs asks for the new one


@pytest.mark.asyncio
async def test_a_successful_read_updates_the_version(hass, monkeypatch):
    FakeClient.running = "v0.1.0-e32v2-beta.19"
    entity, scheduled = await _restored(hass, monkeypatch, {"installed_version": "v0.1.0-e32v2-beta.18"},
                                        client=IdentityClient)
    await entity.async_refresh()
    assert entity.installed_version == "v0.1.0-e32v2-beta.19" and scheduled == []
