# PoolControl

Custom Home Assistant integration and dashboard for **Goldline/Hayward Pro Logic automation and chlorination** systems, using a local TCP bridge (for example, [WishMesh RS485 bridge](https://aircable.co/shop/product/acc2901-aircable-rs485-92)).

## What This Repository Includes

- `custom_components/poolcontrol/`: HACS-installable custom integration
- `dashboards/pool.yaml`: YAML Lovelace dashboard for pool operations

## Features

- Live sensors: water temperature, air temperature, panel time/day
- Decoding of two-line panel display text plus raw display payload
- LED/mode state decoding from panel frames (pool, spa, spillover, aux, valve)
- Momentary key buttons (`+`, `-`, `<`, `>`, `Menu`, `Mode`)
- Pump filter cyclic mode control (`Off -> High -> Low -> Off`) with state confirmation
- Controls for lights, AUX2 (turbo), AUX3 (heater)

## Compatibility

- Target controller family: Goldline/Hayward **Pro Logic** automation and chlorination
- Bridge transport: local TCP stream of RS-485 panel frames

## Install (HACS Custom Repository)

1. In HACS, add this GitHub repo as a **Custom repository** of type **Integration**.
2. Download **PoolControl** from HACS.
3. Restart Home Assistant.
4. Add integration: `Settings -> Devices & Services -> Add Integration -> PoolControl`.
5. Enter your bridge host and port (default `3333`).

## Add the Pool Dashboard

1. Copy `dashboards/pool.yaml` into your HA config `dashboards/` directory.
2. Add under `lovelace:` in `configuration.yaml`:

```yaml
lovelace:
  dashboards:
    pool-panel:
      mode: yaml
      title: Pool
      icon: mdi:pool
      show_in_sidebar: true
      require_admin: false
      filename: dashboards/pool.yaml
```

3. Reload Lovelace or restart Home Assistant.

## Notes

- `select.poolcontrol_filter_mode` intentionally enforces cyclic transitions only.
- Low-speed confirmation relies on `FILTER` + `AUX1` LED semantics from panel feedback.

## Support

- Issues: https://github.com/aircable/PoolControl/issues
