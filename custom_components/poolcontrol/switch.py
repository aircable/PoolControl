"""Switch platform for PoolControl.

Controls PoolControl panel relays and modes via key commands sent over TCP.
Each switch sends a key command to toggle the corresponding panel function.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DATA_UPDATED, DOMAIN, PoolControlTCPClient, get_client
from .core import KEY_CODES

_LOGGER = logging.getLogger(__name__)

# Switch definitions: (key_name, display_name, data_attribute)
SWITCH_DEFINITIONS = [
    ("LIGHTS", "Lights", "led_lights"),
    ("AUX_2", "High Speed", "aux2"),
    ("AUX_3", "Heat Pump", "aux3"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolControl switches from a config entry."""
    client = get_client(hass, entry.entry_id)

    entities = [
        PoolControlSwitch(client, entry, key, name, attr)
        for key, name, attr in SWITCH_DEFINITIONS
    ]
    async_add_entities(entities)


class PoolControlSwitch(SwitchEntity):
    """PoolControl switch entity.

    Sends a key command to the panel to toggle a relay.
    State is tracked from the status frame feedback.
    """

    _attr_should_poll = False

    def __init__(
        self,
        client,
        entry: ConfigEntry,
        switch_key: str,
        name: str,
        data_attr: str,
    ) -> None:
        self._client = client
        self._switch_key = switch_key
        self._data_attr = data_attr
        self._attr_unique_id = f"{entry.entry_id}_switch_{switch_key.lower()}"
        self._attr_name = f"PoolControl {name}"

    @property
    def available(self) -> bool:
        return self._client.data.online

    @property
    def is_on(self) -> bool | None:
        """Return True if switch is on."""
        data = self._client.data
        if not data.online:
            return None
        if self._data_attr.startswith("led_"):
            led_name = self._data_attr.replace("led_", "").upper()
            return data.leds.get(led_name, False)
        return getattr(data, self._data_attr, False)

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on by sending key command."""
        key_code = KEY_CODES.get(self._switch_key, 0)
        if key_code:
            self._client.send_command(key_code)
            _LOGGER.debug("Sent turn_on command for %s (key=0x%04X)", self._switch_key, key_code)

    def turn_off(self, **kwargs: Any) -> None:
        """Turn off by sending key command."""
        key_code = KEY_CODES.get(self._switch_key, 0)
        if key_code:
            self._client.send_command(key_code)
            _LOGGER.debug("Sent turn_off command for %s (key=0x%04X)", self._switch_key, key_code)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, DATA_UPDATED, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Handle data update - refresh state from panel feedback."""
        self.async_write_ha_state()
