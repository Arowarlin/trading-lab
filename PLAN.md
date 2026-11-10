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
- Pendiente: validación explícita del operador para poner `enabled:true` y
  ejecutar la primera orden demo a volumen mínimo.

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
- Estado operativo 2026-11-10 23:42 UTC: EA compilado con **0 errores, 0
  warnings**, JSON copiado a `MQL5/Files`, EA cargado en **EURUSD H1** del
  perfil y corriendo en **ALERT** (log `INIT` + `START` + `CONFIG`), cuenta
  FTMO-Demo con 0 posiciones y 0 órdenes. Ventana de 5 sesiones en curso;
  `defense_mode` sigue en `report`. El chart quedó con `expertmode=0`: antes
  de `CLOSE` hay que ponerlo a 1 y confirmar algo trading.

### Etapa 4 — Presupuesto de riesgo neto por activo

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
|  |  |  |
