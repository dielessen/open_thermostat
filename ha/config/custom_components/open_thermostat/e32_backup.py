"""Daily backups of the E32 settings in Home Assistant, and restoring one (1.0).

Home Assistant fetches the E32's own backup file (POST /config/backup, the same
route as the Backup and restore panel on the E32 page) once a day, and once
shortly after a start when the last backup is older than 24 hours. The file
holds network and time, MQTT and the Home Assistant link, the room plan with
the week programs, the Bluetooth sensors, the flow options and the boiler
model. Passwords and Bluetooth keys travel inside it as one sealed box
(AES-128-CCM, PBKDF2-SHA256), sealed by the E32 with a random passphrase that
Home Assistant generates once per installation and keeps in the entry
(``backup_passphrase``). The Wi-Fi and web passwords are never in a backup.

The files live in one Store per installation under ``.storage``, so Home
Assistant's own backups contain them too: the newest backup of each of the last
7 days, plus the newest one made right before a restore. A Repairs issue appears
when no backup succeeded for 3 days and goes with the next success.

A restore (Configure -> Advanced -> Restore settings to this E32,
e32_backup_flow.py) first lets the E32 check the file and show what changes,
then applies exactly what was checked. The E32 restores the rooms in shadow
mode and refuses while it controls the boiler or a boiler test runs.

The passphrase, the E32 password and the secrets never reach a log, an error
message, the diagnostics download or an entity attribute.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import json
import logging
import re
import secrets

from homeassistant.core import callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .controller_link import BackupRejected, ControllerClient, ControllerLinkError, ControllerLoginRejected

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
FORMAT = "openthermostat-e32-backup"
# The entry data key of the random passphrase that seals the secrets in every backup.
PASSPHRASE = "backup_passphrase"
STATE_KEY = "e32_backups"
# hass.data state key: the entry data a passphrase-only save produced (no reload).
PASSPHRASE_ONLY_UPDATE = "backup_passphrase_data"
KINDS = ("daily", "manual", "pre_restore")
KEEP_DAYS = 7
BACKUP_AGE = timedelta(hours=24)
# How often Home Assistant looks whether a backup is due (and retries after a failure).
CHECK_INTERVAL = timedelta(hours=1)
# After a start: give the E32 link a moment before the first look.
START_DELAY = 120
ISSUE = "e32_backup_failing"
ISSUE_AFTER = timedelta(days=3)
# After a restore that restarts the E32: how long Home Assistant waits for it to answer again.
RESTART_WAIT = 180
RESTART_POLL = 5
# When the E32 does not say: how long after an apply it restarts (ConfigBackupRoute.cpp restartDelayMs).
RESTART_DELAY = 10
_HEX64 = re.compile(r"[0-9a-f]{64}")
# An apply that failed with one of these never changed the E32: the request was not sent, or refused at the door.
_NOT_APPLIED = frozenset({"controller_request_invalid", "controller_auth_failed", "controller_update_required"})
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+00:00")


def _now():
    return dt_util.utcnow()


def issue_id(entry):
    return f"{ISSUE}_{entry.entry_id}"


def store_key(entry_id):
    return f"{DOMAIN}.e32_backups.{entry_id}"


def credentials(entry):
    """The stored E32 address and password, or None without a stored connection."""
    from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_PASSWORD
    address, password = entry.data.get(CONTROLLER_ADDRESS), entry.data.get(CONTROLLER_PASSWORD)
    if type(address) is not str or not address or type(password) is not str or not password:
        return None
    return address, password


def valid_passphrase(value):
    return type(value) is str and 8 <= len(value) <= 64


def new_passphrase(entry):
    """The entry's passphrase, or a new random one (43 URL-safe characters, 256 bits)."""
    value = entry.data.get(PASSPHRASE)
    return value if valid_passphrase(value) else secrets.token_urlsafe(32)


@callback
def ensure_passphrase(hass, entry):
    """The entry's passphrase; generated and stored once (no reload, no plan review)."""
    value = entry.data.get(PASSPHRASE)
    if valid_passphrase(value):
        return value
    value = new_passphrase(entry)
    data = {**entry.data, PASSPHRASE: value}
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if state is not None:
        state[PASSPHRASE_ONLY_UPDATE] = (data, dict(entry.options))
    if not hass.config_entries.async_update_entry(entry, data=data) and state is not None:
        state.pop(PASSPHRASE_ONLY_UPDATE, None)
    return value


def passphrase_only_update(state, entry):
    """True (once) when the last entry change only added the backup passphrase."""
    pending = state.pop(PASSPHRASE_ONLY_UPDATE, None) if state is not None else None
    return pending is not None and pending == (dict(entry.data), dict(entry.options))


def _size(document):
    return len(json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode())


def valid_document(document):
    return (type(document) is dict and document.get("format") == FORMAT
            and type(document.get("schema")) is int and document.get("board") == "e32v2"
            and (document.get("secrets") is None or type(document.get("secrets")) is dict)
            and _size(document) <= 24576)


def _valid_record(record):
    return (type(record) is dict and type(record.get("id")) is str and re.fullmatch(r"[0-9a-f]{16}", record["id"])
            and record.get("kind") in KINDS and type(record.get("created")) is str
            and _UTC.fullmatch(record["created"]) is not None and type(record.get("size")) is int
            and valid_document(record.get("document")))


def _created(record):
    return dt_util.parse_datetime(record["created"])


def retained(records, keep=()):
    """The newest backup of each of the last KEEP_DAYS days, the newest pre-restore backup, and keep (ids)."""
    ordered = sorted(records, key=lambda r: r["created"], reverse=True)
    kept, days = [], set()
    for record in ordered:
        if record["id"] in keep:
            kept.append(record)
            continue
        if record["kind"] == "pre_restore":
            continue
        day = dt_util.as_local(_created(record)).date()
        if day in days or len(days) >= KEEP_DAYS:
            continue
        days.add(day)
        kept.append(record)
    before = next((r for r in ordered if r["kind"] == "pre_restore"), None)
    if before is not None and before not in kept:
        kept.append(before)
    return sorted(kept, key=lambda r: r["created"], reverse=True)


def _error_code(err):
    from .controller_link import BackupRejected
    if isinstance(err, BackupRejected):
        return err.error
    return str(err) if isinstance(err, ControllerLinkError) else "controller_unreachable"


@dataclass(frozen=True, slots=True)
class RestoreCheck:
    """What the E32 said about one stored backup: its summary and the fingerprint to apply."""
    record_id: str
    address: str = field(repr=False)
    password: str = field(repr=False)
    fingerprint: str = field(repr=False)
    summary: dict = field(repr=False)
    identity: str | None


def _summary(value):
    """The E32's validate answer, checked (and nothing else from it)."""
    if (type(value) is not dict or value.get("valid") is not True or type(value.get("fingerprint")) is not str
            or _HEX64.fullmatch(value["fingerprint"]) is None or type(value.get("restart")) is not bool):
        raise ControllerLinkError("controller_response_invalid")
    lists = {key: value.get(key, []) for key in ("changes", "warnings", "reenter")}
    if (any(type(v) is not list for v in lists.values())
            or any(type(c) is not dict or type(c.get("section")) is not str or type(c.get("field")) is not str
                   for c in lists["changes"])
            or any(type(text) is not str for key in ("warnings", "reenter") for text in lists[key])):
        raise ControllerLinkError("controller_response_invalid")
    return {"restart": value["restart"], **lists}


class E32Backups:
    """The backups of one installation: the Store, the schedule and the E32 requests."""

    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        # private: the file is readable by Home Assistant only (it holds the sealed secrets)
        self._store = Store(hass, STORE_VERSION, store_key(entry.entry_id), private=True)
        self._data = {"backups": [], "last_success": None, "last_attempt": None, "last_error": None, "since": None}
        self._lock = asyncio.Lock()
        self._listeners = []
        self._unsubscribe = []
        self._task = None
        self._rejected_password = None

    # -- state ------------------------------------------------------------

    async def async_load(self):
        stored = await self._store.async_load()
        if type(stored) is dict:
            self._data["backups"] = retained([r for r in stored.get("backups") or [] if _valid_record(r)])
            for key in ("last_success", "last_attempt", "since"):
                if type(stored.get(key)) is str and _UTC.fullmatch(stored[key]):
                    self._data[key] = stored[key]
            if type(stored.get("last_error")) is str and re.fullmatch(r"[a-z0-9_]{1,48}", stored["last_error"]):
                self._data["last_error"] = stored["last_error"]
        if self._data["since"] is None:
            self._data["since"] = _now().isoformat()
            await self._store.async_save(self._data)

    def records(self):
        """The stored backups, newest first (each a dict; the document is not for display)."""
        return list(self._data["backups"])

    def record(self, record_id):
        return next((r for r in self._data["backups"] if r["id"] == record_id), None)

    @property
    def last_success(self):
        value = self._data["last_success"]
        return dt_util.parse_datetime(value) if value else None

    @property
    def last_error(self):
        return self._data["last_error"]

    @property
    def busy(self):
        return self._lock.locked()

    def add_listener(self, listener):
        self._listeners.append(listener)

        def remove():
            if listener in self._listeners:
                self._listeners.remove(listener)
        return remove

    def _changed(self):
        for listener in list(self._listeners):
            listener()

    # -- schedule ---------------------------------------------------------

    @callback
    def start(self):
        self._unsubscribe.append(async_call_later(self.hass, START_DELAY, self._tick))
        self._unsubscribe.append(async_track_time_interval(self.hass, self._tick, CHECK_INTERVAL))

    @callback
    def stop(self):
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe.clear()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    def due(self, now=None):
        """A backup is due when the last good one is 24 hours old (or there is none)."""
        now = now or _now()
        last = self.last_success
        return last is None or now - last >= BACKUP_AGE

    @callback
    def _tick(self, _now_value=None):
        if self._task is not None and not self._task.done():
            return
        self._task = self.hass.async_create_background_task(self.async_scheduled(), "OpenThermostat E32 backup")

    async def async_scheduled(self):
        """One scheduled look: back up when due; a failure waits for the next hourly look."""
        if not self.due() or self._lock.locked():
            self._update_issue()
            return
        try:
            await self.async_backup("daily")
        except ControllerLinkError:
            pass  # recorded (last_error) and shown by the sensor and Repairs

    # -- backups ----------------------------------------------------------

    def _client(self, address):
        return ControllerClient(address)

    async def _export(self, client):
        passphrase = ensure_passphrase(self.hass, self.entry)
        document, status = await client.async_config_backup({"action": "export", "passphrase": passphrase})
        if status != 200 or not valid_document(document):
            raise ControllerLinkError("controller_response_invalid")
        return document

    async def _keep(self, kind, document, keep=()):
        now = _now()
        record = {"id": secrets.token_hex(8), "kind": kind, "created": now.isoformat(),
                  "size": _size(document), "firmware": str(document.get("firmware") or "")[:64],
                  "secrets": document.get("secrets") is not None, "document": document}
        self._data["backups"] = retained([record, *self._data["backups"]], keep)
        self._data.update(last_success=record["created"], last_attempt=record["created"], last_error=None)
        await self._store.async_save(self._data)
        ir.async_delete_issue(self.hass, DOMAIN, issue_id(self.entry))
        self._changed()
        return record

    async def _failed(self, code):
        self._data.update(last_attempt=_now().isoformat(), last_error=code)
        await self._store.async_save(self._data)
        self._update_issue()
        self._changed()

    def _login_password(self, password):
        if password == self._rejected_password:
            raise ControllerLoginRejected()  # wait for the new password; Home Assistant asks for it

    async def _sign_in(self, client, password, *, stored):
        try:
            await client.async_login(password)
        except ControllerLoginRejected:
            if stored and password != self._rejected_password:
                from .e32_access import login_rejected
                self._rejected_password = password
                login_rejected(self.hass, self.entry)
            raise
        if stored:
            from .e32_access import report_password
            report_password(self.hass, self.entry, getattr(client, "default_password", None))

    async def async_backup(self, kind="manual"):
        """Fetch one backup from the stored E32 and keep it; raises ControllerLinkError."""
        stored = credentials(self.entry)
        if stored is None:
            raise ControllerLinkError("controller_password_required")
        address, password = stored
        async with self._lock:
            try:
                self._login_password(password)
                async with self._client(address) as client:
                    await self._sign_in(client, password, stored=True)
                    document = await self._export(client)
            except ControllerLinkError as err:
                code = _error_code(err)
                _LOGGER.debug("E32 settings backup failed (%s)", code)
                await self._failed(code)
                raise
            return await self._keep(kind, document)

    def _update_issue(self, now=None):
        now = now or _now()
        last = self.last_success or dt_util.parse_datetime(self._data["since"] or now.isoformat())
        if self._data["last_error"] is not None and now - last >= ISSUE_AFTER:
            ir.async_create_issue(self.hass, DOMAIN, issue_id(self.entry), is_fixable=False, is_persistent=False,
                                  severity=ir.IssueSeverity.WARNING, translation_key=ISSUE,
                                  translation_placeholders={"name": self.entry.title,
                                                            "last": self._last_text()})
        elif self.last_success is not None and now - self.last_success < ISSUE_AFTER:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id(self.entry))

    def _last_text(self):
        last = self.last_success
        return dt_util.as_local(last).strftime("%Y-%m-%d %H:%M") if last else "-"

    # -- restore ----------------------------------------------------------

    def _request(self, action, record, **extra):
        request = {"action": action, "backup": record["document"], **extra}
        if record["document"].get("secrets") is not None:
            request["passphrase"] = ensure_passphrase(self.hass, self.entry)
        return request

    async def async_check(self, address, password, record_id):
        """Let the E32 at address check a stored backup; returns a RestoreCheck."""
        record = self.record(record_id)
        if record is None:
            raise ControllerLinkError("setup_changed")
        stored = credentials(self.entry)
        async with self._lock:
            async with self._client(address) as client:
                await self._sign_in(client, password, stored=stored == (address, password))
                device, _ = await client.async_read("/config/device")
                mqtt = device.get("mqtt") if type(device) is dict else None
                identity = mqtt.get("native_source_device_id") if type(mqtt) is dict else None
                identity = identity if type(identity) is str and re.fullmatch(r"e32_[0-9a-f]{12}", identity) else None
                value, status = await client.async_config_backup(self._request("validate", record))
                if status != 200:
                    raise ControllerLinkError("controller_response_invalid")
                summary = _summary(value)
        return RestoreCheck(record_id, address, password, value["fingerprint"], summary, identity)

    async def async_restore(self, check):
        """Apply exactly what the E32 checked, after a backup of the E32 as it is now.

        Returns {"restart", "restart_scheduled", "online", "reenter"}: online is
        True once the restarted E32 answers again (None without a restart).
        """
        from asyncio import timeout
        if type(check) is not RestoreCheck:
            raise ControllerLinkError("controller_request_invalid")
        record = self.record(check.record_id)
        if record is None:
            raise ControllerLinkError("setup_changed")
        stored = credentials(self.entry)
        async with self._lock:
            value = None
            async with self._client(check.address) as client:
                await self._sign_in(client, check.password, stored=stored == (check.address, check.password))
                before = await self._export(client)
                # The E32 as it is now becomes the undo point once the apply may have changed it, and
                # the backup being restored stays too: restoring the last undo point never loses it.
                try:
                    value, status = await client.async_config_backup(
                        self._request("apply", record, fingerprint=check.fingerprint))
                except BackupRejected as err:
                    if err.error == "save_partial":
                        await self._keep("pre_restore", before, keep=(record["id"],))
                    raise  # refused: the E32 is as it was, and so are the backups
                except ControllerLinkError as err:
                    if str(err) in _NOT_APPLIED:
                        raise
                    value = None  # sent, but no answer (a timeout, a reset connection)
                else:
                    if status != 201 or type(value) is not dict or value.get("applied") is not True:
                        value = None
            if value is None:
                # It may have been applied: both undo points stay, and the E32 checks the backup
                # again. No change left means the restore arrived (and this E32 is the one restored).
                await self._keep("pre_restore", before, keep=(record["id"],))
                arrived = await self._arrived(check, record)
                if arrived is not True:
                    raise ControllerLinkError("e32_restore_unconfirmed" if arrived is None else "e32_restore_not_applied")
                value = {"restart": check.summary["restart"], "restart_scheduled": check.summary["restart"],
                         "reenter": check.summary["reenter"]}
            else:
                await self._keep("pre_restore", before)
            restart = value.get("restart") is True
            scheduled = value.get("restart_scheduled") is True
            reenter = [text for text in value.get("reenter") or [] if type(text) is str]
            self._adopt(check)
            online = None
            if scheduled:
                delay = value.get("restart_in_s")
                delay = delay if type(delay) is int and 0 <= delay <= 60 else RESTART_DELAY
                online = False
                try:
                    async with timeout(RESTART_WAIT):
                        await asyncio.sleep(delay + RESTART_POLL)
                        while not online:
                            try:
                                async with self._client(check.address) as client:
                                    await client.async_login(check.password)
                                    await client.async_read("/status/version")
                                online = True
                            except ControllerLinkError:
                                await asyncio.sleep(RESTART_POLL)
                except TimeoutError:
                    pass
        return {"restart": restart, "restart_scheduled": scheduled, "online": online, "reenter": reenter}

    async def _arrived(self, check, record):
        """After an apply without a valid answer: does the E32 now hold the backup's settings?

        True: the E32's check finds nothing left to change. False: it finds
        changes (the apply did not arrive). None: no answer within RESTART_WAIT,
        or the password is refused (never tried twice).
        """
        from asyncio import timeout
        try:
            async with timeout(RESTART_WAIT):
                while True:
                    try:
                        async with self._client(check.address) as client:
                            await client.async_login(check.password)
                            value, status = await client.async_config_backup(self._request("validate", record))
                            if status == 200:
                                return not _summary(value)["changes"]
                    except ControllerLoginRejected:
                        return None
                    except ControllerLinkError:
                        pass  # restarting, or busy: ask again
                    await asyncio.sleep(RESTART_POLL)
        except TimeoutError:
            return None

    @callback
    def adopt(self, check):
        """The user confirmed: this installation uses the checked E32 from now on (it holds the settings)."""
        return self._adopt(check)

    def _adopt(self, check):
        """After a restore: this installation's E32 is the one restored (a replacement may differ).

        True when the entry uses check's E32 (now or already). Never an E32 of
        another installation in this Home Assistant (other_installation).
        """
        from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_ID, CONTROLLER_PASSWORD
        from .product import commit_configuration, configuration_snapshot
        entry = self.entry
        if self.hass.config_entries.async_get_entry(entry.entry_id) is not entry:
            return False
        wanted = {CONTROLLER_ADDRESS: check.address, CONTROLLER_PASSWORD: check.password}
        if check.identity is not None:
            wanted[CONTROLLER_ID] = check.identity
        if all(entry.data.get(k) == v for k, v in wanted.items()):
            return True
        if other_installation(self.hass, entry, check):
            _LOGGER.warning("E32 settings restored; that E32 belongs to another installation and is not linked")
            return False
        self._rejected_password = None
        if all(entry.data.get(k) == v for k, v in wanted.items() if k != CONTROLLER_PASSWORD):
            from .e32_access import save_password
            save_password(self.hass, entry, check.password)
            return True
        try:
            # Another address or another E32: the entry reloads and links it.
            commit_configuration(self.hass, entry, configuration_snapshot(entry), data={**entry.data, **wanted})
        except ValueError:
            _LOGGER.warning("E32 settings restored; the new E32 address could not be saved in Home Assistant")
            return False
        return True


def other_e32(entry, check):
    """True when check's E32 is not the entry's own one (another address, or another E32 identity)."""
    from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_ID
    return (check.address != entry.data.get(CONTROLLER_ADDRESS)
            or entry.data.get(CONTROLLER_ID) not in (None, check.identity))


def other_installation(hass, entry, check):
    """True when check's E32 belongs to another OpenThermostat installation in this Home Assistant.

    The same E32 identity or address as another entry, or a restore that
    would move the E32's Home Assistant link away from another entry's adapter.
    """
    from .controller_link import controller_address
    from .controller_setup_flow import CONTROLLER_ADDRESS, CONTROLLER_ID
    adapters = set()
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry.entry_id:
            continue
        if check.identity is not None and other.data.get(CONTROLLER_ID) == check.identity:
            return True
        try:
            if controller_address(other.data.get(CONTROLLER_ADDRESS)) == check.address:
                return True
        except ControllerLinkError:
            pass  # no (valid) stored address
        adapter = other.options.get("adapter_id", other.data.get("adapter_id"))
        if type(adapter) is str and adapter:
            adapters.add(adapter)
    adapters.discard(entry.options.get("adapter_id", entry.data.get("adapter_id")))  # its own link
    return any(change["field"] == "mqtt.adapter_id" and change.get("from") in adapters
               for change in check.summary["changes"])


def backups(hass, entry):
    """The running backups of an entry, or None."""
    state = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    return state.get(STATE_KEY) if state is not None else None


async def async_setup_backups(hass, entry, state):
    """Product entries with a stored E32 connection: load the backups and start the schedule."""
    if credentials(entry) is None:
        return None
    manager = E32Backups(hass, entry)
    await manager.async_load()
    state[STATE_KEY] = manager
    manager.start()
    entry.async_on_unload(manager.stop)
    return manager


async def async_remove_backups(hass, entry_id):
    """A removed installation leaves no backup files behind."""
    await Store(hass, STORE_VERSION, store_key(entry_id), private=True).async_remove()


# -- texts of the restore summary (EN/NL/PL) ---------------------------------

_SECTIONS = {
    "network": ("Network", "Netwerk", "Sieć"),
    "bluetooth": ("Bluetooth sensors", "Bluetooth-sensoren", "Czujniki Bluetooth"),
    "heating": ("Rooms", "Ruimtes", "Pomieszczenia"),
    "flow": ("Water temperature", "Watertemperatuur", "Temperatura wody"),
    "boiler_display": ("Boiler model", "Ketelmodel", "Model kotła"),
    "learned": ("What the thermostat has learned", "Wat de thermostaat heeft geleerd", "Czego nauczył się termostat"),
}
_FIELDS = {
    "hostname": ("Device name", "Apparaatnaam", "Nazwa urządzenia"),
    "interface_mode": ("Connection", "Verbinding", "Połączenie"),
    "listenPort": ("Web page port", "Poort van de webpagina", "Port strony"),
    "emsEnabled": ("EMS bus", "EMS-bus", "Magistrala EMS"),
    "emsForwarderEnabled": ("EMS forwarder", "EMS-doorsturing", "Przekazywanie EMS"),
    "rtcEnabled": ("Clock chip", "Klokchip", "Układ zegara"),
    "ntpEnabled": ("Time from the internet", "Tijd van internet", "Czas z internetu"),
    "ntpHost": ("Time server", "Tijdserver", "Serwer czasu"),
    "ntpUtcOffset": ("UTC offset", "Verschil met UTC", "Przesunięcie względem UTC"),
    "ntpDaylightUtcOffset": ("Daylight saving offset", "Verschil zomertijd", "Przesunięcie czasu letniego"),
    "timeZone": ("Time zone", "Tijdzone", "Strefa czasowa"),
    "loggerEnabled": ("Debugging over socket", "Foutopsporing via socket", "Debugowanie przez gniazdo"),
    "loggerHost": ("Debugging over socket", "Foutopsporing via socket", "Debugowanie przez gniazdo"),
    "loggerPort": ("Debugging over socket", "Foutopsporing via socket", "Debugowanie przez gniazdo"),
    "loggerTimeoutMs": ("Debugging over socket", "Foutopsporing via socket", "Debugowanie przez gniazdo"),
    "mqtt.enabled": ("MQTT", "MQTT", "MQTT"),
    "mqtt.modern_shadow": ("Home Assistant link", "Koppeling met Home Assistant", "Połączenie z Home Assistant"),
    "mqtt.adapter_id": ("Home Assistant adapter ID", "Adapter-ID van Home Assistant", "ID adaptera Home Assistant"),
    "mqtt.publishHomeAssistantDiscovery": ("MQTT discovery", "MQTT-discovery", "Wykrywanie MQTT"),
    "mqtt.brokerAddress": ("MQTT broker", "MQTT-broker", "Broker MQTT"),
    "mqtt.brokerPort": ("MQTT port", "MQTT-poort", "Port MQTT"),
    "mqtt.username": ("MQTT user", "MQTT-gebruiker", "Użytkownik MQTT"),
    "mqtt.password": ("MQTT password", "MQTT-wachtwoord", "Hasło MQTT"),
    "mqtt.clientId": ("MQTT client ID", "MQTT-client-ID", "ID klienta MQTT"),
    "mqtt.base": ("MQTT topic", "MQTT-topic", "Temat MQTT"),
    "mqtt.keepAlive": ("MQTT keep-alive", "MQTT-keep-alive", "Keep-alive MQTT"),
    "mqtt.interval": ("MQTT interval", "MQTT-interval", "Interwał MQTT"),
    "openweather.enabled": ("OpenWeather", "OpenWeather", "OpenWeather"),
    "openweather.latitude": ("OpenWeather", "OpenWeather", "OpenWeather"),
    "openweather.longitude": ("OpenWeather", "OpenWeather", "OpenWeather"),
    "openweather.interval": ("OpenWeather", "OpenWeather", "OpenWeather"),
    "openweather.appid": ("OpenWeather API key", "OpenWeather-API-sleutel", "Klucz API OpenWeather"),
    "bt.scanTime": ("Bluetooth listening time", "Luistertijd Bluetooth", "Czas nasłuchu Bluetooth"),
    "bt.scanInterval": ("Bluetooth pause", "Pauze Bluetooth", "Przerwa Bluetooth"),
    "devices": ("Sensors", "Sensoren", "Czujniki"),
    "rooms": ("Rooms", "Ruimtes", "Pomieszczenia"),
    "room_settings": ("Room settings", "Instellingen van de ruimtes", "Ustawienia pomieszczeń"),
    "minimum_flow_c": ("Lowest water temperature", "Laagste watertemperatuur", "Najniższa temperatura wody"),
    "maximum_flow_c": ("Highest water temperature", "Hoogste watertemperatuur", "Najwyższa temperatura wody"),
    "weather_curve": ("Follow outdoor temperature (heating curve)", "Buitentemperatuur volgen (stooklijn)", "Krzywa grzewcza wg temperatury zewnętrznej"),
    "apply_learned": ("Warm on time with the coolest water", "Op tijd warm met het koelste water", "Ciepło na czas przy najchłodniejszej wodzie"),
    "curve_design_flow_c": ("Water temperature at −10 °C outside", "Watertemperatuur bij −10 °C buiten", "Temperatura wody przy −10 °C na zewnątrz"),
    "model": ("Boiler model", "Ketelmodel", "Model kotła"),
    "tuning": ("Comfort and boiler care", "Comfort en zorg voor de ketel", "Komfort i dbałość o kocioł"),
    "tuning_manual": ("Comfort and boiler care: set by you", "Comfort en zorg voor de ketel: door jou ingesteld",
                      "Komfort i dbałość o kocioł: ustawione przez ciebie"),
    "learned": ("What the thermostat has learned", "Wat de thermostaat heeft geleerd", "Czego nauczył się termostat"),
}
_REENTER = {
    "wifi_password": ("Wi-Fi password", "Wifi-wachtwoord", "Hasło Wi-Fi"),
    "web_password": ("Web page password", "Wachtwoord van de webpagina", "Hasło strony"),
    "mqtt_password": ("MQTT password", "MQTT-wachtwoord", "Hasło MQTT"),
    "openweather_key": ("OpenWeather API key", "OpenWeather-API-sleutel", "Klucz API OpenWeather"),
    "bluetooth_keys": ("Bluetooth sensor keys", "Sleutels van Bluetooth-sensoren", "Klucze czujników Bluetooth"),
    "bluetooth_key": ("Bluetooth key for {v}", "Bluetooth-sleutel van {v}", "Klucz Bluetooth dla {v}"),
}
_WARNINGS = {
    "other_firmware": ("Made with firmware {v}.", "Gemaakt met firmware {v}.", "Utworzona z oprogramowaniem {v}."),
    "unknown_key": ("Skipped, not known by this firmware: {v}", "Overgeslagen, onbekend voor deze firmware: {v}",
                    "Pominięto, nieznane dla tego oprogramowania: {v}"),
    "invalid_value": ("Invalid value: {v}", "Ongeldige waarde: {v}", "Nieprawidłowa wartość: {v}"),
    "learned_skipped": ("What the thermostat learned could not be read from this backup; it keeps learning from what it has.",
                        "Wat de thermostaat geleerd heeft kon niet uit deze back-up worden gelezen; hij leert verder met wat hij al weet.",
                        "Nie udało się odczytać z kopii tego, czego nauczył się termostat; uczy się dalej na podstawie tego, co już wie."),
    "interface_kept": ("The connection type stays as it is.", "Het verbindingstype blijft zoals het is.",
                       "Typ połączenia pozostaje bez zmian."),
    "listen_port_kept": ("The web page port stays the same.", "De poort van de webpagina blijft gelijk.",
                         "Port strony pozostaje bez zmian."),
    "mqtt_off_until_password": ("MQTT stays off until you enter the MQTT password.",
                                "MQTT blijft uit tot je het MQTT-wachtwoord invoert.",
                                "MQTT pozostaje wyłączone, dopóki nie wpiszesz hasła MQTT."),
    "native_source_cleared": ("The room profile of this E32 is cleared because the Home Assistant link changes.",
                              "Het ruimteprofiel van deze E32 wordt gewist omdat de koppeling met Home Assistant verandert.",
                              "Profil pomieszczeń tego E32 zostanie usunięty, bo zmienia się połączenie z Home Assistant."),
    "weather_managed_kept": ("Weather settings are managed by Home Assistant and stay as they are.",
                             "De weerinstellingen worden door Home Assistant beheerd en blijven zoals ze zijn.",
                             "Ustawieniami pogody zarządza Home Assistant; pozostają bez zmian."),
    "plan_mode_shadow": ("The rooms are restored in the trial run.", "De ruimtes worden teruggezet in de proefperiode.",
                         "Pomieszczenia zostaną przywrócone w okresie próbnym."),
    "wifi_not_restored": ("Wi-Fi is not changed by a restore.", "Terugzetten verandert de wifi niet.",
                          "Przywracanie nie zmienia Wi-Fi."),
    "secrets_skipped": ("Passwords and keys in the backup are skipped.",
                        "Wachtwoorden en sleutels in de back-up worden overgeslagen.",
                        "Hasła i klucze z kopii zostaną pominięte."),
    "unknown_boiler_model": ("Unknown boiler model skipped: {v}", "Onbekend ketelmodel overgeslagen: {v}",
                             "Pominięto nieznany model kotła: {v}"),
    "unknown_language": ("Unknown language skipped.", "Onbekende taal overgeslagen.", "Pominięto nieznany język."),
    "heating": ("Rooms: {v}", "Ruimtes: {v}", "Pomieszczenia: {v}"),
    "bluetooth": ("Bluetooth sensors: {v}", "Bluetooth-sensoren: {v}", "Czujniki Bluetooth: {v}"),
}
_WORDS = {
    "on": ("On", "Aan", "Wł."), "off": ("Off", "Uit", "Wył."), "hidden": ("will change", "verandert", "zmieni się"),
    "changes": ("These settings change:", "Deze instellingen veranderen:", "Te ustawienia się zmienią:"),
    "notes": ("Notes, and what is skipped:", "Opmerkingen, en wat wordt overgeslagen:", "Uwagi i to, co zostanie pominięte:"),
    "reenter": ("Enter these again on the E32 page afterwards:", "Voer dit daarna opnieuw in op de E32-pagina:",
                "Wpisz to potem ponownie na stronie E32:"),
    "restart": ("The E32 restarts after the restore; Home Assistant waits until it answers again.",
                "De E32 start na het terugzetten opnieuw op; Home Assistant wacht tot hij weer antwoordt.",
                "E32 uruchomi się ponownie po przywróceniu; Home Assistant poczeka, aż znów odpowie."),
    "daily": ("daily", "dagelijks", "codzienna"), "manual": ("manual", "handmatig", "ręczna"),
    "pre_restore": ("before a restore", "vóór terugzetten", "przed przywróceniem"),
    "secrets": ("with passwords and keys", "met wachtwoorden en sleutels", "z hasłami i kluczami"),
}


def _language(language):
    return {"nl": 1, "pl": 2}.get(str(language or "en").split("-")[0], 0)


def _text(table, key, language, detail=""):
    texts = table.get(key)
    return texts[_language(language)].replace("{v}", detail) if texts else key + (f": {detail}" if detail else "")


def _coded(table, item, language):
    code, _, detail = str(item).partition(":")
    return _text(table, code, language, detail) if code in table else str(item)


def _shown(value, language):
    if value is True:
        return _text(_WORDS, "on", language)
    if value is False:
        return _text(_WORDS, "off", language)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "—"
    if value is None or value == "":
        return "—"
    return str(value)


def _tuning_lines(change, label, language):
    """Comfort and boiler care: one line per changed setting, by its plain name and with its value
    in words as the E32's Home page shows it (tuning), or who set it (tuning_manual)."""
    from .learned_overview import KNOB, TEXT, knob_value
    lang = ("en", "nl", "pl")[_language(language)]
    words = TEXT[lang]
    care = _text(_FIELDS, "tuning", language)
    was, now = change.get("from"), change.get("to")
    if change["field"] == "tuning":
        was, now = (value if isinstance(value, dict) else {} for value in (was, now))

        def shown(key, value):
            return knob_value(key, value, lang) if type(value) in (int, float) else "—"
        changed = [key for key in KNOB if was.get(key) != now.get(key)]
        lines = [f"- {care} · {words['knob.' + key]}: {shown(key, was.get(key))} → {shown(key, now.get(key))}"
                 for key in changed]
    else:
        was, now = (set(value) if isinstance(value, list) else set() for value in (was, now))

        def who(key, mine):
            return words["yours" if mine else "automatic" if KNOB[key][0] else "standard"].strip("()")
        lines = [f"- {care} · {words['knob.' + key]}: {who(key, key in was)} → {who(key, key in now)}"
                 for key in KNOB if (key in was) != (key in now)]
    return lines or [f"- {label}: {_text(_WORDS, 'hidden', language)}"]


def summary_text(summary, language):
    """The E32's check as a short list in the user's language (no secret: those are only named)."""
    lines = []
    if summary["changes"]:
        lines.append(_text(_WORDS, "changes", language))
        for change in summary["changes"]:
            section = _text(_SECTIONS, change["section"], language)
            name = _text(_FIELDS, change["field"], language)
            label = name if name == section else f"{section} · {name}"
            if change["field"] in ("tuning", "tuning_manual") and not change.get("hidden"):
                lines += _tuning_lines(change, label, language)
                continue
            value = (_text(_WORDS, "hidden", language) if change.get("hidden")
                     else f"{_shown(change.get('from'), language)} → {_shown(change.get('to'), language)}")
            lines.append(f"- {label}: {value}")
    if summary["warnings"]:
        lines += ["", _text(_WORDS, "notes", language)]
        lines += [f"- {_coded(_WARNINGS, item, language)}" for item in summary["warnings"]]
    if summary["reenter"]:
        lines += ["", _text(_WORDS, "reenter", language)]
        lines += [f"- {_coded(_REENTER, item, language)}" for item in summary["reenter"]]
    if summary["restart"]:
        lines += ["", _text(_WORDS, "restart", language)]
    return "\n".join(lines).strip()


def reenter_text(items, language):
    return "\n".join(f"- {_coded(_REENTER, item, language)}" for item in items) or "-"


def record_label(record, language):
    """One stored backup as the restore form lists it: when, which kind and its size."""
    when = dt_util.as_local(_created(record)).strftime("%Y-%m-%d %H:%M")
    parts = [when, _text(_WORDS, record["kind"], language), f"{max(1, round(record['size'] / 1024))} kB"]
    if record.get("secrets"):
        parts.append(_text(_WORDS, "secrets", language))
    return " · ".join(parts)


def created_text(record):
    return dt_util.as_local(_created(record)).strftime("%Y-%m-%d %H:%M")


def last_backup(manager):
    """For the sensor: the time of the last good backup, the number kept and the newest size."""
    records = manager.records()
    return manager.last_success, {"count": len(records), "size": records[0]["size"] if records else None}
