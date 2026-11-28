# Comparación de programas 50K: Topstep, MFF Rapid y Lucid Flex (misma estrategia hipotética)

**Fecha:** 2026-11-28 · **Autor:** Claude Code · **Estado:** investigación reproducible. **Ninguna
ventaja está validada**: todas las cifras son condicionales a una ventaja hipotética.
**Pregunta:** con la **misma** estrategia, ¿en qué programa llega más dinero neto al operador, y con qué
mediana y qué colas?

## 1. Método

- **Simulador:** `sim/programs_compare.py` (investigación, no el motor FUT-A). 4.000 caminos por
  celda, semilla 11, presupuesto de tarifas de 1.500 USD y horizontes de 6, 12 y 24 meses de sesión.
- **Estrategia:**
  - 1 operación MNQ al día, stop de 25 puntos y objetivo de 1,5 R;
  - riesgo fijo de 250, 500 o 1.000 USD por operación (5, 10 o 20 MNQ);
  - excursión adversa de las ganadoras U(0,1)·riesgo, vigilada en tiempo real.
- **Ventaja:**
  - **bruta** en R, igual para los tres programas: 0; +0,08; +0,13; +0,20; +0,30;
  - cada programa descuenta **sus** comisiones verificadas más 1 tick de slippage por lado (MNQ, ida y
    vuelta): Topstep 1,22 + 1,00; MFF 1,90 + 1,00; Lucid 1,00 + 1,00 USD;
  - ventaja neta = bruta − coste/50 (Topstep −0,044 R, MFF −0,058 R, Lucid −0,040 R).
- **Reglas:** de los YAML (`docs/futures/04 §8` para Topstep; `research/programs/*.yaml` para MFF y
  Lucid). Lo que se modela:

| Regla | Topstep 50K | MFF Rapid 50K | Lucid Flex 50K |
|---|---|---|---|
| Evaluación | 3.000 · trailing EOD 2.000 (se bloquea en S) · consistencia 55 % · 2 días · 50 micros | 3.000 · trailing EOD 2.000 (bloqueo en S: **supuesto**) · 50 % · 2 días · 50 micros | 3.000 · trailing EOD 2.000 (bloqueo en S + 100) · 40 % · 40 micros |
| Tarifas | 49 USD cada 21 sesiones + 149 de activación | 209 de lista (125 con promoción, en la sensibilidad), pago único | **Sin datos**: barrido de 75, 125, 175 y 225, pago único |
| Financiada | trailing EOD 2.000, bloqueo en 0 y en el primer payout · 20 micros (**supuesto**) | **trailing intradía** 2.000 con P&L no realizado, bloqueo en +100 (discrepancia) · 50 micros | trailing EOD 2.000, bloqueo en +100 y al pedir payout · escalado 20/30/40 micros |
| Payout | 5 días ≥ 150 · 50 % del saldo, hasta 2.000 · mínimo 125 · 90 % · 30 USD de transferencia · 10 sesiones de retraso | colchón de 2.100 que no se retira · todo lo que exceda el colchón, sin tope publicado · mínimo 500 · 90 % · comisión 0 y 2 sesiones (**supuestos**) | 5 días ≥ 150 y ciclo neto > 0 · 50 % del beneficio, hasta 2.000 · mínimo 500 · 90 % · comisión 0 y 3 sesiones (**supuestos**) · **5 payouts y pasa a Live** |

- **Supuesto de modelo en MFF.** En el trailing intradía, las perdedoras alcanzan antes una excursión
  favorable U(0,1)·riesgo, que sube el umbral antes de tocar el stop. Su efecto se mide con
  `mfe_losers = 0` en §4.
- **Lucid Live.** La cuenta que llega a 5 payouts sale del modelo, porque las reglas de Live no están
  verificadas, y el proyecto compra otra evaluación si hay presupuesto. **Esto infravalora a Lucid:**
  lo que se ganaría en Live no se cuenta.
- **Control de reproducción.** Con el coste de `risk_sim.py` (2,5 USD) y las reglas de Topstep, este
  simulador da un EV a 12 meses de 3.182 USD frente a 3.149 de `risk_sim.py` (n = 1.000), dentro del
  error Monte Carlo. Las secuencias aleatorias difieren porque aquí se sortea además la excursión
  favorable.

## 2. Resultados

(Se rellena con `sim/programs_compare.json`.)

## 3. Lucid: precio de equilibrio

(Se rellena con el barrido de tarifas.)

## 4. Sensibilidad de MFF (`sim/programs_compare_mff_sens.json`)

EV y mediana a 12 meses y ruina a 24 meses, en USD. Error estándar del EV: entre 12 y 95.

| Variante | Ventaja bruta | Riesgo | EV 12 m | Mediana 12 m | P(neto > 0) | Ruina 24 m |
|---|---:|---:|---:|---:|---:|---:|
| Base (209 de lista; MFE U(0,1)) | +0,13 R | 250 | 561 | −579 | 0,41 | 27,8 % |
| Base | +0,13 R | 500 | 981 | −1.394 | 0,38 | 63,5 % |
| Base | +0,20 R | 500 | 3.873 | 2.362 | 0,61 | 37,9 % |
| `mfe_losers = 0` | +0,13 R | 500 | 1.390 | −1.306 | 0,43 | 57,2 % |
| Promoción a 125 | +0,13 R | 250 | 936 | −220 | 0,47 | 2,7 % |
| Promoción a 125 | +0,13 R | 500 | **2.385** | **1.302** | 0,60 | 35,1 % |
| Promoción a 125 | +0,20 R | 500 | 5.601 | 4.734 | 0,81 | 14,9 % |
| Promoción a 125 + `mfe_losers = 0` | +0,13 R | 500 | 2.851 | 1.898 | 0,65 | 29,2 % |
| Base, sin ventaja bruta | 0 | 500 | −1.137 | −1.463 | 0,07 | 95,6 % |

**Lectura:**
- **En MFF Rapid, el precio de la evaluación domina.** Con el mismo presupuesto, 209 frente a 125 USD
  cambia el número de intentos y hace pasar el EV de 981 a 2.385 (riesgo 500, +0,13 R).
- **El supuesto de la excursión favorable** en el trailing intradía mueve el EV entre un 18 % y un
  42 % en las celdas con ventaja.
- **Sin ventaja bruta, MFF pierde casi todo el presupuesto:** ruina del 96 % a 24 meses con 500 USD
  de riesgo.

## 5. Lectura y recomendación condicional

(Se rellena.)

## 6. Reproducir

```bash
python -I docs/futures/risk/sim/programs_compare.py --paths 4000 --out docs/futures/risk/sim/programs_compare.json
```
