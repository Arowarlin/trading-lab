# RESULTADO · CFD-006 nueva cuenta Trial y reglas verificadas

Fecha: 2026-11-23. Attach-only: no se envió ninguna orden, no se hizo login ni
logout, no se leyó ni escribió ninguna contraseña, no se tocaron tareas
programadas, campañas, OOS, archivos protegidos ni el carril del EA.

## 1. Cuenta

`config/propfund/accounts.yaml` · CFD-006:

- Login anterior **40000453530** → nuevo **40000459328**.
- Servidor `FundingPips-Trial`; mismo terminal
  `C:\Program Files\Darwinex MetaTrader 5\terminal64.exe`.
- Nota añadida: la cuenta anterior fue retirada del panel el 2026-11-23.
- Límites sin cambios: 100.000 USD, pérdida diaria 5.000, pérdida máxima
  10.000 estática, objetivo 8.000, mínimo 3 días, 20 lotes.
- Nota de la cuenta actualizada con el reset (22:00 UTC = 17:00 NY = 00:00
  UTC+2 en invierno) y con la duración máxima del Trial actual: 14 días, fin
  **2026-12-07**.

Referencias al login viejo actualizadas también en
`tests/test_propfund_snapshots.py` y `tests/test_propfund_spreads.py`. No queda
ninguna referencia al login anterior en el repo.

## 2. Verificación attach-only

El terminal FundingPips estaba abierto y logueado en la cuenta nueva. Se adjuntó
en modo lectura, sin enviar credenciales:

- Login conectado **40000459328**; servidor **FundingPips-Trial**; modo **demo**;
  `identity_ok: true`; balance y equity **100.000**.
- Offset del servidor detectado: **UTC+2** (`server_utc_offset_hours: 2.0`,
  `offset_source: detectado`).
- Repetida la lectura después de consultar símbolos: mismo login, servidor y
  offset.
- Símbolos visibles y especificaciones leídas:

| Broker | Contract | Tick | Vol min/max | Dígitos |
|---|---:|---:|---|---:|
| NDX100 | 20 | 0.01 | 0.01 / 10 | 2 |
| SPX500 | 50 | 0.01 | 0.01 / 10 | 2 |
| DJI30 | 5 | 0.01 | 0.01 / 10 | 2 |
| XAUUSD | 100 | 0.01 | 0.01 / 5 | 2 |
| EURUSD | 100.000 | 0.00001 | 0.01 / 20 | 5 |
| GBPUSD | 100.000 | 0.00001 | 0.01 / 20 | 5 |
| USDJPY | 100.000 | 0.001 | 0.01 / 10 | 3 |

`symbol_spec` no expone comisión; la comisión de 5 USD/lote en forex y metales
sigue en `firms.yaml` como `needs_verification` (no se inventa).

## 3. Reset y DST

Panel a las 09:57 de Santo Domingo (UTC-4): `Resets in 08:04:39` → 22:00 UTC.
Con offset UTC+2, **00:00 del servidor = 22:00 UTC = 17:00 Nueva York (EST)**.
Coincide con `Etc/GMT-2`.

- Invierno: `Etc/GMT-2` (UTC+2), reset 22:00 UTC = 17:00 NY.
- Verano: si el servidor pasa a UTC+3 por DST, `_rules_from_account` deriva
  `Etc/GMT-3` del offset real y 00:00 = 21:00 UTC = 17:00 NY. Si el servidor
  mantuviera UTC+2 fijo, el reset sería 18:00 NY; hay que verificar el offset
  en el primer cambio de hora. Test añadido para offset +3.

## 4. Reglas del programa Trial

`config/propfund/firms.yaml` · `fundingpips_trial` · `rules_version
2026-11-23.1`:

- `daily_loss_base` y `reset_time` pasan de `needs_verification` a
  **`verified_operator_panel_2026-11-23`**.
- Añadidas `reset_tz: Etc/GMT-2`, `max_duration_days: 14` y
  `trial_end_date: 2026-12-07`, con el mismo estado de panel.
- El estado nuevo se añadió a `VerificationStatus`; `is_verified` lo reconoce
  como verificado y `constraints`/`onboarding` lo muestran con su valor real.
- La comisión y `max_trades_per_day` siguen `needs_verification` porque el panel
  no los muestra.

## 5. Tarea de spreads

`scripts/sync_spreads_daily.ps1` no contiene el login: recorre CFD-001 y CFD-006
y ejecuta `lab propfund sync-spreads --account CFD-006 --measure --days 1
--write`. Al resolver la cuenta desde `accounts.yaml`, usará el login nuevo sin
cambios. **No se modificó ninguna tarea programada ni el script.**

## 6. Comprobaciones

- `pytest -q`: **1698 passed, 1 skipped** (suite completa; después se añadió una
  aserción DST y `tests/test_propfund.py` pasó 24/24).
- `ruff check src/tradinglab tests docs`: limpio.
- `lab propfund verify`: **4 OK**.
- `lab propfund status`: registro válido, componentes protegidos OK.
- `lab propfund onboard CFD-006 --dry-run --no-mt5`: JSON válido.
- `count_tests`: **1730**.

## 7. Commit y cierre

- Commit `d37d295` · `tl2: CFD-006 nueva cuenta trial y reglas verificadas`
- Tag `tl2-cfd006-v2`
- `git status --short`: solo `?? tl2-edge-map.patch`.
- Sin push; sin campañas; sin OOS; sin operar; sin contraseñas.

PARA.
