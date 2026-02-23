# Changelog

All notable changes to this project are documented in this file.

The format is inspired by Keep a Changelog and uses CalVer tags (for example: `v2026.1.0`).

## [Unreleased]

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
