"""Generated EMS table fields in HA: counters, codes, group count and size."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from custom_components.open_thermostat.boiler_fields import (
    CATALOG_BASE, CATALOG_COUNTERS, CATALOG_FIELDS, CATALOG_VERIFIED, GROUPS, GROUPS_V2, MAX_BYTES, PER_GROUP,
    BoilerFieldCache, validate_group)
from custom_components.open_thermostat.v1_boiler_fields import BoilerFieldEntity
from custom_components.open_thermostat.v1_wire import canonical
from test_boiler_fields import packet
from test_modern_metrics import system

NAMES = [f[0] for f in CATALOG_FIELDS]


def catalog_group(group, sampled=1000, raw=None):
    """A firmware-shaped catalog group; raw: {name: value}, others unobserved."""
    fields = []
    for index in range(group * PER_GROUP, min(group * PER_GROUP + PER_GROUP, CATALOG_BASE + len(CATALOG_FIELDS))):
        name, _, _, _, types, _, _ = CATALOG_FIELDS[index - CATALOG_BASE]
        fields.append([index, raw[name], sampled, 0, types[0]] if raw and name in raw
                      else [index, None, None, 0, 0])
    return {"schema": 1, "sampled_at_ms": sampled, "profile": "classic_observed", "fields": fields}


def group_of(name):
    return (CATALOG_BASE + NAMES.index(name)) // PER_GROUP


def test_generated_fields_match_the_one_cpp_table():
    path = Path(__file__).resolve().parents[2] / "scripts/generate_ems_fields.py"
    module_spec = importlib.util.spec_from_file_location("generate_ems_fields", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.generate(check=True)
    assert len(CATALOG_FIELDS) == 36 and GROUPS_V2 == 11
    assert CATALOG_COUNTERS == {"plus_burner_starts", "plus_burner_runtime", "plus_heating_runtime",
                                "plus_dhw_runtime", "plus_dhw_starts", "boiler_uptime"}
    # Appended rows only: earlier field indexes (and HA history) never move.
    assert NAMES[-6:] == ["last_locking_error_code", "last_locking_error_number", "last_blocking_error_code",
                          "last_blocking_error_number", "boiler_uptime", "thermostat_requested_dhw_temperature"]
    # Rows decoded from the owner's tado (0x17) frames; every one is a known field and telegram type.
    assert CATALOG_VERIFIED == {("thermostat_requested_flow_temperature", 0x1A), ("thermostat_requested_burner_power", 0x1A),
                                ("thermostat_requested_pump_modulation", 0x1A), ("thermostat_setpoint", 0xB1),
                                ("thermostat_room_temperature", 0xB1), ("thermostat_requested_dhw_temperature", 0x33)}
    assert all(t in CATALOG_FIELDS[NAMES.index(n)][4] for n, t in CATALOG_VERIFIED)


def test_counters_are_total_increasing_and_codes_render_as_text():
    cache = BoilerFieldCache()
    client = SimpleNamespace(ready=True, boiler_fields_supported=True, boiler_fields=cache, clock=lambda: 10.0)
    raw = {"boiler_uptime": 100000, "last_locking_error_code": (ord("E") << 8) | ord("A"),
           "last_locking_error_number": 227, "plus_burner_starts": 4321}
    for sequence, group in enumerate(sorted({group_of(n) for n in raw}), 1):
        cache.accept(catalog_group(group, raw=raw), group, sequence, 10.0)
    entity = lambda name: BoilerFieldEntity("fixture", client, CATALOG_BASE + NAMES.index(name))
    uptime, code, number, starts = (entity(n) for n in raw)
    assert uptime.native_value == 100000 and uptime.state_class is SensorStateClass.TOTAL_INCREASING
    assert uptime.device_class is SensorDeviceClass.DURATION and uptime.native_unit_of_measurement == "min"
    assert starts.native_value == 4321 and starts.state_class is SensorStateClass.TOTAL_INCREASING
    assert starts.native_unit_of_measurement is None and starts.device_class is None
    assert code.native_value == "EA" and code.state_class is None and code.native_unit_of_measurement is None
    assert number.native_value == 227 and number.state_class is None
    assert code.translation_key == "field_last_locking_error_code" and uptime.translation_key == "field_boiler_uptime"
    # A field newer than the shipped translations keeps an English name from its id.
    untranslated = BoilerFieldEntity("fixture", client, CATALOG_BASE + NAMES.index("boiler_uptime"), frozenset())
    assert untranslated.name == "Boiler uptime"
    # The 69 v1 OEM counters stay unqualified: no statistics.
    assert BoilerFieldEntity("fixture", client, 18).state_class is None


def test_text_fields_reject_non_printable_codes_generically():
    group = group_of("last_blocking_error_code")
    validate_group(catalog_group(group, raw={"last_blocking_error_code": 0x4541}), group)
    with pytest.raises(ValueError):
        validate_group(catalog_group(group, raw={"last_blocking_error_code": 0x457F}), group)


@pytest.mark.asyncio
async def test_largest_catalog_group_fits_the_envelope(hass):
    e, r, c, now = await system(hass)
    largest = 0
    for group in range(GROUPS, GROUPS_V2):
        sampled = 9007199254740991
        values = catalog_group(group, sampled, raw={n: CATALOG_FIELDS[i][6] for i, n in enumerate(NAMES)})
        values["profile"] = "conflicting_families"
        for field in values["fields"]:
            field[4] = max(CATALOG_FIELDS[field[0] - CATALOG_BASE][4])
        validate_group(values, group)
        p = packet(c, group=group)
        p.update(values=values, sequence=4294967295, grant_sequence=4294967295)
        largest = max(largest, len(canonical(p)))
    assert largest < MAX_BYTES
    await r.async_stop()
