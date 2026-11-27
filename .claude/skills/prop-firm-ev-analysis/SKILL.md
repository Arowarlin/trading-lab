---
name: prop-firm-ev-analysis
description: "Calcular e interpretar el valor esperado neto de retiros de una estrategia de futuros en un programa de prop firm con el motor de docs/futures/04_SPEC_PROP_EV.md (escenarios, horizontes 30/90/180/365, ventaja mínima, bankroll). Usar para comparar firmas o decidir si una estrategia merece una evaluación."
---

# prop-firm-ev-analysis

## Propósito
Traducir una estrategia en dinero neto esperado y en la ventaja mínima que necesita cada programa.

## Cuándo usarla
Comparar programas, dimensionar el riesgo por cuenta o decidir compras (siempre las decide el operador).

## Entradas
Pool de `DayPath` (forward > OOS > IS), programa YAML no caducado, bankroll, política de tamaño y de intentos.

## Procedimiento
1. Rechazar reglas caducadas o `sin_datos` sin `--assume` explícito.
2. Correr los 5 escenarios; el **conservador** es el de decisión.
3. Comprobar el error MC (§6.5) y la monotonía para μ\*.
4. Atribución: EV(estrategia) − EV(sin ventaja).
5. Separar **REALIZADO** (libro real) de **SIMULADO** en cada tabla.

## Validación
Vectores T1-T14 verdes en la versión del motor usada.

## Salidas
Informe en `reports/prop_economics/`.

## Falla si
Pool < 60 días con operaciones, error MC alto o reglas caducadas.

## Restricciones
Nunca mostrar una proyección como beneficio real. No usar el escenario optimista como principal.
