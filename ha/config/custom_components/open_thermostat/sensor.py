"""Room readings beside OpenThermostat climate entities."""

import json
import logging
import math
from decimal import Decimal

from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass, RestoreSensor
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfInformation, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.unit_conversion import DurationConverter, EnergyConverter

from .room_identity import room_device_name, room_key
from .room_values import room_value
from .metric_snapshot import finite as finite_number
from .const import CONF_TOPIC_PREFIX, DOMAIN
from .program import room_program_name
from .heating import HeatingTracker, DEFINITION
from .metrics_reports import note_legacy_metrics, note_metric_definition_migration

_LOGGER = logging.getLogger(__name__)

METRICS = {
    "temperature": ("currentTemp", SensorDeviceClass.TEMPERATURE, 100, UnitOfTemperature.CELSIUS, "Temperature"),
    "temperature_set": ("tempSet", SensorDeviceClass.TEMPERATURE, 100, UnitOfTemperature.CELSIUS, "Temperature set"),
    "humidity": ("currentHumidity", SensorDeviceClass.HUMIDITY, 100, PERCENTAGE, "Humidity"),
    "battery": ("batteryLevel", SensorDeviceClass.BATTERY, 1, PERCENTAGE, "Battery"),
}

HUB_METRICS = {
    "device_status": {
        "memory_free": ("mem_free", SensorDeviceClass.DATA_SIZE, UnitOfInformation.BYTES, SensorStateClass.MEASUREMENT, "Free memory"),
        "memory_min_free": ("mem_min_free", SensorDeviceClass.DATA_SIZE, UnitOfInformation.BYTES, SensorStateClass.MEASUREMENT, "Minimum free memory"),
        "memory_max_alloc": ("mem_max_alloc", SensorDeviceClass.DATA_SIZE, UnitOfInformation.BYTES, SensorStateClass.MEASUREMENT, "Maximum allocable memory"),
        "rtc_temperature": ("temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, "RTC temperature"),
        "cpu_temperature": ("cpu_temperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, "ESP32 CPU temperature"),
        "uptime": ("uptime", SensorDeviceClass.DURATION, "s", SensorStateClass.TOTAL_INCREASING, "Device uptime"),
    },
    "ems_metrics": {
        "energy": ("totalEnergyUsedKwh", SensorDeviceClass.ENERGY, "kWh", SensorStateClass.TOTAL_INCREASING, "Estimated nominal-modulation energy"),
        "energy_warm_water": ("warmWaterEnergyUsedKwh", SensorDeviceClass.ENERGY, "kWh", SensorStateClass.TOTAL_INCREASING, "Estimated nominal-modulation DHW energy"),
        "energy_heating": ("heatingEnergyUsedKwh", SensorDeviceClass.ENERGY, "kWh", SensorStateClass.TOTAL_INCREASING, "Estimated nominal-modulation space-heating energy"),
        "energy_unattributed": ("unattributedEnergyUsedKwh", SensorDeviceClass.ENERGY, "kWh", SensorStateClass.TOTAL_INCREASING, "Estimated nominal-modulation unattributed energy"),
        "burner_observed_time": ("observedBurnerSeconds", SensorDeviceClass.DURATION, "s", SensorStateClass.TOTAL_INCREASING, "Observed reported-flame time"),
        "warm_water_usage": ("warmWaterUsage", SensorDeviceClass.WATER, "L", SensorStateClass.TOTAL_INCREASING, "Integrated reported warm water volume"),
        "warm_water_avg_flow": ("warmWaterAvgFlow", None, "L/min", SensorStateClass.MEASUREMENT, "Mean warm water flow (observed intervals)"),
        "outdoor_temperature": ("outdoorTemperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, "Outdoor temperature"),
    },
    "ems_status": {
        "boiler_selected_hot_water_temperature": ("selectedWarmWaterTemperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, "Boiler selected hot water temperature"),
        "boiler_selected_flow_temperature": ("selectedFlowTemperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, "Boiler selected flow temperature"),
        "boiler_current_flow_temperature": ("currentFlowTemperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, "Boiler current flow temperature"),
        "boiler_pressure": ("pressure", SensorDeviceClass.PRESSURE, "bar", SensorStateClass.MEASUREMENT, "Boiler pressure"),
        "boiler_burner_power": ("currentBurnerPower", None, PERCENTAGE, SensorStateClass.MEASUREMENT, "Reported burner modulation"),
        "boiler_hot_water_flow": ("warmWaterFlow", None, "L/min", SensorStateClass.MEASUREMENT, "Boiler hot water flow"),
        "boiler_current_hot_water_temperature": ("currentWarmWaterTemperature", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT, "Boiler current hot water temperature"),
        "boiler_protocol_version": ("protocolVersion", None, None, None, "Boiler protocol version"),
        "boiler_service_code": ("serviceCode", None, None, None, "Boiler service code"),
        "boiler_display_code": ("displayCode", None, None, None, "Boiler display code"),
    },
}

VERSIONED_METRICS = frozenset(HUB_METRICS["ems_metrics"]) - {"outdoor_temperature"}

HUB_DIVISORS = {
    "boiler_current_flow_temperature": 10,
    "boiler_pressure": 10,
    "boiler_hot_water_flow": 10,
    "boiler_current_hot_water_temperature": 10,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for room values published by the thermostat."""
    if "v1_runtime" in hass.data.get(DOMAIN,{}).get(entry.entry_id,{}):
        from .product import is_product
        from .v1_boiler_fields import async_setup_boiler_fields
        await async_setup_boiler_fields(hass,entry,async_add_entities)
        from .heating_link import async_setup_heating_link
        await async_setup_heating_link(hass,entry,async_add_entities)
        if is_product(entry):
            from .native_entity_cleanup import retire_legacy_entities
            retire_legacy_entities(hass, entry, entry.data[CONF_TOPIC_PREFIX])
            from .product_telemetry import async_setup_sensors
            await async_setup_sensors(hass, entry, async_add_entities, native_metrics=True)
            from .v1_metrics import async_setup_shadow_metrics
            await async_setup_shadow_metrics(hass, entry, async_add_entities)
            return
        from .device_diagnostics import async_setup_device_diagnostics
        await async_setup_device_diagnostics(hass,entry,async_add_entities)
        from .v1_metrics import async_setup_shadow_metrics
        await async_setup_shadow_metrics(hass,entry,async_add_entities)
        return
    prefix = entry.data[CONF_TOPIC_PREFIX]
    hub = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, prefix), entry.entry_id)
    hub_id = hub.id if hub else None
    sensors: dict[tuple[str, str], RoomMetric] = {}
    programs: dict[str, RoomProgram] = {}
    names: dict[str, RoomName] = {}
    hub_sensors: dict[tuple[str, str], HubMetric] = {}
    heating_sensors: dict[tuple[str, str], RoomHeatingSensor] = {}
    tracker: HeatingTracker = hass.data[DOMAIN][entry.entry_id]["heating_tracker"]
    online = False
    active_keys: set[str] = set()
    dhw_status = DhwStatus(prefix, tracker)
    async_add_entities([dhw_status])

    @callback
    def handle_status(message: ReceiveMessage) -> None:
        nonlocal online
        online = message.payload == "on"
        for (key, _metric), entity in sensors.items():
            entity.set_online(online and key in active_keys)
        for key, entity in programs.items():
            entity.set_online(online and key in active_keys)
        for key, entity in names.items():
            entity.set_online(online and key in active_keys)
        for entity in hub_sensors.values():
            entity.set_online(online)

    @callback
    def handle_hub(message: ReceiveMessage, topic: str) -> None:
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid OpenThermostat status on %s", message.topic)
            return
        if not isinstance(payload, dict):
            return
        added = []
        for metric, (field, _device_class, _unit, _state_class, _name) in HUB_METRICS[topic].items():
            value = payload.get(field)
            key = (topic, metric)
            entity = hub_sensors.get(key)
            if entity is None:
                entity = HubMetric(prefix, topic, metric, entry.entry_id, tracker=tracker)
                hub_sensors[key] = entity
                added.append(entity)
            entity.update_payload(payload, online)
            # Retain an existing legacy registry identity as unavailable, without
            # reusing its Recorder statistic definition. Fresh setups create only v2.
            if topic == "ems_metrics" and metric in VERSIONED_METRICS:
                old_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{prefix}_hub_{metric}")
                old_record = er.async_get(hass).async_get(old_id) if old_id else None
                if old_record is not None and old_record.config_entry_id == entry.entry_id:
                    old_key = (topic, metric + "_legacy")
                    old_entity = hub_sensors.get(old_key)
                    if old_entity is None:
                        old_entity = HubMetric(prefix, topic, metric, entry.entry_id, definition_version=1)
                        hub_sensors[old_key] = old_entity
                        added.append(old_entity)
                    old_entity.update_payload(payload, online)
        if added:
            async_add_entities(added)

    def hub_handler(topic: str):
        @callback
        def handle(message: ReceiveMessage) -> None:
            handle_hub(message, topic)
        return handle

    @callback
    def handle_rooms(message: ReceiveMessage) -> None:
        nonlocal active_keys
        try:
            payload = json.loads(message.payload)
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid OpenThermostat room status on %s", message.topic)
            return
        rooms = payload.get("rooms") if isinstance(payload, dict) else None
        if not isinstance(rooms, list):
            return

        added = []
        for index, room in enumerate(rooms):
            if not isinstance(room, dict):
                continue
            key = room_key(room)
            if key is None:
                continue
            for metric, (field, _device_class, _divisor, _unit, _name) in METRICS.items():
                metric_key = (key, metric)
                entity = sensors.get(metric_key)
                value = room.get(field)
                if entity is None:
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        continue
                    entity = RoomMetric(prefix, index, key, room.get("name"), metric, hub_id)
                    sensors[metric_key] = entity
                    added.append(entity)
                entity.update_value(value, online)
            program_name = room_program_name(room, payload.get("activeProgram"))
            program = programs.get(key)
            if program is None and program_name is not None:
                program = RoomProgram(prefix, index, key, room.get("name"), hub_id)
                programs[key] = program
                added.append(program)
            if program is not None:
                program.update_value(program_name, room.get("temporaryProgramSecondsLeft"), online)
            room_name = room.get("name")
            name_entity = names.get(key)
            if name_entity is None and isinstance(room_name, str) and room_name:
                name_entity = RoomName(prefix, index, key, room_name, hub_id)
                names[key] = name_entity
                added.append(name_entity)
            if name_entity is not None:
                name_entity.update_value(room_name, online)
        active_keys = {key for room in rooms if isinstance(room, dict) if (key := room_key(room)) is not None}
        for (key, _metric), entity in sensors.items():
            if key not in active_keys:
                entity.set_online(False)
        for key, entity in programs.items():
            if key not in active_keys:
                entity.set_online(False)
        for key, entity in names.items():
            if key not in active_keys:
                entity.set_online(False)
        if added:
            async_add_entities(added)

    await mqtt.async_wait_for_mqtt_client(hass)
    entry.async_on_unload(
        await mqtt.async_subscribe(hass, f"{prefix}/status", handle_status)
    )
    entry.async_on_unload(
        await mqtt.async_subscribe(hass, f"{prefix}/room_data", handle_rooms)
    )
    for topic in HUB_METRICS:
        entry.async_on_unload(
            await mqtt.async_subscribe(
                hass, f"{prefix}/{topic}", hub_handler(topic)
            )
        )

    @callback
    def update_heating_sensors() -> None:
        dhw_status.update_from_tracker()
        for entity in hub_sensors.values():
            if entity._observation_field:
                entity.update_from_tracker()
        added = []
        for key, room in tracker.rooms.items():
            for metric, entity_class in (
                ("radiator_heating_time", RoomHeatingTime),
                ("radiator_estimated_energy", RoomEstimatedEnergy),
                ("radiator_estimated_power", RoomEstimatedPower),
            ):
                entity_key = (key, metric)
                entity = heating_sensors.get(entity_key)
                if entity is None:
                    entity = entity_class(prefix, room.index, key, room.name, hub_id, tracker)
                    heating_sensors[entity_key] = entity
                    added.append(entity)
                entity.update_from_tracker()
                # Keep an actually existing old statistic identity non-numeric;
                # never seed the changed model from unqualified old totals.
                old_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{prefix}_room_{key}_{metric}")
                old = er.async_get(hass).async_get(old_id) if old_id else None
                if old is not None and old.config_entry_id == entry.entry_id:
                    legacy_key = (key, metric + "_legacy")
                    if legacy_key not in heating_sensors:
                        legacy = entity_class(prefix, room.index, key, room.name, hub_id, tracker, legacy=True)
                        heating_sensors[legacy_key] = legacy
                        added.append(legacy)
                    heating_sensors[legacy_key].update_from_tracker()
        if added:
            async_add_entities(added)

    entry.async_on_unload(tracker.async_add_listener(update_heating_sensors))


class RoomMetric(SensorEntity):
    """A room temperature, humidity, or battery reading."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, prefix: str, index: int, key: str, room_name: str | None, metric: str, hub_id: str | None = None) -> None:
        field, device_class, divisor, unit, display_name = METRICS[metric]
        self._field = field
        self._divisor = divisor
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_name = display_name
        self._attr_unique_id = f"{prefix}_room_{key}_{metric}"
        name = room_device_name(room_name, index)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{prefix}_room_{key}")},
            name=name,
            manufacturer="intuibase",
            model="OpenThermostat room",
            via_device_id=hub_id,
        )
        self._attr_available = False

    def set_online(self, online: bool) -> None:
        """Update availability from the thermostat's MQTT status."""
        self._attr_available = online
        if self.entity_id is not None:
            self.async_write_ha_state()

    def update_value(self, value: object, online: bool) -> None:
        """Apply a raw sensor value."""
        self._attr_native_value = room_value(self._field, value)
        self._attr_available = online
        if self.entity_id is not None:
            self.async_write_ha_state()


class RoomHeatingSensor(RestoreSensor):
    """Base class for a calculated room-heating sensor."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        prefix: str,
        index: int,
        key: str,
        room_name: str | None,
        hub_id: str | None,
        tracker: HeatingTracker,
        metric: str,
        *, legacy: bool = False,
    ) -> None:
        self._legacy_compat = legacy
        self._key = key
        self._tracker = tracker
        self._attr_unique_id = f"{prefix}_room_{key}_{metric}" + ("" if legacy else "_v2")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{prefix}_room_{key}")},
            name=room_device_name(room_name, index),
            manufacturer="intuibase",
            model="OpenThermostat room",
            via_device_id=hub_id,
        )
        self._attr_available = False
        self._attr_name = ("Legacy history: " if legacy else "") + {
            "radiator_heating_time": "Qualified request / reported CH time (model v2)",
            "radiator_estimated_energy": "Modeled radiator energy (v2, not metered)",
            "radiator_estimated_power": "Modeled radiator output (v2, not metered)",
        }[metric]
        self._attr_extra_state_attributes = {
            "definition": DEFINITION if not legacy else "legacy_unqualified_unavailable",
            "not_a_heat_meter": True, "not_delivery_or_flow_proof": True,
            "ems_source_ttl_seconds": 30, "room_snapshot_ttl_seconds": 45,
            "room_temperature_ttl_seconds": 300,
            "return_drop_assumption_c": 10, "radiator_exponent": 1.3,
            "historical_compatibility": "isolated_v2_no_backfill",
            "transport_delay": "unmeasured_not_control_freshness_proof",
        }
        if legacy:
            self._attr_state_class = None
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._legacy_compat:
            from .metrics_reports import note_room_definition_migration
            note_room_definition_migration(self.hass, self._tracker.entry.entry_id)

    async def _async_restored_total(self, converter, unit, maximum):
        """Restore native value/unit only; never mistake display Wh/s for kWh/h.

        No display fallback: missing or invalid native extra data is unknown.
        This source definition was not deployed, so there is no certified v2
        display-only history to import. Old unversioned totals stay isolated.
        """
        if self._legacy_compat:
            return None
        try:
            data = await self.async_get_last_sensor_data()
            if data is None or not isinstance(data.native_unit_of_measurement, str):
                return None
            if data.native_unit_of_measurement not in converter.VALID_UNITS:
                return None
            if type(data.native_value) not in (int, float, Decimal):
                return None
            value = float(data.native_value)
            if not math.isfinite(value) or value < 0:
                return None
            value = converter.convert(value, data.native_unit_of_measurement, unit)
            return value if math.isfinite(value) and 0 <= value <= maximum else None
        except (ValueError, TypeError, KeyError, ArithmeticError):
            return None

    def update_from_tracker(self) -> None:
        previous = (self.available, self.native_value)
        self._update_value()
        self._attr_available = not self._legacy_compat and self._tracker.estimate_available(self._key)
        if isinstance(self, (RoomEstimatedPower, RoomEstimatedEnergy)):
            self._attr_available &= self._tracker.estimated_power(self._key) is not None
        if self._legacy_compat:
            self._attr_native_value = None
        if self.entity_id is not None and previous != (self.available, self.native_value):
            self.async_write_ha_state()

    def _update_value(self) -> None:
        raise NotImplementedError


class RoomHeatingTime(RoomHeatingSensor):
    """Qualified room request coinciding with reported CH, not delivered heat."""

    _attr_translation_key = "radiator_heating_time"
    _attr_suggested_display_precision = 4
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "h"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:timer-outline"

    def __init__(self, *args, legacy=False) -> None:
        super().__init__(*args, "radiator_heating_time", legacy=legacy)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (seconds := await self._async_restored_total(DurationConverter, "s", 1e12)) is not None:
            self._tracker.restore_totals(self._key, seconds=seconds)
        self.update_from_tracker()

    def _update_value(self) -> None:
        room = self._tracker.rooms.get(self._key)
        self._attr_native_value = room.heating_seconds / 3600 if room else None


class RoomEstimatedEnergy(RoomHeatingSensor):
    """Estimated cumulative radiator energy for one room."""

    _attr_translation_key = "estimated_radiator_energy"
    _attr_suggested_display_precision = 5
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:radiator"

    def __init__(self, *args, legacy=False) -> None:
        super().__init__(*args, "radiator_estimated_energy", legacy=legacy)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (energy := await self._async_restored_total(EnergyConverter, "kWh", 1e9)) is not None:
            self._tracker.restore_totals(self._key, energy=energy)
        self.update_from_tracker()

    def _update_value(self) -> None:
        room = self._tracker.rooms.get(self._key)
        self._attr_native_value = room.estimated_energy_kwh if room else None


class RoomEstimatedPower(RoomHeatingSensor):
    """Current estimated heat output of the room's radiators."""

    _attr_translation_key = "estimated_radiator_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = "W"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:radiator"

    def __init__(self, *args, legacy=False) -> None:
        super().__init__(*args, "radiator_estimated_power", legacy=legacy)

    def _update_value(self) -> None:
        power = self._tracker.estimated_power(self._key)
        self._attr_native_value = round(power, 1) if power is not None else None


class RoomProgram(SensorEntity):
    """Human-readable program currently applied to a room."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Program"

    def __init__(self, prefix: str, index: int, key: str, room_name: str | None, hub_id: str | None = None) -> None:
        self._attr_unique_id = f"{prefix}_room_{key}_program"
        name = room_device_name(room_name, index)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{prefix}_room_{key}")},
            name=name,
            manufacturer="intuibase",
            model="OpenThermostat room",
            via_device_id=hub_id,
        )
        self._attr_available = False

    def set_online(self, online: bool) -> None:
        """Update availability from the thermostat's MQTT status."""
        self._attr_available = online
        if self.entity_id is not None:
            self.async_write_ha_state()

    def update_value(self, name: str | None, remaining: object, online: bool) -> None:
        """Apply a program name and optional override countdown."""
        self._attr_native_value = name
        self._attr_extra_state_attributes = (
            {"temporary_seconds_left": remaining}
            if isinstance(remaining, (int, float)) and remaining > 0
            else {}
        )
        self._attr_available = online
        if self.entity_id is not None:
            self.async_write_ha_state()


class DhwStatus(SensorEntity):
    """Read-only observed-family capability/quality, not a water-heater control."""
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_name = "Domestic hot water capabilities"
    _attr_supported_features = 0
    _metric = "dhw_capabilities"

    def __init__(self, prefix, tracker):
        self._tracker = tracker
        self._attr_unique_id = f"{prefix}_hub_dhw_capabilities"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})
        self._attr_native_value = "unknown"
        self._attr_extra_state_attributes = {}

    def update_from_tracker(self):
        value = self._tracker.dhw_snapshot()
        previous = (self.native_value, self.extra_state_attributes)
        self._attr_native_value = value["status"]
        self._attr_extra_state_attributes = value
        if self.entity_id is not None and previous != (self.native_value,self.extra_state_attributes):
            self.async_write_ha_state()


class HubMetric(SensorEntity):
    """A reading published by the thermostat's main device."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, prefix: str, topic: str, metric: str, entry_id: str | None = None, *, definition_version: int = 2, tracker: HeatingTracker | None = None) -> None:
        _field, device_class, unit, state_class, name = HUB_METRICS[topic][metric]
        self._tracker = tracker
        self._observation_field = {
            "boiler_selected_flow_temperature":"selected_flow_c",
            "boiler_current_flow_temperature":"supply_c",
            "boiler_burner_power":"modulation_pct",
        }.get(metric) if topic == "ems_status" else None
        if topic == "device_status":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_name = name
        versioned = topic == "ems_metrics" and metric in VERSIONED_METRICS
        if versioned and definition_version not in (1, 2):
            raise ValueError("Unsupported metric definition")
        self._legacy_compat = versioned and definition_version == 1
        self._versioned = versioned
        self._attr_unique_id = f"{prefix}_hub_{metric}" + ("_v2" if versioned and not self._legacy_compat else "")
        if versioned:
            self._attr_name = ("Legacy history: " + name if self._legacy_compat else name + " (definition v2)")
        if self._legacy_compat:
            self._attr_state_class = None
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._divisor = HUB_DIVISORS.get(metric, 1)
        self._topic, self._metric = topic, metric
        self._entry_id = entry_id
        self._legacy_schema_seen = False
        if topic == "ems_metrics" and metric.startswith("energy"):
            self._attr_extra_state_attributes = {
                "measurement_kind": "estimate_nominal_modulation", "counter_scope": "boot",
                "not_a_gas_meter": True,
            }
        elif topic == "ems_metrics" and metric == "warm_water_usage":
            self._attr_extra_state_attributes = {
                "measurement_kind": "integrated_reported_flow", "counter_scope": "boot",
            }
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})
        self._attr_available = False

    def set_online(self, online: bool) -> None:
        if self._tracker is not None and self._observation_field:
            self.update_from_tracker()
            return
        self._attr_available = online and not self._legacy_compat
        if self.entity_id is not None:
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._legacy_compat and self._entry_id:
            note_metric_definition_migration(self.hass, self._entry_id)
        if self._legacy_schema_seen and self._entry_id:
            note_legacy_metrics(self.hass, self._entry_id)

    def update_from_tracker(self) -> None:
        if self._tracker is None or not self._observation_field:
            return
        previous = (self.available, self.native_value)
        self._attr_native_value = self._tracker.boiler_reading(self._observation_field)
        self._attr_available = self._tracker.ems_available()
        self._attr_extra_state_attributes = {
            "quality":"reported_plus_not_delivery_proof", "source_ttl_seconds":30,
            "not_controller_command":True, "physical_validation":False,
            "historic_freshness":"not_rewritten_or_certified",
        }
        if self.entity_id is not None and previous != (self.available, self.native_value):
            self.async_write_ha_state()

    def update_payload(self, payload: dict, online: bool) -> None:
        if self._tracker is not None and self._observation_field:
            self.update_from_tracker()
            return
        field = HUB_METRICS[self._topic][self._metric][0]
        value = payload.get(field)
        if self._versioned:
            # Old numerical fields must NEVER feed the new statistic IDs.
            old_value = payload.get(field)
            if finite_number(old_value):
                self._legacy_schema_seen = True
                if self.hass is not None and self._entry_id:
                    note_legacy_metrics(self.hass, self._entry_id)
            value = payload.get(field + "V2")
            if (self._legacy_compat or type(payload.get("metricsSchema")) is not int
                    or payload["metricsSchema"] != 2
                    or payload.get("counterDefinition") != "observation-total-v2"):
                value = None
            if isinstance(value, (int, float)) and value < 0:
                value = None
        if self._topic == "ems_metrics":
            self._attr_extra_state_attributes = {
                **(self.extra_state_attributes or {}),
                "definition_version": (1 if self._legacy_compat else 2) if self._versioned else None,
                "historical_compatibility": ("legacy_unavailable" if self._legacy_compat else "isolated_v2_no_backfill") if self._versioned else "unchanged_outdoor",
                "metrics_schema": 2 if type(payload.get("metricsSchema")) is int and payload["metricsSchema"] == 2 else None,
                "protocol_scope": "plus" if payload.get("protocolScope") == "plus" else "unverified",
            }
        if self._metric == "boiler_burner_power" and isinstance(value, (int, float)) and not 0 <= value <= 100:
            value = None
        self.update_value(value, online)

    def update_value(self, value: object, online: bool) -> None:
        if self._legacy_compat:
            value = None
        self._attr_native_value = (
            value / self._divisor
            if finite_number(value)
            else value if self._metric in {"boiler_display_code", "boiler_service_code", "boiler_protocol_version"}
                and isinstance(value, str) and value else None
        )
        self._attr_available = online and not self._legacy_compat
        if self.entity_id is not None:
            self.async_write_ha_state()


class RoomName(SensorEntity):
    """The room name published by the thermostat."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = "Room name"

    def __init__(self, prefix: str, index: int, key: str, room_name: str, hub_id: str | None) -> None:
        self._attr_unique_id = f"{prefix}_room_{key}_name"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{prefix}_room_{key}")},
            name=room_device_name(room_name, index),
            manufacturer="intuibase",
            model="OpenThermostat room",
            via_device_id=hub_id,
        )
        self._attr_available = False

    def set_online(self, online: bool) -> None:
        self._attr_available = online
        if self.entity_id is not None:
            self.async_write_ha_state()

    def update_value(self, value: object, online: bool) -> None:
        self._attr_native_value = value if isinstance(value, str) and value else None
        self._attr_available = online
        if self.entity_id is not None:
            self.async_write_ha_state()
