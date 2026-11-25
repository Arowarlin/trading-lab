# TL3 · Puertas H1 y H3 (T9, sin rendimiento)

## H1 · Deriva nocturna

- Bruto esperado declarado antes de mirar: **3,5 bps/noche**.
- Coste por noche (CFD-006, US100): spread 15:55 + 09:35 del perfil NY5m
  (90 + 90 puntos) + slippage 1 punto + swap largo 7,33 puntos =
  **188,33 puntos**; a precio 26.000 → **0,724 bps**.
- Candado: bruto 3,5 ≥ 2 × 0,724 = 1,449 → **pasa** en CFD-006.
- CFD-001: swap largo +1.076,28 puntos, crédito no fiable → **blocked:
  swap sin datos fiables**.
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
