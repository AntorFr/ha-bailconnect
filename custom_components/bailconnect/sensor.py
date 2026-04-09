"""Sensor platform for BaillConnect integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
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
    """Set up BaillConnect sensor entities from a config entry."""
    coordinator: BaillConnectCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([BaillConnectConnectionSensor(coordinator)])


class BaillConnectRegulationEntity(CoordinatorEntity[BaillConnectCoordinator], SensorEntity):
    """Base entity for the regulation device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BaillConnectCoordinator) -> None:
        super().__init__(coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the regulation (central unit)."""
        reg = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, str(reg.regulation_id))},
            name="BaillConnect",
            manufacturer="Baillindustrie",
            model="BaillConnect Zoning",
        )


class BaillConnectConnectionSensor(BaillConnectRegulationEntity):
    """Sensor showing the regulation connection status."""

    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator: BaillConnectCoordinator) -> None:
        super().__init__(coordinator)
        reg = coordinator.data
        self._attr_unique_id = f"bailconnect_{reg.regulation_id}_connected"

    @property
    def name(self) -> str:
        return "Connection"

    @property
    def native_value(self) -> str | None:
        reg = self.coordinator.data
        if reg is None:
            return None
        return "connected" if reg.is_connected else "disconnected"
