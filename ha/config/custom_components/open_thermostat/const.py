"""Constants for the OpenThermostat room integration."""

from homeassistant.const import Platform

DOMAIN = "open_thermostat"
# Device-registry manufacturer of every OpenThermostat device (metadata only: identifiers stay).
MANUFACTURER = "OpenThermostat"
# Default name of the E32 product device (the same in every language). It sets the
# device's own name only; a name the user gave it in Home Assistant (name_by_user) stays.
E32_DEVICE_NAME = "OpenThermostat E32"
# Long hub names that the project's own test setups (22 Oct 2026) stored as the user's name; never a
# user's choice. Cleared at setup so the device shows E32_DEVICE_NAME again; any other user name stays.
TEST_SETUP_DEVICE_NAMES = frozenset({"E32-regelaar — ketel en diagnose"})
# What older releases stored; renamed once at setup (__init__._rename_old_manufacturer).
OLD_MANUFACTURER = "intuibase"
CONF_TOPIC_PREFIX = "topic_prefix"
# MQTT prefix of a new installation. Existing entries keep their stored prefix
# (older firmware and installations use "ib-therm"); discovery accepts any prefix.
DEFAULT_TOPIC_PREFIX = "openthermostat"
CONF_CREATE_DASHBOARD = "create_dashboard"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.NUMBER, Platform.SENSOR]

# Daily summary and warnings (1.0, daily_summary.py and heating_problem.py). One place for the thresholds.
# A day counts as complete with at least this much observed E32 data; a shorter day is "partial".
SUMMARY_COMPLETE_DAY_HOURS = 20
SUMMARY_DAYS_KEPT = 21
# A burner run shorter than this is a short run (counted per day; the E32's own short-cycling flag is separate).
SUMMARY_SHORT_RUN_MINUTES = 10
# A rise of the room's target by at least this starts a "time to target" measurement ...
SUMMARY_TARGET_STEP_C = 0.5
# ... which ends when the room is within this of the target ...
SUMMARY_TARGET_REACHED_C = 0.2
# ... and counts as on time within this many minutes.
SUMMARY_TARGET_ON_TIME_MINUTES = 120
# After that time, every minute the room is more than this below its target counts as a missed comfort minute.
SUMMARY_MISSED_MARGIN_C = 0.5
# Warning: a room that asks for heat stays more than this below its target for this long.
WARN_ROOM_SLOW_MARGIN_C = 0.5
WARN_ROOM_SLOW_HOURS = 3
# Warning: the E32 is online but Home Assistant has no working session with it for this long.
WARN_SESSION_LOST_MINUTES = 15
