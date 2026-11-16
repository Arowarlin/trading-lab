# AI_ARCHITECTURE — Qué decide cada componente

## Principio

| Decisión | Quién decide |
|---|---|
| Precios, costes, SL, TP, lote, riesgo, límites y autorización de órdenes | Código determinista (ya es así) |
| Métricas (Sharpe, DSR, PBO) y criterios de promoción | Código determinista con criterios congelados por hash |
| Clasificar el régimen y estimar la volatilidad | Modelo estadístico simple (EWMA/GARCH, HMM con 2 estados), solo como variable |
| Filtrar las operaciones de una estrategia que ya tiene edge | Meta-labeling (GBM/LightGBM), y solo con más de 500 operaciones etiquetadas |
| Generar hipótesis, explicar resultados y criticar | LLM |
| Operar de forma discrecional | LLM, **como experimento** que se mide contra sombras aleatorias |

## Estado actual

- El carril IA respeta la separación: el LLM elige la estrategia, el símbolo, la temporalidad y la dirección, y el código calcula todo lo demás. Bien.
- El aprendizaje es asimétrico: lo que reduce riesgo se aplica solo y lo que lo aumenta queda propuesto. Bien.
- TradingAgents y Trading-R1: no hay ninguna evidencia en el repo de que hayan mejorado alguna decisión medida. Hay que medir antes de mantener su coste en tokens.

## Riesgos de aprendizaje

1. **Aprendizaje no es validación.** Una lección aprendida del forward se convierte en una prueba más: debe sumar al contador DSR. Ya lo hace para las lecciones; hay que comprobar que `ai_distill` también lo hace al proponer un bot.
2. **El replay no es forward.** `ai_replay` usa datos anonimizados, pero el LLM puede reconocer regímenes famosos. Sus resultados no deben entrar en el scoreboard forward. Hay que verificar que estén en tablas separadas (tarea T13).
3. **Tamaño de muestra:** con 0,25 % de riesgo y unas 2 operaciones al día por estilo, se tarda de 3 a 6 meses en distinguir +0,1R de 0. Antes de eso no hay que destilar ni promover nada.

## ML recomendado (cuando haya muestra)

- Meta-labeling sobre las operaciones del EA (más de 480 etiquetas en backtest), con validación purgada y embargo (CPCV), con LightGBM en CPU (el 5950X sobra). Objetivo: filtrar, no generar señales. Se registra como 1 prueba y se valida en forward.
- La GPU RX 6800 no aporta nada aquí: los modelos tabulares van mejor en CPU. ROCm en Windows sigue siendo limitado, así que no conviene depender de él.

## Agentes

No hay que añadir roles. El rol útil que falta es un **revisor adversarial** que lea cada informe de validación y busque fugas, unidades mal puestas o criterios cambiados. El LLM local (Qwen 30B A3B) puede hacerlo con la salida de las herramientas, sin capacidad de escribir en la configuración.
