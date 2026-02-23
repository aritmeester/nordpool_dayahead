"""Nordpool Day-Ahead Prices integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_DELIVERY_AREAS,
    CONF_CURRENCY,
    CONF_ENABLE_KWH,
    CONF_ENABLE_HOURLY,
    CONF_CONSUMER_SETTINGS,
    CONF_CONSUMER_PRICE_ENABLED,
    CONF_ENERGY_TAX,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT,
    DEFAULT_CURRENCY,
    DEFAULT_ENERGY_TAX,
    DEFAULT_SUPPLIER_MARKUP,
    DEFAULT_VAT,
)
from .coordinator import NordpoolCoordinator
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)


def _build_consumer_settings(options: dict, delivery_areas: list[str]) -> dict[str, dict]:
    """Build per-area consumer settings with legacy fallback."""
    legacy_defaults = {
        CONF_ENABLE_KWH: options.get(CONF_ENABLE_KWH, True),
        CONF_ENABLE_HOURLY: options.get(CONF_ENABLE_HOURLY, True),
        CONF_CONSUMER_PRICE_ENABLED: options.get(CONF_CONSUMER_PRICE_ENABLED, True),
        CONF_ENERGY_TAX: options.get(CONF_ENERGY_TAX, DEFAULT_ENERGY_TAX),
        CONF_SUPPLIER_MARKUP: options.get(CONF_SUPPLIER_MARKUP, DEFAULT_SUPPLIER_MARKUP),
        CONF_VAT: options.get(CONF_VAT, DEFAULT_VAT),
    }

    per_area_raw = options.get(CONF_CONSUMER_SETTINGS, {})
    result: dict[str, dict] = {}
    for area in delivery_areas:
        area_data = per_area_raw.get(area, {}) if isinstance(per_area_raw, dict) else {}
        result[area] = {
            CONF_ENABLE_KWH: area_data.get(
                CONF_ENABLE_KWH,
                legacy_defaults[CONF_ENABLE_KWH],
            ),
            CONF_ENABLE_HOURLY: area_data.get(
                CONF_ENABLE_HOURLY,
                legacy_defaults[CONF_ENABLE_HOURLY],
            ),
            CONF_CONSUMER_PRICE_ENABLED: area_data.get(
                CONF_CONSUMER_PRICE_ENABLED,
                legacy_defaults[CONF_CONSUMER_PRICE_ENABLED],
            ),
            CONF_ENERGY_TAX: area_data.get(CONF_ENERGY_TAX, legacy_defaults[CONF_ENERGY_TAX]),
            CONF_SUPPLIER_MARKUP: area_data.get(
                CONF_SUPPLIER_MARKUP,
                legacy_defaults[CONF_SUPPLIER_MARKUP],
            ),
            CONF_VAT: area_data.get(CONF_VAT, legacy_defaults[CONF_VAT]),
        }

    return result


def _area_from_unique_id(unique_id: str | None) -> str | None:
    """Extract area code from unique_id like nordpool_NL_..."""
    if not unique_id or not unique_id.startswith("nordpool_"):
        return None
    parts = unique_id.split("_", 2)
    if len(parts) < 3:
        return None
    return parts[1]


def _expected_unique_ids(options: dict) -> set[str]:
    """Build all entity unique_ids that should exist for current options."""
    delivery_areas: list[str] = options.get(CONF_DELIVERY_AREAS, ["NL"])

    consumer_settings = _build_consumer_settings(options, delivery_areas)
    days = ["today", "tomorrow"]
    stats = ["min", "max", "average"]

    expected: set[str] = set()
    for area in delivery_areas:
        expected.add(f"nordpool_{area}_tomorrow_final")
        expected.add(f"nordpool_{area}_today_api_last_fetch")
        expected.add(f"nordpool_{area}_tomorrow_api_last_fetch")

        area_settings = consumer_settings.get(area, {})
        area_enable_kwh = area_settings.get(CONF_ENABLE_KWH, True)
        area_enable_hourly = area_settings.get(CONF_ENABLE_HOURLY, True)
        area_consumer_enabled = area_settings.get(CONF_CONSUMER_PRICE_ENABLED, True)

        units = ["mwh"] + (["kwh"] if area_enable_kwh else [])
        resolutions = ["quarter"] + (["hour"] if area_enable_hourly else [])
        price_types = ["market"] + (["consumer"] if area_consumer_enabled else [])

        for day in days:
            for price_type in price_types:
                for unit in units:
                    for resolution in resolutions:
                        expected.add(f"nordpool_{area}_{day}_{price_type}_{unit}_{resolution}")
                        for stat in stats:
                            expected.add(
                                f"nordpool_{area}_{day}_{price_type}_{unit}_{resolution}_{stat}"
                            )

    return expected


@callback
def _cleanup_removed_areas(
    hass: HomeAssistant,
    entry: ConfigEntry,
    options: dict,
    selected_areas: set[str],
) -> None:
    """Remove entities/devices for areas that are no longer configured."""
    ent_reg = er.async_get(hass)
    expected = _expected_unique_ids(options)

    for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
        area = _area_from_unique_id(entity_entry.unique_id)
        if area and area not in selected_areas:
            ent_reg.async_remove(entity_entry.entity_id)
            continue
        if entity_entry.unique_id and entity_entry.unique_id.startswith("nordpool_"):
            if entity_entry.unique_id not in expected:
                ent_reg.async_remove(entity_entry.entity_id)

    # Re-read remaining entities to determine which devices are still in use.
    remaining_nordpool_device_ids: set[str] = set()
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity_entry.unique_id and entity_entry.unique_id.startswith("nordpool_"):
            if entity_entry.device_id:
                remaining_nordpool_device_ids.add(entity_entry.device_id)

    dev_reg = dr.async_get(hass)
    for device in list(dr.async_entries_for_config_entry(dev_reg, entry.entry_id)):
        has_nordpool_identifier = any(domain == DOMAIN for domain, _ in device.identifiers)
        if not has_nordpool_identifier:
            continue

        # If no Nord Pool entities are left on this device, remove it.
        if device.id not in remaining_nordpool_device_ids:
            dev_reg.async_remove_device(device.id)
            continue

        keep_device = False
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier in selected_areas:
                keep_device = True
                break
        if keep_device:
            continue

        dev_reg.async_remove_device(device.id)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Nordpool integration (register services once)."""
    hass.data.setdefault(DOMAIN, {})
    async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Nordpool Day-Ahead from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    async_register_services(hass)

    options = {**entry.data, **entry.options}
    delivery_areas: list[str] = options.get(CONF_DELIVERY_AREAS, ["NL"])
    selected_areas = set(delivery_areas)
    currency: str = options.get(CONF_CURRENCY, DEFAULT_CURRENCY)
    consumer_settings = _build_consumer_settings(options, delivery_areas)

    _cleanup_removed_areas(hass, entry, options, selected_areas)

    coordinator = NordpoolCoordinator(
        hass=hass,
        config_entry=entry,
        delivery_areas=delivery_areas,
        currency=currency,
        consumer_settings=consumer_settings,
    )

    # Initial data fetch — raises ConfigEntryNotReady on failure
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload on options change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Unregister services only when last entry is removed
    if not hass.data[DOMAIN]:
        async_unregister_services(hass)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removing Nordpool devices from the UI."""
    del hass
    del config_entry
    return any(domain == DOMAIN for domain, _ in device_entry.identifiers)
