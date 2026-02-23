"""Price calculation utilities for Nordpool Day-Ahead integration."""
from __future__ import annotations


def mwh_to_kwh(price_per_mwh: float | None) -> float | None:
    """Convert €/MWh to €/kWh."""
    if price_per_mwh is None:
        return None
    return price_per_mwh / 1000.0


def consumer_price_kwh(
    market_price_kwh: float | None,
    energy_tax: float,
    supplier_markup: float,
    vat: float,
) -> float | None:
    """
    Calculate the consumer price per kWh.

    Formula:
        (market_price_kwh + energy_tax + supplier_markup) * (1 + vat)
    """
    if market_price_kwh is None:
        return None
    excl_vat = market_price_kwh + energy_tax + supplier_markup
    return excl_vat * (1 + vat)


def consumer_price_mwh(
    market_price_mwh: float | None,
    energy_tax: float,
    supplier_markup: float,
    vat: float,
) -> float | None:
    """
    Calculate the consumer price per MWh.

    Converts energy_tax and supplier_markup (given per kWh) to /MWh for consistency.
    """
    if market_price_mwh is None:
        return None
    energy_tax_mwh = energy_tax * 1000
    markup_mwh = supplier_markup * 1000
    excl_vat = market_price_mwh + energy_tax_mwh + markup_mwh
    return excl_vat * (1 + vat)


def build_price_rows(
    rows: list[dict],
    enable_kwh: bool,
    consumer_price_enabled: bool,
    energy_tax: float,
    supplier_markup: float,
    vat: float,
) -> list[dict]:
    """
    Enrich raw API price rows with kWh and consumer price variants.

    Each row already has: startTime, endTime, value (€/MWh)
    We add: value_kwh, consumer_mwh, consumer_kwh
    """
    result = []
    for row in rows:
        mwh_price = row.get("value")
        enriched = {
            "startTime": row.get("startTime"),
            "endTime": row.get("endTime"),
            "market_mwh": round(mwh_price, 5) if mwh_price is not None else None,
        }

        if enable_kwh:
            kwh_price = mwh_to_kwh(mwh_price)
            enriched["market_kwh"] = round(kwh_price, 6) if kwh_price is not None else None
        else:
            enriched["market_kwh"] = None

        if consumer_price_enabled:
            c_mwh = consumer_price_mwh(mwh_price, energy_tax, supplier_markup, vat)
            enriched["consumer_mwh"] = round(c_mwh, 5) if c_mwh is not None else None

            if enable_kwh:
                c_kwh = consumer_price_kwh(
                    mwh_to_kwh(mwh_price), energy_tax, supplier_markup, vat
                )
                enriched["consumer_kwh"] = round(c_kwh, 6) if c_kwh is not None else None
            else:
                enriched["consumer_kwh"] = None
        else:
            enriched["consumer_mwh"] = None
            enriched["consumer_kwh"] = None

        result.append(enriched)
    return result
