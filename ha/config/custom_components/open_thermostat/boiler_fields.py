"""Immutable boiler.fields.v1 IDs; source values are read-only, never control evidence."""
CAPABILITY = "boiler.fields.v1"
MAX_BYTES = 2048
PER_GROUP = 10
GROUPS = 7
# name, unit, raw divisor, original source TTL ms, telegram type
FIELDS = (
    ('reported_selected_flow_temperature', 'degC', 100, 30000, 24),
    ('measured_flow_temperature', 'degC', 100, 30000, 24),
    ('measured_return_temperature', 'degC', 100, 30000, 24),
    ('outdoor_temperature', 'degC', 100, 180000, 25),
    ('reported_burner_modulation', '%', 1, 30000, 24),
    ('reported_requested_power_limit', '%', 1, 30000, 24),
    ('pressure', 'bar', 10, 30000, 24),
    ('raw_burner_bit', 'bool', 1, 30000, 24),
    ('raw_pump_bit', 'bool', 1, 30000, 24),
    ('raw_fan_bit', 'bool', 1, 30000, 24),
    ('raw_boiler_state', 'bits', 1, 30000, 24),
    ('heating_active', 'bool', 1, 30000, 24),
    ('dhw_active', 'bool', 1, 30000, 24),
    ('selected_dhw_temperature', 'degC', 100, 600000, 51),
    ('measured_dhw_temperature', 'degC', 100, 30000, 52),
    ('dhw_flow', 'L/min', 10, 30000, 52),
    ('heating_enabled', 'bool', 1, 600000, 22),
    ('dhw_enabled', 'bool', 1, 600000, 51),
    ('reported_burner_starts', 'starts', 1, 180000, 25),
    ('reported_burner_runtime', 'min', 1, 180000, 25),
    ('reported_heating_runtime', 'min', 1, 180000, 25),
    ('reported_heating_starts', 'starts', 1, 180000, 25),
    ('reported_dhw_runtime', 'min', 1, 30000, 52),
    ('reported_dhw_starts', 'starts', 1, 30000, 52),
    ('display_code', 'text', 1, 30000, 24),
    ('service_number', 'code', 1, 30000, 24),
    ('maximum_burner_power', '%', 1, 600000, 22),
    ('pump_run_on', 'min', 1, 600000, 22),
    ('configured_heating_temperature', 'degC', 100, 600000, 22),
    ('reported_dhw_target', 'degC', 100, 30000, 52),
    ('storage_temperature_1', 'degC', 100, 30000, 24),
    ('storage_temperature_2', 'degC', 100, 30000, 24),
    ('ionisation_current', 'uA', 10, 30000, 24),
    ('raw_second_burner_bit', 'bool', 1, 30000, 24),
    ('raw_ignition_bit', 'bool', 1, 30000, 24),
    ('raw_oil_preheat_bit', 'bool', 1, 30000, 24),
    ('raw_dhw_valve_bit', 'bool', 1, 30000, 24),
    ('raw_dhw_circulation_bit', 'bool', 1, 30000, 24),
    ('boiler_temperature', 'degC', 100, 180000, 25),
    ('exhaust_temperature', 'degC', 100, 180000, 25),
    ('hydraulic_switch_temperature', 'degC', 100, 180000, 25),
    ('reported_heating_pump_modulation', '%', 1, 180000, 25),
    ('reported_second_burner_runtime', 'min', 1, 180000, 25),
    ('heating_hysteresis_off', 'K', 1, 600000, 22),
    ('heating_hysteresis_on', 'K', 1, 600000, 22),
    ('minimum_burner_period', 'min', 1, 600000, 22),
    ('pump_modulation_maximum', '%', 1, 600000, 22),
    ('pump_modulation_minimum', '%', 1, 600000, 22),
    ('configured_pump_mode', 'code', 1, 600000, 22),
    ('secondary_heating_hysteresis_off', 'K', 1, 600000, 22),
    ('secondary_heating_hysteresis_on', 'K', 1, 600000, 22),
    ('pump_start_temperature', 'degC', 100, 600000, 22),
    ('dhw_hysteresis_on', 'K', 1, 600000, 51),
    ('dhw_charge_optimisation_enabled', 'bool', 1, 600000, 51),
    ('dhw_flow_temperature_offset', 'K', 1, 600000, 51),
    ('dhw_circulation_enabled', 'bool', 1, 600000, 51),
    ('configured_dhw_circulation_mode', 'code', 1, 600000, 51),
    ('dhw_disinfection_temperature', 'degC', 100, 600000, 51),
    ('configured_dhw_charge_type', 'code', 1, 600000, 51),
    ('configured_dhw_comfort_mode', 'code', 1, 600000, 51),
    ('secondary_dhw_temperature', 'degC', 100, 30000, 52),
    ('solar_dhw_temperature', 'degC', 100, 30000, 52),
    ('reported_dhw_type', 'code', 1, 30000, 52),
    ('raw_dhw_one_time_bit', 'bool', 1, 30000, 52),
    ('raw_dhw_disinfection_bit', 'bool', 1, 30000, 52),
    ('raw_dhw_charging_bit', 'bool', 1, 30000, 52),
    ('raw_dhw_recharging_bit', 'bool', 1, 30000, 52),
    ('raw_dhw_temperature_ok_bit', 'bool', 1, 30000, 52),
    ('raw_dhw_active_bit', 'bool', 1, 30000, 52),
)

QUALITIES = (0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 2, 2, 0, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1)
LIMITS = ((-6000, 13000), (-6000, 13000), (-6000, 13000), (-6000, 13000), (0, 100), (0, 100), (0, 254), (0, 1), (0, 1), (0, 1), (0, 255), (0, 1), (0, 1), (-6000, 13000), (-6000, 13000), (0, 254), (0, 1), (0, 1), (0, 16777214), (0, 16777214), (0, 16777214), (0, 16777214), (0, 16777214), (0, 16777214), (0, 65535), (0, 65534), (0, 100), (0, 16777214), (-6000, 13000), (-6000, 13000), (-6000, 13000), (-6000, 13000), (0, 65534), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1), (-6000, 13000), (-6000, 50000), (-6000, 13000), (0, 100), (0, 16777214), (-128, 254), (-128, 254), (0, 16777214), (0, 100), (0, 100), (0, 65534), (-128, 254), (-128, 254), (-6000, 13000), (-128, 254), (0, 1), (-128, 254), (0, 1), (0, 65534), (-6000, 13000), (0, 65534), (0, 65534), (-6000, 13000), (-6000, 13000), (0, 65534), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1))

def validate_group(value, group):
    def integer(v, lo=0, hi=9007199254740991):
        return type(v) is int and lo <= v <= hi
    if (type(value) is not dict or set(value) != {"schema", "sampled_at_ms", "profile", "fields"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or not integer(value["sampled_at_ms"])
            or value["profile"] not in ("classic_observed", "plus_observed", "unknown", "conflicting_families")
            or not integer(group, 0, GROUPS-1)):
        raise ValueError("boiler group schema")
    fields = value["fields"]
    begin = group * PER_GROUP
    if type(fields) is not list or len(fields) != min(PER_GROUP, len(FIELDS)-begin):
        raise ValueError("boiler group size")
    for index, field in enumerate(fields, begin):
        if (type(field) is not list or len(field) != 5 or not integer(field[0], index, index)
                or not integer(field[3], 0, 2)):
            raise ValueError("boiler field shape")
        _, raw, observed, quality, source = field
        if observed is None:
            if raw is not None or type(source) is not int or source != 0 or quality != 0:
                raise ValueError("unobserved boiler field")
        elif (not integer(observed, 0, value["sampled_at_ms"])
              or quality != QUALITIES[index]
              or not integer(source, FIELDS[index][4], FIELDS[index][4])
              or (raw is not None and not integer(raw, *LIMITS[index]))):
            raise ValueError("boiler field value")
        if index == 24 and raw is not None and not (32 <= raw >> 8 <= 126 and 32 <= raw & 255 <= 126):
            raise ValueError("boiler display code")
    return value


class BoilerFieldCache:
    """One session cache; an unchanged acquisition never gets a new deadline."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.sequence = 0
        self.sampled = -1
        self.profile = "unknown"
        self.invalid = False
        self.records = {}
        self.received = None

    def accept(self, value, group, sequence, now):
        validate_group(value, group)
        if type(sequence) is not int or not 1 <= sequence <= 4294967295:
            raise ValueError("boiler sequence")
        if sequence <= self.sequence:
            return
        if value["sampled_at_ms"] < self.sampled:
            raise ValueError("boiler source clock reversed")
        pending = {}
        for field in value["fields"]:
            index, raw, observed, quality, source = field
            old = self.records.get(index)
            if old is not None and old[0][2] is not None:
                if observed is None or observed < old[0][2]:
                    raise ValueError("boiler acquisition reversed")
                if observed == old[0][2]:
                    if tuple(field) != old[0]:
                        raise ValueError("boiler acquisition changed")
                    # Even a different publication sequence cannot extend the deadline.
                    continue
            deadline = (None if observed is None else
                now + (FIELDS[index][3] - (value["sampled_at_ms"] - observed)) / 1000)
            pending[index] = (tuple(field), deadline)
        if self.profile == "conflicting_families" and value["profile"] != self.profile:
            raise ValueError("boiler family conflict reverted")
        self.records.update(pending)
        self.profile = value["profile"]
        self.sequence = sequence
        self.sampled = value["sampled_at_ms"]
        self.received = now
        self.invalid = False

    def reading(self, index, now):
        record = self.records.get(index)
        if record is None:
            return None
        field, deadline = record
        usable = (not self.invalid and self.profile == "classic_observed"
                  and self.received is not None and 0 <= now-self.received < 20
                  and deadline is not None and now < deadline
                  and field[1] is not None and field[3] != 1)
        return {"raw": field[1], "observed_at_ms": field[2], "quality": field[3],
                "source_type": field[4], "usable": usable, "profile": self.profile}
