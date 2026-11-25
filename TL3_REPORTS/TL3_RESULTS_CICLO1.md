# TL3 · Resultados del ciclo 1

## Por bloque

| Bloque | Estado | Cifra / veredicto |
|---|---|---|
| T0 | Hecho | Auditoría y colas en `c9c0d12`. |
| T1 | Hecho | Manifiesto de 14 archivos; cargador rechaza granularidad/clase. |
| T2 | Hecho | 8 copias de futuros en `data/tl3/futures/`; originales intactos. |
| T3 | Hecho | Registro `tl3_research.db` con 11 hipótesis; candados y umbrales. |
| T4 | Hecho | Escalera bruto → neto con test a mano. |
| T5 | Hecho | `ai_trader` vs gemela: Δ +0,1675 R, IC95 [−0,2090; +0,5411], n=48 → **Sin datos**. |
| T6 | Hecho | Réplica EA v3.2: 479 ops, +0,3104 R; réplica reproduce (±1 op nueva). |
| T7 | **Bloqueado** | Falta `record-informal` `TL3-T7`; no se ejecutó. |
| T8 | **Bloqueado** | Falta `record-informal` `TL3-T8`; no se ejecutó. |
| T9 | Hecho | H1: coste 0,724 bps, pasa en CFD-006; CFD-001 bloqueado por swap. H3: 207 días, MDE 0,1731 > 0,12 → `no_power`. |
| T10 | Hecho | Este informe. |
| T11 | Pendiente | Cierre, suite, tag y Telegram. |

## Hipótesis

| ID | Hipótesis | Estado | Motivo |
|---|---|---|---|
| H-2026-001 | Fix FX | `rejected` | `gross_lt_cost` |
| H-2026-002 | Asia USDJPY | `rejected` | `no_gross_edge` |
| H-2026-003 | Cambio de mes | `inconclusive` | `no_power_cost_v1` |
| H-2026-004 | Rebote D1 | `inconclusive` | `no_power_cost_v1` |
| H-2026-005 | Donchian | `inconclusive` | `no_power_cost_v1` |
| H-2026-006 | Momentum intradía | `inconclusive` | `no_power_cost_v1` |
| H-2026-007 | NY open GA | `inconclusive` | `no_power_cost_v1` |
| H-2026-008 | EA OOP (T7) | `draft` | bloqueado: falta registro `TL3-T7` |
| H-2026-009 | H2 FOMC (T8) | `draft` | bloqueado: falta registro `TL3-T8` |
| H-2026-010 | H1 nocturna | `draft` | puerta de coste; no se ejecuta |
| H-2026-011 | H3 OR | `rejected` | `no_power` |

## Recomendaciones para el operador

1. **EA:** mantenerlo como está y **INCIERTO**. T7 no se ejecutó por falta
   del registro del contador; si se registra `TL3-T7`, la prueba Dukascopy
   2012-2021 está lista y A-1 ya es válido (85,7 %, 0,9129). No cambiar el
   EA ni el riesgo por este ciclo.
2. **`ai_trader`:** no se distingue de la gemela (Δ +0,1675 R, IC95 incluye
   0; n=48). No aumenta el riesgo; el benchmark de tendencia sigue Sin datos.
3. **Siguiente lista**, ordenada por (bruto esperado − coste) / MDE:
   - H1 nocturna: pasa coste en CFD-006, pero el swap de CFD-001 no es fiable;
     medir swap ≥ 20 sesiones antes de registrarla.
   - H3 OR: sin potencia (MDE 0,1731 > 0,12); no registrar hasta ampliar
     muestra o bajar δ.
   - T7 EA Dukascopy: pendiente solo del registro `TL3-T7`.
   - T8 H2 FOMC: pendiente solo del registro `TL3-T8`.
4. Ninguna de estas recomendaciones se aplica en esta cola.

## Contador

- `count_tests` = **1895**.
- T7 y T8 no suman porque no se ejecutaron. A-1/A-2 de NQ-B son paridad, no
  suma.
