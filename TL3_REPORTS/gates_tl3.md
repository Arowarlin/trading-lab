# TL3 · Puertas H1 y H3 (T9, sin rendimiento)

## H1 · Deriva nocturna

- Bruto esperado declarado antes de mirar: **3,5 bps/noche**.
- **Corrección 2026-11-25:** en `swap.yaml`, CFD-006 tiene `swap_mode: 5`
  (`interest_current`): `-7,33` es **% anual sobre el precio**, no puntos.
  Swap de una noche = 7,33 % / 365 ≈ **2,01 bps**; media con el día triple
  (`swap_rollover3days: 5`) ≈ **2,81 bps**.
- Spread 15:55 + 09:35 del perfil NY5m: 90 + 90 puntos MT5 = 1,8 puntos de
  índice ≈ **0,69 bps** a 26.000.
- Slippage: 0,5 pt de índice por lado = 1,0 pt total = **0,38 bps**.
- **Coste total ≈ 3,08-3,88 bps/noche.** 2 × coste ≈ 6,2-7,8 bps > 3,5 →
  **H-2026-010 = `rejected: cost_gate`**.
- CFD-001: swap largo +1.076,28 puntos, crédito no fiable → **blocked: swap
  sin datos fiables** (no se usa para el candado de CFD-006).
- No se calcula ningún retorno nocturno. Tarea para el operador: medir
  `swap_long/short` durante ≥ 20 sesiones antes de dormir posiciones.

## H3 · Impulso de apertura con expansión de rango

- OR de 30 min (09:30-09:59 NY), rango del día ≥ p70 de las 60 sesiones
  previas; holdout 2011-09-18 → 2014-12-31.
- Sesiones válidas (≥ 29 de 30 velas M1): **655**; con señal: **207 días
  distintos**.
- MDE = 2,49 / √207 = **0,1731 R** > δ 0,12 → **`rejected: no_power`**.
- No se ejecuta la estrategia ni se calcula PnL. No se prueba otra versión.

## Lectura

H1 pasa el candado de coste en CFD-006 pero no se ejecuta como prueba; en
CFD-001 queda bloqueada por el swap. H3 no tiene potencia para δ = 0,12 R con
los días de señal disponibles.
