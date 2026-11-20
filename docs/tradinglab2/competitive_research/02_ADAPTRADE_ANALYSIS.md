# 02 · Adaptrade Builder: análisis técnico

Consulta: 2026-11-20. El sitio oficial no pudo leerse directamente; fuentes: páginas de adaptrade.com
indexadas (Builder, How it Works paso 2, info), boletín "Good or Lucky", guía de usuario publicada (v2.2),
reseña de Stocks & Commodities y el grupo oficial de soporte.

## 1. Qué es

Generador de estrategias para Windows que usa **programación genética** para combinar indicadores,
operadores y órdenes de entrada/salida, y exporta a TradeStation, MultiCharts y otras plataformas. Plantea el
desarrollo como un problema de **inferencia estadística**: cada estrategia candidata es una hipótesis que el
tramo fuera de muestra apoya o refuta.

## 2. Motor evolutivo

| Elemento | Qué hace (documentado) | ¿Lo tenemos? |
|---|---|---|
| Programación genética | Árboles de reglas evolucionados por generaciones | Sí (AST + operadores, doc 05) |
| Población inicial | "Sembrada" según las opciones del usuario | Sí (plantillas + aleatorias) |
| **Build objectives vs build conditions** | Objetivos a maximizar/minimizar y **condiciones** (desigualdades: p. ej. correlación ≥ 0,95, complejidad ≤ 10); el fitness combina ambos. Más de 100 métricas | Sí: 5 objetivos NSGA-II + restricciones duras |
| Fitness | **Suma ponderada** de objetivos (no Pareto) | Nosotros: Pareto (más honesto con objetivos en conflicto) |
| Complejidad | Métrica y condición para limitar sobreajuste; el soporte recomienda añadirla con peso pequeño | Sí (objetivo 4 + `max_nodes`) |
| Bloqueo de partes (lock options) | Fijar partes de la estrategia durante la construcción | **No** (P2) |
| Múltiples series de datos | Construir sobre varios símbolos a la vez | No (P2) |
| Red neuronal como condición de entrada | Disponible | No — y **no conviene** (ver §4) |
| Stress testing / Monte Carlo durante la construcción | Disponible | Parcial (estrés tras la selección) |
| Test de significancia del proceso de construcción | Prueba que considera todo el proceso de búsqueda para ver si cada miembro supera el sesgo de minería de datos (basado en Aronson) | Equivalente conceptual: DSR con N efectivo + contador global |
| Reset por rendimiento OOS | Opción para reiniciar la construcción según el resultado fuera de muestra | **No, y no debe existir** (§4) |
| Multinúcleo | Sí | Sí (12 workers) |
| Editor | Adaptrade Editor (punto y clic) | No (consola Fase 8) |

## 3. Cómo controla el sobreajuste (y dónde falla)

Lo bueno: separación IS/OOS automática, métrica de complejidad, condiciones de selección y una prueba de
significancia que intenta descontar la búsqueda.

Lo que muestran los propios usuarios en el grupo oficial: estrategias buenas en IS **y** OOS que se
deterioran pronto con datos nuevos. Las causas que aparecen en esos hilos son prácticas de **reutilizar el
OOS para decidir**: reconstruir hasta alcanzar un objetivo de beneficio OOS, o elegir la mejor OOS entre
muchas. Eso convierte el OOS en otro tramo de entrenamiento. **Es exactamente el error que nuestro OOS-2
sellado de una sola lectura impide.**

## 4. Lecciones para TradingLab

Adoptar:
- **Condiciones duras separadas de objetivos** (ya lo hacemos) y añadir más condiciones baratas: avg bars en
  ganadoras/perdedoras, MAE máximo, % de operaciones en la ventana de sesión.
- **Bloqueo de partes de la plantilla** (lock): permite investigar una hipótesis concreta ("la entrada es
  esta; busca salida y filtro") con un espacio de búsqueda más pequeño ⇒ menos pruebas ⇒ mejor DSR.
- **Seguimiento de la calidad por generación** (mejor/mediana del frente, diversidad) → panel de evolución.

No adoptar:
- **Redes neuronales como condición** de entrada: multiplican los grados de libertad; el propio soporte
  de Adaptrade sugiere quitarlas cuando los resultados son malos.
- **Cualquier "reset" o reconstrucción guiada por OOS**.
- Fitness por suma ponderada: Pareto ya cubre el caso sin pesos arbitrarios.
