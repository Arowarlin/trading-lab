# TL3-C · T8 corregido: H2 deriva previa al FOMC

> La versión de 972d916 es inválida: swap 100× mayor; ver COLA-TL3-C H-a.

Eventos programados: 121; con datos válidos: 117.
Exclusiones evento×índice: US100 4, US500 4, US30 17.
Placebo: 3261 días; σ bruta = 94.06 bps; σ neta = 94.10 bps; MDE = 21.65 bps; δ = 30 bps.

| Métrica | Valor |
|---|---:|
| Eventos | 117 |
| Bruto eventos | 14.37 bps |
| Bruto placebo | 3.64 bps |
| t Welch unilateral (bruto) | 1.909 |
| Neto eventos | 8.04 bps |
| LCB95 neto (bootstrap) | -0.60 bps |
| **Veredicto** | **no confirma** |

### Escalera bruta → neta (eventos)

| Componente | bps |
|---|---:|
| Bruto | 14.37 |
| − spread | 2.28 |
| − slippage | 2.04 |
| − swap | 2.01 |
| Neto | 8.04 |

### Por época

| Época | n | Bruto bps | Neto bps |
|---|---:|---:|---:|
| ≤ 2015 | 31 | 7.71 | -2.32 |
| ≥ 2016 | 86 | 16.76 | 11.78 |

Lectura fijada: «no confirma» descarta un efecto de 30 bps, no uno de ~20 bps; «confirma» es una replicación independiente 2011-2026 en CFD. Referencia: `TL3_REPORTS/literatura_T8_H1.md`.
