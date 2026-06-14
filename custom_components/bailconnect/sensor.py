"""Sensor platform for BaillConnect integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ThermostatData
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

    entities: list[SensorEntity] = [BaillConnectConnectionSensor(coordinator)]

    for th in coordinator.data.thermostats:
        entities.append(BaillConnectThermostatMotorStateSensor(coordinator, th.thermostat_id))
        entities.append(BaillConnectThermostatFanBarsSensor(coordinator, th.thermostat_id))

    async_add_entities(entities)


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


class BaillConnectThermostatSensor(
    CoordinatorEntity[BaillConnectCoordinator], SensorEntity
):
    """Base class for thermostat-related sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BaillConnectCoordinator, thermostat_id: int) -> None:
        super().__init__(coordinator)
        self._thermostat_id = thermostat_id

    @property
    def _thermostat(self) -> ThermostatData | None:
        reg = self.coordinator.data
        if reg is None:
            return None
        for th in reg.thermostats:
            if th.thermostat_id == self._thermostat_id:
                return th
        return None

    @property
    def device_info(self) -> DeviceInfo:
        th = self._thermostat
        reg = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, f"thermostat_{self._thermostat_id}")},
            name=th.name if th else f"Thermostat {self._thermostat_id}",
            manufacturer="Baillindustrie",
            model="BaillConnect Thermostat",
            via_device=(DOMAIN, str(reg.regulation_id)) if reg else None,
        )


class BaillConnectThermostatMotorStateSensor(BaillConnectThermostatSensor):
    """Raw thermostat motor state from BaillConnect."""

    _attr_icon = "mdi:engine"

    def __init__(self, coordinator: BaillConnectCoordinator, thermostat_id: int) -> None:
        super().__init__(coordinator, thermostat_id)
        self._attr_unique_id = f"bailconnect_{thermostat_id}_motor_state"

    @property
    def name(self) -> str:
        return "Motor state"

    @property
    def native_value(self) -> int | None:
        th = self._thermostat
        if th is None:
            return None
        return th.motor_state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        th = self._thermostat
        if th is None:
            return {}
        return {"motor_open_or_opening": th.motor_state in (5, 6)}


class BaillConnectThermostatFanBarsSensor(BaillConnectThermostatSensor):
    """Effective fan bars (0-5) as shown in BaillConnect UI for this thermostat."""

    _attr_icon = "mdi:fan"
    _attr_native_unit_of_measurement = "bars"

    def __init__(self, coordinator: BaillConnectCoordinator, thermostat_id: int) -> None:
        super().__init__(coordinator, thermostat_id)
        self._attr_unique_id = f"bailconnect_{thermostat_id}_fan_bars_active"

    @property
    def name(self) -> str:
        return "Fan bars active"

    @property
    def native_value(self) -> int | None:
        reg = self.coordinator.data
        th = self._thermostat
        if reg is None or th is None:
            return None

        raw_fan = reg.raw.get("ui_fan")
        try:
            fan_level = int(raw_fan)
        except (TypeError, ValueError):
            return None

        if not reg.ui_on or reg.uc_mode == 0 or th.motor_state not in (5, 6):
            return 0
        return max(0, min(5, fan_level))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        reg = self.coordinator.data
        th = self._thermostat
        if reg is None or th is None:
            return {}

        return {
            "ui_fan_raw": reg.raw.get("ui_fan"),
            "regulation_ui_on": reg.ui_on,
            "regulation_uc_mode": reg.uc_mode,
            "motor_state": th.motor_state,
            "motor_open_or_opening": th.motor_state in (5, 6),
        }
