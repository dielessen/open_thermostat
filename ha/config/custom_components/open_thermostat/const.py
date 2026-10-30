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
