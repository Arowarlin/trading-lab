# 05 · Matriz comparativa

Leyenda: **D** disponible · **P** parcial · **ND** no documentado · **NO** no disponible · **NA** no aplicable.
"D" significa documentado públicamente, no que la implementación sea equivalente a la nuestra.

| Funcionalidad | Build Alpha | Adaptrade | ForexSB (FSB Pro) | EA Studio | **TradingLab (f7b)** |
|---|---|---|---|---|---|
| Generación automática | D | D | D | D | D |
| Genetic Algorithm | ND (detalle) | D (programación genética) | ND (detalle) | ND (detalle) | D (NSGA-II propio) |
| Genetic Programming (árboles) | ND | D | ND | ND | D (AST) |
| Strategy Builder | D | D | D | D | P (DSL, sin editor visual) |
| Biblioteca de señales | D (>5.000) | D (>100 métricas; indicadores) | D | D | P (~30 bloques) |
| Custom indicators | ND | D | D | ND | P (código Python) |
| Fitness multiobjetivo | D (función de fitness) | D (suma ponderada + condiciones) | P (criterio de orden) | P | D (Pareto, 5 objetivos) |
| Optimizer | D | D | D | D | P (solo meseta, a propósito) |
| Out-of-Sample | D | D | D | D | D (IS / OOS-1 / OOS-2 sellado) |
| Monte Carlo | D (equity) | D (stress) | ND | D (mercado + ejecución) | P (orden de operaciones) |
| Noise testing | D | ND | ND | P (variaciones de mercado) | NO |
| Vs Random | D | NO (usa significancia) | NO | NO | D (en OOS-2) |
| Walk Forward | ND | ND | ND | ND | D |
| Multi Market | D | D (varias series) | D (Multi Tester) | D | P (transfer informativo) |
| Análisis de cartera | D | ND | D | D | P (legado) |
| Matriz de correlación | D | ND | ND | ND | P |
| Colecciones | ND | P | D | D | P (por campaña) |
| Editor de estrategias | D | D (Adaptrade Editor) | D | D | NO |
| Simulación prop firm | ND (no verificado) | NO | NO | NO | D (MC por cuenta) |
| Exportación de código | D | D | D | D (MQL4/5) | NO (Fase 12) |
| Integración IA | ND | NO | NO | NO | P (diseño; Fase 9) |
| Automatización (pipelines) | D (workflows) | P | P | D (Reactor/Validator) | P (CLI) |
| **Contador global de pruebas / DSR** | ND | P (test de significancia) | NO | NO | **D** |
| **PBO** | ND | ND | NO | NO | **D** |
| **Holdout sellado de una lectura** | NO documentado | NO | NO | NO | **D** |

## Mejores ideas por producto

| Producto | Lo mejor | Prioridad para nosotros |
|---|---|---|
| Build Alpha | Noise Test, entradas/salidas retrasadas, filtros de robustez dentro del flujo, multi-mercado | **P1** |
| Adaptrade | Condiciones vs objetivos, bloqueo de partes, seguimiento por generación; su enfoque de "inferencia estadística" | P2 |
| FSB Pro | Colecciones como objetos y perfiles de criterios de aceptación reutilizables | P1–P2 |
| EA Studio | Monte Carlo de ejecución/mercado, Reactor/Validator en cadena, "pasa en k de n mercados" | **P1** |

**Conclusión de la matriz:** las plataformas comerciales nos superan en **amplitud** (señales, editor,
exportación, automatización) y en **pruebas de perturbación**; TradingLab ya las supera en **rigor
estadístico** (contador global, DSR, PBO, OOS sellado, test contra el azar sin sesgo de selección). La
estrategia correcta es tomar sus pruebas de perturbación y su organización, **no** su forma de usar el OOS.
