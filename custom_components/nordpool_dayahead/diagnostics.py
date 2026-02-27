"""Diagnostics support for Nordpool Day-Ahead integration."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import NordpoolCoordinator

TO_REDACT: set[str] = set()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator: NordpoolCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    diagnostics: dict = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "title": entry.title,
            "domain": entry.domain,
            "source": entry.source,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
    }

    if coordinator is None:
        diagnostics["coordinator"] = None
        diagnostics["note"] = "Coordinator not loaded for this config entry"
        return async_redact_data(diagnostics, TO_REDACT)

    diagnostics["coordinator"] = coordinator.get_diagnostics_snapshot()
    return async_redact_data(diagnostics, TO_REDACT)
