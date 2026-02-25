"""Sensor platform for Nordpool Day-Ahead prices."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DELIVERY_AREAS,
    CONF_CURRENCY,
    CONF_ENABLE_KWH,
    CONF_ENABLE_HOURLY,
    CONF_CONSUMER_PRICE_ENABLED,
    CONF_ENERGY_TAX,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT,
)
from .coordinator import NordpoolCoordinator, NordpoolData, _next_quarter_boundary
from .price_utils import build_price_rows, mwh_to_kwh, consumer_price_kwh

_LOGGER = logging.getLogger(__name__)
UTC = timezone.utc
LOCAL_TZ = ZoneInfo("Europe/Amsterdam")


_NAME_TOKEN_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "en": {
        "day": {"today": "", "tomorrow": "Tomorrow "},
        "price_type": {"market": "Market", "consumer": "Consumer"},
        "resolution": {"quarter": "Quarter-hour", "hour": "Hourly"},
        "unit": {"mwh": "MWh", "kwh": "kWh"},
        "stat": {"min": "Min", "max": "Max", "average": "Average"},
    },
    "nl": {
        "day": {"today": "", "tomorrow": "Morgen "},
        "price_type": {"market": "Marktprijs", "consumer": "Consumentenprijs"},
        "resolution": {"quarter": "Kwartier", "hour": "Uur"},
        "unit": {"mwh": "MWh", "kwh": "kWh"},
        "stat": {"min": "Min", "max": "Max", "average": "Gemiddelde"},
    },
}


def _localize_name_token(language: str, token_type: str, value: str) -> str:
    labels = _NAME_TOKEN_LABELS.get(language, _NAME_TOKEN_LABELS["en"])
    return labels.get(token_type, {}).get(value, value)


def _currency_unit_prefix(currency: str) -> str:
    return "€" if currency.upper() == "EUR" else currency


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from config entry."""
    coordinator: NordpoolCoordinator = hass.data[DOMAIN][entry.entry_id]
    options = {**entry.data, **entry.options}

    delivery_areas: list[str] = options.get(CONF_DELIVERY_AREAS, ["NL"])
    currency: str = options.get(CONF_CURRENCY, "EUR")

    entities: list[SensorEntity] = []

    for area in delivery_areas:
        area_consumer = coordinator.get_consumer_settings(area)
        enable_kwh = area_consumer.get(CONF_ENABLE_KWH, True)
        enable_hourly = area_consumer.get(CONF_ENABLE_HOURLY, True)
        consumer_enabled = area_consumer.get(CONF_CONSUMER_PRICE_ENABLED, True)
        energy_tax = area_consumer.get(CONF_ENERGY_TAX, 0.0)
        supplier_markup = area_consumer.get(CONF_SUPPLIER_MARKUP, 0.0)
        vat = area_consumer.get(CONF_VAT, 0.0)

        price_kwargs = dict(
            currency=currency,
            enable_kwh=enable_kwh,
            consumer_enabled=consumer_enabled,
            energy_tax=energy_tax,
            supplier_markup=supplier_markup,
            vat=vat,
        )

        price_configs = _build_price_configs(enable_kwh, enable_hourly, consumer_enabled)

        for day in ("today", "tomorrow"):
            entities.append(
                NordpoolApiDiagnosticsSensor(
                    coordinator=coordinator,
                    area=area,
                    day=day,
                )
            )

            # Current price sensors
            for cfg in price_configs:
                entities.append(
                    NordpoolCurrentPriceSensor(
                        coordinator=coordinator,
                        area=area,
                        day=day,
                        price_type=cfg["price_type"],
                        unit_type=cfg["unit_type"],
                        resolution=cfg["resolution"],
                        **price_kwargs,
                    )
                )

            # Stat sensors (min / max / avg) — disabled by default
            for stat in ("min", "max", "average"):
                stat_resolutions = (
                    ["quarter"]
                    if stat == "average"
                    else (["quarter"] + (["hour"] if enable_hourly else []))
                )
                for resolution in stat_resolutions:
                    for price_type in (["market"] + (["consumer"] if consumer_enabled else [])):
                        unit_types = ["kwh"] if price_type == "consumer" else (["mwh"] + (["kwh"] if enable_kwh else []))
                        for unit_type in unit_types:
                            entities.append(
                                NordpoolStatSensor(
                                    coordinator=coordinator,
                                    area=area,
                                    day=day,
                                    stat=stat,
                                    price_type=price_type,
                                    unit_type=unit_type,
                                    resolution=resolution,
                                    **price_kwargs,
                                )
                            )

    expected_unique_ids = {
        entity.unique_id
        for entity in entities
        if entity.unique_id is not None
    }

    ent_reg = er.async_get(hass)
    for entity_entry in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
        if entity_entry.domain != "sensor":
            continue
        unique_id = entity_entry.unique_id
        if not unique_id or not unique_id.startswith("nordpool_"):
            continue
        if unique_id not in expected_unique_ids:
            ent_reg.async_remove(entity_entry.entity_id)

    async_add_entities(entities)


def _build_price_configs(
    enable_kwh: bool,
    enable_hourly: bool,
    consumer_enabled: bool,
) -> list[dict]:
    configs = []
    price_types = ["market"] + (["consumer"] if consumer_enabled else [])
    resolutions = ["quarter"] + (["hour"] if enable_hourly else [])

    for pt in price_types:
        unit_types = ["kwh"] if pt == "consumer" else (["mwh"] + (["kwh"] if enable_kwh else []))
        for ut in unit_types:
            for res in resolutions:
                configs.append({"price_type": pt, "unit_type": ut, "resolution": res})
    return configs


def _apply_conversion(
    mwh_value: float | None,
    price_type: str,
    unit_type: str,
    energy_tax: float,
    supplier_markup: float,
    vat: float,
) -> float | None:
    """Convert a raw MWh market price to the requested price_type and unit_type."""
    if mwh_value is None:
        return None
    if price_type == "market":
        return mwh_value if unit_type == "mwh" else mwh_to_kwh(mwh_value)
    return consumer_price_kwh(mwh_to_kwh(mwh_value), energy_tax, supplier_markup, vat)


class _NordpoolBaseSensor(CoordinatorEntity, SensorEntity):
    """Shared base for all Nordpool sensors."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NordpoolCoordinator,
        area: str,
        day: str,
        price_type: str,
        unit_type: str,
        resolution: str,
        currency: str,
        enable_kwh: bool,
        consumer_enabled: bool,
        energy_tax: float,
        supplier_markup: float,
        vat: float,
    ) -> None:
        super().__init__(coordinator)
        language = getattr(coordinator.hass.config, "language", "en")
        self._language = str(language).split("-", 1)[0].lower() if language else "en"
        self._area = area
        self._day = day
        self._price_type = price_type
        self._unit_type = unit_type
        self._resolution = resolution
        self._currency = currency
        self._enable_kwh = enable_kwh
        self._consumer_enabled = consumer_enabled
        self._energy_tax = energy_tax
        self._supplier_markup = supplier_markup
        self._vat = vat

        unit_prefix = _currency_unit_prefix(currency)
        self._attr_native_unit_of_measurement = (
            f"{unit_prefix}/MWh" if unit_type == "mwh" else f"{unit_prefix}/kWh"
        )

    def _get_data(self) -> NordpoolData | None:
        if self._day == "today":
            return self.coordinator.get_today(self._area)
        return self.coordinator.get_tomorrow(self._area)

    def _convert(self, mwh_value: float | None) -> float | None:
        return _apply_conversion(
            mwh_value,
            self._price_type,
            self._unit_type,
            self._energy_tax,
            self._supplier_markup,
            self._vat,
        )

    def _round(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(value, 6 if self._unit_type == "kwh" else 4)

    @property
    def available(self) -> bool:
        return self._get_data() is not None

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._area)},
            "name": f"Nord Pool {self._area}",
            "manufacturer": "Nord Pool Group",
            "model": "Day-Ahead Market",
        }

    def _base_attributes(self) -> dict:
        data = self._get_data()
        if data is None:
            return {"status": "unavailable"}
        return {
            "status": data.status,
            "delivery_date": data.delivery_date,
            "area": self._area,
            "currency": self._currency,
            "resolution": self._resolution,
            "price_type": self._price_type,
        }


class NordpoolCurrentPriceSensor(_NordpoolBaseSensor):
    """
    Sensor showing the current market or consumer price.

    State = price active at this moment.
    Updates triggered by coordinator AND by an internal timer that fires
    exactly on the next quarter/hour boundary so the value switches instantly.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._attr_translation_key = "current_price"
        self._attr_translation_placeholders = {
            "day": _localize_name_token(self._language, "day", self._day),
            "price_type": _localize_name_token(self._language, "price_type", self._price_type),
            "resolution": _localize_name_token(self._language, "resolution", self._resolution),
            "unit": _localize_name_token(self._language, "unit", self._unit_type),
        }
        self._attr_unique_id = (
            f"nordpool_{self._area}_{self._day}_{self._price_type}"
            f"_{self._unit_type}_{self._resolution}"
        )
        self._attr_icon = "mdi:cash" if self._price_type == "market" else "mdi:account-cash-outline"
        self._unsub_boundary: callable | None = None

    async def async_added_to_hass(self) -> None:
        """Start boundary timer when entity is added."""
        await super().async_added_to_hass()
        self._schedule_next_boundary()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel timer on removal."""
        if self._unsub_boundary:
            self._unsub_boundary()
            self._unsub_boundary = None

    def _schedule_next_boundary(self) -> None:
        """Schedule a state refresh at the next quarter-hour boundary."""
        if self._resolution == "quarter":
            next_time = _next_quarter_boundary()
        else:
            # For hourly: fire at next full hour
            now = datetime.now(tz=UTC)
            next_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        @callback
        def _boundary_reached(now: datetime) -> None:
            self.async_write_ha_state()
            self._schedule_next_boundary()  # schedule the one after that

        self._unsub_boundary = async_track_point_in_utc_time(
            self.hass, _boundary_reached, next_time
        )

    @property
    def native_value(self) -> float | None:
        data = self._get_data()
        if data is None:
            return None

        if self._day == "tomorrow":
            now_local = datetime.now(tz=LOCAL_TZ)
            tomorrow_same_local_time = now_local + timedelta(days=1)
            raw = data.price_at(tomorrow_same_local_time, resolution=self._resolution)

            if raw is None:
                rows = data.quarter_prices if self._resolution == "quarter" else data.hour_prices
                raw = next((row.get("value") for row in rows if row.get("value") is not None), None)
        else:
            raw = data.price_at(datetime.now(tz=UTC), resolution=self._resolution)

        return self._round(self._convert(raw))

    @property
    def extra_state_attributes(self) -> dict:
        data = self._get_data()
        attrs = self._base_attributes()
        if data is None:
            return {**attrs, "prices": []}

        rows = data.quarter_prices if self._resolution == "quarter" else data.hour_prices
        enriched = build_price_rows(
            rows,
            enable_kwh=self._enable_kwh,
            consumer_price_enabled=self._consumer_enabled,
            energy_tax=self._energy_tax,
            supplier_markup=self._supplier_markup,
            vat=self._vat,
        )
        key = f"{self._price_type}_{self._unit_type}"
        prices = [
            {
                "startTime": r["startTime"],
                "endTime": r["endTime"],
                "price": r.get(key),
            }
            for r in enriched
        ]

        # Add block aggregates if available
        extra: dict = {}
        if data.block_aggregates:
            extra["block_aggregates"] = [
                {
                    "blockName": b["blockName"],
                    "deliveryStart": b["deliveryStart"],
                    "deliveryEnd": b["deliveryEnd"],
                    "average": self._round(self._convert(b.get("average_mwh"))),
                    "min": self._round(self._convert(b.get("min_mwh"))),
                    "max": self._round(self._convert(b.get("max_mwh"))),
                }
                for b in data.block_aggregates
            ]

        return {**attrs, "prices": prices, **extra}


class NordpoolStatSensor(_NordpoolBaseSensor):
    """
    Sensor for a daily statistic: min, max or average price.
    Disabled by default — user must enable in the entity registry.
    """

    _attr_entity_registry_enabled_default = False

    def __init__(self, stat: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stat = stat  # "min" | "max" | "average"
        self._attr_translation_key = "daily_stat"
        self._attr_translation_placeholders = {
            "day": _localize_name_token(self._language, "day", self._day),
            "price_type": _localize_name_token(self._language, "price_type", self._price_type),
            "resolution": _localize_name_token(self._language, "resolution", self._resolution),
            "unit": _localize_name_token(self._language, "unit", self._unit_type),
            "stat": _localize_name_token(self._language, "stat", self._stat),
        }
        self._attr_unique_id = (
            f"nordpool_{self._area}_{self._day}_{self._price_type}"
            f"_{self._unit_type}_{self._resolution}_{stat}"
        )

        icon_by_stat = {
            "min": "mdi:arrow-collapse-down",
            "max": "mdi:arrow-collapse-up",
            "average": "mdi:arrow-expand-vertical",
        }
        self._attr_icon = icon_by_stat.get(stat, "mdi:arrow-expand-vertical")

    @property
    def native_value(self) -> float | None:
        data = self._get_data()
        if data is None:
            return None
        stats = data.stats(resolution=self._resolution)
        raw_mwh = stats.get(self._stat)
        return self._round(self._convert(raw_mwh))

    @property
    def extra_state_attributes(self) -> dict:
        data = self._get_data()
        attrs = self._base_attributes()
        if data is None:
            return attrs
        stats = data.stats(resolution=self._resolution)
        return {
            **attrs,
            "min": self._round(self._convert(stats.get("min"))),
            "max": self._round(self._convert(stats.get("max"))),
            "average": self._round(self._convert(stats.get("average"))),
            "count": stats.get("count"),
        }


class NordpoolApiDiagnosticsSensor(CoordinatorEntity, SensorEntity):
    """Diagnostic sensor exposing API metadata and last fetch time per day."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True

    def __init__(self, coordinator: NordpoolCoordinator, area: str, day: str) -> None:
        super().__init__(coordinator)
        self._area = area
        self._day = day
        language = getattr(coordinator.hass.config, "language", "en")
        self._language = str(language).split("-", 1)[0].lower() if language else "en"

        self._attr_translation_key = "api_diagnostics"
        self._attr_translation_placeholders = {
            "day": _localize_name_token(self._language, "day", day),
        }
        self._attr_unique_id = f"nordpool_{area}_{day}_api_last_fetch"
        self._attr_icon = "mdi:api"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.get_last_fetch(self._area, self._day)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.get_day_data(self._area, self._day)
        api_url = self.coordinator.get_last_request_url(self._area, self._day)
        if data is None:
            return {
                "area": self._area,
                "day": self._day,
                "status": "unavailable",
                "delivery_date_cet": None,
                "api_updated_at": None,
                "api_version": None,
                "api_url": api_url,
            }

        raw = data.raw if isinstance(data.raw, dict) else {}
        return {
            "area": self._area,
            "day": self._day,
            "status": data.status,
            "delivery_date_cet": data.delivery_date,
            "api_updated_at": raw.get("updatedAt"),
            "api_version": raw.get("version"),
            "api_url": api_url,
        }

    @property
    def device_info(self) -> dict:
        return {
            "identifiers": {(DOMAIN, self._area)},
            "name": f"Nord Pool {self._area}",
            "manufacturer": "Nord Pool Group",
            "model": "Day-Ahead Market",
        }
