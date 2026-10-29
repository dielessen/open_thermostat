"""Ephemeral native E32 settings client for the normal installation flow.

The cookie, CSRF proof and settings ETag live only in this context. This is not
an arbitrary REST proxy, credential store, source qualifier or MQTT writer.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import ipaddress
import json
import re
import secrets
import socket
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver
from yarl import URL


class ControllerLinkError(ValueError):
    """A bounded public error code, never a response/URL/credential exception."""


class ControllerLoginRejected(ControllerLinkError):
    """The E32 refused the stored password (401 on /auth/login): it was changed on the E32.

    Same public code as before (controller_auth_failed); callers that know the
    entry start Home Assistant's re-authentication with it.
    """

    def __init__(self):
        super().__init__("controller_auth_failed")


class HeatingPlanRejected(ControllerLinkError):
    """The E32 refused a /config/heating write with a named reason (409 = plan_changed)."""

    def __init__(self, status, error):
        super().__init__(error)
        self.status = status
        self.error = error


HEATING_PLAN = "/config/heating"
HEATING_PLAN_BYTES = 4096  # The E32 refuses larger plans (413 plan_too_large).


class ControllerProvisioningError(ControllerLinkError):
    """A remote outcome must be read back before a new attempt, never guessed."""

    def __init__(self, code, *, device_may_have_changed):
        super().__init__(code)
        self.device_may_have_changed = device_may_have_changed


# Home-network DNS names: router/mDNS suffixes (FRITZ!Box, RFC 8375 home.arpa,
# localdomain, internal, lan, local, home). Single-label names are accepted too;
# every name must also resolve to a local address (PrivateResolver).
LOCAL_DNS_SUFFIXES = (".fritz.box", ".home.arpa", ".localdomain", ".internal", ".lan", ".local", ".home")


def private_controller_ip(address, *, link_local=False):
    """A local-network IP (private; link-local only for resolved names), never loopback/public."""
    try:
        address = ipaddress.ip_address(address.split("%", 1)[0] if type(address) is str else address)
    except ValueError:
        return False
    if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_reserved:
        return False
    if address.is_link_local:
        return link_local
    return address.is_private


class PrivateResolver(AbstractResolver):
    """The default resolver, keeping only local-network addresses (no public or loopback hosts).

    Checked at connect time, so a home-network name that resolves (or later
    rebinds) to a public or loopback address is never contacted.
    """

    async def resolve(self, host, port=0, family=socket.AF_INET):
        # A resolver per lookup: the connector does not own (or close) a passed-in resolver.
        resolver = aiohttp.DefaultResolver()
        try:
            results = await resolver.resolve(host, port, family)
        finally:
            await resolver.close()
        local = [result for result in results if private_controller_ip(result["host"], link_local=True)]
        if not local:
            raise OSError(f"{host} does not resolve to a local network address")
        return local

    async def close(self):
        return None


def controller_address(value):
    """Explicit local controller only; fixed API paths and no redirects/proxies."""
    if (type(value) is not str or len(value) > 280 or value != value.strip()
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise ControllerLinkError("controller_address_invalid")
    try:
        url = urlsplit(value)
        host, port = url.hostname, url.port
        if (url.scheme not in ("http", "https") or not host or url.username is not None
                or url.password is not None or url.path not in ("", "/")
                or url.query or url.fragment or port is not None and not 1 <= port <= 65535):
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if (not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?", host)
                    or ".." in host or host.lower() == "localhost" or host.isdecimal()
                    or re.fullmatch(r"0[xX][0-9a-fA-F]+", host)
                    or "." in host and not host.lower().endswith(LOCAL_DNS_SUFFIXES)):
                raise ValueError
        else:
            if not private_controller_ip(address):
                raise ValueError
    except (ValueError, TypeError):
        raise ControllerLinkError("controller_address_invalid") from None
    # Match aiohttp's actual Host header (case/default-port normalization).
    return str(URL(value).origin())


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError


def _decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_object_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError, RecursionError):
        raise ControllerLinkError("controller_response_invalid") from None


async def _error_name(response):
    """The E32's {"error":"<name>"}, or a fixed name; never response text verbatim."""
    fallback = {409: "plan_changed", 413: "plan_too_large", 503: "save_unconfirmed"}.get(response.status, "invalid_plan")
    try:
        value = json.loads(await response.content.read(512))
    except (ValueError, UnicodeError, RecursionError, aiohttp.ClientError):
        return fallback
    error = value.get("error") if type(value) is dict else None
    return error if type(error) is str and re.fullmatch(r"[a-z0-9_]{1,48}", error) else fallback


@dataclass(frozen=True, slots=True)
class InitialControllerLink:
    """A reviewed prospective change, not a stored secret or live admission."""
    source: object = field(repr=False)
    before: object = field(repr=False)
    observed_settings: dict = field(repr=False)
    settings: dict = field(repr=False)
    etag: str = field(repr=False)
    firmware_identity: dict = field(repr=False)
    private_entry_state: str = field(repr=False)
    settings_unchanged: bool
    needs_reboot: bool


def initial_controller_link(hass, entry, *, version, status, updates, settings, etag, rooms):
    """Derive one normal HA installation link from actual authenticated reads.

    Existing NativePlanSource selects logical policy only. Unknown measurement,
    actuator, hydraulic and boiler qualifications remain unknown. No I/O, Store
    change, runtime activation or source replacement happens in this function.
    """
    from .native_provisioning import propose_local_shadow_source, local_device_descriptor, source_from_selection
    from .product import configuration_snapshot, is_product
    from .v1_heating_graph import actual_runtime_active
    from .v1_model import CONF_ENABLED, MODE_SHADOW, integration_mode
    from .v1_wire import identifier
    from .graph_shadow_validation import canonical
    from .native_plan import native_entry_state

    if (not is_product(entry) or integration_mode(entry) != MODE_SHADOW
            or entry.options.get(CONF_ENABLED, False) or actual_runtime_active(hass, entry)):
        raise ControllerLinkError("controller_runtime_off_required")
    if (type(version) is not dict or type(status) is not dict or type(updates) is not dict
            or type(settings) is not dict or type(rooms) is not list):
        raise ControllerLinkError("controller_response_invalid")
    if status.get("controlMode") not in ("legacy", "shadow"):
        raise ControllerLinkError("controller_response_invalid")
    if (type(etag) is not str or re.fullmatch(r'"[0-9a-f]{64}"', etag) is None):
        raise ControllerLinkError("controller_update_required")
    if (type(version.get("version")) is not str
            or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+-e32v2-(?:alpha|beta)\.[0-9]+", version["version"]) is None
            or type(version.get("source")) is not str
            or re.fullmatch(r"[0-9a-f]{40}", version["source"]) is None
            or any(type(version.get(k)) is not str or re.fullmatch(r"[0-9a-f]{64}",version[k]) is None
                   for k in ("sha256", "web_sha256"))):
        raise ControllerLinkError("controller_update_required")
    build = status.get("control_build")
    if (type(build) is not dict or type(build.get("schema")) is not int or build["schema"] != 1
            or build.get("scope") != "compiled_support_only"
            or build.get("authorizes_physical_outputs") is not False
            or type(build.get("source_formats")) is not list
            or "native.source.local.week.v1" not in build["source_formats"]
            or type(build.get("plans")) is not list
            or not any(type(p) is dict and p.get("contract") == "control.plan.week.v1"
                       and type(p.get("maximum_zones")) is int and p["maximum_zones"] == 2
                       and type(p.get("minimum_zones")) is int and p["minimum_zones"] == 1
                       for p in build["plans"])):
        raise ControllerLinkError("controller_update_required")
    if (updates.get("busy") is not False or updates.get("boot_pending") is not False
            or updates.get("reboot_required") is not False or updates.get("reboot_scheduled") is not False):
        raise ControllerLinkError("controller_busy_or_conflict")
    if rooms:
        raise ControllerLinkError("controller_legacy_rooms_present")
    mqtt = settings.get("mqtt")
    if (type(mqtt) is not dict or mqtt.get("enabled") is not True
            or type(mqtt.get("brokerAddress")) is not str or not mqtt["brokerAddress"]
            or type(mqtt.get("brokerPort")) is not int or not 1 <= mqtt["brokerPort"] <= 65535
            or type(mqtt.get("username")) is not str or not mqtt["username"]
            or mqtt.get("password") != ""):
        raise ControllerLinkError("controller_broker_setup_required")
    controller = mqtt.get("native_source_device_id")
    if (type(controller) is not str or re.fullmatch(r"e32_[0-9a-f]{12}", controller) is None
            or type(mqtt.get("native_source_live_apply")) is not bool
            or not identifier(entry.data.get("topic_prefix"))):
        raise ControllerLinkError("controller_update_required")
    source = propose_local_shadow_source(hass, entry, controller, week_reviewed=True)
    selected = source_from_selection(entry)
    if selected is not None and selected != source:
        raise ControllerLinkError("controller_source_conflict")
    descriptor = local_device_descriptor(source)
    current = deepcopy(settings)
    current["mqtt"].pop("native_source_device_id")
    live = current["mqtt"].pop("native_source_live_apply")
    existing = current["mqtt"].get("native_shadow_source")
    # A selected evolution may replace only its exact CURRENT predecessor.
    # An older evolution descriptor retains history, but only its current tail
    # identifies the immediately preceding policy; no historical config is applied.
    previous_descriptor = None
    if source.predecessor is not None:
        previous_descriptor = local_device_descriptor(source.predecessor)
        if existing is None:
            raise ControllerLinkError("controller_source_conflict")
    observed_current = existing
    if type(existing) is list and len(existing) == 3 and existing[0] == "native.source.evolution.v1":
        observed_current = existing[2]
    predecessor_matches = (previous_descriptor is not None
        and canonical(observed_current) == canonical(previous_descriptor))
    if existing is not None and (
            (canonical(existing) != canonical(descriptor) and not predecessor_matches)
            or current["mqtt"].get("adapter_id") != source.policy.adapter_id
            or current["mqtt"].get("base") != entry.data["topic_prefix"]
            or current["mqtt"].get("modern_shadow") is not True):
        raise ControllerLinkError("controller_source_conflict")
    if (current["mqtt"].get("modern_shadow") is True
            and current["mqtt"].get("adapter_id") != source.policy.adapter_id):
        raise ControllerLinkError("controller_source_conflict")
    candidate = deepcopy(current)
    candidate["mqtt"].update(modern_shadow=True, adapter_id=source.policy.adapter_id,
                             base=entry.data["topic_prefix"], native_shadow_source=descriptor)
    # The firmware preserves the same-broker redacted password/weather key.
    # It checks its final secret-preserving serialization against the same quota.
    if len(json.dumps(candidate, ensure_ascii=True, separators=(",", ":")).encode()) >= 2048:
        raise ControllerLinkError("controller_settings_too_large")
    unchanged = canonical(current) == canonical(candidate)
    identity = {key: version[key] for key in ("version", "source", "sha256", "web_sha256")}
    return InitialControllerLink(source, configuration_snapshot(entry), current, candidate, etag, identity,
                                 native_entry_state(entry),
                                 unchanged, not (unchanged and live and status.get("controlMode") == "shadow"))


def _link_guard(hass, entry, before, source=None, private_entry_state=None):
    from .product import configuration_snapshot
    from .v1_heating_graph import actual_runtime_active
    from .v1_model import CONF_ENABLED
    from .native_plan import native_entry_state
    if (hass.config_entries.async_get_entry(entry.entry_id) is not entry
            or configuration_snapshot(entry) != before
            or entry.options.get(CONF_ENABLED, False) or actual_runtime_active(hass, entry)
            or private_entry_state is not None and native_entry_state(entry) != private_entry_state):
        raise ControllerLinkError("setup_changed")
    if source is not None:
        try:
            source.validate_native(hass, entry)
        except ValueError:
            raise ControllerLinkError("setup_changed") from None


async def async_prepare_controller_link(hass, entry, client):
    """Actual bounded reads and existing native schedule compilation; no writes."""
    from .product import configuration_snapshot
    from .native_plan import native_entry_state
    before = configuration_snapshot(entry)
    private_before = native_entry_state(entry)
    _link_guard(hass, entry, before, private_entry_state=private_before)
    observed = {}
    for key, path in (("version", "/status/version"), ("status", "/status"),
                      ("updates", "/updates/status"), ("settings", "/config/device"),
                      ("rooms", "/config/rooms")):
        value = await client.async_read(path)
        _link_guard(hass, entry, before, private_entry_state=private_before)
        if key == "settings":
            observed[key], observed["etag"] = value
        else:
            observed[key] = value
    try:
        plan = initial_controller_link(hass, entry, **observed)
    except ControllerLinkError:
        raise
    except ValueError:
        raise ControllerLinkError("controller_room_configuration_invalid") from None
    # Same compiler/budgets as the real runtime. A saved week alone is not proof
    # its complete 15-day plan fits the actual native contract.
    try:
        await plan.source.async_configuration(hass, entry)
    except ValueError:
        _link_guard(hass, entry, before, plan.source, private_before)
        raise ControllerLinkError("controller_room_configuration_invalid") from None
    _link_guard(hass, entry, before, plan.source, private_before)
    return plan


LINK_BOOT_TIMEOUT = 60
LINK_POLL_INTERVAL = 1


def _saved_link_settings(value, controller):
    if type(value) is not dict or type(value.get("mqtt")) is not dict:
        raise ControllerLinkError("controller_response_invalid")
    result = deepcopy(value)
    mqtt = result["mqtt"]
    identity = mqtt.pop("native_source_device_id", None)
    live = mqtt.pop("native_source_live_apply", None)
    if identity != controller or type(live) is not bool:
        raise ControllerLinkError("controller_changed")
    return result, live


async def async_provision_controller(hass, entry, client, plan, password):
    """Apply this exact initial logical source and verify the running factory.

    Uses existing native device settings/reboot routes. No HA mutation, MQTT
    writer, room-plan apply or physical authorization. A caller must still fence
    and commit HA source selection, then obtain actual MQTT admission/readback.
    """
    from .graph_shadow_validation import canonical
    if type(plan) is not InitialControllerLink:
        raise ControllerLinkError("controller_readback_invalid")
    changed = False
    wrote = False
    rebooted = False
    try:
        _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
        fresh = await async_prepare_controller_link(hass, entry, client)
        _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
        if (fresh.etag != plan.etag or fresh.firmware_identity != plan.firmware_identity
                or fresh.private_entry_state != plan.private_entry_state
                or fresh.source != plan.source
                or canonical(fresh.observed_settings) != canonical(plan.observed_settings)
                or canonical(fresh.settings) != canonical(plan.settings)):
            raise ControllerLinkError("controller_settings_changed")
        if not fresh.settings_unchanged:
            # Set BEFORE the await: a lost response does not prove no flash save.
            changed = True
            try:
                await client.async_save_settings(fresh.settings, fresh.etag)
            except ControllerLinkError as err:
                if str(err) in ("controller_auth_failed", "controller_settings_changed",
                                "controller_busy_or_conflict", "controller_settings_too_large",
                                "controller_readback_invalid", "controller_request_invalid"):
                    changed = False  # Explicit pre-save rejection, not a lost response.
                raise
            wrote = True
            _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
            saved, _ = await client.async_read("/config/device")
            _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
            actual, _ = _saved_link_settings(saved, plan.source.policy.controller_id)
            if canonical(actual) != canonical(plan.settings):
                raise ControllerLinkError("controller_settings_changed")
        if fresh.needs_reboot:
            changed = True
            _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
            try:
                await client.async_reboot()
                rebooted = True
            except ControllerLinkError as err:
                if str(err) != "controller_unreachable":
                    raise
                # A lost reboot response may mean the boot already started.
                # Read only below; never issue a second reboot automatically.
        reauthenticated = False
        try:
            async with asyncio.timeout(LINK_BOOT_TIMEOUT):
                while True:
                    _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
                    try:
                        version = await client.async_read("/status/version")
                        updates = await client.async_read("/updates/status")
                        status = await client.async_read("/status")
                        saved, _ = await client.async_read("/config/device")
                    except ControllerLinkError as err:
                        _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
                        if fresh.needs_reboot and str(err) == "controller_auth_failed" and not reauthenticated:
                            await client.async_login(password)
                            reauthenticated = True
                        elif str(err) != "controller_unreachable":
                            raise
                        await asyncio.sleep(LINK_POLL_INTERVAL)
                        continue
                    _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
                    if any(type(value) is not dict for value in (version, updates, status)):
                        raise ControllerLinkError("controller_response_invalid")
                    if {k: version.get(k) for k in plan.firmware_identity} != plan.firmware_identity:
                        raise ControllerLinkError("controller_changed")
                    actual, live = _saved_link_settings(saved, plan.source.policy.controller_id)
                    if canonical(actual) != canonical(plan.settings):
                        raise ControllerLinkError("controller_settings_changed")
                    if (live is True and status.get("controlMode") == "shadow"
                            and updates.get("busy") is False and updates.get("boot_pending") is False
                            and updates.get("reboot_required") is False and updates.get("reboot_scheduled") is False):
                        break
                    await asyncio.sleep(LINK_POLL_INTERVAL)
        except TimeoutError:
            raise ControllerLinkError("controller_boot_unconfirmed") from None
        _link_guard(hass, entry, plan.before, plan.source, plan.private_entry_state)
        return {"controller_id": plan.source.policy.controller_id,
                "profile_digest": plan.source.policy.profile_digest,
                "device_settings_verified": True, "running_logical_source_verified": True,
                "settings_written": wrote, "reboot_acknowledged": rebooted,
                "mqtt_session_verified": False, "room_plan_applied": False,
                "authorizes_physical_outputs": False}
    except ControllerLinkError as err:
        raise ControllerProvisioningError(str(err), device_may_have_changed=changed) from None


class ControllerClient:
    """One scoped operation using the existing firmware cookie/CSRF contract."""

    _reads = frozenset(("/auth/session", "/status/version", "/status", "/updates/status",
                        "/config/device", "/config/rooms", HEATING_PLAN, "/status/heating"))
    _writes = frozenset(("/auth/login", "/auth/logout", "/config/device", "/updates/reboot", HEATING_PLAN))

    def __init__(self, address):
        self.address = controller_address(address)
        self._session = None
        self._csrf = None
        self.logout_confirmed = False
        # From /auth/session after a login: True while the E32 still has its
        # factory password, False once changed, None on firmware that does not say.
        self.default_password = None

    async def __aenter__(self):
        if self._session is not None and not self._session.closed:
            raise ControllerLinkError("controller_request_invalid")
        self.logout_confirmed = False
        self._csrf = None
        self._session = aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True),  # Native E32 uses LAN IP cookies.
            timeout=aiohttp.ClientTimeout(total=10), trust_env=False,
            connector=aiohttp.TCPConnector(resolver=PrivateResolver()),
        )
        return self

    async def __aexit__(self, *_):
        await self.async_close()

    async def _request(self, method, path, *, form=None, document=None, etag=None):
        if (self._session is None or self._session.closed
                or method == "GET" and path not in self._reads
                or method == "POST" and path not in self._writes
                or method not in ("GET", "POST")):
            raise ControllerLinkError("controller_request_invalid")
        headers = {"Origin": self.address, "Accept": "application/json"}
        if method == "POST" and path == "/config/device" and etag is None:
            raise ControllerLinkError("controller_readback_invalid")
        if method == "POST" and path != "/auth/login":
            if not self._csrf:
                raise ControllerLinkError("controller_auth_failed")
            headers["X-OpenThermostat-CSRF"] = self._csrf
        if etag is not None:
            if type(etag) is not str or re.fullmatch(r'"[0-9a-f]{64}"', etag) is None:
                raise ControllerLinkError("controller_readback_invalid")
            headers["If-Match"] = etag
        data = form
        if form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if document is not None:
            headers["Content-Type"] = "application/json"
            if type(document) is not dict:
                raise ControllerLinkError("controller_request_invalid")
            try:
                data = json.dumps(document, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            except (TypeError, ValueError, RecursionError):
                raise ControllerLinkError("controller_request_invalid") from None
            if path == HEATING_PLAN:
                if len(data.encode()) > HEATING_PLAN_BYTES:
                    raise HeatingPlanRejected(413, "plan_too_large")
            elif len(data.encode()) >= 2048:
                raise ControllerLinkError("controller_settings_too_large")
        try:
            async with self._session.request(method, self.address + path, data=data,
                    headers=headers, allow_redirects=False) as response:
                if response.status == 401 and method == "POST" and path == "/auth/login":
                    raise ControllerLoginRejected()
                if response.status in (401, 403):
                    raise ControllerLinkError("controller_auth_failed")
                if path == HEATING_PLAN and response.status in (400, 409, 413, 503):
                    raise HeatingPlanRejected(response.status, await _error_name(response))
                if response.status == 412:
                    raise ControllerLinkError("controller_settings_changed")
                if response.status == 409:
                    raise ControllerLinkError("controller_busy_or_conflict")
                accepted = ({200, 201} if method == "POST" and path == "/config/device"
                            else {202} if method == "POST" and path == "/updates/reboot"
                            else {200})
                if response.status not in accepted:
                    raise ControllerLinkError("controller_response_invalid")
                body = bytearray()
                async for chunk in response.content.iter_chunked(2048):
                    if len(body) + len(chunk) > 8192:
                        raise ControllerLinkError("controller_response_too_large")
                    body.extend(chunk)
                return bytes(body), response.headers.get("ETag"), response.status
        except (aiohttp.ClientError, TimeoutError):
            raise ControllerLinkError("controller_unreachable") from None

    async def async_read(self, path):
        raw, tag, _ = await self._request("GET", path)
        value = _decode(raw)
        if path == "/config/device":
            if type(value) is not dict or type(tag) is not str or re.fullmatch(r'"[0-9a-f]{64}"', tag) is None:
                raise ControllerLinkError("controller_update_required")
            return value, tag
        return value

    async def async_login(self, password):
        if type(password) is not str or not 1 <= len(password) <= 128:
            raise ControllerLinkError("controller_auth_failed")
        # Do not retain the supplied password in this object or an HA entry.
        await self._request("POST", "/auth/login", form={"username": "admin", "password": password})
        session = await self.async_read("/auth/session")
        if (type(session) is not dict or session.get("authenticated") is not True
                or type(session.get("csrf")) is not str
                or re.fullmatch(r"[0-9a-f]{64}", session["csrf"]) is None):
            raise ControllerLinkError("controller_auth_failed")
        self._csrf = session["csrf"]
        flag = session.get("default_password")
        self.default_password = flag if type(flag) is bool else None

    async def async_read_heating_plan(self):
        """The E32 room plan (GET /config/heating), parsed but not yet validated."""
        return await self.async_read(HEATING_PLAN)

    async def async_save_heating_plan(self, plan):
        """POST the whole plan with the revision it was read at; returns the stored plan.

        A stale revision raises HeatingPlanRejected(409, "plan_changed"); other
        refusals carry the E32's error name (400) or save_unconfirmed (503).
        """
        if type(plan) is not dict:
            raise ControllerLinkError("controller_request_invalid")
        raw, _, _ = await self._request("POST", HEATING_PLAN, document=plan)
        return _decode(raw)

    async def async_save_settings(self, document, etag):
        if type(document) is not dict:
            raise ControllerLinkError("controller_request_invalid")
        await self._request("POST", "/config/device", document=document, etag=etag)

    async def async_upload_firmware(self, image):
        """One already verified firmware image over the local /ota route.

        Same multipart form as the device's update page, with a fixed length
        (the device web server does not accept chunked bodies) and paced 2 KiB
        blocks: the device erases flash sector by sector while it writes.
        """
        if (self._session is None or self._session.closed or not self._csrf
                or type(image) is not bytes or not 1000000 <= len(image) <= 0x3C0000):
            raise ControllerLinkError("controller_request_invalid")
        boundary = "OTFirmware" + secrets.token_hex(12)
        prefix = (f'--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\nfirmware\r\n'
                  f'--{boundary}\r\nContent-Disposition: form-data; name="size"\r\n\r\n{len(image)}\r\n'
                  f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="firmware.bin"\r\n'
                  'Content-Type: application/octet-stream\r\n\r\n').encode()
        suffix = f"\r\n--{boundary}--\r\n".encode()

        async def body():
            yield prefix
            for start in range(0, len(image), 2048):
                yield image[start:start + 2048]
                await asyncio.sleep(0.01)
            yield suffix

        headers = {"Origin": self.address, "X-OpenThermostat-CSRF": self._csrf,
                   "Content-Type": f"multipart/form-data; boundary={boundary}",
                   "Content-Length": str(len(prefix) + len(image) + len(suffix))}
        try:
            async with self._session.post(self.address + "/ota", data=body(), headers=headers,
                    allow_redirects=False, timeout=aiohttp.ClientTimeout(total=600)) as response:
                if response.status in (401, 403):
                    raise ControllerLinkError("controller_auth_failed")
                if response.status == 409:
                    raise ControllerLinkError("controller_busy_or_conflict")
                if response.status != 200:
                    raise ControllerLinkError("controller_response_invalid")
        except (aiohttp.ClientError, TimeoutError):
            raise ControllerLinkError("controller_unreachable") from None

    async def async_reboot(self):
        _, _, status = await self._request("POST", "/updates/reboot")
        if status != 202:
            raise ControllerLinkError("controller_response_invalid")

    async def async_close(self):
        if self._session is None:
            return
        try:
            if self._csrf and not self._session.closed:
                try:
                    async with asyncio.timeout(3):
                        await self._request("POST", "/auth/logout")
                    self.logout_confirmed = True
                except (ControllerLinkError, TimeoutError):
                    pass
        finally:
            self._csrf = None
            self._session.cookie_jar.clear()
            await self._session.close()
