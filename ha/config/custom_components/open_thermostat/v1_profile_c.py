"""Initial room-setpoint actuator adapter, locked out of all normal shadow runs.

Only explicit future bench wiring may inject an authorization callback AND
qualified_profile=True. Neither has a GUI option in this candidate.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_HALF_UP
import math
from collections.abc import Callable

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

ACTION_TIMEOUT_SECONDS = 10.0

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
            state = self.hass.states.get(self.entity_id)
            if state is None or state.state in ("unknown", "unavailable"):
                raise HomeAssistantError("TRV unavailable")
            attrs = state.attributes
            features = attrs.get("supported_features", 0)
            if type(features) is not int or not features & 1:
                raise HomeAssistantError("TRV has no target-temperature capability")
            unit = attrs.get("unit_of_measurement", self.hass.config.units.temperature_unit)
            native = celsius if unit == "°C" else celsius * 9 / 5 + 32 if unit == "°F" else None
            values = [attrs.get("min_temp"), attrs.get("max_temp"), attrs.get("target_temp_step")]
            if native is None or any(isinstance(x, bool) or not isinstance(x, (int, float))
                                     or not math.isfinite(x) for x in values):
                raise HomeAssistantError("TRV capability bounds unverified")
            low, high, step = (Decimal(str(x)) for x in values)
            if step <= 0 or low >= high or not low <= Decimal(str(native)) <= high:
                raise HomeAssistantError("TRV target outside verified bounds")
            actual = low + ((Decimal(str(native)) - low) / step).quantize(
                Decimal(1), rounding=ROUND_HALF_UP) * step
            if not low <= actual <= high or not self._authorize():
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
