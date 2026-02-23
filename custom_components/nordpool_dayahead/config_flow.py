"""Config flow for Nordpool Day-Ahead integration."""
from __future__ import annotations

import asyncio
from copy import deepcopy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    ALL_DELIVERY_AREAS,
    DELIVERY_AREA_LABELS,
    CURRENCIES,
    DEFAULT_CURRENCY,
    DEFAULT_ENERGY_TAX,
    DEFAULT_SUPPLIER_MARKUP,
    DEFAULT_VAT,
    CONF_DELIVERY_AREAS,
    CONF_CURRENCY,
    CONF_ENABLE_KWH,
    CONF_ENABLE_HOURLY,
    CONF_CONSUMER_PRICE_ENABLED,
    CONF_ENERGY_TAX,
    CONF_SUPPLIER_MARKUP,
    CONF_VAT,
    CONF_CONSUMER_SETTINGS,
)


def _consumer_basic_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ENABLE_KWH,
                default=defaults.get(CONF_ENABLE_KWH, True),
            ): bool,
            vol.Required(
                CONF_ENABLE_HOURLY,
                default=defaults.get(CONF_ENABLE_HOURLY, True),
            ): bool,
            vol.Required(
                CONF_CONSUMER_PRICE_ENABLED,
                default=defaults.get(CONF_CONSUMER_PRICE_ENABLED, True),
            ): bool,
        }
    )


def _consumer_rates_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_ENERGY_TAX,
                default=defaults.get(CONF_ENERGY_TAX, DEFAULT_ENERGY_TAX),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Required(
                CONF_SUPPLIER_MARKUP,
                default=defaults.get(CONF_SUPPLIER_MARKUP, DEFAULT_SUPPLIER_MARKUP),
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Required(
                CONF_VAT,
                default=defaults.get(CONF_VAT, DEFAULT_VAT),
            ): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
        }
    )


def _consumer_defaults_for_area(defaults: dict, area: str) -> dict:
    """Resolve consumer defaults for one area with legacy fallback."""
    per_area = defaults.get(CONF_CONSUMER_SETTINGS, {})
    if isinstance(per_area, dict):
        area_data = per_area.get(area)
        if isinstance(area_data, dict):
            return {
                CONF_ENABLE_KWH: area_data.get(CONF_ENABLE_KWH, True),
                CONF_ENABLE_HOURLY: area_data.get(CONF_ENABLE_HOURLY, True),
                CONF_CONSUMER_PRICE_ENABLED: area_data.get(CONF_CONSUMER_PRICE_ENABLED, True),
                CONF_ENERGY_TAX: area_data.get(CONF_ENERGY_TAX, DEFAULT_ENERGY_TAX),
                CONF_SUPPLIER_MARKUP: area_data.get(CONF_SUPPLIER_MARKUP, DEFAULT_SUPPLIER_MARKUP),
                CONF_VAT: area_data.get(CONF_VAT, DEFAULT_VAT),
            }

    return {
        CONF_ENABLE_KWH: defaults.get(CONF_ENABLE_KWH, True),
        CONF_ENABLE_HOURLY: defaults.get(CONF_ENABLE_HOURLY, True),
        CONF_CONSUMER_PRICE_ENABLED: defaults.get(CONF_CONSUMER_PRICE_ENABLED, True),
        CONF_ENERGY_TAX: defaults.get(CONF_ENERGY_TAX, DEFAULT_ENERGY_TAX),
        CONF_SUPPLIER_MARKUP: defaults.get(CONF_SUPPLIER_MARKUP, DEFAULT_SUPPLIER_MARKUP),
        CONF_VAT: defaults.get(CONF_VAT, DEFAULT_VAT),
    }


def _delivery_area_selector() -> selector.SelectSelector:
    """Build selector for selecting one or more delivery areas."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=area, label=DELIVERY_AREA_LABELS.get(area, area))
                for area in ALL_DELIVERY_AREAS
            ],
            multiple=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _build_entry_title(areas: list[str]) -> str:
    """Build config entry title from selected delivery areas."""
    return f"Nord Pool ({', '.join(areas)})"


class NordpoolDayAheadConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Nordpool Day-Ahead."""

    VERSION = 1
    _user_input: dict = {}
    _areas: list[str] = []
    _consumer_index: int = 0

    async def _async_finish_or_next_consumer_area(self) -> FlowResult:
        """Continue with next area or finish config entry creation."""
        if self._consumer_index < len(self._areas) - 1:
            self._consumer_index += 1
            return await self.async_step_consumer()

        areas = self._user_input.get(CONF_DELIVERY_AREAS, ["NL"])
        title = _build_entry_title(areas)

        self._user_input.pop(CONF_CONSUMER_PRICE_ENABLED, None)
        self._user_input.pop(CONF_ENABLE_KWH, None)
        self._user_input.pop(CONF_ENABLE_HOURLY, None)
        self._user_input.pop(CONF_ENERGY_TAX, None)
        self._user_input.pop(CONF_SUPPLIER_MARKUP, None)
        self._user_input.pop(CONF_VAT, None)
        return self.async_create_entry(title=title, data=self._user_input)

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Step 1: Delivery area, currency and basic options."""
        errors: dict = {}

        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            if not user_input.get(CONF_DELIVERY_AREAS):
                errors[CONF_DELIVERY_AREAS] = "no_area_selected"
            else:
                self._user_input.update(user_input)
                self._areas = list(user_input.get(CONF_DELIVERY_AREAS, []))
                self._consumer_index = 0
                self._user_input[CONF_CONSUMER_SETTINGS] = {}
                return await self.async_step_consumer()

        # Build a multi-select via selector
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DELIVERY_AREAS,
                    default=["NL"],
                ): _delivery_area_selector(),
                vol.Required(CONF_CURRENCY, default=DEFAULT_CURRENCY): vol.In(CURRENCIES),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "areas": ", ".join(ALL_DELIVERY_AREAS),
            },
        )

    async def async_step_consumer(self, user_input: dict | None = None) -> FlowResult:
        """Step 2: Consumer price settings per selected area."""
        if not self._areas:
            self._areas = list(self._user_input.get(CONF_DELIVERY_AREAS, []))

        if not self._areas:
            return await self.async_step_user()

        area = self._areas[self._consumer_index]
        defaults = _consumer_defaults_for_area(self._user_input, area)

        if user_input is not None:
            settings = self._user_input.setdefault(CONF_CONSUMER_SETTINGS, {})
            area_settings = settings.setdefault(area, {})
            area_settings.update(
                {
                CONF_ENABLE_KWH: user_input[CONF_ENABLE_KWH],
                CONF_ENABLE_HOURLY: user_input[CONF_ENABLE_HOURLY],
                CONF_CONSUMER_PRICE_ENABLED: user_input[CONF_CONSUMER_PRICE_ENABLED],
                }
            )

            if user_input[CONF_CONSUMER_PRICE_ENABLED]:
                area_settings.setdefault(CONF_ENERGY_TAX, defaults[CONF_ENERGY_TAX])
                area_settings.setdefault(CONF_SUPPLIER_MARKUP, defaults[CONF_SUPPLIER_MARKUP])
                area_settings.setdefault(CONF_VAT, defaults[CONF_VAT])
                return await self.async_step_consumer_rates()

            area_settings[CONF_ENERGY_TAX] = defaults[CONF_ENERGY_TAX]
            area_settings[CONF_SUPPLIER_MARKUP] = defaults[CONF_SUPPLIER_MARKUP]
            area_settings[CONF_VAT] = defaults[CONF_VAT]
            return await self._async_finish_or_next_consumer_area()

        return self.async_show_form(
            step_id="consumer",
            data_schema=_consumer_basic_schema(defaults),
            description_placeholders={
                "area": area,
                "area_label": DELIVERY_AREA_LABELS.get(area, area),
                "index": str(self._consumer_index + 1),
                "total": str(len(self._areas)),
            },
        )

    async def async_step_consumer_rates(self, user_input: dict | None = None) -> FlowResult:
        """Step 3: Detailed consumer rates for the current selected area."""
        area = self._areas[self._consumer_index]
        defaults = _consumer_defaults_for_area(self._user_input, area)

        if user_input is not None:
            settings = self._user_input.setdefault(CONF_CONSUMER_SETTINGS, {})
            area_settings = settings.setdefault(area, {})
            area_settings.update(
                {
                    CONF_ENERGY_TAX: user_input[CONF_ENERGY_TAX],
                    CONF_SUPPLIER_MARKUP: user_input[CONF_SUPPLIER_MARKUP],
                    CONF_VAT: user_input[CONF_VAT],
                }
            )
            return await self._async_finish_or_next_consumer_area()

        return self.async_show_form(
            step_id="consumer_rates",
            data_schema=_consumer_rates_schema(defaults),
            description_placeholders={
                "area": area,
                "area_label": DELIVERY_AREA_LABELS.get(area, area),
                "index": str(self._consumer_index + 1),
                "total": str(len(self._areas)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return NordpoolOptionsFlow(config_entry)


class NordpoolOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Options flow to reconfigure after initial setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        super().__init__(config_entry)
        self._input: dict = {}
        self._areas: list[str] = []
        self._consumer_index: int = 0

    async def _async_delayed_reload(self) -> None:
        """Fallback reload after options are persisted."""
        await asyncio.sleep(0)
        entry = self.hass.config_entries.async_get_entry(self.config_entry.entry_id)
        if entry is not None:
            merged = {**entry.data, **entry.options}
            areas = merged.get(CONF_DELIVERY_AREAS, ["NL"])
            new_title = _build_entry_title(areas)
            if entry.title != new_title:
                self.hass.config_entries.async_update_entry(entry, title=new_title)

        await self.hass.config_entries.async_reload(self.config_entry.entry_id)

    async def _async_finish_or_next_consumer_area(self) -> FlowResult:
        """Continue with next area or save options."""
        if self._consumer_index < len(self._areas) - 1:
            self._consumer_index += 1
            return await self.async_step_consumer()

        self._input.pop(CONF_CONSUMER_PRICE_ENABLED, None)
        self._input.pop(CONF_ENABLE_KWH, None)
        self._input.pop(CONF_ENABLE_HOURLY, None)
        self._input.pop(CONF_ENERGY_TAX, None)
        self._input.pop(CONF_SUPPLIER_MARKUP, None)
        self._input.pop(CONF_VAT, None)
        self.hass.async_create_task(self._async_delayed_reload())
        return self.async_create_entry(title="", data=self._input)

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Step 1: Basic options."""
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            self._input.update(user_input)
            self._areas = list(self._input.get(CONF_DELIVERY_AREAS, current.get(CONF_DELIVERY_AREAS, ["NL"])))
            self._consumer_index = 0
            if CONF_CONSUMER_SETTINGS not in self._input:
                self._input[CONF_CONSUMER_SETTINGS] = deepcopy(
                    current.get(CONF_CONSUMER_SETTINGS, {})
                )
            return await self.async_step_consumer()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DELIVERY_AREAS,
                    default=current.get(CONF_DELIVERY_AREAS, ["NL"]),
                ): _delivery_area_selector(),
                vol.Required(
                    CONF_CURRENCY,
                    default=current.get(CONF_CURRENCY, DEFAULT_CURRENCY),
                ): vol.In(CURRENCIES),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_consumer(self, user_input: dict | None = None) -> FlowResult:
        """Step 2: Consumer price options per selected area."""
        current = {**self.config_entry.data, **self.config_entry.options, **self._input}
        if not self._areas:
            self._areas = list(current.get(CONF_DELIVERY_AREAS, ["NL"]))

        if not self._areas:
            return await self.async_step_init()

        area = self._areas[self._consumer_index]
        defaults = _consumer_defaults_for_area(current, area)

        if user_input is not None:
            if CONF_CONSUMER_SETTINGS not in self._input:
                self._input[CONF_CONSUMER_SETTINGS] = deepcopy(
                    current.get(CONF_CONSUMER_SETTINGS, {})
                )
            settings = self._input[CONF_CONSUMER_SETTINGS]
            area_settings = settings.setdefault(area, {})
            area_settings.update(
                {
                CONF_ENABLE_KWH: user_input[CONF_ENABLE_KWH],
                CONF_ENABLE_HOURLY: user_input[CONF_ENABLE_HOURLY],
                CONF_CONSUMER_PRICE_ENABLED: user_input[CONF_CONSUMER_PRICE_ENABLED],
                }
            )

            if user_input[CONF_CONSUMER_PRICE_ENABLED]:
                area_settings.setdefault(CONF_ENERGY_TAX, defaults[CONF_ENERGY_TAX])
                area_settings.setdefault(CONF_SUPPLIER_MARKUP, defaults[CONF_SUPPLIER_MARKUP])
                area_settings.setdefault(CONF_VAT, defaults[CONF_VAT])
                return await self.async_step_consumer_rates()

            area_settings[CONF_ENERGY_TAX] = defaults[CONF_ENERGY_TAX]
            area_settings[CONF_SUPPLIER_MARKUP] = defaults[CONF_SUPPLIER_MARKUP]
            area_settings[CONF_VAT] = defaults[CONF_VAT]
            return await self._async_finish_or_next_consumer_area()

        return self.async_show_form(
            step_id="consumer",
            data_schema=_consumer_basic_schema(defaults),
            description_placeholders={
                "area": area,
                "area_label": DELIVERY_AREA_LABELS.get(area, area),
                "index": str(self._consumer_index + 1),
                "total": str(len(self._areas)),
            },
        )

    async def async_step_consumer_rates(self, user_input: dict | None = None) -> FlowResult:
        """Step 3: Detailed consumer rates for the current selected area."""
        current = {**self.config_entry.data, **self.config_entry.options, **self._input}
        area = self._areas[self._consumer_index]
        defaults = _consumer_defaults_for_area(current, area)

        if user_input is not None:
            if CONF_CONSUMER_SETTINGS not in self._input:
                self._input[CONF_CONSUMER_SETTINGS] = deepcopy(
                    current.get(CONF_CONSUMER_SETTINGS, {})
                )
            settings = self._input[CONF_CONSUMER_SETTINGS]
            area_settings = settings.setdefault(area, {})
            area_settings.update(
                {
                    CONF_ENERGY_TAX: user_input[CONF_ENERGY_TAX],
                    CONF_SUPPLIER_MARKUP: user_input[CONF_SUPPLIER_MARKUP],
                    CONF_VAT: user_input[CONF_VAT],
                }
            )
            return await self._async_finish_or_next_consumer_area()

        return self.async_show_form(
            step_id="consumer_rates",
            data_schema=_consumer_rates_schema(defaults),
            description_placeholders={
                "area": area,
                "area_label": DELIVERY_AREA_LABELS.get(area, area),
                "index": str(self._consumer_index + 1),
                "total": str(len(self._areas)),
            },
        )
