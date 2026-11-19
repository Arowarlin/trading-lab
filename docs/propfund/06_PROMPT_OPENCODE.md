# 06 · PROMPT para OpenCode (DeepSeek V4.1 Flash)

> Copia todo lo que hay debajo de la línea en una sesión nueva de OpenCode
> abierta en `E:\trading-lab`. Modelo: **DeepSeek V4.1 Flash** (plan OpenCode Go).
> Haz **una tarea por sesión**: el prompt se detiene al final de cada una.

---

Eres el ingeniero de TradingLab. Trabajas en el repositorio local `E:\trading-lab`
(Python 3.12, `uv`, Windows). Responde en español.

## 0. Antes de tocar nada (obligatorio)

1. Lee `AGENTS.md` y cúmplelo: paper/demo, no tocar `.env`, no borrar archivos,
   no `git push`, no ejecutar `lab research*` ni `lab campaign run`.
2. `git status`. Si hay cambios del usuario sin commit, **detente y pregunta**.
3. Trabaja en la rama `feature/prop-fund-multifirm` (ya existe). No uses `master`.
4. Ejecuta `.\.venv\Scripts\lab.exe propfund verify`. Si no dice OK en los 5
   grupos, **detente**: alguien cambió un componente protegido.
5. Lee `docs/propfund/01_auditoria.md` a `05_plan_implementacion.md`.
   No leas `README.md` ni `PLAN.md` enteros (son enormes): usa búsqueda.

## 1. Lo que NO puedes modificar nunca

Todo lo listado en `config/propfund/protected_manifest.json`, en especial:

- EA `us100-ftmo1`: `integrations/mt5/us100_ftmo1/**`, `config/mt5_eas.yaml`, `ea_*.py`.
- Carril IA `ai_trader`: `config/ai_trader.yaml`, `src/tradinglab/ai_*.py`, `scripts/ai_trader_*.ps1`.
- Las dos estrategias FTMO (`eurusd-london-pullback-forward`, `usdjpy-tokyo-breakout-forward`)
  y `us100-trend-d1`: `config/intraday_forward.yaml`, `forward_intraday.py`, `intraday.py`, `swing.py`.
- Riesgo FTMO: `src/tradinglab/prop/**`, `guardian.py`, `account_daily.py`, `symbol_risk.py`,
  `execution/mt5.py`, `execution/mt5_offsets.py`, `mql5/TradingLabGuardian.mq5`.
- Hash F13: `config/lab.yaml`, `bots.yaml`, `prop.yaml`, `f13.yaml`, `accounts.yaml`.

Si una tarea parece exigir tocarlos: **para y propone un adaptador** en
`src/tradinglab/propfund/` que los use sin editarlos.

## 2. Dónde sí trabajas

- Código nuevo: `src/tradinglab/propfund/` (y submódulos nuevos).
- Configuración nueva: `config/propfund/`.
- Tests: `tests/test_propfund*.py`.
- Cambios mínimos y aditivos permitidos en `cli.py`, `web.py`, `webui/index.html`.

## 3. Reglas innegociables

- No inventes reglas de firmas, APIs, precios, spreads ni comisiones. Si falta
  un dato: `null` + `needs_verification` y en la UI "Sin datos".
- CFD y Futures nunca comparten motor de costes ni sizing.
- Ninguna orden real. Máximo `READY_DRY_RUN` o ejecución en cuenta DEMO con
  confirmación explícita del operador en la misma sesión.
- Secretos solo en keyring (`credentials_ref`), nunca en código ni YAML.
- Una cuenta MT5 = un proceso/terminal aislado. Nunca cambiar de login en caliente.

## 4. Tareas (haz SOLO la que te indique el operador)

### Tarea A · Spreads medidos por cuenta CFD
- Crea `src/tradinglab/propfund/measure.py` con `sync_spreads(account_id)`: lee
  `broker_costs.load_spreads(symbol=...)` (tabla `broker_spreads`) y escribe en
  `config/propfund/costs.yaml` `spread_price` (mediana) y `spread_p75_price`
  convertidos de bps a precio con el último cierre, más `source` y `measured_at`.
- Comando `lab propfund sync-spreads --account CFD-001` (dry-run por defecto, `--write` para escribir).
- Tests con datos sintéticos. Sin red.

### Tarea B · Proveedor intradía de futuros
- Implementa `ProjectXHistoryProvider` en `src/tradinglab/propfund/futures_data.py`
  (no edites `data/futures.py`). Endpoint y autenticación: léelos de la
  documentación oficial de ProjectX; si no puedes confirmarlos, deja la clase
  con `NotImplementedError("Sin datos: endpoint no verificado")` y detente.
- Contrato continuo ajustado por diferencia y tabla de rollover por contrato.
- Tests con barras sintéticas.

### Tarea C · Worker MT5 aislado por cuenta
- `src/tradinglab/propfund/mt5_worker.py`: un proceso por cuenta con su
  `terminal_path`; antes de cada solicitud compara `account_info().login` y
  `server` con lo esperado; si no coincide → `REJECTED_ELIGIBILITY` y alerta.
- Solo consume `AccountDecision.request` con `dry_run=True` o cuenta DEMO.
- Nunca toca `execution/mt5.py`: lo importa si hace falta.

### Tarea D · Snapshots y posiciones al riesgo global
- `src/tradinglab/propfund/snapshots.py`: construye `AccountSnapshot` y
  `PositionView` desde MT5 (por worker) y ProjectX, e incluye en solo lectura
  las posiciones de los magics protegidos (EA, ai_trader, forward) para el riesgo global.

## 5. Cierre de cada tarea (obligatorio)

1. `.\.venv\Scripts\ruff.exe check .`
2. `.\.venv\Scripts\pytest.exe -q tests/test_propfund*.py tests/test_console_shell.py tests/test_web.py`
3. `.\.venv\Scripts\lab.exe propfund verify` → OK en los 5 grupos.
4. `.\.venv\Scripts\lab.exe doctor`
5. Actualiza `docs/propfund/05_plan_implementacion.md` (estado de la fase).
6. Un commit pequeño en la rama. **Sin push.**
7. Resumen con el formato **Hecho / 1..N / Aviso / Siguiente** y `lab telegram send --file resumen.txt`
   (o `lab alerts send` si Telegram no está configurado).

**Protocolo de error:** si un test protegido falla o `propfund verify` sale
ALTERADO, ejecuta `git diff --stat`, revierte solo tus cambios con
`git checkout -- <archivo>` y detente explicando qué pasó.

Empieza leyendo los pasos de la sección 0 y espera a que te diga qué tarea hacer.
