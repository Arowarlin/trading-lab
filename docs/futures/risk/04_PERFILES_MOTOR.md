# Seis perfiles de riesgo con el motor real (FUT-A + ORPAE), 3 programas 50K

**Fecha:** 2026-11-28 · **Autor:** Claude Code · **Estado:** SIMULADO e HIPOTÉTICO. Ninguna estrategia
está validada; las ventajas son escenarios, no mediciones.
**Diferencia con `01` y `03`:** aquellos usaban simuladores de investigación (`risk_sim.py`,
`programs_compare.py`). Este estudio usa el **motor de producción** (`src/tradinglab/prop_economics/`), con
las reglas completas de cada YAML:
- consistencia de la evaluación;
- trailing EOD o intradía con bloqueo absoluto y bloqueo al pedir payout;
- colchón de MFF;
- escalado de Lucid (20/30/40 micros);
- máximo de 5 payouts de Lucid antes de pasar a Live;
- topes de contratos;
- tarifas y plazos de cobro.

## 1. Método

- **Código:** `sim/engine_profiles.py`.
- **Simulación:**
  - 4.000 caminos por celda, semilla 13, presupuesto de 1.500 USD;
  - horizontes de 182, 365 y 730 días naturales (≈ 6, 12 y 24 meses, calendario CME);
  - inicio el 2027-01-04;
  - números aleatorios comunes entre perfiles.
- **Estrategia hipotética:**
  - 1 operación MNQ al día, stop de 25 puntos y objetivo de 1,5 R;
  - ganadoras con excursión adversa U(0,1)·riesgo; perdedoras con excursión favorable U(0,1)·riesgo
    (afecta al trailing intradía de MFF).
- **Ventaja bruta en R:** 0, +0,08, +0,13 y +0,20.
- **Coste por contrato, ida y vuelta** (comisión verificada + 1 tick por lado): Topstep 2,22 USD,
  MFF 2,90 y Lucid 2,00.
- **Perfiles** (riesgo por operación, con el máximo de pérdida de 2.000 USD):

| Perfil | Filosofía | Política |
|---|---|---|
| A | Conservador | riesgo fijo de 250 USD (12,5 % del MLL) |
| B | Moderado | 500 USD (25 %) |
| C | Agresivo | 750 USD (37,5 %) |
| D | Muy agresivo | 1.000 USD (50 %) |
| E | Extremo experimental | 1.500 USD (75 %) |
| F | Adaptativo | min(1.000, 0,3·colchón), mínimo 1 micro; antimartingala por construcción |

- **Supuestos explícitos:**
  - Topstep: plazo de cobro de 3 días (Sin datos en el YAML).
  - MFF: sin tope por payout y fracción del 100 % por encima del colchón (Sin datos: la fuente no
    publica tope).
  - Lucid: tarifa de evaluación de 125 USD (Sin datos: web 403).
  - Contratos por perfil: suelo(riesgo / (50 + coste)), por ejemplo 9 MNQ para B en Topstep. Después
    se aplican los topes del programa.
- **Regla de elección** (`01 §5`, sin cambios): máximo EV a 12 meses con mediana > 0, ruina del
  presupuesto a 24 meses ≤ 10 % y P(neto > 0) ≥ 60 %. Si ningún perfil cumple: no comprar.

## 2. Resultados

(Se rellena con `sim/engine_profiles.json`.)

## 3. Lectura

(Se rellena.)

## 4. Reproducir

```bash
python -I docs/futures/risk/sim/engine_profiles.py --paths 4000 --out docs/futures/risk/sim/engine_profiles.json
```
