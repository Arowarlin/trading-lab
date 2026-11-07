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

- [ ] **0.3 Reproducibilidad**
  - Generar `uv.lock`, fijar versiones directas, añadir `pre-commit` y
    actualizar CI (lint + tests, sin secretos ni brokers).
  - Documentar versiones verificadas en `docs/dependencias.md`.
  - Criterio: `uv sync --frozen` funciona, `pre-commit run --all-files` pasa,
    CI en verde y `pytest` local en verde.
  - Comando: `uv lock && uv sync --frozen --extra dev && pytest -q`.

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
- [ ] **2.3 Implementar medición automática de F13**
  - Hecho: tablas `f13_config`/`f13_metrics`, `lab f13 status|freeze|report|
    signal-check|config-check`, comparación con SPY y backtest.
  - Pendiente: slippage real y tamaño real frente a lo calculado; paradas
    automáticas conectadas a alertas.
- [ ] **2.4 Presentar y esperar aprobación**
  - No arrancar el paper sin confirmación explícita del usuario.

## Fase 3 — Mejoras de lab research

- [x] **3.1 Anti-sobreajuste (DSR)** — 2026-11-07
  - Deflated Sharpe Ratio implementado y usado como criterio (>=90%).
  - Resultado: 0 propuestas de 192 variantes; los 18 candidatos previos no
    sobreviven al ajuste por múltiples pruebas.
- [ ] **3.1b PBO (CSCV)** — pendiente; requiere retornos por bloque y
  combinaciones train/test.
- [ ] **3.2 Walk-forward** en lugar de un único 70/30 + reporte por régimen.
- [x] **3.3 Monte Carlo block bootstrap** — ya existía y research usa
  `block_size=5`; documentado.
- [ ] **3.4 Optuna** para explorar parámetros con validación walk-forward.
- [ ] **3.5 QuantStats** para el HTML de cada propuesta frente a SPY.
- [ ] **3.6 Criterio**: research completo con datos sintéticos y semilla fija.

## Fase 4 — Capa de información continua

- [ ] **4.1 Fuentes**: RSS/APIs, SEC EDGAR, FRED, calendario, OpenBB y contraste
  de datos; verificar licencias/límites.
- [ ] **4.2 Triaje barato**: FinBERT o modelo local pequeño; medir latencia/RAM.
- [ ] **4.3 Esquema**: `news_items`, `news_scores`, `macro_events`, dedupe/hash.
- [ ] **4.4 Seguridad**: texto externo no confiable, saneado y delimitado;
  test de prompt injection.
- [ ] **4.5 Planificador**: tareas con logs, reintentos y alertas por fuente.
- [ ] **4.6 Calendario → guard**: `news_blackout_min`, viernes, fin de semana y
  rollover; bloquear aperturas, permitir cierres.

## Fase 5 — Medir si el LLM aporta algo + memoria

- [ ] **5.1 Salida estructurada** validada por esquema y registro de fallos.
- [ ] **5.2 `decision_outcomes`** con retorno a 1/5/20 días hábiles.
- [ ] **5.3 Línea base** contra comprar siempre / no hacer nada, con muestra mínima.
- [ ] **5.4 Comparar MoE ~30B** vs modelo actual en lite; no cambiar el default.
- [ ] **5.5 Versionado de prompts** (hash) y modelo por decisión.

## Fase 6 — Multi-mercado

- [ ] **6.1 IBKR paper** con `ib_async` verificado, guard de identidad, stop
  obligatorio y cierre permitido; CFD solo si se confirma disponibilidad.
- [ ] **6.2 CFD vía MT5** con especificaciones y horarios.
- [ ] **6.3 Futuros**: preset Topstep, MLL y barras continuas con rollover.
- [ ] **6.4 Catálogo único** de instrumentos por clase.
- [ ] **6.5 Agentes por mercado** y coordinador determinista.
- [ ] **6.6 Un mercado a la vez**, cada uno con su mini-F13.

## Fase 7 — Aprendizaje controlado

- [ ] **7.1 Lecciones** semanales en `lessons` con estado `proposed` y aprobación
  humana en el panel.
- [ ] **7.2 Reentrenamiento walk-forward** (LightGBM u otro), `model_registry`,
  campeón/retador y evaluación de Qlib en venv aparte.
- [ ] **7.3 Límites**: versionado, capital máximo por agente y rollback.

## Fase 8 — Motor de eventos (opcional)

- [ ] **8.1 Comparación escrita** NautilusTrader v2/IBKR/Databento, coste de
  migración; no tocar código hasta aprobación.

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
|  |  |  |
