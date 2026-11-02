"""The E32 device's backup entities: "Back up E32 settings now" and "Last E32 backup".

Both exist only with a stored E32 connection (e32_backup.backups). The sensor
shows the time of the last good backup; its attributes are the number of
backups kept and the size of the newest. Never a passphrase, secret or address.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_TOPIC_PREFIX, DOMAIN
from .controller_link import BackupRejected, ControllerLinkError
from .e32_backup import backups, last_backup

# Why a backup started with the button failed, as the exception's translation key.
PRESS_ERRORS = {
    "controller_unreachable": "e32_backup_unreachable",
    "controller_auth_failed": "e32_backup_password",
    "controller_session_capacity": "e32_session_capacity",
    "controller_try_again_later": "e32_try_again_later",
    "controller_update_required": "e32_backup_update_required",
    "busy": "e32_backup_busy",
}


def press_error(err):
    code = err.error if isinstance(err, BackupRejected) else str(err)
    return PRESS_ERRORS.get(code, "e32_backup_failed")


def _options(hass, entry):
    from .installation_group import ensure_installation_group
    return {"config_subentry_id": ensure_installation_group(hass, entry)}


class _BackupEntity:
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, manager, suffix):
        prefix = entry.data[CONF_TOPIC_PREFIX]
        self._manager = manager
        self._attr_unique_id = f"{prefix}_{suffix}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, prefix)})

    async def async_added_to_hass(self):
        self.async_on_remove(self._manager.add_listener(self.async_write_ha_state))


class E32BackupButton(_BackupEntity, ButtonEntity):
    _attr_translation_key = "e32_backup_now"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry, manager):
        super().__init__(entry, manager, "e32_backup_now")

    async def async_press(self):
        try:
            await self._manager.async_backup("manual")
        except ControllerLinkError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key=press_error(err)) from None


class E32LastBackupSensor(_BackupEntity, SensorEntity):
    _attr_translation_key = "e32_last_backup"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry, manager):
        super().__init__(entry, manager, "e32_last_backup")

    @property
    def native_value(self):
        return last_backup(self._manager)[0]

    @property
    def extra_state_attributes(self):
        return last_backup(self._manager)[1]


async def async_setup_buttons(hass, entry, async_add_entities):
    from .product import is_product
    manager = backups(hass, entry)
    if manager is None or not is_product(entry):
        return
    async_add_entities([E32BackupButton(entry, manager)], **_options(hass, entry))


async def async_setup_sensors(hass, entry, async_add_entities):
    from .product import is_product
    manager = backups(hass, entry)
    if manager is None or not is_product(entry):
        return
    async_add_entities([E32LastBackupSensor(entry, manager)], **_options(hass, entry))
