"""Climate platform for BaillConnect integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ThermostatData
from .const import DOMAIN, HVAC_TO_UC_MODE, MAX_TEMP, MIN_TEMP, TEMP_STEP, UC_MODE_TO_HVAC
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)

# Map uc_mode int → HA HVACMode enum
_UC_TO_HA: dict[int, HVACMode] = {
    0: HVACMode.OFF,
    1: HVACMode.HEAT,
    2: HVACMode.COOL,
    3: HVACMode.DRY,
}

_HA_TO_UC: dict[HVACMode, int] = {v: k for k, v in _UC_TO_HA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BaillConnect climate entities from a config entry."""
    coordinator: BaillConnectCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        BaillConnectClimate(coordinator, th.thermostat_id)
        for th in coordinator.data.thermostats
    ]
    async_add_entities(entities)


class BaillConnectClimate(CoordinatorEntity[BaillConnectCoordinator], ClimateEntity):
    """A climate entity representing one BaillConnect thermostat."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.DRY,
    ]

    def __init__(
        self,
        coordinator: BaillConnectCoordinator,
        thermostat_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._thermostat_id = thermostat_id
        self._attr_unique_id = f"bailconnect_{thermostat_id}"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def _thermostat(self) -> ThermostatData | None:
        """Return the thermostat data from the coordinator."""
        if self.coordinator.data is None:
            return None
        for th in self.coordinator.data.thermostats:
            if th.thermostat_id == self._thermostat_id:
                return th
        return None

    @property
    def _regulation(self):
        """Shortcut to the regulation data."""
        return self.coordinator.data

    # ------------------------------------------------------------------
    # Entity properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str | None:
        """Return the thermostat room name."""
        th = self._thermostat
        return th.name if th else None

    @property
    def device_info(self) -> DeviceInfo:
        """Group all thermostats under one device."""
        reg = self._regulation
        return DeviceInfo(
            identifiers={(DOMAIN, str(reg.regulation_id))},
            name="BaillConnect",
            manufacturer="Baillindustrie",
            model="BaillConnect Zoning",
        )

    @property
    def available(self) -> bool:
        """Return True if the thermostat is reachable."""
        th = self._thermostat
        if th is None:
            return False
        return th.is_connected and super().available

    # ------------------------------------------------------------------
    # Climate state
    # ------------------------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current HVAC mode.

        If the thermostat is off locally, report OFF regardless of system mode.
        """
        th = self._thermostat
        if th is None or not th.is_on:
            return HVACMode.OFF
        reg = self._regulation
        if reg is None or not reg.ui_on:
            return HVACMode.OFF
        return _UC_TO_HA.get(reg.uc_mode, HVACMode.OFF)

    @property
    def current_temperature(self) -> float | None:
        """Return the current room temperature."""
        th = self._thermostat
        return th.current_temperature if th else None

    @property
    def target_temperature(self) -> float | None:
        """Return the active setpoint based on current mode and comfort/eco.

        T1 = comfort setpoint, T2 = eco setpoint.
        The active one depends on the thermostat's t1_t2 field.
        """
        th = self._thermostat
        if th is None:
            return None
        reg = self._regulation
        if reg is None:
            return None

        is_cooling = reg.uc_mode == 2  # cool mode
        if is_cooling:
            return th.setpoint_cool_t1 if th.t1_t2 == 1 else th.setpoint_cool_t2
        # heat, dry, or off — use hot setpoints
        return th.setpoint_hot_t1 if th.t1_t2 == 1 else th.setpoint_hot_t2

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        reg = self._regulation
        if reg and reg.uc_mode == 2:
            return reg.uc_cold_min
        return reg.uc_hot_min if reg else MIN_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        reg = self._regulation
        if reg and reg.uc_mode == 2:
            return reg.uc_cold_max
        return reg.uc_hot_max if reg else MAX_TEMP

    # ------------------------------------------------------------------
    # Climate actions
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode (system-wide)."""
        if hvac_mode == HVACMode.OFF:
            # Turn off this thermostat
            await self.coordinator.client.set_thermostat_on(
                self._thermostat_id, False
            )
        else:
            # Ensure thermostat is on
            th = self._thermostat
            if th and not th.is_on:
                await self.coordinator.client.set_thermostat_on(
                    self._thermostat_id, True
                )
            # Set system mode
            uc_mode = _HA_TO_UC.get(hvac_mode)
            if uc_mode is not None:
                await self.coordinator.client.set_regulation_mode(uc_mode)

        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature for this thermostat."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        th = self._thermostat
        reg = self._regulation
        if th is None or reg is None:
            return

        # Determine which setpoint key to update
        is_cooling = reg.uc_mode == 2
        if is_cooling:
            key = "setpoint_cool_t1" if th.t1_t2 == 1 else "setpoint_cool_t2"
        else:
            key = "setpoint_hot_t1" if th.t1_t2 == 1 else "setpoint_hot_t2"

        await self.coordinator.client.set_thermostat_setpoint(
            self._thermostat_id, key, temperature
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn on this thermostat."""
        await self.coordinator.client.set_thermostat_on(
            self._thermostat_id, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off this thermostat."""
        await self.coordinator.client.set_thermostat_on(
            self._thermostat_id, False
        )
        await self.coordinator.async_request_refresh()
