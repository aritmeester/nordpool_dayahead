"""DataUpdateCoordinator for Nordpool Day-Ahead prices."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    API_BASE_URL,
    MARKET,
    STATUS_FINAL,
    STATUS_PRELIMINARY,
    TOMORROW_PRICES_HOUR_CET,
    POLL_INTERVAL_TOMORROW_PENDING,
    CONF_ENABLE_KWH,
    CONF_ENABLE_HOURLY,
    CONF_CONSUMER_PRICE_ENABLED,
    CONF_ENERGY_TAX,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT,
    DEFAULT_ENERGY_TAX,
    DEFAULT_SUPPLIER_MARKUP,
    DEFAULT_VAT,
)

_LOGGER = logging.getLogger(__name__)

CET = ZoneInfo("Europe/Amsterdam")
UTC = timezone.utc


class NordpoolData:
    """
    Holds parsed price data for a single day and delivery area.

    Actual API response structure (confirmed):
    {
      "deliveryDateCET": "2026-02-18",
      "currency": "EUR",
      "areaStates": [{"state": "Final", "areas": ["NL"]}],
      "multiAreaEntries": [
        {
          "deliveryStart": "2026-02-17T23:00:00Z",
          "deliveryEnd":   "2026-02-17T23:15:00Z",
          "entryPerArea":  {"NL": 91.81}
        },
        ...
      ],
      "blockPriceAggregates": [
        {
          "blockName": "Off-peak 1",
          "deliveryStart": "...",
          "deliveryEnd": "...",
          "averagePricePerArea": {"NL": {"average": 99.50, "min": 82.47, "max": 188.67}}
        },
        ...
      ]
    }
    """

    def __init__(self, raw: dict, area: str) -> None:
        self.raw = raw
        self.area = area
        self.delivery_date: str = raw.get("deliveryDateCET", "")
        self.currency: str = raw.get("currency", "EUR")

        # Parse status from areaStates list
        self.status: str = self._parse_status(raw, area)

        # Validate that this area is actually present in the response
        self.area_available: bool = self._check_area_available(raw, area)

        # Parse quarter-hour prices for this area
        self.quarter_prices: list[dict] = self._parse_quarter_prices(raw, area)

        # Derive hourly prices by averaging groups of 4 quarters
        self.hour_prices: list[dict] = self._derive_hourly_from_quarters(self.quarter_prices)

        # Block price aggregates (Off-peak 1, Peak, Off-peak 2)
        self.block_aggregates: list[dict] = self._parse_block_aggregates(raw, area)

    @staticmethod
    def _parse_status(raw: dict, area: str) -> str:
        """
        Extract status for this area from areaStates.
        areaStates = [{"state": "Final", "areas": ["NL"]}, ...]
        Falls back to Preliminary if area not found.
        """
        for entry in raw.get("areaStates", []):
            if area in entry.get("areas", []):
                return entry.get("state", STATUS_PRELIMINARY)
        return STATUS_PRELIMINARY

    @staticmethod
    def _check_area_available(raw: dict, area: str) -> bool:
        """Return True if this area has at least one price entry."""
        for entry in raw.get("multiAreaEntries", []):
            if area in entry.get("entryPerArea", {}):
                return True
        return False

    @staticmethod
    def _parse_quarter_prices(raw: dict, area: str) -> list[dict]:
        """
        Parse multiAreaEntries into a normalised list of quarter-hour price dicts.
        Result: [{"startTime": ..., "endTime": ..., "value": float|None}, ...]
        """
        result = []
        for entry in raw.get("multiAreaEntries", []):
            value = entry.get("entryPerArea", {}).get(area)
            result.append(
                {
                    "startTime": entry.get("deliveryStart"),
                    "endTime": entry.get("deliveryEnd"),
                    "value": value,
                }
            )
        return result

    @staticmethod
    def _derive_hourly_from_quarters(quarters: list[dict]) -> list[dict]:
        """Average each group of 4 consecutive quarters into one hourly price."""
        hours = []
        for i in range(0, len(quarters), 4):
            group = quarters[i : i + 4]
            if not group:
                continue
            prices = [q["value"] for q in group if q.get("value") is not None]
            avg = sum(prices) / len(prices) if prices else None
            hours.append(
                {
                    "startTime": group[0].get("startTime"),
                    "endTime": group[-1].get("endTime"),
                    "value": round(avg, 5) if avg is not None else None,
                }
            )
        return hours

    @staticmethod
    def _parse_block_aggregates(raw: dict, area: str) -> list[dict]:
        """
        Parse blockPriceAggregates for this area.
        Returns simplified list: [{"blockName": ..., "average": ..., "min": ..., "max": ...}]
        """
        result = []
        for block in raw.get("blockPriceAggregates", []):
            area_data = block.get("averagePricePerArea", {}).get(area)
            if area_data:
                result.append(
                    {
                        "blockName": block.get("blockName"),
                        "deliveryStart": block.get("deliveryStart"),
                        "deliveryEnd": block.get("deliveryEnd"),
                        "average_mwh": area_data.get("average"),
                        "min_mwh": area_data.get("min"),
                        "max_mwh": area_data.get("max"),
                    }
                )
        return result

    @property
    def is_final(self) -> bool:
        return self.status == STATUS_FINAL

    @property
    def is_preliminary(self) -> bool:
        return self.status == STATUS_PRELIMINARY

    def price_at(self, dt: datetime, resolution: str = "quarter") -> float | None:
        """
        Return the market price (EUR/MWh) at a given datetime.
        dt should be timezone-aware. resolution: 'quarter' or 'hour'.
        """
        rows = self.quarter_prices if resolution == "quarter" else self.hour_prices
        # Normalise to UTC for comparison with API timestamps
        dt_utc = dt.astimezone(UTC)
        for row in rows:
            start = _parse_dt(row.get("startTime"))
            end = _parse_dt(row.get("endTime"))
            if start and end and start <= dt_utc < end:
                return row.get("value")
        return None

    def current_quarter_price(self) -> float | None:
        """Return the market price (EUR/MWh) for the current quarter-hour period."""
        return self.price_at(datetime.now(tz=UTC), resolution="quarter")

    def current_hour_price(self) -> float | None:
        """Return the market price (EUR/MWh) for the current hour."""
        return self.price_at(datetime.now(tz=UTC), resolution="hour")

    def stats(self, resolution: str = "quarter") -> dict:
        """Return min, max, average over all price rows."""
        rows = self.quarter_prices if resolution == "quarter" else self.hour_prices
        values = [r["value"] for r in rows if r.get("value") is not None]
        if not values:
            return {"min": None, "max": None, "average": None, "count": 0}
        return {
            "min": round(min(values), 5),
            "max": round(max(values), 5),
            "average": round(sum(values) / len(values), 5),
            "count": len(values),
        }

    def cheapest_blocks(
        self,
        n_blocks: int,
        resolution: str = "quarter",
        contiguous: bool = False,
    ) -> list[dict]:
        """
        Find the n cheapest price blocks.

        Args:
            n_blocks:    Number of blocks (quarters or hours) to find.
            resolution:  'quarter' (15 min) or 'hour'.
            contiguous:  If True, find the cheapest n consecutive blocks.

        Returns list of matching price rows sorted by startTime.
        """
        rows = self.quarter_prices if resolution == "quarter" else self.hour_prices
        valid = [r for r in rows if r.get("value") is not None]

        if not valid or n_blocks <= 0 or n_blocks > len(valid):
            return []

        if contiguous:
            # Sliding window: find window of n_blocks with lowest average
            best_start = 0
            best_avg = float("inf")
            for i in range(len(valid) - n_blocks + 1):
                window = valid[i : i + n_blocks]
                avg = sum(r["value"] for r in window) / n_blocks
                if avg < best_avg:
                    best_avg = avg
                    best_start = i
            return valid[best_start : best_start + n_blocks]
        else:
            # n individually cheapest blocks, sorted back into time order
            sorted_by_price = sorted(valid, key=lambda r: r["value"])
            cheapest = sorted_by_price[:n_blocks]
            # Re-sort by time
            return sorted(cheapest, key=lambda r: r.get("startTime", ""))


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # API returns UTC timestamps ending in 'Z'
        # Python 3.11+ handles Z natively; for 3.10 compatibility we replace it
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _is_after_13_cet() -> bool:
    """Return True if current time is at or after 13:00 CET/CEST."""
    now = datetime.now(tz=CET)
    return now.hour >= TOMORROW_PRICES_HOUR_CET


def _today_cet() -> date:
    return datetime.now(tz=CET).date()


def _tomorrow_cet() -> date:
    return _today_cet() + timedelta(days=1)


def _next_quarter_boundary() -> datetime:
    """Return the next :00, :15, :30 or :45 mark in UTC."""
    now = datetime.now(tz=UTC)
    minutes_past = now.minute % 15
    seconds_past = now.second
    wait_seconds = (15 - minutes_past) * 60 - seconds_past
    return now + timedelta(seconds=wait_seconds)


def _seconds_until_13_cet() -> int:
    """Return seconds until 13:00 CET/CEST (>= 0)."""
    now = datetime.now(tz=CET)
    target = now.replace(
        hour=TOMORROW_PRICES_HOUR_CET,
        minute=0,
        second=0,
        microsecond=0,
    )
    if now >= target:
        return 0
    return max(0, int((target - now).total_seconds()))


def _seconds_until_midnight_cet() -> int:
    """Return seconds until next local midnight CET/CEST (>= 0)."""
    now = datetime.now(tz=CET)
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return max(0, int((next_midnight - now).total_seconds()))


class NordpoolCoordinator(DataUpdateCoordinator):
    """Coordinator that manages today's and tomorrow's price data per area."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        delivery_areas: list[str],
        currency: str,
        consumer_settings: dict[str, dict],
    ) -> None:
        self.delivery_areas = delivery_areas
        self.currency = currency
        self.consumer_settings = consumer_settings

        first_area = delivery_areas[0] if delivery_areas else None
        default_settings = self.get_consumer_settings(first_area) if first_area else {
            CONF_CONSUMER_PRICE_ENABLED: True,
            CONF_ENERGY_TAX: DEFAULT_ENERGY_TAX,
            CONF_SUPPLIER_MARKUP: DEFAULT_SUPPLIER_MARKUP,
            CONF_VAT: DEFAULT_VAT,
        }
        self.consumer_price_enabled = default_settings[CONF_CONSUMER_PRICE_ENABLED]
        self.energy_tax = default_settings[CONF_ENERGY_TAX]
        self.supplier_markup = default_settings[CONF_SUPPLIER_MARKUP]
        self.vat = default_settings[CONF_VAT]
        self._session = async_get_clientsession(hass)
        self._has_successful_fetch = False

        # Internal cache keyed by (area, delivery_date_str)
        # Structure: {area: {"today": NordpoolData | None, "tomorrow": NordpoolData | None}}
        self._cache: dict[str, dict] = {}
        self._last_fetch: dict[str, dict[str, datetime]] = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=60),  # adjusted dynamically
            config_entry=config_entry,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_today(self, area: str) -> NordpoolData | None:
        return self._cache.get(area, {}).get("today")

    def get_tomorrow(self, area: str) -> NordpoolData | None:
        return self._cache.get(area, {}).get("tomorrow")

    def get_last_fetch(self, area: str, day_key: str) -> datetime | None:
        """Return last successful fetch timestamp for area/day key."""
        return self._last_fetch.get(area, {}).get(day_key)

    def get_day_data(self, area: str, day_key: str) -> NordpoolData | None:
        """Return day data by key ('today' or 'tomorrow')."""
        return self._cache.get(area, {}).get(day_key)

    def get_consumer_settings(self, area: str | None) -> dict:
        """Return consumer settings for one area with safe defaults."""
        if area and area in self.consumer_settings:
            area_settings = self.consumer_settings[area]
            return {
                CONF_ENABLE_KWH: area_settings.get(CONF_ENABLE_KWH, True),
                CONF_ENABLE_HOURLY: area_settings.get(CONF_ENABLE_HOURLY, True),
                CONF_CONSUMER_PRICE_ENABLED: area_settings.get(CONF_CONSUMER_PRICE_ENABLED, True),
                CONF_ENERGY_TAX: area_settings.get(CONF_ENERGY_TAX, DEFAULT_ENERGY_TAX),
                CONF_SUPPLIER_MARKUP: area_settings.get(
                    CONF_SUPPLIER_MARKUP,
                    DEFAULT_SUPPLIER_MARKUP,
                ),
                CONF_VAT: area_settings.get(CONF_VAT, DEFAULT_VAT),
            }

        return {
            CONF_ENABLE_KWH: True,
            CONF_ENABLE_HOURLY: True,
            CONF_CONSUMER_PRICE_ENABLED: True,
            CONF_ENERGY_TAX: DEFAULT_ENERGY_TAX,
            CONF_SUPPLIER_MARKUP: DEFAULT_SUPPLIER_MARKUP,
            CONF_VAT: DEFAULT_VAT,
        }

    # ------------------------------------------------------------------
    # Update logic
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Fetch data for all areas, using cache where possible."""
        today = _today_cet()
        tomorrow = _tomorrow_cet()
        fetch_tomorrow = _is_after_13_cet()

        tasks = []
        for area in self.delivery_areas:
            area_cache = self._cache.setdefault(area, {})

            # Today: fetch only if not yet cached for this CET calendar day.
            # Important: compare against deliveryDateCET from the API, not a
            # derived UTC date — avoids spurious re-fetches around midnight.
            today_data: NordpoolData | None = area_cache.get("today")
            if today_data is None or today_data.delivery_date != str(today):
                # Also clear stale tomorrow cache when day rolls over
                if today_data is not None and today_data.delivery_date != str(today):
                    _LOGGER.debug("Day rolled over for %s — clearing cache", area)
                    area_cache.pop("tomorrow", None)
                tasks.append(self._fetch_and_store(area, today, "today"))

            # Tomorrow: only after 13:00 CET, and only while not yet final
            if fetch_tomorrow:
                tomorrow_data: NordpoolData | None = area_cache.get("tomorrow")
                need_fetch = (
                    tomorrow_data is None
                    or tomorrow_data.delivery_date != str(tomorrow)
                    or not tomorrow_data.is_final
                )
                if need_fetch:
                    tasks.append(self._fetch_and_store(area, tomorrow, "tomorrow"))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.debug("Background fetch task failed: %s", result)

        if not self._has_successful_fetch:
            raise UpdateFailed("No Nordpool data fetched yet; retrying on next update cycle")

        self._adjust_interval()
        return dict(self._cache)

    async def _fetch_and_store(self, area: str, target_date: date, key: str) -> None:
        url = (
            f"{API_BASE_URL}"
            f"?date={target_date.isoformat()}"
            f"&market={MARKET}"
            f"&deliveryArea={area}"
            f"&currency={self.currency}"
        )
        _LOGGER.debug("Fetching Nordpool data: %s", url)
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    raw = await resp.json()
                    data = NordpoolData(raw, area)
                    if not data.area_available:
                        _LOGGER.warning(
                            "Area %s not found in API response for %s", area, target_date
                        )
                        return
                    self._cache[area][key] = data
                    self._last_fetch.setdefault(area, {})[key] = datetime.now(tz=UTC)
                    self._has_successful_fetch = True
                    _LOGGER.debug(
                        "Fetched %s prices for %s (%s) — status: %s, quarters: %d",
                        key,
                        area,
                        target_date,
                        data.status,
                        len(data.quarter_prices),
                    )
                elif resp.status == 204:
                    _LOGGER.debug("No data yet for %s %s (204)", area, target_date)
                else:
                    _LOGGER.warning(
                        "Unexpected HTTP %s fetching %s %s", resp.status, area, target_date
                    )
        except aiohttp.ClientError as err:
            _LOGGER.error("Network error fetching Nordpool data for %s: %s", area, err)
            # Don't raise UpdateFailed so other areas still succeed

    def _adjust_interval(self) -> None:
        """
        Dynamically set the next poll interval:
        - While today's data for the current CET date is missing: every minute
        - Before 13:00 CET: 1 hour (no tomorrow data needed)
        - After 13:00, some areas still Preliminary: every minute
        - After 13:00, all areas Final: 1 hour

        Additionally, hourly polling is aligned to important local boundaries
        (13:00 publication moment and midnight day rollover) to avoid stale data
        windows around those transitions.
        """
        today_str = str(_today_cet())
        tomorrow_str = str(_tomorrow_cet())

        today_pending = any(
            self._cache.get(area, {}).get("today") is None
            or self._cache.get(area, {}).get("today").delivery_date != today_str
            for area in self.delivery_areas
        )

        if today_pending:
            self.update_interval = timedelta(seconds=POLL_INTERVAL_TOMORROW_PENDING)
            _LOGGER.debug("Today's data pending for at least one area; polling every minute")
            return

        if not _is_after_13_cet():
            next_interval_seconds = 3600
            seconds_until_13 = _seconds_until_13_cet()
            seconds_until_midnight = _seconds_until_midnight_cet()

            if 0 < seconds_until_13 < next_interval_seconds:
                next_interval_seconds = seconds_until_13
            if 0 < seconds_until_midnight < next_interval_seconds:
                next_interval_seconds = seconds_until_midnight

            self.update_interval = timedelta(seconds=max(60, next_interval_seconds))
            return

        all_final = all(
            self._cache.get(area, {}).get("tomorrow") is not None
            and self._cache[area]["tomorrow"].delivery_date == tomorrow_str
            and self._cache[area]["tomorrow"].is_final
            for area in self.delivery_areas
        )

        if all_final:
            seconds_until_midnight = _seconds_until_midnight_cet()
            if 0 < seconds_until_midnight < 3600:
                self.update_interval = timedelta(seconds=max(60, seconds_until_midnight))
            else:
                self.update_interval = timedelta(hours=1)
        else:
            self.update_interval = timedelta(seconds=POLL_INTERVAL_TOMORROW_PENDING)

        _LOGGER.debug("Next poll interval: %s", self.update_interval)
