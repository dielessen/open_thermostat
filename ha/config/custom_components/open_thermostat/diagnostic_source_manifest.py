"""Private installation-owned TV02 receive pins. No writer or control authority."""
from __future__ import annotations

import json
import logging
import os
import re
import stat

from .original_temperature import _pairs, _constant
from .original_tv02 import MANUFACTURERS, Tv02DiagnosticSource
from .v1_model import EntityReference

_LOGGER = logging.getLogger(__name__)
FILE_NAME = ".openthermostat-original-tv02.json"
MAX_BYTES = 32768
MAX_SOURCES = 64
_KEYS = frozenset({"entry_unique_id", "room_id", "entity_id", "platform", "unique_id", "manufacturer", "endpoint"})


def _text(value, maximum):
    return type(value) is str and 0 < len(value) <= maximum and all(ord(c) >= 32 and ord(c) != 127 for c in value)


def decode_manifest(raw):
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("invalid diagnostic manifest")
    value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    if (type(value) is not dict or set(value) != {"schema", "kind", "sources"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or value["kind"] != "original_tv02_receive_only"
            or type(value["sources"]) is not list or len(value["sources"]) > MAX_SOURCES):
        raise ValueError("invalid diagnostic manifest")
    sources, seen = [], set()
    for item in value["sources"]:
        if (type(item) is not dict or set(item) != _KEYS
                or not _text(item["entry_unique_id"], 256)
                or type(item["room_id"]) is not str or not re.fullmatch(r"[0-9a-f]{8}", item["room_id"])
                or not _text(item["entity_id"], 255) or not re.fullmatch(r"climate\.[a-z0-9_]+", item["entity_id"])
                or item["platform"] != "mqtt" or not _text(item["unique_id"], 512)
                or type(item["manufacturer"]) is not str or item["manufacturer"] not in MANUFACTURERS
                or type(item["endpoint"]) is not int or not 1 <= item["endpoint"] <= 240):
            raise ValueError("invalid diagnostic source")
        key = item["entry_unique_id"], item["platform"], item["unique_id"]
        if key in seen:
            raise ValueError("duplicate diagnostic source")
        seen.add(key)
        sources.append(Tv02DiagnosticSource(item["entry_unique_id"], item["room_id"],
            EntityReference(item["entity_id"], item["platform"], item["unique_id"]),
            item["manufacturer"], item["endpoint"]))
    return tuple(sources)


def _read(path):
    # Nonblocking open prevents a special file from stalling startup. The final
    # component cannot be a symlink; only private regular files are accepted.
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("private diagnostic file unsupported")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return ()
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) & 0o077
                or before.st_size > MAX_BYTES):
            raise ValueError("invalid private diagnostic file")
        raw = os.read(fd, MAX_BYTES + 1)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("diagnostic file changed during read")
    finally:
        os.close(fd)
    return decode_manifest(raw)


async def async_selected_sources(hass, entry):
    """One startup snapshot; no watch, discovery fallback, Store or file writes."""
    try:
        sources = await hass.async_add_executor_job(_read, hass.config.path(FILE_NAME))
        return tuple(source for source in sources if source.entry_unique_id == entry.unique_id)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        # No native IDs, path contents, raw payload or exception text in logs.
        _LOGGER.warning("Original TV02 diagnostics disabled: invalid private installation manifest")
        return ()
