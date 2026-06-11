# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Placeholder for upcoming changes.

## [v0.1.1] - 2026-06-11

### Added
- Local brand assets required by HACS validation:
  - `custom_components/poolcontrol/brand/icon.png`
  - `custom_components/poolcontrol/brand/logo.png`

### Changed
- Updated `README.md` with improved installation/setup details.
- Sorted `manifest.json` keys to satisfy Hassfest requirements.

### Fixed
- GitHub CI now passes on `main` for both Hassfest and HACS validation.

## [v0.1.0] - 2026-06-11

### Added
- Initial public release of `poolcontrol` custom integration.
- TCP frame decoding for Pro Logic bridge traffic.
- Focused entity model for pool operations:
  - sensors (air temp, pool temp, day/time, panel display lines/raw)
  - binary sensors for key LEDs/modes
  - switches for lights, AUX2 (turbo), AUX3 (heater)
  - filter mode select with cyclic state machine
  - momentary panel key buttons (`+`, `-`, `<`, `>`, `Menu`, `Mode`)
- Companion YAML dashboard: `dashboards/pool.yaml`.
- Publication metadata and CI:
  - `hacs.json`
  - `.github/workflows/hassfest.yaml`
  - `.github/workflows/hacs.yaml`

[Unreleased]: https://github.com/aircable/PoolControl/compare/v0.1.1...HEAD
[v0.1.1]: https://github.com/aircable/PoolControl/compare/v0.1.0...v0.1.1
[v0.1.0]: https://github.com/aircable/PoolControl/releases/tag/v0.1.0
