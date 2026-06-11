"""Sensor platform for PoolControl."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DATA_UPDATED, DOMAIN, PoolControlTCPClient, get_client

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoolControlSensorEntityDescription(SensorEntityDescription):
    """PoolControl sensor description."""

    key: str
    name: str
SENSOR_TYPES: tuple[PoolControlSensorEntityDescription, ...] = (
    PoolControlSensorEntityDescription(
        key="air_temp",
        name="Air Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PoolControlSensorEntityDescription(
        key="pool_temp",
        name="Pool Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PoolControlSensorEntityDescription(
        key="display_line1",
        name="Panel Line 1",
        icon="mdi:message-text-outline",
    ),
    PoolControlSensorEntityDescription(
        key="display_line2",
        name="Panel Line 2",
        icon="mdi:message-text-outline",
    ),
    PoolControlSensorEntityDescription(
        key="display_raw_hex",
        name="Panel Raw Hex",
        icon="mdi:code-braces",
    ),
    PoolControlSensorEntityDescription(
        key="panel_time",
        name="Panel Time",
        icon="mdi:clock-outline",
    ),
    PoolControlSensorEntityDescription(
        key="panel_day",
        name="Panel Day",
        icon="mdi:calendar-week",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolControl sensors from a config entry."""
    client = get_client(hass, entry.entry_id)

    entities = [
        PoolControlSensor(client, entry, desc) for desc in SENSOR_TYPES
    ]
    async_add_entities(entities)


class PoolControlSensor(SensorEntity):
    """PoolControl sensor entity."""

    entity_description: PoolControlSensorEntityDescription
    _attr_should_poll = False

    def __init__(
        self,
        client: PoolControlTCPClient,
        entry: ConfigEntry,
        description: PoolControlSensorEntityDescription,
    ) -> None:
        self.entity_description = description
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = f"PoolControl {description.name}"

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
        data = self._client.data
        key = self.entity_description.key

        if not data.online:
            self._attr_available = False
            self.async_write_ha_state()
            return

        self._attr_available = True

        if key == "air_temp":
            if data.air_temp is not None:
                self._attr_native_value = data.air_temp
        elif key == "pool_temp":
            if data.pool_temp is not None:
                self._attr_native_value = data.pool_temp
        elif key == "panel_time":
            if data.panel_hour is not None and data.panel_minute is not None:
                self._attr_native_value = (
                    f"{data.panel_hour:02d}:{data.panel_minute:02d}"
                )
            else:
                self._attr_native_value = None
        elif key == "panel_day":
            if data.panel_day:
                self._attr_native_value = data.panel_day
            else:
                self._attr_native_value = None
        elif key == "display_line1":
            self._attr_native_value = data.display_line1
        elif key == "display_line2":
            self._attr_native_value = data.display_line2
        elif key == "display_raw_hex":
            self._attr_native_value = (
                data.display_raw.hex(" ") if data.display_raw is not None else None
            )

        self.async_write_ha_state()
