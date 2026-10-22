"""Initial room-setpoint actuator adapter, locked out of all normal shadow runs.

Only explicit future bench wiring may inject an authorization callback AND
qualified_profile=True. Neither has a GUI option in this candidate.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal, DecimalException, ROUND_HALF_UP
import math
from dataclasses import dataclass
from collections.abc import Callable

from homeassistant.core import HomeAssistant
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.exceptions import HomeAssistantError

ACTION_TIMEOUT_SECONDS = 10.0

class InvalidTargetCapability(HomeAssistantError):
    """Advertised numeric metadata cannot be used without inventing a value."""


@dataclass(frozen=True)
class TargetCapability:
    unit: str
    minimum: Decimal
    maximum: Decimal
    step: Decimal

    def native(self, celsius):
        # Match the existing adapter's numeric conversion and rounding exactly.
        return Decimal(str(celsius if self.unit == "°C" else celsius * 9 / 5 + 32))

    def target(self, celsius):
        value = self.native(celsius)
        if not self.minimum <= value <= self.maximum:
            raise HomeAssistantError("TRV target outside verified bounds")
        try:
            actual = self.minimum + ((value - self.minimum) / self.step).quantize(
                Decimal(1), rounding=ROUND_HALF_UP) * self.step
        except DecimalException as err:
            raise InvalidTargetCapability("TRV capability bounds unverified") from err
        if not self.minimum <= actual <= self.maximum:
            raise HomeAssistantError("Bench authorization expired or invalid target")
        return actual


def target_capability(hass, state):
    """Read advertised target metadata only; this never qualifies physical control."""
    if state is None or state.state in ("unknown", "unavailable"):
        raise HomeAssistantError("TRV unavailable")
    attrs = state.attributes
    features = attrs.get("supported_features", 0)
    # Native climate entities expose this official IntFlag in memory. JSON
    # turns it into an int, so JSON-only fixtures cannot qualify this check.
    if type(features) not in (int, ClimateEntityFeature) or not features & 1:
        raise HomeAssistantError("TRV has no target-temperature capability")
    unit = attrs.get("unit_of_measurement", hass.config.units.temperature_unit)
    values = [attrs.get("min_temp"), attrs.get("max_temp"), attrs.get("target_temp_step")]
    if unit not in ("°C", "°F") or any(isinstance(x, bool) or not isinstance(x, (int, float))
            or not math.isfinite(x) for x in values):
        raise HomeAssistantError("TRV capability bounds unverified")
    low, high, step = (Decimal(str(x)) for x in values)
    if step <= 0 or low >= high:
        raise HomeAssistantError("TRV capability bounds unverified")
    return TargetCapability(unit, low, high, step)


def review_room_targets(hass, room, entity_ids):
    """Compare saved room targets to the SAME conversion as the guarded adapter.

    Read-only metadata/compatibility evidence, never actuator readiness, exclusive
    ownership, measurement quality or a physical profile qualification.
    """
    rows = []
    targets = [("base", room.base_centi_c / 100)]
    for day, blocks in (room.week_program or {}).items():
        targets.extend((f"{day}/{i}", block["target_centi_c"] / 100)
                       for i, block in enumerate(blocks))
    for entity_id in entity_ids:
        row = {"entity_id": entity_id, "status": "unknown", "issues": [], "targets": []}
        try:
            cap = target_capability(hass, hass.states.get(entity_id))
        except HomeAssistantError:
            row["issues"].append("capability_unavailable")
        else:
            row["capability"] = {"unit": cap.unit, "minimum": float(cap.minimum),
                                  "maximum": float(cap.maximum), "step": float(cap.step)}
            if (cap.native(room.minimum_target_centi_c / 100) < cap.minimum
                    or cap.native(room.maximum_target_centi_c / 100) > cap.maximum):
                row["issues"].append("room_limits_exceed_actuator")
            for where, value in targets:
                item = {"where": where, "requested_celsius": value}
                try:
                    actual = cap.target(value)
                except InvalidTargetCapability:
                    row["issues"] = ["capability_unavailable"]
                    row["targets"] = []
                    break
                except HomeAssistantError:
                    item["issue"] = "target_outside_actuator"
                else:
                    if actual == cap.native(value):
                        continue
                    item.update(issue="target_will_round", native_result=float(actual), unit=cap.unit)
                row["targets"].append(item)
            if row["targets"]:
                row["issues"].append("saved_targets_need_review")
            row["status"] = ("unknown" if "capability_unavailable" in row["issues"]
                             else "review_required" if row["issues"] else "compatible")
        rows.append(row)
    return {"status": "unknown" if room.schedule is not None or not rows or any(r["status"] == "unknown" for r in rows)
            else "review_required" if any(r["issues"] for r in rows) else "compatible",
            "scope": "saved_local_room_targets", "external_program_checked": False,
            "external_program_present": room.schedule is not None,
            "authorizes_actuation": False, "actuators": rows}


class ProfileCActuator:
    def __init__(self, hass: HomeAssistant, entity_id: str, *,
                 qualified_profile: bool = False,
                 authorize: Callable[[], bool] | None = None):
        if not entity_id.startswith("climate.") or "," in entity_id:
            raise ValueError("one climate actuator required")
        self.hass, self.entity_id = hass, entity_id
        self._qualified = qualified_profile
        self._authorize = authorize or (lambda: False)
        self._lock = asyncio.Lock()

    async def async_set_room_target(self, celsius: float) -> float:
        from .v1_model import target_centi
        target_centi(celsius)
        async with self._lock:
            if not self._qualified or not self._authorize():
                raise HomeAssistantError("Profile C bench actuation is disabled")
            capability = target_capability(self.hass, self.hass.states.get(self.entity_id))
            actual = capability.target(celsius)
            if not self._authorize():
                raise HomeAssistantError("Bench authorization expired or invalid target")
            # A successful HA call is action acceptance only, NEVER valve readiness.
            try:
                async with asyncio.timeout(ACTION_TIMEOUT_SECONDS):
                    await self.hass.services.async_call(
                        "climate", "set_temperature",
                        {"entity_id": self.entity_id, "temperature": float(actual)},
                        blocking=True,
                    )
            except TimeoutError as err:
                # Cancellation does not prove a remote action was cancelled.
                # No retry or readiness is synthesized from this uncertainty.
                raise HomeAssistantError("TRV action timed out; physical outcome unknown") from err
            return float(actual)
