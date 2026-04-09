"""The BaillConnect integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .api import BaillConnectApiClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import BaillConnectCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.SELECT, Platform.SWITCH]

type BaillConnectConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: BaillConnectConfigEntry) -> bool:
    """Set up BaillConnect from a config entry."""
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    client = BaillConnectApiClient(
        session=session,
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
    )

    coordinator = BaillConnectCoordinator(hass, client, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: BaillConnectConfigEntry
) -> None:
    """Handle options update — adjust the polling interval."""
    coordinator: BaillConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    seconds = entry.options.get(
        CONF_SCAN_INTERVAL,
        int(DEFAULT_SCAN_INTERVAL.total_seconds()),
    )
    coordinator.update_interval = timedelta(seconds=seconds)
    _LOGGER.info("Scan interval updated to %s seconds", seconds)
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: BaillConnectConfigEntry) -> bool:
    """Unload a BaillConnect config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: BaillConnectCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.close()
    return unload_ok
