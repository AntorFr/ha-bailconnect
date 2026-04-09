"""Switch platform for BaillConnect integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BaillConnect switch entities from a config entry."""
    coordinator: BaillConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BaillConnectPowerSwitch(coordinator)])


class BaillConnectPowerSwitch(CoordinatorEntity[BaillConnectCoordinator], SwitchEntity):
    """Switch to turn the regulation system on/off."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:power"

    def __init__(self, coordinator: BaillConnectCoordinator) -> None:
        super().__init__(coordinator)
        reg = coordinator.data
        self._attr_unique_id = f"bailconnect_{reg.regulation_id}_power"

    @property
    def name(self) -> str:
        return "Power"

    @property
    def device_info(self) -> DeviceInfo:
        reg = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, str(reg.regulation_id))},
            name="BaillConnect",
            manufacturer="Baillindustrie",
            model="BaillConnect Zoning",
        )

    @property
    def is_on(self) -> bool | None:
        reg = self.coordinator.data
        if reg is None:
            return None
        return reg.ui_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_regulation_on(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_regulation_on(False)
        await self.coordinator.async_request_refresh()
