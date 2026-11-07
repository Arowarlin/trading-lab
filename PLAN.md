# PLAN.md — TradingLab

Fuente de verdad del plan por fases. Cada casilla se marca **solo** cuando se
cumple su criterio de aceptación, con fecha y comando de evidencia.

Reglas de trabajo:

- Un cambio = un commit pequeño, con test cuando aplique.
- Antes de cerrar una fase: `ruff check`, `pytest`, `lab doctor` y README actualizado.
- Ningún secreto en logs, commits ni informes.
- Nada se activa solo: bots, propuestas, prompts y lecciones nacen en
  `proposed` / `enabled: false`.
- Al final de cada fase: resumen de máximo 15 líneas y espera de confirmación.

## Fase 0 — Higiene y seguridad

- [x] **0.1 README limpio y fusionado** — 2026-11-06
  - Revisar `README.md`: eliminar el párrafo duplicado de la sección 4,
    corregir numeración F14/F15 y comprobar que no haya fechas futuras.
  - `README_corregido.md` **no existe** en `E:\trading-lab` ni en las rutas
    habituales (Desktop, Documents, Downloads, C:\TradingLab). Se documenta la
    ausencia y se aplican los criterios directamente sobre el README actual.
  - Criterio: README sin duplicado, F14 = research y F15 = datos Dukascopy,
    sin fechas futuras; `tests/test_docs.py` pasa.
  - Evidencia: `pytest tests/test_docs.py -q` → 3 passed.

- [x] **0.2 Backups sin secretos en claro** — 2026-11-06
  - Añadir `keyring` y cargar secretos desde Windows Credential Manager con
    fallback a `.env` (precedencia: shell > keyring > `.env`).
  - Excluir `.env` del zip de backup y actualizar `LEEME_BACKUP.txt`.
  - Crear `scripts/migrate_secrets.py` (sin imprimir valores) y
    `scripts/restore_test.ps1`.
  - Escanear el backup restaurado buscando valores de secretos sin imprimirlos.
  - Evaluar restic vs Kopia y proponer uno en `docs/backups.md`.
  - Criterio: restaurar el último zip en una carpeta temporal funciona y el
    escaneo no encuentra secretos; `Select-String`/script de scan = 0 hallazgos.
  - Evidencia: `backup.ps1` → `PASS`, SQLite `ok`, 3 secretos migrados a keyring.
    Zips antiguos con `.env` listados en `docs/backups.md` (pendientes de borrado
    con autorización).

- [x] **0.3 Reproducibilidad** — 2026-11-07
  - `uv.lock`, versiones directas fijadas, `pre-commit` y CI Windows con
    lint + tests (sin secretos ni brokers).
  - Documentado en `docs/dependencias.md`.
  - Evidencia: `uv sync --frozen --extra dev --extra mt5` OK; CI verde en
    `66f2e8f`; `pytest -q` → 129 passed.

- [x] **0.4 Zona horaria y horario de verano** — 2026-11-06
  - Revisar el autodetector de offset MT5 y el reset FTMO (00:00 Praga).
  - Corregir el bug de ticks viejos que producían offsets negativos.
  - Tests en cambios de hora de EE. UU. y Europa.
  - Criterio: el reset diario se calcula bien a ambos lados de los cambios y
    `pytest tests/test_timezone.py -q` pasa.
  - Evidencia: `pytest tests/test_timezone.py -q` → 7 passed. El autodetector
    ahora rechaza ticks viejos; FTMO-Demo reporta offset 0 (antes -3 falso).

## Fase 1 — Kill-switch, alertas y observabilidad

- [x] **1.1 Kill-switch persistente y tests** — 2026-11-06
  - Tests de pérdida diaria, drawdown, bloqueo de aperturas, cierre permitido,
    persistencia tras reinicio y reset manual confirmado.
  - Comandos `lab killswitch status|test|reset` (reset pide confirmación).
  - Criterio: tests verdes; cualquier brecha real corregida y reportada.
  - Evidencia: `pytest tests/test_killswitch.py -q` → 6 passed.
- [x] **1.2 Alertas** — 2026-11-06
  - `alerts.py` con ntfy (recomendado) y Telegram; eventos de guard,
    kill-switch, fallos de broker/LLM/MT5, desfase DB, ciclo no ejecutado y backup.
  - Evidencia: `pytest tests/test_alerts.py -q` → 5 passed.
- [x] **1.3 Dead-man's switch** — 2026-11-06
  - `lab alerts heartbeat` + `HEALTHCHECKS_URL`; llamado al final de dry-run y backup.
- [x] **1.4 Reconciliación diaria** — 2026-11-06
  - `lab reconcile`, tabla `reconciliation`, alerta por diferencia.
  - Evidencia: `pytest tests/test_reconciliation.py -q` → 2 passed; `lab reconcile` → ok.
- [x] **1.5 Panel** — 2026-11-06
  - `lab web` muestra kill-switch, último latido y última reconciliación.

## Fase 2 — Dejar F13 listo para arrancar

- [x] **2.1 Definir criterios de éxito de F13** — 2026-11-07
  - Métricas, umbrales, condiciones de parada y regla de decisión, medibles y
    con tamaño de muestra realista para 4-8 semanas. Documentar en PLAN/README.
  - Decisión: 8 semanas = pilot operativo; edge se extiende a 6 meses o >=20
    trades. 21 trades/11 años => 0-3 trades esperados en 8 semanas.
- [x] **2.2 Elegir el bot del paper** — 2026-11-07
  - `qqq-trend-f13` (QQQ, trend 50/200/200, exposición 0.35), `enabled: false`.
  - Justificación: mejor propuesta de research (21 trades, 65.5% pasa, 7.2%
    breach, 83.5% OOS). No se activa.
- [x] **2.3 Implementar medición automática de F13** — 2026-11-07
  - Tablas `f13_config`/`f13_metrics`, `lab f13 status|freeze|report|
    signal-check|config-check|check`, comparación con SPY y backtest.
  - Slippage real vs señal y error de tamaño; paradas duras con alerta.
  - Evidencia: `pytest tests/test_f13.py -q` → 5 passed; `lab f13 check` no-op
    porque F13 no ha iniciado.
- [x] **2.4 Presentar y esperar aprobación** — pendiente de respuesta del usuario
  - No se ha activado el paper. `qqq-trend-f13` sigue `enabled: false`.

## Fase 3 — Mejoras de lab research

- [x] **3.1 Anti-sobreajuste (DSR)** — 2026-11-07
  - Deflated Sharpe Ratio implementado y usado como criterio (>=90%).
  - Resultado: 0 propuestas de 192 variantes; los 18 candidatos previos no
    sobreviven al ajuste por múltiples pruebas.
- [x] **3.1b PBO (CSCV)** — 2026-11-07
  - `tradinglab.validation.cscv_pbo` con 16 bloques contiguos → 12.870
    combinaciones train/test sobre retornos diarios alineados por fecha.
  - PBO global 24,8% (ok); por activo: QQQ 7,5%, SPY 14,4%, IWM 26,3% (ok);
    GLD 40,9%, TLT 46,0% y EURUSD=X 96,0% (sobreajustados).
  - Sin PBO calculable no se proponen bots.
- [x] **3.2 Walk-forward y regímenes** — 2026-11-07
  - Walk-forward global con train 504 / test 126, Sharpe stitched, fracción de
    folds positivos, eficiencia, rank mediano y estabilidad; `verdict()` devuelve
    `ok`/`fallido` con umbrales fijos documentados en README.
  - `regime_report`/`regime_gate` por variante para 2018/2020/2022; un régimen
    sin datos no aprueba. Drawdown vs buy&hold es informativo.
  - DSR guarda `dsr_n_trials` y `dsr_trial_sr_std`; PBO guarda diagnóstico de
    variantes planas y PBO sin planas (informativo).
- [x] **3.3 Monte Carlo block bootstrap** — ya existía y research usa
  `block_size=5`; documentado.
- [ ] **3.4 Optuna** para explorar parámetros con validación walk-forward.
- [ ] **3.5 QuantStats** para el HTML de cada propuesta frente a SPY.
- [x] **3.6 Criterio**: research completo con datos sintéticos en tests
  (`tests/test_research.py`) y barrido real con PBO/walk-forward/DSR.

## Fase 4 — Capa de información continua

- [ ] **4.1 Fuentes**: RSS Yahoo y SEC EDGAR operativos; FRED operativo para
  CPI/NFP; Finnhub y OpenBB pendientes de conectar/verificar.
- [ ] **4.2 Triaje barato**: FinBERT o modelo local pequeño; medir latencia/RAM.
  - Decisión 2026-11-07: **no usar FinBERT** (CC-BY-NC-SA 4.0, no comercial);
    usar Qwen inicialmente. No se descarga modelo nuevo.
- [x] **4.3 Esquema** — 2026-11-07
  - `news_items`, `news_scores`, `macro_events`; dedupe por hash, trusted=false.
- [x] **4.4 Seguridad** — 2026-11-07
  - `sanitize_untrusted` + `wrap_untrusted`; test de noticia con instrucciones.
- [ ] **4.5 Planificador**: `TradingLab-Intel` 07:10 + logs/alerta; faltan
  reintentos por fuente.
- [x] **4.6 Calendario → guard** — 2026-11-07
  - `news_blackout_min` (antes/después), `weekend_holding` + `friday_cutoff_hour`
    en Europe/Prague, `rollover_blackout_min`; proveedor abstracto y cierres
    siempre permitidos.

## Fase 5 — Medir si el LLM aporta algo + memoria

- [x] **5.1 Salida estructurada** — 2026-11-07
  - `lite` ya usa `json_schema` estricto; los fallos quedan en `llm_calls`.
  - Pendiente: conteo explícito de fallos de validación de esquema.
- [x] **5.2 `decision_outcomes`** — 2026-11-07
  - Tabla + `lab decisions update` con retorno a 1/5/20 días hábiles.
- [x] **5.3 Línea base** — 2026-11-07
  - `lab decisions report` compara LLM lite, buy&hold y señal trend sobre las
    mismas fechas, con retorno medio, hit rate, N y aviso de muestra insuficiente.
- [ ] **5.4 Comparar MoE ~30B** vs modelo actual en lite; no cambiar el default.
- [x] **5.5 Versionado de prompts** — 2026-11-07
  - `prompt_version` + `prompt_hash` guardados por decisión lite; deep usa hash simple.

## Fase 6 — Multi-mercado

- [ ] **6.1 IBKR paper** con `ib_async` verificado, guard de identidad, stop
  obligatorio y cierre permitido; CFD solo si se confirma disponibilidad.
  - Evaluación hecha en `docs/fase6_multimercado.md`; sin cuenta/confirmación.
- [ ] **6.2 CFD vía MT5** con especificaciones y horarios.
- [ ] **6.3 Futuros**: preset Topstep 50K añadido como plantilla inactiva;
  faltan MLL validado y barras continuas con rollover.
- [ ] **6.4 Catálogo único** de instrumentos por clase.
- [ ] **6.5 Agentes por mercado** y coordinador determinista.
- [ ] **6.6 Un mercado a la vez**, cada uno con su mini-F13.

## Fase 7 — Aprendizaje controlado

- [ ] **7.1 Lecciones** semanales en `lessons` con estado `proposed` y aprobación
  humana en el panel.
- [ ] **7.2 Reentrenamiento walk-forward** (LightGBM u otro), `model_registry`,
  campeón/retador y evaluación de Qlib en venv aparte.
- [ ] **7.3 Límites**: versionado, capital máximo por agente y rollback.
  - Evaluación en `docs/fase7_aprendizaje.md`.

## Fase 8 — Motor de eventos (opcional)

- [x] **8.1 Comparación escrita** — 2026-11-07
  - `docs/fase8_nautilus.md`: NautilusTrader 1.231.0, LGPL-3.0, sin v2 estable;
    se mantiene el backtester propio hasta que F13/intradía lo justifiquen.

## Registro de evidencias

| Fecha | Tarea | Comando / evidencia |
|---|---|---|
| 2026-11-06 | Plan creado | `PLAN.md` |
| 2026-11-06 | 0.1 README | `pytest tests/test_docs.py -q` → 3 passed |
| 2026-11-06 | 0.2 Backups/keyring | `backup.ps1` → PASS; keyring 3 secretos |
| 2026-11-06 | 0.4 DST/offset | `pytest tests/test_timezone.py -q` → 9 passed |
| 2026-11-06 | 1.1–1.5 | `pytest -q` → 112 passed; `lab reconcile` → ok |
| 2026-11-07 | 2.1–2.2 | `lab f13 status` → no iniciado; bot `qqq-trend-f13` |
| 2026-11-07 | 3.1/3.3 | `lab research` → 0 propuestas, DSR aplicado |
| 2026-11-07 | 5.1–5.3/5.5 | `pytest tests/test_decisions.py -q` → 2 passed |
| 2026-11-07 | 4.3/4.4 | `lab intel fetch` → 5 noticias; `pytest tests/test_intel.py -q` → 5 passed |
| 2026-11-07 | 0.3 / final | `pytest -q` → 129 passed; CI 66f2e8f verde |
| 2026-11-07 | 3.1/3.1b/3.2 | `pytest tests/test_research.py -q`; PBO 16% (simplificado), WF 4 bloques |
| 2026-11-07 | 3.1b CSCV | `pytest tests/test_validation.py tests/test_research.py -q`; PBO global 24,8% |
| 2026-11-07 | 0–2 walk-forward/guard | `pytest -q` → 188 passed; `lab doctor` OK salvo Finnhub/ProjectX |
| 2026-11-07 | 3 decisions/CI/Topstep | `pytest -q` → 188 passed; CI Windows con markers; preset inactivo |
| 2026-11-07 | 6 cierre | `lab research` → 0 propuestas; PBO 24,8% ok; WF global `fallido`; panel HTTP OK |
| 2026-11-07 | consola v2 | `pytest -q` → 192 passed; panel 8433: market=12, calendar=empty, repos=3 |
| 2026-11-07 | revisión WF/PBO/DSR | `pytest -q` → 197 passed; PBO EURUSD planas 0/16; WF fallido por estabilidad; 2 zips con `.env` intactos |
| 2026-11-07 | Run Detail + FRED | `pytest -q` → 203 passed; 192 artefactos de equity; FRED CPI=10/NFP=50 con futuras 2026-11-10/12-10 y 12-04 |
| 2026-11-07 | F13 prep | `pytest` F13/flow 12 passed; dry-run Alpaca paper sin órdenes; `f13 status` no iniciado; tarea NO registrada |
| 2026-11-07 | MC horizontes | `pytest -q` → 210 passed; `horizons.md/json` top 10 × FTMO/Topstep × 22/44/120d × 0.5/1/2× |
| 2026-11-07 | E1 perfiles/guard | `pytest -q` → 221 passed; 3 perfiles; guard 3 bots; correlación >0.7 avisada |
| 2026-11-07 | E2 intradía | estrategias/costes/report con tests sintéticos; `lab mt5 fetch` bloqueado por offset MT5 desconocido (mercado cerrado) |
| 2026-11-07 | E3 futuros | perfil `intraday_futures` y stub ProjectX documentados; proxy ES=F/NQ=F diario |
| 2026-11-07 | 4.4/4.6/11b | `pytest tests/test_calendar.py tests/test_session.py -q` |
| 2026-11-07 | SEC/CSV/decisions | `pytest tests/test_sec.py tests/test_decisions.py -q` |
|  |  |  |
