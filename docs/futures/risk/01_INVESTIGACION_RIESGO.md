# FUT-RISK-1 · Asignación óptima de riesgo y payouts netos (investigación)

**Fecha:** 2026-11-27 · **Autor:** Claude Code · **Filosofía (encargo del operador):** agresivo cuando
los datos lo justifiquen, menos exposición cuando la ventaja sea incierta, maximizar los retiros netos
recibidos a 6, 12 y 24 meses.

**Reproducir:** `python -I docs/futures/risk/sim/risk_sim.py --paths 4000 --seed 7 --budget 1500
--out docs/futures/risk/sim/topstep_risk_grid.json` (26 s). Resultados en ese JSON.
**Certeza:** reglas de Topstep **Confirmadas** (2026-11-27); ventajas **Hipotéticas**; costes y
escalado de la XFA **Estimados** (supuestos declarados).

## 1. Diagnóstico de la ventaja estadística (Paso 1-2)

| Hecho | Estado | Fuente |
|---|---|---|
| Ninguna estrategia de TradingLab tiene ventaja validada fuera de muestra | Confirmado | `ESTADO.md §2`; 0/34 finalistas; C1 rechazada |
| NQ/MNQ: el forward prerregistrado NQF-A/B/C empieza el 2026-11-30; n = 200 entre 2027-08 y 2030-10 | Confirmado | `NASDAQ_EDGE_INSTITUTIONAL/04_FORWARD/prerregistro.md` |
| Research A (order flow) sin datos; Research B (NY open) con historia contaminada | Confirmado | `docs/futures/00_AUDITORIA_REPO.md` FUT-10/11 |

**Consecuencia:** hoy **no hay nada que dimensionar** con dinero real. Esta investigación define *cómo*
se dimensionará cuando una estrategia pase la validación, y *qué evidencia* hace falta para cada nivel
de agresividad. Ninguna estrategia de producción se ha tocado.

## 2. Matemática

### 2.1 Expectativa
Por operación, en R (riesgo inicial = 1 R): `E = p·W − (1−p)·L`, con `W` y `L` **netos de costes**. Con
stop de 25 puntos en MNQ (1 R = 50 USD por contrato), objetivo 1,5 R y 2,5 USD de coste ida y vuelta
(0,05 R): `W = 1,45 R`, `L = 1,05 R`. La probabilidad de ganar que da una expectativa neta μ es
`p = (μ + L)/(W + L)`.

| Escenario (hipotético) | μ neta | p |
|---|---:|---:|
| Sin ventaja bruta | −0,05 R | 0,400 |
| Débil | +0,03 R | 0,432 |
| Moderada | +0,08 R | 0,452 |
| Sólida | +0,15 R | 0,480 |
| Elevada | +0,25 R | 0,520 |

### 2.2 Kelly, Kelly fraccionario y Optimal f
- **Kelly binario** (fracción del capital que se pierde en un stop): `f* = p − (1−p)·L/W`. Moderada:
  **5,5 %**; sólida: 10,3 %; elevada: 17,2 %.
- **Crecimiento retenido** con una fracción `c` de Kelly: `c·(2 − c)`. Medio Kelly conserva el 75 % del
  crecimiento con la mitad de varianza; un cuarto, el 44 %.
- **Sobreapuesta:** en la aproximación continua `G(f) = f·μ − f²·σ²/2`. Apostar 2× Kelly da crecimiento
  **cero**; más de 2×, negativo. Si la μ estimada dobla la real (habitual tras seleccionar entre muchas
  pruebas), el "full Kelly" estimado es exactamente esa apuesta 2×.
- **Incertidumbre:** con `σ ≈ 1,24 R` por operación (binaria anterior), el error estándar de μ es
  `1,24/√n`. Para que la cota inferior al 95 % (unilateral) supere 0 con μ = 0,08 hacen falta
  **≈ 654 operaciones**; para que supere 0,03, **≈ 1.675**. A una operación al día son 2,6 y 6,6 años.
  Kelly calculado con la μ puntual de 200 operaciones es, por tanto, una apuesta sobre ruido.
- **Optimal f** (Vince) maximiza el crecimiento geométrico sobre la serie histórica; depende de la peor
  pérdida observada y hereda todo el sesgo de selección. Mismas objeciones que Kelly, amplificadas.

### 2.3 Por qué Kelly sobre la cuenta es el objetivo equivocado en una prop firm
Kelly maximiza `E[log riqueza]` cuando perder el capital es la ruina. En una cuenta de fondeo:
- la pérdida está **limitada a la tarifa** (49 USD + 149 de activación en Topstep 50K);
- la ganancia está **capada** por retiro (2.000 USD en el XFA 50K Standard) y condicionada a reglas
  (5 días ganadores de ≥ 150 USD);
- el pago es **convexo**: se parece más a una opción comprada que a un capital propio.

Por eso el tamaño que maximiza los retiros netos es **mayor que Kelly** y lo fija la interacción con
las reglas, no la fórmula. Kelly sí aplica al nivel de arriba: **cuántas cuentas** puede sostener el
presupuesto real del proyecto (§4.3).

### 2.4 Riesgo de ruina de una cuenta
Aproximación browniana con deriva μ y varianza σ² por operación, distancia al MLL `D` y al objetivo `T`
(en R): `P(aprobar) = (1 − e^(−aD)) / (1 − e^(−a(D+T)))`, con `a = 2μ/σ²`. Sin ventaja: `D/(D+T)`.

| Riesgo por operación | D (R) | T (R) | P(aprobar), μ = 0 | P(aprobar), μ = +0,08 R |
|---|---:|---:|---:|---:|
| 250 USD | 8 | 12 | 0,40 | 0,64 |
| 500 USD | 4 | 6 | 0,40 | 0,53 |
| 1.000 USD | 2 | 3 | 0,40 | 0,46 |

Es el caso estático. El trailing EOD de Topstep baja estas cifras; el simulador lo modela exacto.
**Lectura:** más riesgo aprueba menos veces, pero mucho más rápido y con menos cuotas mensuales. El
óptimo económico depende de las tarifas y los payouts, no solo de P(aprobar).

## 3. Interacciones con las reglas de Topstep (verificadas)

1. **Día ganador mínimo de 150 USD para el payout.** Con 1 operación al día y RR 1,5, un día ganador
   neto vale `1,5·r − costes`. Con 100 USD de riesgo: 150 − 5 = **145 < 150**: **nunca cobra**. El
   riesgo mínimo útil es de unos 105 USD por día.
2. **Consistencia del Combine (55 %):** con riesgo ≥ 1.100 USD y RR 1,5, un solo día ganador supera
   1.650 USD y sube el objetivo.
3. **Tope por retiro de 2.000 USD y MLL bloqueado en 0 tras el primer payout:** retirar deja la cuenta a
   pocos días malos de cerrarse. Por eso el valor está en **repetir ciclos baratos**, no en hacer crecer
   una cuenta.
4. **Escalado del XFA:** la tabla es una imagen (Sin datos); el simulador supone 20 micros (el ejemplo
   "2-lot" de Topstep). Afecta al perfil E.

## 4. Simulación (Paso 6)

**Configuración:** Topstep 50K Combine → XFA Standard; 4.000 caminos por celda; semilla 7;
presupuesto de tarifas 1.500 USD (se recargan con los payouts recibidos); 1 operación/día; payout
recibido 10 sesiones después, con 30 USD de transferencia internacional; 5 escenarios de ventaja.

**Perfiles:**
- **A–E:** riesgo fijo por operación: 50 / 100 / 250 / 500 / 1.000 USD (2,5 / 5 / 12,5 / 25 / 50 % del
  MLL).
- **F:** adaptativo, `min(500, 0,25 × colchón)`.
- **K:** Kelly (completo, ½ y ¼) sobre el colchón hasta el MLL.

### 4.1 Resultados con ventaja moderada (+0,08 R) — USD netos recibidos

| Perfil | 6 m EV | 12 m EV | 12 m mediana | 12 m P5 / P95 | P(neto > 0) 12 m | P(≥1 payout recibido) 12 m | 24 m EV | 24 m mediana | P(ruina del presupuesto) 24 m | Cuentas compradas 24 m |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|
| A 50 | −343 | −638 | −637 | −637 / −637 | 0,00 | 0,00 | −1.167 | −1.225 | 0,000 | 1,0 |
| B 100 | −350 | −609 | −637 | −737 / −394 | 0,00 | 0,00 | −922 | −982 | 0,000 | 1,6 |
| C 250 | −39 | 176 | −384 | −884 / 2.993 | 0,37 | 0,87 | 637 | 1 | 0,054 | 10,5 |
| **D 500** | **1.194** | **3.058** | **1.962** | −1.380 / 11.037 | **0,76** | 0,96 | **6.594** | **5.528** | **0,091** | 29,9 |
| E 1.000 | 3.371 | 7.662 | 5.153 | −1.580 / 26.992 | 0,67 | 0,74 | 16.364 | 13.664 | 0,341 | 44,7 |
| F adaptativo | 82 | 357 | −400 | −786 / 3.795 | 0,37 | 0,62 | 990 | 110 | 0,001 | 5,2 |
| K completo | −345 | −622 | −637 | −688 / −492 | 0,00 | 0,00 | −943 | −1.225 | 0,000 | 1,1 |

### 4.2 Todos los escenarios: EV y mediana a 24 meses (USD), y P(ruina del presupuesto)

| Perfil | Sin ventaja | Débil +0,03 | Moderada +0,08 | Sólida +0,15 | Elevada +0,25 |
|---|---|---|---|---|---|
| C 250 | −1.041 / −1.375 / 30 % | −255 / −819 / 12 % | 637 / 1 / 5 % | 2.729 / 1.918 / 1,5 % | 8.010 / 7.098 / 0,1 % |
| D 500 | **409 / −822 / 47 %** | 3.431 / 2.363 / 20,5 % | 6.594 / 5.528 / 9,1 % | 13.212 / 11.866 / 2,8 % | 28.387 / 26.874 / 0,4 % |
| E 1.000 | **1.724 / −1.476 / 69 %** | 8.481 / 2.741 / 47 % | 16.364 / 13.664 / 34 % | 32.023 / 34.183 / 21 % | 58.092 / 63.859 / 8,4 % |
| F adaptativo | −889 / −1.289 / 3 % | −89 / −818 / 0,5 % | 990 / 110 / 0,1 % | 3.820 / 2.831 / 0 % | 11.990 / 10.406 / 0 % |
| K completo | — | −1.211 / −1.225 / 0 % | −943 / −1.225 / 0 % | 1.249 / 529 / 0 % | 8.299 / 8.002 / 0 % |

(A y B pierden la tarifa en todos los escenarios por la regla de los 150 USD.)

**Media frente a mediana:** sin ventaja, D y E tienen **media positiva y mediana negativa**. Eso es la
convexidad de las reglas (pocos caminos con muchos payouts) y **no** una ventaja. Con ese EV, el 53-68 %
de los proyectos pierde dinero y la mitad o más agota el presupuesto.

### 4.3 Varias cuentas (24 meses, 3 cuentas)

| Ventaja | Perfil | Cuentas | EV | Mediana | P5 | P(neto > 0) |
|---|---|---|---:|---:|---:|---:|
| Moderada | D 500 | 3 con la **misma** estrategia (correladas) | 19.781 | 16.586 | −4.434 | 0,860 |
| Moderada | D 500 | 3 estrategias **independientes** | 19.781 | 18.763 | **+3.902** | **0,985** |
| Sin ventaja | D 500 | 3 correladas | 1.227 | −2.465 | −4.738 | 0,383 |
| Sin ventaja | D 500 | 3 independientes | 1.227 | 202 | −4.442 | 0,519 |

Tres cuentas con la misma señal son **una sola apuesta tres veces más grande**: mismo EV y la misma cola.
La diversificación real (estrategias independientes) no sube el EV, pero convierte un P5 de −4.434 en
+3.902.

### 4.4 Rachas agrupadas (regímenes persistentes, ±0,08 en p, cambio del 5 % diario; moderada, 12 m)

| Perfil | EV independiente → con regímenes | Mediana | P(neto > 0) |
|---|---|---|---|
| C 250 | 176 → 687 | −384 → −104 | 0,37 → 0,47 |
| D 500 | 3.058 → 4.760 | 1.962 → 3.438 | 0,76 → 0,83 |
| E 1.000 | 7.662 → 9.574 | 5.153 → 8.084 | 0,67 → 0,72 |

Con un pago convexo, la varianza agrupada **sube** el EV (las buenas rachas aprueban y cobran; las malas
solo cuestan la tarifa). No es una razón para buscar volatilidad: es una advertencia de que suponer
operaciones independientes cambia las cifras y de que hay que medir el agrupamiento real en el forward.

### 4.5 Ratio negativo para el "día mínimo" (propuesta del operador, 2026-11-27)

**Propuesta:** arriesgar casi todo el colchón hasta el MLL para ganar los 150 USD netos que hacen contar
el día (ratio ≈ 1:13; 10 MNQ, 25 USD de coste, objetivo bruto 175 USD, stop = colchón − 10 USD).
**Reproducir:** `python -I docs/futures/risk/sim/min_day_strategy.py --paths 4000 --horizon 252
--out docs/futures/risk/sim/min_day_strategy_h252.json`.

**Teoría:**
- **Acierto:** sin ventaja es `p = R/(R + W)`. Con R = 1.965 USD y W = 175 USD brutos sale 0,918. Para
  llegar al 95 % haría falta `R ≥ 19·W ≈ 3.325 USD`, por encima del MLL de 50K (2.000): **imposible en 50K**.
- **Expectativa:** el acierto alto no cambia la expectativa. Por el teorema de parada opcional, la
  ganancia esperada de un juego justo es 0 con cualquier stop, objetivo o tamaño; queda en −costes.
- **El ciclo de payout pide 5 días ganadores seguidos sin perder:** `0,918⁵ = 0,65`.
- **El Combine pide unos 20 seguidos:** `0,918²⁰ ≈ 0,18`.
- **Tras el primer payout el MLL se bloquea en 0:** con unos 375 USD de balance, el colchón ya no deja
  repetir la jugada.

**Simulación (12 meses, presupuesto 1.500 USD):**

La ventaja de esta tabla es **bruta** (antes de los 25 USD de costes por operación): +65 USD brutos
equivalen a +40 USD netos.

| Ventaja bruta por operación (hipotética) | Neta | Acierto inicial | EV | Mediana | P5 / P95 | P(neto > 0) | Primera XFA con ≥ 1 payout | Payouts | Cuentas compradas | P(ruina) |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 0 USD | −25 | 0,918 | −366 | −595 | −1.469 / 1.594 | 0,27 | 0,66 | 3,7 | 22,7 | 0,070 |
| +10 USD | −15 | 0,923 | −154 | −432 | −1.462 / 1.993 | 0,35 | 0,67 | 4,2 | 21,7 | 0,045 |
| +20 USD | −5 | 0,928 | +81 | −179 | −1.364 / 2.368 | 0,43 | 0,69 | 4,7 | 20,7 | 0,031 |
| +40 USD | +15 | 0,937 | +695 | +360 | −1.157 / 3.625 | 0,62 | 0,72 | 5,9 | 18,7 | 0,009 |
| **+65 USD** | **+40** | 0,949 | **+1.813** | **+1.471** | −708 / 5.676 | **0,82** | 0,77 | 8,1 | 16,1 | **0,003** |

**Comparación justa** (misma ventaja **neta**: +40 USD por operación, 12 meses):

| Estructura | EV | Mediana | P5 | P(neto > 0) | P(ruina del presupuesto) |
|---|---:|---:|---:|---:|---:|
| Perfil D: 500 USD de riesgo, RR 1,5 (+0,08 R) | **+3.058** | **+1.962** | −1.380 | 0,76 | 0,091 (24 m) |
| Ratio negativo ≈ 1:11 (día mínimo) | +1.813 | +1.471 | **−708** | **0,82** | **0,003** |

**Lectura:** no está dominado. Cambia **EV por menos dispersión**: unos 59 % del EV del perfil D, pero
mejor P5, más caminos en positivo y casi sin ruina del presupuesto. Pierde EV porque:
- cada payout está capado al 50 % de un balance pequeño;
- el MLL bloqueado en 0 tras el primer payout deja la cuenta sin colchón;
- los costes pesan el 14 % del objetivo.

**Ventaja en R y su medida:**
- +40 USD sobre 1.965 USD de riesgo son solo **+0,02 R**.
- Basta que el acierto caiga 3 puntos (del 94,9 % al 91,8 %) para borrarla entera: es muy sensible a costes
  y slippage.
- A cambio, su desviación por operación es menor (≈ 471 USD frente a ≈ 622 USD del perfil D). Para que
  la cota inferior al 95 % de +40 USD supere 0 hacen falta **≈ 375 operaciones** (≈ 654 en el perfil D).

**Cuál elegir:** con el criterio de §5 (EV máximo con restricciones), el perfil D gana. Si el operador
fija una tolerancia de ruina ≤ 5 % o pide P(neto > 0) ≥ 80 %, gana el ratio negativo. **La elección
depende del presupuesto y de la tolerancia, y se decide con la ventaja validada de cada estructura.**

**Por qué "parece que funciona":** el 66 % de las primeras cuentas financiadas cobra al menos una vez y
eso es lo que se ve y se comparte. El otro 34 %, y los unos 5 Combines que cuesta cada cuenta
financiada, se comen esos cobros: es **sesgo de supervivencia**.

**Riesgos añadidos:**
- un hueco o slippage más allá del stop toca el MLL;
- objetivos de pocos ticks pueden chocar con las reglas de microscalping (Lucid ≤ 5 s, Tradeify y
  TradeDay ≈ 10 s);
- Alpha Futures prohíbe el enfoque "All or Nothing".

**Decisión:**
- El ratio negativo **queda como una política más** dentro de la rejilla del ORPAE (`02_ORPAE_DISENO.md`).
- Se elige solo si gana en EV con las restricciones de §5 **con la ventaja validada de esa estructura
  concreta**. Las estrategias de alto acierto tienen su propia ventaja, que se mide igual en R.
- Con los datos de hoy, ninguna de las dos estructuras domina a la otra: RR 1,5 da más EV y el ratio
  negativo, menos riesgo de ruina. Decide la tolerancia del operador.

## 5. Regla de decisión y recomendación (Paso 9)

**Criterio:** maximizar el EV a 12 meses **sujeto a** mediana > 0, P(ruina del presupuesto a 24 m)
≤ 10 % y P(neto > 0) ≥ 60 %, usando la **cota inferior** de la ventaja, nunca su estimación puntual.

| Ventaja validada (cota inferior al 95 %) | Política recomendada en Topstep 50K | Motivo |
|---|---|---|
| < 0 o sin validar | **No comprar evaluaciones** (solo paper/forward) | Toda política tiene mediana ≤ 0 o ruina alta |
| ≈ +0,03 R | **No comprar todavía** | D tiene mediana > 0 pero ruina del 20,5 %; C, mediana < 0 |
| ≈ +0,08 R | **D: 500 USD por operación (25 % del MLL)** | EV 3.058 / mediana 1.962 a 12 m; ruina 9,1 % |
| ≈ +0,15 R | **D**; E solo con presupuesto mayor | E: ruina 21 % con 1.500 USD |
| ≥ +0,25 R | **E: 1.000 USD**, si el escalado lo permite | EV 25.275 a 12 m; ruina 8,4 % |

- **Es una "escalera de evidencia":** se sube de peldaño solo cuando la cota inferior de la ventaja,
  medida en el forward, lo justifica. Nunca por una racha ganadora.
- **Se baja de peldaño** si la cota cae (control de deriva, `discovery/drift.py`). Bajar no es recuperar:
  no hay martingala ni aumento tras pérdidas.
- **Kelly sobre la cuenta queda descartado** para el tamaño por operación: arriesga demasiado poco para
  las reglas de payout. Se usa en el nivel del presupuesto: con estas distribuciones (muy
  asimétricas, la mayoría de ciclos pierden la tarifa), dimensionar el **número de cuentas a la vez** por
  la cota inferior y la P(ruina), empezando por 1-3 cuentas con **estrategias distintas**.

## 6. Hipótesis y criterios de aceptación (Paso 4)

| ID | Hipótesis | Aceptación |
|---|---|---|
| H-RISK-1 | En Topstep 50K, con μ validada ≥ +0,08 R, el riesgo de 25 % del MLL domina a 12,5 % y a 50 % en EV con las restricciones de §5 | Diferencia de EV > 2 SE con números aleatorios comunes y restricciones cumplidas en el motor FUT-A |
| H-RISK-2 | El riesgo útil mínimo en Topstep es ≥ (150 + costes)/RR por día ganador | Test del motor: con 100 USD y RR 1,5, 0 payouts en 10.000 caminos |
| H-RISK-3 | La convexidad da EV > 0 sin ventaja con riesgo ≥ 25 % del MLL | Se mide y se marca; **nunca** se acepta como justificación para comprar |
| H-RISK-4 | Estrategias independientes mejoran P5 y P(neto > 0) con el mismo EV | Correlación de los P&L diarios < 0,3 medida en forward |
| H-RISK-5 | El agrupamiento real de pérdidas cambia el tamaño óptimo | Estimar el agrupamiento con el forward NQF y repetir con stationary bootstrap |

## 7. Limitaciones

- **Ventajas hipotéticas:** el día que haya una estrategia validada se sustituyen por su pool de
  `DayPath` (FUT-A) y su cota inferior.
- **Una operación al día**, bracket fijo y ganadoras con excursión adversa uniforme: es una
  simplificación.
- **Pendiente de verificar:**
  - el escalado del XFA (supuesto de 20 micros);
  - las comisiones reales de Topstep;
  - el retraso exacto de los payouts.
- **No modelado:**
  - la reactivación Back2Funded (599 USD);
  - la cuenta Live (LFA);
  - impuestos.
- **Una sola firma.** El resto entra cuando sus fichas tengan reglas suficientes.
  `docs/futures/research/propfirms_2026-11/`.
