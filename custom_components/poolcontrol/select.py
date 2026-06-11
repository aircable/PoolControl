"""Select platform for PoolControl."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DATA_UPDATED, PoolControlTCPClient, get_client
from .core import KEY_CODES

_LOGGER = logging.getLogger(__name__)

FILTER_MODE_OFF = "Off"
FILTER_MODE_HIGH = "High Speed"
FILTER_MODE_LOW = "Low Speed"
FILTER_MODE_OPTIONS = [FILTER_MODE_OFF, FILTER_MODE_HIGH, FILTER_MODE_LOW]
_MODE_ORDER = [FILTER_MODE_OFF, FILTER_MODE_HIGH, FILTER_MODE_LOW]


def _current_filter_mode(client: PoolControlTCPClient) -> str:
    data = client.data
    if not data.online:
        return FILTER_MODE_OFF
    # User-confirmed panel semantics:
    # - FILTER + AUX_1 => Low Speed
    # - FILTER only     => High Speed
    # - otherwise       => Off
    if data.filter_running and data.aux1:
        return FILTER_MODE_LOW
    if data.filter_running:
        return FILTER_MODE_HIGH
    return FILTER_MODE_OFF


async def _wait_for_mode(
    client: PoolControlTCPClient,
    target_mode: str,
    timeout_s: int,
) -> bool:
    end = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < end:
        if _current_filter_mode(client) == target_mode:
            return True
        await asyncio.sleep(2)
    return _current_filter_mode(client) == target_mode


def _next_mode(current_mode: str) -> str:
    idx = _MODE_ORDER.index(current_mode)
    return _MODE_ORDER[(idx + 1) % len(_MODE_ORDER)]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolControl select entities."""
    client = get_client(hass, entry.entry_id)
    async_add_entities([PoolControlFilterModeSelect(client, entry)])


class PoolControlFilterModeSelect(SelectEntity):
    """3-state filter mode control using panel FILTER key sequencing."""

    _attr_should_poll = False

    def __init__(self, client: PoolControlTCPClient, entry: ConfigEntry) -> None:
        self._client = client
        self._lock = asyncio.Lock()
        self._attr_unique_id = f"{entry.entry_id}_select_filter_mode"
        self._attr_name = "PoolControl Filter Mode"
        self._attr_icon = "mdi:pump"

    @property
    def available(self) -> bool:
        return self._client.data.online

    @property
    def current_option(self) -> str | None:
        if not self._client.data.online:
            return None
        return _current_filter_mode(self._client)

    @property
    def options(self) -> list[str]:
        """Only expose valid cyclic choices: current and next."""
        if not self._client.data.online:
            return FILTER_MODE_OPTIONS
        current = _current_filter_mode(self._client)
        nxt = _next_mode(current)
        return [current, nxt]

    async def async_select_option(self, option: str) -> None:
        """Set filter mode by cycling FILTER key and verifying feedback."""
        if option not in FILTER_MODE_OPTIONS:
            return
        if not self._client.data.online:
            return

        async with self._lock:
            start_mode = _current_filter_mode(self._client)
            if option == start_mode:
                return
            if option != _next_mode(start_mode):
                _LOGGER.warning(
                    "Rejected out-of-order filter mode selection: current=%s requested=%s allowed_next=%s",
                    start_mode,
                    option,
                    _next_mode(start_mode),
                )
                return

            async def _press_filter() -> bool:
                return await self.hass.async_add_executor_job(
                    self._client.send_command, KEY_CODES["FILTER"]
                )

            expected_mode = _next_mode(start_mode)
            ok = await _press_filter()
            if not ok:
                _LOGGER.warning("Failed to send FILTER command")
                return
            # High -> Low can take about 3 minutes until AUX1 confirms low speed.
            timeout_s = 190 if expected_mode == FILTER_MODE_LOW else 20
            reached = await _wait_for_mode(self._client, expected_mode, timeout_s=timeout_s)
            if not reached:
                _LOGGER.warning(
                    "FILTER mode transition not confirmed: expected=%s current=%s",
                    expected_mode,
                    _current_filter_mode(self._client),
                )

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, DATA_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
