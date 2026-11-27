---
name: hypothesis-preregistration
description: "Redactar el prerregistro de una hipótesis de futuros (Research A order flow o Research B NY open) antes de ver resultados: mecanismo, datos, regla fija, costes, potencia, contaminación y criterio de rechazo. Usar siempre antes de proponer una campaña o una prueba única."
---

# hypothesis-preregistration

## Propósito
Convertir una idea en una prueba única falsable (método ENG-1 R1) sin mirar el resultado.

## Cuándo usarla
Antes de cualquier campaña, `record-informal` o prueba que sume al DSR.

## Entradas
Idea, instrumento, línea (A o B), datos disponibles.

## Procedimiento
1. Mecanismo económico: quién paga y por qué la ventaja existiría.
2. Datos mínimos según `03 §3.1` (L0/L1/L2/L3). Order flow con OHLCV = **no se registra**.
3. **Contaminación** (FUT-11): ¿la lógica o el periodo ya se miraron (EA `us100-ftmo1`, NASDAQ_EDGE, EDGE-1/2)? Etiquetar `limpia`, `parcial` o `contaminada`; en NQ NY open, solo forward.
4. Regla fija sin parámetros a optimizar; entrada, salida, stop y tamaño exactos.
5. Costes por contrato (comisión, exchange, NFA, slippage en ticks) y coste en R.
6. Potencia: MDE frente a la **ventaja mínima rentable** μ\* del motor EV (`04_SPEC_PROP_EV.md §7.2`). Si MDE > ventaja plausible, no se registra.
7. Criterio de rechazo escrito antes (t HAC, LCB, Bonferroni sobre lecturas de OOS-2).
8. IDs: Campaign `FUT-RA-n`/`FUT-RB-n`, Hypothesis `H-AAAA-NNN`, Experiment.

## Validación
Otra sesión verifica conformidad con el prerregistro (plantilla de `.orquestador/PLANTILLA-COLA.md`, bloque V).

## Salidas
Borrador de prerregistro en Markdown; nunca resultados.

## Falla si
Falta mecanismo, coste, potencia o etiqueta de contaminación.

## Restricciones
**No registra ni ejecuta**: `lab discovery register/approve/run` y `record-informal` son del operador.
