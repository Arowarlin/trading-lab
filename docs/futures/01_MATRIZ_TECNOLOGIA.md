# FUT-1 · Matriz tecnológica open-source, licencias y seguridad (Fase 1)

**Fecha:** 2026-11-27 · **Autor:** Claude Code · **Modo:** solo lectura (nada instalado).

## 0. Método y qué está verificado

| Dato | Cómo se obtuvo | Certeza |
|---|---|---|
| Licencia SPDX, archivado, último push, estrellas, lenguaje, issues abiertos | API de búsqueda de GitHub (`search/repositories`, 2026-11-27) | **Confirmado** |
| Licencias `NOASSERTION` | Lectura del fichero `LICENSE` en `raw.githubusercontent.com` | **Confirmado** |
| Repos mal nombrados o inaccesibles | La API devolvió 422 o vacío; búsqueda por nombre para encontrar el real | **Confirmado** |
| hftbacktest: colas L3 y conversor Databento MBO | Clon superficial y `grep` del código (`L3FIFOQueueModel`, `PowerProbQueueFunc3`, `py-hftbacktest/hftbacktest/data/utils/databento.py`) | **Confirmado** |
| databento-python: esquemas | Clon superficial: `Schema.MBO, MBP_1, MBP_10, TBBO, TRADES, BBO_1S/1M, CBBO, CMBP_1, TCBBO, DEFINITION, STATISTICS, STATUS, IMBALANCE, OHLCV_1S/1M/1H/1D/EOD` | **Confirmado** |
| Capacidades funcionales del resto (futuros, L2/L3, live, adaptadores) | Conocimiento previo de su documentación | **No verificado en el código en esta sesión.** Cada decisión "B" exige un PoC que lo confirme |
| Advisories de seguridad, cobertura de tests, rendimiento | No consultados (la API de advisories no está habilitada en esta sesión) | **Sin datos** |

Todo lo descargado se trató como datos no confiables: clones en `scratchpad/dl/`, sin ejecutar nada.

## 1. Decisión en una tabla

**A** adoptar como dependencia · **B** integrar selectivamente (tras PoC) · **C** solo referencia ·
**D** reimplementar conceptos · **E** rechazar.

### A · Backtesting y trading cuantitativo

| Repo | Licencia | Último push | ★ | Leng. | Encaje futuros | Dec. | Motivo |
|---|---|---|---:|---|---|---|---|
| nautechsystems/nautilus_trader | LGPL-3.0 | 2026-11-27 | 31.867 | Rust/Py | Alto (event-driven, libro L1-L3, adaptador Databento) *(No verificado)* | **B** | Segundo motor de alta fidelidad para validar fills; decisión tras benchmark FUT-X1. No sustituye al núcleo |
| QuantConnect/Lean | Apache-2.0 | 2026-11-27 | 22.755 | C# | Alto, pero ligado a datos de QuantConnect | **C** | Solapa con Nautilus; runtime .NET pesado |
| polakowo/vectorbt | Apache-2.0 + **Commons Clause** | 2026-11-11 | 9.967 | Py | Bajo (vectorizado, OHLC) | **C** | Útil para barridos, que es justo lo que se evita; `fastbt` (numba) ya cubre. Commons Clause prohíbe vender |
| nkaz001/hftbacktest | MIT | 2025-12-23 | 5.147 | Rust/Py | **Alto para order flow**: colas L3 FIFO, funciones de probabilidad de cola, latencias, conversor Databento MBO (**Confirmado**) | **B** | El único candidato serio para fills de límites con cola. PoC con un día de MNQ MBO. Actividad más lenta (11 meses) |
| pst-group/pysystemtrade | GPL-3.0 | 2026-11-02 | 3.648 | Py | Alto (futuros, roll calendars, multiple prices) | **D** | Reimplementar sus conceptos de roll y "multiple prices"; GPL impide copiar código |
| kernc/backtesting.py | AGPL-3.0 | 2026-08-05 | 9.308 | Py | Bajo | **E** | Redundante y AGPL |
| stefan-jansen/zipline-reloaded | — | — | — | — | — | **E** | No accesible con ese nombre (la API no lo encuentra); centrado en acciones |
| edtechre/pybroker | Apache-2.0 + **Commons Clause** | 2026-11-27 | 3.729 | Py | Bajo (acciones/ML) | **E** | Fuera de alcance |
| vnpy/vnpy | MIT | 2026-11-11 | 46.525 | Py | Futuros chinos (CTP), no CME | **E** | Pasarelas no aplicables |
| abides-sim/abides | BSD-3 (fichero `LICENSE.txt`) | 2023-07-06 | 605 | Py | Simulación de agentes | **C** | Inactivo desde 2023; referencia para microestructura sintética |

### B · Datos e infraestructura

| Repo | Licencia | Último push | ★ | Dec. | Motivo |
|---|---|---|---:|---|---|
| databento/databento-python | Apache-2.0 | 2026-11-26 | 336 | **A** (cuando se compre L1/L3) | Cliente oficial; decodifica DBN y la simbología (`instrument_id`, `definition`). Hoy `fetch_databento.py` llama a la API con `httpx` y pierde el `instrument_id` (FUT-06) |
| databento/dbn | Apache-2.0 | 2026-11-24 | 201 | **A** (transitiva) | Viene con el cliente |
| duckdb/duckdb | MIT | 2026-11-27 | 43.433 | **B** | Un solo motor nuevo para agregar ticks a footprint/barras de volumen y consultar el catálogo de datasets en Parquet, fuera de memoria. SQL estable: menos errores de un modelo implementador pequeño |
| pola-rs/polars | MIT | 2026-11-27 | 40.547 | **C** | Solapa con DuckDB; API que cambia a menudo. Se reconsidera solo si el benchmark FUT-X2 lo justifica |
| apache/arrow | Apache-2.0 | 2026-11-27 | 17.362 | **A** (ya está: `pyarrow`) | — |
| TA-Lib/ta-lib-python | BSD-2 | 2026-11-27 | 12.436 | **E** | Dependencia nativa; los indicadores ya existen en `indicators*.py` |
| twopirllc/pandas-ta | — | — | — | **E** | **No accesible** (422); existe un fork `xgboosted/pandas-ta-classic`. Riesgo de cadena de suministro |

### C · Order flow y microestructura

| Repo | Licencia | Último push | ★ | Dec. | Motivo |
|---|---|---|---:|---|---|
| c21eservices/openflow | MIT | 2026-09-17 | 3 | **C** | Footprint/DOM en Electron sobre Ironbeam; ideas de UI |
| damraka/CleoLOB | LGPL-3.0 | 2026-10-25 | 4 | **C** | Laboratorio LOB de investigación; muy joven |
| edwincummins/FootprintOrderFlow | MIT | 2025-04-08 | 1 | **C** | Indicador footprint para NT8; estructura de NinjaScript |
| lachlanspangler/OrderBookSim | **sin licencia** | 2026-08-25 | 1 | **E** | Sin licencia = todos los derechos reservados |
| AbhayAbm/Limit-order-book | **sin licencia** | 2026-08-05 | 0 | **E** | Ídem |

### D · Validación estadística y optimización

| Repo | Licencia | Último push | ★ | Dec. | Motivo |
|---|---|---|---:|---|---|
| ranaroussi/quantstats | Apache-2.0 | 2026-11-02 | 7.922 | **A** (ya está) | Solo informes; nunca decide una puerta |
| optuna/optuna | MIT | 2026-11-25 | 15.093 | **A** (ya está) | Solo con prerregistro; nada de barridos libres |
| scipy/scipy | BSD-3 | 2026-11-27 | 15.262 | **A** | Se importa directamente en 4 ficheros pero **no está declarada** (llega por `arch`): declararla |
| statsmodels/statsmodels | BSD-3 | 2026-11-27 | 11.771 | **A** (transitiva) | HAC/Newey-West; declarar si se importa |
| skfolio/skfolio | BSD-3 | 2026-11-27 | 2.678 | **C** | Optimización de carteras de activos; el reparto entre cuentas no es media-varianza |
| dcajasn/Riskfolio-Lib | BSD-3 | 2026-11-04 | 4.626 | **E** | Solapa con skfolio y no hace falta |
| baobach/mlfinpy | MIT | 2026-10-11 | 95 | **D** | Reimplementar purged k-fold con embargo (López de Prado) donde haga falta; proyecto pequeño |
| AgentJDrew/backtest-guard | MIT | 2026-07-06 | 0 | **C** | Oráculo cruzado para DSR/PBO en tests; TradingLab ya los tiene |
| tslearn-team/tslearn | BSD-2 | 2026-11-26 | 3.194 | **E** | Clustering de series: no hay caso de uso |
| ruptures (real: **deepcharles/ruptures**) | BSD-2 | 2026-10-06 | 2.122 | **C** | La URL `ruptures-dev/ruptures` no existe. Cambio de régimen: reconsiderar en el análisis de regímenes |

### E · Ingeniería de datos y seguimiento de experimentos

| Repo | Licencia | Último push | ★ | Dec. | Motivo |
|---|---|---|---:|---|---|
| mlflow/mlflow | Apache-2.0 | 2026-11-27 | 28.998 | **C** | El registro propio (`tl3_research.db`, `discovery.db`, `count_tests`) es específico del dominio; MLflow duplicaría y no conoce el contador del DSR |
| dvc (real: **treeverse/dvc**) | Apache-2.0 | 2026-11-24 | 16.002 | **D** | La URL `iterative/dvc` ya no resuelve. Basta con hashes SHA-256 por fichero en el manifiesto (ya se hace en `SEAL.md`) |
| ray-project/ray | Apache-2.0 | 2026-11-27 | 44.394 | **E** | Una máquina de 16 núcleos: `multiprocessing` + numba bastan |
| dask/dask | BSD-3 | 2026-11-26 | 13.960 | **E** | DuckDB cubre el fuera-de-memoria |
| PrefectHQ/prefect | Apache-2.0 | 2026-11-27 | 24.253 | **E** | El Programador de Windows ya orquesta; otro servidor sería deuda |
| pandera (real: **unionai-oss/pandera**) | MIT | 2026-11-24 | 4.539 | **C** | La URL `pydantic/pandera` no existe. `discovery/data_quality.py` (1.036 líneas) ya valida; no duplicar |
| great_expectations (real: **fivetran/great_expectations**) | Apache-2.0 | 2026-11-17 | 11.953 | **E** | Movido de organización; pesado para una sola máquina |

### F · IA y multiagente

| Repo | Licencia | Último push | ★ | Dec. | Motivo |
|---|---|---|---:|---|---|
| TauricResearch/TradingAgents | Apache-2.0 | 2026-11-25 | 123.934 | **E** (para futuros) | Centrado en análisis de acciones; el lenguaje principal del repo es ahora **TypeScript**, así que el `vendor/` Python del operador puede divergir. Se congela como legado |
| TauricResearch/Trading-R1 | Apache-2.0 | 2026-11-25 | 783 | **E** | Modelo afinado para acciones; GPU AMD en Windows con soporte ROCm limitado *(No verificado)* |
| AI4Finance-Foundation/FinRobot | Apache-2.0 | 2026-10-24 | 8.491 | **E** | Investigación de acciones (DCF/comps) |
| AI4Finance-Foundation/FinRL | MIT | 2026-11-27 | 17.195 | **E** | RL con alto riesgo de sobreajuste; sin hipótesis económica |
| virattt/ai-hedge-fund | MIT | 2026-11-09 | 64.875 | **E** | Agentes de acciones |
| langchain-ai/langgraph | MIT | 2026-11-26 | 45.514 | **C** | Los subagentes de Claude Code cubren la orquestación; solo si se monta una canalización local con LM Studio |
| pydantic/pydantic-ai | MIT | 2026-11-27 | 21.431 | **C** | Candidato si se crea un agente local tipado contra LM Studio (pydantic ya es dependencia) |
| BerriAI/litellm | MIT (salvo `enterprise/`) | 2026-11-27 | 64.038 | **E** | LM Studio ya expone una API compatible; un gateway añade superficie de ataque |

### G · Ingeniería, seguridad y tests

| Repo | Licencia | Último push | ★ | Dec. | Motivo |
|---|---|---|---:|---|---|
| pytest-dev/pytest | MIT | 2026-11-27 | 14.775 | **A** (ya está) | — |
| astral-sh/ruff | MIT | 2026-11-27 | 51.562 | **A** (ya está) | Activar reglas `S` (bandit) solo en los paquetes nuevos |
| HypothesisWorks/hypothesis | MPL-2.0 (fichero `LICENSE.txt`) | 2026-11-27 | 9.264 | **A** (dev) | Tests de propiedades para el motor de reglas (el umbral trailing nunca baja, identidades contables). Alto valor, coste bajo |
| pytest-dev/pytest-cov | MIT | 2026-10-18 | 2.083 | **A** (dev) | Cobertura de los paquetes nuevos |
| microsoft/pyright | MIT | 2026-11-27 | 15.766 | **B** (dev) | Tipos solo en `futures/` y `prop_economics/` (modo `basic`). El wrapper de PyPI descarga Node: instalar una vez y fijar versión |
| PyCQA/bandit | Apache-2.0 | 2026-11-09 | 8.409 | **E** | Duplica las reglas `S` de ruff |
| semgrep/semgrep | LGPL-2.1 | 2026-11-27 | 18.019 | **C** | Pesado para el tamaño del equipo |
| trufflesecurity/trufflehog | AGPL-3.0 | 2026-11-25 | 29.746 | **B** (herramienta externa) | Escaneo de secretos en pre-commit/CI con `--no-verification` (si verifica, envía el secreto al proveedor). Como binario, el AGPL no contamina el código |
| microsoft/playwright | Apache-2.0 | 2026-11-27 | 101.204 | **C** → B con el dashboard | Ya viene con el entorno en la nube; e2e de la consola cuando se toque |

### H · Catálogos (solo descubrimiento)

`WallStreetPete/awesome-open-source-trading` (CC0-1.0, 53 ★), `ethanstoner/awesome-claude-code`
(MIT, 0 ★, sin actividad desde 2026-04-09), `omgits0mar/awesome-claude-code-extensions` (CC0-1.0, 5 ★),
`ianwieds/awesome-claude-code` (CC0-1.0, 2 ★). Decisión **C**. El catálogo de trading tiene muy pocos
proyectos de futuros CME (ver §4).

## 2. Licencias y seguridad

| Riesgo | Repos | Regla para TradingLab |
|---|---|---|
| Copyleft fuerte (GPL/AGPL) | pysystemtrade, backtesting.py, trufflehog, Serena (aplicación GPL-3.0) | No copiar código. Herramientas externas sí (no se enlazan) |
| Copyleft débil (LGPL/MPL) | nautilus_trader, CleoLOB, semgrep, hypothesis | Uso como dependencia sin modificar: aceptable. Si se modifica, publicar la modificación de esa librería |
| **Commons Clause** | vectorbt, pybroker | Prohíbe "vender" el software o un servicio basado en él. Evitar en el núcleo |
| **Sin licencia** | OrderBookSim, Limit-order-book y varios descubiertos (§4) | No reutilizar código |
| Ejecución remota sin fijar versión | `npx @playwright/mcp@latest`, `uvx --from git+https://github.com/oraios/serena` (manifiestos oficiales) | Fijar versión antes de instalar (ver `02_EXTENSIONES_CLAUDE_CODE.md`) |
| Herramientas que envían datos fuera | trufflehog en modo verificación; MCP remotos (Context7, GitHub) | `--no-verification`; no enviar código ni datos del laboratorio a servicios de terceros sin decisión explícita |
| Repos movidos/renombrados | dvc, pandera, great_expectations, ruptures, everything-claude-code | Fijar la URL real en la documentación; un nombre que cambia de dueño es un vector de cadena de suministro |

TradingLab **no tiene fichero de licencia** en la raíz (Confirmado): hoy es código privado. Las
obligaciones de GPL/AGPL se activan al distribuir; aun así, mezclar ese código cerraría opciones futuras.

## 3. Pila mínima recomendada

| Capa | Hoy | Recomendado | Estado |
|---|---|---|---|
| Núcleo de datos | pandas 3.1.1, numpy 2.5.4, pyarrow 26 | igual | mantener |
| Rendimiento | numba (extra `discovery`) | igual | mantener |
| Estadística | arch, scipy (sin declarar), optuna, quantstats | **declarar `scipy`** | pendiente de aprobación |
| Datos de futuros | `httpx` contra la API de Databento | **`databento` oficial** al comprar L1/L3 | pendiente (FUT-B2) |
| Ticks / footprint | — | **DuckDB** | PoC FUT-X2 |
| Fills con cola (Research A) | — | **hftbacktest** en un extra aislado `microstructure` | PoC FUT-X3 |
| Motor de alta fidelidad | `fastbt` propio | **NautilusTrader** solo en un venv de benchmark | PoC FUT-X1 |
| Tests | pytest, ruff | **+ hypothesis, pytest-cov** (dev) | pendiente de aprobación |
| Tipos | — | pyright en modo `basic` solo en paquetes nuevos | opcional |
| Secretos | — | trufflehog `--no-verification` en pre-commit | pendiente de aprobación |
| **Quitar** | `alpaca-py` declarado y **sin ningún import** en `src/` (Confirmado); carril de acciones archivado | eliminar del `pyproject.toml` | pendiente de aprobación |

Regla: **una herramienta por problema**. DuckDB y no Polars+Dask; Nautilus y no LEAN; registro propio y
no MLflow.

## 4. Proyectos adicionales descubiertos (búsqueda en GitHub, 2026-11-27)

| Repo | Licencia | Último push | ★ | Qué es | Dec. |
|---|---|---|---:|---|---|
| ChristianJStarr/projectx-sdk-python | MIT | 2025-06-05 | 4 | SDK no oficial de ProjectX Gateway | C (la API oficial manda) |
| SharurTrading/projectx-rs | MIT-0 | 2026-11-27 | 3 | Cliente Rust no oficial de ProjectX | C |
| antonio-hickey/TradovatePy | MIT | 2025-07-13 | 45 | Wrapper Python de la API de Tradovate | C |
| tradovate/example-api-js | sin licencia | 2026-05-02 | 56 | Ejemplos de la organización Tradovate | C (documentación de facto) |
| tbraman-dev/ninjatrader-to-parquet | NOASSERTION | 2026-09-27 | 11 | Lee históricos `.ncd` de NT8 | C (licencia por aclarar) |
| Quantrosoft/PythonForNinjaTrader | MIT | 2026-04-27 | 2 | Estrategias NT8 en Python | C |
| murtazayusuf/OrderflowChart | Apache-2.0 | 2026-11-01 | 270 | Footprint con plotly | C (visualización del dashboard) |
| edgedepthhq/edgedepth-terminal | AGPL-3.0 | 2026-10-18 | 32 | Terminal order flow C++/WASM | E (AGPL) |
| gabrielee5/prop-firm-simulator | MIT | 2026-03-14 | 2 | Análisis de retos de prop firms | C (contraste de resultados) |
| shurugiken/prop-firm-eval-simulator | MIT | 2026-06-21 | 2 | MC de evaluaciones de futuros (Apex/TopStep/Lucid) | C (contraste de resultados) |
| fesrr/propguard | MIT | 2026-11-13 | 1 | Motor de cumplimiento y MC sin dependencias | C |
| vchernoy/mbo-orderbook | sin licencia | 2025-11-25 | 2 | Reconstrucción de libro MBO desde DBN | E (sin licencia) |
| herphay/Orderbook_building | GPL-3.0 | 2026-10-22 | 0 | Libro desde BBO de Databento | E |

**Conclusión:** no existe un simulador de prop firms de futuros maduro (todos ≤ 33 ★, sin tests visibles,
reglas sin fecha ni fuente). El motor EV se construye **nativo**; estos repos solo sirven para contrastar
cifras.

## 5. PoC que exige cada decisión "B"

| ID | PoC | Mide | Datos | Aprobación |
|---|---|---|---|---|
| FUT-X1 | `fastbt` vs NautilusTrader con la misma estrategia, contrato, sesión, costes y fills | paridad de operaciones, runtime, RAM | NQ M1 2010-2011 (ya en el equipo) | **Sí** (instala Nautilus en un venv aparte) |
| FUT-X2 | Barras footprint desde `trades`: DuckDB vs pandas | runtime, RAM, igualdad bit a bit | 1 semana de MNQ `trades` (compra mínima o muestra gratuita) | **Sí** |
| FUT-X3 | Fill de límites con cola: hftbacktest vs regla "trade-through 1 tick" | tasa de fill, P&L por operación | 1 día de MNQ MBO | **Sí** (descarga de pago) |
