"""Source-selected logical context evidence; never physical sensor/actuator proof.

No GUI, incoming state attribute or configuration can construct/select a profile.
Callbacks are trusted integration-specific code reviewed separately. Default empty.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import re
import inspect

CONTEXT_MAX_AGE_MS = 120000  # Existing v1 firmware contract, not a new TTL option.


@dataclass(frozen=True, slots=True)
class ContextReport:
    """New logical-source report identity/time, not a temperature measurement."""
    sample_key: str
    sampled_at: datetime


@dataclass(frozen=True, slots=True)
class ContextSourceProfile:
    entry_unique_id: str
    room_id: str
    kind: str
    platform: str
    unique_id: str
    profile_id: str
    report: Callable = field(repr=False, compare=False)
    schema: int = 1
    maximum_age_ms: int = CONTEXT_MAX_AGE_MS

    def validate(self):
        for value in (self.entry_unique_id, self.platform, self.unique_id, self.profile_id):
            if not isinstance(value, str) or not value or len(value)>256:
                raise ValueError("context_profile_invalid")
        if (not isinstance(self.room_id,str) or re.fullmatch(r"[0-9a-f]{8}",self.room_id) is None
                or self.kind not in ("window","presence")
                or type(self.schema) is not int or self.schema!=1
                or type(self.maximum_age_ms) is not int or self.maximum_age_ms!=CONTEXT_MAX_AGE_MS
                or not callable(self.report) or inspect.iscoroutinefunction(self.report)
                or inspect.isgeneratorfunction(self.report)):
            raise ValueError("context_profile_invalid")

    @property
    def identity(self):
        return ("binary_sensor" if self.kind=="window" else "person", self.platform, self.unique_id)
