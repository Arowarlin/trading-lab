# STRATEGY_DEVELOPMENT_PLAN — Candidatas, priorizadas

Cada candidata necesita su **pre-registro** (`docs/campanas.md`) **antes** de ejecutar nada y la aprobación explícita del operador, porque suma pruebas al DSR. Ninguna se ejecuta mientras el DSR no esté corregido (tarea T01).

## S1. EA US100 FTMO1: validación forward (prioridad 1, no suma pruebas)

- Hipótesis: la estructura de la apertura de NY (sweep más FVG más VWAP) tiene una expectativa de al menos +0,10R neta.
- Protocolo: un forward congelado por hash en una cuenta dedicada durante 60 días o 40 operaciones, lo que llegue después. Pasa si PF ≥ 1,15, expectativa ≥ +0,10R, DD ≤ 6 %, slippage ≤ 2 puntos, 0 breach y al menos un 90 % de coincidencia con `ea_us100_engine`.
- Rechazo: expectativa forward < 0 tras 40 operaciones, o coincidencia < 80 % (sería un problema de réplica, no de edge).
- Análisis que no suma pruebas: sensibilidad año a año con las 8 variantes existentes de la rejilla y comparación entre riesgo fijo del 0,35 % y riesgo dinámico.

## S2. Momentum multi-activo diario diversificado (prioridad 2)

- Universo: 20-30 ETFs o futuros continuos de Yahoo (renta variable por región, bonos, materias primas y divisas).
- Reglas: señal de 12 meses menos 1 mes (y de 3 meses), tamaño por volatilidad inversa, rebalanceo mensual y costes de 5 bps.
- Muestra: desde 2005; holdout sellado nuevo a partir de 2024.
- **Una sola** especificación más dos variantes, N = 3. Rechazo si DSR v2 < 0,9 o el holdout tiene Sharpe < 0.
- Por qué no repite la campaña B: el universo es amplio y la especificación es de la literatura, no buscada.

## S3. Cambio de mes en índices (prioridad 3)

- Hipótesis: el retorno de los días −1 a +3 alrededor del cambio de mes supera al resto de días.
- Universo: SPY, QQQ, US100.cash y US500.cash.
- Reglas: largo del cierre de D−2 al cierre de D+3 y fuera el resto, con swap del CFD incluido.
- N = 1. Unos 12 eventos al año: hacen falta 20 años, así que se usan los datos diarios de Yahoo.
- Rechazo: t-stat < 2 en la muestra y en el holdout.

## S4. Reversión a corto en acciones grandes (prioridad 4, carril de equities en Alpaca)

- Reglas: las 10 peores del S&P 100 a 5 días, mantenidas 5 días, con filtro de tendencia de 200 días.
- Riesgo de sesgo de supervivencia: hace falta la composición histórica del índice. Si no está, la estrategia queda en **provisional**.

## Descartar ahora

- EURUSD london_pullback y USDJPY tokyo_breakout: desactivar el forward.
- Cualquier nuevo barrido de familias M15/H1 en FX.

## Seguir investigando

- us100-trend-d1, solo si sigue siendo positiva tras modelar el swap.
- Oro: hacer primero un estudio de costes (spread por hora frente al ATR de M5) antes de cualquier estrategia. Si el coste supera el 10 % del ATR de M5 en la ventana, no hay estrategia intradía viable.

## Complementariedad

S1 (intradía en US100) y S3 (pocos días al mes en el índice) están **correlacionadas en dirección**: comparten el límite de riesgo por símbolo. S2 y S4 diversifican de verdad.
