"""Button platform for PoolControl momentary panel keys."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DATA_UPDATED, PoolControlTCPClient, get_client
from .core import KEY_CODES

_LOGGER = logging.getLogger(__name__)

BUTTON_DEFINITIONS = [
    ("MENU", "Menu", "mdi:menu"),
    ("LEFT", "Left", "mdi:arrow-left-bold"),
    ("RIGHT", "Right", "mdi:arrow-right-bold"),
    ("PLUS", "Plus", "mdi:plus"),
    ("MINUS", "Minus", "mdi:minus"),
    ("POOL_SPA", "Mode", "mdi:pool"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolControl panel key buttons from a config entry."""
    client = get_client(hass, entry.entry_id)
    entities = [
        PoolControlKeyButton(client, entry, key, name, icon)
        for key, name, icon in BUTTON_DEFINITIONS
    ]
    async_add_entities(entities)


class PoolControlKeyButton(ButtonEntity):
    """Momentary key button that sends a panel command frame."""

    _attr_should_poll = False

    def __init__(
        self,
        client: PoolControlTCPClient,
        entry: ConfigEntry,
        key_name: str,
        name: str,
        icon: str,
    ) -> None:
        self._client = client
        self._key_name = key_name
        self._attr_unique_id = f"{entry.entry_id}_button_{key_name.lower()}"
        self._attr_name = f"PoolControl {name}"
        self._attr_icon = icon

    @property
    def available(self) -> bool:
        return self._client.data.online

    async def async_press(self) -> None:
        key_code = KEY_CODES.get(self._key_name, 0)
        if not key_code:
            return
        ok = await self.hass.async_add_executor_job(self._client.send_command, key_code)
        if not ok:
            _LOGGER.warning("Failed to send key command for %s", self._key_name)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, DATA_UPDATED, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

