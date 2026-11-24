# RESULTADO · COLA DESATENDIDA (R2j-b → T1 → T2 → T3)

Fecha: 2026-11-22. Operador ausente. No se ejecutó nada prohibido: sin
approve/run/confirm/supersede, sin registrar campañas, sin leer OOS-1/OOS-2, sin
push, sin tareas programadas, sin borrar/copiar el repo, sin tocar .venv, sin
cambiar umbrales.

## R2j-b · calendario completo, tramos y usable_from

- Commit `8a121d0`, tag `tl2-r2j-b`.
- Informe `.orquestador/RESULTADO-R2j-b.md`.
- Suite **1602 passed, 1 skipped**; ruff limpio; propfund verify 4 OK;
  `count_tests` 1676.
- Resultado: 14 tramos de sesión; 77 claves usable_from; US500 D1 FAIL→WARN y
  XAUUSD D1 WARN→OK; 2647 huecos real→programado (0 por “horario”); 6 FAIL de
  índices H1/H4 explicados por 2015-2018.

## T1 · Preparación SSD (solo lectura)

- Informe `.orquestador/RESULTADO-SSD-prep.md`.
- Sin cambios en el repo; sin commit.
- C: 194,22 GB libres; E: 684,47 GB libres. E:\trading-lab = 3,160 GB
  (data 1,239; familia .venv 1,654; .git 0,043; resto 0,224).
- 53 rutas absolutas a E: en 41 ficheros; tarea `TradingLab_sync_spreads_daily`
  apunta a `E:\trading-lab\scripts\sync_spreads_daily.ps1`; pytest-xdist no
  instalado. Comando robocopy propuesto, no ejecutado.

## T2 · R2i-b · onboarding multi-timeframe

- Commit `d94e625`, tag `tl2-r2i-b`.
- Informe `.orquestador/RESULTADO-R2i-b.md`.
- `propfund/onboarding_mtf.py`, comando `lab propfund onboarding-mtf`, tests
  sintéticos.
- 84 celdas (CFD-001 35 + CFD-006 49), 24 viables (CFD-001 11, CFD-006 13).
  M1-M30 ninguna; H1 US100/USDJPY; H4 US100/EURUSD/GBPUSD/USDJPY y XAUUSD solo
  CFD-006; D1 todos los permitidos. US30 CFD-006 Sin datos.
- Suite **1608 passed, 1 skipped**; ruff limpio; propfund verify 4 OK;
  `count_tests` 1676.

## T3 · Propuestas de campaña (solo papel)

- Informe `.orquestador/PROPUESTAS-campanas.md`.
- Sin cambios en el repo; sin commit; DSR cero.
- 4 propuestas `asia_range_reversion` (US100 H4, USDJPY H4, EURUSD D1, XAUUSD H4
  solo CFD-006), todas por probar, IS 2021-10-01 → 2024-06-30 dentro de
  usable_from, n_total estimado 440 (small GA).
- `suggest` y `edge-map` ejecutados en solo lectura; Edge Map sin candidatas
  nivel 3/4. Preflight/feasibility no ejecutados porque exigen campaña
  registrada y registrar está prohibido.

## Estado final

- `git status --short`: `?? tl2-edge-map.patch`.
- `HEAD`: `d94e625`; tags `tl2-r2j-b` y `tl2-r2i-b` en sus commits.
- `count_tests`: 1676.
- Sin push.

COLA TERMINADA
