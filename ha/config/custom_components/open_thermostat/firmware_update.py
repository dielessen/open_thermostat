"""E32 firmware updates through Home Assistant, like ESPHome.

Home Assistant checks GitHub for the newest E32 release, downloads
firmware.bin, verifies its SHA-256 (GitHub's asset digest), size and embedded
version marker, and uploads it to the E32 over the local network (/ota, the
same route as the device's update page). The E32 itself makes no HTTPS
connection. Credentials are the ones stored by the controller connection step.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import hashlib
import re

import aiohttp
from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_time_interval

from .const import CONF_TOPIC_PREFIX, DOMAIN
from .controller_link import ControllerClient, ControllerLinkError, ControllerLoginRejected
from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD

REPOSITORY = "dielessen/open_thermostat"
CHECK_INTERVAL = timedelta(hours=6)
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)-e32v2-([a-z]+)\.(\d+)$")
MAX_IMAGE = 0x3C0000
CHANNELS = {"alpha": 0, "beta": 1, "rc": 2}


def parse_tag(tag):
    """(major, minor, patch, channel rank, number) or None for a foreign tag."""
    match = TAG.match(tag) if isinstance(tag, str) else None
    if not match or match.group(4) not in CHANNELS:
        return None
    major, minor, patch, channel, number = match.groups()
    return int(major), int(minor), int(patch), CHANNELS[channel], int(number)


def select_release(releases):
    """The newest published E32 release with a firmware.bin and a SHA-256 digest."""
    best = None
    for release in releases if isinstance(releases, list) else []:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        key = parse_tag(release.get("tag_name"))
        asset = next((a for a in release.get("assets") or [] if isinstance(a, dict)
                      and a.get("name") == "firmware.bin"
                      and re.fullmatch(r"sha256:[0-9a-f]{64}", a.get("digest") or "")), None)
        if key is None or asset is None or not isinstance(asset.get("size"), int):
            continue
        if not 1000000 <= asset["size"] <= MAX_IMAGE:
            continue
        candidate = {"key": key, "tag": release["tag_name"], "size": asset["size"],
                     "sha256": asset["digest"][7:], "url": asset.get("browser_download_url"),
                     "page": release.get("html_url"), "notes": release.get("body") or ""}
        if best is None or key > best["key"]:
            best = candidate
    return best


def verify_image(image, release):
    """Only the exact firmware.bin of that release may be uploaded."""
    return (isinstance(image, bytes) and len(image) == release["size"]
            and hashlib.sha256(image).hexdigest() == release["sha256"]
            and f"OT_E32V2_OTA_V1:{release['tag']}:".encode() in image)


class E32FirmwareUpdate(UpdateEntity):
    _attr_has_entity_name = True
    _attr_name = "Firmware"
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES

    def __init__(self, hass, entry):
        self.hass, self._entry = hass, entry
        prefix = entry.data[CONF_TOPIC_PREFIX]
        self._attr_unique_id = f"{prefix}_e32_firmware"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})
        self._release = None
        self._lock = asyncio.Lock()

    def version_is_newer(self, latest_version, installed_version):
        latest, installed = parse_tag(latest_version), parse_tag(installed_version)
        return latest is not None and (installed is None or latest > installed)

    async def async_release_notes(self):
        return self._release["notes"] if self._release else None

    def _client(self):
        return ControllerClient(self._entry.data[CONTROLLER_ADDRESS])

    async def async_refresh(self, _now=None):
        """Read the installed version from the E32 and the newest release from GitHub."""
        if self._lock.locked():
            return
        try:
            if self._entry.data.get(CONTROLLER_PASSWORD) == getattr(self, "_rejected_password", None):
                raise ControllerLinkError("controller_auth_failed")  # wait for the new password
            async with self._client() as client:
                await client.async_login(self._entry.data[CONTROLLER_PASSWORD])
                version = await client.async_read("/status/version")
                from .e32_access import report_password
                report_password(self.hass, self._entry, getattr(client, "default_password", None))
            self._attr_installed_version = version.get("version") if isinstance(version, dict) else None
        except ControllerLoginRejected:
            from .e32_access import login_rejected
            self._rejected_password = self._entry.data.get(CONTROLLER_PASSWORD)
            login_rejected(self.hass, self._entry)
            self._attr_installed_version = None
        except ControllerLinkError:
            self._attr_installed_version = None
        try:
            session = async_get_clientsession(self.hass)
            async with asyncio.timeout(30):
                async with session.get(f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=20",
                                       headers={"Accept": "application/vnd.github+json"}) as response:
                    releases = await response.json() if response.status == 200 else None
            self._release = select_release(releases)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            pass  # GitHub unreachable: keep the last known release
        self._attr_latest_version = self._release["tag"] if self._release else self._attr_installed_version
        self._attr_release_url = self._release["page"] if self._release else None
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()

    async def async_install(self, version, backup, **kwargs):
        async with self._lock:
            release = self._release
            if release is None or (version is not None and version != release["tag"]):
                raise ValueError("Unknown release; refresh first")
            self._attr_in_progress = True
            self.async_write_ha_state()
            try:
                session = async_get_clientsession(self.hass)
                async with asyncio.timeout(300):
                    async with session.get(release["url"]) as response:
                        if response.status != 200:
                            raise ValueError("Download failed")
                        chunks, total = [], 0
                        async for chunk in response.content.iter_chunked(65536):
                            total += len(chunk)
                            if total > MAX_IMAGE:
                                raise ValueError("Firmware larger than the update slot")
                            chunks.append(chunk)
                        image = b"".join(chunks)
                if not verify_image(image, release):
                    raise ValueError("SHA-256, size or version marker does not match the release")
                async with self._client() as client:
                    await client.async_login(self._entry.data[CONTROLLER_PASSWORD])
                    await client.async_upload_firmware(image)
                # The E32 restarts itself; confirm the new version is running.
                for _ in range(36):
                    await asyncio.sleep(5)
                    try:
                        async with self._client() as client:
                            await client.async_login(self._entry.data[CONTROLLER_PASSWORD])
                            running = await client.async_read("/status/version")
                        if isinstance(running, dict) and running.get("version") == release["tag"]:
                            self._attr_installed_version = release["tag"]
                            return
                    except ControllerLinkError:
                        continue
                raise ValueError("The E32 did not report the new version within 3 minutes")
            except ControllerLinkError as err:
                raise ValueError(f"E32 upload failed: {err}") from None
            except (aiohttp.ClientError, TimeoutError):
                raise ValueError("Firmware download from GitHub failed") from None
            finally:
                self._attr_in_progress = False
                self.async_write_ha_state()


async def async_setup_firmware_update(hass, entry, async_add_entities, **add_options):
    """Only with a stored controller connection (address and admin password)."""
    if not entry.data.get(CONTROLLER_ADDRESS) or not entry.data.get(CONTROLLER_PASSWORD):
        return
    entity = E32FirmwareUpdate(hass, entry)
    async_add_entities([entity], **add_options)
    entry.async_on_unload(async_track_time_interval(hass, entity.async_refresh, CHECK_INTERVAL))
    hass.async_create_task(entity.async_refresh())
