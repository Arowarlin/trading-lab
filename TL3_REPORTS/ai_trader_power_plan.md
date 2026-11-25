# TL3-D · D4 Plan de potencia de `ai_trader`

Fuente: las **48 operaciones de T5** (`ai_trader_t5_rows.json` sin los `id` 52 y 54). No se miran operaciones nuevas y nada de este bloque suma al contador.

## Series

| Serie | Media | sd | n para MDE 0.10 R |
|---|---:|---:|---:|
| Δ_t = IA − tendencia | -0.0225 | 0.5341 | **177** |
| Δ_g = IA − gemela | +0.0360 | 0.4059 | **103** |
| real − simulado (IA) | -0.2475 | 1.0231 | descriptivo |
| R real (frente a 0) | +0.0479 | 0.9871 | **605** |

`n = ⌈(2.49 × sd / 0.10)²⌉`. La serie real − simulado se informa porque D3b la descompone; su n no se usa para la regla de evaluación.

## Ritmo y fechas

- 48 operaciones entre **2026-11-13** y **2026-11-25**; **9 días hábiles** entre ambas fechas y **5.33 operaciones cerradas por día hábil**.
- Solo 7 fechas tuvieron operaciones; el denominador de ritmo es el intervalo completo de días hábiles, como pide D4.

| n | Motivo | Fecha estimada |
|---:|---|---|
| 103 | Δ_g | 2026-12-11 |
| 177 | Δ_t | 2027-01-04 |
| 180 | Δ_t redondeado a múltiplo de 10 | 2027-01-04 |
| 605 | R real frente a 0 | 2027-04-29 |

Fechas con el calendario NYSE (sin festivos) y el ritmo observado; son estimaciones, no un compromiso.

## Versiones

- **Playbook:** 1 (48 ops). Una sola versión en las 48.
- **Modelo/prompt:** **Sin datos**. `ai_trades` no guarda modelo ni prompt; `ai_decisions.model` tiene NULL (9897), opencode-go/deepseek-v4.1-flash (59), pero no hay clave `proposal_id` que lo una a las 48 y el emparejamiento por hora/símbolo/entrada no encontró ninguna coincidencia.
- `model_registry` contiene ridge-spy v1 (ridge, SPY), ridge-qqq v1 (ridge, QQQ), ridge-nvda v1 (ridge, NVDA), ridge-msft v1 (ridge, MSFT), ridge-aapl v1 (ridge, AAPL): modelos ridge de acciones, no el modelo de `ai_trader`.
- **Mezcla:** no hay mezcla de playbook; la del modelo no se puede estratificar. La evaluación única debe declarar esta limitación.

## Regla fijada ahora

- La próxima evaluación de `ai_trader` se hace **una sola vez**, cuando el número de operaciones cerradas alcance **180** (n de Δ_t = 177, redondeado hacia arriba a múltiplo de 10).
- Se usan el script de T5 (`scripts/tl3_ai_counterfactual.py`), el criterio de `TL3_AI_TRADER_AUDIT` §5 (Δ ≥ 0.10 R con IC95 > 0) y el bootstrap con semilla 7.
- Antes de ese n **no se mira**. La evaluación necesitará aprobación del operador y registro en el contador; no se ejecuta en esta cola.
- Ninguna alerta cambia el EA, `ai_trader` ni el riesgo.

## Hipótesis registrada

- `H-2026-012` — «ai_trader frente a regla de tendencia, evaluación única a n = 180», estado `draft`, `created_at` 2026-11-25T20:19:37.376617+00:00.
- `dev_window`: 2026-11-13 a 2026-11-25 (las 48). `holdout_window`: 2026-11-26 a 2027-01-04 (estimada).
- `sigma` = sd de Δ_t; `mde` = 0.10 R. No se calcula ningún resultado nuevo ni se toca `ai_trader`.
