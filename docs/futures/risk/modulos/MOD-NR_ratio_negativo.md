# MOD-NR · Módulo de estructuras de RATIO NEGATIVO (objetivo < stop)

**Fecha:** 2026-11-28 · **Autor:** Claude Code · **Pedido del operador:** "crear dos módulos: ventajas de
ratios negativos y también el otro" (el otro es `MOD-PR_ratio_positivo.md`).
**Estado:** módulo de investigación con simulador reproducible. La implementación en el motor de
producción es la tarea FUT-M1 (OpenCode, tras FUT-A6).

## 1. Definición

Una estructura es de **ratio negativo** cuando el objetivo neto `W` es menor que la pérdida neta `L`
(`RR = W/L < 1`). Gana más veces de las que pierde, pero cada pérdida pesa más. Variantes:

| Variante | Definición | Simulador |
|---|---|---|
| NR-fijo | riesgo fijo por operación (250-1.500 USD) y objetivo = RR·riesgo, con RR en {0,1; 0,2; 0,33; 0,5; 0,75} | `sim/structures_sweep.py` |
| NR-colchón ("día mínimo") | stop = todo el colchón hasta el MLL − 10 USD; objetivo = 150 USD netos (lo justo para que el día cuente) | `sim/min_day_strategy.py` |

## 2. Matemática

- **Acierto de equilibrio** (expectativa neta cero): `p* = L/(W + L)`. Con riesgo de 1.000 USD, 10 MNQ y
  RR 0,5: `W = 500 − 25`, `L = 1.000 + 25` → `p* = 0,683`.
- **Ventaja:** `E = p·W − (1−p)·L`. Una mejora de Δp en el acierto vale `Δp·(W + L)` USD. **Un punto de
  acierto vale más cuanto mayor es el stop.**
- **Fragilidad:** caer por debajo de `p*` lo borra todo. Con RR 0,1 hace falta un 91-95 % de acierto y
  un error de 3 puntos (costes, slippage, régimen) basta para volver la ventaja negativa.
- **Validación:** el error estándar de E por operación es `(W + L)·√(p(1−p)/n)`. Con alto acierto, la
  desviación por operación es menor que en RR ≥ 1 al mismo riesgo, así que **se valida con menos
  operaciones** (≈ 375 frente a ≈ 654 para +40 USD sobre unos 2.000 USD de riesgo; `01 §4.5`).
- **No crea ventaja:** el ratio no cambia la expectativa de un juego justo (teorema de parada opcional).
  La ventaja tiene que venir de la estrategia (por ejemplo, reversión a la media con alto acierto
  medido).

## 3. Interacción con las reglas de las firmas

| Regla | Efecto en ratio negativo |
|---|---|
| Día ganador mínimo (Topstep 150, Alpha 200, MFF/Lucid/TradeDay 150 según plan) | el objetivo neto **debe** superar el mínimo: con riesgo ≤ 250 USD y RR ≤ 0,5, **ningún día cuenta** y no hay payout |
| Tope por retiro (Topstep 2.000) y MLL bloqueado en 0 tras el payout | la variante NR-colchón se queda sin colchón tras el primer payout (`01 §4.5`) |
| Microscalping (Lucid ≤ 5 s, Tradeify > 50 % de operaciones de más de 10 s, TradeDay ≈ 10 s) | objetivos de pocos ticks cierran en segundos: **riesgo de anulación de beneficios**. El objetivo mínimo en ticks y la duración media tienen que medirse |
| "All or Nothing" (Alpha Futures) | la variante NR-colchón puede encajar en la prohibición: no usarla en Alpha |
| Hueco o slippage más allá del stop | con el stop cerca del MLL, cualquier deslizamiento rompe la cuenta |
| Escalado de contratos (XFA) | limita el riesgo efectivo en la financiada (supuesto de 20 micros en Topstep) |

## 4. Resultados (Topstep 50K, 4.000 caminos, presupuesto 1.500 USD; ventajas **hipotéticas**)

**Con ventaja neta de +40 USD por operación:**

| Riesgo | RR | EV 12 m | Mediana 12 m | P(neto > 0) | P(≥ 1 payout recibido) | Ruina 24 m | Cuentas 24 m |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 0,5 | 449 | −76 | 0,47 | 0,98 | 4,8 % | 13,3 |
| 500 | 0,75 | 1.102 | 421 | 0,60 | 0,98 | 5,6 % | 18,4 |
| 1.000 | 0,5 | 2.392 | 1.549 | **0,72** | 0,97 | 15,2 % | 43,1 |
| 1.000 | 0,75 | 3.657 | 2.372 | 0,71 | 0,90 | 24,9 % | 50,8 |
| **1.500** | **0,75** | **5.010** | **3.874** | 0,71 | 0,89 | 28,2 % | 74,4 |
| colchón (día mínimo) | ≈ 0,09 | 1.813 | 1.471 | **0,82** | 0,77 (1.ª XFA) | **0,3 %** | 16,1 |

**Con ventaja neta 0** (la ventaja bruta solo cubre los costes):
- con 1.500 USD de riesgo y RR 0,75 sale EV de 2.714, mediana de 1.169 y P(neto > 0) de 0,58 a 12 meses,
  con **ruina del 42 % a 24 meses**;
- con 1.000 USD y RR 0,5 sale EV de 826 y mediana de 108.

Es la **convexidad de las reglas** (pérdida limitada a la tarifa) llevada al extremo, no una ventaja.
Además depende del supuesto de escalado del XFA.

## 5. Cuándo tiene ventaja este módulo

1. **Riesgo por operación alto (≥ 50 % del MLL):** a igual ventaja, RR 0,5-0,75 maximiza la mediana y
   tiene menos ruina que RR ≥ 1,5 al mismo riesgo.
2. **Prioridad a la probabilidad de cobrar** (P(neto > 0), P(≥ 1 payout)) sobre el EV: la variante del
   día mínimo tiene la ruina más baja de todas (0,3 %).
3. **Estrategias cuya ventaja está en el acierto** (reversión, desvanecimiento de extremos) con duración
   suficiente para no caer en las reglas de microscalping.

**No tiene ventaja:**
- con riesgo bajo, porque no llega al día mínimo;
- en Alpha Futures, por la regla "All or Nothing";
- sin una ventaja validada en **su** estructura (el acierto real medido en forward).

## 6. Política de tamaño (para el ORPAE)

```text
objetivo_neto = max(día_mínimo_firma + margen, RR·riesgo − costes)
riesgo        = min(riesgo_política, colchón − margen, contratos_max·stop·valor_punto)
contratos     = suelo(riesgo / (stop_puntos·valor_punto + costes_por_contrato)), mínimo 1 micro
bloqueo       = si la duración media esperada < umbral de microscalping de la firma → NO OPERAR
```

Escalera de evidencia: igual que `01 §5`, pero con la cota inferior del **acierto**. Se opera solo si
`p_LCB > p*` con margen de costes y estrés de +1 tick por lado.

## 7. Criterios de aceptación del módulo

| ID | Criterio |
|---|---|
| NR-A1 | Acierto medido en forward con n ≥ 375 y `p_LCB(95 %) > p* + 0,01` |
| NR-A2 | Duración media de las ganadoras > umbral de microscalping de la firma (Lucid 5 s, Tradeify/TradeDay 10 s) con margen ×3 |
| NR-A3 | EV y mediana a 12 m > 0 en el motor FUT-A con la ventaja en su cota inferior, P(ruina) ≤ tolerancia del operador |
| NR-A4 | Estrés: costes ×1,5 y +1 tick de slippage por lado mantienen E > 0 |

## 8. Reproducir

```bash
python -I docs/futures/risk/sim/structures_sweep.py --paths 4000 --out docs/futures/risk/sim/structures_sweep.json
```

```bash
python -I docs/futures/risk/sim/min_day_strategy.py --paths 4000 --horizon 252 --out docs/futures/risk/sim/min_day_strategy_h252.json
```
