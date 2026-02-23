"""Constants for Nordpool Day-Ahead integration."""

DOMAIN = "nordpool_dayahead"
PLATFORMS = ["sensor", "binary_sensor"]

# API
API_BASE_URL = "https://dataportal-api.nordpoolgroup.com/api/DayAheadPrices"
MARKET = "DayAhead"

# Status
STATUS_PRELIMINARY = "Preliminary"
STATUS_FINAL = "Final"

# Polling intervals (in seconds)
POLL_INTERVAL_TOMORROW_PENDING = 60  # Every minute while tomorrow is still preliminary

# Time at which tomorrow's prices become available (CET/CEST)
TOMORROW_PRICES_HOUR_CET = 13  # 13:00 CET

# Delivery areas grouped
DELIVERY_AREAS = {
    "Baltic": ["EE", "LT", "LV"],
    "CWE": ["AT", "BE", "FR", "GER", "NL", "PL"],
    "Nordic": ["DK1", "DK2", "FI", "NO1", "NO2", "NO3", "NO4", "NO5", "SE1", "SE2", "SE3", "SE4"],
    "SEE": ["BG", "TEL"],
}

ALL_DELIVERY_AREAS = [area for areas in DELIVERY_AREAS.values() for area in areas]

DELIVERY_AREA_LABELS = {
    "EE": "Estonia",
    "LT": "Lithuania",
    "LV": "Latvia",
    "AT": "Austria",
    "BE": "Belgium",
    "FR": "France",
    "GER": "Germany",
    "NL": "Netherlands",
    "PL": "Poland",
    "DK1": "Denmark 1",
    "DK2": "Denmark 2",
    "FI": "Finland",
    "NO1": "Norway 1",
    "NO2": "Norway 2",
    "NO3": "Norway 3",
    "NO4": "Norway 4",
    "NO5": "Norway 5",
    "SE1": "Sweden 1",
    "SE2": "Sweden 2",
    "SE3": "Sweden 3",
    "SE4": "Sweden 4",
    "BG": "Bulgaria",
    "TEL": "TEL",
}

# Currencies
CURRENCIES = ["BGN", "DKK", "EUR", "NOK", "PLN", "RON", "SEK"]
DEFAULT_CURRENCY = "EUR"

# Config keys
CONF_DELIVERY_AREAS = "delivery_areas"
CONF_CURRENCY = "currency"
CONF_ENABLE_KWH = "enable_kwh"
CONF_ENABLE_HOURLY = "enable_hourly"
CONF_CONSUMER_PRICE_ENABLED = "consumer_price_enabled"
CONF_ENERGY_TAX = "energy_tax"            # per kWh
CONF_SUPPLIER_MARKUP = "supplier_markup"  # per kWh
CONF_VAT = "vat"                          # fraction, e.g. 0.21
CONF_CONSUMER_SETTINGS = "consumer_settings"  # per area map

# Defaults for consumer price (NL / Zonneplan example)
DEFAULT_ENERGY_TAX = 0.09161
DEFAULT_SUPPLIER_MARKUP = 0.0165289256198347
DEFAULT_VAT = 0.21

# Coordinator keys
COORDINATOR_TODAY = "today"
COORDINATOR_TOMORROW = "tomorrow"
