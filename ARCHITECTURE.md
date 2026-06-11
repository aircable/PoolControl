# PoolControl Architecture

## Scope

PoolControl is a local Home Assistant custom integration for Pro Logic-class pool controllers. It consumes framed panel data over TCP from a bridge device and provides a focused HA entity model plus an operational Lovelace panel.

## System Context

- Controller: Goldline/Hayward Pro Logic automation/chlorination
- Bridge: RS-485 to TCP forwarder (WishMesh ESP32 implementation)
- Home Assistant integration: `custom_components/poolcontrol`
- Dashboard: `dashboards/pool.yaml`

## Data Flow

1. Bridge forwards raw panel frames over TCP (`host:port`, typically `3333`).
2. `PoolControlTCPClient` receives byte stream and frame scanner extracts DLE/STX framed packets.
3. Parser routes by frame type:
   - `0x0101`: binary status (temps, relays, date/time)
   - `0x0102` / `0x0002`: steady/flashing LED bitfields
   - `0x0103`: two-line panel display text
4. Parsed values merge into runtime state (`PoolControlData`) and dispatch updates to HA entities.

## Entity Model (Intended)

Sensors:
- Air Temperature
- Pool Temperature (single water temp sensor)
- Panel Day
- Panel Time
- Panel Line 1
- Panel Line 2
- Panel Raw Hex

Binary sensors:
- Pool Mode
- Spa Mode
- Spillover
- Lights LED
- AUX2 LED (turbo)
- AUX3 LED (heater)
- Valve 3 LED (waterfall)

Controls:
- Filter Mode (select): `Off -> High -> Low -> Off`
- Lights switch
- AUX2 switch
- AUX3 switch
- Momentary panel key buttons: `Menu`, `<`, `>`, `+`, `-`, `Mode`

## Filter Mode Semantics

Filter mode is modeled as a strict cyclic state machine with live feedback verification:

- `Low` when `FILTER` and `AUX1` LEDs are both on
- `High` when `FILTER` on and `AUX1` off
- `Off` otherwise

Only valid next transition is exposed in the select options to prevent unsupported out-of-order jumps.

## Dashboard Design

`dashboards/pool.yaml` is operational, not decorative:

- Live panel text at top (line 1/line 2 + decoded temps/time/day)
- Keypad block for direct panel navigation and setting changes
- State + control block for mode and actuators
- Temperature history graph

## Validation and Release

Repository includes CI validation for:

- Hassfest (`.github/workflows/hassfest.yaml`)
- HACS validation (`.github/workflows/hacs.yaml`)

Release process targets HACS custom repository distribution for the integration; dashboard YAML is provided as documented companion configuration.
