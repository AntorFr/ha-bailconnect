"""Climate platform for BaillConnect integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    PRESET_COMFORT,
    PRESET_ECO,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ThermostatData
from .const import DOMAIN, MAX_TEMP, MIN_TEMP, TEMP_STEP, UC_MODE_COOL
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)


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
    """A climate entity representing one BaillConnect thermostat.

    The HVAC mode (heat/cool/dry/fan) is managed globally on the regulation
    device via a Select entity.  Each thermostat only controls:
      - on / off  (hvac_mode OFF vs AUTO)
      - comfort / eco preset  (t1_t2 = 1 or 2)
      - target temperature for the active setpoint
    """

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.AUTO]
    _attr_preset_modes = [PRESET_COMFORT, PRESET_ECO]

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

    @property
    def _is_cooling(self) -> bool:
        """Return True if the global system is in cool mode."""
        reg = self._regulation
        return reg is not None and reg.uc_mode == UC_MODE_COOL

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
        """Return device info — one device per thermostat."""
        th = self._thermostat
        reg = self._regulation
        return DeviceInfo(
            identifiers={(DOMAIN, f"thermostat_{self._thermostat_id}")},
            name=th.name if th else f"Thermostat {self._thermostat_id}",
            manufacturer="Baillindustrie",
            model="BaillConnect Thermostat",
            via_device=(DOMAIN, str(reg.regulation_id)) if reg else None,
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
        """Return OFF if the thermostat is off, AUTO otherwise."""
        th = self._thermostat
        if th is None or not th.is_on:
            return HVACMode.OFF
        return HVACMode.AUTO

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset (comfort or eco)."""
        th = self._thermostat
        if th is None or not th.is_on:
            return None
        return PRESET_COMFORT if th.t1_t2 == 1 else PRESET_ECO

    @property
    def current_temperature(self) -> float | None:
        """Return the current room temperature."""
        th = self._thermostat
        return th.current_temperature if th else None

    @property
    def target_temperature(self) -> float | None:
        """Return the active setpoint based on global mode and preset.

        Cool mode → setpoint_cool_t1 / t2
        Other modes → setpoint_hot_t1 / t2
        t1_t2=1 → comfort (T1), t1_t2=2 → eco (T2)
        """
        th = self._thermostat
        if th is None:
            return None

        if self._is_cooling:
            return th.setpoint_cool_t1 if th.t1_t2 == 1 else th.setpoint_cool_t2
        return th.setpoint_hot_t1 if th.t1_t2 == 1 else th.setpoint_hot_t2

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        reg = self._regulation
        if reg and self._is_cooling:
            return reg.uc_cold_min
        return reg.uc_hot_min if reg else MIN_TEMP

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        reg = self._regulation
        if reg and self._is_cooling:
            return reg.uc_cold_max
        return reg.uc_hot_max if reg else MAX_TEMP

    # ------------------------------------------------------------------
    # Climate actions
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn the thermostat on (AUTO) or off (OFF)."""
        await self.coordinator.client.set_thermostat_on(
            self._thermostat_id, hvac_mode != HVACMode.OFF
        )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Switch between comfort (T1) and eco (T2) presets."""
        t1_t2 = 1 if preset_mode == PRESET_COMFORT else 2
        await self.coordinator.client.set_thermostat_t1_t2(
            self._thermostat_id, t1_t2
        )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature for the active setpoint."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        th = self._thermostat
        if th is None:
            return

        if self._is_cooling:
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
