---
name: statistical-validation
description: "Juzgar los resultados de una campaña o prueba de futuros contra las puertas congeladas (v3, PBO sobre población, Bonferroni sobre lecturas de OOS-2, WF, Monte Carlo, estrés de costes). Usar al leer resultados; nunca para ajustar umbrales."
---

# statistical-validation

## Propósito
Decidir aprobado/rechazado con las reglas escritas antes, sin moverlas.

## Cuándo usarla
Tras `lab discovery results`, una prueba única o un forward que alcanza su n.

## Entradas
ID de campaña/prueba, umbrales congelados (hash), resultados IS/OOS-1 y, solo en `confirm`, OOS-2.

## Procedimiento
1. Comprobar que los umbrales coinciden con el prerregistro (hash).
2. Puertas v3 y hallazgos ENG-1 D-01…D-07 aplicables.
3. Multiple testing: contador global + Bonferroni/Holm sobre las lecturas de OOS-2 de la línea (ADR-F10).
4. Estrés: costes ×1,5, +1 tick por lado; sensibilidad; regímenes.
5. Separar observado de estimado.

## Validación
Cada cifra con su fuente (fichero o consulta).

## Salidas
Veredicto con motivo por puerta.

## Falla si
Se pide bajar un umbral, leer OOS-2 fuera de `confirm` o combinar líneas A y B.

## Restricciones
**Nunca** cambia umbrales ni oculta resultados negativos.
