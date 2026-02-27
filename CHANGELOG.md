# Changelog

All notable changes to this project are documented in this file.

The format is inspired by Keep a Changelog and uses CalVer tags (for example: `v2026.1.0`).

## [Unreleased]

### Fixed
- Midnight rollover now also performs lazy cache promotion (tomorrow -> today) when `today` is still empty, preventing temporary gaps in current-value sensors right after 00:00.

### Added
- Added detailed debug logging for midnight cache promotion decisions, including successful promotions and explicit skip reasons.

## [v2026.1.5] - 2026-02-25

### Changed
- Daily average stat sensors are now exposed once per price type/unit (quarter-based) to avoid duplicate quarter/hour average values.

### Fixed
- Upgrade cleanup now removes obsolete hourly average stat entities from existing installations.
- Tomorrow-price fetching now starts from 13:00 CE(S)T and continues polling until API status is `Final`.
- At midnight rollover, cached tomorrow data is now promoted to today to prevent empty today-sensor values between 00:00 and the first successful new-day fetch.

### Added
- API diagnostics attributes now include the last requested `api_url` per area/day.

## [v2026.1.4] - 2026-02-24

### Fixed
- Improved coordinator polling around CET/CEST day rollover: when current-day prices are not yet available, the integration now retries every minute instead of waiting up to an hour.
- Improved 13:00 CET/CEST handling for tomorrow prices by validating the cached delivery date before treating data as final, preventing stale final data from delaying new-day fetch retries.
- Aligned hourly polling to local midnight and 13:00 boundaries to reduce missed transition windows.

## [v2026.1.3] - 2026-02-23

### Fixed
- For EUR currency, sensor units now use Home Assistant style `€/kWh` and `€/MWh` instead of `EUR/kWh` and `EUR/MWh`.

## [v2026.1.2] - 2026-02-23

### Fixed
- Removed unsupported `homeassistant` key from integration manifest to satisfy manifest validation.
- Added `CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)` for config-entry-only setup validation.
- Sorted manifest keys in required `domain`, `name`, then alphabetical order.
- Updated HACS manifest (`hacs.json`) to current supported keys.
- Adjusted HACS workflow to ignore external checks `brands`, `description`, and `topics`.

## [v2026.1.1] - 2026-02-23

### Changed
- Consumer price entities are now exposed in kWh only; consumer MWh variants were removed.
- Dashboard blueprint service now validates that consumer prices can only be used with `unit: kwh`.
- README clarified consumer/kWh behavior and release documentation links.

### Added
- Added `CHANGELOG.md` to keep release changes structured.

## [v2026.1.0] - 2026-02-23

### Added
- First public release of the Nordpool Day-Ahead Home Assistant integration.
