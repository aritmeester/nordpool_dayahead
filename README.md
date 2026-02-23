# Nord Pool Day-Ahead Prices — Home Assistant Custom Component

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/aritmeester/nordpool-dayahead.svg)](https://github.com/aritmeester/nordpool-dayahead/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE.md)

A Home Assistant custom integration that provides **Nord Pool Day-Ahead electricity market prices** for one or more delivery areas. Designed for minimal API usage, exact sensor timing, and full configurability.

**Minimum Home Assistant version:** `2025.1.0`

---

## Features

- 📊 **Quarter-hour prices** (native API resolution) and optional **hourly averages** (mean of 4 quarters)
- 💶 **Market price per MWh**, optionally also per kWh
- 🧾 **Consumer price calculation** — adds configurable energy tax, supplier markup and VAT
- 🎛️ **Per-area options** — kWh/hourly/consumer toggles and rates are configurable per selected area
- 📅 **Today's prices** — fetched once per calendar day, cached until midnight
- 📅 **Tomorrow's prices** — available from 13:00 CET; polling starts automatically at/around 13:00 and continues every minute until `Final`
- ⏱️ **Exact timing** — current price sensors switch value exactly at each quarter/hour boundary
- 🔔 **Binary sensor per area** — indicates whether tomorrow's prices are confirmed (`Final`)
- 📊 **Min / Max / Average sensors** — optional daily statistics per area (disabled by default)
- 🩺 **API diagnostics sensors** — optional per area/day diagnostics with last fetch timestamp, status, `deliveryDateCET`, `updatedAt`, and `version`
- 🔍 **Service: cheapest blocks** — find the cheapest window or individual slots in a day
- 💸 **Device cost forecast service** — estimate expected costs per chosen window and kW load
- 🤖 **Best next window service** — automation-ready start/end output for EV, boiler, heat pump
- 🧩 **Template package generator** — auto-generate YAML snippets for EV, dishwasher and boiler flows
- 🪫 **Export/zero-injection helper** — recommend charge/discharge blocks using market or consumer prices
- 🚨 **Price alerts service** — threshold, negative-price and top-N cheapest period detection
- 🧱 **Dashboard blueprint generator** — generate a ready-to-paste dashboard YAML snippet
- 🌍 **Multiple delivery areas** — configure one or more simultaneously
- 💱 **Configurable currency** — EUR (default), BGN, DKK, NOK, PLN, RON, SEK
- 🌐 **Dutch & English UI** — full translation of config flow, options and service labels
- ⚙️ **All settings editable** after installation via the HA integration options flow

---

## Installation via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** → **Custom repositories**
3. Add `https://github.com/aritmeester/nordpool-dayahead` as type **Integration**
4. Search for **Nord Pool Day-Ahead** and install
5. Restart Home Assistant
6. Go to **Settings → Integrations → Add Integration** and search for **Nord Pool Day-Ahead Prices**

---

## Configuration

The integration is configured entirely via the UI (Config Flow) in per-area steps.

### Step 1 — Area & Currency

| Field | Description | Default |
|-------|-------------|---------|
| Delivery Area(s) | One or more area codes from the list below | NL |
| Currency | BGN, DKK, EUR, NOK, PLN, RON, SEK | EUR |

### Step 2 (per area) — Sensor options & consumer toggle

For each selected area, configure:

| Field | Description | Default |
|-------|-------------|---------|
| Also provide prices per kWh | Expose prices per kWh alongside /MWh for this area | ✅ |
| Also provide hourly prices | Create hourly-average sensors for this area | ✅ |
| Enable consumer price | Enable consumer-price sensors/services for this area | ✅ |

### Step 3 (conditional, per area) — Consumer price rates

Only shown when **Enable consumer price** is on for that area.

| Field | Description | Default (NL / Zonneplan) |
|-------|-------------|--------------------------|
| Energy tax | Per kWh — Dutch energiebelasting | 0.09161 |
| Supplier markup | Per kWh — inkoopvergoeding | 0.016529 |
| VAT rate | Fraction — e.g. 0.21 for 21% BTW | 0.21 |

**Consumer price formula (per kWh):**
```
consumer_price = (market_kwh + energy_tax + supplier_markup) × (1 + VAT)
```

All settings can be changed later via **Settings → Integrations → Nord Pool Day-Ahead → Configure**.

---

## Delivery Areas

| Group | Area codes |
|-------|-----------|
| Baltic | EE, LT, LV |
| CWE (Central Western Europe) | AT, BE, FR, GER, NL, PL |
| Nordic | DK1, DK2, FI, NO1, NO2, NO3, NO4, NO5, SE1, SE2, SE3, SE4 |
| SEE (South East Europe) | BG, TEL |

---

## Sensors

For each configured area and day (`today` / `tomorrow`), sensors are created for each enabled combination of price type, unit and resolution.

### Current price sensors (enabled by default)

| Combination | Example entity ID |
|-------------|-------------------|
| Market · Quarter-hour · MWh | `sensor.nordpool_nl_today_market_quarter_hour_mwh` |
| Market · Quarter-hour · kWh | `sensor.nordpool_nl_today_market_quarter_hour_kwh` |
| Market · Hourly · MWh | `sensor.nordpool_nl_today_market_hourly_mwh` |
| Market · Hourly · kWh | `sensor.nordpool_nl_today_market_hourly_kwh` |
| Consumer · Quarter-hour · kWh | `sensor.nordpool_nl_today_consumer_quarter_hour_kwh` |
| … | |

The sensor **state** is always the price active at the current moment (for `today`).
The sensor switches to the next value **exactly** at the quarter/hour boundary using an internal timer.

For `tomorrow`, the current-price sensor shows the price at **tomorrow on the same local time** (same hour/quarter as now), with fallback to the first available tomorrow slot.

Each sensor exposes a `prices` attribute containing the full day schedule:
```yaml
prices:
  - startTime: "2026-02-18T06:00:00+00:00"
    endTime:   "2026-02-18T06:15:00+00:00"
    price: 0.133530
  - …
```

When block aggregates are available (Off-peak 1, Peak, Off-peak 2), they are included as a `block_aggregates` attribute:
```yaml
block_aggregates:
  - blockName: "Off-peak 1"
    deliveryStart: "…"
    deliveryEnd: "…"
    average: 0.09950
    min: 0.08247
    max: 0.18867
```

### Statistic sensors (disabled by default)

Min, max and average sensors exist for every price/unit/resolution combination but are **disabled in the entity registry** by default. Enable them individually via **Settings → Entities**.

| Statistic | Example entity ID |
|-----------|-------------------|
| Daily minimum | `sensor.nordpool_nl_today_market_quarter_hour_mwh_min` |
| Daily maximum | `sensor.nordpool_nl_today_market_quarter_hour_mwh_max` |
| Daily average | `sensor.nordpool_nl_today_market_quarter_hour_mwh_average` |

### Binary sensor

| Sensor | `on` | `off` |
|--------|------|-------|
| `binary_sensor.nordpool_nl_tomorrow_prices_final` | Tomorrow's prices are confirmed Final | Not yet available or still Preliminary |

### API diagnostics sensors (disabled by default)

Per area and per day (`today`, `tomorrow`), a diagnostic timestamp sensor is available (disabled in registry by default):

| Sensor | State | Attributes |
|--------|-------|------------|
| `sensor.nordpool_nl_today_api_diagnostics` | Last successful API fetch time | `status`, `delivery_date_cet`, `api_updated_at`, `api_version`, `area`, `day` |
| `sensor.nordpool_nl_tomorrow_api_diagnostics` | Last successful API fetch time | `status`, `delivery_date_cet`, `api_updated_at`, `api_version`, `area`, `day` |

---

## Service: `nordpool_dayahead.get_cheapest_blocks`

Find the cheapest price window in the day. Returns structured data usable in automations.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `area` | string | required | Delivery area code, e.g. `NL` |
| `day` | select | `today` | `today` or `tomorrow` |
| `resolution` | select | `quarter` | `quarter` (15 min) or `hour` (60 min) |
| `price_type` | select | `market` | `market` or `consumer` |
| `n_blocks` | integer | `4` | Number of blocks to find (4 quarters = 1 hour). Max: `96` for quarter, `24` for hour |
| `contiguous` | boolean | `true` | Find cheapest consecutive window (`true`) or cheapest individual slots (`false`) |

### Example: cheapest 1-hour window today

```yaml
service: nordpool_dayahead.get_cheapest_blocks
data:
  area: NL
  day: today
  resolution: quarter
  n_blocks: 4
  contiguous: true
```

### Example response

```yaml
area: NL
day: today
resolution: quarter
price_type: market
contiguous: true
n_blocks: 4
total_duration_minutes: 60
average_price_kwh: 0.03748
status: Final
delivery_date: "2026-02-18"
blocks:
  - startTime: "2026-02-18T14:00:00Z"
    endTime:   "2026-02-18T14:15:00Z"
    price_kwh: 0.03748
  - …
```

## Advanced services

### `nordpool_dayahead.forecast_device_cost`

Forecast expected cost for a device load.

```yaml
service: nordpool_dayahead.forecast_device_cost
data:
  area: NL
  day: today
  resolution: hour
  price_type: consumer
  n_blocks: 3
  contiguous: true
  power_kw: 3.7
```

### `nordpool_dayahead.get_best_next_window`

Returns the best upcoming window with direct `window_start` and `window_end` output.

```yaml
service: nordpool_dayahead.get_best_next_window
data:
  area: NL
  resolution: hour
  price_type: market
  n_blocks: 2
  contiguous: true
  power_kw: 2.5
  search_scope: today_or_tomorrow
```

### `nordpool_dayahead.generate_template_package`

Generates ready-to-paste YAML snippets for EV/dishwasher/boiler scenarios.

```yaml
service: nordpool_dayahead.generate_template_package
data:
  area: NL
  device: ev
  price_type: consumer
  resolution: hour
  n_blocks: 3
  power_kw: 3.7
```

### `nordpool_dayahead.generate_dashboard_blueprint`

Generates a ready-to-paste dashboard YAML snippet with quarter/hour switch and area graph entities.

```yaml
service: nordpool_dayahead.generate_dashboard_blueprint
data:
  areas: NL,DK1,SE3   # optional; omit to use all configured areas
  day: today
  price_type: market
  unit: kwh
```

### `nordpool_dayahead.get_export_strategy`

Helper for battery/solar strategies (zero-injection and export-limit behavior).

```yaml
service: nordpool_dayahead.get_export_strategy
data:
  area: NL
  day: tomorrow
  resolution: quarter
  price_type: consumer
  charge_blocks: 6
  discharge_blocks: 4
  charge_mode: negative_or_lowest
```

### `nordpool_dayahead.get_price_alerts`

Returns threshold/negative/top-N alert matches for notification automations.

```yaml
service: nordpool_dayahead.get_price_alerts
data:
  area: NL
  day: today
  resolution: hour
  price_type: market
  threshold_kwh: 0.08
  top_n: 3
  include_negative: true
```

## Automation recipes

### EV charging based on `get_best_next_window`

```yaml
automation:
  - alias: "EV charge in best next window"
    trigger:
      - platform: time_pattern
        minutes: "/15"
    action:
      - service: nordpool_dayahead.get_best_next_window
        data:
          area: NL
          resolution: hour
          price_type: consumer
          n_blocks: 2
          contiguous: true
          power_kw: 3.7
          search_scope: today_or_tomorrow
        response_variable: best
      - variables:
          now_ts: "{{ as_timestamp(now()) }}"
          start_ts: "{{ as_timestamp(best.window_start) if best is defined else none }}"
          end_ts: "{{ as_timestamp(best.window_end) if best is defined else none }}"
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ start_ts is not none and end_ts is not none and start_ts <= now_ts < end_ts }}"
            sequence:
              - service: switch.turn_on
                target:
                  entity_id: switch.car_charger
        default:
          - service: switch.turn_off
            target:
              entity_id: switch.car_charger
```

### Price alert notifications based on `get_price_alerts`

```yaml
automation:
  - alias: "Nord Pool price alerts"
    trigger:
      - platform: time
        at: "13:05:00"
    action:
      - service: nordpool_dayahead.get_price_alerts
        data:
          area: NL
          day: tomorrow
          resolution: hour
          price_type: market
          threshold_kwh: 0.08
          top_n: 3
          include_negative: true
        response_variable: alerts
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ alerts.negative_triggered }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "Nord Pool alert"
                  message: "Negative prices detected tomorrow for NL."
          - conditions:
              - condition: template
                value_template: "{{ alerts.threshold_triggered }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "Nord Pool alert"
                  message: >-
                    Prices below {{ alerts.threshold_kwh }} {{ states('sensor.nordpool_nl_today_market_hourly_kwh') | regex_replace(find='[0-9\\.-]+', replace='') }} detected tomorrow.
        default:
          - service: notify.mobile_app_phone
            data:
              title: "Nord Pool overview"
              message: >-
                No threshold/negative alerts for tomorrow.
```

### Use in an automation (uses service response)

```yaml
automation:
  - alias: "Charge car only during cheapest 3 hours"
    trigger:
      - platform: time_pattern
        minutes: "/15"
    action:
      - service: nordpool_dayahead.get_cheapest_blocks
        data:
          area: NL
          day: today
          resolution: hour
          n_blocks: 3
          contiguous: true
        response_variable: cheapest
      - variables:
          in_cheapest_window: >
            {% set now_ts = as_timestamp(now()) %}
            {% set ns = namespace(match=false) %}
            {% for block in cheapest.blocks %}
              {% set start_ts = as_timestamp(block.startTime) %}
              {% set end_ts = as_timestamp(block.endTime) %}
              {% if start_ts <= now_ts < end_ts %}
                {% set ns.match = true %}
              {% endif %}
            {% endfor %}
            {{ ns.match }}
      - choose:
          - conditions: "{{ in_cheapest_window }}"
            sequence:
              - service: switch.turn_on
                target:
                  entity_id: switch.car_charger
        default:
          - service: switch.turn_off
            target:
              entity_id: switch.car_charger
```

---

## Dashboard example: interactive graph (quarter/hour + area toggles)

This example uses the **ApexCharts Card** (HACS) and lets the user:
- switch between **quarter-hour** and **hourly** graphs
- turn each area **on/off** with toggles

### 1) Create helpers

Add these helpers in **Settings → Devices & Services → Helpers**:
- `input_select.nordpool_graph_resolution` with options: `quarter`, `hour`
- `input_boolean.nordpool_show_nl`
- `input_boolean.nordpool_show_dk1`
- `input_boolean.nordpool_show_se3`

### 2) Add this dashboard YAML

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Nord Pool graph controls
    entities:
      - entity: input_select.nordpool_graph_resolution
        name: Resolution
      - entity: input_boolean.nordpool_show_nl
        name: Show NL
      - entity: input_boolean.nordpool_show_dk1
        name: Show DK1
      - entity: input_boolean.nordpool_show_se3
        name: Show SE3

  # Quarter-hour graphs
  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: quarter
      - entity: input_boolean.nordpool_show_nl
        state: "on"
    card:
      type: custom:apexcharts-card
      graph_span: 24h
      header:
        title: NL · Quarter-hour · Market kWh (today)
      series:
        - entity: sensor.nordpool_nl_today_market_quarter_hour_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: quarter
      - entity: input_boolean.nordpool_show_dk1
        state: "on"
    card:
      type: custom:apexcharts-card
      graph_span: 24h
      header:
        title: DK1 · Quarter-hour · Market kWh (today)
      series:
        - entity: sensor.nordpool_dk1_today_market_quarter_hour_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: quarter
      - entity: input_boolean.nordpool_show_se3
        state: "on"
    card:
      type: custom:apexcharts-card
      graph_span: 24h
      header:
        title: SE3 · Quarter-hour · Market kWh (today)
      series:
        - entity: sensor.nordpool_se3_today_market_quarter_hour_kwh

  # Hourly graphs
  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: hour
      - entity: input_boolean.nordpool_show_nl
        state: "on"
    card:
      type: custom:apexcharts-card
      graph_span: 24h
      header:
        title: NL · Hourly · Market kWh (today)
      series:
        - entity: sensor.nordpool_nl_today_market_hourly_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: hour
      - entity: input_boolean.nordpool_show_dk1
        state: "on"
    card:
      type: custom:apexcharts-card
      graph_span: 24h
      header:
        title: DK1 · Hourly · Market kWh (today)
      series:
        - entity: sensor.nordpool_dk1_today_market_hourly_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: hour
      - entity: input_boolean.nordpool_show_se3
        state: "on"
    card:
      type: custom:apexcharts-card
      graph_span: 24h
      header:
        title: SE3 · Hourly · Market kWh (today)
      series:
        - entity: sensor.nordpool_se3_today_market_hourly_kwh
```

> Replace areas/entity IDs with the areas you configured.

### Alternative: built-in cards only (no custom cards)

If you prefer not to install ApexCharts, you can use only built-in cards.
This keeps the same controls (`resolution` + area toggles) and uses `history-graph`.

```yaml
type: vertical-stack
cards:
  - type: entities
    title: Nord Pool graph controls
    entities:
      - entity: input_select.nordpool_graph_resolution
        name: Resolution
      - entity: input_boolean.nordpool_show_nl
        name: Show NL
      - entity: input_boolean.nordpool_show_dk1
        name: Show DK1
      - entity: input_boolean.nordpool_show_se3
        name: Show SE3

  # Quarter-hour graphs
  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: quarter
      - entity: input_boolean.nordpool_show_nl
        state: "on"
    card:
      type: history-graph
      title: NL · Quarter-hour · Market kWh (today)
      hours_to_show: 24
      entities:
        - entity: sensor.nordpool_nl_today_market_quarter_hour_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: quarter
      - entity: input_boolean.nordpool_show_dk1
        state: "on"
    card:
      type: history-graph
      title: DK1 · Quarter-hour · Market kWh (today)
      hours_to_show: 24
      entities:
        - entity: sensor.nordpool_dk1_today_market_quarter_hour_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: quarter
      - entity: input_boolean.nordpool_show_se3
        state: "on"
    card:
      type: history-graph
      title: SE3 · Quarter-hour · Market kWh (today)
      hours_to_show: 24
      entities:
        - entity: sensor.nordpool_se3_today_market_quarter_hour_kwh

  # Hourly graphs
  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: hour
      - entity: input_boolean.nordpool_show_nl
        state: "on"
    card:
      type: history-graph
      title: NL · Hourly · Market kWh (today)
      hours_to_show: 24
      entities:
        - entity: sensor.nordpool_nl_today_market_hourly_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: hour
      - entity: input_boolean.nordpool_show_dk1
        state: "on"
    card:
      type: history-graph
      title: DK1 · Hourly · Market kWh (today)
      hours_to_show: 24
      entities:
        - entity: sensor.nordpool_dk1_today_market_hourly_kwh

  - type: conditional
    conditions:
      - entity: input_select.nordpool_graph_resolution
        state: hour
      - entity: input_boolean.nordpool_show_se3
        state: "on"
    card:
      type: history-graph
      title: SE3 · Hourly · Market kWh (today)
      hours_to_show: 24
      entities:
        - entity: sensor.nordpool_se3_today_market_hourly_kwh
```

---

## EVCC integration (consumer price, today + tomorrow)

You can let EVCC read prices from this Home Assistant integration, including:
- combined **today + tomorrow** forecast
- **consumer price** (instead of market price)

Approach:
1. Create a Home Assistant template sensor that combines both `prices` arrays.
2. Configure EVCC `tariffs.grid.type: custom` with HTTP + `jq` mapping.

### 1) Home Assistant bridge sensor

```yaml
template:
  - sensor:
      - name: nordpool_evcc_consumer_forecast_nl
        unique_id: nordpool_evcc_consumer_forecast_nl
        state: "{{ now().isoformat() }}"
        attributes:
          prices: >
            {% set t = state_attr('sensor.nordpool_nl_today_consumer_quarter_hour_kwh', 'prices') or [] %}
            {% set m = state_attr('sensor.nordpool_nl_tomorrow_consumer_quarter_hour_kwh', 'prices') or [] %}
            {{ (t + m) | to_json }}
```

### 2) EVCC tariff config

```yaml
tariffs:
  currency: EUR
  grid:
    type: custom

    # current price
    price:
      source: http
      uri: http://<HA_HOST>:8123/api/states/sensor.nordpool_nl_today_consumer_quarter_hour_kwh
      headers:
        Authorization: Bearer <HA_LONG_LIVED_TOKEN>
      jq: ".state | tonumber"

    # forecast (today + tomorrow)
    forecast:
      source: http
      uri: http://<HA_HOST>:8123/api/states/sensor.nordpool_evcc_consumer_forecast_nl
      headers:
        Authorization: Bearer <HA_LONG_LIVED_TOKEN>
      jq: >
        .attributes.prices
        | fromjson
        | map({
            start: (.startTime | sub("\\+00:00$"; "Z")),
            end:   (.endTime   | sub("\\+00:00$"; "Z")),
            value: .price
          })
```

### Notes

- Use a Home Assistant long-lived token with read access to states.
- If EVCC runs in Docker, avoid `localhost`; use the Home Assistant host/IP reachable from EVCC.
- Test in EVCC with `evcc tariff` to verify forecast parsing.
- For hourly pricing, switch entity IDs from `quarter_hour` to `hourly`.

---

## API usage

| Situation | Frequency |
|-----------|-----------|
| Today's prices | 1 request per area per calendar day |
| Before 13:00 CET | Hourly polling; automatically wakes at/around 13:00 CET |
| Tomorrow ≥ 13:00, status Preliminary | 1 request per area per minute |
| Tomorrow status Final | No further requests until next day |

---

## Enabling debug logging

Add this to your `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.nordpool_dayahead: debug
```

---

## License

[MIT](LICENSE.md) © 2026 Albert Ritmeester ([@aritmeester](https://github.com/aritmeester))
