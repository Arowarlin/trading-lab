# 01 · Build Alpha: análisis técnico

Consulta: 2026-11-20. El sitio oficial (buildalpha.com) **no pudo leerse directamente** desde el entorno de
investigación; se usaron una copia indexada de sus páginas de funciones y guía de robustez, artículos del
autor y la guía de usuario publicada. Todo lo que no aparece en esas fuentes se marca **No verificado**.

## 1. Qué es

Generador de estrategias para escritorio (Windows) orientado a futuros, acciones y forex, con una biblioteca
de señales predefinidas que se combinan automáticamente y una batería grande de pruebas de robustez.
Su fuerza no es el algoritmo de generación sino **la cantidad y variedad de pruebas para intentar refutar
una estrategia**.

## 2. Funciones (verificadas y no verificadas)

| Función | Qué resuelve / cómo parece funcionar | Fuente | ¿Lo tenemos? | Valor para TradingLab |
|---|---|---|---|---|
| Biblioteca de señales | Más de 5.000 señales predefinidas (patrones, indicadores, filtros) combinables | Página de funciones | Parcial: ~30 bloques + combinaciones AST | Medio. Más señales = más pruebas; preferimos familias con causa |
| Strategy Builder / generación | Selección de símbolos, fechas, timeframe, entradas, salidas, riesgo y función de fitness | Página de funciones | Sí (DSL + plantillas + GA) | — |
| Algoritmo genético | Mencionado; detalles internos | No verificado | Sí (NSGA-II propio) | — |
| Filtros automáticos de robustez | Exigir, durante la generación, que p. ej. la Noise Test sea positiva o la Variance Test sea x % del backtest | Página de funciones | No (robustez solo tras la selección) | **Alto**, con cuidado (ver doc 07) |
| **Noise Test** | Crea ~1.000 series de precio sumando/restando ruido a los OHLC y re-ejecuta la estrategia; si se derrumba, estaba ajustada al ruido concreto | Artículo del autor | **No** | **Alto (P1)** |
| **Vs Random** | Compara estrategias generadas con estrategias generadas con señales aleatorias | Página de funciones | Sí, mejorado: en OOS-2 (fase 7b) | Ya resuelto con más rigor |
| Across Markets | Re-test en otros mercados, timeframes y clases de activo para detectar backtests "mentirosos" | Página de funciones | Parcial (`retester.transfer`, solo informativo) | Medio-alto (P2) |
| Randomized OOS | Corte IS/OOS aleatorizado para no depender de un único corte | Guía de robustez | No | Bajo-medio: choca con OOS sellado; solo dentro de IS |
| Monte Carlo (bandas de equity) | Reordenación/remuestreo de operaciones | Página de funciones | Sí | — |
| Variance Testing | Variación de resultados ante cambios de supuestos | Página de funciones; método No verificado | Parcial (bootstrap) | Medio |
| Delayed entries/exits | Retrasar entradas/salidas N barras: una ventaja real se degrada suave, una sobreajustada se rompe | Prensa técnica sobre el método; en BA, No verificado en detalle | **No** | **Alto (P1)** |
| Intraday checks, Seasonality/Signal breakdown | Desglose por hora, día, mes y por señal | Parcial / No verificado | Parcial (hora × día) | Medio |
| Regime switching | Rendimiento por régimen | No verificado en detalle | Parcial (regime_report, con bug, ver doc 06) | Medio |
| Equity curve trading | Activar/desactivar según la equity de la propia estrategia | No verificado | No | **Descartar por ahora** (lógica adaptativa en vivo) |
| Parameter sensitivity | Superficie de parámetros | Página de funciones (Delta x3 en la guía) | Sí (meseta ±1) | Mejorar visualización (Fase 8) |
| Portfolio, correlación, ensembles, Portfolio Suggest | Construcción de carteras | No verificado en detalle | Parcial (`portfolio.py` legado) | Alto en Fase 11 |
| Prop Firm Simulator / Challenge Finder / Health Scores | Mencionados en el prompt del operador | **No verificado** (no se encontró documentación pública) | Sí (MC con `prop/simulator`) | Ver doc 07 §6.7 |
| MCP server | Mencionado en el prompt | **No verificado** | No | P3 (solo lectura) |
| Intelligence Report | Informe resumen nuevo | Página de funciones; contenido No verificado | Parcial (`lab discovery show`) | Medio |
| Generación de código | Exporta a varias plataformas (MT4 aparece en la guía) | Guía de usuario | No | Fase 12 |

## 3. Lo mejor de Build Alpha para nosotros

1. **Pruebas de falsificación por perturbación** (Noise Test, entradas/salidas retrasadas): no comparan una
   estrategia con otras —donde el sesgo de selección nos engañó en la fase 7— sino **con versiones
   perturbadas de sí misma**. Son complementarias a lo que ya tenemos.
2. **Pruebas como filtro dentro del flujo**, no solo al final. Útil, pero solo si el filtro **no lee OOS**.
3. Validación entre mercados relacionados como señal de causa real.

## 4. Limitaciones / riesgos

- Una biblioteca enorme de señales multiplica las pruebas: sin contador global tipo DSR, el usuario no ve el
  coste estadístico de buscar tanto. **No documentado** que BA cuente pruebas para ajustar significancia.
- Randomized OOS, si se usa para seleccionar, consume el OOS: incompatible con nuestro OOS sellado.
