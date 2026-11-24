# RESULTADO · F10b — merge F10a y preparación de la descarga H1

Fecha: 2026-11-23. No se ejecutó ninguna descarga de pago. No se leyó, imprimió
ni escribió ninguna API key. No se tocaron campañas, OOS, tareas programadas,
archivos protegidos ni el carril del EA.

## 1. Merge F10a

- Rama `tl2-f10a` (tag `tl2-f10a`, commit `fdb9294`) fusionada con `--no-ff`.
- Sin conflictos: `cli.py` conserva `export-mql5`, `results`, `perturb`,
  `show`, `edge-map` y añade `fetch-databento`; `data_sources` mantiene
  `broker`, `dukascopy` y añade `databento`.
- Commit de merge `8c6e26d` · `merge: F10a Databento`; tag `tl2-merge-f10a`.
- No se borró el worktree ni la rama.

## 2. Re-estimación: BLOQUEADA por autenticación

Comando ejecutado (solo metadata gratuita, sin `timeseries.get_range`):

```powershell
Set-Location E:\trading-lab
.\.venv\Scripts\lab.exe discovery fetch-databento `
  --symbols NQ,ES,YM,GC,6E,6B,6J --schema ohlcv-1h --roll v `
  --start 2010-06-06T00:00:00Z --end 2026-11-23T06:00:48Z `
  --estimate-only
```

Respuesta:

```text
Databento: metadata.get_dataset_range: HTTP 401
{"detail":{"case":"auth_authentication_failed","message":"Authentication failed."}}
```

- En Credential Manager (`tradinglab` / `DATABENTO_API_KEY`) hay un valor de
  64 caracteres que empieza por `db-`, pero Databento lo rechaza.
- **No se usó la clave pegada en el chat, no se escribió, no se imprimió y no
  se guardó en ningún fichero.** F10b exige que la clave se lea de keyring.
- Sin estimación actual no se puede fijar el `--i-approve-cost` exacto ni dar
  por bueno el 6,78 USD de F10a. **PARA aquí la parte de descarga**; el operador
  decide.

### Acción segura para el operador (sin dejar la clave en el historial)

```powershell
Set-Location E:\trading-lab
.\.venv\Scripts\python.exe -c "import getpass, keyring; keyring.set_password('tradinglab', 'DATABENTO_API_KEY', getpass.getpass('Databento API key: '))"
```

Después, repetir la estimación con el comando de arriba. Si el total queda
dentro del ±5 % de 6,78 USD, el comando de descarga será el mismo comando con:

```text
--download --i-approve-cost <TOTAL_EXACTO_DE_LA_NUEVA_ESTIMACION>
```

No se escribe un importe definitivo hasta que la estimación funcione. El fin
del dataset avanza con el mercado; el `--end` debe ser el de la estimación que
se apruebe.

## 3. Referencia F10a (no es la estimación actual)

- H1 `.v.0` de los 7: 683.823 registros, 0,038 GB facturables, **6,776188 USD**
  en el snapshot del 2026-11-23 06:00–06:04 UTC.
- Salida: `data/cache/databento/<SÍMBOLO>_H1.parquet` para US100, US500, US30,
  XAUUSD, EURUSD, GBPUSD y USDJPY. Índice UTC `time`; columnas
  `open/high/low/close/volume`; 6J invertido barra a barra.
- Tamaño esperado: ~0,038 GB, 7 ficheros. Tiempo de descarga no medido; a
  1–10 MB/s serían ~4–40 s de transferencia, más la latencia de la API.
- Roll por volumen `.v.0`, sin ajuste (`--adjust none`), que es el válido para
  ejecución y costes.

## 4. Comprobaciones

- `tests/test_discovery_fetch_databento.py`: **17 passed**.
- Tests EA: **53 passed**.
- `ruff check src/tradinglab tests docs`: limpio.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1730**.
- `pytest -q`: **1712 passed, 1 skipped, 3 failed**. Los 3 fallos son por un
  cambio **externo y no commiteado** en `config/intraday_bots.yaml`: otro
  proceso/sesión puso `enabled: true` en todos los bots intradía y en
  `us100-trend-d1`/`xauusd-trend-d1` durante esta sesión.
  - `test_intraday_bots::test_load_bots_incluye_intraday_sin_tocar_bots_yaml`
  - `test_swing::test_los_bots_del_carril_siguen_desactivados`
  - `test_fund_web::test_fund_limites_bolsillos_y_clusters`

  Ese archivo **no se ha tocado, no se ha revertido y no se ha incluido en
  ningún commit**. Es trabajo externo; los tests esperan el estado anterior
  (`enabled: false`). El merge de F10a no modifica ese archivo.

## 5. Fase siguiente (F10c, no ejecutada)

Cuando el operador diga "DESCARGADO":

1. `lab discovery data-check --source databento` por símbolo, en H1/H4/D1.
2. `lab discovery derive-sessions --source databento` para obtener el horario
   CME real (pausa, cierre y apertura) en vez de la hipótesis actual.
3. `lab discovery usable-from --source databento --write`.
4. Comparación Databento vs Dukascopy por símbolo: correlación de retornos,
   desfase, diferencias de nivel tras el roll y días con huecos. Solo lectura.

No se ejecuta nada de F10c ahora.

## 6. Cierre

- `git status --short`: ` M config/intraday_bots.yaml` (externo) y
  `?? tl2-edge-map.patch` (previo).
- Merge `8c6e26d` · tag `tl2-merge-f10a`.
- Sin push; sin descarga; sin campañas; sin OOS; sin API key expuesta.

PARA.
