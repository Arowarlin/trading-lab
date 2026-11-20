# 08 · Arquitectura propuesta (evolución, no reconstrucción)

Todo vive en `src/tradinglab/discovery/`, `config/discovery/` y `data/discovery.db`. Ningún componente
protegido cambia. Ninguna arquitectura paralela.

## A. Mantener (sin cambios)

DSL y compilador; `fastbt` y su paridad; cola y databank; campañas con n_total inmutable y conteo en
`count_tests`; NSGA-II; tramos IS/OOS-1/OOS-2; `confirm` con lectura única; test contra azar en OOS-2;
niveles/veredictos deterministas; optimizer de meseta; perfiles de coste por cuenta.

## B. Mejorar

| Módulo | Cambio | Reutiliza | Tests | Complejidad |
|---|---|---|---|---|
| `robustness._regime` | Años exigidos = años con datos en IS+OOS-1; R→retorno de cuenta | `walkforward` (sin editar) | gate alcanzable con 2021-25 | Baja |
| `genetic` / plantillas | `symmetric`, espejo automático, `locked` por nodo | `dsl.validate` | corto anómalo rechazado | Media |
| `engine` | Reintento de hijos (≤10) | `genetic` | n_total intacto, diagnostics | Baja |
| `databank` | Tablas `disc_collections`, `disc_collection_items`, `disc_tags`, `disc_families`; vista de clones entre campañas | hash AST, correlación diaria | consultas, dedupe | Media |
| `levels` | Nivel 3 exige las pruebas de perturbación; perfil de aceptación con nombre y hash guardado en la campaña | — | nivel 3/4 | Baja |

## C. Incorporar

| Módulo | Objetivo | Referencia | Archivos | Datos | Riesgo | Prioridad |
|---|---|---|---|---|---|---|
| **Perturbation Lab** | Noise Test, retrasos, MC de ejecución | Build Alpha, EA Studio | `discovery/perturb.py`, `tests/test_discovery_perturb.py` | IS+OOS-1, histograma de spread por hora | Calibrar ruido | **P1** |
| Data 1c | M5 de XAUUSD, EURUSD, GBPUSD, USDJPY, US30, GER40 vía attach-only sin `shutdown` | — | `discovery/fetch.py` + CLI | MT5 (solo lectura) | Terminal equivocado → comprobar login | **P1** |
| Colecciones y familias | Organizar, comparar, detectar clones | FSB Pro, EA Studio | ver B | databank | — | P1 |
| Consola Discovery Lab | Ver todo lo anterior | Todas | `web.py`, `webui/index.html` | API | Botones sin función → prohibido | P1 (Fase 8) |
| Multi-market k-de-n | Causa común | EA Studio | `discovery/multimarket.py` | Mercados pre-declarados | Correlación entre mercados | P2 |
| Familias causales | Sweeps de liquidez, rangos de sesión, día previo, calendario/eventos | — | `blocks.py` (añadir), plantillas | Calendario macro (existe en `intel/`) | Más pruebas → DSR | P2 |
| Contraste del simulador de challenge | Validar nuestro MC contra un simulador abierto con reglas citadas | LuxAlgo prop-firm-sim | `scripts/compare_prop_sim.py` | Reglas FTMO/FundingPips | Diferencias de modelo | P2 |
| Reality Check / SPA | Significancia de la frontera completa | Adaptrade (concepto), White/Hansen | `discovery/significance.py` | Retornos de la frontera | Coste de cómputo | P2 (investigar) |
| Export MQL5 | Fase 12 | EA Studio | `discovery/export/` | — | Paridad | P2 |
| Agentes de hipótesis | Fase 9 | — | `discovery/agents/` | LM Studio | Alucinaciones → solo AST validado | P2 |

## D. Descartar

Redes neuronales como condición; resets o reconstrucciones guiadas por OOS; criterios de aceptación
copiados de estrategias vistas; Randomized OOS para seleccionar; equity curve trading en vivo; optimizer que
cambie parámetros fuera de una campaña registrada; proyecciones del futuro (techain).

## E. Investigar después

Barras de rango o tick (requiere datos de tick); microestructura (requiere order book: no disponible en CFD);
relaciones intermercado (US100 vs US500, oro vs USD) con datos ya disponibles; régimen por modelo
(HMM) solo como filtro informativo; MCP de solo lectura.
