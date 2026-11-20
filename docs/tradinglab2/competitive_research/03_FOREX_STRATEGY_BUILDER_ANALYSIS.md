# 03 · Forex Strategy Builder (FSB Pro): análisis técnico

Consulta: 2026-11-20. Fuentes: wiki oficial de forexsb.com (guía FSB Pro: Acceptance Criteria, Strategy
Optimizer, Multi Tester), foro oficial y registro de cambios. El sitio raíz no pudo leerse directamente.

## 1. Productos y vigencia

forexsb.com publica varias herramientas: **FSB Pro** (escritorio, versión 4.x en 2023), **Expert Advisor
Studio** (web, doc 04) y **Express Generator** (línea de comandos, con un validador multi-mercado en
desarrollo en el foro). El "Forex Strategy Builder" original (no Pro) es **legacy**: el propio optimizador
de FSB Pro se describe como un algoritmo distinto y mejor que el del FSB antiguo.

## 2. Funciones relevantes

| Función | Descripción documentada | ¿Lo tenemos? |
|---|---|---|
| Generator | Genera estrategias y las guarda en una colección; muestra la mejor según el criterio de orden elegido | Sí (motor GA) |
| **Acceptance Criteria** | Requisitos mínimos globales usados por Generator y Optimizer; cada backtest calcula si la estrategia los cumple y la marca visualmente si no | Parcial: restricciones duras + niveles |
| Collections | Conjuntos de estrategias guardados; entrada y salida de herramientas como Multi Tester | Parcial: `disc_strategies` por campaña |
| **Multi Tester** | Re-valida estrategias de una colección o carpeta cambiando fuente de datos, símbolo o periodo, o contra otros criterios de aceptación; escribe el resultado en otra colección | Parcial (`retester.transfer`) |
| Optimizer | Intenta "mejorar" la estrategia según la configuración; recomienda mantener activos los criterios de aceptación; dice no hacer fuerza bruta para evitar sobreajuste | Deliberadamente **no** (optimizer solo meseta) |
| OOS | Porcentaje de datos fuera de muestra configurable en generación y optimización | Sí, más estricto (tres tramos) |

## 3. Colecciones y criterios de aceptación: qué copiar

- **Colecciones como objetos de primera clase**: conjuntos con nombre, que alimentan otras herramientas
  (re-test multi-mercado, cartera, exportación) y guardan el resultado en una colección nueva. Hoy nuestras
  estrategias solo se agrupan por campaña.
- **Criterios de aceptación globales y versionados**: un perfil de umbrales reutilizable en todo el flujo.
  Nosotros tenemos los umbrales repartidos en `engine.yaml` y `levels.py`; convendría un perfil con nombre y
  hash guardado en cada campaña.

## 4. Qué no copiar

- La práctica de usuarios y de la propia documentación de EA Studio de **ajustar los criterios de aceptación
  a partir de una estrategia que gustó** (doc 04): es sesgo de selección.
- El Optimizer que modifica la estrategia tras el descubrimiento sin registrar presupuesto nuevo.
