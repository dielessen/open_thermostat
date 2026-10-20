"""Local v1-domain objects; deliberately NOT a wire schema."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Any

from .v1_program import normalize_program

MODE_LEGACY = "legacy"
MODE_SHADOW = "v1_shadow"
CONF_MODE = "integration_mode"
CONF_ENABLED = "shadow_enabled"
ROOM_LIMIT = 8
ROOM_CLIMATE_TRV = "climate_trv"
ROOM_GRAPH_DRAFT = "graph_only_draft"

def has_graph_rooms(entry: Any) -> bool:
    return any(s.subentry_type == "zone" and s.data.get("binding_mode") == ROOM_GRAPH_DRAFT
               for s in entry.subentries.values())
_ROOM_ID = re.compile(r"[0-9a-f]{8}")

def integration_mode(entry: Any) -> str:
    return entry.options.get(CONF_MODE, entry.data.get(CONF_MODE, MODE_LEGACY))

@dataclass(frozen=True)
class EntityReference:
    entity_id: str
    platform: str | None = None
    unique_id: str | None = None

    @classmethod
    def from_dict(cls, value: dict) -> EntityReference:
        return cls(value["entity_id"], value.get("platform"), value.get("unique_id"))

    def identity(self) -> tuple:
        if self.platform is not None and self.unique_id is not None:
            return (self.entity_id.split(".", 1)[0], self.platform, self.unique_id)
        return (self.entity_id,)

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "platform": self.platform, "unique_id": self.unique_id}

@dataclass(frozen=True)
class RoomBinding:
    room_id: str
    name: str
    temperature: EntityReference
    actuators: tuple[EntityReference, ...]
    setpoint: EntityReference | None = None
    maximum_age_ms: int = 120000
    base_centi_c: int = 2100
    schedule: EntityReference | None = None
    minimum_target_centi_c: int = 500
    maximum_target_centi_c: int = 3500
    week_program: dict | None = None
    binding_mode: str = ROOM_CLIMATE_TRV

    @property
    def shadow_wire_supported(self) -> bool:
        return self.binding_mode == ROOM_CLIMATE_TRV

    @classmethod
    def from_dict(cls, value: dict) -> RoomBinding:
        room_id = value["room_id"]
        if not isinstance(room_id, str) or _ROOM_ID.fullmatch(room_id) is None:
            raise ValueError("invalid permanent room ID")
        age = value.get("maximum_age_ms", 120000)
        if type(age) is not int or not 1000 <= age <= 86400000:
            raise ValueError("invalid source maximum age")
        temperature = EntityReference.from_dict(value["temperature"])
        actuators = tuple(EntityReference.from_dict(x) for x in value["actuators"])
        setpoint = EntityReference.from_dict(value["setpoint"]) if value.get("setpoint") else None
        ids = [temperature.entity_id] + [x.entity_id for x in actuators]
        if setpoint:
            ids.append(setpoint.entity_id)
        mode = value.get("binding_mode", ROOM_CLIMATE_TRV)
        if mode not in (ROOM_CLIMATE_TRV, ROOM_GRAPH_DRAFT):
            raise ValueError("unsupported_room_binding_mode")
        if (mode == ROOM_CLIMATE_TRV and not actuators) or (mode == ROOM_GRAPH_DRAFT and actuators):
            raise ValueError("room_mode_actuator_conflict")
        if len(actuators) > 8 or len(ids) != len(set(ids)):
            raise ValueError("duplicate, looping or missing room binding")
        if not temperature.entity_id.startswith("sensor."):
            raise ValueError("temperature source must be a sensor")
        if any(not x.entity_id.startswith("climate.") for x in actuators):
            raise ValueError("initial profile C requires climate actuators")
        if setpoint and not setpoint.entity_id.startswith(("climate.", "number.")):
            raise ValueError("unsupported physical setpoint source")
        base = value.get("base_centi_c", 2100)
        if type(base) is not int or not 500 <= base <= 3500:
            raise ValueError("invalid base target")
        minimum = value.get("minimum_target_centi_c", 500)
        maximum = value.get("maximum_target_centi_c", 3500)
        if (type(minimum) is not int or type(maximum) is not int
                or not 500 <= minimum < maximum <= 3500
                or not minimum <= base <= maximum):
            raise ValueError("invalid_target_range")
        schedule = EntityReference.from_dict(value["schedule"]) if value.get("schedule") else None
        if schedule and not schedule.entity_id.startswith("schedule."):
            raise ValueError("invalid schedule source")
        week = value.get("week_program")
        if week is not None:
            week = normalize_program(week, minimum, maximum)
            if schedule is not None:
                raise ValueError("program_source_conflict")
        return cls(room_id, str(value["name"]), temperature, actuators, setpoint, age, base, schedule, minimum, maximum, week, mode)

    def as_dict(self) -> dict:
        return {
            "room_id": self.room_id, "name": self.name,
            "temperature": self.temperature.as_dict(),
            "actuators": [x.as_dict() for x in self.actuators],
            "setpoint": self.setpoint.as_dict() if self.setpoint else None,
            "maximum_age_ms": self.maximum_age_ms,
            "actuator_profile": "C_unverified" if self.shadow_wire_supported else "graph_draft_not_applied",
            **({"binding_mode": self.binding_mode} if not self.shadow_wire_supported else {}),
            "base_centi_c": self.base_centi_c,
            "schedule": self.schedule.as_dict() if self.schedule else None,
            "minimum_target_centi_c": self.minimum_target_centi_c,
            "maximum_target_centi_c": self.maximum_target_centi_c,
            **({"week_program": normalize_program(self.week_program,
                 self.minimum_target_centi_c, self.maximum_target_centi_c)}
               if self.week_program is not None else {}),
        }

@dataclass(frozen=True)
class QualifiedReport:
    """Only a model-specific, trusted observer may construct this evidence.

    A cache/state write/device last_seen alone must never create this object.
    There is no GUI switch that turns such reports into physical evidence.
    """
    sample_key: str
    sampled_at: datetime

@dataclass(frozen=True)
class Observation:
    temperature_c: float | None
    quality: str
    source_age_ms: int | None = None
    source_key: str | None = None
    observed_monotonic: float | None = None

@dataclass(frozen=True)
class RoomDecision:
    """Already-admitted firmware state, supplied by the future wire adapter."""
    target_centi_c: int | None
    current_centi_c: int | None
    demand: bool
    reason: str

    def __post_init__(self):
        if self.target_centi_c is not None and (type(self.target_centi_c) is not int or not 500 <= self.target_centi_c <= 3500):
            raise ValueError("invalid confirmed target")
        if self.current_centi_c is not None and (
            type(self.current_centi_c) is not int or not -2000 <= self.current_centi_c <= 6000
        ):
            raise ValueError("invalid confirmed measurement")
        if type(self.demand) is not bool:
            raise ValueError("invalid firmware demand")

def temperature_c(state: Any) -> float | None:
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    try:
        value = float(state.state)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    unit = state.attributes.get("unit_of_measurement")
    if unit == "°F":
        value = (value - 32) * 5 / 9
    elif unit != "°C":
        return None
    return value if -20 <= value <= 60 else None

def target_centi(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("target must be finite numeric Celsius")
    from decimal import Decimal
    scaled = Decimal(str(value)) * 100
    if not 500 <= scaled <= 3500 or scaled != scaled.to_integral_value():
        raise ValueError("target outside 5..35 or has sub-centi precision")
    return int(scaled)
