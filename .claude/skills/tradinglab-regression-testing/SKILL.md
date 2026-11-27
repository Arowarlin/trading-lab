---
name: tradinglab-regression-testing
description: "Aplicar el procedimiento de cambio controlado de AGENTS.md a un componente de producción (EA us100-ftmo1, forward FTMO, riesgo FTMO, ai_trader, Prop Fund, ea_lab): baseline, test de regresión antes/después, CHANGELOG y tag -pre. Usar antes de tocar cualquier fichero del manifiesto protegido."
---

# tradinglab-regression-testing

## Propósito
Poder demostrar qué cambió y volver atrás.

## Cuándo usarla
El hook pide confirmación (`ask`) al editar un fichero del manifiesto protegido.

## Entradas
Componente, motivo, fichero(s).

## Procedimiento
1. `lab propfund baseline --reason "..."` (informa, no bloquea).
2. Tag `tl2-<id>-pre` antes del primer commit.
3. Test de regresión: rojo/igual antes, verde después; si el comportamiento debe ser idéntico, comparación bit a bit.
4. Lock `changelog-produccion` y entrada en `docs/CHANGELOG-produccion.md`.
5. Commit pequeño por ruta.

## Validación
Baseline, test, CHANGELOG y tag existen y se citan en el commit.

## Salidas
Entrada de CHANGELOG con la vuelta atrás.

## Falla si
Falta la aprobación del operador en la sesión o el baseline.

## Restricciones
Nunca live; nunca activar bots ni F13 sin aprobación explícita.
