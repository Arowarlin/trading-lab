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
- [x] **2.4 Presentar, congelar y esperar aprobación** — 2026-11-07
  - F13 congelado el 2026-11-07 y **activado en paper** el mismo día con
    `lab f13 activate --yes`; inicio **2026-11-09**, ventana de 8 semanas y
    hash re-congelado `54b42036…`; `lab f13 config-check` OK.
  - `qqq-trend-f13` quedó `enabled: true`; `TradingLab-F13` está **Ready** con
    próxima ejecución **2026-11-09 22:20**. `lab readiness` resume días en
    paper, decisiones con retorno 20d, muestra mínima, esquema LLM y macro.
    Sin live ni órdenes en la
    activación.
  - **Activación controlada:** `lab f13 activate` edita solo `enabled` del bot,
    re-congela el hash, exige `mode=paper` y audita `f13_activate`. No live.

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
- [x] **3.4 Optuna** para explorar parámetros con validación walk-forward.
  - Completado en la Etapa 7 de optimización; walk-forward sobre desarrollo,
    holdout intacto y trials registrados en el contador DSR.
- [x] **3.5 QuantStats** para el HTML de cada propuesta frente a SPY.
  - Completado en la Etapa 7; HTML por propuesta con benchmark y sin cambiar
    los umbrales de aprobación.
- [x] **3.6 Criterio**: research completo con datos sintéticos en tests
  (`tests/test_research.py`) y barrido real con PBO/walk-forward/DSR.

## Fase 4 — Capa de información continua

- [x] **4.1 Fuentes**: RSS Yahoo y SEC EDGAR operativos; FRED operativo para
  CPI/NFP; Finnhub implementado y verificado con lectura de SPY; OpenBB no
  instalado y no se usa (no se añade dependencia).
- [x] **4.2 Triaje barato**: scoring de noticias con Qwen en `news_scores`.
  - FinBERT descartado por licencia CC-BY-NC-SA 4.0; no se descarga modelo nuevo.
  - `lab intel score` sanea/delimita el texto y devuelve sentimiento/relevancia;
    sin respuesta válida no se inventan puntuaciones.
  - Verificado con 3 noticias reales y el modelo `qwen/qwen3.8-27b`.
- [x] **4.3 Esquema** — 2026-11-07
  - `news_items`, `news_scores`, `macro_events`; dedupe por hash, trusted=false.
- [x] **4.4 Seguridad** — 2026-11-07
  - `sanitize_untrusted` + `wrap_untrusted`; test de noticia con instrucciones.
- [x] **4.5 Planificador**: `TradingLab-Intel` 07:10 + logs/alerta.
  - Reintentos con backoff solo para fallos transitorios (429/5xx/red); un
    404/401 no se reintenta y la ingesta devuelve código distinto de cero si
    fallan todas las fuentes.
- [x] **4.6 Calendario → guard** — 2026-11-07
  - `news_blackout_min` (antes/después), `weekend_holding` + `friday_cutoff_hour`
    en Europe/Prague, `rollover_blackout_min`; proveedor abstracto y cierres
    siempre permitidos.

## Fase 5 — Medir si el LLM aporta algo + memoria

- [x] **5.1 Salida estructurada** — 2026-11-07
  - `lite` usa `json_schema` estricto; `chat_json` valida el subconjunto de
    JSON Schema y guarda `schema_ok`/`schema_error` en `llm_calls`.
  - `lab llm status` muestra validadas, fallidas y últimos errores por modelo.
- [x] **5.2 `decision_outcomes`** — 2026-11-07
  - Tabla + `lab decisions update` con retorno a 1/5/20 días hábiles.
- [x] **5.3 Línea base** — 2026-11-07
  - `lab decisions report` compara LLM lite, buy&hold y señal trend sobre las
    mismas fechas, con retorno medio, hit rate, N y aviso de muestra insuficiente.
- [ ] **5.4 Comparar MoE ~30B** vs modelo actual en lite; no cambiar el default.
  - Marco listo: `lab llm compare TICKER --models actual,candidato` y
    `lab llm report`, con tabla `lite_model_comparisons`, errores saneados y
    aviso de muestra <30. No se cambia el modelo por defecto.
  - MoE `qwen/qwen3-30b-a3b` descargado y tres comparaciones reales 2026-11-09
    (SPY/QQQ/NVDA): ambos Hold en los tres; confianza media 62% vs 60%;
    latencia 190-235 s vs 71-79 s; acuerdo 100%. Muestra n=3 < 30: sin
    conclusión; el default sigue siendo `qwen/qwen3.8-27b`. Repetir en días
    distintos hasta n≥30.
  - Tarea `TradingLab-LLMCompare` registrada y `Ready` (L-V 18:30) para
    acumular la muestra; no cambia el default. Primera ejecución:
    2026-11-09 18:30 local.
- [x] **5.5 Versionado de prompts** — 2026-11-07
  - `prompt_version` + `prompt_hash` guardados por decisión lite; deep usa hash simple.

## Fase 6 — Multi-mercado

- [ ] **6.1 TradeStation SIM** (sustituye a IBKR; el usuario ya tiene cuenta)
  - WebAPI v3 SIM (`https://sim-api.tradestation.com/v3`), OAuth con refresh
    token, access token de 20 min y scopes MarketData/ReadAccount/Trade.
  - Adaptador de solo lectura `execution/tradestation.py`: cuentas, balances,
    posiciones, quotes y `lab tradestation setup|status|accounts|positions`.
  - OAuth manual preparado: `lab tradestation auth-url` genera la URL y
    `lab tradestation exchange` guarda el refresh token en keyring.
  - Guard: solo `sim-api`, cuenta esperada y `dry_run=True`; las funciones de
    órdenes responden dry-run y no envían nada.
  - Bloqueado: falta API Key/refresh token/account ID de soporte TradeStation.
  - IBKR paper queda descartado por ahora; evaluación en
    `docs/fase6_multimercado.md`.
- [ ] **6.2 CFD vía MT5** con especificaciones y horarios.
  - Especificaciones reales verificadas el 2026-11-09: XAUUSD tick 0,01 /
    contrato 100 / volumen mín. 0,01; US100.cash tick 0,01 / contrato 1 /
    volumen mín. 0,01; `trade_mode=4` y `filling_mode=3` en ambos.
  - Horario: la API Python de MT5 instalada no expone sesiones; el catálogo
    mantiene `24/5 UTC` como referencia, no como verificación del bróker.
- [ ] **6.3 Futuros**: preset Topstep 50K añadido como plantilla inactiva;
  faltan MLL validado y barras continuas con rollover.
- [x] **6.4 Catálogo único de instrumentos por clase** — 2026-11-07
  - `instruments.py`: fuente de datos, sesión y zona por instrumento; clases
    equity/forex/futures/cfd.
  - `validate_catalog()` y `catalog()`; CLI `lab instruments --validate`, API
    `/api/instruments` y panel Mercado.
  - CFD solo con especificación verificada; sin inventar índices/horarios.
  - Evidencia: `pytest tests/test_instruments.py -q` → 9 passed; suite completa
    307 passed.
- [x] **6.5 Agentes por mercado y coordinador determinista** — 2026-11-07
  - `config/market_agents.yaml`: etiqueta, perfil, analistas y peso máximo por
    mercado (equity/forex/futures/cfd).
  - Routing que valida la clase del símbolo con `instruments.py` antes de usar
    el agente lite/deep.
  - `coordinate()` determinista con topes por símbolo/mercado, gross máximo y
    cash residual; no ejecuta órdenes ni activa bots.
  - CLI `lab markets list|coordinate`, API `/api/markets` y panel Agentes.
  - Evidencia: `pytest tests/test_market_agents.py -q` → 5 passed; suite
    completa 312 passed.
- [x] **6.6 Un mercado a la vez, cada uno con su mini-F13** — 2026-11-07
  - `config/market_pilots.yaml` con equity `not_started` y forex/futuros
    `blocked` por datos/cuentas; seleccionar no activa bots ni F13.
  - Un solo piloto activo con historial; gate de aperturas en orquestador y
    modo operador; cierres siempre permitidos.
  - CLI `lab markets pilots|pilot-select|pilot-clear`, API `/api/markets` y
    panel Agentes.
  - Evidencia: `pytest tests/test_market_pilots.py -q` → 4 passed; suite
    completa 317 passed.

## Fase 7 — Aprendizaje controlado

- [x] **7.1 Lecciones semanales** — 2026-11-07
  - Job sobre `decision_outcomes` con n≥30; Qwen solo redacta, evidencia
    numérica aparte y estado `proposed`.
  - Sin muestra/LLM: **Sin datos**, no crea propuestas. Deduplica hipótesis.
  - CLI `lab lessons weekly` y script `scripts/lessons_weekly.ps1` (sin registrar).
  - Aprobación exclusivamente humana en el panel Aprendizaje.
  - Evidencia: `pytest tests/test_learning.py -q` → 8 passed; suite completa
    327 passed.
- [x] **7.2 Reentrenamiento walk-forward** — 2026-11-07
  - Ridge determinista en numpy (sin dependencias nuevas) con features de
    precio/volatilidad/rango y ventanas móviles sin lookahead.
  - `model_registry` + `model_registry_history`: versión, métricas, features,
    coeficientes, hash y estado.
  - Challenger por defecto; promoción/rollback manual y confirmada. No activa
    bots ni cambia `enabled`.
  - CLI `lab models ...`, API `/api/models` y panel Aprendizaje.
  - Qlib: solo se comprueba `.venv-qlib`; no se añaden dependencias.
  - Evidencia: `pytest tests/test_models.py -q` → 3 passed; suite completa
    320 passed; challenger SPY v1 registrado sin promoción.
- [x] **7.3 Límites: versionado, capital máximo por agente y rollback** — 2026-11-07
  - `account_limit_versions` con snapshot/hash y rollback confirmado.
  - F13 congelado solo permite rollback que apriete; aflojar espera al
    siguiente día hábil.
  - `bot_capital_limits` + historial; el orquestador recorta `desired` por el
    capital máximo del bot.
  - CLI `lab fund snapshot|versions|rollback` y `lab bots capital|capital-set`.
  - Evidencia: `pytest tests/test_limit_versions.py -q` → 3 passed; suite
    completa 325 passed.
- [ ] **7.4 Acumular 20-30 días de decisiones reales** — en curso
  - No se puede backfillar: `run_lite_agent --date` solo etiqueta la fecha y el
    contexto usa datos hasta hoy. La muestra debe crecer a diario.
  - El job `TradingLab-Agents` (L-V) ejecuta SPY/QQQ/NVDA en modo lite y luego
    `lab decisions update` para rellenar retornos 1/5/20d.
  - Inicio: 2026-11-07 con 3 decisiones (SPY/QQQ/NVDA, todas Hold) y 0 retornos.
  - Cierre: tras 20-30 días, `lab decisions report`, `lab lessons weekly` y
    revisión de deriva/DSR con datos reales. Sin conclusiones antes.

## Fase 8 — Motor de eventos (opcional)

- [x] **8.1 Comparación escrita** — 2026-11-07
  - `docs/fase8_nautilus.md`: NautilusTrader 1.231.0, LGPL-3.0, sin v2 estable;
    se mantiene el backtester propio hasta que F13/intradía lo justifiquen.
- [x] **8.2 Cierre de fase** — 2026-11-07
  - Decisión formal de no adoptar Nautilus ni añadir `nautilus`/`databento`/
    IBKR; gate de reapertura documentado.
  - Evidencia: `pytest tests/test_engine_decision.py -q` → 2 passed; suite
    completa 322 passed.

## Fase 9 — Fondo personal (etapas 1–6)

Objetivo: varias cuentas (capital propio y fondeo), bots por perfil de activo y
límites editables desde la consola. Sin activar bots, sin órdenes, sin dinero
real, sin tocar `.env` y sin borrar archivos.

- [x] **9.1 Modelo de cuentas y límites efectivos** — 2026-11-07
  - `config/accounts.yaml`: `paper_main`, `alpaca_paper`, `ftmo_demo`,
    `topstep_template` (plantilla inactiva), con tipo, broker, plataforma,
    firma/fase, estado, tamaño y bolsillo.
  - `AccountLimits`, `own_limits`, `firm_limits`, `effective_limits` y
    `rules_for_account`; `evaluate_account(limits=...)` usa el mínimo.
  - Guard por cuenta en `orchestrator` (cierre/reducción permitidos).
  - Tests: 3 bots simultáneos en `paper_main` (el tercero se bloquea) y 2
    cuentas con límites distintos.
- [x] **9.2 Almacén editable e historial en SQLite** — 2026-11-07
  - Tabla `account_limit_history` (fecha, cuenta, campo, antes, después,
    origen, efectivo desde, motivo), fuera del hash de F13.
  - `lab fund accounts|set|history`; apretar inmediato, aflojar con confirmación
    y espera al siguiente día hábil; con F13 congelado/iniciado solo apretar.
  - Test: `lab f13 config-check` no cambia al editar límites.
- [x] **9.3 Seguridad de la consola** — 2026-11-07
  - Token CSRF por proceso (`/api/session` + `X-CSRF-Token`), validación de
    `Host`/`Origin` solo `127.0.0.1`, 403 sin token y lista blanca
    `WRITE_ROUTES`.
  - Ningún endpoint activa bots, cambia `enabled`, envía órdenes ni modifica
    los límites de la firma.
  - Evidencia: `pytest tests/test_web_security.py -q` → 10 passed.
- [x] **9.4 Pestaña Fondo** — 2026-11-07
  - Límite de firma (solo lectura), propio editable, efectivo, uso del día,
    colchón, formulario validado, confirmación al aflojar e historial.
  - Kill-switch global, exposición agregada y capital por bolsillo con aviso si
    un clúster supera su presupuesto.
  - Evidencia: `pytest tests/test_fund_web.py -q` → 6 passed.
- [x] **9.5 Intradía forex/CFD** — 2026-11-08, corregido tras reapertura
  - El primer informe usó offset constante y queda conservado como **no
    fiable: offset constante** en `reports/research/intraday_offset_constante.*`.
  - `execution/mt5_offsets.py`: offset por semana desde apertura dominical y
    cierre del viernes en hora de servidor, contra 17:00 America/New_York;
    confirma +2/+3 en las transiciones de EE. UU. (22:00/21:00 UTC).
  - `MT5Broker.rates` aplica el offset de cada barra; `lab mt5 fetch` imprime
    los tramos y escribe `EURUSD_<TF>.offsets.json`.
  - M15: 50.000 barras, 2024-11-04 01:45 → 2026-11-08 23:45 UTC, 5 tramos.
    H1: 20.000 barras, 2023-08-21 14:00 → 2026-11-08 23:00 UTC, 8 tramos.
    Parquet UTC sin duplicados, `NaN` ni OHLC inválido; spread mediano 1/2
    puntos y `spread_reliable=True`.
  - Neto corregido: **0/28 pasan**, mejor Sharpe **−6,78**, PBO 0,0 % con
    `prob_oos_loss=100 %`, walk-forward fallido.
  - Costes por activo: comisión EURUSD **2,50 USD/lote/lado** de la tabla
    oficial de FTMO (“Trading Update | 25 Sep 2025”, 2025-09-25, vigente
    2025-09-29; **0,217 bps/lado**), spread real horario (0,853 bps mediana)
    y slippage explícito optimista 0,5 / conservador 2,0 bps por lado.
  - Coste de equilibrio: mejor variante **0,32 bps**, coste calibrado mediano
    **3,72 bps**; tabla de Sharpe a 0/0,5/1/2/3 bps en informe y Research.
  - Diagnóstico sin costes: mejor bruto **+1,34**, pero PBO 39,4 % y WF
    fallido; la pullback cae a −24,79 neto y la mejor neta (ORB) tiene bruto
    −0,91. Los costes explican el desplome y el equilibrio es menor que el
    coste calibrado; sin edge bruto robusto.
  - Alineación verificada: aperturas semanales 22:00 UTC (invierno) y 21:00
    UTC (verano). Solo avanza el escenario conservador. No se relajó ningún
    umbral, no se activó ningún bot y no se enviaron órdenes.
- [x] **9.6 Documentación** — 2026-11-07
  - README 6d con cuentas, reglas, seguridad, panel, resultados por perfil y
    estado de la etapa 5; tabla por perfil también en Research.
  - Resumen final: 249 tests, `ruff` limpio, `lab doctor` OK salvo Finnhub,
    ProjectX y plantilla de fondeo.

## Fase 10 — Diario y control operativo (etapas 1–6)

Objetivo: medir la operación real (no el backtest) y convertirla en decisiones
controladas, sin activar bots, sin órdenes, sin dinero real y sin tocar `.env`.

- [x] **10.1 Diario de operaciones cerradas** — 2026-11-07
  - `journal.py` reconstruye operaciones cerradas desde `fills` + `orders` con
    lotes FIFO por `(bot, ticker)`, en **solo lectura**. Sin fill, sin lote o sin
    cuenta/perfil en `config/bots.yaml` → **sin datos**; no se inventa PnL.
  - Métricas: retorno sobre capital atribuido, win rate, profit factor,
    expectancy, Sharpe/Sortino/Calmar (PnL diario, 252), MaxDD, distribución de
    retornos e histograma. Aviso si N < 30.
  - Concentración: top 3/neto, top 3/bruto, mejor día/neto y comparación con
    `consistency_pct` de `prop.yaml`.
  - `lab journal` con filtros por bot/cuenta/perfil/activo/fecha y agrupación
    por bot/cuenta/perfil/activo/día/hora; pestaña **Diario** en la consola.
  - Evidencia: `pytest tests/test_journal.py -q` → 7 passed; sobre el `lab.db`
    actual `lab journal` muestra “sin datos” (1 fill abierto, 0 cerradas).
- [x] **10.2 Multiverse por operación** — 2026-11-07
  - `multiverse_by_trade`: 1.000 permutaciones de las operaciones (no de los
    días), semilla fija 42, curvas p5/p50/p95, MaxDD esperado/mediano/peor 5% y
    probabilidad de breach diario, máximo y cualquiera.
  - El límite diario conserva el número de operaciones por día original
    (`bloques_por_dia`); sin días usa `por_operacion`. Se documenta la base.
  - Visible en **Diario** (por cuenta) y **Run Detail**. Run Detail lee el
    sidecar `.trades.parquet`; los artefactos antiguos sin sidecar muestran
    **Sin datos**.
  - Evidencia: `pytest tests/test_multiverse.py -q` → 7 passed; `lab research`
    nuevo guarda sidecar de operaciones por artefacto.
- [x] **10.3 Deriva live vs backtest** — 2026-11-07
  - `drift.py` compara Sharpe/expectancy del Diario con la última evaluación de
    backtest, con IC bootstrap 95% (1.000 remuestreos, seed 42) y mínimo de 20
    operaciones live.
  - Slippage real (fills vs señal) contra el supuesto del backtest y los máximos
    de F13; mínimo 5 fills.
  - Estados **ok / vigilar / deriva**; sin muestra → **Sin datos**. Solo
    informativo, no bloquea bots ni órdenes.
  - `lab drift` y panel **Bots → Deriva live vs backtest**.
  - Nueva columna `bot_evaluations.expectancy` (migración incluida); filas
    antiguas sin ella → Sin datos.
  - Evidencia: `pytest tests/test_drift.py -q` → 5 passed; suite completa
    284 passed.
- [x] **10.4 Salud de cuenta y libro de capital** — 2026-11-07
  - Score 0-100 con pesos en `config/lab.yaml` (`fund_health.weights`):
    colchón diario, colchón de drawdown, racha, deriva y concentración.
  - Desglose por componente, cobertura y `partial`; sin datos no se inventa.
  - Tabla `account_cash_flows` (depósitos/retiros), CLI `lab fund flow-add` y
    `lab fund flows`, y TWR diario descontando flujos.
  - Retorno del fondo TWR ponderado por capital con cobertura; solo cuentas con
    equity histórico local.
  - Visible en **Fondo** (salud y libro de capital).
  - Evidencia: `pytest tests/test_health.py -q` → 5 passed; suite completa
    289 passed.
- [x] **10.5 Streak lock y pausa** — 2026-11-07
  - Pausa de aperturas por N pérdidas seguidas o X% de pérdida diaria propia;
    cerrar/reducir nunca se bloquea.
  - Umbrales en `account_risk_config` con `account_risk_history`, fuera del
    hash de F13. Apretar inmediato; aflojar/reanudar con confirmación y F13
    congelado solo permite apretar.
  - Integrado en `orchestrator.run_bot` y modo operador; Fondo muestra pausa y
    botón Reanudar.
  - CLI `lab fund pause-status|pause-set|pause-resume`.
  - Evidencia: `pytest tests/test_riskpause.py -q` → 4 passed; suite completa
    295 passed.
- [x] **10.6 Aprendizaje controlado** — 2026-11-07
  - `lessons` proposed/approved/rejected con autor `qwen|humano`; Qwen solo
    redacta, el texto de noticias/LLM es no confiable.
  - `learning_holdout` sellado con hash; `record_test` rechaza ventanas que lo
    pisen. Cada prueba incrementa `lesson_tests`, sumado a `n_trials` del DSR.
  - Campeón/retador en paper (`kind=challenger`) queda `proposed`; no activa ni
    cambia `enabled`.
  - Auto-aplicación solo `reduce_risk`; guarda reversión. El resto exige
    aprobación humana. Panel **Aprendizaje** y CLI `lab lessons ...`.
  - Evidencia: `pytest tests/test_learning.py -q` → 6 passed; suite completa
    301 passed.

- [x] **10.7 Reportes CSV/HTML** — 2026-11-07
  - Exportes de Diario, deriva y aprendizaje a `reports/exports` con validación
    de formato/ruta, límite de filas y sin secretos.
  - Vista previa en CLI (`lab reports preview`) y en Registros.
  - Evidencia: `pytest tests/test_exports.py -q` → 4 passed; suite completa
    305 passed.

## Fase 11 — Modo operador (etapa 7)

Objetivo: permitir acciones paper/demo desde la consola con armado por PIN,
confirmación en dos pasos, guards equivalentes a la CLI y auditoría.

- [x] **11.1 Armado, PIN y caducidad** — 2026-11-07
  - Desarmado por defecto; PIN en keyring (`lab operator pin`), nunca en
    `.env`, logs ni auditoría. Ventana configurable (15 min por defecto),
    bloqueo tras N intentos y desarmado al reiniciar.
- [x] **11.2 Acciones y guards** — 2026-11-07
  - Ejecutar bot, orden paper/demo, cerrar, aplanar y activar/desactivar bots.
  - Rechazo de `mode=live`, cuentas no paper/demo y MT5 sin `require_demo`.
  - `evaluate_account`, límites efectivos, kill-switch, blackout e identidad
    reutilizados; cierre/reducción nunca se bloquea.
  - Preview con cuenta, símbolo, lado, qty, precio, SL, riesgo %, equity y
    colchón; token de un solo uso de 60 s.
- [x] **11.3 Runtime de bots y F13** — 2026-11-07
  - `bot_runtime_state` + `bot_runtime_history`; `enabled` efectivo =
    YAML AND runtime. No se edita `config/*.yaml`.
  - F13 congelado/iniciado bloquea activar/modificar su bot; hash intacto.
- [x] **11.4 Auditoría y superficie de escritura** — 2026-11-07
  - `console_actions` con parámetros saneados y resultado; visible en Operador
    y Registros. Sin PIN ni tokens.
  - CSRF + Host/Origin + `WRITE_ROUTES` + `X-Operator-Client`; sin endpoints
    de live, copy trading, EAs o ejecución de código.
- [x] **11.5 Tests y documentación** — 2026-11-07
  - `pytest tests/test_operator.py -q` → 11 passed; suite completa y README 6f.
- [x] **11.6 El CLI lee el armado del panel** — 2026-11-11
  - `lab drill` construía un `OperatorService` nuevo en su propio proceso, así
    que su sesión en memoria nacía vacía y `armed` siempre era `False`: el
    simulacro era inejecutable aunque el panel estuviera armado.
  - `operator.server_session()` consulta `GET /api/operator` en loopback
    (sin proxies, timeout 2 s) y `web_port()` respeta `LAB_WEB_PORT`. El
    armado sigue viviendo solo en la memoria del panel y se pierde al
    reiniciar; sin panel el CLI falla cerrado con un mensaje explícito.
  - `lab operator status` muestra el armado real y sus segundos restantes en
    lugar de una frase fija.
  - `pytest tests/test_operator.py -q` → 20 passed (3 nuevos).

## Fase 12 — Shell de consola y dashboard (etapa 1)

Objetivo: barra lateral oscura colapsable por secciones y dashboard operativo,
sin romper vistas ni añadir dependencias.

- [x] **12.1 Navegación por secciones** — 2026-11-07
  - Secciones: Principal, Laboratorio, Portafolios, Riesgo y fondeo,
    Inteligencia y Sistema.
  - Se conservan las 15 vistas actuales, incluidas Fondo, Diario y Operador.
  - Colapso icon-only persistido en `localStorage`; en móvil vuelve a barra
    horizontal.
- [x] **12.2 Dashboard** — 2026-11-07
  - Tarjetas KPI (incluye PnL del mes), distribución cash/posiciones y por
    cuenta, top performers por Sharpe y calendario mensual de PnL con navegación
    de mes.
  - Si no hay datos: **Sin datos**.
- [x] **12.3 Restricciones de consola** — 2026-11-07
  - Sin CDNs, frameworks, logos ni textos de terceros; HTML/CSS/JS propio.
  - Se mantienen CSRF, Host/Origin, `WRITE_ROUTES`, Fondo/Diario/Operador y
    todas las rutas.
- [x] **12.4 Tests y documentación** — 2026-11-07
  - `pytest tests/test_console_shell.py -q` → 3 passed; `test_web.py` añade
    datos sintéticos de equity/evaluación para el dashboard.
  - README 6g y PLAN Fase 12.

## Fase 13 — Control remoto por Telegram

Objetivo: recibir resúmenes y dar instrucciones desde Telegram sin abrir
puertos, sin exponer secretos y sin habilitar live.

- [x] **13.1 Puente seguro** — 2026-11-07
  - Long polling; token y chat ID en keyring; solo chat/usuario autorizado;
    ignora mensajes reenviados.
  - `config/telegram.yaml` ignorado por git; estado local en
    `data/telegram_state.json`.
- [x] **13.2 Comandos y modo agente** — 2026-11-07
  - Modo `commands` por defecto: `/status`, `/f13`, `/decisions`, `/ping`,
    `/pause`, `/resume`, `/mode`, `/new`, `/continue`.
  - Modo `agent`: `opencode run --agent telegram` con allowlist de shell;
    `.env`, `config/`, `data/`, borrado, `git push` y `f13 freeze` denegados;
    bloqueo si el laboratorio no está en paper.
- [x] **13.3 Arranque y notificaciones** — 2026-11-07
  - `scripts/telegram_bridge.ps1` + `scripts/register_telegram_task.ps1`
    (tarea al iniciar sesión; no se registra automáticamente).
  - `lab telegram send` para el resumen final; el puente envía el resumen del
    agente.
  - Configurado en vivo el 2026-11-07: `@Arowarlin_TradingLab_bot`; tarea
    `TradingLab-Telegram` **Running**; `/ping` → `pong` y `/continue` → agente
    OK. Sin activar bots ni F13.
- [x] **13.4 Tests y documentación** — 2026-11-07
  - `pytest tests/test_telegram.py -q` → 23 passed; suite completa **352
    passed**; `docs/telegram.md`; README 11d; `lab doctor` muestra Telegram
    remoto.
- [x] **13.5 Push/backup con aprobación humana** — 2026-11-07
  - `/push`, `/backup` y `/pushbackup` generan un código de 6 dígitos válido
    5 minutos y de un solo uso; `/confirm <código>` ejecuta; `/cancel` y
    `/pause` cancelan.
  - Push solo rama `master`, `git fetch` previo y sin `--force`; backup ejecuta
    `scripts/backup.ps1` con restore test.
  - Auditoría en `console_actions` con actor `telegram:<user_id>`; sin token ni
    código. El agente automático sigue sin poder hacer push.
  - Evidencia: `pytest tests/test_telegram.py -q` → 23 passed; suite completa
    352 passed.

## Etapa 0 — Correcciones pendientes (2026-11-07)

- [x] **A) Fallo de `f13.status` bloquea y audita**
  - `_f13_bot_locked` devuelve `True` si falla la lectura de F13 y registra
    `f13_status_error` en `console_actions` con error saneado (sin rutas).
  - Test con excepción simulada y comprobación de auditoría.
- [x] **B) PIN 6–12 y bloqueo persistente**
  - `set_pin` exige 6–12 dígitos; un PIN corto existente no se borra.
  - `lab operator status` y la consola muestran aviso de rotación.
  - `operator_pin_state` guarda fallos y `locked_until`; sobrevive reinicios.
  - Tests de mínimo, rotación y persistencia entre instancias.
- [x] **C) Deny de edición del agente Telegram acotado**
  - Solo `scripts/*`, `AGENTS.md`, `operator.py`, `killswitch.py`, `risk.py`,
    `f13.py` y `prop/*`; el resto editable.
  - Test que verifica los deny y que `cli.py`, `README.md` y `tests/` siguen
    editables.
- [x] **D) `/push` muestra diffstat y archivos**
  - El mensaje pendiente incluye `diffstat` y `archivos` antes del código.
  - Sin cambiar el destino: `origin/master`.

Evidencia de la etapa: `pytest tests/test_operator.py tests/test_telegram.py -q`
→ 41 passed; `ruff` limpio; `lab doctor` OK. Sin tocar Telegram, sin push y sin
activar bots/F13.

## Etapa 1 — Calidad de datos (2026-11-07)

- [x] **`datacheck.py` y CLI**
  - `lab datacheck <símbolo> [--timeframe]` sobre parquet: huecos, duplicados,
    orden, OHLC, saltos, TZ, ajuste y bid/ask/mid/spread.
  - Resultado ok/aviso/falla con motivos y fechas.
  - Metadatos de ajuste/TZ al escribir cachés nuevas de Yahoo.
- [x] **Look-ahead**
  - Test que compara estrategias e indicadores con serie truncada vs completa;
    la señal en `t` no cambia al añadir datos posteriores.
- [x] **Gate de research**
  - Un activo con datacheck `falla` no genera resultados ni propuestas.
  - `datachecks` viaja en `latest.json`/`proposals.json` y en cada propuesta.
  - Panel Research y Run Detail muestran estado y motivos.
  - No se relajan umbrales: el gate solo añade un bloqueo.
- [x] **Datos reales**
  - SPY/QQQ `aviso` (huecos de festivos y ajuste no declarado en cachés viejas).
  - EURUSD=X `falla` (88 barras OHLC inconsistentes) y queda fuera de research.
  - GC/`Sin datos` hasta la Etapa 5.

Evidencia: `pytest tests/test_datacheck.py tests/test_lookahead.py
tests/test_research.py -q` → 30 passed; `pytest -q` → 375 passed; `ruff`
limpio; `lab doctor` OK. Sin dependencias nuevas.

## Etapa 2 — Métricas informativas (2026-11-07)

- [x] **SQN, Recovery Factor y riesgo de ruina**
  - `metrics.py` con fórmulas documentadas y supuestos de independencia.
  - `journal.summarize` y `backtest.compute_metrics` los calculan.
  - `research` los guarda por variante y propuesta; el informe tiene sección
    “Métricas informativas”.
  - Diario y Run Detail los muestran. Con N<30, aviso; no cambian criterios.
- Evidencia: `pytest tests/test_metrics.py tests/test_journal.py
  tests/test_engine.py tests/test_research.py -q` → 33 passed; `pytest -q` →
  379 passed; `ruff` limpio; `lab doctor` OK. Sin dependencias nuevas.

## Etapa 3 — Régimen informativo (2026-11-07)

- [x] **Clasificador causal por reglas**
  - Tendencia (SMA200 + pendiente SMA50) y volatilidad (20d vs mediana 252d).
  - Etiquetas `trend_up`/`trend_down`/`range`/`unknown`; sin futuro.
  - Test truncado vs completo.
- [x] **Métricas de régimen**
  - Estabilidad, duración media, cambios, falsos cambios y retraso de
    detección (referencia centrada solo para evaluación).
  - Rendimiento por régimen para el activo y para un bot (`--bot`).
- [x] **Dashboard y selector**
  - Panel “Régimen de mercado” en el Dashboard con el régimen actual de QQQ.
  - Selector por régimen `proposed`, `enabled:false`, no aplicado.
- [x] **GMM/HMM**
  - hmmlearn 0.3.3 y scikit-learn 1.9.1 (BSD-3) evaluados, no adoptados;
    sin dependencias nuevas. Documentado en `docs/regimes.md`.
- Evidencia: `pytest tests/test_regimes.py tests/test_web.py -q` → 23 passed;
  `pytest -q` → 386 passed; `ruff` limpio; `lab doctor` OK.

## Etapa 4 — Validación de modelos (2026-11-07)

- [x] **Purged K-Fold y CPCV**
  - `PurgedKFold`/`CombinatorialPurgedCV` en `models.py`, con purge antes y
    embargo después del test.
  - `train_purged_cv` valida el ridge sin registrar ni promocionar modelos.
  - Tests de no solapamiento, bloqueo de purge/embargo y número de splits CPCV.
- [x] **Meta-labeling/triple barrera**
  - Solo `docs/meta_labeling.md`: requisitos de ≥500 eventos, ≥100 por clase,
    etiquetado con barreras y validación purgada. No se implementa.
- Evidencia: `pytest tests/test_models.py -q` → 6 passed; `pytest -q` → 389
  passed; `ruff` limpio; `lab doctor` OK. Sin dependencias nuevas.

## Etapa 5 — Oro e instrumentos (2026-11-07)

- [x] **XAUUSD y GC separados**
  - XAUUSD `cfd`/`mt5`/`XAUUSD.SPOT`, GC `futures`/`projectx`/`GC.FUT`, con
    sesión, zona, tick, contrato y tick value propios.
  - Spread sin dato verificado: **Sin datos**, no inventado.
  - `validate_universe` rechaza mezclar clases en un mismo backtest.
- [x] **Bid/ask**
  - `normalize` conserva bid/ask/mid/spread y calcula mid/spread si faltan.
  - El `spread` de barras MT5 se conserva.
  - No se descargan series nuevas.
- Evidencia: `pytest tests/test_instruments.py tests/test_data_normalize.py -q`
  → 14 passed; `pytest -q` → 393 passed; `ruff` limpio; `lab doctor` OK.
  Sin dependencias nuevas.

## Etapa 6 — Biblioteca de conocimiento (2026-11-07)

- [x] **Fichas originales**
  - `docs/biblioteca/library.yaml` con 18 fichas: DSR, PBO, walk-forward,
    Monte Carlo, FRED, SEC, yfinance, LM Studio, Optuna, QuantStats, Qlib,
    hmmlearn, VectorBT, Backtrader, LEAN, ResearchGate, Google Scholar y SSRN.
  - Las tres fuentes científicas son de consulta manual: sin scraping, sin
    saltar paywalls y sin tratarlas como peer review.
  - Campos: problema, enlace, licencia, versión, dependencias, datos/costes,
    ventajas, riesgos, pruebas y estado/motivo.
  - `docs/biblioteca/README.md` generado; sin copiar texto de terceros.
- [x] **CLI**
  - `lab library list [--status]` y `lab library show <id> [--json]`.
- Evidencia: `pytest tests/test_library.py -q` → 4 passed; suite completa
  **531 passed**; `ruff` limpio; `lab doctor` OK. Sin dependencias nuevas.

## Etapa 7 — Optuna y QuantStats (2026-11-08)

- [x] **Optuna con walk-forward**
  - `optimize.py` + `lab optimize`: walk-forward sobre el desarrollo; el
    holdout sellado no se usa para seleccionar.
  - Cada trial se guarda en `optimization_trials` y suma a `count_tests`
    (`n_trials` del DSR).
  - Gates DSR ≥90%, PBO ≤30% y WF aprobado; si falla, propuestas vacías.
- [x] **QuantStats**
  - `quantstats_report.py` genera HTML por propuesta frente a SPY en
    `reports/research/quantstats/`; solo lectura.
  - Integrado en `lab research`; sin cambios de criterios.
- [x] **Dependencias**
  - Optuna 5.0.0 (MIT) y QuantStats 0.0.86 (Apache-2.0); `uv.lock` actualizado;
    `docs/dependencias.md` con licencias y versiones.
- Evidencia: `pytest tests/test_optimize.py tests/test_quantstats_report.py
  tests/test_learning.py -q` → 12 passed; `pytest -q` → 400 passed; `ruff`
  limpio; `lab doctor` OK. Smoke real: 3 trials, PBO 80,3%, 0 propuestas.

## Bloque 2026-11-08 — Etapas 1–3

### Etapa 1 — Holdout de una sola lectura

- [x] **Caché por configuración**
  - `holdout_evaluations` con hash de símbolo + estrategia + params.
  - Primera lectura calcula y guarda; segunda devuelve caché sin recalcular.
  - Cada lectura se registra en `holdout_reads` y suma al contador DSR.
  - `lab lessons holdout`, `lab lessons weekly` y Research muestran lecturas.
  - `run_optuna` recalcula el DSR tras la lectura y mantiene
    `used_for_selection: false`; los trials de desarrollo terminan antes del
    holdout.
- Evidencia: `pytest tests/test_learning.py tests/test_optimize.py
  tests/test_web.py -q` → 29 passed; `pytest -q` → 402 passed; `ruff` limpio;
  `lab doctor` OK. Sin dependencias nuevas.

### Etapa 2 — Limpieza de documentación

- [x] **README coherente con F13 activo en paper**
  - Tabla de fases: F13 en ✅ activo en paper con la tarea
    `TradingLab-F13` y primera ejecución el lunes 2026-11-09 22:20.
  - Sección 6d: F13 activo, `qqq-trend-f13` con `enabled: true`; se eliminó
    “congelado, sin activar” y el `enabled: false` obsoleto.
  - Sección 6p: el piloto de equity figura activo en paper.
  - Sección 11: `lab f13 status` descrito como activo y la activación como
    paso ya ejecutado.
  - Test `test_readme_f13_coherente_con_bots_yaml`: falla si el README afirma
    `enabled: false` para `qqq-trend-f13` mientras `bots.yaml` lo tiene activo,
    si conserva “congelado, sin activar” o si la fila F13 no dice paper/activo.
- Evidencia: `pytest tests/test_docs.py -q` → 4 passed; suite completa
  **408 passed**; `ruff` limpio; `lab doctor` OK. Sin cambios de
  comportamiento ni dependencias nuevas.

### Etapa 3 — Reporte diario F13 de la primera semana

- [x] **`lab f13 report` de solo lectura**
  - `f13.daily_report` escribe `reports/f13/YYYY-MM-DD.json`, su Markdown y
    `latest.json`/`latest.md`; no conecta al broker, no envía órdenes, no
    activa bots y no modifica tablas operativas.
  - Ciclos: una fecha con `data/dryrun/dryrun_*.json`; compara ejecutados vs
    días laborables esperados hasta ayer y aplica `min_cycles_pct`.
  - Reconciliaciones: total, OK y porcentaje desde `reconciliation`, con
    `min_reconciliation_ok_pct`; última fila incluida.
  - Slippage p50/p95 y error de tamaño desde `orders`/`fills`/`signals`, con
    `max_slippage_bps_p50`, `max_slippage_bps_p95` y
    `max_size_error_shares`.
  - Hash congelado vs actual y criterios congelados de F13 en el JSON/Markdown.
  - Alerta `f13_monday_missed` si el último lunes esperado dentro de la ventana
    F13 no tiene ciclo; no se alerta antes del lunes de inicio ni el mismo
    lunes (el ciclo puede estar en curso).
  - `scripts/f13_daily.ps1` añade `lab f13 report` tras `f13 check`.
- Evidencia: `pytest tests/test_f13.py -q` → 16 passed; suite completa
  **408 passed**; `ruff` limpio; `lab doctor` OK; sintaxis del `.ps1` OK;
  `lab f13 report` real generó `reports/f13/2026-11-08.json` y `.md` con
  hash `54b420360f17c75d…` OK, 0 ciclos/0 reconciliaciones (F13 empieza el
  lunes) y sin alertas. Sin dependencias nuevas.

---

## Rediseño visual v3 de la consola (2026-11-08)

Solo presentación: sin cambios de rutas API, endpoints, permisos, lógica del
operador ni datos. Inventario base en `docs/ui_inventory.json` y test
`tests/test_console_shell.py::test_inventario_ui_base_sigue_completo`.

### Etapa 1 — Tokens y barra HUD

- [x] **Tokens y tipografía**
  - Grafito `#080c12`, acento cian `#4cc9f0`, semánticos `--positive`,
    `--negative` y `--alert`; radios, sombras y espaciado como variables.
  - Números con `font-variant-numeric: tabular-nums` y monoespaciada del
    sistema; etiquetas pequeñas en mayúsculas con tracking.
- [x] **Barra HUD fija**
  - Modo PAPER, sesión/reloj de Praga, LED de kill-switch, F13, salud de datos
    y operador.
  - Operador armado muestra cuenta atrás `mm:ss` y borde ámbar fijo en toda la
    consola mientras dura; datos de `/api/overview` y `/api/operator`.
- [x] **Inventario congelado**
  - 15 vistas, 232 ids, 34 llamadas `/api/*`, 6 secciones y 15 pestañas.
  - Test falla si desaparece una vista, pestaña, id o llamada; las altas de
    ids nuevos están permitidas.
- Evidencia: `pytest tests/test_console_shell.py -q` → 5 passed; suite completa
  **410 passed**; `ruff` limpio; `lab doctor` OK. Capturas Chrome de las 15
  pestañas en `reports/ui/before` y `reports/ui/stage1`, con diff por pestaña
  en `reports/ui/stage1_diff.json` (reportes ignorados por git).

### Etapa 2 — Componentes

- [x] **KPIs y gauges**
  - Delta y mini-sparkline con series reales de equity/retorno/PnL/drawdown;
    sin historial → “sin serie”.
  - Gauges de colchón diario, colchón de drawdown y salud de cuenta con marca
    de límite; datos de `fund.accounts[].usage` y `fund.health`.
- [x] **Chips, tablas y estados**
  - Chips con icono además de color.
  - Cabecera de tabla fija y densidad cómoda/compacta persistida en
    `localStorage` con `try/catch`.
  - Skeletons iniciales, pulso de refresco y transición de número; desactivados
    con `prefers-reduced-motion`.
- Evidencia: `pytest tests/test_console_shell.py -q` → 6 passed; suite completa
  **411 passed**; `ruff` limpio; `lab doctor` OK. Capturas de las 15 pestañas
  en `reports/ui/stage2` y diff en `reports/ui/stage2_diff.json`.

### Etapa 3 — Gráficas SVG y mapas de calor

- [x] **Equity SVG**
  - Área degradada cian, línea, ejes, último valor y cruz de lectura.
  - Marcas de operaciones reales desde `account.orders`; si no hay órdenes en
    el rango, no se dibujan.
  - Bandas de régimen desde `overview.regime.bands`/`regime_bands`; sin datos →
    “Sin datos de régimen histórico”, sin curvas inventadas.
- [x] **Mapas de calor**
  - PnL diario con intensidad relativa al mes y escala divergente ámbar/cian.
  - Correlación entre bots desde `research.horizons.correlations`, con umbral
    resaltado y etiquetas cortas.
- Evidencia: `pytest tests/test_console_shell.py -q` → 7 passed; suite completa
  **412 passed**; `ruff` limpio; `lab doctor` OK. Smoke SVG con copia temporal
  de DB y 40 snapshots: línea, marcas y cruz; `data/lab.db` real intacto.
  Capturas de las 15 pestañas en `reports/ui/stage3` y diff en
  `reports/ui/stage3_diff.json`.

### Etapa 4 — Accesibilidad, responsive y refresco

- [x] **Accesibilidad**
  - Contraste AA, `:focus-visible` con anillo cian, enlace “Saltar al
    contenido” y `aria-current="page"` en la pestaña activa.
  - Barra lateral navegable con flechas/Home/End; Ctrl+K intacto.
- [x] **Responsive y rendimiento**
  - Layout a 390 px sin desbordamiento horizontal; HUD y acciones se envuelven.
  - Refresco de 8 s con huella del payload y re-render solo si cambió; sin
    mutaciones de `#kpis` en 9,5 s de observación CDP.
  - Sala pixel conserva `#office-floor`, `renderSala()` y su comportamiento.
- Evidencia: `pytest tests/test_console_shell.py -q` → 8 passed; suite completa
  **413 passed**; `ruff` limpio; `lab doctor` OK. Capturas de las 15 pestañas
  en `reports/ui/stage4`, móvil en `reports/ui/stage4/overview_mobile.png` y
  diff en `reports/ui/stage4_diff.json`; Ctrl+K y flechas verificados por CDP.

### Ajustes de formato y métricas

- [x] **Gauges y cero negativo**
  - Arco de colchón = `1 - used`; `used=0` llena el arco y `used=0.8` lo deja
    al 20 % con estado `AL LÍMITE`.
  - `clampZero`/`toneFor`: porcentajes entre -0,005 % y 0 se muestran `0.00 %`
    con tono neutro y sin flecha roja.
- [x] **Salud, moneda y performers**
  - Cobertura <100 % → `PARCIAL · cobertura N%`; centro `100`, sin `/100`,
    para no pisar el arco.
  - `useGrouping: "always"` en moneda (`9.973,51 US$`).
  - Título visible `Evaluaciones de backtest (no reales)` y nota de que los
    trades son eventos de PnL por rebalanceo, no round-trips.
  - Causa de `qqq-trend-f13` 864: `backtest.py` usa `len(realized)` y el bot
    rebalancea a diario; no se modificó la lógica del backtest.
- [x] **Régimen compacto**
  - Sin datos → `panel-compact`, una fila, sin panel alto.
- Evidencia: `pytest tests/test_console_js.py tests/test_console_shell.py -q`
  → 11 passed; suite completa **416 passed**; `ruff` limpio; `lab doctor` OK.

---

## Bloque 2026-11-08 — Cementerio de estrategias (etapas 1-7)

Reglas del bloque: sin activar bots, sin órdenes, sin dinero real, sin tocar
`.env`, sin push, sin cambiar el modo de Telegram, sin borrar nada, sin relajar
umbrales y sin mover módulos. `lab f13 config-check` antes y después de cada
etapa.

### Etapa 1 — Registro de todo lo probado y contador DSR

- [x] **Tabla `strategy_trials`**
  - Familia, hipótesis, activo, parámetros, fecha, resultado, motivo de
    descarte, fuente, `run_id`, `lesson_id` y fingerprint de familia+ventana.
  - Se guardan **también las fallidas**.
- [x] **Contador único del DSR**
  - `count_tests` = lecciones + trials de Optuna + lecturas de holdout +
    `strategy_trials` + bots incubados (hook; 0 hasta la etapa de ciclo de vida).
- [x] **Aviso de reoptimización**
  - Si la familia ya se descartó sobre la misma ventana, avisa antes de
    repetir: EURUSD 2024-11-04→2026-11-08 deja 8 `orb`, 16 `pullback` y 4
    `asian_rev` descartados.
- [x] **Presupuesto semanal por activo**
  - `config/research_budget.yaml` (nuevo): 5 intentos por activo y semana ISO;
    `lab research-intraday` se detiene al agotarlo salvo `--force`.
- [x] **Hipótesis en `lessons`**
  - Las hipótesis nuevas (humanas o de Qwen) nacen como `proposed`; Qwen solo
    redacta y nunca ejecuta (test).
- [x] **Registro real**
  - Barrido EURUSD M15: 28 variantes registradas (run `c7fd4e2c7fd0`), contador
    DSR 5 → 33, presupuesto EURUSD 1/5.
  - `lab research-trials` lista el cementerio, el presupuesto y el contador.
- Evidencia: `pytest tests/test_trials.py tests/test_intraday.py -q` → 18
  passed; suite completa **436 passed**; `ruff` limpio; `lab doctor` OK (WARN
  conocido del modelo configurado); `lab f13 config-check` OK antes y después
  con el mismo hash `54b420360f17c75d…`. Sin bots activados, sin órdenes y sin
  tocar `bots.yaml`, `lab.yaml`, `prop.yaml` ni `f13.yaml`.
### Etapa 2 — Universo bloqueado y un bot distinto por activo

- [x] **Alias reales del broker**
  - Descubiertos en MT5 (no supuestos) y guardados en `asset_aliases`:
    `NASDAQ→US100.CASH`, `XAUUSD→XAUUSD`, `EURUSD→EURUSD`,
    `USDJPY→USDJPY`.
  - `lab mt5 aliases` descubre y persiste; el perfil `intraday_fx` solo
    admite esos cuatro símbolos.
- [x] **Guard de universo**
  - El orquestador bloquea aperturas (`delta > 0`) de cualquier símbolo fuera
    del universo `intraday_fx`; cierres y reducciones nunca se bloquean.
  - El modo operador aplica la misma restricción al previsualizar una orden
    sobre una cuenta con bolsillo `intraday_fx`.
- [x] **Bots intradía declarados**
  - `config/intraday_bots.yaml` (nuevo): 8 bots, todos `enabled:false`,
    `profile: intraday_fx`, `timeframe: M15`, con familia y rejilla propia por
    activo; no se comparten parámetros entre activos.
  - Nasdaq: `orb_ny`, `trend_intraday`. XAUUSD: `asian_rev`,
    `overlap_breakout`. EURUSD: `range_reversal`, `london_pullback`. USDJPY:
    `session_trend`, `tokyo_breakout`.
  - `load_bots` carga `bots.yaml` + `intraday_bots.yaml`; `bots.yaml` no se
    tocó. Las familias aún no implementadas se bloquean sin lanzar órdenes.
- Evidencia: `pytest tests/test_asset_aliases.py tests/test_intraday_bots.py -q`
  → 7 passed; suite completa **443 passed**; `ruff` limpio; `lab doctor` OK
  (WARN conocido del modelo); `lab f13 config-check` OK antes y después con el
  mismo hash `54b420360f17c75d…`. Sin activar bots, sin órdenes y sin tocar
  `bots.yaml`, `lab.yaml`, `prop.yaml` ni `f13.yaml`.

### Etapa 3 — Costes calibrados y validación por activo

- [x] **Costes por activo**
  - Forex EURUSD/USDJPY: **2,50 USD/lote/lado** (FTMO Trading Update
    25-Sep-2025, vigente 29-Sep-2025; 0,217/0,250 bps).
  - Metales XAUUSD: **0,0007 % del volumen/lado** (misma tabla; 0,070 bps).
  - Índices US100.cash: **0** (FTMO “Zero Commissions on Indices”,
    2025-08-01/2025-11-04).
  - Spread real por hora medido por activo y slippage explícito 0,5/2,0 bps
    por lado (optimista/conservador).
- [x] **Datos y offset por activo**
  - 50.000 barras M15 por activo. La detección semanal elige apertura 17:00
    o 18:00 ET según el cierre del viernes: forex 22:00/21:00 UTC,
    metales/índices 23:00/22:00 UTC.
- [x] **Validación por activo**

  | Activo | Familias | DSR n | PBO | WF | Pasan | Mejor neto | Equilibrio | Calibrado |
  |---|---|---|---|---|---|---|---|---|
  | EURUSD | range_reversal, london_pullback | 57 | 0,0 % | fallido | 0/24 | −5,86 | 0,23 | 3,07 |
  | USDJPY | session_trend, tokyo_breakout | 81 | 2,1 % | fallido | 0/24 | −4,03 | 0,14 | 2,28 |
  | XAUUSD | asian_rev, overlap_breakout | 93 | 8,5 % | fallido | 0/12 | −0,23 | 1,61 | 2,08 |
  | US100.cash | orb_ny, trend_intraday | 117 | 37,2 % | fallido | 0/24 | −0,28 | 1,57 | 2,01 |

  - **0/84 variantes pasan**. XAUUSD y US100.cash se acercan, pero el coste
    calibrado supera el de equilibrio; US100 además incumple PBO (<30 %).
  - Cada variante quedó en `strategy_trials`; el contador único DSR terminó
    en **117**. Informes por activo en
    `reports/research/intraday_<ACTIVO>/intraday.md` y `.json`.
- Evidencia: tests de costes/familias/informes + suite completa; `ruff`
  limpio; `lab doctor` OK; `lab f13 config-check` sin cambios. Sin activar
  bots, sin órdenes y sin relajar umbrales.

### Etapa 3b — Puente forward experimental de forex (2026-11-10)

- [x] **Runner separado del orquestador**
  - `src/tradinglab/forward_intraday.py` + CLI `lab intraday forward|status`.
  - `config/intraday_forward.yaml` congela solo dos candidatos:
    EURUSD `london_pullback` (50/100/0.5/16) y USDJPY `tokyo_breakout`
    (8/0.25/4). No toca `intraday_bots.yaml` ni `bots.yaml`.
  - No es una validación: ambos tienen Sharpe negativo y no pasaron la
    puerta de incubación. Es una excepción forward documentada.
- [x] **Guardas fail-closed**
  - Solo `mode=demo`, `identity_ok=True`, cuenta `ftmo_demo`, login y
    servidor esperados; cualquier clave ausente o distinta de `True` aborta.
  - Volumen mínimo del símbolo, nunca más; stop ATR en el bróker; una
    entrada por bot y día UTC; cierre por señal, `max_hold` o corte.
  - Solo se cierran posiciones con el `magic` del bot; una posición ajena
    bloquea aperturas y nunca se toca.
  - Kill-switch, guard de cuenta, presupuesto, sesión, calendario y noticias
    se consultan antes de abrir; los cierres siempre están permitidos.
- [x] **Dry-run real**
  - `lab intraday forward` conectó a MT5 demo y evaluó ambos candidatos sin
    enviar órdenes. A las 16:05 UTC ambos estaban planos porque Londres y
    Tokio ya habían cerrado.
  - El runner necesita 5.000 velas M15 para que MT5 infiera el offset
    semanal; con 600 el terminal no puede confirmar la apertura del domingo.
- [x] **Signal-only programado**
  - `scripts/intraday_forward_signal.ps1` ejecuta `lab intraday forward`
    (dry-run) una vez por barra M15 dentro de las ventanas UTC de Tokio y
    Londres; no usa `--execute` ni envía órdenes.
  - Tarea `TradingLab-IntradayForward` registrada cada 5 minutos; el script
    filtra la ventana y la fase de la barra. Guarda log UTF-8 en
    `logs/intraday_forward/`.
- Evidencia: `pytest tests/test_forward_intraday.py -q` → **29 passed**;
  `pytest tests/test_scripts.py -q` → **14 passed**; suite completa
  **670 passed**; `ruff` limpio; F13 intacto
  (`54b420360f17c75d…`). Sin activar bots, sin órdenes reales y sin tocar
  `bots.yaml`, `lab.yaml`, `prop.yaml` ni `f13.yaml`.

### Etapa 3c — Guardián de equity en MetaTrader 5 (2026-11-10)

- [x] **Exportador (`src/tradinglab/guardian.py`)**
  - `build_config(account_id)` lee `config/accounts.yaml`, los límites
    efectivos de `prop/rules.py` y los `magic` de
    `config/intraday_forward.yaml`.
  - No inventa límites: aborta si falta la cuenta, el `firm/phase`, los
    límites de una cuenta propia o la lista de magics.
  - `export_config` escribe de forma atómica
    `MQL5/Files/tradinglab_guardian.json` si `lab.yaml -> mt5.data_path`
    existe; si no, `data/guardian.json` con aviso.
  - Incluye `reset_utc_offset_minutes` resuelto desde `reset_tz` (MQL5 no
    trae tzdata) y `limits_source` para trazabilidad.
- [x] **CLI `lab guardian export|status`**
  - Exporta y muestra cuenta, límites, reset, offset, magics y bots.
  - `status` enseña ruta, destino (terminal o respaldo), antigüedad y datos;
    sin JSON: **Sin datos**.
- [x] **EA `mql5/TradingLabGuardian.mq5`**
  - Lee el JSON en `OnInit` y cada 60 s; falla cerrado si falta un campo.
  - `OnTimer` cada 1 s; base del día en el primer tick tras las 00:00 locales
    y pico trailing persistidos en variables globales.
  - `ALERT`: Print + ntfy. `CLOSE`: cierra solo los magics listados, escribe
    `tradinglab_guardian_block.flag` y publica
    `TradingLabGuardianBlocked`; insiste cada 2 s. Nunca toca otro magic.
  - Log en `MQL5/Files/tradinglab_guardian.log`.
  - `TestEquityFile` permite probar umbrales con equity sintética en el
    Strategy Tester.
- [x] **Tests y documentación**
  - `tests/test_guardian.py`: 19 passed, 1 skipped (`@pytest.mark.mt5`).
  - `docs/guardian.md`: instalación, JSON, Strategy Tester con equity
    sintética y regla de activación.
  - Regla: `defense_mode: enforce` en el forward solo tras **5 días de sesión
    en ALERT sin falsos positivos**.
- Evidencia: `ruff` limpio; `pytest tests/test_guardian.py -q` → **19 passed,
  1 skipped**; suite completa **734 passed, 1 skipped**; `lab doctor` OK con
  los WARN conocidos (ProjectX sin credenciales y plantilla de fondeo). F13
  sin cambios respecto al estado previo: el hash ya estaba `changed`
  (`6250d4c0…`) por el bloque `daytrader`; este bloque no toca archivos F13.
  Sin activar bots, sin órdenes y sin push.
- Correccion 2026-11-11: hay **dos** terminales de MetaTrader 5 instalados y
  la API de Python se conectaba al que no tiene el EA, asi que la puerta
  backward se leia como 0 de 5 sesiones.
  - `config/guardian.yaml` (nuevo, fuera del hash de F13) fija el terminal del
    EA: `terminal_data_path()` lo busca primero y luego `lab.yaml`.
  - Si el terminal configurado no tiene log, `guardian_sessions` busca el log
    del EA en los demas terminales y avisa de ello; una ruta explicita no
    dispara esa busqueda.
  - `lab guardian export` vuelve a escribir el JSON directamente en
    `MQL5/Files` del terminal correcto (antes caia en `data/guardian.json`).
  - Estado real: **2 de 5 sesiones** (2026.11.10 y 2026.11.11), 0 disparos,
    puerta CLOSE pendiente.

- Estado operativo 2026-11-10 23:42 UTC: EA compilado con **0 errores, 0
  warnings**, JSON copiado a `MQL5/Files`, EA cargado en **EURUSD H1** del
  perfil y corriendo en **ALERT** (log `INIT` + `START` + `CONFIG`), cuenta
  FTMO-Demo con 0 posiciones y 0 órdenes. Ventana de 5 sesiones en curso;
  `defense_mode` sigue en `report`. El chart quedó con `expertmode=0`: antes
  de `CLOSE` hay que ponerlo a 1 y confirmar algo trading.

### Etapa 3d — Oráculos externos del backtest y del simulador (2026-11-11)

- [x] **Venv de herramientas externas (`.venv-vbt`)**
  - `uv venv .venv-vbt` (CPython 3.12.16) con **vectorbt 1.2.0** (Apache-2.0),
    **prop-ev 0.1.0** (MIT, git `eea3870`) y pyarrow 26.0.1.
  - **No son dependencias**: fuera de `pyproject.toml` y de `uv.lock`, y el
    laboratorio nunca las importa. Versiones y licencias en
    `docs/dependencias.md`.
- [x] **Exportador de señales (`lab backtest --export-signals`)**
  - `src/tradinglab/export_signals.py` escribe parquet con fecha, símbolo,
    objetivo de exposición, precio de ejecución, comisión, spread y slippage,
    más qty, side y equity; sidecar `.meta.json` con las métricas del motor.
  - `backtest.py` **no se modifica**: el exportador lee su resultado y replica
    solo el filtro de sesión.
  - `lab backtest` admite además `--family` (intradía M15), `--params` y
    `--exposure`.
- [x] **Oráculo vectorbt (`scripts/oracle_vectorbt.py`)**
  - Recomputa la curva con vectorbt desde las mismas primitivas y compara
    operaciones, PnL total, diferencia por operación (>0,1 %) y curvas.
  - Resultados: **qqq-trend-f13** equity final idéntica (154.886,93) y 584
    operaciones alineadas; **london_pullback EURUSD** 1.542 operaciones
    alineadas, diferencia máxima **0,010 %**; **tokyo_breakout USDJPY** 180
    operaciones, diferencia máxima **0,011 %**. Ninguna operación supera el
    umbral de 0,1 %.
  - Informe en `reports/research/oracles/vectorbt_<bot>.md`.
- [x] **Oráculo prop-ev (`scripts/oracle_prop_ev.py`)**
  - Exporta los retornos diarios de `qqq-trend-f13` y los pasa a prop-ev con
    las reglas efectivas de `config/prop.yaml` (FTMO 100k).
  - 120 días / 1 fase: laboratorio **65,65 %** de P(pasar) y 8,25 % de breach;
    prop-ev **58,41 %**. 30 días / 2 fases: 5,30 % frente a 0,03 %.
  - Informe en `reports/research/oracles/prop_ev.md` con la lectura de por qué
    los dos motores no son equivalentes (bootstrap por bloques frente a
    gaussiana i.i.d. por operación, fases, horizonte y fee sin datos).
- [x] **Sin tocar `backtest.py` ni `prop/simulator.py`**: no hubo diferencias
  materiales; la diferencia de conteo de operaciones está documentada (el motor
  solo realiza PnL cuando la ejecución reduce la posición).
- [x] **Ficha de biblioteca**: `vectorbt` pasa a `status: verificacion` con
  motivo. Tests sintéticos del exportador en `tests/test_export_signals.py`.
- Evidencia: `ruff` limpio; suite completa **740 passed, 1 skipped**;
  `lab doctor` OK con los WARN conocidos; F13 sin cambios respecto al estado
  previo (`6250d4c0…`, ya `changed` por el bloque `daytrader`). Sin push, sin
  activar bots y sin órdenes.

### Etapa 3e — Cadena de hash de auditoría (2026-11-11)

- [x] **Migración aditiva**
  - `orders` y `console_actions` ganan `prev_hash` y `row_hash` (TEXT, NULL en
    las filas antiguas). `init_db` los añade si faltan; la migración es
    **idempotente** y no borra ni reescribe filas.
- [x] **`src/tradinglab/audit.py`**
  - `row_hash = sha256(prev_hash + json_canonico_de_la_fila_sin_los_dos_hashes)`.
    El JSON canónico usa **todas** las columnas de la tabla (las no escritas
    valen `None`), para que el hash no dependa del módulo que insertó.
  - `append_hashed(con, table, row)` inserta y sella la fila; `prev_hash` es el
    `row_hash` de la fila anterior por `id`.
  - `verify_chain(table)` devuelve `ok`, `first_break_id` y `n`. Las filas con
    hash NULL son "antes de la cadena" y **no** fallan.
- [x] **Escritores con cadena**
  - `runtime.py` (acciones de consola, incluida la del operador) y las cuatro
    escrituras de órdenes: `execution/paper.py`, `execution/alpaca.py`,
    `execution/mt5.py` y `execution/projectx.py`.
- [x] **CLI y alerta**
  - `lab audit verify [--table]` muestra el estado y avisa con
    `audit_chain_broken` si la cadena está rota (se puede silenciar con
    `--no-alert`). Sale con código 1 si hay rotura.
  - `lab f13 report` incluye el estado de la cadena de cada tabla.
- [x] **Tests**: cadena válida, fila alterada detectada, fila borrada detectada,
  filas antiguas sin hash que no rompen, migración idempotente, rechazo de
  tabla sin auditar y CLI.
- Evidencia: `ruff` limpio; suite completa **749 passed, 1 skipped**; en la
  base real `lab audit verify` → **OK** con 2+2 filas "antes de la cadena";
  `lab doctor` OK; F13 sin cambios respecto al estado previo (`6250d4c0…`).
  Sin push, sin activar bots y sin órdenes.

### Etapa 3f — Ranking de modelos (2026-11-11)

- [x] **`model_ranking()` en `agent_compare.py`**
  - Junta `lite_model_comparisons`, `agent_comparisons` y `decision_outcomes`
    para contar las decisiones por modelo (claves únicas ticker + fecha) y
    `llm_calls` para la tasa de `schema_ok`.
  - Por modelo: N de decisiones, acierto a 20 días (retorno con el signo de la
    dirección que dio), retorno medio a 20 días, latencia mediana en segundos,
    tasa de `schema_ok`, acuerdo lite/deep y `insufficient` si N < 30.
  - Sin datos devuelve lista vacía; los ratings sin dirección (Hold, REVIEW)
    no cuentan como acierto ni como retorno.
- [x] **Endpoint y CLI**
  - `GET /api/models/ranking` (solo lectura) en `web.py`.
  - `lab llm ranking`.
- [x] **Panel en la consola** (pestaña Agentes): "Ranking de modelos", ordenado
  por acierto, chip de muestra insuficiente y "Sin datos" cuando no hay.
  HTML/CSS/JS propios, sin CDN ni dependencias nuevas.
- [x] **Inventario UI** actualizado con los ids nuevos y la llamada a la API,
  sin retirar ninguna entrada previa.
- [x] **Tests**: ranking con datos sintéticos, caso vacío, orden por acierto,
  ratings sin dirección, muestra insuficiente y consola (panel + inventario).
- Evidencia: `ruff` limpio; suite completa **755 passed, 1 skipped**; en la base
  real `lab llm ranking` muestra 3 modelos con N = 3, 3 y 5, todos marcados
  **insuficientes** y sin retornos 20d todavía. Sin push, sin activar bots y
  sin órdenes.

### Etapa 3g — Verificación de TradingAgents y del modo lite (2026-11-11)

- [x] **Versión**
  - `tradingagents` **0.7.1** (Apache-2.0), instalado en editable desde
    `vendor/TradingAgents` (commit `9fa1196`). `.venv-ta` no tiene pip, así que
    la versión se comprueba con `import tradingagents; __version__`; queda
    documentado en `docs/dependencias.md`.
  - **0.7.1 ≥ 0.2.0**: no se actualiza. El modelo por defecto y
    `config/market_agents.yaml` no se tocan y el endpoint sigue siendo LM
    Studio. La API de configuración multi-proveedor no cambió, así que
    `scripts/run_tradingagents.py` **no se toca**.
- [x] **Modo lite con LM Studio**
  - `lab agent SPY|QQQ|NVDA --mode lite`: 3 de 3 correctos (98,1 s / 143,0 s /
    77,6 s de reloj).
  - `lab llm status`: 45 llamadas, **26 validadas, 26 OK, 0 fallidas** (antes
    15 OK y 0 fallidas) → `schema_ok` **no empeora**.
  - Latencia mediana de `qwen3.8-27b`: **109,2 s** frente a 116,8 s antes
    (**−6,5 %**, muy por debajo del +20 % permitido). Los otros dos modelos no
    cambian (78,1 s y 179,0 s).
- [x] **Hallazgo operativo documentado** (no es un problema de versión)
  - El deep exige ≥16.384 tokens de contexto: con 8.192 falla rápido con
    mensaje explícito y con 32.768 el run **superó la hora** en esta máquina.
  - Con **dos instancias** del modelo resident la latencia del lite se triplica
    (≈90 s → ≈250 s) porque una copia cae a CPU: la VRAM no da para dos copias
    de 17,74 GB. Con una sola instancia la latencia vuelve a su nivel. Queda
    documentado en `docs/dependencias.md` con los comandos `lms`.
- Evidencia: `ruff` limpio; suite completa **755 passed, 1 skipped**; `lab doctor`
  OK con los WARN conocidos; F13 sin cambios respecto al estado previo
  (`6250d4c0…`). Sin push, sin activar bots y sin órdenes.

### Etapa 3h — Puerta automática del guardián y presupuesto del deep (2026-11-11)

- [x] **La puerta de las 5 sesiones es automática**
  - `guardian.guardian_sessions()` lee el log del EA
    (`MQL5/Files/tradinglab_guardian.log`), cuenta las sesiones con línea
    `INIT` y los disparos con línea `TRIGGER`, y marca `gate_ok` solo con 5
    sesiones **y cero disparos**.
  - `lab guardian status` muestra sesiones, disparos y si la puerta está
    cumplida; `--json` lo deja disponible para scripts.
  - `scripts/guardian_enable_close.ps1` **se niega a tocar nada** si la puerta
    no está cumplida (código 1). Si lo está, aplica los tres cambios: preset
    del EA a `Mode=CLOSE`, `expertmode=1` en el chart del perfil y
    `defense: enforce` en el forward. Con `--DryRun` simula.
  - Estado real: **1 de 5 sesiones** (2026.11.10), 0 disparos → puerta
    **pendiente**; probado que el script se niega y no modifica nada.
- [x] **El deep ya no puede colgarse**
  - `scripts/run_tradingagents.py` acepta `--timeout-s` (1.800 s por defecto)
    con watchdog propio: al agotarse escribe el error y corta el proceso.
  - `agents/bridge.run_tradingagents` baja el presupuesto de 7.200 s a
    **1.800 s** y lo propaga al script.
  - Decisión: en esta máquina el deep no cabe (necesita ≥16k de contexto y con
    32k tardó más de una hora). Con el presupuesto acotado **falla rápido y
    claro** y el lado lite sigue su curso; para más margen hace falta más
    VRAM o menos analistas.
- Evidencia: `ruff` limpio; suite completa **759 passed, 1 skipped**; `lab doctor`
  OK; F13 sin cambios (`6250d4c0…`). Commit local pendiente de push en este
  bloque; sin activar bots y sin órdenes.

### Etapa 3i — Registro diario del guardián, deep explícito y lista de pre-apertura (2026-11-11)

- [x] **El guardián deja rastro diario sin tareas nuevas**
  - `scripts/intraday_forward_execute.ps1` escribe **una línea por día UTC** en
    su log con el estado del guardián (sesiones, disparos y puerta) antes de
    evaluar los bots; el estado se guarda en `logs/intraday_forward/
    guardian_state.txt` para no repetirlo.
  - Ejemplo real: `GUARDIAN sesiones=1/5 disparos=0 puerta=pendiente (solo 1 de
    5 sesiones; faltan 4)`.
- [x] **El deep falla de forma visible**
  - `lab agent-compare` añade una línea explícita cuando el deep no se
    completa (motivo y presupuesto de 1.800 s) en vez de un "—" silencioso.
  - Tests: el presupuesto llega al script, el padre mata 60 s después y el CLI
    avisa.
- [x] **Carril de acciones: lista de pre-apertura**
  - El ORB solo se refresca **dentro de sesión**; tras el cierre se genera la
    lista **diaria** (breakout 20d, bull flag, reclaim MA20, oversold y
    oversold bounce) con los cierres completos: es la entrada de la mañana.
  - Copia de seguridad del watchlist ORB del 2026-11-10 13:42 ET antes de
    sobrescribirlo.
  - El scan **no elige**: la elección del ticker sigue siendo del operador. La
    entrada de AAPL que quedó esperando (`trader/entry.json`, status
    `waiting`) expiró con el corte de las 15:30 ET.
  - El carril de acciones necesita además `daytrader.enabled: true` en
    `config/lab.yaml` (hoy `false`) para que el bróker paper ejecute.
- Evidencia: `ruff` limpio; suite completa **762 passed, 1 skipped**; `lab doctor`
  OK; F13 sin cambios (`6250d4c0…`). Commit local pendiente de push; sin activar
  bots y sin órdenes.

### Etapa 3d — Frescura de datos y desviación de reloj (2026-11-11)

- [x] **Tabla de frescura** (`data_freshness`)
  - `src/tradinglab/freshness.py` con `record()` y `check(symbol, timeframe, now)`.
  - La escriben **todos** los fetch: `data/yahoo.py` (yahoo), `intraday.save_bars`
    (mt5) y `data/ticks.py` (ticks).
  - `check()` compara la edad de la **descarga** con la frecuencia esperada por
    timeframe: `ok`, `aviso` o `falla`. **Sin dato es `falla`.**
  - Los umbrales salen de `config/lab.yaml -> freshness` si esa clave existe; si
    no, de los valores por defecto del módulo (documentados). **No se toca
    `lab.yaml`**: ese archivo está en el hash congelado de F13.
- [x] **Gate de aperturas**
  - `orchestrator.run_bot` y el forward intradía bloquean la **apertura** si los
    datos están en `falla` o si el reloj se desvía más de 10 s.
  - **Cierres y reducciones nunca se bloquean** (el camino de salida va antes).
  - El bloqueo por frescura queda auditado en `console_actions` (con la cadena de
    hash) y genera alerta `freshness_block`; el de reloj, `clock_block`.
- [x] **`clock.py`**
  - Compara la hora local con el **servidor MT5** (tick fresco) y con un **NTP
    público por UDP** (solo stdlib). Más de 2 s es `aviso`; más de 10 s, `falla`.
  - `lab doctor` muestra las filas **Reloj** y **Frescura**.
- [x] **SLO en la consola**
  - `GET /api/slo` (solo lectura): frescura por símbolo, desviación de reloj,
    drift de posición de la última reconciliación y último latido.
  - Tres LEDs fijos en el HUD: **DATOS**, **RELOJ**, **POSICIÓN**.
- [x] **Tests**: frescura ok/aviso/falla, sin datos, umbrales desde YAML, reloj
  desviado, apertura bloqueada y cierre permitido.

### Etapa 3e — Objetivo de volatilidad (2026-11-11)

- [x] **`vol_target.scale`**
  - EWMA de 30 días sobre la volatilidad diaria; factor = `min(apalancamiento
    máximo, objetivo / volatilidad)`.
  - Rebalance semanal: el factor se fija el lunes y se mantiene entre medias.
  - **Sin lookahead**: la volatilidad del día `t` usa solo datos hasta `t-1`.
- [x] **Perfiles** (`config/profiles.yaml`, no congelado en F13)
  - `target_vol`: equity 0,08 · intraday_fx 0,06 · intraday_futures 0,10.
  - `vol_target.enabled: false` en todos los perfiles: **nada se activa**.
- [x] **Motor e informes**
  - `backtest.run` acepta `vol_target` y multiplica el objetivo de exposición;
    los guards de presupuesto y de cuenta se siguen aplicando después.
  - `portfolio.account_vol_factor` aplica el segundo factor de cartera
    (opcional, `target_vol` por cuenta en `config/accounts.yaml`).
  - `lab research --vol-target on` escribe
    `reports/research/vol_target/comparison.md` con Sharpe, MaxDD, retorno,
    turnover, coste extra y P(pasar)/P(breach) de FTMO 100k en ambos casos.
- [x] **Tests**: el factor baja con la volatilidad, tope de apalancamiento,
  truncado vs completo, rebalance semanal, exposición menor en el backtest y
  umbrales por perfil.
- **Resultado medido (2026-11-11, `reports/research/vol_target/comparison.md`)**
  - | Bot | Sharpe | MaxDD | P(pasar) FTMO |
    |---|---:|---:|---:|
    | `qqq-trend-f13` | 0,83 → 0,81 | −8,57 % → −3,82 % | 65,65 % → **10,65 %** |
    | `trend-spy` | 0,75 → 0,71 | −24,15 % → −14,33 % | 59,60 % → 63,10 % |
    | `meanrev-large` | 0,22 → 0,23 | −36,94 % → −11,04 % | 38,45 % → **12,70 %** |
  - Resultado **mixto**: el objetivo de volatilidad recorta el|MaxDD (hasta la
    mitad) pero hunde la probabilidad de pasar el challenge FTMO en dos de los
    tres bots, porque la exposición se reduce justo en los tramos de retorno.
  - **No se activa**: `vol_target.enabled: false` en todos los perfiles. Queda
    medido y documentado, sin relajar umbrales.

### Etapa 3f — TCA: coste de ejecución real (2026-11-11)

- [x] **Tabla `tca`**
  - `fill_id, bot, account, symbol, side, signal_px, order_px, fill_px,
    slippage_bps, latency_ms, expected_cost_bps, realized_cost_bps, ts_utc`.
  - Se rellena al registrar cada fill en **paper**, **MT5** y **Alpaca**.
- [x] **`tca.py`**
  - EWMA de **20 fills** del slippage y del coste realizado, por bot y símbolo.
  - Estados con los umbrales de `drift.py`: `ok`, `vigilar`, `deriva`; con menos
    de 5 fills, **sin datos**.
  - La alerta `tca_drift` se envía **solo al pasar a `deriva`** (estado previo en
    `tca_state`).
- [x] **Integraciones**
  - `drift.py` añade la EWMA y el estado de TCA a cada fila de deriva.
  - `GET /api/tca` y panel **"Ejecución (TCA)"** en la pestaña Bots (slippage
    EWMA vs supuesto, fill rate, latencia mediana, coste realizado y estado).
  - `lab tca status [--bot]`.
- [x] **Tests**: EWMA, umbrales de estado, sin datos, EWMA del slippage y
  alerta una sola vez.

### Etapa 3g — Condicionadores de mercado (2026-11-11)

- [x] **`conditioners.py`** con flags diarios por fecha y símbolo, todos
  **causales** (para el día `t` solo se usan datos hasta `t-1`):
  - `pre_fomc`: 24 h antes de una reunión de la FOMC (desde `macro_events`).
    **Sin dato no hay flag** y se avisa.
  - `tom_window`: -5..+3 hábiles alrededor del Employment Report.
  - `month_end_selloff`: los 5 hábiles previos al fin de mes.
  - `monday_overnight`: lunes.
  - `boundary_extreme`: precio o retorno de 20 días a más de 2 desviaciones
    típicas de su propia historia (252 barras).
  - `regime_ok`: el régimen de `regimes.py`.
- [x] **Multiplicador de exposición** (`strategies/base.py`)
  - `exposure_multiplier(flags, table)` con tabla opcional por bot
    (`conditioners:` en `config/bots.yaml`). Por defecto todo 1,0: **no se toca
    `bots.yaml`** porque está en el hash congelado de F13.
- [x] **Research e informes**
  - `lab research --conditioned on` escribe
    `reports/research/conditioners/<bot>.md` con Sharpe, Sharpe stitched, MaxDD,
    bloques positivos y días afectados. Cada variante condicionada suma **1** al
    contador de pruebas del DSR (no uno por flag).
- [x] **API y consola**
  - `GET /api/conditioners/today` y panel **"Condicionadores activos"** en la
    pestaña Mercado (flags de la última sesión).
- [x] **Tests**: multiplicador, causalidad (truncado vs completo), flags sin
  calendario y días hábiles.
- **Resultado medido (2026-11-11, `reports/research/conditioners/`)**
  - Tabla propuesta: `pre_fomc` 0,5 · `tom_window` 0,75 · `month_end_selloff`
    0,75 · `monday_overnight` 0,75 · `boundary_extreme` 0,5 · `regime_ok` 1,0.
  - `qqq-trend-f13` con **1.498 días afectados**: Sharpe 0,83 → **0,76** y
    retorno 69,97 % → **49,67 %**, por un MaxDD que solo mejora de −8,57 % a
    −8,09 %. `trend-spy` y `meanrev-large` igual: sin mejora de Sharpe.
  - **No compensa**: los multiplicadores quedan como **propuesta** en
    `config/conditioners.yaml` (`default: {}` y `bots: {}`, sin efecto en
    producción). `proposal_table()` los deja disponibles solo para informes.
  - El multiplicador **sí** quedó conectado al orquestador (antes de los
    guards de apertura); con la tabla vacía no cambia el comportamiento.

### Etapa 3h — Familias de sesión intradía (2026-11-11)

- [x] **`session_hold`**: entrada en la apertura de sesión (Londres 08:00 o NY
  13:30 Europe/London, con DST), en el sentido del retorno de la sesión
  anterior (o el contrario con `direction`), stop ATR(14) × `k` y salida al
  cierre de la sesión. **Una operación por sesión.**
  - El stop se comprueba con el mínimo/máximo de la vela que lo rompe y la
    posición se cierra en el cierre de esa vela: el motor de serie no ejecuta
    intrabarra, así que el resultado es conservador frente a un stop real-fill.
  - El emparejado con la sesión anterior es lineal (antes era cuadrático).
- [x] **`fix_flow`**: flujo del fix (ECB 13:15 Europe/London, que equivale a
  14:15 CET, o London 16:00 Europe/London con DST): ventana de 30/60 min antes
  del fix, plano después, con filtro opcional de volatilidad.
- [x] **Bots** en `config/intraday_bots.yaml` con `enabled: false`
  (`eurusd-session-hold`, `usdjpy-session-hold-ny`, `eurusd-fix-flow`).
- [x] **Catálogo**: `Instrument.tick_ratio = tick_size / (precio × volatilidad
  diaria)` y visible en Mercado.
- [x] **Catálogo de research**: `session_hold` y `fix_flow` están en
  `INTRADAY_GRIDS` y asignadas a EURUSD y USDJPY (`ASSET_FAMILIES`) con
  rejillas acotadas (`session` × `direction` × `atr_k`; `window_min` × `side`
  × `fix` × `vol_filter`).
- [x] **Tests**: una operación por sesión, ventana del fix, causalidad, el stop
  recorta la exposición y el fix solo opera dentro de su ventana.

- **Resultado medido (2026-11-11, `reports/research/intraday_session/`)**
  - `session_hold` y `fix_flow` entran en la validacion intradia de EURUSD y
    USDJPY: **0 de 56 variantes pasan** (EURUSD 0/52, USDJPY 0/52).
  - Mejor Sharpe: **-2,33** (USDJPY `session_hold` LDN, `direction` -1, ATR
    x2,0) y **-4,04** en EURUSD; PBO 0,5-0,6 %; WF global **fallido**;
    DSR 0 en todas; P(pasar) FTMO 0,000.
  - El motivo es de costes, no de inestabilidad: el neto va de -0,14 % a -0,33 % y
    el equilibrio (0,00-0,94 bps) queda por debajo del coste calibrado del
    activo (2,51-3,16 bps). No hay edge que conservar.
  - **Se documenta y se para**: no se relajan umbrales, no se crea ningun bot y
    los tres bots de `config/intraday_bots.yaml` siguen `enabled: false`.
  - DSR acumulado: 365 pruebas; presupuesto semanal EURUSD 4/5 y USDJPY 3/5.

### Etapa 3i — Reversión overnight (2026-11-11)

- [x] **Universo**: SPY, QQQ, IWM, DIA, XLK, XLF, XLE, XLV, XLY, XLP, XLI,
  XLU, XLB, XLRE, XLC, TLT, GLD.
- [x] **`strategies/overnight_reversal.py`**
  - Retorno overnight `open_t / close_{t-1} - 1`.
  - `select_terciles`: largo el tercil más bajo, corto el más alto, pesos iguales.
  - `simulate_daily`: entra en la apertura y sale en el cierre (**sin posición
    nocturna**), con costes por lado.
- [x] **Costes**: 0 bps (optimista), 2 bps y 5 bps (conservador) por lado.
- [x] **Informe** `src/tradinglab/overnight_report.py` → 
  `reports/research/overnight_reversal/` con Sharpe, CAGR, MaxDD, retorno,
  operaciones, turnover y el Monte Carlo de FTMO 100k (P(pasar) y P(breach)).
- [x] **Tests**: retornos overnight, terciles, simulación sin posición nocturna.

- **Resultado medido (2026-11-11, `reports/research/overnight_reversal/report.md`)**
  - Universo de 17 ETFs, seleccion transversal (tercil mas bajo largo, tercil
    mas alto corto), 0 bps por lado: Sharpe **-0,15**, CAGR -1,03 %, MaxDD
    -18,18 %, retorno total **-8,28 %**, 2.110 operaciones, P(pasar) FTMO
    **16,95 %** y P(breach) **37,55 %** (2 bps: -8,57 %; 5 bps: -9,00 %).
  - **Falla**: edge negativo y probabilidad de breach alta. **Se documenta y se
    para**: no se crea bot, no se toca `config/bots.yaml` y no se relaja ningun
    umbral.
  - Correccion aplicada antes de medir: los pesos de los terciles se normalizan
    a **bruto <= 1** (`simulate_daily`). Sin esa normalizacion, doce activos a
    1/3 son ~4x de apalancamiento y el informe salia en -91,75 % con
    MaxDD -96,01 %: era apalancamiento, no estrategia.

### Etapa 3j — Embudo, disciplina, presupuesto de alertas y simulacro (2026-11-11)

- [x] **`GET /api/funnel`**: variantes probadas, pasan gates, candidato,
  incubando, evaluado, promovible y piloto activo, con tasa de caída. Panel
  **"Embudo"** en el Dashboard.
- [x] **`GET /api/discipline`**: órdenes bloqueadas por guard (30 días), días
  dentro del colchón y racha limpia. Panel **"Disciplina"** en Fondo.
- [x] **Presupuesto de alertas**
  - Tabla `alert_budget` y contador semanal por canal y tipo.
  - `lab alerts budget` muestra el uso frente al presupuesto
    (`alerts.weekly_budget` de `config/lab.yaml` cuando exista; por defecto
    40). Las **críticas nunca se suprimen**.
- [x] **`lab drill` (R8)**
  - Solo paper/demo: **rechaza `mode=live`**.
  - Exige operador **armado** y `--confirm`.
  - Cancela órdenes pendientes, cierra posiciones de los magics del laboratorio,
    avisa por ntfy **y** Telegram, activa el kill-switch y lo resetea con
    confirmación; mide tiempos y lo deja en `console_actions` con actor `drill`.
  - `scripts/drill_monthly.ps1` (no registra nada) y
    `scripts/register_drill_task.ps1` (**no se registra sin autorización**).
- [x] **`docs/paper_vs_live.md`**: huecos de paper/demo y cómo se cubren.
- [x] **Tests**: embudo y disciplina sin datos, ticker ratio, familias de
  sesión y overnight.

### Etapa 3k - Carril de acciones con ticker fijo y simulacro mensual (2026-11-11)

- [x] **Decisiones del operador (2026-11-11)**
  - Ticker del carril de acciones: **AAPL** (el del pipeline externo y el 13F
    de Berkshire que da los pesos de referencia).
  - `daytrader.enabled: true` en `config/lab.yaml`: el carril queda
    habilitado en **paper**. Sigue necesitando `--execute`, el veredicto
    `PASS` del pipeline externo y los guards del laboratorio.
  - Tarea programada del simulacro: **registrada** (`TradingLab-Drill`,
    domingo 03:00).
- [x] **`config/equities_lane.yaml` y `equities_lane.py`** (nuevo)
  - El ticker del carril vive en la configuracion: el scan no elige.
  - `lab daytrader lane` muestra ticker, cuenta, si puede ejecutar, la entrada
    pendiente, los hits del ticker en el watchlist y el peso de referencia.
- [x] **Guard de simbolo en `daytrader.plan_orders`**
  - Una orden que no sea del ticker del carril se rechaza con `BLOCK` antes
    de los guards: el carril es de un solo simbolo.
- [x] **Simulacion del simulacro (`lab drill --dry-run`)**
  - Informa de ordenes abiertas, posiciones, kill-switch y canales **sin**
    cancelar, cerrar, activar el kill-switch ni enviar avisos; deja rastro en
    `console_actions` con actor `drill`.
  - `scripts/drill_monthly.ps1` usa la simulacion por defecto; el simulacro
    real (`-Confirm`) sigue exigiendo operador armado, y el estado "armado"
    vive en memoria, asi que una tarea programada nunca lo ve.
  - `scripts/register_drill_task.ps1` registra la tarea de simulacion.
- [x] **Bug corregido**: el aviso de Telegram del simulacro nunca salia
  (`from .telegram import send`, funcion que no existe). Ahora usa
  `send_configured`.
- Evidencia: `ruff` limpio; `pytest tests/test_drill.py
  tests/test_equities_lane.py tests/test_daytrader.py -q` -> 20 passed; tarea
  `TradingLab-Drill` en estado Ready (proxima: domingo 03:00); hash F13
  `7fe0f5a6.` (sigue `changed` por el bloque `daytrader`).

### Etapa 3l - Re-congelado de F13 por cambios ajenos al bot (2026-11-11)

- [x] **Diagnostico del hash `changed`**
  - Congelado `54b420360f17c75d1768000b8a8587afbddc8e748713cb4bb05b8d853e469d12`;
    actual `7fe0f5a637bf29cb524b778d566d7aa58658bd5cc8fd0cfcccdf17556ac8c767`.
  - El hash congelado se reproduce exactamente en el commit `0a6f867`
    ("chore(f13): activa qqq-trend-f13 en paper"), con `bots.yaml` en CRLF y
    los otros tres en LF. Contra ese commit: `bots.yaml`, `prop.yaml` y
    `f13.yaml` son identicos; `lab.yaml` solo difiere por el bloque
    `daytrader` (carril AAPL). No hay ninguna otra diferencia.
- [x] **`lab f13 refreeze --reason <texto> --yes`**
  - Baseline por archivo: columna nueva `f13_config.file_hashes` (la guarda
    `freeze`) y, si falta, reconstruccion desde el historial git buscando el
    commit cuyo hash combinado coincide con el congelado (probando CRLF/LF).
  - Rechaza si cambio `bots.yaml`, `prop.yaml`, `f13.yaml` o el bloque del bot
    F13; acepta si solo cambio `lab.yaml`.
  - Guarda en `f13_config` el hash anterior, el nuevo, el motivo y la fecha;
    el historial completo en `f13_refreezes`; y audita `f13_refreeze` en
    `console_actions`.
  - `lab f13 report` muestra el historial de re-congelados (tabla y seccion
    en el markdown).
- [x] **Migracion aditiva**: `f13_config` gana `file_hashes`, `previous_hash`,
    `refreeze_reason` y `refrozen_at`; tabla nueva `f13_refreezes`. Nada se
    borra ni se reescribe.
- [x] **Ejecucion real**: `54b42036…` -> `7fe0f5a6…`, motivo "cambio ajeno al
    bot: bloque daytrader (carril AAPL)", archivos cambiados `lab.yaml`,
    baseline `git:0a6f867`. `lab f13 config-check` queda **OK**.
- [x] **Tests sinteticos** (`tests/test_f13.py`): rechazo si cambia
    `bots.yaml` o el bloque del bot; aceptacion si solo cambia `lab.yaml`
    (con historial y auditoria); motivo obligatorio; sin freeze previo falla;
    no repite si el hash no cambio; el reporte muestra el historial; el CLI
    pide confirmacion.
- Evidencia: `ruff` limpio; `pytest tests/test_f13.py -q` -> 24 passed; suite
  completa **827 passed, 1 skipped**; `lab doctor` OK con los WARN conocidos;
  `lab f13 status|check|report` OK. Sin push.

### Etapa 3m - Tendencia diaria en CFDs de tick grande (2026-11-11)

- [x] **Datos (solo lectura, mercado abierto y offset conocido)**
  - `lab mt5 status`: FTMO-Demo, `trade_allowed=True`, offset +2,00 detectado.
  - `lab mt5 fetch US100.cash --timeframe H4 --bars 50000` -> 9.761 barras
    (2017-12-28 -> 2026-11-11, 19 tramos de offset).
  - `lab mt5 fetch XAUUSD --timeframe H4 --bars 50000` -> 34.372 barras
    (2004-06-11 -> 2026-11-11, 46 tramos).
  - `lab mt5 fetch ... --timeframe D1` **falla** en ambos: la inferencia de
    offset por tramos no puede confirmar D1 sin ambigüedad (la apertura
    semanal no concuerda con el cierre del viernes). No se aplica un offset
    global: D1 queda **Sin datos** y la serie diaria se construye desde H4.
  - Datacheck obligatorio: H4 `aviso` (calendario no configurado para 4h,
    ajuste no declarado) y diario `aviso` (US100 con 7,3 % de huecos); ninguno
    es `falla`.
- [x] **Una sola familia nueva, `trend`, con mecanismo**
  - `strategies/swing.py`: reutiliza `trend_signal` sobre barras diarias (sin
    copiar el indicador) y añade la ejecución H4 con la señal del día
    anterior, el stop ATR 2×/3× sobre cierres (sin reentrar hasta que la
    señal vuelve a 0) y el tratamiento del domingo como lunes de mercado.
  - Estrategia registrada como `trend_daily_atr`; `family: trend`.
- [x] **Perfil y bots (nada enabled)**
  - `config/profiles.yaml`: `swing_cfd` con riesgo 0,5 % por operación,
    `target_vol` 0,10, `vol_target.enabled: false`, `min_trades` 20.
  - `config/intraday_bots.yaml`: `us100-trend-d1` y `xauusd-trend-d1`,
    `enabled: false`, rejilla de **5 variantes por activo** (rápida 20/50,
    lenta 100/200, stop ATR 2/3).
- [x] **Costes FTMO reales**
  - Índices comisión 0 y oro 0,0007 %/lado (catálogo `config/costs.yaml`).
  - Spread medido en las velas H4 en bps (punto 0,01): US100 0,50 bps de
    mediana (p95 1,18) y XAUUSD 0,39 (p95 3,34); se usa la mediana de los
    últimos 3 años (0,58 y 0,67 bps) más slippage conservador 2 bps.
  - `backtest.run` con sesión explícita y `flat_dates` (sin vencimientos en
    CFDs al contado).
- [x] **`lab research-swing`**
  - DSR (n_trials = variantes + intentos previos), PBO CSCV global y por
    activo, walk-forward (504/126 días), holdout del 30 % y Monte Carlo FTMO
    100k (2.000 paths, 120 días).
  - Registra cada variante en `strategy_trials` (familia `TREND`, fuente
    `sweep`, run_id por pasada) y respeta el presupuesto semanal.
  - Informe en `reports/research/swing_cfd/swing.json|md`.
- [x] **Resultado medido (run `d2316a4be339`)**
  - **0 de 10 variantes pasan.** PBO global 80,3 % (US100 79,5 %, XAUUSD
    30,1 %); walk-forward global `ok`; DSR 1,000 en las variantes US100 y
    0,000-1,000 en oro.
  - US100: Sharpe 0,77-0,81, CAGR 11,1-11,7 %, MaxDD -26/-29 %, P(pasar)
    54-55 %, **P(breach) 45-46 %**.
  - XAUUSD: Sharpe 0,24-0,66, CAGR 1,9-8,9 %, MaxDD -25/-30 %, P(pasar)
    42-55 %, **P(breach) 46-53 %**.
  - El motivo es el riesgo de la cuenta: el MaxDD de la estrategia
    (-25/-30 %) es mayor que el límite máximo de FTMO (10 %), así que la
    probabilidad de reventar es alta aunque el Sharpe sea positivo. Se
    documenta y se para; no se relajan umbrales ni se activa ningún bot.
  - Presupuesto semanal tras la pasada: US100.CASH 5/5 y XAUUSD 4/5.
  - Las dos pasadas anteriores (`d3207dca0458`, `8ecc653cfc71`) quedaron
    invalidadas por dos bugs propios: el veredicto del walk-forward no se
    anadia al informe y el Sharpe/CAGR se anualizaban con 252 barras H4 en
    vez de con dias. Se corrigieron antes de la pasada valida; las filas
    antiguas se conservan en el cementerio (no se borran).
- Evidencia: `ruff` limpio; `pytest tests/test_swing.py tests/test_profiles.py
  -q` -> 18 passed; suite completa **840 passed, 1 skipped**; `lab doctor` OK
  con los WARN conocidos; `lab f13 config-check` OK (`7fe0f5a6.`, sin tocar).
  Sin push.

### Etapa 3n - Barrido de exposición del challenge (2026-11-11)

- [x] **Artefacto de la variante (run `d2316a4be339`)**
  - El run no guardó los retornos diarios: `run_swing` no los persistía. Se
    añadió `save_variant_artifact` (parquet con `returns` y `equity`) y se
    reconstruyó la serie de US100 50/200/ATR 3 con el mismo código y datos.
  - Verificación contra las métricas guardadas del run: Sharpe 0,801 ·
    CAGR 11,61 % · MaxDD −26,37 % · 10 trades · P(pasar) 54,6 % · 2.145 días.
    Coinciden (diferencias < 1e-6): la serie es la del run.
  - Artefacto: `reports/research/swing_cfd/artifacts/us100-trend-d1.parquet`
    con sidecar de procedencia y verificación.
- [x] **`lab prop exposure-sweep --bot us100-trend-d1`**
  - Lee el artefacto (no recalcula el backtest), escala los retornos por
    `k ∈ {0,25; 0,35; 0,5; 0,75; 1,0}` y corre `prop/simulator.monte_carlo`
    con FTMO 100k (10 % objetivo, 5 % diario, 10 % total static, 2.000 paths).
  - Dos horizontes: 120 días (24 bloques de 5) y sin límite (150 bloques =
    750 días). El motor cuenta bloques; la conversión se hace en el barrido y
    se documenta, sin cambiar el simulador.
  - Reporta P(pasar), P(breach), sin resolver, mediana de días, MaxDD mediano
    y peor 5 % (`p5_max_drawdown`, columna nueva del simulador).
- [x] **EV neto por k**
  - Cuota 540 EUR y split 80 % (parámetros; `prop.yaml` no tiene `economics`
    y se deja como está).
  - Pago del mes 1: bootstrap de 21 días desde una cuenta fondeada; si el
    path revienta el diario o el total, paga 0; si no, `split × beneficio`.
  - EURUSD 1,11472 del cierre H1 de la caché MT5 (2026-11-08) para pasar el
    pago a EUR.
- [x] **Oráculo prop-ev 0.1.0** (`.venv-vbt`, 20.000 paths normales)
  - P(pasar): k=0,25 58,7 % vs 58,0 % propio; k=0,5 82,8 % vs 71,2 %;
    k=1 73,9 % vs 54,6 %. Divergen al subir k porque el bootstrap conserva
    los retornos reales (lumpiness de 10 trades) y prop-ev usa normales iid.
- [x] **Resultado medido (`reports/research/swing_cfd/exposure_sweep.md`)**
  - 120 días: P(pasar) 0,2-42,2 %; sin límite: 54,6-71,2 %.
  - P(breach) sin límite: 10,4 % (k=0,25) → 45,4 % (k=1); peor 5 % de MaxDD
    −9,5 % → −34,1 %.
  - EV neto: −307 (k=0,25), −150 (0,35), +33 (0,5), +233 (0,75), **+338 (k=1)**.
  - **Recomendación: k=1 por EV**, con óptimo plano (k=0,5-1,0) y el aviso de
    que subir k dispara el breach y el peor MaxDD. Es un estudio: no se cambia
    la exposición de ningún bot ni se activa nada.
  - **Decisi?n (2026-11-11): k=0,75** para un eventual intento. Acepta 105 EUR
    menos de EV que k=1 (+233 frente a +338) a cambio de 9,4 pp menos de breach
    (36,0 % frente a 45,4 %) y 7,5 pp menos de cola (-26,6 % frente a -34,1 %
    de MaxDD al 5 % peor). El EV de k=1 est? dentro del ruido del modelo del
    mes 1 y una reventada cuesta otra cuota entera. El bot `us100-trend-d1`
    queda con `exposure: 0.75` y **sigue `enabled: false`**: no se activa nada.
  - EV oráculo (un objetivo completo): +3.378 a +4.570; se muestra como
    contraste de convención, no como criterio.
- [x] **Tests sintéticos** (`tests/test_exposure_sweep.py`, 10 passed):
  k escala el MaxDD, el horizonte sin límite termina, conversión a bloques,
  artefacto ida/vuelta, sin artefacto falla, mes fondeado paga 0 si revienta,
  economía desde prop.yaml, recomendación negativa/positiva e informe/CLI.
- Evidencia: `ruff` limpio; `pytest tests/test_exposure_sweep.py -q` -> 10
  passed; suite completa **850 passed, 1 skipped**; `lab doctor` OK con los
  WARN conocidos; `lab f13 config-check` OK (`7fe0f5a6.`). Sin push.


- **Correcci?n (2026-11-11):** el guard de riesgo abierto multiplicaba los
  lotes de **todos** los s?mbolos por el `$/lote` del s?mbolo propuesto
  (bloqueaba el oro por los 2,04 lotes de EURUSD: 13.985 USD de riesgo
  inexistente). `PropGuard.evaluate` acepta `open_risk_usd` y `lab mt5 run`
  lo calcula por posici?n con el `$/lote` de cada instrumento; dos tests
  nuevos en `tests/test_prop.py`.
### Etapa 3o - Exposición con muestra larga y reembolso de cuota (2026-11-11)

- [x] **Reembolso de la cuota (FTMO 2-Step)**
  - `fee_refund_on_pass` (por defecto `True`) con fuente: FTMO FAQ "Is the entry
    fee refunded?" (2-Step: se devuelve con la primera retirada de Reward;
    1-Step/Instant no) · consultada 2026-11-11.
  - `EV = P(pasar)·(pago_mes_1 + cuota·refund) − cuota`; se mantiene la columna
    **sin reembolso** con la fórmula anterior.
  - US100: EV +6 / +224 / +418 / +579 / **+633** (antes −307 / −150 / +33 /
    +233 / +338).
- [x] **Artefacto `qqq-trend-cfd`** (misma regla, otro vehículo)
  - QQQ diario 1999-03-10 → 2026-11-10 desde caché (6.962 barras), trend
    50/200 + stop ATR 3, costes de US100.cash en FTMO (comisión 0, spread
    0,58 bps, slippage 2 bps).
  - 72 operaciones · Sharpe 0,589 · CAGR 8,00 % · MaxDD −26,40 %.
  - `save_variant_artifact` (returns + equity) y `save_artifact` con
    procedencia; **no** entra en `strategy_trials` ni suma al DSR: no es
    research nuevo, es la misma hipótesis con otro vehículo.
  - Datacheck: `aviso` (3,6 % huecos de calendario, ajuste no declarado). Se
    corrigió un falso `falla` por ruido de coma flotante (close − high =
    3,6e−15) con una tolerancia relativa 1e−9 y su test.
- [x] **Barrido QQQ** (`--name exposure_sweep_qqq --compare us100-trend-d1
  --adopted-k 0.75`)
  - P(pasar) sin límite: 40,6 / 58,0 / 62,9 / 55,9 / 47,9 % (más baja que la
    muestra de 10 operaciones).
  - EV neto: −177 / +61 / +246 / +355 / **+397**; k óptima **1**.
  - IC 90 % (200 remuestreos por k): 42,0 / 40,6 / 33,2 / 24,9 / 20,0 pp;
    mediano **46,5 pp (US100, 10 trades) → 33,2 pp (QQQ, 72 trades)**,
    factor 0,71.
  - **Conclusión: la k óptima no cambia (1,0)**, pero la muestra larga baja la
    P(pasar) y el EV (397 frente a 633): el edge es más débil de lo que
    sugerían 10 operaciones. La decisión adoptada (k=0,75) es de riesgo, no de
    EV: +355 EUR, breach 43,7 %, peor 5 % de MaxDD −26,0 %. **No se cambia la
    exposición de ningún bot**: decide el operador.
- [x] **Ops**: LM Studio arrancado y modelo recargado con 32.768 de contexto
  (el deep de los agentes fallaba por 8.192); `lab doctor` LM Studio OK.
- [x] **Demo manual (pedido por el operador)**: add-on de oro 0,03 lotes y
  trailing manual con `scripts/trail_demo_positions.py` (breakeven a 0,5R,
  trailing 1×ATR a 1R, nunca aleja el stop); solo demo, no abre órdenes.
- [x] **Tests**: reembolso cambia el EV, IC se estrecha con más operaciones,
  trailing (5 casos) y tolerancia OHLC. `pytest tests/test_exposure_sweep.py
  tests/test_trail_demo.py tests/test_datacheck.py -q` -> 28 passed.
- Evidencia: `ruff` limpio; suite completa pendiente; `lab doctor` OK; `lab
  f13 config-check` OK (`7fe0f5a6.`). Sin push.

### Etapa 3p - Cierre: operaciones manuales, estado y backup (2026-11-11)

- [x] **Diario: operaciones manuales**
  - `orders.magic` (columna aditiva) se guarda al enviar en MT5; el Diario
    marca `manual` toda operación de la cuenta MT5 cuyo magic no está en
    `config/intraday_forward.yaml` (o, en filas anteriores a la columna, cuyo
    bot no es del laboratorio y el símbolo es del universo MT5).
  - La vista Diario muestra la columna **Modo** (`bot`/`manual`) y el resumen
    cuenta las manuales; `lab journal` añade la fila.
  - `drift.py` excluye las manuales del cálculo de deriva (y publica
    `manual_excluded`); `lifecycle` no las cuenta para la incubación.
  - **Health y guardián no las excluyen**: la equity real es la que es.
- [x] **Riesgo abierto con tres símbolos**
  - Test en `tests/test_prop.py`: EURUSD 1,0 lote ($250 al stop) + XAUUSD 0,05
    ($331) + US100.cash 0,5 ($305) abiertos; una propuesta de 0,02 lotes de oro
    pasa (886 + 132 < 2.000) y una de 0,20 se bloquea (886 + 1.326 > 2.000).
    La fórmula vieja (lotes totales × un solo `$/lote`) habría bloqueado la
    pequeña.
- [x] **`docs/estado.md`**
  - Tabla de procesos en marcha (F13, Agents, LLMCompare, DeepCompare,
    IntradayForward, Drill, Guardian): qué mide, desde cuándo, cuándo tiene
    muestra y qué comando lo revisa.
  - Lista **"no construir hasta"**: guardián 5/5 → CLOSE; forward US100 60 días
    → decisión de challenge; decisiones n≥30 → lecciones; 30 operaciones
    cerradas → MFE/MAE y replay.
- [x] **Backup con restore test**
  - `scripts/backup.ps1` ya restaura el zip en una carpeta temporal
    (`restore_test.ps1`) y verifica archivos mínimos, ausencia de `.env`,
    secretos en claro y `PRAGMA integrity_check`.
  - Ejecutado real: zip nuevo en `F:\TradingLabBackups` y restore test en PASS.
- [x] **Cierre**
  - Suite completa **861 passed, 1 skipped**; `ruff` limpio; `lab doctor` OK;
    `lab f13 config-check` OK (`7fe0f5a6.`).
  - Push **no** ejecutado: queda para `/push` con confirmación por Telegram.

- **Correcci?n (2026-11-11):** el deep de agentes reintentaba analista por
  analista con 1.800 s **cada uno** (hasta 2,5 h colgado). Ahora hay un
  presupuesto **total** (`--deep-timeout`, 1.800 s) que comparten todos los
  reintentos; con el presupuesto agotado no se lanza ninguno. Tests: no
  reintenta sin presupuesto y reintenta uno a uno si el fallo es r?pido.
### Etapa 3q - Fills MT5 y forward swing US100 (2026-11-11)

- `fills` guarda los deals de MT5 con `deal_id` único (idempotente), bot,
  cuenta, símbolo, lado, volumen, precio, comisión, swap, magic, `ts_utc` y
  `contract_size`. Los deals con magic ajeno se guardan como `manual`.
- El Diario empareja FIFO en largo y en corto; `contract_size` corrige el PnL
  de CFDs y el swap entra en el neto. `entry_order_id=0` significa "deal sin
  orden del laboratorio".
- `us100-trend-d1`: H4, `trend_daily_atr` 50/200, stop 3 ATR, magic 20261153,
  `exposure: 0.75` (sobre el volumen mínimo; el mínimo manda), sin
  `force_exit` (`swing: true`), **encendido el 2026-11-11**.
- La tarea `TradingLab-IntradayForward` evalúa US100 solo en la primera barra
  H4 del día UTC (04:00-04:04 UTC); los dos forwards existentes siguen en sus
  ventanas.
- `lab lifecycle incubate us100-trend-d1 --force`: incubando 60 días (mín. 8
  trades, Sharpe forward > 0, slippage <= 3 bps, 0 breach), hash
  `67f7695cf087e673`; no toca `enabled`.
- Procedimiento de encendido y reversión en `docs/encendido.md`.

### Etapa 3r - Carril IA discrecional (2026-11-12)

- `config/ai_trader.yaml`: `ftmo_demo`, magic `20261190`, 9 estrategias, riesgo
  0,5 %/operación, stop diario 2 %, 6 operaciones/día, 1 por símbolo, 3 abiertas.
- `src/tradinglab/ai_setups.py`: biblioteca cerrada (orb_ny, vwap_reversion,
  bollinger_squeeze, liquidity_sweep, london_breakout, ema_pullback,
  rsi2_connors, donchian_turtle, inside_bar) con asignación por activo. El LLM
  elige estrategia/símbolo/timeframe/lado; los niveles los calcula el código.
- `src/tradinglab/ai_trader.py`: snapshot (≤3.000 tokens), propose/execute con
  lote por riesgo (rechaza < volume_min), SL ≥ 3×spread y stops_level,
  coste/R ≤ 0,10, PropGuard y límites del carril; manage con trailing por
  timeframe y Donchian de 10 días; scoreboard real vs sombra por celda con
  pausa automática; review con lecciones `proposed`; `ai_trades` y
  `ai_cell_state`.
- CLI `lab ai-trader` (snapshot, propose, execute, manage, scoreboard, resume,
  review, approve-lesson, no-trade). Skill `trading-lab-operador` versionada
  en `docs/ai_trader_skill.md`. Panel de solo lectura en la consola.

### Etapa 4 - Presupuesto de riesgo neto por activo

- [x] **`config/risk_budget.yaml`**
  - Riesgo abierto por activo **1,00 %**, rebanada inicial por bot **0,25 %**
    y máxima **0,50 %**. Clúster USD con tope **1,50 %**.
- [x] **Guard neto**
  - Riesgo firmado por activo: largos positivos, cortos negativos; se
    compensan antes de comparar con el presupuesto.
  - Tope total de riesgo abierto = mínimo del límite efectivo de cuenta
    (firma/propio); el guard rechaza aperturas que lo superen. Cierres y
    reducciones nunca se bloquean.
  - Clúster USD: EURUSD largo y USDJPY corto comparten dirección; se muestra
    el peor caso con todos los stops.
  - Integrado en `run_bot` y en la previsualización de órdenes del operador.
- [x] **Apagón de noticias**
  - `macro_events` filtrado por palabras USD (CPI, NFP, FOMC, PCE, Fed…) y
    BoJ/JPY para USDJPY, con ventana ±30 min. Sin datos → “sin datos”, no
    bloquea por invención.
- [x] **Rebanadas**
  - `risk_slice_overrides` + `risk_slice_history`. Bajar es inmediato; subir
    exige operador armado + confirmación, se rechaza para el bot F13
    congelado y se puede revertir por id de historial.
  - CLI: `lab risk-budget status|set|revert|news`.
- Evidencia: `pytest tests/test_risk_budget.py tests/test_intraday_bots.py -q`
  → 14 passed; suite completa **458 passed**; `ruff` limpio; `lab doctor` OK;
  `lab f13 config-check` OK (hash `54b420360f17c75d…` sin cambios). Sin
  activar bots, sin órdenes y sin tocar los YAML prohibidos.
### Etapa 5 — Ciclo de vida e incubadora

- [x] **Estados y historial**
  - `candidato → incubando → evaluado → promovible`, más `rechazado` y
    `archivado`; no existe ningún estado de dinero real.
  - `lifecycle_bots` + `lifecycle_events` con actor, fecha y motivo.
- [x] **Puerta de incubación** (`config/lifecycle.yaml`)
  - Datacheck ok, N mínimo, coste de equilibrio ≥ 1,5× el calibrado y sin
    régimen catastrófico. Solo marca elegible; nunca activa.
  - Límite de bots incubando a la vez (3) y criterios congelados con hash al
    entrar: ventana, min trades, Sharpe forward, slippage, deriva y brechas.
- [x] **Reporte y decisión**
  - `lab lifecycle status|report`: progreso, trades, Sharpe/expectancy
    forward, slippage real vs supuesto, deriva y brechas.
  - Al cerrar la ventana propone `promovible` o `rechazado`; la decisión final
    exige `set_final_state` humano. Cada bot incubado suma una prueba al DSR.
- Evidencia: `pytest tests/test_lifecycle.py -q` → 7 passed; suite completa
  **465 passed**; `ruff` limpio; `lab doctor` OK; `lab f13 config-check` OK
  (hash sin cambios). Sin activar bots, sin órdenes.

### Etapa 6 — Procedencia de decisiones y comparación lite/deep

- [x] **Procedencia**
  - `decision_outcomes` guarda `analysts` y `duration_s`; migración aditiva que
    conserva el historial existente.
  - `deep_prompt_hash` unifica el hash de modelo, analistas y fecha entre
    `decision_outcomes` y `agent_comparisons`.
  - `lab decisions report` añade la tabla **por fuente** (lite/deep), con N,
    retornos 1/5/20d, hit rate, t/p y aviso de retornos pendientes.
- [x] **Comparación**
  - `agent_comparisons` guarda rating, confianza, objetivo, modelo, hash,
    analistas, duración, acuerdo, errores saneados y marca `retrospective`.
  - `lab agent-compare TICKER` compara el mismo activo y fecha; fuera de hoy
    exige `--retrospective` y esas pasadas se excluyen del reporte forward.
  - Si el run con todos los analistas falla, se prueba uno a uno y se usa el
    primero que funcione. Los errores se recortan y redactan secretos.
  - Reporte: acuerdo, matriz de ratings lite→deep y diferencia media de
    objetivo. Con menos de 30 comparaciones: **muestra insuficiente**.
- [x] **Automatización preparada, no registrada**
  - `scripts/deep_compare_nightly.ps1`: un activo rotatorio por noche, solo
    mide y actualiza retornos; no ejecuta órdenes ni activa bots.
  - `scripts/register_deep_compare_task.ps1`: tarea `TradingLab-DeepCompare`
    registrada el 2026-11-09 a las 02:30 (estado `Ready`); solo mide.
- Evidencia: `pytest tests/test_agent_compare.py tests/test_decisions.py
  tests/test_scripts.py -q` → 19 passed; suite completa **474 passed**;
  `ruff` limpio; `lab doctor` OK con WARN conocidos; `lab f13 config-check`
  OK (hash sin cambios); `lab agent-compare --report` → sin datos. No se
  lanzó ningún deep real: los tests usan runners simulados. Sin órdenes.

### Etapa 7 — Vista por activo, incubadora y etiquetas lite/deep

- [x] **Vista Activo**
  - Selector que agrupa alias (`US100.cash`/`NASDAQ`, `GOLD`/`XAUUSD`) y reúne
    precio/tendencia de la caché local, bots asignados, decisiones lite/deep y
    ciclo de vida del activo. Sin parquet → **Sin datos**.
- [x] **Pestaña Incubadora**
  - Estados, progreso, trades, Sharpe forward, deriva, brechas, propuesta,
    motivos e historial `lifecycle_events`. Solo lectura: no activa ni opera.
- [x] **Lite/deep y procedencia**
  - Agentes etiqueta el modo, muestra analistas y añade acuerdo, matriz
    lite→deep y tabla por fuente. Decisiones añade N total, N con retorno 20d,
    retornos, hit rate y muestra insuficiente por fuente.
- [x] **Compatibilidad**
  - Se conservan las 15 vistas, ids y rutas `/api/*` anteriores; no se añadió
    ningún endpoint. `overview` incorpora `lifecycle` y `agent_comparisons`.
  - Inventario actualizado a **17 vistas, 267 ids, 34 llamadas API, 6 secciones
    y 17 pestañas**; el test lo verifica sin retirar entradas previas.
- Evidencia: `pytest tests/test_web.py tests/test_console_shell.py
  tests/test_console_js.py tests/test_agent_compare.py
  tests/test_lifecycle.py -q` → 46 passed; suite completa **477 passed**;
  `ruff` limpio; `lab doctor` OK con WARN conocidos; `lab f13 config-check`
  OK (hash sin cambios). Sin activar bots, sin órdenes y sin abrir deep real.

### Fases 4 y 5 — Noticias y validación de modelos (2026-11-09)

- [x] **Noticias**
  - Reintentos RSS con backoff solo para 429/5xx/red; 401/404 no se reintentan.
  - Finnhub como proveedor alternativo verificado (`lab intel providers --check`);
    se descargaron 10 noticias reales saneadas y con `trusted=false`.
  - Scoring con Qwen: prompt con texto delimitado como no confiable, schema
    estricto, sentimiento/relevancia y escritura idempotente en `news_scores`.
  - `lab intel score` procesó 3 noticias reales con `qwen/qwen3.8-27b`; 88
    quedaron pendientes para las siguientes pasadas. OpenBB no está instalado
    y no se añadió como dependencia.
- [x] **Validación de esquema**
  - `validate_schema` cubre objetos, arrays, enums, requeridos, tipos, rangos y
    `additionalProperties:false`.
  - `llm_calls.schema_ok/schema_error` se rellena tras cada `chat_json` con
    schema; `lab llm status` muestra el conteo explícito.
- [x] **Comparación de modelos (marco)**
  - `lite_model_comparisons`, `lab llm compare` y `lab llm report`; no cambia
    el default ni envía órdenes.
  - La ejecución real contra un MoE ~30B queda pendiente porque no hay ese
    modelo cargado en LM Studio.
- Evidencia: suite completa **531 passed**; `ruff` limpio; `lab doctor` OK con
  WARN conocidos; `lab f13 config-check` OK. Verificación real: Finnhub `ok`,
  10 noticias nuevas y scoring 3/3 con `qwen/qwen3.8-27b` sin inválidas y
  latencia real 62-96 s por lote.

### F9c y F15 — Backtest y ticks (2026-11-09)

- [x] **Sesiones y rollover**
  - `backtest.run` acepta `session`, `session_tz` y `flat_dates`; fuera de
    sesión o en día plano el objetivo se fuerza a 0 en la apertura siguiente,
    sin lookahead. Los defaults conservan el comportamiento anterior.
  - CLI: `lab backtest --session/--session-tz/--flat-dates`.
  - `continuous.stitch_continuous` une contratos antiguo→nuevo con ajuste
    `ratio` o `difference`, volumen intacto y validación de rolls/solapes.
  - CLI: `lab futures stitch --old/--new/--roll/--out`.
- [x] **Ticks Dukascopy**
  - `lab ticks fetch|summary|spread`; descarga `.bi5`, LZMA, registros de 20
    bytes, point por símbolo, parquet y métricas de spread. 404 = Sin datos.
  - `research-intraday --tick-spread <parquet>` sustituye el spread horario de
    las velas MT5 por la mediana horaria de ticks; el informe indica la fuente.
  - Verificación real: EURUSD 2025-01-10 14 UTC, 15.997 ticks, spread mediano
    0,29 bps.
  - Descarga de día completo pendiente: Dukascopy devolvió HTTP 429; se añadió
    `--interval` y backoff de 5 s; no se fuerza el rate limit.
- [x] **DeepCompare**
  - Tarea `TradingLab-DeepCompare` registrada y en estado `Ready` (02:30).
- [ ] **F7 Trading-R1**
  - WSL2 instalado: WSL 3.0.3, Ubuntu 24.04.5 LTS, usuario `pc` (UID 1000,
    sudo) y versión predeterminada 2. `networkingMode=mirrored` en
    `C:\Users\PC\.wslconfig` para alcanzar LM Studio en `127.0.0.1:1234`.
  - Trading-R1 0.1.1 en `~/.venv-r1`, perfil `vllm` con `qwen3.8-27b` y bun
    1.4.4 nativo en `~/.bun/bin`; inferencia real HTTP 200 y TUI verificada.
    Validado 2026-11-09: informe pre-market en 1 ronda y envío real por
    Telegram con `lab telegram send`; el canal nativo de Trading-R1 sigue sin
    configurar para no duplicar el token.
  - Runner `scripts/trading_r1_premarket.ps1` (`-PreflightOnly`, `-Send`):
    genera datos locales con `lab premarket --no-llm`, pide a Trading-R1 solo
    la redacción (sin web/herramientas), guarda MD/JSON en
    `reports/premarket/` y usa `lab telegram send`. No envía órdenes.
  - Fallback nativo `lab premarket` con Qwen, datos, calendario y Telegram;
    no usa Trading-R1 ni envía órdenes.
  - `TradingLab-Resume` reabrirá Windows Terminal y la sesión exacta de OpenCode
    tras el reinicio; guía en `docs/reinicio_wsl.md`.
    Fix 2026-11-09: usa `scripts/resume_terminal.ps1` con `-File` y un marcador
    por arranque, porque `wt.exe` partía el comando inline en cada `;`.
  - Se mantiene sin claves Tauric ni cambios de Telegram.
- Evidencia: `pytest tests/test_ticks.py tests/test_continuous.py
  tests/test_engine.py -q` → 18 passed; suite completa **531 passed**; `ruff` limpio;
  `lab f13 config-check` OK. Sin órdenes.

---

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
| 2026-11-07 | clústeres | `lab research-clusters` → 9/10 top en un clúster; presupuesto 1% y guard agregado |
| 2026-11-07 | clúster estático | `trend-spy` y `qqq-trend-f13` comparten `trend_equity`; reserva antes de arrancar |
| 2026-11-07 | cartera/costes | 3 bots, Sharpe 1,03, FTMO 120d 70,6%/3,5%; 0/10 frágiles a 2/20 bps |
| 2026-11-07 | 4.4/4.6/11b | `pytest tests/test_calendar.py tests/test_session.py -q` |
| 2026-11-07 | SEC/CSV/decisions | `pytest tests/test_sec.py tests/test_decisions.py -q` |
| 2026-11-07 | E1 fondo cuentas | `pytest tests/test_accounts.py -q` → 8 passed; 3 bots misma cuenta, 2 cuentas |
| 2026-11-07 | E2 fondo SQLite | `lab fund set/history`; `pytest -q` → 235 passed; hash F13 sin cambios |
| 2026-11-07 | E3 consola CSRF | `pytest tests/test_web_security.py -q` → 10 passed; `pytest -q` → 244 passed |
| 2026-11-07 | E4 pestaña Fondo | `pytest tests/test_fund_web.py -q` → 6 passed; `pytest -q` → 249 passed |
| 2026-11-07 | E5 intradía | `lab mt5 status` → offset unknown + mercado cerrado; sin descarga |
| 2026-11-07 | E6 documentación | README 6d y Fase 9; tabla por perfil en Research; `ruff` + doctor |
| 2026-11-07 | 10.1 Diario | `pytest tests/test_journal.py -q` → 7 passed; `lab journal` → sin datos; README 6e |
| 2026-11-07 | 11 Modo operador | `pytest tests/test_operator.py -q` → 11 passed; 2 pasos/PIN/keyring/auditoría; README 6f |
| 2026-11-07 | 12 Shell consola | `pytest tests/test_console_shell.py -q` → 3 passed; `pytest -q` → 327 passed; 6 secciones, 15 vistas, dashboard; README 6g |
| 2026-11-07 | 10.2 Multiverse | `pytest tests/test_multiverse.py -q` → 7 passed; `pytest -q` → 279 passed; 1.000 permutaciones, seed 42, Diario + Run Detail |
| 2026-11-07 | 10.3 Deriva | `pytest tests/test_drift.py -q` → 5 passed; `pytest -q` → 284 passed; IC bootstrap, mínimo 20, slippage, Bots + `lab drift` |
| 2026-11-07 | 10.4 Salud/TWR | `pytest tests/test_health.py -q` → 5 passed; `pytest -q` → 289 passed; score 0-100, flujos y TWR en Fondo |
| 2026-11-07 | 10.5 Pausa | `pytest tests/test_riskpause.py -q` → 4 passed; `pytest -q` → 295 passed; racha/día, F13 solo aprieta, Fondo + CLI |
| 2026-11-07 | 10.6 Aprendizaje | `pytest tests/test_learning.py -q` → 6 passed; `pytest -q` → 301 passed; lecciones, holdout, DSR trials, challenger, panel |
| 2026-11-07 | 10.7 Reportes | `pytest tests/test_exports.py -q` → 4 passed; `pytest -q` → 305 passed; CSV/HTML, validación, preview CLI/Registros |
| 2026-11-07 | 6.4 Catálogo | `pytest tests/test_instruments.py -q` → 9 passed; `pytest -q` → 307 passed; fuente/sesión/TZ, CLI/API/Mercado |
| 2026-11-07 | 6.5 Agentes mercado | `pytest tests/test_market_agents.py -q` → 5 passed; `pytest -q` → 312 passed; routing, coordinador, CLI/API/Agentes |
| 2026-11-07 | 6.6 Pilotos mercado | `pytest tests/test_market_pilots.py -q` → 4 passed; `pytest -q` → 317 passed; un mercado, gate aperturas, CLI/API/Agentes |
| 2026-11-07 | 7.2 Modelos/registry | `pytest tests/test_models.py -q` → 3 passed; `pytest -q` → 320 passed; walk-forward, challenger, promote/rollback, Qlib status |
| 2026-11-07 | 8 Cierre motor | `pytest tests/test_engine_decision.py -q` → 2 passed; `pytest -q` → 322 passed; sin Nautilus/databento/IBKR |
| 2026-11-07 | 7.3 Versiones/capital | `pytest tests/test_limit_versions.py -q` → 3 passed; `pytest -q` → 325 passed; snapshot/rollback y capital por bot |
| 2026-11-07 | 7.1 Lecciones semanales | `pytest tests/test_learning.py -q` → 8 passed; `pytest -q` → 327 passed; Qwen solo redacta, proposed, Sin datos |
| 2026-11-07 | F13 congelado | `lab f13 freeze --yes --start 2026-11-09`; hash `df8acdaa…`; `config-check` OK; bot `enabled: false`; sin tarea F13 |
| 2026-11-07 | Datos aprendizaje | Job `TradingLab-Agents` + `decisions update`; 3 decisiones SPY/QQQ/NVDA del 2026-11-07; 0 retornos 1/5/20d; ventana 20-30 días |
| 2026-11-07 | Job diario + outcomes | `pytest tests/test_scripts.py -q` → 5 passed; `pytest -q` → 328 passed; `agents_daily.ps1` ejecuta `decisions update`; `ruff` limpio |
| 2026-11-07 | 13 Telegram remoto | `pytest tests/test_telegram.py -q` → 23 passed; `pytest -q` → 352 passed; long polling, keyring, comandos, push/backup con `/confirm` y agente restringido; docs/telegram.md |
| 2026-11-07 | Etapa 0 | `pytest tests/test_operator.py tests/test_telegram.py -q` → 41 passed; `pytest -q` → 357 passed; F13 falla→bloquea+audita, PIN 6-12 persistente, denies acotados, `/push` con diffstat |
| 2026-11-07 | F13 activado | `lab f13 activate --yes` → hash `54b42036…`; `config-check` OK; bot `enabled:true`; `TradingLab-F13` Ready, próxima 2026-11-09 22:20; backup `trading-lab_20261107_223737.zip` PASS |
| 2026-11-07 | Etapa 1 | `pytest tests/test_datacheck.py tests/test_lookahead.py tests/test_research.py -q` → 30 passed; `pytest -q` → 375 passed; datacheck ok/aviso/falla, gate research, UI Research/Run Detail |
| 2026-11-07 | Etapa 2 | `pytest tests/test_metrics.py tests/test_journal.py tests/test_engine.py tests/test_research.py -q` → 33 passed; `pytest -q` → 379 passed; SQN/Recovery/ruina informativos, N<30 aviso |
| 2026-11-07 | Etapa 3 | `pytest tests/test_regimes.py tests/test_web.py -q` → 23 passed; `pytest -q` → 386 passed; régimen causal, Dashboard y selector proposed; GMM/HMM no adoptado |
| 2026-11-07 | Etapa 4 | `pytest tests/test_models.py -q` -> 6 passed; `pytest -q` -> 389 passed; PurgedKFold/CPCV sin solapamiento; meta-labeling solo doc |
| 2026-11-07 | Etapa 5 | `pytest tests/test_instruments.py tests/test_data_normalize.py -q` -> 14 passed; `pytest -q` -> 393 passed; XAUUSD/GC separados, bid/ask conservados |
| 2026-11-07 | Etapa 6 | `pytest tests/test_library.py -q` -> 3 passed; `pytest -q` -> 396 passed; 15 fichas originales, `lab library list|show` |
| 2026-11-08 | Etapa 7 | `pytest tests/test_optimize.py tests/test_quantstats_report.py tests/test_learning.py -q` -> 12 passed; `pytest -q` -> 400 passed; Optuna 5.0.0/QuantStats 0.0.86; smoke PBO 80.3%, 0 propuestas |
| 2026-11-08 | Bloque Etapa 1 | `pytest tests/test_learning.py tests/test_optimize.py tests/test_web.py -q` -> 29 passed; `pytest -q` -> 408 passed; holdout cache por hash, lecturas al DSR, UI/CLI |
| 2026-11-08 | Bloque Etapa 2 | `pytest tests/test_docs.py -q` -> 4 passed; `pytest -q` -> 408 passed; README F13 activo en paper + test de coherencia con bots.yaml |
| 2026-11-08 | Bloque Etapa 3 | `pytest tests/test_f13.py -q` -> 16 passed; `pytest -q` -> 408 passed; `lab f13 report` en reports/f13/ (ciclos, reconciliaciones, slippage, tamano, hash, alerta lunes), solo lectura |
| 2026-11-08 | UI v3 Etapa 1 | `pytest tests/test_console_shell.py -q` -> 5 passed; `pytest -q` -> 410 passed; tokens grafito/cian, HUD fijo, borde de operador armado, inventario UI congelado |
| 2026-11-08 | UI v3 Etapa 2 | `pytest tests/test_console_shell.py -q` -> 6 passed; `pytest -q` -> 411 passed; KPIs delta/sparkline, gauges de colchon/DD/salud, chips con icono, densidad persistida, skeletons y reduced-motion |
| 2026-11-08 | UI v3 Etapa 3 | `pytest tests/test_console_shell.py -q` -> 7 passed; `pytest -q` -> 412 passed; equity SVG con cruz/marcas/bandas, heatmaps PnL y correlacion, sin curvas inventadas |
| 2026-11-08 | UI v3 Etapa 4 | `pytest tests/test_console_shell.py -q` -> 8 passed; `pytest -q` -> 413 passed; foco visible, skip-link, aria-current, flechas, Ctrl+K, responsive 390px y refresco 8s sin re-render |
| 2026-11-08 | 9.5 inicial (NO FIABLE: offset constante) | `lab mt5 status` -> offset +2.00 detectado; M15 50k + H1 20k; `lab research-intraday` -> 0/28, WF fallido, spread real; sin activar bots |
| 2026-11-08 | 9.5 offset corregido | `pytest tests/test_mt5_offsets.py tests/test_intraday.py -q` -> 11 passed; offset por periodo +2/+3 (5 tramos M15, 8 H1); neto mejor -6.78, bruto +1.34, equilibrio 0.32 vs calibrado 3.72 bps; 0/28; WF fallido |
| 2026-11-08 | 9.5 costes calibrados | `pytest tests/test_intraday.py tests/test_console_shell.py -q` -> 20 passed; comision oficial FTMO 2.50 USD/lote/lado; spread horario + slippage opt/cons; tabla Sharpe 0/0.5/1/2/3 y equilibrio |
| 2026-11-08 | Cementerio Etapa 1 | `pytest tests/test_trials.py tests/test_intraday.py -q` -> 18 passed; `pytest -q` -> 436 passed; strategy_trials (fallidas tambien), contador DSR 5->33, aviso de familia descartada, presupuesto config/research_budget.yaml, f13 config-check OK |
| 2026-11-09 | Universo Etapa 2 | `pytest tests/test_asset_aliases.py tests/test_intraday_bots.py -q` -> 7 passed; `pytest -q` -> 443 passed; alias MT5 US100.CASH/XAUUSD/EURUSD/USDJPY; guard rechaza aperturas fuera del universo; 8 bots intrad?a enabled:false |
| 2026-11-09 | Validacion Etapa 3 | `pytest tests/test_intraday.py tests/test_mt5_offsets.py tests/test_asset_aliases.py tests/test_intraday_bots.py -q` -> 28 passed; `pytest -q` -> 448 passed; 4 activos M15, costes por activo, 0/84 pasan, DSR 117, informes por activo |
| 2026-11-09 | Riesgo Etapa 4 | `pytest tests/test_risk_budget.py tests/test_intraday_bots.py -q` -> 14 passed; `pytest -q` -> 458 passed; budget 1%/0.25%/0.5%, neto por activo, cluster USD, news blackout, slices con historial y F13 lock |
| 2026-11-09 | Incubadora Etapa 5 | `pytest tests/test_lifecycle.py -q` -> 7 passed; `pytest -q` -> 465 passed; estados, gate, criterios congelados, reporte forward y limite concurrente; sin activar bots |
| 2026-11-09 | Procedencia Etapa 6 | `pytest tests/test_agent_compare.py tests/test_decisions.py tests/test_scripts.py -q` -> 19 passed; `pytest -q` -> 474 passed; comparacion lite/deep, procedencia, reporte por fuente y scripts nocturnos sin registrar |
| 2026-11-09 | UI Etapa 7 | `pytest tests/test_web.py tests/test_console_shell.py tests/test_console_js.py tests/test_agent_compare.py tests/test_lifecycle.py -q` -> 46 passed; `pytest -q` -> 477 passed; vista Activo, Incubadora, lite/deep y desglose por fuente; 17 vistas/267 ids/34 API sin retirar las anteriores |
| 2026-11-09 | Fases 4-5 | `pytest -q` -> 531 passed; Finnhub real ok + 10 noticias; scoring Qwen 3/3 (62-96 s/lote); `llm status` con schema_ok; `ruff`/doctor/f13 OK; MoE real bloqueado por modelo no cargado |
| 2026-11-09 | CFD specs F6 | `lab mt5 spec XAUUSD` y `US100.cash` -> tick 0.01, contratos 100/1, volumen min 0.01, trade_mode 4; API MT5 sin sesiones |
| 2026-11-09 | Biblioteca fuentes | `pytest tests/test_library.py -q` -> 4 passed; 18 fichas; ResearchGate, Google Scholar y SSRN como consulta manual, sin scraping ni paywalls |
| 2026-11-09 | F9c/F15 | `pytest tests/test_ticks.py tests/test_continuous.py tests/test_engine.py -q` -> 19 passed; suite 513; ticks EURUSD 15.997 y 0.29 bps; DeepCompare Ready |
| 2026-11-09 | TradeStation/F15 | `pytest tests/test_tradestation.py tests/test_ticks.py tests/test_intraday.py -q` -> 30 passed; suite 521; SIM read-only/OAuth con mocks; spread de ticks integrado en research |
| 2026-11-09 | F7 fallback/resume | `pytest tests/test_premarket.py tests/test_scripts.py -q` -> 14 passed; suite 527; premarket Qwen 3/3 + Telegram; TradingLab-Premarket y TradingLab-Resume Ready |
| 2026-11-09 | CLI/OAuth/readiness | `pytest -q` -> 531 passed; `lab backtest --session`, `lab futures stitch`, `lab tradestation auth-url|exchange`, `lab readiness` |
| 2026-11-08 | UI formato/metricas | `pytest tests/test_console_js.py tests/test_console_shell.py -q` -> 11 passed; `pytest -q` -> 416 passed; gauges restantes, cero negativo, moneda agrupada, salud parcial, performers y regimen compacto |
| 2026-11-09 | Fix reapertura tras reinicio | `pytest -q --basetemp=...` -> 531 passed; `ruff` limpio; `lab doctor` OK; `resume_after_reboot.ps1` omite si ya corrió en el arranque; `wt.exe` ya no parte el comando por `;` |
| 2026-11-09 | WSL2 + Trading-R1 | WSL 3.0.3, Ubuntu 24.04.5, usuario pc; Trading-R1 0.1.1 en ~/.venv-r1; bun 1.4.4 nativo; mirrored + LM Studio HTTP 200; TUI viva |
| 2026-11-09 | Runner Trading-R1 | `.\scripts\trading_r1_premarket.ps1 -PreflightOnly` -> backend 8765 + qwen3.8-27b OK; `pytest tests/test_scripts.py tests/test_docs.py -q` -> 16 passed |
| 2026-11-09 | Trading-R1 premarket | 1 ronda, 2354 chars, datos locales, `Sin datos` donde falta; Telegram enviado; reporte en `reports/premarket/` |
| 2026-11-09 | Suite final Trading-R1 | `pytest -q --basetemp=...` -> 532 passed; `ruff` limpio; informe premarket 1 ronda + Telegram OK; runner local validado |
| 2026-11-09 | MoE 30B vs actual | `lab llm compare` SPY/QQQ/NVDA -> Hold/Hold, media 62%/60%, 190-235s vs 71-79s, acuerdo 100%, n=3/30 |
| 2026-11-09 | Tarea LLMCompare | `TradingLab-LLMCompare` Ready, L-V 18:30, `IgnoreNew`; preflight OK; suite 533 passed; sin ordenes |
| 2026-11-09 | Comparacion 84 variantes eventos | `execution_model` antes `a8743f9` vs actual: tablas identicas, 0/84 cambios; es modelo de costes, no motor de eventos. Serie por activo (mediana): EURUSD Sharpe -6.79, coste 4.62 bps/op, equilibrio 0.00, 0 pasan; USDJPY -7.03, 5.38, 0.00, 0; XAUUSD -2.55, 6.27, 0.74, 0; US100 -2.01, 5.44, 0.00, 0. Evento real solo `caja_ny` US100 (4 variantes): Sharpe neto medio -3.10 -> -3.57 (-15.0%), session_skipped 0 -> 31.510/variante, DSR 121/116 sin cambios. No se invento session_skipped para las 84. |
| 2026-11-11 | Guardian MQL5 (ALERT) | `lab guardian status` -> 2 de 5 sesiones (2026.11.10, 2026.11.11), 0 disparos; puerta CLOSE pendiente (faltan 3) |
| 2026-11-11 | Sesion de Tokio | forward 04:02/04:17/07:02/07:17/13:32 UTC -> 0 ordenes, 0 deals, 0 posiciones (los dos candidatos, flat sin posicion) |
| 2026-11-11 | Objetivo de volatilidad | `vol_report.compare` -> qqq-trend-f13 MaxDD -8,57%->-3,82% pero P(pasar) 65,65%->10,65%; trend-spy 59,60%->63,10%; meanrev-large 38,45%->12,70%; mixto, no se activa |
| 2026-11-11 | Condicionadores | propuesta con 1.498 dias afectados: Sharpe 0,83->0,76, retorno 69,97%->49,67%, MaxDD -8,57%->-8,09%; no compensa, queda como propuesta (`default: {}`) |
| 2026-11-11 | Reversion overnight | Sharpe -0,15, MaxDD -18,18%, retorno -8,28%, P(pasar) 16,95%, P(breach) 37,55%; falla, se documenta y se para (pesos normalizados a bruto <= 1) |
| 2026-11-11 | Familias de sesion | `research-intraday` EURUSD 0/52 y USDJPY 0/52 con `session_hold` y `fix_flow` (stop ATR real); informe en `reports/research/intraday_session/`; suite 805 passed, 1 skipped; ruff limpio |
| 2026-11-11 | F13 re-congelado | `lab f13 refreeze --reason "cambio ajeno al bot: bloque daytrader (carril AAPL)" --yes` -> 54b42036 -> 7fe0f5a6; solo `lab.yaml`; baseline `git:0a6f867`; `config-check` OK; historial en `f13_refreezes` y auditoria `f13_refreeze`; sin push |
| 2026-11-11 | Tendencia diaria en CFDs | `mt5 fetch` H4 US100.cash 9.761 y XAUUSD 34.372 barras; D1 Sin datos (offset no confirmable); perfil `swing_cfd` y bots `enabled: false`; `lab research-swing` -> 0/10, PBO 80,3%, P(breach) 45-53%; se documenta y se para; DSR 395 pruebas |
| 2026-11-11 | Barrido de exposicion | Artefacto US100 50/200/ATR3 reconstruido y verificado contra el run d2316a4be339; `prop exposure-sweep` -> EV -307/-150/+33/+233/+338 EUR (k 0,25-1,0), P(breach) 10-45%, peor 5% MaxDD -9,5/-34,1%; oraculo prop-ev 0.1.0 comparado; k=1 por EV, sin activar nada; 10 tests nuevos |
| 2026-11-11 | Barrido con muestra larga | Reembolso de cuota (FTMO 2-Step, FAQ 2026-10-06): EV US100 +633 en k=1 (antes +338); artefacto `qqq-trend-cfd` (QQQ 1999-2026, 72 trades) -> 0/10 no aplica: EV -177..+397, k optima 1; IC 90% 46,5 -> 33,2 pp (factor 0,71); conclusion en `exposure_sweep_qqq.md`; decision k=0,75 sin tocar bots |
| 2026-11-11 | Fills MT5 + swing US100 | `pytest tests/test_mt5_fills.py tests/test_journal.py -q` -> 21 passed; `fills` con `deal_id` idempotente, FIFO largo/corto y `contract_size`; `us100-trend-d1` H4 enabled:false; incubando 60 d, hash `67f7695cf087e673`; `docs/encendido.md`; sin push |
| 2026-11-11 | Encendido US100 | `us100-trend-d1` pasa a `enabled: true` tras el procedimiento de `docs/encendido.md`; signal 0 en el dry-run (flat), ventana 04:00-04:04 UTC; sin push |
| 2026-11-11 | Tendencia diaria GBPUSD | `research-swing --symbols GBPUSD --paths 500` -> 0/5, mejor Sharpe +0,08 (50/200, stop 2), PBO 43,0 %, P(pasar) 16,6 %, P(breach) 11,0 %, 23-25 trades; informe `reports/research/swing_cfd_gbpusd/`; no se gasta el ultimo intento de EURUSD |
| 2026-11-12 | Campana 2026-11-A (registrada y ejecutada) | `lab campaign universe` -> 55 medidos, 49 con comision verificada, 28 convertibles, elegibles H1 0 / H4 0 / D1 16; `lab campaign fetch` -> corte comun `2026-04-14`, `N_total=228`, 0 celdas fuera por historia, 47 series selladas, `holdout_hash=2ecf219c...`; `lab campaign register --confirm` -> `count_tests` 568 -> 796 (+228); `lab campaign run --confirm` -> 228 celdas, 0 candidatas, 0 confirmadas (la condicion c exige positivo en H4 y H4 no tiene elegibles), informe en `reports/research/campaign/2026-11-A.md`, `finished_at` 01:57Z, 228 filas con `counted=0`; `count_tests` 801 al cerrar (5 de un sweep ajeno). Bugs corregidos antes de ver holdout: import `daily_returns` y descubrimiento que corria H1/H4 ignorando la elegibilidad (752 -> 228, alineado con `N_total`); reanudacion por `run_id` y `finished_at` unico. `pytest tests/test_campaign.py -q` -> 13 passed; ruff limpio; `f13 config-check` OK; sin push. Hallazgo de las 47 celdas que solo fallan (c) en `docs/campanas.md` |
| 2026-11-12 | DeepCompare deshabilitado | `Disable-ScheduledTask -TaskName 'TradingLab-DeepCompare'` desde proceso elevado (UAC aceptado) -> `State` `Ready` -> `Disabled`, `Settings.Enabled` `False`; tarea conservada (no borrada), trigger diario 02:30 inerte; `docs/estado.md` actualizado con el estado real y la reactivacion (saldo primero, clave despues, `Enable-ScheduledTask` con elevacion); sin push |
| 2026-11-12 | IA discrecional · tres estilos | `config/ai_trader.yaml` con `scalping` (20261191, M1/M5, 0,25 %, stop 1 %, 15 trades, coste/R 0,15, ventana 09:30-12:00 NY), `intraday` (20261192, M15/H1, 0,5 %, stop 1 %, 3 trades, coste/R 0,10) y `swing` (20261193, H4/D1, 1 %, stop 1 %, riesgo abierto 2 %); global stop 3 %, 5 abiertas, 1 por símbolo y estilo, reset FTMO. `propose`/`skip`/`execute`/`status` con lote hacia abajo (rechaza < volume_min), SL >= stops_level y 3×spread, coste/R con comisión FTMO + slippage en puntos, límites por estilo/global y `ai_decisions`; guardian.json incluye los tres magics y `daily_stop_global`; doctor avisa si la suma de stops supera el global; Diario/drift reconocen los magics IA. `pytest -q` -> 919 passed, 1 skipped; `ruff check .` limpio; `lab doctor` OK (3,00 % = 3,00 %); `lab f13 config-check` OK; `lab ai-trader snapshot --symbols XAUUSD` real con M1/M5/H4/D1 (M1 usa 20k barras para inferir offset); sin push |
| 2026-11-12 | Campaña 2026-11-A reconstruida (sin registrar) | `lab campaign fetch` descarga H1/H4 con 50.000 barras de los 51 candidatos (ya no solo de los elegibles), exige mercado abierto y offset +2 h detectado, re-mide elegibilidad con las velas completas y aplica un holdout común mínimo de 2 años quitando la serie que lo limita. Resultado: H1 0 / H4 0 / D1 16 activos y **232 celdas**; corte común `2024-08-08 00:00:00+00:00`, holdout 2,26 años; XCUUSD fuera por historia (507 barras D1, holdout 0,58 años); 0 celdas fuera por historia; 48 series selladas. `lab campaign n-total` -> 232; `lab campaign plan --force` reescribe `config/campaigns/2026-11-A.yaml` con `config_hash=0edeff2f…` y `holdout_hash=768204bd…`, **sin ejecutar `register`**. La condición de meseta y los clústeres solo usan barras anteriores al corte (test). `ruff` limpio; `pytest -q` -> **928 passed, 1 skipped**; `lab doctor` OK con los WARN conocidos; `lab f13 config-check` OK. Sin push. |
| 2026-11-12 | IA discrecional · biblioteca de 10 estrategias | `ai_setups.py` con `orb_ny`, `vwap_reversion`, `bollinger_squeeze`, `liquidity_sweep`, `london_breakout`, `ema_pullback`, `rsi2_connors`, `donchian_turtle`, `inside_bar` y `trend_pullback` H4; ventanas NY/Londres y validación de setups por código. `config/ai_trader.yaml` con la asignación exacta por símbolo/estilo/timeframe (`intraday` M15/H1, `swing` H4/D1; `scalping` sin M1/M5 en el playbook v1, rechaza). `snapshot --style --symbols` compacto con indicadores, setups válidos, coste/R, eventos 24 h, posiciones y presupuesto: ≈640 tokens estimados para `swing` y ≈560 para `intraday` con los 5 símbolos. `manage` sin LLM: breakeven 0,5R, trailing 1 ATR desde 1R, Donchian 10 días, salida D1 sobre SMA5 y cierres 16:00 NY/Londres, sin alejar el stop y solo magics 20261191/92/93. `pytest -q` -> 936 passed, 1 skipped; `ruff check .` limpio; `lab doctor` OK; `lab f13 config-check` OK; sin push. |
| 2026-11-12 | Scalping IA · plan y ejecución sin LLM | `ai_setups.py` con `ema_ribbon_pullback` M1, `vwap_bounce` M5, `orb_5m` M5 y `momentum_burst` M1; asignación solo US100/XAUUSD en el estilo `scalping`. `lab ai-trader plan` valida y guarda `ai_plans` (un plan activo por símbolo y sesión, setups/bias/horas prohibidas/motivo); `lab ai-trader scalp` hace una pasada sin LLM sobre la última vela cerrada, aplica bias, horas prohibidas, coste/R y límites, ejecuta en demo y registra `take`/`skip`/`no_setup` con `plan_id`. Sin plan no opera; fuera de 09:30-12:00 NY no hace nada; MT5 caído, datos de más de 2 velas o kill-switch activo registran el skip. `pytest -q` -> **949 passed, 1 skipped**; `ruff check .` limpio; `lab doctor` OK; `lab f13 config-check` OK; `snapshot --style scalping` real = 413 tokens; `propose` real rechazado por setup, sin ejecutar; sin push. |
| 2026-11-12 | Sombras, scoreboard y panel IA | `ai_trades` con `source` (forward/replay) y segunda sombra `shadow2_*` para scalping (lado contrario al real, mismos niveles/trailing; la aleatoria mantiene semilla fija por id). `lab ai-trader scoreboard` por estilo × estrategia × símbolo × timeframe: n, hit, R medio, IC bootstrap 90%, coste/R, slippage TCA, diferencia vs sombra y vs sin plan, estados `explorando/ganadora/perdedora/neutral`; solo `source=forward`; las perdedoras se pausan. Panel `IA discrecional` de solo lectura con posiciones por estilo, presupuesto diario por estilo/global, marcador y plan de scalping activo; inventario UI actualizado sin retirar ids. Skill `trading-lab-operador` en `~/.config/opencode/skills/` y copia `docs/ai_trader_skill.md` con las sesiones London/NY/daily. `lab doctor` avisa `IA sesiones` si una sesión cerrada no dejó filas en `ai_decisions` (hoy WARN: Londres sin filas). `pytest -q` -> **957 passed, 1 skipped**; `ruff check .` limpio; `lab doctor` OK con el WARN esperado; `lab f13 config-check` OK; sin push. |
| 2026-11-12 | Tareas IA · preflight, permisos y panel | `scripts/ai_trader_session.ps1` (london/ny/daily), `ai_trader_manage.ps1`, `ai_trader_scalp.ps1` y `ai_trader_task_common.ps1`: candado con PID, preflight de ventana local/kill-switch/demo/MT5/stop global/mercado, log y estado en `logs/ai_trader/`, resumen Telegram/ntfy. `tradinglab/ai_session.py` con ventanas Nueva York/Londres/DST y República Dominicana. `register_ai_trader_tasks.ps1` ejecutado el 2026-11-12: 5 tareas registradas (4 `Ready`; **AI-Scalp `Disabled` hasta el primer plan**) (London 03:05, NY 09:35/10:35, Daily 18:15, Scalp 09:25-13:05, Manage cada 15 min dom-vie, UTC-4, usuario actual). Agente OpenCode `ai-operator` con solo `lab ai-trader` (snapshot/propose/skip/execute/plan/manage/scoreboard/status), sin editar/git/otros; `opencode run --standalone --agent ai-operator --model opencode-go/deepseek-v4.1-flash`. `lab doctor` añade `IA tareas`. `docs/ai_trader_opencode.md`, `docs/estado.md`, `docs/campanas.md` (regla (c) de 2026-11-B decidida, sin registrar). `pytest tests/test_ai_session.py` -> 10 passed; suite completa **967 passed, 1 skipped**; `ruff` limpio; `f13` OK; sin push. |
| 2026-11-12 | Replay ciego de setups | `lab ai-trader replay --style intraday|swing --n 200 [--strategy] [--symbol]`: muestrea momentos históricos con semilla fija, solo setups válidos y anteriores al corte de `2026-11-A` (2024-08-08); snapshot anonimizado (sin fecha/símbolo, clase de activo, precios a 100); pide take/skip a `ai-replay` en lotes de 10 (DeepSeek V4.1 Flash) tras mostrar decisiones/llamadas/tokens y exigir `--yes`; simula R neto con costes y sombra aleatoria; filas `ai_decisions source=replay`; n≥50 y IC90 de la diferencia vs sombra <0 pausa la celda, audita y notifica. Rechaza `--style scalping`; replay excluido del marcador forward, panel y resúmenes. `pytest tests/test_ai_replay.py` -> 7 passed; suite completa **975 passed, 1 skipped**; `ruff` limpio; `f13` OK; sin push. |
| 2026-11-12 | Campaña 2026-11-B ejecutada y contaminada (0 confirmadas) | `run_discovery` sobre 232 celdas, `run_id=0315bb0089ea`; 23 candidatas tras la meseta y **0 confirmadas** en el holdout. **Contaminada**: holdout solapado con el descubrimiento de `2026-11-A` y regla (c) decidida tras ver el anexo; el tramo `2024-08-08 → hoy` queda consumido para esos activos. Las 232 pruebas siguen en `count_tests` (1033). Informe `reports/research/campaign/2026-11-B.md`; el generador ahora usa el `campaign_id` en título y mapas de calor. `lab campaign run` exige `--approved-by-operator`; `register` rechaza holdouts solapados. Sin push. |
| 2026-11-12 | Aprendizaje diario IA | `lab ai-trader learn` sin LLM al final de la sesión daily: pausa celdas perdedoras, excluye hora/día/condición del snapshot con n≥15 e IC90 superior <0, y reduce a la mitad el riesgo de un símbolo en un estilo con n≥30 y expectativa negativa. Máximo 2 cambios por semana; cada uno sube `playbook_version`, actualiza `config/ai_trader.yaml`, `docs/ai_trader_skill.md` y el SKILL.md del operador, audita en `ai_learn_changes` y notifica con evidencia. Reactivar, subir riesgo o ampliar quedan como lección `proposed`. El marcador agrupa por `playbook_version`. Script daily llama a learn. `pytest tests/test_ai_learn.py` -> 8 passed; suite completa **984 passed, 1 skipped**; `ruff` limpio; `f13` OK; sin push. |
| 2026-11-12 | Destilación semanal IA | `lab ai-trader distill` (domingo 12:00 DOM, sin LLM): celdas ganadoras con n≥30 e IC90>0; en scalping exige plan > sombra sin plan. Árbol de profundidad ≤2 con numpy, filtro legible o vacío si no supera “tomar siempre”. Candidato `ai-<estrategia>-<símbolo>-<tf>` en `intraday_bots.yaml`/`bots.yaml` con `enabled:false`, riesgo del estilo, magic propio 20262100+, `origin: destilado de ia-discrecional`, `playbook_version` y filtro. Validación con/sin filtro: costes, DSR (+2 por destilación), PBO, walk-forward y Monte Carlo FTMO; gana la versión sin filtro si supera a la filtrada. Si pasa, lifecycle incuba 60 días (15 trades, Sharpe>0, slippage≤3 bps, 0 breach) y la celda IA pasa a `destilada`; el LLM deja de operarla. Scalping exige ticks Dukascopy de las mismas horas. Panel con embudo, filtro y evidencia. `TradingLab-AI-Distill` añadida al script de registro **sin registrar**. `pytest tests/test_ai_distill.py` -> 5 passed; suite completa **990 passed, 1 skipped**; `ruff` limpio; `f13` OK; sin push. |
| 2026-11-12 | Primer plan scalping y AI-Scalp | Planes activos para US100.cash y XAUUSD (4 setups M1/M5, bias both, horas prohibidas 09:30-09:45 y 11:30-12:00 NY). La sesión `ny` crea el plan del día con `lab ai-trader plan` si no existe; en invierno el orden es apertura NY 10:30, sesión 10:35 y primer scalp después. `TradingLab-AI-Scalp` pasa de `Disabled` a `Ready`; `TradingLab-AI-Distill` no registrada. |
| 2026-11-12 | Slippage, límites y stop de cuenta | `slippage_price` por símbolo (US100 1,0; XAUUSD 0,15; EURUSD/GBPUSD 0,00005; USDJPY 0,005) y coste/R con `2×`; sin dato, `propose`/`scalp` rechazan. `max_open` 2 por estilo y global 5; swing 2 trades/día y coste/R 0,05. `account_daily_stop: 0.04` suma realizada + flotante de todos los magics; `PropGuard`, forward, `ai_trader` y preflight lo consultan; panel y `guardian.json` exportan el consumo y los seis magics. `lab doctor` avisa si la suma de stops de estilo supera 0,04. |
| 2026-11-12 | Campañas: aprobación y contaminación | `lab campaign run` exige `--approved-by-operator` además de `--confirm`; AGENTS.md prohíbe a los agentes ejecutar campañas o barridos sin aprobación explícita. `register` rechaza holdouts solapados con descubrimiento u holdout de campañas ejecutadas sobre los mismos activos. `2026-11-B` quedó marcada como contaminada (`run_id=0315bb0089ea`): holdout solapado con 2026-11-A, regla (c) post-hoc y ejecución sin aprobación; 0 de 23 confirmadas. Su tramo `2024-08-08 → hoy` queda consumido y las 232 pruebas siguen contando. |
| 2026-11-12 | Latidos, backup y lease | `lab heartbeat` con 12 checks de Healthchecks.io en keyring y pings start/ok/fail en F13, Agents, LLMCompare, IntradayForward, AI-London/NY/Daily/Scalp/Manage, Drill y backup; sin URL se omite y `lab doctor` avisa. `TradingLab-Heartbeat` registrada cada 5 min (MT5 + SQLite). `backup.ps1 -Offsite` cifra AES-256-CBC con `BACKUP_PASSWORD` de keyring, copia a `backup.offsite_dir`, comprueba 50 % de espacio libre, descifra en `restore_test.ps1` y retiene 14 diarias + 8 semanales. `execution_lease` de 2 min con host; `ai_trader` y `forward_intraday` se niegan a operar con lease de otro host. |
| 2026-11-12 | Control cruzado, COT y VIX | `lab data crosscheck` compara H1 de MT5 con ticks Dukascopy, alinea por hora, calcula retornos 1h/1d, correlación y divergencias >3σ; informe en `reports/data/crosscheck/`; `datacheck` avisa si corr 1h < 0,95. `lab data cot` descarga la CFTC (Legacy/financieros), guarda referencia y publicación y `latest_as_of` evita lookahead. `lab data vix` obtiene VIXCLS/VXVCLS de FRED, ratio VIX/VIX3M y flag contango/backwardation; se expone en conditioners y snapshot IA sin tocar multiplicadores. Sin coste y solo lectura. |
| 2026-11-12 | Cierre: tests, F13 y bloque | `pytest -q` -> **1016 passed, 1 skipped**; `ruff check .` limpio; `lab f13 config-check` OK tras re-congelar `1ac90c80be916202…` por cambios ajenos al bot en `config/lab.yaml` (heartbeat, backup offsite); `lab doctor` OK en MT5/IA y WARN esperado en Latidos (0/12 URLs) y tareas London/NY/Scalp. `TradingLab-AI-Scalp` sigue `Ready`; `TradingLab-AI-Distill` no registrada; `TradingLab-Heartbeat` registrada. Sin push. |
| 2026-11-12 | Decisión de campañas y Heartbeat | No se abre campaña nueva: el holdout de `2026-11-B` queda consumido y `register` rechaza solapamientos; se espera a datos posteriores al 2026-11-12 o activos fuera del universo consumido. En este bloque no se ejecutó ninguna campaña ni barrido. `TradingLab-Heartbeat` se registró cada 5 min (MT5 + SQLite); `BACKUP_PASSWORD` se generó y guardó en keyring sin imprimirla. Las 12 URLs de Healthchecks.io siguen sin configurar. |
| 2026-11-12 | Reorganización tras cierre de apps | MT5 `FTMO-Demo` (1515220028) y consola `8420` levantados de nuevo; `TradingLab-Heartbeat` corre cada 5 min con resultado 0. Corregido `PaperBroker.equity_series` para aceptar timestamps ISO mixtos (`format="mixed"`), causa de los fallos de `TradingLab-DryRun` y `TradingLab-F13` de las 22:15/22:20; dry-run manual vuelve a exit 0. `lab doctor` OK en MT5/IA; WARN esperado en Latidos (0/12 URLs) y tareas London/NY/Scalp. |
| 2026-11-12 | Verificación F13/DryRun | `f13_daily.ps1` manual a las 23:05 -> exit 0 y `F13 daily OK`; `dryrun_daily.ps1` a las 22:54 -> exit 0. Ambos quedan listos para su próxima tarea programada. London 03:05 y AI-Scalp 09:25 aún no han corrido. Healthchecks.io sigue en 0/12 URLs: falta la cuenta/URLs del operador; no se inventan. |
| 2026-11-13 | London 03:05 y Healthchecks | London ejecutó a las 03:05 con `status=ok`: 4 decisiones (`USDJPY` no_setup, `EURUSD` skip por coste/R 0,128 > 0,10, `GBPUSD` y `XAUUSD` skip sin setup), 0 trades y 0 posiciones. Check `pc` de Healthchecks.io configurado con la URL recibida; 11 checks siguen pendientes. AI-Scalp aún no ha corrido. |
| 2026-11-13 | F13 y DryRun verificados en tarea | Tareas registradas `TradingLab-DryRun` y `TradingLab-F13` lanzadas a las 07:59; ambas terminaron con `LastTaskResult=0` (`F13 daily OK`, dry-run registrado). La próxima ejecución programada sigue a las 22:15/22:20. |
| 2026-11-13 | Separación de configuración F13 | `config/ops.yaml` recibe timezone/starting_cash/currency, llm, daytrader, mt5, projectx, prop, operator, fund_health, learning y backup; `config/lab.yaml` queda con `mode`, `risk`, `data` y `execution`. `Settings.load` mezcla lab+ops; freshness y guardian leen ops con fallback. El hash de F13 cubre solo el bloque `qqq-trend-f13` de bots.yaml, f13.yaml, prop.yaml, la cuenta real del bot (`paper_main`) y las claves mode/risk/data/execution. Re-congelado `9c183b780e6849e4…` → `02a06348f7afab59…` y después a `d701f7d2287fa877…` al cubrir la cuenta real `paper_main`: F13 se queda en `paper_main` (no se cambia a `alpaca_paper` para no alterar el piloto). Dry-run antes/después idéntico: QQQ target 1.0, held 13, desired 5, delta -8. Tests `tests/test_f13_config_scope.py` 2 passed; suite F13 28 passed; suite completa 1020 passed, 1 skipped. |
| 2026-11-13 | AI-Scalp primer día y revisión | `TradingLab-AI-Scalp` corrió 09:25-13:05 y cerró 5 trades (5 cerrados, 0 abiertos): **+1,49R / +372,92 USD**; `TradingLab-AI-NY` y `AI-Manage` terminaron 0. Corregidos dos fallos: las sombras usan 20.000 barras M1 y ventana que incluye la vela de entrada/salida (antes `shadow_r` quedaba None), y las estrategias de scalping fuerzan cierre a las 12:00 NY. `manage` cerró las dos posiciones que quedaban abiertas. Tests AI 32 passed; ruff limpio. |
| 2026-11-13 | F13 migrado a alpaca_paper | Informe de los 4 días archivado en `reports/f13/paper_main_2026-11-09_a_13.md`; cierre auditado de 5 QQQ de F13 en paper_main (`orders.id=18`; las 8 restantes eran de `trend-spy`). Verificado Alpaca paper (`BaseURL.TRADING_PAPER`, cash/equity 100.000, sin posiciones). `lab f13 migrate-account` cambió solo `account` y `start_date`: hash `d701f7d2…` → `26fd15fd…`, inicio **2026-11-13**, fin 2027-01-08. El orquestador enruta cada bot al bróker de su cuenta; `lab reconcile --account alpaca_paper` separa los fills de F13 (QQQ) y del daytrader (AAPL), y el límite de trades diarios ya no cuenta órdenes de otra cuenta. Dry-run de control: target 1.0 y objetivo 5 QQQ (antes held 13, delta -8; después held 0, delta +5). Tests nuevos de migración, reconciliación por bot, fills Alpaca y ruteo; suite completa **1036 passed, 1 skipped**; `ruff` limpio; `lab doctor` OK; `lab f13 config-check` OK. Sin push. |
| 2026-11-13 | Latido pc: causa y programación | `pc` llevaba ~7 h sin ping aunque `TradingLab-Heartbeat` corría cada 5 min: el script solo pingueaba después de comprobar SQLite y MT5 y la tarea tiene límite de 2 min; cuando `lab mt5 status` se bloqueó, el Programador mató el proceso antes del ping. Ahora hace `start` inmediato, comprueba MT5 con timeout de 60 s y siempre termina con `ok` o `fail` con motivo (`--message`). La tabla de 12 checks se calculó desde los disparadores reales y quedó en `docs/heartbeat.md`: pc período 10 min/gracia 10; ai-manage `*/15 0-17 * * 1-5`/30 min; drill `0 3 * * 0`/2 h; el resto cron L-V con 1 h. No hay `HEALTHCHECKS_API_KEY` en keyring: no se tocó la API. Tests de ping con motivo, cron y script; `pytest tests/test_heartbeat.py` 9 passed; `ruff` limpio; `lab doctor` OK; `lab f13 config-check` OK. Sin push. |
| 2026-11-13 | Vector: observabilidad local | `docs/vector.md` fija Vector **0.61.0** (MPL-2.0, herramienta externa; no entra en `pyproject.toml` ni en `uv.lock`) con hashes SHA-256 de los assets oficiales. `config/vector/vector.yaml` lee logs del lab, diario del terminal MT5 y Experts (**UTF-16 LE con BOM**, verificado con un log real), guardi?n UTF-8 y el canal `Microsoft-Windows-TaskScheduler/Operational`; VRL clasifica info/warn/critical (traceback, AutoTrading disabled, TRIGGER/BLOCK/CLOSE del guardi?n, retcodes 10006/10013/10014/10016/10019/10027/10031, tareas TradingLab-* con retorno !=0; requotes, reconexiones y desconexi?n aislada) y a?ade fuente, tarea/s?mbolo y hora UTC. Destinos locales `all-%Y-%m-%d.jsonl` (retenci?n 14 d?as por `vector_cleanup.ps1`) y `alerts.jsonl`; sin red. `lab alerts relay` lee el offset de SQLite, deduplica 30 min, escala la segunda desconexi?n y env?a solo critical con presupuesto; las warn quedan en `vector_daily`. `TradingLab-Heartbeat` llama al relevo y a la limpieza. `lab doctor` avisa si Vector est? instalado sin servicio o si `all-*.jsonl` lleva >15 min sin l?neas con mercado abierto. `scripts/vector_install.ps1` (no ejecutado), `scripts/vector_test.ps1` y tests nativos en el YAML (critical/warn/normal). Vector **0.61.0** instalado con el MSI oficial (SHA-256 verificado), servicio `Vector` en `Automatic` y corriendo; `vector validate` OK y los 8 tests nativos pasan (`scripts/vector_test.ps1`). El log operativo del Programador estaba deshabilitado: se activ? y Vector ya escribe `logs/vector/all-2026-11-13.jsonl`. Tests del relevo/doctor/config; suite completa **1056 passed, 1 skipped**; `ruff` limpio; `lab doctor` OK (Vector activo); `lab f13 config-check` OK. Sin push. |
| 2026-11-14 | EA US100 FTMO1 integrado y validado | `config/mt5_eas.yaml` registra el EA externo `us100-ftmo1` (US100.cash, magic 93010001, setfile `US100_FTMO_v3_challenge.set`). `lab ea list/status/validate/optimize`; el magic se mapea a `ea:us100-ftmo1` en el Diario/TCA y la consola web muestra una tarjeta externa de solo lectura. Motor Python portado a `ea_us100_engine.py`; validaci?n con 366.847 velas M5 (2017-12-28 ? 2026-11-13): 480 trades, PF 1,45, +0,298 R, +143,2 R, DD 24,8 R; DSR 1,0; PBO 24,1 %; WF ok (Sharpe OOS 1,31); reg?menes 2021-2026 positivos; coste con 2 pts +0,246 R. **PASA** los filtros. Barrido de 8 variantes alrededor de v3: la propia v3 es la mejor; no se cambia el setfile. Se a?adi? el riesgo din?mico v3 (1,0/0,6/0,35/0,25 %) a `US100_EA.mq5` y `US100_RiskManager.mqh` y se compil? con MetaEditor: 0 errores, 0 warnings. Simulaci?n din?mica: +140,8 %, DD de pico ?13,9 %, sin tocar el kill 8 %; MC 21d pass 1,74 %, breach 0 %. Docs `docs/ea_us100_ftmo1.md`; tests `test_ea_registry.py`; suite completa al cierre. Sin push. |
| 2026-11-15 | EA US100 · controles compartidos, trial y forward | `guardian.json` incluye los magics `93010001`/`93020001` del EA de `ftmo_demo` (y sigue cubriendo forward + IA); `account_daily_stop` suma realizado y flotante de esos magics, no cierra posiciones del EA, bloquea aperturas del lab, escribe `console_actions` y alerta `critical` una vez; `symbol_risk_caps["US100.cash"]=0.02` suma riesgo de lab + EA y lo aplican PropGuard, `ai_trader`, forward y `lab doctor`; `ftmo_trial_ea` queda `blocked` con reglas FTMO 100k y `mt5_eas.yaml` permite mover el EA con `account`; forward pre-registrado en lifecycle con hash `2bfad45ca4ba36fc`, inicio al primer fill, 60 d/40 ops, PF ≥ 1,15, +0,10R, DD ≤ 6 %, slippage ≤ 2 pts, 0 breach y coincidencia ≥ 90 %; barrido 21/60/120/750 d en `reports/research/ea_us100_ftmo1/horizon.md`. Tests `test_guardian.py`, `test_account_daily.py`, `test_symbol_risk.py`, `test_ea_forward.py`; suite completa **1077 passed, 1 skipped**; `ruff` limpio; `lab doctor` ejecutado (Frescura FAIL por mercado cerrado; WARN conocidos de LM Studio y reglas de fondeo); `lab f13 config-check` OK. Sin push. |
