"""Initial room-setpoint actuator adapter, locked out of all normal shadow runs.

Only explicit future bench wiring may inject an authorization callback AND
qualified_profile=True. Neither has a GUI option in this candidate.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal, DecimalException, ROUND_HALF_UP
import math
from dataclasses import dataclass, field, replace
from collections.abc import Callable

from homeassistant.core import HomeAssistant
from homeassistant.components.climate.const import ClimateEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .native_binding import native_binding_identity as _dispatch_binding

ACTION_TIMEOUT_SECONDS = 10.0

MODE_MESSAGES = {
    "local_schedule_active": ("De TV02 meldt een eigen weekprogramma. Dat kan het kamerdoel overschrijven.",
                              "The TV02 reports automatic scheduling, which can override the room target."),
    "holiday_mode_active": ("De TV02 meldt een vakantieprogramma. Dat kan het kamerdoel overschrijven.",
                            "The TV02 reports a holiday program, which can override the room target."),
    "heating_disabled": ("De TV02 meldt verwarming uit; de software schakelt de kraan niet automatisch in.",
                         "The TV02 reports heating off; software will not turn the valve on automatically."),
    "operating_mode_unknown": ("De bedrijfsmodus van de TV02 is niet bevestigd. Controleer de kraan en laad opnieuw.",
                               "The TV02 operating mode is unconfirmed. Check the valve, then reload."),
}


def reported_operating_mode(hass, entity_id):
    """Known TV02 mode conflicts only, never fresh echo or physical readiness.

    Registry model and HA state are declarations. They may deny a command but
    cannot provide its required profile/authorization or confirm motor movement.
    No inference from target temperature and no implicit preset/mode repair.
    """
    entity = er.async_get(hass).async_get(entity_id)
    device = dr.async_get(hass).async_get(entity.device_id) if entity and entity.device_id else None
    if device is None or getattr(device, "model_id", None) != "TV02-Zigbee":
        return None
    state = hass.states.get(entity_id)
    preset = state.attributes.get("preset_mode") if state else None
    if type(preset) is not str or preset not in ("auto", "manual", "holiday"):
        preset = None
    mode = state.state if state and state.state in ("heat", "off") else None
    issues = []
    if preset == "auto":
        issues.append("local_schedule_active")
    elif preset == "holiday":
        issues.append("holiday_mode_active")
    elif preset != "manual":
        issues.append("operating_mode_unknown")
    if mode == "off":
        issues.append("heating_disabled")
    elif mode is None and "operating_mode_unknown" not in issues:
        issues.append("operating_mode_unknown")
    return {"profile": "TV02-Zigbee", "scope": "reported_ha_operating_mode",
            "preset": preset, "system_mode": mode, "issues": issues,
            "authorizes_actuation": False}

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
        operating_mode = reported_operating_mode(hass, entity_id)
        if operating_mode is not None:
            row["operating_mode"] = operating_mode
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
            if operating_mode is not None:
                row["issues"].extend(operating_mode["issues"])
            row["status"] = ("unknown" if "capability_unavailable" in row["issues"]
                             else "review_required" if row["issues"] else "compatible")
        rows.append(row)
    return {"status": "unknown" if room.schedule is not None or not rows or any(r["status"] == "unknown" for r in rows)
            else "review_required" if any(r["issues"] for r in rows) else "compatible",
            "scope": "saved_local_room_targets", "external_program_checked": False,
            "external_program_present": room.schedule is not None,
            "authorizes_actuation": False, "actuators": rows}


@dataclass(frozen=True, slots=True)
class RoomTargetCommand:
    """Already admitted LOCAL command; deadline is on the HA receiver's clock.

    This is not a broker schema or session/freshness proof. The future native
    owner must validate those BEFORE invoking this existing serialized adapter.
    One adapter belongs to one immutable binding and admitted owner lifetime.
    """
    sequence: int
    target_centi_c: int
    deadline: float


@dataclass(frozen=True, slots=True)
class ActuatorServiceReceipt:
    sequence: int
    requested_centi_c: int
    native_target: float
    native_unit: str
    duplicate: bool = False
    status: str = field(default="ha_action_accepted", init=False)
    scope: str = field(default="service_acceptance_only", init=False)
    device_reported: bool = field(default=False, init=False)
    valve_ready: bool = field(default=False, init=False)
    control_qualified: bool = field(default=False, init=False)


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
        self._request = 0
        # Reconstruct only after SOURCE-owner outcome review/requalification.
        # Lease renewal or another target cannot clear an uncertain dispatch.
        self._outcome_unknown = False
        self._binding = _dispatch_binding(hass, entity_id)
        # One latest result plus a lifetime high-water sequence. No Store,
        # dispatch task, retry queue or resetting an original command budget.
        self._command_sequence = 0
        self._command_key = self._command_result = None
        self._command_mode = self._legacy_mode = False

    async def async_apply_command(self, command: RoomTargetCommand) -> ActuatorServiceReceipt:
        """Deduplicate an already admitted command within THIS owner only.

        An exact repeat shares the original outcome; an evicted older command
        is rejected rather than replayed. Cancellation of a waiting duplicate
        cannot cancel a possibly dispatched original action. The normal native
        shadow connection does not invoke this API or create actuation authority.
        """
        if (type(command) is not RoomTargetCommand
                or type(command.sequence) is not int or not 1 <= command.sequence <= 4294967295
                or type(command.target_centi_c) is not int or not 500 <= command.target_centi_c <= 3500
                or type(command.deadline) not in (int, float)):
            raise HomeAssistantError("Invalid local TRV command")
        try:
            finite = math.isfinite(command.deadline)
        except OverflowError:
            finite = False
        if not finite:
            raise HomeAssistantError("Invalid local TRV command deadline")
        if self._legacy_mode:
            raise HomeAssistantError("TRV owner already uses unsequenced actions; rebuild the admitted owner")
        key = (command.sequence, command.target_centi_c, command.deadline)
        if command.sequence < self._command_sequence:
            raise HomeAssistantError("TRV command sequence is older than the admitted high-water mark")
        if command.sequence == self._command_sequence:
            if key != self._command_key:
                raise HomeAssistantError("TRV duplicate command payload changed")
            receipt = await asyncio.shield(self._command_result)
            return replace(receipt, duplicate=True) # Historical acceptance, no IO.
        now = self.hass.loop.time()
        if not now < command.deadline <= now + ACTION_TIMEOUT_SECONDS:
            raise HomeAssistantError("TRV command expired or exceeds original action budget; no command sent")
        self._command_mode = True
        result = self.hass.loop.create_future()
        # The owner also awaits the action directly. Mark an unobserved cached
        # failure retrieved, while preserving it for exact duplicate callers.
        def settled(future):
            if not future.cancelled():
                future.exception()
        result.add_done_callback(settled)
        self._command_sequence, self._command_key, self._command_result = command.sequence, key, result
        try:
            actual, unit = await self._execute_target(command.target_centi_c / 100,
                                                      deadline=command.deadline)
            receipt = ActuatorServiceReceipt(command.sequence, command.target_centi_c, actual, unit)
        except asyncio.CancelledError:
            result.set_exception(HomeAssistantError("TRV command owner cancelled; no automatic retry"))
            raise
        except Exception as error:
            result.set_exception(error)
            raise
        result.set_result(receipt)
        return receipt

    async def async_set_room_target(self, celsius: float) -> float:
        from .v1_model import target_centi
        target_centi(celsius)
        if self._command_mode:
            raise HomeAssistantError("TRV owner requires sequenced commands; unsequenced action refused")
        self._legacy_mode = True
        actual, _unit = await self._execute_target(celsius)
        return actual

    async def _execute_target(self, celsius: float, *, deadline: float | None = None) -> tuple[float, str]:
        from .v1_model import target_centi
        target_centi(celsius)
        self._request += 1
        request = self._request
        if deadline is None:
            deadline = self.hass.loop.time() + ACTION_TIMEOUT_SECONDS
        dispatched = False

        def current():
            if self._outcome_unknown:
                raise HomeAssistantError("TRV previous action outcome unknown; source-owner requalification required")
            if request != self._request:
                raise HomeAssistantError("TRV target superseded before dispatch")
            if self.hass.loop.time() >= deadline:
                raise HomeAssistantError("TRV target expired before dispatch; no command sent")

        try:
            # One original budget includes waiting for this serialized owner.
            # A newer queued request retires older queued targets, without
            # pretending an already dispatched action can be unsent.
            async with asyncio.timeout_at(deadline):
                async with self._lock:
                    current()
                    if not self._qualified or not self._authorize():
                        raise HomeAssistantError("Profile C bench actuation is disabled")
                    if self._binding is None or _dispatch_binding(self.hass, self.entity_id) != self._binding:
                        raise HomeAssistantError("TRV native binding changed; requalification required")
                    capability = target_capability(self.hass, self.hass.states.get(self.entity_id))
                    actual = capability.target(celsius)
                    operating_mode = reported_operating_mode(self.hass, self.entity_id)
                    if not self._authorize():
                        raise HomeAssistantError("Bench authorization expired or invalid target")
                    current_mode = reported_operating_mode(self.hass, self.entity_id)
                    if (operating_mode is None) != (current_mode is None):
                        raise HomeAssistantError("TRV model changed before target dispatch")
                    if current_mode is not None and current_mode["issues"]:
                        raise HomeAssistantError("TV02 local operating mode conflicts with external target")
                    if self._binding is None or _dispatch_binding(self.hass, self.entity_id) != self._binding:
                        raise HomeAssistantError("TRV native binding changed; requalification required")
                    current_capability = target_capability(self.hass, self.hass.states.get(self.entity_id))
                    if current_capability != capability or current_capability.target(celsius) != actual:
                        raise HomeAssistantError("TRV capability changed before target dispatch")
                    current() # Synchronous observers may have consumed the budget.
                    # No await or external callback between final check and dispatch.
                    dispatched = True
                    await self.hass.services.async_call(
                        "climate", "set_temperature",
                        {"entity_id": self.entity_id, "temperature": float(actual)},
                        blocking=True,
                    )
                    # The service yields to HA while the source lease, registry
                    # and device metadata may change. Acceptance belongs only
                    # to the original reviewed owner, never a replacement.
                    # Losing that owner cannot undo a dispatched command.
                    authorized = self._authorize()
                    if not authorized or not self._qualified:
                        raise HomeAssistantError("TRV owner lost during action")
                    if _dispatch_binding(self.hass, self.entity_id) != self._binding:
                        raise HomeAssistantError("TRV native binding changed during action")
                    completed_mode = reported_operating_mode(self.hass, self.entity_id)
                    if ((operating_mode is None) != (completed_mode is None)
                            or completed_mode is not None and completed_mode["issues"]):
                        raise HomeAssistantError("TRV operating mode changed during action")
                    if target_capability(self.hass, self.hass.states.get(self.entity_id)) != capability:
                        raise HomeAssistantError("TRV capability changed during action")
                    if self.hass.loop.time() >= deadline:
                        raise HomeAssistantError("TRV action completed after deadline")
                    # A newer queued target does not erase historical service
                    # acceptance. It still cannot confirm an echo or readiness.
                    return float(actual), capability.unit
        except TimeoutError as err:
            if dispatched:
                self._outcome_unknown = True
                raise HomeAssistantError("TRV action timed out; physical outcome unknown") from err
            raise HomeAssistantError("TRV target expired before dispatch; no command sent") from err
        except asyncio.CancelledError:
            if dispatched:
                self._outcome_unknown = True
            raise
        except Exception as err:
            if dispatched:
                self._outcome_unknown = True
                raise HomeAssistantError("TRV action failed; physical outcome unknown") from err
            raise
