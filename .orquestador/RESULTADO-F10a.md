# RESULTADO · F10a · Databento: coste y tubería (sin descargar)

- Fecha: 2026-11-23
- Worktree: `C:\Users\PC\.local\share\opencode\worktree\tl2-f10a`
- Rama: `tl2-f10a`, desde `c684ac9` (`feature/prop-fund-multifirm`)
- Commit: `fdb9294` · tag `tl2-f10a`
- Sin descargas de pago, sin campañas, sin approve/run/confirm/supersede, sin OOS, sin push, sin merge.

## Hecho

1. **Clave.** `DATABENTO_API_KEY` existe en Windows Credential Manager (`tradinglab`, 32 caracteres). Se lee con `keyring`; no se ha impreso ni escrito.
2. **Coste (gratis).** Dataset `GLBX.MDP3`, rango `2010-06-06T00:00:00Z` → `2026-11-23T06:00:48Z` (el fin avanza con el mercado). Se usaron solo `metadata.get_cost`, `metadata.get_record_count` y `metadata.get_billable_size`; **ninguna** llamada a `timeseries.get_range`. Snapshot: 2026-11-23 06:00–06:04 UTC.
3. **Tubería.** `discovery/fetch_databento.py` + `lab discovery fetch-databento`. Por defecto solo estima; `--download` exige `--i-approve-cost USD` y se rechaza antes de cualquier descarga si no coincide al centavo. CSV de Databento → parquet UTC `time/open/high/low/close/volume` en `data/cache/databento/<SÍMBOLO>_M1.parquet` o `_H1.parquet`.
4. **Integración.** `data_sources` acepta `databento`; `usable_from` y `data-check` funcionan con la fuente (tests con fixtures). Sesiones CME declaradas como hipótesis en `engine.yaml`: pausa 17:00–18:00 NY, cierre viernes 17:00, apertura domingo 18:00. Sin calendario de festivos CME (no se inventan).
5. **Verificación.** `ruff` limpio, tests nuevos 17/17, `lab propfund verify` 4 OK, `pytest -q` completo ejecutado una vez (detalle abajo).
6. **Commit/tag.** `fdb9294` · `tl2-f10a`. No push, no merge.

## Tabla de costes

### M1 (`ohlcv-1m`)

| Símbolo | Root | Roll | Registros | Tamaño facturable (GB) | Coste USD |
|---|---|---|---:|---:|---:|
| US100 | NQ | c | 5.480.586 | 0,307 | 20,008438 |
| US500 | ES | c | 5.702.291 | 0,319 | 20,817836 |
| US30 | YM | c | 5.422.077 | 0,304 | 19,794835 |
| XAUUSD | GC | c | 252.648 | 0,014 | 0,922363 |
| EURUSD | 6E | c | 3.483.322 | 0,195 | 12,716858 |
| GBPUSD | 6B | c | 3.133.303 | 0,175 | 11,439014 |
| USDJPY | 6J | c | 3.360.367 | 0,188 | 12,267976 |
| US100 | NQ | v | 5.581.533 | 0,313 | 20,376974 |
| US500 | ES | v | 5.756.323 | 0,322 | 21,015095 |
| US30 | YM | v | 5.544.381 | 0,310 | 20,241340 |
| XAUUSD | GC | v | 5.709.728 | 0,320 | 20,844986 |
| EURUSD | 6E | v | 5.660.024 | 0,317 | 20,663528 |
| GBPUSD | 6B | v | 5.280.053 | 0,296 | 19,276336 |
| USDJPY | 6J | v | 5.609.921 | 0,314 | 20,480613 |
| **TOTAL** | | **c** | **26.834.594** | **1,503** | **97,967320** |
| **TOTAL** | | **v** | **39.141.963** | **2,192** | **142,898872** |

### H1 (`ohlcv-1h`)

| Símbolo | Root | Roll | Registros | Tamaño facturable (GB) | Coste USD |
|---|---|---|---:|---:|---:|
| US100 | NQ | c | 97.591 | 0,005 | 0,967056 |
| US500 | ES | c | 97.633 | 0,005 | 0,967472 |
| US30 | YM | c | 97.683 | 0,005 | 0,967967 |
| XAUUSD | GC | c | 41.013 | 0,002 | 0,406409 |
| EURUSD | 6E | c | 87.607 | 0,005 | 0,868122 |
| GBPUSD | 6B | c | 77.308 | 0,004 | 0,766066 |
| USDJPY | 6J | c | 80.791 | 0,005 | 0,800580 |
| US100 | NQ | v | 98.073 | 0,005 | 0,971832 |
| US500 | ES | v | 98.113 | 0,005 | 0,972228 |
| US30 | YM | v | 98.168 | 0,005 | 0,972773 |
| XAUUSD | GC | v | 98.289 | 0,006 | 0,973972 |
| EURUSD | 6E | v | 97.075 | 0,005 | 0,961943 |
| GBPUSD | 6B | v | 97.050 | 0,005 | 0,961695 |
| USDJPY | 6J | v | 97.055 | 0,005 | 0,961744 |
| **TOTAL** | | **c** | **579.626** | **0,032** | **5,743672** |
| **TOTAL** | | **v** | **683.823** | **0,038** | **6,776188** |

**Qué opción cubre M1 de los 7.** `.c.0` es más barato en total (97,97 USD) pero **no cubre M1**: GC trae 252.648 barras frente a 5,7 M de `.v.0`, y los FX 3,1–3,5 M frente a 5,3–5,7 M. Son series dispersas, no continuas. La opción **más barata que cubre M1 de los 7 con una sola regla es `.v.0` en los 7: 142,898872 USD** (39.141.963 registros, 2,19 GB). Una mezcla `.c.0` en NQ/ES/YM + `.v.0` en GC/6E/6B/6J cuesta 141,886571 USD (1,01 USD menos), pero deja los índices con roll calendario y no es homogénea; no la recomiendo para el primer dataset.

## Tubería y 6J

- Mapeo: `NQ→US100`, `ES→US500`, `YM→US30`, `GC→XAUUSD`, `6E→EURUSD`, `6B→GBPUSD`, `6J→USDJPY`.
- **6J invertido barra a barra** porque 6J cotiza USD por JPY y USDJPY es JPY por USD:
  `open = 1/open_6J`, `high = 1/low_6J`, `low = 1/high_6J`, `close = 1/close_6J`; volumen intacto.
- **Roll:** `.c.0` (calendario) y `.v.0` (volumen). Por defecto `--adjust none`, precios sin ajustar (ejecución y costes). `--adjust back --roll-table JSON` suma la diferencia acumulada de cada roll a las barras anteriores; la tabla es explícita (`diff = nuevo - viejo`), no se deduce de los datos, y exige caché vacía para no mezclar series.
- **Formato:** parquet UTC con índice `time` y columnas `open/high/low/close/volume`, el mismo formato base que Dukascopy (sin ASK porque Databento OHLCV no lo trae).
- **Sesiones CME:** hipótesis declarada en `engine.yaml` (pausa 17:00–18:00 NY, viernes 17:00, domingo 18:00) para los 7 símbolos; se derivará con datos. `data_sources` remuestrea con corte 18:00 NY.

## Verificación

- `ruff check src/tradinglab/discovery tests`: **OK**.
- `tests/test_discovery_fetch_databento.py`: **17 passed** (cliente HTTP simulado, sin red).
- `pytest -q` completo: **1627 passed, 3 skipped, 23 failed** en 467,94 s.
  - **5 fallos por CRLF del worktree** (hashes del EA; no se tocan): `test_ea_forward` (3), `test_ea_lab_candidate` (1), `test_ea_lab_session_equivalence` (1).
  - **18 fallos por datos del entorno ausentes en el worktree**, no por el código:
    - 11 por falta de `data/lab.db` (spreads): `test_discovery_engine` 1, `test_discovery_feasibility` 1, `test_discovery_jobs` 4, `test_discovery_noise` 1, `test_discovery_noise_full` 1, `test_discovery_segments` 1, `test_discovery_spec` 2.
    - 4 por falta de `data/cache`: `test_ai_replay` 4.
    - 3 por falta de `reports/research/latest.json`: `test_optimize` 1, `test_research` 2.
  - Tras copiar al worktree `data/lab.db`, `data/cache` y `reports/research/latest.json` **de solo lectura** desde `E:\trading-lab`, se reejecutaron **los 18 y pasaron los 18** (8 discovery + 4 ai_replay + 1 optimize + 2 research + `test_real_resume_after_kill` + `test_noise_five_campaigns` + `test_full_noise_pipeline_never_level4`; estos 3 últimos, 11:04 min). Queda aislado que ningún fallo es de código: 18 son de datos ausentes en el worktree y 5 son CRLF del EA.
- `lab propfund verify`: **4 OK** (ai_trader, ea_us100_ftmo1, ftmo_forward, ftmo_risk).
- `lab doctor`: sin FAIL; WARN preexistentes (carpeta logs, vendor, reglas de fondeo, IA Londres/Manage).
- `count_tests`: **1730** en la base principal (lectura con `discovery_db`), **1060** en el worktree sin `data/discovery.db`. Esta fase no registra campañas ni lecturas, así que no cambia el contador.

## Recomendación para `OK DESCARGA`

Descargar **M1 con roll por volumen (`.v.0`) de los 7**: **142,90 USD**, 39.141.963 registros y 2,19 GB facturables. Es la opción homogénea que cubre M1; `.c.0` ahorra 45 USD pero deja GC/FX con series dispersas.

Comando exacto (no ejecutado):

```powershell
cd C:\Users\PC\.local\share\opencode\worktree\tl2-f10a
$env:PYTHONPATH="$PWD\src"
E:\trading-lab\.venv\Scripts\lab.exe discovery fetch-databento `
  --symbols NQ,ES,YM,GC,6E,6B,6J --schema ohlcv-1m --roll v `
  --download --i-approve-cost 142.90
```

Si se quiere validar la tubería barata primero: **H1 `.v.0` de los 7 por 6,78 USD** (683.823 registros, 0,038 GB). No cubre M1, pero ejercita el flujo completo.

## Aviso

- **No se ha llamado a `timeseries.get_range` ni se ha descargado un solo registro de pago.** Las llamadas de coste son metadata gratuita.
- El fin del dataset avanza con el mercado; si el operador tarda, debe repetir la estimación y aprobar el nuevo importe.
- `--adjust back` necesita una tabla de rolls construida desde contratos individuales; no se inventan diferencias. El valor por defecto `none` es el correcto para ejecución y costes.
- Las campañas/jobs del Discovery Lab todavía limitan `data_source` a `broker|dukascopy`; esta fase integra `data_sources`, `usable_from` y `data-check`, no el registro/cola de campañas con futuros. Queda para la fase que lo pida.

## Siguiente

`OK DESCARGA` (M1 `.v.0`, 142,90 USD) o la variante H1 (6,78 USD). Después: descargar, `lab discovery data-check --source databento` y `lab discovery usable-from --source databento --write`.

PARA.
