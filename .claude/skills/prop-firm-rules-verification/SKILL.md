---
name: prop-firm-rules-verification
description: "Verificar las reglas vigentes de un programa de una firma de fondeo de futuros (Topstep, Apex, TradeDay, MyFundedFutures, Take Profit Trader, Earn2Trade…) en fuentes oficiales y dejarlas versionadas con URL, fecha y certeza. Usar antes de calcular EV o de comprar una evaluación."
---

# prop-firm-rules-verification

## Propósito
Que el motor EV solo use reglas oficiales, fechadas y no caducadas (ADR-F09).

## Cuándo usarla
Programa nuevo, regla cerca de caducar (30 días) o cambio anunciado por la firma.

## Entradas
Firma, programa, tamaño.

## Procedimiento
1. Solo páginas oficiales de la firma (help center, términos). Las secundarias, como pista y marcadas.
2. Para cada campo de `04_SPEC_PROP_EV.md §8`: valor, URL exacta, cita corta, fecha de consulta.
3. Dos páginas oficiales en desacuerdo → `discrepancia` con ambas URL.
4. Imágenes o tablas no legibles → `sin_datos`.

## Validación
Cada número del YAML tiene `status` y `source`.

## Salidas
`config/prop_economics/programs/<firma>_<programa>_<tamaño>.yaml` y `docs/futures/research/prop_firms_<fecha>.md`.

## Falla si
Solo hay fuente secundaria para una regla que cambia el resultado.

## Restricciones
No inventar ni presentar reglas antiguas como vigentes. Nunca evadir reglas de la firma.
