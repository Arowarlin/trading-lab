# 04 · Expert Advisor Studio (EA Studio): análisis técnico

Consulta: 2026-11-20. Fuentes: wiki oficial (EA Studio guide: Acceptance Criteria, Validator, Monte Carlo;
EA Studio Academy) y foro oficial de forexsb.com. expert-advisor-studio.com no pudo leerse directamente.

## 1. Qué es

Aplicación web de forexsb.com para generar, validar y exportar EAs de MT4/MT5. Comparte filosofía con FSB Pro
(criterios de aceptación, colecciones) pero se organiza como **cadena de herramientas**: Generator → Reactor
→ Validator → Collection → Portfolio/Export.

## 2. Flujo y funciones

| Herramienta | Descripción documentada | ¿Lo tenemos? |
|---|---|---|
| Generator | Genera estrategias; las que pasan los criterios de aceptación van a la Collection | Sí |
| **Acceptance Criteria** | Filtro aplicado en Generator, Reactor, Validator y Optimizer, sobre tres zonas del backtest (completo, IS y OOS si está activo) | Parcial (niveles) |
| **Reactor** | Genera y valida automáticamente en cadena; solo las estrategias que pasan **todas** las validaciones activadas llegan a la colección | Parcial (pipeline manual por CLI) |
| **Validator** | Importa colecciones/EAs y los pasa por las herramientas activadas (aceptación, Monte Carlo, multi-mercado); solo pasan a la colección las que superan todo | Parcial |
| **Monte Carlo** | Dos familias: **variaciones de mercado** (altera los datos dentro de un rango, lo que cambia los indicadores) y **problemas de ejecución** (fallos al ejecutar las señales); se aprueba si pasa un % de las simulaciones (p. ej. 80 %) | Parcial: nuestro MC solo reordena/remuestrea operaciones |
| Multi Market | Valida en otros símbolos; en Express Generator se trabaja en "pasa en k de n mercados" | Parcial (transfer informativo) |
| Optimizer | Optimiza parámetros con criterios de aceptación activos | Deliberadamente no |
| Export MQL4/MQL5 | EAs listos para MetaTrader | No (Fase 12) |

## 3. Diferencias con FSB Pro

EA Studio añade la automatización en cadena (Reactor, Validator) y el Monte Carlo con perturbaciones de
datos y ejecución. Se solapan en criterios de aceptación, colecciones, optimizador y exportación.

## 4. Qué adoptar

1. **Monte Carlo de ejecución y de mercado** (P1): saltar operaciones al azar, spread aleatorio por
   operación, slippage aleatorio, retraso de fill y ruido en precios. Nuestro MC actual no altera la
   estrategia ni los datos, solo el orden de las operaciones.
2. **"Pasa en k de n"** como forma de prueba multi-mercado, con mercados elegidos **antes** de ver
   resultados (P2).
3. **Pipeline en cadena con criterio "todas las pruebas activadas"**: ya es nuestro modelo de niveles; falta
   la automatización y la vista en consola.

## 5. Qué evitar

- La guía oficial sugiere fijar los criterios de aceptación a partir de una estrategia que guste para que el
  generador encuentre "similares": eso orienta la búsqueda con resultados ya vistos.
- Validaciones sucesivas que filtran por OOS repetidamente sin contar las pruebas.
