# RESULTADO · COLA-carriles — max-trades, frescura y horario us100

Fecha: 2026-11-23. Autorización del operador aplicada solo a los cuatro puntos
acordados. No se operó, no se enviaron/cerraron órdenes, no se instaló/compiló/
adjuntó ningún EA, no se modificaron ni registraron tareas programadas, no se
ejecutaron campañas ni OOS, no se hizo push y no se borró nada.

## 1. Forward: 1 por bot, 2 por cuenta

`src/tradinglab/forward_intraday.py`:

- Constante `FORWARD_ACCOUNT_MAX_TRADES_PER_DAY = 2` (línea 60).
- `bot_max` = límite del bot/perfil (1); `account_max` = 2, acotado por la
  cuenta (líneas 1345-1352).
- El bloqueo por bot usa `bot_max` (líneas 1356-1369); el guard de cuenta
  recibe `account_trades` y `max_trades_per_day=account_max` (línea 1446).
- `guards["max_trades"]` publica `bot X/1 cuenta Y/2`.

Tests (`tests/test_forward_intraday.py`):
- USDJPY ya entró y EURUSD aún puede entrar el mismo día (cuenta 1/2).
- Un tercer forward el mismo día queda bloqueado por cuenta (2/2).
- El mismo bot no entra dos veces (test existente, sigue pasando).

## 2. Frescura por edad de la vela y fuente/cuenta

`src/tradinglab/freshness.py`:

- `latest(..., source=..., use_bar_age=...)` filtra por fuente y, con
  `use_bar_age`, ordena por `last_bar_utc`, no por `fetched_at_utc`
  (líneas 244-280).
- `check(..., source=..., use_bar_age=True)` usa la edad de `last_bar_utc`;
  una descarga reciente de un histórico viejo ya **no** desbloquea
  (líneas 286-410). Sin `use_bar_age` se conserva el comportamiento anterior
  para no romper el doctor diario.
- El forward llama con `use_bar_age=True` y
  `source="mt5:<login>"` (líneas 1155-1160).
- `execution/mt5.py` registra `source="mt5:<login>"` al descargar barras
  (línea 503), de modo que la fuente/cuenta queda separada.

Tests (`tests/test_freshness.py`):
- Descarga de hace 3 h con vela de hace 10 min → `ok`.
- Descarga reciente con vela de 2025 → `falla` ("vela vieja").
- Filtro por fuente: `yahoo` reciente no tapa una vela `mt5` vieja.

## 3. us100-trend-d1 a 06:00-06:04 UTC

`scripts/intraday_forward_execute.ps1:43`:

```powershell
$inUs100 = $minuteOfDay -ge (6 * 60) -and $minuteOfDay -le (6 * 60 + 4)
```

La ventana de la señal (`entry_start/entry_end` 00:00-04:00) no cambia: lo que
cambia es cuándo se evalúa, al cerrar la vela H4 02:00-06:00 (invierno) o
01:00-05:00 (verano). Test nuevo en `tests/test_forward_intraday.py`: con velas
H4 alineadas a 02:00 y a 01:00, a las 06:02 UTC `_bar_in_entry_window` es True
en ambos casos.

La tarea programada se ejecuta cada 5 min; **no hay que cambiar su hora de
disparo ni registrarla de nuevo**.

## 4. Trazabilidad

`scripts/intraday_forward_execute.ps1`:

- `$runId` de 12 hex y `INICIO ... run_id=...` en cada pasada (línea 30).
- `FIN ... run_id=...` también en salidas tempranas por ventana (74), mutex
  (81), invocaciones (106/116), salida normal (141) y error (151).
- No se modificó la tarea programada.

## 5. Re-sellado de protegidos

Se usó `lab propfund freeze --approved-by-operator`; después se añadió al
manifiesto `authorizations` con fecha y el texto literal de la autorización
(alcance `COLA-carriles`). `lab propfund verify`: **4 OK**.

Hashes nuevos (CRLF normalizado a LF):

| Archivo | sha256 |
|---|---|
| `src/tradinglab/forward_intraday.py` | `b14dee974a8d3f28c8f572aa55858278eab4849fc6a9e36d4722be357c1bb719` |
| `config/intraday_forward.yaml` | `7c2ec75bc517ea7897bf31ebc25acfc24be06c33ee33cf69090761a585763af4` |
| `scripts/intraday_forward_execute.ps1` | `270c1d5fd49d48aa4464305cffa25a58a67e7edd34577aa8742322e2880046d8` |
| `src/tradinglab/execution/mt5.py` | `a88d57ad755f96e59e4aad160a75cc39fed746680e0a8432b8f0a332dabccbe0` |

## 6. EA v3.2 (solo preparación)

Documento: `.orquestador/EA-v32-instalar.md`.

- Repo: `integrations/mt5/us100_ftmo1/`; terminal:
  `...\Terminal\81A933A9AFC5DE3C23B15CAB19C63850\MQL5\Experts\TradingLab\US100_FTMO1`.
- `setfile_sha256=3f2b0fc5…`, `code_sha256=5f8f0751…`, criterios
  `f490642ba7a1f71b`; versión 3.20.
- Incluye hashes individuales, copia, compilación en MetaEditor, gráfico
  `US100.cash` M5, setfile v3.2, magics 93010001/93020001 y verificación
  attach-only con `lab ea status`, `lab ea forward` y el log
  `US100_EA (US100.cash,M5)`.
- **Reloj del forward:** la fila actual de `lifecycle_bots` ya tiene
  `start_date=2026-11-16` y `frozen_at=2026-11-16T02:38:13Z`; reinstalar el EA
  **no** reinicia el reloj por sí solo. Para que empiece en la fecha de
  instalación hace falta un reset explícito del forward (no ejecutado; no hay
  comando CLI de reset). Si se autoriza, quedaría `start_date=<instalación>`,
  `end_date=+60 días`, `frozen_at=<reset>` y evento en `lifecycle_events`.
  Decisión del operador.

## 7. R7b

Rama `tl2-r7b`, commit **`476ef41`** · `tl2: R7b - count_tests usa discovery de E`
(no merge).

- `learning.CANONICAL_DISCOVERY_DB` apunta a
  `E:\trading-lab\data\discovery.db` (override
  `TRADINGLAB_DISCOVERY_DB`).
- `count_tests` usa esa DB si no se pasa `discovery_db`; si falta, lanza
  `FileNotFoundError`, nunca devuelve 0 silencioso.
- `tests/conftest.py` aísla con una discovery vacía; el test de DB ausente
  espera la excepción.
- Verificación: `tests/test_learning.py` + `tests/test_discovery_count.py`
  **17 passed**; `ruff` limpio.
- `count_tests(E:\trading-lab\data\lab.db)` con el código de R7b = **1730**.
  Desde el worktree, `DEFAULT_DB` es el `lab.db` local (stub) y da 670
  (solo discovery); no es el contador global.

## 8. Comprobaciones

- `pytest -q`: **1720 passed, 1 skipped**.
- `ruff check src/tradinglab tests docs`: limpio.
- `lab propfund verify`: **4 OK**.
- `count_tests`: **1730** (E:\trading-lab).
- `git status --short`: solo `?? tl2-edge-map.patch`.
- Commit/tag: **`c8df27d`** · `tl2-carriles-fix`.

## 9. Pendiente del operador

1. Instalar el EA v3.2 siguiendo `.orquestador/EA-v32-instalar.md`; no lo hace
   el agente.
2. Decidir si se resetea el reloj del forward del EA en la fecha de instalación
   (hoy la fila mantiene 2026-11-16).
3. No hay cambio de tarea programada: el script ya corre cada 5 min y la
   ventana interna de us100 es ahora 06:00-06:04 UTC.

PARA.
