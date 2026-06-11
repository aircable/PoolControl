"""Binary sensor platform for PoolControl.

Exposes LED states from the PoolControl panel as binary sensors.
This is a key enhancement over the standard HA integration.
"""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DATA_UPDATED, DOMAIN, PoolControlTCPClient, get_client

_LOGGER = logging.getLogger(__name__)

# LED binary sensor definitions: (key, name, device_class)
# Reduced to the indicators used in this installation.
LED_SENSORS = [
    ("led_pool", "Pool Mode", BinarySensorDeviceClass.RUNNING),
    ("led_spa", "Spa Mode", BinarySensorDeviceClass.RUNNING),
    ("led_spillover", "Spillover", BinarySensorDeviceClass.RUNNING),
    ("led_lights", "Lights On", BinarySensorDeviceClass.POWER),
    ("led_aux_2", "High Speed", BinarySensorDeviceClass.POWER),
    ("led_aux_3", "Heat Pump", BinarySensorDeviceClass.HEAT),
    ("led_valve_3", "Valve 3", BinarySensorDeviceClass.OPENING),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolControl LED binary sensors from a config entry."""
    client: PoolControlTCPClient = get_client(hass, entry.entry_id)

    entities = [
        PoolControlLedSensor(client, entry, key, name, device_class)
        for key, name, device_class in LED_SENSORS
    ]
    async_add_entities(entities)


class PoolControlLedSensor(BinarySensorEntity):
    """PoolControl LED state binary sensor."""

    _attr_should_poll = False

    def __init__(
        self,
        client: PoolControlTCPClient,
        entry: ConfigEntry,
        sensor_key: str,
        name: str,
        device_class: BinarySensorDeviceClass | None,
    ) -> None:
        self._client = client
        self._led_name = sensor_key.replace("led_", "").upper()
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_name = f"PoolControl {name}"
        if device_class:
            self._attr_device_class = device_class

    @property
    def available(self) -> bool:
        return self._client.data.online

    @property
    def is_on(self) -> bool | None:
        """Return True if LED is on."""
        data = self._client.data
        if not data.online:
            return None
        return data.leds.get(self._led_name, False)

    @property
    def icon(self) -> str:
        """Return icon based on LED type."""
        if "CHECK_SYSTEM" in self._led_name:
            return "mdi:alert-circle" if self.is_on else "mdi:alert-circle-outline"
        if "HEATER" in self._led_name:
            return "mdi:fire" if self.is_on else "mdi:fire-off"
        if "FILTER" in self._led_name:
            return "mdi:pump" if self.is_on else "mdi:pump-off"
        if "LIGHTS" in self._led_name:
            return "mdi:lightbulb-on" if self.is_on else "mdi:lightbulb-outline"
        if "SPA" in self._led_name:
            return "mdi:hot-tub" if self.is_on else "mdi:hot-tub-outline"
        if "POOL" in self._led_name:
            return "mdi:pool" if self.is_on else "mdi:pool-outline"
        if "VALVE" in self._led_name:
            return "mdi:valve" if self.is_on else "mdi:valve-closed"
        if "AUX" in self._led_name:
            return "mdi:toggle-switch-variant" if self.is_on else "mdi:toggle-switch-variant-off"
        if "SERVICE" in self._led_name:
            return "mdi:wrench" if self.is_on else "mdi:wrench-outline"
        if "SPILLOVER" in self._led_name:
            return "mdi:waves" if self.is_on else "mdi:waves-arrow-left"
        if "SUPER_CHLORINATE" in self._led_name:
            return "mdi:test-tube" if self.is_on else "mdi:test-tube-empty"
        return "mdi:led-on" if self.is_on else "mdi:led-outline"

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, DATA_UPDATED, self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        """Handle data update."""
        self.async_write_ha_state()
