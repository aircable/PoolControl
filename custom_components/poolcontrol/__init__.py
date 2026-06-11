"""PoolControl - Enhanced PoolControl pool controller integration for Home Assistant.

Provides proper sensor, switch, and LED binary_sensor support for PoolControl
pool panels connected via ESP32 TCP-to-RS485 bridge.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .core import PoolControlTCPClient

_LOGGER = logging.getLogger(__name__)

DOMAIN = "poolcontrol"
DATA_UPDATED = f"{DOMAIN}_data_updated"

PLATFORMS = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
]

DEFAULT_PORT = 3333


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PoolControl from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)

    client = PoolControlTCPClient(
        host=host,
        port=port,
        data_callback=lambda d: _data_updated(hass),
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    # Start TCP client in executor to avoid blocking
    await hass.async_add_executor_job(client.start)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("PoolControl setup complete for %s:%d", host, port)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    client = hass.data[DOMAIN].pop(entry.entry_id)
    await hass.async_add_executor_job(client.stop)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    client = get_client(hass, entry.entry_id)
    await hass.async_add_executor_job(client.restart)
    _data_updated(hass)


def _data_updated(hass: HomeAssistant) -> None:
    """Signal that new data is available."""
    try:
        hass.loop.call_soon_threadsafe(async_dispatcher_send, hass, DATA_UPDATED)
    except RuntimeError:
        pass  # Event loop closed


def get_client(hass: HomeAssistant, entry_id: str) -> PoolControlTCPClient:
    """Get the TCP client for a config entry."""
    return hass.data[DOMAIN][entry_id]
