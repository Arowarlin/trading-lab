# Comportamiento intradía del Nasdaq · estado y protocolo

Estado al 2026-11-25: **descriptivas DEV medidas (Fase B)**. Resultados en la
sección 5. Son frecuencias de comportamiento, **no** resultados de estrategia: no
llevan costes, stops ni tamaño, y no implican expectancy positiva. Las cifras que
circulan en foros y libros no indican la muestra, el periodo ni el método, y no
se usan.

## 1. Por qué no se mide todavía

Las estadísticas descriptivas de la sección 1.2 del encargo sirven para generar
hipótesis. Calcularlas sobre todo el histórico y después elegir estrategias con
ellas es data snooping. El laboratorio ya tuvo ese incidente:
`reports/discovery/incidente-r9-snooping.md`.

Por eso, antes de calcular nada, se **sella** el tramo de prueba (sección 3) y
las descriptivas se calculan **solo** en el tramo de desarrollo.

## 2. Datos disponibles en el laboratorio (inventario de solo lectura)

| Serie | Instrumento | Resolución | Rango | Volumen | Estado / uso previo |
|---|---|---|---|---|---|
| `data/cache/databento/US100_M1.parquet` | **NQ** CME (NQ.c.0, GLBX.MDP3) | M1 | 2010-06-07 → **2018-12-31** | volumen CME real | Usado por el EA `us100-ftmo1` (B3 2010–2017, A-2 2018): ver `reports/ea/us100-ftmo1-nq-2010-2017.md`. 288 sesiones de roll excluidas |
| `data/cache/databento/US100_H1.parquet` | NQ | H1 | 2010-06 → 2026-11-23 | real | validado en F10c |
| `data/cache/dukascopy/US100_M1.parquet` | Nasdaq-100 CFD (Dukascopy) | M1 bid + ask | 2011-09-18 → 2026-11-20 | tick volume | apto frente al bróker (corr 0,98–0,9995; R2g) |
| MT5 `US100.cash` | CFD FTMO | M5 | desde 2021-10 | tick volume | snapshots en `data/discovery/snapshots/` |
| MNQ | — | — | **no existe** en el laboratorio | — | MNQ cotiza desde mayo de 2019 |

Hueco crítico: **NQ/MNQ M1 de 2019-01 a 2026-11.** Sin ese tramo:
- los modelos de volumen (E) y RVOL solo pueden medirse en NQ 2010–2018;
- los modelos de precio se pueden medir en el proxy Dukascopy, sin el volumen CME;
- ningún resultado se puede atribuir a MNQ con datos recientes de MNQ.

Cómo conseguirlo: Databento GLBX.MDP3, esquema `ohlcv-1m`, símbolos `NQ.c.0` y
`MNQ.c.0` (y `definition` para los rolls), de 2019-01-01 a hoy. El coste
depende del uso y lo muestra el portal de Databento antes de descargar: **Sin
datos** aquí. La compra y la descarga las decide y hace el operador.

## 3. Protocolo de partición propuesto (a aprobar)

| Tramo | Fechas | Uso |
|---|---|---|
| Desarrollo (DEV) | 2010-06 → 2021-12 | descriptivas 1.2, definición de reglas, ablación |
| Validación (OOS-1, walk-forward) | 2022-01 → 2023-12 | elegir entre variantes preregistradas; incluye el mercado bajista de 2022 |
| **Sellado (OOS-2)** | 2024-01-01 → 2026-11-20 | **una sola lectura por configuración final** (`docs/holdout.md`) |

Las mismas fechas valen para NQ (si se compra el tramo 2019+) y para el proxy
Dukascopy.

## 4. Métricas que se calcularán en DEV (plantilla)

Cada tabla declara: instrumento, fuente, fechas, número de sesiones, sesiones
excluidas (rolls, festivos, medias sesiones) y definición exacta.

1. **Rango de apertura** (OR5, OR15, OR30 desde las 9:30 ET): percentiles 10/25/50/75/90 en puntos y en múltiplos de ATR(14) diario; por año y por día de la semana.
2. **Ruptura**: primera vela M1 que cierra fuera del OR antes de las 11:30.
   - Continuación: alcanza +k·OR antes de volver dentro del OR.
   - Falsa: vuelve a cerrar dentro antes de alcanzar +0,5·OR.
3. **VWAP de sesión** (desde las 9:30): probabilidad de tocar el VWAP antes de las 12:00 condicionada a la distancia en las 10:00 (en bandas de desviación).
4. **Alcances de 5/10/15/20/30/50/100 pt** desde el precio de las 9:30, 9:45, 10:00 y 10:30. Se reportan **también en múltiplos de ATR**, porque 20 pt en 2012 no equivalen a 20 pt en 2025.
5. **Barridos** de PDH/PDL y ONH/ONL: frecuencia de rebasar el nivel ≥ 1 tick y cerrar de vuelta dentro en ≤ N velas; recorrido posterior en R.
6. **Días de la semana** y **régimen de volatilidad**: cuartil del ATR(14) diario a cierre de la víspera, sin dato futuro.
7. **Días con noticias Tier 1/2** frente a días sin ellas. El calendario histórico sale de BLS, BEA y la Fed, y se reconstruye con fechas oficiales, no desde un calendario comercial.

Todas las cifras llevan un intervalo de confianza: binomial Wilson para
proporciones y bootstrap por sesión para medias.

## 5. Resultados DEV (Fase B, 2026-11-25)

**Muestras**
- **NQ** = Databento NQ.c.0 M1, volumen CME. 1.733 sesiones RTH completas,
  2010-06-30 → 2018-12-31. Excluidas: ventanas de roll, medias sesiones y
  sesiones con < 380 barras.
- **DUK** = Dukascopy USA100 M1 bid, sin volumen útil. 2.204 sesiones,
  2012-02-07 → 2021-12-31.

**Método**
- `tools/phase_b.py`, barras etiquetadas por su hora de apertura, ET.
- ATR = ATR(14) diario de RTH con el dato de la víspera.
- Intervalos: Wilson al 95 %.
- OOS-1 y OOS-2 **no** se han leído.

### 5.1 Rango por franja (mediana · p75, en puntos; mediana en ATR)

| Franja ET | NQ pts | NQ ×ATR | DUK pts | DUK ×ATR | % del rango RTH (NQ, mediana) |
|---|---|---:|---|---:|---:|
| Pre-market 08:00–09:30 | 10,0 · 15,5 | 0,21 | 17,8 · 33,2 | 0,20 | 27 % |
| 09:30–09:35 (OR5) | 8,0 · 11,8 | 0,17 | 12,9 · 25,9 | 0,17 | 21 % |
| 09:30–09:45 (OR15) | 12,8 · 19,3 | 0,28 | 20,9 · 40,5 | 0,28 | 35 % |
| 09:30–10:00 (OR30) | 16,8 · 25,5 | 0,36 | 26,9 · 52,2 | 0,35 | 46 % |
| 09:45–10:00 | 10,3 · 15,5 | 0,22 | 15,8 · 30,3 | 0,22 | 28 % |
| 10:00–10:30 | 13,5 · 20,0 | 0,29 | 20,1 · 38,3 | 0,27 | 37 % |
| 10:30–11:30 | 15,3 · 23,8 | 0,33 | 24,5 · 46,8 | 0,32 | 42 % |
| Mediodía 11:30–13:30 | 16,0 · 25,0 | 0,35 | 24,9 · 50,7 | 0,34 | 44 % |
| Tarde 13:30–16:00 | 18,3 · 28,3 | 0,40 | 29,0 · 58,0 | 0,39 | 51 % |

En puntos, el rango crece con el nivel del índice. Mediana del OR15:
- NQ: 9,8 pt en 2010 → 31,8 pt en 2018;
- DUK: 61,5 pt en 2021.

En múltiplos de ATR es estable entre fuentes y años. **Conclusión:** los
umbrales de 5–100 pt no son comparables entre años, y el sistema debe usar
múltiplos de ATR. El día de la semana apenas cambia el OR: medianas del OR15 en
NQ de 12,3 a 13,3 pt.

### 5.2 Rupturas del rango de apertura

Definición:
- primera vela M1 que **cierra** fuera del OR antes de las 11:30;
- continuación = alcanza nivel ± 1×OR antes de volver a cerrar dentro;
- falsa = vuelve a cerrar dentro antes de recorrer 0,5×OR.

| OR | Fuente | Rupturas | Continuación | Falsa | Vuelve tras 0,5×OR |
|---|---|---:|---|---|---|
| OR5 | NQ | 1.732 | 31,1 % [29,0–33,3] | 48,8 % [46,4–51,1] | 20,1 % |
| OR5 | DUK | 2.204 | 29,4 % [27,5–31,3] | 49,8 % [47,7–51,9] | 20,8 % |
| OR15 | NQ | 1.696 | 16,6 % [14,9–18,5] | 69,3 % [67,1–71,5] | 14,0 % |
| OR15 | DUK | 2.163 | 16,4 % [14,9–18,0] | 68,8 % [66,9–70,8] | 14,5 % |
| OR30 | NQ | 1.613 | 12,2 % [10,7–13,9] | 77,3 % [75,1–79,2] | 10,2 % |
| OR30 | DUK | 2.042 | 11,2 % [9,9–12,6] | 78,2 % [76,4–79,9] | 10,1 % |

- Las dos fuentes coinciden dentro de los intervalos.
- La continuación de 1×OR tras un primer cierre fuera es minoritaria en los tres OR.
- No hay patrón estable por año: OR15 NQ va del 13,5 % al 23,4 %.
- Por cuartil de ATR, la diferencia es de ±3 pp, dentro del ruido.
- En días FOMC la falsa ruptura sube (OR5 NQ: 58 %), pero son solo 36 rupturas.

Lectura: un breakout ingenuo al primer cierre M1 fuera del OR **no** tiene base
descriptiva favorable. Eso no prueba que el fade sea rentable: el recorrido medio
de la reversión y el stop determinan la expectancy, y eso se mide en la Fase C.

### 5.3 VWAP: tocarlo entre las 10:00 y las 12:00 según la distancia a las 10:00

| Distancia a las 10:00 | NQ | DUK (proxy sin volumen) |
|---|---|---|
| < 0,5σ | 96,1 % [93,6–97,7] (n = 361) | 96,0 % (n = 472) |
| 0,5–1σ | 90,5 % [87,2–93,0] (n = 400) | 92,5 % (n = 559) |
| 1–2σ | 81,5 % [78,7–84,0] (n = 800) | 83,4 % (n = 961) |
| ≥ 2σ | 78,5 % [71,8–84,0] (n = 172) | 80,7 % (n = 212) |

σ = desviación de precio ponderada por volumen desde las 9:30. La frecuencia
alta de retorno al VWAP es **esperable por construcción**: el VWAP sigue al
precio. No es una señal por sí misma.

### 5.4 Alcanzar X puntos desde la apertura de las 9:30 (NQ; arriba · abajo · cualquiera)

| X pt | antes de las 10:30 | antes de las 16:00 |
|---:|---|---|
| 5 | 72 · 72 · 99 % | 84 · 82 · 100 % |
| 10 | 48 · 48 · 81 % | 67 · 65 · 97 % |
| 15 | 30 · 32 · 57 % | 53 · 53 · 87 % |
| 20 | 20 · 22 · 39 % | 41 · 43 · 72 % |
| 30 | 9 · 12 · 20 % | 24 · 28 · 47 % |
| 50 | 2 · 4 · 7 % | 9 · 13 · 20 % |
| 100 | 0,3 · 0,4 · 0,6 % | 1,8 · 3,1 · 4,7 % |

En ATR (NQ, cualquier dirección antes del cierre):
- 0,25×ATR: 96,7 %;
- 0,5×ATR: 65,0 %;
- 0,75×ATR: 35,3 %;
- 1×ATR: 18,0 %.

DUK en ATR: 96,6 / 63,7 / 35,1 / 19,4 %. Las tablas en puntos de DUK son
mayores porque cubren 2019–2021, con el índice más alto (ver el JSON).

### 5.5 Barridos 9:30–11:30 (nivel rebasado ≥ 2 ticks; reclaim = cierre M5 de vuelta dentro en ≤ 15 min)

| Nivel | Fuente | Sesiones | Rebasado | Reclaim \| rebasado | VWAP antes de un nuevo extremo \| reclaim |
|---|---|---:|---|---|---|
| PDH | NQ | 1.330 | 23,7 % | 66,3 % [61,0–71,3] | 61,7 % [55,0–68,0] (n = 209) |
| PDL | NQ | 1.330 | 21,8 % | 64,1 % | 57,5 % [50,3–64,4] (n = 186) |
| ONH | NQ | 1.362 | 52,5 % | 64,6 % | 62,6 % [58,1–66,9] (n = 462) |
| ONL | NQ | 1.362 | 50,1 % | 68,9 % | 67,2 % [62,9–71,3] (n = 470) |
| PDH | DUK | 1.921 | 22,9 % | 64,7 % | 60,9 % (n = 284) |
| PDL | DUK | 1.921 | 19,6 % | 60,6 % | 58,8 % (n = 228) |
| ONH | DUK | 1.688 | 54,8 % | 64,1 % | 63,4 % (n = 593) |
| ONL | DUK | 1.688 | 49,8 % | 71,7 % | 61,7 % (n = 603) |

Es la única familia en la que la frecuencia del desenlace favorable supera el
50 % con intervalo propio: ONL NQ, 62,9–71,3 %. Pero:
- el resultado compara llegar al VWAP con superar el extremo del barrido sin
  normalizar las distancias. Si el VWAP queda más lejos que el extremo, un 60 %
  puede ser una expectancy negativa;
- es un candidato a medir en la Fase C (modelo B), **no** un edge.

### 5.6 Días de la semana y régimen

- Ni el día de la semana ni el cuartil de ATR previo separan las tasas de
  ruptura más allá del ruido de cada celda (n ≈ 300–550, ±4–5 pp).
- No hay base para un filtro por día de la semana.
