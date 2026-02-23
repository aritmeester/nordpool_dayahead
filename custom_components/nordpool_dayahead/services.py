"""Services for Nordpool Day-Ahead integration."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_CONSUMER_PRICE_ENABLED, CONF_ENERGY_TAX, CONF_SUPPLIER_MARKUP, CONF_VAT
from .coordinator import NordpoolCoordinator
from .price_utils import consumer_price_kwh, mwh_to_kwh

_LOGGER = logging.getLogger(__name__)

UTC = timezone.utc

SERVICE_CHEAPEST_BLOCKS = "get_cheapest_blocks"
SERVICE_FORECAST_DEVICE_COST = "forecast_device_cost"
SERVICE_GET_BEST_NEXT_WINDOW = "get_best_next_window"
SERVICE_GENERATE_TEMPLATE_PACKAGE = "generate_template_package"
SERVICE_GENERATE_DASHBOARD_BLUEPRINT = "generate_dashboard_blueprint"
SERVICE_GET_EXPORT_STRATEGY = "get_export_strategy"
SERVICE_GET_PRICE_ALERTS = "get_price_alerts"

ALL_SERVICES = [
    SERVICE_CHEAPEST_BLOCKS,
    SERVICE_FORECAST_DEVICE_COST,
    SERVICE_GET_BEST_NEXT_WINDOW,
    SERVICE_GENERATE_TEMPLATE_PACKAGE,
    SERVICE_GENERATE_DASHBOARD_BLUEPRINT,
    SERVICE_GET_EXPORT_STRATEGY,
    SERVICE_GET_PRICE_ALERTS,
]

SCHEMA_CHEAPEST_BLOCKS = vol.Schema(
    {
        vol.Required("area"): cv.string,
        vol.Optional("day", default="today"): vol.In(["today", "tomorrow"]),
        vol.Optional("resolution", default="quarter"): vol.In(["quarter", "hour"]),
        vol.Optional("price_type", default="market"): vol.In(["market", "consumer"]),
        vol.Optional("n_blocks", default=4): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=96)
        ),
        vol.Optional("contiguous", default=True): cv.boolean,
    }
)

SCHEMA_FORECAST_DEVICE_COST = vol.Schema(
    {
        vol.Required("area"): cv.string,
        vol.Required("power_kw"): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
        vol.Optional("day", default="today"): vol.In(["today", "tomorrow"]),
        vol.Optional("resolution", default="quarter"): vol.In(["quarter", "hour"]),
        vol.Optional("price_type", default="market"): vol.In(["market", "consumer"]),
        vol.Optional("n_blocks", default=4): vol.All(vol.Coerce(int), vol.Range(min=1, max=96)),
        vol.Optional("contiguous", default=True): cv.boolean,
        vol.Optional("start_time"): cv.string,
        vol.Optional("end_time"): cv.string,
    }
)

SCHEMA_BEST_NEXT_WINDOW = vol.Schema(
    {
        vol.Required("area"): cv.string,
        vol.Optional("resolution", default="quarter"): vol.In(["quarter", "hour"]),
        vol.Optional("price_type", default="market"): vol.In(["market", "consumer"]),
        vol.Optional("n_blocks", default=4): vol.All(vol.Coerce(int), vol.Range(min=1, max=96)),
        vol.Optional("contiguous", default=True): cv.boolean,
        vol.Optional("power_kw", default=1.0): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
        vol.Optional("search_scope", default="today_or_tomorrow"): vol.In(
            ["today", "tomorrow", "today_or_tomorrow"]
        ),
    }
)

SCHEMA_TEMPLATE_PACKAGE = vol.Schema(
    {
        vol.Required("area"): cv.string,
        vol.Optional("device", default="ev"): vol.In(["ev", "dishwasher", "boiler"]),
        vol.Optional("price_type", default="market"): vol.In(["market", "consumer"]),
        vol.Optional("resolution", default="hour"): vol.In(["quarter", "hour"]),
        vol.Optional("n_blocks", default=3): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
        vol.Optional("power_kw", default=3.7): vol.All(vol.Coerce(float), vol.Range(min=0.01)),
    }
)

SCHEMA_DASHBOARD_BLUEPRINT = vol.Schema(
    {
        vol.Optional("areas", default=None): vol.Any(None, cv.string, vol.All(list, [cv.string])),
        vol.Optional("day", default="today"): vol.In(["today", "tomorrow"]),
        vol.Optional("price_type", default="market"): vol.In(["market", "consumer"]),
        vol.Optional("unit", default="kwh"): vol.In(["kwh", "mwh"]),
    }
)

SCHEMA_EXPORT_STRATEGY = vol.Schema(
    {
        vol.Required("area"): cv.string,
        vol.Optional("day", default="today"): vol.In(["today", "tomorrow"]),
        vol.Optional("resolution", default="quarter"): vol.In(["quarter", "hour"]),
        vol.Optional("price_type", default="market"): vol.In(["market", "consumer"]),
        vol.Optional("charge_blocks", default=4): vol.All(vol.Coerce(int), vol.Range(min=1, max=96)),
        vol.Optional("discharge_blocks", default=4): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=96)
        ),
        vol.Optional("charge_mode", default="negative_or_lowest"): vol.In(
            ["negative_only", "negative_or_lowest", "lowest"]
        ),
    }
)

SCHEMA_PRICE_ALERTS = vol.Schema(
    {
        vol.Required("area"): cv.string,
        vol.Optional("day", default="today"): vol.In(["today", "tomorrow"]),
        vol.Optional("resolution", default="hour"): vol.In(["quarter", "hour"]),
        vol.Optional("price_type", default="market"): vol.In(["market", "consumer"]),
        vol.Optional("threshold_kwh"): vol.Coerce(float),
        vol.Optional("top_n", default=3): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
        vol.Optional("include_negative", default=True): cv.boolean,
    }
)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_max_blocks(resolution: str, n_blocks: int) -> None:
    max_blocks = 96 if resolution == "quarter" else 24
    if n_blocks > max_blocks:
        raise ServiceValidationError(
            f"n_blocks={n_blocks} is too high for resolution '{resolution}'. Maximum is {max_blocks}."
        )


def _get_data_or_raise(coordinator: NordpoolCoordinator, area: str, day: str):
    data = coordinator.get_today(area) if day == "today" else coordinator.get_tomorrow(area)
    if data is None:
        raise ServiceValidationError(
            f"No price data available for area '{area}' ({day}). "
            "Tomorrow's prices are only available after 13:00 CET."
        )
    return data


def _row_price_kwh(
    coordinator: NordpoolCoordinator,
    area: str,
    row: dict,
    price_type: str,
) -> float | None:
    price_mwh = row.get("value")
    market_kwh = mwh_to_kwh(price_mwh)
    if market_kwh is None:
        return None
    if price_type == "market":
        return market_kwh
    settings = coordinator.get_consumer_settings(area)
    return consumer_price_kwh(
        market_kwh,
        settings[CONF_ENERGY_TAX],
        settings[CONF_SUPPLIER_MARKUP],
        settings[CONF_VAT],
    )


def _validate_consumer_enabled(
    coordinator: NordpoolCoordinator,
    area: str,
    price_type: str,
) -> None:
    if price_type != "consumer":
        return
    settings = coordinator.get_consumer_settings(area)
    if not settings.get(CONF_CONSUMER_PRICE_ENABLED, True):
        raise ServiceValidationError(f"Consumer price is disabled for area '{area}'.")


def _rows_for_resolution(data, resolution: str) -> list[dict]:
    return data.quarter_prices if resolution == "quarter" else data.hour_prices


def _select_rows_by_window(rows: list[dict], start_time: str, end_time: str) -> list[dict]:
    start_dt = _parse_dt(start_time)
    end_dt = _parse_dt(end_time)
    if start_dt >= end_dt:
        raise ServiceValidationError("start_time must be before end_time")

    selected = []
    for row in rows:
        row_start = _parse_dt(row["startTime"])
        row_end = _parse_dt(row["endTime"])
        if row_end > start_dt and row_start < end_dt and row.get("value") is not None:
            selected.append(row)
    return selected


def _window_summary(
    coordinator: NordpoolCoordinator,
    area: str,
    day: str,
    resolution: str,
    rows: list[dict],
    price_type: str,
    power_kw: float,
):
    detailed_blocks = []
    total_energy_kwh = 0.0
    total_cost = 0.0

    for row in rows:
        start_dt = _parse_dt(row["startTime"])
        end_dt = _parse_dt(row["endTime"])
        duration_hours = (end_dt - start_dt).total_seconds() / 3600
        price_kwh = _row_price_kwh(coordinator, area, row, price_type)
        if price_kwh is None:
            continue

        energy_kwh = power_kw * duration_hours
        cost = energy_kwh * price_kwh
        total_energy_kwh += energy_kwh
        total_cost += cost

        detailed_blocks.append(
            {
                "startTime": row["startTime"],
                "endTime": row["endTime"],
                "duration_hours": round(duration_hours, 4),
                "price_kwh": round(price_kwh, 6),
                "energy_kwh": round(energy_kwh, 4),
                "cost": round(cost, 4),
            }
        )

    if not detailed_blocks:
        raise ServiceValidationError("No valid priced blocks found for the requested window.")

    average_price_kwh = total_cost / total_energy_kwh if total_energy_kwh > 0 else 0
    return {
        "area": area,
        "day": day,
        "resolution": resolution,
        "price_type": price_type,
        "power_kw": power_kw,
        "currency": coordinator.currency,
        "total_energy_kwh": round(total_energy_kwh, 4),
        "total_cost": round(total_cost, 4),
        "average_price_kwh": round(average_price_kwh, 6),
        "window_start": detailed_blocks[0]["startTime"],
        "window_end": detailed_blocks[-1]["endTime"],
        "blocks": detailed_blocks,
    }


def _render_template_package(
    area: str,
    device: str,
    price_type: str,
    resolution: str,
    n_blocks: int,
    power_kw: float,
) -> str:
    script_entity = f"switch.{device}_power"
    sensor_name = f"nordpool_{device}_forecast"
    return f"""template:
  - trigger:
      - platform: time_pattern
        minutes: '/15'
    action:
      - service: nordpool_dayahead.forecast_device_cost
        data:
          area: {area}
          day: today
          resolution: {resolution}
          price_type: {price_type}
          n_blocks: {n_blocks}
          contiguous: true
          power_kw: {power_kw}
        response_variable: forecast
    sensor:
      - name: {sensor_name}
        unique_id: {sensor_name}
                unit_of_measurement: "€"
        state: >-
          {{ forecast.total_cost if forecast is defined else none }}
        attributes:
          start: >-
            {{ forecast.window_start if forecast is defined else none }}
          end: >-
            {{ forecast.window_end if forecast is defined else none }}

automation:
  - alias: "Run {device} in cheapest window"
    trigger:
      - platform: time_pattern
        minutes: '/15'
    action:
      - service: nordpool_dayahead.get_best_next_window
        data:
          area: {area}
          resolution: {resolution}
          price_type: {price_type}
          n_blocks: {n_blocks}
          power_kw: {power_kw}
          search_scope: today_or_tomorrow
        response_variable: best
      - variables:
          start_ts: "{{ as_timestamp(best.window_start) if best is defined else none }}"
          end_ts: "{{ as_timestamp(best.window_end) if best is defined else none }}"
          now_ts: "{{ as_timestamp(now()) }}"
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ start_ts is not none and end_ts is not none and start_ts <= now_ts < end_ts }}"
            sequence:
              - service: switch.turn_on
                target:
                  entity_id: {script_entity}
        default:
          - service: switch.turn_off
            target:
              entity_id: {script_entity}
"""


def _render_dashboard_blueprint(areas: list[str], day: str, price_type: str, unit: str) -> str:
    area_entities_quarter = "\n".join(
        [
            f"        - entity: sensor.nordpool_{area.lower()}_{day}_{price_type}_quarter_hour_{unit}"
            for area in areas
        ]
    )
    area_entities_hour = "\n".join(
        [
            f"        - entity: sensor.nordpool_{area.lower()}_{day}_{price_type}_hourly_{unit}"
            for area in areas
        ]
    )
    return f"""# Dashboard blueprint snippet (paste in a manual dashboard)
type: vertical-stack
cards:
  - type: entities
    title: Nordpool graph controls
    entities:
      - entity: input_select.nordpool_graph_resolution
        name: Resolution (quarter/hour)
  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: quarter
    card:
      type: history-graph
      title: Nordpool {price_type} quarter-hour ({day})
      hours_to_show: 24
      entities:
{area_entities_quarter}
  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: hour
    card:
      type: history-graph
      title: Nordpool {price_type} hourly ({day})
      hours_to_show: 24
      entities:
{area_entities_hour}
"""


def async_register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    if hass.services.has_service(DOMAIN, SERVICE_CHEAPEST_BLOCKS):
        return

    async def handle_cheapest_blocks(call: ServiceCall) -> ServiceResponse:
        """
        Find the n cheapest quarter-hour or hourly price blocks for a given area and day.

        Returns a list of price blocks sorted by time with their market prices.
        """
        area: str = call.data["area"].upper()
        day: str = call.data["day"]
        resolution: str = call.data["resolution"]
        price_type: str = call.data["price_type"]
        n_blocks: int = call.data["n_blocks"]
        contiguous: bool = call.data["contiguous"]

        _validate_max_blocks(resolution, n_blocks)

        coordinator = _find_coordinator(hass, area)
        if coordinator is None:
            raise ServiceValidationError(
                f"Area '{area}' is not configured in any Nordpool Day-Ahead integration."
            )

        data = _get_data_or_raise(coordinator, area, day)

        blocks = data.cheapest_blocks(
            n_blocks=n_blocks,
            resolution=resolution,
            contiguous=contiguous,
        )

        if not blocks:
            raise ServiceValidationError(
                f"Could not find {n_blocks} {'contiguous ' if contiguous else ''}"
                f"{resolution} blocks for {area} ({day})."
            )

        block_minutes = 15 if resolution == "quarter" else 60
        total_minutes = len(blocks) * block_minutes
        _validate_consumer_enabled(coordinator, area, price_type)
        kwh_values = [_row_price_kwh(coordinator, area, block, price_type) for block in blocks]
        valid_kwh = [value for value in kwh_values if value is not None]
        if not valid_kwh:
            raise ServiceValidationError("No valid priced blocks found.")
        avg_price_kwh = sum(valid_kwh) / len(valid_kwh)

        return {
            "area": area,
            "day": day,
            "resolution": resolution,
            "price_type": price_type,
            "contiguous": contiguous,
            "n_blocks": n_blocks,
            "total_duration_minutes": total_minutes,
            "average_price_kwh": round(avg_price_kwh, 6),
            "status": data.status,
            "delivery_date": data.delivery_date,
            "blocks": [
                {
                    "startTime": b["startTime"],
                    "endTime": b["endTime"],
                    "price_kwh": (
                        round(_row_price_kwh(coordinator, area, b, price_type), 6)
                        if _row_price_kwh(coordinator, area, b, price_type) is not None
                        else None
                    ),
                }
                for b in blocks
            ],
        }

    async def handle_forecast_device_cost(call: ServiceCall) -> ServiceResponse:
        area: str = call.data["area"].upper()
        power_kw: float = call.data["power_kw"]
        day: str = call.data["day"]
        resolution: str = call.data["resolution"]
        price_type: str = call.data["price_type"]
        n_blocks: int = call.data["n_blocks"]
        contiguous: bool = call.data["contiguous"]
        start_time: str | None = call.data.get("start_time")
        end_time: str | None = call.data.get("end_time")

        _validate_max_blocks(resolution, n_blocks)
        coordinator = _find_coordinator(hass, area)
        if coordinator is None:
            raise ServiceValidationError(f"Area '{area}' is not configured.")

        _validate_consumer_enabled(coordinator, area, price_type)

        data = _get_data_or_raise(coordinator, area, day)
        rows = _rows_for_resolution(data, resolution)

        if (start_time and not end_time) or (end_time and not start_time):
            raise ServiceValidationError("Provide both start_time and end_time, or neither.")

        if start_time and end_time:
            selected_rows = _select_rows_by_window(rows, start_time, end_time)
        else:
            selected_rows = data.cheapest_blocks(
                n_blocks=n_blocks,
                resolution=resolution,
                contiguous=contiguous,
            )

        return _window_summary(
            coordinator=coordinator,
            area=area,
            day=day,
            resolution=resolution,
            rows=selected_rows,
            price_type=price_type,
            power_kw=power_kw,
        )

    async def handle_get_best_next_window(call: ServiceCall) -> ServiceResponse:
        area: str = call.data["area"].upper()
        resolution: str = call.data["resolution"]
        price_type: str = call.data["price_type"]
        n_blocks: int = call.data["n_blocks"]
        contiguous: bool = call.data["contiguous"]
        power_kw: float = call.data["power_kw"]
        search_scope: str = call.data["search_scope"]

        _validate_max_blocks(resolution, n_blocks)
        coordinator = _find_coordinator(hass, area)
        if coordinator is None:
            raise ServiceValidationError(f"Area '{area}' is not configured.")

        _validate_consumer_enabled(coordinator, area, price_type)

        now_utc = datetime.now(tz=UTC)
        candidate_rows: list[dict] = []
        candidate_day = "today"

        day_order = (
            [search_scope]
            if search_scope in ["today", "tomorrow"]
            else ["today", "tomorrow"]
        )
        for day in day_order:
            data = coordinator.get_today(area) if day == "today" else coordinator.get_tomorrow(area)
            if data is None:
                continue
            rows = _rows_for_resolution(data, resolution)
            future_rows = [r for r in rows if r.get("value") is not None and _parse_dt(r["endTime"]) > now_utc]
            if len(future_rows) >= n_blocks:
                candidate_rows = future_rows
                candidate_day = day
                break

        if not candidate_rows:
            raise ServiceValidationError("No future priced blocks available for the requested scope.")

        if contiguous:
            best_avg = float("inf")
            best_window: list[dict] = []
            for idx in range(0, len(candidate_rows) - n_blocks + 1):
                window = candidate_rows[idx : idx + n_blocks]
                prices = [_row_price_kwh(coordinator, area, row, price_type) for row in window]
                valid = [price for price in prices if price is not None]
                if len(valid) != n_blocks:
                    continue
                avg = sum(valid) / n_blocks
                if avg < best_avg:
                    best_avg = avg
                    best_window = window
            if not best_window:
                raise ServiceValidationError("No contiguous window found.")
            selected = best_window
        else:
            priced = [
                (row, _row_price_kwh(coordinator, area, row, price_type))
                for row in candidate_rows
            ]
            valid = [(row, price) for row, price in priced if price is not None]
            selected = [row for row, _ in sorted(valid, key=lambda item: item[1])[:n_blocks]]
            selected = sorted(selected, key=lambda row: row["startTime"])

        summary = _window_summary(
            coordinator=coordinator,
            area=area,
            day=candidate_day,
            resolution=resolution,
            rows=selected,
            price_type=price_type,
            power_kw=power_kw,
        )
        summary["search_scope"] = search_scope
        return summary

    async def handle_generate_template_package(call: ServiceCall) -> ServiceResponse:
        area: str = call.data["area"].upper()
        device: str = call.data["device"]
        price_type: str = call.data["price_type"]
        resolution: str = call.data["resolution"]
        n_blocks: int = call.data["n_blocks"]
        power_kw: float = call.data["power_kw"]
        package_yaml = _render_template_package(
            area=area,
            device=device,
            price_type=price_type,
            resolution=resolution,
            n_blocks=n_blocks,
            power_kw=power_kw,
        )
        return {
            "device": device,
            "area": area,
            "resolution": resolution,
            "price_type": price_type,
            "package_yaml": package_yaml,
        }

    async def handle_generate_dashboard_blueprint(call: ServiceCall) -> ServiceResponse:
        areas: list[str] = _normalize_areas_input(hass, call.data.get("areas"))
        day: str = call.data["day"]
        price_type: str = call.data["price_type"]
        unit: str = call.data["unit"]
        blueprint_yaml = _render_dashboard_blueprint(
            areas=areas,
            day=day,
            price_type=price_type,
            unit=unit,
        )
        return {
            "areas": areas,
            "day": day,
            "price_type": price_type,
            "unit": unit,
            "dashboard_yaml": blueprint_yaml,
        }

    async def handle_get_export_strategy(call: ServiceCall) -> ServiceResponse:
        area: str = call.data["area"].upper()
        day: str = call.data["day"]
        resolution: str = call.data["resolution"]
        price_type: str = call.data["price_type"]
        charge_blocks: int = call.data["charge_blocks"]
        discharge_blocks: int = call.data["discharge_blocks"]
        charge_mode: str = call.data["charge_mode"]

        _validate_max_blocks(resolution, charge_blocks)
        _validate_max_blocks(resolution, discharge_blocks)
        coordinator = _find_coordinator(hass, area)
        if coordinator is None:
            raise ServiceValidationError(f"Area '{area}' is not configured.")

        _validate_consumer_enabled(coordinator, area, price_type)

        data = _get_data_or_raise(coordinator, area, day)
        rows = [row for row in _rows_for_resolution(data, resolution) if row.get("value") is not None]
        priced_rows = [(row, _row_price_kwh(coordinator, area, row, price_type)) for row in rows]
        valid_rows = [(row, price) for row, price in priced_rows if price is not None]
        if not valid_rows:
            raise ServiceValidationError("No valid prices available for export strategy.")

        negatives = [(row, price) for row, price in valid_rows if price < 0]
        if charge_mode == "negative_only":
            charge_source = negatives
        elif charge_mode == "negative_or_lowest":
            charge_source = negatives if negatives else valid_rows
        else:
            charge_source = valid_rows

        charge_selected = [row for row, _ in sorted(charge_source, key=lambda item: item[1])[:charge_blocks]]
        discharge_selected = [
            row for row, _ in sorted(valid_rows, key=lambda item: item[1], reverse=True)[:discharge_blocks]
        ]

        charge_selected = sorted(charge_selected, key=lambda row: row["startTime"])
        discharge_selected = sorted(discharge_selected, key=lambda row: row["startTime"])

        return {
            "area": area,
            "day": day,
            "resolution": resolution,
            "price_type": price_type,
            "charge_mode": charge_mode,
            "charge_blocks": [
                {
                    "startTime": row["startTime"],
                    "endTime": row["endTime"],
                    "price_kwh": round(_row_price_kwh(coordinator, area, row, price_type), 6),
                }
                for row in charge_selected
            ],
            "discharge_blocks": [
                {
                    "startTime": row["startTime"],
                    "endTime": row["endTime"],
                    "price_kwh": round(_row_price_kwh(coordinator, area, row, price_type), 6),
                }
                for row in discharge_selected
            ],
        }

    async def handle_get_price_alerts(call: ServiceCall) -> ServiceResponse:
        area: str = call.data["area"].upper()
        day: str = call.data["day"]
        resolution: str = call.data["resolution"]
        price_type: str = call.data["price_type"]
        threshold_kwh: float | None = call.data.get("threshold_kwh")
        top_n: int = call.data["top_n"]
        include_negative: bool = call.data["include_negative"]

        _validate_max_blocks(resolution, top_n)
        coordinator = _find_coordinator(hass, area)
        if coordinator is None:
            raise ServiceValidationError(f"Area '{area}' is not configured.")

        _validate_consumer_enabled(coordinator, area, price_type)

        data = _get_data_or_raise(coordinator, area, day)
        rows = [row for row in _rows_for_resolution(data, resolution) if row.get("value") is not None]
        priced_rows = [
            {
                "startTime": row["startTime"],
                "endTime": row["endTime"],
                "price_kwh": _row_price_kwh(coordinator, area, row, price_type),
            }
            for row in rows
        ]
        valid = [row for row in priced_rows if row["price_kwh"] is not None]

        threshold_matches = []
        if threshold_kwh is not None:
            threshold_matches = [
                row for row in valid if row["price_kwh"] is not None and row["price_kwh"] < threshold_kwh
            ]

        negative_matches = [row for row in valid if row["price_kwh"] is not None and row["price_kwh"] < 0]
        top_cheapest = sorted(valid, key=lambda row: row["price_kwh"])[:top_n]

        return {
            "area": area,
            "day": day,
            "resolution": resolution,
            "price_type": price_type,
            "threshold_kwh": threshold_kwh,
            "threshold_triggered": len(threshold_matches) > 0,
            "negative_triggered": include_negative and len(negative_matches) > 0,
            "top_n": top_n,
            "top_cheapest": [
                {
                    "startTime": row["startTime"],
                    "endTime": row["endTime"],
                    "price_kwh": round(row["price_kwh"], 6),
                }
                for row in top_cheapest
            ],
            "threshold_matches": [
                {
                    "startTime": row["startTime"],
                    "endTime": row["endTime"],
                    "price_kwh": round(row["price_kwh"], 6),
                }
                for row in threshold_matches
            ],
            "negative_matches": [
                {
                    "startTime": row["startTime"],
                    "endTime": row["endTime"],
                    "price_kwh": round(row["price_kwh"], 6),
                }
                for row in negative_matches
            ],
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_CHEAPEST_BLOCKS,
        handle_cheapest_blocks,
        schema=SCHEMA_CHEAPEST_BLOCKS,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FORECAST_DEVICE_COST,
        handle_forecast_device_cost,
        schema=SCHEMA_FORECAST_DEVICE_COST,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_BEST_NEXT_WINDOW,
        handle_get_best_next_window,
        schema=SCHEMA_BEST_NEXT_WINDOW,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_TEMPLATE_PACKAGE,
        handle_generate_template_package,
        schema=SCHEMA_TEMPLATE_PACKAGE,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_DASHBOARD_BLUEPRINT,
        handle_generate_dashboard_blueprint,
        schema=SCHEMA_DASHBOARD_BLUEPRINT,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_EXPORT_STRATEGY,
        handle_get_export_strategy,
        schema=SCHEMA_EXPORT_STRATEGY,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PRICE_ALERTS,
        handle_get_price_alerts,
        schema=SCHEMA_PRICE_ALERTS,
        supports_response=SupportsResponse.ONLY,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_CHEAPEST_BLOCKS)


def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister integration services."""
    for service in ALL_SERVICES:
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


def _all_configured_areas(hass: HomeAssistant) -> list[str]:
    """Return sorted unique list of all configured areas across entries."""
    domain_data = hass.data.get(DOMAIN, {})
    areas: set[str] = set()
    for coordinator in domain_data.values():
        if isinstance(coordinator, NordpoolCoordinator):
            areas.update(coordinator.delivery_areas)
    return sorted(areas)


def _normalize_areas_input(hass: HomeAssistant, raw_areas) -> list[str]:
    """Normalize areas input from service data to uppercase list."""
    if raw_areas is None:
        areas = _all_configured_areas(hass)
        if not areas:
            raise ServiceValidationError("No configured delivery areas found.")
        return areas

    if isinstance(raw_areas, str):
        split_areas = [item.strip().upper() for item in raw_areas.split(",") if item.strip()]
        if not split_areas:
            raise ServiceValidationError("areas must not be empty.")
        return split_areas

    if isinstance(raw_areas, list):
        parsed = [str(area).strip().upper() for area in raw_areas if str(area).strip()]
        if not parsed:
            raise ServiceValidationError("areas must not be empty.")
        return parsed

    raise ServiceValidationError("areas must be a string, list, or omitted.")


def _find_coordinator(hass: HomeAssistant, area: str) -> NordpoolCoordinator | None:
    """Find a coordinator that is configured for the given area."""
    domain_data = hass.data.get(DOMAIN, {})
    for coordinator in domain_data.values():
        if isinstance(coordinator, NordpoolCoordinator) and area in coordinator.delivery_areas:
            return coordinator
    return None
