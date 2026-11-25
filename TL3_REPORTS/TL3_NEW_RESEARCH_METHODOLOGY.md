# TL3 · Nueva metodología de investigación

**Principio:** una hipótesis solo se ejecuta si, **antes de mirar ningún rendimiento**, se puede
demostrar con un cálculo que (a) el efecto esperado es mayor que el coste conocido y (b) la muestra
disponible puede detectarlo (MDE ≤ efecto). Si no se cumplen las dos condiciones, no se registra.
Así se evitan las 11 de 16 campañas que no podían decir nada (`TL3_STATISTICAL_VALIDATION_AUDIT.md §D`).

Leyenda en `TL3_FORENSIC_AUDIT.md`. Todo lo de este documento es **[REC]** salvo que se indique otra
etiqueta.

## 1. Restricción estratégica que hay que aceptar primero

**[INFERENCIA]** El objetivo práctico es pasar retos de fondeo (FTMO, FundingPips): +8–10 % en semanas
con un DD diario del 5 %. Eso exige Sharpe alto y frecuencia intradía. Es justo donde (1) los costes
pesan más (0,05–0,10 R por operación en US100 M5) y (2) las anomalías publicadas están más
arbitradas. Las anomalías con mejor evidencia académica (momentum de serie temporal, carry, drift
nocturno) tienen Sharpe de 0,3–0,8 anual: **son reales, pero no pasan un reto en 30 días**.

Consecuencia: hay que investigar en dos carriles con criterios distintos y no mezclarlos.
- **Carril R (reto):** intradía, alta frecuencia y coste dominante. Pocas hipótesis, de probabilidad
  previa baja.
- **Carril S (sostenido):** D1/eventos, ventaja pequeña pero documentada. Útil para la cuenta fondeada
  o una cartera, no para pasar la fase 1.

## 2. Triaje de familias (antes de implementar nada)

Columnas: fundamento económico (★ débil · ★★ medio · ★★★ fuerte/literatura) · ¿datos disponibles hoy? ·
operaciones/año por instrumento · MDE con 10 años y 3 instrumentos (σ = 1 R) · decisión.

| Familia | Fundamento | Datos hoy | Ops/año | MDE | Decisión |
|---|---|---|---:|---:|---|
| **Momentum** · intradía (1.ª media hora → última) | ★★ Gao-Han-Li-Zhou 2018 (SPY) | Sí (Dukascopy M1 BID) | 250 | 0,029 | **Probado en US100 M5 2021-24: bruto ≈ 0** (`intraday_momentum_close_v2`, neto −0,078, coste 0,064). No repetir sin un cambio de hipótesis |
| · apertura / ruptura OR | ★ práctica, poca literatura limpia | Sí | 200 | 0,032 | GA y barridos ORB_NY ≈ 0 neto en 2021-24. Solo como H3, con datos no vistos |
| · expansión de volatilidad | ★★ clustering de vol (GARCH) predice **rango**, no **dirección** | Sí | — | — | Útil como **filtro**, no como señal |
| · continuación de tendencia D1 (TSMOM) | ★★★ Moskowitz-Ooi-Pedersen 2012 | Sí (FX/XAU 2003+, índices 2011+) | 4–8 por activo | — (medir por Sharpe de cartera) | **Carril S**, H4 |
| · time-of-day | ★★ Heston-Korajczyk-Sadka 2010 (acciones) | Sí | 250 | 0,029 | Baja prioridad: evidencia en acciones individuales, no en índices |
| **Reversión** · VWAP / sobreextensión | ★ provisión de liquidez; evidencia mixta | Sí (volumen Dukascopy dudoso) | 100–200 | 0,04 | No ahora: muchos grados de libertad |
| · rupturas fallidas / sweeps | ★ narrativa de liquidez, sin evidencia cuantitativa limpia | Sí | 100 | 0,045 | No ahora |
| · reversión de rango | ★ | Sí | — | — | `asia_range_reversion` USDJPY: bruto −0,053 con 1.321 ops. **Cerrada** |
| **Estructura** · máx/mín día previo, overnight | ★ | Sí | 100–200 | 0,04 | Como **condición** dentro de H3, no como familia aparte |
| · transiciones de sesión (fix) | ★★ flujos de fixing | Sí | 375 | 0,03 | **Cerrada**: bruto 0,019 < coste 0,032 (v2, 7.527 ops) |
| **Volatilidad** · régimen ATR, compresión | ★★ como condicionante | Sí | — | — | Solo como variable de régimen **prerregistrada**, no optimizada |
| **Calendario / eventos** · deriva pre-FOMC | ★★★ Lucca-Moench 2015 (≈ 0,5 % en 24 h, decae tras 2015) | Sí (`.orquestador/fomc-fechas.md`) | 8 | Efecto grande por evento (≈ 0,4 σ diaria) → n ≈ 40 eventos bastan | **H2** |
| · deriva nocturna (overnight) | ★★★ Cliff-Cooper-Gulen 2008; Lou-Polk-Skouras 2019 | Sí | 250 | ≈ 3 bps/noche con ~3.800 noches/índice | **H1**: barata y decisiva sobre la prima bruta; el swap puede anular la neta |
| · cambio de mes | ★★ | Sí | 12 | 0,24 | No en un instrumento. Solo como cesta, y ya está en `v2-tom-indices-d1` |
| **Microestructura** (delta, order flow, imbalance) | ★★ | **No.** OHLCV sin bid/ask ni libro; Databento MBP-1/MBO tiene coste aparte | — | — | **No investigable** hasta tener datos de libro en futuros (Prioridad 2) |

## 3. Hipótesis prerregistrables (semana 3)

Reglas comunes: un parámetro primario fijo, una rejilla de meseta de ≤ 9 celdas solo para estabilidad,
**desarrollo y holdout fuera de periodo** fijados en la spec, costes v2 con spread por franja horaria y
swap, `plausible_edge_r` y `sigma_r` declarados, y MDE_holdout ≤ δ comprobado en el preflight.

### H1 · Deriva nocturna en índices (carril S, test decisivo y barato)

| Campo | Contenido |
|---|---|
| 1. Explicación económica | Los inversores exigen prima por cargar riesgo durante el cierre (no pueden cubrirse), y la presión compradora de minoristas en la apertura y vendedora institucional intradía genera un "tira y afloja" documentado: el retorno de los índices de EE. UU. se concentra fuera de la sesión |
| 2. Comportamiento | Retorno cierre (16:00 NY) → apertura (09:30 NY) > 0 de media; retorno intradía ≈ 0 |
| 3. Entrada | Largo a las 15:55 NY (BID+spread), todos los días hábiles NYSE |
| 4. Salida | 09:35 NY del día siguiente. Sin stop (la pregunta es la deriva, no la gestión) |
| 5. Mercado | Cesta US100, US500, US30 (CFD). No NQ/ES |
| 6. Temporalidad | M5 para precios de entrada y salida |
| 7. Frecuencia | ~250 noches/año/índice |
| 8. Riesgos | El swap largo de índice (~tipo + margen del bróker) puede ser ≈ la prima; gaps de fin de semana; el spread de la apertura se ensancha |
| 9. Benchmark | Mantener largo 24 h (buy & hold) y el retorno intradía (09:35 → 15:55) |
| 10. Métrica primaria | Retorno neto medio por noche en bps (después de spread y swap), cesta igual ponderada; LCB95 por bootstrap de bloques semanales |
| 11. Rechazo | LCB95 neto ≤ 0, o retorno nocturno ≤ intradía. **Sin partición desarrollo/holdout**: la regla no tiene parámetros libres, así que toda la muestra 2011-09 → 2026-11 (Dukascopy BID, spread modelado, **swap histórico** de T13) es una única prueba confirmatoria, prerregistrada y contada una vez. La muestra es posterior a la publicada (Cliff-Cooper-Gulen usan datos hasta 2006) |

Potencia [INFERENCIA]: ~3.800 noches por índice y σ nocturna ≈ 80 bps → MDE ≈ 3,2 bps. Los tres
índices están muy correlacionados (ρ ≈ 0,9), así que la cesta apenas reduce el MDE. La prima bruta
publicada ronda 3–4 bps/noche, y el swap (≈ 1,5–2 bps/noche con tipos del 5 %, casi 0 entre 2012 y 2021)
más el spread (≈ 0,7 bps en US100) se comen buena parte. **La prueba decide si existe la prima bruta.
La neta, con alta probabilidad, saldrá ≈ 0**, y eso también es un resultado útil y barato.

### H2 · Deriva previa al FOMC (carril S, eventos)

| Campo | Contenido |
|---|---|
| 1 | Resolución de incertidumbre antes del anuncio; la prima se cobra en las 24 h previas (Lucca-Moench 2015) |
| 2 | Retorno positivo anormal desde el cierre de t−1 hasta 14:00 NY del día del FOMC |
| 3 | Largo al cierre de t−1 |
| 4 | Salida 13:55 NY del día del anuncio (antes del comunicado) |
| 5 | Cesta US500, US100, US30 |
| 6 | M5 |
| 7 | 8 eventos/año |
| 8 | Efecto publicado en 2015, posible decaimiento; muy pocos eventos; fechas de reuniones no programadas |
| 9 | Retorno de cualquier ventana de la misma duración en días no FOMC (distribución de placebo) |
| 10 | Retorno neto medio por evento frente al placebo (diferencia en bps), t de Welch |
| 11 | Ventana fijada por la literatura (sin parámetros libres): una única prueba sobre todos los eventos 2011-09 → 2026-11 (~120), posteriores a la muestra publicada (1994-2011). Rechazo si la diferencia neta frente al placebo ≤ 0 o p ≥ 0,05 |

Potencia [INFERENCIA]: con σ diaria ≈ 120 bps y ~120 eventos, MDE ≈ 27 bps. El efecto publicado es
≈ 49 bps; si ha decaído a la mitad, la prueba queda justa. **Declarar δ = 30 bps y aceptar ese límite
en la spec.**

### H3 · Continuación del impulso de apertura con expansión de rango (carril R)

| Campo | Contenido |
|---|---|
| 1 | Información nocturna y órdenes acumuladas se ejecutan en la primera media hora. Cuando el rango del día se expande (vol alta), el desequilibrio continúa. Es el mecanismo del EA, **sin** sus ~70 parámetros |
| 2 | Si el precio a las 10:00 NY supera el máximo (mínimo) del rango 09:30–10:00 y el rango de esa media hora es ≥ p70 de los últimos 60 días, la tendencia sigue hasta el cierre |
| 3 | Ruptura del OR de 30 min en la dirección del gap, solo con rango OR ≥ p70 (parámetro primario fijo: 30 min, p70) |
| 4 | Stop en el lado opuesto del OR; salida a las 15:45 NY; sin objetivo (dejar correr) |
| 5 | Cesta US100, US500, US30 |
| 6 | M5 |
| 7 | ~70 operaciones/año/índice (30 % de los días) |
| 8 | Familia ya explorada en 2021-24 con resultado ≈ 0 (ORB_NY, GA, momentum). **Probabilidad previa baja.** Coste alto por stop corto |
| 9 | La misma regla sin el filtro de rango y la misma regla con lado aleatorio |
| 10 | Expectativa neta por operación (R), cesta |
| 11 | Desarrollo 2015-2020 (Dukascopy); holdout 2011-2014. **Nunca 2021-2026 de US100** (muestra del EA). Rechazo si LCB95 ≤ 0 o no supera al benchmark sin filtro |

Potencia [INFERENCIA]: 3 × 70 × 4 años ≈ 840 operaciones en el holdout → MDE ≈ 0,086 R con σ = 1 y
operaciones independientes. Las rupturas de los tres índices coinciden en muchos días, así que el n
efectivo es menor (quizá 400–500) y el MDE real ≈ 0,11–0,12 R. Declarar δ = 0,12 R. Si el preflight,
con el conteo real de días distintos, da MDE > δ, **no se registra**.

### Regla general que sale de H1–H3
Una hipótesis **sin parámetros libres** (ventana fijada por la literatura o por el mecanismo) no
necesita partición desarrollo/holdout: toda la muestra es una prueba confirmatoria si se prerregistra
y se cuenta una vez. La partición solo hace falta cuando hay algo que elegir. Eso dobla la muestra útil
y es la forma más barata de ganar potencia sin sumar pruebas.

### H4 · Tendencia en XAUUSD y cesta FX (carril S, prioridad 3)
Reutilizar `q3-tsmom-cesta-d1`, pero con desarrollo 2010-2020 y holdout 2003-2009 (Dukascopy) en lugar
de OOS-2 2025+. Métrica: Sharpe diario de cartera, no R por operación (4–8 operaciones/año por activo).

## 4. Reglas que los agentes no pueden saltarse

1. **Hipótesis cambiada = hipótesis nueva.** Si, tras ver un resultado, se cambia la regla, la ventana,
   el mercado o el criterio, se registra con un `hypothesis_id` nuevo y **un holdout nuevo**. El
   holdout usado queda quemado para esa familia.
2. **Los agentes proponen; no aprueban.** Ni las specs ni los criterios se aprueban sin el operador.
   Los umbrales estadísticos viven en un archivo con hash, fuera del alcance de escritura de los
   agentes (ver `TL3_ARCHITECTURE_PROPOSAL.md`).
3. **Antes de registrar:** cálculo de coste frente a bruto esperado (literatura o estudio de evento
   sin PnL) y MDE ≤ δ. Si falla, no se registra.
4. **Toda mirada cuenta.** Mirar una curva "solo para ver" es una prueba (`record-informal`).
5. **Benchmark obligatorio** en cada spec: placebo, lado aleatorio o regla trivial.
6. **Sin "PF > 1" como criterio.** La primaria es siempre una expectativa neta con su intervalo.
