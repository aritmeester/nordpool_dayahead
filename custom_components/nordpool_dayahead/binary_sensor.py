"""Binary sensor platform for Nordpool Day-Ahead — tomorrow price status."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DELIVERY_AREAS,
)
from .coordinator import NordpoolCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors from config entry."""
    coordinator: NordpoolCoordinator = hass.data[DOMAIN][entry.entry_id]
    options = {**entry.data, **entry.options}
    delivery_areas: list[str] = options.get(CONF_DELIVERY_AREAS, ["NL"])

    entities = [
        NordpoolTomorrowStatusSensor(coordinator, area)
        for area in delivery_areas
    ]
    async_add_entities(entities)


class NordpoolTomorrowStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """
    Binary sensor indicating whether tomorrow's prices are final.

    ON  = prices are Final
    OFF = prices are Preliminary or not yet available
    """

    def __init__(self, coordinator: NordpoolCoordinator, area: str) -> None:
        super().__init__(coordinator)
        self._area = area
        self._attr_has_entity_name = True
        self._attr_translation_key = "tomorrow_prices_final"
        self._attr_unique_id = f"nordpool_{area}_tomorrow_final"

    @property
    def is_on(self) -> bool:
        """True when tomorrow's prices are confirmed final."""
        data = self.coordinator.get_tomorrow(self._area)
        if data is None:
            return False
        return data.is_final

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.get_tomorrow(self._area)
        if data is None:
            return {
                "status": "unavailable",
                "delivery_date": None,
            }
        return {
            "status": data.status,
            "delivery_date": data.delivery_date,
            "area": self._area,
        }

    @property
    def icon(self) -> str:
        data = self.coordinator.get_tomorrow(self._area)
        if data is None:
            return "mdi:timer-sand-empty"
        if data.is_final:
            return "mdi:timer-sand-complete"
        return "mdi:timer-sand"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._area)},
            "name": f"Nord Pool {self._area}",
            "manufacturer": "Nord Pool Group",
            "model": "Day-Ahead Market",
        }
