"""DataUpdateCoordinator for BaillConnect integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AuthenticationError,
    BaillConnectApiClient,
    CannotConnect,
    ParsingError,
    RegulationData,
)
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _get_scan_interval(entry: ConfigEntry) -> timedelta:
    """Return the scan interval from options, falling back to the default."""
    seconds = entry.options.get(
        CONF_SCAN_INTERVAL,
        int(DEFAULT_SCAN_INTERVAL.total_seconds()),
    )
    return timedelta(seconds=seconds)


class BaillConnectCoordinator(DataUpdateCoordinator[RegulationData]):
    """Coordinator that polls BaillConnect for regulation data."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        client: BaillConnectApiClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=_get_scan_interval(entry),
        )
        self.client = client

    async def _async_update_data(self) -> RegulationData:
        """Fetch the latest regulation data from BaillConnect."""
        try:
            return await self.client.get_regulation()
        except AuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "BaillConnect authentication failed"
            ) from err
        except (CannotConnect, ParsingError) as err:
            raise UpdateFailed(f"Error fetching BaillConnect data: {err}") from err
