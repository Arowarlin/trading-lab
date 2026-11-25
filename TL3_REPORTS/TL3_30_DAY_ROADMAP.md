# TL3 · Plan de 30 días

**Qué no promete este plan:** encontrar una estrategia rentable. Promete salir del día 30 con (a) un
veredicto fuera de muestra válido sobre el EA, (b) 2–3 hipótesis con potencia probadas de forma
limpia y (c) un proceso que impida repetir los fallos de estas tres semanas.

Restricciones permanentes: demo/paper; no tocar componentes protegidos; nada que sume pruebas sin
aprobación del operador en la sesión; sin borrar; sin push. Cada bloque termina con tests, `ruff`,
`pytest`, `lab doctor`, README/PLAN y un commit pequeño (`AGENTS.md`).

## Semana 1 · Diagnóstico (días 1–7) — **hecha en buena parte con este informe**

| Día | Tarea | Entregable | Suma pruebas |
|---|---|---|---|
| 1 | Auditoría forense en solo lectura | `TL3_REPORTS/*.md` | No |
| 1 | **Decidir NQ-B antes de que se ejecute B2** (`TL3_FORENSIC_AUDIT.md` G-1): enmendar la puerta de validez sin mirar 2010-2017, o pararla | Nota del operador en `RESULTADO-NQ-B.md` | No |
| 2 | Revisión por el operador de los 10 documentos; lista de desacuerdos | Comentarios | No |
| 3 | Reetiquetar en el Edge Map los veredictos v1 sin potencia ("no concluyente") **en un informe nuevo**, sin tocar `discovery.db` | `TL3_REPORTS/edge_map_tl3.md` | No |
| 4–5 | Inventario de datos con manifiesto (granularidad por año, instrumento real, ASK) en **solo lectura** | `TL3_REPORTS/data_manifest.md` | No |
| 6–7 | Aprobación explícita del plan de la semana 2 | — | No |

## Semana 2 · Correcciones prioritarias (días 8–14)

Todo en `src/tradinglab/tl3/` y `data/tl3/`; ningún cambio en módulos protegidos.

| # | Corrección | Aceptación | Prioridad |
|---|---|---|---|
| W2-1 | `data_manifest.py` + cargador que rechaza granularidad y clase de instrumento erróneas | Test: cargar 2018 de la caché del EA como M5 falla; cargar `databento/US100_M1` como CFD falla | P0 |
| W2-2 | Copias de futuros con nombre propio (`data/tl3/futures/NQ_c0_M1.parquet`) y `raw_symbol` si la API lo da; la caché original no se toca | Manifiesto con `instrument_class=future` | P0 |
| W2-3 | Registro de hipótesis, experimentos y libro de muestras (`tl3/registry.py`) | Tests: hash estructural bloquea reapariciones; un holdout solapado se rechaza | P0 |
| W2-4 | Candados de potencia, coste e identidad (`tl3/gates.py`) + `thresholds.yaml` con hash | Arnés T01: P(aprobar \| 0) ≤ 0,005 sin cambio; P(aprobar \| δ) documentada | P0 |
| W2-5 | Informe bruto → neto por componente, usando `spread_r/slip_r/comm_r/swap_r` de v2 | Test sintético con costes conocidos a mano | P1 |
| W2-6 | Spread: seguir midiendo `broker_spreads` 4 semanas (ya automático); declarar US500/US30 FTMO "Sin datos" hasta entonces | — | P1 |
| W2-7 | Contrafactual correcto de `ai_trader` **como análisis offline** (TL3), sin tocar el carril: gemela desde la vela siguiente, M1, orden temporal, costes; más la regla de tendencia | Recalcular las 44 operaciones con la gemela corregida | P1 |

**Pruebas del EA (requieren aprobación explícita y `informal_trials`):**
- W2-8 · Una ejecución del motor con el setfile congelado y `counted=0` para exportar la lista de
  operaciones (lado, hora, MAE/MFE). Es un análisis descriptivo, no una variante. **1 prueba informal.**
- W2-9 · Prerregistro de la prueba US100 fuera de periodo con Dukascopy 2011-09 → 2021-08
  (`TL3_US100_CASE_STUDY.md §6`): normalización de RVOL, perfil de spread y paridad 2022 ≥ 80 %
  **decididos antes**.

## Semana 3 · Investigación controlada (días 15–21)

| Orden | Experimento | Muestra | Criterio | Pruebas |
|---|---|---|---|---|
| 1 | **EA fuera de periodo** (W2-9), una ejecución | US100 Dukascopy 2011-2021 | n ≥ 300, exp ≥ 0,10 R, LCB95 > 0 | 1 |
| 2 | **H1 deriva nocturna** (sin parámetros, muestra completa) | US100/US500/US30 2011-2026 | LCB95 neto > 0 y nocturno > intradía | 1 |
| 3 | **H2 pre-FOMC** (sin parámetros, ~120 eventos) | Cesta de índices 2011-2026 | Diferencia neta frente a placebo > 0, p < 0,05 | 1 |
| 4 | H3 apertura + expansión, **solo si** el preflight da MDE ≤ 0,12 R | Desarrollo 2015-2020, holdout 2011-2014 | LCB95 > 0 y supera al benchmark sin filtro | ≤ 9 (meseta) |

Total previsto: **≤ 12 pruebas nuevas**, frente a las 1.894 acumuladas. Cada una con
`hypothesis_id`, spec firmada y aprobación del operador en la sesión.

## Semana 4 · Evaluación (días 22–30)

| Día | Tarea |
|---|---|
| 22–23 | Informes estándar de cada experimento (bruto → neto, benchmark, estabilidad, veredicto literal) |
| 24 | Descartar falsas ventajas: todo lo que no cumpla la regla prerregistrada se cierra con `rejection_reason`, **sin reformular sobre la misma muestra** |
| 25–26 | Para cualquier candidata: definir la validación independiente (otro instrumento o periodo, o SPRT forward con δ y plazo calculados) |
| 27 | Decisión sobre el EA: si pasa el fuera de periodo → mantener el forward con SPRT y medir slippage real; si no pasa → reetiquetarlo como "ajuste en muestra" y no basar en él decisiones de riesgo (p. ej., subir a 0,65 %) |
| 28 | Decisión sobre `ai_trader` con el contrafactual corregido (W2-7) |
| 29 | Siguiente lista de hipótesis, priorizada por (efecto esperado − coste) / MDE |
| 30 | Resumen Hecho / 1..N / Aviso / Siguiente a Telegram o ntfy |

## Indicadores de éxito del mes (no son rentabilidad)

| Indicador | Hoy | Objetivo día 30 |
|---|---|---|
| Campañas registradas sin δ | 18/18 | 0 |
| Campañas con MDE > δ | 11/16 | 0 |
| Pruebas fuera de muestra válidas del EA | 0 (US500/US30 son fuera de instrumento) | 1 fuera de periodo |
| Archivos de futuros con nombre de CFD | 8 | 0 en TL3 |
| Veredictos con costes v1 presentados como "cerrados" | 3 | 0 |
| Pruebas nuevas por hipótesis probada | ~100 (1.894 / ~18) | ≤ 9 |
