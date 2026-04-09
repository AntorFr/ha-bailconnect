"""Select platform for BaillConnect integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HVAC_TO_UC_MODE, UC_MODE_TO_HVAC
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)

# Options displayed in the select (excluding "off" — handled by the switch)
MODE_OPTIONS = ["heat", "cool", "dry"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BaillConnect select entities from a config entry."""
    coordinator: BaillConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BaillConnectModeSelect(coordinator)])


class BaillConnectModeSelect(CoordinatorEntity[BaillConnectCoordinator], SelectEntity):
    """Select entity to change the regulation HVAC mode."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:hvac"
    _attr_options = MODE_OPTIONS

    def __init__(self, coordinator: BaillConnectCoordinator) -> None:
        super().__init__(coordinator)
        reg = coordinator.data
        self._attr_unique_id = f"bailconnect_{reg.regulation_id}_mode_select"

    @property
    def name(self) -> str:
        return "Mode"

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
    def current_option(self) -> str | None:
        reg = self.coordinator.data
        if reg is None:
            return None
        return UC_MODE_TO_HVAC.get(reg.uc_mode, "heat")

    async def async_select_option(self, option: str) -> None:
        uc_mode = HVAC_TO_UC_MODE.get(option)
        if uc_mode is None:
            return
        await self.coordinator.client.set_regulation_mode(uc_mode)
        await self.coordinator.async_request_refresh()
