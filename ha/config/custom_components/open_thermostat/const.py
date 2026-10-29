"""Constants for the OpenThermostat room integration."""

from homeassistant.const import Platform

DOMAIN = "open_thermostat"
# Device-registry manufacturer of every OpenThermostat device (metadata only: identifiers stay).
MANUFACTURER = "OpenThermostat"
# What older releases stored; renamed once at setup (__init__._rename_old_manufacturer).
OLD_MANUFACTURER = "intuibase"
CONF_TOPIC_PREFIX = "topic_prefix"
# MQTT prefix of a new installation. Existing entries keep their stored prefix
# (older firmware and installations use "ib-therm"); discovery accepts any prefix.
DEFAULT_TOPIC_PREFIX = "openthermostat"
CONF_CREATE_DASHBOARD = "create_dashboard"
PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.NUMBER, Platform.SENSOR]
