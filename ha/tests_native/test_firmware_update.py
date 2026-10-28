"""E32 firmware through Home Assistant: only the exact verified release is uploaded."""
import hashlib
from types import SimpleNamespace

import pytest

from custom_components.open_thermostat import firmware_update as module
from custom_components.open_thermostat.firmware_update import E32FirmwareUpdate, parse_tag, select_release, verify_image

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
