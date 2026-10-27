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
                or self.kind not in ("window","presence","contact")
                or type(self.schema) is not int or self.schema!=1
                or type(self.maximum_age_ms) is not int or self.maximum_age_ms!=CONTEXT_MAX_AGE_MS
                or not callable(self.report) or inspect.iscoroutinefunction(self.report)
                or inspect.isgeneratorfunction(self.report)):
            raise ValueError("context_profile_invalid")

    @property
    def identity(self):
        return ("binary_sensor" if self.kind in ("window","contact") else "person", self.platform, self.unique_id)


@dataclass(frozen=True, slots=True)
class ControllerPolicySourceProfile:
    """Exact logical SOURCE policy/owner/config expectation, never output rights.

    Selected by native entry SOURCE code only. No GUI/remote discovery can
    construct or select this object; an advertised digest alone is insufficient.
    """
    entry_unique_id: str
    controller_id: str
    adapter_id: str
    profile_digest: str
    config_digest: str
    schema: int = 1

    def validate(self):
        if (not isinstance(self.entry_unique_id,str) or not self.entry_unique_id
                or len(self.entry_unique_id)>256 or type(self.schema) is not int or self.schema!=1):
            raise ValueError("controller_policy_profile_invalid")
        for value in (self.controller_id,self.adapter_id):
            if not isinstance(value,str) or re.fullmatch(r"[A-Za-z0-9_-]{1,32}",value) is None:
                raise ValueError("controller_policy_profile_invalid")
        for value in (self.profile_digest,self.config_digest):
            if not isinstance(value,str) or re.fullmatch(r"[0-9a-f]{64}",value) is None:
                raise ValueError("controller_policy_profile_invalid")

    def matches(self,message):
        value=message.get("source_policy")
        return (message.get("controller_id")==self.controller_id and type(value) is dict
            and set(value)=={"schema","kind","adapter_id","profile_digest","config_pin",
                              "physical_outputs_enabled","frost_protection_available"}
            and type(value["schema"]) is int and value["schema"]==self.schema
            and value["kind"]=="seasonal.shadow.v1" and value["adapter_id"]==self.adapter_id
            and value["profile_digest"]==self.profile_digest and value["config_pin"]==self.config_digest
            and value["physical_outputs_enabled"] is False and value["frost_protection_available"] is False)
