"""Immutable boiler.fields.v1 IDs; source values are read-only, never control evidence."""
import json
import math

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

# BEGIN GENERATED CATALOG FIELDS (scripts/generate_ems_fields.py)
# name, unit, raw divisor, source TTL ms, telegram types, raw minimum, raw maximum
CATALOG_FIELDS = (
    ('thermostat_requested_flow_temperature', 'degC', 1, 180000, (26,), 0, 100),
    ('thermostat_requested_burner_power', '%', 1, 180000, (26,), 0, 100),
    ('thermostat_requested_pump_modulation', '%', 1, 180000, (26,), 0, 100),
    ('maintenance_message', 'code', 1, 600000, (28,), 0, 254),
    ('thermostat_setpoint', 'degC', 2, 180000, (177, 145, 174, 65, 62), 0, 70),
    ('thermostat_room_temperature', 'degC', 10, 180000, (177, 145, 174, 65, 62, 677), -300, 600),
    ('thermostat_target_flow_temperature', 'degC', 1, 180000, (62, 677), 0, 100),
    ('plus_selected_flow_temperature', 'degC', 1, 180000, (228,), 0, 100),
    ('plus_flow_temperature', 'degC', 10, 180000, (228,), 0, 1300),
    ('plus_requested_burner_power', '%', 1, 180000, (228,), 0, 100),
    ('plus_burner_modulation', '%', 1, 180000, (228,), 0, 100),
    ('plus_burner_on', 'bool', 1, 180000, (228,), 0, 1),
    ('plus_dhw_valve', 'bool', 1, 180000, (228,), 0, 1),
    ('plus_return_temperature', 'degC', 10, 180000, (228,), 1, 1300),
    ('plus_flame_current', 'uA', 10, 180000, (228,), 0, 1000),
    ('plus_pressure', 'bar', 10, 180000, (228,), 1, 40),
    ('plus_exhaust_temperature', 'degC', 10, 180000, (228,), 0, 5000),
    ('plus_heating_pump', 'bool', 1, 180000, (229,), 0, 1),
    ('plus_burner_starts', 'starts', 1, 180000, (229,), 0, 16777214),
    ('plus_burner_runtime', 'min', 1, 180000, (229,), 0, 16777214),
    ('plus_heating_runtime', 'min', 1, 180000, (229,), 0, 16777214),
    ('plus_heating_pump_modulation', '%', 1, 180000, (229,), 0, 100),
    ('plus_dhw_target', 'degC', 1, 180000, (233,), 0, 100),
    ('plus_dhw_temperature', 'degC', 10, 180000, (233,), 0, 1000),
    ('plus_dhw_flow', 'L/min', 10, 180000, (233,), 0, 250),
    ('plus_dhw_runtime', 'min', 1, 180000, (233,), 0, 16777214),
    ('plus_dhw_starts', 'starts', 1, 180000, (233,), 0, 16777214),
    ('plus_dhw_selected_temperature', 'degC', 1, 600000, (234,), 0, 100),
    ('plus_heating_temperature', 'degC', 1, 600000, (230,), 0, 100),
    ('plus_maximum_burner_power', '%', 1, 600000, (230,), 0, 100),
    ('last_locking_error_code', 'text', 1, 86400000, (16,), 8224, 32382),
    ('last_locking_error_number', 'code', 1, 86400000, (16,), 0, 9999),
    ('last_blocking_error_code', 'text', 1, 86400000, (17,), 8224, 32382),
    ('last_blocking_error_number', 'code', 1, 86400000, (17,), 0, 9999),
    ('boiler_uptime', 'min', 1, 600000, (20,), 0, 16777214),
    ('thermostat_requested_dhw_temperature', 'degC', 1, 180000, (51,), 0, 100),
)
# EMS 3-byte lifetime counters (EntityKind::u24): Home Assistant total_increasing
CATALOG_COUNTERS = frozenset({'plus_burner_starts', 'plus_burner_runtime', 'plus_heating_runtime', 'plus_dhw_runtime', 'plus_dhw_starts', 'boiler_uptime'})
# (name, telegram type) rows decoded from real frames with plausible values
CATALOG_VERIFIED = frozenset({('thermostat_requested_flow_temperature', 26), ('thermostat_requested_burner_power', 26), ('thermostat_requested_pump_modulation', 26), ('thermostat_setpoint', 177), ('thermostat_room_temperature', 177), ('thermostat_requested_dhw_temperature', 51)})
# END GENERATED CATALOG FIELDS

# boiler.fields.v2: the same route with whole groups 7.. holding the EMS entity
# catalog from index 70 (src/EMS/EmsEntityTable.h is the single source).
CAPABILITY_V2 = "boiler.fields.v2"
CATALOG_BASE = 70
GROUPS_V2 = GROUPS + (len(CATALOG_FIELDS) + PER_GROUP - 1) // PER_GROUP
INDEXES = tuple(range(len(FIELDS))) + tuple(range(CATALOG_BASE, CATALOG_BASE + len(CATALOG_FIELDS)))
INDEX_SET = frozenset(INDEXES)
# Retained state (E32 beta.19): valid while the E32 is online and its heartbeat
# (every 60 s) is current; three missed heartbeats make it unavailable.
STATE_STALE_SECONDS = 3 * 60 + 15


def spec(index):
    """(name, unit, raw divisor, source TTL ms) of a v1 or catalog field."""
    if index < len(FIELDS):
        return FIELDS[index][:4]
    return CATALOG_FIELDS[index - CATALOG_BASE][:4]


def quality(index):
    return QUALITIES[index] if index < len(FIELDS) else 0


# One physical value, two wire families (F28): each EMS+ catalog field and the
# Classic field the same boiler quantity arrives in (EMS-ESP decodes both
# telegrams into one value: 0xE4/0x18 monitor, 0xE5/0x19 counters, 0xE9/0x34
# hot water, 0xE6/0x16 and 0xEA/0x33 settings). Home Assistant shows one
# entity per pair and names the source family in an attribute. Catalog fields
# not listed here (thermostat rows, records, uptime) have no Classic twin.
PLUS_CLASSIC_TWINS = {
    'plus_selected_flow_temperature': 'reported_selected_flow_temperature',
    'plus_flow_temperature': 'measured_flow_temperature',
    'plus_requested_burner_power': 'reported_requested_power_limit',
    'plus_burner_modulation': 'reported_burner_modulation',
    'plus_burner_on': 'raw_burner_bit',
    'plus_dhw_valve': 'raw_dhw_valve_bit',
    'plus_return_temperature': 'measured_return_temperature',
    'plus_flame_current': 'ionisation_current',
    'plus_pressure': 'pressure',
    'plus_exhaust_temperature': 'exhaust_temperature',
    'plus_heating_pump': 'raw_pump_bit',
    'plus_burner_starts': 'reported_burner_starts',
    'plus_burner_runtime': 'reported_burner_runtime',
    'plus_heating_runtime': 'reported_heating_runtime',
    'plus_heating_pump_modulation': 'reported_heating_pump_modulation',
    'plus_dhw_target': 'reported_dhw_target',
    'plus_dhw_temperature': 'measured_dhw_temperature',
    'plus_dhw_flow': 'dhw_flow',
    'plus_dhw_runtime': 'reported_dhw_runtime',
    'plus_dhw_starts': 'reported_dhw_starts',
    'plus_dhw_selected_temperature': 'selected_dhw_temperature',
    'plus_heating_temperature': 'configured_heating_temperature',
    'plus_maximum_burner_power': 'maximum_burner_power',
}
INDEX_BY_NAME = {spec(index)[0]: index for index in INDEXES}
_TWIN = {}
for _plus, _classic in PLUS_CLASSIC_TWINS.items():
    if _plus in INDEX_BY_NAME and _classic in INDEX_BY_NAME:
        _TWIN[INDEX_BY_NAME[_plus]] = INDEX_BY_NAME[_classic]
        _TWIN[INDEX_BY_NAME[_classic]] = INDEX_BY_NAME[_plus]


def concept(index):
    """The field indexes that carry the same physical value as index.

    Preference order: reported (quality 0) fields before the unreliable
    Classic raw bits and OEM counters, then Classic before EMS+. A field
    without a twin is its own concept.
    """
    if index not in _TWIN:
        return (index,)
    return tuple(sorted((index, _TWIN[index]), key=lambda i: (quality(i) == 1, i >= CATALOG_BASE)))


# fw/config/boiler_profile (retained, E32 beta.19, src/EMS/BoilerProfile.h): which
# fields THIS boiler has, learned on the E32 from its own reports. A field in none
# of the lists is still "unknown" (too few observations). "supported" includes a
# not-fitted field the owner chose to show anyway on the E32 boiler page.
PROFILE_TOPIC = "fw/config/boiler_profile"
PROFILE_MAX_BYTES = 1024
PROFILE_LISTS = ("supported", "not_fitted", "not_reported")


def validate_profile(value):
    """{index: state} of a boiler profile; indexes this HA does not know are ignored."""
    if (type(value) is not dict or value.get("schema") != 1 or type(value.get("boiler")) is not dict
            or not set(PROFILE_LISTS) <= set(value)):
        raise ValueError("boiler profile schema")
    states = {}
    for key in PROFILE_LISTS:
        items = value[key]
        if type(items) is not list or len(items) > 256:
            raise ValueError("boiler profile list")
        for index in items:
            if not _integer(index, 0, 255) or index in states:
                raise ValueError("boiler profile index")
            states[index] = key
    return {index: state for index, state in states.items() if index in INDEX_SET}


def combined_state(states):
    """One physical value (F28 concept) from the profile states of its fields:
    supported when any field is, unknown while any may still turn out, not
    fitted when one is and none is supported, else not reported."""
    for state in ("supported", "unknown", "not_fitted"):
        if state in states:
            return state
    return "not_reported"


def _integer(v, lo=0, hi=9007199254740991):
    return type(v) is int and lo <= v <= hi


def validate_field(field, index, sampled):
    """One [index, raw, observed_ms, quality, source type] row of the group or state wire."""
    integer = _integer
    if (type(field) is not list or len(field) != 5 or not integer(field[0], index, index)
            or not integer(field[3], 0, 2)):
        raise ValueError("boiler field shape")
    _, raw, observed, quality, source = field
    if observed is None:
        if raw is not None or type(source) is not int or source != 0 or quality != 0:
            raise ValueError("unobserved boiler field")
    elif index >= CATALOG_BASE:
        _, _, _, _, types, low, high = CATALOG_FIELDS[index - CATALOG_BASE]
        if (not integer(observed, 0, sampled) or quality != 0
                or type(source) is not int or source not in types
                or (raw is not None and not integer(raw, low, high))):
            raise ValueError("boiler catalog field value")
    elif (not integer(observed, 0, sampled)
          or quality != QUALITIES[index]
          or not integer(source, FIELDS[index][4], FIELDS[index][4])
          or (raw is not None and not integer(raw, *LIMITS[index]))):
        raise ValueError("boiler field value")
    if spec(index)[1] == "text" and raw is not None and not (32 <= raw >> 8 <= 126 and 32 <= raw & 255 <= 126):
        raise ValueError("boiler display code")


def _validate_values(value):
    if (type(value) is not dict or set(value) != {"schema", "sampled_at_ms", "profile", "fields"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or not _integer(value["sampled_at_ms"])
            or value["profile"] not in ("classic_observed", "plus_observed", "unknown", "conflicting_families")
            or type(value["fields"]) is not list):
        raise ValueError("boiler group schema")


def validate_rows(value):
    """``fw/state/boiler``: the same values with any known field indexes, each once."""
    _validate_values(value)
    seen = set()
    if not 1 <= len(value["fields"]) <= 32:
        raise ValueError("boiler state size")
    for field in value["fields"]:
        index = field[0] if type(field) is list and field else None
        if type(index) is not int or index not in INDEX_SET or index in seen:
            raise ValueError("boiler state index")
        seen.add(index)
        validate_field(field, index, value["sampled_at_ms"])
    return value


def validate_group(value, group):
    def integer(v, lo=0, hi=9007199254740991):
        return type(v) is int and lo <= v <= hi
    if (type(value) is not dict or set(value) != {"schema", "sampled_at_ms", "profile", "fields"}
            or type(value["schema"]) is not int or value["schema"] != 1
            or not integer(value["sampled_at_ms"])
            or value["profile"] not in ("classic_observed", "plus_observed", "unknown", "conflicting_families")
            or not integer(group, 0, GROUPS_V2-1)):
        raise ValueError("boiler group schema")
    fields = value["fields"]
    begin = group * PER_GROUP
    end = len(FIELDS) if group < GROUPS else CATALOG_BASE + len(CATALOG_FIELDS)
    if type(fields) is not list or len(fields) != min(PER_GROUP, end-begin):
        raise ValueError("boiler group size")
    for index, field in enumerate(fields, begin):
        if (type(field) is not list or len(field) != 5 or not integer(field[0], index, index)
                or not integer(field[3], 0, 2)):
            raise ValueError("boiler field shape")
        _, raw, observed, quality, source = field
        if observed is None:
            if raw is not None or type(source) is not int or source != 0 or quality != 0:
                raise ValueError("unobserved boiler field")
        elif index >= CATALOG_BASE:
            _, _, _, _, types, low, high = CATALOG_FIELDS[index - CATALOG_BASE]
            if (not integer(observed, 0, value["sampled_at_ms"]) or quality != 0
                    or type(source) is not int or source not in types
                    or (raw is not None and not integer(raw, low, high))):
                raise ValueError("boiler catalog field value")
        elif (not integer(observed, 0, value["sampled_at_ms"])
              or quality != QUALITIES[index]
              or not integer(source, FIELDS[index][4], FIELDS[index][4])
              or (raw is not None and not integer(raw, *LIMITS[index]))):
            raise ValueError("boiler field value")
        if spec(index)[1] == "text" and raw is not None and not (32 <= raw >> 8 <= 126 and 32 <= raw & 255 <= 126):
            raise ValueError("boiler display code")
    return value


class BoilerFieldCache:
    """One session cache; an unchanged acquisition never gets a new deadline.

    Since E32 beta.19 the fields arrive as retained state instead
    (``accept_state``): not bound to a shadow session, the E32 itself sends a
    value that outlived its lifetime as null, and a value stays usable while
    the E32 is alive (``heartbeat``/``availability``), not for its own TTL.
    """
    def __init__(self):
        self.state_mode = False
        # The boiler profile is retained configuration, not session data: no reset clears it.
        self.field_profile = None   # {index: state}; None: no profile (older firmware)
        self.profile_boiler = None
        self.profile_settled = False
        self.profile_sequence = 0
        self.reset()

    def reset_session(self):
        """A shadow session ended: only the session cache goes; the retained state stays."""
        if not self.state_mode:
            self.reset()

    def reset(self):
        self.state_mode = False
        self.online = None
        self.heartbeat_at = None
        self.first_state_at = None
        self.sampled_by_index = {}
        self.sequence = 0
        self.sampled = -1
        self.profile = "unknown"
        self.invalid = False
        self.records = {}
        self.received = None
        self.retired = {}

    def accept_profile(self, raw):
        """A retained ``fw/config/boiler_profile``; empty clears it. False: invalid, ignored."""
        if raw in ("", b"", None):
            changed = self.field_profile is not None
            self.field_profile, self.profile_boiler, self.profile_settled = None, None, False
        else:
            try:
                if not isinstance(raw, str) or len(raw) > PROFILE_MAX_BYTES:
                    raise ValueError("boiler profile bytes")
                value = json.loads(raw)
                states = validate_profile(value)
            except (ValueError, TypeError):
                return False
            settled = value.get("settled") is True
            changed = (states, value["boiler"], settled) != (self.field_profile, self.profile_boiler, self.profile_settled)
            self.field_profile, self.profile_boiler, self.profile_settled = states, value["boiler"], settled
        if changed:
            self.profile_sequence += 1
        return True

    def field_state(self, index):
        """This boiler's profile state of one field: supported, not_fitted, not_reported,
        unknown; None without a profile."""
        if self.field_profile is None:
            return None
        return self.field_profile.get(index, "unknown")

    def concept_state(self, members):
        """The profile state of one physical value (its F28 members); None without a profile."""
        if self.field_profile is None:
            return None
        return combined_state({self.field_state(index) for index in members})

    def invalidate(self):
        # A later valid GROUP cannot restore old permission for OTHER fields.
        # Keep acquisition fences separate from global stream availability.
        self.invalid = True
        for index, (field, _) in self.records.items():
            if field[2] is not None:
                self.retired[index] = max(self.retired.get(index, -1), field[2])

    def alive(self, now):
        """Retained state: online and heard (from the first state until the first heartbeat)."""
        if self.online is False:
            return False
        since = self.heartbeat_at if self.heartbeat_at is not None else self.first_state_at
        return since is not None and 0 <= now - since <= STATE_STALE_SECONDS

    def heartbeat(self, now, uptime_s=None):
        """A live fw/heartbeat; an uptime below what was seen means the E32 restarted."""
        if (type(uptime_s) is int and self.sampled_by_index
                and uptime_s * 1000 + 60000 < max(self.sampled_by_index.values())):
            self.records, self.sampled_by_index = {}, {}
        self.heartbeat_at, self.online = now, True

    def availability(self, online, now):
        self.online = online
        if online and self.heartbeat_at is None:
            self.heartbeat_at = now

    def accept_state(self, value, group, now):
        """A retained ``fw/state/boiler_fields/<g>`` (group) or ``fw/state/boiler`` (group None)."""
        if group is None:
            validate_rows(value)
        else:
            validate_group(value, group)
        if not self.state_mode:
            self.reset()
            self.state_mode = True
        sampled = value["sampled_at_ms"]
        for field in value["fields"]:
            index = field[0]
            if sampled < self.sampled_by_index.get(index, -1):
                continue  # a newer value of this field came on the other topic
            self.records[index] = (tuple(field), math.inf if field[2] is not None else None)
            self.sampled_by_index[index] = sampled
        self.profile = value["profile"]
        self.sampled = max(self.sampled, sampled)
        self.received = now
        self.invalid = False
        self.sequence += 1  # the entities write their state when this changes
        if self.first_state_at is None:
            self.first_state_at = now

    def accept(self, value, group, sequence, now):
        validate_group(value, group)
        if type(sequence) is not int or not 1 <= sequence <= 4294967295:
            raise ValueError("boiler sequence")
        if sequence <= self.sequence:
            return
        if self.received is not None and now < self.received:
            raise ValueError("boiler local clock reversed")
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
                        # Firmware may withdraw a conflicting acquisition as
                        # null. This only restricts, preserving its old deadline.
                        if raw is None and old[0][1] is not None:
                            pending[index] = (tuple(field), old[1])
                            continue
                        raise ValueError("boiler acquisition changed")
                    # Even a different publication sequence cannot extend the deadline.
                    continue
            deadline = (None if observed is None else
                now + (spec(index)[3] - (value["sampled_at_ms"] - observed)) / 1000)
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
        # The 69 v1 fields are Classic telegrams; catalog fields name their own family.
        family = self.profile == "classic_observed" or index >= CATALOG_BASE
        stream = (self.alive(now) if self.state_mode else
                  self.received is not None and 0 <= now-self.received < 20)
        usable = (not self.invalid and family and stream
                  and deadline is not None and now < deadline
                  and field[1] is not None and field[3] != 1
                  and field[2] > self.retired.get(index, -1))
        # Diagnostics preserve why a value is absent; they grant no authority.
        state = ("unknown" if field[2] is None else "invalid" if field[1] is None
                 else "stale" if deadline is None or now >= deadline else "valid")
        reason = ("invalid_packet" if self.invalid else
                  "protocol_unqualified" if not family else
                  "stream_unavailable" if not stream else
                  "not_observed" if field[2] is None else
                  "invalid_value" if field[1] is None else
                  "source_expired" if deadline is None or now >= deadline else
                  "unreliable" if field[3] == 1 else
                  "source_retired" if field[2] <= self.retired.get(index, -1) else "ready")
        return {"raw": field[1], "observed_at_ms": field[2], "quality": field[3],
                "source_type": field[4], "usable": usable, "profile": self.profile,
                "measurement_state": state, "availability_reason": reason}


    def diagnostic_snapshot(self, now):
        """Bounded public cache evidence, never a new measurement or permission."""
        clock_valid = (type(now) in (int, float) and math.isfinite(now) and now >= 0
                       and (self.received is None or now >= self.received))
        fields = {}
        for index in INDEXES:
            if index >= CATALOG_BASE and index not in self.records:
                continue  # catalog fields appear once a v2 session sent them
            name, unit, divisor, ttl = spec(index)
            value = self.reading(index, now) if clock_valid else None
            record = self.records.get(index)
            age = None
            if clock_valid and record is not None and record[1] is not None:
                # The original deadline survives repeated publications/groups.
                elapsed = ttl + (now-record[1])*1000
                if math.isfinite(elapsed):
                    age = max(0, math.ceil(elapsed))
            fields[name] = {
                "raw": value["raw"] if value else None,
                "unit": unit, "raw_divisor": divisor, "source_ttl_ms": ttl,
                "measurement_state": value["measurement_state"] if value else "unknown",
                "availability_reason": ("local_clock_invalid" if not clock_valid else
                                        value["availability_reason"] if value else "not_received"),
                "source_type": value["source_type"] if value else None,
                "source_observed_at_ms": value["observed_at_ms"] if value else None,
                "quality": value["quality"] if value else None,
                "estimated_source_age_ms": age,
                "source_usable": bool(value and value["usable"]),
            }
        received_age = None
        if clock_valid and self.received is not None:
            elapsed = (now-self.received)*1000
            if math.isfinite(elapsed):
                received_age = math.ceil(elapsed)
        return {"schema": 1, "control_qualified": False,
                "scope": "current_native_session_cache_only",
                "source_clock": "firmware_boot_monotonic_ms",
                "age_basis": "firmware_snapshot_plus_local_elapsed; network transit unmeasured",
                "local_clock_valid": clock_valid,
                "profile": self.profile, "sequence": self.sequence,
                "source_snapshot_at_ms": self.sampled if self.sampled >= 0 else None,
                "snapshot_received_age_ms": received_age, "fields": fields}
